"""
PhoneIdentityResolver — Sprint A.

Resolve um telefone cru para uma PaladinoIdentity GLOBAL (cross-tenant),
criando a identidade se não existir, e garante o Customer tenant-scoped
via resolve_for_tenant().

Normalização: manual para BR (sem dependência de phonenumbers — decisão
registrada: a lib não insere o 9º dígito de celulares antigos, regra que
o projeto já aplica em customers/service.normalize_phone; manter a mesma
semântica evita identidades duplicadas para o mesmo número).

Regra da visão: DDD OBRIGATÓRIO — telefone sem DDD → HTTP 422.

Formatos produzidos:
  phone_e164                 → "+5562988887777"  (E.164 com '+')
  phone_national_normalized  → "62988887777"     (DDD + local com 9)
  Customer.phone continua    → "5562988887777"   (convenção existente, sem '+')
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Customer, PaladinoIdentity

logger = logging.getLogger(__name__)


@dataclass
class ResolveResult:
    identity_id: UUID
    phone_e164: str
    phone_national_normalized: str
    is_new_identity: bool


def normalize_phone_e164(raw_phone: str, default_country: str = "BR") -> tuple[str, str]:
    """
    Normaliza telefone BR para E.164. Retorna (phone_e164, phone_national).

    Regras (mesma semântica de customers/service.normalize_phone, porém
    ESTRITA — DDD obrigatório):
      1. Remove tudo que não é dígito.
      2. 12/13 dígitos começando com 55 → DDI já presente.
         10/11 dígitos → nacional com DDD, prefixa 55.
         Qualquer outro tamanho → 422 (sem DDD ou formato inválido).
      3. Com 12 dígitos (55 + DDD + 8): local iniciando em 2/3/4 → fixo,
         mantém; senão → celular sem o 9, insere o 9 após o DDD.
    """
    if default_country != "BR":
        raise HTTPException(
            status_code=422,
            detail=f"País não suportado pelo resolver: {default_country}",
        )

    digits = re.sub(r"\D", "", raw_phone or "")

    # Tratar leading zero (hábito brasileiro de discagem interurbana)
    # Ex.: "062..." → "62...", "0062..." → ignorar (pode ser DDI internacional)
    if digits.startswith("0") and not digits.startswith("00"):
        digits = digits[1:]

    if len(digits) in (12, 13) and digits.startswith("55"):
        pass  # DDI 55 presente
    elif len(digits) in (10, 11):
        digits = "55" + digits
    else:
        raise HTTPException(
            status_code=422,
            detail="Telefone inválido — informe DDD + número (ex.: 62 98888-7777)",
        )

    ddd = digits[2:4]
    if ddd[0] == "0":
        raise HTTPException(status_code=422, detail="DDD inválido")

    if len(digits) == 12:
        local_first = digits[4]
        if local_first not in ("2", "3", "4"):
            # Celular sem o 9 — insere após o DDD
            digits = digits[:4] + "9" + digits[4:]

    phone_e164 = f"+{digits}"
    phone_national = digits[2:]
    return phone_e164, phone_national


class PhoneIdentityResolver:

    def resolve(
        self,
        db: Session,
        raw_phone: str,
        default_country: str = "BR",
        name: Optional[str] = None,
    ) -> ResolveResult:
        """
        Normaliza para E.164 (DDD obrigatório — 422 se ausente), busca a
        PaladinoIdentity global por phone_e164 e cria se não existir.
        Idempotente: a segunda chamada retorna a identidade existente.
        """
        phone_e164, phone_national = normalize_phone_e164(raw_phone, default_country)

        identity = (
            db.query(PaladinoIdentity)
            .filter(PaladinoIdentity.phone_e164 == phone_e164)
            .first()
        )
        if identity:
            self._register_alias(db, identity, raw_phone, phone_e164)
            if name and not identity.name:
                identity.name = name
                db.commit()
            return ResolveResult(
                identity_id=identity.id,
                phone_e164=phone_e164,
                phone_national_normalized=phone_national,
                is_new_identity=False,
            )

        identity = PaladinoIdentity(
            phone_e164=phone_e164,
            phone_national_normalized=phone_national,
            possible_aliases=[],
            name=name,
        )
        db.add(identity)
        try:
            db.commit()
            db.refresh(identity)
            is_new = True
        except IntegrityError:
            # Race: outra request criou a mesma identity entre SELECT e INSERT
            db.rollback()
            logger.warning(
                "PhoneIdentityResolver: IntegrityError (race) — retrying SELECT "
                "phone_e164=%s", phone_e164,
            )
            identity = (
                db.query(PaladinoIdentity)
                .filter(PaladinoIdentity.phone_e164 == phone_e164)
                .first()
            )
            if not identity:
                raise
            is_new = False

        return ResolveResult(
            identity_id=identity.id,
            phone_e164=phone_e164,
            phone_national_normalized=phone_national,
            is_new_identity=is_new,
        )

    def resolve_for_tenant(
        self,
        db: Session,
        raw_phone: str,
        company_id: UUID,
        default_country: str = "BR",
        name: Optional[str] = None,
    ) -> tuple[Customer, bool]:
        """
        Resolve identidade global + garante Customer para o tenant.
        Retorna (customer, is_new_customer).

        - Customer inexistente para (company_id, telefone) → cria com
          identity_id preenchido.
        - Customer existente com identity_id NULL → vincula (lazy backfill).
        """
        # Lazy import — customers/service também importa este módulo
        from app.modules.customers import service as customer_svc

        result = self.resolve(db, raw_phone, default_country, name=name)

        customer = customer_svc._find_by_phone_smart(db, company_id, raw_phone)
        if customer:
            if customer.identity_id is None:
                customer.identity_id = result.identity_id
                db.commit()
            return customer, False

        customer_name = name or "Cliente"
        # Convenção existente: customers.phone sem o '+'
        normalized_no_plus = result.phone_e164.lstrip("+")
        try:
            customer = Customer(
                company_id=company_id,
                name=customer_name,
                phone=normalized_no_plus,
                identity_id=result.identity_id,
            )
            db.add(customer)
            db.commit()
            db.refresh(customer)
            return customer, True
        except IntegrityError:
            db.rollback()
            logger.warning(
                "resolve_for_tenant: IntegrityError (race) — retrying SELECT. "
                "company_id=%s phone=%s", company_id, normalized_no_plus,
            )
            customer = customer_svc._find_by_phone_smart(db, company_id, raw_phone)
            if customer:
                if customer.identity_id is None:
                    customer.identity_id = result.identity_id
                    db.commit()
                return customer, False
            raise

    def _register_alias(
        self, db: Session, identity: PaladinoIdentity, raw_phone: str, phone_e164: str
    ) -> None:
        """Registra variação crua que difere da forma canônica (ex.: sem o 9)."""
        raw_digits = re.sub(r"\D", "", raw_phone or "")
        canonical_digits = phone_e164.lstrip("+")
        if not raw_digits or raw_digits == canonical_digits:
            return
        aliases = list(identity.possible_aliases or [])
        if raw_digits not in aliases:
            aliases.append(raw_digits)
            identity.possible_aliases = aliases
            db.commit()


resolver = PhoneIdentityResolver()

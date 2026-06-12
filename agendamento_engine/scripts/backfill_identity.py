"""
Backfill de PaladinoIdentity para customers existentes — Sprint A.

NÃO roda na migration (volume pode ser alto; migrations devem ser rápidas).
Executar em janela de manutenção, após o deploy das migrations e0sA1–e0sA3:

    .\\venv\\Scripts\\python.exe -m scripts.backfill_identity [--dry-run]

Comportamento:
  1. Agrupa customers (identity_id IS NULL) por telefone E.164 canônico —
     a normalização insere o 9º dígito, então variações com/sem 9 do mesmo
     número caem no MESMO grupo (mesma identity cross-tenant).
  2. Para cada grupo: busca/cria PaladinoIdentity e seta customer.identity_id.
  3. Colisões de nome (mesmo E.164, nomes divergentes): usa o nome mais
     recente (updated_at maior) na identity e registra a colisão em
     backfill_collision_report.csv para revisão manual (não bloqueia).
  4. Telefone não normalizável (sem DDD/formato inválido): pulado e
     registrado no relatório com motivo INVALID_PHONE.

Idempotente: re-executar não duplica identidades (lookup por phone_e164
UNIQUE) nem sobrescreve identity_id já preenchido.
"""
import argparse
import csv
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException

from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.models import Customer, PaladinoIdentity
from app.modules.identity.resolver import normalize_phone_e164

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_identity")

REPORT_FILE = "backfill_collision_report.csv"


def run(dry_run: bool = False) -> dict:
    db = SessionLocal()
    stats = {
        "customers_scanned": 0,
        "identities_created": 0,
        "identities_reused": 0,
        "customers_linked": 0,
        "skipped_invalid_phone": 0,
        "name_collisions": 0,
    }
    report_rows: list[dict] = []

    try:
        customers = (
            db.query(Customer)
            .filter(Customer.identity_id.is_(None))
            .order_by(Customer.id)
            .all()
        )
        stats["customers_scanned"] = len(customers)
        logger.info("Customers sem identity: %d", len(customers))

        # 1. Agrupar por E.164 canônico
        groups: dict[str, list[Customer]] = defaultdict(list)
        for c in customers:
            try:
                phone_e164, _ = normalize_phone_e164(c.phone)
            except HTTPException as exc:
                stats["skipped_invalid_phone"] += 1
                report_rows.append({
                    "type": "INVALID_PHONE",
                    "phone_e164": "",
                    "customer_id": str(c.id),
                    "company_id": str(c.company_id),
                    "name": c.name,
                    "detail": f"phone={c.phone!r}: {exc.detail}",
                })
                continue
            groups[phone_e164].append(c)

        # 2. Resolver identity por grupo
        for phone_e164, members in groups.items():
            _, phone_national = normalize_phone_e164(phone_e164)

            identity = (
                db.query(PaladinoIdentity)
                .filter(PaladinoIdentity.phone_e164 == phone_e164)
                .first()
            )

            # Colisão de nome: nomes divergentes no mesmo E.164 → usa o mais
            # recente (updated_at maior); demais vão para o relatório
            names = {m.name.strip() for m in members if m.name}
            chosen = max(
                members,
                key=lambda m: m.updated_at or datetime.min.replace(tzinfo=timezone.utc),
            )
            if len(names) > 1:
                stats["name_collisions"] += 1
                for m in members:
                    report_rows.append({
                        "type": "NAME_COLLISION",
                        "phone_e164": phone_e164,
                        "customer_id": str(m.id),
                        "company_id": str(m.company_id),
                        "name": m.name,
                        "detail": f"nome escolhido: {chosen.name!r} "
                                  f"(updated_at={chosen.updated_at})",
                    })

            if identity is None:
                identity = PaladinoIdentity(
                    phone_e164=phone_e164,
                    phone_national_normalized=phone_national,
                    possible_aliases=sorted(
                        {m.phone for m in members if m.phone != phone_e164.lstrip("+")}
                    ),
                    name=chosen.name,
                )
                db.add(identity)
                db.flush()  # garante identity.id sem commit por grupo
                stats["identities_created"] += 1
            else:
                stats["identities_reused"] += 1

            for m in members:
                m.identity_id = identity.id
                stats["customers_linked"] += 1

        if dry_run:
            db.rollback()
            logger.info("DRY-RUN: rollback executado — nada persistido")
        else:
            db.commit()
            logger.info("Commit executado")

        # 3. Relatório de colisões/skips
        if report_rows:
            with open(REPORT_FILE, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "type", "phone_e164", "customer_id",
                        "company_id", "name", "detail",
                    ],
                )
                writer.writeheader()
                writer.writerows(report_rows)
            logger.info("Relatório gravado: %s (%d linhas)", REPORT_FILE, len(report_rows))

        logger.info("Stats: %s", stats)
        return stats
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill PaladinoIdentity")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="executa tudo e faz rollback no final (nada persistido)",
    )
    args = parser.parse_args()
    result = run(dry_run=args.dry_run)
    sys.exit(0)

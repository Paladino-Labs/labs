"""Routers do módulo Payments — Sprints 8 + 9 + 11 + PagSeguro Point.

Endpoints Sprint 8:
    GET    /payment-sources
    POST   /payment-sources            OWNER/ADMIN
    DELETE /payment-sources/{id}       OWNER/ADMIN
    POST   /payments/webhook/asaas/account_status   token asaas-access-token (fail-closed)
    GET    /financial/settings         OWNER/ADMIN

Endpoints Sprint 9:
    POST   /payments
    GET    /payments                   OWNER/ADMIN
    GET    /payments/{id}
    POST   /payments/{id}/refund       OWNER/ADMIN + reason enum
    POST   /payments/webhook/asaas/transaction   token asaas-access-token (fail-closed)
    GET    /deposit-policies           OWNER/ADMIN
    POST   /deposit-policies           OWNER/ADMIN
    PUT    /deposit-policies/{id}      OWNER/ADMIN

Endpoints Sprint 11:
    POST   /payments/{id}/confirm-manual   OWNER/ADMIN — CASH/manual apenas

Endpoints PagSeguro Point:
    GET    /payments/terminals         OWNER/ADMIN
      Retorna lista de terminais Point disponíveis para o tenant.
      Requer IntegrationCredential provider=PAGSEGURO ativa.
      Retorna [] se o provider ativo não for PagSeguroProvider.
"""
import hmac
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_company_id, get_current_user, require_role
from app.infrastructure.db.models.account import Account
from app.infrastructure.db.models.company import Company
from app.infrastructure.db.models.payment_source import PaymentSource
from app.infrastructure.db.session import get_db
from app.modules.payments import service as payment_service
from app.modules.payments.schemas import (
    ConfirmManualRequest,
    ConfirmManualResponse,
    ManualDiscountRequest,
    DepositPolicyCreate,
    DepositPolicyResponse,
    DepositPolicyUpdate,
    FeeWarning,
    FinancialSettingsResponse,
    PaymentCreate,
    PaymentResponse,
    PaymentSourceCreate,
    PaymentSourceResponse,
    RefundRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])
financial_router = APIRouter(prefix="/financial", tags=["financial"])

_owner_admin = require_role("OWNER", "ADMIN", "PLATFORM_OWNER")


# ── Payment Sources ───────────────────────────────────────────────────────────

@router.get("/payment-sources", response_model=list[PaymentSourceResponse])
def list_payment_sources(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return (
        db.query(PaymentSource)
        .filter(PaymentSource.company_id == company_id, PaymentSource.is_active == True)
        .all()
    )


@router.post("/payment-sources", response_model=PaymentSourceResponse, status_code=201)
def create_payment_source(
    body: PaymentSourceCreate,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    if body.type not in ("CARD_CREDIT", "CARD_DEBIT"):
        raise HTTPException(
            status_code=422,
            detail="type deve ser CARD_CREDIT ou CARD_DEBIT. PIX/BOLETO/CASH não são PaymentSources.",
        )
    ps = PaymentSource(company_id=user.company_id, **body.model_dump())
    db.add(ps)
    db.commit()
    db.refresh(ps)
    return ps


@router.delete("/payment-sources/{source_id}", status_code=204)
def delete_payment_source(
    source_id: UUID,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    ps = (
        db.query(PaymentSource)
        .filter(
            PaymentSource.source_id == source_id,
            PaymentSource.company_id == user.company_id,
        )
        .first()
    )
    if not ps:
        raise HTTPException(status_code=404, detail="PaymentSource não encontrada")
    ps.is_active = False
    db.commit()


# ── Payments ──────────────────────────────────────────────────────────────────

@router.post("/payments", response_model=PaymentResponse, status_code=201)
def create_payment(
    body: PaymentCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return payment_service.create_payment(
        company_id=user.company_id,
        customer_id=body.customer_id,
        gross_amount=body.gross_amount,
        payment_method=body.payment_method,
        payment_submethod=body.payment_submethod,
        provider=body.provider,
        target_account_id=body.target_account_id,
        appointment_id=body.appointment_id,
        payment_source_id=body.payment_source_id,
        customer_cpf_cnpj=body.customer_cpf_cnpj,
        due_date=body.due_date,
        coupon_code=body.coupon_code,
        db=db,
    )


@router.get("/payments", response_model=list[PaymentResponse])
def list_payments(
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return payment_service.list_payments(company_id=user.company_id, db=db)


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: UUID,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return payment_service.get_payment(
        payment_id=payment_id,
        company_id=user.company_id,
        db=db,
    )


@router.post("/payments/{payment_id}/confirm-manual", response_model=ConfirmManualResponse)
def confirm_manual_payment(
    payment_id: UUID,
    body: Optional[ConfirmManualRequest] = None,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    payment, fee_warning_data = payment_service.confirm_manual(
        payment_id=payment_id,
        company_id=user.company_id,
        db=db,
        payment_submethod=body.payment_submethod if body else None,
    )
    response = ConfirmManualResponse.model_validate(payment)
    if fee_warning_data:
        response = response.model_copy(update={"fee_warning": FeeWarning(**fee_warning_data)})
    return response


@router.post("/payments/{payment_id}/manual-discount", response_model=PaymentResponse)
def manual_discount_payment(
    payment_id: UUID,
    body: ManualDiscountRequest,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    """Desconto manual auditado (Sprint 16) — OWNER/ADMIN apenas.

    reason obrigatório; registra DiscountApplication manual (promotion_id=None),
    incrementa manual_override_count e audita via record_sensitive_action.
    """
    return payment_service.apply_manual_discount(
        payment_id=payment_id,
        company_id=user.company_id,
        discount_amount=body.discount_amount,
        reason=body.reason,
        actor_id=user.id,
        db=db,
        actor_role=user.role,
    )


@router.post("/payments/{payment_id}/refund", response_model=PaymentResponse)
def refund_payment(
    payment_id: UUID,
    body: RefundRequest,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    if body.force_local and user.role not in ("OWNER", "PLATFORM_OWNER"):
        raise HTTPException(
            status_code=403,
            detail="force_local restrito a OWNER",
        )
    return payment_service.refund(
        payment_id=payment_id,
        reason=body.reason,
        actor_id=user.id,
        company_id=user.company_id,
        db=db,
        force_local=body.force_local,
        actor_role=user.role,
    )


# ── Webhooks Asaas — autenticação compartilhada ──────────────────────────────

def _require_asaas_webhook_token(
    received: str,
    *,
    endpoint: str,
    event: str,
    client_host: str,
) -> None:
    """Valida o header asaas-access-token contra ASAAS_WEBHOOK_TOKEN.

    Fail-closed: sem token configurado no ambiente, TODA requisição é rejeitada
    (falha nossa de config — logada como ERROR porque bloqueia webhooks legítimos
    até alguém agir). Header ausente, vazio ou errado caem no MESMO 401 com o
    mesmo detail — distinguir os casos daria oráculo a quem sonda o endpoint.
    Comparação em tempo constante; o token recebido nunca vai para o log.
    """
    expected = settings.ASAAS_WEBHOOK_TOKEN.strip()
    if not expected:
        logger.error(
            "asaas_webhook_auth: ASAAS_WEBHOOK_TOKEN não configurado — webhooks "
            "Asaas rejeitarão todas as requisições (endpoint=%s event=%s origin=%s)",
            endpoint, event, client_host,
        )
        raise HTTPException(status_code=401, detail="Token de webhook inválido")
    if not hmac.compare_digest(received.encode(), expected.encode()):
        logger.warning(
            "asaas_webhook_auth: token inválido endpoint=%s event=%s origin=%s "
            "token_len=%d",
            endpoint, event, client_host, len(received),
        )
        raise HTTPException(status_code=401, detail="Token de webhook inválido")


# ── Webhook Asaas — transaction ───────────────────────────────────────────────

@router.post("/payments/webhook/asaas/transaction")
def webhook_asaas_transaction(
    payload: dict,
    request: Request = None,
    asaas_access_token: str = Header(default="", alias="asaas-access-token"),
    db: Session = Depends(get_db),
):
    """Público na rede, autenticado por token estático (asaas-access-token).

    Contrato de resposta (o Asaas decide retry pelo STATUS HTTP, nunca pelo corpo):
      - 401 → token ausente/errado ou não configurado no ambiente — evento NÃO
              processado; o Asaas reenfileira, então problema de config aparece
              em vez de sumir evento legítimo em silêncio.
      - 200 → evento consumido ou reconhecidamente não-acionável (retry não ajudaria).
      - 503 → Payment ainda não visível no banco (corrida webhook × commit) — reenviar.
      - 500 → confirm() falhou (ex.: violação de integridade no Financial Core) — reenviar.

    Idempotência garantida dentro de confirm().
    """
    _require_asaas_webhook_token(
        asaas_access_token,
        endpoint="transaction",
        event=payload.get("event", ""),
        client_host=(request.client.host if request is not None and request.client else "?"),
    )

    event_id = payload.get("id") or payload.get("event_id")
    if not event_id:
        # Payload malformado/não-nosso: o reenvio traria o MESMO payload sem id —
        # retry não resolve, logo 200 (skip) é a resposta correta.
        logger.warning("asaas_webhook_transaction: payload sem id event_payload=%s",
                       list(payload.keys()))
        return {"ok": True, "skipped": "missing_event_id"}

    # Gate de tipo de evento: só eventos de confirmação de pagamento acionam
    # confirm(). Antes deste gate, QUALQUER evento (PAYMENT_CREATED,
    # PAYMENT_OVERDUE, ...) confirmava o Payment. Também evita que o 503 do
    # payment_not_found abaixo prenda a fila de retry do Asaas com eventos
    # irrelevantes de cobranças desconhecidas.
    event_type = payload.get("event", "")
    if event_type not in ("PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"):
        logger.info("asaas_webhook_transaction: evento não-acionável event_id=%s event=%s",
                    event_id, event_type)
        return {"ok": True, "skipped": "event_not_handled", "event": event_type}

    # Resolve payment a partir do externalReference ou similar
    external_charge_id = (
        payload.get("payment", {}).get("id")
        if isinstance(payload.get("payment"), dict)
        else payload.get("externalReference") or payload.get("external_charge_id")
    )

    from app.infrastructure.db.models.payment import Payment as PaymentModel
    payment = None
    if external_charge_id:
        payment = (
            db.query(PaymentModel)
            .filter(PaymentModel.external_charge_id == external_charge_id)
            .first()
        )

    if not payment:
        # CORRIDA, não skip: com o gate acima só chegam aqui eventos de pagamento
        # confirmado — se o Payment ainda não existe, o webhook chegou antes do
        # commit da linha Payment. 503 faz o Asaas reenviar quando ela existir.
        logger.warning(
            "asaas_webhook_transaction: payment não encontrado (possível corrida "
            "webhook × commit) external_charge_id=%s event_id=%s event=%s",
            external_charge_id, event_id, event_type,
        )
        raise HTTPException(status_code=503, detail="payment_not_yet_visible")

    try:
        payment_service.confirm(
            payment_id=payment.payment_id,
            event_id=str(event_id),
            webhook_data=payload,
            company_id=payment.company_id,
            db=db,
        )
    except Exception:
        # Falha de processamento do NOSSO lado: responder não-2xx para o Asaas
        # reenviar (200 com {"ok": false} era interpretado como processado).
        logger.exception(
            "asaas_webhook_transaction: confirm falhou event_id=%s event=%s "
            "external_charge_id=%s payment_id=%s",
            event_id, event_type, external_charge_id, payment.payment_id,
        )
        raise HTTPException(status_code=500, detail="confirm_failed")

    return {"ok": True, "event_id": str(event_id)}


# ── Webhook Asaas — account_status ───────────────────────────────────────────

@router.post("/payments/webhook/asaas/account_status")
def webhook_asaas_account_status(
    request: Request,
    payload: dict,
    asaas_access_token: str = Header(default="", alias="asaas-access-token"),
    db: Session = Depends(get_db),
):
    """Autenticado por token estático (asaas-access-token); atualiza external_account_status.

    Mesma validação fail-closed do webhook de transaction — antes deste sprint,
    token não configurado aceitava tudo em silêncio e a comparação era `!=`.
    """
    _require_asaas_webhook_token(
        asaas_access_token,
        endpoint="account_status",
        event=payload.get("event", ""),
        client_host=(request.client.host if request.client else "?"),
    )

    event = payload.get("event", "")
    account_data = payload.get("account", {})
    account_id = account_data.get("id") or payload.get("accountId")
    new_status = account_data.get("status") or payload.get("accountStatus")

    if not account_id or not new_status:
        logger.warning("asaas_webhook_missing_fields",
                       extra={"payload_keys": list(payload.keys())})
        return {"ok": True, "skipped": "missing_fields"}

    company = (
        db.query(Company)
        .filter(Company.external_account_id == account_id)
        .first()
    )
    if not company:
        logger.info("asaas_webhook_company_not_found",
                    extra={"account_id": account_id})
        return {"ok": True, "skipped": "company_not_found"}

    status_map = {
        "ACTIVE": "active",
        "APPROVED": "active",
        "PENDING": "pending_verification",
        "SUSPENDED": "suspended",
        "REJECTED": "suspended",
    }
    normalized = status_map.get(new_status.upper(), new_status.lower())
    company.external_account_status = normalized
    db.commit()

    logger.info(
        "asaas_webhook_account_status_updated",
        extra={"account_id": account_id, "status": normalized, "event": event},
    )
    return {"ok": True, "status": normalized}


# ── Deposit Policies ──────────────────────────────────────────────────────────

@router.get("/deposit-policies", response_model=list[DepositPolicyResponse])
def list_deposit_policies(
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return payment_service.list_deposit_policies(company_id=user.company_id, db=db)


@router.post("/deposit-policies", response_model=DepositPolicyResponse, status_code=201)
def create_deposit_policy(
    body: DepositPolicyCreate,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return payment_service.create_deposit_policy(
        company_id=user.company_id,
        deposit_type=body.deposit_type,
        deposit_value=body.deposit_value,
        service_id=body.service_id,
        refundable_until_hours_before=body.refundable_until_hours_before,
        refund_on_tenant_fault=body.refund_on_tenant_fault,
        retain_on_no_show=body.retain_on_no_show,
        commission_on_retained_deposit=body.commission_on_retained_deposit,
        db=db,
    )


@router.put("/deposit-policies/{policy_id}", response_model=DepositPolicyResponse)
def update_deposit_policy(
    policy_id: UUID,
    body: DepositPolicyUpdate,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return payment_service.update_deposit_policy(
        policy_id=policy_id,
        company_id=user.company_id,
        db=db,
        **body.model_dump(exclude_none=True),
    )


# ── PagSeguro Point — Terminais ──────────────────────────────────────────────

@router.get("/payments/terminals")
def list_payment_terminals(
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    """Lista terminais Point disponíveis para o tenant.

    Retorna [] se o provider ativo não for PagSeguroProvider (ex: Asaas).
    Requer IntegrationCredential provider=PAGSEGURO com status=ACTIVE.

    ⚠ NOTA: list_terminals() é um stub — o endpoint REST de listagem de
      terminais PagBank não foi confirmado pela documentação pública.
      Ver comentários em providers/pagseguro.py.
    """
    from app.modules.payments.provider_factory import get_payment_provider
    from app.modules.payments.providers.pagseguro import (
        PagSeguroError,
        PagSeguroProvider,
    )

    try:
        provider = get_payment_provider(company_id=user.company_id, db=db)
    except Exception as exc:
        logger.warning("list_terminals_provider_error", extra={"error": str(exc)})
        return []

    if not isinstance(provider, PagSeguroProvider):
        return []

    try:
        return provider.list_terminals(company_id=user.company_id, db=db)
    except PagSeguroError as exc:
        logger.warning(
            "list_terminals_error",
            extra={"company_id": str(user.company_id), "error": str(exc)},
        )
        return []


# ── Financial Settings ────────────────────────────────────────────────────────

@financial_router.get("/settings", response_model=FinancialSettingsResponse)
def get_financial_settings(
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    accounts_count = (
        db.query(Account)
        .filter(Account.company_id == user.company_id)
        .count()
    )

    return FinancialSettingsResponse(
        payment_provider=company.payment_provider,
        external_account_id=company.external_account_id,
        external_account_status=company.external_account_status,
        external_account_created_at=company.external_account_created_at,
        accounts_count=accounts_count,
    )

"""Handlers do fluxo de compra de produto via bot (Sprint 2.6).

Estados:
  ESCOLHENDO_PRODUTO            → lista produtos ativos com estoque > 0
  CONFIRMANDO_QUANTIDADE_PRODUTO → pede a quantidade
  CONFIRMANDO_PRODUTO          → resumo + [Confirmar] [Cancelar]
  (PAGANDO_PRODUTO)            → transição interna ao confirmar: cria Payment
                                 (manual/CASH) + StockMovement VENDA e reseta.

Não existe Operation/Appointment PRODUCT×SALE no domínio (Appointment exige
profissional + horário). A venda é representada pela primitiva real do Sprint 17:
Payment (receita) + StockMovement VENDA (baixa de estoque e custo). FSM soberano:
o classificador apenas sugere a entrada neste fluxo; estas funções é que validam.
"""
import logging
import re
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.intent import telemetry as intent_telemetry
from app.modules.whatsapp.session import reset_session
from app.modules.stock import service as stock_service
from app.modules.products import service as products_service
from app.modules.payments import service as payment_service

logger = logging.getLogger(__name__)

STATE_ESCOLHENDO_PRODUTO             = "ESCOLHENDO_PRODUTO"
STATE_CONFIRMANDO_QUANTIDADE_PRODUTO = "CONFIRMANDO_QUANTIDADE_PRODUTO"
STATE_CONFIRMANDO_PRODUTO            = "CONFIRMANDO_PRODUTO"
STATE_MENU_PRINCIPAL                 = "MENU_PRINCIPAL"

_MAX_LIST = 10  # WhatsApp list message: até 10 linhas


def start(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
) -> None:
    """Lista produtos ativos com estoque > 0 e entra em ESCOLHENDO_PRODUTO."""
    products = [
        p for p in stock_service.list_stock(db=db, company_id=company_id, active_only=True)
        if (p.stock or 0) > 0
    ]

    if not products:
        sender.send_text(instance, whatsapp_id, messages.SEM_PRODUTOS)
        reset_session(session)
        session.state = STATE_MENU_PRINCIPAL
        return

    products = products[:_MAX_LIST]  # paginação: máx 10 por list message

    last_list, rows, buttons = [], [], []
    for i, p in enumerate(products):
        row_id = f"prod_{i}"
        last_list.append({"row_id": row_id, "payload": str(p.id), "title": p.name})
        rows.append({"rowId": row_id, "title": p.name, "description": f"R$ {p.price}"})
        buttons.append({"buttonId": row_id, "buttonText": {"displayText": p.name}})

    ctx = dict(session.context or {})
    ctx["last_list"] = last_list
    session.context = ctx
    session.state = STATE_ESCOLHENDO_PRODUTO

    if len(products) <= 3:
        sender.send_buttons(instance, whatsapp_id, messages.escolha_produto(), buttons)
    else:
        sender.send_list(instance, whatsapp_id, "🛍️ Produtos",
                         messages.escolha_produto(), rows)


def handle_escolhendo_produto(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
) -> None:
    ctx = session.context or {}
    payload = resolve_input(user_input, ctx.get("last_list", []))
    if not payload:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    try:
        product = products_service.get_product_or_404(db, company_id, UUID(payload))
    except Exception:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx = dict(ctx)
    ctx["product_id"] = str(product.id)
    ctx["product_name"] = product.name
    ctx["unit_price"] = str(product.price)
    ctx["last_list"] = []
    session.context = ctx
    session.state = STATE_CONFIRMANDO_QUANTIDADE_PRODUTO

    sender.send_text(instance, whatsapp_id, messages.pedir_quantidade(product.name))


def handle_confirmando_quantidade(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx = session.context or {}
    match = re.search(r"\d+", (user_input or ""))
    quantity = int(match.group(0)) if match else 0
    if quantity <= 0:
        sender.send_text(instance, whatsapp_id, messages.QUANTIDADE_INVALIDA)
        return

    product_name = ctx.get("product_name", "Produto")
    unit_price = Decimal(str(ctx.get("unit_price", "0")))
    total = (unit_price * quantity).quantize(Decimal("0.01"))

    ctx = dict(ctx)
    ctx["quantity"] = quantity
    ctx["last_list"] = [
        {"row_id": "opt_confirmar_produto", "payload": "confirmar_produto",
         "title": "✅ Confirmar"},
        {"row_id": "opt_cancelar_produto", "payload": "cancelar_produto",
         "title": "❌ Cancelar"},
    ]
    session.context = ctx
    session.state = STATE_CONFIRMANDO_PRODUTO

    sender.send_buttons(
        instance, whatsapp_id,
        messages.confirmar_produto(product_name, quantity, total),
        [
            {"buttonId": "opt_confirmar_produto", "buttonText": {"displayText": "✅ Confirmar"}},
            {"buttonId": "opt_cancelar_produto", "buttonText": {"displayText": "❌ Cancelar"}},
        ],
    )


def handle_confirmando_produto(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
) -> None:
    ctx = session.context or {}
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if payload == "cancelar_produto":
        intent_telemetry.record_flow_outcome(
            db, session, company_id, {"COMPRAR_PRODUTO"},
            intent_telemetry.OUTCOME_FLOW_CANCELLED, {"stage": "CONFIRMANDO_PRODUTO"},
        )
        sender.send_text(instance, whatsapp_id, messages.COMPRA_CANCELADA)
        reset_session(session)
        session.state = STATE_MENU_PRINCIPAL
        return

    if payload == "confirmar_produto":
        _finalize(db, session, company_id, whatsapp_id, instance)
        return

    sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO)


def _finalize(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str,
) -> None:
    """PAGANDO_PRODUTO: cria Payment (manual/CASH) + StockMovement VENDA."""
    ctx = session.context or {}
    customer_id = ctx.get("customer_id")
    product_id = ctx.get("product_id")
    quantity = int(ctx.get("quantity", 0))
    product_name = ctx.get("product_name", "Produto")
    unit_price = Decimal(str(ctx.get("unit_price", "0")))

    if not (customer_id and product_id and quantity > 0):
        sender.send_text(instance, whatsapp_id, messages.ERRO_GENERICO)
        reset_session(session)
        return

    # Verifica estoque antes de cobrar (mensagem amigável se insuficiente)
    try:
        product = products_service.get_product_or_404(db, company_id, UUID(product_id))
    except Exception:
        sender.send_text(instance, whatsapp_id, messages.ERRO_GENERICO)
        reset_session(session)
        return

    available = product.stock if product.stock is not None else 0
    if available < quantity and not _allow_negative(db, company_id):
        sender.send_text(
            instance, whatsapp_id,
            messages.produto_estoque_insuficiente(product_name, available),
        )
        reset_session(session)
        session.state = STATE_MENU_PRINCIPAL
        return

    total = (unit_price * quantity).quantize(Decimal("0.01"))

    # 1. Payment (provider manual, pago presencialmente)
    payment = payment_service.create_payment(
        company_id=company_id,
        customer_id=UUID(customer_id),
        gross_amount=total,
        payment_method="CASH",
        provider="manual",
        db=db,
    )

    # 2. StockMovement VENDA (baixa imediata) — created_by = OWNER do tenant
    owner_id = _resolve_owner_user_id(db, company_id)
    if owner_id:
        try:
            stock_service.record_movement(
                company_id=company_id,
                product_id=UUID(product_id),
                movement_type="VENDA",
                quantity=quantity,
                created_by=owner_id,
                db=db,
                source_type="OPERATION",
                source_id=getattr(payment, "payment_id", None),
            )
        except Exception:
            logger.exception(
                "comprando_produto: falha ao registrar StockMovement VENDA product_id=%s",
                product_id,
            )
    else:
        logger.warning(
            "comprando_produto: sem OWNER para company_id=%s — StockMovement VENDA não registrado",
            company_id,
        )

    intent_telemetry.record_flow_outcome(
        db, session, company_id, {"COMPRAR_PRODUTO"},
        intent_telemetry.OUTCOME_FLOW_CONFIRMED,
        {"payment_id": str(getattr(payment, "payment_id", None))},
    )
    sender.send_text(
        instance, whatsapp_id,
        messages.produto_comprado(product_name, quantity, total),
    )
    reset_session(session)
    session.state = STATE_MENU_PRINCIPAL


def _allow_negative(db: Session, company_id: UUID) -> bool:
    from app.infrastructure.db.models.tenant_config import TenantConfig
    config = (
        db.query(TenantConfig)
        .filter(TenantConfig.company_id == company_id)
        .first()
    )
    return bool(config and config.allow_negative_stock)


def _resolve_owner_user_id(db: Session, company_id: UUID):
    from app.infrastructure.db.models import User
    owner = (
        db.query(User)
        .filter(
            User.company_id == company_id,
            User.role == "OWNER",
            User.active == True,  # noqa: E712
        )
        .first()
    )
    return owner.id if owner else None

"""Handlers do fluxo de contratação de pacote via bot (Sprint 2.6).

Estados:
  ESCOLHENDO_PACOTE   → lista PackagePlans ativos (is_active=True)
  CONFIRMANDO_PACOTE  → resumo + [Confirmar] [Cancelar]
  (PAGANDO_PACOTE)    → transição interna ao confirmar: reutiliza
                        packages.purchase() (Sprint 14) → PackagePurchase
                        PENDING_PAYMENT + Payment PENDING e reseta.

FSM soberano: o classificador apenas sugere a entrada neste fluxo.
"""
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.intent import telemetry as intent_telemetry
from app.modules.whatsapp.session import reset_session
from app.modules.packages import service as packages_service

logger = logging.getLogger(__name__)

STATE_ESCOLHENDO_PACOTE  = "ESCOLHENDO_PACOTE"
STATE_CONFIRMANDO_PACOTE = "CONFIRMANDO_PACOTE"
STATE_MENU_PRINCIPAL     = "MENU_PRINCIPAL"

_MAX_LIST = 10  # WhatsApp list message: até 10 linhas


def start(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
) -> None:
    """Lista pacotes ativos e entra em ESCOLHENDO_PACOTE."""
    packages = [
        p for p in packages_service.list_packages(company_id, db)
        if p.is_active
    ]

    if not packages:
        sender.send_text(instance, whatsapp_id, messages.SEM_PACOTES)
        reset_session(session)
        session.state = STATE_MENU_PRINCIPAL
        return

    packages = packages[:_MAX_LIST]

    last_list, rows, buttons = [], [], []
    for i, p in enumerate(packages):
        row_id = f"pkg_{i}"
        desc = messages.descricao_pacote(p.name, p.total_cotas, p.validity_days, p.price)
        last_list.append({"row_id": row_id, "payload": str(p.package_id), "title": p.name})
        rows.append({"rowId": row_id, "title": p.name, "description": desc})
        buttons.append({"buttonId": row_id, "buttonText": {"displayText": p.name}})

    ctx = dict(session.context or {})
    ctx["last_list"] = last_list
    session.context = ctx
    session.state = STATE_ESCOLHENDO_PACOTE

    if len(packages) <= 3:
        sender.send_buttons(instance, whatsapp_id, messages.escolha_pacote(), buttons)
    else:
        sender.send_list(instance, whatsapp_id, "🎁 Pacotes",
                         messages.escolha_pacote(), rows)


def handle_escolhendo_pacote(
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
        package = packages_service._get_package_or_404(UUID(payload), company_id, db)
    except Exception:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx = dict(ctx)
    ctx["package_id"] = str(package.package_id)
    ctx["package_name"] = package.name
    ctx["last_list"] = [
        {"row_id": "opt_confirmar_pacote", "payload": "confirmar_pacote",
         "title": "✅ Confirmar"},
        {"row_id": "opt_cancelar_pacote", "payload": "cancelar_pacote",
         "title": "❌ Cancelar"},
    ]
    session.context = ctx
    session.state = STATE_CONFIRMANDO_PACOTE

    sender.send_buttons(
        instance, whatsapp_id,
        messages.confirmar_pacote(package.name, package.total_cotas,
                                  package.validity_days, package.price),
        [
            {"buttonId": "opt_confirmar_pacote", "buttonText": {"displayText": "✅ Confirmar"}},
            {"buttonId": "opt_cancelar_pacote", "buttonText": {"displayText": "❌ Cancelar"}},
        ],
    )


def handle_confirmando_pacote(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
) -> None:
    ctx = session.context or {}
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if payload == "cancelar_pacote":
        intent_telemetry.record_flow_outcome(
            db, session, company_id, {"COMPRAR_PACOTE"},
            intent_telemetry.OUTCOME_FLOW_CANCELLED, {"stage": "CONFIRMANDO_PACOTE"},
        )
        sender.send_text(instance, whatsapp_id, messages.COMPRA_CANCELADA)
        reset_session(session)
        session.state = STATE_MENU_PRINCIPAL
        return

    if payload == "confirmar_pacote":
        _finalize(db, session, company_id, whatsapp_id, instance)
        return

    sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO)


def _finalize(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str,
) -> None:
    """PAGANDO_PACOTE: reutiliza packages.purchase() (Sprint 14)."""
    ctx = session.context or {}
    customer_id = ctx.get("customer_id")
    package_id = ctx.get("package_id")
    package_name = ctx.get("package_name", "Pacote")

    if not (customer_id and package_id):
        sender.send_text(instance, whatsapp_id, messages.ERRO_GENERICO)
        reset_session(session)
        return

    try:
        purchase = packages_service.purchase(
            customer_id=UUID(customer_id),
            package_id=UUID(package_id),
            seller_user_id=None,         # bot não tem User
            payment_method="CASH",
            target_account_id=None,      # backend resolve conta CAIXA
            company_id=company_id,
            db=db,
        )
    except Exception:
        logger.exception("comprando_pacote: falha em purchase package_id=%s", package_id)
        sender.send_text(instance, whatsapp_id, messages.ERRO_GENERICO)
        reset_session(session)
        session.state = STATE_MENU_PRINCIPAL
        return

    intent_telemetry.record_flow_outcome(
        db, session, company_id, {"COMPRAR_PACOTE"},
        intent_telemetry.OUTCOME_FLOW_CONFIRMED,
        {"purchase_id": str(getattr(purchase, "purchase_id", None))},
    )
    sender.send_text(instance, whatsapp_id, messages.pacote_contratado(package_name))
    reset_session(session)
    session.state = STATE_MENU_PRINCIPAL

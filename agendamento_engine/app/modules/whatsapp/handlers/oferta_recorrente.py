"""Handler do estado OFERTA_RECORRENTE."""
import uuid as uuidlib
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender

STATE_CONFIRMANDO = "CONFIRMANDO"


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    start_escolhendo_servico,
    start_escolhendo_horario,
    send_confirmacao_resumo,
) -> None:
    ctx       = dict(session.context or {})
    payload   = resolve_input(user_input, ctx.get("last_list", []))
    predicted = ctx.get("predicted_slot")

    if not payload:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    if payload == "opt_confirmar_oferta" and predicted:
        expires = datetime.fromisoformat(predicted["expires_at"])
        if datetime.now(timezone.utc) > expires:
            sender.send_text(instance, whatsapp_id, messages.OFERTA_EXPIRADA)
            ctx["service_id"]        = predicted["service_id"]
            ctx["service_name"]      = predicted["service_name"]
            ctx["professional_id"]   = predicted["professional_id"]
            ctx["professional_name"] = predicted["professional_name"]
            ctx.pop("predicted_slot", None)
            session.context = ctx
            start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
            return

        ctx["service_id"]              = predicted["service_id"]
        ctx["service_name"]            = predicted["service_name"]
        ctx["professional_id"]         = predicted["professional_id"]
        ctx["professional_name"]       = predicted["professional_name"]
        ctx["slot_start_at"]           = predicted["start_at"]
        ctx["booking_idempotency_key"] = str(uuidlib.uuid4())
        ctx.pop("predicted_slot", None)
        session.context = ctx
        session.state = STATE_CONFIRMANDO
        send_confirmacao_resumo(instance, whatsapp_id, ctx)
        return

    if payload == "opt_outro_horario" and predicted:
        ctx["service_id"]        = predicted["service_id"]
        ctx["service_name"]      = predicted["service_name"]
        ctx["professional_id"]   = predicted["professional_id"]
        ctx["professional_name"] = predicted["professional_name"]
        ctx.pop("predicted_slot", None)
        session.context = ctx
        start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "opt_outro_servico":
        ctx.pop("predicted_slot", None)
        session.context = ctx
        start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
        return

    sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
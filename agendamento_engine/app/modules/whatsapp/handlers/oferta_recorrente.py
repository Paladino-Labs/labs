"""Handler do estado OFERTA_RECORRENTE."""
import logging
import uuid as uuidlib
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.booking.engine import booking_engine

logger = logging.getLogger(__name__)

STATE_CONFIRMANDO = "CONFIRMANDO"


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    start_escolhendo_servico,
    start_escolhendo_horario,
    send_confirmacao_resumo,
    send_escolher_data,
) -> None:
    ctx       = dict(session.context or {})
    payload   = resolve_input(user_input, ctx.get("last_list", []))
    predicted = ctx.get("predicted_slot")

    if not payload:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    if payload == "opt_confirmar_oferta" and predicted:
        expires = datetime.fromisoformat(predicted["expires_at"])
        now     = datetime.now(timezone.utc)

        # ── Oferta expirada ───────────────────────────────────────────────────
        if now > expires:
            sender.send_text(instance, whatsapp_id, messages.OFERTA_EXPIRADA)
            ctx["service_id"]        = predicted["service_id"]
            ctx["service_name"]      = predicted["service_name"]
            ctx["professional_id"]   = predicted["professional_id"]
            ctx["professional_name"] = predicted["professional_name"]
            ctx.pop("predicted_slot", None)
            session.context = ctx
            send_escolher_data(db, session, company_id, instance, whatsapp_id)
            return

        # ── Pre-flight: verifica se o slot ainda está disponível ──────────────
        # O slot da oferta NÃO é reservado — outro cliente pode ter agendado
        # enquanto a oferta estava sendo exibida. Checamos antes de ir ao
        # CONFIRMANDO para dar UX imediata em vez de só detectar no confirm().
        predicted_start = datetime.fromisoformat(predicted["start_at"])
        prof_id_str     = predicted.get("professional_id")
        svc_id_str      = predicted.get("service_id")

        slot_still_available = False
        try:
            prof_id = UUID(prof_id_str) if prof_id_str else None
            svc_id  = UUID(svc_id_str)
            available = booking_engine.list_available_slots(
                db, company_id, prof_id, svc_id,
                predicted_start.date(), limit=0,
            )
            slot_still_available = any(
                s.start_at == predicted_start and s.professional_id == prof_id
                for s in available
            )
        except Exception:
            logger.warning("oferta_recorrente: pre-flight check falhou — prosseguindo")
            slot_still_available = True   # fail-open: deixa o confirm() tratar

        if not slot_still_available:
            sender.send_text(
                instance, whatsapp_id,
                "😬 Esse horário acabou de ser ocupado por outro cliente!\n\n"
                "Vamos procurar um novo horário para você.",
            )
            ctx["service_id"]        = predicted["service_id"]
            ctx["service_name"]      = predicted["service_name"]
            ctx["professional_id"]   = predicted["professional_id"]
            ctx["professional_name"] = predicted["professional_name"]
            ctx.pop("predicted_slot", None)
            session.context = ctx
            send_escolher_data(db, session, company_id, instance, whatsapp_id)
            return

        # ── Slot disponível — vai para confirmação ────────────────────────────
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
        send_escolher_data(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "opt_outro_servico":
        ctx.pop("predicted_slot", None)
        session.context = ctx
        start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
        return

    sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
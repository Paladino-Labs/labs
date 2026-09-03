"""Handlers dos estados AGUARDANDO_NOME e CONFIRMAR_NOME."""
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp import trace
from app.modules.whatsapp import fallback
from app.modules.whatsapp import name_validator
from app.modules.whatsapp.helpers import first_name
from app.modules.customers import service as customer_svc

logger = logging.getLogger(__name__)

STATE_AGUARDANDO_NOME = "AGUARDANDO_NOME"
STATE_CONFIRMAR_NOME  = "CONFIRMAR_NOME"
STATE_MENU_PRINCIPAL  = "MENU_PRINCIPAL"

# Tipos de mídia que `helpers.extract_message_type` entrega e que o
# `extract_user_text` não sabe ler — todos chegam aqui com `user_input == ""`.
#
# ⚠️ Áudio e imagem NÃO são o mesmo caso, e tratá-los igual foi o defeito de
# 25/08: a cliente mandou a foto do corte de referência e o bot respondeu "Pode
# me dizer seu nome novamente?", como se ela tivesse ERRADO ao tentar dizer o
# nome. Áudio é a mensagem inteira (sem ouvir, o bot não sabe nada → pedir por
# escrito); imagem é complemento (→ reconhecer e seguir de onde estava).
_AUDIO_TYPES = frozenset({"audioMessage", "pttMessage", "voiceMessage"})
_IMAGE_TYPES = frozenset({
    "imageMessage", "videoMessage", "stickerMessage", "documentMessage",
    "documentWithCaptionMessage",
})


def handle_aguardando_nome(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    message_type: str = "",
) -> None:
    # ── Mídia: reconhecer o que chegou, não pedir de volta ────────────────────
    # ⚠️ O `reason` é o `no_text_to_parse` do S2, não um sexto valor. A definição
    # dele — "chegou mensagem sem texto: áudio, imagem, sticker; não é falha de
    # compreensão, é tipo de mídia não suportado" — descreve exatamente este
    # caso. Um valor novo separaria o mesmo fenômeno por ESTADO, e o estado já é
    # coluna própria (`fsm_state`); a origem já distingue o site (`detail.origin`).
    if not (user_input or "").strip() and message_type:
        if message_type in _AUDIO_TYPES:
            texto = messages.NOME_AUDIO
        elif message_type in _IMAGE_TYPES:
            texto = messages.NOME_MIDIA_RECEBIDA
        else:
            # protocolMessage (mensagem apagada), localização, contato: não há o
            # que reconhecer nem o que transcrever. Repetir a pergunta é honesto.
            texto = messages.PEDIR_NOME_NOVAMENTE
        trace.note_dispatch(
            fallback.TRACE_HANDLER,
            reason=fallback.REASON_NO_TEXT,
            origin="aguardando_nome.handle_aguardando_nome.media",
            options=0,
            message_type=message_type,
        )
        sender.send_text(instance, whatsapp_id, texto)
        return

    ok, motivo, nome = name_validator.validate_name(user_input)
    if not ok:
        # ⚠️ A saída tem de funcionar APESAR de os comandos universais estarem
        # desligados neste estado (`bot_service.py:1275`) — ver
        # `fallback.offer_human_only`.
        logger.info(
            "nome rejeitado motivo=%s whatsapp_id=%s input=%r",
            motivo, whatsapp_id, (user_input or "")[:60],
        )
        fallback.offer_human_only(
            session, instance, whatsapp_id,
            origin="aguardando_nome.handle_aguardando_nome",
            header=messages.NOME_INVALIDO_TITULO,
            body=messages.NOME_INVALIDO_DICA,
            reason=fallback.REASON_UNRECOGNIZED,
        )
        return

    ctx = dict(session.context or {})
    ctx["nome_temp"] = nome
    session.context = ctx
    session.state = STATE_CONFIRMAR_NOME
    sender.send_text(instance, whatsapp_id, messages.confirmar_nome(nome))


def handle_confirmando_nome(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    start_escolhendo_servico,
) -> None:
    resposta  = user_input.strip().lower()
    ctx       = dict(session.context or {})
    nome_temp = ctx.get("nome_temp")

    if not nome_temp:
        session.state = STATE_AGUARDANDO_NOME
        session.context = ctx
        sender.send_text(instance, whatsapp_id, messages.PEDIR_NOME_NOVAMENTE)
        return

    if resposta in ("1", "sim", "s", "ok", "isso", "confirmar"):
        phone = whatsapp_id.split("@")[0]  # extrai número do JID completo
        # Sprint A: resolver garante PaladinoIdentity global + Customer do
        # tenant (mesma deduplicação do get_or_create_by_phone anterior —
        # sem mudança de comportamento visível para o cliente).
        from app.modules.identity.resolver import resolver
        from app.modules.identity import consent_service
        from app.modules.identity.consent_service import ConsentType, SourceChannel

        customer, is_new = resolver.resolve_for_tenant(
            db, phone, company_id, name=nome_temp
        )
        if is_new:
            consent_service.grant_consent(
                db, customer.identity_id, company_id,
                ConsentType.COMMUNICATION, None, SourceChannel.BOT,
                notes="Cadastro via bot WhatsApp",
            )
        ctx["customer_id"]   = str(customer.id)
        ctx["customer_name"] = customer.name
        ctx.pop("nome_temp", None)
        session.context = ctx
        session.state = STATE_MENU_PRINCIPAL

        nome_curto = first_name(customer.name)
        sender.send_text(instance, whatsapp_id, messages.boas_vindas_nome_confirmado(nome_curto))
        start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
        return

    if resposta in ("2", "não", "nao", "n", "errado", "corrigir"):
        session.state = STATE_AGUARDANDO_NOME
        session.context = ctx
        sender.send_text(instance, whatsapp_id, messages.PEDIR_NOME_NOVAMENTE)
        return

    fallback.not_understood(
        session, instance, whatsapp_id,
        origin="aguardando_nome.handle_confirmando_nome", user_input=user_input,
        options=[
            {"row_id": "1", "payload": "1", "title": "Sim"},
            {"row_id": "2", "payload": "2", "title": "Corrigir"},
        ],
    )
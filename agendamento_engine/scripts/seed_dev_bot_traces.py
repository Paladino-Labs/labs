"""Semeia bot_message_traces no DEV para exercitar a tela de telemetria.

Reproduz as três assinaturas que o S-bot-1 distingue (regex não casou /
casou errado / handler não tratou) mais o tipo ilegível, para a verificação
manual da tela ter os casos que importam.

⚠️ Guard de produção idêntico ao de `seed_dev.py`: aborta se o DATABASE_URL
apontar para o ref do Supabase de produção. Nunca rode isto em produção — a
tabela é telemetria real de clientes.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

PROD_REF = "uhhygdqioqcgcfqfbmif"

url = os.environ.get("DATABASE_URL", "")
if not url:
    sys.exit("DATABASE_URL ausente")
if PROD_REF in url:
    sys.exit("ABORTADO: DATABASE_URL aponta para PRODUÇÃO")

engine = sa.create_engine(url)
BASE = datetime.now(timezone.utc) - timedelta(days=2)

INSERT = sa.text("""
    INSERT INTO bot_message_traces (
        id, company_id, received_at, instance_name, event,
        whatsapp_hash, whatsapp_masked, message_id, message_type,
        session_id, fsm_state, fsm_state_after, outcome, user_input,
        webhook, classifier, dispatch, outbound, duration_ms
    ) VALUES (
        :id, :company_id, :received_at, 'paladino-dev', 'messages.upsert',
        :wa_hash, :wa_masked, :message_id, :message_type,
        :session_id, :fsm_state, :fsm_state_after, 'PROCESSED', :user_input,
        '{}'::jsonb, CAST(:classifier AS jsonb), CAST(:dispatch AS jsonb),
        CAST(:outbound AS jsonb), 120
    )
""")


def classifier(intent, conf, decision, matched=None):
    if intent is None:
        return "{}"
    import json
    m = matched if matched is not None else conf > 0.0
    return json.dumps({
        "regex": {"intent": intent, "confidence": conf, "matched": m,
                  "active_intents": ["AGENDAR", "CANCELAR", "CONSULTAR"]},
        "final": {"intent": intent, "confidence": conf, "source": "REGEX",
                  "entities": {}, "classification_id": str(uuid.uuid4()),
                  "threshold": 0.7},
        "routing": {"decision": decision, "routed": decision == "ROUTED",
                    "reason": None},
    })


def dispatch(handler):
    import json
    return json.dumps({"handler": handler, "path": [handler]})


def outbound(*texts):
    import json
    return json.dumps([{"kind": "text", "text": t, "ok": True} for t in texts])


MENU = "Escolha uma opção:\n1 Agendar\n2 Meus agendamentos\n3 Falar com atendente"

# (hash, masked, [(min, texto, intent, conf, decision, handler, tipo, saida)])
CONVERSAS = [
    # ⚠️ Saudação e agradecimento aparecem como MENU_FALLBACK, não como
    # "sem classificação": o catálogo não tem essas intenções (achado da
    # INV Classificador), então o regex roda, não casa nada e cai no menu.
    ("dev-ana-001", "+55 62 *****-1122", [
        (0, "oi", "MENU_PRINCIPAL", 0.0, "MENU_FALLBACK", "show_menu_principal",
         "conversation", (MENU,)),
        (2, "queria marcar um corte pra sexta", "MENU_PRINCIPAL", 0.0,
         "MENU_FALLBACK", "show_menu_principal", "conversation", (MENU,)),
        (4, "1", "AGENDAR", 0.9, "ROUTED", "booking_engine",
         "listResponseMessage", ("Qual serviço você quer?",)),
    ]),
    ("dev-bruno-002", "+55 62 *****-3344", [
        (0, "bom dia", "MENU_PRINCIPAL", 0.0, "MENU_FALLBACK",
         "show_menu_principal", "conversation", (MENU,)),
        (1, "quanto custa a barba?", "MENU_PRINCIPAL", 0.0, "MENU_FALLBACK",
         "show_menu_principal", "conversation", (MENU,)),
        (3, None, None, 0.0, None, "show_menu_principal",
         "audioMessage", (MENU,)),
        (6, "obrigado", "MENU_PRINCIPAL", 0.0, "MENU_FALLBACK",
         "show_menu_principal", "conversation", (MENU,)),
    ]),
    ("dev-carla-003", "+55 62 *****-5566", [
        (0, "quero cancelar meu horário", "CANCELAR", 0.9, "ROUTED",
         "cancelando", "conversation", ("Qual agendamento você quer cancelar?",)),
        (2, "o de amanhã", "MENU_PRINCIPAL", 0.0, "MENU_FALLBACK",
         "show_menu_principal", "conversation", (MENU,)),
    ]),
]


def main():
    with engine.begin() as c:
        company_id = c.execute(sa.text("select id from companies limit 1")).scalar()
        c.execute(
            sa.text("delete from bot_message_traces where whatsapp_hash like 'dev-%'")
        )
        n = 0
        for wa_hash, masked, msgs in CONVERSAS:
            session_id = uuid.uuid4()
            for i, (mins, text, intent, conf, decision, handler, mtype, out) in enumerate(msgs):
                c.execute(INSERT, {
                    "id": uuid.uuid4(),
                    "company_id": company_id,
                    "received_at": BASE + timedelta(minutes=mins),
                    "wa_hash": wa_hash,
                    "wa_masked": masked,
                    "message_id": f"{wa_hash}-{i}",
                    "message_type": mtype,
                    "session_id": session_id,
                    "fsm_state": "MENU_PRINCIPAL",
                    "fsm_state_after": "MENU_PRINCIPAL",
                    "user_input": text,
                    "classifier": classifier(intent, conf, decision),
                    "dispatch": dispatch(handler),
                    "outbound": outbound(*out),
                })
                n += 1
            BASE_SHIFT = 0  # conversas em dias diferentes ficam por received_at
        print(f"OK: {n} traces em {len(CONVERSAS)} conversas (company {company_id})")


if __name__ == "__main__":
    main()

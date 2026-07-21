"""Diagnóstico de serialização por conversa do bot (S2.1) — a ferramenta que
provou que advisory lock de sessão NÃO funciona no pooler transaction-mode.

Compara, contra o banco apontado por DATABASE_URL, dois mecanismos de exclusão
mútua entre DUAS conexões (dois "workers"):

  1. advisory lock de sessão  → esperado FALHAR no pooler transaction-mode (6543)
                                 e passar em session mode (5432)/direto.
  2. lease em tabela (o adotado) → esperado PASSAR em QUALQUER modo de pooler.

Uso:
  DATABASE_URL=postgresql://... python scripts/verify_bot_serialization.py

Requer a tabela bot_conversation_leases (migration e0s32) e >=1 company para o
teste de lease. Não deixa resíduo (limpa a sentinela). É read-mostly; a única
escrita é uma linha de lease sentinela, removida ao final.
"""
import os
import sys

from sqlalchemy import create_engine, text

URL = os.environ.get("DATABASE_URL")
if not URL:
    print("Defina DATABASE_URL (ex.: o do worker). Abortando.")
    sys.exit(2)

if "uhhygdqioqcgcfqfbmif" in URL:
    ref = "producao(uhhygdqioqcgcfqfbmif)"
elif "tvguwtdfayhrctlpollf" in URL:
    ref = "dev(tvguwtdfayhrctlpollf)"
else:
    ref = "outro"
print(f"alvo: {ref}\n")

KEY = "s21diag:convDIAG"
SENT_W = "__s21_diag_lease__"

_TRY_LOCK = text("SELECT pg_try_advisory_lock(hashtext(:k))")
_UNLOCK = text("SELECT pg_advisory_unlock(hashtext(:k))")
_CLAIM = text("""
    INSERT INTO bot_conversation_leases (company_id, whatsapp_id, locked_by, locked_until)
    VALUES (:c, :w, :by, now() + make_interval(secs => 30))
    ON CONFLICT (company_id, whatsapp_id) DO UPDATE
        SET locked_by = EXCLUDED.locked_by, locked_until = EXCLUDED.locked_until
        WHERE bot_conversation_leases.locked_until < now()
    RETURNING locked_by
""")
_CLEAN = text("DELETE FROM bot_conversation_leases WHERE company_id=:c AND whatsapp_id=:w")


def test_advisory():
    """exclusão mútua OK ⟺ worker2 é bloqueado enquanto worker1 detém."""
    e1 = create_engine(URL)
    e2 = create_engine(URL)
    c1 = e1.connect()
    c2 = e2.connect()
    try:
        c1.execute(_TRY_LOCK, {"k": KEY}).scalar()
        c1.commit()  # encerra a transação — onde o pooler reassina o backend
        g2 = c2.execute(_TRY_LOCK, {"k": KEY}).scalar()
        c2.commit()
        c1.execute(_UNLOCK, {"k": KEY})
        c1.commit()
        if g2:
            c2.execute(_UNLOCK, {"k": KEY})
            c2.commit()
        return g2 is False
    finally:
        c1.close()
        c2.close()
        e1.dispose()
        e2.dispose()


def test_lease():
    """exclusão mútua OK ⟺ um worker adquire a lease e o outro NÃO."""
    e0 = create_engine(URL)
    with e0.connect() as c0:
        cid = c0.execute(text("SELECT id FROM companies LIMIT 1")).scalar()
    e0.dispose()
    if cid is None:
        print("lease: PULADO (sem company no banco)")
        return None
    p = {"c": cid, "w": SENT_W}
    e1 = create_engine(URL)
    e2 = create_engine(URL)
    c1 = e1.connect()
    c2 = e2.connect()
    try:
        c1.execute(_CLEAN, p)
        c1.commit()
        g1 = c1.execute(_CLAIM, {**p, "by": "diag-1"}).fetchone()
        c1.commit()
        g2 = c2.execute(_CLAIM, {**p, "by": "diag-2"}).fetchone()
        c2.commit()
        c1.execute(_CLEAN, p)
        c1.commit()
        return (g1 is not None) and (g2 is None)
    finally:
        c1.close()
        c2.close()
        e1.dispose()
        e2.dispose()


adv = test_advisory()
print(f"1) advisory lock de sessao — exclusao mutua entre workers: {'OK' if adv else 'FALHOU'}")
if not adv:
    print("   -> conexao e transaction-mode: estado de sessao NAO e preservado (advisory lock evapora).")

lease = test_lease()
if lease is None:
    print("2) lease em tabela — PULADO")
else:
    print(f"2) lease em tabela (adotado)  — exclusao mutua entre workers: {'OK' if lease else 'FALHOU'}")

print()
if lease:
    print("VEREDICTO: o lease serializa corretamente nesta conexao (independe do modo do pooler).")
    sys.exit(0)
print("VEREDICTO: o lease NAO serializou — investigar (regressao no claim?).")
sys.exit(1)

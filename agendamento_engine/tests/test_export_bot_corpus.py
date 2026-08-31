"""Testes do exportador do corpus do bot — S0.

Mínimos de propósito: `scripts/export_bot_corpus.py` é código descartável
(roda duas vezes antes de 07/09 e não volta a ser usado). O que se testa aqui
é que o script monta as queries e escreve os arquivos — nada de banco.

O que NÃO é opcional, e por isso tem teste: as duas divergências de nome de
coluna que o enunciado do sprint supôs errado. Se elas voltarem, a exportação
quebra contra produção na única janela em que há dado para exportar.
"""
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import scripts.export_bot_corpus as exp


# ── Queries ──────────────────────────────────────────────────────────────────

def test_conjunto1_nao_usa_labeled_at():
    """`bot_message_labels` tem created_at/updated_at, NÃO labeled_at (e0s36)."""
    assert "labeled_at" not in exp.SQL_TRACES_LABELS
    assert "l.created_at" in exp.SQL_TRACES_LABELS
    assert "l.updated_at" in exp.SQL_TRACES_LABELS


def test_conjunto2_nao_usa_recorded_at():
    """`intent_outcomes` tem outcome_at, NÃO recorded_at (e0s30)."""
    assert "recorded_at" not in exp.SQL_CLASSIFICATIONS
    assert "o.outcome_at" in exp.SQL_CLASSIFICATIONS


@pytest.mark.parametrize("sql", [exp.SQL_TRACES_LABELS, exp.SQL_CLASSIFICATIONS,
                                 exp.SQL_CORPUS_LEITURA])
def test_joins_sao_left(sql):
    """JOIN interno perderia o corpus não-rotulado, que é a maior parte dele."""
    assert "LEFT JOIN" in sql
    assert sql.count("JOIN") == sql.count("LEFT JOIN")


@pytest.mark.parametrize("sql", [exp.SQL_TRACES_LABELS, exp.SQL_CLASSIFICATIONS,
                                 exp.SQL_CORPUS_LEITURA])
def test_queries_sao_somente_leitura(sql):
    upper = sql.upper()
    assert upper.lstrip().startswith("SELECT")
    for proibido in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"):
        # \b: `UPDATE` é substring de `UPDATED_AT`, que é coluna legítima
        assert re.search(rf"\b{proibido}\b", upper) is None


def test_conjunto4_traz_as_colunas_de_leitura():
    for col in ("whatsapp_hash", "user_input", "expected_intent", "understood"):
        assert col in exp.SQL_CORPUS_LEITURA
    assert "dispatch_reason" in exp.SQL_CORPUS_LEITURA
    assert "'detail' ->> 'reason'" in exp.SQL_CORPUS_LEITURA


# ── Conjunto 3 (sonda de fila de espera) ─────────────────────────────────────

def test_waitlist_query_usa_bind_params():
    sql, params = exp.build_waitlist_query(["avis", "fila"])
    assert params == {"t0": "%avis%", "t1": "%fila%"}
    # o termo nunca é interpolado no SQL
    assert "avis" not in sql and "fila" not in sql
    assert sql.count("ILIKE") == 2
    assert "event = 'messages.upsert'" in sql
    assert "user_input IS NOT NULL" in sql


def test_waitlist_cobre_a_unica_fala_conhecida():
    """"Se por acaso surgir horário para os dois c me avisa"."""
    fala = "se por acaso surgir horário para os dois c me avisa"
    assert any(t in fala for t in exp.WAITLIST_TERMS)


# ── Escrita dos arquivos ─────────────────────────────────────────────────────

FIXTURE_TRACES = [
    {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "received_at": datetime(2026, 8, 20, 14, 30, tzinfo=timezone.utc),
        "whatsapp_hash": "aaa",
        "fsm_state": "MENU_PRINCIPAL",
        "fsm_state_after": "MENU_PRINCIPAL",
        "message_type": "conversation",
        "user_input": "Vou atrasar um pouco",
        "classifier": {"final": {"intent": "MENU_PRINCIPAL", "confidence": 0.0}},
        "dispatch": {"handler": "show_menu", "detail": {"reason": "no_match"}},
        "confidence": Decimal("0.900"),
        "expected_intent": None,
        "understood": None,
        "dispatch_reason": "no_match",
    },
    {
        "id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "received_at": datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc),
        "whatsapp_hash": "bbb",
        "fsm_state": "INICIO",
        "fsm_state_after": "AGENDANDO",
        "message_type": "conversation",
        "user_input": "Mano, tem horário hoje 15:30?",
        "classifier": {},
        "dispatch": {},
        "confidence": None,
        "expected_intent": "agendar",
        "understood": "YES",
        "dispatch_reason": None,
    },
]


def test_write_jsonl_serializa_uuid_datetime_decimal_e_jsonb(tmp_path):
    destino = tmp_path / "c1.jsonl"
    n = exp.write_jsonl(FIXTURE_TRACES, destino)

    assert n == 2
    linhas = destino.read_text(encoding="utf-8").strip().split("\n")
    assert len(linhas) == 2

    primeira = json.loads(linhas[0])
    assert primeira["id"] == "11111111-1111-1111-1111-111111111111"
    assert primeira["received_at"] == "2026-08-20T14:30:00+00:00"
    # Decimal vira string, não float: `confidence` é NUMERIC(4,3) e vira estatística
    assert primeira["confidence"] == "0.900"
    # JSONB continua sendo objeto, não string escapada
    assert primeira["dispatch"]["detail"]["reason"] == "no_match"
    # acento preservado (ensure_ascii=False)
    assert "horário" in linhas[1]


def test_write_csv_escreve_cabecalho_e_so_as_colunas_pedidas(tmp_path):
    destino = tmp_path / "c4.csv"
    n = exp.write_csv(FIXTURE_TRACES, exp.CORPUS_LEITURA_COLS, destino)

    assert n == 2
    texto = destino.read_text(encoding="utf-8-sig")
    linhas = texto.strip().split("\n")
    assert linhas[0].strip() == ",".join(exp.CORPUS_LEITURA_COLS)
    assert len(linhas) == 3
    # colunas fora da lista não vazam para o CSV de leitura
    assert "classifier" not in linhas[0]
    # NULL vira célula vazia, não a string "None"
    assert "None" not in texto
    assert "Vou atrasar um pouco" in texto
    assert "MENU_PRINCIPAL" in texto


def test_write_csv_aceita_linha_sem_a_coluna(tmp_path):
    destino = tmp_path / "c3.csv"
    n = exp.write_csv([{"user_input": "me avisa"}], exp.WAITLIST_COLS, destino)
    assert n == 1
    assert "me avisa" in destino.read_text(encoding="utf-8-sig")


# ── Guardas ──────────────────────────────────────────────────────────────────

def test_destino_dentro_do_repo_aborta():
    """🔴 O corpus tem user_input em claro. Não pode entrar em git."""
    repo = exp._repo_root()
    assert repo is not None, "teste roda dentro do repositório git"
    with pytest.raises(SystemExit) as exc:
        exp._guard_destino(repo / "corpus")
    assert "ABORTADO" in str(exc.value)


def test_destino_fora_do_repo_passa(tmp_path):
    exp._guard_destino(Path(tmp_path).resolve())  # não levanta


def test_describe_target_nao_expoe_a_senha():
    alvo = exp._describe_target(
        "postgresql://usuario:senha_secreta@db.exemplo.com:6543/postgres"
    )
    assert alvo["host"] == "db.exemplo.com"
    assert alvo["port"] == 6543
    assert alvo["database"] == "postgres"
    assert alvo["username"] == "usuario"
    assert "senha_secreta" not in json.dumps(alvo)


def test_nao_importa_nada_de_app():
    """Sem dependência de `app/`: o script não pode parar quando o app mudar."""
    fonte = Path(exp.__file__).read_text(encoding="utf-8")
    # só as linhas de import — a docstring FALA de `app/`, e isso é legítimo
    imports = [ln.strip() for ln in fonte.splitlines()
               if ln.startswith(("import ", "from "))]
    assert imports, "o script tem imports"
    assert not [ln for ln in imports if ln.split()[1].split(".")[0] == "app"]


def test_nenhuma_url_hardcodada():
    """Causa raiz do incidente 'local = produção'."""
    fonte = Path(exp.__file__).read_text(encoding="utf-8")
    assert "postgresql://" not in fonte
    assert "postgres://" not in fonte
    assert "supabase.com" not in fonte


def test_run_sem_database_url_aborta(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        exp.run(tmp_path, exp.WAITLIST_TERMS)
    assert "DATABASE_URL" in str(exc.value)

"""Testes S2 — "Não entendi": reexibir, oferecer atendimento, gravar `reason`.

O caso que motiva o sprint (produção, 25/08): uma cliente nova descreveu o
serviço ("Raspar na 2 e pezinho quadrado"), informou a restrição de horário
("Só posso após as 20 hrs") e explicou por que procurou a barbearia. Recebeu
"Não entendi 😅 / Escolhe uma das opções ali em cima 👆" **três vezes** — uma
linha apontando para uma lista de três a cinco minutos e três mensagens acima —
e sumiu por 1h14. Os três traces gravaram `PROCESSED` sem `reason`: do ponto de
vista da telemetria, nada aconteceu.

Cobertura:
  - Reexibição por família de estado (FSM e legado): a lista volta, a opção de
    atendimento está presente, e `dispatch.detail.reason` fica preenchido.
  - A conversa da Thayná reproduzida em AWAITING_SERVICE.
  - Aceitação da oferta: número da linha → escalada pelo caminho central.
  - Guard de formato do sender: 12 linhas entram, 10 saem, e a opção de
    atendimento sobrevive ao corte.
  - PERSISTÊNCIA do marcador da oferta pelo dispatcher REAL, nos dois
    pipelines — o fallback deixou de ser envio puro e passou a mutar
    `session.context`; se algum caminho retornasse sem `save_session`, o
    marcador se perderia e o "4" do cliente viraria seleção de lista.
  - `BOT_FALLBACK_MAX_COUNT` não existe mais em lugar nenhum.

Estratégia: FakeDB in-memory + monkeypatch (padrão test_bot_f3 / test_bot_f4).
"""
import asyncio
import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.core.config import settings
from app.infrastructure.db.models import (
    BotSession,
    CompanySettings,
    WhatsAppConnection,
)
from app.infrastructure.db.models.booking_session import BookingSession
from app.modules.booking.actions import InvalidActionError
from app.modules.whatsapp import bot_service
from app.modules.whatsapp import fallback
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp import trace
from app.modules.whatsapp.helpers import (
    HUMAN_OPTION_ROW_ID,
    HUMAN_OPTION_TITLE,
    is_universal_command,
)
from app.modules.whatsapp.handlers import escolhendo_servico as h_servico
from app.modules.whatsapp.handlers import escolhendo_turno as h_turno
from app.modules.whatsapp.helpers import resolve_input
from app.modules.whatsapp.input_parser import whatsapp_input_parser


TZ = "America/Sao_Paulo"
SP = ZoneInfo(TZ)
COMPANY_ID = uuid.uuid4()
PROF_ID    = uuid.uuid4()

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─── Fakes ────────────────────────────────────────────────────────────────────

class FakeDB:
    def __init__(self, results=None):
        self._results = dict(results or {})
        self.added = []

    def query(self, model, *rest):
        db = self

        class Q:
            def filter(self, *a, **k): return self
            def order_by(self, *a, **k): return self
            def all(self_q): return db._results.get(model, [])
            def first(self_q):
                rows = db._results.get(model, [])
                return rows[0] if rows else None

        return Q()

    def add(self, obj): self.added.append(obj)
    def flush(self): pass
    def commit(self): pass
    def refresh(self, obj): pass


def fake_session(state="MENU_PRINCIPAL", **ctx):
    base = {"customer_id": str(uuid.uuid4()), "customer_name": "Thayná"}
    base.update(ctx)
    return SimpleNamespace(id=uuid.uuid4(), state=state, context=base)


def _bs(state="AWAITING_SERVICE", ctx=None):
    return SimpleNamespace(
        id=uuid.uuid4(), company_id=COMPANY_ID, channel="whatsapp",
        company_timezone=TZ, state=state, context=dict(ctx or {}),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        last_action=None, last_action_at=None,
        customer_id=uuid.uuid4(), appointment_id=None,
    )


@pytest.fixture
def captured(monkeypatch):
    sent = []
    monkeypatch.setattr(sender, "send_text",
                        lambda inst, to, text: sent.append(("text", text)))
    monkeypatch.setattr(sender, "send_buttons",
                        lambda inst, to, text, buttons: sent.append(("buttons", text, buttons)))
    monkeypatch.setattr(sender, "send_list",
                        lambda inst, to, title, desc, rows, *a, **k: sent.append(("list", title, rows)))
    return sent


@pytest.fixture
def traced(monkeypatch):
    """Abre um trace real e o devolve — `note_dispatch` é @_safe e nunca levanta,
    mas sem trace aberto ele vira no-op e o `reason` não seria observável."""
    monkeypatch.setattr(settings, "BOT_TRACE_ENABLED", True)
    trace.start("messages.upsert", "inst", {})
    t = trace.current()
    yield t
    trace._current.set(None)


def _reason(t):
    return (t.dispatch.get("detail") or {}).get("reason")


def _titles(rows):
    return [r["title"] for r in rows]


def _assert_fallback_ok(captured, traced, *, expect_title, expect_reason):
    """As três coisas que o sprint exige, sempre juntas."""
    kind, title, rows = captured[-1]
    assert kind == "list", "a resposta precisa REEXIBIR a lista, não ser uma linha solta"
    assert title == messages.ESCOLHA_OPCAO_OPS
    titles = _titles(rows)
    assert expect_title in titles, f"a lista não voltou: {titles}"
    assert titles[-1] == HUMAN_OPTION_TITLE, "atendimento humano precisa ser a última linha"
    assert _reason(traced) == expect_reason
    return rows


# ═════════════════════════════════════════════════════════════════════════════
# 1. Reexibição por família de estado
# ═════════════════════════════════════════════════════════════════════════════

class TestReexibicaoPorFamilia:
    """Uma por família: FSM por lista, FSM por página de slots, sub-estado de
    turno, e legado (last_list). Os quatro caminhos que montam lista diferente.
    """

    def test_fsm_awaiting_service_reexibe(self, captured, traced, monkeypatch):
        """A CONVERSA DA THAYNÁ — o teste que dá nome ao sprint.

        "Raspar na 2 e pezinho quadrado" em AWAITING_SERVICE. Antes: uma linha
        apontando para cima. Agora: a lista de serviços de volta, com saída
        para uma pessoa, e o motivo gravado.
        """
        bs = _bs("AWAITING_SERVICE", {
            "last_listed_services": [
                {"row_key": "svc_1", "name": "Corte", "price": "40.00", "duration_minutes": 30},
                {"row_key": "svc_2", "name": "Corte + Barba", "price": "60.00", "duration_minutes": 60},
            ],
        })
        db = FakeDB({BookingSession: [bs]})
        session = fake_session("AWAITING_SERVICE", booking_session_id=str(bs.id))

        bot_service._handle_booking_state(
            db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net",
            "Raspar na 2 e pezinho quadrado", TZ,
        )

        rows = _assert_fallback_ok(
            captured, traced,
            expect_title="Corte",
            expect_reason=fallback.REASON_UNRECOGNIZED,
        )
        # A lista reexibida é a que o cliente via: serviços + "← Voltar" + atendimento
        assert _titles(rows) == ["Corte", "Corte + Barba", "← Voltar", HUMAN_OPTION_TITLE]
        assert traced.dispatch["detail"]["origin"] == "booking_fsm.parse"

    def test_fsm_awaiting_time_reexibe_a_pagina(self, captured, traced, monkeypatch):
        """AWAITING_TIME: a lista reexibida é a PÁGINA, não o dia inteiro —
        mesma fonte que o matching numérico usa (invariante do F3)."""
        monkeypatch.setattr(settings, "BOT_MAX_SLOTS_DISPLAYED", 6)
        slots = []
        for i in range(10):
            start = datetime(2026, 7, 20, 9, 0, tzinfo=SP) + timedelta(minutes=30 * i)
            slots.append({
                "start_at": start.isoformat(), "end_at": start.isoformat(),
                "professional_id": str(PROF_ID), "professional_name": "Maria",
                "row_key": f"slot_{i + 1}",
            })
        bs = _bs("AWAITING_TIME", {"last_listed_slots": slots, "slot_offset": 0})
        db = FakeDB({BookingSession: [bs]})
        session = fake_session("AWAITING_TIME", booking_session_id=str(bs.id))

        bot_service._handle_booking_state(
            db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net",
            "Só posso após as 20 hrs", TZ,
        )

        _, _, rows = captured[-1]
        titles = _titles(rows)
        # 6 slots da página + "Mais tarde →" + "← Voltar" + atendimento = 9
        assert len(rows) == 9
        assert titles[-1] == HUMAN_OPTION_TITLE
        assert "Mais tarde →" in titles
        assert _reason(traced) == fallback.REASON_UNRECOGNIZED

    def test_substate_turno_reexibe(self, captured, traced):
        shifts = [
            {"shift": "manha", "label": "Manhã", "slot_count": 6,
             "has_availability": True, "row_key": "manha"},
            {"shift": "tarde", "label": "Tarde", "slot_count": 12,
             "has_availability": True, "row_key": "tarde"},
        ]
        bs = _bs("AWAITING_TIME", {
            bot_service.BOT_SUBSTATE_KEY: bot_service.SUBSTATE_SHIFT,
            "last_listed_shifts": shifts,
        })
        db = FakeDB({BookingSession: [bs]})
        session = fake_session("AWAITING_TIME", booking_session_id=str(bs.id))

        bot_service._handle_booking_state(
            db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net",
            "por isso estou procurando por vcs", TZ,
        )

        _assert_fallback_ok(
            captured, traced,
            expect_title="Manhã (6 horários)",
            expect_reason=fallback.REASON_UNRECOGNIZED,
        )

    def test_legado_le_last_list(self, captured, traced):
        """Handler legado: a lista vem de `session.context["last_list"]` — os
        22 sites não precisam saber montar lista nenhuma."""
        session = fake_session("ESCOLHENDO_SERVICO", last_list=[
            {"row_id": "s1", "payload": "s1", "service_name": "Corte", "title": "Corte"},
            {"row_id": "s2", "payload": "s2", "service_name": "Barba", "title": "Barba"},
        ])

        h_servico.handle(
            FakeDB(), session, COMPANY_ID, "5511999@s.whatsapp.net", "inst",
            "quanto custa?", resolve_input=resolve_input,
            start_escolhendo_profissional=lambda *a, **k: None,
        )

        _assert_fallback_ok(
            captured, traced,
            expect_title="Corte",
            expect_reason=fallback.REASON_UNRECOGNIZED,
        )

    def test_legado_turno(self, captured, traced):
        session = fake_session("ESCOLHENDO_TURNO", last_list=[
            {"row_id": "turno_manha", "payload": "manha", "title": "Manhã (3 horários)"},
            {"row_id": "turno_tarde", "payload": "tarde", "title": "Tarde (5 horários)"},
        ])

        h_turno.handle(
            FakeDB(), session, COMPANY_ID, "5511999@s.whatsapp.net", "inst",
            "de manhãzinha bem cedo se der", resolve_input=resolve_input,
            start_escolhendo_horario=lambda *a, **k: None,
        )

        _assert_fallback_ok(
            captured, traced,
            expect_title="Manhã (3 horários)",
            expect_reason=fallback.REASON_UNRECOGNIZED,
        )


# ═════════════════════════════════════════════════════════════════════════════
# 2. Valores de `reason`
# ═════════════════════════════════════════════════════════════════════════════

class TestReason:
    """Os valores viram série histórica. Cada um responde uma pergunta que os
    outros não respondem — e todos têm a MESMA aparência externa."""

    def test_texto_livre_nao_reconhecido(self, captured, traced):
        session = fake_session(last_list=[{"row_id": "a", "payload": "a", "title": "Corte"}])
        fallback.not_understood(session, "inst", "to", origin="t", user_input="oi tudo bem")
        assert _reason(traced) == fallback.REASON_UNRECOGNIZED

    def test_input_vazio_e_distinto(self, captured, traced):
        """Áudio/imagem/sticker chegam como "" (S23). Não é falha de compreensão —
        e confundir os dois esconderia a classe inteira na agregação."""
        session = fake_session(last_list=[{"row_id": "a", "payload": "a", "title": "Corte"}])
        fallback.not_understood(session, "inst", "to", origin="t", user_input="")
        assert _reason(traced) == fallback.REASON_NO_TEXT

    def test_nao_colide_com_o_empty_input_do_classificador(self):
        """⚠️ O gate do classificador grava `empty_input` desde o F5a, com outro
        significado: lá o classificador NÃO RODOU; aqui o handler não conseguiu
        PARSEAR. Num `GROUP BY reason` sem o `handler` — que é como qualquer um
        vai agregar primeiro — os dois se somariam."""
        assert fallback.REASON_NO_TEXT != "empty_input"

        src = io.open(
            os.path.join(REPO_ROOT, "app", "modules", "whatsapp", "bot_service.py"),
            encoding="utf-8",
        ).read()
        assert 'reason="empty_input"' in src, (
            "o gate do classificador mudou de valor — reavalie a distinção"
        )

        # E os cinco valores do fallback são distintos entre si.
        valores = [
            fallback.REASON_UNRECOGNIZED, fallback.REASON_NO_TEXT,
            fallback.REASON_NO_OPTIONS, fallback.REASON_INVALID_SELECTION,
            fallback.REASON_INVALID_ACTION,
        ]
        assert len(set(valores)) == len(valores)

    def test_sem_lista_no_contexto(self, captured, traced):
        """Defeito nosso, não do cliente: não havia o que casar nem o que reexibir."""
        session = fake_session(last_list=[])
        fallback.not_understood(session, "inst", "to", origin="t", user_input="corte")
        assert _reason(traced) == fallback.REASON_NO_OPTIONS
        assert captured[-1] == ("text", messages.NAO_ENTENDI_SEM_LISTA)

    def test_selecao_invalida_e_explicita(self, captured, traced):
        session = fake_session(last_list=[{"row_id": "a", "payload": "a", "title": "Corte"}])
        fallback.not_understood(
            session, "inst", "to", origin="t", user_input="1",
            reason=fallback.REASON_INVALID_SELECTION,
        )
        assert _reason(traced) == fallback.REASON_INVALID_SELECTION

    def test_invalid_action_do_engine(self, captured, traced, monkeypatch):
        bs = _bs("AWAITING_SERVICE", {
            "last_listed_services": [{"row_key": "svc_1", "name": "Corte"}],
        })
        db = FakeDB({BookingSession: [bs]})
        session = fake_session("AWAITING_SERVICE", booking_session_id=str(bs.id))

        from app.modules.booking.engine import booking_engine
        monkeypatch.setattr(
            booking_engine, "update",
            lambda *a, **k: (_ for _ in ()).throw(InvalidActionError("nope")),
        )

        bot_service._handle_booking_state(
            db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "1", TZ,
        )
        assert _reason(traced) == fallback.REASON_INVALID_ACTION

    def test_origin_distingue_os_sites(self, captured, traced):
        """`handler` é um valor só (greppável); quem separa os 22 sites é `origin`,
        e o recorte por estado vem da coluna `fsm_state` do trace."""
        session = fake_session(last_list=[{"row_id": "a", "payload": "a", "title": "Corte"}])
        fallback.not_understood(
            session, "inst", "to", origin="escolhendo_servico.handle", user_input="x",
        )
        assert traced.dispatch["handler"] == fallback.TRACE_HANDLER
        assert traced.dispatch["detail"]["origin"] == "escolhendo_servico.handle"
        assert fallback.TRACE_HANDLER in traced.dispatch["path"]


# ═════════════════════════════════════════════════════════════════════════════
# 3. A oferta de atendimento — na PRIMEIRA falha, e ela funciona
# ═════════════════════════════════════════════════════════════════════════════

class TestOfertaDeAtendimento:

    def test_primeira_falha_ja_oferece(self, captured, traced):
        """Decisão D6: sem contador. Insistir cansa — a Thayná recebeu a mesma
        resposta três vezes e sumiu por 1h14."""
        session = fake_session(last_list=[{"row_id": "a", "payload": "a", "title": "Corte"}])
        fallback.not_understood(session, "inst", "to", origin="t", user_input="oi")
        _, _, rows = captured[-1]
        assert rows[-1]["rowId"] == HUMAN_OPTION_ROW_ID

    def test_clique_escala_por_comando_universal(self):
        """O rowId e o título exatos são comando universal — o clique escala em
        qualquer estado sem que nenhum dos 22 handlers saiba escalar."""
        assert is_universal_command(HUMAN_OPTION_ROW_ID) == "humano"
        assert is_universal_command(HUMAN_OPTION_TITLE) == "humano"
        assert is_universal_command(HUMAN_OPTION_TITLE.upper()) == "humano"

    def test_numero_da_linha_e_aceito(self, captured, traced):
        """O formato real hoje é texto numerado (POLLS e BUTTONS desligados):
        o cliente digita o número, não o rowId."""
        session = fake_session(last_list=[
            {"row_id": "a", "payload": "a", "title": "Corte"},
            {"row_id": "b", "payload": "b", "title": "Barba"},
        ])
        fallback.not_understood(session, "inst", "to", origin="t", user_input="oi")
        # 2 opções + atendimento → o atendimento é o "3"
        assert session.context[fallback.OFFER_KEY]["index"] == 3
        assert fallback.take_offer(session, "3") is True

    def test_oferta_vale_uma_mensagem_so(self, captured, traced):
        """O marcador é consumido mesmo quando recusado: um "3" digitado dois
        turnos depois é seleção de lista, não pedido de atendente."""
        session = fake_session(last_list=[{"row_id": "a", "payload": "a", "title": "Corte"}])
        fallback.not_understood(session, "inst", "to", origin="t", user_input="oi")
        assert fallback.take_offer(session, "1") is False    # recusou → consome
        assert fallback.OFFER_KEY not in session.context
        assert fallback.take_offer(session, "2") is False    # marcador já foi

    def test_sem_oferta_pendente_nao_escala(self):
        session = fake_session()
        assert fallback.take_offer(session, "2") is False

    def test_numeros_das_linhas_anteriores_nao_deslocam(self, captured, traced):
        """A opção humana é a ÚLTIMA linha, de propósito: quem estava prestes a
        digitar "2" continua acertando o mesmo item."""
        options = [
            {"row_id": "a", "payload": "a", "title": "Corte"},
            {"row_id": "b", "payload": "b", "title": "Barba"},
        ]
        session = fake_session(last_list=options)
        fallback.not_understood(session, "inst", "to", origin="t", user_input="oi")
        _, _, rows = captured[-1]
        assert [r["rowId"] for r in rows][:2] == ["a", "b"]


# ═════════════════════════════════════════════════════════════════════════════
# 4. Guard de formato do sender
# ═════════════════════════════════════════════════════════════════════════════

class TestGuardDeFormato:

    def test_doze_linhas_entram_dez_saem(self, monkeypatch):
        got = {}
        monkeypatch.setattr(settings, "BOT_USE_POLLS", False)
        monkeypatch.setattr(
            sender.evolution_client, "send_list",
            lambda inst, to, title, desc, btn, rows, sec: got.update(rows=rows),
        )
        rows = [{"rowId": f"r{i}", "title": f"Serviço {i}", "description": ""} for i in range(12)]
        sender.send_list("inst", "to", "t", "d", rows)
        assert len(got["rows"]) == 10

    def test_opcao_de_atendimento_sobrevive_ao_corte(self, monkeypatch):
        """⚠️ Cortar pelo fim (`rows[:10]`) descartaria justamente a opção de
        atendimento — que é sempre a última — e apagaria o objetivo do sprint."""
        got = {}
        monkeypatch.setattr(settings, "BOT_USE_POLLS", False)
        monkeypatch.setattr(
            sender.evolution_client, "send_list",
            lambda inst, to, title, desc, btn, rows, sec: got.update(rows=rows),
        )
        rows = [{"rowId": f"r{i}", "title": f"Serviço {i}", "description": ""} for i in range(12)]
        rows.append({"rowId": "nav_voltar", "title": "← Voltar", "description": ""})
        rows.append({"rowId": HUMAN_OPTION_ROW_ID, "title": HUMAN_OPTION_TITLE, "description": ""})

        sender.send_list("inst", "to", "t", "d", rows)

        out_ids = [r["rowId"] for r in got["rows"]]
        assert len(out_ids) == 10
        assert HUMAN_OPTION_ROW_ID in out_ids
        assert "nav_voltar" in out_ids
        # o corte saiu do CONTEÚDO, e a ordem original foi mantida
        assert out_ids[:8] == [f"r{i}" for i in range(8)]
        assert out_ids[-2:] == ["nav_voltar", HUMAN_OPTION_ROW_ID]

    def test_botoes_limitados_a_tres(self, monkeypatch):
        got = {}
        monkeypatch.setattr(settings, "BOT_USE_POLLS", False)
        monkeypatch.setattr(settings, "BOT_USE_BUTTONS", True)
        monkeypatch.setattr(
            sender.evolution_client, "send_buttons",
            lambda inst, to, text, buttons: got.update(buttons=buttons),
        )
        buttons = [
            {"buttonId": f"b{i}", "buttonText": {"displayText": f"Opção {i}"}}
            for i in range(5)
        ]
        sender.send_buttons("inst", "to", "t", buttons)
        assert len(got["buttons"]) == 3

    def test_lista_dentro_do_limite_passa_intacta(self, monkeypatch):
        got = {}
        monkeypatch.setattr(settings, "BOT_USE_POLLS", False)
        monkeypatch.setattr(
            sender.evolution_client, "send_list",
            lambda inst, to, title, desc, btn, rows, sec: got.update(rows=rows),
        )
        rows = [{"rowId": f"r{i}", "title": f"S{i}", "description": ""} for i in range(10)]
        sender.send_list("inst", "to", "t", "d", rows)
        assert len(got["rows"]) == 10

    def test_awaiting_time_cheio_cabe_exatamente(self, monkeypatch):
        """⚠️ O risco declarado do sprint: AWAITING_TIME é o pior caso.
        BOT_MAX_SLOTS_DISPLAYED=6 + "← Mais cedo" + "Mais tarde →" + "← Voltar"
        + atendimento = 10. Cabe — mas sem folga: mexer no page size passa do
        limite e o guard passa a cortar slot real."""
        assert settings.BOT_MAX_SLOTS_DISPLAYED + 4 <= sender.MAX_LIST_ROWS


# ═════════════════════════════════════════════════════════════════════════════
# 5. BOT_FALLBACK_MAX_COUNT não existe mais
# ═════════════════════════════════════════════════════════════════════════════

def test_bot_fallback_max_count_nao_existe():
    """A constante declarava "Fallbacks antes de oferecer atendente humano" e
    era a ÚNICA ocorrência no repositório — o contador nunca foi implementado.
    Mantê-la criaria uma terceira fonte de verdade sobre o fallback, agora que
    a decisão é oferecer na primeira falha (D6)."""
    assert not hasattr(settings, "BOT_FALLBACK_MAX_COUNT")

    hits = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [
            d for d in dirs
            if d not in ("__pycache__", "venv", ".git", "node_modules", "docs", ".pytest_cache")
        ]
        for f in files:
            if not f.endswith((".py", ".env", ".example")):
                continue
            path = os.path.join(root, f)
            if os.path.abspath(path) == os.path.abspath(__file__):
                continue
            try:
                if "BOT_FALLBACK_MAX_COUNT" in io.open(path, encoding="utf-8", errors="ignore").read():
                    hits.append(os.path.relpath(path, REPO_ROOT))
            except OSError:
                pass
    assert hits == [], f"BOT_FALLBACK_MAX_COUNT ainda presente em: {hits}"


# ═════════════════════════════════════════════════════════════════════════════
# 6. visible_options — fonte única entre matching e reexibição
# ═════════════════════════════════════════════════════════════════════════════

class TestVisibleOptions:
    """Se o que se REEXIBE divergir do que se CASA, o número que o cliente digita
    passa a apontar para outra linha. Foi esse desalinhamento que o F3 achou na
    paginação de horários — por isso as duas coisas saem da mesma função."""

    def test_awaiting_service_espelha_o_matching(self):
        ctx = {"last_listed_services": [
            {"row_key": "svc_1", "name": "Corte"},
            {"row_key": "svc_2", "name": "Barba"},
        ]}
        opts = whatsapp_input_parser.visible_options("AWAITING_SERVICE", ctx)
        assert [o["title"] for o in opts] == ["Corte", "Barba", "← Voltar"]
        # o número que o cliente vê resolve para a mesma linha
        assert resolve_input("2", opts) == "svc_2"
        assert resolve_input("3", opts) == "nav_voltar"

    def test_awaiting_confirmation(self):
        opts = whatsapp_input_parser.visible_options("AWAITING_CONFIRMATION", {})
        assert [o["title"] for o in opts] == ["Confirmar", "Alterar horário", "Cancelar"]

    def test_contexto_vazio_devolve_lista_vazia(self):
        assert whatsapp_input_parser.visible_options("AWAITING_SERVICE", {}) == []
        assert whatsapp_input_parser.visible_options("ESTADO_INEXISTENTE", {}) == []


# ═════════════════════════════════════════════════════════════════════════════
# 7. Persistência do marcador — pelo dispatcher REAL, nos dois pipelines
# ═════════════════════════════════════════════════════════════════════════════
#
# ⚠️ Antes do S2 o caminho de fallback era envio PURO: nenhuma mutação de
# estado. Agora ele grava `fallback_offer` em `session.context`, e esse dado
# precisa sobreviver até a mensagem SEGUINTE — que relê a sessão do banco.
#
# Ler o código e concluir "o `try` do dispatcher envolve todos os branches e o
# `save_session` vem depois, inclusive após exceção" é argumento. Estes testes
# são a prova: dirigem `handle_inbound_message` de ponta a ponta e conferem que
# o commit aconteceu e que a mensagem seguinte escala de verdade.

JID = "5511987654321@s.whatsapp.net"
INSTANCE = "inst-s2"


def _criterion_matches(obj, c) -> bool:
    key = c.left.key
    actual = getattr(obj, key, None)
    right = c.right
    right_cls = right.__class__.__name__
    if right_cls == "True_":
        val = True
    elif right_cls == "False_":
        val = False
    elif right_cls == "Null":
        val = None
    else:
        val = getattr(right, "value", None)
    op_name = getattr(c.operator, "__name__", "")
    if op_name in ("is_", "is_op"):
        return actual is val
    if op_name in ("ne", "is_not", "is_not_op"):
        return actual != val
    return actual == val


class _Query:
    def __init__(self, items):
        self.items = list(items)

    def filter(self, *criteria):
        return _Query([i for i in self.items if all(_criterion_matches(i, c) for c in criteria)])

    def with_for_update(self, *a, **k): return self
    def order_by(self, *a, **k): return self
    def limit(self, n): return _Query(self.items[:n])
    def first(self): return self.items[0] if self.items else None
    def all(self): return list(self.items)


class DispatchDB:
    """FakeDB com avaliação real de filtros + contador de commits.

    `commits` é o que interessa aqui: `save_session` faz `db.commit()`, então
    um commit a mais depois do fallback é a evidência de que o marcador foi
    persistido — não só escrito em memória.
    """

    def __init__(self):
        self.stores = {}
        self.commits = 0

    def _store(self, model): return self.stores.setdefault(model, [])
    def query(self, model, *rest): return _Query(self._store(model))

    def add(self, obj):
        if getattr(obj, "id", None) is None and hasattr(obj, "id"):
            obj.id = uuid.uuid4()
        self._store(type(obj)).append(obj)

    def commit(self): self.commits += 1
    def flush(self): pass
    def refresh(self, obj): pass
    def rollback(self): pass
    def close(self): pass


def _dispatch_db(state, bot_ctx=None, booking_sessions=()):
    db = DispatchDB()
    cid = uuid.uuid4()
    db._store(WhatsAppConnection).append(
        SimpleNamespace(id=uuid.uuid4(), company_id=cid, instance_name=INSTANCE)
    )
    db._store(CompanySettings).append(SimpleNamespace(company_id=cid, bot_enabled=True))
    db._store(bot_service.Company).append(
        SimpleNamespace(id=cid, name="Barbearia", timezone=TZ)
    )
    session = SimpleNamespace(
        id=uuid.uuid4(), company_id=cid, whatsapp_id=JID, state=state,
        context={"customer_id": str(uuid.uuid4()), "customer_name": "Thayná",
                 **(bot_ctx or {})},
        last_message_id=None, expires_at=None,
    )
    db._store(BotSession).append(session)
    for bs in booking_sessions:
        db._store(BookingSession).append(bs)
    return db, cid, session


def _inbound(db, text, msg_id):
    asyncio.run(bot_service.handle_inbound_message(db, INSTANCE, {
        "key": {"id": msg_id, "fromMe": False, "remoteJid": JID},
        "pushName": "Thayná",
        "message": {"conversation": text},
    }))


@pytest.fixture
def saves(monkeypatch):
    """Snapshot do `session.context` no instante de CADA `save_session`.

    ⚠️ Sem isto os testes desta seção seriam vacuosos: o FakeDB guarda o mesmo
    objeto em memória, então o marcador "sobreviveria" à segunda mensagem mesmo
    que nada fosse comitado. O que precisa ser provado é que o commit que segue
    o fallback JÁ ENXERGA o marcador — é isso que faz a mensagem seguinte, que
    relê a sessão do banco, encontrá-lo.
    """
    snaps = []
    real = bot_service.save_session

    def _spy(db, session):
        snaps.append(dict(getattr(session, "context", None) or {}))
        return real(db, session)

    monkeypatch.setattr(bot_service, "save_session", _spy)
    return snaps


def _marcador_foi_comitado(snaps) -> bool:
    """True se ALGUM save_session viu o marcador no contexto."""
    return any(fallback.OFFER_KEY in snap for snap in snaps)


@pytest.fixture
def dispatcher_sender(monkeypatch):
    """Captura no evolution_client, não no sender: o guard de formato e o
    fallback de texto numerado do sender precisam rodar de verdade."""
    out = []
    import app.modules.whatsapp.evolution_client as ec
    monkeypatch.setattr(settings, "BOT_USE_POLLS", False)
    monkeypatch.setattr(settings, "BOT_USE_BUTTONS", False)
    monkeypatch.setattr(ec, "send_text", lambda i, to, t: out.append(("text", t)))
    monkeypatch.setattr(ec, "send_list",
                        lambda i, to, ti, d, b, rows, sec: out.append(("list", ti, rows)))
    monkeypatch.setattr(ec, "send_buttons", lambda i, to, t, b: out.append(("buttons", t)))
    return out


class TestPersistenciaDoMarcador:

    def test_pipeline_fsm_persiste_e_escala_na_mensagem_seguinte(
        self, dispatcher_sender, saves, monkeypatch,
    ):
        """Pipeline BookingEngine: fallback → marcador comitado → o número da
        linha na mensagem SEGUINTE escala pelo caminho central."""
        bs = _bs("AWAITING_SERVICE", {
            "last_listed_services": [
                {"row_key": "svc_1", "name": "Corte"},
                {"row_key": "svc_2", "name": "Corte + Barba"},
            ],
        })
        db, cid, session = _dispatch_db(
            "AWAITING_SERVICE", {"booking_session_id": str(bs.id)}, [bs],
        )
        bs.company_id = cid

        eventos = []
        monkeypatch.setattr(
            bot_service, "_publish_conversation_escalated",
            lambda sess, company_id, trigger: eventos.append(trigger),
        )

        commits_antes = db.commits
        _inbound(db, "Raspar na 2 e pezinho quadrado", "MSG-1")

        # 1. o marcador ficou no contexto...
        oferta = session.context.get(fallback.OFFER_KEY)
        assert oferta is not None, "o marcador da oferta não sobreviveu ao dispatcher"
        # serviços + "← Voltar" + atendimento
        assert oferta["index"] == 4
        # 2. ...e o save_session que veio depois do fallback JÁ o enxergava —
        #    é isso que o próximo `get_session_locked` vai reler do banco
        assert db.commits > commits_antes
        assert _marcador_foi_comitado(saves), (
            "o marcador foi escrito em memória mas nenhum save_session o viu"
        )

        # 3. a mensagem seguinte com o número escala de verdade
        _inbound(db, "4", "MSG-2")
        assert session.state == bot_service.STATE_HUMANO
        assert eventos == ["FALLBACK"], "a escalada precisa passar por _escalate_to_human"
        assert any(k == "text" and t == messages.HUMANO_CHAMADO
                   for k, t, *_ in dispatcher_sender)

    def test_pipeline_legado_persiste_e_escala(self, dispatcher_sender, saves, monkeypatch):
        """Handler legado (ESCOLHENDO_SERVICO): mesmo contrato, outro caminho."""
        db, cid, session = _dispatch_db("ESCOLHENDO_SERVICO", {
            "last_list": [
                {"row_id": "s1", "payload": "s1", "service_name": "Corte", "title": "Corte"},
                {"row_id": "s2", "payload": "s2", "service_name": "Barba", "title": "Barba"},
            ],
        })
        eventos = []
        monkeypatch.setattr(
            bot_service, "_publish_conversation_escalated",
            lambda sess, company_id, trigger: eventos.append(trigger),
        )

        commits_antes = db.commits
        _inbound(db, "quanto custa o degradê?", "MSG-1")

        oferta = session.context.get(fallback.OFFER_KEY)
        assert oferta is not None
        assert oferta["index"] == 3          # 2 serviços + atendimento
        assert db.commits > commits_antes
        assert _marcador_foi_comitado(saves)

        _inbound(db, "3", "MSG-2")
        assert session.state == bot_service.STATE_HUMANO
        assert eventos == ["FALLBACK"]

    def test_confirmar_nome_escala_apesar_dos_universais_desligados(
        self, dispatcher_sender, saves, monkeypatch,
    ):
        """⚠️ CONFIRMAR_NOME é um dos dois estados onde os comandos universais
        estão desligados de propósito (cliente chamado "Ajuda" não deve
        escalar). É por isso que o marcador é consumido ANTES daquele guard —
        senão este seria o único estado sem saída para uma pessoa."""
        db, cid, session = _dispatch_db("CONFIRMAR_NOME", {"nome_temp": "Thayná"})
        eventos = []
        monkeypatch.setattr(
            bot_service, "_publish_conversation_escalated",
            lambda sess, company_id, trigger: eventos.append(trigger),
        )

        _inbound(db, "não sei o que responder", "MSG-1")
        assert session.context[fallback.OFFER_KEY]["index"] == 3   # Sim, Corrigir, atendimento
        assert _marcador_foi_comitado(saves)

        _inbound(db, "3", "MSG-2")
        assert session.state == bot_service.STATE_HUMANO
        assert eventos == ["FALLBACK"]

    def test_recusa_consome_e_a_selecao_seguinte_funciona(
        self, dispatcher_sender, monkeypatch,
    ):
        """A oferta vale UMA mensagem: quem não a aceita segue para o handler do
        estado com o contexto limpo, e o número volta a ser seleção de lista."""
        db, cid, session = _dispatch_db("ESCOLHENDO_SERVICO", {
            "last_list": [
                {"row_id": "s1", "payload": "s1", "service_name": "Corte", "title": "Corte"},
                {"row_id": "s2", "payload": "s2", "service_name": "Barba", "title": "Barba"},
            ],
        })
        monkeypatch.setattr(
            bot_service, "_start_escolhendo_profissional",
            lambda *a, **k: None,
        )

        _inbound(db, "quanto custa?", "MSG-1")
        assert fallback.OFFER_KEY in session.context

        _inbound(db, "1", "MSG-2")           # escolheu Corte, não o atendente
        assert session.state != bot_service.STATE_HUMANO
        assert fallback.OFFER_KEY not in session.context
        assert session.context["service_id"] == "s1"

    def test_marcador_persiste_mesmo_se_o_handler_explodir_depois(
        self, dispatcher_sender, saves, monkeypatch,
    ):
        """O `save_session` do dispatcher roda no caminho de exceção também —
        o que garante que nenhum fallback fica sem persistir por causa de um
        erro posterior no mesmo turno."""
        db, cid, session = _dispatch_db("ESCOLHENDO_TURNO", {
            "last_list": [
                {"row_id": "turno_manha", "payload": "manha", "title": "Manhã (3 horários)"},
            ],
        })

        def _explode(*a, **k):
            raise RuntimeError("falha depois do fallback")

        # o handler de turno chama o fallback e retorna; forçamos a explosão no
        # passo seguinte do mesmo turno para exercitar o `except` do dispatcher
        real = h_turno.handle

        def _handle_and_explode(*a, **k):
            real(*a, **k)
            _explode()

        monkeypatch.setattr(bot_service.h_turno, "handle", _handle_and_explode)

        _inbound(db, "de manhãzinha bem cedo", "MSG-1")
        assert session.context.get(fallback.OFFER_KEY) is not None
        assert db.commits > 0
        assert _marcador_foi_comitado(saves)

    def test_o_spy_nao_e_vacuoso(self, dispatcher_sender, saves):
        """Guarda do guarda: numa mensagem que o bot ENTENDE não há marcador
        nenhum nos snapshots. Se `_marcador_foi_comitado` devolvesse True aqui,
        os asserts acima não estariam provando nada."""
        db, cid, session = _dispatch_db("ESCOLHENDO_SERVICO", {
            "last_list": [
                {"row_id": "s1", "payload": "s1", "service_name": "Corte", "title": "Corte"},
            ],
        })
        _inbound(db, "1", "MSG-1")           # clicou certo — sem fallback
        assert saves, "nenhum save_session foi observado"
        assert not _marcador_foi_comitado(saves)


"""Testes S5 — validação de nome e mídia em `AGUARDANDO_NOME`.

Dois defeitos no mesmo handler:

1. **A primeira mensagem do cliente virava o nome dele.** A única validação era
   `len(nome) >= 2`. Dez registros em produção desde abril, todos com
   agendamentos ativos — de `"Blz"` à resposta de cinco linhas do Pascoal. E o
   dano atravessa barbearias: `handle_confirmando_nome` grava em
   `PaladinoIdentity.name`, que é identidade GLOBAL.

2. **Mídia era tratada como tentativa fracassada de dizer o nome.** Produção,
   25/08: a cliente mandou a foto do corte de referência e o bot respondeu
   "Pode me dizer seu nome novamente?". Não foi ignorar — foi pedir de volta uma
   coisa que ela não estava tentando dar.

⚠️ O eixo destes testes é ASSIMÉTRICO, e de propósito. `AGUARDANDO_NOME` é a
primeira interação de todo cliente novo: rejeitar `"Blz"` é acerto; rejeitar
`"Tobin"` prende gente antes do primeiro agendamento. Por isso os 7 nomes reais
têm classe própria, e o `Tobin` é nomeado no teste — é ele que quebra se alguém
"apertar" a regra depois.

Estratégia: FakeDB in-memory + monkeypatch, e o dispatcher REAL onde o que se
prova é o caminho (a oferta de atendente, e a chegada a `PaladinoIdentity`).
"""
import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.infrastructure.db.models import (
    BotSession,
    CompanySettings,
    WhatsAppConnection,
)
from app.modules.whatsapp import bot_service
from app.modules.whatsapp import fallback
from app.modules.whatsapp import messages
from app.modules.whatsapp import name_validator
from app.modules.whatsapp import sender
from app.modules.whatsapp import trace
from app.modules.whatsapp.handlers import aguardando_nome as h_nome
from app.modules.whatsapp.helpers import HUMAN_OPTION_ROW_ID, HUMAN_OPTION_TITLE

TZ = "America/Sao_Paulo"
INSTANCE = "inst"
JID = "5511999999999@s.whatsapp.net"


# ═════════════════════════════════════════════════════════════════════════════
# Corpora — os três conjuntos que decidem se a regra está calibrada
# ═════════════════════════════════════════════════════════════════════════════

# Os 10 registros contaminados de produção (§10.2), tal como estão no banco.
CONTAMINADOS = [
    "Blz",
    "Bom?",
    "Bom dia”",
    "Quero cortar meu cabelo com você hoje. Você tem horário hoje? Se sim, qual horário?",
    "Quais seriam os horários disponíveis para corte com o Ivan?",
    "como está a disponibilidade pra corte e barba?",
    "Meu horário amanhã está confirmado às 13h?",
    "Tô querendo fazer minha barba e cortar o cabelo na sexta. Vai funcionar?",
    "Faço e produzo sites profissionais rápidos e baratos, algo simples que funcione",
    "Já está na barbearia nova? / Se sim, marca / 2 cortes / 1 barba / "
    "Sábado 02/05 / 10:00 / Aqui é o Pascoal Júnior",
]

# As 6 entradas de `AGUARDANDO_NOME` no corpus exportado que NÃO eram nomes.
# Duas famílias: resposta à saudação, e o pedido já na primeira mensagem.
CORPUS_NAO_NOME = [
    "Tudo bem ?",
    "tudo bom?",
    "Tudo bem",
    "Aonde vc tá",
    "Tem horário hoje após as 18 hrs?",
    "Queria marcar um horário",
]

# ⚠️ Os nomes reais. `Tobin` é o teste da regra — curto, sem acento, incomum:
# qualquer heurística que tente reconhecer o que É nome o rejeita.
NOMES_REAIS = ["Thayná", "Antônio", "Daniel", "Guilherme", "Eduardo", "Ivan", "Tobin"]


# ═════════════════════════════════════════════════════════════════════════════
# Fakes
# ═════════════════════════════════════════════════════════════════════════════

def _criterion_matches(item, c):
    try:
        col = c.left
        val = c.right.value
    except AttributeError:
        return True
    actual = getattr(item, col.key, None)
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


def _dispatch_db(state, bot_ctx=None):
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
        context=dict(bot_ctx or {}), last_message_id=None, expires_at=None,
    )
    db._store(BotSession).append(session)
    return db, cid, session


def _inbound(db, message, msg_id, message_type=None):
    """Entrega um evento `messages.upsert` cru ao dispatcher real."""
    payload = {
        "key": {"id": msg_id, "fromMe": False, "remoteJid": JID},
        "pushName": "Cliente",
        "message": message,
    }
    if message_type:
        payload["messageType"] = message_type
    asyncio.run(bot_service.handle_inbound_message(db, INSTANCE, payload))


def _texto(msg):
    return {"conversation": msg}


@pytest.fixture
def captured(monkeypatch):
    sent = []
    monkeypatch.setattr(sender, "send_text",
                        lambda inst, to, text: sent.append(("text", text, None)))
    monkeypatch.setattr(sender, "send_buttons",
                        lambda inst, to, text, buttons: sent.append(("buttons", text, buttons)))
    monkeypatch.setattr(sender, "send_list",
                        lambda inst, to, title, desc, rows, *a, **k: sent.append(("list", title, rows)))
    return sent


@pytest.fixture
def traced(monkeypatch):
    monkeypatch.setattr(settings, "BOT_TRACE_ENABLED", True)
    trace.start("messages.upsert", INSTANCE, {})
    t = trace.current()
    yield t
    trace._current.set(None)


def _reason(t):
    return (t.dispatch.get("detail") or {}).get("reason")


def _handle(session, user_input, message_type="", captured_db=None):
    h_nome.handle_aguardando_nome(
        captured_db or DispatchDB(), session, uuid.uuid4(), JID, INSTANCE,
        user_input, message_type=message_type,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 1. A regra — os três corpora
# ═════════════════════════════════════════════════════════════════════════════

class TestRegraContraOsCorpora:
    """Os únicos testes que decidem se o sprint acertou. Tudo o mais é encanamento."""

    @pytest.mark.parametrize("entrada", CONTAMINADOS)
    def test_os_10_contaminados_sao_rejeitados(self, entrada):
        ok, motivo, _ = name_validator.validate_name(entrada)
        assert not ok, f"aceito como nome: {entrada!r}"
        assert motivo

    def test_a_frase_de_cinco_linhas_do_pascoal(self):
        """O registro mais longo — e o que carrega um nome REAL no fim.

        ⚠️ "Aqui é o Pascoal Júnior" está lá dentro, e o descascador de prefixo
        reconhece essa forma. O que impede a extração de acontecer aqui é a
        ORDEM: o prefixo só casa no INÍCIO do texto, e este começa com uma
        pergunta. Se alguém trocar o `match` por um `search`, este teste quebra.
        """
        ok, motivo, _ = name_validator.validate_name(CONTAMINADOS[-1])
        assert not ok
        assert motivo == name_validator.R_QUESTION

    @pytest.mark.parametrize("entrada", CORPUS_NAO_NOME)
    def test_as_6_nao_nomes_do_corpus_sao_rejeitadas(self, entrada):
        ok, _, _ = name_validator.validate_name(entrada)
        assert not ok, f"aceito como nome: {entrada!r}"

    @pytest.mark.parametrize("nome", NOMES_REAIS)
    def test_os_7_nomes_reais_passam(self, nome):
        ok, motivo, limpo = name_validator.validate_name(nome)
        assert ok, f"nome real REJEITADO por {motivo}: {nome!r}"
        assert limpo == nome

    def test_tobin_passa(self):
        """🔴 O teste que este sprint não pode falhar.

        Curto, sem acento, sem sufixo brasileiro — não "parece" nome para
        nenhuma heurística estatística. É por ele que a regra só rejeita o que
        reconhece como NÃO-nome, em vez de tentar reconhecer o que é nome.
        """
        ok, motivo, _ = name_validator.validate_name("Tobin")
        assert ok, f"Tobin foi rejeitado por {motivo} — a regra está apertada demais"

    def test_nome_composto_com_particula_passa(self):
        """`da`, `de`, `dos` ficam fora do léxico de pedido de propósito."""
        for nome in ("Maria da Silva", "Pascoal Júnior", "Ana Beatriz de Souza Lima Ferreira"):
            ok, motivo, _ = name_validator.validate_name(nome)
            assert ok, f"{nome!r} rejeitado por {motivo}"

    def test_apresentacao_educada_e_descascada_nao_rejeitada(self):
        """"Oi, meu nome é Tobin" é o cliente RESPONDENDO — e com educação.

        Tratar "meu"/"nome"/"sou" como sinal de rejeição pegaria exatamente
        quem acertou. Por isso o descascador vem ANTES do julgamento.
        """
        for entrada, esperado in (
            ("Oi, meu nome é Tobin", "Tobin"),
            ("me chamo Thayná", "Thayná"),
            ("Bom dia, Daniel", "Daniel"),
            ("sou o Guilherme", "Guilherme"),
        ):
            ok, motivo, limpo = name_validator.validate_name(entrada)
            assert ok, f"{entrada!r} rejeitado por {motivo}"
            assert limpo == esperado

    def test_saudacao_sozinha_nao_vira_nome_vazio(self):
        """"Oi" descascado seria vazio — precisa ser rejeitado, não aceito."""
        for entrada in ("Oi", "Ola", "Bom dia", "Beleza"):
            ok, _, _ = name_validator.validate_name(entrada)
            assert not ok, f"{entrada!r} passou"

    def test_o_lexico_de_pedido_nao_alcanca_palavra_isolada(self):
        """⚠️ A guarda que protege o `Tobin`, escrita como invariante.

        Uma palavra desconhecida e isolada é aceita POR CONSTRUÇÃO. Sem esta
        guarda, o léxico teria poder de rejeitar nome curto — que é o defeito
        que este sprint não pode ter.

        ⚠️ O preço, medido e aceito: `"Tarde"` está no léxico de pedido e
        **passa** sozinha. Um cliente que responda só "Tarde" à pergunta do nome
        é cadastrado assim. É o lado certo para errar — rejeitá-la exigiria
        aplicar o léxico a palavra isolada, e aí `Tobin` cai junto.
        """
        # Sozinha, uma palavra do léxico de pedido não é alcançada por ele.
        ok, _, _ = name_validator.validate_name("Tarde")
        assert ok
        # Só a lista de cortesia rejeita palavra isolada — e por igualdade exata.
        ok, motivo, _ = name_validator.validate_name("Beleza")
        assert not ok and motivo == name_validator.R_COURTESY
        # Uma palavra fora de qualquer lista passa, por mais estranha que seja.
        ok, _, _ = name_validator.validate_name("Zyrtec")
        assert ok
        # Em 2+ palavras o léxico volta a valer.
        ok, motivo, _ = name_validator.validate_name("Tarde tem horário")
        assert not ok and motivo == name_validator.R_REQUEST


# ═════════════════════════════════════════════════════════════════════════════
# 2. A saída — a oferta de atendente com os universais desligados
# ═════════════════════════════════════════════════════════════════════════════

class TestSaidaParaAtendente:
    """⚠️ `AGUARDANDO_NOME` e `CONFIRMAR_NOME` têm os comandos universais
    DESLIGADOS (`bot_service.py:1275`) — um cliente chamado "Ajuda" não deve
    escalar. A saída da rejeição precisa funcionar apesar disso, e o mecanismo
    é o marcador `fallback_offer`, consumido pelo dispatcher ANTES do guard.
    """

    def test_rejeicao_oferece_atendente_na_primeira_vez(self, captured, traced):
        session = SimpleNamespace(id=uuid.uuid4(), state="AGUARDANDO_NOME", context={})
        _handle(session, "Tudo bem")

        kind, title, rows = captured[-1]
        assert kind == "list", "a oferta precisa ser lista — texto puro não escapa daqui"
        assert title == messages.NOME_INVALIDO_TITULO
        assert title != messages.ESCOLHA_OPCAO_OPS, (
            "'Não entendi' seria falso: o bot entendeu que é cortesia"
        )
        assert [r["title"] for r in rows] == [HUMAN_OPTION_TITLE]
        assert session.context[fallback.OFFER_KEY]["index"] == 1
        assert _reason(traced) == fallback.REASON_UNRECOGNIZED

    def test_a_dica_vem_junto_com_a_pergunta(self, captured, traced, monkeypatch):
        """Sem a dica o cliente repete a mesma coisa e o loop se fecha."""
        bodies = []
        monkeypatch.setattr(
            sender, "send_list",
            lambda inst, to, title, desc, rows, *a, **k: bodies.append(desc),
        )
        session = SimpleNamespace(id=uuid.uuid4(), state="AGUARDANDO_NOME", context={})
        _handle(session, "Queria marcar um horário")
        assert bodies[-1] == messages.NOME_INVALIDO_DICA

    def test_numero_da_linha_escala_apesar_dos_universais_desligados(self, captured, monkeypatch):
        """O caminho ponta a ponta, pelo dispatcher REAL.

        Duas mensagens: a rejeição grava o marcador; o "1" seguinte é consumido
        pelo `take_offer` no dispatcher, ANTES do guard que desliga os
        universais — que é a única razão de a saída existir.
        """
        db, cid, session = _dispatch_db("AGUARDANDO_NOME")
        escaladas = []
        monkeypatch.setattr(
            bot_service, "_escalate_to_human",
            lambda *a, **k: escaladas.append(k.get("trigger")),
        )

        _inbound(db, _texto("Tudo bem ?"), "MSG-1")
        assert fallback.OFFER_KEY in session.context

        _inbound(db, _texto("1"), "MSG-2")
        assert escaladas == ["FALLBACK"]
        assert session.state == "AGUARDANDO_NOME", (
            "o handler do estado não pode ter rodado — o dispatcher escalou antes"
        )

    def test_a_palavra_atendente_tambem_escala(self, captured, monkeypatch):
        """⚠️ Sem isto, quem responde "atendente" à oferta seria CADASTRADO
        com o nome "atendente": a palavra passa na validação (uma palavra só,
        desconhecida) e os universais estão desligados neste estado.
        """
        db, cid, session = _dispatch_db("AGUARDANDO_NOME")
        escaladas = []
        monkeypatch.setattr(
            bot_service, "_escalate_to_human",
            lambda *a, **k: escaladas.append(k.get("trigger")),
        )

        _inbound(db, _texto("Blz"), "MSG-1")
        _inbound(db, _texto("atendente"), "MSG-2")
        assert escaladas == ["FALLBACK"]
        assert "nome_temp" not in session.context

    def test_sem_oferta_pendente_a_palavra_atendente_nao_escala(self, monkeypatch):
        """O guarda do teste acima: o alcance é a janela da oferta, não o estado.

        Fora dessa janela, `AGUARDANDO_NOME` continua sem escalar por palavra —
        que é a decisão original (um cliente chamado "Ajuda").
        """
        db, cid, session = _dispatch_db("AGUARDANDO_NOME")
        escaladas = []
        monkeypatch.setattr(
            bot_service, "_escalate_to_human",
            lambda *a, **k: escaladas.append(k.get("trigger")),
        )
        _inbound(db, _texto("Ajuda"), "MSG-1")
        assert escaladas == []
        assert session.context.get("nome_temp") == "Ajuda"


# ═════════════════════════════════════════════════════════════════════════════
# 3. Mídia — áudio e imagem NÃO são o mesmo caso
# ═════════════════════════════════════════════════════════════════════════════

class TestMidia:

    def test_imagem_reconhece_a_foto_sem_repetir_a_pergunta(self, captured, traced):
        """A conversa de 25/08. A foto do corte não era tentativa de dizer o nome."""
        session = SimpleNamespace(id=uuid.uuid4(), state="AGUARDANDO_NOME", context={})
        _handle(session, "", message_type="imageMessage")

        kind, text, _ = captured[-1]
        assert kind == "text"
        assert text == messages.NOME_MIDIA_RECEBIDA
        assert text != messages.PEDIR_NOME_NOVAMENTE, (
            "pedir 'novamente' trata a cliente como se ela tivesse errado"
        )
        assert "Recebi" in text
        assert _reason(traced) == fallback.REASON_NO_TEXT

    def test_audio_pede_por_escrito(self, captured, traced):
        """Áudio é a mensagem INTEIRA — sem transcrição o bot não sabe nada."""
        session = SimpleNamespace(id=uuid.uuid4(), state="AGUARDANDO_NOME", context={})
        _handle(session, "", message_type="audioMessage")

        kind, text, _ = captured[-1]
        assert kind == "text"
        assert text == messages.NOME_AUDIO
        assert text != messages.NOME_MIDIA_RECEBIDA, "áudio e imagem não são o mesmo caso"
        assert _reason(traced) == fallback.REASON_NO_TEXT

    def test_o_reason_de_midia_e_o_do_s2(self, traced):
        """⚠️ `no_text_to_parse`, não um sexto valor.

        A definição do S2 — "chegou mensagem sem texto; não é falha de
        compreensão, é tipo de mídia não suportado" — descreve exatamente este
        caso. Separar por estado seria redundante: `fsm_state` é coluna própria
        e `detail.origin` já distingue o site.
        """
        session = SimpleNamespace(id=uuid.uuid4(), state="AGUARDANDO_NOME", context={})
        _handle(session, "", message_type="audioMessage")
        assert _reason(traced) == "no_text_to_parse"
        assert _reason(traced) != "empty_input", (
            "colidiria com o `reason` do gate do classificador (F5a)"
        )
        assert (traced.dispatch.get("detail") or {}).get("message_type") == "audioMessage"

    def test_midia_nao_grava_nome(self, captured):
        session = SimpleNamespace(id=uuid.uuid4(), state="AGUARDANDO_NOME", context={})
        _handle(session, "", message_type="imageMessage")
        assert "nome_temp" not in session.context
        assert session.state == "AGUARDANDO_NOME"

    def test_midia_pelo_dispatcher_real(self, captured):
        """O `message_type` precisa CHEGAR ao handler — a fiação é do bot_service."""
        db, cid, session = _dispatch_db("AGUARDANDO_NOME")
        _inbound(db, {"imageMessage": {"url": "x"}}, "MSG-1")
        assert any(t == messages.NOME_MIDIA_RECEBIDA for _, t, _ in captured)

    def test_tipo_desconhecido_repete_a_pergunta(self, captured, traced):
        """protocolMessage (mensagem apagada): não há o que reconhecer."""
        session = SimpleNamespace(id=uuid.uuid4(), state="AGUARDANDO_NOME", context={})
        _handle(session, "", message_type="protocolMessage")
        assert captured[-1][1] == messages.PEDIR_NOME_NOVAMENTE
        assert _reason(traced) == fallback.REASON_NO_TEXT


# ═════════════════════════════════════════════════════════════════════════════
# 4. Regressão — o caminho feliz não pode ter sido tocado
# ═════════════════════════════════════════════════════════════════════════════

class TestCaminhoFeliz:

    def test_nome_valido_chega_a_confirmar_nome(self, captured):
        session = SimpleNamespace(id=uuid.uuid4(), state="AGUARDANDO_NOME", context={})
        _handle(session, "Tobin")
        assert session.state == "CONFIRMAR_NOME"
        assert session.context["nome_temp"] == "Tobin"
        assert captured[-1][1] == messages.confirmar_nome("Tobin")
        assert fallback.OFFER_KEY not in session.context

    def test_confirmacao_grava_identity_com_consent(self, captured, monkeypatch):
        """⚠️ Regressão do fim da cadeia: `PaladinoIdentity` é GLOBAL.

        É por aqui que o lixo atravessava barbearias, e é este trecho que o
        sprint NÃO pode ter quebrado ao validar o passo anterior.
        """
        from app.modules.identity import resolver as resolver_mod
        from app.modules.identity import consent_service

        cid = uuid.uuid4()
        customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4(), name="Tobin")
        chamadas, consents = [], []
        monkeypatch.setattr(
            resolver_mod.resolver, "resolve_for_tenant",
            lambda db, phone, company_id, name=None: (chamadas.append(name), (customer, True))[1],
        )
        monkeypatch.setattr(
            consent_service, "grant_consent",
            lambda *a, **k: consents.append(a[3] if len(a) > 3 else None),
        )

        session = SimpleNamespace(
            id=uuid.uuid4(), state="CONFIRMAR_NOME", context={"nome_temp": "Tobin"},
        )
        h_nome.handle_confirmando_nome(
            DispatchDB(), session, cid, JID, INSTANCE, "1",
            start_escolhendo_servico=lambda *a, **k: None,
        )

        assert chamadas == ["Tobin"], "o nome validado não chegou ao resolver"
        assert len(consents) == 1, "consent não foi concedido para o cliente novo"
        assert session.state == "MENU_PRINCIPAL"
        assert session.context["customer_name"] == "Tobin"

    @pytest.mark.parametrize("nome", NOMES_REAIS)
    def test_todos_os_nomes_reais_chegam_a_confirmar_nome(self, nome, captured):
        session = SimpleNamespace(id=uuid.uuid4(), state="AGUARDANDO_NOME", context={})
        _handle(session, nome)
        assert session.state == "CONFIRMAR_NOME", f"{nome!r} não passou pelo handler"

    def test_confirmar_nome_nao_foi_tocado(self, captured, traced):
        """O S2 já tratou o `CONFIRMAR_NOME` — a rejeição de nome não muda nada ali."""
        session = SimpleNamespace(
            id=uuid.uuid4(), state="CONFIRMAR_NOME", context={"nome_temp": "Tobin"},
        )
        h_nome.handle_confirmando_nome(
            DispatchDB(), session, uuid.uuid4(), JID, INSTANCE, "xyz",
            start_escolhendo_servico=lambda *a, **k: None,
        )
        kind, title, rows = captured[-1]
        assert kind == "list"
        assert title == messages.ESCOLHA_OPCAO_OPS, "aqui o 'Não entendi' do S2 continua certo"
        assert [r["title"] for r in rows] == ["Sim", "Corrigir", HUMAN_OPTION_TITLE]

    def test_corrigir_volta_para_aguardando_nome(self, captured):
        session = SimpleNamespace(
            id=uuid.uuid4(), state="CONFIRMAR_NOME", context={"nome_temp": "Tobin"},
        )
        h_nome.handle_confirmando_nome(
            DispatchDB(), session, uuid.uuid4(), JID, INSTANCE, "2",
            start_escolhendo_servico=lambda *a, **k: None,
        )
        assert session.state == "AGUARDANDO_NOME"
        assert captured[-1][1] == messages.PEDIR_NOME_NOVAMENTE

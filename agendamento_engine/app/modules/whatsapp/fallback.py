"""
Resposta do bot quando não entendeu o cliente (S2).

Antes deste módulo, os 22 pontos de fallback do bot enviavam UMA linha —
"Não entendi 😅 / Escolhe uma das opções ali em cima 👆" — apontando para uma
lista que podia estar três mensagens e cinco minutos acima, no celular. Uma
cliente descreveu o serviço, informou a restrição de horário e explicou por que
procurou a barbearia; recebeu a mesma linha três vezes e sumiu por 1h14.

Este módulo troca aquela linha por três coisas, sempre juntas:

  1. **Reexibe a lista** que o cliente está vendo, agora logo abaixo do
     "Não entendi".
  2. **Oferece atendimento humano** — na PRIMEIRA falha, sem contador
     (decisão D6). Insistir cansa e passa sensação de bot burro; o custo de
     oferecer cedo demais é muito menor que o de perder a cliente.
  3. **Grava o motivo no trace** (`dispatch.detail.reason`). Sem isso,
     "o cliente escreveu português e o bot não entendeu" é indistinguível,
     na telemetria, de "o cliente clicou certo e o fluxo seguiu": ambos gravam
     `outcome=PROCESSED`, `reason` vazio e `fsm_state_after == fsm_state`.

⚠️ A forma escolhida para não repetir 22 correções nem escrever um `if` gigante
por estado: **a lista que o cliente vê já está guardada**, em duas formas —
`session.context["last_list"]` nos handlers legados, e reconstruível a partir de
`booking_session.context` pelo `input_parser.visible_options()` no pipeline do
BookingEngine. Este módulo só RENDERIZA; nenhum estado precisa lhe explicar o
que exibe.

⚠️ A opção de atendimento NÃO é resolvida pelos handlers. Ela vira comando
universal (`helpers.is_universal_command` reconhece o rowId e o título) e, para
o cliente que digita o NÚMERO da linha, o marcador `fallback_offer` gravado no
contexto é consumido pelo dispatcher antes do handler do estado. Um só ponto de
escalada, o `_escalate_to_human` de sempre.
"""
import logging
from typing import Optional

from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp import trace
from app.modules.whatsapp.helpers import (
    HUMAN_OPTION_ROW_ID,
    HUMAN_OPTION_TITLE,
)

logger = logging.getLogger(__name__)

# ─── Valores de `reason` ──────────────────────────────────────────────────────
# ⚠️ Estes valores viram SÉRIE HISTÓRICA e agregação de painel: eles são o
# instrumento que mede o resto do plano do bot (S15, S18a, S20, S22). Acrescente
# valor novo quando ele responder uma pergunta que os existentes não respondem;
# NÃO renomeie os existentes — isso quebra a comparação com o que já foi gravado.
#
# Cada um responde uma pergunta diferente sobre a MESMA aparência externa
# ("o bot não entendeu"):

# O cliente escreveu, havia lista, e nada casou. É o caso da conversa que motivou
# o sprint — e o único que significa "o bot precisa entender melhor".
REASON_UNRECOGNIZED = "unrecognized_input"

# Chegou mensagem sem texto: áudio, imagem, sticker, protocolMessage. O
# extract_user_text não conhece o formato e devolve "". Não é falha de
# compreensão — é tipo de mídia não suportado (S23).
#
# ⚠️ O valor NÃO é "empty_input", e a diferença importa: o gate do classificador
# (`bot_service`, handler `classifier_skipped`) já grava `empty_input` desde o
# F5a, com outro significado — lá é "o classificador não RODOU por falta de
# texto", aqui é "o handler não conseguiu PARSEAR por falta de texto". Os dois
# convivem em `bot_message_traces`, e um `GROUP BY reason` sem o `handler` os
# somaria, medindo uma coisa achando que mede outra. Nomes distintos tornam a
# leitura correta o caminho fácil — em vez de depender de quem agrega lembrar
# de incluir o handler.
REASON_NO_TEXT = "no_text_to_parse"

# Não havia lista nenhuma no contexto para casar nem para reexibir. Contexto
# perdido, expirado ou nunca gravado: é sinal de DEFEITO nosso, não do cliente.
REASON_NO_OPTIONS = "no_options_in_context"

# O input casou com uma linha, mas o payload resolvido não serve para este
# estado (item sumiu da lista, formato inesperado). Incoerência entre o que foi
# exibido e o que o handler aceita — também defeito nosso, e distinto do acima.
REASON_INVALID_SELECTION = "invalid_selection"

# O BookingEngine recusou a ação (InvalidActionError): o parser produziu uma
# transição que o FSM não permite naquele estado.
REASON_INVALID_ACTION = "invalid_action"

# Nome único do handler no trace. `dispatch.path` já traz o handler do estado
# (gravado pelo dispatcher); esta entrada, logo depois, diz que aquele estado
# terminou em fallback. Um valor só, greppável — o recorte por estado vem da
# coluna `fsm_state`, e o recorte por site vem de `detail.origin`.
TRACE_HANDLER = "fallback_nao_entendi"

# Chave do marcador de oferta no contexto da BotSession. Vive UMA mensagem: o
# dispatcher a consome (e apaga) na mensagem seguinte ao fallback.
OFFER_KEY = "fallback_offer"


def human_row() -> dict:
    """A linha de atendimento humano, no formato de `last_list`."""
    return {
        "row_id":  HUMAN_OPTION_ROW_ID,
        "payload": HUMAN_OPTION_ROW_ID,
        "title":   HUMAN_OPTION_TITLE,
    }


def not_understood(
    session,
    instance: str,
    whatsapp_id: str,
    *,
    origin: str,
    user_input: str = "",
    options: Optional[list] = None,
    reason: Optional[str] = None,
) -> None:
    """Responde "não entendi" reexibindo a lista e oferecendo atendimento.

    Args:
        session:     BotSession — usada só para ler `last_list` e gravar o
                     marcador da oferta. Nenhuma transição de estado acontece aqui.
        origin:      quem chamou (ex. "escolhendo_servico.handle") — vai para o
                     trace e é o que distingue os 22 sites entre si.
        user_input:  o que o cliente mandou; usado para derivar o `reason`.
        options:     a lista visível, no formato `[{row_id, payload, title}]`.
                     `None` → lê `session.context["last_list"]`, que é onde os
                     handlers legados já guardam exatamente isso.
        reason:      força um valor; `None` → derivado (ver constantes acima).
    """
    ctx = dict(getattr(session, "context", None) or {})

    if options is None:
        options = ctx.get("last_list") or []

    # Só linhas realmente selecionáveis são reexibidas. O "__empty__" da lista de
    # datas ("Nenhum dia disponível nesta semana") é rótulo, não escolha.
    visible = [
        o for o in options
        if isinstance(o, dict) and o.get("title") and o.get("row_id") != "__empty__"
    ]

    if reason is None:
        if not (user_input or "").strip():
            reason = REASON_NO_TEXT
        elif not visible:
            reason = REASON_NO_OPTIONS
        else:
            reason = REASON_UNRECOGNIZED

    trace.note_dispatch(
        TRACE_HANDLER,
        reason=reason,
        origin=origin,
        options=len(visible),
    )

    # ── Sem lista para reexibir: o cliente ainda precisa de uma saída ─────────
    if not visible:
        logger.info(
            "fallback sem lista para reexibir origin=%s reason=%s whatsapp_id=%s",
            origin, reason, whatsapp_id,
        )
        sender.send_text(instance, whatsapp_id, messages.NAO_ENTENDI_SEM_LISTA)
        return

    # ── Reexibe + oferece atendimento ────────────────────────────────────────
    # A opção humana é a ÚLTIMA linha: os números das linhas anteriores não se
    # deslocam, então quem estava prestes a digitar "2" continua acertando.
    offered = visible + [human_row()]

    rows = [
        {
            "rowId":       str(o.get("row_id", "")),
            "title":       str(o.get("title", "")),
            "description": str(o.get("description", "") or ""),
        }
        for o in offered
    ]

    # Marcador de uma mensagem: quem digitar o NÚMERO da última linha é
    # atendido pelo dispatcher, sem que nenhum handler saiba escalar.
    ctx[OFFER_KEY] = {
        "index":  len(offered),          # 1-based, como o cliente vê
        "row_id": HUMAN_OPTION_ROW_ID,
        "title":  HUMAN_OPTION_TITLE,
    }
    session.context = ctx

    # Sempre `send_list`, nunca botões: o limite de 3 botões do WhatsApp não
    # comporta uma lista reexibida + a opção de atendimento.
    sender.send_list(
        instance, whatsapp_id,
        messages.ESCOLHA_OPCAO_OPS,
        messages.NAO_ENTENDI_DESCRICAO,
        rows,
    )


def offer_human_only(
    session,
    instance: str,
    whatsapp_id: str,
    *,
    origin: str,
    header: str,
    body: str,
    reason: str,
) -> None:
    """Repete a pergunta do estado e oferece atendimento — sem lista a reexibir.

    ⚠️ Existe porque `AGUARDANDO_NOME` (S5) não tem `last_list`: a pergunta é
    texto puro, e `not_understood` com `options=[]` cairia em
    `NAO_ENTENDI_SEM_LISTA`, que manda "digite *0*" e "*atendente*" — as duas
    palavras que NÃO funcionam ali, porque os comandos universais estão
    desligados nesse estado de propósito (um cliente chamado "Ajuda" não deve
    escalar). O cliente receberia uma saída que não abre.

    A saída que abre é o MARCADOR: uma lista de UMA linha
    ("💬 Falar com atendente") mais o `fallback_offer` no contexto, consumido
    pelo dispatcher ANTES do guard de comandos universais. O cliente escapa
    clicando a linha, digitando "1", ou escrevendo "atendente" — e continua
    livre para simplesmente digitar o nome, que é o caminho esperado.

    `header`/`body` são do chamador porque "Não entendi 😅" seria falso aqui:
    o bot entendeu que "Tudo bem?" é cortesia; o que falta é a resposta.
    """
    trace.note_dispatch(TRACE_HANDLER, reason=reason, origin=origin, options=0)

    row = human_row()
    ctx = dict(getattr(session, "context", None) or {})
    ctx[OFFER_KEY] = {
        "index":  1,
        "row_id": row["row_id"],
        "title":  row["title"],
    }
    session.context = ctx

    sender.send_list(
        instance, whatsapp_id, header, body,
        [{"rowId": row["row_id"], "title": row["title"], "description": ""}],
    )


def take_offer(session, user_input: str) -> bool:
    """True se o input é a resposta à opção de atendimento oferecida no fallback.

    Consome o marcador SEMPRE que ele existe (a oferta vale uma mensagem só):
    quem não a aceitou segue para o handler do estado com o contexto limpo.

    Só o NÚMERO precisa deste caminho — o rowId e o título exatos já são
    reconhecidos por `is_universal_command`, em qualquer estado. Este marcador
    cobre o fallback de texto numerado, que é o formato que a Evolution entrega
    hoje (BOT_USE_POLLS e BOT_USE_BUTTONS estão desligados).

    ⚠️ S5 — a palavra solta ("atendente", "humano") também é aceita AQUI, e não
    só por `is_universal_command`. Em `AGUARDANDO_NOME`/`CONFIRMAR_NOME` os
    universais estão desligados, então quem responde à oferta escrevendo a
    palavra seria cadastrado com o nome "atendente". O marcador existe apenas na
    mensagem seguinte a uma oferta, o que mantém o alcance dessa aceitação
    exatamente na janela em que a palavra é resposta, e não nome.
    """
    ctx = getattr(session, "context", None) or {}
    offer = ctx.get(OFFER_KEY)
    if not offer:
        return False

    ctx = dict(ctx)
    ctx.pop(OFFER_KEY, None)
    session.context = ctx

    text = (user_input or "").strip().lower()
    if not text:
        return False
    if text in (str(offer.get("row_id", "")).lower(), str(offer.get("title", "")).lower()):
        return True

    from app.modules.whatsapp.helpers import is_universal_command
    if is_universal_command(text) == "humano":
        return True

    import re
    m = re.match(r"^(\d+)", text)
    return bool(m and int(m.group(1)) == int(offer.get("index", 0)))

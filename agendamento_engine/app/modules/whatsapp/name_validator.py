"""Validação do que o cliente digita em `AGUARDANDO_NOME` (S5).

O PROBLEMA
──────────
A única validação era `len(nome) >= 2`. O cliente novo recebe a saudação e a
pergunta "Qual é o seu nome?" na MESMA mensagem, e responde à saudação — ou já
manda o pedido inteiro. O que ele escreveu vira o nome dele.

Dez registros em produção desde abril, todos com agendamentos ativos: `"Blz"`,
`"Bom?"`, `"Bom dia”"`, `"Quero cortar meu cabelo com você hoje…"`, e a resposta
de cinco linhas do Pascoal. No corpus exportado, `AGUARDANDO_NOME` recebeu 8
entradas e só 2 eram nomes.

⚠️ O dano não para na agenda feia. `handle_confirmando_nome` chama
`resolver.resolve_for_tenant`, que grava em `PaladinoIdentity.name` — identidade
GLOBAL, cross-tenant. O lixo atravessa barbearias. E o nome volta em toda
saudação: um cliente chamado `"Blz"` lê "Prazer, Blz!" para sempre.

A REGRA ERRA PARA O LADO DE ACEITAR
───────────────────────────────────
🔴 Restrição de produto do sprint, e ela desenha o módulo inteiro.

`AGUARDANDO_NOME` é a PRIMEIRA interação de todo cliente novo. Um falso positivo
— nome legítimo rejeitado — prende o cliente num loop antes do primeiro
agendamento; o dado sujo é só feio. Os dois erros não custam o mesmo, então a
regra não é simétrica: **cada sinal aqui rejeita, nenhum aceita.** O default é
aceitar, e cada sinal precisa se justificar sozinho.

Consequência prática: `Tobin` é o teste da regra. Curto, incomum, sem acento,
não parece nome para nenhuma heurística estatística. Qualquer regra que tente
reconhecer o que É nome o rejeita. Por isso este módulo só reconhece o que
NÃO é — e uma palavra só, desconhecida, passa por definição.

O DESENHO EM TRÊS CAMADAS
─────────────────────────
1. **Descascar** (`_strip_prefixes`) — "Oi, meu nome é Tobin" é um nome com
   embalagem, não uma não-resposta. Descascar antes de julgar transforma um
   falso positivo caro numa aceitação correta.
2. **Rejeitar por sinal forte** — interrogação, dígito, URL, tamanho. Nenhum
   deles aparece em nome de gente.
3. **Rejeitar por léxico explícito** — cortesia (frase inteira) e palavras de
   pedido (só em entrada de 2+ palavras). ⚠️ Lista explícita, não heurística:
   esta é a família mais frequente E a mais fácil de confundir com nome real.

⚠️ Por que o léxico de pedido NÃO vale para entrada de uma palavra só: uma
palavra desconhecida e isolada é quase sempre o nome. O léxico existe para
frases ("Queria marcar um horário"), e é justamente em palavra isolada que ele
teria o poder de rejeitar um `Tobin`.
"""
import re
import unicodedata
from typing import Optional, Tuple

# ─── Motivos de rejeição ──────────────────────────────────────────────────────
# Só para log, teste e calibragem — NÃO viram `reason` de trace. O `reason` da
# rejeição é o REASON_UNRECOGNIZED do S2 (ver `handlers/aguardando_nome.py`);
# estes rótulos dizem QUAL sinal disparou, e servem para afrouxar a regra
# quando ela pegar gente, não para agregar painel.
R_TOO_SHORT   = "too_short"
R_TOO_LONG    = "too_long"
R_QUESTION    = "question_mark"
R_DIGITS      = "has_digits"
R_URL         = "has_url"
R_NO_LETTERS  = "no_letters"
R_COURTESY    = "courtesy_phrase"
R_REQUEST     = "request_words"


def _strip_accents(text: str) -> str:
    """Tira acento preservando a posição de cada caractere.

    Preserva a posição porque `_strip_prefixes` corta o texto por índice: o
    regex de prefixo precisa casar "meu nome é" (com acento) sem que o corte
    caia no meio do nome que vem depois.
    """
    out = []
    for ch in text or "":
        d = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in d if not unicodedata.combining(c))
        out.append(base or ch)
    return "".join(out)


def _norm(text: str) -> str:
    """minúsculas, sem acento, sem espaço de borda — a forma de comparação."""
    return _strip_accents(text).lower().strip()


def _strip_punct(token: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", token, flags=re.UNICODE)


# ─── Camada 1: embalagens ─────────────────────────────────────────────────────
# "Meu nome é Tobin" é o nome, não uma não-resposta. Se estas frases fossem
# tratadas como sinal de rejeição (elas contêm "meu", "nome", "sou", "chamo"),
# a regra rejeitaria exatamente o cliente que RESPONDEU à pergunta, e com
# educação. Por isso essas palavras ficam FORA do léxico de pedido: são
# consumidas aqui.
_PREFIXES = re.compile(
    r"^(?:"
    r"(?:o\s+)?meu\s+nome\s+(?:e|eh)\s+"
    r"|me\s+chamo\s+"
    r"|(?:eu\s+)?sou\s+(?:o\s+|a\s+)?"
    r"|aqui\s+(?:e|eh)\s+(?:o\s+|a\s+)?"
    r"|pode\s+(?:me\s+)?chamar\s+(?:de\s+)?"
    r"|nome\s*:\s*"
    r")",
    re.IGNORECASE,
)

# Saudação de abertura: "Oi, Tobin" → "Tobin". Só descasca quando há separador
# E sobra algo — protege "Olavo" de virar "vo" e "Oi" de virar vazio.
_OPENERS = ("bom dia", "boa tarde", "boa noite", "e ai",
            "oi", "ola", "opa", "eae", "salve", "fala", "oie", "oiee", "alo")


def _strip_prefixes(raw: str) -> str:
    """Remove saudação de abertura e embalagem de apresentação."""
    text = (raw or "").strip()

    n = _norm(text)
    for op in sorted(_OPENERS, key=len, reverse=True):
        if n.startswith(op):
            rest = text[len(op):]
            if rest[:1] in (",", "!", "-", " ", ".", ";") and rest.strip(" ,!-.;"):
                text = rest.strip(" ,!-.;")
                break

    # O regex roda sobre o texto SEM acento (para casar "é"/"e"), mas o corte é
    # aplicado ao texto original — a capitalização do nome não se perde.
    m = _PREFIXES.match(_strip_accents(text))
    if m and text[m.end():].strip():
        text = text[m.end():].strip()

    return text


# ─── Camada 3a: cortesia (casa a FRASE INTEIRA) ───────────────────────────────
# ⚠️ A família mais frequente do corpus e a mais perigosa: são palavras curtas,
# de uma ou duas sílabas, exatamente como um nome curto. Por isso a comparação é
# por IGUALDADE da frase normalizada — nunca "contém". `"Beleza"` é rejeitado;
# um hipotético `"Beleza Maria"` não.
_COURTESY = frozenset({
    "blz", "blza", "beleza", "belezura", "suave", "firmeza", "tranquilo",
    "tranquila", "de boa", "boa", "bom", "boas",
    "bom dia", "boa tarde", "boa noite",
    "oi", "ola", "opa", "eae", "eai", "e ai", "iai", "salve", "fala",
    "oie", "oiee", "alo", "hey", "hi", "hello",
    "tudo bem", "tudo bom", "td bem", "td bom", "tudo certo", "tudo joia",
    "tudo tranquilo", "tudo blz", "como vai", "como esta", "tudo",
    "ok", "okay", "okey", "certo", "sim", "nao",
    "obrigado", "obrigada", "obg", "vlw", "valeu", "agradecido",
    "bora", "vamos", "tchau", "ate mais", "ate logo",
})


# ─── Camada 3b: palavras de pedido (só em entrada de 2+ palavras) ─────────────
# Palavras que o cliente usa para PEDIR, não para se apresentar. ⚠️ Nenhuma
# delas pode ser nome de gente, nem partícula de nome composto: `de`, `da`, `do`,
# `dos`, `das`, `e`, `junior`, `filho`, `neto` ficam DE FORA de propósito —
# "Maria da Silva" e "Pascoal Júnior" precisam passar inteiros.
_REQUEST_WORDS = frozenset({
    # interrogativas
    "qual", "quais", "quando", "quanto", "quantos", "quantas",
    "onde", "aonde", "como", "porque", "pq", "porq",
    # verbos de pedido / disponibilidade
    "quero", "queria", "gostaria", "preciso", "precisava", "pode", "poderia",
    "tem", "teria", "tinha", "temos", "vai", "funciona", "funcionar",
    "marcar", "marca", "agendar", "agenda", "agendamento", "agendado",
    "cancelar", "cancela", "remarcar", "reagendar", "desmarcar",
    "confirmar", "confirmado", "confirmada", "atende", "atendem", "atendendo",
    "faco", "fazer", "produzo", "vendo", "trabalho",
    # tempo / disponibilidade
    "horario", "horarios", "hora", "horas", "hrs", "hr",
    "disponivel", "disponiveis", "disponibilidade", "vaga", "vagas",
    "hoje", "amanha", "ontem", "semana", "sabado", "domingo", "segunda",
    "terca", "quarta", "quinta", "sexta", "feira", "manha", "tarde", "noite",
    "cedo", "depois", "antes", "apos",
    # serviço / catálogo
    "corte", "cortar", "cabelo", "barba", "barbear", "barbeiro", "barbearia",
    "sobrancelha", "pezinho", "luzes", "quimica", "progressiva", "platinado",
    "preco", "precos", "valor", "valores", "custa",
    # coloquiais de conversa
    "vc", "vcs", "voce", "voces", "ta", "to", "tou", "pra", "pro",
    "blz", "tudo", "bem", "site", "sites", "whatsapp", "zap",
})

_URL_RE   = re.compile(r"(https?://|www\.|\.com|\.br/|@\w+\.)", re.IGNORECASE)
_DIGIT_RE = re.compile(r"\d")

MAX_CHARS = 60
MAX_WORDS = 6
MIN_CHARS = 2


def validate_name(raw: str) -> Tuple[bool, Optional[str], str]:
    """Diz se o texto pode ser gravado como nome do cliente.

    Returns:
        (ok, motivo, nome_limpo) — `motivo` é None quando ok. `nome_limpo` é o
        que deve ser gravado: o texto já sem a embalagem de apresentação
        ("Oi, meu nome é Tobin" → "Tobin"). Em rejeição, vem o texto descascado
        mesmo assim, só para o log e a calibragem.
    """
    name = _strip_prefixes(raw)
    n = _norm(name)

    if len(n) < MIN_CHARS:
        return False, R_TOO_SHORT, name

    # ── Camada 2: sinais fortes ───────────────────────────────────────────────
    # Interrogação: quem pergunta não está se apresentando. Cobre 6 dos 10
    # contaminados de produção sozinha.
    if "?" in name:
        return False, R_QUESTION, name

    # Dígito: nenhum nome de pessoa tem. É sinal de horário, data ou quantidade
    # ("2 cortes", "às 13h", "após as 18 hrs") — o pedido, não o nome.
    if _DIGIT_RE.search(name):
        return False, R_DIGITS, name

    if _URL_RE.search(name):
        return False, R_URL, name

    # Tamanho: o registro do Pascoal tem cinco linhas. Um nome completo
    # brasileiro cabe folgado em 6 palavras / 60 caracteres — "Ana Beatriz de
    # Souza Lima Ferreira" tem 6. O corte é ACIMA disso, não nele.
    if "\n" in name or len(name) > MAX_CHARS:
        return False, R_TOO_LONG, name

    words = [w for w in (_strip_punct(w) for w in n.split()) if w]
    if len(words) > MAX_WORDS:
        return False, R_TOO_LONG, name

    # Sem nenhuma letra (emoji, pontuação solta): não é nome nem pedido.
    if not re.search(r"[^\W\d_]", name, flags=re.UNICODE):
        return False, R_NO_LETTERS, name

    # ── Camada 3a: cortesia, frase inteira ────────────────────────────────────
    flat = " ".join(words)
    if flat in _COURTESY:
        return False, R_COURTESY, name

    # ── Camada 3b: palavras de pedido, só com 2+ palavras ─────────────────────
    # ⚠️ A guarda de 2+ palavras é o que protege `Tobin`, `Ivan`, `Thayná`: uma
    # palavra isolada e desconhecida é aceita por construção.
    if len(words) >= 2 and any(w in _REQUEST_WORDS for w in words):
        return False, R_REQUEST, name

    return True, None, name.strip()

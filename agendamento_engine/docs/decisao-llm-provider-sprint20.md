# Decisão: provider LLM do IntentClassifier (Sprint 2.0)

Decisão D8 (aprovada): regex first, LLM como fallback (confidence < 0.7).
Esta nota documenta a escolha do provider/modelo de LLM, decidida durante a
execução do Sprint 2.0.

## Provider e modelo escolhidos

- **Provider:** Anthropic (`LLM_PROVIDER=anthropic`)
- **Modelo:** Claude Haiku 4.5 (`LLM_MODEL=claude-haiku-4-5`)

## Justificativa

- **Custo:** Haiku 4.5 é o modelo de menor custo da família Claude
  (US$ 1 / US$ 5 por milhão de tokens de entrada/saída). A tarefa de
  classificação de intenção é um caso de uso de texto curto e baixa
  complexidade — não justifica um modelo maior (Sonnet/Opus).
- **Latência:** Haiku é o modelo mais rápido da família, compatível com o
  timeout de 5s exigido para não travar a conversa do bot (mesmo que o
  LLMClassifier não esteja integrado ao FSM nesta sprint — Sprint 2.6).
- **Confiabilidade de saída estruturada:** o SDK `anthropic` suporta tool use
  com `tool_choice={"type": "tool", "name": ...}`, forçando a resposta a ser
  sempre uma chamada de ferramenta com schema fixo (`ALL_INTENTS` como enum +
  `confidence` + `entities`) — atende à invariante 2 (IA nunca gera texto
  livre, apenas JSON estruturado).
- **Consistência com o restante do projeto:** o backend já é majoritariamente
  Python/FastAPI com integrações via SDKs oficiais (Asaas, Mailtrap); o SDK
  `anthropic` segue o mesmo padrão (`client.with_options(timeout=...)`,
  exceções tipadas `anthropic.AnthropicError`).

## Configuração

Variáveis adicionadas em `app/core/config.py`:

| Variável | Default | Descrição |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | Único provider implementado nesta sprint |
| `LLM_MODEL` | `claude-haiku-4-5` | Modelo usado pelo `LLMClassifier` |
| `LLM_API_KEY` | `""` | Chave da API Anthropic. Vazia → `LLMClassifier` degrada direto para `FALLBACK_INTENT` (sem chamar API) |
| `LLM_TIMEOUT_SECONDS` | `5.0` | Timeout por requisição (`client.with_options(timeout=...)`) |

`anthropic==0.69.0` adicionado ao `requirements.txt`.

## Alternativas consideradas

- **OpenAI (GPT-4o-mini / GPT-4.1-nano):** custo/latência comparáveis, mas
  introduziria um segundo SDK de IA no projeto sem ganho claro — Anthropic já
  é a família de modelos usada nas demais ferramentas de desenvolvimento do
  projeto.
- **Sem fallback LLM (regex-only):** rejeitado pela decisão D8 — regex não
  cobre variações de linguagem natural com confiança suficiente; o LLM cobre
  a cauda longa de frases ambíguas.

## Test double

`NullLLMClassifier` (em `app/modules/whatsapp/intent/llm_classifier.py`) nunca
chama a API da Anthropic — usado em todos os testes do Sprint 2.0. Resultado
controlável via env var `NULL_LLM_OUTCOME=fallback|agendar|falar_com_humano`.

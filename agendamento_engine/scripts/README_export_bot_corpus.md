# Exportação do corpus do bot — S0

`scripts/export_bot_corpus.py`

Exporta a telemetria do bot **antes que a retenção a destrua**. Código
descartável: roda duas vezes e não volta a ser usado.

---

## 🔴 Prazo: 07/09/2026

`bot_message_traces` tem retenção de 30 dias (`BOT_TRACE_RETENTION_DAYS`,
`app/core/config.py`) e o expurgo é **oportunista** — `trace._maybe_purge`
dispara quando o bot recebe mensagem, não por cron. Não há como pausá-lo sem
`BOT_TRACE_ENABLED=false`, que desligaria a gravação inteira.

E **`bot_message_labels` morre junto**: `trace_id` é `ON DELETE CASCADE` sobre
`bot_message_traces` (migration `e0s36`). A rotulagem manual desaparece com o
corpus. Depois de 07/09 o dado não existe mais e não há como refazer.

---

## As duas execuções

| | Quando | Para quê |
|---|---|---|
| **Execução 1** | agora | Seguro contra o expurgo. Se algo der errado nas próximas semanas, o corpus de agosto está salvo. |
| **Execução 2** | depois do S1 **e** da rotulagem manual | O S1 acrescenta `atraso` ao `EXPECTED_INTENTS`; sem ele não há como rotular as ~17 falas de atraso, que são a maior carga do inbox. **Esta é a que vale como insumo do desenho.** |

**Ambas antes de 07/09.** Os arquivos levam o timestamp da execução no nome
justamente para as duas coexistirem no mesmo destino — a execução 2 não
sobrescreve a 1.

---

## Como rodar

O script não depende do app rodando e não importa nada de `app/`.

```powershell
$env:DATABASE_URL = "<url do banco alvo>"
.\venv\Scripts\python.exe -m scripts.export_bot_corpus --out C:\paladino-corpus
```

- `--out` é **obrigatório** e deve ficar **fora do repositório**. O script
  aborta se o caminho cair dentro do repo git — o corpus tem `user_input` em
  claro (conversa real de cliente) e não pode entrar em git nem por acidente.

  ⚠️ **Telefone.** O número do **cliente** sai mascarado: `whatsapp_hash` e
  `whatsapp_masked` são pseudônimos por desenho, e no `webhook` cru o
  `key.remoteJid` também é mascarado pelo `sanitize` de `trace.py`
  (`5562*******77@s.whatsapp.net` — verificado). Mas o mascaramento é por
  **sufixo de JID** e não alcança campo de número sem sufixo: o evento
  `connection.update` grava `data["number"]` — **a linha do próprio tenant** —
  em claro no `webhook`. Com isso, e com a conversa real em `user_input`,
  **o arquivo exportado é dado pessoal**: guarde fora de nuvem sincronizada e
  fora de pasta compartilhada.
- Nenhuma URL é hardcodada. **Confira o host impresso no cabeçalho** antes de
  deixar a execução seguir: rodar contra dev pensando que é produção (ou o
  inverso) é fácil demais.
- `--term <substring>` (repetível) substitui a lista de termos da sonda de fila
  de espera. Sem isso, usa a lista padrão do script.

### Read-only por construção

Tudo roda dentro de **uma** transação aberta com `SET TRANSACTION READ ONLY`.
Só há `SELECT` no script, e qualquer escrita falharia no banco, não apenas por
convenção. A transação única também garante que os quatro conjuntos saem do
mesmo snapshot.

---

## O que sai

Todos no destino, com o timestamp UTC da execução no nome.

| Arquivo | Formato | Conteúdo |
|---|---|---|
| `1_traces_labels_<ts>.jsonl` | JSONL | **O principal.** Todas as colunas de `bot_message_traces` + o rótulo (`LEFT JOIN` — a maioria não foi rotulada, e o corpus inteiro é o insumo). |
| `2_classificacoes_desfechos_<ts>.jsonl` | JSONL | `intent_classifications` + `intent_outcomes` (`LEFT JOIN`; sem linha = desfecho pendente). |
| `3_fila_espera_<ts>.csv` | CSV | Sonda textual da pendência §2.5/§9.3 — se "fila de espera" merece virar intenção do catálogo. |
| `4_corpus_leitura_<ts>.csv` | CSV | Corpus limpo, ordenado por conversa. **É o que se abre para conferir a exportação.** |
| `manifest_<ts>.json` | JSON | Alvo, contagens, conferências e termos usados. |

JSONL nos conjuntos 1 e 2 porque `webhook`/`classifier`/`dispatch`/`outbound`
são JSONB e não sobrevivem bem a achatamento em CSV. Os CSV saem em `utf-8-sig`
para o Excel no Windows não quebrar os acentos.

---

## Como validar a execução

O script imprime ao fim: contagem por conjunto conferida contra
`count(*)` da origem, quantos traces têm rótulo, o intervalo de `received_at`
exportado (o que ficou de fora já foi expurgado) e o tamanho de cada arquivo.

Sinais de alarme no relatório:

- **`** DIVERGE **`** numa linha — o exportado não bate com a origem.
- **`Traces COM rotulo: 0`** — ou o join está errado, ou nada foi rotulado.

**A validação que importa** é a última seção: o script procura, no corpus, as
falas que motivaram o redesenho inteiro — `"Só posso após as 20 hrs"`,
`"Vou atrasar um pouco"`, `"Mano, tem horário hoje 15:30?"`. Contra **produção**,
se elas não aparecem, a exportação falhou silenciosamente e não se deve
prosseguir. Contra **dev** a ausência é esperada: as falas são de produção.

Depois disso, abra o `4_corpus_leitura_<ts>.csv` e leia algumas conversas.

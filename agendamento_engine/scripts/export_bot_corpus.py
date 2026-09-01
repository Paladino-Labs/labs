"""Exporta o corpus do bot ANTES do expurgo da retenção — S0.

    python -m scripts.export_bot_corpus --out C:\\paladino-corpus

Por que existe
--------------
`bot_message_traces` tem retenção de 30 dias (`BOT_TRACE_RETENTION_DAYS`) e o
expurgo é OPORTUNISTA (`app/modules/whatsapp/trace.py::_maybe_purge`): dispara
quando o bot recebe mensagem, não por cron. Não há como pausá-lo sem
`BOT_TRACE_ENABLED=false`, que desligaria a gravação inteira.

E `bot_message_labels.trace_id` é `ON DELETE CASCADE` sobre os traces: a
rotulagem manual do Silva morre junto com o corpus. Exportar só os traces
perderia o trabalho de rotulagem.

🔴 PRAZO: 07/09/2026. Depois disso o dado não existe mais e não há como refazer.

DUAS EXECUÇÕES
--------------
Execução 1 — agora. Seguro contra o expurgo: se algo der errado nas próximas
semanas, o corpus de agosto está salvo.

Execução 2 — depois do S1 e da rotulagem manual. O S1 acrescenta `atraso` ao
`EXPECTED_INTENTS`; sem ele não há como rotular as ~17 falas de atraso, que são
a maior carga do inbox. A segunda execução é a que vale como insumo do desenho.

Ambas antes de 07/09. O nome dos arquivos leva o timestamp da execução
justamente para as duas coexistirem no mesmo destino.

Garantias
---------
* READ-ONLY POR CONSTRUÇÃO. Tudo roda dentro de uma única transação aberta com
  `SET TRANSACTION READ ONLY` — qualquer INSERT/UPDATE/DELETE/DDL falharia no
  banco, não só por convenção. Só há `SELECT` aqui.
* Transação única = snapshot único: os quatro conjuntos são consistentes entre si.
* Sem `import app.*`. Só `sqlalchemy`/`psycopg2` e a URL, para o script não
  parar de funcionar quando o app mudar.
* `DATABASE_URL` vem do ambiente. NENHUMA URL é hardcodada aqui — foi a causa
  raiz do incidente "local = produção".
* O host de destino é impresso ANTES de qualquer query, para conferência.

🔴 O corpus contém `user_input` EM CLARO — conversa real de cliente. O destino
é parâmetro obrigatório e o script ABORTA se o caminho cair dentro do
repositório git.

⚠️ Sobre telefone no `webhook` (o `t.*` traz a coluna crua). O `sanitize` de
`trace.py` mascara por SUFIXO de JID, então o número do CLIENTE — que chega em
`key.remoteJid` — sai mascarado (`5562*******77@s.whatsapp.net`). Verificado.
Mas o mascaramento não alcança campo de número SEM sufixo: o evento
`connection.update` carrega `data["number"]` — a linha do PRÓPRIO TENANT — e
esse valor vai para o `webhook` EM CLARO. Some-se a isso o `user_input`, que é
conversa real. **Trate o destino como dado pessoal: fora de nuvem sincronizada,
fora de pasta compartilhada.**
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import make_url

# ── Conjunto 1 — traces com rótulos (o principal) ────────────────────────────
# ⚠️ LEFT JOIN, não JOIN: a maioria dos traces não foi rotulada e o corpus
# inteiro é o insumo.
# ⚠️ `t.*` (e não a lista de colunas) de propósito: este dado é destruído em
# 07/09 e não há como refazer. Sub-exportar é irreversível; exportar a mais
# custa disco. Contém, portanto, o pedido do sprint como superconjunto.
# ⚠️ `bot_message_labels` NÃO tem `labeled_at` — tem `created_at`/`updated_at`
# (conferido em migrations/versions/e0s36_bot_message_labels.py). Aliasados
# abaixo para não colidirem com colunas homônimas do trace.
SQL_TRACES_LABELS = """
SELECT t.*,
       l.id              AS label_id,
       l.understood      AS understood,
       l.expected_intent AS expected_intent,
       l.note            AS label_note,
       l.labeled_by      AS labeled_by,
       l.created_at      AS label_created_at,
       l.updated_at      AS label_updated_at
FROM bot_message_traces t
LEFT JOIN bot_message_labels l ON l.trace_id = t.id
ORDER BY t.whatsapp_hash, t.received_at
"""

# ── Conjunto 2 — classificações com desfecho ─────────────────────────────────
# ⚠️ `intent_outcomes` NÃO tem `recorded_at` — tem `outcome_at` (conferido em
# migrations/versions/e0s30_intent_telemetry.py).
# ⚠️ `intent_classifications` não tem expurgo: este conjunto não corre risco,
# mas vai junto porque o valor está no cruzamento com o conjunto 1.
SQL_CLASSIFICATIONS = """
SELECT c.*,
       o.id             AS outcome_id,
       o.outcome        AS outcome,
       o.outcome_detail AS outcome_detail,
       o.outcome_at     AS outcome_at
FROM intent_classifications c
LEFT JOIN intent_outcomes o ON o.classification_id = c.id
ORDER BY c.classified_at
"""

# ── Conjunto 3 — medição da fila de espera (pendência §2.5/§9.3) ─────────────
# A pergunta do desenho é se "fila de espera" merece virar intenção do
# catálogo, e a resposta depende da frequência no corpus. Não há regex para
# isso: a busca é textual e aproximada, por SUBSTRING (ILIKE '%termo%'), então
# um radical curto cobre as flexões — "avis" pega avisa/avise/aviso/avisar.
# A única fala conhecida é "Se por acaso surgir horário para os dois c me
# avisa" (casa em "surgi" e em "avis").
# ⚠️ Deliberadamente sobre-inclusivo: falso positivo se descarta na leitura,
# falso negativo some com a tabela em 07/09.
WAITLIST_TERMS = [
    "avis",             # avisa, avise, aviso, avisar  (fala conhecida)
    "surgi",            # surgir, surgiu               (fala conhecida)
    "surja",
    "vag",              # vaga, vagar, vagou, vagas
    "liber",            # liberar, liberou, liberado
    "desist",           # desistir, desistiu
    "desmarc",          # desmarcar, desmarcou — quem desmarca abre a vaga
    "cancelar alguém",
    "cancelar alguem",  # sem acento: cliente digita dos dois jeitos
    "fila",
    "espera",           # "fico na espera", "lista de espera"
    "aguard",           # aguardando, aguardar
    "encaix",           # encaixe, encaixar — o vocabulário de salão p/ isto
    "abrir",            # "se abrir horário"
    "abra",             # "caso abra"
]


def build_waitlist_query(terms):
    """Monta o conjunto 3. Retorna (sql, params).

    Termos entram como bind params (`:t0`, `:t1`, …), nunca interpolados —
    o `%` do ILIKE vai no valor, não no SQL.
    """
    clauses = " OR ".join(f"user_input ILIKE :t{i}" for i in range(len(terms)))
    params = {f"t{i}": f"%{term}%" for i, term in enumerate(terms)}
    sql = f"""
SELECT whatsapp_hash, received_at, fsm_state, user_input
FROM bot_message_traces
WHERE event = 'messages.upsert'
  AND user_input IS NOT NULL
  AND ({clauses})
ORDER BY received_at
"""
    return sql, params


# ── Conjunto 4 — corpus limpo para leitura humana ────────────────────────────
# O conjunto 1 tem JSONB grande e é ruim de ler. Este é o arquivo que se abre
# para conferir se a exportação faz sentido, e o que alimenta a leitura do
# catálogo depois.
SQL_CORPUS_LEITURA = """
SELECT t.whatsapp_hash,
       t.received_at,
       t.fsm_state,
       t.fsm_state_after,
       t.message_type,
       t.user_input,
       l.expected_intent,
       l.understood,
       t.dispatch -> 'detail' ->> 'reason' AS dispatch_reason
FROM bot_message_traces t
LEFT JOIN bot_message_labels l ON l.trace_id = t.id
ORDER BY t.whatsapp_hash, t.received_at
"""

CORPUS_LEITURA_COLS = [
    "whatsapp_hash", "received_at", "fsm_state", "fsm_state_after",
    "message_type", "user_input", "expected_intent", "understood",
    "dispatch_reason",
]

WAITLIST_COLS = ["whatsapp_hash", "received_at", "fsm_state", "user_input"]

# ⚠️ A validação que importa: se o corpus exportado não tem as falas que
# motivaram o redesenho inteiro, a exportação falhou SILENCIOSAMENTE.
# Comparação em minúsculas contra `user_input`.
FALAS_CONHECIDAS = [
    "só posso após as 20",
    "vou atrasar",
    "15:30",
]


def _json_default(obj):
    """Serializa o que o psycopg2 devolve e o `json` não conhece."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        # str, não float: `confidence` é NUMERIC(4,3) e float introduziria
        # ruído de arredondamento num dado que vai virar estatística.
        return str(obj)
    if isinstance(obj, (bytes, memoryview)):
        return bytes(obj).decode("utf-8", errors="replace")
    raise TypeError(f"não serializável: {type(obj).__name__}")


def write_jsonl(rows, path):
    """Uma linha JSON por registro. Retorna a contagem escrita.

    JSONL e não CSV porque `webhook`/`classifier`/`dispatch`/`outbound` são
    JSONB e não sobrevivem bem a achatamento.
    """
    n = 0
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), default=_json_default, ensure_ascii=False))
            fh.write("\n")
            n += 1
    return n


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=_json_default, ensure_ascii=False)
    return value


def write_csv(rows, cols, path):
    """CSV para leitura humana. Retorna a contagem escrita.

    `utf-8-sig`: o Silva abre isto no Excel no Windows, e sem BOM os acentos
    do português saem quebrados.
    """
    n = 0
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            d = dict(row)
            writer.writerow({c: _cell(d.get(c)) for c in cols})
            n += 1
    return n


def _stream(conn, sql, params=None):
    """Executa em cursor server-side: o corpus não precisa caber na memória."""
    result = conn.execution_options(stream_results=True, max_row_buffer=500).execute(
        sa.text(sql), params or {}
    )
    return result.mappings()


def _describe_target(url):
    """Host/porta/banco/usuário — NUNCA a senha."""
    u = make_url(url)
    return {
        "host": u.host, "port": u.port,
        "database": u.database, "username": u.username,
        "driver": u.drivername,
    }


def _repo_root():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if out.returncode == 0:
            return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _guard_destino(out_dir):
    """🔴 O corpus tem conversa real de cliente em claro. Não pode entrar em git."""
    repo = _repo_root()
    if repo is None:
        return
    try:
        out_dir.relative_to(repo)
    except ValueError:
        return
    sys.exit(
        f"ABORTADO: o destino {out_dir} está DENTRO do repositório ({repo}).\n"
        "O corpus contém user_input em claro — conversa real de cliente — e não\n"
        "pode entrar em git nem por acidente. Escolha um destino fora do repo."
    )


def run(out_dir, terms, stamp=None):
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        sys.exit(
            "DATABASE_URL ausente no ambiente.\n"
            "  PowerShell:  $env:DATABASE_URL = '<url>'\n"
            "Nenhuma URL é hardcodada neste script, de propósito."
        )

    out_dir = Path(out_dir).expanduser().resolve()
    _guard_destino(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = _describe_target(url)

    # ⚠️ ANTES de qualquer query: o Silva confere que é o banco certo.
    # Rodar contra dev pensando que é produção (ou o inverso) é fácil demais.
    print("=" * 72)
    print("EXPORTAÇÃO DO CORPUS DO BOT — S0")
    print("=" * 72)
    print(f"  host     : {target['host']}:{target['port']}")
    print(f"  database : {target['database']}")
    print(f"  usuario  : {target['username']}")
    print(f"  destino  : {out_dir}")
    print(f"  execucao : {stamp}")
    print("  modo     : SOMENTE LEITURA (SET TRANSACTION READ ONLY)")
    print("=" * 72)

    paths = {
        "1_traces_labels": out_dir / f"1_traces_labels_{stamp}.jsonl",
        "2_classificacoes_desfechos": out_dir / f"2_classificacoes_desfechos_{stamp}.jsonl",
        "3_fila_espera": out_dir / f"3_fila_espera_{stamp}.csv",
        "4_corpus_leitura": out_dir / f"4_corpus_leitura_{stamp}.csv",
    }
    counts = {}
    falas = {f: 0 for f in FALAS_CONHECIDAS}

    def _tally(rows):
        for row in rows:
            texto = (row.get("user_input") or "").lower()
            for fala in FALAS_CONHECIDAS:
                if fala in texto:
                    falas[fala] += 1
            yield row

    engine = sa.create_engine(url)
    with engine.connect() as conn:
        # 🔴 A garantia de leitura, no banco e não na convenção. Precisa ser o
        # PRIMEIRO comando da transação.
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        # `bot_message_traces` tem RLS (e0s34). A policy libera quando
        # `app.current_company_id` é a string vazia; sem isto, um papel sujeito
        # a RLS exportaria ZERO linha sem erro nenhum — silencioso, que é
        # exatamente a falha que este sprint não pode ter. `true` = escopo da
        # transação (o pooler em modo transaction não preserva SET de sessão).
        conn.execute(sa.text("SELECT set_config('app.current_company_id', '', true)"))

        print("\n[1/4] traces + rotulos (LEFT JOIN) -> JSONL")
        counts["1_traces_labels"] = write_jsonl(
            _stream(conn, SQL_TRACES_LABELS), paths["1_traces_labels"]
        )

        print("[2/4] classificacoes + desfechos (LEFT JOIN) -> JSONL")
        counts["2_classificacoes_desfechos"] = write_jsonl(
            _stream(conn, SQL_CLASSIFICATIONS), paths["2_classificacoes_desfechos"]
        )

        print(f"[3/4] sonda de fila de espera ({len(terms)} termos) -> CSV")
        wl_sql, wl_params = build_waitlist_query(terms)
        counts["3_fila_espera"] = write_csv(
            _stream(conn, wl_sql, wl_params), WAITLIST_COLS, paths["3_fila_espera"]
        )

        print("[4/4] corpus limpo para leitura -> CSV")
        counts["4_corpus_leitura"] = write_csv(
            _tally(_stream(conn, SQL_CORPUS_LEITURA)),
            CORPUS_LEITURA_COLS, paths["4_corpus_leitura"],
        )

        # ── Conferências contra a origem ─────────────────────────────────────
        checks = conn.execute(sa.text("""
            SELECT (SELECT count(*) FROM bot_message_traces)        AS traces,
                   (SELECT count(*) FROM bot_message_labels)        AS labels,
                   (SELECT count(*) FROM intent_classifications)    AS classifications,
                   (SELECT count(*) FROM intent_outcomes)           AS outcomes,
                   (SELECT count(*) FROM bot_message_traces t
                      JOIN bot_message_labels l ON l.trace_id = t.id) AS traces_com_rotulo,
                   (SELECT min(received_at) FROM bot_message_traces) AS min_at,
                   (SELECT max(received_at) FROM bot_message_traces) AS max_at
        """)).mappings().one()

    sizes = {k: p.stat().st_size for k, p in paths.items()}
    print(_report(target, out_dir, stamp, paths, counts, sizes, checks, falas, terms))

    manifest = {
        "executado_em": stamp,
        "alvo": target,
        "destino": str(out_dir),
        "arquivos": {k: p.name for k, p in paths.items()},
        "contagens": counts,
        "tamanhos_bytes": sizes,
        "conferencia_origem": dict(checks),
        "termos_fila_espera": terms,
        "falas_conhecidas": falas,
    }
    (out_dir / f"manifest_{stamp}.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )
    return manifest


def _report(target, out_dir, stamp, paths, counts, sizes, checks, falas, terms):
    L = ["", "=" * 72, "RESULTADO", "=" * 72]
    L.append(f"  banco    : {target['host']}:{target['port']}/{target['database']}")
    L.append(f"  destino  : {out_dir}")
    L.append("")
    L.append("  Conjunto                       exportado   origem   arquivo (bytes)")
    L.append("  " + "-" * 68)
    pares = [
        ("1 traces+rotulos", "1_traces_labels", checks["traces"]),
        ("2 classificacoes+desfechos", "2_classificacoes_desfechos", checks["classifications"]),
        ("3 sonda fila de espera", "3_fila_espera", None),
        ("4 corpus p/ leitura", "4_corpus_leitura", checks["traces"]),
    ]
    for rotulo, chave, origem in pares:
        org = "-" if origem is None else str(origem)
        diverge = origem is not None and counts[chave] != origem
        marca = "  ** DIVERGE **" if diverge else ""
        L.append(f"  {rotulo:<30} {counts[chave]:>9}  {org:>7}   {sizes[chave]:>10,}{marca}")
    L.append("")
    zero = not checks["traces_com_rotulo"]
    L.append(f"  Traces COM rotulo        : {checks['traces_com_rotulo']}"
             + ("   [!] ZERO - algo esta errado no join, ou nada foi rotulado ainda"
                if zero else ""))
    L.append(f"  Rotulos na origem        : {checks['labels']}")
    L.append(f"  Desfechos na origem      : {checks['outcomes']}")
    L.append("")
    L.append("  Intervalo de received_at (o que ficou de fora ja foi expurgado):")
    L.append(f"    minimo : {checks['min_at']}")
    L.append(f"    maximo : {checks['max_at']}")
    L.append("")
    L.append(f"  Sonda de fila de espera - {len(terms)} termos (substring, ILIKE):")
    L.append(f"    {', '.join(terms)}")
    L.append("")
    L.append("  [!] VALIDACAO QUE IMPORTA - falas que motivaram o redesenho:")
    for fala, n in falas.items():
        estado = f"encontrada ({n}x)" if n else "NAO ENCONTRADA"
        L.append(f"    {'OK ' if n else '[!]'} {fala!r}: {estado}")
    if not any(falas.values()):
        L.append("")
        L.append("    Nenhuma fala conhecida no corpus. Em DEV isto e ESPERADO -")
        L.append("    as falas sao de producao. Contra PRODUCAO, significa que a")
        L.append("    exportacao FALHOU silenciosamente: nao prossiga.")
    L.append("")
    L.append("  Arquivos:")
    for chave, p in paths.items():
        L.append(f"    {p.name}")
    L.append(f"    manifest_{stamp}.json")
    L.append("=" * 72)
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Exporta o corpus do bot antes do expurgo da retencao (S0).",
    )
    ap.add_argument(
        "--out", required=True,
        help="Diretorio de destino. FORA do repositorio: o corpus tem "
             "user_input em claro.",
    )
    ap.add_argument(
        "--term", action="append", default=None, metavar="SUBSTRING",
        help="Substitui os termos da sonda de fila de espera (conjunto 3). "
             "Repetivel. Sem isto, usa a lista padrao do script.",
    )
    args = ap.parse_args(argv)
    run(args.out, args.term or WAITLIST_TERMS)


if __name__ == "__main__":
    main()

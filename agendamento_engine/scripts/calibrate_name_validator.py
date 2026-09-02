r"""Calibragem da regra de validação de nome (S5) contra os nomes REAIS.

🔴 **Esta é a validação que decide se o sprint pode ir para produção.**
`AGUARDANDO_NOME` é a primeira interação de todo cliente novo — uma regra
apertada demais prende gente antes do primeiro agendamento. Nenhum corpus de
teste substitui rodar a regra contra os nomes que existem no banco.

COMO LER O RESULTADO
────────────────────
  ✅ Entre os REJEITADOS devem estar os 10 contaminados conhecidos
     ("Blz", "Bom?", "Bom dia”", as frases de pedido, a resposta do Pascoal).
  🔴 **Qualquer nome de PESSOA na lista de rejeitados** significa que a regra
     está apertada demais e precisa afrouxar antes do push.

⚠️ Rejeitar `"Blz"` é acerto. Rejeitar `"Tobin"` é o defeito que este sprint
não pode ter. Na dúvida sobre um caso da lista, afrouxe — o dado sujo é feio, o
loop perde cliente.

O QUE FAZER SE UM NOME REAL APARECER
────────────────────────────────────
A coluna `motivo` diz qual sinal disparou, e cada um tem endereço em
`app/modules/whatsapp/name_validator.py`:

  courtesy_phrase → tire a palavra de `_COURTESY`
  request_words   → tire a palavra de `_REQUEST_WORDS`
  too_long        → suba `MAX_WORDS` / `MAX_CHARS`
  has_digits / question_mark / has_url → sinal forte; um nome real que dispare
                   isso é caso a investigar, não a afrouxar às cegas

COMO RODAR
──────────
Read-only: só faz SELECT em `customers`. Nenhuma escrita, nenhum commit.

    cd agendamento_engine
    .\venv\Scripts\python.exe scripts\calibrate_name_validator.py

Por padrão usa `DATABASE_URL` do ambiente. ⚠️ O `.env` versionado aponta para
PRODUÇÃO, e aqui isso é intencional — a calibragem só vale contra os nomes
reais. Como o script não escreve nada, rodá-lo contra produção é seguro; o que
NÃO é seguro é subir o backend contra ela (use `run_dev_api.py` para isso).

⚠️ A saída contém nomes de clientes reais. Não cole em issue, ticket ou chat —
leia no terminal e descarte.

A query de referência do sprint, para conferência manual:

    SELECT id, name, right(phone, 4) AS fim,
           created_at AT TIME ZONE 'America/Sao_Paulo' AS criado
    FROM customers
    ORDER BY created_at DESC;
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.whatsapp.name_validator import validate_name  # noqa: E402

QUERY = """
    SELECT id, name, right(phone, 4) AS fim,
           created_at AT TIME ZONE 'America/Sao_Paulo' AS criado
    FROM customers
    ORDER BY created_at DESC
"""


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        # O .env do repo carrega DATABASE_URL; sem ele, não há o que calibrar.
        try:
            from dotenv import load_dotenv
            load_dotenv()
            url = os.environ.get("DATABASE_URL")
        except ImportError:
            pass
    if not url:
        print("DATABASE_URL não definido — nada a calibrar.", file=sys.stderr)
        return 2

    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    with engine.connect() as conn:
        rows = list(conn.execute(text(QUERY)))

    rejeitados, aceitos = [], []
    for r in rows:
        nome = r.name or ""
        ok, motivo, limpo = validate_name(nome)
        (aceitos if ok else rejeitados).append((nome, motivo, limpo, r.fim, r.criado))

    print(f"\n{len(rows)} clientes · {len(aceitos)} aceitos · {len(rejeitados)} rejeitados\n")

    print("═" * 78)
    print("REJEITADOS — os 10 contaminados devem estar aqui.")
    print("🔴 QUALQUER NOME DE PESSOA NESTA LISTA = a regra está apertada demais.")
    print("═" * 78)
    if not rejeitados:
        print("  (nenhum — ⚠️ suspeito: os 10 contaminados deveriam aparecer)")
    for nome, motivo, _, fim, criado in rejeitados:
        print(f"  [{motivo:16}] …{fim}  {criado:%d/%m/%Y}  {nome!r}")

    print()
    print("═" * 78)
    print("ACEITOS COM ALTERAÇÃO — o descascador removeu embalagem de apresentação.")
    print("Confira que o que sobrou é de fato o nome.")
    print("═" * 78)
    alterados = [(n, l, f) for n, _, l, f, _ in aceitos if l.strip() != (n or "").strip()]
    if not alterados:
        print("  (nenhum)")
    for nome, limpo, fim in alterados:
        print(f"  …{fim}  {nome!r}  →  {limpo!r}")

    print()
    print(f"Veredicto: {len(rejeitados)} rejeitados. Se algum for pessoa, AFROUXE "
          f"antes do push (ver o cabeçalho deste arquivo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

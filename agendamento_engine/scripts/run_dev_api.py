"""Sobe a API apontando para o Supabase de DEV, nunca para produção.

⚠️ Existe porque o `.env` versionado tem `DATABASE_URL` de **produção**
(aviso registrado no CLAUDE.md). Rodar `uvicorn app.main:app` direto num
ambiente de verificação sobe a API contra o banco de produção.

Este runner carrega o `.env.dev` ANTES de importar o app e aborta se a URL
resultante for a de produção. Fail-closed: se o `.env.dev` não existir, não
sobe — não cai para o `.env`.
"""
import os
import pathlib
import sys

from dotenv import dotenv_values

PROD_REF = "uhhygdqioqcgcfqfbmif"

ROOT = pathlib.Path(__file__).resolve().parents[1]
# O script vive em scripts/, então a raiz do projeto (onde mora `app/`) não
# entra no sys.path sozinha.
sys.path.insert(0, str(ROOT))

env_dev = ROOT / ".env.dev"

if not env_dev.exists():
    sys.exit("ABORTADO: .env.dev não encontrado — não caio para o .env (produção)")

# Precede a importação de app.config: as env vars vencem o load_dotenv.
for key, value in dotenv_values(env_dev).items():
    if value is not None:
        os.environ[key] = value

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    sys.exit("ABORTADO: .env.dev sem DATABASE_URL")
if PROD_REF in db_url:
    sys.exit("ABORTADO: .env.dev aponta para PRODUÇÃO")

print(f"API de dev — banco {db_url.split('@')[-1].split('/')[0]}", flush=True)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)

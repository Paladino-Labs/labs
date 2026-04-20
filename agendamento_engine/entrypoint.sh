#!/bin/sh
# =============================================================================
# entrypoint.sh — Força IPv4 para o banco de dados antes de iniciar a API
#
# Problema: Docker Desktop no Windows não roteia IPv6 externo. O hostname do
# Supabase resolve para IPv6 primeiro → "Network is unreachable".
#
# Solução: Resolver o hostname para IPv4 e fixar em /etc/hosts ANTES do app
# iniciar. /etc/hosts tem prioridade sobre DNS em toda a stack Linux.
# Isso cobre a API, o Alembic e qualquer outra lib que faça conexões.
# =============================================================================
set -e

# Extrai o hostname da DATABASE_URL (ex: db.xxx.supabase.co)
DB_HOST=$(python3 -c "
import os
from urllib.parse import urlparse
url = os.environ.get('DATABASE_URL', '')
print(urlparse(url).hostname or '')
")

if [ -n "$DB_HOST" ]; then
    # Resolve SOMENTE IPv4 (AF_INET), ignorando IPv6
    IPV4=$(DB_HOST="$DB_HOST" python3 -c "
import os, socket
host = os.environ['DB_HOST']
try:
    result = socket.getaddrinfo(host, None, socket.AF_INET)
    print(result[0][4][0])
except Exception as e:
    import sys
    print('', file=sys.stderr)
    print(f'[entrypoint] Aviso: resolucao IPv4 falhou: {e}', file=sys.stderr)
    print('')
")
    if [ -n "$IPV4" ]; then
        echo "$IPV4    $DB_HOST" >> /etc/hosts
        echo "[entrypoint] IPv6 bypass: $DB_HOST → $IPV4 fixado em /etc/hosts"
    else
        echo "[entrypoint] AVISO: nao foi possivel resolver $DB_HOST para IPv4, usando DNS padrao"
    fi
else
    echo "[entrypoint] AVISO: DATABASE_URL nao encontrada ou sem hostname"
fi

# Garante que o diretório de uploads existe (caso volume seja montado vazio)
mkdir -p /app/static/uploads

# Inicia o processo principal (CMD do Dockerfile)
exec "$@"

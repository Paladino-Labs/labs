FROM python:3.11-slim

WORKDIR /app

# Copia requirements primeiro — camada de cache separada do código
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copia o código e o entrypoint
COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
 && mkdir -p /app/static/uploads

EXPOSE 8000

# O entrypoint resolve o hostname do banco para IPv4 antes de iniciar.
# CMD é passado como argumentos para o entrypoint via exec "$@".
ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh", "-c", \
     "if [ \"$RELOAD\" = 'true' ]; then \
          exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --reload; \
      else \
          exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}; \
      fi"]

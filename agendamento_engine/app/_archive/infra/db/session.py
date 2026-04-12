import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()

# No Supabase, prefira a Connection String do tipo 'Transaction' (porta 6543)
# para evitar estourar o limite de conexões em escala.
DATABASE_URL = os.getenv("DATABASE_URL")

# Configurações do Engine para resiliência:
# 1. pool_size: Quantas conexões manter abertas.
# 2. max_overflow: Quantas conexões extras abrir em picos de tráfego.
# 3. pool_recycle: Fecha conexões antigas a cada 30 min para evitar 'Broken Pipe
# 4. pool_pre_ping: Testa a conexão antes de usar (essencial para Cloud Run).
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
    pool_pre_ping=True
)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Dependency Injection para o FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
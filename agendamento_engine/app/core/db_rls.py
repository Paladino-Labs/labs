"""
Row Level Security — contexto de sessão SQLAlchemy.

set_rls_context: chamado por get_db() e tasks Celery para setar o tenant ativo.
configure_rls_events: registra listener de checkout no engine de produção.
  NÃO chamar em testes (SQLite não suporta set_config).
"""
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def set_rls_context(db: Session, company_id: str | None) -> None:
    """Seta app.current_company_id na conexão atual (nível de sessão, não transação).

    company_id=None ou '' → string vazia → política RLS concede acesso irrestrito
    (equivalente a PLATFORM_OWNER ou worker de plataforma).
    """
    value = str(company_id) if company_id else ""
    db.execute(
        text("SELECT set_config('app.current_company_id', :v, false)"),
        {"v": value},
    )


def configure_rls_events(engine: Engine) -> None:
    """Registra listener de checkout que reseta app.current_company_id a cada conexão.

    O reset garante que conexões recicladas do pool não vazem contexto de tenant
    entre requisições diferentes.
    """
    @event.listens_for(engine, "checkout")
    def reset_rls_context(dbapi_connection, connection_record, connection_proxy):
        cursor = dbapi_connection.cursor()
        cursor.execute("SELECT set_config('app.current_company_id', '', false)")
        cursor.close()

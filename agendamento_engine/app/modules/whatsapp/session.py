"""
Infraestrutura de sessão do bot WhatsApp.

Responsabilidades:
  - Obter sessão com lock exclusivo (SELECT FOR UPDATE NOWAIT)
  - Persistir sessão com TTL renovado
  - Resetar sessão para INICIO preservando opcionalmente dados do cliente
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.core.config import settings

# Estado inicial — importado aqui para evitar dependência circular com bot_service
STATE_INICIO = "INICIO"


def get_session_locked(db: Session, company_id, whatsapp_id: str) -> BotSession:
    """
    Retorna a BotSession com lock exclusivo (SELECT FOR UPDATE NOWAIT).
    Cria uma nova sessão se ainda não existir.
    Levanta OperationalError se a linha já estiver bloqueada por outra transação
    (sinal de mensagem simultânea do mesmo usuário — o chamador deve descartar).
    """
    session = (
        db.query(BotSession)
        .filter(
            BotSession.company_id == company_id,
            BotSession.whatsapp_id == whatsapp_id,
        )
        .with_for_update(nowait=True)
        .first()
    )
    if not session:
        session = BotSession(
            company_id=company_id,
            whatsapp_id=whatsapp_id,
            state=STATE_INICIO,
            context={},
        )
        db.add(session)
        db.flush()
    return session


def save_session(db: Session, session: BotSession) -> None:
    """
    Renova o TTL da sessão e persiste no banco.
    Deve ser chamado ao final de cada mensagem processada, inclusive em duplicatas
    (para renovar expires_at sem reprocessar o conteúdo).
    """
    session.expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.BOT_SESSION_TTL_MINUTES
    )
    db.commit()


def reset_session(session: BotSession, keep_customer: bool = True) -> None:
    """
    Reseta o estado da sessão para INICIO.

    Args:
        session: instância BotSession a ser resetada (modificada in-place).
        keep_customer: se True (padrão), preserva customer_id, customer_name e
                       company_name no contexto para evitar re-identificação do
                       cliente na próxima interação da mesma sessão.
    """
    ctx = session.context or {}
    preserved = {}
    if keep_customer:
        for k in ("customer_id", "customer_name", "company_name"):
            if k in ctx:
                preserved[k] = ctx[k]
    session.context = preserved
    session.state = STATE_INICIO


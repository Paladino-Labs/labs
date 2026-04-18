from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str = "troque-em-producao"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h

    # Evolution API — necessário para o módulo WhatsApp
    EVOLUTION_API_URL: str = "http://localhost:8080"
    EVOLUTION_API_KEY: str = "evolution-api-key"

    # URL pública do backend acessível pela Evolution API (sem barra final)
    # Exemplo: https://api.seudominio.com
    WEBHOOK_BASE_URL: str = "http://localhost:8000"

    # Bot — sessão e UX
    BOT_SESSION_TTL_MINUTES: int = 30           # TTL da sessão, resetado a cada mensagem
    BOT_PREDICTIVE_OFFER_TTL_MINUTES: int = 5  # Expiração da oferta recorrente
    BOT_MAX_SLOTS_DISPLAYED: int = 6            # Máximo de horários exibidos por página
    BOT_FALLBACK_MAX_COUNT: int = 3             # Fallbacks antes de oferecer atendente humano
    BOT_USE_BUTTONS: bool = False               # True quando Evolution API entregar botões interativos (Cloud API)
    BOT_USE_POLLS: bool = True                  # Usa sendPoll (nativo Baileys) no lugar de sendButtons/sendList

    # Agendamentos — políticas de negócio
    APPOINTMENT_MIN_HOURS_BEFORE_CANCEL: int = 2      # Prazo mínimo para cancelar
    APPOINTMENT_MIN_HOURS_BEFORE_RESCHEDULE: int = 2  # Prazo mínimo para remarcar

    # WhatsApp
    WHATSAPP_QR_TTL_SECONDS: int = 60  # TTL do QR Code

    # Workers
    BOT_SESSION_CLEANUP_BATCH_SIZE: int = 100  # Sessões deletadas por ciclo
    BOT_REMINDER_ADVANCE_HOURS_FIRST: int = 24  # Primeiro lembrete (horas antes)
    BOT_REMINDER_ADVANCE_HOURS_SECOND: int = 2  # Segundo lembrete (horas antes)

    class Config:
        env_file = ".env"


settings = Settings()

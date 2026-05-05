from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str = "troque-em-producao"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h

    # CORS — origens permitidas (separadas por vírgula no .env)
    # Exemplo: ALLOWED_ORIGINS=https://app.seudominio.com.br,https://api.seudominio.com.br
    # Em desenvolvimento usa o default abaixo; em produção OBRIGATÓRIO sobrescrever via .env
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    # Evolution API — necessário para o módulo WhatsApp
    EVOLUTION_API_URL: str = "http://localhost:8080"
    EVOLUTION_API_KEY: str = "evolution-api-key"

    # URL pública do backend acessível pela Evolution API (sem barra final)
    # Exemplo: https://api.seudominio.com
    WEBHOOK_BASE_URL: str = "http://localhost:8000"

    # URL pública do frontend (painel + booking page). Sem barra final.
    # Exemplo: https://app.seudominio.com
    FRONTEND_URL: str = "http://localhost:3000"

    # Bot — sessão e UX
    BOT_SESSION_TTL_MINUTES: int = 30           # TTL da sessão, resetado a cada mensagem
    BOT_PREDICTIVE_OFFER_TTL_MINUTES: int = 5  # Expiração da oferta recorrente
    BOT_MAX_SLOTS_DISPLAYED: int = 6            # Máximo de horários exibidos por página
    DATE_WINDOW_SIZE: int = 7                   # Dias por página na seleção de data
    DATE_MAX_ADVANCE_DAYS: int = 60             # Limite máximo de antecedência para agendamento online (dias)
    BOT_FALLBACK_MAX_COUNT: int = 3             # Fallbacks antes de oferecer atendente humano
    BOT_USE_BUTTONS: bool = False               # True quando Evolution API entregar botões interativos (Cloud API)
    BOT_USE_POLLS: bool = False                 # Usa sendPoll (nativo Baileys) no lugar de sendButtons/sendList

    # Agendamentos — políticas de negócio
    APPOINTMENT_MIN_HOURS_BEFORE_CANCEL: int = 2      # Prazo mínimo para cancelar
    APPOINTMENT_MIN_HOURS_BEFORE_RESCHEDULE: int = 2  # Prazo mínimo para remarcar

    # WhatsApp
    WHATSAPP_QR_TTL_SECONDS: int = 60  # TTL do QR Code

    # Workers
    BOT_SESSION_CLEANUP_BATCH_SIZE: int = 100  # Sessões deletadas por ciclo
    BOT_REMINDER_ADVANCE_HOURS_FIRST: int = 24  # Primeiro lembrete (horas antes)
    BOT_REMINDER_ADVANCE_HOURS_SECOND: int = 2  # Segundo lembrete (horas antes)

    # BookingSession unificado — TTL por canal
    BOOKING_SESSION_TTL_WEB_MINUTES: int = 15       # Web: 15 min (fluxo assistido)
    BOOKING_SESSION_TTL_WHATSAPP_MINUTES: int = 30  # WhatsApp: 30 min (digitação lenta)

    # Fuso horário padrão quando company.timezone não estiver preenchido
    DEFAULT_COMPANY_TIMEZONE: str = "America/Sao_Paulo"

    # URL pública do booking (widget / link direto). Sem barra final.
    # Deve incluir o segmento de rota — ex: https://app.seudominio.com/book
    # O slug da empresa é concatenado: {BOOKING_BASE_URL}/{slug}
    BOOKING_BASE_URL: str = "http://localhost:3000/book"

    class Config:
        env_file = ".env"
        extra = "ignore"   # ignora vars no .env não declaradas aqui


settings = Settings()

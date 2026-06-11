"""Adapters de email plugáveis — Sprint I.

O provider global é escolhido via env var EMAIL_PROVIDER (config.py):
  mailtrap (default) → Mailtrap HTTP API (requer MAILTRAP_API_TOKEN;
                       MAILTRAP_SANDBOX_INBOX_ID > 0 usa a API de sandbox)
  sendgrid           → SendGrid HTTP API v3 (requer SENDGRID_API_KEY)
  smtp               → força o caminho SMTP (credencial do tenant ou SMTP_* global)

Railway bloqueia SMTP de saída (25/465/587/2525) — em produção usar um
provider HTTP (mailtrap com token de produção, ou sendgrid).

get_email_adapter() retorna None quando o provider HTTP escolhido não tem
credencial configurada — o chamador (CommunicationService._send_email) faz
fallback para o caminho SMTP (credencial do tenant → SMTP_* global).
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class EmailAdapter(ABC):
    @abstractmethod
    def send(
        self,
        to: str,
        subject: str,
        body: str,
        from_email: str,
        from_name: str = "Paladino",
    ) -> None:
        """Envia email texto-plano. Levanta exceção em falha."""


class MailtrapAdapter(EmailAdapter):
    """Mailtrap HTTP API — sandbox (inbox_id > 0) ou produção (Email Sending API)."""

    def __init__(self, api_token: str, sandbox_inbox_id: int = 0):
        self.api_token = api_token
        self.sandbox_inbox_id = sandbox_inbox_id

    def send(self, to, subject, body, from_email, from_name="Paladino") -> None:
        import requests

        if self.sandbox_inbox_id:
            url = f"https://sandbox.api.mailtrap.io/api/send/{self.sandbox_inbox_id}"
            headers = {"Api-Token": self.api_token}
        else:
            url = "https://send.api.mailtrap.io/api/send"
            headers = {"Authorization": f"Bearer {self.api_token}"}

        resp = requests.post(
            url,
            json={
                "from": {"email": from_email, "name": from_name},
                "to": [{"email": to}],
                "subject": subject,
                "text": body,
            },
            headers=headers,
            timeout=10,
        )
        if not resp.ok:
            raise RuntimeError(f"Mailtrap HTTP API erro {resp.status_code}: {resp.text}")


class SendGridAdapter(EmailAdapter):
    """SendGrid Mail Send API v3 — implementação mínima (texto plano)."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def send(self, to, subject, body, from_email, from_name="Paladino") -> None:
        import requests

        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            json={
                "personalizations": [{"to": [{"email": to}]}],
                "from": {"email": from_email, "name": from_name},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            },
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        # SendGrid responde 202 Accepted em sucesso.
        if not resp.ok:
            raise RuntimeError(f"SendGrid API erro {resp.status_code}: {resp.text}")


def get_email_adapter() -> Optional[EmailAdapter]:
    """Resolve o adapter HTTP global conforme EMAIL_PROVIDER.

    Retorna None quando o caminho SMTP deve ser usado (EMAIL_PROVIDER=smtp,
    provider desconhecido, ou credencial do provider HTTP ausente).
    """
    from app.core.config import settings

    provider = (settings.EMAIL_PROVIDER or "mailtrap").lower()

    if provider == "sendgrid":
        if settings.SENDGRID_API_KEY:
            return SendGridAdapter(settings.SENDGRID_API_KEY)
        logger.warning("EMAIL_PROVIDER=sendgrid sem SENDGRID_API_KEY — fallback SMTP")
        return None

    if provider == "smtp":
        return None

    if provider != "mailtrap":
        logger.warning("EMAIL_PROVIDER=%r desconhecido — fallback SMTP", provider)
        return None

    if settings.MAILTRAP_API_TOKEN:
        return MailtrapAdapter(
            settings.MAILTRAP_API_TOKEN,
            settings.MAILTRAP_SANDBOX_INBOX_ID,
        )
    return None

"""
Emails de plataforma (Sprint C) — enviados DIRETO via Mailtrap/SMTP global,
sem CommunicationService (eventos de plataforma não pertencem ao tenant).
Mesmo padrão de _send_reset_email_direct em modules/auth/service.py.
"""
from typing import Optional


def _send_direct(recipient_email: str, subject: str, body: str) -> None:
    from app.core.config import settings as app_settings

    from_email = app_settings.SMTP_FROM_EMAIL or "noreply@paladino.app"

    if app_settings.MAILTRAP_API_TOKEN:
        import requests

        if app_settings.MAILTRAP_SANDBOX_INBOX_ID:
            url = f"https://sandbox.api.mailtrap.io/api/send/{app_settings.MAILTRAP_SANDBOX_INBOX_ID}"
            headers = {"Api-Token": app_settings.MAILTRAP_API_TOKEN}
        else:
            url = "https://send.api.mailtrap.io/api/send"
            headers = {"Authorization": f"Bearer {app_settings.MAILTRAP_API_TOKEN}"}
        payload = {
            "from": {"email": from_email, "name": "Paladino"},
            "to": [{"email": recipient_email}],
            "subject": subject,
            "text": body,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if not resp.ok:
            raise RuntimeError(f"Mailtrap erro {resp.status_code}: {resp.text}")
        return

    import smtplib
    from email.mime.text import MIMEText

    if not app_settings.SMTP_HOST:
        raise RuntimeError("Email não configurado: MAILTRAP_API_TOKEN e SMTP_HOST ausentes")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = recipient_email
    with smtplib.SMTP(app_settings.SMTP_HOST, app_settings.SMTP_PORT, timeout=10) as s:
        if app_settings.SMTP_USE_TLS:
            s.starttls()
        if app_settings.SMTP_USER and app_settings.SMTP_PASSWORD:
            s.login(app_settings.SMTP_USER, app_settings.SMTP_PASSWORD)
        s.sendmail(from_email, [recipient_email], msg.as_string())


def send_suspension_email(
    recipient_email: str,
    owner_name: str,
    company_name: str,
    reason: Optional[str],
) -> None:
    subject = f"Sua conta Paladino foi suspensa — {company_name}"
    body = (
        f"Olá, {owner_name or 'responsável'}!\n\n"
        f"A conta da empresa {company_name} na plataforma Paladino foi suspensa.\n"
        + (f"\nMotivo: {reason}\n" if reason else "")
        + "\nSeus dados estão preservados. Entre em contato com o suporte "
        "para regularizar a situação.\n"
    )
    _send_direct(recipient_email, subject, body)

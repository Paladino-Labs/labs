"""Testes do adapter de email plugável — Sprint I.

Cobre:
  1. get_email_adapter() resolve provider por EMAIL_PROVIDER + credencial
  2. Fallback para SMTP (None) quando credencial ausente ou provider=smtp
  3. MailtrapAdapter sandbox vs produção (URL + header)
  4. SendGridAdapter payload mínimo
  5. _send_email() delega ao adapter quando configurado
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.modules.communication.email_adapters import (
    MailtrapAdapter,
    SendGridAdapter,
    get_email_adapter,
)


# ── 1/2. get_email_adapter() ──────────────────────────────────────────────────

class TestGetEmailAdapter:

    def test_mailtrap_default_with_token(self):
        with patch("app.core.config.settings") as s:
            s.EMAIL_PROVIDER = "mailtrap"
            s.MAILTRAP_API_TOKEN = "tok"
            s.MAILTRAP_SANDBOX_INBOX_ID = 123
            adapter = get_email_adapter()
        assert isinstance(adapter, MailtrapAdapter)
        assert adapter.sandbox_inbox_id == 123

    def test_mailtrap_without_token_falls_back_to_smtp(self):
        with patch("app.core.config.settings") as s:
            s.EMAIL_PROVIDER = "mailtrap"
            s.MAILTRAP_API_TOKEN = ""
            assert get_email_adapter() is None

    def test_sendgrid_with_key(self):
        with patch("app.core.config.settings") as s:
            s.EMAIL_PROVIDER = "sendgrid"
            s.SENDGRID_API_KEY = "sg-key"
            adapter = get_email_adapter()
        assert isinstance(adapter, SendGridAdapter)

    def test_sendgrid_without_key_falls_back_to_smtp(self):
        with patch("app.core.config.settings") as s:
            s.EMAIL_PROVIDER = "sendgrid"
            s.SENDGRID_API_KEY = ""
            assert get_email_adapter() is None

    def test_smtp_provider_returns_none(self):
        with patch("app.core.config.settings") as s:
            s.EMAIL_PROVIDER = "smtp"
            assert get_email_adapter() is None

    def test_unknown_provider_returns_none(self):
        with patch("app.core.config.settings") as s:
            s.EMAIL_PROVIDER = "pombo-correio"
            assert get_email_adapter() is None


# ── 3. MailtrapAdapter ────────────────────────────────────────────────────────

class TestMailtrapAdapter:

    def _send(self, adapter):
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True
            adapter.send(
                to="x@y.com", subject="S", body="B", from_email="noreply@p.app"
            )
        return mock_post.call_args

    def test_sandbox_url_and_header(self):
        args = self._send(MailtrapAdapter("tok", sandbox_inbox_id=42))
        assert args.args[0] == "https://sandbox.api.mailtrap.io/api/send/42"
        assert args.kwargs["headers"] == {"Api-Token": "tok"}

    def test_production_url_and_bearer(self):
        args = self._send(MailtrapAdapter("tok", sandbox_inbox_id=0))
        assert args.args[0] == "https://send.api.mailtrap.io/api/send"
        assert args.kwargs["headers"] == {"Authorization": "Bearer tok"}

    def test_error_raises(self):
        adapter = MailtrapAdapter("tok")
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = False
            mock_post.return_value.status_code = 401
            mock_post.return_value.text = "unauthorized"
            with pytest.raises(RuntimeError):
                adapter.send("x@y.com", "S", "B", "noreply@p.app")


# ── 4. SendGridAdapter ────────────────────────────────────────────────────────

class TestSendGridAdapter:

    def test_payload_and_auth(self):
        adapter = SendGridAdapter("sg-key")
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True
            adapter.send("x@y.com", "Assunto", "Corpo", "noreply@p.app")

        args = mock_post.call_args
        assert args.args[0] == "https://api.sendgrid.com/v3/mail/send"
        assert args.kwargs["headers"]["Authorization"] == "Bearer sg-key"
        payload = args.kwargs["json"]
        assert payload["personalizations"][0]["to"] == [{"email": "x@y.com"}]
        assert payload["content"][0]["value"] == "Corpo"

    def test_error_raises(self):
        adapter = SendGridAdapter("sg-key")
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = False
            mock_post.return_value.status_code = 403
            mock_post.return_value.text = "forbidden"
            with pytest.raises(RuntimeError):
                adapter.send("x@y.com", "S", "B", "noreply@p.app")


# ── 5. _send_email() delega ao adapter ───────────────────────────────────────

class TestSendEmailUsesAdapter:

    def test_send_email_delegates_to_adapter(self):
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        comm_settings = MagicMock()
        comm_settings.smtp_credential_id = None
        mock_adapter = MagicMock()

        with patch(
            "app.modules.communication.email_adapters.get_email_adapter",
            return_value=mock_adapter,
        ):
            svc._send_email(
                comm_settings,
                {"recipient_email": "x@y.com", "email_subject": "Oi"},
                "corpo renderizado",
                MagicMock(),
            )

        mock_adapter.send.assert_called_once()
        kwargs = mock_adapter.send.call_args.kwargs
        assert kwargs["to"] == "x@y.com"
        assert kwargs["subject"] == "Oi"
        assert kwargs["body"] == "corpo renderizado"

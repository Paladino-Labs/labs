"""
Testes do canal EMAIL — CommunicationService + forgot_password.

Todos os testes usam mocks; nenhuma conexão real é feita.
"""
import smtplib
import uuid
import pytest
from datetime import datetime, time, timezone
from unittest.mock import MagicMock, patch, call


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_settings(
    email_enabled: bool = True,
    whatsapp_enabled: bool = False,
    smtp_credential_id=None,
    quiet_hours_enabled: bool = False,
    quiet_start: time = time(22, 0),
    quiet_end: time = time(8, 0),
) -> MagicMock:
    s = MagicMock()
    s.email_enabled = email_enabled
    s.whatsapp_enabled = whatsapp_enabled
    s.smtp_credential_id = smtp_credential_id
    s.quiet_hours_enabled = quiet_hours_enabled
    s.quiet_hours_start = quiet_start
    s.quiet_hours_end = quiet_end
    s.company_id = uuid.uuid4()
    return s


def _make_template(event_type: str = "auth.password_reset_requested", channel: str = "EMAIL") -> MagicMock:
    t = MagicMock()
    t.template_id = uuid.uuid4()
    t.body_template = "Olá, {{user_name}}! Seu código: {{token}}"
    t.event_type = event_type
    t.channel = channel
    t.is_active = True
    return t


def _make_db(
    settings=None,
    template=None,
    cred=None,
    channel_filter: str | None = None,
) -> MagicMock:
    """
    Mock de Session. Retorna template apenas se channel_filter é None ou bate com
    o primeiro filter() chamado que menciona o channel buscado — simulado via
    side_effect que sempre devolve o template fornecido (comportamento conservador:
    os filtros de canal são aplicados no código, não aqui).
    """
    def query_side_effect(model_class):
        q = MagicMock()
        name = model_class.__name__

        if name == "CommunicationSetting" and settings is not None:
            q.filter.return_value.first.return_value = settings
        elif name == "CommunicationTemplate" and template is not None:
            q.filter.return_value.first.return_value = template
        elif name == "IntegrationCredential" and cred is not None:
            q.filter.return_value.first.return_value = cred
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []

        return q

    db = MagicMock()
    db.query.side_effect = query_side_effect
    return db


# ── 1. dispatch() EMAIL com template válido → _send_email() chamado ──────────

class TestDispatchEmail:

    def test_dispatch_email_calls_send_email(self):
        """dispatch() com email_enabled=True e template EMAIL → _send_email() chamado."""
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        settings = _make_settings(email_enabled=True)
        template = _make_template(channel="EMAIL")
        db = _make_db(settings=settings, template=template)

        with patch.object(svc, "_send_email") as mock_send:
            log = svc.dispatch(
                event_type="auth.password_reset_requested",
                company_id=settings.company_id,
                context={
                    "recipient_email": "user@example.com",
                    "token": "123456",
                    "user_name": "Maria",
                },
                recipient_id=uuid.uuid4(),
                recipient_type="CLIENT",
                db=db,
            )

        assert log.status == "SENT"
        mock_send.assert_called_once()

    def test_dispatch_whatsapp_not_called_when_email_enabled(self):
        """Quando email_enabled=True e há template EMAIL, _send_whatsapp não é chamado."""
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        settings = _make_settings(email_enabled=True, whatsapp_enabled=True)
        template = _make_template(channel="EMAIL")
        db = _make_db(settings=settings, template=template)

        with patch.object(svc, "_send_email") as mock_email, \
             patch.object(svc, "_send_whatsapp") as mock_wa:
            svc.dispatch(
                event_type="auth.password_reset_requested",
                company_id=settings.company_id,
                context={"recipient_email": "x@x.com", "token": "000000", "user_name": "X"},
                recipient_id=uuid.uuid4(),
                recipient_type="CLIENT",
                db=db,
            )

        mock_email.assert_called_once()
        mock_wa.assert_not_called()

    def test_dispatch_no_channels_enabled_returns_skipped(self):
        """Nenhum canal habilitado → SKIPPED_CHANNEL_DISABLED."""
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        settings = _make_settings(email_enabled=False, whatsapp_enabled=False)
        db = _make_db(settings=settings)

        log = svc.dispatch(
            event_type="auth.password_reset_requested",
            company_id=settings.company_id,
            context={},
            recipient_id=uuid.uuid4(),
            recipient_type="CLIENT",
            db=db,
        )

        assert log.status == "SKIPPED_CHANNEL_DISABLED"


# ── 2. dispatch() sem template EMAIL → SKIPPED_NO_TEMPLATE ───────────────────

class TestDispatchNoTemplate:

    def test_dispatch_email_enabled_but_no_template_returns_skipped(self):
        """email_enabled=True mas sem template EMAIL → SKIPPED_NO_TEMPLATE."""
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        settings = _make_settings(email_enabled=True, whatsapp_enabled=False)
        db = _make_db(settings=settings, template=None)  # nenhum template

        log = svc.dispatch(
            event_type="auth.password_reset_requested",
            company_id=settings.company_id,
            context={"recipient_email": "user@example.com"},
            recipient_id=uuid.uuid4(),
            recipient_type="CLIENT",
            db=db,
        )

        assert log.status == "SKIPPED_NO_TEMPLATE"

    def test_dispatch_email_falls_back_to_whatsapp_when_no_email_template(self):
        """email_enabled=True mas sem template EMAIL; whatsapp_enabled=True com template → WHATSAPP."""
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        settings = _make_settings(email_enabled=True, whatsapp_enabled=True)

        call_count = [0]
        whatsapp_template = _make_template(channel="WHATSAPP")

        def query_side_effect(model_class):
            q = MagicMock()
            name = model_class.__name__
            if name == "CommunicationSetting":
                q.filter.return_value.first.return_value = settings
            elif name == "CommunicationTemplate":
                call_count[0] += 1
                # Primeira chamada (EMAIL) → None; segunda (WHATSAPP) → template
                if call_count[0] == 1:
                    q.filter.return_value.first.return_value = None
                else:
                    q.filter.return_value.first.return_value = whatsapp_template
            else:
                q.filter.return_value.first.return_value = None
            return q

        db = MagicMock()
        db.query.side_effect = query_side_effect

        with patch.object(svc, "_send_whatsapp") as mock_wa, \
             patch.object(svc, "_send_email") as mock_email:
            log = svc.dispatch(
                event_type="appointment.confirmed",
                company_id=settings.company_id,
                context={"recipient_phone": "5562999999999"},
                recipient_id=uuid.uuid4(),
                recipient_type="CLIENT",
                db=db,
            )

        assert log.status == "SENT"
        mock_wa.assert_called_once()
        mock_email.assert_not_called()


# ── 3. _send_email() com SMTP mock → log SENT gravado ────────────────────────

class TestSendEmail:

    @pytest.fixture(autouse=True)
    def _patch_smtp_settings(self, monkeypatch):
        import app.core.config as cfg
        monkeypatch.setattr(cfg.settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(cfg.settings, "SMTP_PORT", 587)
        monkeypatch.setattr(cfg.settings, "SMTP_USER", "testuser")
        monkeypatch.setattr(cfg.settings, "SMTP_PASSWORD", "testpass")
        monkeypatch.setattr(cfg.settings, "SMTP_FROM_EMAIL", "noreply@paladino.app")
        monkeypatch.setattr(cfg.settings, "SMTP_USE_TLS", True)

    def test_send_email_uses_smtplib(self):
        """_send_email() abre conexão SMTP, chama starttls/login/sendmail."""
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        comm_settings = _make_settings(email_enabled=True, smtp_credential_id=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch("smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = lambda s: mock_server
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)

            svc._send_email(
                comm_settings=comm_settings,
                context={
                    "recipient_email": "cliente@example.com",
                    "email_subject": "Código de reset",
                },
                rendered_body="Seu código: 123456",
                db=db,
            )

        MockSMTP.assert_called_once_with("smtp.mailtrap.io", 587, timeout=10)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("testuser", "testpass")
        mock_server.sendmail.assert_called_once()
        # Verifica destinatário no sendmail (2º argumento posicional é a lista de recipients)
        pos_args = mock_server.sendmail.call_args[0]
        assert "cliente@example.com" in pos_args[1]

    def test_send_email_uses_tenant_credential_when_present(self):
        """_send_email() usa credencial SMTP do tenant quando smtp_credential_id está presente."""
        from app.modules.communication.service import CommunicationService
        from app.core.encryption import encrypt_secret
        from cryptography.fernet import Fernet
        import app.core.config as cfg

        # Setup encryption key for this test
        key = Fernet.generate_key().decode()
        original_key = cfg.settings.CREDENTIAL_ENCRYPTION_KEY
        cfg.settings.CREDENTIAL_ENCRYPTION_KEY = key

        try:
            svc = CommunicationService()
            cred_id = uuid.uuid4()
            comm_settings = _make_settings(email_enabled=True, smtp_credential_id=cred_id)

            mock_cred = MagicMock()
            mock_cred.config = {
                "host": "smtp.tenant.com",
                "port": 465,
                "from_email": "tenant@company.com",
                "use_tls": True,
            }
            mock_cred.secret_encrypted = encrypt_secret("tenantpassword")

            def query_side_effect(model_class):
                q = MagicMock()
                if model_class.__name__ == "IntegrationCredential":
                    q.filter.return_value.first.return_value = mock_cred
                else:
                    q.filter.return_value.first.return_value = None
                return q

            db = MagicMock()
            db.query.side_effect = query_side_effect

            with patch("smtplib.SMTP") as MockSMTP:
                mock_server = MagicMock()
                MockSMTP.return_value.__enter__ = lambda s: mock_server
                MockSMTP.return_value.__exit__ = MagicMock(return_value=False)

                svc._send_email(
                    comm_settings=comm_settings,
                    context={"recipient_email": "user@tenant.com"},
                    rendered_body="Mensagem de teste",
                    db=db,
                )

            MockSMTP.assert_called_once_with("smtp.tenant.com", 465, timeout=10)
        finally:
            cfg.settings.CREDENTIAL_ENCRYPTION_KEY = original_key

    def test_send_email_raises_when_recipient_email_missing(self):
        """_send_email() levanta ValueError quando recipient_email ausente no context."""
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        comm_settings = _make_settings(email_enabled=True, smtp_credential_id=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="recipient_email"):
            svc._send_email(
                comm_settings=comm_settings,
                context={},  # sem recipient_email
                rendered_body="Corpo do e-mail",
                db=db,
            )

    def test_send_email_raises_when_smtp_host_missing(self):
        """_send_email() levanta RuntimeError quando SMTP_HOST não configurado."""
        from app.modules.communication.service import CommunicationService
        import app.core.config as cfg

        svc = CommunicationService()
        comm_settings = _make_settings(email_enabled=True, smtp_credential_id=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        # Remove SMTP_HOST para simular falta de config
        original = cfg.settings.SMTP_HOST
        cfg.settings.SMTP_HOST = ""
        try:
            with pytest.raises(RuntimeError, match="SMTP_HOST"):
                svc._send_email(
                    comm_settings=comm_settings,
                    context={"recipient_email": "user@example.com"},
                    rendered_body="Corpo",
                    db=db,
                )
        finally:
            cfg.settings.SMTP_HOST = original


# ── 4. _send_email() com falha → log FAILED, sem propagação ──────────────────

class TestSendEmailFailure:

    @pytest.fixture(autouse=True)
    def _patch_smtp_settings(self, monkeypatch):
        import app.core.config as cfg
        monkeypatch.setattr(cfg.settings, "SMTP_HOST", "smtp.mailtrap.io")
        monkeypatch.setattr(cfg.settings, "SMTP_PORT", 587)
        monkeypatch.setattr(cfg.settings, "SMTP_USER", "testuser")
        monkeypatch.setattr(cfg.settings, "SMTP_PASSWORD", "testpass")
        monkeypatch.setattr(cfg.settings, "SMTP_FROM_EMAIL", "noreply@paladino.app")
        monkeypatch.setattr(cfg.settings, "SMTP_USE_TLS", True)

    def test_dispatch_email_failure_returns_failed_log_without_raising(self):
        """Falha no envio SMTP → log FAILED gravado, exceção não propaga."""
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        settings = _make_settings(email_enabled=True)
        template = _make_template(channel="EMAIL")
        db = _make_db(settings=settings, template=template)

        with patch.object(svc, "_send_email", side_effect=smtplib.SMTPException("Connection refused")):
            log = svc.dispatch(
                event_type="auth.password_reset_requested",
                company_id=settings.company_id,
                context={"recipient_email": "user@example.com", "token": "654321", "user_name": "João"},
                recipient_id=uuid.uuid4(),
                recipient_type="CLIENT",
                db=db,
            )

        assert log.status == "FAILED"
        assert "Connection refused" in log.error_message

    def test_dispatch_smtp_error_does_not_raise(self):
        """smtplib.SMTPException não propaga para fora de dispatch()."""
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        settings = _make_settings(email_enabled=True)
        template = _make_template(channel="EMAIL")
        db = _make_db(settings=settings, template=template)

        # Não deve levantar nenhuma exceção
        with patch.object(svc, "_send_email", side_effect=smtplib.SMTPException("timeout")):
            result = svc.dispatch(
                event_type="auth.password_reset_requested",
                company_id=settings.company_id,
                context={"recipient_email": "user@example.com", "token": "111111", "user_name": "Ana"},
                recipient_id=uuid.uuid4(),
                recipient_type="CLIENT",
                db=db,
            )
        assert result is not None


# ── 5. forgot_password() → token no banco mesmo com SMTP indisponível ─────────

class TestForgotPassword:

    @pytest.fixture(autouse=True)
    def _setup_encryption(self, monkeypatch):
        from cryptography.fernet import Fernet
        import app.core.config as cfg
        key = Fernet.generate_key().decode()
        monkeypatch.setattr(cfg.settings, "CREDENTIAL_ENCRYPTION_KEY", key)

    def test_forgot_password_saves_token_even_when_smtp_unavailable(self):
        """Token gravado no banco mesmo quando SMTP lança exceção."""
        from app.modules.auth.service import forgot_password
        from app.core.security import verify_password

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.company_id = uuid.uuid4()
        mock_user.email = "user@example.com"
        mock_user.name = "Usuário Teste"
        mock_user.active = True

        added_tokens = []

        def query_side_effect(model_class):
            q = MagicMock()
            name = model_class.__name__
            if name == "User":
                q.filter.return_value.first.return_value = mock_user
            elif name == "PasswordResetToken":
                q.filter.return_value.update.return_value = 0
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = query_side_effect
        mock_db.add.side_effect = lambda obj: added_tokens.append(obj)

        with patch(
            "app.modules.communication.service.CommunicationService._send_email",
            side_effect=smtplib.SMTPException("SMTP down"),
        ):
            forgot_password(mock_db, "user@example.com")

        # Token foi adicionado ao banco (db.add chamado com PasswordResetToken).
        # Pode haver um segundo db.add para o CommunicationLog (status=FAILED), o que é esperado.
        assert mock_db.commit.called
        from app.infrastructure.db.models.password_reset_token import PasswordResetToken
        reset_tokens = [obj for obj in added_tokens if isinstance(obj, PasswordResetToken)]
        assert len(reset_tokens) == 1
        assert reset_tokens[0].user_id == mock_user.id
        assert reset_tokens[0].token_hash

    def test_forgot_password_unknown_email_is_silent(self):
        """Email desconhecido → retorna sem erro, sem commit."""
        from app.modules.auth.service import forgot_password

        def query_side_effect(model_class):
            q = MagicMock()
            q.filter.return_value.first.return_value = None
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = query_side_effect

        forgot_password(mock_db, "naoexiste@example.com")

        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_forgot_password_context_includes_recipient_email(self):
        """forgot_password() inclui recipient_email no context passado ao dispatch."""
        from app.modules.auth.service import forgot_password

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.company_id = uuid.uuid4()
        mock_user.email = "cliente@example.com"
        mock_user.name = "Cliente"
        mock_user.active = True

        def query_side_effect(model_class):
            q = MagicMock()
            name = model_class.__name__
            if name == "User":
                q.filter.return_value.first.return_value = mock_user
            elif name == "PasswordResetToken":
                q.filter.return_value.update.return_value = 0
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = query_side_effect

        captured_context = {}

        def mock_dispatch(**kwargs):
            captured_context.update(kwargs.get("context", {}))
            return MagicMock(status="SKIPPED_CHANNEL_DISABLED")

        with patch(
            "app.modules.communication.service.communication_service.dispatch",
            side_effect=mock_dispatch,
        ):
            forgot_password(mock_db, "cliente@example.com")

        assert captured_context.get("recipient_email") == "cliente@example.com"
        assert "token" in captured_context

"""
Testes do Sprint 5 — CommunicationService, encrypt/decrypt, templates, credenciais.

Usa mocks (unittest.mock) para isolar da infraestrutura (Evolution API, banco PostgreSQL).
"""
import uuid
import pytest
from datetime import datetime, time, timezone, timedelta
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_comm_settings(
    whatsapp_enabled: bool = True,
    quiet_hours_enabled: bool = True,
    quiet_start: time = time(22, 0),
    quiet_end: time = time(8, 0),
) -> MagicMock:
    s = MagicMock()
    s.whatsapp_enabled = whatsapp_enabled
    s.quiet_hours_enabled = quiet_hours_enabled
    s.quiet_hours_start = quiet_start
    s.quiet_hours_end = quiet_end
    s.company_id = uuid.uuid4()
    return s


def _make_template(event_type: str = "appointment.confirmed") -> MagicMock:
    t = MagicMock()
    t.template_id = uuid.uuid4()
    t.body_template = "Olá, {{cliente_nome}}! Seu {{servico}} está confirmado."
    t.event_type = event_type
    t.is_active = True
    return t


def _make_db(settings=None, template=None, conn=None, customer=None) -> MagicMock:
    """Cria um mock de Session que retorna os objetos conforme o modelo consultado."""

    def query_side_effect(model_class):
        q = MagicMock()
        name = model_class.__name__

        if name == "CommunicationSetting" and settings is not None:
            q.filter.return_value.first.return_value = settings
        elif name == "CommunicationTemplate" and template is not None:
            q.filter.return_value.first.return_value = template
        elif name == "WhatsAppConnection" and conn is not None:
            q.filter.return_value.first.return_value = conn
        elif name == "Customer" and customer is not None:
            q.filter.return_value.first.return_value = customer
        elif name == "CommunicationLog":
            # drain_scheduled: retorna lista com log agendado
            log_mock = MagicMock()
            log_mock.status = "SCHEDULED"
            log_mock.scheduled_send_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            log_mock.rendered_body = None
            log_mock.company_id = uuid.uuid4()
            q.filter.return_value.all.return_value = []
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []

        return q

    mock_db = MagicMock()
    mock_db.query.side_effect = query_side_effect
    return mock_db


# ── 1 e 2. Quiet hours — transacional vs automático ───────────────────────────

class TestQuietHoursBehavior:

    # ─ Horário fixo DENTRO de quiet_hours: 23:00 UTC ──────────────────────────
    _INSIDE_QUIET = datetime(2026, 1, 15, 23, 0, 0, tzinfo=timezone.utc)

    def _dispatch_with_fixed_time(
        self,
        event_type: str,
        settings: MagicMock,
        template: MagicMock | None,
        fixed_now: datetime,
    ):
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        mock_db = _make_db(settings=settings, template=template)

        with patch("app.modules.communication.service.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now

            with patch.object(svc, "_send_whatsapp"):
                log = svc.dispatch(
                    event_type=event_type,
                    company_id=settings.company_id,
                    context={"cliente_nome": "João", "servico": "Corte"},
                    recipient_id=uuid.uuid4(),
                    recipient_type="CLIENT",
                    db=mock_db,
                )

        return log

    def test_transactional_event_bypasses_quiet_hours_and_returns_sent(self):
        """appointment.confirmed dentro de quiet_hours → status SENT (bypass transacional)."""
        settings = _make_comm_settings(quiet_hours_enabled=True)
        template = _make_template("appointment.confirmed")

        log = self._dispatch_with_fixed_time(
            event_type="appointment.confirmed",
            settings=settings,
            template=template,
            fixed_now=self._INSIDE_QUIET,
        )

        assert log.status == "SENT", (
            f"Evento transacional deveria bypass quiet_hours e ser SENT, mas foi: {log.status}"
        )

    def test_automatic_event_in_quiet_hours_returns_scheduled(self):
        """appointment.reminder_due dentro de quiet_hours → status SCHEDULED (automático)."""
        settings = _make_comm_settings(quiet_hours_enabled=True)

        log = self._dispatch_with_fixed_time(
            event_type="appointment.reminder_due",
            settings=settings,
            template=None,  # não chega a buscar template — retorna antes
            fixed_now=self._INSIDE_QUIET,
        )

        assert log.status == "SCHEDULED", (
            f"Evento automático em quiet_hours deveria ser SCHEDULED, mas foi: {log.status}"
        )

    def test_automatic_event_outside_quiet_hours_does_not_schedule(self):
        """Evento automático FORA de quiet_hours não retorna SCHEDULED diretamente."""
        # 10:00 UTC — fora de [22:00, 08:00)
        outside_quiet = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        settings = _make_comm_settings(quiet_hours_enabled=True)
        template = _make_template("appointment.reminder_due")

        log = self._dispatch_with_fixed_time(
            event_type="appointment.reminder_due",
            settings=settings,
            template=template,
            fixed_now=outside_quiet,
        )

        assert log.status != "SCHEDULED"

    def test_cancelled_is_transactional_and_bypasses_quiet_hours(self):
        """appointment.cancelled também é transacional → bypass quiet_hours."""
        settings = _make_comm_settings(quiet_hours_enabled=True)
        template = _make_template("appointment.cancelled")

        log = self._dispatch_with_fixed_time(
            event_type="appointment.cancelled",
            settings=settings,
            template=template,
            fixed_now=self._INSIDE_QUIET,
        )

        # Se o template existe e send funciona → SENT; se template não existe → SKIPPED_NO_TEMPLATE
        # Em ambos os casos, NÃO deve ser SCHEDULED
        assert log.status != "SCHEDULED", (
            f"appointment.cancelled é transacional, não deve ser SCHEDULED"
        )


# ── 3. drain_scheduled ────────────────────────────────────────────────────────

class TestDrainScheduled:

    def test_drain_processes_scheduled_log_with_rendered_body(self):
        """drain_scheduled envia mensagens com rendered_body e retorna contagem."""
        from app.modules.communication.service import communication_service

        company_id = uuid.uuid4()

        mock_log = MagicMock()
        mock_log.status = "SCHEDULED"
        mock_log.scheduled_send_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        mock_log.rendered_body = "Olá, João! Seu corte está confirmado."
        mock_log.company_id = company_id
        mock_log.recipient_id = uuid.uuid4()

        mock_settings = MagicMock()
        mock_settings.whatsapp_enabled = True
        mock_settings.company_id = company_id

        mock_conn = MagicMock()
        mock_conn.instance_name = "evo-test-instance"

        mock_customer = MagicMock()
        mock_customer.phone = "5562999999999"

        def query_side_effect(model_class):
            q = MagicMock()
            name = model_class.__name__
            if name == "CommunicationLog":
                q.filter.return_value.all.return_value = [mock_log]
            elif name == "CommunicationSetting":
                q.filter.return_value.first.return_value = mock_settings
            elif name == "WhatsAppConnection":
                q.filter.return_value.first.return_value = mock_conn
            elif name == "Customer":
                q.filter.return_value.first.return_value = mock_customer
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = query_side_effect

        with patch("app.modules.whatsapp.evolution_client.send_text") as mock_send:
            sent = communication_service.drain_scheduled(mock_db)

        assert sent == 1
        assert mock_log.status == "SENT"
        mock_send.assert_called_once_with(
            "evo-test-instance", "5562999999999", "Olá, João! Seu corte está confirmado."
        )

    def test_drain_marks_failed_when_rendered_body_missing(self):
        """drain_scheduled marca FAILED quando rendered_body é None."""
        from app.modules.communication.service import communication_service

        mock_log = MagicMock()
        mock_log.status = "SCHEDULED"
        mock_log.rendered_body = None
        mock_log.company_id = uuid.uuid4()
        mock_log.recipient_id = uuid.uuid4()

        mock_settings = MagicMock()
        mock_settings.whatsapp_enabled = True

        def query_side_effect(model_class):
            q = MagicMock()
            name = model_class.__name__
            if name == "CommunicationLog":
                q.filter.return_value.all.return_value = [mock_log]
            elif name == "CommunicationSetting":
                q.filter.return_value.first.return_value = mock_settings
            elif name == "WhatsAppConnection":
                q.filter.return_value.first.return_value = MagicMock()
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = query_side_effect

        sent = communication_service.drain_scheduled(mock_db)
        assert sent == 0
        assert mock_log.status == "FAILED"

    def test_drain_skips_when_channel_disabled(self):
        """drain_scheduled ignora logs se whatsapp_enabled=False."""
        from app.modules.communication.service import communication_service

        mock_log = MagicMock()
        mock_log.status = "SCHEDULED"
        mock_log.rendered_body = "mensagem"
        mock_log.company_id = uuid.uuid4()

        mock_settings = MagicMock()
        mock_settings.whatsapp_enabled = False

        def query_side_effect(model_class):
            q = MagicMock()
            name = model_class.__name__
            if name == "CommunicationLog":
                q.filter.return_value.all.return_value = [mock_log]
            elif name == "CommunicationSetting":
                q.filter.return_value.first.return_value = mock_settings
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = query_side_effect

        sent = communication_service.drain_scheduled(mock_db)
        assert sent == 0
        assert mock_log.status == "SKIPPED_CHANNEL_DISABLED"


# ── 4. encrypt/decrypt round-trip ─────────────────────────────────────────────

class TestEncryptDecrypt:

    @pytest.fixture(autouse=True)
    def _set_encryption_key(self, monkeypatch):
        """Injeta chave Fernet válida para os testes."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key)
        # Força o reload das settings para pegar a nova chave
        import app.core.config as cfg_module
        # Patch direto no objeto settings
        monkeypatch.setattr(cfg_module.settings, "CREDENTIAL_ENCRYPTION_KEY", key)

    def test_round_trip_encrypt_decrypt(self):
        """decrypt(encrypt('abc')) == 'abc'."""
        from app.core.encryption import encrypt_secret, decrypt_secret

        plaintext = "abc"
        ciphertext = encrypt_secret(plaintext)
        recovered = decrypt_secret(ciphertext)
        assert recovered == plaintext

    def test_encrypt_does_not_return_plaintext(self):
        """O ciphertext não deve ser igual ao plaintext."""
        from app.core.encryption import encrypt_secret

        plaintext = "minha_senha_secreta"
        ciphertext = encrypt_secret(plaintext)
        assert ciphertext != plaintext

    def test_decrypt_with_wrong_key_raises(self, monkeypatch):
        """Descriptografar com chave diferente deve levantar erro."""
        from cryptography.fernet import Fernet
        from app.core.encryption import encrypt_secret

        plaintext = "segredo"
        ciphertext = encrypt_secret(plaintext)

        # Troca a chave
        new_key = Fernet.generate_key().decode()
        import app.core.config as cfg_module
        monkeypatch.setattr(cfg_module.settings, "CREDENTIAL_ENCRYPTION_KEY", new_key)

        from app.core import encryption as enc_module
        from cryptography.fernet import InvalidToken
        with pytest.raises((InvalidToken, Exception)):
            enc_module.decrypt_secret(ciphertext)


# ── 5. make_masked_preview ────────────────────────────────────────────────────

class TestMaskedPreview:

    def test_masked_preview_shows_last_4_chars(self):
        """make_masked_preview('abcdef1234') == '***•••1234'"""
        from app.core.encryption import make_masked_preview

        result = make_masked_preview("abcdef1234")
        assert result == "***•••1234"

    def test_masked_preview_with_short_string(self):
        """Funciona com strings curtas (< 4 chars)."""
        from app.core.encryption import make_masked_preview

        result = make_masked_preview("ab")
        # Mostra os 2 últimos chars (que são todos os chars disponíveis)
        assert result.endswith("ab")
        assert "***•••" in result

    def test_masked_preview_with_api_key(self):
        """Simula uma chave de API real."""
        from app.core.encryption import make_masked_preview

        api_key = "sk_live_XXXX_0000_YYYY_ZZZZ_ABCD1234"
        result = make_masked_preview(api_key)
        assert result.endswith("1234")
        assert result.startswith("***•••")


# ── 6. CredentialResponse — sem secret_encrypted, com masked_preview ─────────

class TestCredentialResponseSchema:

    def test_credential_response_has_no_secret_encrypted_field(self):
        """CredentialResponse não deve expor secret_encrypted."""
        from app.modules.integrations.schemas import CredentialResponse

        fields = CredentialResponse.model_fields
        assert "secret_encrypted" not in fields, (
            "secret_encrypted não deve ser exposto na resposta da API"
        )

    def test_credential_response_has_masked_preview_field(self):
        """CredentialResponse deve expor masked_preview."""
        from app.modules.integrations.schemas import CredentialResponse

        fields = CredentialResponse.model_fields
        assert "masked_preview" in fields, (
            "masked_preview deve estar presente na resposta da API"
        )

    def test_credential_response_from_attributes(self):
        """CredentialResponse pode ser construído a partir de atributos de modelo."""
        from app.modules.integrations.schemas import CredentialResponse

        mock_cred = MagicMock()
        mock_cred.credential_id = uuid.uuid4()
        mock_cred.company_id = uuid.uuid4()
        mock_cred.provider = "SMTP"
        mock_cred.label = "SMTP principal"
        mock_cred.masked_preview = "***•••5678"
        mock_cred.config = {}
        mock_cred.status = "ACTIVE"
        mock_cred.created_at = datetime.now(timezone.utc)

        # Verifica que o schema consegue serializar sem 'secret_encrypted'
        resp = CredentialResponse.model_validate(mock_cred)
        data = resp.model_dump()
        assert "secret_encrypted" not in data
        assert data["masked_preview"] == "***•••5678"


# ── 7. Template is_default — DELETE bloqueado ────────────────────────────────

class TestTemplateDefaultRestrictions:

    def test_delete_default_template_raises_422(self):
        """DELETE em template com is_default=True deve retornar 422."""
        from app.modules.communication.router import delete_template
        from fastapi import HTTPException

        mock_template = MagicMock()
        mock_template.template_id = uuid.uuid4()
        mock_template.is_default = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_template

        mock_user = MagicMock()
        mock_user.role = "OWNER"

        with pytest.raises(HTTPException) as exc_info:
            delete_template(
                template_id=mock_template.template_id,
                user=mock_user,
                company_id=uuid.uuid4(),
                db=mock_db,
            )

        assert exc_info.value.status_code == 422
        assert "padrão" in exc_info.value.detail.lower()

    def test_delete_non_default_template_succeeds(self):
        """DELETE em template com is_default=False deve funcionar normalmente."""
        from app.modules.communication.router import delete_template

        mock_template = MagicMock()
        mock_template.template_id = uuid.uuid4()
        mock_template.is_default = False

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_template

        mock_user = MagicMock()
        mock_user.role = "OWNER"

        # Não deve levantar
        delete_template(
            template_id=mock_template.template_id,
            user=mock_user,
            company_id=uuid.uuid4(),
            db=mock_db,
        )

        mock_db.delete.assert_called_once_with(mock_template)
        mock_db.commit.assert_called_once()

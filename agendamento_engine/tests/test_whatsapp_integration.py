"""
Testes de integração da Evolution API / WhatsApp.

Cobre (casos obrigatórios do escopo):
  1. dispatch() → send_text() chamado com phone e rendered_body corretos
  2. dispatch() → WhatsApp DISCONNECTED → RuntimeError → log FAILED (sem propagação)
  3. Webhook sem EVOLUTION_WEBHOOK_SECRET → aceita qualquer request (compatibilidade)
  4. Webhook com segredo + header correto → 200
  5. Webhook com segredo + header errado → 401
  6. send_list() não gera log em nível ERROR em fluxo normal
"""
import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_conn(status: str = "CONNECTED", company_id=None) -> MagicMock:
    c = MagicMock()
    c.instance_name = "test-instance"
    c.status = status
    c.company_id = company_id or uuid.uuid4()
    return c


def _make_comm_settings(company_id=None) -> MagicMock:
    s = MagicMock()
    s.whatsapp_enabled = True
    s.quiet_hours_enabled = False
    s.company_id = company_id or uuid.uuid4()
    return s


def _make_template(body: str = "Olá, {{cliente_nome}}! Confirmado.") -> MagicMock:
    t = MagicMock()
    t.template_id = uuid.uuid4()
    t.body_template = body
    t.event_type = "appointment.confirmed"
    t.is_active = True
    return t


def _make_db(settings_obj=None, template=None, conn=None) -> MagicMock:
    """Cria um mock de Session que retorna os objetos conforme o modelo consultado."""
    def _q(model_class):
        q = MagicMock()
        name = model_class.__name__
        if name == "CommunicationSetting":
            q.filter.return_value.first.return_value = settings_obj
        elif name == "CommunicationTemplate":
            q.filter.return_value.first.return_value = template
        elif name == "WhatsAppConnection":
            q.filter.return_value.first.return_value = conn
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    mock_db = MagicMock()
    mock_db.query.side_effect = _q
    return mock_db


# ── 1. dispatch() → send_text() com phone e rendered_body corretos ─────────────

class TestDispatchSendText:

    def test_dispatch_calls_send_text_with_correct_args(self):
        """dispatch() deve chamar evolution_client.send_text com phone e corpo renderizado."""
        from app.modules.communication.service import CommunicationService

        company_id = uuid.uuid4()
        conn = _make_conn("CONNECTED", company_id=company_id)
        comm_settings = _make_comm_settings(company_id=company_id)
        template = _make_template("Olá, {{cliente_nome}}! Confirmado.")

        db = _make_db(settings_obj=comm_settings, template=template, conn=conn)
        svc = CommunicationService()

        with patch("app.modules.whatsapp.evolution_client.send_text") as mock_send:
            log = svc.dispatch(
                event_type="appointment.confirmed",
                company_id=company_id,
                context={
                    "cliente_nome": "Maria",
                    "recipient_phone": "5511999999999",
                },
                recipient_id=uuid.uuid4(),
                recipient_type="CLIENT",
                db=db,
            )

        assert log.status == "SENT"
        mock_send.assert_called_once_with(
            conn.instance_name,
            "5511999999999",
            "Olá, Maria! Confirmado.",
        )


# ── 2. dispatch() → DISCONNECTED → RuntimeError interna → log FAILED ──────────

class TestDispatchDisconnected:

    def test_dispatch_disconnected_returns_failed_no_propagation(self):
        """
        Sem conexão CONNECTED (conn=None) → RuntimeError interna no _send_whatsapp.
        Não deve propagar — log com status=FAILED deve ser retornado.
        """
        from app.modules.communication.service import CommunicationService

        company_id = uuid.uuid4()
        comm_settings = _make_comm_settings(company_id=company_id)
        template = _make_template()

        # conn=None simula ausência de conexão CONNECTED no banco
        db = _make_db(settings_obj=comm_settings, template=template, conn=None)
        svc = CommunicationService()

        # Não deve levantar exceção
        log = svc.dispatch(
            event_type="appointment.confirmed",
            company_id=company_id,
            context={
                "cliente_nome": "Carlos",
                "recipient_phone": "5511888888888",
            },
            recipient_id=uuid.uuid4(),
            recipient_type="CLIENT",
            db=db,
        )

        assert log.status == "FAILED"
        assert log.error_message  # RuntimeError message deve estar presente


# ── 3, 4, 5. Webhook — validação de segredo via header x-evolution-global-apikey ─

class TestWebhookSecretValidation:
    """
    Testa a validação de EVOLUTION_WEBHOOK_SECRET no endpoint POST /whatsapp/webhook.
    Usa uma mini-app FastAPI isolada com o router real e get_db mockado.
    """

    def _make_client(self) -> TestClient:
        from app.modules.whatsapp.router import router
        from app.infrastructure.db.session import get_db

        app = FastAPI()
        app.include_router(router)

        mock_db = MagicMock()

        def _override_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_db
        return TestClient(app, raise_server_exceptions=False)

    # Payload de evento desconhecido — nenhum handler é chamado, sem IO de DB
    _UNKNOWN_EVENT = {"event": "UNKNOWN_EVENT_FOR_TEST", "instance": "x", "data": {}}

    def test_no_secret_configured_accepts_any_request(self):
        """EVOLUTION_WEBHOOK_SECRET vazio → qualquer request aceito (modo legado)."""
        client = self._make_client()

        with patch("app.modules.whatsapp.router.settings") as mock_settings:
            mock_settings.EVOLUTION_WEBHOOK_SECRET = ""
            resp = client.post("/whatsapp/webhook", json=self._UNKNOWN_EVENT)

        assert resp.status_code == 200

    def test_correct_secret_header_returns_200(self):
        """EVOLUTION_WEBHOOK_SECRET configurado + header correto → 200."""
        client = self._make_client()

        with patch("app.modules.whatsapp.router.settings") as mock_settings:
            mock_settings.EVOLUTION_WEBHOOK_SECRET = "meu-segredo-secreto"
            resp = client.post(
                "/whatsapp/webhook",
                json=self._UNKNOWN_EVENT,
                headers={"x-evolution-global-apikey": "meu-segredo-secreto"},
            )

        assert resp.status_code == 200

    def test_wrong_secret_header_returns_401(self):
        """EVOLUTION_WEBHOOK_SECRET configurado + header errado → 401 com status=rejected."""
        client = self._make_client()

        with patch("app.modules.whatsapp.router.settings") as mock_settings:
            mock_settings.EVOLUTION_WEBHOOK_SECRET = "meu-segredo-secreto"
            resp = client.post(
                "/whatsapp/webhook",
                json=self._UNKNOWN_EVENT,
                headers={"x-evolution-global-apikey": "segredo-errado"},
            )

        assert resp.status_code == 401
        body = resp.json()
        assert body.get("status") == "rejected"

    def test_missing_secret_header_returns_401(self):
        """EVOLUTION_WEBHOOK_SECRET configurado + header ausente → 401."""
        client = self._make_client()

        with patch("app.modules.whatsapp.router.settings") as mock_settings:
            mock_settings.EVOLUTION_WEBHOOK_SECRET = "meu-segredo-secreto"
            resp = client.post(
                "/whatsapp/webhook",
                json=self._UNKNOWN_EVENT,
                # sem o header x-evolution-global-apikey
            )

        assert resp.status_code == 401


# ── 6. send_list() — sem log ERROR em fluxo normal ────────────────────────────

class TestSendListNoErrorLog:

    def test_send_list_does_not_log_error_on_success(self, caplog):
        """send_list() em resposta 2xx não deve emitir nenhum log em nível ERROR."""
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.status_code = 201

        with patch("httpx.post", return_value=mock_response):
            with caplog.at_level(
                logging.ERROR,
                logger="app.modules.whatsapp.evolution_client",
            ):
                from app.modules.whatsapp.evolution_client import send_list
                send_list(
                    instance_name="test-instance",
                    to="5511999999999",
                    title="Serviços",
                    description="Escolha um serviço",
                    button_text="Ver opções",
                    rows=[{"rowId": "s1", "title": "Corte", "description": ""}],
                )

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert not error_records, (
            "send_list() emitiu log(s) ERROR inesperado(s) em fluxo normal: "
            + str([r.getMessage() for r in error_records])
        )

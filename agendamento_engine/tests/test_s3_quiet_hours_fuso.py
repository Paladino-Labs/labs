"""
S3 — quiet_hours para eventos operacionais.

Dois defeitos somados faziam o alerta de escalada sumir no pico da barbearia:

  1. `conversation.escalated` não estava em nenhuma das duas listas de exceção,
     então caía no `else` e virava SKIPPED_QUIET_HOURS — descartado, não adiado.
  2. A janela era comparada em UTC contra Time naive que é hora LOCAL do tenant.
     Com o default 22:00–08:00, a janela efetiva em Brasília era 19:00 → 05:00.

Os testes abaixo congelam o relógio em horários de Brasília e verificam o status
resultante. `America/Sao_Paulo` é UTC-3 o ano todo (sem horário de verão desde
2019), então BRT = UTC-3 nas conversões daqui.
"""
import uuid
from datetime import datetime, time, timezone
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _brt(year, month, day, hour, minute=0) -> datetime:
    """Instante UTC correspondente a um horário de Brasília (UTC-3)."""
    from zoneinfo import ZoneInfo
    local = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/Sao_Paulo"))
    return local.astimezone(timezone.utc)


def _make_comm_settings() -> MagicMock:
    s = MagicMock()
    s.whatsapp_enabled = True
    s.email_enabled = False
    s.quiet_hours_enabled = True
    s.quiet_hours_start = time(22, 0)
    s.quiet_hours_end = time(8, 0)
    s.company_id = uuid.uuid4()
    return s


def _make_template(event_type: str) -> MagicMock:
    t = MagicMock()
    t.template_id = uuid.uuid4()
    t.body_template = "Cliente {{customer_name}} pediu atendimento."
    t.event_type = event_type
    t.is_active = True
    return t


_SENTINEL = object()


def _make_db(settings, template=None, company_tz=_SENTINEL) -> MagicMock:
    """Session mockada. `company_tz`:
      - string      → Company existe com esse timezone;
      - None        → Company existe com timezone nulo (fallback);
      - _SENTINEL   → Company NÃO existe (fallback).
    """
    def query_side_effect(model_class):
        q = MagicMock()
        name = model_class.__name__
        if name == "CommunicationSetting":
            q.filter.return_value.first.return_value = settings
        elif name == "CommunicationTemplate":
            q.filter.return_value.first.return_value = template
        elif name == "Company":
            if company_tz is _SENTINEL:
                q.filter.return_value.first.return_value = None
            else:
                company = MagicMock()
                company.timezone = company_tz
                q.filter.return_value.first.return_value = company
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    db = MagicMock()
    db.query.side_effect = query_side_effect
    return db


def _dispatch_at(event_type, fixed_now, *, template=None, company_tz=_SENTINEL,
                 recipient_type="OWNER"):
    from app.modules.communication.service import CommunicationService

    settings = _make_comm_settings()
    svc = CommunicationService()
    db = _make_db(settings, template=template, company_tz=company_tz)

    with patch("app.modules.communication.service.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        with patch.object(svc, "_send_whatsapp"):
            return svc.dispatch(
                event_type=event_type,
                company_id=settings.company_id,
                context={
                    "customer_name": "João",
                    "recipient_phone": "5562988887777",
                },
                recipient_id=uuid.uuid4(),
                recipient_type=recipient_type,
                db=db,
            )


# ── 1. conversation.escalated sai a qualquer hora ─────────────────────────────

class TestEscaladaBypassaQuietHours:
    """O alerta de 'tem cliente esperando AGORA' não pode ser adiado nem descartado."""

    @pytest.mark.parametrize("hora, minuto", [(19, 30), (21, 0), (4, 0)])
    def test_escalated_e_enviada_dentro_da_janela_morta(self, hora, minuto):
        """19:30, 21:00 e 04:00 BRT — os três horários medidos como SKIPPED antes do S3."""
        log = _dispatch_at(
            "conversation.escalated",
            _brt(2026, 1, 16, hora, minuto),
            template=_make_template("conversation.escalated"),
            company_tz="America/Sao_Paulo",
        )
        assert log.status == "SENT", (
            f"conversation.escalated as {hora:02d}:{minuto:02d} BRT deveria ser SENT, "
            f"mas foi: {log.status}"
        )

    def test_escalated_tambem_sai_no_horario_comercial(self):
        """Controle: fora da janela nada muda."""
        log = _dispatch_at(
            "conversation.escalated",
            _brt(2026, 1, 16, 14, 0),
            template=_make_template("conversation.escalated"),
            company_tz="America/Sao_Paulo",
        )
        assert log.status == "SENT"


# ── 2. O escopo não vazou ─────────────────────────────────────────────────────

class TestEscopoNaoVazou:
    """Só `conversation.escalated` entrou na lista transacional — nada mais."""

    def test_evento_fora_das_duas_listas_continua_descartado(self):
        """Evento sem lista, 23:00 BRT → SKIPPED_QUIET_HOURS, como antes.

        ⚠️ 23:00 e não 21:00: depois da correção do fuso, 21:00 BRT está FORA de
        22:00–08:00 local. O horário que exercita o `else` é um de dentro da
        janela verdadeira.
        """
        log = _dispatch_at(
            "marketing.campaign_blast",
            _brt(2026, 1, 15, 23, 0),
            template=_make_template("marketing.campaign_blast"),
            company_tz="America/Sao_Paulo",
        )
        assert log.status == "SKIPPED_QUIET_HOURS", (
            f"Evento fora das duas listas deveria continuar descartado, mas foi: {log.status}"
        )

    def test_evento_da_lista_scheduled_continua_adiado(self):
        """appointment.reminder_24h as 23:00 BRT → SCHEDULED, como antes."""
        log = _dispatch_at(
            "appointment.reminder_24h",
            _brt(2026, 1, 15, 23, 0),
            company_tz="America/Sao_Paulo",
        )
        assert log.status == "SCHEDULED"

    def test_scheduled_send_at_e_o_fim_da_janela_no_fuso_local(self):
        """23:00 BRT → agendado para 08:00 BRT do dia seguinte = 11:00 UTC."""
        log = _dispatch_at(
            "appointment.reminder_24h",
            _brt(2026, 1, 15, 23, 0),
            company_tz="America/Sao_Paulo",
        )
        assert log.status == "SCHEDULED"
        assert log.scheduled_send_at == datetime(2026, 1, 16, 11, 0, tzinfo=timezone.utc), (
            f"scheduled_send_at deveria ser 08:00 BRT (11:00 UTC), mas foi: "
            f"{log.scheduled_send_at}"
        )


# ── 3. Mudança de comportamento visível: a janela andou 3h ────────────────────

class TestJanelaCorrigida:
    """Registro executável da mudança: 19:00–22:00 BRT deixou de ser quiet_hours."""

    def test_lembrete_as_20h_brt_nao_e_mais_adiado(self):
        """20:00 BRT era 23:00 UTC → adiado antes do S3. Agora sai."""
        log = _dispatch_at(
            "appointment.reminder_24h",
            _brt(2026, 1, 15, 20, 0),
            template=_make_template("appointment.reminder_24h"),
            company_tz="America/Sao_Paulo",
        )
        assert log.status == "SENT", (
            f"20:00 BRT esta fora de 22:00-08:00 local; deveria sair. Foi: {log.status}"
        )

    def test_lembrete_as_06h_brt_passa_a_ser_adiado(self):
        """06:00 BRT era 09:00 UTC → saía antes do S3. Agora é adiado (correto)."""
        log = _dispatch_at(
            "appointment.reminder_24h",
            _brt(2026, 1, 16, 6, 0),
            template=_make_template("appointment.reminder_24h"),
            company_tz="America/Sao_Paulo",
        )
        assert log.status == "SCHEDULED"


# ── 4. O fuso é lido do tenant, não hardcoded ─────────────────────────────────

class TestFusoVemDoTenant:

    def test_mesmo_instante_dois_fusos_dois_resultados(self):
        """01:30 UTC = 22:30 São Paulo (dentro) e 21:30 Manaus (fora, UTC-4)."""
        instante = datetime(2026, 1, 16, 1, 30, tzinfo=timezone.utc)

        log_sp = _dispatch_at(
            "appointment.reminder_24h", instante,
            template=_make_template("appointment.reminder_24h"),
            company_tz="America/Sao_Paulo",
        )
        log_manaus = _dispatch_at(
            "appointment.reminder_24h", instante,
            template=_make_template("appointment.reminder_24h"),
            company_tz="America/Manaus",
        )

        assert log_sp.status == "SCHEDULED", f"Sao Paulo: {log_sp.status}"
        assert log_manaus.status == "SENT", (
            f"Manaus e UTC-4: 21:30 local esta fora da janela. Foi: {log_manaus.status}"
        )


# ── 5. Fallback de fuso ───────────────────────────────────────────────────────

class TestFallbackDeFuso:
    """Sem fuso utilizável cai em America/Sao_Paulo — nunca em UTC, que
    reproduziria o defeito em silêncio."""

    @pytest.mark.parametrize("company_tz, rotulo", [
        (_SENTINEL, "Company inexistente"),
        (None, "timezone nulo"),
        ("", "timezone vazio"),
        ("Marte/Olympus_Mons", "timezone invalido"),
    ])
    def test_fallback_usa_sao_paulo(self, company_tz, rotulo):
        """23:00 BRT (= 02:00 UTC): dentro da janela local, FORA se comparada em
        UTC. O teste falha se o fallback for UTC em vez de America/Sao_Paulo."""
        log = _dispatch_at(
            "appointment.reminder_24h",
            _brt(2026, 1, 15, 23, 0),
            company_tz=company_tz,
        )
        assert log.status == "SCHEDULED", f"{rotulo}: {log.status}"

    def test_fallback_nao_quebra_a_escalada(self):
        """Sem Company, conversation.escalated continua saindo (nem chega a consultar)."""
        log = _dispatch_at(
            "conversation.escalated",
            _brt(2026, 1, 16, 21, 0),
            template=_make_template("conversation.escalated"),
        )
        assert log.status == "SENT"

    def test_erro_ao_ler_company_nao_derruba_o_dispatch(self):
        """db.query levantando no meio do caminho → default, sem exceção."""
        from app.modules.communication.service import _company_timezone

        db = MagicMock()
        db.query.side_effect = RuntimeError("conexao caiu")
        assert _company_timezone(db, uuid.uuid4()) == "America/Sao_Paulo"


# ── 6. Transacional não paga a query de Company ───────────────────────────────

class TestCustoDaQuery:

    def test_evento_transacional_nao_consulta_company(self):
        """A leitura do fuso é preguiçosa: só o ramo que avalia quiet_hours paga."""
        from app.modules.communication.service import CommunicationService

        settings = _make_comm_settings()
        svc = CommunicationService()
        db = _make_db(settings, template=_make_template("conversation.escalated"),
                      company_tz="America/Sao_Paulo")

        with patch("app.modules.communication.service.datetime") as mock_dt:
            mock_dt.now.return_value = _brt(2026, 1, 16, 21, 0)
            with patch.object(svc, "_send_whatsapp"):
                svc.dispatch(
                    event_type="conversation.escalated",
                    company_id=settings.company_id,
                    context={"customer_name": "João", "recipient_phone": "5562988887777"},
                    recipient_id=uuid.uuid4(),
                    recipient_type="OWNER",
                    db=db,
                )

        consultados = [c.args[0].__name__ for c in db.query.call_args_list if c.args]
        assert "Company" not in consultados, (
            f"dispatch transacional nao deveria consultar Company. Consultou: {consultados}"
        )

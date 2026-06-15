"""
Testes de timezone para geração de slots de disponibilidade.

Garante que opening_time/closing_time (horário local do tenant) são
convertidos corretamente para UTC antes de gerar e comparar slots.
"""
import uuid
from datetime import date, time, datetime, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest


# ── _localize_to_utc ─────────────────────────────────────────────────────────

class TestLocalizeToUtc:

    def test_sao_paulo_morning_to_utc(self):
        """09:00 BRT (UTC-3) deve converter para 12:00 UTC."""
        from app.modules.availability.service import _localize_to_utc

        result = _localize_to_utc(date(2026, 6, 1), time(9, 0), "America/Sao_Paulo")

        assert result.hour == 12
        assert result.minute == 0
        assert result.tzinfo is not None

    def test_sao_paulo_afternoon_to_utc(self):
        """18:00 BRT (UTC-3) deve converter para 21:00 UTC."""
        from app.modules.availability.service import _localize_to_utc

        result = _localize_to_utc(date(2026, 6, 1), time(18, 0), "America/Sao_Paulo")

        assert result.hour == 21
        assert result.tzinfo is not None

    def test_utc_timezone_unchanged(self):
        """Para timezone UTC o horário não muda."""
        from app.modules.availability.service import _localize_to_utc

        result = _localize_to_utc(date(2026, 6, 1), time(9, 0), "UTC")

        assert result.hour == 9
        assert result.tzinfo is not None

    def test_invalid_timezone_falls_back_to_sao_paulo(self):
        """Timezone inválido usa fallback America/Sao_Paulo (não levanta exceção)."""
        from app.modules.availability.service import _localize_to_utc

        # "Invalid/Zone" não existe — deve usar fallback e retornar hora válida
        result = _localize_to_utc(date(2026, 6, 1), time(9, 0), "Invalid/Zone")

        assert result.tzinfo is not None
        assert result.hour == 12  # fallback America/Sao_Paulo → UTC+3h

    def test_result_is_utc_aware(self):
        """O resultado sempre é timezone-aware em UTC."""
        from app.modules.availability.service import _localize_to_utc

        result = _localize_to_utc(date(2026, 6, 1), time(10, 30), "America/Sao_Paulo")

        assert result.tzinfo is not None
        assert result.utcoffset().total_seconds() == 0


# ── get_available_slots com TenantConfig.timezone ────────────────────────────

class TestGetAvailableSlotsTimezone:
    """
    Testa que get_available_slots usa TenantConfig.timezone para converter
    opening_time/closing_time de horário local para UTC.
    """

    def _make_mock_db(self, tz_name: str, opening: time, closing: time,
                      professional_id, company_id, service_id):
        """Cria um mock de Session configurado para o cenário de disponibilidade."""
        mock_db = MagicMock()

        # Mock Professional
        mock_prof = MagicMock()
        mock_prof.id = professional_id
        mock_prof.company_id = company_id
        mock_prof.active = True
        mock_prof.name = "Teste Prof"

        # Mock Service
        mock_svc = MagicMock()
        mock_svc.id = service_id
        mock_svc.company_id = company_id
        mock_svc.active = True
        mock_svc.duration = 60  # 60 minutos

        # Mock WorkingHour
        mock_wh = MagicMock()
        mock_wh.opening_time = opening
        mock_wh.closing_time = closing

        # Mock TenantConfig
        mock_config = MagicMock()
        mock_config.timezone = tz_name

        # Configura as queries na ordem em que são chamadas por get_available_slots:
        # 1. Professional, 2. Service, 3. WorkingHour, 4. TenantConfig, 5. Appointment, 6. ScheduleBlock
        def query_side_effect(model_class):
            from app.infrastructure.db.models import (
                Professional, Service, WorkingHour, TenantConfig,
                Appointment, ScheduleBlock,
            )
            mock_q = MagicMock()
            filter_result = MagicMock()

            if model_class is Professional:
                filter_result.first.return_value = mock_prof
            elif model_class is Service:
                filter_result.first.return_value = mock_svc
            elif model_class is WorkingHour:
                filter_result.first.return_value = mock_wh
            elif model_class is TenantConfig:
                filter_result.first.return_value = mock_config
            elif model_class is Appointment:
                filter_result.all.return_value = []
            elif model_class is ScheduleBlock:
                filter_result.all.return_value = []
            else:
                filter_result.first.return_value = None
                filter_result.all.return_value = []

            mock_q.filter.return_value = filter_result
            return mock_q

        mock_db.query.side_effect = query_side_effect
        return mock_db

    def test_slot_generation_uses_tenant_timezone(self):
        """
        Profissional com horário 09:00-12:00 em America/Sao_Paulo (UTC-3).
        Slots devem ser retornados como 12:00-15:00 UTC, não 09:00-12:00 UTC.
        """
        from app.modules.availability.service import get_available_slots

        professional_id = uuid.uuid4()
        company_id = uuid.uuid4()
        service_id = uuid.uuid4()

        target_date = date(2027, 1, 15)  # data futura fixa, independente do horário de execução
        opening = time(9, 0)
        closing = time(12, 0)

        mock_db = self._make_mock_db(
            tz_name="America/Sao_Paulo",
            opening=opening,
            closing=closing,
            professional_id=professional_id,
            company_id=company_id,
            service_id=service_id,
        )

        slots = get_available_slots(mock_db, company_id, professional_id, service_id, target_date)

        assert len(slots) > 0, "Deve haver pelo menos um slot disponível"

        first_slot = slots[0]
        assert first_slot.start_at.tzinfo is not None, "start_at deve ser timezone-aware"

        # 09:00 BRT = 12:00 UTC
        utc_hour = first_slot.start_at.astimezone(ZoneInfo("UTC")).hour
        assert utc_hour == 12, (
            f"Primeiro slot deve começar às 12:00 UTC (09:00 BRT), mas foi {utc_hour}:00 UTC"
        )

    def test_slots_not_treated_as_utc(self):
        """
        Sem conversão de timezone, 09:00 seria tratado como 09:00 UTC
        e os slots gerariam às 09:00 UTC em vez de 12:00 UTC.
        Confirma que o bug original (UTC hardcoded) não está presente.
        """
        from app.modules.availability.service import get_available_slots

        professional_id = uuid.uuid4()
        company_id = uuid.uuid4()
        service_id = uuid.uuid4()

        target_date = date(2027, 1, 15)  # data futura fixa, independente do horário de execução

        mock_db = self._make_mock_db(
            tz_name="America/Sao_Paulo",
            opening=time(9, 0),
            closing=time(12, 0),
            professional_id=professional_id,
            company_id=company_id,
            service_id=service_id,
        )

        slots = get_available_slots(mock_db, company_id, professional_id, service_id, target_date)

        assert len(slots) > 0
        first_utc_hour = slots[0].start_at.astimezone(ZoneInfo("UTC")).hour

        # Se o bug estivesse presente, first_utc_hour == 9 (UTC hardcoded)
        assert first_utc_hour != 9, (
            "Bug: horário tratado como UTC. Esperado 12:00 UTC (09:00 BRT), mas obteve 09:00 UTC"
        )
        assert first_utc_hour == 12

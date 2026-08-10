"""
S-onboarding — os bloqueadores que só apareceriam no primeiro tenant novo.

Os dois tenants em produção são de São Paulo e foram configurados à mão, o que
escondia dois defeitos: o tenant nasce mudo (item 1) e o fuso das mensagens é
uma constante (item 3). Os testes abaixo exercitam justamente o que o cadastro
manual mascarava — por isso o teste de fuso usa um tenant que NÃO é de SP.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo


# ── Item 1 — o tenant novo nasce com canal ligado ─────────────────────────────

def _create_company_added_objects():
    """Roda create_company com db mockado e devolve tudo que foi db.add()."""
    from app.modules.companies.service import create_company
    from app.modules.companies.schemas import CompanyCreate

    added: list = []
    mock_db = MagicMock()
    mock_db.add.side_effect = lambda obj: added.append(obj)
    # checagem de conflito de slug → sem conflito
    mock_db.query.return_value.filter.return_value.first.return_value = None

    data = CompanyCreate(name="Barbearia Onboarding", slug=f"onb-{uuid.uuid4().hex[:6]}")
    create_company(mock_db, data)
    return added


def _only_communication_setting(added: list):
    settings = [o for o in added if type(o).__name__ == "CommunicationSetting"]
    assert len(settings) == 1, f"esperava 1 CommunicationSetting, veio {len(settings)}"
    return settings[0]


def test_new_tenant_is_born_with_whatsapp_enabled():
    """Sem isto o dispatch sai em SKIPPED_CHANNEL_DISABLED e o tenant nasce mudo."""
    cs = _only_communication_setting(_create_company_added_objects())
    assert cs.whatsapp_enabled is True


def test_new_tenant_is_born_with_email_disabled():
    """Decisão registrada do sprint: EMAIL é o primeiro da preferência de canal, e a
    queda para WHATSAPP só cobre template ausente — nunca falha de envio. Ligar o
    e-mail sem provedor configurado roteia o reset de senha para um canal que não
    entrega. Se um provedor real for configurado, este teste deve ser revisto junto."""
    cs = _only_communication_setting(_create_company_added_objects())
    assert cs.email_enabled is False


def test_new_tenant_seeds_whatsapp_templates_reachable_by_the_enabled_channel():
    """Os templates semeados precisam existir NO canal que nasce ligado — senão a
    correção do flag não entrega mensagem nenhuma."""
    added = _create_company_added_objects()
    templates = [o for o in added if type(o).__name__ == "CommunicationTemplate"]
    whatsapp = [t for t in templates if t.channel == "WHATSAPP"]
    assert whatsapp, "nenhum template WHATSAPP semeado"
    # a confirmação de agendamento ao cliente é o caminho vivo mais óbvio
    assert any(
        t.event_type == "appointment.confirmed" and t.audience == "CLIENT"
        for t in whatsapp
    )


def test_dispatch_for_new_tenant_does_not_skip_channel_disabled():
    """O teste que amarra o item 1 ao efeito: com o CommunicationSetting que o
    create_company produz, o dispatch NÃO sai no primeiro passo."""
    from app.modules.communication.service import communication_service

    cs = _only_communication_setting(_create_company_added_objects())
    company_id = uuid.uuid4()

    template = MagicMock()
    template.template_id = uuid.uuid4()
    template.body_template = "Olá, {{customer_name}}!"
    template.channel = "WHATSAPP"

    logged: list = []

    def query_side_effect(model_class):
        q = MagicMock()
        name = model_class.__name__
        if name == "CommunicationSetting":
            q.filter.return_value.first.return_value = cs
        elif name == "CommunicationTemplate":
            q.filter.return_value.first.return_value = template
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    mock_db = MagicMock()
    mock_db.query.side_effect = query_side_effect
    mock_db.add.side_effect = lambda obj: logged.append(obj)

    with patch.object(communication_service, "_send_whatsapp"):
        entry = communication_service.dispatch(
            event_type="appointment.confirmed",
            company_id=company_id,
            context={"customer_name": "Ana", "recipient_phone": "5511999999999"},
            recipient_id=uuid.uuid4(),
            recipient_type="CLIENT",
            db=mock_db,
        )

    assert entry.status != "SKIPPED_CHANNEL_DISABLED"
    assert entry.status == "SENT"
    assert entry.channel == "WHATSAPP"


# ── Item 3 — o fuso vem do TenantConfig, não de uma constante ─────────────────

def _db_with_tenant_config(timezone_name):
    """Session mockada cujo TenantConfig devolve o timezone pedido (None = sem config)."""
    config = None
    if timezone_name is not None:
        config = MagicMock()
        config.timezone = timezone_name

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = config
    return mock_db


def test_get_company_tz_reads_tenant_config():
    """Antes do S-onboarding esta função lia CompanySettings.timezone — coluna
    inexistente — e o AttributeError virava sempre America/Sao_Paulo, sem log."""
    from app.modules.notifications import _get_company_tz

    tz = _get_company_tz(_db_with_tenant_config("America/Manaus"), uuid.uuid4())
    assert tz == ZoneInfo("America/Manaus")


def test_get_company_tz_falls_back_without_tenant_config():
    from app.modules.notifications import _get_company_tz

    tz = _get_company_tz(_db_with_tenant_config(None), uuid.uuid4())
    assert tz == ZoneInfo("America/Sao_Paulo")


def test_get_company_tz_falls_back_on_invalid_timezone():
    from app.modules.notifications import _get_company_tz

    tz = _get_company_tz(_db_with_tenant_config("Nao/Existe"), uuid.uuid4())
    assert tz == ZoneInfo("America/Sao_Paulo")


def test_rendered_hour_differs_for_a_tenant_outside_sao_paulo():
    """⚠️ Este é o teste que PROVA o item 3.

    Sem um tenant de outro fuso, a função quebrada e a corrigida devolvem o mesmo
    valor e o teste não prova nada. 14:30 UTC é 11:30 em São Paulo (UTC-3) e
    10:30 em Manaus (UTC-4) — a mensagem tem de sair com a hora do tenant.
    """
    from app.modules.notifications import _get_company_tz, _fmt_datetime

    instant = datetime(2026, 5, 5, 14, 30, tzinfo=timezone.utc)

    tz_sp = _get_company_tz(_db_with_tenant_config("America/Sao_Paulo"), uuid.uuid4())
    tz_manaus = _get_company_tz(_db_with_tenant_config("America/Manaus"), uuid.uuid4())

    data_sp, hora_sp = _fmt_datetime(instant, tz_sp)
    data_manaus, hora_manaus = _fmt_datetime(instant, tz_manaus)

    assert hora_sp == "11:30"
    assert hora_manaus == "10:30", (
        "o tenant fora de SP recebeu a hora de SP — o resolvedor voltou a ser constante"
    )
    assert data_sp == data_manaus == "5 de maio"


def test_get_company_tz_never_raises_and_logs_the_fallback():
    """O except amplo é rede de segurança (o caller é envio de notificação), mas
    agora registra o motivo em vez de engolir em silêncio."""
    from app.modules import notifications

    broken_db = MagicMock()
    broken_db.query.side_effect = RuntimeError("banco fora do ar")

    with patch.object(notifications.logger, "warning") as warn:
        tz = notifications._get_company_tz(broken_db, uuid.uuid4())

    assert tz == ZoneInfo("America/Sao_Paulo")
    warn.assert_called_once()

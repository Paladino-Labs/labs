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


def test_new_tenant_is_born_with_email_enabled():
    """Decisão revisada do sprint: cada canal onde ele funciona.

    O e-mail é o ÚNICO canal com template para `user.invitation_sent` — é por ele
    que o dono de cada barbearia recebe acesso — e o provedor está configurado no
    Railway (SMTP_* + MAILTRAP_*). A leitura anterior, de que não havia provedor,
    veio do `.env` local, que não reflete o ambiente de produção.
    """
    cs = _only_communication_setting(_create_company_added_objects())
    assert cs.email_enabled is True


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


def test_dispatch_for_new_tenant_falls_back_to_whatsapp_for_client_events():
    """O teste que amarra o item 1 ao efeito.

    Com o CommunicationSetting que o create_company produz, o dispatch não sai em
    SKIPPED_CHANNEL_DISABLED. E prova o custo aceito na decisão revisada: como
    `channel_preference` é ["EMAIL", "WHATSAPP"] e `appointment.confirmed` não tem
    template EMAIL, há DUAS buscas de template por mensagem — a primeira sempre
    falha — antes de cair no WhatsApp, que entrega.
    """
    from app.modules.communication.service import communication_service

    cs = _only_communication_setting(_create_company_added_objects())
    company_id = uuid.uuid4()

    whatsapp_template = MagicMock()
    whatsapp_template.template_id = uuid.uuid4()
    whatsapp_template.body_template = "Olá, {{customer_name}}!"
    whatsapp_template.channel = "WHATSAPP"

    # O dispatch percorre channel_preference em ordem; espelhamos a realidade do
    # tenant novo: sem template EMAIL para este evento, com template WHATSAPP.
    template_lookups: list = []

    def query_side_effect(model_class):
        q = MagicMock()
        name = model_class.__name__
        if name == "CommunicationSetting":
            q.filter.return_value.first.return_value = cs
        elif name == "CommunicationTemplate":
            def first():
                template_lookups.append(len(template_lookups))
                # 1ª busca = EMAIL → não existe; 2ª = WHATSAPP → existe
                return None if len(template_lookups) == 1 else whatsapp_template
            q.filter.return_value.first.side_effect = first
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    mock_db = MagicMock()
    mock_db.query.side_effect = query_side_effect

    with patch.object(communication_service, "_send_whatsapp") as send_wpp, \
         patch.object(communication_service, "_send_email") as send_email:
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
    assert entry.channel == "WHATSAPP", "o cliente final tem de sair pelo WhatsApp"
    send_wpp.assert_called_once()
    send_email.assert_not_called()
    assert len(template_lookups) == 2, (
        "esperava a busca EMAIL falha antes do fallback WHATSAPP — se virou 1, a "
        "ordem de canal mudou e o custo descrito na decisão do item 1 sumiu"
    )


# ── Item 5 — por que o template WHATSAPP de convite NÃO foi criado ────────────

def test_invitation_dispatch_context_has_no_phone():
    """⚠️ Documenta o bloqueio do item 5, não um comportamento desejado.

    Um template WHATSAPP para `user.invitation_sent` só pode existir se o contexto
    do dispatch carregar `recipient_phone` — `_send_whatsapp` levanta
    `ValueError` sem ele (communication/service.py). Não carrega, e não há de onde:
    `User` e `UserInvitation` não têm coluna de telefone, e `InviteUserRequest`
    não tem campo. Criar o template trocaria SKIPPED_NO_TEMPLATE por FAILED —
    pior, porque parece que tentou.

    Se este teste quebrar porque o contexto passou a ter telefone, o item 5 está
    destravado: crie o template.
    """
    from app.modules.users import service as users_service
    from app.infrastructure.db.models.user_invitation import UserInvitation
    from app.infrastructure.db.models.user import User

    assert not hasattr(UserInvitation, "phone")
    assert not hasattr(User, "phone")

    captured: dict = {}

    def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    actor = MagicMock()
    actor.id = uuid.uuid4()
    actor.company_id = uuid.uuid4()
    actor.role = "OWNER"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("app.modules.communication.service.communication_service.dispatch",
               side_effect=fake_dispatch), \
         patch.object(users_service, "record_sensitive_action"):
        users_service.invite_user(
            db=mock_db,
            actor=actor,
            email="dono@barbearianova.com",
            role="OWNER",
        )

    assert captured, "invite_user não chegou a chamar o dispatch"
    assert captured["event_type"] == "user.invitation_sent"
    assert "recipient_phone" not in captured["context"], (
        "há telefone no contexto — o item 5 está destravado"
    )


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

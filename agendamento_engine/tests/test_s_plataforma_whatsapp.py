"""
S-plataforma-whatsapp — convite, reset e escalada por WhatsApp.

Um barbeiro da Le Duc recebeu o convite por e-mail e não abriu. O público do
produto é dono e funcionário de barbearia: o WhatsApp é o canal de identidade
deles, e-mail é formalidade preenchida no cadastro.

Os testes cobrem a cadeia inteira que estava faltando — telefone no convite,
telefone na conta ativada, WhatsApp na frente da preferência de canal — e, no
fim, o achado da Parte 6: por que `conversation.escalated` nunca gerou log.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


# ── 1. O convite exige telefone e o contexto do dispatch o carrega ────────────

def _invite(phone, role="OWNER"):
    """Roda invite_user com db mockado; devolve (invitation, kwargs do dispatch)."""
    from app.modules.users import service as users_service

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

    added: list = []
    mock_db.add.side_effect = lambda obj: added.append(obj)

    with patch("app.modules.communication.service.communication_service.dispatch",
               side_effect=fake_dispatch), \
         patch.object(users_service, "record_sensitive_action"):
        invitation = users_service.invite_user(
            db=mock_db,
            actor=actor,
            email="barbeiro@leduc.com",
            role=role,
            phone=phone,
        )
    return invitation, captured


def test_invite_requires_phone():
    """Decisão do Silva: obrigatório. Quem convida conhece a pessoa e tem o
    telefone à mão; opcional criaria o caso permanente "usuário sem canal"."""
    with pytest.raises(HTTPException) as exc:
        _invite(phone="")
    assert exc.value.status_code == 422
    assert "obrigat" in str(exc.value.detail).lower()


def test_invite_rejects_invalid_ddd():
    """O gate de formulário (whitelist ANATEL) vale também no painel: telefone
    com DDD inexistente vira convite que nunca chega."""
    with pytest.raises(HTTPException) as exc:
        _invite(phone="(00) 98565-7312")
    assert exc.value.status_code == 422


def test_invite_normalizes_phone_with_the_canonical_normalizer():
    """⚠️ Há 4 normalizações de telefone no backend. A usada aqui é a
    canônica-estrita (`identity/resolver.normalize_phone_e164`), que INSERE o 9º
    dígito. A quarta (`public/service._normalize_phone`) não insere e produziria
    uma chave diferente para o mesmo número."""
    invitation, captured = _invite(phone="62 8888-7777")  # celular antigo, sem o 9
    assert invitation.phone == "5562988887777"
    assert captured["context"]["recipient_phone"] == "5562988887777"


def test_invitation_dispatch_context_carries_the_invitee_phone():
    """O sucessor de `test_invitation_dispatch_context_has_no_phone` (S-onboarding).

    ⚠️ O telefone é o DO CONVIDADO. `Company.owner_mobile_phone` parece resolver e
    é armadilha: `invite_user` convida também ADMIN, OPERATOR e PROFESSIONAL, e
    usá-lo mandaria o link de ativação da conta de outra pessoa para o WhatsApp do
    dono — caminho de tomada de conta, não imprecisão de roteamento.
    """
    _, captured = _invite(phone="(11) 98888-7777", role="OPERATOR")

    assert captured["event_type"] == "user.invitation_sent"
    ctx = captured["context"]
    assert ctx["recipient_phone"] == "5511988887777"
    assert ctx["recipient_email"] == "barbeiro@leduc.com"
    assert ctx["activation_link"]


def test_invite_request_schema_requires_phone():
    """A obrigatoriedade vive também no contrato da API — não só no service."""
    from pydantic import ValidationError
    from app.modules.users.schemas import InviteUserRequest

    with pytest.raises(ValidationError):
        InviteUserRequest(email="a@b.com", role="OPERATOR")

    ok = InviteUserRequest(email="a@b.com", role="OPERATOR", phone="11988887777")
    assert ok.phone == "11988887777"


# ── 2. O telefone passa para o User na ativação ───────────────────────────────

def test_activation_copies_phone_from_invitation_to_user():
    """Sem isto o telefone morre no convite e o reset de senha volta ao e-mail."""
    from app.modules.auth import activate_service

    token = uuid.uuid4()
    invitation = MagicMock()
    invitation.status = "PENDING"
    invitation.email = "barbeiro@leduc.com"
    invitation.role = "PROFESSIONAL"
    invitation.company_id = uuid.uuid4()
    invitation.phone = "5562988887777"
    invitation.professional_id = None
    from datetime import datetime, timedelta, timezone
    invitation.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    created: list = []
    mock_db = MagicMock()
    mock_db.add.side_effect = lambda obj: created.append(obj)

    def query_side_effect(model_class):
        q = MagicMock()
        if model_class.__name__ == "UserInvitation":
            q.filter.return_value.first.return_value = invitation
        else:  # User (checagem de e-mail duplicado)
            q.filter.return_value.first.return_value = None
        return q

    mock_db.query.side_effect = query_side_effect

    activate_service.activate_account(
        db=mock_db, token=token, password="Senha123", password_confirm="Senha123",
    )

    users = [o for o in created if type(o).__name__ == "User"]
    assert len(users) == 1
    assert users[0].phone == "5562988887777"


def test_activation_tolerates_invitation_without_phone():
    """Convites PENDING criados antes deste sprint não têm telefone — a ativação
    não pode quebrar por isso."""
    from app.modules.auth import activate_service
    from datetime import datetime, timedelta, timezone

    invitation = MagicMock(spec=["status", "email", "role", "company_id",
                                 "expires_at", "professional_id"])
    invitation.status = "PENDING"
    invitation.email = "antigo@leduc.com"
    invitation.role = "OPERATOR"
    invitation.company_id = uuid.uuid4()
    invitation.professional_id = None
    invitation.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    created: list = []
    mock_db = MagicMock()
    mock_db.add.side_effect = lambda obj: created.append(obj)

    def query_side_effect(model_class):
        q = MagicMock()
        if model_class.__name__ == "UserInvitation":
            q.filter.return_value.first.return_value = invitation
        else:
            q.filter.return_value.first.return_value = None
        return q

    mock_db.query.side_effect = query_side_effect

    activate_service.activate_account(
        db=mock_db, token=uuid.uuid4(),
        password="Senha123", password_confirm="Senha123",
    )
    users = [o for o in created if type(o).__name__ == "User"]
    assert users[0].phone is None


# ── 3. Os três eventos de plataforma escolhem WhatsApp ────────────────────────

def _dispatch_with(context, event_type, recipient_type,
                   whatsapp_enabled=True, email_enabled=True,
                   has_email_template=True, has_whatsapp_template=True):
    """Roda o dispatch real com db mockado; devolve (log, canais consultados)."""
    from app.modules.communication.service import communication_service

    cs = MagicMock()
    cs.whatsapp_enabled = whatsapp_enabled
    cs.email_enabled = email_enabled
    cs.quiet_hours_enabled = False
    cs.company_id = uuid.uuid4()

    looked_up: list = []

    def query_side_effect(model_class):
        q = MagicMock()
        name = model_class.__name__
        if name == "CommunicationSetting":
            q.filter.return_value.first.return_value = cs
        elif name == "CommunicationTemplate":
            def filter_(*criteria):
                # O canal é o 3º critério do filtro (company, event, channel, …).
                channel = str(criteria[2].right.value)
                looked_up.append(channel)
                inner = MagicMock()
                available = (
                    (channel == "EMAIL" and has_email_template)
                    or (channel == "WHATSAPP" and has_whatsapp_template)
                )
                if available:
                    tpl = MagicMock()
                    tpl.template_id = uuid.uuid4()
                    tpl.body_template = "corpo"
                    inner.first.return_value = tpl
                else:
                    inner.first.return_value = None
                return inner
            q.filter.side_effect = filter_
        else:
            q.filter.return_value.first.return_value = None
        return q

    mock_db = MagicMock()
    mock_db.query.side_effect = query_side_effect

    with patch.object(communication_service, "_send_whatsapp") as wpp, \
         patch.object(communication_service, "_send_email") as mail:
        entry = communication_service.dispatch(
            event_type=event_type,
            company_id=uuid.uuid4(),
            context=context,
            recipient_id=uuid.uuid4(),
            recipient_type=recipient_type,
            db=mock_db,
        )
    return entry, looked_up, wpp, mail


@pytest.mark.parametrize("event_type,recipient_type", [
    ("user.invitation_sent", "CLIENT"),
    ("auth.password_reset_requested", "CLIENT"),
    ("conversation.escalated", "OWNER"),
])
def test_platform_events_choose_whatsapp(event_type, recipient_type):
    """Os três eventos de plataforma. Com telefone no contexto, saem por WhatsApp
    — e sem consultar o template de e-mail antes."""
    entry, looked_up, wpp, mail = _dispatch_with(
        context={"recipient_phone": "5562988887777", "recipient_email": "a@b.com"},
        event_type=event_type,
        recipient_type=recipient_type,
    )
    assert entry.status == "SENT"
    assert entry.channel == "WHATSAPP"
    assert looked_up == ["WHATSAPP"], f"buscou {looked_up} — WhatsApp deve vir 1º"
    wpp.assert_called_once()
    mail.assert_not_called()


def test_whatsapp_first_still_falls_back_to_email_without_template():
    """A inversão não desliga o fallback: sem template WHATSAPP, o e-mail entrega."""
    entry, looked_up, wpp, mail = _dispatch_with(
        context={"recipient_phone": "5562988887777", "recipient_email": "a@b.com"},
        event_type="user.invitation_sent",
        recipient_type="CLIENT",
        has_whatsapp_template=False,
    )
    assert entry.status == "SENT"
    assert entry.channel == "EMAIL"
    assert looked_up == ["WHATSAPP", "EMAIL"]
    mail.assert_called_once()


# ── 4./6. Degradação dos usuários existentes — sem telefone ───────────────────

def test_user_without_phone_still_gets_the_reset_by_email():
    """⚠️ O teste que protege os tenants existentes.

    Todos os usuários de hoje ficam SEM telefone até o Silva preencher por SQL.
    Se o WhatsApp entrasse na preferência mesmo sem destinatário, o dispatch
    escolheria WHATSAPP, `_send_whatsapp` levantaria por falta de
    `recipient_phone` e o reset viraria FAILED — o fallback do passo 3 cobre
    AUSÊNCIA DE TEMPLATE, nunca falha de envio. Por isso um canal só entra na
    preferência quando há endereço para ele.
    """
    entry, looked_up, wpp, mail = _dispatch_with(
        context={"recipient_phone": None, "recipient_email": "dono@leduc.com"},
        event_type="auth.password_reset_requested",
        recipient_type="CLIENT",
    )
    assert entry.status == "SENT"
    assert entry.channel == "EMAIL"
    assert looked_up == ["EMAIL"], "WhatsApp não pode ser tentado sem telefone"
    wpp.assert_not_called()


def test_dispatch_without_any_recipient_is_explicit():
    """Nem telefone nem e-mail: o log diz o que aconteceu em vez de virar FAILED
    genérico ou se confundir com canal desligado."""
    entry, _, wpp, mail = _dispatch_with(
        context={},
        event_type="auth.password_reset_requested",
        recipient_type="CLIENT",
    )
    assert entry.status == "SKIPPED_NO_RECIPIENT"
    wpp.assert_not_called()
    mail.assert_not_called()


def test_forgot_password_end_to_end_with_phone():
    """O fluxo que o sprint anterior acabou de ligar — não pode quebrar, e agora
    passa a ter destinatário WhatsApp de verdade."""
    from app.modules.auth import service as auth_service

    user = MagicMock()
    user.id = uuid.uuid4()
    user.company_id = uuid.uuid4()
    user.email = "dono@leduc.com"
    user.name = "Dono"
    user.phone = "5562988887777"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    captured: dict = {}

    def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with patch("app.modules.communication.service.communication_service.dispatch",
               side_effect=fake_dispatch):
        auth_service.forgot_password(mock_db, "dono@leduc.com")

    assert captured["event_type"] == "auth.password_reset_requested"
    assert captured["context"]["recipient_phone"] == "5562988887777"
    assert captured["context"]["token"]


# ── 5. conversation.escalated gera log ────────────────────────────────────────

def _run_escalation_handler(owner):
    """Roda o handler real com SessionLocal mockado; devolve os kwargs do dispatch."""
    from app.workers.handlers import conversation_handler

    captured: dict = {}

    def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    mock_db = MagicMock()

    def query_side_effect(model_class):
        q = MagicMock()
        if model_class.__name__ == "User":
            q.filter.return_value.first.return_value = owner
        else:  # Customer
            customer = MagicMock()
            customer.name = "Ana"
            q.filter.return_value.first.return_value = customer
        return q

    mock_db.query.side_effect = query_side_effect

    event = MagicMock()
    event.company_id = uuid.uuid4()
    event.payload = {
        "session_id": str(uuid.uuid4()),
        "phone": "5562988887777",
        "customer_id": str(uuid.uuid4()),
        "trigger": "INTENT",
    }

    with patch.object(conversation_handler, "SessionLocal", return_value=mock_db), \
         patch.object(conversation_handler, "set_rls_context"), \
         patch("app.modules.communication.service.communication_service.dispatch",
               side_effect=fake_dispatch):
        conversation_handler.handle_conversation_escalated(event)

    return captured


def test_escalation_notifies_the_owner_by_whatsapp():
    """O alerta é operacional e em tempo real: o dono precisa saber AGORA que um
    cliente pediu humano. Com telefone no OWNER, sai por WhatsApp."""
    owner = MagicMock()
    owner.id = uuid.uuid4()
    owner.email = "dono@leduc.com"
    owner.phone = "5511977776666"

    captured = _run_escalation_handler(owner)

    assert captured["event_type"] == "conversation.escalated"
    assert captured["recipient_type"] == "OWNER"
    ctx = captured["context"]
    # `recipient_phone` é o do DONO (destino); `phone` é o do CLIENTE (corpo).
    assert ctx["recipient_phone"] == "5511977776666"
    assert ctx["phone"] == "5562988887777"
    assert ctx["customer_name"] == "Ana"


def test_escalation_without_owner_phone_still_reaches_the_owner_by_email():
    """Le Duc e Paladino Labs ficam sem telefone até o backfill do Silva."""
    owner = MagicMock()
    owner.id = uuid.uuid4()
    owner.email = "dono@leduc.com"
    owner.phone = None

    captured = _run_escalation_handler(owner)
    assert captured["context"]["recipient_phone"] == ""
    assert captured["context"]["recipient_email"] == "dono@leduc.com"


def test_escalation_without_owner_no_longer_exits_in_silence():
    """⚠️ Um alerta que sai em silêncio é pior que alerta nenhum — cria a
    impressão de cobertura. O guard `if owner is None: return` permanece (não há
    destinatário, e o CommunicationLog exige recipient_id), mas agora registra."""
    from app.workers.handlers import conversation_handler

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    event = MagicMock()
    event.company_id = uuid.uuid4()
    event.payload = {"session_id": str(uuid.uuid4()), "phone": "556299"}

    with patch.object(conversation_handler, "SessionLocal", return_value=mock_db), \
         patch.object(conversation_handler, "set_rls_context"), \
         patch.object(conversation_handler.logger, "warning") as warn:
        conversation_handler.handle_conversation_escalated(event)

    warn.assert_called_once()


def test_the_menu_path_to_HUMANO_never_publishes_the_event():
    """⚠️ ACHADO DA PARTE 6 — documenta a causa, não um comportamento desejado.

    3 escaladas reais, zero linhas em `communication_logs`. O candidato do
    enunciado (o guard `if owner is None`) NÃO é a causa: o dispatch grava log em
    qualquer desfecho, então zero linhas significa que ele nunca foi chamado.

    A causa está antes. O Sprint 2.7 centralizou a escalada em
    `bot_service._escalate_to_human`, que publica `conversation.escalated` — mas
    só o comando universal ("humano"/"atendente") e a intenção FALAR_COM_HUMANO
    passam por lá. Quem CLICA na opção do menu cai em
    `handlers/menu_principal.py` ou `handlers/inicio.py`, que setam
    `session.state = "HUMANO"` na mão, respondem HUMANO_CHAMADO e retornam:
    sem publicar evento, sem persistir a mensagem no inbox.

    Sessão em HUMANO, dono sem aviso — exatamente a evidência.

    ⚠️ NÃO CORRIGIDO NESTE SPRINT: `whatsapp/` está fora do escopo (a telemetria
    do S-bot-1 está coletando e uma mudança de comportamento do bot perturbaria a
    coleta). A correção é rotear os dois `opt_humano` por `_escalate_to_human`,
    passando trigger="MENU". Este teste quebra quando isso for feito — é o sinal
    de que a Parte 6 fechou.
    """
    import inspect
    from app.modules.whatsapp.handlers import menu_principal, inicio

    for module in (menu_principal, inicio):
        source = inspect.getsource(module)
        assert 'STATE_HUMANO' in source
        assert "_escalate_to_human" not in source, (
            f"{module.__name__} passou a escalar pelo caminho central — "
            "a causa da Parte 6 foi corrigida; remova este teste"
        )


# ── Templates: os três eventos de plataforma, sem emoji ───────────────────────

def _seeded_templates():
    from app.modules.companies.service import _DEFAULT_TEMPLATES
    return _DEFAULT_TEMPLATES


@pytest.mark.parametrize("event_type", [
    "user.invitation_sent",
    "auth.password_reset_requested",
    "conversation.escalated",
])
def test_platform_event_has_a_whatsapp_template(event_type):
    """Sem template WHATSAPP a inversão de canal não entrega nada — o dispatch
    cairia de volta no e-mail para os três eventos."""
    assert any(
        t["event_type"] == event_type and t["channel"] == "WHATSAPP"
        for t in _seeded_templates()
    )


@pytest.mark.parametrize("event_type", [
    "user.invitation_sent",
    "auth.password_reset_requested",
    "conversation.escalated",
])
def test_platform_templates_have_no_emoji(event_type):
    """Decisão do Silva: emoji em mensagem automatizada causa estranheza e marca
    "robô". Estrutura e quebra de linha no lugar."""
    bodies = [
        t["body_template"] for t in _seeded_templates()
        if t["event_type"] == event_type
    ]
    assert bodies
    for body in bodies:
        offenders = [c for c in body if ord(c) > 0x2100]
        assert not offenders, f"emoji em {event_type}: {offenders}"


def test_escalation_template_leads_with_who_and_what():
    """Quem lê está cortando cabelo e olha o celular por três segundos: a
    primeira linha precisa dizer quem e o quê, sem abrir nada."""
    body = next(
        t["body_template"] for t in _seeded_templates()
        if t["event_type"] == "conversation.escalated" and t["channel"] == "WHATSAPP"
    )
    first_line = body.splitlines()[0]
    assert "{{customer_name}}" in first_line
    assert "atendente" in first_line.lower()

"""
`SKIPPED_CONSENT_REVOKED` não existia no enum — o dispatch quebrava ao revogar.

`communication/service.py` gravava esse valor no passo de consent; o enum
`communicationlogstatus` tem `SKIPPED_NO_CONSENT`. Em PostgreSQL o commit
levantava `InvalidTextRepresentation` — ou seja, **o cliente que revogava
consentimento derrubava o envio**, em vez de ser pulado com registro.

⚠️ Nenhum teste pegou isso porque todos usam FakeDB/mocks, que aceitam qualquer
string. O primeiro teste deste arquivo é o guarda que faltava: ele compara o que
o código GRAVA com o que o enum ACEITA, sem precisar de banco.
"""
import re
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── O guarda estrutural ───────────────────────────────────────────────────────

def _enum_values() -> set:
    from app.infrastructure.db.models.communication_log import CommunicationLog

    return set(CommunicationLog.__table__.c.status.type.enums)


def _statuses_written_by_dispatch() -> set:
    """Todos os literais passados a `_log(...)` em communication/service.py."""
    from app.modules.communication import service as comm_service

    source = Path(comm_service.__file__).read_text(encoding="utf-8")
    # _log("STATUS", ...) e _log(\n    "STATUS", ...)
    return set(re.findall(r'_log\(\s*["\']([A-Z_]+)["\']', source))


def test_every_status_the_dispatch_writes_exists_in_the_enum():
    """⚠️ O TESTE QUE FALTAVA.

    Um status fora do enum não é aviso: é `InvalidTextRepresentation` no commit,
    e o caminho inteiro cai. Comparar código × enum não precisa de PostgreSQL.
    """
    written = _statuses_written_by_dispatch()
    assert written, "nenhum literal encontrado — o padrão de `_log` mudou?"

    unknown = written - _enum_values()
    assert not unknown, (
        f"status gravado que o enum communicationlogstatus não aceita: {sorted(unknown)}. "
        "Em PostgreSQL isso derruba o dispatch no commit. Ou use um valor existente, "
        "ou acrescente o valor ao enum por migration (ALTER TYPE ... ADD VALUE)."
    )


def test_the_consent_status_is_the_one_that_exists():
    """Fixa a escolha (a): `SKIPPED_NO_CONSENT`, o valor que já existia."""
    written = _statuses_written_by_dispatch()
    assert "SKIPPED_NO_CONSENT" in written
    assert "SKIPPED_CONSENT_REVOKED" not in written


# ── Comportamento: revogar não quebra, e registra ─────────────────────────────

def _dispatch_with_consent(granted: bool, event_type="appointment.confirmed"):
    """Roda o dispatch real com db mockado e consent controlado."""
    from app.modules.communication.service import communication_service

    cs = MagicMock()
    cs.whatsapp_enabled = True
    cs.email_enabled = False
    cs.quiet_hours_enabled = False
    cs.company_id = uuid.uuid4()

    template = MagicMock()
    template.template_id = uuid.uuid4()
    template.body_template = "corpo"

    def query_side_effect(model_class):
        q = MagicMock()
        name = model_class.__name__
        if name == "CommunicationSetting":
            q.filter.return_value.first.return_value = cs
        elif name == "CommunicationTemplate":
            q.filter.return_value.first.return_value = template
        else:
            q.filter.return_value.first.return_value = None
        return q

    mock_db = MagicMock()
    mock_db.query.side_effect = query_side_effect

    identity_id = uuid.uuid4()

    with patch.object(communication_service, "_resolve_identity_id",
                      return_value=identity_id), \
         patch("app.modules.identity.consent_service.check_consent",
               return_value=granted), \
         patch.object(communication_service, "_send_whatsapp") as send:
        entry = communication_service.dispatch(
            event_type=event_type,
            company_id=uuid.uuid4(),
            context={"recipient_phone": "5562988887777"},
            recipient_id=uuid.uuid4(),
            recipient_type="CLIENT",
            db=mock_db,
        )
    return entry, send


def test_revoked_consent_skips_with_a_valid_status():
    """Caso 1 do DoD: não quebra, e grava o status certo."""
    entry, send = _dispatch_with_consent(granted=False)

    assert entry.status == "SKIPPED_NO_CONSENT"
    assert entry.status in _enum_values(), "status fora do enum → quebraria no commit"
    send.assert_not_called()


def test_granted_consent_still_sends():
    """A correção não pode bloquear quem consentiu."""
    entry, send = _dispatch_with_consent(granted=True)

    assert entry.status == "SENT"
    send.assert_called_once()


def test_marketing_without_identity_blocks_with_the_same_status():
    """O 2º ramo do passo de consent.

    ⚠️ Aqui NADA foi revogado — não há sequer identidade resolvida. O nome antigo
    ("CONSENT_REVOKED") mentia neste caso; "NO_CONSENT" descreve os dois.
    """
    from app.modules.communication.service import communication_service

    cs = MagicMock()
    cs.whatsapp_enabled = True
    cs.email_enabled = False
    cs.quiet_hours_enabled = False
    cs.company_id = uuid.uuid4()

    template = MagicMock()
    template.template_id = uuid.uuid4()
    template.body_template = "corpo"

    def query_side_effect(model_class):
        q = MagicMock()
        if model_class.__name__ == "CommunicationSetting":
            q.filter.return_value.first.return_value = cs
        elif model_class.__name__ == "CommunicationTemplate":
            q.filter.return_value.first.return_value = template
        else:
            q.filter.return_value.first.return_value = None
        return q

    mock_db = MagicMock()
    mock_db.query.side_effect = query_side_effect

    with patch.object(communication_service, "_resolve_identity_id", return_value=None), \
         patch.object(communication_service, "_send_whatsapp") as send:
        entry = communication_service.dispatch(
            event_type="marketing.promo",
            company_id=uuid.uuid4(),
            context={"recipient_phone": "5562988887777"},
            recipient_id=uuid.uuid4(),
            recipient_type="CLIENT",
            db=mock_db,
        )

    assert entry.status == "SKIPPED_NO_CONSENT"
    send.assert_not_called()


# ── Caso 2 do DoD: distinguível na leitura dos logs ───────────────────────────

def test_the_status_is_distinguishable_from_the_other_skips():
    """Não se confunde com canal desligado, quiet hours ou template ausente —
    cada motivo de não-envio tem valor próprio."""
    values = _enum_values()
    for other in ("SKIPPED_CHANNEL_DISABLED", "SKIPPED_QUIET_HOURS",
                  "SKIPPED_NO_TEMPLATE"):
        assert other in values
        assert other != "SKIPPED_NO_CONSENT"


def test_the_panel_already_has_a_label_for_it():
    """O painel de logs rotula `SKIPPED_NO_CONSENT` desde sempre — foi um dos
    motivos de usar o valor existente em vez de criar outro: `SKIPPED_CONSENT_REVOKED`
    apareceria cru na tela, sem tradução."""
    constants = Path(__file__).parents[2] / "painel" / "lib" / "constants.ts"
    if not constants.exists():
        pytest.skip("frontend não disponível neste checkout")
    assert "SKIPPED_NO_CONSENT" in constants.read_text(encoding="utf-8")


# ── O consumidor que estava inalcançável ──────────────────────────────────────

def test_nps_expires_the_survey_on_no_consent():
    """`nps/service.py` já tratava o caso — mas lendo a string errada, e o
    dispatch nem chegava a devolver: o commit levantava antes. O ramo era
    inalcançável por dois motivos ao mesmo tempo."""
    from app.modules.nps import service as nps_service

    source = Path(nps_service.__file__).read_text(encoding="utf-8")
    branch = re.search(r'log\.status == ["\']([A-Z_]+)["\']', source)
    assert branch, "o ramo de consent sumiu do send_pending_surveys"
    assert branch.group(1) == "SKIPPED_NO_CONSENT", (
        "o NPS voltou a ler um status que o dispatch não grava — a pesquisa "
        "ficaria PENDING retentando a cada 15 min para sempre"
    )
    assert branch.group(1) in _enum_values()

"""
Testes de segurança — invalidação de sessão após troca de senha.

Verifica que get_current_user rejeita JWTs emitidos antes de
user.last_password_change_at com HTTP 401.

Estratégia: chamar get_current_user diretamente com mocks de db e credentials,
evitando dependências de banco de dados (SQLite/UUID incompatibilidade).
"""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt as jose_jwt

from app.core.config import settings
from app.core.security import create_access_token
from app.core.deps import get_current_user


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token(user_id: str, role: str = "OWNER", iat: datetime | None = None) -> str:
    """Cria JWT com iat/exp usando create_access_token (iat = now)."""
    return create_access_token({"sub": user_id, "role": role})


def _make_token_with_iat(user_id: str, iat: datetime, role: str = "OWNER") -> str:
    """Cria JWT com iat explícito — simula token emitido em momento específico."""
    expire = iat + timedelta(hours=1)
    return jose_jwt.encode(
        {"sub": user_id, "role": role, "iat": iat.timestamp(), "exp": expire.timestamp()},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _make_token_without_iat(user_id: str, role: str = "OWNER") -> str:
    """Cria JWT sem campo iat — simula token legado."""
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    return jose_jwt.encode(
        {"sub": user_id, "role": role, "exp": expire.timestamp()},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _mock_user(
    user_id: str | None = None,
    active: bool = True,
    last_password_change_at: datetime | None = None,
) -> MagicMock:
    """Retorna um mock de User com os campos necessários para get_current_user."""
    user = MagicMock()
    user.id = uuid.UUID(user_id) if user_id else uuid.uuid4()
    user.active = active
    user.last_password_change_at = last_password_change_at
    return user


def _call_get_current_user(token: str, db_user: MagicMock | None) -> MagicMock:
    """
    Chama get_current_user diretamente injetando mocks de credentials e db.
    Levanta HTTPException se a função levantar.
    """
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = db_user

    # get_current_user é uma função síncrona normal (não async)
    return get_current_user(credentials=credentials, db=mock_db)


# ── Testes ────────────────────────────────────────────────────────────────────

class TestSessionInvalidation:

    def test_sem_token_rejeitado(self):
        """Requisição sem credentials → 401 Não autenticado."""
        with pytest.raises(HTTPException) as exc:
            get_current_user(credentials=None, db=MagicMock())
        assert exc.value.status_code == 401

    def test_token_invalido_rejeitado(self):
        """Token com assinatura inválida → 401."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token.invalido.aqui")
        with pytest.raises(HTTPException) as exc:
            get_current_user(credentials=credentials, db=MagicMock())
        assert exc.value.status_code == 401

    def test_token_valido_sem_troca_de_senha(self):
        """Token válido + last_password_change_at=None → usuário retornado."""
        uid = str(uuid.uuid4())
        user = _mock_user(user_id=uid, last_password_change_at=None)
        token = _make_token(uid)

        result = _call_get_current_user(token, db_user=user)
        assert result is user

    def test_token_emitido_antes_da_troca_rejeitado(self):
        """Token emitido 10 min antes da troca → 401 'Sessão expirada — senha alterada.'"""
        password_changed_at = datetime.now(timezone.utc)
        uid = str(uuid.uuid4())
        user = _mock_user(user_id=uid, last_password_change_at=password_changed_at)

        issued_at = password_changed_at - timedelta(minutes=10)
        token = _make_token_with_iat(uid, iat=issued_at)

        with pytest.raises(HTTPException) as exc:
            _call_get_current_user(token, db_user=user)
        assert exc.value.status_code == 401
        assert "senha alterada" in exc.value.detail.lower()

    def test_token_emitido_apos_troca_aceito(self):
        """Token emitido após a troca de senha → aceito."""
        password_changed_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        uid = str(uuid.uuid4())
        user = _mock_user(user_id=uid, last_password_change_at=password_changed_at)

        # Emitido agora — depois de password_changed_at
        token = _make_token(uid)

        result = _call_get_current_user(token, db_user=user)
        assert result is user

    def test_token_exatamente_no_momento_da_troca_rejeitado(self):
        """Token emitido exatamente na mesma data da troca → rejeitado (strict <)."""
        password_changed_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        uid = str(uuid.uuid4())
        user = _mock_user(user_id=uid, last_password_change_at=password_changed_at)

        # Token emitido 1 segundo ANTES — deve ser rejeitado
        issued_at = password_changed_at - timedelta(seconds=1)
        token = _make_token_with_iat(uid, iat=issued_at)

        with pytest.raises(HTTPException) as exc:
            _call_get_current_user(token, db_user=user)
        assert exc.value.status_code == 401
        assert "senha alterada" in exc.value.detail.lower()

    def test_token_sem_iat_nao_rejeitado(self):
        """Token legado sem campo iat + last_password_change_at definido → aceito (retrocompat)."""
        password_changed_at = datetime.now(timezone.utc)
        uid = str(uuid.uuid4())
        user = _mock_user(user_id=uid, last_password_change_at=password_changed_at)

        token = _make_token_without_iat(uid)

        # Sem iat, não há como comparar — token é aceito (não rejeitado)
        result = _call_get_current_user(token, db_user=user)
        assert result is user

    def test_usuario_nao_encontrado_rejeitado(self):
        """DB retorna None (user inexistente ou inativo) → 401."""
        uid = str(uuid.uuid4())
        token = _make_token(uid)

        with pytest.raises(HTTPException) as exc:
            _call_get_current_user(token, db_user=None)
        assert exc.value.status_code == 401

    def test_troca_invalida_token_anterior_mas_novo_funciona(self):
        """Fluxo completo: token_A antes da troca → rejeitado; token_B depois → aceito."""
        uid = str(uuid.uuid4())
        # password_changed_at no passado para que token_b (emitido "agora") seja
        # claramente posterior, mesmo com resolução de 1 segundo do campo iat.
        password_changed_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        user = _mock_user(user_id=uid, last_password_change_at=password_changed_at)

        # Token A — emitido antes da troca
        token_a = _make_token_with_iat(uid, iat=password_changed_at - timedelta(minutes=30))

        # Token B — emitido após a troca
        token_b = _make_token(uid)

        with pytest.raises(HTTPException) as exc_a:
            _call_get_current_user(token_a, db_user=user)
        assert exc_a.value.status_code == 401
        assert "senha alterada" in exc_a.value.detail.lower()

        result_b = _call_get_current_user(token_b, db_user=user)
        assert result_b is user

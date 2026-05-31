"""Validadores e utilitários PII para CPF/CNPJ.

CPF/CNPJ NUNCA armazenado como plaintext no banco, nos logs ou nas respostas de API.
Decrypt permitido apenas internamente no AsaasProvider ao enviar para a API.

Hierarquia de chaves:
  PII_ENCRYPTION_KEY → Fernet encryption (cpf_cnpj_encrypted)
  PII_HASH_KEY       → HMAC-SHA256 (cpf_cnpj_hash)
  Fallback: CREDENTIAL_ENCRYPTION_KEY se PII_* ausentes.
  Startup falha se nenhuma estiver disponível em produção.
"""
import hashlib
import hmac
import logging
import re

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Resolução de chaves ───────────────────────────────────────────────────────

def _get_pii_encryption_key() -> bytes:
    key = settings.PII_ENCRYPTION_KEY.strip()
    if not key:
        key = settings.CREDENTIAL_ENCRYPTION_KEY.strip()
    if not key:
        raise KeyError(
            "PII_ENCRYPTION_KEY (ou CREDENTIAL_ENCRYPTION_KEY como fallback) "
            "ausente nas variáveis de ambiente. "
            "Gerar com: from cryptography.fernet import Fernet; Fernet.generate_key()"
        )
    return key.encode() if isinstance(key, str) else key


def _get_pii_hash_key() -> bytes:
    key = settings.PII_HASH_KEY.strip()
    if not key:
        key = settings.CREDENTIAL_ENCRYPTION_KEY.strip()
    if not key:
        raise KeyError(
            "PII_HASH_KEY (ou CREDENTIAL_ENCRYPTION_KEY como fallback) "
            "ausente nas variáveis de ambiente."
        )
    return key.encode() if isinstance(key, str) else key


# ── Validação de dígito verificador ──────────────────────────────────────────

def validate_cpf(digits: str) -> bool:
    """Valida CPF via dígito verificador. digits deve ter exatamente 11 chars numéricos."""
    if len(digits) != 11 or not digits.isdigit():
        return False
    if digits == digits[0] * 11:
        return False

    def _check(d, n):
        soma = sum(int(d[i]) * (n - i) for i in range(n - 1))
        resto = (soma * 10) % 11
        return resto if resto < 10 else 0

    return _check(digits, 10) == int(digits[9]) and _check(digits, 11) == int(digits[10])


def validate_cnpj(digits: str) -> bool:
    """Valida CNPJ via dígito verificador. digits deve ter exatamente 14 chars numéricos."""
    if len(digits) != 14 or not digits.isdigit():
        return False
    if digits == digits[0] * 14:
        return False

    def _check(d, weights):
        soma = sum(int(d[i]) * weights[i] for i in range(len(weights)))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return _check(digits, w1) == int(digits[12]) and _check(digits, w2) == int(digits[13])


def normalize_cpf_cnpj(raw: str) -> str:
    """Remove pontuação, valida dígito verificador. Raise ValueError se inválido."""
    digits = re.sub(r"[^\d]", "", raw or "")
    if len(digits) == 11:
        if not validate_cpf(digits):
            raise ValueError(f"CPF inválido (dígito verificador falhou)")
        return digits
    if len(digits) == 14:
        if not validate_cnpj(digits):
            raise ValueError(f"CNPJ inválido (dígito verificador falhou)")
        return digits
    raise ValueError(f"CPF/CNPJ inválido: esperado 11 ou 14 dígitos, recebido {len(digits)}")


# ── Cripto PII ────────────────────────────────────────────────────────────────

def encrypt_pii(value: str) -> str:
    """Criptografa com Fernet(PII_ENCRYPTION_KEY). Retorna ciphertext base64."""
    from cryptography.fernet import Fernet
    f = Fernet(_get_pii_encryption_key())
    return f.encrypt(value.encode()).decode()


def decrypt_pii(ciphertext: str) -> str:
    """Descriptografa PII. Usar APENAS internamente no adapter; nunca retornar via API."""
    from cryptography.fernet import Fernet
    f = Fernet(_get_pii_encryption_key())
    return f.decrypt(ciphertext.encode()).decode()


def hash_pii(value: str) -> str:
    """HMAC-SHA256 para deduplicação sem plaintext. Determinístico para a mesma chave."""
    key = _get_pii_hash_key()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


# ── Mascaramento ──────────────────────────────────────────────────────────────

def mask_cpf(digits: str) -> str:
    """Retorna CPF mascarado: ***.***.***-XX onde XX são os 2 últimos dígitos."""
    return f"***.***.***-{digits[-2:]}"


def mask_cnpj(digits: str) -> str:
    """Retorna CNPJ mascarado: **.***.***/****-XX onde XX são os 2 últimos dígitos."""
    return f"**.***.***/****-{digits[-2:]}"


def mask_cpf_cnpj(digits: str) -> str:
    """Escolhe mask_cpf ou mask_cnpj baseado no tamanho."""
    return mask_cpf(digits) if len(digits) == 11 else mask_cnpj(digits)

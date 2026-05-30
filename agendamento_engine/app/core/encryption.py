"""
Criptografia de credenciais de integração — Sprint 5.

Algoritmo: Fernet (AES-128-CBC + HMAC-SHA256).
Chave:     CREDENTIAL_ENCRYPTION_KEY (32 bytes URL-safe base64).

decrypt_secret() é usado APENAS internamente em test_connection.
Nunca retornar o resultado em resposta de API.
"""
from app.core.config import settings


def _fernet():
    from cryptography.fernet import Fernet
    key = settings.CREDENTIAL_ENCRYPTION_KEY.strip()
    if not key:
        raise KeyError(
            "CREDENTIAL_ENCRYPTION_KEY ausente nas variáveis de ambiente. "
            "Gerar com: from cryptography.fernet import Fernet; Fernet.generate_key()"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def make_masked_preview(plaintext: str) -> str:
    return f"***•••{plaintext[-4:]}"

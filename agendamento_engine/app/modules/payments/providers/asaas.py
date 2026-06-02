"""AsaasProvider — adapter para a API Asaas.

Resolve a API key na seguinte ordem:
  1. IntegrationCredential do tenant (provider=ASAAS) via decrypt_secret
  2. settings.ASAAS_API_KEY (fallback global)

CPF/CNPJ é descriptografado internamente via PII_ENCRYPTION_KEY antes de
enviar para a API Asaas. O valor descriptografado nunca é retornado.
"""
import logging
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import decrypt_secret
from app.modules.payments.providers.base import PaymentProvider
from app.modules.payments.validators import decrypt_pii

logger = logging.getLogger(__name__)


class AsaasError(Exception):
    """Erro retornado pela API Asaas ou por falha de comunicação."""


def _resolve_api_key(company_id: UUID, db: Session) -> str:
    """Busca API key do tenant via IntegrationCredential; fallback para settings.

    Usa savepoint (begin_nested) para isolar falhas de DB: se a query falhar
    por qualquer motivo (coluna ausente, RLS, etc.), apenas o savepoint é
    revertido e a transação pai continua utilizável.
    """
    try:
        from app.infrastructure.db.models.integration_credential import IntegrationCredential
        with db.begin_nested():
            cred = (
                db.query(IntegrationCredential)
                .filter(
                    IntegrationCredential.company_id == company_id,
                    IntegrationCredential.provider == "ASAAS",
                    IntegrationCredential.status == "ACTIVE",
                )
                .first()
            )
        if cred:
            return decrypt_secret(cred.secret_encrypted)
    except Exception as exc:
        logger.warning("asaas_credential_resolve_failed", extra={"company_id": str(company_id), "error": str(exc)})

    if settings.ASAAS_API_KEY:
        return settings.ASAAS_API_KEY

    raise AsaasError("Nenhuma API key Asaas disponível para este tenant")


class AsaasProvider(PaymentProvider):

    def __init__(self, company_id: UUID, db: Session):
        self._api_key = _resolve_api_key(company_id, db)
        self._base_url = settings.ASAAS_API_URL.rstrip("/")

    def _headers(self) -> dict:
        return {
            "access_token": self._api_key,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            resp = httpx.post(url, json=body, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise AsaasError(f"Asaas HTTP {exc.response.status_code}: {exc.response.text}") from exc
        except httpx.RequestError as exc:
            raise AsaasError(f"Asaas connection error: {exc}") from exc

    def _get(self, path: str) -> dict:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            resp = httpx.get(url, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise AsaasError(f"Asaas HTTP {exc.response.status_code}: {exc.response.text}") from exc
        except httpx.RequestError as exc:
            raise AsaasError(f"Asaas connection error: {exc}") from exc

    def create_subaccount(self, name: str, cpf_cnpj: str, email: str) -> dict:
        """
        Cria subconta Asaas.

        cpf_cnpj deve ser o valor descriptografado (digits only).
        Este método recebe o plaintext internamente; nunca o expõe para fora.
        """
        payload = {
            "name": name,
            "email": email,
            "cpfCnpj": cpf_cnpj,
            "companyType": "MEI",
        }
        data = self._post("/accounts", payload)
        return {
            "accountId": data.get("id", data.get("accountId", "")),
            "status": data.get("accountStatus", "pending_verification"),
        }

    def _put(self, path: str, body: dict) -> dict:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            resp = httpx.put(url, json=body, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise AsaasError(f"Asaas HTTP {exc.response.status_code}: {exc.response.text}") from exc
        except httpx.RequestError as exc:
            raise AsaasError(f"Asaas connection error: {exc}") from exc

    def ensure_customer(
        self, name: str, email: str | None, external_reference: str,
        cpf_cnpj: str | None = None,
    ) -> str:
        """Cria customer no Asaas e retorna o ID (cus_...).

        Usa externalReference (UUID interno) para rastreabilidade.
        cpf_cnpj: apenas dígitos — obrigatório para PIX/BOLETO.
        """
        payload: dict = {"name": name, "externalReference": external_reference}
        if email:
            payload["email"] = email
        if cpf_cnpj:
            payload["cpfCnpj"] = cpf_cnpj
        data = self._post("/customers", payload)
        return data["id"]

    def update_customer(self, asaas_id: str, cpf_cnpj: str) -> None:
        """Atualiza CPF/CNPJ de um customer Asaas já existente."""
        self._put(f"/customers/{asaas_id}", {"cpfCnpj": cpf_cnpj})

    def create_charge(self, amount, customer: dict, payment_method: str, **kwargs) -> dict:
        payload = {
            "customer": customer.get("external_id", customer.get("id")),
            "billingType": payment_method,
            "value": float(amount),
            **{k: v for k, v in kwargs.items()},
        }
        data = self._post("/payments", payload)
        return data

    def handle_webhook(self, payload: dict) -> dict:
        event = payload.get("event", "")
        return {
            "event": event,
            "external_id": payload.get("payment", {}).get("id") or payload.get("account", {}).get("id"),
            "status": payload.get("payment", {}).get("status") or payload.get("account", {}).get("status"),
            "raw": payload,
        }

    def refund(self, external_charge_id: str, reason: str) -> dict:
        data = self._post(f"/payments/{external_charge_id}/refund", {"description": reason})
        return data

    def get_status(self, external_charge_id: str) -> str:
        data = self._get(f"/payments/{external_charge_id}")
        return data.get("status", "UNKNOWN")

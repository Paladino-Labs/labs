"""NullProvider — provider para testes unitários e dev.

Implementa todos os métodos de PaymentProvider sem chamar serviços externos.
Funciona como spy: registra cada chamada em self.calls.

outcome="success" (padrão) → operações bem-sucedidas.
outcome="error"           → levanta AsaasError em create_subaccount.

refund(): a env var NULLPROVIDER_REFUND_OUTCOME=success|error (default: success)
sobrepõe o outcome do construtor — permite simular falha de gateway no estorno
sem alterar código.
"""
import os
from uuid import uuid4

from app.modules.payments.providers.base import PaymentProvider
from app.modules.payments.providers.asaas import AsaasError


class NullProvider(PaymentProvider):

    def __init__(self, outcome: str = "success"):
        self.outcome = outcome
        self.calls: list[dict] = []

    def create_subaccount(self, name: str, cpf_cnpj: str, email: str) -> dict:
        self.calls.append({
            "method": "create_subaccount",
            "args": {"name": name, "cpf_cnpj": "[REDACTED]", "email": email},
        })
        if self.outcome == "error":
            raise AsaasError("null_provider_error")
        return {
            "accountId": f"null_{uuid4().hex[:8]}",
            "status": "pending_verification",
        }

    def create_charge(self, amount, customer: dict, payment_method: str, **kwargs) -> dict:
        self.calls.append({
            "method": "create_charge",
            "args": {"amount": amount, "payment_method": payment_method},
        })
        if self.outcome == "error":
            raise AsaasError("null_provider_error")
        return {
            "id": f"null_charge_{uuid4().hex[:8]}",
            "status": "PENDING",
            "value": float(amount),
        }

    def handle_webhook(self, payload: dict) -> dict:
        self.calls.append({"method": "handle_webhook", "args": {}})
        return {
            "event": payload.get("event", ""),
            "external_id": payload.get("id", f"null_{uuid4().hex[:8]}"),
            "status": payload.get("status", "CONFIRMED"),
            "raw": payload,
        }

    def refund(self, external_charge_id: str, reason: str) -> dict:
        self.calls.append({
            "method": "refund",
            "args": {"external_charge_id": external_charge_id},
        })
        outcome = os.getenv("NULLPROVIDER_REFUND_OUTCOME", self.outcome)
        if outcome == "error":
            raise AsaasError("null_provider_error")
        return {"id": external_charge_id, "status": "REFUNDED"}

    def get_status(self, external_charge_id: str) -> str:
        self.calls.append({
            "method": "get_status",
            "args": {"external_charge_id": external_charge_id},
        })
        return "CONFIRMED" if self.outcome == "success" else "FAILED"

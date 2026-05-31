"""PaymentProvider — interface abstrata para adapters de pagamento."""
from abc import ABC, abstractmethod


class PaymentProvider(ABC):

    @abstractmethod
    def create_subaccount(self, name: str, cpf_cnpj: str, email: str) -> dict:
        """Cria subconta no provider. Retorna dict com 'accountId' e 'status'."""

    @abstractmethod
    def create_charge(self, amount, customer: dict, payment_method: str, **kwargs) -> dict:
        """Cria cobrança. Retorna dict com 'id' e campos do provider."""

    @abstractmethod
    def handle_webhook(self, payload: dict) -> dict:
        """Interpreta payload de webhook. Retorna dict normalizado."""

    @abstractmethod
    def refund(self, external_charge_id: str, reason: str) -> dict:
        """Estorna cobrança. Retorna dict com status do estorno."""

    @abstractmethod
    def get_status(self, external_charge_id: str) -> str:
        """Retorna status atual da cobrança no provider."""

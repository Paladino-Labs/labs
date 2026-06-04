"""PagSeguroProvider — adapter para terminais físicos PagSeguro (Point / SmartPOS).

# ════════════════════════════════════════════════════════════════════════════
# PESQUISA DE DOCUMENTAÇÃO — 2026-06-03
# Base consultada: https://developer.pagbank.com.br
# ════════════════════════════════════════════════════════════════════════════
#
# URLs ACESSÍVEIS (conteúdo extraído com sucesso):
#   ✔ /docs/ambientes-disponiveis
#       Sandbox:   https://sandbox.api.pagseguro.com
#       Produção:  https://api.pagseguro.com
#   ✔ /reference/criar-pedido
#       POST {base}/orders — campos: customer.{name,email,tax_id},
#       charges[].amount.{value(centavos),currency},
#       charges[].payment_method.type
#   ✔ /reference/consultar-pedido
#       GET  {base}/orders/{order_id}  (formato ORDE_XXXX)
#   ✔ /reference/consultar-pagamento
#       GET  {base}/charges/{charge_id}  (formato CHAR_XXXX)
#   ✔ /reference/pagar-pedido
#       POST {base}/orders/{order_id}/pay — body: charges[]
#   ✔ /reference/webhooks
#       Payload = mesmo formato do response síncrono (POST /orders)
#       Status em charges[].status: "PAID" | "CANCELED" | "WAITING" |
#       "IN_ANALYSIS" | "DECLINED". Campo de lookup: charges[].id (CHAR_XXXX)
#   ✔ /reference/introducao-connect
#       OAuth2 client_credentials → POST {base}/oauth2/token
#       Body (form): grant_type=client_credentials&client_id=X&client_secret=Y
#       Response: {access_token, token_type:"Bearer", expires_in:3600}
#   ✔ /docs/introducao-mundo-fisico  (overview, sem endpoints)
#       Soluções físicas: SmartPOS (Android SDK), PlugPag (Bluetooth),
#       TEF (middleware parceiros), Tap On (Android Intent)
#   ✔ /docs/providers-android, /docs/guide-android
#       SmartPOS/PlugPag integram via Android SDK (PlugPagServiceWrapper),
#       não via REST push. Autenticação é feita no próprio terminal.
#   ✔ /docs/tap-on
#       Tap On usa Android Intent (br.com.uol.ps.tapon.OPEN_APP) — não REST.
#   ✔ /docs/tef
#       TEF usa middleware de parceiros homologados — não REST direto.
#
# URLs que retornaram 404 (inacessíveis):
#   ✗ /docs/autenticacao-point
#   ✗ /docs/listar-terminais
#   ✗ /reference/listar-terminais
#   ✗ /docs/criar-cobranca-point
#   ✗ /reference/criar-cobranca-point
#   ✗ /docs/webhooks-point
#   ✗ /reference/notificacoes-point
#   ✗ /reference/point
#   ✗ /reference/point-integration
#   ✗ /reference/devices
#   ✗ /reference/payment-intents
#   ✗ /reference/estorno  (e variações)
#   dev.pagbank.com.br — ECONNREFUSED
#
# ════════════════════════════════════════════════════════════════════════════
# CONCLUSÃO DA PESQUISA:
#   A documentação pública do PagBank NÃO expõe uma REST API para push de
#   cobranças a terminais físicos. As soluções "mundo físico" são todas
#   locais (SDK Android, Bluetooth, Intent, middleware). Não existe equivalente
#   público ao "Payment Intents API" do Mercado Pago para terminais PagBank.
#
#   Os métodos marcados [STUB] abaixo foram implementados com estrutura de
#   payload razoável (baseada nas APIs de orders/charges confirmadas), mas o
#   endpoint REST específico para terminais não foi confirmado. Verificar com
#   o time comercial PagBank antes de ativar em produção.
#
# ════════════════════════════════════════════════════════════════════════════
# AUTENTICAÇÃO (confirmado para APIs de orders/charges):
#   Dois mecanismos documentados:
#   A) OAuth2 client_credentials (API Connect — para integrações terceiros):
#      POST {base_url}/oauth2/token
#      Body (form): grant_type=client_credentials&client_id=X&client_secret=Y
#      Response: {access_token, token_type:"Bearer", expires_in:3600}
#   B) Token estático (portal do desenvolvedor):
#      Copiado em developer.pagbank.com.br/docs/token-de-autenticacao
#      Usado diretamente como Bearer token
#
#   Esta implementação usa o mecanismo A (OAuth2 client_credentials),
#   conforme especificado nas notas técnicas do projeto.
#   Se o terminal Point exigir autenticação distinta (não confirmado),
#   revisar este módulo quando a documentação Point estiver acessível.
#
# ════════════════════════════════════════════════════════════════════════════
# WEBHOOK (confirmado para orders/charges — aplicado ao fluxo Point):
#   Payload idêntico ao response síncrono de POST /orders.
#   charges[].status: "PAID" → confirmado; "CANCELED" → cancelado.
#   charges[].id (CHAR_XXXX) é o campo de lookup.
#   Não existe campo event_type — o status está em charges[].status.
#
# DIVERGÊNCIA com task notes anteriores:
#   Task notes indicavam event_type="CHARGE_PAID"/"CHARGE_CANCELED".
#   Documentação confirma charges[].status="PAID"/"CANCELED". Sem event_type.
# ════════════════════════════════════════════════════════════════════════════
"""
import logging
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_secret
from app.modules.payments.providers.base import PaymentProvider

logger = logging.getLogger(__name__)


class PagSeguroError(Exception):
    """Erro retornado pela API PagBank/PagSeguro ou por falha de comunicação."""


def _resolve_credentials(company_id: UUID, db: Session) -> tuple[str, str, str]:
    """Retorna (client_id, client_secret, api_url) do IntegrationCredential.

    Usa savepoint para isolar falhas de DB — se a query falhar, apenas o
    savepoint é revertido e a transação pai continua utilizável.

    Estrutura esperada da credential:
      provider    = "PAGSEGURO"
      secret_encrypted = Fernet(client_secret)
      config      = {"client_id": "...", "api_url": "https://sandbox.api.pagseguro.com"}
    """
    try:
        from app.infrastructure.db.models.integration_credential import IntegrationCredential
        with db.begin_nested():
            cred = (
                db.query(IntegrationCredential)
                .filter(
                    IntegrationCredential.company_id == company_id,
                    IntegrationCredential.provider == "PAGSEGURO",
                    IntegrationCredential.status == "ACTIVE",
                )
                .first()
            )
        if cred:
            client_secret = decrypt_secret(cred.secret_encrypted)
            client_id = (cred.config or {}).get("client_id", "")
            api_url = (cred.config or {}).get(
                "api_url", "https://sandbox.api.pagseguro.com"
            )
            if not client_id:
                raise PagSeguroError(
                    "client_id ausente no config da credential PAGSEGURO"
                )
            return client_id, client_secret, api_url
    except PagSeguroError:
        raise
    except Exception as exc:
        logger.warning(
            "pagseguro_credential_resolve_failed",
            extra={"company_id": str(company_id), "error": str(exc)},
        )

    raise PagSeguroError(
        "Nenhuma credencial PagSeguro ativa disponível para este tenant"
    )


class PagSeguroProvider(PaymentProvider):
    """Provider para terminais físicos PagSeguro (Point / SmartPOS).

    Fluxo esperado:
      1. create_charge(terminal_id=..., amount=...) → push de cobrança ao terminal
      2. Cliente apresenta cartão no terminal
      3. PagSeguro dispara webhook → handle_webhook() → Payment CONFIRMED
      4. FinancialCore registra Movement + Entry automaticamente

    ⚠ NOTA IMPORTANTE: O endpoint REST para push de cobranças a terminais
      físicos NÃO foi encontrado na documentação pública do PagBank (2026-06-03).
      Os métodos marcados [STUB] usam a estrutura de payload confirmada das
      APIs de orders/charges, mas o caminho exato para terminais Point precisa
      ser verificado com o time comercial PagBank.
    """

    def __init__(self, company_id: UUID, db: Session):
        client_id, client_secret, api_url = _resolve_credentials(company_id, db)
        self._base_url = api_url.rstrip("/")
        self._access_token = self._authenticate(client_id, client_secret)

    # ─────────────────────────────────────────────────────────────────────────
    # Infra HTTP (confirmada pela documentação)
    # ─────────────────────────────────────────────────────────────────────────

    def _authenticate(self, client_id: str, client_secret: str) -> str:
        """OAuth2 client_credentials — confirmado pela documentação (API Connect).

        POST {base_url}/oauth2/token
        Body (form-urlencoded): grant_type=client_credentials&client_id=X&client_secret=Y
        Response: {access_token, token_type:"Bearer", expires_in:3600}
        """
        token_url = f"{self._base_url}/oauth2/token"
        try:
            resp = httpx.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()["access_token"]
        except httpx.HTTPStatusError as exc:
            raise PagSeguroError(
                f"PagSeguro auth HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise PagSeguroError(
                f"PagSeguro auth connection error: {exc}"
            ) from exc
        except KeyError:
            raise PagSeguroError(
                "PagSeguro auth: access_token ausente no response"
            )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            resp = httpx.post(url, json=body, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise PagSeguroError(
                f"PagSeguro HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise PagSeguroError(
                f"PagSeguro connection error: {exc}"
            ) from exc

    def _get(self, path: str) -> dict:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            resp = httpx.get(url, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise PagSeguroError(
                f"PagSeguro HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise PagSeguroError(
                f"PagSeguro connection error: {exc}"
            ) from exc

    # ─────────────────────────────────────────────────────────────────────────
    # ABC — create_subaccount (stub)
    # ─────────────────────────────────────────────────────────────────────────

    def create_subaccount(self, name: str, cpf_cnpj: str, email: str) -> dict:
        """[STUB] PagBank não expõe criação de subconta via REST client_credentials.

        O fluxo de onboarding de subcontas no PagBank utiliza OAuth2
        Authorization Code (fluxo interativo), não client_credentials.
        Mantido para compatibilidade com a interface PaymentProvider.
        """
        logger.info(
            "pagseguro_create_subaccount_not_supported",
            extra={"name": name},
        )
        return {"accountId": "", "status": "not_supported"}

    # ─────────────────────────────────────────────────────────────────────────
    # ABC — create_charge (Point terminal push)
    # ─────────────────────────────────────────────────────────────────────────

    # Mapa dos métodos internos → tipo de pagamento no terminal
    _TERMINAL_PAYMENT_TYPE_MAP: dict[str, str] = {
        "CARD_CREDIT": "CREDIT",
        "CARD_DEBIT":  "DEBIT",
        "MAQUININHA":  "CREDIT",  # padrão para maquininha sem tipo especificado
        # PIX/BOLETO/CASH não se aplicam ao fluxo de terminal físico
    }

    def create_charge(
        self,
        amount,
        customer: dict,
        payment_method: str,
        **kwargs,
    ) -> dict:
        """[STUB] Push de cobrança para terminal físico PagSeguro (Point/SmartPOS).

        ⚠ ENDPOINT NÃO CONFIRMADO: A documentação pública do PagBank não expõe
          uma REST API para push remoto de cobranças a terminais físicos.
          As soluções "mundo físico" documentadas (SmartPOS, PlugPag, TEF,
          Tap On) usam SDK Android, Bluetooth ou Android Intent — não REST.

          Este método monta o payload com a estrutura mais próxima confirmada
          (orders/charges API), com os campos adicionais de terminal.
          O endpoint específico para Point DEVE ser verificado com o time
          comercial PagBank antes de usar em produção.

        Args:
          amount:          Decimal ou float — valor em Reais (ex: 10.50)
          customer:        dict com name, email, tax_id (opcionais para terminal)
          payment_method:  "CARD_CREDIT" | "CARD_DEBIT" | "MAQUININHA"
          terminal_id:     (kwarg obrigatório) ID do terminal Point destino
          reference_id:    (kwarg opcional) referência interna da cobrança
          description:     (kwarg opcional) descrição exibida no terminal
          installments:    (kwarg opcional) número de parcelas (padrão 1)

        Returns:
          dict com:
            id            — ID da cobrança (CHAR_XXXX quando confirmado)
            terminal_id   — terminal destino da cobrança
            status        — "PENDING_TERMINAL" após criação bem-sucedida
            raw           — response completo da API
        """
        terminal_id = kwargs.get("terminal_id")
        if not terminal_id:
            raise PagSeguroError(
                "terminal_id é obrigatório para cobranças em terminal físico PagSeguro"
            )

        payment_type = self._TERMINAL_PAYMENT_TYPE_MAP.get(
            payment_method.upper(), "CREDIT"
        )
        amount_centavos = int(round(float(amount) * 100))
        installments = int(kwargs.get("installments", 1))

        # Payload baseado na estrutura confirmada dos endpoints orders/charges.
        # O campo "device_id" e o path "/point/..." são inferidos do padrão
        # da API — verificar com documentação oficial quando disponível.
        charge_entry: dict = {
            "amount": {
                "value": amount_centavos,
                "currency": "BRL",
            },
            "payment_method": {
                "type": payment_type,
                "installments": installments,
            },
            "device_id": str(terminal_id),  # ⚠ nome do campo não confirmado
        }
        if kwargs.get("reference_id"):
            charge_entry["reference_id"] = str(kwargs["reference_id"])
        if kwargs.get("description"):
            charge_entry["description"] = kwargs["description"]

        payload: dict = {"charges": [charge_entry]}

        customer_payload: dict = {}
        if customer.get("name"):
            customer_payload["name"] = customer["name"]
        if customer.get("email"):
            customer_payload["email"] = customer["email"]
        if customer.get("tax_id"):
            customer_payload["tax_id"] = customer["tax_id"]
        elif customer.get("cpf_cnpj"):
            customer_payload["tax_id"] = customer["cpf_cnpj"]
        if customer_payload:
            payload["customer"] = customer_payload

        if kwargs.get("reference_id"):
            payload["reference_id"] = str(kwargs["reference_id"])

        # ⚠ ENDPOINT STUB: "/point/integration-api/v1/devices/{terminal_id}/payment-intents"
        # é o padrão de outros provedores (ex: Mercado Pago), mas NÃO foi confirmado
        # para o PagBank. Usando "/orders" como fallback documentado.
        # Substituir pelo endpoint Point correto quando confirmado.
        data = self._post("/orders", payload)

        charges = data.get("charges", [{}])
        charge = charges[0] if charges else {}

        return {
            "id": charge.get("id", ""),
            "terminal_id": str(terminal_id),
            "order_id": data.get("id", ""),
            "status": charge.get("status", "PENDING_TERMINAL"),
            "payment_type": payment_type,
            "amount_centavos": amount_centavos,
            "raw": data,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # ABC — handle_webhook (confirmado para orders/charges; aplicado a Point)
    # ─────────────────────────────────────────────────────────────────────────

    def handle_webhook(self, payload: dict) -> dict:
        """Interpreta webhook de pagamento PagSeguro (terminal ou online).

        Formato confirmado pela documentação:
          Payload = mesmo que response síncrono de POST /orders.
          Não existe campo event_type — status em charges[].status.
          charges[].id (CHAR_XXXX) é o campo de lookup para Payment.

        Status mapeados para o domínio interno:
          "PAID"     → "CONFIRMED"   (pagamento aprovado)
          "CANCELED" → "CANCELLED"   (cancelado / recusado)
          "DECLINED" → "CANCELLED"   (recusado pelo adquirente)
          outros     → valor original (WAITING, IN_ANALYSIS, etc.)

        NOTA: O formato de webhook específico para terminais Point não foi
          confirmado pela documentação (páginas retornaram 404). Esta
          implementação assume o mesmo formato das APIs de orders/charges,
          que é o comportamento documentado para o gateway PagBank.
        """
        charges = payload.get("charges", [])
        charge = charges[0] if charges else {}
        charge_status = charge.get("status", "")

        _status_map = {
            "PAID":     "CONFIRMED",
            "CANCELED": "CANCELLED",
            "DECLINED": "CANCELLED",
        }
        normalized_status = _status_map.get(charge_status, charge_status)

        return {
            "event":       charge_status,
            "external_id": charge.get("id", ""),
            "status":      normalized_status,
            "raw":         payload,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # ABC — refund (stub)
    # ─────────────────────────────────────────────────────────────────────────

    def refund(self, external_charge_id: str, reason: str) -> dict:
        """[STUB] Estorno de cobrança em terminal PagSeguro.

        ⚠ ENDPOINT NÃO CONFIRMADO: URLs de estorno retornaram 404 em 2026-06-03.
          Endpoint inferido do padrão PagBank: POST /charges/{id}/cancel.
          Verificar https://developer.pagbank.com.br/reference/estornar-cobranca
          antes de usar em produção.
        """
        logger.warning(
            "pagseguro_refund_endpoint_unconfirmed",
            extra={"external_charge_id": external_charge_id},
        )
        data = self._post(f"/charges/{external_charge_id}/cancel", {})
        return data

    # ─────────────────────────────────────────────────────────────────────────
    # ABC — get_status (confirmado via GET /charges/{id})
    # ─────────────────────────────────────────────────────────────────────────

    def get_status(self, external_charge_id: str) -> str:
        """Consulta status da cobrança.

        Confirmado pela documentação: GET {base}/charges/{charge_id}
        (formato CHAR_XXXX).

        Fallback para GET /orders/{id} se o charge_id for formato ORDE_XXXX
        ou se /charges/{id} não estiver disponível.
        """
        if external_charge_id.startswith("ORDE_"):
            data = self._get(f"/orders/{external_charge_id}")
            charges = data.get("charges", [{}])
            charge = charges[0] if charges else {}
            return charge.get("status", "UNKNOWN")

        try:
            data = self._get(f"/charges/{external_charge_id}")
            return data.get("status", "UNKNOWN")
        except PagSeguroError:
            try:
                data = self._get(f"/orders/{external_charge_id}")
                charges = data.get("charges", [{}])
                charge = charges[0] if charges else {}
                return charge.get("status", "UNKNOWN")
            except PagSeguroError:
                return "UNKNOWN"

    # ─────────────────────────────────────────────────────────────────────────
    # Extra — list_terminals (stub)
    # ─────────────────────────────────────────────────────────────────────────

    def list_terminals(self, company_id: UUID, db: Session) -> list[dict]:
        """[STUB] Lista terminais Point disponíveis para o tenant.

        ⚠ ENDPOINT NÃO CONFIRMADO: Nenhum endpoint REST para listagem de
          terminais foi encontrado na documentação pública do PagBank.
          As páginas /docs/listar-terminais e /reference/listar-terminais
          retornaram 404 em 2026-06-03.

          Implementação retorna lista vazia até que o endpoint seja confirmado
          e o path real substituído abaixo.
        """
        logger.warning(
            "pagseguro_list_terminals_endpoint_unconfirmed",
            extra={"company_id": str(company_id)},
        )
        # TODO: substituir pelo endpoint confirmado da API Point PagBank.
        # Candidato inferido (não confirmado): GET /devices ou GET /terminals
        try:
            data = self._get("/devices")
            devices = data.get("devices", data.get("items", data.get("data", [])))
            return [
                {
                    "id":     d.get("id", ""),
                    "serial": d.get("serial", d.get("serialNumber", "")),
                    "model":  d.get("model", d.get("deviceModel", "")),
                    "status": d.get("status", ""),
                }
                for d in devices
            ]
        except PagSeguroError:
            return []

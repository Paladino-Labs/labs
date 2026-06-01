# Integrações — Paladino

## Asaas (Pagamentos)

### Visão geral
Asaas é a plataforma de pagamentos integrada ao Paladino.
Cada tenant tem uma subconta Asaas criada automaticamente no onboarding.

### Credencial
Armazenada em `IntegrationCredential` com `provider=ASAAS`.
API key decriptada via Fernet(CREDENTIAL_ENCRYPTION_KEY) quando necessário.
Fallback: `settings.ASAAS_API_KEY` (global da plataforma) se tenant sem credencial.

### Subconta
- Criada em `create_company` (hook não-bloqueante)
- Status inicial: `pending_verification`
- Webhook `POST /payments/webhook/asaas/account_status` → atualiza status
- Status após verificação Asaas: `active`
- Status banner: `/dashboard/settings/financial`

### Webhooks
| Endpoint | Evento Asaas | Ação |
|----------|-------------|------|
| `POST /payments/webhook/asaas/account_status` | Ativação de subconta | Atualiza `company.external_account_status` |
| `POST /payments/webhook/asaas/transaction` | Confirmação de pagamento | `PaymentsEngine.confirm()` (idempotente) |

### CPF/CNPJ
O Asaas exige CPF ou CNPJ para criação de subcontas e pagamentos.
O valor descriptografado (`cpf_cnpj_encrypted`) é passado para o
`AsaasProvider` internamente — nunca exposto para fora do adaptador.

---

## Evolution API (WhatsApp)

### Status
Infraestrutura implementada. Ativação aguarda configuração de instância.

### Como ativar
1. Configurar instância da Evolution API (self-hosted ou cloud)
2. Adicionar credencial em `/dashboard/integrations`:
   - Provider: `WHATSAPP_EVOLUTION`
   - API key da instância
3. Sistema conecta e exibe QR code para vinculação do número

### Credencial
`IntegrationCredential` com `provider=WHATSAPP_EVOLUTION`.
URL e API key configuradas nas variáveis de ambiente:
`EVOLUTION_API_URL`, `EVOLUTION_API_KEY`.

### Webhook
`POST /whatsapp/webhook` — recebe mensagens e eventos do WhatsApp.
Processa via FSM do BotSession.

---

## SMTP (E-mail)

### Configuração
`IntegrationCredential` com `provider=SMTP`.
Parâmetros em `config JSONB`: host, port, use_tls, username.
Senha em `secret_encrypted`.

### Uso
`CommunicationService` usa a credencial SMTP do tenant para envios
transacionais (reset de senha, confirmações, lembretes).

---

## Supabase Storage

### Uso
Upload de imagens (logo, galeria, avatar de profissional).

### Configuração
`SUPABASE_URL` e `SUPABASE_SERVICE_KEY` nas variáveis de ambiente.

### Fluxo
```
POST /uploads/ { file: multipart }
  → Upload para Supabase Storage
  → Retorna URL pública permanente
  → Frontend armazena a URL (não o arquivo)
```
/**
 * Constantes de domínio compartilhadas.
 * Importe nestes arquivos em vez de redefinir localmente.
 */

export const ROLE_LABELS: Record<string, string> = {
  OWNER:        "Proprietário",
  ADMIN:        "Administrador",
  OPERATOR:     "Operador",
  PROFESSIONAL: "Profissional",
  CLIENT:       "Cliente",
}

export const PAYMENT_METHOD_LABELS: Record<string, string> = {
  // Métodos/submethods canônicos (chaves MAQUININHA_* = MAQUININHA + payment_submethod)
  CASH:                          "Dinheiro",
  CHAVE_PIX:                     "Chave Pix",
  MAQUININHA:                    "Maquininha",
  MAQUININHA_PIX:                "Pix QrCode",
  MAQUININHA_CREDIT_VISA_MASTER: "Crédito Visa/Master",
  MAQUININHA_CREDIT_ELO:         "Crédito Elo",
  MAQUININHA_CREDIT_HIPER_AMEX:  "Crédito Hiper/Amex",
  MAQUININHA_CREDIT_OUTROS:      "Crédito Outros",
  MAQUININHA_DEBIT_VISA_MASTER:  "Débito Visa/Master",
  MAQUININHA_DEBIT_ELO:          "Débito Elo",
  MAQUININHA_DEBIT_OUTROS:       "Débito Outros",
  // Legados — pagamentos históricos e cobranças online (Asaas)
  PIX:               "PIX",
  MAQUININHA_CREDIT: "Maquininha (Crédito)",
  MAQUININHA_DEBIT:  "Maquininha (Débito)",
  BOLETO:            "Boleto",
  CARD_CREDIT:       "Cartão de Crédito",
  CARD_DEBIT:        "Cartão de Débito",
}

// 10 fee_sources canônicos das fee policies (taxa Asaas vem via webhook,
// por isso PIX/BOLETO/CARD_* não existem mais aqui)
export const FEE_SOURCE_LABELS: Record<string, string> = {
  CASH:                          "Dinheiro",
  CHAVE_PIX:                     "Chave Pix",
  MAQUININHA_PIX:                "Pix QrCode",
  MAQUININHA_CREDIT_VISA_MASTER: "Crédito Visa/Master",
  MAQUININHA_CREDIT_ELO:         "Crédito Elo",
  MAQUININHA_CREDIT_HIPER_AMEX:  "Crédito Hiper/Amex",
  MAQUININHA_CREDIT_OUTROS:      "Crédito Outros",
  MAQUININHA_DEBIT_VISA_MASTER:  "Débito Visa/Master",
  MAQUININHA_DEBIT_ELO:          "Débito Elo",
  MAQUININHA_DEBIT_OUTROS:       "Débito Outros",
}

export type PaymentMethodGroup = "Dinheiro / Pix" | "Crédito" | "Débito"

export const PAYMENT_METHOD_GROUPS: PaymentMethodGroup[] = ["Dinheiro / Pix", "Crédito", "Débito"]

export interface PaymentMethodOption {
  key: string
  /** Label completo do glossário (confirmações, tooltips) */
  label: string
  /** Label curto para cards compactos */
  shortLabel: string
  group: PaymentMethodGroup
  payment_method: string
  payment_submethod: string | null
}

export const PAYMENT_METHOD_OPTIONS: PaymentMethodOption[] = [
  { key: "CASH",                          label: "Dinheiro",            shortLabel: "Dinheiro",   group: "Dinheiro / Pix", payment_method: "CASH",       payment_submethod: null },
  { key: "CHAVE_PIX",                     label: "Chave Pix",           shortLabel: "Chave Pix",  group: "Dinheiro / Pix", payment_method: "CHAVE_PIX",  payment_submethod: null },
  { key: "MAQUININHA_PIX",                label: "Pix QrCode",          shortLabel: "Pix QrCode", group: "Dinheiro / Pix", payment_method: "MAQUININHA", payment_submethod: "PIX" },
  { key: "MAQUININHA_CREDIT_VISA_MASTER", label: "Crédito Visa/Master", shortLabel: "Visa/Mst",   group: "Crédito",        payment_method: "MAQUININHA", payment_submethod: "CREDIT_VISA_MASTER" },
  { key: "MAQUININHA_CREDIT_ELO",         label: "Crédito Elo",         shortLabel: "Elo",        group: "Crédito",        payment_method: "MAQUININHA", payment_submethod: "CREDIT_ELO" },
  { key: "MAQUININHA_CREDIT_HIPER_AMEX",  label: "Crédito Hiper/Amex",  shortLabel: "Hiper/Amx",  group: "Crédito",        payment_method: "MAQUININHA", payment_submethod: "CREDIT_HIPER_AMEX" },
  { key: "MAQUININHA_CREDIT_OUTROS",      label: "Crédito Outros",      shortLabel: "Outros",     group: "Crédito",        payment_method: "MAQUININHA", payment_submethod: "CREDIT_OUTROS" },
  { key: "MAQUININHA_DEBIT_VISA_MASTER",  label: "Débito Visa/Master",  shortLabel: "Visa/Mst",   group: "Débito",         payment_method: "MAQUININHA", payment_submethod: "DEBIT_VISA_MASTER" },
  { key: "MAQUININHA_DEBIT_ELO",          label: "Débito Elo",          shortLabel: "Elo",        group: "Débito",         payment_method: "MAQUININHA", payment_submethod: "DEBIT_ELO" },
  { key: "MAQUININHA_DEBIT_OUTROS",       label: "Débito Outros",       shortLabel: "Outros",     group: "Débito",         payment_method: "MAQUININHA", payment_submethod: "DEBIT_OUTROS" },
]

/* ============================ Fase 2 — Comercial ============================ */

// Status de cota (CustomerCredit) — usado na ficha do cliente e em compras de pacote
export const CUSTOMER_CREDIT_STATUS_LABELS: Record<string, string> = {
  ACTIVE:    "Ativo",
  EXHAUSTED: "Esgotado",
  EXPIRED:   "Expirado",
  REVOKED:   "Revogado",
}

// Tipo de desconto de promoção
export const DISCOUNT_TYPE_LABELS: Record<string, string> = {
  PERCENTAGE:     "Percentual",
  FIXED_AMOUNT:   "Valor fixo",
  OVERRIDE_PRICE: "Preço fixo",
  FREE_ITEM:      "Item grátis",
}

// Modo de aplicação de promoção
export const APPLICATION_MODE_LABELS: Record<string, string> = {
  AUTOMATIC:       "Automática",
  COUPON_REQUIRED: "Requer cupom",
}

// Tipo de geração de cupom
export const GENERATION_TYPE_LABELS: Record<string, string> = {
  BULK:         "Em lote",
  SINGLE_USE:   "Uso único",
  PER_CUSTOMER: "Por cliente",
}

// Política de reabertura de cupom no estorno
export const COUPON_REOPEN_LABELS: Record<string, string> = {
  NEVER_REOPEN:     "Não reabrir",
  REOPEN_ON_REFUND: "Reabrir no estorno",
}

export const APPOINTMENT_STATUS_LABELS: Record<string, string> = {
  SCHEDULED:   "Agendado",
  REQUESTED:   "Solicitado",
  DRAFT:       "Rascunho",
  IN_PROGRESS: "Em andamento",
  COMPLETED:   "Concluído",
  CANCELLED:   "Cancelado",
  NO_SHOW:     "Não compareceu",
  FAILED:      "Falhou",
}

export const APPOINTMENT_STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  SCHEDULED:   "default",
  REQUESTED:   "secondary",
  DRAFT:       "outline",
  IN_PROGRESS: "secondary",
  COMPLETED:   "outline",
  CANCELLED:   "destructive",
  NO_SHOW:     "destructive",
  FAILED:      "destructive",
}

/* ========================= Fase 3 — Financeiro profundo ========================= */

// FSMs (chaves exatas do backend — CANCELLED em inglês na despesa)
export const EXPENSE_STATUS_LABELS: Record<string, string> = {
  PENDENTE:  "Pendente",
  PAGA:      "Paga",
  CANCELLED: "Cancelada",
}

export const PAYABLE_STATUS_LABELS: Record<string, string> = {
  OPEN:           "Em aberto",
  PARTIALLY_PAID: "Parcial",
  PAID:           "Paga",
  CANCELLED:      "Cancelada",
}

export const INSTALLMENT_STATUS_LABELS: Record<string, string> = {
  OPEN:      "Em aberto",
  PAID:      "Paga",
  CANCELLED: "Cancelada",
}

export const RECONCILIATION_STATUS_LABELS: Record<string, string> = {
  OPEN:   "Aberta",
  CLOSED: "Fechada",
}

export const STATEMENT_STATUS_LABELS: Record<string, string> = {
  PENDING:   "Pendente",
  MATCHED:   "Conciliado",
  DISMISSED: "Dispensado",
}

export const TRANSFER_STATUS_LABELS: Record<string, string> = {
  REQUESTED: "Solicitada",
  COMPLETED: "Concluída",
  FAILED:    "Falhou",
}

// Estoque
export const STOCK_MOVEMENT_TYPE_LABELS: Record<string, string> = {
  ENTRADA:     "Entrada",
  VENDA:       "Venda",
  USO_INTERNO: "Uso interno",
  PERDA:       "Perda",
  AJUSTE:      "Ajuste",
}

// Tipos de movimento registráveis (ENTRADA fica fora — só via Receber pedido)
export const STOCK_MOVEMENT_TYPE_OPTIONS = ["VENDA", "USO_INTERNO", "PERDA", "AJUSTE"] as const

// Contas financeiras
export const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  CAIXA:    "Caixa",
  ACQUIRER: "Adquirente",
  BANK:     "Banco",
  ESCROW:   "Conta garantia",
}

export const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  INFLOW:       "Entrada",
  OUTFLOW:      "Saída",
  TRANSFER_IN:  "Transf. recebida",
  TRANSFER_OUT: "Transf. enviada",
}

export const ENTRY_TYPE_LABELS: Record<string, string> = {
  RECEITA:  "Receita",
  CUSTO:    "Custo",
  DESPESA:  "Despesa",
  TAXA:     "Taxa",
  COMISSAO: "Comissão",
  ESTORNO:  "Estorno",
  AJUSTE:   "Ajuste",
}

export const CLOSING_METHOD_LABELS: Record<string, string> = {
  CASH_AT_CREATION: "À vista",
  INSTALLMENTS:     "Parcelado",
}

export const CASH_COUNT_RESOLUTION_LABELS: Record<string, string> = {
  ADJUSTED:      "Com ajuste",
  NO_ADJUSTMENT: "Sem ajuste",
}

// Mapa completo categoria → label PT-BR (entry_category.py) — Despesas, DRE, Lançamentos, Ajuste
export const ENTRY_CATEGORY_LABELS: Record<string, string> = {
  // RECEITA
  SERVICOS:              "Serviços",
  PRODUTOS:              "Produtos",
  PACOTE:                "Pacote",
  ASSINATURA_ADESAO:     "Assinatura (adesão)",
  ASSINATURA_RENOVACAO:  "Assinatura (renovação)",
  SINAL_SERVICO:         "Sinal de serviço",
  RECEITA_OUTROS:        "Outras receitas",
  // CUSTO
  INSUMOS_USO_INTERNO:   "Insumos (uso interno)",
  PRODUTO_VENDIDO:       "Produto vendido",
  MATERIAL_DESCARTAVEL:  "Material descartável",
  PERDA_ESTOQUE:         "Perda de estoque",
  PERDA_OPERACIONAL:     "Perda operacional",
  CUSTO_OUTROS:          "Outros custos",
  // DESPESA
  ALUGUEL:               "Aluguel",
  UTILITIES:             "Utilidades (água/luz)",
  MARKETING:             "Marketing",
  SOFTWARE:              "Software",
  CONTABILIDADE:         "Contabilidade",
  LIMPEZA:               "Limpeza",
  MANUTENCAO:            "Manutenção",
  SALARIO:               "Salário",
  SERVICOS_PJ:           "Serviços PJ",
  ALIMENTACAO_COPA:      "Alimentação/copa",
  EQUIPAMENTOS:          "Equipamentos",
  TAXAS_BANCARIAS:       "Taxas bancárias",
  TREINAMENTO:           "Treinamento",
  DESPESA_OUTROS:        "Outras despesas",
  // TAXA
  ACQUIRER_FEE:          "Taxa de adquirente",
  WITHDRAW_FEE:          "Taxa de saque",
  ANTECIPATION_FEE:      "Taxa de antecipação",
  TAXA_OUTROS:           "Outras taxas",
  // COMISSAO
  COMISSAO_SERVICO:      "Comissão de serviço",
  COMISSAO_VENDA:        "Comissão de venda",
  COMISSAO_RENOVACAO:    "Comissão de renovação",
  COMISSAO_PERSONALIZADA:"Comissão personalizada",
  // ESTORNO
  REEMBOLSO_CLIENTE:     "Reembolso ao cliente",
  CHARGEBACK:            "Chargeback",
  REVERSAO_TAXA:         "Reversão de taxa",
  // AJUSTE
  CONTAGEM_CAIXA:        "Contagem de caixa",
  CONTAGEM_ESTOQUE:      "Contagem de estoque",
  CORRECAO_LANCAMENTO:   "Correção de lançamento",
  CORRECAO_COMISSAO:     "Correção de comissão",
  AJUSTE_OUTROS:         "Outros ajustes",
}

// Categorias DESPESA — Select de categoria no form de Despesa
export const EXPENSE_CATEGORY_OPTIONS: string[] = [
  "ALUGUEL", "UTILITIES", "MARKETING", "SOFTWARE", "CONTABILIDADE", "LIMPEZA",
  "MANUTENCAO", "SALARIO", "SERVICOS_PJ", "ALIMENTACAO_COPA", "EQUIPAMENTOS",
  "TAXAS_BANCARIAS", "TREINAMENTO", "DESPESA_OUTROS",
]

// Categorias AJUSTE — Select de categoria no Ajuste manual
export const ADJUSTMENT_CATEGORY_OPTIONS: string[] = [
  "CONTAGEM_CAIXA", "CONTAGEM_ESTOQUE", "CORRECAO_LANCAMENTO",
  "CORRECAO_COMISSAO", "AJUSTE_OUTROS",
]

// Frequências de recorrência de despesa
export const RECURRENCE_FREQUENCY_LABELS: Record<string, string> = {
  MONTHLY:   "Mensal",
  WEEKLY:    "Semanal",
  QUARTERLY: "Trimestral",
  YEARLY:    "Anual",
}

/* ===================== Fase 4 — Relacionamento e Administração ===================== */

// NPS — status da survey (NpsSurveyResponse.status)
export const NPS_SURVEY_STATUS_LABELS: Record<string, string> = {
  PENDING:   "Pendente",
  SENT:      "Enviada",
  RESPONDED: "Respondida",
  EXPIRED:   "Expirada",
}

// Comunicação — status do log de envio (CommunicationLogResponse.status)
export const COMMUNICATION_LOG_STATUS_LABELS: Record<string, string> = {
  SENT:                     "Enviada",
  SCHEDULED:                "Agendada",
  FAILED:                   "Falhou",
  SKIPPED_QUIET_HOURS:      "Adiada (silêncio)",
  SKIPPED_NO_CONSENT:       "Sem consentimento",
  SKIPPED_CHANNEL_DISABLED: "Canal desativado",
  SKIPPED_NO_TEMPLATE:      "Sem template",
}

// Canal de comunicação (WHATSAPP|EMAIL|SMS)
export const COMMUNICATION_CHANNEL_LABELS: Record<string, string> = {
  WHATSAPP: "WhatsApp",
  EMAIL:    "E-mail",
  SMS:      "SMS",
}

// Público-alvo do template / destinatário do log (CLIENT|PROFESSIONAL|OWNER)
export const COMMUNICATION_AUDIENCE_LABELS: Record<string, string> = {
  CLIENT:       "Cliente",
  PROFESSIONAL: "Profissional",
  OWNER:        "Proprietário",
}

// Tipo de API do WhatsApp (whatsapp_api_type)
export const WHATSAPP_API_TYPE_LABELS: Record<string, string> = {
  UNOFFICIAL_BAILEYS: "Não-oficial (Baileys)",
  OFFICIAL_META:      "Oficial (Meta)",
}

// Módulos do tenant — enum fechado (module_activation.py): 10 módulos
export const MODULE_LABELS: Record<string, string> = {
  ESTOQUE:      "Estoque",
  COMISSOES:    "Comissões",
  PACOTES:      "Pacotes",
  ASSINATURAS:  "Assinaturas",
  PROMOCOES:    "Promoções",
  CRM:          "CRM",
  NPS:          "NPS",
  FILA:         "Fila de espera",
  BOT_WHATSAPP: "Bot WhatsApp",
  LINK_PUBLICO: "Link público",
}

// Descrição curta por módulo (informativo)
export const MODULE_DESCRIPTIONS: Record<string, string> = {
  ESTOQUE:      "Controle de produtos, entradas e movimentações.",
  COMISSOES:    "Cálculo automático de comissões por profissional.",
  PACOTES:      "Pacotes de serviços pré-pagos com saldo.",
  ASSINATURAS:  "Planos recorrentes com cobrança automática.",
  PROMOCOES:    "Cupons e campanhas promocionais.",
  CRM:          "Classificação e jornada do cliente.",
  NPS:          "Pesquisas de satisfação pós-atendimento.",
  FILA:         "Fila de espera com avisos automáticos.",
  BOT_WHATSAPP: "Atendimento automatizado via WhatsApp.",
  LINK_PUBLICO: "Página pública de agendamento.",
}

// Dependências conhecidas por módulo (texto informativo — não existe no backend)
export const MODULE_DEPENDENCIES: Record<string, string> = {
  COMISSOES:    "Funciona melhor com Estoque ativo.",
  PACOTES:      "Requer Catálogo de serviços.",
  ASSINATURAS:  "Requer integração de pagamento.",
  NPS:          "Use junto com WhatsApp ou E-mail.",
  BOT_WHATSAPP: "Requer conexão WhatsApp ativa.",
}

// Ordem de exibição dos módulos (espelha o grid das screenshots)
export const MODULE_ORDER = [
  "ESTOQUE", "COMISSOES", "PACOTES",
  "ASSINATURAS", "PROMOCOES", "CRM",
  "NPS", "FILA", "BOT_WHATSAPP",
  "LINK_PUBLICO",
] as const

// Catálogo de eventos de comunicação (_DEFAULT_TEMPLATES do backend)
export const COMMUNICATION_EVENT_TYPE_LABELS: Record<string, string> = {
  "appointment.confirmed":          "Agendamento confirmado",
  "appointment.cancelled":          "Agendamento cancelado",
  "appointment.reminder_24h":       "Lembrete 24h",
  "appointment.reminder_2h":        "Lembrete 2h",
  "appointment.completed":          "Atendimento concluído",
  "appointment.no_show":            "Não comparecimento",
  "auth.password_reset_requested":  "Redefinição de senha",
  "user.invitation_sent":           "Convite de usuário",
  "nps.survey_request":             "Pesquisa NPS",
  "nps.low_score_alert":            "Alerta de nota baixa",
  "waitlist.slot_available":        "Vaga disponível (fila)",
  "conversation.escalated":         "Conversa escalada",
}

// Eventos disponíveis no Select de criação de template
export const COMMUNICATION_EVENT_TYPE_OPTIONS = Object.keys(COMMUNICATION_EVENT_TYPE_LABELS)

// Variáveis {{}} sugeridas por evento (chips clicáveis no editor — hint de UX, não validação)
export const TEMPLATE_VARIABLES_BY_EVENT: Record<string, string[]> = {
  "appointment.confirmed":     ["cliente_nome", "servico", "profissional", "data", "horario", "empresa_nome", "manage_url"],
  "appointment.cancelled":     ["cliente_nome", "servico", "profissional", "data", "horario", "empresa_nome", "manage_url"],
  "appointment.reminder_24h":  ["cliente_nome", "servico", "profissional", "data", "horario", "empresa_nome", "manage_url"],
  "appointment.reminder_2h":   ["cliente_nome", "servico", "profissional", "data", "horario", "empresa_nome", "manage_url"],
  "appointment.completed":     ["cliente_nome", "servico", "profissional", "data", "horario", "empresa_nome", "manage_url"],
  "appointment.no_show":       ["cliente_nome", "servico", "profissional", "data", "horario", "empresa_nome", "manage_url"],
  "nps.survey_request":        ["cliente_nome", "nps_url"],
  "nps.low_score_alert":       ["cliente_nome", "nota", "comentario"],
  "user.invitation_sent":      ["company_name", "activation_link", "role"],
  "auth.password_reset_requested": ["user_name", "token"],
  "waitlist.slot_available":   ["cliente_nome"],
  "conversation.escalated":    ["customer_name", "phone", "panel_url"],
}

// Valores de exemplo para o preview de template (substituem {{var}})
export const TEMPLATE_VARIABLE_EXAMPLES: Record<string, string> = {
  cliente_nome:    "João",
  customer_name:   "João",
  servico:         "Corte masculino",
  profissional:    "Carlos",
  data:            "15/06/2026",
  horario:         "14:30",
  empresa_nome:    "Barbearia do Zeca",
  company_name:    "Barbearia do Zeca",
  manage_url:      "https://app.exemplo.com/gestao/abc123",
  nps_url:         "https://app.exemplo.com/nps/respond/abc123",
  activation_link: "https://app.exemplo.com/activate/abc123",
  token:           "123456",
  user_name:       "Ana",
  role:            "Operador",
  nota:            "4",
  comentario:      "Atendimento poderia ser mais rápido",
  phone:           "+55 11 91234-5678",
  panel_url:       "https://app.exemplo.com/inbox",
}

// Status de convite (InvitationResponse.status)
export const INVITATION_STATUS_LABELS: Record<string, string> = {
  PENDING:   "Pendente",
  ACCEPTED:  "Aceito",
  CANCELLED: "Cancelado",
  EXPIRED:   "Expirado",
}

// Anti-escalonamento — papéis que cada ator pode atribuir/convidar (INVITE_PERMISSION)
export const ASSIGNABLE_ROLES_BY_ACTOR: Record<string, string[]> = {
  OWNER: ["OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL"],
  ADMIN: ["OPERATOR", "PROFESSIONAL"],
}

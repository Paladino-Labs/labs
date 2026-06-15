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

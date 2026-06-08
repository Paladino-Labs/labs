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
  CASH:              "Dinheiro",
  PIX:               "PIX",
  MAQUININHA:        "Maquininha",
  MAQUININHA_CREDIT: "Maquininha (Crédito)",
  MAQUININHA_DEBIT:  "Maquininha (Débito)",
  BOLETO:            "Boleto",
  CARD_CREDIT:       "Cartão de Crédito",
  CARD_DEBIT:        "Cartão de Débito",
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

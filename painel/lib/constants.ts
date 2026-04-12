/**
 * Constantes de domínio compartilhadas — status de agendamento.
 * Importe nestes arquivos em vez de redefinir localmente.
 */

export const APPOINTMENT_STATUS_LABELS: Record<string, string> = {
  SCHEDULED:   "Agendado",
  IN_PROGRESS: "Em andamento",
  COMPLETED:   "Concluído",
  CANCELLED:   "Cancelado",
  NO_SHOW:     "Não compareceu",
}

export const APPOINTMENT_STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  SCHEDULED:   "default",
  IN_PROGRESS: "secondary",
  COMPLETED:   "outline",
  CANCELLED:   "destructive",
  NO_SHOW:     "destructive",
}

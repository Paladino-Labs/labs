import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Formata um valor numérico como moeda BRL.
 * Ex: 50 → "R$ 50,00"
 */
export function formatBRL(value: number | string): string {
  const num = typeof value === "string" ? parseFloat(value) : value
  if (isNaN(num)) return "—"
  return num.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
}

/**
 * Formata uma string ISO 8601 como data e hora curtas em pt-BR.
 * Ex: "2026-04-12T14:30:00Z" → "12/04/2026 11:30"
 */
export function formatDateTime(isoString: string): string {
  if (!isoString) return "—"
  return new Date(isoString).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  })
}

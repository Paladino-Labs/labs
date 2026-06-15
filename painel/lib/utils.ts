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

/**
 * Converte uma string decimal da API (ex.: "38.50") em BRL formatado.
 * A API devolve valores monetários como string decimal — esta helper
 * faz o parse antes de delegar para formatBRL().
 */
export function formatBRLFromDecimal(value: string | number | null | undefined): string {
  if (value == null || value === "") return "—"
  const num = typeof value === "string" ? parseFloat(value) : value
  if (isNaN(num)) return "—"
  return formatBRL(num)
}

/**
 * Tempo relativo humano em pt-BR a partir de um ISO no passado.
 * Ex.: "há 12 min", "há 2 h", "há 3 d".
 */
export function timeAgo(isoString: string | null | undefined): string {
  if (!isoString) return "—"
  const then = new Date(isoString).getTime()
  if (isNaN(then)) return "—"
  const diffMs = Date.now() - then
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return "agora"
  if (min < 60) return `há ${min} min`
  const h = Math.floor(min / 60)
  if (h < 24) return `há ${h} h`
  const d = Math.floor(h / 24)
  return `há ${d} d`
}

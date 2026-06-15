"use client"

import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface MoneyInputProps {
  value: string
  onChange: (value: string) => void
  id?: string
  className?: string
  placeholder?: string
  disabled?: boolean
}

/**
 * Input numérico com prefixo "R$" para valores monetários.
 * Emite a string crua (ex.: "38.50"); o chamador envia ao backend como decimal.
 * Sem cálculo no cliente — apenas captura o valor.
 */
export function MoneyInput({
  value,
  onChange,
  id,
  className,
  placeholder = "0,00",
  disabled,
}: MoneyInputProps) {
  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
        R$
      </span>
      <Input
        id={id}
        type="number"
        min="0"
        step="0.01"
        inputMode="decimal"
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={cn("pl-9", className)}
      />
    </div>
  )
}

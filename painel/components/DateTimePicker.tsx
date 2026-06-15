"use client"

import { Input } from "@/components/ui/input"

interface Props {
  value: string
  onChange: (value: string) => void
  id?: string
  className?: string
  disabled?: boolean
}

/**
 * Wrapper controlado sobre <Input type="datetime-local">.
 * Emite a string crua do input (formato "YYYY-MM-DDTHH:mm"); o chamador
 * converte para ISO via new Date(value).toISOString() ao enviar.
 */
export function DateTimePicker({ value, onChange, id, className, disabled }: Props) {
  return (
    <Input
      id={id}
      type="datetime-local"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={className}
    />
  )
}

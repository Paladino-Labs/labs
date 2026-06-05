"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { X } from "lucide-react"
import { api } from "@/lib/api"
import { Input } from "@/components/ui/input"
import type { Customer } from "@/types"

interface Props {
  value: string | null
  onChange: (id: string, name: string) => void
  placeholder?: string
}

export function CustomerAutocomplete({ value, onChange, placeholder = "Buscar cliente…" }: Props) {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [inputText, setInputText] = useState("")
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.get<Customer[]>("/customers/").then(setCustomers).catch(() => {})
  }, [])

  useEffect(() => {
    if (!value) setInputText("")
  }, [value])

  const filtered = useMemo(() => {
    const q = inputText.trim().toLowerCase()
    if (q.length < 2) return []
    return customers.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.phone ?? "").includes(q)
    )
  }, [customers, inputText])

  function handleSelect(c: Customer) {
    setInputText(c.name)
    setOpen(false)
    onChange(c.id, c.name)
  }

  function handleClear() {
    setInputText("")
    setOpen(false)
    onChange("", "")
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    setInputText(e.target.value)
    setOpen(true)
    if (value) onChange("", "")
  }

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleOutside)
    return () => document.removeEventListener("mousedown", handleOutside)
  }, [])

  const showDropdown = open && inputText.trim().length >= 2

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Input
          value={inputText}
          onChange={handleInputChange}
          onFocus={() => { if (inputText.trim().length >= 2) setOpen(true) }}
          placeholder={placeholder}
        />
        {(value || inputText) && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            aria-label="Limpar cliente"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {showDropdown && (
        <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-border bg-card shadow-md">
          {filtered.length === 0 ? (
            <div className="px-3 py-2.5 text-sm text-muted-foreground">
              Nenhum cliente encontrado.
            </div>
          ) : (
            <ul className="max-h-48 divide-y divide-border overflow-y-auto">
              {filtered.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onMouseDown={() => handleSelect(c)}
                    className="w-full px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted"
                  >
                    <span className="font-medium">{c.name}</span>
                    {c.phone && (
                      <span className="ml-2 text-muted-foreground">{c.phone}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

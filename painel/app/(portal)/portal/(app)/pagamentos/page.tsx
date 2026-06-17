"use client"

import { useState } from "react"
import { CreditCard, Info, Plus, Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

// ⚠️ BLOQUEADO por backend (Asaas).
// O adapter Asaas NÃO tokeniza cartão — `source_token` precisa vir
// pré-tokenizado, o que depende de conta/contrato Asaas pendentes. Além disso,
// adicionar fonte exige consent PAYMENT_STORAGE concedido (senão 422).
//
// Endpoints existentes (a serem ligados quando Asaas estiver ativo):
//   GET    /portal/payment-sources
//   POST   /portal/payment-sources { company_id*, source_token*, mode* (ONCE|ALWAYS), last_four?, brand? }
//   DELETE /portal/payment-sources/{authorization_id}
//
// Por ora: estrutura visual aprovada (banner + lista + Adicionar), SEM wiring
// real. Os cartões abaixo são placeholders estáticos para validar o layout.

interface MockCard {
  id: string
  brand: string
  last_four: string
  is_default: boolean
}

const MOCK_CARDS: MockCard[] = [
  { id: "1", brand: "Visa", last_four: "4242", is_default: true },
  { id: "2", brand: "Mastercard", last_four: "5566", is_default: false },
]

type Mode = "ONCE" | "ALWAYS"

export default function PortalPagamentosPage() {
  const [cards, setCards] = useState<MockCard[]>(MOCK_CARDS)
  const [addOpen, setAddOpen] = useState(false)
  const [mode, setMode] = useState<Mode>("ONCE")

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl tracking-wide text-foreground">Pagamentos</h1>

      <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-4 py-3">
        <Info size={16} strokeWidth={1.5} className="mt-0.5 flex-shrink-0 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          Esta área está em desenvolvimento. A integração de pagamentos estará disponível em breve.
        </p>
      </div>

      <div className="space-y-2">
        {cards.map((card) => (
          <div
            key={card.id}
            className="flex items-center justify-between gap-3 rounded-xl bg-card px-4 py-3 ring-1 ring-foreground/10"
          >
            <div className="flex items-center gap-3">
              <CreditCard size={18} strokeWidth={1.5} className="text-muted-foreground" />
              <div>
                <p className="text-sm font-medium text-foreground">
                  {card.brand} •••• {card.last_four}
                </p>
                {card.is_default && (
                  <Badge variant="outline" className="mt-1">
                    Cartão padrão
                  </Badge>
                )}
              </div>
            </div>
            <button
              onClick={() => setCards((c) => c.filter((x) => x.id !== card.id))}
              className="flex items-center gap-1.5 text-sm text-destructive transition-colors hover:text-destructive/80"
            >
              <Trash2 size={14} strokeWidth={1.5} /> Remover
            </button>
          </div>
        ))}
      </div>

      <Button onClick={() => setAddOpen(true)}>
        <Plus size={16} strokeWidth={1.5} /> Adicionar forma de pagamento
      </Button>

      {/* Form de adicionar — modelo de autorização em radio nativo
          (não há RadioGroup no projeto). Submit desabilitado até Asaas ativo. */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adicionar forma de pagamento</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Escolha como deseja autorizar o uso deste cartão.
          </p>
          <fieldset className="space-y-2">
            {(
              [
                { value: "ONCE", label: "Apenas esta vez", hint: "Autoriza um único uso." },
                { value: "ALWAYS", label: "Permitir sempre", hint: "Salva para próximas compras." },
              ] as { value: Mode; label: string; hint: string }[]
            ).map((opt) => (
              <label
                key={opt.value}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors",
                  mode === opt.value ? "border-primary bg-primary/5" : "border-border",
                )}
              >
                <input
                  type="radio"
                  name="auth-mode"
                  value={opt.value}
                  checked={mode === opt.value}
                  onChange={() => setMode(opt.value)}
                  className="mt-0.5 accent-primary"
                />
                <span>
                  <span className="block text-sm font-medium text-foreground">{opt.label}</span>
                  <span className="block text-xs text-muted-foreground">{opt.hint}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              Cancelar
            </Button>
            {/* TODO(Asaas): habilitar quando a tokenização de cartão estiver ativa. */}
            <Button disabled title="Disponível em breve">
              Adicionar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

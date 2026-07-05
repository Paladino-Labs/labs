"use client"

import { useEffect, useState } from "react"
import { AlertTriangle } from "lucide-react"
import { api } from "@/lib/api"

// Aviso informativo no fluxo de conclusão de agendamento (Sprint C produtos):
// produtos que o cliente comprou e ainda não retirou nesta empresa.
// NÃO bloqueia a conclusão — o operador conclui ciente e entrega/cobra.

interface PendingProduct {
  product_name: string
  quantity: number
  status: "RESERVED" | "PURCHASED"
  total_price: string
}

interface PendingProductsResponse {
  has_pending: boolean
  items: PendingProduct[]
}

const STATUS_LABELS: Record<string, string> = {
  RESERVED:  "aguardando pagamento e retirada",
  PURCHASED: "pago, aguardando retirada",
}

export function PendingProductsNotice({ appointmentId }: { appointmentId: string }) {
  const [pending, setPending] = useState<PendingProductsResponse | null>(null)

  useEffect(() => {
    if (!appointmentId) return
    setPending(null)
    api.get<PendingProductsResponse>(`/appointments/${appointmentId}/pending-products`)
      .then(setPending)
      .catch(() => setPending(null))
  }, [appointmentId])

  if (!pending?.has_pending) return null

  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 space-y-1.5">
      <p className="flex items-center gap-1.5 text-sm font-medium text-amber-700 dark:text-amber-400">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        Este cliente tem produtos a retirar
      </p>
      <ul className="space-y-0.5 text-xs text-muted-foreground">
        {pending.items.map((item, i) => (
          <li key={i}>
            {item.product_name} ({item.quantity}) —{" "}
            {STATUS_LABELS[item.status] ?? item.status}
          </li>
        ))}
      </ul>
    </div>
  )
}

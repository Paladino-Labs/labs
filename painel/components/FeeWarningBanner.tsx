"use client"

import { X } from "lucide-react"

import { FEE_SOURCE_LABELS } from "@/lib/constants"

interface Props {
  feeSource: string
  message?: string
  onDismiss: () => void
  /**
   * CTA "Configurar agora". Omitir quando quem está vendo o aviso não pode
   * abrir /financeiro/taxas (OPERATOR) — nesse caso o banner explica o que
   * aconteceu e a quem recorrer, em vez de mandar para uma tela sem acesso.
   */
  onConfigureClick?: () => void
}

export function FeeWarningBanner({ feeSource, message, onDismiss, onConfigureClick }: Props) {
  const label = FEE_SOURCE_LABELS[feeSource] ?? feeSource

  return (
    <div className="flex items-start gap-3 rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
      <span className="flex-1">
        {message ?? `Nenhuma taxa configurada para ${label}.`}{" "}
        {onConfigureClick ? (
          <button
            type="button"
            onClick={onConfigureClick}
            className="font-medium underline hover:no-underline"
          >
            Configurar agora →
          </button>
        ) : (
          <span>
            O pagamento foi registrado normalmente; o valor líquido saiu sem
            desconto de taxa. Avise a gerência para configurar a taxa desta forma
            de pagamento.
          </span>
        )}
      </span>
      <button
        type="button"
        onClick={onDismiss}
        className="shrink-0 text-yellow-600 hover:text-yellow-900"
        aria-label="Fechar aviso"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

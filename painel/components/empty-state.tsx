import { Inbox } from "lucide-react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface EmptyStateProps {
  /** Mensagem simples (modo legado — renderiza texto centralizado em itálico). */
  message?: string
  /** Título destacado (modo card). */
  title?: string
  description?: string
  action?: ReactNode
  icon?: ReactNode
  className?: string
}

export function EmptyState({
  message,
  title,
  description,
  action,
  icon,
  className,
}: EmptyStateProps) {
  // Modo legado: apenas `message` → texto simples (mantém compatibilidade).
  if (message && !title) {
    return (
      <div className={cn("text-center text-sm italic text-muted-foreground py-10", className)}>
        {message}
      </div>
    )
  }

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-md border border-dashed border-border bg-card/40 px-6 py-16 text-center",
        className
      )}
    >
      <div className="mb-3 text-muted-foreground">
        {icon ?? <Inbox size={28} strokeWidth={1.5} />}
      </div>
      <p className="font-display text-xl text-foreground">{title ?? message}</p>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

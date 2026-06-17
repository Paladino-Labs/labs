import Link from "next/link"
import type { ReactNode } from "react"

// Shell centralizado das telas de auth do portal (login, magic).
// Wordmark + subtítulo acima do conteúdo; link discreto "Voltar para o site".
export function PortalAuthShell({
  children,
  showBackLink = true,
}: {
  children: ReactNode
  showBackLink?: boolean
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="mb-6 text-center">
        <span className="font-display block text-3xl tracking-[0.3em] text-primary leading-none">
          PALADINO
        </span>
        <span className="mt-2 block text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
          Portal do Cliente
        </span>
      </div>

      <div className="w-full max-w-sm">{children}</div>

      {showBackLink && (
        <Link
          href="/"
          className="mt-6 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          ← Voltar para o site
        </Link>
      )}
    </div>
  )
}

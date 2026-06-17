import type { ReactNode } from "react"

/**
 * Shell público compartilhado (grupo de rota `(public)`).
 * Distinto do shell do painel: sem sidebar, sem header autenticado, sem guard.
 * Header mínimo com o wordmark PALADINO; rodapé discreto. Paleta do sistema
 * via `.book-page` / tokens. `/book/[slug]` NÃO usa este layout — vive fora do grupo.
 */
export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="book-page flex min-h-screen flex-col bg-background">
      <header className="py-6 text-center">
        <span className="font-display text-2xl tracking-[0.3em] text-primary">PALADINO</span>
      </header>
      <main className="mx-auto w-full max-w-xl flex-1 px-4 py-8">{children}</main>
      <footer className="py-6 text-center text-xs text-muted-foreground">© PALADINO</footer>
    </div>
  )
}

import type { ReactNode } from "react"

// Shell EXTERNO mínimo do Portal do Cliente (grupo de rota `(portal)`).
// Propositalmente sem header/nav/guard: as telas de autenticação
// (`login`, `magic/[token]`) renderizam seu próprio layout centrado com
// wordmark; a área autenticada (`(app)/layout.tsx`) renderiza a nav lateral
// e o bottom nav. Mantê-lo como wrapper neutro evita chrome duplicado.
//
// ⛔ O Portal NÃO importa Sidebar/Header/AuthContext/apiFetch do painel do
//    tenant — é um terceiro shell isolado (JWT type="portal").
export default function PortalLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-background">{children}</div>
}

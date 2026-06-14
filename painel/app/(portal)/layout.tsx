"use client"

import Link from "next/link"

// Shell do Portal do Cliente — sem o sidebar do tenant, só header mínimo.
// Fase 0: estrutura básica; as telas do portal chegam em fase posterior.
export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="border-b border-border">
        <div className="mx-auto max-w-3xl flex items-center justify-between px-6 h-14">
          <Link href="/portal" className="font-display text-lg tracking-[0.3em] text-primary">
            PALADINO
          </Link>
        </div>
      </header>
      <main className="flex-1">
        <div className="mx-auto max-w-3xl px-6 py-10">{children}</div>
      </main>
    </div>
  )
}

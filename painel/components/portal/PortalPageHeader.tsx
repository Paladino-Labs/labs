"use client"
// Redesign F4b — cabeçalho padrão das seções do portal: a nav agora é
// hub → blocos → seções, então toda seção tem "‹ Voltar" para a home.
import Link from "next/link"
import { ChevronLeft } from "lucide-react"

export function PortalPageHeader({ title }: { title: string }) {
  return (
    <div className="flex items-center gap-3">
      <Link
        href="/portal/dashboard"
        className="flex flex-shrink-0 items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
      >
        <ChevronLeft size={14} strokeWidth={1.5} /> Voltar
      </Link>
      <h1 className="font-display text-3xl tracking-wide text-foreground">{title}</h1>
    </div>
  )
}

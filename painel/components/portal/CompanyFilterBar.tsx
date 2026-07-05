"use client"
// Redesign F4a — menu horizontal de empresas (chips roláveis).
// Referência visual: Screenshots/redesign-portal-cliente + barberflow-system
// src/components/portal/company-chips.tsx (chip ativo = borda/fundo dourados).
import { useCompanyFilter } from "@/context/CompanyFilterContext"
import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"

export function CompanyFilterBar() {
  const { companies, companiesLoading, selectedCompanyId, setSelectedCompanyId } =
    useCompanyFilter()

  // Cliente sem empresas: o portal está vazio de qualquer forma — sem barra.
  if (!companiesLoading && companies.length === 0) return null

  return (
    <div className="border-b border-border/60 bg-background/95 backdrop-blur">
      {/* `!` — globals.css tem `* { scrollbar-width: thin }` FORA de @layer,
          que vence utilities em camada independente de especificidade. */}
      <div className="flex gap-2 overflow-x-auto px-4 py-2 md:px-8 [scrollbar-width:none]! [&::-webkit-scrollbar]:hidden!">
        {companiesLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-28 flex-shrink-0 rounded-full" />
          ))
        ) : (
          <>
            <Chip
              label="Todas"
              active={selectedCompanyId === null}
              onClick={() => setSelectedCompanyId(null)}
            />
            {companies.map((c) => (
              <Chip
                key={c.company_id}
                label={c.company_name}
                active={selectedCompanyId === c.company_id}
                onClick={() => setSelectedCompanyId(c.company_id)}
              />
            ))}
          </>
        )}
      </div>
    </div>
  )
}

function Chip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex-shrink-0 whitespace-nowrap rounded-full border px-3 py-1.5 text-xs uppercase tracking-wider transition-colors",
        active
          ? "border-primary bg-primary/15 text-primary"
          : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
      )}
    >
      {label}
    </button>
  )
}

import { cn } from "@/lib/utils"

// Barra de progresso de cota (Fase 5B). O projeto NÃO tem o componente
// `Progress` → implementada como div (trilho bg-muted + preenchimento por
// width %). Cor por faixa de percentual restante (tokens semânticos):
//   pct > 50 → primary | pct > 25 → amber-500 | pct > 0 → amber-700 | 0 → muted-foreground
function barColor(pct: number): string {
  if (pct > 50) return "bg-primary"
  if (pct > 25) return "bg-amber-500"
  if (pct > 0) return "bg-amber-700"
  return "bg-muted-foreground"
}

export function QuotaProgress({
  remaining,
  total,
  className,
}: {
  remaining: number
  total: number
  className?: string
}) {
  const pct = total > 0 ? Math.max(0, Math.min(100, (remaining / total) * 100)) : 0
  return (
    <div className={cn("h-2 w-full rounded-full bg-muted", className)}>
      <div
        className={cn("h-2 rounded-full transition-all", barColor(pct))}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

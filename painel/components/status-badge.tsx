import { Badge } from "@/components/ui/badge"

interface StatusBadgeProps {
  active: boolean
  labelActive?: string
  labelInactive?: string
}

export function StatusBadge({
  active,
  labelActive = "Ativo",
  labelInactive = "Inativo",
}: StatusBadgeProps) {
  return (
    <Badge variant={active ? "default" : "secondary"}>
      {active ? labelActive : labelInactive}
    </Badge>
  )
}

import { Badge } from "@/components/ui/badge"

interface ActiveBadgeProps {
  active: boolean
}

/**
 * Badge padronizado de status ativo/inativo.
 * Substitui o padrão repetido: <Badge variant={x.active ? "default" : "secondary"}>
 */
export function ActiveBadge({ active }: ActiveBadgeProps) {
  return (
    <Badge variant={active ? "default" : "secondary"}>
      {active ? "Ativo" : "Inativo"}
    </Badge>
  )
}

import { Badge } from "@/components/ui/badge"
import { TENANT_STATUS_LABELS, TENANT_STATUS_VARIANT } from "@/lib/constants"

/** Badge colorido por status do tenant (TRIAL/ACTIVE/SUSPENDED/CHURNED). */
export function TenantStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={TENANT_STATUS_VARIANT[status] ?? "outline"}>
      {TENANT_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

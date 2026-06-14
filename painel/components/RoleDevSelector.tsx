"use client"

import { useAuth, ROLE_LABELS, type Role } from "@/context/AuthContext"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

// Roles testáveis no painel do tenant (PLATFORM_OWNER tem shell próprio).
const DEV_ROLES: Role[] = ["OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL"]

export default function RoleDevSelector() {
  const { role, setRole } = useAuth()

  // Renderizado apenas em desenvolvimento.
  if (process.env.NODE_ENV !== "development") return null

  const current = DEV_ROLES.includes((role ?? "") as Role) ? (role as Role) : undefined

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-muted-foreground hidden sm:inline">Role:</span>
      <Select value={current} onValueChange={(v) => setRole(v as Role)}>
        <SelectTrigger size="sm" className="w-[130px]">
          <SelectValue placeholder="Role" />
        </SelectTrigger>
        <SelectContent>
          {DEV_ROLES.map((r) => (
            <SelectItem key={r} value={r}>
              {ROLE_LABELS[r]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

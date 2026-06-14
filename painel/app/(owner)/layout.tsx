"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"

export default function OwnerLayout({ children }: { children: React.ReactNode }) {
  const { token, role, companyId, hydrated } = useAuth()
  const router = useRouter()

  // Indicador real de PLATFORM_OWNER no backend é company_id == null
  // (o JWT de tenant sempre carrega company_id). Ver brief §8.
  const isPlatformOwner = role === "PLATFORM_OWNER" || (!!token && companyId == null)

  useEffect(() => {
    if (!hydrated) return
    if (!token) {
      router.replace("/")
      return
    }
    if (!isPlatformOwner) {
      router.replace("/dashboard")
    }
  }, [hydrated, token, isPlatformOwner, router])

  if (!hydrated) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground text-sm">
        Carregando…
      </div>
    )
  }

  if (!token || !isPlatformOwner) return null

  return <div className="min-h-screen bg-background">{children}</div>
}

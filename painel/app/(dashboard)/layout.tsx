"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import Sidebar from "@/components/Sidebar"

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { token, hydrated } = useAuth()
  const router = useRouter()

  useEffect(() => {
    // Só redireciona depois que a hidratação do localStorage terminou.
    // Sem esse guard, token===null antes da hidratação causaria um loop
    // infinito: dashboard → login → dashboard → ...
    if (hydrated && !token) {
      router.replace("/")
    }
  }, [hydrated, token, router])

  // Enquanto não hidratou, mostra tela de carregamento neutra
  if (!hydrated) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground text-sm">
        Carregando…
      </div>
    )
  }

  // Hidratado mas sem token → aguarda redirect do useEffect acima
  if (!token) return null

  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <main className="flex-1 p-8 bg-gray-50 overflow-auto">{children}</main>
    </div>
  )
}

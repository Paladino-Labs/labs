"use client"

import { useEffect } from "react"
import { useRouter, usePathname } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import { BrandingProvider } from "@/context/BrandingContext"
import Sidebar from "@/components/Sidebar"
import Header from "@/components/Header"

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { token, role, hydrated } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    // Só redireciona depois que a hidratação do localStorage terminou.
    // Sem esse guard, token===null antes da hidratação causaria um loop
    // infinito: dashboard → login → dashboard → ...
    if (hydrated && !token) {
      router.replace("/")
    }
  }, [hydrated, token, router])

  // PROFESSIONAL não acessa o financeiro → volta ao dashboard.
  // Exceção: /financeiro/taxas é liberada em modo leitura (Passo 10 — escopo PROFESSIONAL).
  useEffect(() => {
    if (
      hydrated &&
      role === "PROFESSIONAL" &&
      pathname.startsWith("/financeiro") &&
      !pathname.startsWith("/financeiro/taxas")
    ) {
      router.replace("/dashboard")
    }
  }, [hydrated, role, pathname, router])

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
    <BrandingProvider>
      <div className="h-screen flex overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col min-w-0">
          <Header />
          <main className="flex flex-1 flex-col px-6 py-8 md:px-10 md:py-10 bg-background overflow-y-auto">
            {children}
          </main>
        </div>
      </div>
    </BrandingProvider>
  )
}

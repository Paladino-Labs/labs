"use client"

import { useEffect, useRef, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { Link2Off, Loader2 } from "lucide-react"
import { portalFetch, setPortalToken } from "@/lib/portal-api"
import type { PortalTokenResponse } from "@/lib/portal-types"
import { PortalAuthShell } from "@/components/portal/PortalAuthShell"
import { Button } from "@/components/ui/button"

type View = "verifying" | "error"

export default function PortalMagicPage() {
  // ⚠️ Token no SEGMENTO DE ROTA (não query string): o backend gera o link
  // como {base}/portal/magic/{raw_token}. Ler via useParams.
  const { token } = useParams<{ token: string }>()
  const router = useRouter()
  const [view, setView] = useState<View>("verifying")
  const consumed = useRef(false)

  useEffect(() => {
    if (consumed.current || !token) return
    consumed.current = true // consome o token só uma vez

    portalFetch<PortalTokenResponse>("/portal/auth/magic-link/verify", {
      method: "POST",
      body: JSON.stringify({ token }),
    })
      .then((res) => {
        setPortalToken(res.access_token)
        router.replace("/portal/dashboard")
      })
      .catch(() => {
        // 422 (expirado/usado) ou qualquer outra falha → tela de erro.
        setView("error")
      })
  }, [token, router])

  return (
    <PortalAuthShell showBackLink={false}>
      <div className="rounded-xl bg-card p-8 text-center ring-1 ring-foreground/10">
        {view === "verifying" ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">Validando seu acesso…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <Link2Off className="h-10 w-10 text-muted-foreground" strokeWidth={1.5} />
            <h1 className="font-display text-xl tracking-wide text-foreground">
              Link expirado
            </h1>
            <p className="max-w-xs text-sm text-muted-foreground">
              Este link expirou ou já foi utilizado.
            </p>
            <Button className="mt-2" onClick={() => router.push("/portal/login")}>
              Pedir novo link
            </Button>
          </div>
        )}
      </div>
    </PortalAuthShell>
  )
}

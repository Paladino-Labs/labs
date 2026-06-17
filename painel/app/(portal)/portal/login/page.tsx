"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { KeyRound, Loader2, Mail, MailCheck } from "lucide-react"
import { cn } from "@/lib/utils"
import { portalFetch, setPortalToken } from "@/lib/portal-api"
import type { PortalTokenResponse } from "@/lib/portal-types"
import { PortalAuthShell } from "@/components/portal/PortalAuthShell"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

type Mode = "magic" | "password"
type MagicState = "idle" | "sending" | "sent" | "error"

export default function PortalLoginPage() {
  const router = useRouter()
  const [mode, setMode] = useState<Mode>("magic")

  // Magic link
  const [magicEmail, setMagicEmail] = useState("")
  const [magicState, setMagicState] = useState<MagicState>("idle")

  // E-mail + senha
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)

  async function handleMagicLink(e: React.FormEvent) {
    e.preventDefault()
    if (!magicEmail) return
    setMagicState("sending")
    try {
      // Backend responde sempre 200 — nunca revela se o e-mail existe.
      await portalFetch("/portal/auth/magic-link", {
        method: "POST",
        body: JSON.stringify({ email: magicEmail }),
      })
      setMagicState("sent")
    } catch {
      // Único erro possível aqui é falha de rede.
      setMagicState("error")
    }
  }

  async function handlePasswordLogin(e: React.FormEvent) {
    e.preventDefault()
    if (!email || !password) return
    setSubmitting(true)
    setLoginError(null)
    try {
      const res = await portalFetch<PortalTokenResponse>("/portal/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      })
      setPortalToken(res.access_token)
      router.push("/portal/dashboard")
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      setLoginError(
        status === 401
          ? "E-mail ou senha incorretos."
          : "Não foi possível entrar. Tente novamente.",
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PortalAuthShell>
      <div className="rounded-xl bg-card p-6 ring-1 ring-foreground/10">
        <h1 className="font-display text-2xl tracking-wide text-foreground">Acesse sua conta</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Use o link mágico ou entre com e-mail e senha.
        </p>

        {/* Toggle de modo — controle segmentado (não há Tabs segmentado no projeto) */}
        <div className="mt-5 grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
          <button
            type="button"
            onClick={() => setMode("magic")}
            className={cn(
              "flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
              mode === "magic"
                ? "bg-background font-medium text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Mail size={14} strokeWidth={1.5} /> Magic link
          </button>
          <button
            type="button"
            onClick={() => setMode("password")}
            className={cn(
              "flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
              mode === "password"
                ? "bg-background font-medium text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <KeyRound size={14} strokeWidth={1.5} /> E-mail e senha
          </button>
        </div>

        {mode === "magic" ? (
          magicState === "sent" ? (
            <div className="mt-5 rounded-lg border border-primary/30 bg-primary/5 p-4">
              <div className="flex items-center gap-2 text-foreground">
                <MailCheck size={16} strokeWidth={1.5} className="text-primary" />
                <p className="text-sm font-medium">Link enviado</p>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                Se houver uma conta com esse e-mail, enviamos um link de acesso. Confira
                sua caixa de entrada.
              </p>
              <button
                type="button"
                onClick={() => {
                  setMagicState("idle")
                  setMagicEmail("")
                }}
                className="mt-3 text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                Enviar para outro e-mail
              </button>
            </div>
          ) : (
            <form onSubmit={handleMagicLink} className="mt-5 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="magic-email">E-mail</Label>
                <Input
                  id="magic-email"
                  type="email"
                  required
                  placeholder="seu@email.com"
                  value={magicEmail}
                  onChange={(e) => setMagicEmail(e.target.value)}
                  disabled={magicState === "sending"}
                  className="h-10"
                />
              </div>
              {magicState === "error" && (
                <p className="text-sm text-destructive">
                  Não foi possível enviar o link. Verifique sua conexão e tente novamente.
                </p>
              )}
              <Button type="submit" className="h-10 w-full" disabled={magicState === "sending"}>
                {magicState === "sending" ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Enviando…
                  </>
                ) : (
                  "Enviar link"
                )}
              </Button>
            </form>
          )
        ) : (
          <form onSubmit={handlePasswordLogin} className="mt-5 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="login-email">E-mail</Label>
              <Input
                id="login-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                className="h-10"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="login-password">Senha</Label>
              <Input
                id="login-password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
                className="h-10"
              />
            </div>
            {loginError && <p className="text-sm text-destructive">{loginError}</p>}
            <Button type="submit" className="h-10 w-full" disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Entrando…
                </>
              ) : (
                "Entrar"
              )}
            </Button>
          </form>
        )}
      </div>
    </PortalAuthShell>
  )
}

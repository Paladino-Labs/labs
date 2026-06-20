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
type View = "login" | "register"
type MagicState = "idle" | "sending" | "sent" | "error"
type RegisterState = "idle" | "submitting" | "done"

export default function PortalLoginPage() {
  const router = useRouter()
  const [view, setView] = useState<View>("login")
  const [mode, setMode] = useState<Mode>("magic")

  // Magic link
  const [magicEmail, setMagicEmail] = useState("")
  const [magicState, setMagicState] = useState<MagicState>("idle")

  // E-mail + senha
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)

  // Criar conta
  const [regName, setRegName] = useState("")
  const [regPhone, setRegPhone] = useState("")
  const [regEmail, setRegEmail] = useState("")
  const [regPassword, setRegPassword] = useState("")
  const [regState, setRegState] = useState<RegisterState>("idle")
  const [regError, setRegError] = useState<string | null>(null)
  const [regHistory, setRegHistory] = useState(false)

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    setRegError(null)
    // Espelha a regra do backend para um erro imediato e claro.
    if (regPassword.length < 8 || !/[A-Z]/.test(regPassword) || !/[0-9]/.test(regPassword)) {
      setRegError("A senha deve ter no mínimo 8 caracteres, 1 maiúscula e 1 número.")
      return
    }
    setRegState("submitting")
    try {
      const res = await portalFetch<{ has_existing_history: boolean; message: string }>(
        "/portal/auth/register",
        {
          method: "POST",
          body: JSON.stringify({
            name: regName,
            phone: regPhone,
            email: regEmail,
            password: regPassword,
          }),
        },
      )
      setRegHistory(res.has_existing_history)
      setRegState("done")
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      const message = (err as Error).message
      setRegError(
        status === 409
          ? "Já existe uma conta com este e-mail ou telefone."
          : status === 422
            ? (message || "Verifique os dados (telefone com DDD e senha forte).")
            : "Não foi possível criar a conta. Tente novamente.",
      )
      setRegState("idle")
    }
  }

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
      {view === "login" ? (
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

        <p className="mt-5 text-center text-sm text-muted-foreground">
          Não tem conta?{" "}
          <button
            type="button"
            onClick={() => setView("register")}
            className="font-medium text-foreground underline-offset-2 hover:underline"
          >
            Criar conta
          </button>
        </p>
      </div>
      ) : (
      <div className="rounded-xl bg-card p-6 ring-1 ring-foreground/10">
        {regState === "done" ? (
          <div>
            <div className="flex items-center gap-2 text-foreground">
              <MailCheck size={16} strokeWidth={1.5} className="text-primary" />
              <p className="text-sm font-medium">Conta criada</p>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Enviamos um link para confirmar seu e-mail. Confira sua caixa de entrada
              para ativar o acesso.
            </p>
            {regHistory && (
              <p className="mt-2 text-sm text-muted-foreground">
                Encontramos um histórico de atendimentos associado a este telefone — ele
                foi vinculado à sua nova conta.
              </p>
            )}
            <Button
              className="mt-4 h-10 w-full"
              onClick={() => { setView("login"); setRegState("idle") }}
            >
              Ir para o login
            </Button>
          </div>
        ) : (
          <>
            <h1 className="font-display text-2xl tracking-wide text-foreground">Criar conta</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Cadastre-se para acompanhar seus agendamentos e histórico.
            </p>

            <form onSubmit={handleRegister} className="mt-5 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="reg-name">Nome</Label>
                <Input
                  id="reg-name"
                  required
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  disabled={regState === "submitting"}
                  className="h-10"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="reg-phone">Telefone (com DDD)</Label>
                <Input
                  id="reg-phone"
                  type="tel"
                  required
                  placeholder="(11) 91234-5678"
                  value={regPhone}
                  onChange={(e) => setRegPhone(e.target.value)}
                  disabled={regState === "submitting"}
                  className="h-10"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="reg-email">E-mail</Label>
                <Input
                  id="reg-email"
                  type="email"
                  required
                  placeholder="seu@email.com"
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  disabled={regState === "submitting"}
                  className="h-10"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="reg-password">Senha</Label>
                <Input
                  id="reg-password"
                  type="password"
                  required
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                  disabled={regState === "submitting"}
                  className="h-10"
                />
                <p className="text-xs text-muted-foreground">
                  Mínimo de 8 caracteres, com 1 maiúscula e 1 número.
                </p>
              </div>
              {regError && <p className="text-sm text-destructive">{regError}</p>}
              <Button type="submit" className="h-10 w-full" disabled={regState === "submitting"}>
                {regState === "submitting" ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Criando…
                  </>
                ) : (
                  "Criar conta"
                )}
              </Button>
            </form>

            <p className="mt-4 text-center text-sm text-muted-foreground">
              Já tem conta?{" "}
              <button
                type="button"
                onClick={() => { setView("login"); setRegError(null) }}
                className="font-medium text-foreground underline-offset-2 hover:underline"
              >
                Entrar
              </button>
            </p>
          </>
        )}
      </div>
      )}
    </PortalAuthShell>
  )
}

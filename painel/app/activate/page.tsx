"use client"

import { Suspense, useState } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

function validatePassword(pwd: string): string | null {
  if (pwd.length < 8) return "Mínimo 8 caracteres."
  if (!/[A-Z]/.test(pwd)) return "Deve conter ao menos 1 letra maiúscula."
  if (!/\d/.test(pwd)) return "Deve conter ao menos 1 número."
  return null
}

export default function ActivatePage() {
  return (
    <Suspense>
      <ActivateContent />
    </Suspense>
  )
}

function ActivateContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get("token") ?? ""
  const { login } = useAuth()

  const [name, setName] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tokenInvalid, setTokenInvalid] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const pwdErr = validatePassword(password)
    if (pwdErr) { setError(pwdErr); return }
    if (password !== confirm) { setError("As senhas não coincidem."); return }
    setError(null)
    setLoading(true)
    try {
      const body: Record<string, string> = { token, password, password_confirm: confirm }
      if (name.trim()) body.name = name.trim()
      const data = await api.post<{ access_token: string; token_type: string }>(
        "/auth/activate",
        body,
      )
      localStorage.setItem("token", data.access_token)
      login(data.access_token)
      router.replace("/dashboard")
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      if (status === 400 || status === 404 || status === 410) {
        setTokenInvalid(true)
      } else {
        setError((err as Error).message ?? "Erro ao ativar conta.")
      }
    } finally {
      setLoading(false)
    }
  }

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="text-center space-y-3">
          <p className="text-sm text-muted-foreground">
            Link de convite inválido.
          </p>
          <Link
            href="/"
            className="text-sm text-primary hover:underline"
          >
            ← Voltar ao login
          </Link>
        </div>
      </div>
    )
  }

  if (tokenInvalid) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="text-center space-y-4 max-w-sm">
          <p className="text-sm text-destructive">
            Este convite é inválido ou já foi utilizado.
          </p>
          <Link
            href="/"
            className="block text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Voltar ao login
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        <div>
          <h2 className="font-display text-3xl">Criar sua conta</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Você foi convidado. Configure sua senha para começar.
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="name">Seu nome <span className="text-muted-foreground">(opcional)</span></Label>
            <Input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              placeholder="Como prefere ser chamado"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="pwd">Senha</Label>
            <Input
              id="pwd"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              placeholder="Mínimo 8 caracteres, 1 maiúscula, 1 número"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="confirm">Confirmar senha</Label>
            <Input
              id="confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "Ativando…" : "Ativar conta"}
          </Button>
          <p className="text-center">
            <Link
              href="/"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              ← Voltar ao login
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}

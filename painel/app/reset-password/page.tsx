"use client"

import { Suspense, useState } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

function validatePassword(pwd: string): string | null {
  if (pwd.length < 8) return "Mínimo 8 caracteres."
  if (!/[A-Z]/.test(pwd)) return "Deve conter ao menos 1 letra maiúscula."
  if (!/\d/.test(pwd)) return "Deve conter ao menos 1 número."
  return null
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPasswordContent />
    </Suspense>
  )
}

function ResetPasswordContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get("token") ?? ""

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
      await api.post("/auth/reset-password", { token, new_password: password })
      router.replace("/?reset=ok")
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      if (status === 400 || status === 404 || status === 410 || status === 422) {
        setTokenInvalid(true)
      } else {
        setError((err as Error).message ?? "Erro ao redefinir senha.")
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
            Link de recuperação inválido.
          </p>
          <Link
            href="/forgot-password"
            className="text-sm text-primary hover:underline"
          >
            Solicitar novo link
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
            Este link de recuperação é inválido ou já expirou.
          </p>
          <Link
            href="/forgot-password"
            className="block text-sm text-primary hover:underline"
          >
            Solicitar novo link
          </Link>
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
          <h2 className="font-display text-3xl">Nova senha</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Escolha uma senha segura para sua conta
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="pwd">Nova senha</Label>
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
            {loading ? "Salvando…" : "Redefinir senha"}
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

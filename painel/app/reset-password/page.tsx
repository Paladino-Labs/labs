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
  const urlToken = searchParams.get("token") ?? ""

  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // O e-mail entrega um código de 6 dígitos (sem link). Se a URL trouxer ?token=
  // (fluxo de link), usa esse valor; senão, usa o código digitado manualmente.
  const token = urlToken || code.trim()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!token) { setError("Informe o código recebido por e-mail."); return }
    const pwdErr = validatePassword(password)
    if (pwdErr) { setError(pwdErr); return }
    if (password !== confirm) { setError("As senhas não coincidem."); return }
    setError(null)
    setLoading(true)
    try {
      await api.post("/auth/reset-password", {
        token,
        new_password: password,
        new_password_confirm: confirm,
      })
      router.replace("/?reset=ok")
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      if (status === 400 || status === 404 || status === 410) {
        setError("Código inválido ou expirado.")
      } else if (status === 422) {
        setError((err as Error).message ?? "Verifique os dados informados.")
      } else {
        setError((err as Error).message ?? "Erro ao redefinir senha.")
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        <div>
          <h2 className="font-display text-3xl">Nova senha</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {urlToken
              ? "Escolha uma senha segura para sua conta"
              : "Informe o código enviado ao seu e-mail e escolha uma nova senha."}
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {!urlToken && (
            <div className="space-y-1">
              <Label htmlFor="code">Código de verificação</Label>
              <Input
                id="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                required
                placeholder="000000"
              />
              <p className="text-xs text-muted-foreground">
                Código de 6 dígitos enviado ao seu e-mail.
              </p>
            </div>
          )}
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
          <div className="flex flex-col items-center gap-1.5">
            <Link
              href="/forgot-password"
              className="text-sm text-primary hover:underline"
            >
              Solicitar novo código
            </Link>
            <Link
              href="/"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              ← Voltar ao login
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}

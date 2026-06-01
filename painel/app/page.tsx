"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Sparkles } from "lucide-react"
import { useAuth } from "@/hooks/useAuth"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function LoginPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { token, hydrated, login } = useAuth()

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const resetOk = searchParams.get("reset") === "ok"

  useEffect(() => {
    if (hydrated && token) {
      router.replace("/dashboard")
    }
  }, [hydrated, token, router])

  async function handleLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const data = await api.post<{ access_token: string }>("/auth/login", {
        email,
        password,
      })
      login(data.access_token)
      router.replace("/dashboard")
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      setError(
        status === 401
          ? "E-mail ou senha inválidos."
          : "Erro ao conectar. Verifique se o servidor está rodando."
      )
    } finally {
      setLoading(false)
    }
  }

  if (!hydrated) return null
  if (token) return null

  return (
    <div className="grid min-h-screen lg:grid-cols-2">

      {/* Esquerda — só desktop */}
      <div className="hidden flex-col justify-between bg-sidebar p-12 lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Sparkles className="h-4 w-4" />
          </div>
          <span className="font-display text-2xl tracking-wider">PALADINO</span>
        </div>
        <div>
          <h1 className="font-display text-5xl leading-tight">
            Sua agenda,<br />sua equipe,<br />seu caixa.
          </h1>
          <p className="mt-4 max-w-sm text-muted-foreground">
            Tudo em um painel feito para barbearias. Sem planilhas, sem atrito.
          </p>
        </div>
        <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} Paladino</p>
      </div>

      {/* Direita — form */}
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm space-y-6">
          <div>
            <h2 className="font-display text-3xl">Entrar</h2>
            <p className="mt-1 text-sm text-muted-foreground">Acesse o painel da sua barbearia</p>
          </div>
          {resetOk && (
            <p className="text-sm text-green-600 dark:text-green-400 rounded-md border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950 px-3 py-2">
              Senha redefinida com sucesso. Faça login com a nova senha.
            </p>
          )}
          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="email">E-mail</Label>
              <Input
                id="email"
                type="email"
                placeholder="admin@barbearia.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Senha</Label>
                <Link
                  href="/forgot-password"
                  className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  Esqueci minha senha
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>

            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Entrando…" : "Entrar"}
            </Button>
          </form>
        </div>
      </div>

    </div>
  )
}

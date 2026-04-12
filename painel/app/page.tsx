"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export default function LoginPage() {
  const router = useRouter()
  const { token, hydrated, login } = useAuth()

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Redireciona usuário já autenticado — só depois da hidratação
  useEffect(() => {
    if (hydrated && token) {
      router.replace("/dashboard")
    }
  }, [hydrated, token, router])

  // handleLogin declarado ANTES de qualquer return condicional
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

  // Aguarda hidratação — evita flash do formulário para usuário já logado
  if (!hydrated) return null

  // Usuário logado — aguarda redirect do useEffect
  if (token) return null

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-2xl font-bold">Paladino Labs</CardTitle>
        </CardHeader>
        <CardContent>
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
              <Label htmlFor="password">Senha</Label>
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

            {/* native button — não depende do shadcn Button propagar type="submit" */}
            <button
              type="submit"
              disabled={loading}
              className="w-full h-8 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:pointer-events-none"
            >
              {loading ? "Entrando…" : "Entrar"}
            </button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

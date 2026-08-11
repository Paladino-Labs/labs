"use client"

import { useState } from "react"
import Link from "next/link"
import { api } from "@/lib/api"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await api.post("/auth/forgot-password", { email })
    } catch {
      // deliberadamente ignorado — não revelar se o e-mail está cadastrado
    } finally {
      setLoading(false)
      setSubmitted(true)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        <div>
          <h2 className="font-display text-3xl">Recuperar senha</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Informe seu e-mail cadastrado
          </p>
        </div>

        {submitted ? (
          <div className="space-y-4">
            <p className="text-sm rounded-md border border-border bg-card px-4 py-3">
              Se esse e-mail estiver cadastrado, você receberá um{" "}
              <strong>código de 6 dígitos</strong> em instantes. Ele vale por 15
              minutos.
            </p>
            {/* O backend envia um CÓDIGO, não um link — sem este CTA o fluxo
                terminava aqui, anunciando sucesso para algo que não concluía:
                /reset-password existia e não era alcançável por nenhum caminho. */}
            <Link
              href="/reset-password"
              className={cn(buttonVariants(), "w-full")}
            >
              Já tenho o código
            </Link>
            <p className="text-center">
              <Link
                href="/"
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                ← Voltar ao login
              </Link>
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
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
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Enviando…" : "Enviar código de recuperação"}
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
        )}
      </div>
    </div>
  )
}

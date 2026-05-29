"use client"

import { useState } from "react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

// ─── Validação client-side ────────────────────────────────────────────────────

function validatePassword(password: string): string | null {
  if (password.length < 8) return "Mínimo 8 caracteres."
  if (!/[A-Z]/.test(password)) return "Deve conter pelo menos 1 letra maiúscula."
  if (!/[0-9]/.test(password)) return "Deve conter pelo menos 1 número."
  return null
}

// ─── Página ───────────────────────────────────────────────────────────────────

export default function SecurityPage() {
  const [form, setForm] = useState({
    current_password: "",
    new_password: "",
    new_password_confirm: "",
  })
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
    // Limpa erro do campo ao digitar
    if (fieldErrors[name]) {
      setFieldErrors((prev) => {
        const next = { ...prev }
        delete next[name]
        return next
      })
    }
  }

  function validate(): boolean {
    const errors: Record<string, string> = {}

    if (!form.current_password) {
      errors.current_password = "Informe a senha atual."
    }

    const pwdError = validatePassword(form.new_password)
    if (pwdError) errors.new_password = pwdError

    if (form.new_password !== form.new_password_confirm) {
      errors.new_password_confirm = "As senhas não coincidem."
    }

    setFieldErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return

    setSaving(true)
    setError(null)
    setSuccess(false)

    try {
      await api.post("/auth/change-password", form)
      setSuccess(true)
      setForm({ current_password: "", new_password: "", new_password_confirm: "" })
      setTimeout(() => setSuccess(false), 4000)
    } catch (err: unknown) {
      setError((err as Error).message ?? "Erro ao alterar senha.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-lg">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Segurança</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Altere sua senha de acesso.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Trocar senha</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">

            <div className="space-y-1.5">
              <Label htmlFor="current_password">Senha atual</Label>
              <Input
                id="current_password"
                name="current_password"
                type="password"
                value={form.current_password}
                onChange={handleChange}
                autoComplete="current-password"
              />
              {fieldErrors.current_password && (
                <p className="text-xs text-destructive">{fieldErrors.current_password}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="new_password">Nova senha</Label>
              <Input
                id="new_password"
                name="new_password"
                type="password"
                value={form.new_password}
                onChange={handleChange}
                autoComplete="new-password"
              />
              <p className="text-xs text-muted-foreground">
                Mínimo 8 caracteres, 1 maiúscula e 1 número.
              </p>
              {fieldErrors.new_password && (
                <p className="text-xs text-destructive">{fieldErrors.new_password}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="new_password_confirm">Confirmar nova senha</Label>
              <Input
                id="new_password_confirm"
                name="new_password_confirm"
                type="password"
                value={form.new_password_confirm}
                onChange={handleChange}
                autoComplete="new-password"
              />
              {fieldErrors.new_password_confirm && (
                <p className="text-xs text-destructive">{fieldErrors.new_password_confirm}</p>
              )}
            </div>

            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}

            {success && (
              <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
                Senha alterada com sucesso!
              </div>
            )}

            <div className="flex justify-end pt-2">
              <Button type="submit" disabled={saving} className="min-w-32">
                {saving ? "Salvando…" : "Alterar senha"}
              </Button>
            </div>

          </form>
        </CardContent>
      </Card>
    </div>
  )
}

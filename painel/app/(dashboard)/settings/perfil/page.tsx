"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

const ROLE_LABELS: Record<string, string> = {
  OWNER: "Proprietário",
  ADMIN: "Administrador",
  OPERATOR: "Operador",
  PROFESSIONAL: "Profissional",
}

interface MeResponse {
  name: string
  email: string
  role: string
}

export default function PerfilPage() {
  const { setName: setContextName } = useAuth()

  const [name, setName] = useState("")
  const [originalName, setOriginalName] = useState("")
  const [email, setEmail] = useState("")
  const [role, setRole] = useState("")
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<MeResponse>("/auth/me").then((data) => {
      setName(data.name ?? "")
      setOriginalName(data.name ?? "")
      setEmail(data.email ?? "")
      setRole(data.role ?? "")
    })
  }, [])

  const isDirty = name !== originalName

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!isDirty) return
    setLoading(true)
    setError(null)
    try {
      await api.patch("/auth/profile", { name })
      setOriginalName(name)
      setContextName(name)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err: unknown) {
      setError((err as Error).message ?? "Erro ao salvar.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h1 className="font-display text-3xl tracking-wide">Meu Perfil</h1>
        <p className="mt-1 text-sm text-muted-foreground">Suas informações de acesso</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Informações pessoais</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1">
              <Label htmlFor="name">Nome</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Seu nome"
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                value={email}
                readOnly
                className="text-muted-foreground cursor-default"
              />
              <p className="text-xs text-muted-foreground">(não editável)</p>
            </div>

            <div className="space-y-1">
              <Label>Papel</Label>
              <div>
                <Badge variant="secondary">
                  {ROLE_LABELS[role] ?? role}
                </Badge>
              </div>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center gap-3">
              <Button type="submit" disabled={!isDirty || loading}>
                {loading ? "Salvando…" : "Salvar"}
              </Button>
              {saved && (
                <span className="text-sm text-muted-foreground">Salvo ✓</span>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

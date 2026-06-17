"use client"

import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { ROLE_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

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
    try {
      await api.patch("/auth/profile", { name })
      setOriginalName(name)
      setContextName(name)
      toast.success("Perfil atualizado")
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <PageHeader eyebrow="Configurações" title="Meu Perfil" description="Suas informações de acesso." />

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

            <div className="flex items-center gap-3">
              <Button type="submit" disabled={!isDirty || loading}>
                {loading ? "Salvando…" : "Salvar"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

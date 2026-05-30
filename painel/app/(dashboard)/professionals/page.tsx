"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { api } from "@/lib/api"
import type { Professional } from "@/types"
import { cn } from "@/lib/utils"
import { AvatarInitials } from "@/components/avatar-initials"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"

const WEEK_LABELS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]

export default function ProfessionalsPage() {
  const router = useRouter()
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState("")

  async function fetchProfessionals() {
    try {
      const data = await api.get<Professional[]>("/professionals/")
      setProfessionals(data)
    } catch {
      setError("Erro ao carregar barbeiros.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProfessionals() }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.post("/professionals/", { name })
      setOpen(false)
      setName("")
      fetchProfessionals()
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function toggleActive(p: Professional) {
    try {
      await api.patch(`/professionals/${p.id}`, { active: !p.active })
      fetchProfessionals()
    } catch (err: unknown) {
      alert((err as Error).message)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-3xl tracking-wide">Barbeiros</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger render={<Button />}>
            + Novo Barbeiro
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Novo Barbeiro</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4 py-2">
              <div className="space-y-1">
                <Label htmlFor="p-name">Nome *</Label>
                <Input
                  id="p-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  placeholder="Ex: João Silva"
                />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
                <Button type="submit" disabled={saving}>{saving ? "Salvando…" : "Criar"}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Carregando…</p>
      ) : professionals.length === 0 ? (
        <p className="text-center text-muted-foreground py-12">Nenhum barbeiro cadastrado.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {professionals.map((p) => (
            <Card key={p.id}>
              <CardContent className="p-6 space-y-4">

                {/* Avatar + nome + horário */}
                <div className="flex items-center gap-4">
                  <AvatarInitials name={p.name} size="lg" />
                  <div>
                    <p className="font-semibold">{p.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {p.work_start ?? "—"} – {p.work_end ?? "—"}
                    </p>
                  </div>
                </div>

                {/* Especialidades */}
                <div className="flex flex-wrap gap-1">
                  {p.specialties && p.specialties.length > 0
                    ? p.specialties.map((s) => (
                        <Badge key={s} variant="secondary" className="text-[10px]">{s}</Badge>
                      ))
                    : <span className="text-[10px] text-muted-foreground opacity-50">Especialidades em breve</span>
                  }
                </div>

                {/* Dias da semana */}
                <div className="flex flex-wrap gap-1">
                  {p.working_days
                    ? WEEK_LABELS.map((l, i) => (
                        <span
                          key={l}
                          className={cn(
                            "flex h-6 w-8 items-center justify-center rounded text-[10px]",
                            p.working_days!.includes(i)
                              ? "bg-primary/15 text-primary"
                              : "bg-muted text-muted-foreground"
                          )}
                        >
                          {l}
                        </span>
                      ))
                    : <span className="text-[10px] text-muted-foreground opacity-50">Horários em breve</span>
                  }
                </div>

                {/* Comissão */}
                <div className="flex items-center justify-between border-t border-border pt-4">
                  <span className="text-xs text-muted-foreground">Comissão</span>
                  {p.commission_rate != null
                    ? <span className="[font-family:var(--font-display)] text-xl text-primary">{p.commission_rate}%</span>
                    : <span className="text-xs text-muted-foreground opacity-50">Em breve</span>
                  }
                </div>

                {/* Ações */}
                <div className="flex gap-2 pt-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1"
                    onClick={() => router.push(`/professionals/${p.id}`)}
                  >
                    Editar
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => toggleActive(p)}
                  >
                    {p.active ? "Desativar" : "Ativar"}
                  </Button>
                </div>

              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

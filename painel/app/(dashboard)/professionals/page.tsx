"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { UserCheck } from "lucide-react"
import { api } from "@/lib/api"
import type { Professional } from "@/types"
import { cn } from "@/lib/utils"
import { AvatarInitials } from "@/components/avatar-initials"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { ActiveBadge } from "@/components/ActiveBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"

const WEEK_LABELS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]

export default function ProfessionalsPage() {
  const router = useRouter()
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState("")
  const [busy, setBusy] = useState<string | null>(null)

  const fetchProfessionals = useCallback(async () => {
    setLoading(true); setLoadError(null)
    try {
      setProfessionals(await api.get<Professional[]>("/professionals/"))
    } catch (err: unknown) {
      setLoadError((err as Error).message ?? "Erro ao carregar barbeiros.")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchProfessionals() }, [fetchProfessionals])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post("/professionals/", { name })
      toast.success("Barbeiro criado")
      setOpen(false)
      setName("")
      fetchProfessionals()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao criar barbeiro")
    } finally {
      setSaving(false)
    }
  }

  async function toggleActive(p: Professional) {
    setBusy(p.id)
    try {
      await api.patch(`/professionals/${p.id}`, { active: !p.active })
      toast.success(p.active ? "Barbeiro desativado" : "Barbeiro ativado")
      fetchProfessionals()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao atualizar")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administração" title="Barbeiros" description="Equipe de profissionais da casa.">
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger render={<Button />}>+ Novo Barbeiro</DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Novo Barbeiro</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4 py-2">
              <div className="space-y-1">
                <Label htmlFor="p-name">Nome *</Label>
                <Input id="p-name" value={name} onChange={(e) => setName(e.target.value)} required placeholder="Ex: João Silva" />
              </div>
              <DialogFooter>
                <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
                <Button type="submit" disabled={saving || !name.trim()}>{saving ? "Salvando…" : "Criar"}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </PageHeader>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-56 w-full" />)}
        </div>
      ) : loadError ? (
        <ErrorState message={loadError} onRetry={fetchProfessionals} />
      ) : professionals.length === 0 ? (
        <EmptyState
          icon={<UserCheck size={28} strokeWidth={1.5} />}
          title="Nenhum barbeiro cadastrado"
          description="Cadastre o primeiro barbeiro da equipe."
          action={<Button onClick={() => setOpen(true)}>+ Novo Barbeiro</Button>}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {professionals.map((p) => (
            <Card key={p.id}>
              <CardContent className="p-6 space-y-4">

                {/* Avatar + nome + horário */}
                <div className="flex items-center gap-4">
                  <AvatarInitials name={p.name} size="lg" />
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{p.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {p.work_start ?? "—"} – {p.work_end ?? "—"}
                    </p>
                  </div>
                  <ActiveBadge active={p.active} />
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
                  <Button size="sm" variant="outline" className="flex-1" onClick={() => router.push(`/professionals/${p.id}`)}>
                    Editar
                  </Button>
                  <Button size="sm" variant="ghost" disabled={busy === p.id} onClick={() => toggleActive(p)}>
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

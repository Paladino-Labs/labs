"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Pencil, PowerOff } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { formatDateTime } from "@/lib/utils"
import type { Supplier } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { ActiveBadge } from "@/components/ActiveBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"

/* ------------------------------ Criar / editar ------------------------------ */
function SupplierDialog({ open, onOpenChange, onSaved, editing }: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onSaved: () => void
  editing: Supplier | null
}) {
  const [name, setName] = useState("")
  const [contact, setContact] = useState("")
  const [document, setDocument] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setName(editing?.name ?? "")
      setContact(editing?.contact ?? "")
      setDocument(editing?.document ?? "")
    }
  }, [open, editing])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const body = { name: name.trim(), contact: contact || null, document: document || null }
      if (editing) await api.patch(`/suppliers/${editing.id}`, body)
      else await api.post("/suppliers/", body)
      toast.success(editing ? "Fornecedor atualizado" : "Fornecedor criado")
      onOpenChange(false)
      onSaved()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar fornecedor")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{editing ? "Editar fornecedor" : "Novo fornecedor"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSave} className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="sup-name">Nome *</Label>
            <Input id="sup-name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={255} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sup-contact">Contato</Label>
            <Input id="sup-contact" value={contact} onChange={(e) => setContact(e.target.value)} placeholder="Telefone ou e-mail" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sup-doc">Documento</Label>
            <Input id="sup-doc" value={document} onChange={(e) => setDocument(e.target.value)} placeholder="CNPJ ou CPF" />
          </div>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" disabled={saving || !name.trim()}>{saving ? "Salvando…" : "Salvar"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ---------------------------------- Página ---------------------------------- */
export default function FornecedoresPage() {
  const { role } = useAuth()
  const canWrite = role === "OWNER" || role === "ADMIN"

  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showInactive, setShowInactive] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Supplier | null>(null)
  const [deactivateTarget, setDeactivateTarget] = useState<Supplier | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setSuppliers(await api.get<Supplier[]>(`/suppliers/?active=${showInactive ? "false" : "true"}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [showInactive])

  useEffect(() => { load() }, [load])

  async function handleDeactivate() {
    if (!deactivateTarget) return
    setBusy(deactivateTarget.id)
    try {
      await api.delete<Supplier>(`/suppliers/${deactivateTarget.id}`)
      toast.success("Fornecedor desativado")
      setDeactivateTarget(null)
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao desativar")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Financeiro" title="Fornecedores" description="Cadastro de fornecedores e desativação lógica.">
        {canWrite && <Button onClick={() => { setEditing(null); setDialogOpen(true) }}>+ Novo fornecedor</Button>}
      </PageHeader>

      <div className="flex items-center justify-end gap-2">
        <Label htmlFor="show-inactive" className="text-sm text-muted-foreground">Mostrar inativos</Label>
        <Switch id="show-inactive" checked={showInactive} onCheckedChange={setShowInactive} />
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : suppliers.length === 0 ? (
        <EmptyState title="Nenhum fornecedor" description="Cadastre o primeiro fornecedor." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Nome</th>
                <th className="px-4 py-3 text-left font-medium">Contato</th>
                <th className="px-4 py-3 text-left font-medium">Documento</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Criado</th>
                {canWrite && <th className="px-4 py-3 text-right font-medium">Ações</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {suppliers.map((s) => (
                <tr key={s.id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3 font-medium">{s.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{s.contact ?? "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{s.document ?? "—"}</td>
                  <td className="px-4 py-3"><ActiveBadge active={s.active} /></td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateTime(s.created_at)}</td>
                  {canWrite && (
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button size="icon-sm" variant="ghost" disabled={busy === s.id}
                          onClick={() => { setEditing(s); setDialogOpen(true) }}>
                          <Pencil className="h-4 w-4 text-muted-foreground" />
                        </Button>
                        {s.active && (
                          <Button size="sm" variant="ghost" disabled={busy === s.id} onClick={() => setDeactivateTarget(s)}>
                            <PowerOff className="h-3.5 w-3.5" /> Desativar
                          </Button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SupplierDialog open={dialogOpen} onOpenChange={setDialogOpen} onSaved={load} editing={editing} />

      <Dialog open={!!deactivateTarget} onOpenChange={(v) => !v && setDeactivateTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desativar fornecedor</DialogTitle>
            <DialogDescription>
              Desativar “{deactivateTarget?.name}”? Ele permanece no histórico, mas deixa de aparecer em novas seleções.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Voltar</DialogClose>
            <Button variant="destructive" onClick={handleDeactivate} disabled={busy === deactivateTarget?.id}>Desativar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

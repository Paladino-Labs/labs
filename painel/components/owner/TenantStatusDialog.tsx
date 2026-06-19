"use client"

import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"

type Action = "suspend" | "reactivate"

/**
 * Dialog de mudança de status do tenant. Suspender exige motivo (reason);
 * Reativar é uma confirmação simples. Em sucesso chama `onDone()`.
 */
export function TenantStatusDialog({
  open,
  onOpenChange,
  companyId,
  tenantName,
  action,
  onDone,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  companyId: string
  tenantName: string
  action: Action
  onDone: () => void
}) {
  const [reason, setReason] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (open) setReason("") }, [open])

  const isSuspend = action === "suspend"

  async function handleConfirm() {
    if (isSuspend && !reason.trim()) return
    setSaving(true)
    try {
      await api.patch(`/platform/tenants/${companyId}/status`, {
        status: isSuspend ? "SUSPENDED" : "ACTIVE",
        ...(isSuspend ? { reason: reason.trim() } : {}),
      })
      toast.success(isSuspend ? "Tenant suspenso" : "Tenant reativado")
      onOpenChange(false)
      onDone()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao alterar status")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isSuspend ? "Suspender tenant" : "Reativar tenant"}</DialogTitle>
          <DialogDescription>
            {isSuspend
              ? `Suspender ${tenantName} bloqueia o login do tenant e notifica o proprietário.`
              : `Reativar ${tenantName} restaura o acesso ao painel do tenant.`}
          </DialogDescription>
        </DialogHeader>
        {isSuspend && (
          <div className="space-y-1.5 py-1">
            <Label htmlFor="ts-reason">Motivo (obrigatório)</Label>
            <Textarea
              id="ts-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Descreva o motivo da suspensão…"
              rows={3}
            />
          </div>
        )}
        <DialogFooter>
          <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
          <Button
            variant={isSuspend ? "destructive" : "default"}
            onClick={handleConfirm}
            disabled={saving || (isSuspend && !reason.trim())}
          >
            {saving ? "Salvando…" : isSuspend ? "Suspender" : "Reativar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

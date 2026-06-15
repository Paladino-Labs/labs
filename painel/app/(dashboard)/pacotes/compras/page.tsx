"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { api } from "@/lib/api"
import { formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import type { PackagePurchase, Package, Customer } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { PackagePurchaseBadge } from "@/components/FsmBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

const STATUS_LABELS: Record<string, string> = {
  all: "Todos os status",
  PENDING_PAYMENT: "Pagamento pendente",
  ACTIVE: "Ativo",
  REVOKED: "Revogado",
}

export default function PackagePurchasesPage() {
  const [purchases, setPurchases] = useState<PackagePurchase[]>([])
  const [customerMap, setCustomerMap] = useState<Map<string, string>>(new Map())
  const [packageMap, setPackageMap] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [query, setQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const [detail, setDetail] = useState<PackagePurchase | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const data = await api.get<PackagePurchase[]>("/package-purchases")
      setPurchases(data)
      try {
        const [custs, pkgs] = await Promise.all([
          api.get<Customer[]>("/customers/"),
          api.get<Package[]>("/packages"),
        ])
        setCustomerMap(new Map(custs.map((c) => [c.id, c.name])))
        setPackageMap(new Map(pkgs.map((p) => [p.package_id, p.name])))
      } catch { /* nomes ficam como id */ }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => purchases.filter((p) => {
    if (statusFilter !== "all" && p.status !== statusFilter) return false
    if (query.trim()) {
      const name = (customerMap.get(p.customer_id) ?? p.customer_id).toLowerCase()
      if (!name.includes(query.trim().toLowerCase())) return false
    }
    return true
  }), [purchases, statusFilter, query, customerMap])

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Pacotes" title="Compras" description="Histórico de vendas de pacotes." />

      <div className="flex flex-wrap gap-4 rounded-lg border border-border bg-card p-4">
        <Input
          placeholder="Buscar cliente…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-xs flex-1"
        />
        <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
          <SelectTrigger className="w-56"><SelectValue>{STATUS_LABELS[statusFilter]}</SelectValue></SelectTrigger>
          <SelectContent>
            {Object.keys(STATUS_LABELS).map((s) => (
              <SelectItem key={s} value={s}>{STATUS_LABELS[s]}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : filtered.length === 0 ? (
        <EmptyState title="Nenhuma compra" description="Nenhuma compra de pacote para os filtros selecionados." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Data</th>
                <th className="px-4 py-3 text-left font-medium">Cliente</th>
                <th className="px-4 py-3 text-left font-medium">Pacote</th>
                <th className="px-4 py-3 text-right font-medium">Valor</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Pagamento</th>
                <th className="px-4 py-3 text-right font-medium">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((p) => (
                <tr
                  key={p.purchase_id}
                  className="cursor-pointer transition-colors hover:bg-muted/30"
                  onClick={() => setDetail(p)}
                >
                  <td className="px-4 py-3 text-muted-foreground">{formatDateTime(p.created_at)}</td>
                  <td className="px-4 py-3 font-medium">{customerMap.get(p.customer_id) ?? p.customer_id}</td>
                  <td className="px-4 py-3">{packageMap.get(p.package_id) ?? p.package_id}</td>
                  <td className="px-4 py-3 text-right">{formatBRLFromDecimal(p.total_price)}</td>
                  <td className="px-4 py-3"><PackagePurchaseBadge status={p.status} /></td>
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    {p.payment_id ? (
                      <Link href={`/payments/${p.payment_id}`} className="text-xs text-primary hover:underline">Ver</Link>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                    <Link href={`/customers/${p.customer_id}`} className="text-xs text-primary hover:underline">
                      Ver cotas
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Compra de pacote</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-2 py-1 text-sm">
              <DetailRow label="Cliente" value={customerMap.get(detail.customer_id) ?? detail.customer_id} />
              <DetailRow label="Pacote" value={packageMap.get(detail.package_id) ?? detail.package_id} />
              <DetailRow label="Valor" value={formatBRLFromDecimal(detail.total_price)} />
              <DetailRow label="Status" value={STATUS_LABELS[detail.status] ?? detail.status} />
              <DetailRow label="Data" value={formatDateTime(detail.created_at)} />
              {detail.activated_at && <DetailRow label="Ativado em" value={formatDateTime(detail.activated_at)} />}
            </div>
          )}
          <DialogFooter>
            {detail && (
              <Button variant="outline" render={<Link href={`/customers/${detail.customer_id}`} />}>Ver cotas</Button>
            )}
            <DialogClose render={<Button />}>Fechar</DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  )
}

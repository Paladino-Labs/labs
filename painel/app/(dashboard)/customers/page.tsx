"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Search } from "lucide-react"
import { api } from "@/lib/api"
import type { Customer } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { CrmBadge } from "@/components/FsmBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"

interface ClassificationOut {
  customer_id: string
  classification: string
  computed_at: string
}

const CLASSIFICATION_FILTERS = ["NOVO", "FREQUENTE", "VIP", "EM_RISCO", "RECUPERADO", "REGULAR"]
const EmReve = () => <span className="text-xs text-muted-foreground opacity-50">Em breve</span>

export default function CustomersPage() {
  const router = useRouter()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [classMap, setClassMap] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState("")
  const [classFilter, setClassFilter] = useState("all")

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<Customer[]>("/customers/")
      setCustomers(data)
      try {
        const classes = await api.get<ClassificationOut[]>("/crm/classifications")
        const m = new Map<string, string>()
        for (const c of classes) m.set(c.customer_id, c.classification)
        setClassMap(m)
      } catch { /* classificação opcional */ }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = customers.filter((c) => {
    const matchesQ =
      c.name.toLowerCase().includes(q.toLowerCase()) || c.phone.includes(q)
    const matchesClass =
      classFilter === "all" || classMap.get(c.id) === classFilter
    return matchesQ && matchesClass
  })

  return (
    <div className="space-y-6">
      <PageHeader title="Clientes" description={`${customers.length} cadastrados`}>
        <NewCustomerDialog onCreated={load} />
      </PageHeader>

      <div className="flex flex-wrap items-end gap-3">
        <div className="relative w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por nome ou telefone" className="pl-9" />
        </div>
        <div className="space-y-1">
          <Label>Classificação</Label>
          <Select value={classFilter} onValueChange={(v) => v && setClassFilter(v)}>
            <SelectTrigger className="w-44">
              <SelectValue>{classFilter === "all" ? "Todas" : classFilter}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas</SelectItem>
              {CLASSIFICATION_FILTERS.map((c) => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <div className="rounded-md border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>Telefone</TableHead>
                <TableHead>Última visita</TableHead>
                <TableHead>Classificação</TableHead>
                <TableHead>Ticket médio</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="p-0">
                    <EmptyState message={q || classFilter !== "all" ? "Nenhum cliente encontrado." : "Nenhum cliente cadastrado."} />
                  </TableCell>
                </TableRow>
              )}
              {filtered.map((c) => {
                const cls = classMap.get(c.id)
                return (
                  <TableRow
                    key={c.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/customers/${c.id}`)}
                  >
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-3">
                        <div className="h-9 w-9 rounded-full bg-primary/15 text-xs font-medium text-primary flex items-center justify-center flex-shrink-0 select-none">
                          {c.name.split(" ").slice(0, 2).map((p) => p[0]?.toUpperCase()).join("")}
                        </div>
                        <div>
                          <div>{c.name}</div>
                          {c.notes && (
                            <div className="text-xs text-muted-foreground mt-0.5 max-w-xs truncate line-clamp-1">{c.notes}</div>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-sm">{c.phone}</TableCell>
                    <TableCell><EmReve /></TableCell>
                    <TableCell>{cls ? <CrmBadge classification={cls} /> : <span className="text-muted-foreground">—</span>}</TableCell>
                    <TableCell><EmReve /></TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <Button size="sm" variant="outline" onClick={() => router.push(`/customers/${c.id}`)}>
                        Ficha
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

function NewCustomerDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState("")
  const [phone, setPhone] = useState("")
  const [email, setEmail] = useState("")

  async function handleCreate() {
    if (!name.trim() || !phone.trim()) { toast.error("Nome e telefone são obrigatórios."); return }
    setSaving(true)
    try {
      await api.post("/customers/", { name, phone, email: email || undefined })
      toast.success("Cliente criado")
      setOpen(false)
      setName(""); setPhone(""); setEmail("")
      onCreated()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao criar cliente")
    } finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>+ Novo cliente</DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Novo cliente</DialogTitle></DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="nc-name">Nome *</Label>
            <Input id="nc-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="nc-phone">Telefone *</Label>
            <Input id="nc-phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="(11) 99999-9999" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="nc-email">E-mail (opcional)</Label>
            <Input id="nc-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
          <Button onClick={handleCreate} disabled={saving}>{saving ? "Salvando…" : "Criar"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

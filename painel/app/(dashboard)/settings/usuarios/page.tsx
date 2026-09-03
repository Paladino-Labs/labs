"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { UserPlus, Crown, UserMinus, Mail, X, Pencil, Check, AlertTriangle } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { formatDateTime, formatPhoneBR } from "@/lib/utils"
import {
  ROLE_LABELS,
  ROLE_INVITE_HINTS,
  INVITATION_STATUS_LABELS,
  ASSIGNABLE_ROLES_BY_ACTOR,
} from "@/lib/constants"
import type { Professional } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { ActiveBadge } from "@/components/ActiveBadge"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

interface User {
  id: string
  company_id?: string | null
  email: string
  name?: string | null
  phone?: string | null
  role: string
  active: boolean
}

interface Invitation {
  invitation_id: string
  email: string
  phone?: string | null
  role: string
  status: string
  expires_at: string
  created_at: string
  invited_by_user_id: string
  company_id?: string | null
}

function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id
}

/**
 * `users.phone` é gravado em E.164 SEM o '+' ("5562985657312") — a convenção do
 * backend (models/user.py:70-75), a mesma para quem chega pelo convite e para
 * quem é editado aqui. Descarta o 55 antes de mascarar: `formatPhoneBR` corta em
 * 11 dígitos e truncaria o final. Mesmo tratamento de `prefillInvitePhone` em
 * professionals/[id].
 */
function stripBRCountryCode(raw?: string | null): string {
  const digits = (raw ?? "").replace(/\D/g, "")
  if (digits.startsWith("55") && (digits.length === 12 || digits.length === 13)) {
    return digits.slice(2)
  }
  return digits
}

function displayPhoneBR(raw?: string | null): string {
  const digits = stripBRCountryCode(raw)
  return digits ? formatPhoneBR(digits) : ""
}

/* ------------------------------ Convidar usuário ------------------------------ */
function InviteDialog({ open, onOpenChange, actorRole, onDone }: {
  open: boolean
  onOpenChange: (v: boolean) => void
  actorRole: string
  onDone: () => void
}) {
  // Papéis que este ator pode convidar (anti-escalonamento, espelha INVITE_PERMISSION).
  const allowed = ASSIGNABLE_ROLES_BY_ACTOR[actorRole] ?? []
  // Default no papel menos poderoso da lista — para OWNER, `allowed[0]` seria
  // OWNER, e um convite de proprietário por descuido é caro de desfazer.
  const defaultRole = allowed.includes("PROFESSIONAL") ? "PROFESSIONAL" : (allowed[0] ?? "")
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  // Obrigatório: o convite sai por WhatsApp, e sem telefone a pessoa fica sem o
  // caminho de acesso — foi assim que um barbeiro da Le Duc ficou sem entrar.
  const [phone, setPhone] = useState("")
  const [role, setRole] = useState(defaultRole)
  const [saving, setSaving] = useState(false)

  // 10 (fixo) ou 11 (celular) dígitos — mesmo universo que o backend aceita em
  // validate_user_phone_input. A validação de DDD (whitelist ANATEL) fica no
  // backend, fonte única; aqui só barramos o incompleto óbvio.
  const phoneDigits = phone.replace(/\D/g, "")
  const phoneValid = phoneDigits.length === 10 || phoneDigits.length === 11

  // Vínculo opcional com um cadastro de profissional (só faz sentido em PROFESSIONAL).
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [linkedProfId, setLinkedProfId] = useState("")

  useEffect(() => {
    if (open) { setEmail(""); setName(""); setPhone(""); setRole(defaultRole); setLinkedProfId("") }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // Carrega profissionais sem vínculo quando o Dialog abre.
  useEffect(() => {
    if (!open) return
    api.get<Professional[]>("/professionals/")
      .then((profs) => setProfessionals(profs.filter((p) => !p.user_id && p.active)))
      .catch(() => {})
  }, [open])

  const linkedProfLabel = linkedProfId
    ? (professionals.find((p) => p.id === linkedProfId)?.name ?? "")
    : ""

  async function handleInvite() {
    if (!email.trim() || !role || !phoneValid) return
    setSaving(true)
    try {
      const res = await api.post<{ expires_at: string }>("/users/invite", {
        email: email.trim(),
        phone: phoneDigits,
        role,
        ...(name.trim() ? { name: name.trim() } : {}),
        ...(role === "PROFESSIONAL" && linkedProfId && linkedProfId !== "__none__"
          ? { professional_id: linkedProfId }
          : {}),
      })
      toast.success(`Convite enviado — expira em ${formatDateTime(res.expires_at)}`)
      onOpenChange(false)
      onDone()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao enviar convite")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Mail className="h-4 w-4" /> Convidar usuário</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="inv-email">E-mail</Label>
            <Input id="inv-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="nome@empresa.com" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="inv-phone">WhatsApp</Label>
            <Input
              id="inv-phone"
              type="tel"
              inputMode="numeric"
              value={phone}
              onChange={(e) => setPhone(formatPhoneBR(e.target.value))}
              placeholder="(11) 90000-0000"
            />
            <p className="text-xs text-muted-foreground">
              {phone && !phoneValid
                ? "Informe DDD + número (10 ou 11 dígitos)."
                : "O convite é enviado por WhatsApp — é por aqui que a pessoa recebe o acesso."}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="inv-name">Nome (opcional)</Label>
            <Input id="inv-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Papel</Label>
            <Select value={role} onValueChange={(v) => v && setRole(v)}>
              <SelectTrigger className="w-full"><SelectValue>{ROLE_LABELS[role] ?? role}</SelectValue></SelectTrigger>
              <SelectContent>
                {allowed.map((r) => <SelectItem key={r} value={r}>{ROLE_LABELS[r] ?? r}</SelectItem>)}
              </SelectContent>
            </Select>
            {role && ROLE_INVITE_HINTS[role] && (
              <p className="text-xs text-muted-foreground">{ROLE_INVITE_HINTS[role]}</p>
            )}
          </div>
          {role === "PROFESSIONAL" && (
            <div className="space-y-1.5">
              <Label>
                Profissional vinculado{" "}
                <span className="text-muted-foreground text-xs">(opcional)</span>
              </Label>
              <Select value={linkedProfId} onValueChange={(v) => setLinkedProfId(v === "__none__" ? "" : (v ?? ""))}>
                <SelectTrigger className="w-full">
                  <span className={linkedProfId ? "text-foreground" : "text-muted-foreground"}>
                    {linkedProfId ? linkedProfLabel : "Selecionar profissional…"}
                  </span>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Nenhum (vincular depois)</SelectItem>
                  {professionals.map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {professionals.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  Todos os profissionais já têm conta vinculada.
                </p>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
          <Button onClick={handleInvite} disabled={saving || !email.trim() || !phoneValid}>
            {saving ? "Enviando…" : "Enviar convite"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ---------------------------- Transferir propriedade ---------------------------- */
function TransferDialog({ open, onOpenChange, members, onDone }: {
  open: boolean
  onOpenChange: (v: boolean) => void
  members: User[]
  onDone: () => void
}) {
  const candidates = members.filter((m) => m.active && m.role !== "OWNER")
  const [newOwner, setNewOwner] = useState("")
  const [confirm, setConfirm] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (open) { setNewOwner(""); setConfirm("") } }, [open])

  async function handleTransfer() {
    if (!newOwner || confirm !== "TRANSFERIR") return
    setSaving(true)
    try {
      await api.post("/users/transfer-ownership", {
        new_owner_user_id: newOwner,
        current_owner_new_role: "ADMIN",
      })
      toast.success("Propriedade transferida")
      onOpenChange(false)
      onDone()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao transferir propriedade")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Crown className="h-4 w-4" /> Transferir propriedade</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Você deixará de ser <strong>Proprietário</strong> e se tornará <strong>Administrador</strong>.
          Esta ação não pode ser desfeita sem o novo Proprietário.
        </p>
        <div className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label>Novo Proprietário</Label>
            <Select value={newOwner} onValueChange={(v) => v && setNewOwner(v)}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Selecione…">
                  {newOwner ? (candidates.find((c) => c.id === newOwner)?.name || candidates.find((c) => c.id === newOwner)?.email) : "Selecione…"}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {candidates.map((c) => (
                  <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tr-confirm">Digite <span className="font-mono">TRANSFERIR</span> para confirmar</Label>
            <Input id="tr-confirm" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
          <Button variant="destructive" onClick={handleTransfer} disabled={saving || !newOwner || confirm !== "TRANSFERIR"}>
            {saving ? "Transferindo…" : "Transferir"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------- Célula WhatsApp ------------------------------- */
/**
 * O telefone é o destino da escalada ("tem cliente esperando") e do reset de
 * senha. Ele era write-once no convite: quem não tinha caía no e-mail, e não
 * havia como consertar pela interface — este sprint existe por causa disso.
 *
 * Dois caminhos, os mesmos do backend:
 *   próprio usuário → PATCH /auth/profile
 *   terceiro        → PATCH /users/{id}/phone (OWNER/ADMIN, mesmo tenant)
 *
 * A validação de 10–11 dígitos aqui é a mesma do convite; a whitelist ANATEL de
 * DDD fica no backend, fonte única — daí a mensagem de erro vir de lá.
 */
function PhoneCell({ user, isSelf, canEdit, onSaved }: {
  user: User
  isSelf: boolean
  canEdit: boolean
  onSaved: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")
  const [saving, setSaving] = useState(false)

  const digits = draft.replace(/\D/g, "")
  // Vazio é válido: limpar um telefone digitado errado é caso legítimo.
  const valid = digits.length === 0 || digits.length === 10 || digits.length === 11

  function startEdit() {
    setDraft(displayPhoneBR(user.phone))
    setEditing(true)
  }

  async function save() {
    if (!valid) return
    setSaving(true)
    try {
      // Envia os dígitos crus; a normalização para E.164 sem '+' é do backend
      // (identity/resolver.normalize_phone_for_storage), a MESMA do convite.
      if (isSelf) {
        await api.patch("/auth/profile", { phone: digits || null })
      } else {
        await api.patch(`/users/${user.id}/phone`, { phone: digits || null })
      }
      toast.success(digits ? "WhatsApp atualizado" : "WhatsApp removido")
      setEditing(false)
      onSaved()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar o WhatsApp")
    } finally {
      setSaving(false)
    }
  }

  if (editing) {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-1">
          <Input
            autoFocus
            type="tel"
            inputMode="numeric"
            className="h-8 w-40"
            value={draft}
            onChange={(e) => setDraft(formatPhoneBR(e.target.value))}
            onKeyDown={(e) => {
              if (e.key === "Enter") save()
              if (e.key === "Escape") setEditing(false)
            }}
            placeholder="(11) 90000-0000"
          />
          <Button size="sm" variant="ghost" onClick={save} disabled={saving || !valid}
            aria-label="Salvar WhatsApp">
            <Check className="h-3.5 w-3.5" />
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={saving}
            aria-label="Cancelar">
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
        {!valid && (
          <p className="text-xs text-destructive">DDD + número (10 ou 11 dígitos).</p>
        )}
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1">
      {user.phone ? (
        <span className="text-muted-foreground">{displayPhoneBR(user.phone)}</span>
      ) : (
        // ⚠️ Não é um traço. Telefone ausente é a informação que o dono precisa
        // ver para agir — um "—" seria indistinguível de "não carregou".
        <Tooltip>
          <TooltipTrigger render={<span />}>
            <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-600 dark:text-amber-500">
              <AlertTriangle className="h-3.5 w-3.5" /> Sem WhatsApp
            </span>
          </TooltipTrigger>
          <TooltipContent>
            Sem WhatsApp, os avisos deste usuário — inclusive &quot;tem cliente
            esperando&quot; — saem por e-mail.
          </TooltipContent>
        </Tooltip>
      )}
      {canEdit && (
        <Button size="sm" variant="ghost" onClick={startEdit}
          aria-label={user.phone ? "Editar WhatsApp" : "Adicionar WhatsApp"}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  )
}

/* ---------------------------------- Página ---------------------------------- */
export default function UsuariosPage() {
  const { role: actorRole, userId } = useAuth()
  const isOwner = actorRole === "OWNER"
  const canInvite = actorRole === "OWNER" || actorRole === "ADMIN"

  const [users, setUsers] = useState<User[]>([])
  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const [inviteOpen, setInviteOpen] = useState(false)
  const [transferOpen, setTransferOpen] = useState(false)
  const [deactivateTarget, setDeactivateTarget] = useState<User | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [list, invs] = await Promise.all([
        api.get<User[]>("/users/"),
        api.get<Invitation[]>("/users/invitations").catch(() => [] as Invitation[]),
      ])
      setUsers(list)
      setInvitations(invs)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const assignableRoles = ASSIGNABLE_ROLES_BY_ACTOR[actorRole ?? ""] ?? []
  const activeOwners = useMemo(() => users.filter((u) => u.role === "OWNER" && u.active).length, [users])
  const pendingInvites = useMemo(() => invitations.filter((i) => i.status === "PENDING"), [invitations])

  async function handleChangeRole(user: User, newRole: string) {
    if (newRole === user.role) return
    setBusy(user.id)
    try {
      await api.patch(`/users/${user.id}/role`, { role: newRole })
      toast.success("Papel atualizado")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao alterar papel")
    } finally {
      setBusy(null)
    }
  }

  async function handleDeactivate() {
    if (!deactivateTarget) return
    setBusy(deactivateTarget.id)
    try {
      await api.delete(`/users/${deactivateTarget.id}`)
      toast.success("Usuário desativado")
      setDeactivateTarget(null)
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao desativar usuário")
    } finally {
      setBusy(null)
    }
  }

  async function handleCancelInvite(inv: Invitation) {
    setBusy(inv.invitation_id)
    try {
      await api.delete(`/users/invitations/${inv.invitation_id}`)
      toast.success("Convite cancelado")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao cancelar convite")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administração" title="Usuários e acessos" description="Quem tem acesso à plataforma e em qual papel.">
        {isOwner && (
          <Button variant="outline" onClick={() => setTransferOpen(true)}>
            <Crown className="h-4 w-4" /> Transferir propriedade
          </Button>
        )}
        {canInvite && (
          <Button onClick={() => setInviteOpen(true)}>
            <UserPlus className="h-4 w-4" /> Convidar usuário
          </Button>
        )}
      </PageHeader>

      {loading ? (
        <Skeleton className="h-72 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <Tabs defaultValue="members">
          <TabsList>
            <TabsTrigger value="members">Membros</TabsTrigger>
            <TabsTrigger value="invites">Convites pendentes ({pendingInvites.length})</TabsTrigger>
          </TabsList>

          {/* Membros */}
          <TabsContent value="members">
            {users.length === 0 ? (
              <EmptyState title="Nenhum membro" description="Convide o primeiro membro da equipe." />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">Nome</th>
                      <th className="px-4 py-3 text-left font-medium">E-mail</th>
                      <th className="px-4 py-3 text-left font-medium">WhatsApp</th>
                      <th className="px-4 py-3 text-left font-medium">Papel</th>
                      <th className="px-4 py-3 text-left font-medium">Ativo</th>
                      <th className="px-4 py-3 text-right font-medium">Ações</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {users.map((u) => {
                      const isSelf = u.id === userId
                      // Pode alterar o papel se: não é a própria linha, ator tem papéis atribuíveis,
                      // e o papel atual do alvo está dentro do que o ator gerencia.
                      const canManageRole = !isSelf && assignableRoles.length > 0 && (u.role !== "OWNER" || isOwner)
                      const roleOptions = Array.from(new Set([...assignableRoles, u.role]))
                      const isLastOwner = u.role === "OWNER" && u.active && activeOwners <= 1
                      const canDeactivate = !isSelf && u.active && !isLastOwner
                      // Espelha o gate do backend: o próprio usuário sempre pode
                      // (PATCH /auth/profile); para terceiro vale INVITE_PERMISSION
                      // — por isso ADMIN não alcança o telefone de um OWNER.
                      // Usuário inativo não é alvo (o service filtra active).
                      const canEditPhone = u.active && (isSelf || assignableRoles.includes(u.role))
                      const rowBusy = busy === u.id
                      return (
                        <tr key={u.id} className="transition-colors hover:bg-muted/30">
                          <td className="px-4 py-3 font-medium">{u.name || "—"}</td>
                          <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                          <td className="px-4 py-3">
                            <PhoneCell user={u} isSelf={isSelf} canEdit={canEditPhone} onSaved={load} />
                          </td>
                          <td className="px-4 py-3">
                            {canManageRole ? (
                              <Select value={u.role} onValueChange={(v) => v && handleChangeRole(u, v)} disabled={rowBusy}>
                                <SelectTrigger size="sm" className="w-40"><SelectValue>{ROLE_LABELS[u.role] ?? u.role}</SelectValue></SelectTrigger>
                                <SelectContent>
                                  {roleOptions.map((r) => <SelectItem key={r} value={r}>{ROLE_LABELS[r] ?? r}</SelectItem>)}
                                </SelectContent>
                              </Select>
                            ) : (
                              <Badge variant="outline">{ROLE_LABELS[u.role] ?? u.role}</Badge>
                            )}
                          </td>
                          <td className="px-4 py-3"><ActiveBadge active={u.active} /></td>
                          <td className="px-4 py-3">
                            <div className="flex justify-end">
                              {isSelf ? (
                                <span className="text-xs italic text-muted-foreground">Você</span>
                              ) : !u.active ? (
                                <span className="text-xs text-muted-foreground">—</span>
                              ) : canDeactivate ? (
                                <Button size="sm" variant="ghost" className="text-destructive" disabled={rowBusy}
                                  onClick={() => setDeactivateTarget(u)}>
                                  <UserMinus className="h-3.5 w-3.5" /> Desativar
                                </Button>
                              ) : isLastOwner ? (
                                <Tooltip>
                                  <TooltipTrigger render={<span />}>
                                    <Button size="sm" variant="ghost" className="text-destructive" disabled>
                                      <UserMinus className="h-3.5 w-3.5" /> Desativar
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Não é possível desativar o último Proprietário ativo.</TooltipContent>
                                </Tooltip>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>

          {/* Convites */}
          <TabsContent value="invites">
            {invitations.length === 0 ? (
              <EmptyState title="Nenhum convite" description="Convites enviados aparecem aqui." />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">E-mail</th>
                      <th className="px-4 py-3 text-left font-medium">Papel</th>
                      <th className="px-4 py-3 text-left font-medium">Status</th>
                      <th className="px-4 py-3 text-left font-medium">Expira</th>
                      <th className="px-4 py-3 text-left font-medium">Convidado por</th>
                      <th className="px-4 py-3 text-right font-medium">Ações</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {invitations.map((inv) => (
                      <tr key={inv.invitation_id} className="transition-colors hover:bg-muted/30">
                        <td className="px-4 py-3 font-medium">{inv.email}</td>
                        <td className="px-4 py-3 text-muted-foreground">{ROLE_LABELS[inv.role] ?? inv.role}</td>
                        <td className="px-4 py-3">
                          <Badge variant={inv.status === "PENDING" ? "default" : "secondary"}>
                            {INVITATION_STATUS_LABELS[inv.status] ?? inv.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{formatDateTime(inv.expires_at)}</td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{shortId(inv.invited_by_user_id)}</td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end">
                            {inv.status === "PENDING" && (
                              <Button size="sm" variant="ghost" disabled={busy === inv.invitation_id}
                                onClick={() => handleCancelInvite(inv)}>
                                <X className="h-3.5 w-3.5" /> Cancelar
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>
        </Tabs>
      )}

      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} actorRole={actorRole ?? ""} onDone={load} />
      <TransferDialog open={transferOpen} onOpenChange={setTransferOpen} members={users} onDone={load} />

      {/* Desativar */}
      <Dialog open={!!deactivateTarget} onOpenChange={(v) => !v && setDeactivateTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desativar usuário</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {deactivateTarget?.name || deactivateTarget?.email} perderá o acesso à plataforma. O cadastro é mantido (desativação).
          </p>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button variant="destructive" onClick={handleDeactivate} disabled={busy === deactivateTarget?.id}>
              Desativar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

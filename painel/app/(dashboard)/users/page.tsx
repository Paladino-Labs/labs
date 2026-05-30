"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

// ─── Tipos ────────────────────────────────────────────────────────────────────

interface User {
  id: string
  name: string
  email: string
  role: string
  active: boolean
}

const ROLE_LABELS: Record<string, string> = {
  OWNER: "Proprietário",
  ADMIN: "Administrador",
  OPERATOR: "Operador",
  PROFESSIONAL: "Profissional",
  CLIENT: "Cliente",
}

const ROLE_COLORS: Record<string, string> = {
  OWNER: "bg-purple-100 text-purple-800",
  ADMIN: "bg-blue-100 text-blue-800",
  OPERATOR: "bg-yellow-100 text-yellow-800",
  PROFESSIONAL: "bg-success/15 text-success",
  CLIENT: "bg-gray-100 text-gray-800",
}

// Roles que cada papel pode convidar (anti-escalonamento espelhado do backend)
const INVITE_OPTIONS: Record<string, string[]> = {
  OWNER: ["ADMIN", "OPERATOR", "PROFESSIONAL", "CLIENT"],
  ADMIN: ["OPERATOR", "PROFESSIONAL", "CLIENT"],
}

// ─── Modal de convite ─────────────────────────────────────────────────────────

function InviteModal({
  currentRole,
  onClose,
  onSuccess,
}: {
  currentRole: string
  onClose: () => void
  onSuccess: () => void
}) {
  const [email, setEmail] = useState("")
  const [role, setRole] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const availableRoles = INVITE_OPTIONS[currentRole] ?? []

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email || !role) return
    setSaving(true)
    setError(null)
    try {
      await api.post("/users/invite", { email, role })
      onSuccess()
      onClose()
    } catch (err: unknown) {
      setError((err as Error).message ?? "Erro ao enviar convite.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-background rounded-xl shadow-xl p-6 w-full max-w-md">
        <h2 className="text-lg font-semibold mb-4">Convidar usuário</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="invite-email">E-mail</Label>
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="usuario@exemplo.com"
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="invite-role">Papel</Label>
            <select
              id="invite-role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              required
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm
                ring-offset-background focus-visible:outline-none focus-visible:ring-2
                focus-visible:ring-ring"
            >
              <option value="">Selecione…</option>
              {availableRoles.map((r) => (
                <option key={r} value={r}>{ROLE_LABELS[r] ?? r}</option>
              ))}
            </select>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Enviando…" : "Enviar convite"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showInvite, setShowInvite] = useState(false)
  const [currentUser, setCurrentUser] = useState<{ role: string; id: string } | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [me, list] = await Promise.all([
        api.get<{ id: string; role: string }>("/auth/me"),
        api.get<User[]>("/users/"),
      ])
      setCurrentUser(me)
      setUsers(list)
    } catch (err: unknown) {
      setError((err as Error).message ?? "Erro ao carregar usuários.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  async function handleDeactivate(userId: string) {
    if (!confirm("Desativar este usuário?")) return
    setActionError(null)
    try {
      await api.delete(`/users/${userId}`)
      await loadData()
    } catch (err: unknown) {
      setActionError((err as Error).message ?? "Erro ao desativar usuário.")
    }
  }

  async function handleChangeRole(userId: string, newRole: string) {
    setActionError(null)
    try {
      await api.patch(`/users/${userId}/role`, { role: newRole })
      await loadData()
    } catch (err: unknown) {
      setActionError((err as Error).message ?? "Erro ao alterar papel.")
    }
  }

  // Papéis visíveis para OWNER (todos) e ADMIN (exceto OWNER)
  const visibleRoles = currentUser?.role === "OWNER"
    ? ["OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL", "CLIENT"]
    : ["OPERATOR", "PROFESSIONAL", "CLIENT"]

  const visibleUsers = users.filter((u) => visibleRoles.includes(u.role))
  const canInvite = currentUser && (currentUser.role === "OWNER" || currentUser.role === "ADMIN")

  if (loading) return <p className="text-muted-foreground">Carregando…</p>
  if (error) return <p className="text-destructive text-sm">{error}</p>

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl">Usuários</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Gerencie os membros da sua equipe.
          </p>
        </div>
        {canInvite && (
          <Button onClick={() => setShowInvite(true)}>Convidar</Button>
        )}
      </div>

      {actionError && (
        <p className="text-sm text-destructive mb-4">{actionError}</p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Membros da equipe</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {visibleUsers.length === 0 ? (
            <p className="text-sm text-muted-foreground px-6 py-4">
              Nenhum usuário encontrado.
            </p>
          ) : (
            <div className="divide-y">
              {visibleUsers.map((u) => (
                <div key={u.id} className="flex items-center justify-between px-6 py-4 gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{u.name || u.email}</p>
                    <p className="text-sm text-muted-foreground truncate">{u.email}</p>
                  </div>

                  <span
                    className={`text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap
                      ${ROLE_COLORS[u.role] ?? "bg-gray-100 text-gray-800"}`}
                  >
                    {ROLE_LABELS[u.role] ?? u.role}
                  </span>

                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      u.active
                        ? "bg-success/15 text-success"
                        : "bg-red-100 text-red-700"
                    }`}
                  >
                    {u.active ? "Ativo" : "Inativo"}
                  </span>

                  {/* Ações — não aparece sobre si mesmo */}
                  {currentUser && u.id !== currentUser.id && u.active && (
                    <div className="flex items-center gap-2 shrink-0">
                      {currentUser.role === "OWNER" && u.role !== "OWNER" && (
                        <select
                          value={u.role}
                          onChange={(e) => handleChangeRole(u.id, e.target.value)}
                          className="text-sm border rounded px-2 py-1 bg-background"
                        >
                          {["ADMIN", "OPERATOR", "PROFESSIONAL", "CLIENT"].map((r) => (
                            <option key={r} value={r}>{ROLE_LABELS[r] ?? r}</option>
                          ))}
                        </select>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-destructive border-destructive hover:bg-destructive/10"
                        onClick={() => handleDeactivate(u.id)}
                      >
                        Desativar
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {showInvite && currentUser && (
        <InviteModal
          currentRole={currentUser.role}
          onClose={() => setShowInvite(false)}
          onSuccess={loadData}
        />
      )}
    </div>
  )
}

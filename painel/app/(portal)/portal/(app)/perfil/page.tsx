"use client"

import { PortalPageHeader } from "@/components/portal/PortalPageHeader"

import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { portal } from "@/lib/portal-api"
import type { PortalIdentity } from "@/lib/portal-types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ErrorState"

type Load = "loading" | "ok" | "error"
type Save = "idle" | "saving" | "saved" | "error"

// Máscara pt-BR: (11) 98123-4567 / (11) 8123-4567
function maskPhone(value: string): string {
  const d = value.replace(/\D/g, "").slice(0, 11)
  if (d.length <= 2) return d.length ? `(${d}` : ""
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`
}

interface ProfileUpdateResponse {
  identity_id: string
  name: string | null
  email: string | null
  phone_e164: string
  email_verification_sent: boolean
}

export default function PortalPerfilPage() {
  const [state, setState] = useState<Load>("loading")
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")

  const [save, setSave] = useState<Save>("idle")
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  function load() {
    setState("loading")
    portal
      .get<PortalIdentity>("/portal/identity/me")
      .then((id) => {
        setName(id.name ?? "")
        setEmail(id.email ?? "")
        setPhone(id.phone_national_normalized ? maskPhone(id.phone_national_normalized) : "")
        setState("ok")
      })
      .catch(() => setState("error"))
  }

  useEffect(() => {
    load()
  }, [])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSave("saving")
    setSaveMsg(null)
    try {
      const res = await portal.patch<ProfileUpdateResponse>("/portal/profile", {
        name: name || null,
        email: email || null,
        phone: phone ? phone.replace(/\D/g, "") : null,
      })
      setSave("saved")
      setSaveMsg(
        res.email_verification_sent
          ? "Perfil salvo. Enviamos um link para confirmar seu novo e-mail."
          : "Perfil salvo.",
      )
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      const msg = (err as { message?: string }).message
      setSave("error")
      if (status === 409) {
        setSaveMsg(msg || "Telefone ou e-mail já vinculado a outra conta.")
      } else if (status === 422) {
        setSaveMsg(msg || "Verifique os dados informados (inclua o DDD no telefone).")
      } else {
        setSaveMsg("Não foi possível salvar. Tente novamente.")
      }
    }
  }

  return (
    <div className="space-y-6">
      <PortalPageHeader title="Perfil" />

      {state === "loading" && (
        <div className="max-w-lg space-y-4 rounded-xl bg-card p-6 ring-1 ring-foreground/10">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      )}
      {state === "error" && <ErrorState onRetry={load} />}
      {state === "ok" && (
        <form
          onSubmit={handleSave}
          className="max-w-lg space-y-4 rounded-xl bg-card p-6 ring-1 ring-foreground/10"
        >
          <div className="space-y-1.5">
            <Label htmlFor="profile-name">Nome</Label>
            <Input
              id="profile-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-10"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-email">E-mail</Label>
            <Input
              id="profile-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-10"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-phone">Telefone</Label>
            <Input
              id="profile-phone"
              inputMode="tel"
              value={phone}
              onChange={(e) => setPhone(maskPhone(e.target.value))}
              placeholder="(11) 98123-4567"
              className="h-10"
            />
          </div>

          <div>
            <Button type="submit" disabled={save === "saving"}>
              {save === "saving" ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Salvando…
                </>
              ) : (
                "Salvar"
              )}
            </Button>
            {saveMsg && (
              <p
                className={
                  save === "error"
                    ? "mt-2 text-sm text-destructive"
                    : "mt-2 text-sm text-muted-foreground"
                }
              >
                {saveMsg}
              </p>
            )}
          </div>
        </form>
      )}
    </div>
  )
}

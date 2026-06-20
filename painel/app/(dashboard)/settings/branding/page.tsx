"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { Camera, Check, Link2, Music2, Star, Upload, Loader2 } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { PageHeader } from "@/components/PageHeader"
import { ErrorState } from "@/components/ErrorState"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

// ─── Tipos das três fontes ────────────────────────────────────────────────────

interface Branding {
  branding_id: string
  company_id: string
  logo_url?: string | null
  primary_color?: string | null
  secondary_color?: string | null
  font_family?: string | null
  favicon_url?: string | null
  custom_texts: Record<string, unknown>
}

interface CompanyProfile {
  tagline: string
  description: string
  logo_url: string
  cover_url: string
  gallery_urls: string[]
  address: string
  city: string
  whatsapp: string
  maps_url: string
  instagram_url: string
  facebook_url: string
  tiktok_url: string
  google_review_url: string
  business_hours: string
}

interface CompanyResponse {
  name?: string | null
  slug?: string | null
  settings?: { online_booking_enabled?: boolean } | null
}

const FONT_OPTIONS = ["Inter", "Roboto", "Open Sans", "Lato", "Montserrat", "Poppins", "Cormorant Garamond"]
const HEX_RE = /^#[0-9a-fA-F]{6}$/

const DEFAULT_PRIMARY = "#2A2A2A"
const DEFAULT_SECONDARY = "#C9A26B"

const EMPTY_PROFILE: CompanyProfile = {
  tagline: "", description: "", logo_url: "", cover_url: "",
  gallery_urls: [], address: "", city: "", whatsapp: "",
  maps_url: "", instagram_url: "", facebook_url: "",
  tiktok_url: "", google_review_url: "", business_hours: "",
}

// A API pode retornar null em qualquer campo opcional — normaliza para os defaults.
function normalizeProfile(data: Partial<Record<keyof CompanyProfile, string | string[] | null>>): CompanyProfile {
  return {
    tagline:           (data.tagline           as string  | null) ?? "",
    description:       (data.description       as string  | null) ?? "",
    logo_url:          (data.logo_url          as string  | null) ?? "",
    cover_url:         (data.cover_url         as string  | null) ?? "",
    gallery_urls:      (data.gallery_urls      as string[] | null) ?? [],
    address:           (data.address           as string  | null) ?? "",
    city:              (data.city              as string  | null) ?? "",
    whatsapp:          (data.whatsapp          as string  | null) ?? "",
    maps_url:          (data.maps_url          as string  | null) ?? "",
    instagram_url:     (data.instagram_url     as string  | null) ?? "",
    facebook_url:      (data.facebook_url      as string  | null) ?? "",
    tiktok_url:        (data.tiktok_url        as string  | null) ?? "",
    google_review_url: (data.google_review_url as string  | null) ?? "",
    business_hours:    (data.business_hours    as string  | null) ?? "",
  }
}

// ─── Helper de upload ─────────────────────────────────────────────────────────

async function uploadImage(file: File): Promise<string> {
  const fd = new FormData()
  fd.append("file", file)
  const res = await api.postForm<{ url: string }>("/uploads/", fd)
  return res.url
}

// ─── Página ───────────────────────────────────────────────────────────────────

export default function BrandingPage() {
  const { companyId } = useAuth()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Sobre a empresa
  const [name, setName] = useState("")
  const [profile, setProfile] = useState<CompanyProfile>(EMPTY_PROFILE)

  // Visual do painel
  const [primary, setPrimary] = useState(DEFAULT_PRIMARY)
  const [secondary, setSecondary] = useState(DEFAULT_SECONDARY)
  const [fontFamily, setFontFamily] = useState("Inter")
  const [logoPainel, setLogoPainel] = useState<string | null>(null)
  const [faviconUrl, setFaviconUrl] = useState<string | null>(null)
  const [uploadingLogoPainel, setUploadingLogoPainel] = useState(false)
  const [uploadingFavicon, setUploadingFavicon] = useState(false)

  const logoPainelRef = useRef<HTMLInputElement>(null)
  const faviconRef = useRef<HTMLInputElement>(null)

  // Vitrine pública — Agendamento Online (PATCHs próprios)
  const [slug, setSlug] = useState<string | null>(null)
  const [slugInput, setSlugInput] = useState("")
  const [onlineBookingEnabled, setOnlineBookingEnabled] = useState(false)
  const [savingSlug, setSavingSlug] = useState(false)
  const [bookingUrl, setBookingUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  // ── Carregamento inicial — Promise.all das três leituras ────────────────────
  const load = useCallback(async () => {
    if (!companyId) return
    setLoading(true); setError(null)
    try {
      const [branding, prof, company] = await Promise.all([
        api.get<Branding>(`/tenant/branding?company_id=${companyId}`),
        api.get<Partial<Record<keyof CompanyProfile, string | string[] | null>>>("/company/profile"),
        api.get<CompanyResponse>("/companies/me"),
      ])

      setPrimary(branding.primary_color && HEX_RE.test(branding.primary_color) ? branding.primary_color : DEFAULT_PRIMARY)
      setSecondary(branding.secondary_color && HEX_RE.test(branding.secondary_color) ? branding.secondary_color : DEFAULT_SECONDARY)
      setFontFamily(branding.font_family || "Inter")
      setLogoPainel(branding.logo_url ?? null)
      setFaviconUrl(branding.favicon_url ?? null)

      setProfile(normalizeProfile(prof))

      setName(company.name ?? "")
      setSlug(company.slug ?? null)
      setSlugInput(company.slug ?? "")
      setOnlineBookingEnabled(company.settings?.online_booking_enabled ?? false)
      if (company.slug) {
        api.get<{ booking_url: string }>(`/booking/${company.slug}/info`)
          .then((info) => setBookingUrl(info.booking_url))
          .catch(() => {})
      }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [companyId])

  useEffect(() => { load() }, [load])

  function setProfileField(field: keyof CompanyProfile) {
    return (value: string) => setProfile((prev) => ({ ...prev, [field]: value }))
  }

  function handleProfileInput(field: keyof CompanyProfile) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setProfile((prev) => ({ ...prev, [field]: e.target.value }))
  }

  // ── Upload de imagens do painel (logo + favicon) ────────────────────────────
  async function handlePainelUpload(file: File, kind: "logo" | "favicon") {
    const setUploading = kind === "logo" ? setUploadingLogoPainel : setUploadingFavicon
    setUploading(true)
    try {
      const url = await uploadImage(file)
      if (kind === "logo") setLogoPainel(url)
      else setFaviconUrl(url)
      toast.success(`${kind === "logo" ? "Logo" : "Favicon"} enviado`)
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao enviar arquivo")
    } finally {
      setUploading(false)
    }
  }

  // ── Salvar — Promise.all dos 3 destinos ─────────────────────────────────────
  async function handleSave() {
    if (!HEX_RE.test(primary) || !HEX_RE.test(secondary)) {
      toast.error("Cores devem estar no formato #RRGGBB")
      return
    }
    setSaving(true)
    try {
      await Promise.all([
        api.put<Branding>("/tenant/branding", {
          primary_color: primary,
          secondary_color: secondary,
          font_family: fontFamily,
          logo_url: logoPainel,
          favicon_url: faviconUrl,
        }),
        api.patch("/company/profile", {
          tagline:           profile.tagline           || null,
          description:       profile.description       || null,
          business_hours:    profile.business_hours    || null,
          logo_url:          profile.logo_url          || null,
          cover_url:         profile.cover_url         || null,
          gallery_urls:      profile.gallery_urls,
          address:           profile.address           || null,
          city:              profile.city              || null,
          whatsapp:          profile.whatsapp          || null,
          maps_url:          profile.maps_url          || null,
          instagram_url:     profile.instagram_url     || null,
          facebook_url:      profile.facebook_url      || null,
          tiktok_url:        profile.tiktok_url        || null,
          google_review_url: profile.google_review_url || null,
        }),
        api.patch("/companies/me", { company: { name: name.trim() || null } }),
      ])
      toast.success("Identidade salva")
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar")
    } finally {
      setSaving(false)
    }
  }

  // ── Agendamento Online (ações próprias) ─────────────────────────────────────
  async function handleSaveSlug() {
    const newSlug = slugInput.trim()
    if (!newSlug) return
    setSavingSlug(true)
    try {
      await api.patch("/companies/me", { company: { slug: newSlug } })
      setSlug(newSlug)
      api.get<{ booking_url: string }>(`/booking/${newSlug}/info`)
        .then((info) => setBookingUrl(info.booking_url))
        .catch(() => {})
      toast.success("Link salvo")
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao salvar link")
    } finally {
      setSavingSlug(false)
    }
  }

  async function handleToggleOnlineBooking() {
    const next = !onlineBookingEnabled
    try {
      await api.patch("/companies/me", { settings: { online_booking_enabled: next } })
      setOnlineBookingEnabled(next)
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao alterar agendamento online")
    }
  }

  function handleCopyLink() {
    if (!bookingUrl) return
    navigator.clipboard.writeText(bookingUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Configurações"
        title="Identidade da empresa"
        description="Dados, identidade visual do painel e vitrine pública da sua empresa."
      >
        <Button onClick={handleSave} disabled={saving || loading}>
          {saving ? "Salvando…" : "Salvar"}
        </Button>
      </PageHeader>

      {loading ? (
        <div className="space-y-6">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <div className="max-w-3xl space-y-6">

          {/* ── Sobre a empresa ──────────────────────────────────────────── */}
          <Card>
            <CardHeader><CardTitle className="text-base">Sobre a empresa</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-1.5">
                <Label htmlFor="name">Nome da empresa</Label>
                <Input id="name" value={name} onChange={(e) => setName(e.target.value)}
                  placeholder="Ex: Barbearia Paladino" />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="tagline">Slogan / Tagline</Label>
                <Input id="tagline" value={profile.tagline} onChange={handleProfileInput("tagline")}
                  placeholder="Ex: Tradição e estilo desde 2010" maxLength={180} />
                <p className="text-xs text-muted-foreground text-right">{profile.tagline.length}/180</p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="description">Descrição</Label>
                <Textarea id="description" value={profile.description} onChange={handleProfileInput("description")}
                  rows={4} placeholder="Conte um pouco sobre sua barbearia, diferenciais, história…" />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="business_hours">Horário de funcionamento</Label>
                <Input id="business_hours" value={profile.business_hours} onChange={handleProfileInput("business_hours")}
                  placeholder="Seg–Sex 9h–20h · Sáb 8h–18h" />
              </div>
            </CardContent>
          </Card>

          {/* ── Visual do painel ─────────────────────────────────────────── */}
          <Card>
            <CardHeader><CardTitle className="text-base">Visual do painel</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <ColorField label="Cor primária" value={primary} onChange={setPrimary} />
                <ColorField label="Cor secundária" value={secondary} onChange={setSecondary} />
              </div>

              <div className="space-y-1.5">
                <Label>Fonte</Label>
                <Select value={fontFamily} onValueChange={(v) => v && setFontFamily(v)}>
                  <SelectTrigger className="w-full"><SelectValue>{fontFamily}</SelectValue></SelectTrigger>
                  <SelectContent>
                    {FONT_OPTIONS.map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label>Logo no painel</Label>
                  <p className="text-xs text-muted-foreground">Exibido no menu lateral do painel.</p>
                  {logoPainel && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={logoPainel} alt="Logo no painel" className="h-12 w-auto rounded border border-border object-contain" />
                  )}
                  <input ref={logoPainelRef} type="file" accept="image/*" hidden
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) handlePainelUpload(f, "logo"); e.target.value = "" }} />
                  <Button variant="outline" size="sm" disabled={uploadingLogoPainel} onClick={() => logoPainelRef.current?.click()}>
                    {uploadingLogoPainel ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Enviar
                  </Button>
                </div>
                <div className="space-y-1.5">
                  <Label>Favicon</Label>
                  <p className="text-xs text-muted-foreground">Ícone da aba do navegador.</p>
                  {faviconUrl && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={faviconUrl} alt="Favicon" className="h-12 w-12 rounded border border-border object-contain" />
                  )}
                  <input ref={faviconRef} type="file" accept="image/*" hidden
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) handlePainelUpload(f, "favicon"); e.target.value = "" }} />
                  <Button variant="outline" size="sm" disabled={uploadingFavicon} onClick={() => faviconRef.current?.click()}>
                    {uploadingFavicon ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Enviar
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ── Vitrine pública ──────────────────────────────────────────── */}
          <Card>
            <CardHeader><CardTitle className="text-base">Vitrine pública</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <p className="text-xs text-muted-foreground">
                Imagens exibidas na página pública de agendamento dos seus clientes.
              </p>

              <div className="flex gap-6 flex-wrap">
                <ImageField
                  label="Logo na vitrine"
                  hint="Recomendado: quadrado, mín. 200×200px"
                  value={profile.logo_url}
                  onChange={setProfileField("logo_url")}
                  aspectClass="h-24 w-24 rounded-full"
                />
                <ImageField
                  label="Foto de capa"
                  hint="Recomendado: 1200×400px"
                  value={profile.cover_url}
                  onChange={setProfileField("cover_url")}
                  aspectClass="h-24 w-48 rounded-xl"
                  cover
                />
              </div>

              <GalleryField
                value={profile.gallery_urls}
                onChange={(urls) => setProfile((prev) => ({ ...prev, gallery_urls: urls }))}
              />

              {/* Agendamento Online (slug + toggle) — ações próprias */}
              <div className="space-y-4 border-t pt-5">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Link2 className="h-4 w-4" /> Agendamento Online
                </div>

                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">
                    Link personalizado da sua empresa (somente letras, números e hífen).
                  </p>
                  <div className="flex gap-2">
                    <Input
                      value={slugInput}
                      onChange={(e) => setSlugInput(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                      placeholder="minha-barbearia"
                    />
                    <Button type="button" size="sm" onClick={handleSaveSlug}
                      disabled={savingSlug || !slugInput.trim() || slugInput === slug}>
                      {savingSlug ? "Salvando…" : "Salvar link"}
                    </Button>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-sm text-muted-foreground">Agendamento online:</span>
                  <button
                    type="button"
                    onClick={handleToggleOnlineBooking}
                    disabled={!slug}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-40 ${
                      onlineBookingEnabled ? "bg-primary" : "bg-muted"
                    }`}
                    aria-label="Toggle online booking"
                  >
                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                      onlineBookingEnabled ? "translate-x-6" : "translate-x-1"
                    }`} />
                  </button>
                  <span className="text-sm font-medium">{onlineBookingEnabled ? "Ativado" : "Desativado"}</span>
                </div>
                {!slug && (
                  <p className="text-xs text-muted-foreground">
                    Configure o link personalizado acima para ativar o agendamento online.
                  </p>
                )}

                {bookingUrl && onlineBookingEnabled && (
                  <div className="rounded-lg bg-muted px-3 py-2 text-sm break-all flex items-center justify-between gap-2">
                    <span className="text-muted-foreground font-mono text-xs">{bookingUrl}</span>
                    <Button type="button" size="sm" variant="outline" onClick={handleCopyLink}>
                      {copied ? <><Check className="h-4 w-4" /> Copiado</> : "Copiar"}
                    </Button>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* ── Contato e localização ────────────────────────────────────── */}
          <Card>
            <CardHeader><CardTitle className="text-base">Contato e localização</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="city">Cidade</Label>
                  <Input id="city" value={profile.city} onChange={handleProfileInput("city")}
                    placeholder="Ex: Goiânia – GO" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="whatsapp">WhatsApp</Label>
                  <Input id="whatsapp" type="tel" value={profile.whatsapp} onChange={handleProfileInput("whatsapp")}
                    placeholder="5562999999999" />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="address">Endereço completo</Label>
                <Input id="address" value={profile.address} onChange={handleProfileInput("address")}
                  placeholder="Rua das Flores, 123 – Setor Central" />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="maps_url">Link do Google Maps</Label>
                <Input id="maps_url" type="url" value={profile.maps_url} onChange={handleProfileInput("maps_url")}
                  placeholder="https://maps.app.goo.gl/…" />
              </div>
            </CardContent>
          </Card>

          {/* ── Redes sociais ────────────────────────────────────────────── */}
          <Card>
            <CardHeader><CardTitle className="text-base">Redes sociais e avaliações</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="instagram_url">Instagram</Label>
                <div className="flex items-center gap-2">
                  <Camera className="h-4 w-4 text-muted-foreground" />
                  <Input id="instagram_url" type="url" value={profile.instagram_url} onChange={handleProfileInput("instagram_url")}
                    placeholder="https://instagram.com/suabarbearia" />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="facebook_url">Facebook</Label>
                <div className="flex items-center gap-2">
                  <Link2 className="h-4 w-4 text-muted-foreground" />
                  <Input id="facebook_url" type="url" value={profile.facebook_url} onChange={handleProfileInput("facebook_url")}
                    placeholder="https://facebook.com/suabarbearia" />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="tiktok_url">TikTok</Label>
                <div className="flex items-center gap-2">
                  <Music2 className="h-4 w-4 text-muted-foreground" />
                  <Input id="tiktok_url" type="url" value={profile.tiktok_url} onChange={handleProfileInput("tiktok_url")}
                    placeholder="https://tiktok.com/@suabarbearia" />
                </div>
              </div>

              <div className="space-y-1.5 pt-2 border-t">
                <Label htmlFor="google_review_url">Link para avaliação no Google</Label>
                <p className="text-xs text-muted-foreground">
                  Aparece como botão "Avaliar no Google" na página de agendamento.
                </p>
                <div className="flex items-center gap-2">
                  <Star className="h-4 w-4 text-muted-foreground" />
                  <Input id="google_review_url" type="url" value={profile.google_review_url} onChange={handleProfileInput("google_review_url")}
                    placeholder="https://g.page/r/…/review" />
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-end pb-8">
            <Button onClick={handleSave} disabled={saving} className="min-w-32">
              {saving ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Sub-componentes ──────────────────────────────────────────────────────────

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const valid = HEX_RE.test(value)
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={valid ? value : "#000000"}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-9 w-12 shrink-0 cursor-pointer rounded border border-border bg-transparent"
          aria-label={label}
        />
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          placeholder="#RRGGBB"
          maxLength={7}
          aria-invalid={!valid}
          className="font-mono"
        />
      </div>
      {!valid && <p className="text-xs text-destructive">Use o formato #RRGGBB</p>}
    </div>
  )
}

function ImageField({
  label, hint, value, onChange, aspectClass = "h-32 w-32", cover = false,
}: {
  label: string
  hint?: string
  value: string
  onChange: (url: string) => void
  aspectClass?: string
  cover?: boolean
}) {
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const url = await uploadImage(file)
      onChange(url)
    } catch (err: unknown) {
      toast.error("Erro ao enviar imagem: " + (err as Error).message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}

      {value ? (
        <div className="relative inline-block">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={value} alt={label} className={`${aspectClass} object-cover rounded-xl border`}
            style={{ maxWidth: cover ? "100%" : undefined }} />
          <button type="button" onClick={() => onChange("")}
            className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-destructive text-white
              flex items-center justify-center text-xs shadow hover:opacity-90 transition-opacity">
            ×
          </button>
        </div>
      ) : (
        <div
          onClick={() => fileRef.current?.click()}
          className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed
            border-muted-foreground/30 cursor-pointer hover:border-primary/50 transition-colors
            text-muted-foreground text-sm gap-1"
          style={{ height: cover ? 140 : 96, width: cover ? "100%" : 96 }}
        >
          <Camera className="h-6 w-6" />
          <span className="text-xs">Clique para enviar</span>
        </div>
      )}

      <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />

      {value && (
        <Button type="button" variant="outline" size="sm"
          onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? "Enviando…" : "Trocar imagem"}
        </Button>
      )}
      {uploading && !value && <p className="text-xs text-muted-foreground">Enviando…</p>}
    </div>
  )
}

function GalleryField({ value, onChange }: { value: string[]; onChange: (urls: string[]) => void }) {
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    if (!files.length) return
    if (value.length + files.length > 6) {
      toast.error("A galeria suporta no máximo 6 fotos.")
      return
    }
    setUploading(true)
    try {
      const urls = await Promise.all(files.map(uploadImage))
      onChange([...value, ...urls])
    } catch (err: unknown) {
      toast.error("Erro ao enviar imagem: " + (err as Error).message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  return (
    <div className="space-y-2">
      <Label>Galeria <span className="text-muted-foreground font-normal">(até 6 fotos)</span></Label>
      <p className="text-xs text-muted-foreground">Fotos do ambiente, trabalhos realizados, equipe, etc.</p>

      <div className="grid grid-cols-3 gap-2">
        {value.map((url, i) => (
          <div key={i} className="relative aspect-square">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={url} alt={`Foto ${i + 1}`} className="w-full h-full object-cover rounded-xl border" />
            <button type="button" onClick={() => onChange(value.filter((_, idx) => idx !== i))}
              className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-destructive text-white
                flex items-center justify-center text-xs shadow hover:opacity-90 transition-opacity">
              ×
            </button>
          </div>
        ))}

        {value.length < 6 && (
          <div onClick={() => fileRef.current?.click()}
            className="aspect-square flex flex-col items-center justify-center rounded-xl
              border-2 border-dashed border-muted-foreground/30 cursor-pointer
              hover:border-primary/50 transition-colors text-muted-foreground">
            <span className="text-2xl">+</span>
            <span className="text-xs mt-1">Adicionar</span>
          </div>
        )}
      </div>

      <input ref={fileRef} type="file" accept="image/*" multiple className="hidden" onChange={handleFile} />
      {uploading && <p className="text-xs text-muted-foreground">Enviando fotos…</p>}
    </div>
  )
}

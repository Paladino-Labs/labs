"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { Upload, Loader2 } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { PageHeader } from "@/components/PageHeader"
import { ErrorState } from "@/components/ErrorState"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

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

const FONT_OPTIONS = ["Inter", "Roboto", "Open Sans", "Lato", "Montserrat", "Poppins", "Cormorant Garamond"]
const HEX_RE = /^#[0-9a-fA-F]{6}$/

const DEFAULT_PRIMARY = "#2A2A2A"
const DEFAULT_SECONDARY = "#C9A26B"

export default function BrandingPage() {
  const { companyId } = useAuth()

  const [data, setData] = useState<Branding | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [primary, setPrimary] = useState(DEFAULT_PRIMARY)
  const [secondary, setSecondary] = useState(DEFAULT_SECONDARY)
  const [fontFamily, setFontFamily] = useState("Inter")
  const [logoUrl, setLogoUrl] = useState<string | null>(null)
  const [faviconUrl, setFaviconUrl] = useState<string | null>(null)
  const [uploadingLogo, setUploadingLogo] = useState(false)
  const [uploadingFavicon, setUploadingFavicon] = useState(false)

  const logoRef = useRef<HTMLInputElement>(null)
  const faviconRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    if (!companyId) return
    setLoading(true); setError(null)
    try {
      const b = await api.get<Branding>(`/tenant/branding?company_id=${companyId}`)
      setData(b)
      setPrimary(b.primary_color && HEX_RE.test(b.primary_color) ? b.primary_color : DEFAULT_PRIMARY)
      setSecondary(b.secondary_color && HEX_RE.test(b.secondary_color) ? b.secondary_color : DEFAULT_SECONDARY)
      setFontFamily(b.font_family || "Inter")
      setLogoUrl(b.logo_url ?? null)
      setFaviconUrl(b.favicon_url ?? null)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [companyId])

  useEffect(() => { load() }, [load])

  async function handleUpload(file: File, kind: "logo" | "favicon") {
    const setUploading = kind === "logo" ? setUploadingLogo : setUploadingFavicon
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const res = await api.postForm<{ url: string }>("/uploads/", fd)
      if (kind === "logo") setLogoUrl(res.url)
      else setFaviconUrl(res.url)
      toast.success(`${kind === "logo" ? "Logo" : "Favicon"} enviado`)
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao enviar arquivo")
    } finally {
      setUploading(false)
    }
  }

  async function handleSave() {
    if (!HEX_RE.test(primary) || !HEX_RE.test(secondary)) {
      toast.error("Cores devem estar no formato #RRGGBB")
      return
    }
    setSaving(true)
    try {
      const updated = await api.put<Branding>("/tenant/branding", {
        primary_color: primary,
        secondary_color: secondary,
        font_family: fontFamily,
        logo_url: logoUrl,
        favicon_url: faviconUrl,
      })
      setData(updated)
      toast.success("Identidade visual salva")
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Configurações" title="Branding" description="Personalize cores, fonte e logo da sua marca.">
        <Button onClick={handleSave} disabled={saving || loading}>
          {saving ? "Salvando…" : "Salvar"}
        </Button>
      </PageHeader>

      {loading ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-80 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Form */}
          <Card>
            <CardHeader><CardTitle className="text-base">Identidade visual</CardTitle></CardHeader>
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
                  <Label>Logo</Label>
                  {logoUrl && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={logoUrl} alt="Logo" className="h-12 w-auto rounded border border-border object-contain" />
                  )}
                  <input ref={logoRef} type="file" accept="image/*" hidden
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f, "logo"); e.target.value = "" }} />
                  <Button variant="outline" size="sm" disabled={uploadingLogo} onClick={() => logoRef.current?.click()}>
                    {uploadingLogo ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Enviar
                  </Button>
                </div>
                <div className="space-y-1.5">
                  <Label>Favicon</Label>
                  {faviconUrl && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={faviconUrl} alt="Favicon" className="h-12 w-12 rounded border border-border object-contain" />
                  )}
                  <input ref={faviconRef} type="file" accept="image/*" hidden
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f, "favicon"); e.target.value = "" }} />
                  <Button variant="outline" size="sm" disabled={uploadingFavicon} onClick={() => faviconRef.current?.click()}>
                    {uploadingFavicon ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Enviar
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Preview ao vivo (cores literais — objetivo da tela) */}
          <Card>
            <CardHeader><CardTitle className="text-base">Pré-visualização</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-hidden rounded-xl border border-border" style={{ fontFamily }}>
                <div className="flex items-center justify-between px-5 py-4" style={{ backgroundColor: primary }}>
                  <span className="text-lg font-semibold" style={{ color: "#fff" }}>
                    {logoUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={logoUrl} alt="Logo" className="h-7 w-auto object-contain" />
                    ) : "Sua Marca"}
                  </span>
                  <span className="rounded-md px-3 py-1.5 text-sm font-medium" style={{ backgroundColor: secondary, color: "#1a1a1a" }}>
                    Agendar
                  </span>
                </div>
                <div className="bg-white px-5 py-6">
                  <h3 className="text-xl font-semibold" style={{ color: "#1a1a1a" }}>Bem-vindo ao painel</h3>
                  <p className="mt-1 text-sm" style={{ color: "#555" }}>Este é um cartão de exemplo com sua identidade aplicada.</p>
                  <span className="mt-4 inline-block rounded-full border px-3 py-1 text-xs"
                    style={{ borderColor: secondary, color: secondary }}>
                    Selo decorativo
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

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

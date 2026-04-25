"use client"

import { useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

// ─── Tipo ─────────────────────────────────────────────────────────────────────

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

const EMPTY: CompanyProfile = {
  tagline: "", description: "", logo_url: "", cover_url: "",
  gallery_urls: [], address: "", city: "", whatsapp: "",
  maps_url: "", instagram_url: "", facebook_url: "",
  tiktok_url: "", google_review_url: "", business_hours: "",
}

// ─── Helper de upload (mesmo padrão do services page) ────────────────────────

async function uploadImage(file: File): Promise<string> {
  const fd = new FormData()
  fd.append("file", file)
  const res = await api.postForm<{ url: string }>("/uploads/", fd)
  return res.url
}

// ─── Sub-componente: campo de imagem com upload ───────────────────────────────

function ImageField({
  label,
  hint,
  value,
  onChange,
  aspectClass = "h-32 w-32",
  cover = false,
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
      alert("Erro ao enviar imagem: " + (err as Error).message)
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
          <img
            src={value}
            alt={label}
            className={`${aspectClass} object-cover rounded-xl border`}
            style={{ maxWidth: cover ? "100%" : undefined }}
          />
          <button
            type="button"
            onClick={() => onChange("")}
            className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-destructive text-white
              flex items-center justify-center text-xs shadow hover:bg-red-600 transition-colors"
          >
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
          <span className="text-2xl">📷</span>
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
      {uploading && !value && (
        <p className="text-xs text-muted-foreground">Enviando…</p>
      )}
    </div>
  )
}

// ─── Sub-componente: galeria de até 6 fotos ───────────────────────────────────

function GalleryField({
  value,
  onChange,
}: {
  value: string[]
  onChange: (urls: string[]) => void
}) {
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    if (!files.length) return
    if (value.length + files.length > 6) {
      alert("A galeria suporta no máximo 6 fotos.")
      return
    }
    setUploading(true)
    try {
      const urls = await Promise.all(files.map(uploadImage))
      onChange([...value, ...urls])
    } catch (err: unknown) {
      alert("Erro ao enviar imagem: " + (err as Error).message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  function removePhoto(index: number) {
    onChange(value.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-2">
      <Label>Galeria <span className="text-muted-foreground font-normal">(até 6 fotos)</span></Label>
      <p className="text-xs text-muted-foreground">
        Fotos do ambiente, trabalhos realizados, equipe, etc.
      </p>

      <div className="grid grid-cols-3 gap-2">
        {value.map((url, i) => (
          <div key={i} className="relative aspect-square">
            <img src={url} alt={`Foto ${i + 1}`}
              className="w-full h-full object-cover rounded-xl border" />
            <button type="button" onClick={() => removePhoto(i)}
              className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-destructive text-white
                flex items-center justify-center text-xs shadow hover:bg-red-600 transition-colors">
              ×
            </button>
          </div>
        ))}

        {value.length < 6 && (
          <div
            onClick={() => fileRef.current?.click()}
            className="aspect-square flex flex-col items-center justify-center rounded-xl
              border-2 border-dashed border-muted-foreground/30 cursor-pointer
              hover:border-primary/50 transition-colors text-muted-foreground"
          >
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

// ─── Página principal ─────────────────────────────────────────────────────────

export default function CompanyProfilePage() {
  const [form,    setForm]    = useState<CompanyProfile>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [saving,  setSaving]  = useState(false)
  const [success, setSuccess] = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  // ── Fetch inicial ──────────────────────────────────────────────────────────
  useEffect(() => {
    api.get<Partial<CompanyProfile>>("/company/profile")
      .then((data) => setForm({ ...EMPTY, ...data, gallery_urls: data.gallery_urls ?? [] }))
      .catch(() => setError("Não foi possível carregar o perfil."))
      .finally(() => setLoading(false))
  }, [])

  // ── Helpers ────────────────────────────────────────────────────────────────
  function set(field: keyof CompanyProfile) {
    return (value: string) => setForm((prev) => ({ ...prev, [field]: value }))
  }

  function handleInput(field: keyof CompanyProfile) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  // ── Submit ─────────────────────────────────────────────────────────────────
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(false)
    try {
      await api.patch("/company/profile", {
        ...form,
        // Envia null para campos vazios para limpar no banco
        tagline:           form.tagline           || null,
        description:       form.description       || null,
        logo_url:          form.logo_url          || null,
        cover_url:         form.cover_url         || null,
        address:           form.address           || null,
        city:              form.city              || null,
        whatsapp:          form.whatsapp          || null,
        maps_url:          form.maps_url          || null,
        instagram_url:     form.instagram_url     || null,
        facebook_url:      form.facebook_url      || null,
        tiktok_url:        form.tiktok_url        || null,
        google_review_url: form.google_review_url || null,
        business_hours:    form.business_hours    || null,
      })
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err: unknown) {
      setError((err as Error).message ?? "Erro ao salvar perfil.")
    } finally {
      setSaving(false)
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  if (loading) return <p className="text-muted-foreground">Carregando…</p>

  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Perfil da Empresa</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Essas informações aparecem na página de agendamento online para seus clientes.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">

        {/* ── Identidade ──────────────────────────────────────────────────── */}
        <Card>
          <CardHeader><CardTitle className="text-base">Identidade visual</CardTitle></CardHeader>
          <CardContent className="space-y-5">

            <div className="flex gap-6 flex-wrap">
              <ImageField
                label="Logo"
                hint="Recomendado: quadrado, mín. 200×200px"
                value={form.logo_url}
                onChange={set("logo_url")}
                aspectClass="h-24 w-24 rounded-full"
              />
              <ImageField
                label="Foto de capa"
                hint="Recomendado: 1200×400px"
                value={form.cover_url}
                onChange={set("cover_url")}
                aspectClass="h-24 w-48 rounded-xl"
                cover
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tagline">Slogan / Tagline</Label>
              <Input id="tagline" value={form.tagline} onChange={handleInput("tagline")}
                placeholder="Ex: Tradição e estilo desde 2010" maxLength={180} />
              <p className="text-xs text-muted-foreground text-right">
                {form.tagline.length}/180
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="description">Descrição</Label>
              <textarea
                id="description"
                value={form.description}
                onChange={handleInput("description")}
                rows={4}
                placeholder="Conte um pouco sobre sua barbearia, diferenciais, história…"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm
                  ring-offset-background focus-visible:outline-none focus-visible:ring-2
                  focus-visible:ring-ring resize-none"
              />
            </div>

          </CardContent>
        </Card>

        {/* ── Galeria ─────────────────────────────────────────────────────── */}
        <Card>
          <CardHeader><CardTitle className="text-base">Galeria de fotos</CardTitle></CardHeader>
          <CardContent>
            <GalleryField
              value={form.gallery_urls}
              onChange={(urls) => setForm((prev) => ({ ...prev, gallery_urls: urls }))}
            />
          </CardContent>
        </Card>

        {/* ── Localização e contato ────────────────────────────────────────── */}
        <Card>
          <CardHeader><CardTitle className="text-base">Localização e contato</CardTitle></CardHeader>
          <CardContent className="space-y-4">

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="city">Cidade</Label>
                <Input id="city" value={form.city} onChange={handleInput("city")}
                  placeholder="Ex: Goiânia – GO" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="whatsapp">WhatsApp</Label>
                <Input id="whatsapp" type="tel" value={form.whatsapp}
                  onChange={handleInput("whatsapp")} placeholder="5562999999999" />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="address">Endereço completo</Label>
              <Input id="address" value={form.address} onChange={handleInput("address")}
                placeholder="Rua das Flores, 123 – Setor Central" />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="maps_url">Link do Google Maps</Label>
              <Input id="maps_url" type="url" value={form.maps_url}
                onChange={handleInput("maps_url")}
                placeholder="https://maps.app.goo.gl/…" />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="business_hours">Horário de funcionamento</Label>
              <Input id="business_hours" value={form.business_hours}
                onChange={handleInput("business_hours")}
                placeholder="Seg–Sex 9h–20h · Sáb 8h–18h" />
            </div>

          </CardContent>
        </Card>

        {/* ── Redes sociais ────────────────────────────────────────────────── */}
        <Card>
          <CardHeader><CardTitle className="text-base">Redes sociais e avaliações</CardTitle></CardHeader>
          <CardContent className="space-y-4">

            <div className="space-y-1.5">
              <Label htmlFor="instagram_url">Instagram</Label>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground text-sm">📸</span>
                <Input id="instagram_url" type="url" value={form.instagram_url}
                  onChange={handleInput("instagram_url")}
                  placeholder="https://instagram.com/suabarbearia" />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="facebook_url">Facebook</Label>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground text-sm">👤</span>
                <Input id="facebook_url" type="url" value={form.facebook_url}
                  onChange={handleInput("facebook_url")}
                  placeholder="https://facebook.com/suabarbearia" />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tiktok_url">TikTok</Label>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground text-sm">🎵</span>
                <Input id="tiktok_url" type="url" value={form.tiktok_url}
                  onChange={handleInput("tiktok_url")}
                  placeholder="https://tiktok.com/@suabarbearia" />
              </div>
            </div>

            <div className="space-y-1.5 pt-2 border-t">
              <Label htmlFor="google_review_url">Link para avaliação no Google</Label>
              <p className="text-xs text-muted-foreground">
                Aparece como botão "Avaliar no Google" na página de agendamento.
                Para gerar o link: Google Meu Negócio → Compartilhar perfil → Peça avaliações.
              </p>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground text-sm">⭐</span>
                <Input id="google_review_url" type="url" value={form.google_review_url}
                  onChange={handleInput("google_review_url")}
                  placeholder="https://g.page/r/…/review" />
              </div>
            </div>

          </CardContent>
        </Card>

        {/* ── Feedback + botão ─────────────────────────────────────────────── */}
        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {success && (
          <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            ✅ Perfil salvo com sucesso! As alterações já aparecem na página de agendamento.
          </div>
        )}

        <div className="flex justify-end pb-8">
          <Button type="submit" disabled={saving} className="min-w-32">
            {saving ? "Salvando…" : "Salvar alterações"}
          </Button>
        </div>

      </form>
    </div>
  )
}
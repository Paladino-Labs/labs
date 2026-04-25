"use client"

import { useEffect, useRef, useState } from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import BookingFlow from "./BookingFlow"

// ─── Tipos ────────────────────────────────────────────────────────────────────

interface CompanyProfile {
  company_name: string
  tagline: string | null
  description: string | null
  logo_url: string | null
  cover_url: string | null
  gallery_urls: string[]
  address: string | null
  city: string | null
  whatsapp: string | null
  maps_url: string | null
  instagram_url: string | null
  facebook_url: string | null
  tiktok_url: string | null
  google_review_url: string | null
  business_hours: string | null
  online_booking_enabled: boolean
}

// ─── API ──────────────────────────────────────────────────────────────────────

const API = process.env.NEXT_PUBLIC_API_URL!

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" } })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw Object.assign(new Error(body.detail ?? "Erro desconhecido"), { status: res.status })
  }
  return res.json()
}

// ─── Ícones SVG inline ────────────────────────────────────────────────────────

function IconInstagram() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
      <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
    </svg>
  )
}

function IconFacebook() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
      <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
    </svg>
  )
}

function IconTikTok() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
      <path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/>
    </svg>
  )
}

function IconGoogle() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
      <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
    </svg>
  )
}

function IconWhatsApp() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
    </svg>
  )
}

function IconMapPin() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4 flex-shrink-0">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z"/>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z"/>
    </svg>
  )
}

function IconClock() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4 flex-shrink-0">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  )
}

function IconStar() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-amber-400">
      <path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/>
    </svg>
  )
}

function IconScissors() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-8 h-8">
      <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>
      <line x1="20" y1="4" x2="8.12" y2="15.88"/>
      <line x1="14.47" y1="14.48" x2="20" y2="20"/>
      <line x1="8.12" y1="8.12" x2="12" y2="12"/>
    </svg>
  )
}

// ─── Componente principal ─────────────────────────────────────────────────────

export default function BookingPage() {
  const { slug }       = useParams<{ slug: string }>()
  const searchParams   = useSearchParams()
  const router         = useRouter()

  const [profile,     setProfile]     = useState<CompanyProfile | null>(null)
  const [error,       setError]       = useState<string | null>(null)
  const [showBooking, setShowBooking] = useState(false)
  const [bookingToken, setBookingToken] = useState<string | null>(
    searchParams.get("t")
  )

  const bookingRef = useRef<HTMLDivElement>(null)

  // Se vier com ?book=1, pula direto para o fluxo
  useEffect(() => {
    if (searchParams.get("book") === "1") setShowBooking(true)
  }, [searchParams])

  useEffect(() => {
    apiFetch<CompanyProfile>(`/booking/${slug}/profile`)
      .then(setProfile)
      .catch((e: Error) => setError(e.message))
  }, [slug])

  function handleStartBooking() {
    setShowBooking(true)
    setTimeout(() => {
      bookingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
    }, 80)
  }

  // Persiste o token do fluxo na URL sem reload
  function handleTokenChange(token: string) {
    setBookingToken(token)
    const url = new URL(window.location.href)
    url.searchParams.set("t", token)
    router.replace(url.pathname + url.search, { scroll: false })
  }

  // ── Guards ────────────────────────────────────────────────────────────────
  if (!profile && !error) {
    return (
      <div className="book-page min-h-screen flex items-center justify-center"
        style={{ background: "var(--book-gradient-dark)" }}>
        <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>Carregando…</p>
      </div>
    )
  }

  if (error || !profile) {
    return (
      <div className="book-page min-h-screen flex items-center justify-center"
        style={{ background: "var(--book-gradient-dark)" }}>
        <div className="text-center max-w-sm px-6">
          <div className="text-4xl mb-4">😕</div>
          <h1 className="text-xl font-bold mb-2" style={{ color: "var(--book-text)" }}>Página não encontrada</h1>
          <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>{error}</p>
        </div>
      </div>
    )
  }

  const hasSocials = profile.instagram_url || profile.facebook_url || profile.tiktok_url
  const hasContact = profile.whatsapp || profile.address || profile.business_hours

  return (
    <div className="book-page" style={{ background: "var(--book-gradient-dark)", minHeight: "100vh" }}>

      {/* ══ HERO ══════════════════════════════════════════════════════════════ */}
      <section className="relative overflow-hidden" style={{ minHeight: 420 }}>

        {profile.cover_url ? (
          <div className="absolute inset-0">
            <img src={profile.cover_url} alt="Capa" className="w-full h-full object-cover" />
            <div className="absolute inset-0"
              style={{ background: "linear-gradient(to bottom, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.75) 100%)" }} />
          </div>
        ) : (
          <div className="absolute inset-0"
            style={{ background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)" }}>
            <div className="absolute inset-0 opacity-10"
              style={{ backgroundImage: "repeating-linear-gradient(45deg, transparent, transparent 30px, rgba(255,255,255,0.05) 30px, rgba(255,255,255,0.05) 60px)" }} />
          </div>
        )}

        <div className="relative z-10 flex flex-col items-center justify-center text-center px-6 py-16"
          style={{ minHeight: 420 }}>

          {profile.logo_url ? (
            <img src={profile.logo_url} alt={profile.company_name}
              className="w-24 h-24 rounded-full object-cover mb-5 shadow-xl"
              style={{ border: "3px solid rgba(255,255,255,0.2)" }} />
          ) : (
            <div className="w-20 h-20 rounded-full flex items-center justify-center mb-5 shadow-xl"
              style={{ background: "var(--book-primary)", border: "3px solid rgba(255,255,255,0.2)", color: "#fff" }}>
              <IconScissors />
            </div>
          )}

          <h1 className="text-3xl font-bold text-white mb-2 drop-shadow">{profile.company_name}</h1>

          {profile.tagline && (
            <p className="text-base text-white/80 mb-2 max-w-sm">{profile.tagline}</p>
          )}

          {profile.city && (
            <div className="flex items-center gap-1 text-white/60 text-sm mb-6">
              <IconMapPin /><span>{profile.city}</span>
            </div>
          )}

          {profile.online_booking_enabled && (
            <button onClick={handleStartBooking}
              className="book-btn-primary px-8 py-3.5 text-base font-semibold rounded-xl shadow-lg
                transition-transform duration-150 active:scale-95 hover:scale-105">
              Agendar agora
            </button>
          )}

          {hasSocials && (
            <div className="flex items-center gap-4 mt-6">
              {profile.instagram_url && (
                <a href={profile.instagram_url} target="_blank" rel="noopener noreferrer"
                  className="text-white/70 hover:text-white transition-colors"><IconInstagram /></a>
              )}
              {profile.facebook_url && (
                <a href={profile.facebook_url} target="_blank" rel="noopener noreferrer"
                  className="text-white/70 hover:text-white transition-colors"><IconFacebook /></a>
              )}
              {profile.tiktok_url && (
                <a href={profile.tiktok_url} target="_blank" rel="noopener noreferrer"
                  className="text-white/70 hover:text-white transition-colors"><IconTikTok /></a>
              )}
            </div>
          )}
        </div>
      </section>

      {/* ══ SOBRE + CONTATO ═══════════════════════════════════════════════════ */}
      {(profile.description || hasContact || profile.google_review_url) && (
        <section className="max-w-lg mx-auto px-6 py-8 space-y-4">

          {profile.description && (
            <div className="rounded-2xl p-5"
              style={{ background: "var(--book-surface)", border: "1px solid var(--book-border)" }}>
              <p className="text-sm leading-relaxed" style={{ color: "var(--book-text-secondary)" }}>
                {profile.description}
              </p>
            </div>
          )}

          {hasContact && (
            <div className="rounded-2xl p-5 space-y-3"
              style={{ background: "var(--book-surface)", border: "1px solid var(--book-border)" }}>
              {profile.business_hours && (
                <div className="flex items-start gap-3">
                  <span style={{ color: "var(--book-primary)" }}><IconClock /></span>
                  <p className="text-sm" style={{ color: "var(--book-text-secondary)" }}>{profile.business_hours}</p>
                </div>
              )}
              {profile.address && (
                <div className="flex items-start gap-3">
                  <span style={{ color: "var(--book-primary)" }}><IconMapPin /></span>
                  <div>
                    <p className="text-sm" style={{ color: "var(--book-text-secondary)" }}>{profile.address}</p>
                    {profile.maps_url && (
                      <a href={profile.maps_url} target="_blank" rel="noopener noreferrer"
                        className="text-xs font-medium mt-0.5 inline-block" style={{ color: "var(--book-primary)" }}>
                        Ver no mapa →
                      </a>
                    )}
                  </div>
                </div>
              )}
              {profile.whatsapp && (
                <a href={`https://wa.me/${profile.whatsapp.replace(/\D/g, "")}`}
                  target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-3 rounded-xl px-4 py-2.5 transition-opacity hover:opacity-80"
                  style={{ background: "#25D366", color: "#fff" }}>
                  <IconWhatsApp />
                  <span className="text-sm font-medium">Chamar no WhatsApp</span>
                </a>
              )}
            </div>
          )}

          {profile.google_review_url && (
            <a href={profile.google_review_url} target="_blank" rel="noopener noreferrer"
              className="flex items-center justify-center gap-3 rounded-2xl px-5 py-3.5 w-full transition-opacity hover:opacity-80"
              style={{ background: "var(--book-surface)", border: "1px solid var(--book-border)", color: "var(--book-text)" }}>
              <IconGoogle />
              <span className="text-sm font-medium">Avaliar no Google</span>
              <div className="flex gap-0.5 ml-1">{[...Array(5)].map((_, i) => <IconStar key={i} />)}</div>
            </a>
          )}
        </section>
      )}

      {/* ══ GALERIA ═══════════════════════════════════════════════════════════ */}
      {profile.gallery_urls.length > 0 && (
        <section className="max-w-lg mx-auto px-6 pb-8">
          <h2 className="text-base font-semibold mb-4" style={{ color: "var(--book-text)" }}>Galeria</h2>
          <div className="grid grid-cols-3 gap-2">
            {profile.gallery_urls.slice(0, 6).map((url, i) => (
              <div key={i} className="aspect-square rounded-xl overflow-hidden"
                style={{ border: "1px solid var(--book-border)" }}>
                <img src={url} alt={`Foto ${i + 1}`} className="w-full h-full object-cover" />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ══ BOTÃO FIXO MOBILE (só enquanto fluxo não está visível) ═══════════ */}
      {profile.online_booking_enabled && !showBooking && (
        <div className="fixed bottom-0 left-0 right-0 z-30 p-4 lg:hidden"
          style={{ background: "linear-gradient(to top, var(--book-gradient-dark) 60%, transparent)" }}>
          <button onClick={handleStartBooking}
            className="book-btn-primary w-full py-4 text-base font-semibold rounded-xl shadow-xl">
            Agendar agora
          </button>
        </div>
      )}

      {/* ══ FLUXO DE AGENDAMENTO (aparece com transição suave) ═══════════════ */}
      <div ref={bookingRef}
        className="transition-all duration-500"
        style={{ overflow: showBooking ? "visible" : "hidden", maxHeight: showBooking ? "9999px" : 0, opacity: showBooking ? 1 : 0 }}>
        {showBooking && (
          <section>
            {/* Divisor */}
            <div className="flex items-center gap-3 max-w-lg mx-auto px-6 py-6">
              <div className="flex-1 h-px" style={{ background: "var(--book-border)" }} />
              <span className="text-xs font-semibold uppercase tracking-widest"
                style={{ color: "var(--book-text-muted)" }}>Agendamento</span>
              <div className="flex-1 h-px" style={{ background: "var(--book-border)" }} />
            </div>

            {/* Fluxo — sem header próprio, pois a landing já apresenta a empresa */}
            <BookingFlow
              slug={slug}
              companyName={profile.company_name}
              initialToken={bookingToken}
              onTokenChange={handleTokenChange}
            />
          </section>
        )}
      </div>

      {/* Espaço para o botão fixo mobile */}
      {!showBooking && <div className="h-24 lg:hidden" />}
    </div>
  )
}
"use client"

import { Suspense, useEffect, useRef, useState } from "react"
import {
  Clock, CreditCard, ExternalLink, Frown,
  MapPin, MessageCircle, Package, Phone, RefreshCw, Scissors, Star, Tag,
} from "lucide-react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import BookingFlow from "./BookingFlow"
import { publicFetch } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/empty-state"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { formatBRL, formatBRLFromDecimal, cn } from "@/lib/utils"
import type { PublicProduct, PublicPackage, PublicPlan, PublicPromotion } from "@/lib/portal-types"

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

interface ServiceOption {
  id: string
  name: string
  price: string
  duration_minutes: number
  description?: string | null
}

// ─── InfoCard ─────────────────────────────────────────────────────────────────

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h2 className="label-eyebrow mb-3">{title}</h2>
      {children}
    </section>
  )
}

// ─── Componente principal ─────────────────────────────────────────────────────

export default function BookingPage() {
  return (
    <Suspense>
      <BookingContent />
    </Suspense>
  )
}

function BookingContent() {
  const { slug }       = useParams<{ slug: string }>()
  const searchParams   = useSearchParams()
  const router         = useRouter()

  interface ProfessionalOption {
    id: string | null
    name: string
    row_key: string
  }

  const [profile,         setProfile]         = useState<CompanyProfile | null>(null)
  const [services,        setServices]        = useState<ServiceOption[]>([])
  const [products,        setProducts]        = useState<PublicProduct[]>([])
  const [productsState,   setProductsState]   = useState<"loading" | "ok" | "error">("loading")
  const [vitrineProfs,    setVitrineProfs]    = useState<ProfessionalOption[]>([])
  // Pacotes
  const [packages,        setPackages]        = useState<PublicPackage[]>([])
  const [packagesState,   setPackagesState]   = useState<"loading" | "ok" | "error">("loading")
  // Assinaturas
  const [plans,           setPlans]           = useState<PublicPlan[]>([])
  const [plansState,      setPlansState]      = useState<"loading" | "ok" | "error">("loading")
  // Promoções
  const [promotions,      setPromotions]      = useState<PublicPromotion[]>([])
  const [promotionsState, setPromotionsState] = useState<"loading" | "ok" | "error">("loading")
  const [error,           setError]           = useState<string | null>(null)
  const [showBooking,       setShowBooking]       = useState(false)
  const [initialServiceId,  setInitialServiceId]  = useState<string | null>(null)
  const [bookingToken,      setBookingToken]       = useState<string | null>(
    searchParams.get("t")
  )

  const bookingRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (searchParams.get("book") === "1") setShowBooking(true)
  }, [searchParams])

  useEffect(() => {
    publicFetch<CompanyProfile>(`/booking/${slug}/profile`)
      .then(setProfile)
      .catch((e: Error) => setError(e.message))
  }, [slug])

  // B6 — vitrine de produtos (público).
  useEffect(() => {
    if (!slug) return
    setProductsState("loading")
    publicFetch<PublicProduct[]>(`/booking/${slug}/products`)
      .then((data) => { setProducts(data); setProductsState("ok") })
      .catch(() => setProductsState("error"))
  }, [slug])

  // Pacotes (público).
  useEffect(() => {
    if (!slug) return
    setPackagesState("loading")
    publicFetch<PublicPackage[]>(`/booking/${slug}/packages`)
      .then((data) => { setPackages(data); setPackagesState("ok") })
      .catch(() => setPackagesState("error"))
  }, [slug])

  // Assinaturas (público).
  useEffect(() => {
    if (!slug) return
    setPlansState("loading")
    publicFetch<PublicPlan[]>(`/booking/${slug}/subscription-plans`)
      .then((data) => { setPlans(data); setPlansState("ok") })
      .catch(() => setPlansState("error"))
  }, [slug])

  // Promoções (público).
  useEffect(() => {
    if (!slug) return
    setPromotionsState("loading")
    publicFetch<PublicPromotion[]>(`/booking/${slug}/promotions`)
      .then((data) => { setPromotions(data); setPromotionsState("ok") })
      .catch(() => setPromotionsState("error"))
  }, [slug])

  useEffect(() => {
    publicFetch<ServiceOption[]>(`/booking/${slug}/services`)
      .then((svcs) => {
        setServices(svcs)
        // Carrega profissionais usando o primeiro serviço disponível
        if (svcs.length > 0) {
          publicFetch<ProfessionalOption[]>(
            `/booking/${slug}/professionals?service_id=${svcs[0].id}`
          )
            .then((profs) => {
              // Filtra "Qualquer disponível" (id=null) para mostrar só profissionais reais
              setVitrineProfs(profs.filter((p) => p.id !== null))
            })
            .catch(() => {})
        }
      })
      .catch(() => {})
  }, [slug])

  function handleStartBooking() {
    setInitialServiceId(null)
    setShowBooking(true)
    setTimeout(() => {
      bookingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
    }, 80)
  }

  function handleBookService(serviceId: string) {
    setInitialServiceId(serviceId)
    setShowBooking(true)
    setTimeout(() => {
      bookingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
    }, 80)
  }

  function handleTokenChange(token: string) {
    setBookingToken(token)
    const url = new URL(window.location.href)
    url.searchParams.set("t", token)
    router.replace(url.pathname + url.search, { scroll: false })
  }

  // ── Guards ────────────────────────────────────────────────────────────────

  if (!profile && !error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Carregando…</p>
      </div>
    )
  }

  if (error || !profile) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center max-w-sm px-6">
          <Frown className="h-10 w-10 mx-auto mb-4 text-muted-foreground" />
          <h1 className="text-xl font-semibold mb-2">Página não encontrada</h1>
          <p className="text-sm text-muted-foreground">{error}</p>
        </div>
      </div>
    )
  }

  // Compõe o array de fotos: cover primeiro, depois gallery
  const photos = [profile.cover_url, ...profile.gallery_urls].filter(Boolean) as string[]
  const hasSocials = profile.instagram_url || profile.facebook_url || profile.tiktok_url

  return (
    <div className="min-h-screen bg-background text-foreground">

      {/* ══ GRID 2 COLUNAS ══════════════════════════════════════════════════════ */}
      <div className="mx-auto max-w-6xl px-6 py-10 grid gap-10 lg:grid-cols-[1fr_320px]">

        <main className="space-y-10">

          {/* ── Hero ───────────────────────────────────────────────────────── */}
          <section className="flex flex-col gap-6 sm:flex-row sm:items-start">
            {profile.logo_url ? (
              <img
                src={profile.logo_url}
                alt={profile.company_name}
                className="h-20 w-20 shrink-0 rounded-2xl object-cover border border-border"
              />
            ) : (
              <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl border border-primary/30 bg-primary/10 text-primary">
                <Scissors className="h-8 w-8" />
              </div>
            )}

            <div className="flex-1">
              <h1 className="font-display text-4xl tracking-wide leading-tight">
                {profile.company_name}
              </h1>

              {profile.tagline && (
                <p className="mt-1 text-sm text-muted-foreground">{profile.tagline}</p>
              )}

              {profile.city && (
                <div className="mt-2 flex items-center gap-1 text-sm text-muted-foreground">
                  <MapPin className="h-4 w-4" />
                  <span>{profile.city}</span>
                </div>
              )}

              {profile.google_review_url && (
                <a
                  href={profile.google_review_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors"
                >
                  <Star className="h-4 w-4" />
                  Ver avaliações no Google
                </a>
              )}

              {profile.description && (
                <p className="mt-3 max-w-prose text-sm text-muted-foreground">
                  {profile.description}
                </p>
              )}

              {profile.online_booking_enabled && (
                <button
                  onClick={handleStartBooking}
                  className="book-btn-primary mt-5 px-8 py-3 text-base"
                >
                  Agendar agora
                </button>
              )}

              {hasSocials && (
                <div className="flex items-center gap-4 mt-4">
                  {profile.instagram_url && (
                    <a href={profile.instagram_url} target="_blank" rel="noreferrer"
                       className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors">
                      <ExternalLink className="h-4 w-4" />
                      <span>Instagram</span>
                    </a>
                  )}
                  {profile.facebook_url && (
                    <a href={profile.facebook_url} target="_blank" rel="noreferrer"
                       className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors">
                      <ExternalLink className="h-4 w-4" />
                      <span>Facebook</span>
                    </a>
                  )}
                  {profile.tiktok_url && (
                    <a href={profile.tiktok_url} target="_blank" rel="noreferrer"
                       className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors">
                      <ExternalLink className="h-4 w-4" />
                      <span>TikTok</span>
                    </a>
                  )}
                </div>
              )}
            </div>
          </section>

          {/* ── Galeria ────────────────────────────────────────────────────── */}
          {photos.length > 0 && (
            <section className="grid gap-3 sm:grid-cols-[2fr_1fr]">
              <img
                src={photos[0]}
                alt={`${profile.company_name} — ambiente`}
                className="h-80 w-full rounded-lg object-cover border border-border"
                loading="lazy"
              />
              <div className="grid grid-cols-3 gap-3 sm:grid-cols-1">
                {photos.slice(1, 4).map((src, i) => (
                  <img
                    key={src}
                    src={src}
                    alt={`${profile.company_name} — ambiente ${i + 2}`}
                    className="h-24 sm:h-[calc((20rem-0.75rem*2)/3)] w-full rounded-lg object-cover border border-border"
                    loading="lazy"
                  />
                ))}
              </div>
            </section>
          )}

          {/* ── Tabs ───────────────────────────────────────────────────────── */}
          <Tabs defaultValue="services">
            <TabsList>
              <TabsTrigger value="services">Serviços</TabsTrigger>
              <TabsTrigger value="professionals">Barbeiros</TabsTrigger>
              <TabsTrigger value="packages">Pacotes</TabsTrigger>
              <TabsTrigger value="subscriptions">Assinaturas</TabsTrigger>
              <TabsTrigger value="products">Produtos</TabsTrigger>
              <TabsTrigger value="promotions">Promoções</TabsTrigger>
              <TabsTrigger value="reviews">Avaliações</TabsTrigger>
            </TabsList>

            <TabsContent value="services">
              <div className="grid gap-3">
                {services.map((s) => (
                  <article
                    key={s.id}
                    className="rounded-lg border border-border bg-card p-5 flex items-center gap-4 transition-colors hover:border-primary/60"
                  >
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                      <Scissors className="h-5 w-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold">{s.name}</h3>
                      {s.description && (
                        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                          {s.description}
                        </p>
                      )}
                      <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {s.duration_minutes} min
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <span className="font-display text-lg text-primary">
                        {formatBRL(s.price)}
                      </span>
                      {profile.online_booking_enabled && (
                        <button
                          onClick={() => handleBookService(s.id)}
                          className="book-btn-secondary px-3 py-1 text-xs"
                        >
                          Agendar
                        </button>
                      )}
                    </div>
                  </article>
                ))}
                {services.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    Nenhum serviço disponível.
                  </p>
                )}
              </div>
            </TabsContent>

            <TabsContent value="professionals">
              {vitrineProfs.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
                  Nenhum profissional disponível no momento.
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">
                  {vitrineProfs.map((p) => (
                    <article
                      key={p.id}
                      className="rounded-lg border border-border bg-card p-5 flex items-center gap-4"
                    >
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-semibold text-sm">
                        {p.name.split(" ").map((n) => n[0]).slice(0, 2).join("").toUpperCase()}
                      </div>
                      <div>
                        <h3 className="font-semibold">{p.name}</h3>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="packages">
              {packagesState === "loading" ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {[1, 2, 3].map((i) => <Skeleton key={i} className="h-48 rounded-xl" />)}
                </div>
              ) : packagesState === "error" ? (
                <EmptyState
                  icon={<Package size={28} strokeWidth={1.5} />}
                  title="Não foi possível carregar os pacotes."
                />
              ) : packages.length === 0 ? (
                <EmptyState
                  icon={<Package size={28} strokeWidth={1.5} />}
                  title="Em breve"
                  description="Os pacotes do estabelecimento aparecerão aqui."
                />
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {packages.map((pkg) => (
                    <div key={pkg.package_id}
                      className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3">
                      {/* Nome */}
                      <p className="font-semibold text-sm">{pkg.name}</p>

                      {/* Chips de itens */}
                      <div className="flex flex-wrap gap-1">
                        {pkg.items.map((item, i) => (
                          <span key={i}
                            className={cn(
                              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                              item.item_type === "SERVICE"
                                ? "bg-primary/10 text-primary border border-primary/30"
                                : "bg-muted text-muted-foreground border border-border"
                            )}>
                            {item.quantity}× {item.service_name ?? item.product_name ?? "Item"}
                          </span>
                        ))}
                      </div>

                      {/* Cotas e validade */}
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{pkg.total_cotas} {pkg.total_cotas === 1 ? "cota" : "cotas"} no total</span>
                        {pkg.validity_days && (
                          <span>· Válido por {pkg.validity_days} dias</span>
                        )}
                      </div>

                      {/* Preço + botão */}
                      <div className="flex items-center justify-between mt-auto pt-1">
                        <span className="font-display text-lg text-primary">
                          {formatBRLFromDecimal(pkg.price)}
                        </span>
                        <button
                          disabled
                          title="Em breve"
                          className="book-btn-secondary px-3 py-1 text-xs opacity-50 cursor-not-allowed">
                          Adicionar
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="subscriptions">
              {plansState === "loading" ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {[1, 2].map((i) => <Skeleton key={i} className="h-48 rounded-xl" />)}
                </div>
              ) : plansState === "error" ? (
                <EmptyState
                  icon={<RefreshCw size={28} strokeWidth={1.5} />}
                  title="Não foi possível carregar os planos."
                />
              ) : plans.length === 0 ? (
                <EmptyState
                  icon={<RefreshCw size={28} strokeWidth={1.5} />}
                  title="Em breve"
                  description="Os planos de assinatura aparecerão aqui."
                />
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {plans.map((plan) => (
                    <div key={plan.plan_id}
                      className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3">
                      {/* Nome */}
                      <p className="font-semibold text-sm">{plan.name}</p>

                      {/* Chips de itens */}
                      <div className="flex flex-wrap gap-1">
                        {plan.items.map((item, i) => (
                          <span key={i}
                            className={cn(
                              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                              item.item_type === "SERVICE"
                                ? "bg-primary/10 text-primary border border-primary/30"
                                : "bg-muted text-muted-foreground border border-border"
                            )}>
                            {item.quantity}× {item.service_name ?? item.product_name ?? "Item"}
                          </span>
                        ))}
                      </div>

                      {/* Cotas e ciclo */}
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{plan.total_cotas_per_cycle} {plan.total_cotas_per_cycle === 1 ? "cota" : "cotas"}/ciclo</span>
                        <span>· Renova a cada {plan.cycle_days} dias</span>
                      </div>

                      {/* Preço + botão */}
                      <div className="flex items-center justify-between mt-auto pt-1">
                        <div>
                          <span className="font-display text-lg text-primary">
                            {formatBRLFromDecimal(plan.price)}
                          </span>
                          <span className="text-xs text-muted-foreground ml-1">
                            /{plan.cycle_days === 30 ? "mês" : plan.cycle_days === 7 ? "sem." : `${plan.cycle_days}d`}
                          </span>
                        </div>
                        <button
                          disabled
                          title="Em breve"
                          className="book-btn-secondary px-3 py-1 text-xs opacity-50 cursor-not-allowed">
                          Assinar
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="products">
              {productsState === "loading" ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-32 rounded-xl" />
                  ))}
                </div>
              ) : productsState === "error" ? (
                <EmptyState
                  icon={<Package size={28} strokeWidth={1.5} />}
                  title="Não foi possível carregar os produtos."
                />
              ) : products.length === 0 ? (
                <EmptyState
                  icon={<Package size={28} strokeWidth={1.5} />}
                  title="Em breve"
                  description="Os produtos do estabelecimento aparecerão aqui."
                />
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {products.map((p) => (
                    <div
                      key={p.id}
                      className={cn(
                        "rounded-xl border border-border bg-card p-4 flex flex-col gap-2",
                        !p.available && "opacity-60"
                      )}
                    >
                      {p.image_url ? (
                        <img
                          src={p.image_url}
                          alt={p.name}
                          className="h-24 w-full rounded-lg object-cover"
                        />
                      ) : (
                        <div className="flex h-24 items-center justify-center rounded-lg bg-muted">
                          <Package size={32} strokeWidth={1.5} className="text-muted-foreground" />
                        </div>
                      )}
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-sm line-clamp-1">{p.name}</p>
                          {p.description && (
                            <p className="text-xs text-muted-foreground line-clamp-1">
                              {p.description}
                            </p>
                          )}
                        </div>
                        {!p.available && (
                          <Badge variant="secondary" className="shrink-0 text-xs">
                            Esgotado
                          </Badge>
                        )}
                      </div>
                      <span className="font-display text-lg text-primary">
                        {formatBRLFromDecimal(p.price)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="promotions">
              {promotionsState === "loading" ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {[1, 2, 3].map((i) => <Skeleton key={i} className="h-32 rounded-xl" />)}
                </div>
              ) : promotionsState === "error" ? (
                <EmptyState
                  icon={<Tag size={28} strokeWidth={1.5} />}
                  title="Não foi possível carregar as promoções."
                />
              ) : promotions.length === 0 ? (
                <EmptyState
                  icon={<Tag size={28} strokeWidth={1.5} />}
                  title="Sem promoções ativas"
                  description="As promoções do estabelecimento aparecerão aqui."
                />
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {promotions.map((promo) => (
                    <div key={promo.promotion_id}
                      className="rounded-xl border border-border bg-card p-4 flex flex-col gap-2">
                      {/* Badge de tipo + validade — promoções públicas são automáticas */}
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary" className="text-xs">
                          Promoção
                        </Badge>
                        {promo.valid_until && (
                          <span className="text-xs text-muted-foreground">
                            Válido até {new Date(promo.valid_until).toLocaleDateString("pt-BR", {
                              day: "2-digit", month: "2-digit", year: "numeric"
                            })}
                          </span>
                        )}
                      </div>

                      {/* Nome */}
                      <p className="font-semibold text-sm">{promo.name}</p>

                      {/* Descrição */}
                      {promo.description && (
                        <p className="text-xs text-muted-foreground line-clamp-2">{promo.description}</p>
                      )}

                      {/* Desconto */}
                      {promo.discount_value && (
                        <p className="font-display text-lg text-primary">
                          {promo.discount_type === "PERCENTAGE"
                            ? `${parseFloat(promo.discount_value).toFixed(0)}% off`
                            : promo.discount_type === "FIXED_AMOUNT"
                            ? `${formatBRLFromDecimal(promo.discount_value)} off`
                            : promo.discount_type === "OVERRIDE_PRICE"
                            ? `Por ${formatBRLFromDecimal(promo.discount_value)}`
                            : "Grátis"}
                        </p>
                      )}

                      {/* Promoções públicas aplicam-se automaticamente no checkout */}
                      <Badge variant="outline" className="text-xs w-fit mt-auto">
                        Aplicado automaticamente
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            <TabsContent value="reviews">
              <EmptyState
                icon={<Star size={28} strokeWidth={1.5} />}
                title="Avaliações em breve"
                description="Em breve você poderá ler e deixar avaliações sobre o atendimento."
              />
            </TabsContent>
          </Tabs>
        </main>

        {/* ══ ASIDE ═══════════════════════════════════════════════════════════ */}
        <aside className="space-y-6 lg:sticky lg:top-6 lg:self-start">

          {profile.address && (
            <InfoCard title="Localização">
              <a
                href={
                  profile.maps_url ??
                  `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(profile.address)}`
                }
                target="_blank"
                rel="noreferrer"
                className="flex items-start gap-2 text-sm hover:text-primary transition-colors"
              >
                <MapPin className="h-4 w-4 mt-0.5 shrink-0 text-primary" />
                <span>{profile.address}</span>
              </a>
            </InfoCard>
          )}

          {profile.business_hours && (
            <InfoCard title="Horário de atendimento">
              <p className="text-sm text-muted-foreground whitespace-pre-line">
                {profile.business_hours}
              </p>
            </InfoCard>
          )}

          <InfoCard title="Formas de pagamento">
            <div className="flex flex-wrap gap-2">
              {["Dinheiro", "Pix", "Crédito", "Débito"].map((p) => (
                <Badge key={p} variant="outline" className="gap-1">
                  <CreditCard className="h-3 w-3" />
                  {p}
                </Badge>
              ))}
            </div>
          </InfoCard>

          {profile.whatsapp && (
            <InfoCard title="Contato">
              <a
                href={`https://wa.me/${profile.whatsapp.replace(/\D/g, "")}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm hover:text-primary transition-colors"
              >
                <Phone className="h-4 w-4 text-primary" />
                {profile.whatsapp}
              </a>
            </InfoCard>
          )}

          {hasSocials && (
            <InfoCard title="Redes sociais">
              <div className="flex flex-col gap-2">
                {profile.instagram_url && (
                  <a href={profile.instagram_url} target="_blank" rel="noreferrer"
                     className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors">
                    <ExternalLink className="h-4 w-4" />
                    <span>Instagram</span>
                  </a>
                )}
                {profile.facebook_url && (
                  <a href={profile.facebook_url} target="_blank" rel="noreferrer"
                     className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors">
                    <ExternalLink className="h-4 w-4" />
                    <span>Facebook</span>
                  </a>
                )}
                {profile.tiktok_url && (
                  <a href={profile.tiktok_url} target="_blank" rel="noreferrer"
                     className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors">
                    <ExternalLink className="h-4 w-4" />
                    <span>TikTok</span>
                  </a>
                )}
              </div>
            </InfoCard>
          )}
        </aside>
      </div>

      {/* ══ BOTÃO FIXO MOBILE ════════════════════════════════════════════════ */}
      {profile.online_booking_enabled && !showBooking && (
        <div
          className="fixed bottom-0 left-0 right-0 z-30 p-4 lg:hidden"
          style={{ background: "linear-gradient(to top, var(--background) 60%, transparent)" }}
        >
          <button
            onClick={handleStartBooking}
            className="book-btn-primary w-full py-4 text-base font-semibold"
          >
            Agendar agora
          </button>
        </div>
      )}

      {/* ══ FLUXO DE AGENDAMENTO ═════════════════════════════════════════════ */}
      <div
        ref={bookingRef}
        className="transition-all duration-500"
        style={{
          overflow: showBooking ? "visible" : "hidden",
          maxHeight: showBooking ? "9999px" : 0,
          opacity: showBooking ? 1 : 0,
        }}
      >
        {showBooking && (
          <section>
            <div className="flex items-center gap-3 max-w-lg mx-auto px-6 py-6">
              <div className="flex-1 h-px bg-border" />
              <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Agendamento
              </span>
              <div className="flex-1 h-px bg-border" />
            </div>
            <BookingFlow
              slug={slug}
              companyName={profile.company_name}
              initialToken={bookingToken}
              onTokenChange={handleTokenChange}
              initialServiceId={initialServiceId}
            />
          </section>
        )}
      </div>

      {/* Espaço para o botão fixo mobile */}
      {!showBooking && <div className="h-24 lg:hidden" />}
    </div>
  )
}

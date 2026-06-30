"use client"

import { Suspense, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import {
  ArrowLeft, CheckCircle2, Minus, Plus, Tag, X,
} from "lucide-react"
import { publicFetch } from "@/lib/api"
import { getPortalToken, portalFetch } from "@/lib/portal-api"
import { formatBRL, formatBRLFromDecimal } from "@/lib/utils"
import {
  CartProvider, useCart,
  type CartItem, type CartServiceItem, type CartPackageItem,
  type CartSubscriptionItem, type CartProductItem,
} from "@/context/CartContext"
import type { CheckoutResponse, PortalIdentity } from "@/lib/portal-types"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

// ─── Helpers ────────────────────────────────────────────────────────────────

const KIND_LABEL: Record<CartItem["kind"], string> = {
  service:      "SERVIÇO",
  package:      "PACOTE",
  subscription: "ASSINATURA",
  product:      "PRODUTO",
}

function itemTitle(item: CartItem): string {
  switch (item.kind) {
    case "service":      return item.service_name
    case "package":      return item.package_name
    case "subscription": return item.plan_name
    case "product":      return item.product_name
  }
}

function itemSubtitle(item: CartItem): string | null {
  if (item.kind === "service") {
    const when = new Date(item.start_at).toLocaleString("pt-BR", {
      weekday: "short", day: "2-digit", month: "2-digit",
      hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo",
    })
    return item.professional_name ? `${when} · ${item.professional_name}` : when
  }
  return null
}

// ─── Página ─────────────────────────────────────────────────────────────────

export default function CheckoutPage() {
  return (
    <Suspense>
      <CheckoutRoot />
    </Suspense>
  )
}

function CheckoutRoot() {
  const { slug } = useParams<{ slug: string }>()
  return (
    <CartProvider slug={slug}>
      <CheckoutContent slug={slug} />
    </CartProvider>
  )
}

type Step = 1 | 2 | "success"

function CheckoutContent({ slug }: { slug: string }) {
  const router = useRouter()
  const {
    cart, hydrated, removeItem, updateQty, applyCoupon, clearCoupon,
    subtotalCents, totalCents, clear,
  } = useCart()

  const [step, setStep] = useState<Step>(1)

  // Cupom
  const [couponInput, setCouponInput] = useState("")
  const [couponError, setCouponError] = useState<string | null>(null)
  const [validating, setValidating]   = useState(false)

  // Dados do cliente (logado via portal)
  const [portalIdentity, setPortalIdentity] = useState<PortalIdentity | null>(null)
  const [name, setName]   = useState("")
  const [phone, setPhone] = useState("")
  const [email, setEmail] = useState("")

  // Submissão
  const [submitting, setSubmitting]       = useState(false)
  const [submitError, setSubmitError]     = useState<string | null>(null)
  const [checkoutResult, setCheckoutResult] = useState<CheckoutResponse | null>(null)

  // Sessão do portal — preenche os dados automaticamente se logado.
  useEffect(() => {
    const token = getPortalToken()
    if (!token) return
    portalFetch<PortalIdentity>("/portal/identity/me")
      .then(setPortalIdentity)
      .catch(() => {})  // falha silenciosa — tratar como não logado
  }, [])

  async function handleApplyCoupon() {
    const code = couponInput.trim()
    if (!code) return
    setValidating(true)
    setCouponError(null)
    try {
      const result = await publicFetch<{
        valid: boolean
        discount_value?: string | null
        net_amount?: string | null
        error?: string | null
      }>(`/booking/${slug}/coupon/validate`, {
        method: "POST",
        body: JSON.stringify({
          coupon_code: code,
          gross_amount: String(subtotalCents / 100),
        }),
      })
      if (result.valid) {
        const discountCents = result.discount_value != null
          ? Math.round(parseFloat(result.discount_value) * 100)
          : result.net_amount != null
            ? subtotalCents - Math.round(parseFloat(result.net_amount) * 100)
            : 0
        applyCoupon(code, Math.max(0, discountCents))
        setCouponInput("")
      } else {
        setCouponError(result.error ?? "Cupom inválido.")
      }
    } catch (e) {
      setCouponError((e as Error).message || "Não foi possível validar o cupom.")
    } finally {
      setValidating(false)
    }
  }

  async function handleConfirm() {
    setSubmitting(true)
    setSubmitError(null)
    const body = {
      customer_name:  portalIdentity?.name ?? name,
      customer_phone: portalIdentity?.phone_e164 ?? phone,
      services: cart.items
        .filter((i): i is CartServiceItem => i.kind === "service")
        .map((i) => ({
          professional_id: i.professional_id ?? "",
          service_id:      i.service_id,
          start_at:        i.start_at,
          end_at:          i.end_at,
        })),
      packages: cart.items
        .filter((i): i is CartPackageItem => i.kind === "package")
        .map((i) => ({ package_id: i.package_id, payment_method: "CASH" })),
      subscriptions: cart.items
        .filter((i): i is CartSubscriptionItem => i.kind === "subscription")
        .map((i) => ({ plan_id: i.plan_id, payment_method: "CASH" })),
      products: cart.items
        .filter((i): i is CartProductItem => i.kind === "product")
        .map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
      coupon_code: cart.coupon_code ?? null,
    }
    try {
      const result = await publicFetch<CheckoutResponse>(
        `/booking/${slug}/checkout`,
        { method: "POST", body: JSON.stringify(body) },
      )
      clear()
      setCheckoutResult(result)
      setStep("success")
    } catch (e) {
      setSubmitError((e as Error).message || "Não foi possível concluir o pedido.")
    } finally {
      setSubmitting(false)
    }
  }

  // ── Shell ──────────────────────────────────────────────────────────────────
  const Shell = ({ children }: { children: React.ReactNode }) => (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto grid max-w-4xl grid-cols-[1fr_auto_1fr] items-center px-6 py-4">
          <a href={`/book/${slug}`}
            className="inline-flex min-w-0 items-center gap-2 justify-self-start text-sm text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-4 w-4 shrink-0" />
            <span className="truncate">Voltar ao catálogo</span>
          </a>
          <span className="justify-self-center font-display text-2xl tracking-[0.3em] text-primary leading-none">
            PALADINO
          </span>
          <div aria-hidden className="justify-self-end" />
        </div>
      </header>
      <div className="mx-auto max-w-4xl px-6 py-8">{children}</div>
    </div>
  )

  // ── Carrinho vazio ──────────────────────────────────────────────────────────
  if (hydrated && cart.items.length === 0 && step !== "success") {
    return (
      <Shell>
        <div className="flex flex-col items-center text-center py-20 space-y-4">
          <h1 className="font-display text-3xl tracking-wide">Seu carrinho está vazio</h1>
          <p className="text-sm text-muted-foreground">
            Adicione serviços, pacotes ou produtos para continuar.
          </p>
          <a href={`/book/${slug}`} className="book-btn-primary px-6 py-2.5 text-sm">
            Ir ao catálogo
          </a>
        </div>
      </Shell>
    )
  }

  // ── Sucesso ──────────────────────────────────────────────────────────────────
  if (step === "success" && checkoutResult) {
    return (
      <Shell>
        <div className="flex flex-col items-center text-center py-12 space-y-6 max-w-lg mx-auto">
          <div className="h-16 w-16 rounded-full bg-success/15 text-success flex items-center justify-center">
            <CheckCircle2 className="h-8 w-8" />
          </div>
          <h1 className="font-display text-4xl tracking-wide">Pedido confirmado!</h1>

          <div className="w-full rounded-xl border border-border bg-card p-4 text-sm text-left space-y-2">
            {checkoutResult.appointments.map((a) => (
              <div key={a.appointment_id} className="flex justify-between">
                <span className="text-muted-foreground">Agendamento — {a.service_name}</span>
                <span>{formatBRLFromDecimal(a.total_amount)}</span>
              </div>
            ))}
            {checkoutResult.purchases.map((p) => (
              <div key={p.purchase_id} className="flex justify-between">
                <span className="text-muted-foreground">Pacote — {p.package_name}</span>
                <span>{formatBRLFromDecimal(p.amount_paid)}</span>
              </div>
            ))}
            {checkoutResult.subscriptions.map((s) => (
              <div key={s.subscription_id} className="flex justify-between">
                <span className="text-muted-foreground">Assinatura — {s.plan_name}</span>
                <span>{formatBRLFromDecimal(s.amount_paid)}</span>
              </div>
            ))}
            {checkoutResult.product_sales.map((p, i) => (
              <div key={i} className="flex justify-between">
                <span className="text-muted-foreground">Produto — {p.product_name}</span>
                <span>{formatBRLFromDecimal(p.amount_paid)}</span>
              </div>
            ))}
            {checkoutResult.discount_amount && (
              <div className="flex justify-between text-success border-t border-border pt-2">
                <span>Desconto ({checkoutResult.coupon_applied})</span>
                <span>−{formatBRLFromDecimal(checkoutResult.discount_amount)}</span>
              </div>
            )}
            <div className="flex justify-between font-semibold border-t border-border pt-2">
              <span>Total</span>
              <span className="font-display text-primary">
                {formatBRLFromDecimal(checkoutResult.total_charged)}
              </span>
            </div>
          </div>

          {checkoutResult.appointments.length > 0 && (
            portalIdentity ? (
              <p className="text-sm text-muted-foreground">
                Acompanhe e gerencie este agendamento no seu Painel do Cliente.
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                📱 Enviamos o link de gestão do agendamento para o seu WhatsApp.
              </p>
            )
          )}

          {checkoutResult.warnings.length > 0 && (
            <div className="w-full rounded-lg border border-border bg-muted/40 p-3 text-left text-xs text-muted-foreground space-y-1">
              {checkoutResult.warnings.map((w, i) => <p key={i}>{w}</p>)}
            </div>
          )}

          <a href={portalIdentity ? "/portal/dashboard" : "/portal/login"}
             className="book-btn-secondary px-6 py-2 text-sm inline-flex items-center gap-2">
            {portalIdentity ? "Gerenciar no Painel do Cliente" : "Acessar Painel do Cliente"}
          </a>
          <a href={`/book/${slug}`}
             className="text-sm text-muted-foreground hover:text-foreground transition-colors">
            Voltar ao catálogo
          </a>
        </div>
      </Shell>
    )
  }

  // ── Resumo lateral (compartilhado entre os steps) ────────────────────────────
  const Summary = (
    <aside className="space-y-3 rounded-xl border border-border bg-card p-5 lg:sticky lg:top-6 lg:self-start">
      <h2 className="label-eyebrow">Resumo</h2>
      <div className="space-y-1.5 text-sm">
        <div className="flex justify-between text-muted-foreground">
          <span>Subtotal</span>
          <span>{formatBRL(subtotalCents / 100)}</span>
        </div>
        {cart.discount_cents > 0 && (
          <div className="flex justify-between text-success">
            <span>Desconto</span>
            <span>−{formatBRL(cart.discount_cents / 100)}</span>
          </div>
        )}
        <div className="flex justify-between border-t border-border pt-2 font-semibold">
          <span>Total</span>
          <span className="font-display text-lg text-primary">
            {formatBRL(Math.max(0, totalCents) / 100)}
          </span>
        </div>
      </div>
    </aside>
  )

  // ── Steps ────────────────────────────────────────────────────────────────────
  return (
    <Shell>
      <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
        <div className="space-y-6">

          {/* Step 1 — Revisão */}
          {step === 1 && (
            <div className="space-y-5">
              <h1 className="font-display text-3xl tracking-wide">Revise seu pedido</h1>

              <div className="space-y-3">
                {cart.items.map((item, i) => (
                  <div key={i}
                    className="rounded-lg border border-border bg-card p-4 flex gap-3">
                    <div className="flex-1 min-w-0 space-y-1">
                      <span className="inline-block rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                        {KIND_LABEL[item.kind]}
                      </span>
                      <p className="font-medium text-sm">{itemTitle(item)}</p>
                      {itemSubtitle(item) && (
                        <p className="text-xs text-muted-foreground">{itemSubtitle(item)}</p>
                      )}
                      {item.kind === "product" && (
                        <div className="flex items-center gap-2 pt-1">
                          <button onClick={() => updateQty(i, item.quantity - 1)}
                            className="flex h-6 w-6 items-center justify-center rounded border border-border hover:bg-accent">
                            <Minus className="h-3 w-3" />
                          </button>
                          <span className="w-6 text-center text-sm">{item.quantity}</span>
                          <button onClick={() => updateQty(i, item.quantity + 1)}
                            className="flex h-6 w-6 items-center justify-center rounded border border-border hover:bg-accent">
                            <Plus className="h-3 w-3" />
                          </button>
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col items-end justify-between">
                      <button onClick={() => removeItem(i)} aria-label="Remover item"
                        className="text-muted-foreground hover:text-destructive transition-colors">
                        <X className="h-4 w-4" />
                      </button>
                      <span className="font-display text-sm text-primary">
                        {formatBRL(
                          item.kind === "product"
                            ? parseFloat(item.price) * item.quantity
                            : parseFloat(item.price)
                        )}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Cupom */}
              <div className="space-y-2">
                {cart.coupon_code ? (
                  <div className="flex items-center justify-between rounded-lg border border-primary/30 bg-primary/5 px-3 py-2">
                    <span className="inline-flex items-center gap-1.5 text-sm">
                      <Tag className="h-3.5 w-3.5 text-primary" /> {cart.coupon_code}
                    </span>
                    <button onClick={clearCoupon}
                      className="text-xs text-muted-foreground hover:text-destructive transition-colors">
                      Remover
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="flex gap-2">
                      <Input value={couponInput} onChange={(e) => setCouponInput(e.target.value)}
                        placeholder="Cupom de desconto" className="h-9 max-w-xs" />
                      <button onClick={handleApplyCoupon}
                        disabled={validating || !couponInput.trim()}
                        className="book-btn-secondary shrink-0 px-3 py-1 text-xs disabled:opacity-40">
                        {validating ? "…" : "Aplicar"}
                      </button>
                    </div>
                    {couponError && <p className="text-xs text-destructive">{couponError}</p>}
                  </>
                )}
              </div>

              <div className="flex justify-end pt-2">
                <button onClick={() => setStep(2)} className="book-btn-primary px-8 py-3 text-sm">
                  Continuar →
                </button>
              </div>
            </div>
          )}

          {/* Step 2 — Seus dados */}
          {step === 2 && (
            <div className="space-y-5">
              <h1 className="font-display text-3xl tracking-wide">Seus dados</h1>

              {portalIdentity ? (
                <>
                  <div className="rounded-lg border border-border bg-card p-6 space-y-2">
                    <p className="text-xs text-muted-foreground uppercase tracking-widest">Logado como</p>
                    <p className="font-display text-2xl">Olá, {portalIdentity.name ?? "cliente"}</p>
                    <p className="text-muted-foreground">
                      {portalIdentity.phone_national_normalized || portalIdentity.phone_e164}
                    </p>
                  </div>
                  {submitError && <p className="text-sm text-destructive">{submitError}</p>}
                  <div className="flex justify-between pt-4">
                    <button onClick={() => setStep(1)} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                      ← Voltar
                    </button>
                    <button onClick={handleConfirm} disabled={submitting}
                      className="book-btn-primary px-8 py-3 text-sm disabled:opacity-50">
                      {submitting ? "Confirmando…" : "Confirmar pedido →"}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  {/* CTA de login */}
                  <div className="rounded-lg border border-border bg-muted/50 p-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm">Já tem conta? Entre para confirmar sem digitar nada.</p>
                    <a href={`/portal/login?redirect=/book/${slug}/checkout`}
                       className="book-btn-secondary px-3 py-1.5 text-xs text-center">
                      Entrar
                    </a>
                  </div>
                  <div className="text-center text-xs text-muted-foreground py-1">
                    ── ou continue como visitante ──
                  </div>

                  {/* Formulário */}
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="name">Nome completo *</Label>
                      <Input id="name" value={name} onChange={(e) => setName(e.target.value)}
                        placeholder="Seu nome completo" />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div className="space-y-2">
                        <Label htmlFor="phone">Telefone *</Label>
                        <Input id="phone" value={phone} onChange={(e) => setPhone(e.target.value)}
                          placeholder="(11) 90000-0000" />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="email">E-mail (opcional)</Label>
                        <Input id="email" type="email" value={email}
                          onChange={(e) => setEmail(e.target.value)} placeholder="seu@email.com" />
                      </div>
                    </div>
                  </div>

                  {submitError && <p className="text-sm text-destructive">{submitError}</p>}

                  <div className="flex justify-between pt-2">
                    <button onClick={() => setStep(1)} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                      ← Voltar
                    </button>
                    <button onClick={handleConfirm} disabled={submitting || !name || !phone}
                      className="book-btn-primary px-8 py-3 text-sm disabled:opacity-50">
                      {submitting ? "Confirmando…" : "Confirmar pedido →"}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {Summary}
      </div>
    </Shell>
  )
}

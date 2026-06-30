"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Minus, Plus, Tag, X } from "lucide-react"
import { publicFetch } from "@/lib/api"
import { formatBRL } from "@/lib/utils"
import { useCart, type CartItem } from "@/context/CartContext"
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from "@/components/ui/sheet"
import { Input } from "@/components/ui/input"

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
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
      timeZone: "America/Sao_Paulo",
    })
    return item.professional_name
      ? `${when} · ${item.professional_name}`
      : when
  }
  return null
}

export function CartDrawer({
  slug, open, onOpenChange,
}: {
  slug: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const router = useRouter()
  const {
    cart, removeItem, updateQty, applyCoupon, clearCoupon,
    subtotalCents, totalCents,
  } = useCart()

  const [couponInput, setCouponInput] = useState("")
  const [couponError, setCouponError] = useState<string | null>(null)
  const [validating, setValidating]   = useState(false)

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

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="gap-0">
        <SheetHeader>
          <SheetTitle>Seu carrinho</SheetTitle>
        </SheetHeader>

        {/* Lista de itens */}
        <div className="flex-1 overflow-y-auto py-4 space-y-3">
          {cart.items.length === 0 ? (
            <p className="text-sm text-muted-foreground py-12 text-center">
              Seu carrinho está vazio.
            </p>
          ) : (
            cart.items.map((item, i) => (
              <div key={i}
                className="rounded-lg border border-border bg-card p-3 flex gap-3">
                <div className="flex-1 min-w-0 space-y-1">
                  <span className="inline-block rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                    {KIND_LABEL[item.kind]}
                  </span>
                  <p className="font-medium text-sm truncate">{itemTitle(item)}</p>
                  {itemSubtitle(item) && (
                    <p className="text-xs text-muted-foreground">{itemSubtitle(item)}</p>
                  )}

                  {item.kind === "product" ? (
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={() => updateQty(i, item.quantity - 1)}
                        className="flex h-6 w-6 items-center justify-center rounded border border-border hover:bg-accent">
                        <Minus className="h-3 w-3" />
                      </button>
                      <span className="w-6 text-center text-sm">{item.quantity}</span>
                      <button
                        onClick={() => updateQty(i, item.quantity + 1)}
                        className="flex h-6 w-6 items-center justify-center rounded border border-border hover:bg-accent">
                        <Plus className="h-3 w-3" />
                      </button>
                    </div>
                  ) : null}
                </div>

                <div className="flex flex-col items-end justify-between">
                  <button
                    onClick={() => removeItem(i)}
                    aria-label="Remover item"
                    className="text-muted-foreground hover:text-destructive transition-colors">
                    <X className="h-4 w-4" />
                  </button>
                  <span className="font-display text-sm text-primary">
                    {formatBRL(
                      (item.kind === "product"
                        ? parseFloat(item.price) * item.quantity
                        : parseFloat(item.price))
                    )}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>

        {cart.items.length > 0 && (
          <div className="border-t border-border pt-4 space-y-4">
            {/* Cupom */}
            <div className="space-y-2">
              {cart.coupon_code ? (
                <div className="flex items-center justify-between rounded-lg border border-primary/30 bg-primary/5 px-3 py-2">
                  <span className="inline-flex items-center gap-1.5 text-sm">
                    <Tag className="h-3.5 w-3.5 text-primary" />
                    {cart.coupon_code}
                  </span>
                  <button
                    onClick={clearCoupon}
                    className="text-xs text-muted-foreground hover:text-destructive transition-colors">
                    Remover
                  </button>
                </div>
              ) : (
                <>
                  <div className="flex gap-2">
                    <Input
                      value={couponInput}
                      onChange={(e) => setCouponInput(e.target.value)}
                      placeholder="Cupom de desconto"
                      className="h-9"
                    />
                    <button
                      onClick={handleApplyCoupon}
                      disabled={validating || !couponInput.trim()}
                      className="book-btn-secondary shrink-0 px-3 py-1 text-xs disabled:opacity-40">
                      {validating ? "…" : "Aplicar"}
                    </button>
                  </div>
                  {couponError && (
                    <p className="text-xs text-destructive">{couponError}</p>
                  )}
                </>
              )}
            </div>

            {/* Totais */}
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

            {/* Ações */}
            <div className="space-y-2">
              <button
                onClick={() => { onOpenChange(false); router.push(`/book/${slug}/checkout`) }}
                className="book-btn-primary w-full py-3 text-sm">
                Ir para checkout
              </button>
              <button
                onClick={() => onOpenChange(false)}
                className="w-full py-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
                Continuar comprando
              </button>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

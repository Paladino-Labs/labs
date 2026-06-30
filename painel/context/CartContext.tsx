"use client"
import { createContext, useContext, useEffect, useState, ReactNode } from "react"

// ── Tipos ──────────────────────────────────────────────────────────────────

export type CartServiceItem = {
  kind:            "service"
  service_id:      string
  service_name:    string
  professional_id: string | null
  professional_name: string | null
  start_at:        string    // ISO UTC
  end_at:          string    // ISO UTC
  price:           string    // Decimal-string
}

export type CartPackageItem = {
  kind:         "package"
  package_id:   string
  package_name: string
  price:        string
  total_cotas:  number
}

export type CartSubscriptionItem = {
  kind:      "subscription"
  plan_id:   string
  plan_name: string
  price:     string
  cycle_days: number
}

export type CartProductItem = {
  kind:        "product"
  product_id:  string
  product_name: string
  price:       string
  quantity:    number
}

export type CartItem =
  | CartServiceItem
  | CartPackageItem
  | CartSubscriptionItem
  | CartProductItem

export interface Cart {
  items:         CartItem[]
  coupon_code?:  string
  discount_cents: number  // em centavos, calculado no cliente
  slug:          string
}

// ── Context ────────────────────────────────────────────────────────────────

interface CartContextValue {
  cart:        Cart
  hydrated:    boolean
  addItem:     (item: CartItem) => void
  removeItem:  (index: number) => void
  updateQty:   (index: number, qty: number) => void
  applyCoupon: (code: string, discountCents: number) => void
  clearCoupon: () => void
  clear:       () => void
  totalCents:  number
  subtotalCents: number
  itemCount:   number
}

const CartContext = createContext<CartContextValue | null>(null)

export function useCart() {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error("useCart must be used within CartProvider")
  return ctx
}

// ── Provider ───────────────────────────────────────────────────────────────

function storageKey(slug: string) {
  return `paladino_cart_v1_${slug}`
}

function priceToInt(price: string): number {
  return Math.round(parseFloat(price) * 100)
}

function itemPrice(item: CartItem): number {
  if (item.kind === "product")
    return priceToInt(item.price) * item.quantity
  return priceToInt(item.price)
}

export function CartProvider({
  children,
  slug,
}: {
  children: ReactNode
  slug: string
}) {
  const emptyCart: Cart = { items: [], slug, discount_cents: 0 }
  const [cart, setCart]       = useState<Cart>(emptyCart)
  const [hydrated, setHydrated] = useState(false)

  // Hidratar do localStorage na montagem (padrão AuthContext)
  useEffect(() => {
    if (typeof window === "undefined") { setHydrated(true); return }
    try {
      const raw = localStorage.getItem(storageKey(slug))
      if (raw) setCart(JSON.parse(raw) as Cart)
    } catch { /* localStorage indisponível */ }
    setHydrated(true)
  }, [slug])

  // Persistir no localStorage a cada mudança
  useEffect(() => {
    if (!hydrated) return
    if (typeof window === "undefined") return
    try {
      localStorage.setItem(storageKey(slug), JSON.stringify(cart))
    } catch { /* quota exceeded etc */ }
  }, [cart, hydrated, slug])

  const subtotalCents = cart.items.reduce((acc, i) => acc + itemPrice(i), 0)
  const totalCents    = subtotalCents - cart.discount_cents
  const itemCount     = cart.items.length

  function addItem(item: CartItem) {
    setCart(prev => ({ ...prev, items: [...prev.items, item] }))
  }

  function removeItem(index: number) {
    setCart(prev => ({
      ...prev,
      items: prev.items.filter((_, i) => i !== index),
    }))
  }

  function updateQty(index: number, qty: number) {
    if (qty < 1) return removeItem(index)
    setCart(prev => {
      const items = [...prev.items]
      const item  = items[index]
      if (item.kind === "product") items[index] = { ...item, quantity: qty }
      return { ...prev, items }
    })
  }

  function applyCoupon(code: string, discountCents: number) {
    setCart(prev => ({ ...prev, coupon_code: code, discount_cents: discountCents }))
  }

  function clearCoupon() {
    setCart(prev => ({ ...prev, coupon_code: undefined, discount_cents: 0 }))
  }

  function clear() {
    setCart(emptyCart)
    if (typeof window !== "undefined")
      localStorage.removeItem(storageKey(slug))
  }

  return (
    <CartContext.Provider value={{
      cart, hydrated, addItem, removeItem, updateQty,
      applyCoupon, clearCoupon, clear, totalCents, subtotalCents, itemCount,
    }}>
      {children}
    </CartContext.Provider>
  )
}

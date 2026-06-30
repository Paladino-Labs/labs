"use client"

import { useState } from "react"
import { ShoppingCart } from "lucide-react"
import { useCart } from "@/context/CartContext"
import { CartDrawer } from "./CartDrawer"

export function CartButton({ slug }: { slug: string }) {
  const { itemCount } = useCart()
  const [open, setOpen] = useState(false)

  if (itemCount === 0) return null

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="Abrir carrinho"
        className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105"
      >
        <ShoppingCart className="h-6 w-6" />
        <span className="absolute -top-1 -right-1 flex h-6 min-w-6 items-center justify-center rounded-full border-2 border-background bg-foreground px-1.5 text-xs font-semibold text-background">
          {itemCount}
        </span>
      </button>

      <CartDrawer slug={slug} open={open} onOpenChange={setOpen} />
    </>
  )
}

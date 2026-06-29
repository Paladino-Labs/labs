"use client"

import { Suspense, useEffect, useState } from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { publicFetch } from "@/lib/api"
import { CartProvider } from "@/context/CartContext"
import BookingFlow from "../BookingFlow"

// Tela dedicada de agendamento (separada da vitrine), espelhando o protótipo:
// o cliente é direcionado para cá em vez de o fluxo expandir abaixo dos serviços.
export default function AgendarPage() {
  return (
    <Suspense>
      <AgendarRoot />
    </Suspense>
  )
}

function AgendarRoot() {
  const { slug } = useParams<{ slug: string }>()
  return (
    <CartProvider slug={slug}>
      <AgendarContent slug={slug} />
    </CartProvider>
  )
}

function AgendarContent({ slug }: { slug: string }) {
  const searchParams = useSearchParams()
  const router       = useRouter()

  const [companyName,  setCompanyName]  = useState("")
  const [bookingToken, setBookingToken] = useState<string | null>(searchParams.get("t"))
  const initialServiceId = searchParams.get("service")

  // Nome da empresa para o link "voltar à vitrine" no header do BookingFlow.
  useEffect(() => {
    publicFetch<{ company_name: string }>(`/booking/${slug}/profile`)
      .then((p) => setCompanyName(p.company_name))
      .catch(() => {})
  }, [slug])

  function handleTokenChange(token: string) {
    setBookingToken(token)
    const url = new URL(window.location.href)
    url.searchParams.set("t", token)
    router.replace(url.pathname + url.search, { scroll: false })
  }

  return (
    <BookingFlow
      slug={slug}
      companyName={companyName}
      initialToken={bookingToken}
      onTokenChange={handleTokenChange}
      initialServiceId={initialServiceId}
    />
  )
}

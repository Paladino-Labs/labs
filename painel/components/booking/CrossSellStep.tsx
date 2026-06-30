"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Check, Package, RefreshCw } from "lucide-react"
import { publicFetch } from "@/lib/api"
import { cn, formatBRLFromDecimal } from "@/lib/utils"
import { useCart } from "@/context/CartContext"
import type { PublicPackage, PublicPlan } from "@/lib/portal-types"
import { Skeleton } from "@/components/ui/skeleton"

interface CrossSellStepProps {
  slug:              string
  serviceId:         string
  serviceName:       string
  servicePrice:      string
  professionalId:    string | null
  professionalName:  string | null
  startAt:           string
  endAt:             string
  onConfirmOnly:     () => void  // prosseguir sem extras
}

export function CrossSellStep({
  slug, serviceId, serviceName, servicePrice,
  professionalId, professionalName, startAt, endAt, onConfirmOnly,
}: CrossSellStepProps) {
  const router = useRouter()
  const { addItem, itemCount } = useCart()

  const [loading, setLoading]   = useState(true)
  const [packages, setPackages] = useState<PublicPackage[]>([])
  const [plans, setPlans]       = useState<PublicPlan[]>([])
  const [added, setAdded]       = useState<Record<string, boolean>>({})

  // Conta apenas os extras adicionados nesta tela (exclui o serviço).
  const extrasAdded = Object.values(added).filter(Boolean).length

  useEffect(() => {
    let cancelled = false
    Promise.all([
      publicFetch<PublicPackage[]>(`/booking/${slug}/packages?service_id=${serviceId}`)
        .catch(() => [] as PublicPackage[]),
      publicFetch<PublicPlan[]>(`/booking/${slug}/subscription-plans?service_id=${serviceId}`)
        .catch(() => [] as PublicPlan[]),
    ]).then(([pkgs, pls]) => {
      if (cancelled) return
      // Skip silencioso da Tela 4 quando não há cross-sell.
      if (pkgs.length === 0 && pls.length === 0) {
        onConfirmOnly()
        return
      }
      setPackages(pkgs)
      setPlans(pls)
      setLoading(false)
    })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, serviceId])

  function addServiceToCart() {
    addItem({
      kind:              "service",
      service_id:        serviceId,
      service_name:      serviceName,
      professional_id:   professionalId,
      professional_name: professionalName,
      start_at:          startAt,
      end_at:            endAt,
      price:             servicePrice,
    })
  }

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-48 rounded-xl" />)}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-2xl tracking-wide">Aproveite e leve mais por menos</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Pacotes e assinaturas que incluem {serviceName}
        </p>
      </div>

      {/* Pacotes */}
      {packages.length > 0 && (
        <div className="space-y-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <Package className="h-4 w-4" /> Pacotes
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {packages.map((pkg) => {
              const key = `pkg:${pkg.package_id}`
              const isAdded = !!added[key]
              return (
                <div key={pkg.package_id}
                  className={cn(
                    "rounded-xl border border-border bg-card p-4 flex flex-col gap-3 transition-colors",
                    isAdded && "bg-muted/60 border-primary/40"
                  )}>
                  <p className="font-semibold text-sm">{pkg.name}</p>
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
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>{pkg.total_cotas} {pkg.total_cotas === 1 ? "cota" : "cotas"} no total</span>
                    {pkg.validity_days && <span>· Válido por {pkg.validity_days} dias</span>}
                  </div>
                  <div className="flex items-center justify-between mt-auto pt-1">
                    <span className="font-display text-lg text-primary">
                      {formatBRLFromDecimal(pkg.price)}
                    </span>
                    <button
                      disabled={isAdded}
                      onClick={() => {
                        addItem({
                          kind: "package", package_id: pkg.package_id,
                          package_name: pkg.name, price: pkg.price,
                          total_cotas: pkg.total_cotas,
                        })
                        setAdded((p) => ({ ...p, [key]: true }))
                      }}
                      className={cn(
                        "px-3 py-1 text-xs",
                        isAdded
                          ? "inline-flex items-center gap-1 text-success"
                          : "book-btn-secondary"
                      )}>
                      {isAdded ? <><Check className="h-3 w-3" /> Adicionado</> : "Adicionar"}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Assinaturas */}
      {plans.length > 0 && (
        <div className="space-y-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <RefreshCw className="h-4 w-4" /> Assinaturas
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {plans.map((plan) => {
              const key = `plan:${plan.plan_id}`
              const isAdded = !!added[key]
              return (
                <div key={plan.plan_id}
                  className={cn(
                    "rounded-xl border border-border bg-card p-4 flex flex-col gap-3 transition-colors",
                    isAdded && "bg-muted/60 border-primary/40"
                  )}>
                  <p className="font-semibold text-sm">{plan.name}</p>
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
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>{plan.total_cotas_per_cycle} {plan.total_cotas_per_cycle === 1 ? "cota" : "cotas"}/ciclo</span>
                    <span>· Renova a cada {plan.cycle_days} dias</span>
                  </div>
                  <div className="flex items-center justify-between mt-auto pt-1">
                    <span className="font-display text-lg text-primary">
                      {formatBRLFromDecimal(plan.price)}
                    </span>
                    <button
                      disabled={isAdded}
                      onClick={() => {
                        addItem({
                          kind: "subscription", plan_id: plan.plan_id,
                          plan_name: plan.name, price: plan.price,
                          cycle_days: plan.cycle_days,
                        })
                        setAdded((p) => ({ ...p, [key]: true }))
                      }}
                      className={cn(
                        "px-3 py-1 text-xs",
                        isAdded
                          ? "inline-flex items-center gap-1 text-success"
                          : "book-btn-secondary"
                      )}>
                      {isAdded ? <><Check className="h-3 w-3" /> Adicionado</> : "Assinar"}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Rodapé de ações */}
      <div className="flex flex-col-reverse items-stretch gap-2 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-between">
        <button
          onClick={onConfirmOnly}
          className="book-btn-secondary px-5 py-2.5 text-sm">
          Confirmar só o agendamento
        </button>
        {(extrasAdded > 0 || itemCount > 0) && (
          <button
            onClick={() => { addServiceToCart(); router.push(`/book/${slug}/checkout`) }}
            className="book-btn-primary px-6 py-2.5 text-sm">
            Continuar para checkout →
          </button>
        )}
      </div>
    </div>
  )
}

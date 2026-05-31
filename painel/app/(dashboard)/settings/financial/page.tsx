"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

interface FinancialSettings {
  payment_provider: string | null
  external_account_id: string | null
  external_account_status: string | null
  external_account_created_at: string | null
  accounts_count: number
}

function AsaasStatusBanner({ status }: { status: string | null }) {
  if (status === "active") {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800">
        <p className="font-medium">Subconta Asaas ativa</p>
        <p className="text-green-700 mt-1">
          Sua conta de pagamentos está ativa e pronta para receber cobranças.
        </p>
      </div>
    )
  }

  if (status === "pending_verification") {
    return (
      <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800">
        <p className="font-medium">Subconta Asaas em análise</p>
        <p className="text-yellow-700 mt-1">
          Sua conta de pagamentos está sendo verificada pela Asaas. Este processo
          pode levar até 2 dias úteis. Você receberá uma notificação quando a conta
          for aprovada.
        </p>
        <p className="text-yellow-700 mt-2">
          Enquanto isso, você pode continuar configurando seu sistema normalmente.
        </p>
      </div>
    )
  }

  if (status === "suspended") {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        <p className="font-medium">Subconta Asaas suspensa</p>
        <p className="text-red-700 mt-1">
          Sua conta foi suspensa. Entre em contato com o suporte Asaas para mais informações.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">Pagamentos online não configurados</p>
      <p className="mt-1">
        A subconta de pagamentos ainda não foi criada. Entre em contato com o suporte
        Paladino para configurar seus pagamentos.
      </p>
    </div>
  )
}

export default function FinancialSettingsPage() {
  const [data, setData] = useState<FinancialSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<FinancialSettings>("/financial/settings")
      .then(setData)
      .catch((e: unknown) => setError((e as Error).message ?? "Erro ao carregar"))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-muted-foreground">Carregando…</p>
  if (error)   return <p className="text-destructive">{error}</p>
  if (!data)   return null

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="font-display text-3xl tracking-wide">Configurações Financeiras</h1>

      <Card>
        <CardHeader>
          <CardTitle>Status da Subconta Asaas</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <AsaasStatusBanner status={data.external_account_status} />

          {data.external_account_id && (
            <div className="text-sm text-muted-foreground space-y-1 pt-2 border-t">
              <p>
                <span className="text-foreground font-medium">ID da conta:</span>{" "}
                {data.external_account_id}
              </p>
              {data.external_account_created_at && (
                <p>
                  <span className="text-foreground font-medium">Criada em:</span>{" "}
                  {new Date(data.external_account_created_at).toLocaleDateString("pt-BR")}
                </p>
              )}
              <p>
                <span className="text-foreground font-medium">Contas financeiras:</span>{" "}
                {data.accounts_count}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

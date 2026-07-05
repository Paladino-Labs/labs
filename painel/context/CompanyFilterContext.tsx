"use client"
// Redesign F4a — filtro de empresa do Portal do Cliente.
// Estado de sessão de UI (NÃO persiste em localStorage — reset ao recarregar
// é aceitável; o padrão é "Todas"). Consumido pelo CompanyFilterBar e pelas
// telas de listagem via ?company_id=.
import { createContext, useContext, useEffect, useState, ReactNode } from "react"
import { portal } from "@/lib/portal-api"
import type { PortalCompanyItem } from "@/lib/portal-types"

interface CompanyFilterValue {
  companies:         PortalCompanyItem[]
  companiesLoading:  boolean
  selectedCompanyId: string | null   // null = "Todas"
  setSelectedCompanyId: (id: string | null) => void
  selectedCompany:   PortalCompanyItem | null   // derivado, p/ CTA/labels
}

const CompanyFilterContext = createContext<CompanyFilterValue | null>(null)

export function useCompanyFilter() {
  const ctx = useContext(CompanyFilterContext)
  if (!ctx) throw new Error("useCompanyFilter must be used within CompanyFilterProvider")
  return ctx
}

export function CompanyFilterProvider({ children }: { children: ReactNode }) {
  const [companies, setCompanies] = useState<PortalCompanyItem[]>([])
  const [companiesLoading, setCompaniesLoading] = useState(true)
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null)

  useEffect(() => {
    portal.get<PortalCompanyItem[]>("/portal/companies")
      .then((data) => setCompanies(data))
      .catch(() => setCompanies([]))
      .finally(() => setCompaniesLoading(false))
  }, [])

  const selectedCompany = selectedCompanyId
    ? companies.find(c => c.company_id === selectedCompanyId) ?? null
    : null

  return (
    <CompanyFilterContext.Provider value={{
      companies, companiesLoading,
      selectedCompanyId, setSelectedCompanyId, selectedCompany,
    }}>
      {children}
    </CompanyFilterContext.Provider>
  )
}

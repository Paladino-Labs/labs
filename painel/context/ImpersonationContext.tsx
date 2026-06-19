"use client"

import { createContext, useCallback, useContext, useEffect, useState } from "react"

/**
 * Sessão de impersonation ativa do PLATFORM_OWNER.
 *
 * Persistida em **sessionStorage** (não localStorage) — intencional: a sessão
 * de impersonation morre ao fechar a aba. O header `X-Impersonate-Grant` ainda
 * NÃO é injetado por `apiFetch` neste sprint (wiring futuro de um wrapper fino);
 * aqui o estado dirige apenas o banner persistente do shell do owner.
 */
export interface ActiveGrant {
  grant_id: string
  company_id: string
  company_name: string
  mode: string
  expires_at: string
}

interface ImpersonationContextValue {
  activeGrant: ActiveGrant | null
  startImpersonation: (grant: ActiveGrant) => void
  endImpersonation: () => void
}

const STORAGE_KEY = "impersonation_grant"

const ImpersonationContext = createContext<ImpersonationContextValue>({
  activeGrant: null,
  startImpersonation: () => {},
  endImpersonation: () => {},
})

export default function ImpersonationProvider({ children }: { children: React.ReactNode }) {
  const [activeGrant, setActiveGrant] = useState<ActiveGrant | null>(null)

  // Hidrata do sessionStorage no mount (sobrevive a refresh, não a fechar a aba)
  useEffect(() => {
    if (typeof window === "undefined") return
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return
    try {
      const grant = JSON.parse(raw) as ActiveGrant
      // Descarta grants já expirados
      if (new Date(grant.expires_at).getTime() > Date.now()) {
        setActiveGrant(grant)
      } else {
        sessionStorage.removeItem(STORAGE_KEY)
      }
    } catch {
      sessionStorage.removeItem(STORAGE_KEY)
    }
  }, [])

  const startImpersonation = useCallback((grant: ActiveGrant) => {
    setActiveGrant(grant)
    if (typeof window !== "undefined") {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(grant))
    }
  }, [])

  const endImpersonation = useCallback(() => {
    setActiveGrant(null)
    if (typeof window !== "undefined") {
      sessionStorage.removeItem(STORAGE_KEY)
    }
  }, [])

  return (
    <ImpersonationContext.Provider value={{ activeGrant, startImpersonation, endImpersonation }}>
      {children}
    </ImpersonationContext.Provider>
  )
}

export function useImpersonation() {
  return useContext(ImpersonationContext)
}

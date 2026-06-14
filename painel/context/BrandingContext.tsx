"use client"

import { createContext, useContext, useEffect } from "react"

export interface Branding {
  primary: string      // hex
  accent: string       // hex
  logoText: string     // ex: "PALADINO"
  fontDisplay: string  // ex: "Cormorant Garamond"
}

// Mock fixo para a Fase 0.
// Fase 1: substituir por GET /tenant/branding (endpoint público).
const BRANDING_MOCK: Branding = {
  primary: "#16242c",
  accent: "#c79a5a",
  logoText: "PALADINO",
  fontDisplay: "Cormorant Garamond",
}

const BrandingContext = createContext<Branding>(BRANDING_MOCK)

export function BrandingProvider({ children }: { children: React.ReactNode }) {
  const branding = BRANDING_MOCK

  // Injeta os tokens de marca como CSS vars em :root via efeito.
  // Não bloqueia render e não causa SSR mismatch (roda só no cliente).
  useEffect(() => {
    const root = document.documentElement
    root.style.setProperty("--brand-primary", branding.primary)
    root.style.setProperty("--brand-accent", branding.accent)
    root.style.setProperty("--brand-font-display", branding.fontDisplay)
  }, [branding.primary, branding.accent, branding.fontDisplay])

  return (
    <BrandingContext.Provider value={branding}>
      {children}
    </BrandingContext.Provider>
  )
}

export function useBranding() {
  return useContext(BrandingContext)
}

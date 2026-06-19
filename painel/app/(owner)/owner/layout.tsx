"use client"

import ImpersonationProvider from "@/context/ImpersonationContext"
import { OwnerSidebar } from "@/components/owner/OwnerSidebar"
import { ImpersonationBanner } from "@/components/owner/ImpersonationBanner"

/**
 * Chrome do Painel Owner (quarto shell, isolado dos demais).
 *
 * NÃO importa Sidebar/Header/BrandingProvider do tenant. O guard de
 * PLATFORM_OWNER vive no layout externo `(owner)/layout.tsx` (não recriar aqui).
 */
export default function OwnerChromeLayout({ children }: { children: React.ReactNode }) {
  return (
    <ImpersonationProvider>
      <div className="flex min-h-screen">
        <OwnerSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <ImpersonationBanner />
          <main className="flex-1 overflow-auto bg-background px-6 py-8 md:px-10 md:py-10">
            {children}
          </main>
        </div>
      </div>
    </ImpersonationProvider>
  )
}

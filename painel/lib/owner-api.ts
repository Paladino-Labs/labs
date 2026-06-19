/**
 * Helper de API para o Painel Owner.
 *
 * Baseado em `apiFetch` (JWT tenant, company_id=null), com injeção automática
 * de `X-Impersonate-Grant: {grant_id}` quando há uma sessão de impersonation
 * ativa em sessionStorage. Criado como wrapper separado porque a injeção do
 * header de impersonation é uma preocupação transversal às 7 telas do owner —
 * centralizá-la aqui evita repetição e risco de esquecer call-sites.
 *
 * NOTA ARQUITETURAL: A diretriz original ("sem ownerFetch; reusar api.*") foi
 * revogada neste sprint porque a injeção de X-Impersonate-Grant é necessidade
 * real — apiFetch não expõe extraHeaders na sua superfície pública.
 */

import { apiFetch } from "./api"

// Mesma chave persistida pelo ImpersonationContext (sessionStorage).
const IMPERSONATION_STORAGE_KEY = "impersonation_grant"

interface StoredGrant {
  grant_id: string
  expires_at: string
}

function getImpersonationHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {}
  try {
    const raw = sessionStorage.getItem(IMPERSONATION_STORAGE_KEY)
    if (!raw) return {}
    const grant = JSON.parse(raw) as StoredGrant
    if (new Date(grant.expires_at).getTime() <= Date.now()) {
      sessionStorage.removeItem(IMPERSONATION_STORAGE_KEY)
      return {}
    }
    return { "X-Impersonate-Grant": grant.grant_id }
  } catch {
    return {}
  }
}

async function ownerFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const impersonationHeaders = getImpersonationHeaders()
  return apiFetch<T>(path, {
    ...options,
    headers: {
      ...impersonationHeaders,
      ...options?.headers,
    },
  })
}

export const owner = {
  get: <T>(path: string) => ownerFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    ownerFetch<T>(path, {
      method: "POST",
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    }),
  put: <T>(path: string, body: unknown) =>
    ownerFetch<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    ownerFetch<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => ownerFetch<T>(path, { method: "DELETE" }),
}

// Helper de API ISOLADO do Portal do Cliente (Fase 5B).
//
// Espelha o padrão de `apiFetch`/`publicFetch` de `lib/api.ts`, mas:
//  - Lê o token de uma CHAVE PRÓPRIA do localStorage ("portal_token") —
//    NUNCA a chave "token" do painel do tenant (JWTs são mutuamente
//    inutilizáveis: o portal usa type="portal" sem company_id).
//  - No 401: limpa o token do portal e redireciona para /portal/login
//    (não para o login do tenant).
//  - Expõe `.status` no erro lançado (Object.assign), igual a apiFetch.
//
// ⛔ Não importar apiFetch, setAuthErrorHandler, AuthContext, Sidebar nem
//    Header do painel do tenant aqui ou em qualquer tela do portal.
import { BASE } from "./api"

export const PORTAL_TOKEN_KEY = "portal_token"

function parseDetailMessage(detail: unknown): string {
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d.msg ?? "Erro de validação").join("; ")
  }
  if (typeof detail === "string") return detail
  return "Erro desconhecido"
}

function getPortalToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(PORTAL_TOKEN_KEY)
}

export function setPortalToken(token: string): void {
  if (typeof window !== "undefined") localStorage.setItem(PORTAL_TOKEN_KEY, token)
}

export function clearPortalToken(): void {
  if (typeof window !== "undefined") localStorage.removeItem(PORTAL_TOKEN_KEY)
}

interface PortalApiError extends Error {
  status: number
}

// Handler global de 401, registrado pelo layout do grupo (app)/ após montagem.
// Análogo ao setAuthErrorHandler do tenant, porém SEPARADO (módulo distinto).
let _onPortalAuthError: (() => void) | null = null
let _redirecting = false

export function setPortalAuthErrorHandler(handler: () => void): void {
  _onPortalAuthError = handler
  _redirecting = false
}

export async function portalFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getPortalToken()

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = Object.assign(new Error(parseDetailMessage(body.detail)), {
      status: res.status,
    }) as PortalApiError

    // 401 = token portal expirado/inválido → limpa e volta ao login do portal.
    if (res.status === 401) {
      clearPortalToken()
      if (_onPortalAuthError && !_redirecting) {
        _redirecting = true
        _onPortalAuthError()
      }
    }

    throw err
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const portal = {
  get:    <T>(path: string)                => portalFetch<T>(path),
  post:   <T>(path: string, body?: unknown) =>
    portalFetch<T>(path, { method: "POST", ...(body !== undefined ? { body: JSON.stringify(body) } : {}) }),
  patch:  <T>(path: string, body: unknown) =>
    portalFetch<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string)                => portalFetch<T>(path, { method: "DELETE" }),
}

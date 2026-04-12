const BASE = process.env.NEXT_PUBLIC_API_URL!

function getToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem("token")
}

interface ApiError extends Error {
  status: number
}

// Callback registrado pelo AuthContext após hidratação.
// Chamado uma única vez quando o servidor responde 401 (token inválido/expirado).
let _onAuthError: (() => void) | null = null
let _redirecting = false

export function setAuthErrorHandler(handler: () => void): void {
  _onAuthError = handler
  _redirecting = false
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken()

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
    const err = Object.assign(new Error(body.detail ?? "Erro desconhecido"), {
      status: res.status,
    }) as ApiError

    // 401 = token expirado/inválido → força logout
    if (res.status === 401 && _onAuthError && !_redirecting) {
      _redirecting = true
      _onAuthError()
    }

    throw err
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get:    <T>(path: string)                => apiFetch<T>(path),
  post:   <T>(path: string, body: unknown) => apiFetch<T>(path, { method: "POST",   body: JSON.stringify(body) }),
  patch:  <T>(path: string, body: unknown) => apiFetch<T>(path, { method: "PATCH",  body: JSON.stringify(body) }),
  delete: <T>(path: string)                => apiFetch<T>(path, { method: "DELETE" }),
}

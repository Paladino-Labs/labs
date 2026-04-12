"use client"

import { createContext, useCallback, useContext, useEffect, useState } from "react"
import { setAuthErrorHandler } from "@/lib/api"

interface AuthContextValue {
  token: string | null
  role: string | null
  userId: string | null
  email: string | null
  companyId: string | null
  isAdmin: boolean
  hydrated: boolean   // true após validação do token (localStorage + servidor)
  login: (token: string) => void
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue>({
  token: null,
  role: null,
  userId: null,
  email: null,
  companyId: null,
  isAdmin: false,
  hydrated: false,
  login: () => {},
  logout: () => {},
})

interface JwtPayload {
  sub?: string
  email?: string
  company_id?: string
  role?: string
  exp?: number
}

/** Decodifica o payload do JWT sem verificar assinatura (uso client-only). */
function decodeJwtPayload(token: string): JwtPayload {
  try {
    const payload = token.split(".")[1]
    return JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")))
  } catch {
    return {}
  }
}

/** C1: Verifica se o token já expirou com base no campo exp (segundos). */
function isTokenExpired(payload: JwtPayload): boolean {
  if (!payload.exp) return true
  return payload.exp * 1000 < Date.now()
}

function extractUserData(payload: JwtPayload) {
  return {
    role: payload.role ?? null,
    userId: payload.sub ?? null,
    email: payload.email ?? null,
    companyId: payload.company_id ?? null,
  }
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [userId, setUserId] = useState<string | null>(null)
  const [email, setEmail] = useState<string | null>(null)
  const [companyId, setCompanyId] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)

  function applyUserData(t: string, payload: JwtPayload) {
    const data = extractUserData(payload)
    setToken(t)
    setRole(data.role)
    setUserId(data.userId)
    setEmail(data.email)
    setCompanyId(data.companyId)
  }

  // M1: logout faz redirect direto — não depende do layout estar montado.
  const logout = useCallback(() => {
    localStorage.removeItem("token")
    setToken(null)
    setRole(null)
    setUserId(null)
    setEmail(null)
    setCompanyId(null)
    window.location.replace("/")
  }, [])

  // C2: registra handler global de 401 no api.ts após hidratação.
  useEffect(() => {
    if (!hydrated) return
    setAuthErrorHandler(logout)
  }, [hydrated, logout])

  // Hidratação: C1 (exp) + C4 (/auth/me) + M4 (user data do payload).
  useEffect(() => {
    const stored = localStorage.getItem("token")

    if (!stored) {
      setHydrated(true)
      return
    }

    const payload = decodeJwtPayload(stored)

    // C1: token expirado client-side → descarta imediatamente, sem chamada ao servidor
    if (isTokenExpired(payload)) {
      localStorage.removeItem("token")
      setHydrated(true)
      return
    }

    // C4: valida token contra o servidor antes de confiar nele
    const BASE = process.env.NEXT_PUBLIC_API_URL!
    fetch(`${BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${stored}` },
    })
      .then((res) => {
        if (!res.ok) {
          // Token rejeitado pelo servidor (ex: usuário desativado, secret trocado)
          localStorage.removeItem("token")
          setHydrated(true)
          return null
        }
        return res.json()
      })
      .then((data) => {
        if (data === null) return
        // Token válido — aplica dados do payload (evita round-trip extra)
        applyUserData(stored, payload)
        setHydrated(true)
      })
      .catch(() => {
        // Servidor indisponível: confia no token client-side (exp passou)
        // O interceptor de 401 tratará qualquer rejeição nas chamadas seguintes
        applyUserData(stored, payload)
        setHydrated(true)
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const login = useCallback((newToken: string) => {
    localStorage.setItem("token", newToken)
    const payload = decodeJwtPayload(newToken)
    applyUserData(newToken, payload)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <AuthContext.Provider
      value={{
        token,
        role,
        userId,
        email,
        companyId,
        isAdmin: role === "ADMIN",
        hydrated,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}

"use client"

import { createContext, useCallback, useContext, useEffect, useState } from "react"
import { setAuthErrorHandler, BASE } from "@/lib/api"

export type Role =
  | "OWNER"
  | "ADMIN"
  | "OPERATOR"
  | "PROFESSIONAL"
  | "PLATFORM_OWNER"

export const ROLE_LABELS: Record<Role, string> = {
  OWNER:          "Proprietário",
  ADMIN:          "Administrador",
  OPERATOR:       "Operador",
  PROFESSIONAL:   "Profissional",
  PLATFORM_OWNER: "Paladino",
}

interface AuthContextValue {
  token: string | null
  role: string | null
  setRole: (role: Role) => void
  userId: string | null
  email: string | null
  companyId: string | null
  name: string | null
  professionalId: string | null   // null se não-PROFESSIONAL ou sem vínculo
  isAdmin: boolean
  hydrated: boolean   // true após validação do token (localStorage + servidor)
  login: (token: string) => void
  logout: () => void
  setName: (name: string | null) => void
}

export const AuthContext = createContext<AuthContextValue>({
  token: null,
  role: null,
  setRole: () => {},
  userId: null,
  email: null,
  companyId: null,
  name: null,
  professionalId: null,
  isAdmin: false,
  hydrated: false,
  login: () => {},
  logout: () => {},
  setName: () => {},
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
  const [role, setRoleState] = useState<string | null>(null)
  const [userId, setUserId] = useState<string | null>(null)
  const [email, setEmail] = useState<string | null>(null)
  const [companyId, setCompanyId] = useState<string | null>(null)
  const [name, setName] = useState<string | null>(null)
  const [professionalId, setProfessionalId] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)

  const isDev = process.env.NODE_ENV === "development"

  function applyUserData(t: string, payload: JwtPayload) {
    const data = extractUserData(payload)
    setToken(t)
    // Em dev, um override manual via RoleDevSelector tem precedência sobre o JWT.
    const devRole = isDev ? localStorage.getItem("dev_role") : null
    setRoleState(devRole ?? data.role)
    setUserId(data.userId)
    setEmail(data.email)
    setCompanyId(data.companyId)
  }

  // setRole: atualiza estado em memória + persiste em localStorage (dev_role).
  // Usado apenas pelo RoleDevSelector — não chama API.
  const setRole = useCallback((next: Role) => {
    setRoleState(next)
    if (isDev) localStorage.setItem("dev_role", next)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // M1: logout faz redirect direto — não depende do layout estar montado.
  const logout = useCallback(() => {
    localStorage.removeItem("token")
    setToken(null)
    setRoleState(null)
    setUserId(null)
    setEmail(null)
    setCompanyId(null)
    setName(null)
    setProfessionalId(null)
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
      // Dev: permite testar o shell role-aware sem login real.
      if (isDev) {
        const devRole = localStorage.getItem("dev_role")
        if (devRole) setRoleState(devRole)
      }
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
        if (data?.name) setName(data.name)
        if (data?.professional_id !== undefined) setProfessionalId(data.professional_id ?? null)
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
    // Busca name do /auth/me após login (JWT não carrega name no payload)
    fetch(`${BASE}/auth/me`, { headers: { Authorization: `Bearer ${newToken}` } })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.name) setName(data.name)
        if (data?.professional_id !== undefined) setProfessionalId(data.professional_id ?? null)
      })
      .catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <AuthContext.Provider
      value={{
        token,
        role,
        setRole,
        userId,
        email,
        companyId,
        name,
        professionalId,
        isAdmin: role === "ADMIN",
        hydrated,
        login,
        logout,
        setName,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}

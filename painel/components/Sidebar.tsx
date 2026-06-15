"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth, type Role } from "@/context/AuthContext"
import { cn } from "@/lib/utils"
import {
  LayoutDashboard,
  Calendar,
  ClipboardList,
  ListOrdered,
  MessageSquare,
  Users,
  Send,
  BookOpen,
  Scissors,
  Package,
  Tag,
  Gift,
  Percent,
  CreditCard,
  Landmark,
  Truck,
  ArrowLeftRight,
  BarChart3,
  TrendingUp,
  Wallet,
  RefreshCw,
  FileText,
  Receipt,
  Boxes,
  FileWarning,
  CircleDollarSign,
  UserCheck,
  ShieldCheck,
  Settings,
  ScrollText,
  Star,
  Blocks,
  Palette,
  Link2,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  type LucideIcon,
} from "lucide-react"

type SubItem = {
  title: string
  url: string
  icon: LucideIcon
}

type NavItem = {
  title: string
  url: string
  icon: LucideIcon
  roles: Role[] | "ALL"
  submenu?: SubItem[]
}

type NavGroup = {
  label: string
  items: NavItem[]
}

const ALL: Role[] = ["OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL", "PLATFORM_OWNER"]

const NAV: NavGroup[] = [
  {
    label: "Operação",
    items: [
      { title: "Dashboard",          url: "/dashboard",    icon: LayoutDashboard, roles: "ALL" },
      { title: "Agenda",             url: "/agenda",       icon: Calendar,        roles: "ALL" },
      { title: "Operações",          url: "/appointments", icon: ClipboardList,   roles: "ALL" },
      { title: "Fila",               url: "/fila",         icon: ListOrdered,     roles: ["OWNER", "ADMIN", "OPERATOR"] },
      { title: "Atendimento humano", url: "/inbox",        icon: MessageSquare,   roles: ["OWNER", "ADMIN", "OPERATOR"] },
    ],
  },
  {
    label: "Relacionamento",
    items: [
      { title: "Clientes / CRM", url: "/customers", icon: Users,      roles: "ALL" },
      { title: "CRM",            url: "/crm",       icon: TrendingUp, roles: ["OWNER", "ADMIN"] },
      {
        title: "Comunicação", url: "/comunicacao", icon: Send, roles: ["OWNER", "ADMIN"],
        submenu: [
          { title: "Templates", url: "/comunicacao",      icon: FileText },
          { title: "Logs",      url: "/comunicacao/logs", icon: ScrollText },
        ],
      },
      {
        title: "NPS", url: "/nps", icon: Star, roles: ["OWNER", "ADMIN"],
        submenu: [
          { title: "Pesquisas",    url: "/nps",        icon: Star },
          { title: "Configuração", url: "/nps/config", icon: Settings },
        ],
      },
    ],
  },
  {
    label: "Comercial",
    items: [
      {
        title: "Catálogo", url: "/catalogo", icon: BookOpen, roles: ["OWNER", "ADMIN", "OPERATOR"],
        submenu: [
          { title: "Serviços",   url: "/services",            icon: Scissors },
          { title: "Produtos",   url: "/products",            icon: Package },
          { title: "Categorias", url: "/catalogo/categorias", icon: Tag },
        ],
      },
      {
        title: "Pacotes", url: "/pacotes", icon: Gift, roles: ["OWNER", "ADMIN"],
        submenu: [
          { title: "Planos",  url: "/pacotes",         icon: Gift },
          { title: "Compras", url: "/pacotes/compras", icon: ClipboardList },
        ],
      },
      {
        title: "Assinaturas", url: "/assinaturas", icon: RefreshCw, roles: ["OWNER", "ADMIN"],
        submenu: [
          { title: "Planos",     url: "/assinaturas/planos", icon: ListOrdered },
          { title: "Instâncias", url: "/assinaturas",        icon: Users },
        ],
      },
      { title: "Promoções / Cupons",    url: "/promocoes", icon: Percent, roles: ["OWNER", "ADMIN"] },
    ],
  },
  {
    label: "Financeiro",
    items: [
      { title: "Pagamentos", url: "/financeiro/pagamentos",  icon: CreditCard, roles: ["OWNER", "ADMIN", "OPERATOR"] },
      { title: "Caixa",      url: "/financeiro/conciliacao", icon: Landmark,   roles: ["OWNER", "ADMIN", "OPERATOR"] },
      {
        title: "Gestão Financeira", url: "/financeiro/dre", icon: BarChart3, roles: ["OWNER", "ADMIN"],
        submenu: [
          { title: "DRE",         url: "/financeiro/dre",         icon: TrendingUp },
          { title: "Contas",      url: "/financeiro/contas",      icon: Wallet },
          { title: "Conciliação", url: "/financeiro/conciliacao", icon: RefreshCw },
          { title: "Extrato",     url: "/financeiro/extrato",     icon: FileText },
        ],
      },
      { title: "Despesas",               url: "/despesas",         icon: Receipt,          roles: ["OWNER", "ADMIN", "OPERATOR"] },
      {
        title: "Estoque", url: "/estoque", icon: Boxes, roles: ["OWNER", "ADMIN", "OPERATOR"],
        submenu: [
          { title: "Produtos",      url: "/estoque",               icon: Package },
          { title: "Movimentações", url: "/estoque/movimentacoes", icon: ArrowLeftRight },
        ],
      },
      { title: "Fornecedores",           url: "/fornecedores",     icon: Truck,            roles: ["OWNER", "ADMIN", "OPERATOR"] },
      { title: "Contas a pagar",         url: "/payables",         icon: FileWarning,      roles: ["OWNER", "ADMIN", "OPERATOR"] },
      { title: "Comissões",              url: "/comissoes",        icon: CircleDollarSign, roles: ["OWNER", "ADMIN"] },
      { title: "Taxas",                  url: "/financeiro/taxas", icon: Percent,          roles: ["OWNER", "ADMIN"] },
    ],
  },
  {
    label: "Administração",
    items: [
      { title: "Profissionais",      url: "/professionals",     icon: UserCheck,   roles: ["OWNER", "ADMIN"] },
      { title: "Usuários e acessos", url: "/settings/usuarios", icon: ShieldCheck, roles: ["OWNER", "ADMIN"] },
      {
        title: "Configurações", url: "/settings", icon: Settings, roles: ["OWNER", "ADMIN"],
        submenu: [
          { title: "Financeiro",  url: "/settings/financial",   icon: Wallet },
          { title: "Integrações", url: "/settings/integracoes",  icon: Link2 },
          { title: "Módulos",     url: "/settings/modulos",      icon: Blocks },
          { title: "Branding",    url: "/settings/branding",     icon: Palette },
        ],
      },
      { title: "Auditoria",          url: "/audit",             icon: ScrollText,  roles: ["OWNER", "ADMIN"] },
    ],
  },
]

function isVisible(item: NavItem, role: string | null): boolean {
  if (item.roles === "ALL") return true
  return item.roles.includes((role ?? "") as Role)
}

function isActive(pathname: string, url: string): boolean {
  if (url === "/dashboard") return pathname === url
  return pathname === url || pathname.startsWith(url + "/")
}

function NavLinkRow({
  title,
  url,
  Icon,
  active,
  collapsed,
  onNavigate,
  nested = false,
}: {
  title: string
  url: string
  Icon: LucideIcon
  active: boolean
  collapsed: boolean
  onNavigate?: () => void
  nested?: boolean
}) {
  return (
    <Link
      href={url}
      onClick={onNavigate}
      title={collapsed ? title : undefined}
      className={cn(
        "flex items-center rounded-md py-2 transition-colors",
        collapsed ? "justify-center px-2" : "justify-between px-3",
        nested && !collapsed && "pl-9",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
      )}
    >
      <span className={cn("flex items-center min-w-0", !collapsed && "gap-3")}>
        <Icon size={16} strokeWidth={1.5} className="flex-shrink-0 text-sidebar-primary" />
        {!collapsed && (
          <span className={cn("font-display text-lg leading-tight truncate", active && "italic")}>
            {title}
          </span>
        )}
      </span>
      {active && !collapsed && (
        <span className="text-[10px] text-sidebar-primary leading-none flex-shrink-0">◆</span>
      )}
    </Link>
  )
}

function NavItemRow({
  item,
  pathname,
  collapsed,
  onNavigate,
}: {
  item: NavItem
  pathname: string
  collapsed: boolean
  onNavigate?: () => void
}) {
  const selfActive = isActive(pathname, item.url)
  const childActive = item.submenu?.some((s) => isActive(pathname, s.url)) ?? false
  const [open, setOpen] = useState(selfActive || childActive)

  // Mantém o submenu aberto quando a rota ativa está dentro dele.
  useEffect(() => {
    if (childActive) setOpen(true)
  }, [childActive])

  if (!item.submenu || collapsed) {
    return (
      <NavLinkRow
        title={item.title}
        url={item.url}
        Icon={item.icon}
        active={selfActive || childActive}
        collapsed={collapsed}
        onNavigate={onNavigate}
      />
    )
  }

  const Icon = item.icon
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex w-full items-center justify-between rounded-md px-3 py-2 transition-colors",
          childActive
            ? "text-sidebar-accent-foreground"
            : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
        )}
      >
        <span className="flex items-center gap-3 min-w-0">
          <Icon size={16} strokeWidth={1.5} className="flex-shrink-0 text-sidebar-primary" />
          <span className={cn("font-display text-lg leading-tight truncate", childActive && "italic")}>
            {item.title}
          </span>
        </span>
        <ChevronDown
          size={14}
          strokeWidth={1.5}
          className={cn("flex-shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="mt-0.5 space-y-0.5">
          {item.submenu.map((sub) => (
            <NavLinkRow
              key={sub.url}
              title={sub.title}
              url={sub.url}
              Icon={sub.icon}
              active={isActive(pathname, sub.url)}
              collapsed={collapsed}
              onNavigate={onNavigate}
              nested
            />
          ))}
        </div>
      )}
    </div>
  )
}

function SidebarContent({
  pathname,
  role,
  onNavigate,
  collapsed = false,
  onToggleCollapse,
}: {
  pathname: string
  role: string | null
  onNavigate?: () => void
  collapsed?: boolean
  onToggleCollapse?: () => void
}) {
  const groups = NAV
    .map((g) => ({ ...g, items: g.items.filter((i) => isVisible(i, role)) }))
    .filter((g) => g.items.length > 0)

  return (
    <div className="flex flex-col h-full">
      {/* Wordmark */}
      <div
        className={cn(
          "py-5 border-b border-sidebar-border",
          collapsed
            ? "px-0 flex flex-col items-center gap-3"
            : "px-6 flex items-center justify-between gap-2",
        )}
      >
        {collapsed ? (
          <span className="font-display text-2xl text-sidebar-primary leading-none">P</span>
        ) : (
          <span className="font-display text-xl tracking-[0.3em] text-sidebar-primary leading-none">
            PALADINO
          </span>
        )}
        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
            title={collapsed ? "Expandir menu" : "Recolher menu"}
            className="hidden lg:flex w-6 h-6 items-center justify-center rounded-md
              text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent
              transition-colors flex-shrink-0"
          >
            {collapsed ? <ChevronRight size={16} strokeWidth={1.5} /> : <ChevronLeft size={16} strokeWidth={1.5} />}
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className={cn("flex-1 py-5 overflow-y-auto", collapsed ? "px-2" : "px-4")}>
        <div className="space-y-5">
          {groups.map((group) => (
            <div key={group.label}>
              {!collapsed && (
                <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground mb-2 px-2">
                  {group.label}
                </p>
              )}
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavItemRow
                    key={item.url}
                    item={item}
                    pathname={pathname}
                    collapsed={collapsed}
                    onNavigate={onNavigate}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </nav>

      {/* Rodapé */}
      <div
        className={cn(
          "py-4 border-t border-sidebar-border",
          collapsed ? "px-2 text-center" : "px-6",
        )}
      >
        <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          {collapsed ? "F0" : "V 0.1 · Fase 0"}
        </p>
      </div>
    </div>
  )
}

export default function Sidebar() {
  const pathname = usePathname()
  const { role } = useAuth()
  const [open, setOpen] = useState(false)

  // Colapso do sidebar desktop, persistido em localStorage
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === "undefined") return false
    return localStorage.getItem("sidebar_collapsed") === "true"
  })

  const toggleCollapsed = () => {
    const next = !collapsed
    setCollapsed(next)
    localStorage.setItem("sidebar_collapsed", String(next))
  }

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setOpen(false) }, [pathname])

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : ""
    return () => { document.body.style.overflow = "" }
  }, [open])

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={cn(
          "hidden lg:flex min-h-screen bg-sidebar border-r border-sidebar-border flex-col shadow-sm flex-shrink-0",
          "transition-all duration-200",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <SidebarContent
          pathname={pathname}
          role={role}
          collapsed={collapsed}
          onToggleCollapse={toggleCollapsed}
        />
      </aside>

      {/* Mobile: hamburger */}
      <button
        onClick={() => setOpen(true)}
        className={cn(
          "lg:hidden fixed top-4 left-4 z-40",
          "w-9 h-9 flex flex-col items-center justify-center gap-1.5 rounded-lg",
          "bg-sidebar border border-sidebar-border shadow-sm transition-opacity",
          open && "opacity-0 pointer-events-none",
        )}
        aria-label="Abrir menu"
      >
        <span className="w-4 h-0.5 bg-sidebar-foreground rounded-full" />
        <span className="w-4 h-0.5 bg-sidebar-foreground rounded-full" />
        <span className="w-4 h-0.5 bg-sidebar-foreground rounded-full" />
      </button>

      {/* Mobile: overlay */}
      {open && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Mobile: drawer */}
      <aside
        className={cn(
          "lg:hidden fixed top-0 left-0 h-full w-72 z-50 bg-sidebar shadow-xl overflow-y-auto",
          "transform transition-transform duration-300 ease-in-out",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <button
          onClick={() => setOpen(false)}
          className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-sidebar-accent text-sidebar-foreground text-lg leading-none z-10"
          aria-label="Fechar menu"
        >
          ×
        </button>
        <SidebarContent pathname={pathname} role={role} onNavigate={() => setOpen(false)} />
      </aside>
    </>
  )
}

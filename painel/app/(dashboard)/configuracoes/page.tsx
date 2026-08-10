"use client"

import Link from "next/link"
import {
  UserCircle,
  Building2,
  KeyRound,
  UserCog,
  Link2,
  MessageSquare,
  Send,
  Percent,
  Blocks,
  Palette,
  BarChart3,
  ChevronRight,
  type LucideIcon,
} from "lucide-react"
import { useAuth, type Role } from "@/context/AuthContext"
import { PageHeader } from "@/components/PageHeader"
import { Card, CardContent } from "@/components/ui/card"

type Section = {
  href: string
  icon: LucideIcon
  title: string
  description: string
  roles: Role[] | "ALL"
}

const OWNER_ADMIN: Role[] = ["OWNER", "ADMIN"]

// As roles espelham o submenu "Configurações" da Sidebar — este hub é a outra
// porta para as mesmas telas (a Sidebar recolhida leva a ele). Um card para
// tela que o papel não abre é menu que leva a erro.
const SECTIONS: Section[] = [
  { href: "/settings/perfil",      icon: UserCircle, title: "Meu Perfil",        description: "Nome e informações da sua conta.",       roles: "ALL" },
  { href: "/settings/profile",     icon: Building2,  title: "Perfil da empresa", description: "Dados, identidade visual e contato.",    roles: OWNER_ADMIN },
  { href: "/settings/security",    icon: KeyRound,   title: "Segurança",         description: "Alterar senha e acesso.",                roles: "ALL" },
  { href: "/settings/usuarios",    icon: UserCog,    title: "Usuários",          description: "Membros da equipe e convites.",          roles: OWNER_ADMIN },
  { href: "/settings/integracoes", icon: Link2,      title: "Integrações",       description: "WhatsApp, Asaas e pagamentos.",          roles: OWNER_ADMIN },
  // Duas telas distintas, antes descritas por um card só ("Templates e canais de
  // envio") que levava apenas aos modelos: /settings/comunicacao — o liga/desliga
  // do canal, ligado a GET/PUT /communication/settings — não era alcançável por
  // nenhum menu, e é ela que o dono de um tenant novo precisa para poder enviar.
  { href: "/comunicacao",            icon: MessageSquare, title: "Modelos de mensagem", description: "Textos automáticos por evento e canal.", roles: OWNER_ADMIN },
  { href: "/settings/comunicacao",   icon: Send,          title: "Canais de envio",     description: "Ligue o WhatsApp e o e-mail do envio.",  roles: OWNER_ADMIN },
  { href: "/financeiro/taxas",     icon: Percent,    title: "Taxas",             description: "Taxas de maquininha por método.",        roles: ["OWNER", "ADMIN", "PROFESSIONAL"] },
  { href: "/settings/modulos",     icon: Blocks,     title: "Módulos",           description: "Ative ou desative funcionalidades.",     roles: OWNER_ADMIN },
  { href: "/settings/branding",    icon: Palette,    title: "Branding",          description: "Cores, logo e identidade.",              roles: OWNER_ADMIN },
  { href: "/relatorios",           icon: BarChart3,  title: "Relatórios",        description: "Acesso rápido a indicadores.",           roles: OWNER_ADMIN },
]

export default function ConfiguracoesPage() {
  const { role } = useAuth()
  const sections = SECTIONS.filter(
    (s) => s.roles === "ALL" || s.roles.includes((role ?? "") as Role),
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administração"
        title="Configurações"
        description="Gerencie as configurações da sua empresa."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sections.map((s) => (
          <Link key={s.href} href={s.href}>
            <Card className="h-full cursor-pointer transition-colors hover:border-primary">
              <CardContent className="flex items-start gap-4 p-6">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                  <s.icon size={20} strokeWidth={1.5} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="[font-family:var(--font-display)] text-lg leading-tight">{s.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{s.description}</p>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}

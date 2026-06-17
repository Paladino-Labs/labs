import Link from "next/link"
import {
  UserCircle,
  Building2,
  KeyRound,
  UserCog,
  Link2,
  MessageSquare,
  Percent,
  Blocks,
  Palette,
  BarChart3,
  ChevronRight,
  type LucideIcon,
} from "lucide-react"
import { PageHeader } from "@/components/PageHeader"
import { Card, CardContent } from "@/components/ui/card"

type Section = {
  href: string
  icon: LucideIcon
  title: string
  description: string
}

const SECTIONS: Section[] = [
  { href: "/settings/perfil",      icon: UserCircle, title: "Meu Perfil",        description: "Nome e informações da sua conta." },
  { href: "/settings/profile",     icon: Building2,  title: "Perfil da empresa", description: "Dados, identidade visual e contato." },
  { href: "/settings/security",    icon: KeyRound,   title: "Segurança",         description: "Alterar senha e acesso." },
  { href: "/settings/usuarios",    icon: UserCog,    title: "Usuários",          description: "Membros da equipe e convites." },
  { href: "/settings/integracoes", icon: Link2,      title: "Integrações",       description: "WhatsApp, Asaas e pagamentos." },
  { href: "/comunicacao",          icon: MessageSquare, title: "Comunicação",    description: "Templates e canais de envio." },
  { href: "/financeiro/taxas",     icon: Percent,    title: "Taxas",             description: "Taxas de maquininha por método." },
  { href: "/settings/modulos",     icon: Blocks,     title: "Módulos",           description: "Ative ou desative funcionalidades." },
  { href: "/settings/branding",    icon: Palette,    title: "Branding",          description: "Cores, logo e identidade." },
  { href: "/relatorios",           icon: BarChart3,  title: "Relatórios",        description: "Acesso rápido a indicadores." },
]

export default function ConfiguracoesPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administração"
        title="Configurações"
        description="Gerencie as configurações da sua empresa."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SECTIONS.map((s) => (
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

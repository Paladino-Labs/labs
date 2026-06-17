import Link from "next/link"
import { Building2, KeyRound, ChevronRight, UserCog, Link2, MessageSquare, UserCircle } from "lucide-react"
import { PageHeader } from "@/components/PageHeader"
import { Card, CardContent } from "@/components/ui/card"

const sections = [
  {
    href: "/settings/perfil",
    icon: UserCircle,
    title: "Meu Perfil",
    description: "Nome e informações da sua conta",
  },
  {
    href: "/settings/profile",
    icon: Building2,
    title: "Perfil da empresa",
    description: "Dados, identidade visual, galeria e informações de contato",
  },
  {
    href: "/settings/security",
    icon: KeyRound,
    title: "Segurança",
    description: "Alterar senha e configurações de acesso",
  },
  {
    href: "/settings/usuarios",
    icon: UserCog,
    title: "Usuários",
    description: "Gerenciar membros da equipe e convites",
  },
  {
    href: "/settings/integracoes",
    icon: Link2,
    title: "Integrações",
    description: "WhatsApp, Asaas e gateways de pagamento",
  },
  {
    href: "/settings/comunicacao",
    icon: MessageSquare,
    title: "Comunicação",
    description: "Configurações de email e WhatsApp",
  },
]

export default function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <PageHeader
        eyebrow="Administração"
        title="Configurações"
        description="Gerencie as configurações da sua empresa."
      />
      <div className="grid gap-4 sm:grid-cols-2">
        {sections.map((s) => (
          <Link key={s.href} href={s.href}>
            <Card className="h-full cursor-pointer transition-colors hover:border-primary">
              <CardContent className="flex items-start gap-4 p-6">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                  <s.icon className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <p className="[font-family:var(--font-display)] text-lg">{s.title}</p>
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

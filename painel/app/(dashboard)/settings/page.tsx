import Link from "next/link"
import { Building2, KeyRound, ChevronRight } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"

const sections = [
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
]

export default function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="font-display text-3xl tracking-wide">Configurações</h1>
        <p className="mt-1 text-sm text-muted-foreground">Gerencie as configurações da sua empresa</p>
      </div>
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

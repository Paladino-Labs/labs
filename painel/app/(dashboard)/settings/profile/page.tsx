import { redirect } from "next/navigation"

// Tela consolidada no Sprint C — "Identidade da empresa" agora absorve os campos
// que viviam aqui (company/profile) e em companies/me.
export default function ProfilePage() {
  redirect("/settings/branding")
}

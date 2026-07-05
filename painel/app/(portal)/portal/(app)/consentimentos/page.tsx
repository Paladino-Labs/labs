import { redirect } from "next/navigation"

// F5: consentimentos foram consolidados dentro do perfil.
// Rota preservada para links salvos/bookmarks.
export default function ConsentimentosPage() {
  redirect("/portal/perfil")
}

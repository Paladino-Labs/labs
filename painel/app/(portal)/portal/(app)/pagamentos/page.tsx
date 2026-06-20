import { Info } from "lucide-react"

// ⚠️ BLOQUEADO por backend (Asaas).
// O adapter Asaas NÃO tokeniza cartão — `source_token` precisa vir
// pré-tokenizado, o que depende de conta/contrato Asaas pendentes. Além disso,
// adicionar fonte exige consent PAYMENT_STORAGE concedido (senão 422).
//
// Endpoints existentes (a serem ligados quando Asaas estiver ativo):
//   GET    /portal/payment-sources
//   POST   /portal/payment-sources { company_id*, source_token*, mode* (ONCE|ALWAYS), last_four?, brand? }
//   DELETE /portal/payment-sources/{authorization_id}
//
// Até o wiring real existir, NÃO exibir cartões nem a opção de adicionar —
// apenas o aviso de área em desenvolvimento, para não dar a impressão de que
// há formas de pagamento cadastradas.

export default function PortalPagamentosPage() {
  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl tracking-wide text-foreground">Pagamentos</h1>

      <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-4 py-3">
        <Info size={16} strokeWidth={1.5} className="mt-0.5 flex-shrink-0 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          Esta área está em desenvolvimento. O cadastro de formas de pagamento estará
          disponível em breve.
        </p>
      </div>
    </div>
  )
}

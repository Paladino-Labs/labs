import { AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"

interface ErrorStateProps {
  message?: string
  onRetry?: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-destructive/40 bg-destructive/5 px-6 py-12 text-center">
      <div className="mb-3 text-destructive">
        <AlertTriangle size={28} strokeWidth={1.5} />
      </div>
      <p className="font-display text-xl text-foreground">Algo deu errado</p>
      <p className="mt-1 max-w-sm text-sm text-muted-foreground">
        {message ?? "Não foi possível carregar os dados."}
      </p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          Tentar novamente
        </Button>
      )}
    </div>
  )
}

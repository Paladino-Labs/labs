import { cn } from "@/lib/utils"

interface EmptyStateProps {
  message: string
  className?: string
}

export function EmptyState({ message, className }: EmptyStateProps) {
  return (
    <div className={cn("text-center text-sm italic text-muted-foreground py-10", className)}>
      {message}
    </div>
  )
}

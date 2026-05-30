import { cn } from "@/lib/utils"

const sizeClasses = {
  sm: "h-7 w-7 text-xs",
  md: "h-9 w-9 text-sm",
  lg: "h-12 w-12 text-lg",
}

interface AvatarInitialsProps {
  name: string
  size?: "sm" | "md" | "lg"
  className?: string
}

export function AvatarInitials({ name, size = "md", className }: AvatarInitialsProps) {
  const initials = name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("")

  return (
    <div
      className={cn(
        "rounded-full bg-primary/15 text-primary font-display flex items-center justify-center flex-shrink-0",
        sizeClasses[size],
        className
      )}
    >
      {initials}
    </div>
  )
}

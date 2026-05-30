"use client"

import { createContext, useContext, useState } from "react"
import { cn } from "@/lib/utils"

const TabsCtx = createContext<{ value: string; set: (v: string) => void }>({
  value: "",
  set: () => {},
})

function Tabs({
  defaultValue,
  children,
  className,
}: {
  defaultValue: string
  children: React.ReactNode
  className?: string
}) {
  const [value, set] = useState(defaultValue)
  return (
    <TabsCtx.Provider value={{ value, set }}>
      <div className={className}>{children}</div>
    </TabsCtx.Provider>
  )
}

function TabsList({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div role="tablist" className={cn("flex border-b border-border", className)}>
      {children}
    </div>
  )
}

function TabsTrigger({
  value,
  children,
  className,
}: {
  value: string
  children: React.ReactNode
  className?: string
}) {
  const ctx = useContext(TabsCtx)
  const active = ctx.value === value
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={() => ctx.set(value)}
      className={cn(
        "-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
        active
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground",
        className
      )}
    >
      {children}
    </button>
  )
}

function TabsContent({
  value,
  children,
  className,
}: {
  value: string
  children: React.ReactNode
  className?: string
}) {
  const ctx = useContext(TabsCtx)
  if (ctx.value !== value) return null
  return <div className={cn("mt-6", className)}>{children}</div>
}

export { Tabs, TabsList, TabsTrigger, TabsContent }

import { type FC, useState, useCallback, lazy, Suspense } from "react"
import { ChatWindow } from "./components/chat/ChatWindow"
import { HealthDashboard } from "./components/health/HealthDashboard"
import { ThemeToggle } from "./components/shared/ThemeToggle"
import { Spinner } from "./components/shared/Spinner"

const MemoryViewer = lazy(() =>
  import("./components/memory/MemoryViewer").then((m) => ({
    default: m.MemoryViewer,
  })),
)

const LogViewer = lazy(() =>
  import("./components/logs/LogViewer").then((m) => ({
    default: m.LogViewer,
  })),
)

type View = "chat" | "health" | "memory" | "logs"

const NAV_ITEMS: { key: View; label: string }[] = [
  { key: "chat", label: "Chat" },
  { key: "health", label: "Health" },
  { key: "memory", label: "Memory" },
  { key: "logs", label: "Logs" },
]

export const App: FC = () => {
  const [view, setView] = useState<View>("chat")

  const switchTo = useCallback((v: View) => () => setView(v), [])

  return (
    <div className="flex flex-col h-screen bg-base-100 text-base-content">
      <nav className="navbar bg-base-200 border-b border-base-300 px-4">
        <div className="flex-1">
          <span className="text-lg font-bold tracking-wide">Talon</span>
        </div>
        <div className="flex gap-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              className={`btn btn-sm ${view === item.key ? "btn-primary" : "btn-ghost"}`}
              onClick={switchTo(item.key)}
            >
              {item.label}
            </button>
          ))}
          <ThemeToggle />
        </div>
      </nav>

      <main className="flex-1 overflow-hidden">
        {view === "chat" && <ChatWindow />}
        {view === "health" && <HealthDashboard />}
        {view === "memory" && (
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-full">
                <Spinner size="lg" />
              </div>
            }
          >
            <MemoryViewer />
          </Suspense>
        )}
        {view === "logs" && (
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-full">
                <Spinner size="lg" />
              </div>
            }
          >
            <LogViewer />
          </Suspense>
        )}
      </main>
    </div>
  )
}

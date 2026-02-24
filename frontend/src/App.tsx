import { type FC, useState, useCallback } from "react"
import { ChatWindow } from "./components/chat/ChatWindow"
import { HealthDashboard } from "./components/health/HealthDashboard"
import { ThemeToggle } from "./components/shared/ThemeToggle"

type View = "chat" | "health"

export const App: FC = () => {
  const [view, setView] = useState<View>("chat")

  const switchTo = useCallback((v: View) => () => setView(v), [])

  return (
    <div className="flex flex-col h-screen bg-base-100 text-base-content">
      {/* Navbar */}
      <nav className="navbar bg-base-200 border-b border-base-300 px-4">
        <div className="flex-1">
          <span className="text-lg font-bold tracking-wide">Talon</span>
        </div>
        <div className="flex gap-1">
          <button
            className={`btn btn-sm ${view === "chat" ? "btn-primary" : "btn-ghost"}`}
            onClick={switchTo("chat")}
          >
            Chat
          </button>
          <button
            className={`btn btn-sm ${view === "health" ? "btn-primary" : "btn-ghost"}`}
            onClick={switchTo("health")}
          >
            Health
          </button>
          <ThemeToggle />
        </div>
      </nav>

      {/* Content */}
      <main className="flex-1 overflow-hidden">
        {view === "chat" && <ChatWindow />}
        {view === "health" && <HealthDashboard />}
      </main>
    </div>
  )
}

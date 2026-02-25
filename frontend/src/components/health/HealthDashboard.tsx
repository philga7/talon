import { type FC, useEffect, useState, useCallback } from "react"
import type { HealthResponse } from "../../types/api"
import { fetchHealth } from "../../api/client"
import { ProviderCard } from "./ProviderCard"
import { Spinner } from "../shared/Spinner"
import { ErrorBanner } from "../shared/ErrorBanner"

const POLL_INTERVAL = 15_000

export const HealthDashboard: FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await fetchHealth()
      setHealth(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load health")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL)
    return () => clearInterval(id)
  }, [load])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4">
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      </div>
    )
  }

  if (!health) return null

  return (
    <div className="p-6 space-y-6 max-w-2xl mx-auto">
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-bold">System Health</h2>
        <span
          className={`badge ${
            health.status === "healthy" ? "badge-success" : "badge-warning"
          }`}
        >
          {health.status}
        </span>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-2 opacity-70">Providers</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {health.providers.map((p) => (
            <ProviderCard key={p.name} provider={p} />
          ))}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-2 opacity-70">Memory</h3>
        <div className="stats shadow bg-base-200">
          <div className="stat">
            <div className="stat-title">Core Tokens</div>
            <div className="stat-value text-lg">
              {health.memory.core_tokens.toLocaleString()}
            </div>
          </div>
          <div className="stat">
            <div className="stat-title">Episodic Memories</div>
            <div className="stat-value text-lg">
              {health.memory.episodic_count.toLocaleString()}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

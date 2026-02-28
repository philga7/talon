import { type FC, useEffect, useState, useCallback, useRef } from "react"
import { Spinner } from "../shared/Spinner"
import { ErrorBanner } from "../shared/ErrorBanner"

interface LogEntry {
  timestamp: string
  level: string
  event: string
  [key: string]: unknown
}

const LEVEL_COLORS: Record<string, string> = {
  error: "text-error",
  warning: "text-warning",
  info: "text-info",
  debug: "text-base-content opacity-50",
}

const POLL_INTERVAL = 5_000
const MAX_ENTRIES = 200

export const LogViewer: FC = () => {
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState("")
  const [levelFilter, setLevelFilter] = useState<string>("all")
  const [autoScroll, setAutoScroll] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/health")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const health = (await res.json()) as Record<string, unknown>
      const logData = health["recent_logs"] as LogEntry[] | undefined

      if (logData && Array.isArray(logData)) {
        setEntries(logData.slice(-MAX_ENTRIES))
      }
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load logs")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL)
    return () => clearInterval(id)
  }, [load])

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [entries, autoScroll])

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

  const lowerFilter = filter.toLowerCase()
  const filtered = entries.filter((e) => {
    if (levelFilter !== "all" && e.level !== levelFilter) return false
    if (
      filter &&
      !e.event.toLowerCase().includes(lowerFilter) &&
      !JSON.stringify(e).toLowerCase().includes(lowerFilter)
    )
      return false
    return true
  })

  return (
    <div className="flex flex-col h-full p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Application Logs</h2>
        <div className="flex gap-2">
          <select
            className="select select-bordered select-xs"
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
          >
            <option value="all">All levels</option>
            <option value="error">Error</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
            <option value="debug">Debug</option>
          </select>
          <label className="label cursor-pointer gap-1">
            <span className="label-text text-xs">Auto-scroll</span>
            <input
              type="checkbox"
              className="toggle toggle-xs"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
          </label>
        </div>
      </div>

      <input
        type="text"
        placeholder="Filter logs..."
        className="input input-bordered input-sm w-full"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto bg-base-200 rounded-lg p-2 font-mono text-xs space-y-0.5"
      >
        {filtered.length === 0 ? (
          <p className="text-center opacity-50 py-8">
            {entries.length === 0
              ? "No log entries available. Logs appear here when the API reports recent activity."
              : "No entries match filter."}
          </p>
        ) : (
          filtered.map((entry, i) => {
            const colorClass = LEVEL_COLORS[entry.level] ?? ""
            const time = entry.timestamp
              ? new Date(entry.timestamp).toLocaleTimeString()
              : ""
            const extra = Object.entries(entry)
              .filter(([k]) => !["timestamp", "level", "event"].includes(k))
              .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
              .join(" ")

            return (
              <div key={`${entry.timestamp}-${i}`} className={`${colorClass} whitespace-pre-wrap`}>
                <span className="opacity-50">{time}</span>{" "}
                <span className="font-semibold uppercase">{entry.level}</span>{" "}
                <span>{entry.event}</span>
                {extra && <span className="opacity-70"> {extra}</span>}
              </div>
            )
          })
        )}
      </div>

      <p className="text-xs opacity-50">
        Showing {filtered.length} of {entries.length} entries (max {MAX_ENTRIES})
      </p>
    </div>
  )
}

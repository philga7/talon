import { type FC, useEffect, useState, useCallback } from "react"
import { Spinner } from "../shared/Spinner"
import { ErrorBanner } from "../shared/ErrorBanner"

interface MatrixRow {
  category: string
  key: string
  value: string
  priority: number
}

interface MemoryData {
  schema: string[]
  rows: MatrixRow[]
  compiled_at: string
  token_count: number
}

export const MemoryViewer: FC = () => {
  const [data, setData] = useState<MemoryData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState("")

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/memory")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = (await res.json()) as Record<string, unknown>
      const matrix = json["core_matrix"] as MemoryData | undefined
      if (matrix) {
        const rows = (matrix.rows ?? []).map((r: unknown) => {
          const arr = r as (string | number)[]
          return {
            category: String(arr[0] ?? ""),
            key: String(arr[1] ?? ""),
            value: String(arr[2] ?? ""),
            priority: Number(arr[3] ?? 2),
          }
        })
        setData({ ...matrix, rows })
      }
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load memory")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
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

  if (!data) return null

  const lowerFilter = filter.toLowerCase()
  const filtered = data.rows.filter(
    (r) =>
      !filter ||
      r.category.toLowerCase().includes(lowerFilter) ||
      r.key.toLowerCase().includes(lowerFilter) ||
      r.value.toLowerCase().includes(lowerFilter),
  )

  const categories = [...new Set(filtered.map((r) => r.category))]

  return (
    <div className="p-6 space-y-4 max-w-3xl mx-auto">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Core Memory Matrix</h2>
        <div className="flex gap-2 items-center">
          <span className="badge badge-ghost">{data.token_count} tokens</span>
          <span className="badge badge-ghost">{data.rows.length} rows</span>
        </div>
      </div>

      <input
        type="text"
        placeholder="Filter memories..."
        className="input input-bordered input-sm w-full"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />

      {categories.map((cat) => (
        <div key={cat} className="collapse collapse-arrow bg-base-200">
          <input type="checkbox" defaultChecked />
          <div className="collapse-title font-semibold capitalize">
            {cat.replace(/_/g, " ")}
            <span className="badge badge-sm badge-ghost ml-2">
              {filtered.filter((r) => r.category === cat).length}
            </span>
          </div>
          <div className="collapse-content">
            <table className="table table-xs">
              <thead>
                <tr>
                  <th>Key</th>
                  <th>Value</th>
                  <th>Priority</th>
                </tr>
              </thead>
              <tbody>
                {filtered
                  .filter((r) => r.category === cat)
                  .map((r, i) => (
                    <tr key={`${r.key}-${i}`}>
                      <td className="font-mono text-xs">{r.key}</td>
                      <td className="text-sm">{r.value}</td>
                      <td>
                        <span
                          className={`badge badge-xs ${
                            r.priority === 1
                              ? "badge-primary"
                              : r.priority === 2
                                ? "badge-ghost"
                                : "badge-neutral"
                          }`}
                        >
                          P{r.priority}
                        </span>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      <p className="text-xs opacity-50">
        Compiled at: {new Date(data.compiled_at).toLocaleString()}
      </p>
    </div>
  )
}

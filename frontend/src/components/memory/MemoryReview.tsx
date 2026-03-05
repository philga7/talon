import { type FC, useCallback, useEffect, useState } from "react"
import type { MemoryProposal } from "../../types/api"
import {
  acceptMemoryProposal,
  fetchMemoryProposals,
  rejectMemoryProposal,
} from "../../api/client"
import { Spinner } from "../shared/Spinner"
import { ErrorBanner } from "../shared/ErrorBanner"

export const MemoryReview: FC = () => {
  const [proposals, setProposals] = useState<MemoryProposal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<"pending" | "accepted" | "rejected">(
    "pending",
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchMemoryProposals(undefined, statusFilter)
      setProposals(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load memory proposals")
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    void load()
  }, [load])

  const handleAccept = async (id: string) => {
    try {
      const updated = await acceptMemoryProposal(id)
      setProposals((prev) => prev.map((p) => (p.id === id ? updated : p)))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to accept proposal")
    }
  }

  const handleReject = async (id: string) => {
    try {
      const updated = await rejectMemoryProposal(id)
      setProposals((prev) => prev.map((p) => (p.id === id ? updated : p)))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reject proposal")
    }
  }

  const pendingCount = proposals.filter((p) => p.status === "pending").length

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Memory Proposals</h2>
        <div className="flex gap-2 items-center">
          <select
            className="select select-sm select-bordered"
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(e.target.value as "pending" | "accepted" | "rejected")
            }
          >
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
          </select>
          <button
            type="button"
            className="btn btn-sm btn-outline"
            onClick={() => {
              void load()
            }}
          >
            Refresh
          </button>
          <span className="badge badge-primary badge-sm">
            {pendingCount} pending
          </span>
        </div>
      </div>

      {error && (
        <ErrorBanner
          message={error}
          onDismiss={() => {
            setError(null)
          }}
        />
      )}

      {proposals.length === 0 ? (
        <p className="text-sm opacity-60">No proposals found for this filter.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead>
              <tr>
                <th>Persona</th>
                <th>Category</th>
                <th>Key</th>
                <th>Value</th>
                <th>Priority</th>
                <th>Confidence</th>
                <th>Source</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {proposals.map((p) => (
                <tr key={p.id}>
                  <td className="font-mono text-xs">{p.persona_id}</td>
                  <td className="text-xs">{p.category}</td>
                  <td className="font-mono text-xs">{p.key}</td>
                  <td className="text-xs max-w-xs">
                    <div className="truncate" title={p.value}>
                      {p.value}
                    </div>
                  </td>
                  <td>
                    <span className="badge badge-ghost badge-xs">P{p.priority}</span>
                  </td>
                  <td>
                    <span
                      className={`badge badge-xs ${
                        p.confidence >= 0.9
                          ? "badge-success"
                          : p.confidence >= 0.7
                            ? "badge-warning"
                            : "badge-ghost"
                      }`}
                    >
                      {(p.confidence * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td>
                    {p.source_session_id ? (
                      <details>
                        <summary className="cursor-pointer text-xs underline">
                          Session {p.source_session_id.slice(0, 8)}
                        </summary>
                        <pre className="mt-2 whitespace-pre-wrap text-xs">
                          {p.source_excerpt || "No excerpt available"}
                        </pre>
                      </details>
                    ) : (
                      <span className="text-xs opacity-60">N/A</span>
                    )}
                  </td>
                  <td>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="btn btn-xs btn-success"
                        disabled={p.status === "accepted"}
                        onClick={() => {
                          void handleAccept(p.id)
                        }}
                      >
                        Accept
                      </button>
                      <button
                        type="button"
                        className="btn btn-xs btn-ghost"
                        disabled={p.status === "rejected"}
                        onClick={() => {
                          void handleReject(p.id)
                        }}
                      >
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}


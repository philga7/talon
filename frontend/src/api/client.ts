import type { ChatHistoryResponse, HealthResponse, MemoryProposal } from "../types/api"

const BASE = "/api"

export class APIError extends Error {
  readonly status: number
  readonly recoverable: boolean

  constructor(status: number, message: string, recoverable = false) {
    super(message)
    this.name = "APIError"
    this.status = status
    this.recoverable = recoverable
  }
}

export async function sendMessage(
  message: string,
  sessionId: string,
): Promise<void> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  })
  if (!res.ok) {
    const err: Record<string, unknown> = await res.json().catch(() => ({}))
    throw new APIError(
      res.status,
      (err["message"] as string) ?? "Request failed",
      (err["recoverable"] as boolean) ?? false,
    )
  }
}

export async function fetchChatHistory(sessionId: string): Promise<ChatHistoryResponse> {
  const res = await fetch(
    `${BASE}/chat/history?session_id=${encodeURIComponent(sessionId)}`,
  )
  if (!res.ok) {
    throw new APIError(res.status, "Failed to load chat history")
  }
  return (await res.json()) as ChatHistoryResponse
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BASE}/health`)
  if (!res.ok) {
    throw new APIError(res.status, "Health check failed")
  }
  return (await res.json()) as HealthResponse
}

export async function fetchMemoryProposals(
  personaId?: string,
  status: "pending" | "accepted" | "rejected" | null = "pending",
): Promise<MemoryProposal[]> {
  const params = new URLSearchParams()
  if (personaId) params.set("persona_id", personaId)
  if (status !== null) params.set("status", status)
  const res = await fetch(`${BASE}/memory/proposals?${params.toString()}`)
  if (!res.ok) {
    throw new APIError(res.status, "Failed to load memory proposals")
  }
  return (await res.json()) as MemoryProposal[]
}

export async function acceptMemoryProposal(id: string): Promise<MemoryProposal> {
  const res = await fetch(`${BASE}/memory/proposals/${encodeURIComponent(id)}/accept`, {
    method: "POST",
  })
  if (!res.ok) {
    throw new APIError(res.status, "Failed to accept proposal")
  }
  return (await res.json()) as MemoryProposal
}

export async function rejectMemoryProposal(id: string): Promise<MemoryProposal> {
  const res = await fetch(`${BASE}/memory/proposals/${encodeURIComponent(id)}/reject`, {
    method: "POST",
  })
  if (!res.ok) {
    throw new APIError(res.status, "Failed to reject proposal")
  }
  return (await res.json()) as MemoryProposal
}

import type { ChatHistoryResponse, HealthResponse } from "../types/api"

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

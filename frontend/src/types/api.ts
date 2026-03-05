export interface ChatRequest {
  message: string
  session_id: string
}

export interface ChatResponse {
  content: string
  provider: string
  tokens: Record<string, number> | null
}

export interface ChatHistoryTurn {
  role: string
  content: string
  created_at: string
}

export interface ChatHistoryResponse {
  turns: ChatHistoryTurn[]
}

export interface ProviderHealth {
  name: string
  state: "closed" | "open" | "half_open"
  failure_count: number
  opened_seconds_ago: number | null
}

export interface MemoryHealth {
  core_tokens: number
  episodic_count: number
}

export interface HealthResponse {
  status: "healthy" | "degraded"
  providers: ProviderHealth[]
  memory: MemoryHealth
}

export interface MemoryProposal {
  id: string
  persona_id: string
  category: string
  key: string
  value: string
  priority: number
  confidence: number
  status: "pending" | "accepted" | "rejected"
  source_session_id: string | null
  source_entry_ids: string[]
  source_excerpt: string
  created_at: string
  updated_at: string
}

export type SSEEvent =
  | { type: "token"; text: string }
  | { type: "tool_start"; tool: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; tool: string; result: unknown; success: boolean }
  | { type: "done" }
  | { type: "error"; message: string; recoverable: boolean }

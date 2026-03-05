import { create } from "zustand"

export interface ToolEvent {
  name: string
  arguments?: Record<string, unknown>
  result?: unknown
  success?: boolean
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  provider?: string
  isStreaming?: boolean
  error?: string
  tools?: ToolEvent[]
  createdAt: Date
}

export const CHAT_SESSION_STORAGE_KEY = "talon_chat_session_id"

interface ChatStore {
  messages: Message[]
  sessionId: string
  pendingPrompt: string | null
  isConnected: boolean
  addUserMessage: (content: string) => void
  startAssistantMessage: () => void
  appendToken: (delta: string) => void
  addToolStart: (name: string, args: Record<string, unknown>) => void
  addToolResult: (name: string, result: unknown, success: boolean) => void
  finalizeMessage: () => void
  setError: (error: string) => void
  setConnected: (v: boolean) => void
  setPendingPrompt: (p: string | null) => void
  stripTrailingError: () => void
  setSessionId: (sessionId: string) => void
  loadMessagesFromHistory: (turns: { role: string; content: string }[]) => void
}

function uid(): string {
  return crypto.randomUUID()
}

function getStoredSessionId(): string {
  if (typeof window === "undefined") return uid()
  const stored = localStorage.getItem(CHAT_SESSION_STORAGE_KEY)
  return stored ?? uid()
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  sessionId: getStoredSessionId(),
  pendingPrompt: null,
  isConnected: false,

  addUserMessage: (content) =>
    set((s) => ({
      messages: [
        ...s.messages,
        { id: uid(), role: "user", content, createdAt: new Date() },
      ],
    })),

  startAssistantMessage: () =>
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id: uid(),
          role: "assistant",
          content: "",
          isStreaming: true,
          tools: [],
          createdAt: new Date(),
        },
      ],
    })),

  appendToken: (delta) =>
    set((s) => {
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.isStreaming) {
        msgs[msgs.length - 1] = { ...last, content: last.content + delta }
      }
      return { messages: msgs }
    }),

  addToolStart: (name, args) =>
    set((s) => {
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.isStreaming) {
        const tools = [...(last.tools ?? []), { name, arguments: args }]
        msgs[msgs.length - 1] = { ...last, tools }
      }
      return { messages: msgs }
    }),

  addToolResult: (name, result, success) =>
    set((s) => {
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.isStreaming && last.tools) {
        const tools = [...last.tools]
        const idx = tools.findLastIndex((t: ToolEvent) => t.name === name && t.result === undefined)
        if (idx >= 0) {
          tools[idx] = { ...tools[idx], result, success }
        }
        msgs[msgs.length - 1] = { ...last, tools }
      }
      return { messages: msgs }
    }),

  finalizeMessage: () =>
    set((s) => {
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.isStreaming) {
        msgs[msgs.length - 1] = { ...last, isStreaming: false }
      }
      return { messages: msgs, pendingPrompt: null }
    }),

  setError: (error) =>
    set((s) => {
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.isStreaming) {
        msgs[msgs.length - 1] = { ...last, isStreaming: false, error }
      }
      return { messages: msgs, pendingPrompt: null }
    }),

  setConnected: (isConnected) => set({ isConnected }),
  setPendingPrompt: (pendingPrompt) => set({ pendingPrompt }),
  setSessionId: (sessionId) => {
    if (typeof window !== "undefined") {
      localStorage.setItem(CHAT_SESSION_STORAGE_KEY, sessionId)
    }
    set({ sessionId })
  },
  loadMessagesFromHistory: (turns) =>
    set({
      messages: turns.map((t, i) => ({
        id: `hist-${i}-${t.role}`,
        role: t.role as "user" | "assistant",
        content: t.content,
        createdAt: new Date(),
      })),
    }),
  stripTrailingError: () =>
    set((s) => {
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.error && !last.content) {
        msgs.pop()
      }
      return { messages: msgs }
    }),
}))

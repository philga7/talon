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
}

function uid(): string {
  return crypto.randomUUID()
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  sessionId: uid(),
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

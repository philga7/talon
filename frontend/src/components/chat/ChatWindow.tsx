import { type FC, useCallback } from "react"
import { useChatStore } from "../../stores/chatStore"
import { useSSE } from "../../hooks/useSSE"
import type { SSEEvent } from "../../types/api"
import { MessageList } from "./MessageList"
import { ChatInput } from "./ChatInput"

export const ChatWindow: FC = () => {
  const {
    messages,
    sessionId,
    pendingPrompt,
    addUserMessage,
    startAssistantMessage,
    appendToken,
    addToolStart,
    addToolResult,
    finalizeMessage,
    setError,
    setConnected,
    setPendingPrompt,
    clearMessages,
  } = useChatStore()

  const handleEvent = useCallback(
    (event: SSEEvent) => {
      switch (event.type) {
        case "token":
          appendToken(event.text)
          break
        case "tool_start":
          addToolStart(event.tool, event.arguments)
          break
        case "tool_result":
          addToolResult(event.tool, event.result, event.success)
          break
        case "done":
          finalizeMessage()
          break
        case "error":
          setError(event.message)
          break
      }
    },
    [appendToken, addToolStart, addToolResult, finalizeMessage, setError],
  )

  const { connected } = useSSE(sessionId, pendingPrompt, {
    onEvent: handleEvent,
    maxRetries: 0,
  })

  const handleSend = useCallback(
    (message: string) => {
      // Clear any prior error bubbles (including transient provider failures)
      // so a new request starts with a clean transcript.
      clearMessages()
      addUserMessage(message)
      startAssistantMessage()
      setConnected(true)
      setPendingPrompt(message)
    },
    [addUserMessage, startAssistantMessage, setConnected, setPendingPrompt, clearMessages],
  )

  const isStreaming = messages.at(-1)?.isStreaming ?? false

  return (
    <div className="flex flex-col h-full">
      <MessageList messages={messages} />
      <ChatInput onSend={handleSend} disabled={isStreaming} />
      {connected && (
        <div className="text-xs text-center py-1 text-success opacity-60">
          streaming…
        </div>
      )}
    </div>
  )
}

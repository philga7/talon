import type { FC } from "react"
import type { ToolEvent } from "../../stores/chatStore"
import { Spinner } from "../shared/Spinner"

interface MessageBubbleProps {
  role: "user" | "assistant"
  content: string
  isStreaming?: boolean
  error?: string
  tools?: ToolEvent[]
}

const ToolIndicator: FC<{ tool: ToolEvent }> = ({ tool }) => (
  <div className="mt-1 flex items-center gap-1 text-xs opacity-70">
    <span className="badge badge-outline badge-xs">
      {tool.name}
    </span>
    {tool.result === undefined ? (
      <Spinner size="xs" />
    ) : tool.success ? (
      <span className="badge badge-success badge-xs">done</span>
    ) : (
      <span className="badge badge-error badge-xs">failed</span>
    )}
  </div>
)

export const MessageBubble: FC<MessageBubbleProps> = ({
  role,
  content,
  isStreaming,
  error,
  tools,
}) => {
  if (error) {
    return (
      <div className={`chat ${role === "user" ? "chat-end" : "chat-start"}`}>
        <div className="chat-bubble chat-bubble-error">{error}</div>
      </div>
    )
  }

  return (
    <div className={`chat ${role === "user" ? "chat-end" : "chat-start"}`}>
      <div
        className={`chat-bubble whitespace-pre-wrap ${
          role === "user" ? "chat-bubble-primary" : ""
        }`}
      >
        {content}
        {isStreaming && !content && <Spinner size="sm" />}
        {tools?.map((t, i) => <ToolIndicator key={i} tool={t} />)}
      </div>
    </div>
  )
}

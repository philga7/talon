import { type FC, useEffect, useRef } from "react"
import type { Message } from "../../stores/chatStore"
import { MessageBubble } from "./MessageBubble"

interface MessageListProps {
  messages: Message[]
}

export const MessageList: FC<MessageListProps> = ({ messages }) => {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-base-content/40">
        <p className="text-lg">Send a message to start chatting.</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          role={msg.role}
          content={msg.content}
          isStreaming={msg.isStreaming}
          error={msg.error}
          tools={msg.tools}
        />
      ))}
      <div ref={endRef} />
    </div>
  )
}

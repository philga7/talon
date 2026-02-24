import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { MessageList } from "../MessageList"
import type { Message } from "../../../stores/chatStore"

function makeMsg(overrides: Partial<Message> & { id: string; role: Message["role"] }): Message {
  return {
    content: "",
    createdAt: new Date(),
    ...overrides,
  }
}

describe("MessageList", () => {
  it("shows empty state when no messages", () => {
    render(<MessageList messages={[]} />)
    expect(screen.getByText(/send a message/i)).toBeInTheDocument()
  })

  it("renders messages", () => {
    const messages: Message[] = [
      makeMsg({ id: "1", role: "user", content: "Hello" }),
      makeMsg({ id: "2", role: "assistant", content: "Hi" }),
    ]
    render(<MessageList messages={messages} />)
    expect(screen.getByText("Hello")).toBeInTheDocument()
    expect(screen.getByText("Hi")).toBeInTheDocument()
  })
})

import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { MessageBubble } from "../MessageBubble"

describe("MessageBubble", () => {
  it("renders user message on the right", () => {
    render(<MessageBubble role="user" content="Hello" />)
    const bubble = screen.getByText("Hello")
    expect(bubble.closest(".chat")).toHaveClass("chat-end")
  })

  it("renders assistant message on the left", () => {
    render(<MessageBubble role="assistant" content="Hi there" />)
    const bubble = screen.getByText("Hi there")
    expect(bubble.closest(".chat")).toHaveClass("chat-start")
  })

  it("renders error state", () => {
    render(<MessageBubble role="assistant" content="" error="Something broke" />)
    expect(screen.getByText("Something broke")).toBeInTheDocument()
  })

  it("renders tool indicators", () => {
    const tools = [
      { name: "searxng_search", arguments: { query: "test" }, result: { data: "ok" }, success: true },
    ]
    render(<MessageBubble role="assistant" content="Result" tools={tools} />)
    expect(screen.getByText("searxng_search")).toBeInTheDocument()
    expect(screen.getByText("done")).toBeInTheDocument()
  })

  it("shows spinner for pending tool", () => {
    const tools = [{ name: "web_search" }]
    render(<MessageBubble role="assistant" content="" isStreaming tools={tools} />)
    expect(screen.getByText("web_search")).toBeInTheDocument()
  })

  it("preserves whitespace in content", () => {
    render(<MessageBubble role="assistant" content={"line1\nline2"} />)
    const bubble = screen.getByText(/line1/)
    expect(bubble).toHaveClass("whitespace-pre-wrap")
  })
})

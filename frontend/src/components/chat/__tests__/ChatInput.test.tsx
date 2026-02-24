import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ChatInput } from "../ChatInput"

describe("ChatInput", () => {
  it("calls onSend with trimmed message", async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} />)

    const input = screen.getByPlaceholderText("Type a message…")
    await user.type(input, "  hello  ")
    await user.click(screen.getByRole("button", { name: /send/i }))

    expect(onSend).toHaveBeenCalledWith("hello")
  })

  it("clears input after send", async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} />)

    const input = screen.getByPlaceholderText("Type a message…")
    await user.type(input, "test")
    await user.click(screen.getByRole("button", { name: /send/i }))

    expect(input).toHaveValue("")
  })

  it("does not send empty message", async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} />)

    await user.click(screen.getByRole("button", { name: /send/i }))
    expect(onSend).not.toHaveBeenCalled()
  })

  it("disables input when disabled prop is true", () => {
    render(<ChatInput onSend={vi.fn()} disabled />)
    expect(screen.getByPlaceholderText("Type a message…")).toBeDisabled()
  })

  it("submits on enter key", async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} />)

    const input = screen.getByPlaceholderText("Type a message…")
    await user.type(input, "hello{Enter}")

    expect(onSend).toHaveBeenCalledWith("hello")
  })
})

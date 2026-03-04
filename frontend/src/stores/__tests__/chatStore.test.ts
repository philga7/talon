import { describe, it, expect, beforeEach } from "vitest"
import { useChatStore } from "../chatStore"

describe("chatStore", () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: [],
      pendingPrompt: null,
      isConnected: false,
    })
  })

  it("adds user message", () => {
    useChatStore.getState().addUserMessage("Hello")
    const msgs = useChatStore.getState().messages
    expect(msgs).toHaveLength(1)
    expect(msgs[0].role).toBe("user")
    expect(msgs[0].content).toBe("Hello")
  })

  it("starts assistant message in streaming state", () => {
    useChatStore.getState().startAssistantMessage()
    const msgs = useChatStore.getState().messages
    expect(msgs).toHaveLength(1)
    expect(msgs[0].role).toBe("assistant")
    expect(msgs[0].isStreaming).toBe(true)
    expect(msgs[0].content).toBe("")
  })

  it("appends tokens to streaming message", () => {
    useChatStore.getState().startAssistantMessage()
    useChatStore.getState().appendToken("Hello")
    useChatStore.getState().appendToken(" world")
    expect(useChatStore.getState().messages[0].content).toBe("Hello world")
  })

  it("tracks tool start and result", () => {
    useChatStore.getState().startAssistantMessage()
    useChatStore.getState().addToolStart("search", { q: "test" })
    useChatStore.getState().addToolResult("search", { data: "ok" }, true)

    const tools = useChatStore.getState().messages[0].tools
    expect(tools).toHaveLength(1)
    expect(tools![0].name).toBe("search")
    expect(tools![0].success).toBe(true)
  })

  it("finalizes message", () => {
    useChatStore.getState().startAssistantMessage()
    useChatStore.getState().appendToken("Done")
    useChatStore.getState().finalizeMessage()

    const msg = useChatStore.getState().messages[0]
    expect(msg.isStreaming).toBe(false)
    expect(msg.content).toBe("Done")
  })

  it("sets error on streaming message", () => {
    useChatStore.getState().startAssistantMessage()
    useChatStore.getState().setError("Provider failed")

    const msg = useChatStore.getState().messages[0]
    expect(msg.isStreaming).toBe(false)
    expect(msg.error).toBe("Provider failed")
  })

  it("strips trailing error-only assistant message", () => {
    useChatStore.getState().addUserMessage("Hello")
    useChatStore.getState().startAssistantMessage()
    useChatStore.getState().setError("Provider failed")
    useChatStore.getState().stripTrailingError()
    const msgs = useChatStore.getState().messages
    expect(msgs).toHaveLength(1)
    expect(msgs[0].role).toBe("user")
    expect(msgs[0].content).toBe("Hello")
  })
})

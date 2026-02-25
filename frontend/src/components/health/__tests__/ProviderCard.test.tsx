import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { ProviderCard } from "../ProviderCard"
import type { ProviderHealth } from "../../../types/api"

describe("ProviderCard", () => {
  it("renders provider name and closed state", () => {
    const provider: ProviderHealth = {
      name: "openai",
      state: "closed",
      failure_count: 0,
      opened_seconds_ago: null,
    }
    render(<ProviderCard provider={provider} />)
    expect(screen.getByText("openai")).toBeInTheDocument()
    expect(screen.getByText("closed")).toBeInTheDocument()
  })

  it("shows failure count when nonzero", () => {
    const provider: ProviderHealth = {
      name: "anthropic",
      state: "half_open",
      failure_count: 2,
      opened_seconds_ago: 15.5,
    }
    render(<ProviderCard provider={provider} />)
    expect(screen.getByText("2 failures")).toBeInTheDocument()
    expect(screen.getByText("half_open")).toBeInTheDocument()
    expect(screen.getByText(/opened 16s ago/)).toBeInTheDocument()
  })

  it("shows singular failure text for 1 failure", () => {
    const provider: ProviderHealth = {
      name: "gemini",
      state: "open",
      failure_count: 1,
      opened_seconds_ago: 3,
    }
    render(<ProviderCard provider={provider} />)
    expect(screen.getByText("1 failure")).toBeInTheDocument()
  })
})

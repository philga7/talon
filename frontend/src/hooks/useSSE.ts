import { useEffect, useRef, useState } from "react"
import type { SSEEvent } from "../types/api"

interface UseSSEOptions {
  onEvent: (event: SSEEvent) => void
  maxRetries?: number
}

export function useSSE(sessionId: string, prompt: string | null, options: UseSSEOptions) {
  const [connected, setConnected] = useState(false)
  const [reconnectCount, setReconnectCount] = useState(0)
  const esRef = useRef<EventSource | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const retriesRef = useRef(0)
  const maxRetries = options.maxRetries ?? 10
  const onEventRef = useRef(options.onEvent)
  useEffect(() => {
    onEventRef.current = options.onEvent
  })

  useEffect(() => {
    if (!prompt) return

    retriesRef.current = 0

    function openConnection(p: string) {
      if (esRef.current) esRef.current.close()

      const encoded = encodeURIComponent(p)
      const es = new EventSource(`/api/sse/${sessionId}?prompt=${encoded}`)
      esRef.current = es

      es.onopen = () => {
        setConnected(true)
        retriesRef.current = 0
        setReconnectCount(0)
      }

      es.addEventListener("token", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data as string) as { text: string }
          onEventRef.current({ type: "token", text: data.text })
        } catch {
          /* malformed event */
        }
      })

      es.addEventListener("tool_start", (e: MessageEvent) => {
        try {
          onEventRef.current({
            type: "tool_start",
            ...(JSON.parse(e.data as string) as {
              tool: string
              arguments: Record<string, unknown>
            }),
          })
        } catch {
          /* malformed */
        }
      })

      es.addEventListener("tool_result", (e: MessageEvent) => {
        try {
          onEventRef.current({
            type: "tool_result",
            ...(JSON.parse(e.data as string) as {
              tool: string
              result: unknown
              success: boolean
            }),
          })
        } catch {
          /* malformed */
        }
      })

      es.addEventListener("done", () => {
        onEventRef.current({ type: "done" })
        es.close()
        setConnected(false)
      })

      es.addEventListener("error", (e: Event) => {
        if ("data" in e) {
          try {
            const msg = e as MessageEvent
            onEventRef.current({
              type: "error",
              ...(JSON.parse(msg.data as string) as {
                message: string
                recoverable: boolean
              }),
            })
          } catch {
            /* malformed */
          }
        }
        setConnected(false)
        es.close()
      })

      es.onerror = () => {
        setConnected(false)
        es.close()
        if (retriesRef.current < maxRetries) {
          const delay = Math.min(1000 * 2 ** retriesRef.current, 30_000)
          retryRef.current = setTimeout(() => {
            retriesRef.current++
            setReconnectCount((n) => n + 1)
            openConnection(p)
          }, delay)
        }
      }
    }

    openConnection(prompt)

    return () => {
      esRef.current?.close()
      clearTimeout(retryRef.current)
    }
  }, [prompt, sessionId, maxRetries])

  return { connected, reconnectCount }
}

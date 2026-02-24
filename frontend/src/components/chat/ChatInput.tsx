import { type FC, type FormEvent, useState, useCallback } from "react"

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
}

export const ChatInput: FC<ChatInputProps> = ({ onSend, disabled }) => {
  const [value, setValue] = useState("")

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault()
      const trimmed = value.trim()
      if (!trimmed || disabled) return
      onSend(trimmed)
      setValue("")
    },
    [value, disabled, onSend],
  )

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 p-4 border-t border-base-300">
      <input
        type="text"
        className="input input-bordered flex-1"
        placeholder="Type a message…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
        autoFocus
      />
      <button
        type="submit"
        className="btn btn-primary"
        disabled={disabled || !value.trim()}
      >
        Send
      </button>
    </form>
  )
}

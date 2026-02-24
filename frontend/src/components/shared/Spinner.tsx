import type { FC } from "react"

interface SpinnerProps {
  size?: "xs" | "sm" | "md" | "lg"
}

export const Spinner: FC<SpinnerProps> = ({ size = "md" }) => (
  <span className={`loading loading-dots loading-${size}`} />
)

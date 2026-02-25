import type { FC } from "react"
import type { ProviderHealth } from "../../types/api"

interface ProviderCardProps {
  provider: ProviderHealth
}

const STATE_BADGE: Record<string, string> = {
  closed: "badge-success",
  half_open: "badge-warning",
  open: "badge-error",
}

export const ProviderCard: FC<ProviderCardProps> = ({ provider }) => {
  const badgeClass = STATE_BADGE[provider.state] ?? "badge-ghost"

  return (
    <div className="card bg-base-200 shadow-sm">
      <div className="card-body p-4">
        <h3 className="card-title text-sm">{provider.name}</h3>
        <div className="flex items-center gap-2">
          <span className={`badge ${badgeClass} badge-sm`}>
            {provider.state}
          </span>
          {provider.failure_count > 0 && (
            <span className="text-xs opacity-60">
              {provider.failure_count} failure{provider.failure_count !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        {provider.opened_seconds_ago !== null && (
          <p className="text-xs opacity-50">
            opened {Math.round(provider.opened_seconds_ago)}s ago
          </p>
        )}
      </div>
    </div>
  )
}

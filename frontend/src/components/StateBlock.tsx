import type { Icon } from "@phosphor-icons/react";
import { Tray, WarningCircle } from "@phosphor-icons/react";

/**
 * Empty, loading and error states, in one place.
 *
 * Every data surface in this app has all three. They are here rather than
 * hand-written per panel because an empty state written in a hurry is the one
 * that ships as a bare "No data" and tells the operator nothing about whether
 * something is broken or nothing has happened yet.
 */

export function EmptyState({
  icon: IconComponent = Tray,
  title,
  body,
  action,
}: {
  icon?: Icon;
  title: string;
  body?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="state">
      <IconComponent size={22} weight="regular" className="state-icon" aria-hidden />
      <div className="state-title">{title}</div>
      {body && <p className="state-body">{body}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ title, body, onRetry }: { title: string; body?: string; onRetry?: () => void }) {
  return (
    <div className="state is-error" role="alert">
      <WarningCircle size={22} weight="regular" className="state-icon" aria-hidden />
      <div className="state-title">{title}</div>
      {body && <p className="state-body">{body}</p>}
      {onRetry && (
        <button className="btn btn-sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

/** Skeletons take the shape of the thing loading, so nothing jumps when it lands. */
export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="skeleton skeleton-row"
          style={{ width: `${88 - (i % 3) * 14}%` }}
        />
      ))}
    </div>
  );
}

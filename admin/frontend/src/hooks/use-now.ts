import { useEffect, useState } from "react";

/**
 * Returns Date.now() (unix ms) updated at `intervalMs`. Use to render
 * time-relative labels (e.g. "3s ago") without piping data through state
 * trees. Each subscriber owns a tiny interval — fine for the handful of
 * cards on a page; if we ever scale to hundreds of subscribers, hoist to
 * a shared singleton.
 */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export function formatAgo(unixSeconds: number | undefined, nowMs: number): string {
  if (!unixSeconds) return "never";
  const diffSec = Math.max(0, Math.floor(nowMs / 1000 - unixSeconds));
  if (diffSec < 1) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

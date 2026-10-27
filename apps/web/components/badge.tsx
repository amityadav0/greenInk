import type { TriageBadge } from "@/lib/api";

const STYLES: Record<TriageBadge["level"], string> = {
  green: "bg-ink-light text-ink-dark ring-ink/30",
  amber: "bg-amber-light text-amber ring-amber/30",
  red: "bg-block-light text-block ring-block/30",
};
const LABELS: Record<TriageBadge["level"], string> = { green: "Winnable", amber: "Stretch", red: "Unlikely" };

export function WinBadge({ badge }: { badge: TriageBadge | null | undefined }) {
  if (!badge) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-stone-400" />
        Scoring…
      </span>
    );
  }
  return (
    <span
      title={badge.reason}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${STYLES[badge.level]}`}
    >
      {LABELS[badge.level]}
    </span>
  );
}

import { STATUS_COLORS, STATUS_LABELS } from "../lib/format";

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        STATUS_COLORS[status] ?? "bg-gray-600/30 text-gray-300"
      }`}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

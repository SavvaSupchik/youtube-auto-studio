export function fmtDuration(sec: number | null | undefined): string {
  if (!sec) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = bytes / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(1)} ${units[i]}`;
}

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  generating: "Генерация",
  ready: "Готово",
  error: "Ошибка",
};

export const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-600/30 text-gray-300",
  generating: "bg-amber-600/30 text-amber-300",
  ready: "bg-emerald-600/30 text-emerald-300",
  error: "bg-red-600/30 text-red-300",
};

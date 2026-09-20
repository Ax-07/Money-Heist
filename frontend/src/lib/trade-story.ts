export function formatTradeDurationLabel(
  openedAt: string | null | undefined,
  closedAt: string | null | undefined,
): string | null {
  if (!openedAt || !closedAt) return null;
  const opened = Date.parse(openedAt);
  const closed = Date.parse(closedAt);
  if (!Number.isFinite(opened) || !Number.isFinite(closed) || closed < opened) return null;
  const minutes = Math.round((closed - opened) / 60000);
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours <= 0) return `${remainingMinutes}m`;
  if (remainingMinutes === 0) return `${hours}h`;
  return `${hours}h${String(remainingMinutes).padStart(2, "0")}`;
}

export function grossMovePct(args: {
  side: string | null | undefined;
  entryPrice: string | number | null | undefined;
  exitPrice: string | number | null | undefined;
}): number | null {
  const side = (args.side ?? "").toUpperCase();
  const entry = Number(args.entryPrice);
  const exit = Number(args.exitPrice);
  if (!Number.isFinite(entry) || !Number.isFinite(exit) || entry <= 0) return null;
  if (side === "SHORT") return ((entry - exit) / entry) * 100;
  return ((exit - entry) / entry) * 100;
}

export function realizedRMultiple(args: {
  side: string | null | undefined;
  entryPrice: string | number | null | undefined;
  exitPrice: string | number | null | undefined;
  stopPrice: string | number | null | undefined;
}): number | null {
  const side = (args.side ?? "").toUpperCase();
  const entry = Number(args.entryPrice);
  const exit = Number(args.exitPrice);
  const stop = Number(args.stopPrice);
  if (!Number.isFinite(entry) || !Number.isFinite(exit) || !Number.isFinite(stop)) return null;

  const riskPerUnit = side === "SHORT" ? stop - entry : entry - stop;
  if (!Number.isFinite(riskPerUnit) || riskPerUnit <= 0) return null;

  const realizedPerUnit = side === "SHORT" ? entry - exit : exit - entry;
  return realizedPerUnit / riskPerUnit;
}

export function riskReasonLabel(code: string | null | undefined): string {
  switch ((code ?? "").toUpperCase()) {
    case "MIN_EXPECTED_RR":
      return "RR insuffisant";
    case "MAX_POSITIONS":
      return "Max positions";
    case "RISK_PROFILE_BLOCKED":
      return "Profil risk bloqué";
    case "POSITION_SIZE_ZERO":
      return "Taille nulle";
    case "STOP_DISTANCE_INVALID":
      return "Stop invalide";
    default:
      return code ?? "—";
  }
}

export const LEVELS = ["Low", "Moderate", "High", "Severe", "No Travel"];
export const LEVEL_COLORS = ["#2e9e5b", "#d9b100", "#f08a24", "#d8332a", "#6b1d6e"];
export const ROUTE_COLORS = ["#1f6feb", "#8957e5", "#0e9aa7"];

export const fmtDuration = (s) => {
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
};

export const fmtTime = (iso) =>
  new Date(iso).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });

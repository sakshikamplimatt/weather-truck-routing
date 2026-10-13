import { LEVEL_COLORS, LEVELS } from "../risk.js";

export default function HeatSlider({ heat, loading, hour, setHour, show, setShow }) {
  const label = heat
    ? new Date(new Date(heat.start).getTime() + hour * 3600e3).toLocaleString([], {
        weekday: "short",
        hour: "numeric",
      })
    : "";
  return (
    <div className="heatbar">
      <label className="toggle">
        <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Weather heatmap
      </label>
      <input
        type="range"
        min="0"
        max={heat?.hours ?? 48}
        value={hour}
        disabled={!heat}
        onChange={(e) => setHour(Number(e.target.value))}
      />
      <span className="heat-label">
        {loading ? "Loading forecast…" : heat ? `+${hour}h · ${label}` : "Run a search to load"}
      </span>
      <span className="legend">
        {LEVELS.map((n, i) => (
          <i key={n} title={n} style={{ background: LEVEL_COLORS[i] }} />
        ))}
      </span>
    </div>
  );
}

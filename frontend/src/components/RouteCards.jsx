import { LEVEL_COLORS, LEVELS, ROUTE_COLORS, fmtDuration, fmtTime } from "../risk.js";

export default function RouteCards({ plan, selected, onSelect }) {
  return (
    <div className="routes">
      <div className="reco">
        <strong>Route {plan.recommended_index + 1} recommended.</strong> {plan.recommendation_reason}
      </div>
      {plan.routes.map((r, i) => {
        const s = r.summary;
        const total = r.distance_mi || 1;
        return (
          <button
            key={r.id}
            className={`route-card ${selected === i ? "active" : ""}`}
            style={{ borderLeftColor: ROUTE_COLORS[i % 3] }}
            onClick={() => onSelect(i)}
          >
            <div className="route-head">
              <span>Route {i + 1}</span>
              {r.recommended && <span className="badge">Recommended</span>}
              <span className="pill" style={{ background: LEVEL_COLORS[s.max_level] }}>
                max {s.max_label}
              </span>
            </div>
            <div className="route-meta">
              {r.distance_mi} mi · {fmtDuration(r.duration_s)} · arrive {fmtTime(r.arrival)}
            </div>
            <div className="bar" title="Share of route miles by risk level">
              {LEVELS.map((name, lv) => {
                const mi = s.miles_by_level[name];
                return mi > 0 ? (
                  <span key={name} style={{ width: `${(mi / total) * 100}%`, background: LEVEL_COLORS[lv] }} />
                ) : null;
              })}
            </div>
            <div className="route-meta small">
              Severe {s.severe_miles} mi · High {s.high_miles} mi · avg risk {s.avg_risk.toFixed(2)}
              {s.no_travel_miles > 0 && <b> · No Travel {s.no_travel_miles} mi</b>}
            </div>
          </button>
        );
      })}
      {plan.notes.map((n) => (
        <small key={n} className="hint">
          {n}
        </small>
      ))}
    </div>
  );
}

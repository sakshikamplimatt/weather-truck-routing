import { useEffect, useMemo, useRef } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import { LEVEL_COLORS, ROUTE_COLORS, fmtTime } from "../risk.js";

function FitBounds({ plan }) {
    const map = useMap();
    useEffect(() => {
        if (!plan) return;
        const pts = plan.routes.flatMap((r) => r.geometry.map(([lon, lat]) => [lat, lon]));
        map.fitBounds(L.latLngBounds(pts), { padding: [40, 40] });
    }, [plan, map]);
    return null;
}

// Weather overlay: one translucent circle per corridor sample point, coloured by that point's
// risk level (so colour always matches the route cards - no density artefacts). Circles are
// created once per forecast; the slider only calls setStyle, which is cheap on the canvas renderer.
const HEAT_RADIUS_M = 40000; // ~25 mi, overlaps the ~30 mi sample spacing

function HeatLayer({ points, hour, enabled }) {
    const map = useMap();
    const group = useMemo(() => L.layerGroup(), []);
    const circles = useRef([]);
    // Dedicated pane + canvas: lets us blur the whole overlay (smooth gradient between circles)
    // without blurring routes/markers, and keeps it under them.
    const renderer = useMemo(() => {
        let pane = map.getPane("weather");
        if (!pane) {
            pane = map.createPane("weather");
            pane.style.zIndex = 350;
            pane.style.pointerEvents = "none";
            pane.style.filter = "blur(14px)";
        }
        return L.canvas({ pane: "weather", padding: 0.3 });
    }, [map]);

    useEffect(() => {
        if (enabled) group.addTo(map);
        return () => {
            map.removeLayer(group);
        };
    }, [enabled, group, map]);

    useEffect(() => {
        group.clearLayers();
        circles.current = (points || []).map((p) => {
            const c = L.circle([p.lat, p.lon], { radius: HEAT_RADIUS_M, stroke: false, interactive: false, renderer });
            group.addLayer(c);
            return c;
        });
    }, [points, group, renderer]);

    useEffect(() => {
        (points || []).forEach((p, i) => {
            const lv = p.levels[hour];
            circles.current[i]?.setStyle({ fillColor: LEVEL_COLORS[lv], fillOpacity: lv === 0 ? 0.2 : 0.38 });
        });
    }, [points, hour]);

    return null;
}

export default function MapView({ plan, selected, heat, hour, showHeat }) {
    return (
        <MapContainer center={[39.5, -98.35]} zoom={4} className="map" preferCanvas>
            <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <FitBounds plan={plan} />
            <HeatLayer points={heat?.points} hour={hour} enabled={showHeat} />
            {plan &&
                plan.routes.map((r, i) => {
                    const active = i === selected;
                    return (
                        <Polyline
                            key={r.id}
                            positions={r.geometry.map(([lon, lat]) => [lat, lon])}
                            pathOptions={{
                                color: ROUTE_COLORS[i % 3],
                                weight: active ? 6 : 4,
                                opacity: active ? 0.95 : 0.45,
                                dashArray: r.recommended ? null : "8 6",
                            }}
                            eventHandlers={{ click: () => { } }}
                        />
                    );
                })}
            {plan &&
                plan.routes[selected].checkpoints.map((c) => (
                    <CircleMarker
                        key={c.mile}
                        center={[c.lat, c.lon]}
                        radius={7}
                        pathOptions={{ color: "#fff", weight: 2, fillColor: LEVEL_COLORS[c.level], fillOpacity: 1 }}
                    >
                        <Popup>
                            <b>Mile {c.mile}</b> — {c.label}
                            <br />
                            ETA {fmtTime(c.eta)}
                            <br />
                            Wind {c.wind_mph} mph · Rain {c.rain_in_hr} in/hr · Snow {c.snow_in_hr} in/hr
                            {c.reasons.length > 0 && (
                                <ul className="popup-reasons">
                                    {c.reasons.map((x) => (
                                        <li key={x}>{x}</li>
                                    ))}
                                </ul>
                            )}
                        </Popup>
                    </CircleMarker>
                ))}
        </MapContainer>
    );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchHeatmap, planTrip } from "./api.js";
import TripForm from "./components/TripForm.jsx";
import RouteCards from "./components/RouteCards.jsx";
import MapView from "./components/MapView.jsx";
import HeatSlider from "./components/HeatSlider.jsx";

export default function App() {
  const [plan, setPlan] = useState(null);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [heat, setHeat] = useState(null);
  const [heatLoading, setHeatLoading] = useState(false);
  const [hour, setHour] = useState(0);
  const [showHeat, setShowHeat] = useState(true);
  const ctrl = useRef(null);

  const submit = useCallback(async (req) => {
    ctrl.current?.abort();
    ctrl.current = new AbortController();
    const { signal } = ctrl.current;
    setLoading(true);
    setError("");
    setHeat(null);
    try {
      const p = await planTrip(
        {
          origin: req.origin,
          destination: req.destination,
          departure: req.departure,
          load_lb: req.load_lb,
          interval_miles: req.interval_miles,
        },
        signal,
      );
      setPlan(p);
      setSelected(p.recommended_index);
      setLoading(false);
      // Heatmap is a second, slower request: the plan renders first, heat fills in after.
      setHeatLoading(true);
      setHour(0);
      try {
        setHeat(await fetchHeatmap({ points: p.heatmap_points, load_lb: p.load_lb }, signal));
      } catch (e) {
        if (e.name !== "AbortError") setError(`Heatmap unavailable: ${e.message}`);
      } finally {
        setHeatLoading(false);
      }
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
      setLoading(false);
    }
  }, []);

  useEffect(() => () => ctrl.current?.abort(), []);

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Weather-Aware Truck Routing</h1>
        <TripForm loading={loading} onSubmit={submit} />
        {error && <div className="error">{error}</div>}
        {plan && <RouteCards plan={plan} selected={selected} onSelect={setSelected} />}
      </aside>
      <main className="mapwrap">
        <MapView plan={plan} selected={selected} heat={heat} hour={hour} showHeat={showHeat} />
        <HeatSlider heat={heat} loading={heatLoading} hour={hour} setHour={setHour} show={showHeat} setShow={setShowHeat} />
      </main>
    </div>
  );
}

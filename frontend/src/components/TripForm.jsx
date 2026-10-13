import { useState } from "react";
import PlaceInput from "./PlaceInput.jsx";

const defaultDeparture = () => {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  d.setMinutes(0, 0, 0);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
};

export default function TripForm({ loading, onSubmit }) {
  const [origin, setOrigin] = useState(null);
  const [destination, setDestination] = useState(null);
  const [departure, setDeparture] = useState(defaultDeparture);
  const [load, setLoad] = useState(42000);
  const [interval, setInterval] = useState(25);

  const valid = origin && destination && departure && load > 0;

  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          origin,
          destination,
          departure: new Date(departure).toISOString(),
          load_lb: Number(load),
          interval_miles: Number(interval),
        });
      }}
    >
      <PlaceInput label="Origin" value={origin} onSelect={setOrigin} />
      <PlaceInput label="Destination" value={destination} onSelect={setDestination} />
      <label className="field">
        <span>Departure</span>
        <input type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} />
      </label>
      <div className="row">
        <label className="field">
          <span>Load (lb)</span>
          <input type="number" min="1" max="100000" step="any" value={load} onChange={(e) => setLoad(e.target.value)} />
        </label>
        <label className="field">
          <span>Sample every</span>
          <select value={interval} onChange={(e) => setInterval(e.target.value)}>
            <option value={10}>10 miles</option>
            <option value={25}>25 miles</option>
            <option value={50}>50 miles</option>
          </select>
        </label>
      </div>
      <button type="submit" disabled={!valid || loading}>
        {loading ? "Analyzing routes…" : "Find safest route"}
      </button>
      {!valid && <small className="hint">Pick origin and destination from the suggestions.</small>}
    </form>
  );
}

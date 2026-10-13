import { useEffect, useRef, useState } from "react";
import { geocode } from "../api.js";

// Debounced geocoding autocomplete. Calls onSelect({label, lat, lon}) when a result is picked.
export default function PlaceInput({ label, value, onSelect }) {
  const [text, setText] = useState(value?.label || "");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const ctrl = useRef(null);

  useEffect(() => {
    if (value && text === value.label) return; // already chosen
    if (text.trim().length < 3) {
      setResults([]);
      return;
    }
    const t = setTimeout(async () => {
      ctrl.current?.abort();
      ctrl.current = new AbortController();
      try {
        const data = await geocode(text, ctrl.current.signal);
        setResults(data.results);
        setError(data.results.length ? "" : "No matches");
        setOpen(true);
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
      }
    }, 450); // Nominatim asks for <= 1 request/second
    return () => clearTimeout(t);
  }, [text, value]);

  return (
    <label className="field">
      <span>{label}</span>
      <input
        value={text}
        placeholder="City or address"
        onChange={(e) => {
          setText(e.target.value);
          onSelect(null);
        }}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && results.length > 0 && (
        <ul className="suggestions">
          {results.map((r) => (
            <li
              key={`${r.lat},${r.lon}`}
              onMouseDown={() => {
                setText(r.label);
                onSelect(r);
                setOpen(false);
              }}
            >
              {r.label}
            </li>
          ))}
        </ul>
      )}
      {error && !open && <small className="hint">{error}</small>}
    </label>
  );
}

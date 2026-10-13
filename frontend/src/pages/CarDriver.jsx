import { useEffect, useState } from "react";
import { api, useOnce } from "../api.js";
import NetworkMap from "../components/NetworkMap.jsx";
import { Notifications, Stat, Waiting } from "../components/Feed.jsx";

const ALERT_TEXT = {
  incident: (a) => `Lane blocked on ${a.street}`,
  flood: (a) => `Flooded: ${a.street}`,
  congestion: (a) => `Heavy traffic on ${a.street}`,
  ambulance: (a) => `Ambulance heading for ${a.junction}: keep it clear`,
  rain: (a) => `Rain (${Math.round(a.intensity * 100)}%): drive slower`,
};

function TripPlanner({ live, onRoute }) {
  const places = useOnce(live.scenario ? "/places" : null, [live.scenario]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [trip, setTrip] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (places && !from) { setFrom(places.from[0]?.edge || ""); setTo(places.to[places.to.length - 1]?.edge || ""); }
  }, [places]);
  const plan = async () => {
    if (!from || !to) { setError("Choose where you start and where you're going"); return; }
    try {
      const t = await api(`/trip?origin=${from}&destination=${to}`);
      if (t.error) { setError(t.error); setTrip(null); onRoute(null); return; }
      setError(""); setTrip(t); onRoute(t);
    } catch (e) { setError(String(e)); }
  };
  useEffect(() => {                          // keep the plan fresh while driving
    if (!trip) return;
    const id = setInterval(plan, 5000);
    return () => clearInterval(id);
  }, [trip !== null, from, to]);
  if (!places) return null;
  return (
    <div className="card">
      <h2>Plan my trip</h2>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <span className="muted">From</span>
        <select value={from} onChange={(e) => setFrom(e.target.value)}>
          {places.from.map((p) => <option key={p.edge} value={p.edge}>{p.name}</option>)}
        </select>
        <span className="muted">to</span>
        <select value={to} onChange={(e) => setTo(e.target.value)}>
          {places.to.map((p) => <option key={p.edge} value={p.edge}>{p.name}</option>)}
        </select>
        <button className="primary" onClick={plan}>Find my route</button>
      </div>
      {error && <span style={{ color: "#f4a497", fontSize: 13 }}>{error}</span>}
      {trip && <>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div className="stat"><b>{Math.round(trip.time_s / 60 * 10) / 10} min</b><span>travel time now</span></div>
          <div className="stat"><b style={{ color: trip.delay_s > 30 ? "#e6a23c" : undefined }}>+{Math.max(0, trip.delay_s)} s</b>
            <span>vs normal ({Math.round(trip.normal_s)} s)</span></div>
        </div>
        <div><span className="muted">Via </span>{trip.streets.join(" → ")}</div>
        {trip.alerts.length === 0 && <div className="note info">No problems on your route right now.</div>}
        {trip.alerts.map((a, i) => (
          <div key={i} className={`note ${a.kind === "rain" ? "info" : a.kind === "congestion" ? "warning" : "danger"}`}>
            {ALERT_TEXT[a.kind] ? ALERT_TEXT[a.kind](a) : a.kind}
          </div>
        ))}
        {trip.alternative && (trip.alternative.saving_s > 0
          ? <div className="note info"><b>Better route:</b> via {trip.alternative.streets.join(" → ")}, saves about {trip.alternative.saving_s} s (shown in amber).</div>
          : <div className="note">An alternative avoiding the problem (amber) would be {-trip.alternative.saving_s} s slower: your route is still the fastest.</div>)}
        <span className="muted" style={{ fontSize: 12 }}>Updated every 5 s · {trip.clock}</span>
      </>}
    </div>
  );
}

export default function CarDriver({ live }) {
  const [trip, setTrip] = useState(null);
  const f = live.forecast || {};
  const busiest = [...(live.junctions || [])].sort((a, b) => b.queue - a.queue)[0];
  const onRoute = (n) => trip && ((n.where?.edges || []).some((e) => trip.edges.includes(e)) ||
                                  (n.where?.junctions || []).some((j) => trip.junctions.includes(j)) || n.type === "RAIN");
  return (
    <>
      <div><h1>Your drive through the centre</h1>
        <p className="muted">Faycel · plan your trip, see what's on your route, and get a better one when something changes.</p></div>
      <Waiting live={live} />
      <div className="grid g4">
        <Stat label="incidents reported" value={live.incidents?.length || 0} tone={live.incidents?.length ? "#e5604d" : undefined} />
        <Stat label="congested roads" value={live.congestion?.length || 0} tone={live.congestion?.length ? "#e6a23c" : undefined} />
        <Stat label="flooded roads" value={live.floods?.length || 0} tone={live.floods?.length ? "#5c9bea" : undefined} />
        <Stat label="traffic next 30 min" value={f.level ? `${Math.round(f.level * 100)}%` : "—"} />
      </div>
      {(live.status === "running" || live.status === "finished") && <TripPlanner live={live} onRoute={setTrip} />}
      <div className="split">
        <div className="card">
          <h2>Map</h2>
          <NetworkMap live={live} highlight={{
            incidents: [...(live.incidents || []).map((i) => i.subject), ...(live.congestion || []).map((c) => c.subject)],
            floods: live.floods?.map((x) => x.subject), routeB: trip?.edges || [],
            alt: trip?.alternative?.edges || [] }} />
          <span className="muted">Teal: your route · amber: alternative · red: blocked or congested · dashed blue: flooded
            {busiest ? ` · busiest junction ${busiest.id} (${busiest.queue} queued)` : ""}</span>
        </div>
        <div className="grid">
          {trip && <Notifications live={live} persona="car_driver" filter={onRoute} title="On your route"
                                  empty="Nothing affecting your route" />}
          <Notifications live={live} persona="car_driver" title={trip ? "Everywhere else" : "Notifications"}
                         filter={trip ? (n) => !onRoute(n) : undefined} />
        </div>
      </div>
    </>
  );
}

import { useState } from "react";
import { Notifications, Waiting } from "../components/Feed.jsx";
import NetworkMap from "../components/NetworkMap.jsx";
import { useOnce } from "../api.js";

export default function BusPassenger({ live }) {
  const lines = live.lines || {};
  const lineIds = Object.keys(lines);
  const [line, setLine] = useState("L1_east");
  const [stop, setStop] = useState("");
  const stops = lines[line] || [];
  const myStop = stops.includes(stop) ? stop : stops[0];
  const buses = Object.entries(live.buses || {}).filter(([, b]) => b.line === line);
  const coming = buses.map(([id, b]) => {
    const hit = (b.upcoming || []).find(([j]) => j === myStop);
    return hit ? { id, ...b, dist: hit[1], eta: Math.round(hit[1] / Math.max(b.speed || 0, 6)) } : null;
  }).filter(Boolean).sort((a, b) => a.eta - b.eta);
  const geo = useOnce(live.scenario ? "/network" : null, [live.scenario]);
  const stopName = (j) => {
    const st = (geo?.bus_stops || []).find((b) => b.junction === j && b.lines.includes(line));
    return st ? `Stop before ${j} · ${st.name}` : j;
  };
  const mine = (n) => n.where?.line === line || (n.where?.junctions || []).includes(myStop) || n.type === "RAIN" || n.type === "FLOOD";
  return (
    <>
      <div><h1>When is my bus coming?</h1>
        <p className="muted">Mamadou · choose your line and stop to see the next buses and alerts that concern you.</p></div>
      <Waiting live={live} />
      <div className="bar">
        <span className="muted">Line</span>
        {(lineIds.length ? lineIds : ["L1_east"]).map((l) => (
          <button key={l} className={l === line ? "primary" : ""} onClick={() => setLine(l)}>{l.replace("_", " ")}</button>
        ))}
        <span className="muted" style={{ marginLeft: 12 }}>My stop</span>
        <select value={myStop || ""} onChange={(e) => setStop(e.target.value)}>
          {stops.map((s) => <option key={s} value={s}>{stopName(s)}</option>)}
        </select>
      </div>
      <div className="split">
        <div className="card">
          <NetworkMap live={live} lines={[line]} focus={coming.map((b) => b.id)} height={300} />
          <h2>Next buses at the stop before {myStop}</h2>
          {coming.length === 0 && <span className="muted">No bus of this line is on its way to this stop yet.</span>}
          <table>
            {coming.length > 0 && <thead><tr><th>Bus</th><th>Arrives in</th><th>Distance</th><th>Gap to previous</th><th>Status</th></tr></thead>}
            <tbody>
              {coming.map((b) => (
                <tr key={b.id}>
                  <td className="mono">{b.id.replace("bus_", "")}</td>
                  <td><b>{b.eta < 60 ? `${b.eta} s` : `${Math.round(b.eta / 60)} min`}</b></td>
                  <td>{b.dist} m</td>
                  <td>{b.gap_s == null ? "—" : `${Math.round(b.gap_s / 60)} min`}</td>
                  <td>{b.late ? <span className="pill warn">late</span> : <span className="pill ok">regular</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <span className="muted">Scheduled every 4 minutes; a gap above 6 minutes counts as late. Arrival times are estimates.</span>
        </div>
        <Notifications live={live} persona="bus_passenger" filter={mine} title={`Alerts for line ${line.replace("_", " ")}`}
                       empty="Nothing affecting your line or stop" />
      </div>
    </>
  );
}

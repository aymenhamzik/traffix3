import NetworkMap from "../components/NetworkMap.jsx";
import Copilot from "../components/Copilot.jsx";
import { Notifications, Stat, Waiting } from "../components/Feed.jsx";

const MODE = { max_pressure: ["ok", "max-pressure"], actuated: ["warn", "actuated (fallback)"], fixed: ["bad", "fixed (stale data)"] };

export default function Operator({ live }) {
  const f = live.forecast || {};
  return (
    <>
      <div><h1>Network control room</h1>
        <p className="muted">Kamel · what is wrong, how confident the system is, and whether the data is fresh.</p></div>
      <Waiting live={live} />
      <div className="grid g4">
        <Stat label="stale detectors" value={live.stale?.length || 0} tone={live.stale?.length ? "#e6a23c" : undefined} />
        <Stat label="incidents" value={live.incidents?.length || 0} tone={live.incidents?.length ? "#e5604d" : undefined} />
        <Stat label="rain intensity" value={live.weather?.rain ? `${Math.round(live.weather.rain * 100)}%` : "dry"} />
        <Stat label="forecast, next 30 min" value={f.level ? `${Math.round(f.level * 100)}% · ${f.inbound_share > 0.55 ? "inbound" : f.inbound_share < 0.45 ? "outbound" : "balanced"}` : "—"} />
      </div>
      {(live.status === "running" || live.status === "finished") && <Copilot live={live} />}
      <div className="split">
        <div className="card">
          <NetworkMap live={live} highlight={{ incidents: live.incidents?.map((i) => i.subject), floods: live.floods?.map((x) => x.subject) }} />
          <table>
            <thead><tr><th>Junction</th><th>Mode</th><th>Queue</th><th>Emergency</th></tr></thead>
            <tbody>
              {(live.junctions || []).map((j) => (
                <tr key={j.id}>
                  <td><b>{j.id}</b> <span className="muted">{j.name}</span></td>
                  <td><span className={`pill ${MODE[j.mode][0]}`}>{MODE[j.mode][1]}</span></td>
                  <td>{j.queue}</td><td>{j.preempt || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {live.incidents?.map((i) => (
            <div key={i.subject} className="note warning">Lane blockage on {i.lane}: confidence {Math.round(i.confidence * 100)}%,
              data {Math.round(i.freshness_s)}s old. Cause not determined.</div>
          ))}
        </div>
        <Notifications live={live} persona="operator" />
      </div>
    </>
  );
}

import NetworkMap from "../components/NetworkMap.jsx";
import { Notifications, Waiting } from "../components/Feed.jsx";

export default function EmergencyCrew({ live }) {
  const amb = (live.vehicles || []).filter((v) => ["ambulance", "police", "fire"].includes(v.kind));
  const decisions = (live.emergency_decisions || []).slice().reverse();
  return (
    <>
      <div><h1>Clear the way</h1>
        <p className="muted">Touhami · ambulances, police cars and fire trucks on the move, junctions preparing ahead, grants and denials.</p></div>
      <Waiting live={live} />
      <div className="split">
        <div className="card">
          <h2>{amb.length ? `${amb.length} emergency vehicle${amb.length > 1 ? "s" : ""} active` : "No emergency vehicle active"}</h2>
          <NetworkMap live={live} focus={amb.map((a) => a.id)} highlight={{ incidents: live.incidents?.map((i) => i.subject) }} height={360} />
          <table>
            <thead><tr><th>Time</th><th>What happened</th><th>Decision</th></tr></thead>
            <tbody>
              {decisions.slice(0, 12).map((d) => (
                <tr key={d.id}>
                  <td className="mono" style={{ whiteSpace: "nowrap" }}>{d.clock || `${Math.round(d.t)}s`}</td>
                  <td>{d.text || d.reason}</td>
                  <td>{d.reason.includes("DENIED") ? <span className="pill bad">denied</span>
                     : d.reason.includes("GRANTED") ? <span className="pill ok">green</span>
                     : d.reason.includes("PREPARE") ? <span className="pill info">preparing</span>
                     : d.reason.includes("RECOVER") ? <span className="pill info">recovery</span>
                     : <span className="pill warn">request</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Notifications live={live} persona="emergency_crew" />
      </div>
    </>
  );
}

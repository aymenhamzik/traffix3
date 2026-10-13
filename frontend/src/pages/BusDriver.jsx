import { useEffect, useState } from "react";
import NetworkMap from "../components/NetworkMap.jsx";
import { Notifications, Waiting } from "../components/Feed.jsx";

export default function BusDriver({ live }) {
  const buses = Object.keys(live.buses || {});
  const [bus, setBus] = useState("");
  useEffect(() => { if (!buses.includes(bus) && buses.length) setBus(buses[0]); }, [buses.join()]);
  const b = live.buses?.[bus];
  const decisions = (live.transit_decisions || []).filter((d) => d.details?.vehicle === bus).reverse();
  return (
    <>
      <div><h1>Your run</h1>
        <p className="muted">Hédi (bus driver) · schedule gap and signal priority at the junctions ahead.</p></div>
      <Waiting live={live} />
      <div className="bar">
        <span className="muted">Bus</span>
        <select value={bus} onChange={(e) => setBus(e.target.value)}>
          {buses.map((x) => <option key={x}>{x}</option>)}
        </select>
        {b && <>
          <span>line {b.line}</span><span>next {b.next_junction} in {b.distance_m} m</span>
          <span>gap to bus ahead {Math.round(b.gap_s)}s</span>
          {b.late ? <span className="pill warn">late: priority requested</span> : <span className="pill ok">on time: no priority</span>}
        </>}
      </div>
      <div className="split">
        <div className="card">
          <NetworkMap live={live} focus={[bus]} lines={b ? [b.line] : []} height={330} />
          <h2>Priority decisions for this bus</h2>
          {decisions.length === 0 && <span className="muted">No decision about this bus yet.</span>}
          {decisions.slice(0, 8).map((d) => (
            <div key={d.id} className="note"><time>{d.clock || `${Math.round(d.t)}s`}</time>{d.text || d.reason}</div>
          ))}
        </div>
        <Notifications live={live} persona="bus_driver" />
      </div>
    </>
  );
}

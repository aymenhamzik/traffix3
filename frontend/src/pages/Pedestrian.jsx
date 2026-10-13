import { Notifications, Waiting } from "../components/Feed.jsx";

export default function Pedestrian({ live }) {
  const rain = live.weather?.rain > 0;
  return (
    <>
      <div><h1>Crossings near you</h1>
        <p className="muted">Ferjani · walk signals, waits, and whether the green is held while people finish crossing.</p></div>
      <Waiting live={live} />
      {rain && <div className="card"><span className="pill info">Rain</span>Walking is slower in the rain; clearance times are lengthened.</div>}
      <div className="split">
        <div className="grid g2">
          {(live.junctions || []).filter((j) => j.crossings.length).map((j) => (
            <div key={j.id} className="card">
              <h3>{j.id} · {j.name}</h3>
              <table><tbody>
                {j.crossings.map((c) => (
                  <tr key={c.id}>
                    <td className="mono">{c.id.replace(":", "")}</td>
                    <td>{c.walk ? <span className="pill ok">walk</span> : <span className="pill bad">wait</span>}</td>
                    <td>{c.waiting} waiting{c.waiting ? `, longest ${c.longest_wait}s` : ""}</td>
                    <td className="muted">{c.on_crossing ? `${c.on_crossing} crossing` : ""}</td>
                  </tr>
                ))}
              </tbody></table>
            </div>
          ))}
        </div>
        <Notifications live={live} persona="pedestrian" />
      </div>
    </>
  );
}

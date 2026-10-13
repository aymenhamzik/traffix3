import { useMemo, useState } from "react";
import { useOnce } from "../api.js";

const LABEL = { fixed: "Fixed-time", actuated: "Actuated", junction_only: "Junction only",
                traffix_rules: "TraffiX (rules)", traffix: "TraffiX", traffix_predictive: "Predictive",
                traffix_rl: "RL" };
const COMPARISONS = {
  "vs actuated": "TraffiX vs SUMO actuated",
  "supermaster adds": "What the supermaster adds (vs junction only)",
  "models add": "What the trained models add (vs rules)",
  "predictive vs max-pressure": "Predictive agent vs max-pressure",
  "RL vs max-pressure": "Reinforcement learning agent vs max-pressure",
};
const METRIC = { veh_mean_wait_s: "car wait", ped_mean_wait_s: "pedestrian wait",
                 ambulance_mean_travel_s: "ambulance trip" };

export default function Results() {
  const data = useOnce("/results");
  const personas = useMemo(() => [...new Set((data?.summary || []).map((r) => r.persona))], [data]);
  const [persona, setPersona] = useState(null);
  const p = persona || personas[0];
  const measures = useMemo(() => [...new Set((data?.summary || []).filter((r) => r.persona === p).map((r) => r.measure))], [data, p]);
  const [measure, setMeasure] = useState(null);
  const m = measures.includes(measure) ? measure : measures[0];

  if (!data) return <div className="card empty">Loading results…</div>;
  if (!data.summary.length)
    return <div className="card empty">No results yet. Run <span className="mono">python scripts/run_experiments.py</span> then <span className="mono">python scripts/analyze.py</span>.</div>;

  const rows = data.summary.filter((r) => r.persona === p && r.measure === m);
  const cell = (s, c) => rows.find((r) => r.scenario === s && r.controller === c);
  const sig = data.significance.filter((r) => r.p < 0.05);

  return (
    <>
      <div><h1>Experiment results</h1>
        <p className="muted">Mean over seeds for every scenario and controller. Lower is better for every measure.
          The best value in each row is highlighted.</p></div>

      <div className="bar">
        {personas.map((x) => (
          <button key={x} className={x === p ? "primary" : ""} onClick={() => { setPersona(x); setMeasure(null); }}>{x}</button>
        ))}
      </div>

      <div className="card">
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <h2 style={{ flex: 1 }}>{p}</h2>
          <select value={m} onChange={(e) => setMeasure(e.target.value)} aria-label="Measure">
            {measures.map((x) => <option key={x}>{x}</option>)}
          </select>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead><tr><th>Scenario</th>{data.controllers.map((c) => <th key={c} style={{ textAlign: "right" }}>{LABEL[c]}</th>)}</tr></thead>
            <tbody>
              {data.scenarios.map((s) => {
                const vals = data.controllers.map((c) => cell(s, c)?.mean).filter((v) => v !== undefined && v !== null);
                if (!vals.length) return null;
                const best = Math.min(...vals);
                return (
                  <tr key={s}>
                    <td>{s.replaceAll("_", " ")}</td>
                    {data.controllers.map((c) => {
                      const r = cell(s, c);
                      const isBest = r && r.mean === best;
                      return (
                        <td key={c} style={{ textAlign: "right", fontWeight: c === "traffix" ? 600 : 400,
                                             color: isBest ? "#2bc4b5" : undefined }}>
                          {r && r.mean !== null ? r.mean : "—"}
                          {r && r.std !== null && <span className="muted" style={{ fontSize: 12 }}> ±{r.std}</span>}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid g3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
        {Object.entries(COMPARISONS).map(([key, title]) => {
          const items = sig.filter((r) => r.comparison === key);
          return (
            <div key={key} className="card">
              <h2>{title}</h2>
              {items.length === 0 && <span className="muted">No significant difference (p &lt; 0.05).</span>}
              {items.map((r, i) => (
                <div key={i} className={`note ${r["change_%"] < 0 ? "info" : "danger"}`}>
                  <b>{r.scenario.replaceAll("_", " ")}</b>, {METRIC[r.metric] || r.metric}:{" "}
                  <span style={{ color: r["change_%"] < 0 ? "#8fe3d8" : "#f4a497" }}>
                    {r["change_%"] > 0 ? "+" : ""}{r["change_%"]}%
                  </span>{" "}
                  <span className="muted">({r.traffix} vs {r.other}, p = {r.p})</span>
                </div>
              ))}
            </div>
          );
        })}
      </div>

      {data.has_chart && (
        <div className="card">
          <h2>Charts</h2>
          <img src="/api/results/chart" alt="Bar charts comparing controllers across scenarios for each persona measure"
               style={{ width: "100%", borderRadius: 8, background: "#fff" }} />
        </div>
      )}
      <p className="muted">Simulation on a schematic central-Tunis network. Significance: paired t-tests over seeds.
        Green change = TraffiX better, red = worse.</p>
    </>
  );
}

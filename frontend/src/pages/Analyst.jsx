import { useEffect, useState } from "react";
import { api, useOnce } from "../api.js";
import { Waiting } from "../components/Feed.jsx";

export default function Analyst({ live }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [error, setError] = useState("");
  const metrics = useOnce("/models");
  const hasEmergency = ["emergency", "combined"].includes(live.scenario);
  const examples = hasEmergency
    ? ["Why did ambulance 0 get green?", "What happened with the fire truck 0?", "Was any emergency vehicle denied?"]
    : ["Why did the late buses get priority?", "What happened with the incident?", "Why was the walk signal delayed at B2?",
       "What did the rain change?"];
  useEffect(() => { setQuestion(examples[0]); setAnswer(null); }, [live.scenario]);
  useEffect(() => {
    if (live.status !== "running" && live.status !== "finished") return;
    const id = setTimeout(() => api(`/decisions?limit=150&q=${encodeURIComponent(q)}`).then(setRows).catch(() => {}), 300);
    return () => clearTimeout(id);
  }, [q, live.counts?.decisions]);
  const ask = async () => {
    if (!question.trim()) { setError("Type a question first"); return; }
    setError("");
    try { setAnswer(await api("/ask", { method: "POST", headers: { "Content-Type": "application/json" },
                                         body: JSON.stringify({ question }) })); }
    catch (e) { setError(String(e)); }
  };
  return (
    <>
      <div><h1>Why did the system do that?</h1>
        <p className="muted">Tahani · every decision has a reason code. Synapse explains with citations or abstains.</p></div>
      <Waiting live={live} />
      <div className="card">
        <h2>Ask Synapse</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <input style={{ flex: 1 }} value={question} onChange={(e) => { setQuestion(e.target.value); setError(""); }} />
          <button className="primary" onClick={ask}>Ask</button>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {examples.map((x) => (
            <button key={x} style={{ fontSize: 12, padding: "3px 10px" }} onClick={() => setQuestion(x)}>{x}</button>
          ))}
        </div>
        {error && <span style={{ color: "#f4a497", fontSize: 13 }}>{error}</span>}
        {answer && <div className="answer">
          <span className={`pill ${answer.abstained ? "warn" : "ok"}`}>{answer.abstained ? "abstained" : `${answer.citations.length} citations`}</span>{"\n"}{answer.answer}</div>}
      </div>
      <div className="split">
        <div className="card">
          <h2>Decision log</h2>
          <input placeholder="Filter: ambulance, B3, bus, crossing, rain..." value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="feed">
            <table><tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className="mono muted" style={{ whiteSpace: "nowrap" }}>{e.clock || `${Math.round(e.t)}s`}</td>
                  <td>
                    <div>{e.text || e.reason}</div>
                    <details style={{ marginTop: 3 }}>
                      <summary className="muted" style={{ fontSize: 12, cursor: "pointer" }}>#{e.id} · {e.agent} · {e.reason}</summary>
                      <span className="muted mono" style={{ fontSize: 12, wordBreak: "break-all" }}>{JSON.stringify(e.details)}</span>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody></table>
          </div>
        </div>
        <div className="card">
          <h2>Trained models</h2>
          {!metrics || !Object.keys(metrics).length ? <span className="muted">Run python scripts/train.py</span> :
            <table><tbody>
              {Object.entries(metrics).filter(([k]) => !k.startsWith("_")).map(([k, v]) => (
                <tr key={k}><td><b>{k.replaceAll("_", " ")}</b></td>
                  <td className="mono">{Object.entries(v).filter(([, x]) => typeof x !== "object").slice(0, 4)
                    .map(([a, b]) => `${a}: ${b}`).join(" · ")}</td></tr>
              ))}
            </tbody></table>}
        </div>
      </div>
    </>
  );
}

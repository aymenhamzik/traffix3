import { useEffect, useState } from "react";
import { api } from "../api.js";
import { dirOf, t, useLang } from "../i18n.js";

// Operator copilot (Synapse layer): summary, suggested actions with Approve / Dismiss
// (recorded in the decision log, never applied automatically) and an incident report draft.
export default function Copilot({ live }) {
  const { lang } = useLang();
  const [data, setData] = useState(null);
  const [report, setReport] = useState(null);
  const [decided, setDecided] = useState({});
  const [busy, setBusy] = useState(false);
  const load = () => api(`/copilot?lang=${lang}`).then(setData).catch(() => setData(null));
  useEffect(() => {
    if (live.status !== "running" && live.status !== "finished") return;
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [lang, live.status, live.scenario]);
  const decide = async (s, decision) => {
    await api("/copilot/decision", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suggestion_id: s.id, title: s.title, decision }) });
    setDecided({ ...decided, [s.id]: decision });
  };
  const draft = async () => {
    setBusy(true);
    try { setReport(await api(`/copilot/report?lang=${lang}`, { method: "POST" })); } finally { setBusy(false); }
  };
  if (!data) return null;
  return (
    <div className="card" dir={dirOf(lang)}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <h2 style={{ flex: 1 }}>{t("copilot", lang)}</h2>
        <span className={`pill ${data.engine === "llm" ? "ok" : "info"}`}>{data.engine === "llm" ? "LLM" : "rules"}</span>
        <span className="muted mono">{data.clock?.slice(11)}</span>
        <button onClick={load} style={{ padding: "3px 10px", fontSize: 12 }}>{t("refresh", lang)}</button>
      </div>
      <p style={{ lineHeight: 1.6, margin: 0 }}>{data.summary}</p>
      <h3>{t("suggestions", lang)}</h3>
      {data.suggestions.length === 0 && <span className="muted">{data.empty_text || "—"}</span>}
      {data.suggestions.map((s) => (
        <div key={s.id} className="note warning" style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 240 }}>
            <b>{s.title}</b>{s.why && <div className="muted" style={{ fontSize: 13 }}>{s.why}</div>}
            {s.citations?.length > 0 && <div className="muted mono" style={{ fontSize: 12 }}>{s.citations.map((c) => `#${c}`).join(" ")}</div>}
          </div>
          {decided[s.id]
            ? <span className={`pill ${decided[s.id] === "approve" ? "ok" : "info"}`}>{t(decided[s.id] === "approve" ? "approved" : "dismissed", lang)}</span>
            : <>
                <button className="primary" style={{ padding: "4px 12px" }} onClick={() => decide(s, "approve")}>{t("approve", lang)}</button>
                <button style={{ padding: "4px 12px" }} onClick={() => decide(s, "dismiss")}>{t("dismiss", lang)}</button>
              </>}
        </div>
      ))}
      <div><button onClick={draft} disabled={busy}>{busy ? "…" : t("report", lang)}</button></div>
      {report && <div className="answer" style={{ whiteSpace: "pre-wrap" }}>{report.report}</div>}
    </div>
  );
}

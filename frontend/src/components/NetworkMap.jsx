import { useEffect, useRef, useState } from "react";
import { useOnce } from "../api.js";

// Vehicle shapes (map units are metres; sizes exaggerated so they stay visible when zoomed out)
const VEHICLES = {
  car: { w: 10, h: 5, fill: "#b9c4cc", label: "Car" },
  moto: { w: 7, h: 3, fill: "#f2c47a", label: "Motorcycle" },
  bus: { w: 24, h: 7, fill: "#5c9bea", label: "Bus" },
  ambulance: { w: 13, h: 7, fill: "#ffffff", stroke: "#ff4a3a", cross: true, label: "Ambulance" },
  police: { w: 12, h: 6, fill: "#2f5bff", stripe: "#ffffff", label: "Police" },
  fire: { w: 18, h: 7, fill: "#ff6e1e", stripe: "#ffd23f", label: "Fire truck" },
};

function Vehicle({ v, x, y, focused, scale = 1 }) {
  const s = VEHICLES[v.kind] || VEHICLES.car;
  const k = (focused ? 1.8 : 1) * scale;
  const w = s.w * k, h = s.h * k;
  return (
    <g transform={`translate(${x},${y}) rotate(${(v.angle ?? 90) - 90})`}>
      <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={h / 3} fill={s.fill}
            stroke={focused ? "#fff" : s.stroke || "none"} strokeWidth={focused ? 3 : s.stroke ? 2 : 0} />
      {s.stripe && <rect x={-w / 2} y={-h / 6} width={w} height={h / 3} fill={s.stripe} />}
      {s.cross && <>
        <rect x={-1.2 * k} y={-h / 2.6} width={2.4 * k} height={h / 1.3} fill="#ff4a3a" />
        <rect x={-h / 2.6} y={-1.2 * k} width={h / 1.3} height={2.4 * k} fill="#ff4a3a" />
      </>}
      <rect x={w / 2 - 2} y={-h / 2 + 1} width={2} height={h - 2} fill="#12161e" opacity="0.35" />
    </g>
  );
}

export function Legend() {
  return (
    <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 13 }} className="muted">
      {Object.entries(VEHICLES).map(([k, s]) => (
        <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <svg width="26" height="12" aria-hidden="true">
            <rect x="1" y="2" width="24" height="8" rx="3" fill={s.fill} stroke={s.stroke || "none"} strokeWidth="1.5" />
            {s.stripe && <rect x="1" y="5" width="24" height="2.5" fill={s.stripe} />}
            {s.cross && <rect x="11.5" y="2.5" width="3" height="7" fill="#ff4a3a" />}
          </svg>{s.label}
        </span>
      ))}
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4" fill="#e8ecef" /></svg>Pedestrian
      </span>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4" fill="#ff4fd8" /></svg>Slow walker
      </span>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <svg width="34" height="12" aria-hidden="true">
          <circle cx="6" cy="6" r="4.5" fill="#ff4a3a" /><circle cx="17" cy="6" r="4.5" fill="#ffc83d" />
          <circle cx="28" cy="6" r="4.5" fill="#35d07f" /></svg>Traffic light
      </span>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <svg width="26" height="12" aria-hidden="true"><line x1="1" y1="6" x2="25" y2="6" stroke="#35d07f" strokeWidth="4" strokeDasharray="2.5 2.5" /></svg>Crossing (green = walk)
      </span>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <svg width="14" height="14" aria-hidden="true"><rect x="1" y="1" width="12" height="12" rx="3" fill="#1d4f9c" stroke="#fff" />
          <text x="7" y="10.5" textAnchor="middle" fontSize="9" fill="#fff" fontWeight="700">B</text></svg>Bus stop
      </span>
    </div>
  );
}

// Draws the Tunis network, junction states, vehicles and pedestrians. Zoom with the mouse wheel,
// drag to pan, double-click or the reset button to fit the whole network again.
// highlight: { incidents, floods, routeB, alt } (edge ids), focus: vehicle ids to emphasise
const LINE_COLORS = { L1_east: "#5c9bea", L1_west: "#8fb8f2", L2_south: "#a77cf2", L2_north: "#c7a8f7" };

export default function NetworkMap({ live, highlight = {}, focus = [], showCars = true, height = 420, lines = [] }) {
  const geo = useOnce(live.scenario ? "/network" : null, [live.scenario]);
  const svgRef = useRef(null);
  const [view, setView] = useState(null);           // [x, y, w, h] of the visible area
  const [peds, setPeds] = useState(true);
  const drag = useRef(null);

  const pad = 60;
  const full = geo ? (() => {
    const [x0, y0, x1, y1] = geo.bounds;
    return [0, 0, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad];
  })() : null;
  useEffect(() => { if (full) setView(full); }, [geo]);

  useEffect(() => {                                  // wheel zoom needs a non-passive listener
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e) => {
      e.preventDefault();
      zoomAt(e.deltaY < 0 ? 0.8 : 1.25, e.clientX, e.clientY);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  if (!geo || !view || live.status === "idle" || live.status === "offline")
    return <div className="map empty" style={{ height }}>Start a scenario to see the map</div>;

  const [x0, , , y1] = geo.bounds;
  const X = (x) => x - x0 + pad, Y = (y) => y1 - y + pad;
  const toMap = (cx, cy) => {
    const r = svgRef.current.getBoundingClientRect();
    const scale = Math.max(view[2] / r.width, view[3] / r.height);
    const offX = (r.width * scale - view[2]) / 2, offY = (r.height * scale - view[3]) / 2;
    return [view[0] - offX + (cx - r.left) * scale, view[1] - offY + (cy - r.top) * scale, scale];
  };
  function zoomAt(factor, cx, cy) {
    setView((v) => {
      if (!v) return v;
      const r = svgRef.current.getBoundingClientRect();
      const [mx, my] = cx === undefined ? [v[0] + v[2] / 2, v[1] + v[3] / 2] : toMap(cx, cy);
      const w = Math.min(Math.max(v[2] * factor, full[2] / 20), full[2] * 1.5);
      const h = w * (v[3] / v[2]);
      const k = w / v[2];
      return [mx - (mx - v[0]) * k, my - (my - v[1]) * k, w, h];
    });
  }
  const onDown = (e) => { drag.current = { x: e.clientX, y: e.clientY, v: view }; e.currentTarget.setPointerCapture?.(e.pointerId); };
  const onMove = (e) => {
    if (!drag.current) return;
    const r = svgRef.current.getBoundingClientRect();
    const scale = Math.max(view[2] / r.width, view[3] / r.height);
    const { x, y, v } = drag.current;
    setView([v[0] - (e.clientX - x) * scale, v[1] - (e.clientY - y) * scale, v[2], v[3]]);
  };
  const onUp = () => { drag.current = null; };

  const status = Object.fromEntries((live.junctions || []).map((j) => [j.id, j]));
  const inc = new Set(highlight.incidents || []), fl = new Set(highlight.floods || []);
  const rb = new Set(highlight.routeB || []), alt = new Set(highlight.alt || []);
  const color = (j) => !j ? "#5a6470" : j.preempt ? "#e5604d" : j.mode === "fixed" ? "#e6a23c"
    : j.mode === "actuated" ? "#c9b25a" : j.queue > 12 ? "#e6a23c" : "#2bc4b5";
  const zoomedIn = view[2] < full[2] * 0.6;
  const btn = { padding: "2px 10px", fontSize: 16, lineHeight: "22px" };
  const jr = Math.max(9, Math.min(30, view[2] / 55));     // junction markers shrink when zooming in
  const sr = Math.max(3.5, Math.min(9, view[2] / 170));    // traffic light size
  const br = Math.max(5, Math.min(13, view[2] / 120));     // bus stop size
  const walk = {};
  (live.junctions || []).forEach((j) => j.crossings.forEach((c) => { walk[c.id] = c.walk; }));
  const lightColor = { G: "#35d07f", y: "#ffc83d", r: "#ff4a3a" };
  const vk = Math.max(0.5, Math.min(1.4, view[2] / 1100));   // vehicles approach true size when zoomed in
  const pr = Math.max(0.9, Math.min(3, view[2] / 550));        // pedestrian dot radius

  return (
    <div style={{ position: "relative" }}>
      <svg ref={svgRef} className="map" viewBox={view.join(" ")} style={{ height, cursor: drag.current ? "grabbing" : "grab", touchAction: "none" }}
           role="img" aria-label="Zoomable map of the central Tunis network with junctions, vehicles and pedestrians"
           onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}
           onDoubleClick={() => setView(full)}>
        {/* sidewalks, then each traffic lane (real widths in metres) */}
        {geo.edges.flatMap((e) => (e.sidewalks || []).map((sh, i) => (
          <polyline key={`sw${e.id}${i}`} points={sh.map(([x, y]) => `${X(x)},${Y(y)}`).join(" ")} fill="none"
                    stroke="#4b5462" strokeWidth={2.4} strokeLinecap="round" />
        )))}
        {geo.edges.flatMap((e) => (e.lane_shapes || [e.shape]).map((sh, i) => (
          <polyline key={`ln${e.id}${i}`} points={sh.map(([x, y]) => `${X(x)},${Y(y)}`).join(" ")} fill="none"
                    stroke="#2c3442" strokeWidth={e.lane_shapes ? 3.3 : 8 + e.lanes * 5} strokeLinecap="butt" />
        )))}
        {geo.edges.filter((e) => fl.has(e.id) || inc.has(e.id) || rb.has(e.id) || alt.has(e.id)).map((e) => {
          const stroke = fl.has(e.id) ? "#5c9bea" : inc.has(e.id) ? "#e5604d" : rb.has(e.id) ? "#2bc4b5" : "#e6a23c";
          return <polyline key={`hl${e.id}`} points={e.shape.map(([x, y]) => `${X(x)},${Y(y)}`).join(" ")} fill="none"
                           stroke={stroke} strokeWidth={Math.max(4, e.lanes * 3.3)} opacity="0.7"
                           strokeDasharray={fl.has(e.id) ? "14 8" : undefined} />;
        })}
        {geo.edges.filter((e) => e.bus_lane).map((e) => (
          <polyline key={`bl${e.id}`} points={e.shape.map(([x, y]) => `${X(x)},${Y(y)}`).join(" ")} fill="none"
                    stroke="#8a2f3a" strokeWidth={5} strokeDasharray="10 6" />
        ))}
        {lines.map((ln) => (geo.lines?.[ln] || []).map((eid) => {
          const e = geo.edges.find((x) => x.id === eid);
          return e && <polyline key={`ln${ln}${eid}`} points={e.shape.map(([x, y]) => `${X(x)},${Y(y)}`).join(" ")}
                                fill="none" stroke={LINE_COLORS[ln] || "#5c9bea"} strokeWidth={6} opacity="0.85" />;
        }))}
        {(geo.crossings || []).map((c) => (
          <polyline key={c.id} points={c.shape.map(([x, y]) => `${X(x)},${Y(y)}`).join(" ")} fill="none"
                    stroke={walk[c.id] ? "#35d07f" : "#e8ecef"} strokeWidth={4} strokeDasharray="2.5 2.5"
                    opacity={walk[c.id] ? 0.95 : 0.55} />
        ))}
        {zoomedIn && geo.edges.filter((e) => e.name).map((e) => {
          const [[ax, ay], [bx, by]] = [e.shape[0], e.shape[e.shape.length - 1]];
          if (e.id > e.id.split("_").reverse().join("_")) return null;     // one label per road
          return <text key={`n${e.id}`} x={(X(ax) + X(bx)) / 2} y={(Y(ay) + Y(by)) / 2 - 22} textAnchor="middle"
                       fontSize={view[2] / 45} fill="#8995a0" fontFamily="IBM Plex Sans">{e.name}</text>;
        })}
        {peds && (live.people || []).map(([x, y, slow], i) => (
          <circle key={`p${i}`} cx={X(x)} cy={Y(y)} r={slow ? pr * 1.15 : pr} fill={slow ? "#ff4fd8" : "#e8ecef"} opacity="0.9" />
        ))}
        {showCars && (live.vehicles || []).map((v) => (
          <Vehicle key={v.id} v={v} x={X(v.x)} y={Y(v.y)} focused={focus.includes(v.id)} scale={vk} />
        ))}
        {(geo.bus_stops || []).map((b) => (
          <g key={b.id}>
            <rect x={X(b.x) - br} y={Y(b.y) - br} width={br * 2} height={br * 2} rx={br / 3} fill="#1d4f9c"
                  stroke="#ffffff" strokeWidth={br / 5} />
            <text x={X(b.x)} y={Y(b.y) + br * 0.4} textAnchor="middle" fontSize={br * 1.1} fill="#fff"
                  fontFamily="IBM Plex Sans" fontWeight="700">B</text>
            {zoomedIn && <text x={X(b.x)} y={Y(b.y) + br * 2.6} textAnchor="middle" fontSize={br * 0.9}
                               fill="#a9c8f3" fontFamily="IBM Plex Sans">bus stop</text>}
          </g>
        ))}
        {(geo.signals || []).map((g) => {
          const c = live.signals?.[g.tls]?.[g.edge] || "r";
          return (
            <g key={`s${g.edge}`}>
              <rect x={X(g.x) - sr * 1.25} y={Y(g.y) - sr * 1.25} width={sr * 2.5} height={sr * 2.5} rx={sr * 0.6}
                    fill="#0b0e13" stroke="#3a4454" strokeWidth={sr * 0.2} />
              <circle cx={X(g.x)} cy={Y(g.y)} r={sr} fill={lightColor[c]} />
            </g>
          );
        })}
        {geo.nodes.filter((n) => n.signal).map((n) => (
          <g key={n.id}>
            <circle cx={X(n.x)} cy={Y(n.y)} r={jr} fill={color(status[n.id])} opacity={zoomedIn ? 0.75 : 0.92} />
            <text x={X(n.x)} y={Y(n.y) + jr * 0.27} textAnchor="middle" fontSize={jr * 0.8} fontFamily="IBM Plex Mono"
                  fill="#12161e" fontWeight="600">{n.id}</text>
          </g>
        ))}
      </svg>
      <div style={{ position: "absolute", top: 10, right: 10, display: "flex", flexDirection: "column", gap: 6 }}>
        <button style={btn} onClick={() => zoomAt(0.7)} aria-label="Zoom in">+</button>
        <button style={btn} onClick={() => zoomAt(1.4)} aria-label="Zoom out">−</button>
        <button style={{ ...btn, fontSize: 12 }} onClick={() => setView(full)} aria-label="Reset view">fit</button>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 8, flexWrap: "wrap" }}>
        <Legend />
        <label className="muted" style={{ fontSize: 13, display: "inline-flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={peds} onChange={(e) => setPeds(e.target.checked)} style={{ padding: 0 }} />
          show pedestrians
        </label>
      </div>
    </div>
  );
}

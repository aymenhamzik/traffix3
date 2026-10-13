// All data comes from the Python backend (supermaster API). Nothing talks to SUMO directly.
import { useEffect, useState } from "react";

export async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

// Polls the live snapshot once per second.
export function useLive() {
  const [state, setState] = useState({ status: "idle" });
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await api("/state");
        if (alive) setState(s);
      } catch {
        if (alive) setState({ status: "offline" });
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  return state;
}

export function useOnce(path, deps = []) {
  const [data, setData] = useState(null);
  useEffect(() => {
    if (!path) { setData(null); return; }        // nothing to fetch yet
    api(path).then(setData).catch(() => setData(null));
  }, deps);
  return data;
}

export const PERSONAS = [
  { id: "pedestrian", path: "/pedestrian", name: "Ferjani", role: "Pedestrian" },
  { id: "car_driver", path: "/driver", name: "Faycel", role: "Car driver" },
  { id: "bus_passenger", path: "/passenger", name: "Mamadou", role: "Bus passenger" },
  { id: "bus_driver", path: "/bus-driver", name: "Hédi", role: "Bus driver" },
  { id: "emergency_crew", path: "/emergency", name: "Touhami", role: "Ambulance crew" },
  { id: "operator", path: "/operator", name: "Kamel", role: "Traffic operator" },
  { id: "analyst", path: "/analyst", name: "Tahani", role: "Incident analyst" },
];

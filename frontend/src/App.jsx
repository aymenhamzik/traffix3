import { useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { LangContext } from "./i18n.js";
import { PERSONAS, useLive } from "./api.js";
import ScenarioBar from "./components/ScenarioBar.jsx";
import Home from "./pages/Home.jsx";
import Pedestrian from "./pages/Pedestrian.jsx";
import CarDriver from "./pages/CarDriver.jsx";
import BusPassenger from "./pages/BusPassenger.jsx";
import BusDriver from "./pages/BusDriver.jsx";
import EmergencyCrew from "./pages/EmergencyCrew.jsx";
import Operator from "./pages/Operator.jsx";
import Analyst from "./pages/Analyst.jsx";
import Results from "./pages/Results.jsx";

export default function App() {
  const live = useLive();
  const [lang, setLangState] = useState(() => {
    try { return localStorage.getItem("traffix-lang") || "en"; } catch { return "en"; }
  });
  const setLang = (l) => { setLangState(l); try { localStorage.setItem("traffix-lang", l); } catch {} };
  const pages = { pedestrian: Pedestrian, car_driver: CarDriver, bus_passenger: BusPassenger,
                  bus_driver: BusDriver, emergency_crew: EmergencyCrew, operator: Operator, analyst: Analyst };
  return (
    <LangContext.Provider value={{ lang, setLang }}>
    <div className="app">
      <aside className="side">
        <div className="brand">Traffi<span>X</span></div>
        <NavLink to="/" end className="nav">Overview<small>Choose a scenario</small></NavLink>
        {PERSONAS.map((p) => (
          <NavLink key={p.id} to={p.path} className="nav">
            {p.role}<small>{p.name}</small>
          </NavLink>
        ))}
        <NavLink to="/results" className="nav" style={{ marginTop: 12 }}>Results<small>All experiments</small></NavLink>
      </aside>
      <main className="main">
        <ScenarioBar live={live} />
        <Routes>
          <Route path="/" element={<Home live={live} />} />
          <Route path="/results" element={<Results />} />
          {PERSONAS.map((p) => {
            const Page = pages[p.id];
            return <Route key={p.id} path={p.path} element={<Page live={live} />} />;
          })}
        </Routes>
      </main>
    </div>
    </LangContext.Provider>
  );
}

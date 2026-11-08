import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { get } from "./api";
import { devMode, logout } from "./auth";
import { ROLE_LABEL, User, isStaff } from "./types";
import Dashboard from "./pages/Dashboard";
import Requests from "./pages/Requests";
import RequestForm from "./pages/RequestForm";
import RequestDetail from "./pages/RequestDetail";
import InboundReview from "./pages/InboundReview";
import Admin from "./pages/Admin";

export default function App() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => get<User>("/me") });
  const role = me.data?.role;
  const isAdmin = role === "ADMIN";
  const staff = isStaff(role);

  const switchDev = (v: string) => { localStorage.setItem("srm_dev_user", v); location.reload(); };

  return (
    <div className="layout">
      <aside>
        <h1>SRM</h1>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/requests">{staff ? "Richieste" : "Le mie richieste"}</NavLink>
          <NavLink to="/requests/new">+ Nuova richiesta</NavLink>
          {staff && <NavLink to="/inbound">Bozze da email (AI)</NavLink>}
          {isAdmin && <NavLink to="/admin">Amministrazione</NavLink>}
        </nav>
        <div className="me">
          {me.data && <><b>{me.data.full_name}</b><br /><small>{ROLE_LABEL[me.data.role]}</small></>}
          {devMode ? (
            <select value={localStorage.getItem("srm_dev_user") ?? ""} onChange={(e) => switchDev(e.target.value)}>
              <option value="">dev admin</option>
              <option value="back-demo@local">dev backoffice</option>
              <option value="sales-demo@local">dev sales</option>
            </select>
          ) : <button className="link" onClick={logout}>Esci</button>}
        </div>
      </aside>
      <main>
        {role === "SALES" && me.data?.sales_agent_id == null && (
          <div className="alert">Il tuo utente non è ancora collegato a un agente commerciale: contatta l'amministratore per poter creare e vedere richieste.</div>
        )}
        {me.isError && <div className="alert">Accesso non riuscito: {(me.error as Error).message}</div>}
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/requests" element={<Requests />} />
          <Route path="/requests/new" element={<RequestForm />} />
          <Route path="/requests/:id" element={<RequestDetail />} />
          <Route path="/requests/:id/edit" element={<RequestForm />} />
          <Route path="/inbound" element={me.isLoading ? null : staff ? <InboundReview /> : <Navigate to="/" />} />
          <Route path="/admin" element={me.isLoading ? null : isAdmin ? <Admin /> : <Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}

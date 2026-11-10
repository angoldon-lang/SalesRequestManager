import { useEffect } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, get } from "./api";
import { devMode, logout, mode } from "./auth";
import { ROLE_LABEL, User, isStaff } from "./types";
import Dashboard from "./pages/Dashboard";
import Requests from "./pages/Requests";
import RequestForm from "./pages/RequestForm";
import RequestDetail from "./pages/RequestDetail";
import InboundReview from "./pages/InboundReview";
import Admin from "./pages/Admin";
import Users from "./pages/Users";
import Login from "./pages/Login";
import ChangePassword from "./pages/ChangePassword";

export default function App() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => get<User>("/me") });
  // Dopo login/logout/cambio password: si scartano i dati in cache (di un altro utente) e si ricarica "me"
  const refreshMe = () => {
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    qc.refetchQueries({ queryKey: ["me"] });
  };

  // sessione scaduta / cambio password richiesto, segnalato da api.ts
  useEffect(() => {
    window.addEventListener("srm-session-changed", refreshMe);
    return () => window.removeEventListener("srm-session-changed", refreshMe);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const role = me.data?.role;
  const isAdmin = role === "ADMIN";
  const staff = isStaff(role);

  if (mode === "local" && me.error instanceof ApiError && me.error.status === 401) return <Login onDone={refreshMe} />;
  if (me.isLoading) return <div className="login-wrap muted">Caricamento…</div>;
  if (mode === "local" && me.data?.must_change_password) return <ChangePassword forced onDone={refreshMe} />;

  const switchDev = (v: string) => { localStorage.setItem("srm_dev_user", v); location.reload(); };

  return (
    <div className="layout">
      <aside>
        <h1>SRM</h1>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/requests" end>{staff ? "Richieste" : "Le mie richieste"}</NavLink>
          <NavLink to="/requests/new">+ Nuova richiesta</NavLink>
          {staff && <NavLink to="/inbound">Bozze da email (AI)</NavLink>}
          {isAdmin && <NavLink to="/users">Utenti e ruoli</NavLink>}
          {isAdmin && <NavLink to="/admin">Configurazione</NavLink>}
        </nav>
        <div className="me">
          {me.data && <><b>{me.data.full_name}</b><br /><small>{ROLE_LABEL[me.data.role]}</small></>}
          {devMode() && (
            <select value={localStorage.getItem("srm_dev_user") ?? ""} onChange={(e) => switchDev(e.target.value)}>
              <option value="">dev admin</option>
              <option value="back-demo@local">dev backoffice</option>
              <option value="sales-demo@local">dev sales</option>
            </select>
          )}
          <div className="row" style={{ marginTop: 8, gap: 12 }}>
            {mode === "local" && <NavLink className="mini" to="/password">Cambia password</NavLink>}
            {!devMode() && <button className="link" onClick={logout}>Esci</button>}
          </div>
        </div>
      </aside>
      <main>
        {me.isError && <div className="alert">Accesso non riuscito: {(me.error as Error).message}</div>}
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/requests" element={<Requests />} />
          <Route path="/requests/new" element={<RequestForm />} />
          <Route path="/requests/:id" element={<RequestDetail />} />
          <Route path="/requests/:id/edit" element={<RequestForm />} />
          <Route path="/inbound" element={staff ? <InboundReview /> : <Navigate to="/" />} />
          <Route path="/users" element={isAdmin ? <Users meId={me.data?.id} /> : <Navigate to="/" />} />
          <Route path="/admin" element={isAdmin ? <Admin /> : <Navigate to="/" />} />
          <Route path="/password" element={<><h2>Il mio account</h2><ChangePassword onDone={() => qc.invalidateQueries({ queryKey: ["me"] })} /></>} />
        </Routes>
      </main>
    </div>
  );
}

import { FormEvent, useState } from "react";
import { ApiError, post } from "../api";
import { logout, setToken } from "../auth";
import { ErrorBox } from "../components";

/** forced = primo accesso o password reimpostata dall'admin: unica schermata disponibile. */
export default function ChangePassword({ forced, onDone }: { forced?: boolean; onDone: () => void }) {
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);

  const tooShort = pw.length > 0 && pw.length < 10;
  const mismatch = pw2.length > 0 && pw !== pw2;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await post<{ access_token: string }>("/auth/change-password", { current_password: cur, new_password: pw });
      setToken(r.access_token);
      setOk(true); setCur(""); setPw(""); setPw2("");
      onDone();
    } catch (x) { setErr(x instanceof ApiError ? x : x); } finally { setBusy(false); }
  };

  const form = (
    <form className="card login" onSubmit={submit} style={forced ? undefined : { maxWidth: 440 }}>
      <h2>{forced ? "Imposta la tua password" : "Cambia password"}</h2>
      {forced && <p className="muted">Per sicurezza devi scegliere una nuova password prima di continuare.</p>}
      {ok && !forced && <div className="ok">Password aggiornata.</div>}
      <ErrorBox e={err} />
      <label className="field"><span>Password attuale</span>
        <input type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />
      </label>
      <label className={`field ${tooShort ? "has-error" : ""}`}><span>Nuova password (almeno 10 caratteri)</span>
        <input type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
        {tooShort && <small className="err">Almeno 10 caratteri</small>}
      </label>
      <label className={`field ${mismatch ? "has-error" : ""}`}><span>Ripeti la nuova password</span>
        <input type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
        {mismatch && <small className="err">Le password non coincidono</small>}
      </label>
      <div className="row">
        <button className="primary" disabled={busy || !cur || pw.length < 10 || pw !== pw2}>Salva password</button>
        {forced && <button type="button" onClick={logout}>Esci</button>}
      </div>
    </form>
  );
  return forced ? <div className="login-wrap">{form}</div> : form;
}

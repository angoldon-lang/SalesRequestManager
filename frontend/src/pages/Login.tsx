import { FormEvent, useState } from "react";
import { post } from "../api";
import { setToken } from "../auth";
import { ErrorBox } from "../components";

export default function Login({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await post<{ access_token: string }>("/auth/login", { username, password });
      setToken(r.access_token);
      onDone();
    } catch (x) { setErr(x); } finally { setBusy(false); }
  };

  return (
    <div className="login-wrap">
      <form className="login card" onSubmit={submit}>
        <h1>SRM</h1>
        <p className="muted">SalesRequestManager — accedi per continuare</p>
        <ErrorBox e={err} />
        <label className="field"><span>Utente</span>
          <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="field"><span>Password</span>
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button className="primary" disabled={busy || !username || !password}>{busy ? "Accesso…" : "Accedi"}</button>
      </form>
    </div>
  );
}

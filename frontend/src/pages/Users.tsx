import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, get, patch, post } from "../api";
import { Card, ErrorBox, Field, fmtDateTime } from "../components";
import { ROLE_HELP, ROLE_LABEL, Role, User } from "../types";

const ROLES = Object.keys(ROLE_LABEL) as Role[];
type Creds = { username: string; password: string; name: string };

function status(u: User) {
  if (!u.is_active) return <span className="badge draft">Disattivato</span>;
  if (u.locked_until && new Date(u.locked_until) > new Date()) return <span className="badge reminded">Bloccato</span>;
  if (!u.has_password) return <span className="badge reminded">Senza password</span>;
  if (u.must_change_password) return <span className="badge sent">Deve cambiare password</span>;
  return <span className="badge closed">Attivo</span>;
}

export default function Users({ meId }: { meId?: number }) {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => get<User[]>("/users") });
  const [edit, setEdit] = useState<Partial<User> & { password?: string } | null>(null);
  const [reset, setReset] = useState<User | null>(null);
  const [creds, setCreds] = useState<Creds | null>(null);
  const [filter, setFilter] = useState<"" | Role>("");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["users"] }); qc.invalidateQueries({ queryKey: ["agents"] }); };

  const rows = (users.data ?? []).filter((u) => !filter || u.role === filter);
  const nSales = users.data?.filter((u) => u.role === "SALES" && u.is_active).length ?? 0;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Utenti e ruoli</h2>
        <button className="primary" onClick={() => setEdit({ role: "SALES", is_active: true, password: "" })}>+ Nuovo utente</button>
      </div>
      <Card>
        <div className="grid g3 help">
          {ROLES.map((r) => <div key={r}><b>{ROLE_LABEL[r]}</b><br /><small className="muted">{ROLE_HELP[r]}</small></div>)}
        </div>
      </Card>
      {nSales === 0 && users.data && <div className="alert">Non c'è nessun agente commerciale: crea almeno un utente con ruolo <b>Sales</b> per poterlo scegliere nelle richieste.</div>}
      <Card title={`${rows.length} utenti`} actions={
        <select value={filter} onChange={(e) => setFilter(e.target.value as Role | "")} style={{ width: "auto" }}>
          <option value="">Tutti i ruoli</option>{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
        </select>}>
        <ErrorBox e={users.error} />
        <table>
          <thead><tr><th>Nome</th><th>Utente</th><th>Email</th><th>Ruolo</th><th>Stato</th><th>Ultimo accesso</th><th /></tr></thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id}>
                <td>{u.full_name}{u.id === meId && <small className="muted"> (tu)</small>}</td>
                <td>{u.username}</td><td>{u.email ?? "—"}</td><td>{ROLE_LABEL[u.role]}</td>
                <td>{status(u)}</td><td>{fmtDateTime(u.last_login_at)}</td>
                <td className="row">
                  <button onClick={() => setEdit(u)}>Modifica</button>
                  <button onClick={() => setReset(u)}>Password</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {edit && <EditDialog init={edit} isSelf={edit.id === meId} onClose={() => setEdit(null)}
        onDone={(c) => { setEdit(null); refresh(); if (c) setCreds(c); }} />}
      {reset && <ResetDialog user={reset} onClose={() => setReset(null)}
        onDone={(c) => { setReset(null); refresh(); setCreds(c); }} />}
      {creds && <CredsDialog c={creds} onClose={() => setCreds(null)} />}
    </>
  );
}

function PasswordField({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) {
  const gen = async () => onChange((await get<{ password: string }>("/users/generate-password")).password);
  return (
    <Field label="Password provvisoria (min. 10 caratteri)" required error={error}>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input value={value} onChange={(e) => onChange(e.target.value)} autoComplete="off" spellCheck={false} />
        <button type="button" onClick={gen}>Genera</button>
      </div>
      <small className="muted">L'utente dovrà cambiarla al primo accesso.</small>
    </Field>
  );
}

function EditDialog({ init, isSelf, onClose, onDone }: {
  init: Partial<User> & { password?: string }; isSelf: boolean; onClose: () => void; onDone: (c?: Creds) => void;
}) {
  const isNew = !init.id;
  const [v, setV] = useState({ username: init.username ?? "", full_name: init.full_name ?? "", email: init.email ?? "",
    role: (init.role ?? "SALES") as Role, is_active: init.is_active ?? true, password: init.password ?? "" });
  const save = useMutation({
    mutationFn: () => isNew
      ? post<User>("/users", { ...v, email: v.email || null })
      : patch<User>(`/users/${init.id}`, { full_name: v.full_name, email: v.email || null, role: v.role, is_active: v.is_active }),
    onSuccess: () => onDone(isNew ? { username: v.username, password: v.password, name: v.full_name } : undefined),
  });
  const f = (save.error as ApiError | null)?.fields ?? {};
  return (
    <div className="modal-bg" onClick={onClose}><div className="modal" onClick={(e) => e.stopPropagation()}>
      <h3>{isNew ? "Nuovo utente" : `Modifica ${init.username}`}</h3>
      <div className="grid" style={{ margin: "14px 0" }}>
        {isNew && <Field label="Nome utente (per il login)" required error={f.username}>
          <input value={v.username} autoComplete="off" onChange={(e) => setV({ ...v, username: e.target.value.trim() })} /></Field>}
        <Field label="Nome e cognome" required error={f.full_name}>
          <input value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} /></Field>
        <Field label={v.role === "SALES" ? "Email (obbligatoria: viene messa in CC)" : "Email"} required={v.role === "SALES"} error={f.email}>
          <input type="email" value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} /></Field>
        <Field label="Ruolo" required>
          <select value={v.role} disabled={isSelf} onChange={(e) => setV({ ...v, role: e.target.value as Role })}>
            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select>
          <small className="muted">{ROLE_HELP[v.role]}</small>
        </Field>
        {isNew && <PasswordField value={v.password} onChange={(p) => setV({ ...v, password: p })} error={f.password} />}
        <label className="row"><input type="checkbox" style={{ width: "auto" }} checked={v.is_active} disabled={isSelf}
          onChange={(e) => setV({ ...v, is_active: e.target.checked })} /> Attivo (può accedere)</label>
        {isSelf && <small className="muted">Non puoi cambiare il tuo ruolo né disattivarti.</small>}
      </div>
      <ErrorBox e={save.error} />
      <div className="row">
        <button className="primary" disabled={save.isPending || !v.full_name || (isNew && (!v.username || v.password.length < 10))}
          onClick={() => save.mutate()}>Salva</button>
        <button onClick={onClose}>Annulla</button>
      </div>
    </div></div>
  );
}

function ResetDialog({ user, onClose, onDone }: { user: User; onClose: () => void; onDone: (c: Creds) => void }) {
  const [pw, setPw] = useState("");
  const m = useMutation({
    mutationFn: () => post(`/users/${user.id}/reset-password`, { new_password: pw }),
    onSuccess: () => onDone({ username: user.username, password: pw, name: user.full_name }),
  });
  const f = (m.error as ApiError | null)?.fields ?? {};
  return (
    <div className="modal-bg" onClick={onClose}><div className="modal" onClick={(e) => e.stopPropagation()}>
      <h3>Reimposta password — {user.full_name}</h3>
      <p className="muted">Le sessioni aperte verranno chiuse, l'account sbloccato e al prossimo accesso sarà richiesta una nuova password.</p>
      <PasswordField value={pw} onChange={setPw} error={f.new_password} />
      <ErrorBox e={m.error} />
      <div className="row" style={{ marginTop: 14 }}>
        <button className="primary" disabled={m.isPending || pw.length < 10} onClick={() => m.mutate()}>Reimposta</button>
        <button onClick={onClose}>Annulla</button>
      </div>
    </div></div>
  );
}

function CredsDialog({ c, onClose }: { c: Creds; onClose: () => void }) {
  return (
    <div className="modal-bg"><div className="modal">
      <h3>Credenziali per {c.name}</h3>
      <p className="muted">Consegnale all'utente: <b>non verranno più mostrate</b>. Al primo accesso dovrà sceglierne una nuova.</p>
      <dl><dt>Utente</dt><dd><code>{c.username}</code></dd><dt>Password provvisoria</dt><dd><code>{c.password}</code></dd></dl>
      <div className="row" style={{ marginTop: 14 }}><button className="primary" onClick={onClose}>Ho annotato le credenziali</button></div>
    </div></div>
  );
}

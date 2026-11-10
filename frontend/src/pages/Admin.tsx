import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { del, get, post, put } from "../api";
import { Card, ErrorBox, Field } from "../components";
import type { Config, MapRow, Supplier, Vendor } from "../types";

const TABS = ["Configurazione", "Vendor", "Supplier", "Mapping"] as const;
const emails = (s: string) => s.split(/[,;\s]+/).map((x) => x.trim()).filter(Boolean);

export default function Admin() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Configurazione");
  return (
    <>
      <h2>Amministrazione</h2>
      <div className="tabs">{TABS.map((t) => <button key={t} className={t === tab ? "on" : ""} onClick={() => setTab(t)}>{t}</button>)}</div>
      {tab === "Configurazione" && <ConfigTab />}
      {tab === "Vendor" && <Simple path="vendors" cols={[["name", "Nome"], ["website", "Sito"], ["notes", "Note"]]} />}
      {tab === "Supplier" && <Simple path="suppliers" cols={[["name", "Nome"], ["notes", "Note"]]} />}
      {tab === "Mapping" && <MapTab />}
    </>
  );
}

function ConfigTab() {
  const qc = useQueryClient();
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => get<Config>("/config") });
  const [v, setV] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const form = v ?? (cfg.data && { ...cfg.data, default_cc: cfg.data.default_cc.join(", ") });
  const save = useMutation({
    mutationFn: () => put("/config", { ...form, default_cc: emails(form.default_cc), reminder_after_days: +form.reminder_after_days, reminder_max_count: +form.reminder_max_count }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["config"] }); setV(null); setMsg("Configurazione salvata."); },
  });
  const test = useMutation({ mutationFn: () => post("/config/test-mail"), onSuccess: (r: any) => setMsg(`Mail di prova inviata a ${r.to}.`) });
  if (!form) return null;
  const set = (k: string, val: any) => { setMsg(""); setV({ ...form, [k]: val }); };
  return (
    <Card>
      {msg && <div className="ok">{msg}</div>}
      <ErrorBox e={save.error ?? test.error} />
      <div className="form">
        <Field label="Mittente (mailbox M365 per l'invio via Graph)"><input value={form.sender_email} onChange={(e) => set("sender_email", e.target.value)} /></Field>
        <Field label="Mailbox dedicata per email in ingresso (AI)"><input value={form.inbound_mailbox} onChange={(e) => set("inbound_mailbox", e.target.value)} /></Field>
        <Field label="Cartella email elaborate"><input value={form.inbound_processed_folder} onChange={(e) => set("inbound_processed_folder", e.target.value)} /></Field>
        <Field label="Modello LLM"><input value={form.llm_model} onChange={(e) => set("llm_model", e.target.value)} /></Field>
        <div className="full"><Field label="CC di default (separati da virgola)"><input value={form.default_cc} onChange={(e) => set("default_cc", e.target.value)} /></Field></div>
        <Field label="Reminder dopo X giorni"><input type="number" min={1} max={60} value={form.reminder_after_days} onChange={(e) => set("reminder_after_days", e.target.value)} /></Field>
        <Field label="Numero massimo di solleciti"><input type="number" min={1} max={10} value={form.reminder_max_count} onChange={(e) => set("reminder_max_count", e.target.value)} /></Field>
        <label className="row"><input type="checkbox" style={{ width: "auto" }} checked={form.reminder_business_days} onChange={(e) => set("reminder_business_days", e.target.checked)} /> Conta solo giorni lavorativi (esclusi weekend e festivi IT)</label>
      </div>
      <div className="row" style={{ marginTop: 16 }}>
        <button className="primary" disabled={save.isPending} onClick={() => save.mutate()}>Salva</button>
        <button onClick={() => test.mutate()} disabled={test.isPending}>Invia mail di prova</button>
      </div>
    </Card>
  );
}

function Simple({ path, cols }: { path: string; cols: [string, string][] }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: [path], queryFn: () => get<any[]>(`/${path}`) });
  const [edit, setEdit] = useState<any | null>(null);
  const save = useMutation({
    mutationFn: (o: any) => (o.id ? put(`/${path}/${o.id}`, o) : post(`/${path}`, o)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [path] }); setEdit(null); },
  });
  return (
    <Card actions={<button className="primary" onClick={() => setEdit({ is_active: true })}>+ Aggiungi</button>}>
      <table>
        <thead><tr>{cols.map(([, l]) => <th key={l}>{l}</th>)}<th>Attivo</th><th /></tr></thead>
        <tbody>
          {list.data?.map((o) => (
            <tr key={o.id}>{cols.map(([k]) => <td key={k}>{o[k]}</td>)}<td>{o.is_active ? "Sì" : "No"}</td>
              <td><button onClick={() => setEdit(o)}>Modifica</button></td></tr>
          ))}
        </tbody>
      </table>
      {edit && (
        <div className="modal-bg" onClick={() => setEdit(null)}><div className="modal" onClick={(e) => e.stopPropagation()}>
          <h3>{edit.id ? "Modifica" : "Nuovo"}</h3>
          <div className="grid" style={{ margin: "14px 0" }}>
            {cols.map(([k, l]) => <Field key={k} label={l}><input value={edit[k] ?? ""} onChange={(e) => setEdit({ ...edit, [k]: e.target.value || null })} /></Field>)}
            <label className="row"><input type="checkbox" style={{ width: "auto" }} checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /> Attivo</label>
          </div>
          <ErrorBox e={save.error} />
          <div className="row"><button className="primary" onClick={() => save.mutate(edit)}>Salva</button><button onClick={() => setEdit(null)}>Annulla</button></div>
        </div></div>
      )}
    </Card>
  );
}

function MapTab() {
  const qc = useQueryClient();
  const maps = useQuery({ queryKey: ["map"], queryFn: () => get<MapRow[]>("/vendor-supplier-map") });
  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => get<Vendor[]>("/vendors") });
  const suppliers = useQuery({ queryKey: ["suppliers"], queryFn: () => get<Supplier[]>("/suppliers") });
  const [e, setE] = useState<any | null>(null);
  const save = useMutation({
    mutationFn: () => put("/vendor-supplier-map", { vendor_id: +e.vendor_id, supplier_id: +e.supplier_id, to_emails: emails(e.to), cc_emails: emails(e.cc ?? ""), supports_dr: e.supports_dr, is_preferred: e.is_preferred }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["map"] }); setE(null); },
  });
  const remove = useMutation({ mutationFn: (id: number) => del(`/vendor-supplier-map/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["map"] }) });
  const name = (list: { id: number; name: string }[] | undefined, id: number) => list?.find((x) => x.id === id)?.name ?? id;
  return (
    <Card actions={<button className="primary" onClick={() => setE({ to: "", cc: "", supports_dr: true, is_preferred: false, vendor_id: "", supplier_id: "" })}>+ Aggiungi mapping</button>}>
      <ErrorBox e={remove.error} />
      <table>
        <thead><tr><th>Vendor</th><th>Supplier</th><th>A (To)</th><th>CC</th><th>DR</th><th>Preferito</th><th /></tr></thead>
        <tbody>{maps.data?.map((m) => (
          <tr key={m.id}><td>{name(vendors.data, m.vendor_id)}</td><td>{name(suppliers.data, m.supplier_id)}</td>
            <td>{m.to_emails.join(", ")}</td><td>{m.cc_emails.join(", ")}</td><td>{m.supports_dr ? "Sì" : "No"}</td><td>{m.is_preferred ? "★" : ""}</td>
            <td className="row"><button onClick={() => setE({ ...m, to: m.to_emails.join(", "), cc: m.cc_emails.join(", ") })}>Modifica</button>
              <button className="danger" onClick={() => confirm("Eliminare il mapping?") && remove.mutate(m.id)}>Elimina</button></td></tr>
        ))}</tbody>
      </table>
      {e && (
        <div className="modal-bg" onClick={() => setE(null)}><div className="modal" onClick={(ev) => ev.stopPropagation()}>
          <h3>Mapping vendor ↔ supplier</h3>
          <div className="grid" style={{ margin: "14px 0" }}>
            <Field label="Vendor"><select value={e.vendor_id} disabled={!!e.id} onChange={(x) => setE({ ...e, vendor_id: x.target.value })}><option value="">—</option>{vendors.data?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></Field>
            <Field label="Supplier"><select value={e.supplier_id} disabled={!!e.id} onChange={(x) => setE({ ...e, supplier_id: x.target.value })}><option value="">—</option>{suppliers.data?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></Field>
            <Field label="Destinatari (To), separati da virgola"><input value={e.to} onChange={(x) => setE({ ...e, to: x.target.value })} /></Field>
            <Field label="CC specifici del mapping"><input value={e.cc} onChange={(x) => setE({ ...e, cc: x.target.value })} /></Field>
            <label className="row"><input type="checkbox" style={{ width: "auto" }} checked={e.supports_dr} onChange={(x) => setE({ ...e, supports_dr: x.target.checked })} /> Gestisce Deal Registration</label>
            <label className="row"><input type="checkbox" style={{ width: "auto" }} checked={e.is_preferred} onChange={(x) => setE({ ...e, is_preferred: x.target.checked })} /> Supplier preferito per il vendor</label>
          </div>
          <ErrorBox e={save.error} />
          <div className="row"><button className="primary" onClick={() => save.mutate()}>Salva</button><button onClick={() => setE(null)}>Annulla</button></div>
        </div></div>
      )}
    </Card>
  );
}

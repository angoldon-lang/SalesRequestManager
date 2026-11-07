import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { get, qs } from "../api";
import { Badge, Card, TypeTag, fmtDate, money } from "../components";
import type { Req, Vendor } from "../types";

export default function Requests() {
  const nav = useNavigate();
  const [f, setF] = useState({ q: "", status: "", type: "", vendor_id: "", from: "", to: "" });
  const [page, setPage] = useState(0);
  const size = 25;
  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => get<Vendor[]>("/vendors") });
  const list = useQuery({
    queryKey: ["requests", f, page],
    queryFn: () => get<{ items: Req[]; total: number }>(`/requests${qs({ ...f, limit: size, offset: page * size })}`),
  });
  const set = (k: string, v: string) => { setPage(0); setF({ ...f, [k]: v }); };

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Richieste</h2>
        <Link className="btn primary" to="/requests/new">+ Nuova richiesta</Link>
      </div>
      <Card>
        <div className="row filters" style={{ marginBottom: 12 }}>
          <input placeholder="Cerca codice, oggetto, cliente…" value={f.q} onChange={(e) => set("q", e.target.value)} />
          <select value={f.status} onChange={(e) => set("status", e.target.value)}>
            <option value="">Tutti gli stati</option>
            <option value="DRAFT">Bozza</option><option value="SENT">Inviata</option>
            <option value="REMINDED">Sollecitata</option><option value="CLOSED">Chiusa</option>
          </select>
          <select value={f.type} onChange={(e) => set("type", e.target.value)}>
            <option value="">Nuovo + DR</option><option value="NUOVO">Nuovo</option><option value="DR">DR</option>
          </select>
          <select value={f.vendor_id} onChange={(e) => set("vendor_id", e.target.value)}>
            <option value="">Tutti i vendor</option>
            {vendors.data?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
          <input type="date" value={f.from} onChange={(e) => set("from", e.target.value)} title="Dal" />
          <input type="date" value={f.to} onChange={(e) => set("to", e.target.value)} title="Al" />
        </div>
        <table>
          <thead><tr><th>Codice</th><th>Tipo</th><th>Oggetto</th><th>Vendor / Supplier</th><th>Cliente</th><th>Valore</th><th>Stato</th><th>Inviata</th></tr></thead>
          <tbody>
            {list.data?.items.map((r) => (
              <tr key={r.id} className="click" onClick={() => nav(`/requests/${r.id}`)}>
                <td>{r.code}</td><td><TypeTag t={r.request_type} /></td>
                <td>{r.subject}{r.needs_review && <span className="review">da rivedere</span>}</td>
                <td>{r.vendor_name ?? "—"}<br /><small className="muted">{r.supplier_name ?? ""}</small></td>
                <td>{r.end_customer_name ?? "—"}</td><td>{money(r.estimated_deal_value, r.currency)}</td>
                <td><Badge r={r} />{r.reminder_count > 0 && <small className="muted"> ×{r.reminder_count}</small>}</td>
                <td>{fmtDate(r.sent_at)}</td>
              </tr>
            ))}
            {list.data?.items.length === 0 && <tr><td colSpan={8} className="muted">Nessuna richiesta.</td></tr>}
          </tbody>
        </table>
        <div className="row" style={{ marginTop: 12, justifyContent: "space-between" }}>
          <span className="muted">{list.data?.total ?? 0} risultati</span>
          <div className="row">
            <button disabled={page === 0} onClick={() => setPage(page - 1)}>←</button>
            <button disabled={(page + 1) * size >= (list.data?.total ?? 0)} onClick={() => setPage(page + 1)}>→</button>
          </div>
        </div>
      </Card>
    </>
  );
}

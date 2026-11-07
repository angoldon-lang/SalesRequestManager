import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "../api";
import { Badge, Card, ErrorBox, TypeTag, fmtDateTime } from "../components";
import type { Inbound, Req } from "../types";

const LABEL: Record<string, string> = { NEW: "Nuova", PARSED: "Elaborata", NEEDS_REVIEW: "Da rivedere", ERROR: "Errore", IGNORED: "Ignorata" };

export default function InboundReview() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("NEEDS_REVIEW");
  const [open, setOpen] = useState<number | null>(null);
  const inbound = useQuery({ queryKey: ["inbound", status], queryFn: () => get<Inbound[]>(`/inbound?status=${status}`) });
  const drafts = useQuery({ queryKey: ["requests", "review"], queryFn: () => get<{ items: Req[] }>("/requests?status=DRAFT&needs_review=true") });
  const done = () => { qc.invalidateQueries({ queryKey: ["inbound"] }); qc.invalidateQueries({ queryKey: ["requests"] }); };
  const reprocess = useMutation({ mutationFn: (id: number) => post(`/inbound/${id}/reprocess`), onSuccess: done });
  const ignore = useMutation({ mutationFn: (id: number) => post(`/inbound/${id}/ignore`), onSuccess: done });

  return (
    <>
      <h2>Bozze da email (AI)</h2>
      <Card title={`Bozze da rivedere (${drafts.data?.items.length ?? 0})`}>
        <table>
          <thead><tr><th>Codice</th><th>Tipo</th><th>Oggetto</th><th>Vendor</th><th>Confidenza</th><th /></tr></thead>
          <tbody>
            {drafts.data?.items.map((r) => (
              <tr key={r.id}><td>{r.code}</td><td><TypeTag t={r.request_type} /></td><td>{r.subject}</td><td>{r.vendor_name ?? "—"}</td>
                <td>{r.ai_confidence}</td><td><Link className="btn" to={`/requests/${r.id}/edit`}>Rivedi</Link></td></tr>
            ))}
            {drafts.data?.items.length === 0 && <tr><td colSpan={6} className="muted">Nessuna bozza da rivedere.</td></tr>}
          </tbody>
        </table>
      </Card>
      <Card title="Email ricevute" actions={
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: "auto" }}>
          {Object.entries(LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>}>
        <ErrorBox e={reprocess.error ?? ignore.error} />
        <table>
          <thead><tr><th>Ricevuta</th><th>Da</th><th>Oggetto</th><th>Stato</th><th /></tr></thead>
          <tbody>
            {inbound.data?.map((m) => (
              <>
                <tr key={m.id}>
                  <td>{fmtDateTime(m.received_at)}</td><td>{m.from_email}</td><td>{m.subject}</td>
                  <td><span className="badge draft">{LABEL[m.status]}</span></td>
                  <td className="row">
                    <button onClick={() => setOpen(open === m.id ? null : m.id)}>Dettagli</button>
                    {(m.status === "ERROR" || m.status === "IGNORED") && <button onClick={() => reprocess.mutate(m.id)}>Rielabora</button>}
                    {m.status !== "IGNORED" && <button className="danger" onClick={() => ignore.mutate(m.id)}>Ignora</button>}
                  </td>
                </tr>
                {open === m.id && (
                  <tr key={`${m.id}d`}><td colSpan={5}>
                    {m.error_message && <div className="alert">{m.error_message}</div>}
                    <b>Testo email</b><pre style={{ whiteSpace: "pre-wrap" }}>{m.body_text}</pre>
                    {m.llm_raw_output && <><b>Output LLM</b><pre>{JSON.stringify(m.llm_raw_output, null, 2)}</pre></>}
                  </td></tr>
                )}
              </>
            ))}
            {inbound.data?.length === 0 && <tr><td colSpan={5} className="muted">Nessuna email.</td></tr>}
          </tbody>
        </table>
      </Card>
    </>
  );
}

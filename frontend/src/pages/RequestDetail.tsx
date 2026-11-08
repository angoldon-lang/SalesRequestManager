import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { del, get, post } from "../api";
import { Badge, Card, ErrorBox, Field, TypeTag, fmtDate, fmtDateTime, money } from "../components";
import { CloseReason, EventRow, REASON_LABEL, Req } from "../types";

export default function RequestDetail() {
  const id = useParams().id!;
  const nav = useNavigate();
  const qc = useQueryClient();
  const [closing, setClosing] = useState(false);
  const r = useQuery({ queryKey: ["request", id], queryFn: () => get<Req>(`/requests/${id}`) });
  const ev = useQuery({ queryKey: ["events", id], queryFn: () => get<EventRow[]>(`/requests/${id}/events`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["request", id] }); qc.invalidateQueries({ queryKey: ["events", id] }); qc.invalidateQueries({ queryKey: ["requests"] }); };
  const act = useMutation({ mutationFn: (p: [string, any?]) => post(`/requests/${id}/${p[0]}`, p[1]), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => del(`/requests/${id}`), onSuccess: () => { refresh(); nav("/requests"); } });

  const x = r.data;
  if (!x) return <ErrorBox e={r.error} />;
  const open = x.status === "SENT" || x.status === "REMINDED";

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>{x.code} <TypeTag t={x.request_type} /> <Badge r={x} /></h2>
        <div className="row">
          {x.status === "DRAFT" && <>
            <Link className="btn" to={`/requests/${x.id}/edit`}>Modifica</Link>
            <button className="primary" disabled={act.isPending} onClick={() => act.mutate(["send"])}>Invia</button>
            <button className="danger" onClick={() => confirm("Eliminare la bozza?") && remove.mutate()}>Elimina</button>
          </>}
          {open && <>
            <Link className="btn" to={`/requests/${x.id}/edit`}>Aggiorna dati DR</Link>
            <button disabled={act.isPending} onClick={() => confirm("Inviare un sollecito ora?") && act.mutate(["remind"])}>Sollecita ora</button>
            <button className="primary" onClick={() => setClosing(true)}>Chiudi</button>
          </>}
          {x.status === "CLOSED" && <button onClick={() => act.mutate(["reopen"])}>Riapri</button>}
        </div>
      </div>
      <ErrorBox e={act.error ?? remove.error} />
      {x.needs_review && <div className="alert">Bozza creata dall'AI da rivedere (confidenza {x.ai_confidence}).</div>}
      {x.status === "REMINDED" && !x.first_vendor_reply_at && <div className="ok">Sollecito {x.reminder_count} inviato il {fmtDateTime(x.last_reminder_at)}.</div>}
      {x.first_vendor_reply_at && open && <div className="ok">Il vendor ha risposto il {fmtDateTime(x.first_vendor_reply_at)}: chiudi la richiesta quando è conclusa.</div>}

      <div className="grid g2">
        <Card title="Dettagli">
          <dl>
            <dt>Oggetto</dt><dd>{x.subject}</dd>
            <dt>Vendor</dt><dd>{x.vendor_name ?? "—"}</dd>
            <dt>Supplier</dt><dd>{x.supplier_name ?? "—"}</dd>
            <dt>Agente (CC)</dt><dd>{x.agent_name ?? "—"}</dd>
            <dt>Prodotti</dt><dd>{x.product_description ?? "—"}{x.quantity ? ` × ${x.quantity}` : ""}</dd>
            <dt>Origine</dt><dd>{x.source === "EMAIL_AI" ? "Email (AI)" : "Manuale"}</dd>
          </dl>
          {x.body && <p style={{ whiteSpace: "pre-wrap" }}>{x.body}</p>}
        </Card>
        <Card title="Tracking">
          <dl>
            <dt>Creata</dt><dd>{fmtDateTime(x.created_at)}</dd>
            <dt>Inviata</dt><dd>{fmtDateTime(x.sent_at)}</dd>
            <dt>Solleciti</dt><dd>{x.reminder_count}</dd>
            <dt>Prima risposta</dt><dd>{fmtDateTime(x.first_vendor_reply_at)}</dd>
            <dt>Chiusa</dt><dd>{fmtDateTime(x.closed_at)}</dd>
          </dl>
        </Card>
        {x.request_type === "DR" && (
          <Card title="Deal Registration">
            <dl>
              <dt>Cliente finale</dt><dd>{x.end_customer_name ?? "—"}</dd>
              <dt>Valore stimato</dt><dd>{money(x.estimated_deal_value, x.currency)}</dd>
              <dt>Chiusura prevista</dt><dd>{fmtDate(x.expected_close_date)}</dd>
              <dt>Codice DR vendor</dt><dd>{x.vendor_dr_reference ?? "—"}</dd>
              <dt>Approvata il</dt><dd>{fmtDate(x.dr_approved_at)}</dd>
              <dt>Scade il</dt><dd>{fmtDate(x.dr_expires_at)}</dd>
            </dl>
          </Card>
        )}
        <Card title="Storico">
          <table><tbody>
            {ev.data?.map((e) => (
              <tr key={e.id}><td>{fmtDateTime(e.created_at)}</td><td><b>{e.event_type}</b></td><td className="muted">{e.actor}</td></tr>
            ))}
          </tbody></table>
        </Card>
      </div>
      {closing && <CloseDialog req={x} onClose={() => setClosing(false)} onDone={() => { setClosing(false); refresh(); }} />}
    </>
  );
}

function CloseDialog({ req, onClose, onDone }: { req: Req; onClose: () => void; onDone: () => void }) {
  const reasons: CloseReason[] = req.request_type === "DR" ? ["APPROVED", "REJECTED", "CANCELLED", "NO_RESPONSE"] : ["WON", "LOST", "CANCELLED", "NO_RESPONSE"];
  const [v, setV] = useState({ reason: reasons[0], vendor_dr_reference: "", dr_approved_at: "", dr_expires_at: "" });
  const m = useMutation({
    mutationFn: () => post(`/requests/${req.id}/close`, {
      reason: v.reason, vendor_dr_reference: v.vendor_dr_reference || undefined,
      dr_approved_at: v.dr_approved_at || undefined, dr_expires_at: v.dr_expires_at || undefined,
    }),
    onSuccess: onDone,
  });
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Chiudi {req.code}</h3>
        <div className="grid" style={{ margin: "14px 0" }}>
          <Field label="Esito">
            <select value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value as CloseReason })}>
              {reasons.map((r) => <option key={r} value={r}>{REASON_LABEL[r]}</option>)}
            </select>
          </Field>
          {req.request_type === "DR" && v.reason === "APPROVED" && <>
            <Field label="Codice DR assegnato dal vendor"><input value={v.vendor_dr_reference} onChange={(e) => setV({ ...v, vendor_dr_reference: e.target.value })} /></Field>
            <Field label="Approvata il"><input type="date" value={v.dr_approved_at} onChange={(e) => setV({ ...v, dr_approved_at: e.target.value })} /></Field>
            <Field label="Scade il"><input type="date" value={v.dr_expires_at} onChange={(e) => setV({ ...v, dr_expires_at: e.target.value })} /></Field>
          </>}
        </div>
        <ErrorBox e={m.error} />
        <div className="row"><button className="primary" disabled={m.isPending} onClick={() => m.mutate()}>Conferma chiusura</button><button onClick={onClose}>Annulla</button></div>
      </div>
    </div>
  );
}

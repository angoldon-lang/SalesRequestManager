import { ReactNode } from "react";
import { REASON_LABEL, Req, STATUS_LABEL } from "./types";

export const Badge = ({ r }: { r: Pick<Req, "status" | "close_reason"> }) => (
  <span className={`badge ${r.status.toLowerCase()}`}>
    {STATUS_LABEL[r.status]}{r.close_reason ? ` · ${REASON_LABEL[r.close_reason]}` : ""}
  </span>
);
export const TypeTag = ({ t }: { t: string }) => <span className={`tag ${t.toLowerCase()}`}>{t === "DR" ? "DR" : "Nuovo"}</span>;

export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleDateString("it-IT") : "—");
export const fmtDateTime = (s?: string | null) => (s ? new Date(s).toLocaleString("it-IT") : "—");
export const money = (v?: string | null, cur = "EUR") =>
  v ? Number(v).toLocaleString("it-IT", { style: "currency", currency: cur }) : "—";

export function Field({ label, error, required, children }: { label: string; error?: string; required?: boolean; children: ReactNode }) {
  return (
    <label className={`field ${error ? "has-error" : ""}`}>
      <span>{label}{required && <em className="req" title="Obbligatorio"> *</em>}</span>
      {children}
      {error && <small className="err" role="alert">{error}</small>}
    </label>
  );
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && <header><h3>{title}</h3><div>{actions}</div></header>}
      {children}
    </section>
  );
}

export const ErrorBox = ({ e }: { e: unknown }) => (e ? <div className="alert">{(e as Error).message}</div> : null);

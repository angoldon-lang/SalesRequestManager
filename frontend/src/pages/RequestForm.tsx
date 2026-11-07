import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiError, get, patch, post } from "../api";
import { Card, ErrorBox, Field } from "../components";
import type { Agent, MapRow, Req, Supplier, Vendor } from "../types";

const num = (v: unknown) => (v === "" || v === null || v === undefined ? undefined : Number(String(v).replace(",", ".")));
const opt = (v: unknown) => (v === "" ? undefined : v);

const base = z.object({
  vendor_id: z.coerce.number({ invalid_type_error: "Seleziona un vendor" }).int().positive("Seleziona un vendor"),
  supplier_id: z.coerce.number({ invalid_type_error: "Seleziona un supplier" }).int().positive("Seleziona un supplier"),
  sales_agent_id: z.coerce.number({ invalid_type_error: "Seleziona un agente" }).int().positive("Seleziona un agente"),
  subject: z.string().trim().min(3, "Almeno 3 caratteri"),
  body: z.string().optional(),
  product_description: z.string().optional(),
  quantity: z.preprocess(num, z.number().int().positive("Deve essere > 0").optional()),
});

/** Schema completo (invio): i campi DR diventano obbligatori solo se request_type = DR. */
export const sendSchema = z.discriminatedUnion("request_type", [
  base.extend({ request_type: z.literal("NUOVO") }),
  base.extend({
    request_type: z.literal("DR"),
    end_customer_name: z.string({ required_error: "Obbligatorio" }).trim().min(2, "Obbligatorio"),
    estimated_deal_value: z.preprocess(num, z.number({ required_error: "Obbligatorio", invalid_type_error: "Obbligatorio" }).positive("Deve essere > 0")),
    expected_close_date: z.preprocess(opt, z.string({ required_error: "Obbligatorio" }).min(1, "Obbligatorio")),
  }),
]);

type FormVals = Record<string, any>;
const EMPTY: FormVals = { request_type: "NUOVO", currency: "EUR" };

export default function RequestForm() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [serverErr, setServerErr] = useState<ApiError | null>(null);

  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => get<Vendor[]>("/vendors?active_only=true") });
  const suppliers = useQuery({ queryKey: ["suppliers"], queryFn: () => get<Supplier[]>("/suppliers?active_only=true") });
  const agents = useQuery({ queryKey: ["agents"], queryFn: () => get<Agent[]>("/agents?active_only=true") });
  const maps = useQuery({ queryKey: ["map"], queryFn: () => get<MapRow[]>("/vendor-supplier-map") });
  const existing = useQuery({ queryKey: ["request", id], enabled: !!id, queryFn: () => get<Req>(`/requests/${id}`) });

  const { register, handleSubmit, watch, reset, getValues, setValue, setError, trigger, formState: { errors } } =
    useForm<FormVals>({ defaultValues: EMPTY, resolver: zodResolver(sendSchema) as any, shouldUnregister: false });

  useEffect(() => {
    if (existing.data) reset({ ...EMPTY, ...Object.fromEntries(Object.entries(existing.data).map(([k, v]) => [k, v ?? ""])) });
  }, [existing.data, reset]);

  const type = watch("request_type");
  const vendorId = Number(watch("vendor_id")) || 0;
  const isDR = type === "DR";
  const mappedSuppliers = maps.data?.filter((m) => m.vendor_id === vendorId) ?? [];
  const supplierOptions = vendorId
    ? (suppliers.data ?? []).filter((s) => mappedSuppliers.some((m) => m.supplier_id === s.id))
    : [];

  // Quando cambia il vendor preseleziona il supplier preferito
  useEffect(() => {
    if (!vendorId || id) return;
    const pref = mappedSuppliers.find((m) => m.is_preferred) ?? mappedSuppliers[0];
    if (pref) setValue("supplier_id", pref.supplier_id);
  }, [vendorId]); // eslint-disable-line react-hooks/exhaustive-deps

  const clean = (v: FormVals) => {
    const out: FormVals = {};
    for (const k of ["request_type", "vendor_id", "supplier_id", "sales_agent_id", "subject", "body", "product_description",
      "quantity", "end_customer_name", "estimated_deal_value", "currency", "expected_close_date"]) {
      const x = v[k];
      if (x === "" || x === undefined || x === null || Number.isNaN(x)) continue;
      out[k] = ["vendor_id", "supplier_id", "sales_agent_id", "quantity"].includes(k) ? Number(x)
        : k === "estimated_deal_value" ? String(x).replace(",", ".") : x;
    }
    return out;
  };

  const save = useMutation({
    mutationFn: async (send: boolean) => {
      const payload = clean(getValues());
      const saved = id ? await patch<Req>(`/requests/${id}`, payload) : await post<Req>("/requests", payload);
      if (send) await post(`/requests/${saved.id}/send`);
      return { saved, send };
    },
    onSuccess: ({ saved }) => { qc.invalidateQueries({ queryKey: ["requests"] }); nav(`/requests/${saved.id}`); },
    onError: (e) => {
      const err = e as ApiError;
      setServerErr(err);
      Object.entries(err.fields).forEach(([f, m]) => setError(f, { message: m }));
    },
  });

  const onSaveDraft = async () => {
    setServerErr(null);
    // la bozza richiede solo tipo e oggetto
    const ok = await trigger("subject");
    if (!ok) return;
    save.mutate(false);
  };
  const onSend = handleSubmit(() => { setServerErr(null); save.mutate(true); });

  const locked = existing.data && existing.data.status !== "DRAFT";
  const err = (k: string) => errors[k]?.message as string | undefined;

  return (
    <>
      <h2>{id ? `Modifica ${existing.data?.code ?? ""}` : "Nuova richiesta"}</h2>
      {locked && <div className="alert">La richiesta è già stata inviata e non è più modificabile.</div>}
      {existing.data?.needs_review && <div className="alert">Bozza creata dall'AI (confidenza {existing.data.ai_confidence}): controlla i dati prima di inviare.</div>}
      <ErrorBox e={serverErr} />
      <form onSubmit={onSend}>
        <Card>
          <fieldset disabled={!!locked} style={{ border: 0, padding: 0, margin: 0 }}>
            <div className="form">
              <Field label="Tipo richiesta" required>
                <select {...register("request_type")} aria-label="Tipo richiesta">
                  <option value="NUOVO">Nuovo</option>
                  <option value="DR">Richiesta DR (Deal Registration)</option>
                </select>
              </Field>
              <Field label="Agente commerciale (in CC)" required error={err("sales_agent_id")}>
                <select {...register("sales_agent_id")}>
                  <option value="">—</option>
                  {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.full_name}</option>)}
                </select>
              </Field>
              <Field label="Vendor" required error={err("vendor_id")}>
                <select {...register("vendor_id")}>
                  <option value="">—</option>
                  {vendors.data?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
              </Field>
              <Field label="Supplier" required error={err("supplier_id")}>
                <select {...register("supplier_id")} disabled={!vendorId}>
                  <option value="">{vendorId ? "—" : "Scegli prima il vendor"}</option>
                  {supplierOptions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>
              <div className="full"><Field label="Oggetto" required error={err("subject")}><input {...register("subject")} /></Field></div>

              {isDR && (
                <div className="dr-box" data-testid="dr-box">
                  <h4>Dati Deal Registration (obbligatori)</h4>
                  <Field label="Cliente finale" required error={err("end_customer_name")}>
                    <input {...register("end_customer_name")} />
                  </Field>
                  <Field label="Valore stimato del deal" required error={err("estimated_deal_value")}>
                    <div className="row" style={{ flexWrap: "nowrap" }}>
                      <input inputMode="decimal" {...register("estimated_deal_value")} />
                      <select {...register("currency")} style={{ width: 90 }}>
                        <option>EUR</option><option>USD</option><option>GBP</option><option>CHF</option>
                      </select>
                    </div>
                  </Field>
                  <Field label="Chiusura prevista" required error={err("expected_close_date")}>
                    <input type="date" {...register("expected_close_date")} />
                  </Field>
                </div>
              )}

              <div className="full"><Field label="Testo della richiesta" error={err("body")}><textarea {...register("body")} /></Field></div>
              <Field label="Prodotti / servizi" error={err("product_description")}><input {...register("product_description")} /></Field>
              <Field label="Quantità" error={err("quantity")}><input inputMode="numeric" {...register("quantity")} /></Field>
            </div>
          </fieldset>
        </Card>
        {!locked && (
          <div className="row">
            <button type="button" onClick={onSaveDraft} disabled={save.isPending}>Salva bozza</button>
            <button className="primary" type="submit" disabled={save.isPending}>Invia al supplier</button>
            <button type="button" onClick={() => nav(-1)}>Annulla</button>
          </div>
        )}
      </form>
    </>
  );
}

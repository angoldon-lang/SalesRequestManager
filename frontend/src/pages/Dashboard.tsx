import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, qs } from "../api";
import { Card, fmtDate } from "../components";

const C = { nuovo: "#2a9d8f", dr: "#7c4dff", open: "#f4a261", closed: "#1a7f4b", bar: "#3b6cff" };
const days = (n: number) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);

export default function Dashboard() {
  const [from, setFrom] = useState(days(90));
  const [to, setTo] = useState(days(0));
  const p = qs({ from, to });
  const sum = useQuery({ queryKey: ["dash", "sum", p], queryFn: () => get(`/dashboard/summary${p}`) });
  const ts = useQuery({ queryKey: ["dash", "ts", p], queryFn: () => get<any[]>(`/dashboard/timeseries${p}&granularity=week`) });
  const vend = useQuery({ queryKey: ["dash", "v", p], queryFn: () => get<any[]>(`/dashboard/vendors${p}`) });
  const esc = useQuery({ queryKey: ["dash", "esc"], queryFn: () => get<any[]>("/dashboard/escalations") });
  const s = sum.data;

  const kpi = (label: string, value: any, sub?: string) => (
    <Card><div className="kpi"><small>{label}</small><b>{value ?? "—"}</b>{sub && <small>{sub}</small>}</div></Card>
  );

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Dashboard</h2>
        <div className="row filters">
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
      </div>
      {s && <>
        <div className="grid g4">
          {kpi("Richieste inviate", s.totale, `${s.bozze} bozze (${s.bozze_da_rivedere} da rivedere)`)}
          {kpi("Nuovo vs DR", `${s.pct_nuovo}% / ${s.pct_dr}%`, `${s.nuovo} nuovo · ${s.dr} DR`)}
          {kpi("Aperte / Chiuse", `${s.aperte} / ${s.chiuse}`, `${s.pct_chiuse}% chiuse`)}
          {kpi("Risposta media vendor", s.ore_risposta_media != null ? `${s.ore_risposta_media} h` : "—", s.ore_risposta_media != null ? `≈ ${(s.ore_risposta_media / 24).toFixed(1)} giorni` : "nessuna risposta")}
        </div>
        <div className="grid g2">
          <Card title="Nuovo vs DR">
            <ResponsiveContainer height={230}><PieChart>
              <Pie dataKey="v" nameKey="n" innerRadius={55} outerRadius={85} label data={[{ n: "Nuovo", v: s.nuovo }, { n: "DR", v: s.dr }]}>
                <Cell fill={C.nuovo} /><Cell fill={C.dr} />
              </Pie><Legend /><Tooltip />
            </PieChart></ResponsiveContainer>
          </Card>
          <Card title="Aperte vs Chiuse">
            <ResponsiveContainer height={230}><PieChart>
              <Pie dataKey="v" nameKey="n" innerRadius={55} outerRadius={85} label data={[{ n: "Aperte", v: s.aperte }, { n: "Chiuse", v: s.chiuse }]}>
                <Cell fill={C.open} /><Cell fill={C.closed} />
              </Pie><Legend /><Tooltip />
            </PieChart></ResponsiveContainer>
          </Card>
          <Card title="Volume settimanale">
            <ResponsiveContainer height={240}><LineChart data={ts.data}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis dataKey="period" tickFormatter={fmtDate} /><YAxis allowDecimals={false} />
              <Tooltip labelFormatter={fmtDate} /><Legend />
              <Line dataKey="nuovo" name="Nuovo" stroke={C.nuovo} strokeWidth={2} />
              <Line dataKey="dr" name="DR" stroke={C.dr} strokeWidth={2} />
            </LineChart></ResponsiveContainer>
          </Card>
          <Card title="Tempo medio di risposta per vendor (ore)">
            <ResponsiveContainer height={240}><BarChart data={vend.data?.filter((v) => v.ore_medie != null)} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis type="number" /><YAxis type="category" dataKey="name" width={90} />
              <Tooltip /><Bar dataKey="ore_medie" name="Ore medie" fill={C.bar} />
            </BarChart></ResponsiveContainer>
          </Card>
        </div>
        <Card title="Da escalare (solleciti esauriti, nessuna risposta)">
          <table><thead><tr><th>Codice</th><th>Oggetto</th><th>Vendor</th><th>Inviata</th><th>Solleciti</th></tr></thead>
            <tbody>
              {esc.data?.map((r) => <tr key={r.id}><td><Link to={`/requests/${r.id}`}>{r.code}</Link></td><td>{r.subject}</td><td>{r.vendor}</td><td>{fmtDate(r.sent_at)}</td><td>{r.reminder_count}</td></tr>)}
              {esc.data?.length === 0 && <tr><td colSpan={5} className="muted">Nulla da escalare.</td></tr>}
            </tbody></table>
        </Card>
      </>}
    </>
  );
}

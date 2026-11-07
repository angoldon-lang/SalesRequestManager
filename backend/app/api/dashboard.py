from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import current_user
from app.services.reminder_service import to_escalate

router = APIRouter(prefix="/dashboard", dependencies=[Depends(current_user)])


def _range(date_from: date | None, date_to: date | None):
    d_to = (date_to or date.today()) + timedelta(days=1)
    d_from = date_from or (d_to - timedelta(days=91))
    return {"f": d_from, "t": d_to}


@router.get("/summary")
def summary(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
            db: Session = Depends(get_db)):
    p = _range(date_from, date_to)
    k = db.execute(text("""
        SELECT count(*) FILTER (WHERE status <> 'DRAFT')                         AS totale,
               count(*) FILTER (WHERE status <> 'DRAFT' AND request_type='NUOVO') AS nuovo,
               count(*) FILTER (WHERE status <> 'DRAFT' AND request_type='DR')    AS dr,
               count(*) FILTER (WHERE status IN ('SENT','REMINDED'))              AS aperte,
               count(*) FILTER (WHERE status = 'CLOSED')                          AS chiuse,
               count(*) FILTER (WHERE status = 'DRAFT')                           AS bozze,
               count(*) FILTER (WHERE status = 'DRAFT' AND needs_review)          AS bozze_da_rivedere,
               avg(extract(epoch FROM first_vendor_reply_at - sent_at)/3600)      AS ore_risposta_media
        FROM requests WHERE created_at >= :f AND created_at < :t
    """), p).mappings().one()
    totale = k["totale"] or 0
    inviate = (k["aperte"] or 0) + (k["chiuse"] or 0)
    return {
        "totale": totale, "nuovo": k["nuovo"], "dr": k["dr"],
        "pct_dr": round(100 * k["dr"] / totale, 1) if totale else 0,
        "pct_nuovo": round(100 * k["nuovo"] / totale, 1) if totale else 0,
        "aperte": k["aperte"], "chiuse": k["chiuse"], "bozze": k["bozze"],
        "bozze_da_rivedere": k["bozze_da_rivedere"],
        "pct_chiuse": round(100 * k["chiuse"] / inviate, 1) if inviate else 0,
        "ore_risposta_media": round(float(k["ore_risposta_media"]), 1) if k["ore_risposta_media"] is not None else None,
        "range": {"from": p["f"].isoformat(), "to": (p["t"] - timedelta(days=1)).isoformat()},
    }


@router.get("/timeseries")
def timeseries(granularity: str = Query("week", pattern="^(day|week|month)$"),
               date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
               db: Session = Depends(get_db)):
    p = _range(date_from, date_to)
    rows = db.execute(text(f"""
        SELECT date_trunc('{granularity}', created_at)::date AS period,
               count(*) FILTER (WHERE request_type='NUOVO') AS nuovo,
               count(*) FILTER (WHERE request_type='DR')    AS dr
        FROM requests WHERE status <> 'DRAFT' AND created_at >= :f AND created_at < :t
        GROUP BY 1 ORDER BY 1"""), p).mappings().all()
    return [{"period": r["period"].isoformat(), "nuovo": r["nuovo"], "dr": r["dr"]} for r in rows]


@router.get("/vendors")
def vendors(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
            db: Session = Depends(get_db)):
    p = _range(date_from, date_to)
    rows = db.execute(text("""
        SELECT v.name, count(*) AS richieste,
               count(r.first_vendor_reply_at) AS risposte,
               round(avg(extract(epoch FROM r.first_vendor_reply_at - r.sent_at)/3600)::numeric, 1) AS ore_medie,
               round((percentile_cont(0.5) WITHIN GROUP
                     (ORDER BY extract(epoch FROM r.first_vendor_reply_at - r.sent_at)/3600))::numeric, 1) AS ore_mediana
        FROM requests r JOIN vendors v ON v.id = r.vendor_id
        WHERE r.status <> 'DRAFT' AND r.sent_at >= :f AND r.sent_at < :t
        GROUP BY v.name ORDER BY richieste DESC"""), p).mappings().all()
    return [{**r, "ore_medie": float(r["ore_medie"]) if r["ore_medie"] is not None else None,
             "ore_mediana": float(r["ore_mediana"]) if r["ore_mediana"] is not None else None} for r in rows]


@router.get("/escalations")
def escalations(db: Session = Depends(get_db)):
    return [{"id": r.id, "code": r.code, "subject": r.subject, "vendor": r.vendor.name if r.vendor else None,
             "sent_at": r.sent_at, "reminder_count": r.reminder_count} for r in to_escalate(db)]

from html import escape

from app.models import Request, RequestType


def _row(label: str, value) -> str:
    return (f"<tr><td style='padding:4px 12px 4px 0;color:#555'><b>{escape(label)}</b></td>"
            f"<td style='padding:4px 0'>{escape(str(value))}</td></tr>")


def render_request(req: Request, agent_name: str) -> str:
    rows = [_row("Codice richiesta", req.code)]
    if req.request_type == RequestType.DR:
        rows += [
            _row("Tipo", "Deal Registration"),
            _row("Cliente finale", req.end_customer_name),
            _row("Valore stimato", f"{req.estimated_deal_value:,.2f} {req.currency}"),
            _row("Chiusura prevista", req.expected_close_date.strftime("%d/%m/%Y")),
        ]
    else:
        rows.append(_row("Tipo", "Nuova richiesta"))
    if req.product_description:
        rows.append(_row("Prodotti / servizi", req.product_description))
    if req.quantity:
        rows.append(_row("Quantità", req.quantity))
    body = escape(req.body or "").replace("\n", "<br>")
    return (
        "<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px'>"
        "<p>Buongiorno,</p>"
        f"<p>{body}</p>"
        f"<table style='border-collapse:collapse'>{''.join(rows)}</table>"
        f"<p>Referente commerciale: {escape(agent_name)} (in copia).<br>"
        "Grazie per un cortese riscontro.</p></div>"
    )


def render_reminder(req: Request) -> str:
    sent = req.sent_at.strftime("%d/%m/%Y") if req.sent_at else ""
    return (
        "<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px'>"
        f"<p>Buongiorno, riprendiamo la richiesta <b>{escape(req.code)}</b> inviata il {sent}.<br>"
        "Potete darci un aggiornamento? Grazie.</p></div>"
    )

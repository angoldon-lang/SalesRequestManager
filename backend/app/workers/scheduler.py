"""Processo worker: polling inbound, tracking risposte, reminder."""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app.db import SessionLocal
from app.services.graph_client import get_graph
from app.services.inbound_service import poll_inbound
from app.services.llm_parser import get_parser
from app.services.reminder_service import run_reminders
from app.services.reply_tracker import track_replies

log = logging.getLogger("srm.worker")
graph = get_graph()


def _job(fn, *extra):
    def wrapper():
        with SessionLocal() as db:
            try:
                res = fn(db, graph, *extra)
                log.info("%s -> %s", fn.__name__, res)
            except Exception:
                db.rollback()
                log.exception("Job %s fallito", fn.__name__)
    wrapper.__name__ = fn.__name__
    return wrapper


def build_scheduler() -> BlockingScheduler:
    s = BlockingScheduler(timezone="Europe/Rome")
    kw = dict(max_instances=1, coalesce=True)
    s.add_job(_job(poll_inbound, get_parser()), "interval", minutes=2, **kw)
    s.add_job(_job(track_replies), "interval", minutes=10, **kw)
    # Reminder: solo giorni feriali, 09:00 e 15:00
    s.add_job(_job(run_reminders), "cron", day_of_week="mon-fri", hour="9,15", minute=0, **kw)
    return s


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_scheduler().start()

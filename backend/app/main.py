import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import config, dashboard, inbound, masterdata, me, requests
from app.config import settings

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Comodo in sviluppo; in produzione usare il servizio `worker` dedicato.
    if settings.run_workers_in_api:
        from app.workers.scheduler import build_scheduler
        threading.Thread(target=build_scheduler().start, daemon=True).start()
    yield


app = FastAPI(title="SalesRequestManager - SRM", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_methods=["*"], allow_headers=["*"])

for r in (me.router, requests.router, masterdata.router, config.router, inbound.router, dashboard.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}

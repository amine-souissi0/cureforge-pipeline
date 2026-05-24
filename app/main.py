import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from app.api.candidates import router as candidates_router, oauth_router
from app.api.templates import router as templates_router
from app.api.tasks import router as tasks_router
from app.api.evaluations import router as evaluations_router
from app.api.gate import router as gate_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.auth import require_api_key
from app.middleware.rate_limiter import RateLimiterMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import init_db
    await init_db()
    yield


app = FastAPI(
    title="CureForge Pipeline Agent",
    description="AI-powered recruiting pipeline — M9 Auth",
    version="0.9.0",
    lifespan=lifespan,
)

# Rate limiter: 600 req/min per IP (generous for normal use; blocks runaway automation)
app.add_middleware(RateLimiterMiddleware, limit=600, window_seconds=60)

_auth = [Depends(require_api_key)]

# Protected — require X-API-Key on every request
app.include_router(candidates_router, dependencies=_auth)
app.include_router(templates_router, dependencies=_auth)
app.include_router(tasks_router, dependencies=_auth)
app.include_router(evaluations_router, dependencies=_auth)
app.include_router(gate_router, dependencies=_auth)
app.include_router(dashboard_router, dependencies=_auth)

# Unprotected — health probes (Cloud Run) and OAuth redirect flow (browser)
app.include_router(health_router)
app.include_router(oauth_router)

# Founder UI — served at /ui (unprotected path; API calls from the UI use X-Api-Key)
_static = Path(__file__).parent / "static"
app.mount("/ui", StaticFiles(directory=str(_static), html=True), name="ui")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "milestone": "M8"}


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(str(_static / "index.html"))

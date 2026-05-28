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

from app.api.candidates import router as candidates_router, oauth_router, auth_google_router, webhook_router
from app.api.github_webhook import router as github_webhook_router
from app.api.templates import router as templates_router
from app.api.tasks import router as tasks_router
from app.api.evaluations import router as evaluations_router
from app.api.gate import router as gate_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.auth_router import router as auth_router
from app.auth import require_api_key
from app.middleware.rate_limiter import RateLimiterMiddleware


async def _seed_admin() -> None:
    """Create the default admin account on first boot if no users exist."""
    from app.auth import hash_password
    from app.services.user_store import UserStore
    if await UserStore.count() == 0:
        email = os.environ.get("ADMIN_EMAIL", "admin@cureforge.com")
        password = os.environ.get("ADMIN_PASSWORD", "admin123")
        await UserStore.create(
            email=email,
            name="Founder",
            hashed_password=hash_password(password),
            role="admin",
        )
        logging.getLogger(__name__).info(f"Seeded default admin: {email}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import init_db
    await init_db()
    await _seed_admin()
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

# Unprotected — login, health probes, OAuth redirect, Gmail Pub/Sub webhook, GitHub push webhook
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(oauth_router)
app.include_router(auth_google_router)
app.include_router(webhook_router)
app.include_router(github_webhook_router)

# Founder UI — served at /ui (unprotected path; API calls from the UI use X-Api-Key)
_static = Path(__file__).parent / "static"
app.mount("/ui", StaticFiles(directory=str(_static), html=True), name="ui")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "milestone": "M8"}


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(str(_static / "index.html"))

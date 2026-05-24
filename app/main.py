from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.candidates import router as candidates_router, oauth_router
from app.api.templates import router as templates_router
from app.api.tasks import router as tasks_router
from app.api.evaluations import router as evaluations_router
from app.api.gate import router as gate_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.middleware.rate_limiter import RateLimiterMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import init_db
    await init_db()
    yield


app = FastAPI(
    title="CureForge Pipeline Agent",
    description="AI-powered recruiting pipeline — M8 Hardening",
    version="0.8.0",
    lifespan=lifespan,
)

# Rate limiter: 600 req/min per IP (generous for normal use; blocks runaway automation)
app.add_middleware(RateLimiterMiddleware, limit=600, window_seconds=60)

app.include_router(candidates_router)
app.include_router(oauth_router)
app.include_router(templates_router)
app.include_router(tasks_router)
app.include_router(evaluations_router)
app.include_router(gate_router)
app.include_router(dashboard_router)
app.include_router(health_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "milestone": "M8"}

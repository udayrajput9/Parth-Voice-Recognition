"""
VoiceAuth — FastAPI Application Entry Point

Run:
    python main.py
    # or
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import uvicorn

from config import settings, BASE_DIR, UPLOADS_DIR
from database.db import init_db
from routers import auth, dashboard, voice

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    # Startup
    logger.info("Starting %s...", settings.APP_NAME)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "static" / "audio").mkdir(parents=True, exist_ok=True)
    init_db()
    logger.info("Database ready: %s", settings.DATABASE_URL)
    logger.info("App ready → http://127.0.0.1:8000")
    yield
    # Shutdown
    logger.info("%s shutting down", settings.APP_NAME)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="Voice-based biometric authentication — Speaker Verification with Anti-Spoofing",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(voice.router)


# ── Root redirect ─────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/auth/")


# ── Exception handler: redirect on 302 HTTPException ─────────────────────────
@app.exception_handler(302)
async def redirect_exception_handler(request: Request, exc):
    return RedirectResponse(url=exc.headers.get("Location", "/auth/signin"))


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )

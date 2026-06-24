import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.auth import router as auth_router
from api.documents import router as documents_router
from db.session import engine
from models.db.base import Base

# ── Explicit model imports so Base.metadata always has every table ────────────
# These must stay here. Base.metadata.create_all only creates tables for models
# that have been imported before the call. Relying on the router import chain
# to pull models in is fragile — an import order change silently drops a table.
from models.db.user import User          # noqa: F401
from models.db.document import Document  # noqa: F401

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (replaces deprecated @app.on_event) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created")
    yield
    # shutdown (nothing to clean up in MVP)


# ── App factory ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="AskMyDocs API",
    description="Production-grade RAG platform — MVP",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js dev server
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(documents_router)


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"], include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


# ── Global exception handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred"},
    )

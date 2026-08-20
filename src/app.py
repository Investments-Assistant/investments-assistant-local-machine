"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.agent.clients import create_llm_client
from src.agent.utils.logger import get_logger, setup_logging
from src.config import settings
from src.db.database import create_all_tables
from src.scheduler.jobs import setup_scheduler, shutdown_scheduler
from src.web.routes import STATIC_DIR, router

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────────
    logger.info(
        "Starting Investment Assistant (mode=%s, backend=llama_cpp, model=%s)",
        settings.trading_mode,
        settings.llm_model_path,
    )
    await create_all_tables()
    # Load the local GGUF model before accepting traffic. Model construction is
    # synchronous and large enough to block the event loop; doing it here on a
    # worker thread prevents the first WebSocket upgrade from racing model load.
    await asyncio.to_thread(create_llm_client)
    setup_scheduler()
    yield
    # ── Shutdown ───────────────────────────────────────────────────────────────
    shutdown_scheduler()
    logger.info("Investment Assistant shut down")


app = FastAPI(
    title="Investment Assistant",
    description="AI-powered investment agent with real-time market data and brokerage integrations",
    version="1.0.0",
    lifespan=lifespan,
    # Disable docs in production to reduce attack surface
    docs_url="/docs" if settings.is_development else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.is_development else None,
)

# Serve static files (CSS, JS)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include all routes
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.app:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )

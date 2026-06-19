from __future__ import annotations

from contextlib import asynccontextmanager

from arq import create_pool
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analyze import router as analyze_router
from app.api.cards import router as cards_router
from app.api.coach import router as coach_router
from app.api.dashboard import router as dashboard_router
from app.api.exercises import router as exercises_router
from app.api.explorer import router as explorer_router
from app.api.export import router as export_router
from app.api.health import router as health_router
from app.api.imports import router as imports_router
from app.api.jobs import router as jobs_router
from app.api.lichess import router as lichess_router
from app.api.mobile import router as mobile_router
from app.api.notify import router as notify_router
from app.api.ocr import router as ocr_router
from app.api.play import router as play_router
from app.api.progress import router as progress_router
from app.api.repertoire import router as repertoire_router
from app.api.similarity import router as similarity_router
from app.api.tablebase import router as tablebase_router
from app.api.trainer import router as trainer_router
from app.api.weaknesses import router as weaknesses_router
from app.api.weekly import router as weekly_router
from app.core.config import get_settings
from app.core.security import ApiKeyAuth
from app.services.stockfish import shutdown_engine
from app.worker.settings import _redis_settings


API_DESCRIPTION = """
Self-hosted chess-coach backend. The Chess.com username it targets is
configured via the `CHESSCOM_USERNAME` environment variable.

This API powers a Unity 3D client. Most endpoints require the
`X-API-Key` header (configured via `COACH_API_KEY` in `.env`).

### Modules
* **imports**     — pull games from Chess.com
* **analysis**    — Stockfish-driven move evaluation
* **weaknesses**  — pattern detection across played games
* **repertoire**  — opening tree + theory matching
* **trainer**     — SM-2 spaced repetition over repertoire nodes
* **exercises**   — puzzles built from your own blunders
* **coach**       — LLM (Ollama / Llama 3.1) move explanations
* **dashboard**   — single aggregated home-screen call

### Public endpoints (no key required)
`GET /health`, `GET /docs`, `GET /openapi.json`
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Arq pool for enqueueing jobs from request handlers
    try:
        app.state.arq = await create_pool(_redis_settings())
    except Exception:
        app.state.arq = None
    yield
    if app.state.arq is not None:
        await app.state.arq.aclose()
    await shutdown_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Coach Chess API",
        description=API_DESCRIPTION,
        version="0.1.0",
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    # CORS — Unity client may run on any localhost port during development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # /health stays unversioned and public (liveness probe + smoke test)
    app.include_router(health_router)

    # Everything else lives under /api/v1 and requires the API key
    v1 = APIRouter(prefix="/api/v1", dependencies=[ApiKeyAuth])
    v1.include_router(imports_router)
    v1.include_router(analyze_router)
    v1.include_router(weaknesses_router)
    v1.include_router(repertoire_router)
    v1.include_router(trainer_router)
    v1.include_router(coach_router)
    v1.include_router(exercises_router)
    v1.include_router(dashboard_router)
    v1.include_router(jobs_router)
    v1.include_router(play_router)
    v1.include_router(progress_router)
    v1.include_router(export_router)
    v1.include_router(explorer_router)
    v1.include_router(tablebase_router)
    v1.include_router(similarity_router)
    v1.include_router(lichess_router)
    v1.include_router(weekly_router)
    v1.include_router(mobile_router)
    v1.include_router(cards_router)
    v1.include_router(ocr_router)
    v1.include_router(notify_router)
    app.include_router(v1)

    return app


app = create_app()

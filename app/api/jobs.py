"""Async job enqueueing + status polling.

Each enqueue endpoint returns immediately with `{job_id, queued_at}`.
The client polls GET /jobs/{job_id} until status is 'complete' or 'failed'.

We keep the existing sync endpoints (e.g. POST /games/{id}/analyze) for
ad-hoc / testing use. Unity should always go through the async ones.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from arq import ArqRedis
from arq.jobs import Job, JobStatus
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["jobs"])


def _arq(request: Request) -> ArqRedis:
    pool: ArqRedis | None = getattr(request.app.state, "arq", None)
    if pool is None:
        raise HTTPException(503, "Worker queue not initialised")
    return pool


class EnqueueResponse(BaseModel):
    job_id: str
    queued_at: datetime
    function: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    function: str | None
    enqueue_time: datetime | None
    start_time: datetime | None
    finish_time: datetime | None
    result: Any | None
    success: bool | None


# ---------- Generic status endpoint ----------

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, request: Request) -> JobStatusResponse:
    pool = _arq(request)
    job = Job(job_id=job_id, redis=pool)
    status = await job.status()
    info = await job.info()
    result = None
    success: bool | None = None
    if status == JobStatus.complete:
        try:
            res = await job.result(timeout=0.1)
            result = res
            success = True
        except Exception as e:
            result = {"error": repr(e)}
            success = False
    return JobStatusResponse(
        job_id=job_id,
        status=str(status),
        function=getattr(info, "function", None) if info else None,
        enqueue_time=getattr(info, "enqueue_time", None) if info else None,
        start_time=getattr(info, "start_time", None) if info else None,
        finish_time=getattr(info, "finish_time", None) if info else None,
        result=result,
        success=success,
    )


# ---------- Enqueue helpers ----------

async def _enqueue(pool: ArqRedis, function: str, *args, **kwargs) -> EnqueueResponse:
    job = await pool.enqueue_job(function, *args, **kwargs)
    if job is None:
        raise HTTPException(409, "Job already exists or queue rejected")
    return EnqueueResponse(
        job_id=job.job_id,
        queued_at=datetime.utcnow(),
        function=function,
    )


# ---------- Enqueue endpoints (async variants) ----------

class AnalyzeGameAsyncIn(BaseModel):
    game_id: int
    depth: int | None = Field(None, ge=8, le=40)
    force: bool = False


@router.post("/async/games/analyze", response_model=EnqueueResponse)
async def enqueue_analyze_game(payload: AnalyzeGameAsyncIn, request: Request) -> EnqueueResponse:
    return await _enqueue(_arq(request), "analyze_game_task", payload.game_id, payload.depth, payload.force)


class AnalyzePendingAsyncIn(BaseModel):
    limit: int = Field(100, ge=1, le=1000)
    depth: int | None = Field(None, ge=8, le=40)
    since_rating: int | None = None


@router.post("/async/analyze/pending", response_model=EnqueueResponse)
async def enqueue_analyze_pending(payload: AnalyzePendingAsyncIn, request: Request) -> EnqueueResponse:
    return await _enqueue(
        _arq(request), "analyze_pending_task",
        payload.limit, payload.depth, payload.since_rating,
    )


class LiveDebriefAsyncIn(BaseModel):
    pgn: str
    my_color: str | None = None
    depth: int | None = None
    max_blunders: int = 5
    generate_puzzles: bool = True
    explain_with_llm: bool = True


@router.post("/async/coach/live_debrief", response_model=EnqueueResponse)
async def enqueue_live_debrief(payload: LiveDebriefAsyncIn, request: Request) -> EnqueueResponse:
    return await _enqueue(
        _arq(request), "live_debrief_task",
        payload.pgn, payload.my_color, payload.depth, payload.max_blunders,
        payload.generate_puzzles, payload.explain_with_llm,
    )


class ScoutAsyncIn(BaseModel):
    opponent_username: str
    max_months: int = 3
    max_games: int = 100
    generate_plan: bool = True


@router.post("/async/coach/scout", response_model=EnqueueResponse)
async def enqueue_scout(payload: ScoutAsyncIn, request: Request) -> EnqueueResponse:
    return await _enqueue(
        _arq(request), "scout_task",
        payload.opponent_username, payload.max_months, payload.max_games, payload.generate_plan,
    )


class ImportFullAsyncIn(BaseModel):
    username: str | None = None


@router.post("/async/import/chesscom/full", response_model=EnqueueResponse)
async def enqueue_import_full(payload: ImportFullAsyncIn, request: Request) -> EnqueueResponse:
    return await _enqueue(_arq(request), "import_full_task", payload.username)


@router.post("/async/repertoire/me/rebuild", response_model=EnqueueResponse)
async def enqueue_build_repertoire(request: Request) -> EnqueueResponse:
    return await _enqueue(_arq(request), "build_repertoire_task")


@router.post("/async/player/me/weaknesses/refresh", response_model=EnqueueResponse)
async def enqueue_refresh_weaknesses(request: Request) -> EnqueueResponse:
    return await _enqueue(_arq(request), "refresh_weaknesses_task")


class GenerateExercisesAsyncIn(BaseModel):
    min_cp_loss: int = 120


@router.post("/async/exercises/generate", response_model=EnqueueResponse)
async def enqueue_generate_exercises(payload: GenerateExercisesAsyncIn, request: Request) -> EnqueueResponse:
    return await _enqueue(_arq(request), "generate_exercises_task", payload.min_cp_loss)


class DeepAnalyzeAsyncIn(BaseModel):
    limit: int = Field(50, ge=1, le=500)
    depth: int = Field(28, ge=18, le=40)
    min_cp_loss: int = Field(150, ge=50)
    force: bool = False


@router.post("/async/analyze/deep/critical", response_model=EnqueueResponse)
async def enqueue_deep_analyze(payload: DeepAnalyzeAsyncIn, request: Request) -> EnqueueResponse:
    return await _enqueue(
        _arq(request), "deep_analyze_task",
        payload.limit, payload.depth, payload.min_cp_loss, payload.force,
    )


@router.post("/async/coach/me/progress/snapshot", response_model=EnqueueResponse)
async def enqueue_snapshot(request: Request) -> EnqueueResponse:
    return await _enqueue(_arq(request), "snapshot_progress_task")


class WatchLiveAsyncIn(BaseModel):
    depth: int = Field(14, ge=8, le=25)


@router.post("/async/coach/watch", response_model=EnqueueResponse)
async def enqueue_watch_live(payload: WatchLiveAsyncIn, request: Request) -> EnqueueResponse:
    """Trigger a manual watch tick now (in addition to the cron schedule)."""
    return await _enqueue(_arq(request), "watch_live_task", payload.depth)

"""Dev launcher that forces Windows ProactorEventLoop for the FastAPI worker.

Why this exists:
  - Stockfish needs `subprocess_exec`, which is only supported by
    ProactorEventLoop on Windows.
  - Uvicorn's default `asyncio` loop factory returns `SelectorEventLoop`
    whenever it thinks a subprocess context is active (e.g. with --reload),
    which crashes Stockfish with NotImplementedError.
  - Reload mode is therefore disabled here: it's incompatible with engine
    subprocesses on Windows.

Use this instead of `uvicorn app.main:app ...`:
    uv run python run_dev.py
"""
from __future__ import annotations

import asyncio
import sys


# Force the ProactorEventLoop policy at the process level *before* uvicorn
# touches anything.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
    except AttributeError:
        pass


def _patch_uvicorn_loop_factory() -> None:
    """Make uvicorn always return ProactorEventLoop on Windows, regardless
    of its `use_subprocess` heuristic."""
    if sys.platform != "win32":
        return
    try:
        import uvicorn.loops.asyncio as uvicorn_asyncio  # type: ignore
    except Exception:
        return

    def patched_factory(use_subprocess: bool = False):  # noqa: ARG001
        return asyncio.ProactorEventLoop  # type: ignore[attr-defined]

    uvicorn_asyncio.asyncio_loop_factory = patched_factory  # type: ignore[attr-defined]


_patch_uvicorn_loop_factory()


if __name__ == "__main__":
    import uvicorn

    print("=== coach_chess FastAPI on :8765 (ProactorEventLoop forced) ===")
    print("Reload disabled — Stockfish subprocess is incompatible with uvicorn's reload mode on Windows.")
    print("To reload after a code change : Ctrl+C and re-run this script.")
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        loop="asyncio",
    )

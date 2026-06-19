# coach_chess

Self-hosted personal chess coach backend. The Chess.com account it targets
is configured via the `CHESSCOM_USERNAME` environment variable.

Built as a complete, opinionated single-user pipeline: imports your
Chess.com games, analyzes them with Stockfish, detects fine-grained
tactical and positional weaknesses, builds a personalized lesson plan
every day, and provides interactive drill modes for openings, puzzles,
and play-from-position.

A Unity 6 frontend consumes this API:
**[jeremie0342/chess_coach](https://github.com/jeremie0342/chess_coach)**.
The API under `/api/v1` is the contract between the two repositories.

---

## Stack

| Layer | Tech |
|---|---|
| Language | Python 3.14 |
| Package manager | `uv` |
| Web | FastAPI + uvicorn |
| ORM | SQLAlchemy 2 + asyncpg + psycopg |
| Migrations | Alembic |
| Database | PostgreSQL 17 (`coach_chess`) |
| Queue | arq + Memurai (Redis-compat on Windows) |
| Chess engine | Stockfish 18 (vendored under `stockfish/`) |
| LLM coach | Ollama with Llama 3.1 8B (local) |
| Puzzles | Lichess 6M dump (`exercises` table) |
| Openings DB | Lichess + python-chess |
| Tablebases | Lichess API + optional local Syzygy |
| Tests | pytest + pytest-asyncio |

---

## One-time setup

```powershell
# Project deps
uv sync

# Create DB and run migrations
uv run python scripts/create_db.py
uv run alembic upgrade head

# Load opening theory + Lichess puzzles
uv run python scripts/load_openings.py
uv run python scripts/load_lichess_puzzles.py   # ~7 min, 6M rows

# Import your Chess.com games
uv run python scripts/import_games.py --full

# Build empirical repertoire + detect weaknesses
uv run python scripts/build_repertoire.py
uv run python scripts/detect_weaknesses.py

# Generate puzzles from your blunders
uv run python scripts/generate_exercises.py
```

---

## Daily usage

```powershell
# Launch everything (Postgres + Memurai assumed up via Windows services)
.\start.ps1

# Health check
uv run python scripts/coach_status.py

# Your training session for today (auto-composed plan)
uv run python scripts/today.py

# Drill repertoire (Anki-style SR)
uv run python scripts/train.py --color black --max 15

# Solve puzzles adapted to your ELO
uv run python scripts/solve.py --rating 464

# Drill a specific tactic theme
uv run python scripts/solve.py --theme fork --rating 464

# Play vs Stockfish from any position
uv run python scripts/play.py --color white --elo 1200
uv run python scripts/play.py --exercise 42 --color black   # play out from a puzzle

# Debrief a freshly-played game
uv run python scripts/debrief.py path/to/game.pgn

# Scout a chess.com opponent
uv run python scripts/scout.py SomeOpponentUsername

# Take a metric snapshot + view progress
uv run python scripts/progress.py --days 30

# Contextual blunder analysis
uv run python scripts/context.py

# Export annotated PGN for any past game
uv run python scripts/export_pgn.py --game-id 349 --output data/g349.pgn

# Tablebase probe (≤7 pieces, via Lichess API)
uv run python scripts/tb_probe.py "4k3/8/8/8/8/8/4K3/4R3 w - - 0 1"
```

---

## API endpoints (under `/api/v1`)

Authentication: `X-API-Key: <COACH_API_KEY from .env>` for every `/api/v1/*`.
`/health` and `/docs` are public.

### Coach
- `GET  /coach/me/dashboard` — aggregated home-screen feed
- `GET  /coach/me/today` — adaptive lesson plan
- `POST /coach/me/today/items/{id}/complete`
- `POST /coach/games/{id}/explain_move?ply=N`
- `POST /coach/games/{id}/review`
- `POST /coach/live_debrief` — paste PGN, get debrief
- `POST /coach/scout` — analyze a chess.com opponent

### Trainer (repertoire SR)
- `GET  /trainer/next?color=`
- `POST /trainer/answer`
- `GET  /trainer/stats`

### Exercises (puzzles SR)
- `GET  /exercises/next?source_kind=&theme=&rating=&rating_window=`
- `POST /exercises/answer`
- `POST /exercises/generate`

### Play vs Stockfish
- `POST /train/play/start`
- `POST /train/play/{id}/move`
- `POST /train/play/{id}/abandon`

### Analysis / weaknesses / progress
- `POST /games/{id}/analyze` · `POST /analyze/pending` · `POST /analyze/deep/critical`
- `POST /player/me/weaknesses/refresh` · `GET /player/me/weaknesses`
- `POST /coach/me/progress/snapshot` · `GET /coach/me/progress?days=30`
- `GET  /coach/me/contextual_patterns`
- `GET  /coach/me/elo_calibration`
- `GET  /coach/me/similar_positions?fen=`

### Openings
- `POST /repertoire/me/rebuild`
- `GET  /repertoire/me/top-lines?color=`
- `GET  /openings/match?fen=`
- `GET  /openings/explorer?fen=&db=masters|lichess`
- `POST /repertoire/me/annotate` (needs `LICHESS_TOKEN` if rate-limited)
- `GET  /repertoire/me/with_gm`
- `POST /games/{id}/out_of_book`

### Tablebase
- `GET  /tablebase/probe?fen=`
- `GET  /tablebase/status`

### Export
- `GET  /games/{id}/annotated.pgn`

### Async (enqueue + poll)
- `POST /async/<task>` → returns `{job_id}`
- `GET  /jobs/{job_id}` → returns status + result

---

## Architecture

```
app/
├── core/               # Settings, security (X-API-Key)
├── db/                 # Async engine, Base, sessions
├── models/             # SQLAlchemy ORM models
│   ├── player, game, move, analysis
│   ├── opening, repertoire, weakness, exercise
│   ├── daily_plan, position_session, metric_snapshot
├── services/           # Domain logic (no FastAPI dep)
│   ├── analyzer, deep_analyzer       # Stockfish wrappers
│   ├── stockfish, llm/ollama         # engine clients
│   ├── pgn_importer, import_orchestrator
│   ├── chesscom, lichess_explorer
│   ├── openings/                     # theory, oob, repertoire builder
│   ├── detectors/                    # weakness detectors (pluggable)
│   ├── tactical_themes               # missed_fork etc. classifier
│   ├── coach/                        # explainer, game_review, lesson_plan
│   ├── exercises/                    # generator, solver
│   ├── trainer/                      # SM-2 SRS
│   ├── scout/                        # opponent profiling
│   ├── live_debrief, live_watcher
│   ├── play_engine
│   ├── progress, elo_calibration, contextual_patterns
│   ├── position_similarity
│   ├── tablebase
│   ├── pgn_exporter
│   └── repertoire_annotator
├── api/                # FastAPI routers (one file per topic)
├── worker/             # arq worker — task wrappers + cron
└── main.py             # FastAPI app factory + lifespan + auth
```

Scripts (`scripts/`) are thin CLIs around services.

---

## Database schema highlights

- **`players`** (`is_me` flag for the current user)
- **`games`** → **`moves`** (FEN before/after each ply) → **`move_analyses`**
  (Stockfish eval, quality, tactical tags, deep re-analysis fields)
- **`openings`** = Lichess theory (~3.7k named positions)
- **`repertoire_nodes`** = empirical tree from your games + SR state + GM annotations
- **`weaknesses`** = aggregated detector findings per `(player_id, category, phase)`
- **`exercises`** = puzzles (6M Lichess + your own blunders) + per-puzzle SR state
- **`daily_plans`** + **`daily_plan_items`** = composed training sessions
- **`position_sessions`** + **`position_session_moves`** = your games vs SF
- **`metric_snapshots`** = nightly progress checkpoints

---

## Tests

```powershell
# Full suite
uv run pytest

# Skip slow tests (Stockfish / Ollama heavy)
uv run pytest -m "not slow"
```

Currently **59 tests** covering SM-2, quality classification, tactical themes,
PGN import idempotency, weakness engine (no duplicates), exercise picker,
lesson plan composer, and API auth/dashboard.

---

## Cron jobs (run by the arq worker)

- Every 5 min — `watch_live_task` polls Chess.com for new games and runs the full pipeline (import → analyze → puzzles → weakness refresh).
- 22:30 UTC daily — `refresh_weaknesses_task`.
- 23:00 UTC daily — `snapshot_progress_task`.

---

## .env reference

```
DATABASE_URL=postgresql+asyncpg://postgres:root@localhost:5432/coach_chess
DATABASE_URL_SYNC=postgresql+psycopg://postgres:root@localhost:5432/coach_chess
TEST_DATABASE_URL=...                # for pytest
STOCKFISH_PATH=stockfish/stockfish/stockfish-windows-x86-64-avx2.exe
STOCKFISH_THREADS=4
STOCKFISH_HASH_MB=512
STOCKFISH_DEFAULT_DEPTH=25
CHESSCOM_USERNAME=your_chesscom_username
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
COACH_API_KEY=your_local_api_key
COACH_CORS_ORIGINS=http://localhost,http://127.0.0.1,*
REDIS_URL=redis://127.0.0.1:6379/0
LICHESS_TOKEN=                       # optional, only if explorer 401s
```

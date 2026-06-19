# Contributing

Thanks for your interest. This is a self-hosted personal coaching tool. The
codebase is opinionated for a single user, but contributions that keep that
spirit are welcome.

## Ground rules

- Be respectful in issues and pull requests.
- Keep changes focused. One topic per pull request makes review tractable.
- Match the existing code style. The project uses standard Python conventions
  with `ruff` for linting and `pytest` for tests.
- Do not commit secrets, real API keys, real personal data, or large binaries.
- Do not commit your own `.env`; copy from `.env.example` instead.

## Reporting bugs

Open an issue with:

1. A clear description of what you observed and what you expected.
2. The Python version, the operating system, and how you launched the server.
3. A minimal reproduction. If a database state matters, describe the relevant
   rows and which detector or service you exercised.
4. Server logs and the failing HTTP response body, copied as text.

## Suggesting improvements

Open a discussion issue before sending a large pull request. The architecture
described in `README.md` (single Chess.com user, idempotent imports, services
under `app/services/`, thin routers under `app/api/`) is intentional;
proposals that depart from it will be evaluated against that direction.

## Setting up a dev environment

1. Install Python 3.13 or later.
2. Install [uv](https://github.com/astral-sh/uv).
3. Provision PostgreSQL and a Redis-compatible queue (Memurai on Windows works).
4. Provide a Stockfish binary at `stockfish/stockfish/`.
5. Copy `.env.example` to `.env` and fill in real values.
6. Run `uv sync` then `uv run alembic upgrade head` then `uv run uvicorn app.main:app --host 127.0.0.1 --port 8765`.

## Running tests

```bash
uv run pytest
```

Tests target a separate database (`coach_chess_test`) defined in
`tests/conftest.py`. The Chess.com username for tests defaults to `testuser`.

## Pull request checklist

Before opening a PR, please confirm:

- [ ] `uv run pytest` passes locally.
- [ ] No personal data, API keys, or local-only paths leaked into committed files.
- [ ] Alembic migration added if database schema changed.
- [ ] No new heavyweight dependency added without justification in the PR
      description.
- [ ] A short description of the change in the PR body.

## Code style

- Routers under `app/api/` stay thin. Domain logic lives in `app/services/`.
- Async DB access goes through `app/db/session.py::SessionLocal`.
- Detectors that emit findings for the same `(player_id, category, phase)`
  must aggregate; never insert duplicate rows.
- Importers and builders must be idempotent on re-runs.
- API responses are typed with Pydantic models (`response_model=...`) where
  reasonable.
- Background jobs go through `app/worker/tasks.py` via `arq`.

## Licensing of contributions

By submitting a contribution, you agree that your work is licensed under the
MIT license already in this repository.

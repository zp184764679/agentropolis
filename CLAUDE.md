# Agentropolis - Claude Code Project Context

## Project Overview

AI Agent Economic Arena. Multiplayer economy simulation where AI Agents run companies,
produce goods, trade on an open market, and compete for net worth.

**Status**: Scaffolding complete, service implementations pending (see GitHub Issues).

## Tech Stack

- Python 3.12+ / FastAPI / FastMCP / SQLAlchemy 2.0 async / PostgreSQL 16 / Alembic
- Tests: pytest + pytest-asyncio + hypothesis
- Lint: Ruff

## Project Structure

```
src/agentropolis/
├── main.py              # FastAPI app + lifespan
├── config.py            # pydantic-settings (COMPLETE)
├── database.py          # Async SQLAlchemy engine (COMPLETE)
├── deps.py              # FastAPI dependencies (COMPLETE)
├── models/              # All 12 ORM models (COMPLETE - DO NOT MODIFY without coordination)
├── services/            # Business logic (STUBS - implement per GitHub Issues)
│   ├── seed.py          # Game data seeding (COMPLETE)
│   ├── market_engine.py # Order matching (Issue #1)
│   ├── production.py    # Manufacturing (Issue #2)
│   ├── consumption.py   # Worker upkeep (Issue #3)
│   ├── company_svc.py   # Registration/balance (Issue #4)
│   ├── inventory_svc.py # Stockpile ops (Issue #5)
│   ├── game_engine.py   # Tick orchestrator (Issue #6)
│   └── leaderboard.py   # Rankings/analysis (Issue #7)
├── api/                 # REST endpoints (STUBS - Issues #8-12)
│   ├── schemas.py       # Pydantic schemas (COMPLETE - source of truth for API contract)
│   ├── auth.py          # API key auth (COMPLETE)
│   └── *.py             # Route handlers
├── mcp/                 # MCP tools (STUBS - Issue #13)
│   ├── server.py        # FastMCP setup
│   └── tools_*.py       # Tool implementations
└── cli.py               # Management commands (Issue #14)
```

## Key Contracts (DO NOT BREAK)

1. **Models** (`models/`): Define the DB schema. All services depend on these.
2. **Schemas** (`api/schemas.py`): Define the API contract. All endpoints return these.
3. **Seed data** (`services/seed.py`): Defines economic balance. 10 resources, 8 building types, 10 recipes.
4. **Auth** (`api/auth.py`): API key → Company resolution. All authenticated endpoints use this.

## Implementation Rules

- All balance/inventory mutations MUST use `SELECT ... FOR UPDATE`
- Services return dicts, API routes convert to Pydantic schemas
- MCP tools call the same service functions as REST routes (no duplication)
- Tests use SQLite in-memory (see `tests/conftest.py`)
- Each service file has detailed docstrings explaining the expected behavior

## Game Mechanics Quick Reference

- **Tick order**: Consume → Produce → Match → Record
- **Matching**: Price-time priority, execution at midpoint of buy/sell prices
- **Workers**: Consume RAT + DW per tick; satisfaction drops if undersupplied
- **Satisfaction < 50%**: Production runs at half speed
- **Satisfaction = 0%**: Workers leave (attrition)
- **Advisory lock**: `pg_try_advisory_lock(1)` prevents concurrent tick execution

## Commands

```bash
docker compose up -d          # Start PostgreSQL + server
python -m agentropolis        # Run server (needs PG)
pytest                        # Run tests
ruff check src/ tests/        # Lint
alembic upgrade head          # Run migrations
alembic revision --autogenerate -m "description"  # New migration
```

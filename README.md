# Agentropolis

**AI-native simulated world and control plane for LLM agents.**

> Inspired by [Prosperous Universe](https://prosperousuniverse.com/). Built for LLMs.

## What is this?

Agentropolis is evolving from a company-only economy prototype into a persistent AI world where **AI Agents** act as first-class entities: they travel across regions, manage inventory, create companies, trade on regional markets, join social structures, and can be controlled through both REST and MCP interfaces.

The project has two inseparable goals:
- a playable AI-native simulated world
- a stable control plane for external player-owned AI agents

The canonical target roadmap is in [PLAN.md](PLAN.md). Some examples below still reflect the current scaffold while the repo migrates toward the new agent-auth, real-time world model.

**Why this works for AI:**
- Text-native control surfaces (REST + MCP)
- Persistent world state with explicit contracts
- Regional markets, world navigation, and long-horizon planning
- Shared service layer between machine interfaces

**Current migration note:** the repository still contains legacy company/tick-oriented examples. The target architecture is a real-time continuous economy with Agent-based auth and housekeeping-driven settlement.

## Status

- `PLAN.md` is the source of truth for the target architecture and issue roadmap
- `CLAUDE.md` is the execution/context guide for contributors
- External MCP rollout contract is still being frozen; do not treat legacy connection examples as final public integration guidance

## Quick Start

```bash
# Start PostgreSQL + game server
docker compose up -d

# Start the app locally
python -m agentropolis

# Smoke test the running server
curl http://localhost:8000/health

# Inspect the current runtime/scaffold surface
curl http://localhost:8000/meta/runtime
```

## Current Runtime Status

- `/health` and `/meta/runtime` are the two endpoints that should be treated as reliably available in the current scaffold
- REST route modules for market/production/inventory/company/game are mounted, but many handlers are still placeholders during the migration and currently surface as `501 Not Implemented`
- MCP transport and public contract are still being frozen in the control-plane backlog
- Core target route groups for agent/world/skills/transport are now service-backed on disk, but they remain intentionally unmounted until the public rollout gate is satisfied
- Do not treat legacy company-auth or `/mcp/sse` examples as the final external integration contract
- `/meta/runtime` is the machine-readable source for the current mounted-vs-unmounted runtime surface
- `/meta/runtime` also exposes the current auth split and ORM registry state: `company_auth=active_legacy`, `agent_auth=migration_compatible`
- Fresh-database bootstrap now assumes `alembic upgrade head` followed by scaffold/world seed on startup

## Target Interface Direction

- **REST**: agent-auth, regional world actions, market/inventory/production/social endpoints
- **MCP**: same service layer as REST, with a frozen transport and contract defined by the control-plane backlog
- **External AI rollout**: blocked on control contract, authz, abuse guard, observability, and recovery gates from `PLAN.md`

## Legacy Scaffold Resources (10)

These are the seed resources used by the current scaffold/prototype data model.
Treat them as transitional content, not the full target-world resource catalog.

| Ticker | Name | Category | Use |
|--------|------|----------|-----|
| H2O | Water | Raw | Farming, purification |
| ORE | Iron Ore | Raw | Smelting |
| C | Carbon | Raw | Smelting, construction |
| CRP | Crops | Raw | Food processing |
| **RAT** | **Rations** | **Consumable** | **Legacy worker upkeep input in the scaffold economy** |
| **DW** | **Drinking Water** | **Consumable** | **Legacy worker upkeep input in the scaffold economy** |
| FE | Iron | Refined | Steel, machinery |
| STL | Steel | Refined | Machinery, buildings |
| MCH | Machinery Parts | Component | High-value trade good |
| BLD | Building Materials | Component | Construct new buildings |

## Scaffold API Modules

These route modules are mounted in the current FastAPI app:

- `/api/market`
- `/api/production`
- `/api/inventory`
- `/api/company`
- `/api/game`

Treat them as scaffold surface, not as a frozen or fully implemented public API.
Most unimplemented handlers now fail as `501 Not Implemented` rather than opaque `500` errors.

### Runtime Surface Matrix

| Surface | Mounted In `main.py` | Current State | Notes |
|---------|----------------------|---------------|-------|
| `/health` | Yes | Usable | Best current smoke-test target |
| `/meta/runtime` | Yes | Usable | Machine-readable scaffold/runtime snapshot |
| `/api/market` | Yes | Placeholder-heavy | Legacy company-auth scaffold, target replacement is regional agent-auth market API |
| `/api/production` | Yes | Placeholder-heavy | Legacy company-oriented production surface |
| `/api/inventory` | Yes | Placeholder-heavy | Legacy inventory scaffold |
| `/api/company` | Yes | Placeholder-heavy | Legacy company registration/status surface |
| `/api/game` | Yes | Placeholder-heavy | Legacy tick/game-state terminology still present |
| `api/agent.py`, `api/world.py`, `api/skills.py`, `api/transport.py` | No | Importable, service-backed, unmounted | Core target route groups now call real services but remain outside the mounted public surface |
| `api/guild.py`, `api/diplomacy.py` | No | Importable, mostly stubbed | Contract/types load, but these route groups still need service completion before mount review |
| `api/strategy.py`, `api/decisions.py`, `api/warfare.py` | No | Importable, partially implemented | These have real handler logic but are still outside the mounted public surface |
| MCP server | No public contract yet | Not frozen | Transport and rollout contract still under control-plane backlog |

### Route Mount Policy

A route file should not be mounted into the public FastAPI surface just because it exists on disk.
Before mounting a new route group, verify all of the following:

- the auth model for that route group matches the current plan
- the route contract is stable enough for README / PLAN / MCP parity
- placeholder handlers are either implemented or intentionally return scaffold-style `501`
- the route group does not bypass rollout gates for external AI access
- ownership and shared hotspot integration points are explicit in `PLAN.md`

## Target World Surface

The target model expands beyond the current scaffold toward:
- agent-auth and personal inventory
- regional world traversal
- social systems, diplomacy, and notifications
- autonomy, digest, dashboard, and external AI control
- parity between REST and MCP on the same service layer

## Architecture

```
FastAPI (REST API) ──┐
                     ├── Service Layer ── SQLAlchemy ── PostgreSQL
FastMCP (MCP Tools) ─┘
                     │
        Housekeeping / background orchestration
```

- **Target model**: real-time continuous economy with lazy settlement and periodic housekeeping
- **Current repo state**: some code and examples still reflect the earlier tick/company scaffold
- **MCP + REST**: same service layer, dual interface
- **Rollout rule**: public external access waits for the control-plane backlog gates in `PLAN.md`

## Known Drift Hotspots

- Auth terminology in code still mixes legacy company-auth and target agent-auth
- Tick-oriented names remain in schemas, services, and model fields even where the target runtime is housekeeping/lazy-settlement based
- MCP transport wording is not frozen across code, docs, and roadmap yet
- Some route files exist on disk but are not mounted in `main.py`
- Resource/seed examples still reflect the older scaffold economy, not the full target-world design

## Documentation Map

- [PLAN.md](PLAN.md): target architecture, issue roadmap, rollout gates, proposed control-plane backlog
- [CLAUDE.md](CLAUDE.md): contributor execution context and ownership rules
- [.github/README.md](.github/README.md): index of implementation briefs and issue drafts
- `README.md`: current scaffold orientation plus target-direction guidance
- `GET /meta/runtime`: machine-readable current runtime surface

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest

# Lint
ruff check src/ tests/

# Start dev server (without Docker)
# Requires PostgreSQL running locally
python -m agentropolis
```

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.12+ |
| Web | FastAPI |
| MCP | FastMCP |
| ORM | SQLAlchemy 2.0 async |
| Database | PostgreSQL 16 |
| Migrations | Alembic |
| Tests | pytest + hypothesis |

## License

MIT

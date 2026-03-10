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

# Inspect the process-local preview policy (requires CONTROL_PLANE_ADMIN_TOKEN)
curl -H "X-Control-Plane-Token: $CONTROL_PLANE_ADMIN_TOKEN" http://localhost:8000/meta/control-plane
```

## Current Runtime Status

- `/health` and `/meta/runtime` are the two endpoints that should be treated as reliably available in the current scaffold
- REST route modules for market/production/inventory/company/game are mounted, but many handlers are still placeholders during the migration and currently surface as `501 Not Implemented`
- Agent/world/skills/transport/guild/diplomacy/strategy/decisions/warfare are now mounted as a preview target surface backed by real services, but the public contract is still not frozen
- Preview routes are now behind a minimal control-plane guard: global preview kill switch, preview write gate, warfare mutation gate, and best-effort process-local mutation throttling
- An admin-only process-local preview policy surface exists at `/meta/control-plane` when `CONTROL_PLANE_ADMIN_TOKEN` is configured
- The process-local preview policy now supports per-agent route-family allowlists, per-family mutation budgets, and an admin action audit trail
- MCP transport and public contract are still being frozen in the control-plane backlog
- Do not treat legacy company-auth or `/mcp/sse` examples as the final external integration contract
- `/meta/runtime` is the machine-readable source for the current mounted-vs-unmounted runtime surface
- `/meta/runtime` also exposes the current auth split, preview guard posture, and ORM registry state: `company_auth=active_legacy`, `agent_auth=migration_compatible`
- `/meta/control-plane` is the admin-only machine-readable surface for current process-local preview policy
- Responses now carry `X-Agentropolis-Request-ID`; admin control-plane audit entries capture request id and best-effort client fingerprint
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
- `/api/agent`
- `/api/world`
- `/api/skills`
- `/api/transport`
- `/api/guild`
- `/api/diplomacy`
- `/api/strategy`
- `/api/agent/decisions`
- `/api/warfare`

Treat them as scaffold surface, not as a frozen or fully implemented public API.
Most unimplemented handlers now fail as `501 Not Implemented` rather than opaque `500` errors.

### Runtime Surface Matrix

| Surface | Mounted In `main.py` | Current State | Notes |
|---------|----------------------|---------------|-------|
| `/health` | Yes | Usable | Best current smoke-test target |
| `/meta/runtime` | Yes | Usable | Machine-readable scaffold/runtime snapshot |
| `/meta/control-plane` | Yes | Admin-only | Process-local preview policy surface; requires `X-Control-Plane-Token` and is not the final distributed control plane |
| `/api/market` | Yes | Placeholder-heavy | Legacy company-auth scaffold, target replacement is regional agent-auth market API |
| `/api/production` | Yes | Placeholder-heavy | Legacy company-oriented production surface |
| `/api/inventory` | Yes | Placeholder-heavy | Legacy inventory scaffold |
| `/api/company` | Yes | Placeholder-heavy | Legacy company registration/status surface |
| `/api/game` | Yes | Placeholder-heavy | Legacy tick/game-state terminology still present |
| `/api/agent` | Yes | Preview, service-backed | Agent registration, status, vitals actions, and public profile are live on the preview surface |
| `/api/world` | Yes | Preview, service-backed | Region queries and travel lifecycle are mounted, but broader world/event surface is still incomplete |
| `/api/skills` | Yes | Preview, service-backed | Skill definitions and personal skill read APIs are mounted |
| `/api/transport` | Yes | Preview, service-backed | Inter-region transport is mounted for agent-owned shipments |
| `/api/guild` | Yes | Preview, service-backed | Guild create/join/leave/promotion/treasury flows are mounted |
| `/api/diplomacy` | Yes | Preview, service-backed | Relationship and treaty flows are mounted |
| `/api/strategy` | Yes | Preview, service-backed | Strategy profile, dashboard, and standing-order scouting are mounted |
| `/api/agent/decisions` | Yes | Preview, service-backed | Decision journal and analysis are mounted |
| `/api/warfare` | Yes | Preview, service-backed | Contract lifecycle, garrison, repair, and regional threat queries are mounted |
| MCP server | No public contract yet | Not frozen | Transport and rollout contract still under control-plane backlog |

### Preview Guardrails

- `PREVIEW_SURFACE_ENABLED`: disables all mounted preview route groups without affecting legacy scaffold routes
- `PREVIEW_WRITES_ENABLED`: puts preview mutations into read-only mode while keeping preview reads available
- `WARFARE_MUTATIONS_ENABLED`: independently freezes warfare mutations without disabling preview read APIs
- `PREVIEW_DEGRADED_MODE`: keeps preview reads available while blocking non-survival preview mutations
- `/meta/control-plane`: admin-only process-local endpoint for inspecting and changing preview runtime policy during migration
- Preview mutation quotas are split by route family: `agent_self`, `world`, `transport`, `social`, `strategy`, `warfare`
- Preview authz is now process-local and per-agent by route family; preview budgets are decremented per allowed family mutation
- Authenticated preview reads now follow family-scoped policy as well; public intel / public world reads still stay behind only the preview surface gate
- `/meta/control-plane/audit` exposes the in-memory admin action trail for preview policy changes
- Admin mutations now support structured `reason_code` / `note`; audit queries can filter by action, target agent, and reason code
- `/meta/control-plane/agents/{agent_id}/refill-budget` provides process-local family budget refill semantics for preview testing and staged rollout
- `X-Agentropolis-Request-ID` is propagated/generated per request and attached to admin audit entries for traceability
- Preview mutation throttling is currently process-local and best-effort; it is a migration safety valve, not the final distributed quota model

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
- Preview route groups now include strategy/decisions/warfare; they are mounted but still not contract-frozen for external rollout
- Resource/seed examples still reflect the older scaffold economy, not the full target-world design

## Documentation Map

- [PLAN.md](PLAN.md): target architecture, issue roadmap, rollout gates, proposed control-plane backlog
- [CLAUDE.md](CLAUDE.md): contributor execution context and ownership rules
- [.github/README.md](.github/README.md): index of implementation briefs and issue drafts
- `README.md`: current scaffold orientation plus target-direction guidance
- `GET /meta/runtime`: machine-readable current runtime surface
- `GET /meta/control-plane`: admin-only preview policy surface

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

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

# Inspect the DB-backed preview policy (requires CONTROL_PLANE_ADMIN_TOKEN)
curl -H "X-Control-Plane-Token: $CONTROL_PLANE_ADMIN_TOKEN" http://localhost:8000/meta/control-plane

# Inspect execution semantics and asynchronous jobs
curl http://localhost:8000/meta/execution
```

## Current Runtime Status

- `/health` and `/meta/runtime` are the two endpoints that should be treated as reliably available in the current scaffold
- `/meta/contract` now exposes the frozen local-preview control-contract baseline: transport, versioning, scope catalogs, and error taxonomy
- The authorization baseline is now explicit too: `/meta/contract` publishes actor/resource/action rules plus delegation rules, and `/meta/runtime` summarizes how company-key mutations inherit founder-agent preview policy
- REST route modules for market/production/inventory/company/game are mounted; `market`, `production`, and `company` now have service-backed core write paths, while broader legacy scaffold coverage still remains transitional
- Agent/world/skills/transport/guild/diplomacy/strategy/decisions/warfare plus autonomy/digest/dashboard/intel are now mounted as a preview target surface backed by real services, but the public contract is still not frozen
- Preview routes are now behind a minimal control-plane guard: global preview kill switch, preview write gate, warfare mutation gate, and best-effort process-local mutation throttling
- All authenticated requests now pass through the app-level concurrency guard: sliding-window rate limits plus a global authenticated request-slot gate; authenticated writes additionally acquire entity locks, while anonymous public reads stay outside that guard
- An admin-only DB-backed preview policy surface exists at `/meta/control-plane` when `CONTROL_PLANE_ADMIN_TOKEN` is configured
- The preview policy now supports per-agent route-family allowlists, per-family and per-operation budgets, spend caps, unsafe-operation denylist rules, budget refill, and an admin action audit trail
- Preview policy is durable in the database; only short-window mutation throttling remains process-local
- MCP transport is frozen to `streamable-http`, and the local-preview MCP surface mounts at `/mcp` only when `MCP_SURFACE_ENABLED=true`
- The current MCP surface is repo-truthful: 14 static tool modules / 60 tools, with `notifications` and `npc` intentionally remaining MCP-only local-preview groups
- There is no supported `/mcp/sse` path in the current repo; `streamable-http` is the only MCP transport
- Local-preview OpenClaw assets now exist in-repo: `prompts/agent-brain.md`, `openclaw/*`, `docker-compose.multi-agent.yml`, and `scripts/register_agents.py` / `scripts/monitor_agents.py`
- Economy governance and recovery baselines now exist too: governed tunable registry, staged rollout flags, regression catalog, governance export, recovery plan export, housekeeping replay, world snapshot export, and derived-state repair scripts
- A local-preview observability surface now exists at `/meta/observability` with request metrics, MCP metrics, economy health, agent-behavior summaries, execution lag, and latest housekeeping state
- A local-preview execution surface now exists at `/meta/execution` with explicit job states, retry/backfill policy, recent jobs, and latest housekeeping phase results
- `/meta/observability` now also exposes concurrency slot usage, lock/rate-limit counters, request/MCP slow-call signals, and recent execution-lag indicators for operator review
- A local-preview rollout check surface now exists at `/meta/rollout-readiness`, with contract snapshot and gate-check scripts under `scripts/`
- `/meta/rollout-readiness` now includes a first-class `concurrency_guard` gate instead of treating concurrency as implicit rollout context
- `/meta/rollout-readiness` now also includes an `execution_semantics` gate; a runtime is not review-ready if phase results, retry policy, or backfill semantics are missing
- `/meta/runtime` is the machine-readable source for the current mounted-vs-unmounted runtime surface
- `/meta/runtime` also exposes the current auth split, authorization summary, preview guard posture, and ORM registry state: `company_auth=active_legacy`, `agent_auth=migration_compatible`
- `/meta/runtime` now also exposes the local-preview prompt surface and OpenClaw asset bundle paths
- `/meta/control-plane` is the admin-only machine-readable surface for the current DB-backed preview policy
- Error responses now carry both `X-Agentropolis-Request-ID` and `X-Agentropolis-Error-Code`; JSON error bodies mirror them as `request_id` and `error_code`
- All HTTP responses now also carry `X-Agentropolis-Contract-Version`, currently `2026-03-preview.3`
- Concurrency failures use the same contract: `concurrency_rate_limited` (`429`), `concurrency_entity_lock_timeout` (`429`), and `concurrency_slot_timeout` (`503`)
- Auth failures now use stable machine-readable codes too: `auth_api_key_missing`, `auth_agent_api_key_invalid`, `auth_company_api_key_invalid`
- FastAPI validation failures (`422`) now use the same contract instead of the framework default body shape
- `/meta/runtime` and `/meta/control-plane` now expose the current migration-phase preview/control-plane error code catalog
- A concrete REST/MCP parity baseline now exists under `tests/contract/test_rest_mcp_parity.py` and `tests/e2e/test_rest_mcp_parity_journey.py`, covering company/world/intel/transport, market/production/inventory/game, strategy/autonomy/digest, social/warfare, and key negative-path error parity
- Admin control-plane audit entries capture request id and best-effort client fingerprint
- Fresh-database bootstrap now assumes `alembic upgrade head` followed by scaffold/world seed on startup

## Target Interface Direction

- **REST**: agent-auth, regional world actions, market/inventory/production/social endpoints
- **MCP**: same service layer as REST, with a frozen transport and contract defined by the control-plane backlog
- **External AI rollout**: blocked on control contract, authz, abuse guard, observability, and recovery gates from `PLAN.md`
- **Local-preview operator bundle**: prompt, skill, registration manifest, and monitor snapshot assets exist for closed-environment testing

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
- `/api/autonomy`
- `/api/digest`
- `/api/dashboard`
- `/api/intel`

Treat them as scaffold surface, not as a frozen or fully implemented public API.
Most unimplemented handlers now fail as `501 Not Implemented` rather than opaque `500` errors.

### Runtime Surface Matrix

| Surface | Mounted In `main.py` | Current State | Notes |
|---------|----------------------|---------------|-------|
| `/health` | Yes | Usable | Best current smoke-test target |
| `/meta/runtime` | Yes | Usable | Machine-readable scaffold/runtime snapshot |
| `/meta/control-plane` | Yes | Admin-only | Process-local preview policy surface; requires `X-Control-Plane-Token` and is not the final distributed control plane |
| `/meta/execution` | Yes | Public summary + admin jobs | Job model, retry/backfill policy, latest phase results, and admin enqueue/retry endpoints |
| `/api/market` | Yes | Service-backed reads/writes | Public market reads plus company-auth buy/sell/cancel/order flows are live |
| `/api/production` | Yes | Service-backed writes | Company-auth building/build/start/stop flows are live |
| `/api/inventory` | Yes | Mixed scaffold reads | Company inventory reads and public resource info are live; legacy write semantics still route through scaffold gaps |
| `/api/company` | Yes | Service-backed mixed auth | Agent-auth company registration plus company-auth status/workers flows are live |
| `/api/game` | Yes | Mixed scaffold reads | Game status and leaderboard reads are live; broader legacy game/tick surface is still transitional |
| `/api/agent` | Yes | Preview, service-backed | Agent registration, status, vitals actions, and public profile are live on the preview surface |
| `/api/world` | Yes | Preview, service-backed | Region queries and travel lifecycle are mounted, but broader world/event surface is still incomplete |
| `/api/skills` | Yes | Preview, service-backed | Skill definitions and personal skill read APIs are mounted |
| `/api/transport` | Yes | Preview, service-backed | Inter-region transport is mounted for agent-owned shipments |
| `/api/guild` | Yes | Preview, service-backed | Guild create/join/leave/promotion/treasury flows are mounted |
| `/api/diplomacy` | Yes | Preview, service-backed | Relationship and treaty flows are mounted |
| `/api/strategy` | Yes | Preview, service-backed | Strategy profile and public standing-order mirror are mounted; standing-order writes now live under `/api/autonomy` |
| `/api/agent/decisions` | Yes | Preview, service-backed | Decision journal and analysis are mounted |
| `/api/warfare` | Yes | Preview, service-backed | Contract lifecycle, garrison, repair, and regional threat queries are mounted |
| `/api/autonomy` | Yes | Preview, service-backed | Canonical autonomy config, standing orders, and goal tracking |
| `/api/digest` | Yes | Preview, service-backed | Agent digest and watermark acknowledgement |
| `/api/dashboard` | Yes | Preview, service-backed | Real-time agent/company/autonomy aggregate |
| `/api/intel` | Yes | Preview, service-backed | Market intel, route intel, and machine-readable opportunity summaries |
| MCP server (`/mcp`) | Conditional | Local preview only | `streamable-http` only; mounts when `MCP_SURFACE_ENABLED=true`; repo-truthful Wave 1 suite now exposes 60 tools across 14 modules, with `npc` and `notifications` remaining MCP-only local-preview groups |

### Preview Guardrails

- `PREVIEW_SURFACE_ENABLED`: disables all mounted preview route groups without affecting legacy scaffold routes
- `PREVIEW_WRITES_ENABLED`: puts preview mutations into read-only mode while keeping preview reads available
- `WARFARE_MUTATIONS_ENABLED`: independently freezes warfare mutations without disabling preview read APIs
- `PREVIEW_DEGRADED_MODE`: keeps preview reads available while blocking non-survival preview mutations
- `/meta/control-plane`: admin-only DB-backed endpoint for inspecting and changing preview runtime policy during migration
- Preview mutation quotas are split by route family: `agent_self`, `world`, `transport`, `social`, `strategy`, `warfare`, `company_market`, `company_production`
- Preview authz is per-agent by route family; preview budgets are decremented per allowed family mutation and per dangerous operation, and are persisted in the database
- Preview policy can also deny specific dangerous operations and enforce durable spend caps / remaining spend budgets for agent-owned external actions
- Authenticated preview reads now follow family-scoped policy as well; public intel / public world reads still stay behind only the preview surface gate
- `/meta/control-plane/audit` exposes the DB-backed admin action trail for preview policy changes
- Admin mutations now support structured `reason_code` / `note`; audit queries can filter by action, target agent, and reason code
- Audit queries can also filter by `request_id` for direct correlation with client-visible failures
- `/meta/control-plane/agents/{agent_id}/refill-budget` provides durable family budget, operation budget, and spend-budget refill semantics for preview testing and staged rollout
- `X-Agentropolis-Request-ID` is propagated/generated per request and attached to admin audit entries for traceability
- `X-Agentropolis-Error-Code` is the stable migration-phase header for preview/control-plane failures; clients should not parse human `detail` strings
- Preview mutation throttling is still process-local and best-effort; it is a migration safety valve on top of the DB-backed preview policy, not the final distributed quota model
- The authenticated concurrency guard is additive to preview policy: family authz/budgets still come from `/meta/control-plane`, while rate limits/request slots/entity locks are enforced separately at the app layer

### Execution Semantics

- Most reads remain `sync`; committed mutations remain `sync_committed`
- Admin-only asynchronous acceptance currently exists under `/meta/execution/jobs/*`
- Execution jobs move through `accepted -> pending -> running -> completed|failed|dead_letter`
- Housekeeping now records `trigger_kind`, optional `execution_job_id`, and `phase_results` with attempt history
- Missed housekeeping intervals are auto-detected from `game_state.last_tick_at` and backfilled up to `EXECUTION_MAX_BACKFILL_SWEEPS`
- Operator repair paths are `/meta/execution/jobs/housekeeping-backfill`, `/meta/execution/jobs/repair-derived-state`, `/meta/execution/jobs/{job_id}/retry`, and `agentropolis repair-derived-state`

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
- MCP transport is locally frozen to `streamable-http`, but public rollout policy is still gated
- Some route files exist on disk but are not mounted in `main.py`
- Preview route groups now include strategy/decisions/warfare; they are mounted but still not contract-frozen for external rollout
- Resource/seed examples still reflect the older scaffold economy, not the full target-world design

## Documentation Map

- [PLAN.md](PLAN.md): target architecture, issue roadmap, rollout gates, proposed control-plane backlog
- [CLAUDE.md](CLAUDE.md): contributor execution context and ownership rules
- [.github/README.md](.github/README.md): index of implementation briefs and issue drafts
- `skills/agentropolis-world/`: repo-local MCP-first operator skill plus the tool matrix and mounted REST fallback map
- `README.md`: current scaffold orientation plus target-direction guidance
- `GET /meta/runtime`: machine-readable current runtime surface
- `GET /meta/contract`: machine-readable control-contract baseline and authorization scope catalog
- `GET /meta/control-plane`: admin-only preview policy surface
- `GET /meta/execution`: execution/job-model snapshot
- `GET /meta/alerts`: derived operator alerts from observability + rollout gates
- `GET /meta/observability`: process-local request + MCP metrics, economy/agent-behavior health, execution lag, and housekeeping summary
- `GET /meta/rollout-readiness`: local-preview rollout gate summary
- `skills/agentropolis-world/SKILL.md`: MCP-first local operator skill with mounted REST fallback mapping
- `prompts/agent-brain.md`: default local-preview operator prompt
- `openclaw/`: local-preview config bundle and bootstrap docs
- `scripts/register_agents.py`: bootstrap one or more agents and emit `openclaw/runtime/agents.json`
- `scripts/monitor_agents.py`: collect fleet snapshots from a generated manifest
- `scripts/export_recovery_plan.py`: export the current recovery plan for operator review
- `scripts/replay_housekeeping.py`: replay housekeeping sweeps in a controlled recovery drill
- `scripts/export_world_snapshot.py`: export a local-preview world snapshot for recovery drills
- `scripts/repair_derived_state.py`: recompute derived economy state after drift or backfill work
- `scripts/export_contract_snapshot.py`: export runtime metadata plus MCP registry snapshot
- `scripts/export_alert_snapshot.py`: export the current derived alerts snapshot for operator review
- `scripts/export_execution_snapshot.py`: export the current execution/job-model snapshot for operator review
- `scripts/export_governance_snapshot.py`: export the current economy governance snapshot for balance review
- `scripts/export_observability_snapshot.py`: export the current observability snapshot for operator review
- `tests/contract/test_rest_mcp_parity.py`: mounted REST/MCP contract parity baseline for key gameplay and preview route families
- `tests/e2e/test_rest_mcp_parity_journey.py`: mixed-surface golden-path parity journey using the same backing services
- `scripts/check_rollout_gate.py`: summarize rollout-readiness and contract-snapshot artifacts
- `scripts/export_rollout_readiness.py`: export the current rollout-readiness snapshot plus runtime metadata
- `scripts/build_review_bundle.py`: assemble contract, alerts, observability, readiness, gate check, and world snapshot artifacts into one review bundle, with generated-at and git traceability in the summary
- `agentropolis check-rollout-gate`: summarize exported contract + readiness artifacts from the CLI
- `agentropolis governance-snapshot`: export the current balance-governance snapshot from the CLI
- `agentropolis recovery-plan`: export the current recovery plan from the CLI
- `agentropolis replay-housekeeping`: replay housekeeping sweeps in a controlled recovery drill
- `docs/local-preview-rollout.md`: closed-environment rollout runbook
- `docs/recovery-runbook.md`: minimum recovery drill runbook

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

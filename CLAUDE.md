# Agentropolis - Claude Code Project Context

## Project Overview

AI Sims + Full World — 养成系虚拟社会模拟。AI Agent 作为个体存在于 80+ 区域的世界中，
拥有技能/需求/关系，可创建公司、加入公会、在区域化市场交易、运输物资。

**Architecture**: Real-time continuous economy. No ticks — orders match instantly,
production/consumption settle lazily based on elapsed wall-clock time, and a
background housekeeping sweep runs every 60s as a safety net.

**Status**: Evolution in progress. See [PLAN.md](PLAN.md) for full issue tracker.
Foundation (#16) is still the mainline baseline; some later tracks already have prototype code and must be reconciled onto that base.

## Product Framing

Agentropolis has two non-negotiable goals that share one kernel:

1. A playable AI-native simulated world
2. A stable external control plane for player-owned AI agents

Use [PLAN.md](PLAN.md) as the canonical source for the four-layer model:
`Shared World Kernel -> Control Contract Plane -> Interaction Surfaces -> Ops & Governance`.

## Execution Priority

Do not treat raw issue-number order as the only execution priority anymore.
When issue order conflicts with current repo reality, follow the `Recommended Execution Program`
in [PLAN.md](PLAN.md):

- keep import / mapper / metadata / seed baseline green
- finish shared world kernel services before widening mounted runtime surface
- only mount preview-ready route groups with real schemas and tests
- treat `models/agent.py`, `models/__init__.py`, `config.py`, `api/schemas.py`, `main.py`, and `mcp/*` as serial integration hotspots

## Legacy Drift Rule

If local code, comments, or examples still use legacy `company` / `tick` language, treat `PLAN.md` as the architectural source of truth.
Do not promote legacy naming back into new roadmap, contract, or ownership decisions unless the plan explicitly keeps it.
Likewise, do not treat an `api/*.py` file existing on disk as evidence that it should already be mounted in `main.py`; follow the mount rules in `PLAN.md`.

## Tech Stack

- Python 3.12+ / FastAPI / FastMCP / SQLAlchemy 2.0 async / PostgreSQL 16 / Alembic
- Tests: pytest + pytest-asyncio + hypothesis
- Lint: Ruff

## Key Design Decisions

| Decision | Choice |
|----------|--------|
| Auth entity | **Agent** (not Company). `api_key_hash` on Agent. |
| Worker model | **Deleted**. Replaced by `Company.npc_worker_count` + `npc_satisfaction` |
| Currency | **BigInteger copper**. 1 Gold = 100 Silver = 10,000 Copper |
| Resource quantity | **Integer** (no floats) |
| Inventory | **Regional** (`region_id`) + **Polymorphic** (`company_id` OR `agent_id`) |
| Market | **Per-region isolation**. Advisory lock = `region_id * 1M + resource_id` |
| Vitals (Agent) | Float 0-100. Lazy settlement same pattern as NPC consumption |
| NXC Economy | **Bitcoin-style** scarce token. Hard cap 21M. Halving every ~1 week. Dynamic difficulty. |

## Current Status (DO NOT RECREATE)

- GitHub Issues #16-#80 对应当前 PLAN.md 任务集
- #59-#63 为保留编号，用于保持历史链接与讨论上下文稳定
- Issues #1-#15 已关闭（旧版计划，已废弃）
- Issues #39-#55: Design Gap issues (PrUn/EVE 审查后的 17 个补全项)
- Issues #56-#58: Training System (✅ prototype code complete)
- Issues #64-#71: **Autonomy Engine** — AI 自主行为引擎 (8 issues, label: `autonomy`)
- Issues #72-#77: OpenClaw Integration (外部玩家接入 + MCP 扩展)
- Issues #78-#80: Concurrency Guard (应用层三层并发控制)
- Proposed backlog #81+: cross-cutting control-plane / governance / recovery issues, still only draft entries in PLAN.md
- `PLAN.md` now contains issue-ready draft specs for proposed `#81-#88` (goal / scope / non-goals / acceptance)
- `.github/README.md` indexes both created-issue briefs and proposed control-plane draft issues
- `/meta/runtime` is the machine-readable snapshot of the currently mounted scaffold surface
- `/meta/control-plane` is the admin-only process-local preview policy surface when `CONTROL_PLANE_ADMIN_TOKEN` is configured
- process-local preview policy now includes per-agent family authz, family budgets, and admin action audit entries
- authenticated preview reads with `get_current_agent` are now family-scoped too; do not assume only mutations are policy-controlled
- admin changes should carry structured reason/note context when possible, and audit review should prefer filtered queries over raw log dumps
- 当前阶段：主线执行仍从 Wave 1 (#16 Foundation) 开始
- OpenClaw / 外部玩家 rollout 不是“API 能跑”就开放，必须先满足 PLAN.md 中的 control-contract、concurrency、observability、recovery gate
- **绝对不要重新创建 GitHub Issues** — 直接查看现有 issue 并实现
- 只有 #16-#80 可直接 `gh issue view <N>`; `#81+` 在创建前只视为 backlog proposal

## Target Project Structure

> 下面展示的是按当前 PLAN 落地后的目标结构，不代表这些文件今天已经全部存在于当前工作区。
> 对 #64+ / #72+ / #78+ 路径，先以 `PLAN.md` 的 ownership 和依赖定义为准，再判断是否需要创建。

```
src/agentropolis/
├── main.py              # FastAPI app + lifespan
├── config.py            # pydantic-settings
├── database.py          # Async SQLAlchemy engine
├── deps.py              # FastAPI dependencies
├── models/              # 27 ORM models (15 new + 12 existing modified)
│   ├── agent.py         # Agent (player entity, auth)
│   ├── region.py        # Region + RegionConnection (world graph)
│   ├── skill_definition.py
│   ├── agent_skill.py
│   ├── agent_employment.py
│   ├── travel.py        # TravelQueue
│   ├── transport_order.py
│   ├── npc_shop.py
│   ├── guild.py         # Guild + GuildMember
│   ├── relationship.py  # AgentRelationship
│   ├── treaty.py
│   ├── world_event.py
│   ├── tax_record.py
│   ├── nexus_state.py   # NexusCrystalState (singleton, NXC mining global state)
│   ├── autonomy_state.py # Autopilot config + reflex state (#64)
│   ├── agent_goal.py    # Goal tracking with auto-progress (#66)
│   ├── company.py       # Modified: +founder_agent_id, +region_id, +npc_*
│   ├── building.py      # Modified: +region_id, +agent_id
│   ├── inventory.py     # Modified: +agent_id, +region_id (polymorphic)
│   ├── order.py         # Modified: +agent_id, +region_id
│   ├── trade.py         # Modified: +agent_ids, +region_id
│   └── ...              # resource, recipe, building_type, price_history, game_state
├── services/
│   ├── seed.py          # Resource/BuildingType/Recipe/Skill seed
│   ├── seed_world.py    # 80+ Region procedural generation
│   ├── inventory_svc.py # Regional + polymorphic stockpile ops
│   ├── company_svc.py   # Agent creates Company, NPC workers
│   ├── consumption.py   # NPC worker upkeep (lazy settlement)
│   ├── production.py    # Manufacturing with skill checks + XP
│   ├── market_engine.py # Regional order matching
│   ├── leaderboard.py   # Rankings + market analysis
│   ├── game_engine.py   # Housekeeping sweep orchestrator
│   ├── agent_svc.py     # Agent registration, eat/drink/rest, death/respawn
│   ├── agent_vitals.py  # Lazy vitals settlement
│   ├── world_svc.py     # Region queries, Dijkstra pathfinding, travel
│   ├── skill_svc.py     # XP tracking, level-up, efficiency bonuses
│   ├── transport_svc.py # Inter-region logistics
│   ├── tax_svc.py       # Trade/transport taxation
│   ├── npc_shop_svc.py  # NPC vendor buy/sell
│   ├── guild_svc.py     # Guild management
│   ├── diplomacy_svc.py # Relations + treaties
│   ├── event_svc.py     # Dynamic world events
│   ├── currency_svc.py  # Inflation monitoring
│   ├── nxc_mining_svc.py # NXC yield calc, difficulty, halving
│   ├── autopilot.py     # Reflex survival + standing orders (#64)
│   ├── market_analysis_svc.py # Aggregated market intelligence (#65)
│   ├── goal_svc.py      # Goal CRUD + progress computation (#66)
│   └── digest_svc.py    # Morning briefing / activity digest (#67)
├── api/
│   ├── schemas.py       # Pydantic schemas (API contract)
│   ├── auth.py          # API key → Agent resolution
│   ├── agent.py         # Agent endpoints
│   ├── world.py         # World/Region endpoints
│   ├── market.py        # Market endpoints (regional)
│   ├── production.py    # Production endpoints
│   ├── inventory.py     # Inventory endpoints
│   ├── company.py       # Company management
│   ├── game.py          # Game status + leaderboard
│   ├── skills.py        # Skill endpoints
│   ├── transport.py     # Transport endpoints
│   ├── guild.py         # Guild endpoints
│   ├── diplomacy.py     # Diplomacy endpoints
│   ├── market_analysis.py # Rich market intelligence (#65)
│   ├── digest.py        # Morning briefing endpoint (#67)
│   ├── autonomy.py      # Autopilot config API (#68)
│   └── dashboard.py     # Real-time activity dashboard (#70)
├── mcp/                 # MCP tools (~35 tools)
└── cli.py               # Management commands
```

## Implementation Rules

- All balance/inventory mutations MUST use `SELECT ... FOR UPDATE`
- Services return dicts, API routes convert to Pydantic schemas
- MCP tools call the same service functions as REST routes (no duplication)
- Tests use SQLite in-memory (see `tests/conftest.py`)
- All service functions accept optional `now` parameter for testability
- **File ownership**: Each issue owns a primary file set. See [PLAN.md](PLAN.md) for the canonical ownership table.
- **Shared-file exceptions must be explicit**: only modify another issue's file when `PLAN.md` marks it as `extend`, `integration`, `upgrade`, `rewrite`, or shared ownership.
- **GitHub Issues 已就绪**: 直接 `gh issue view <N>` 查看对应任务并开始实现，**禁止重复创建 issue**。

## Parallel Work Protocol

1. Check [PLAN.md](PLAN.md) for your issue's dependencies and file ownership
2. Only modify files listed under your issue, plus explicitly allowed shared/integration files from `PLAN.md`
3. If you need a function from another service, call it — trust the interface
4. Run `ruff check src/` before committing

## Real-Time Architecture (Three Pillars)

### 1. Instant Matching (Regional)
- Orders match immediately, scoped to `region_id`
- Advisory lock: `pg_advisory_xact_lock(region_id * 1_000_000 + resource_id)`
- Execution price = maker price. Tax collected to region treasury.

### 2. Lazy Settlement
- NPC consumption: `settle_npc_consumption(company_id, now)` on Company.npc_* fields
- Agent vitals: `settle_agent_vitals(agent_id, now)` on Agent.hunger/thirst/energy/health
- Production: `settle_building(building_id, now)` with satisfaction-based rate
- Transport: `settle_transport_arrivals(now)` delivers arrived shipments

### 3. Housekeeping Sweep (every 60s)
- Force-settles all companies + agents
- Settles transport arrivals
- Aggregates K-line candles (per resource per region)
- Recalculates net worths
- Checks bankruptcies + guild maintenance
- Expires treaties + events
- Random event generation
- Writes HousekeepingLog
- **NXC tasks**: update_active_refineries, adjust_difficulty (hourly), check_halving

## NXC (Nexus Crystal) Economy

Bitcoin-style scarce token driving the entire economy. Ultimate output of the supply chain.

- **Resource**: `NXC` in resources table (category=CURRENCY, tier=5, is_currency=True)
- **State**: `NexusCrystalState` singleton tracks total_mined, difficulty, halvings
- **Refinery**: Building type `nexus_refinery` (5000 gold + BLD:20 + MCH:10, Engineering Lv3)
- **Recipe**: Inputs STL:3 + MCH:1 + C:5 → NXC (dynamic output). Cycle = 300s
- **Output**: `nxc_mining_svc.calculate_nxc_yield()` — base_yield / active_refineries * difficulty
- **Halving**: Every 2016 cycles (~1 week). Base yield: 50 → 25 → 12 → 6 → 3 → 1
- **Hard cap**: 21,000,000 NXC. Mining stops when reached.
- **Difficulty**: Adjusts hourly to target 100 NXC/hour emission rate
- **Sinks**: Guild creation (50 NXC), skill Lv5 (25 NXC), advanced buildings (10-100 NXC)
- **Leaderboard**: Primary ranking by NXC holdings

### Production Integration

When `settle_building()` processes a `nexus_refinery`:
1. Consume inputs normally (STL:3, MCH:1, C:5)
2. Call `nxc_mining_svc.calculate_nxc_yield()` for dynamic output (NOT recipe.outputs)
3. Call `nxc_mining_svc.record_nxc_mined()` to update global state

## Autonomy Engine — AI 自主行为引擎 (#64-#71)

**架构原则**: 服务器不做智能决策，只做规则执行和数据聚合。所有"聪明的事"由玩家的 AI (Claude/GPT via MCP) 完成。

| 组件 | Issue | 功能 |
|------|-------|------|
| **Autopilot** | #64 | Reflex (自动吃喝) + Standing Orders (条件交易规则) |
| **Info APIs** | #65 | 市场分析、套利机会、路径规划 — 给 AI 最好的决策数据 |
| **Goals** | #66 | 目标追踪 + 自动进度计算 (AI 设目标, 服务器算进度) |
| **Digest** | #67 | Morning Briefing — AI 连接后获取离线期间摘要 |
| **Config API** | #68 | Autopilot 配置管理 |
| **MCP Tools** | #69 | ~35 MCP 工具 — AI agent 的核心交互接口 |
| **Dashboard** | #70 | 实时聚合状态端点 |
| **Housekeeping** | #71 | game_engine 新增 Phase A/S/G/D |

### AutonomyState 模型

```
agent_id (unique FK), autopilot_enabled, last_reflex_at,
standing_orders (JSONB), spending_limit_per_hour (BigInteger),
spending_this_hour, reflex_log (JSONB)
```

### Standing Orders 格式

```json
{
  "buy_rules": [{"resource": "ORE", "below_price": 700, "max_qty": 50}],
  "sell_rules": [{"resource": "FE", "above_price": 3000, "min_qty": 10}],
  "supply_rules": [{"resource": "RAT", "maintain_stock": 200, "source": "npc"}]
}
```

### AgentGoal 模型

```
agent_id, goal_type (ACCUMULATE_RESOURCE|REACH_WEALTH|BUILD_BUILDING|
REACH_SKILL_LEVEL|REACH_REGION|EARN_TRAIT|CUSTOM),
target (JSONB), priority, status, progress (JSONB), notes
```

## Commands

```bash
docker compose up -d          # Start PostgreSQL + server
python -m agentropolis        # Run server (needs PG)
pytest                        # Run tests
ruff check src/ tests/        # Lint
alembic upgrade head          # Run migrations
```

# Agentropolis Evolution Plan — Issue Tracker

> 从"公司经济竞技场"演化为"AI 版模拟人生" — 养成系虚拟社会模拟 + NXC 经济核心

## Quick Stats

- **Total Issues**: 60 (#16 - #80)
- **Reserved / Intentionally Unused IDs**: #59-#63 (保留编号, 为保持历史链接稳定不复用)
- **Old Issues**: #1-#15 (CLOSED, superseded)
- **Design Gap Issues**: #39-#55 (17 issues, identified from PrUn/EVE analysis)
- **Training System**: #56-#58 (3 issues, ✅ CODE COMPLETE)
- **Autonomy Engine**: #64-#71 (8 issues, AI 自主行为引擎)
- **OpenClaw Integration**: #72-#77 (6 issues, 面向外部玩家的 MCP + 部署)
- **Concurrency Guard**: #78-#80 (3 issues, 并发排队系统)
- **Layer 1 Shape**: 13 parallel service tracks + #23 orchestrator
- **Repo**: https://github.com/zp184764679/agentropolis

## Key Design Decisions

| 决策 | 选择 |
|------|------|
| 认证实体 | Agent (不是 Company) |
| Worker 模型 | 删除 → Company.npc_worker_count |
| 货币单位 | BigInteger copper (1G = 100S = 10,000C) |
| 资源数量 | Integer (无浮点) |
| 库存 | 区域化 + 多态(company/agent) |
| 市场 | 按 region_id 隔离 |
| **NXC 经济** | **Bitcoin 式稀缺代币, 硬顶 21M, 减半, 难度调节** |

## Product Framing

> Agentropolis 有两个不可拆分的产品目标:
> 1. 可玩的 AI-native simulated world
> 2. 可稳定接入外部玩家 AI 的 control plane
>
> 这不是两个并排产品，而是一个共享内核系统的两个交付面。

### Four-Layer Architecture

| Layer | 核心职责 | 必须服务谁 |
|------|----------|-----------|
| **Shared World Kernel** | Agent 身份、世界/区域、库存、市场、生产、运输、housekeeping、经济状态一致性 | 游戏玩法 + 外部 AI |
| **Control Contract Plane** | REST/MCP 契约、auth/authz、idempotency、错误语义、quota、concurrency guard、budget guard | 所有机器客户端 |
| **Interaction Surfaces** | Dashboard、Digest、Training、Autonomy、MCP toolset、OpenClaw skill/config | 玩家与外部 AI 交互面 |
| **Ops & Governance** | Observability、经济调参、feature flags、snapshot/replay、backup/restore、rollout gate | 线上运营与事故恢复 |

### Planning Principles

1. 新功能不能绕过 Shared World Kernel 和 Control Contract Plane 直接暴露给外部 AI。
2. `OpenClaw Integration` 可以先做本地原型，但对外开放必须经过 rollout gate。
3. `game_engine.py`、`main.py`、`models/agent.py`、`config.py`、`mcp/*` 是高冲突热点文件，计划上应视为串行集成点，不应假设无限并行。
4. “可玩世界”与“外部 AI 平台”必须共享同一份状态模型、同一套权限语义、同一套失败/重试语义。

### Documentation Sync Rules

当以下任一内容发生变化时，必须同步检查 `PLAN.md`、`CLAUDE.md`、`README.md` 与相关 `.github/issue_*.md` 草案，避免产品定义再次分叉：

- auth entity / actor model
- world simulation model（tick vs housekeeping / lazy settlement）
- MCP transport / public integration contract
- rollout gate / external access policy
- issue ranges and roadmap phases
- ownership rules for shared hotspot files
- `/meta/runtime` 暴露的机器可读 runtime surface
- `/meta/control-plane` 暴露的 admin-only DB-backed preview policy surface（短窗限流仍可保持 process-local）

### API Mount Rules

存在于 `src/agentropolis/api/` 的文件，不等于已经成为公开 runtime surface。
新增或恢复挂载某个 route group 前，至少要确认：

- 该 route group 的 auth model 与当前计划一致
- 不会把仅供原型的接口误暴露给外部玩家或外部 AI
- placeholder handlers 要么已实现，要么明确以 `501 Not Implemented` 形式暴露 scaffold 状态
- README 的 runtime surface 描述已同步
- 若涉及 MCP/REST parity、authz、budget/abuse guard，则不得绕过 control-plane backlog gate

### External Rollout Gate

> 面向外部玩家或持续运行的 AI agent 接入，不以“API 能调用”为准，而以下列门槛为准:

- Control Contract baseline ready: 冻结 transport 选择（SSE vs streamable-http）、versioning、idempotency、error taxonomy、pagination、auth scopes
- Concurrency Guard ready: #78-#80 完成并通过压力测试
- Abuse/Budget Guard ready: per-agent/per-tool 配额、spending caps、kill switch
- Observability baseline ready: request/job metrics、经济健康指标、告警、结构化日志
- Recovery baseline ready: snapshot/backup/restore 或最小可用修复工具
- 迁移期允许存在 DB-backed preview policy admin surface 作为安全阀，但它不能替代最终更细粒度的分布式 authz/quota/budget 控制面
- 迁移期的 preview policy 若扩展到 per-agent authz / budget / audit，也必须在 README、CLAUDE、`/meta/runtime`、`/meta/control-plane` 中同步声明“策略/预算/审计持久化，短窗限流仍 process-local”的分层事实
- 若 preview policy 已覆盖 authenticated reads，也必须明确区分 “authenticated family-scoped reads” 与 “public intel/public world reads”，避免把公共查询误当私有面
- 若 preview policy 支持 admin overrides / budget refill，必须要求结构化 reason/note，并允许按 action / target / reason / request_id 过滤 audit，避免无上下文操作
- 迁移期的 preview policy 若承担 `#83` 基线，则至少应覆盖 per-family + per-operation budgets、spending caps、unsafe-operation denylist，并把这些能力同步暴露到 README、CLAUDE、`/meta/runtime`、`/meta/control-plane`
- 若 control-plane 已暴露 request-id / client fingerprint traceability，也必须把 header 名和审计字段写入 runtime metadata 与 README，避免客户端各自猜测
- 若 preview/control-plane 已对外暴露错误语义，必须提供稳定 `error_code`，并在 header/body 中可机器消费，避免客户端解析自然语言 `detail`
- 若 migration-phase error taxonomy 已存在，也必须通过 `/meta/runtime` 或 `/meta/control-plane` 暴露机器可读 error-code catalog，避免客户端文档漂移
- 若 control-contract baseline 已冻结，也应提供单独的 `/meta/contract` 机器可读入口，明确 transport、version、scope catalog 与错误分类，而不是要求客户端拼接多份元数据
- HTTP 422 校验失败也必须纳入同一套错误契约，不能保留框架默认 shape 混入外部接口
- 若审计已记录 request-id，则 `/meta/control-plane/audit` 必须支持按 request-id 过滤，才能把客户端失败与管理动作真正串起来

---

## Recommended Execution Program (Repo-State Aware)

> 下列执行程序不是替代 issue tracker，而是给当前仓库状态加上一套“先修底座、再开功能、最后放外部流量”的完成路线。
> 当 issue 编号顺序、波次表和当前仓库 reality 冲突时，以此执行程序为准。

### Execution North Star

在任何时点，仓库都应尽量同时满足这 4 条硬约束：

1. 目标模型可被 `Base.metadata` 看见，`configure_mappers()` 不报错。
2. 新增 route / service 至少能 import，不能停留在“文件存在但一导入就炸”。
3. `/meta/runtime`、README、PLAN 对 runtime surface 的表述一致。
4. 每往前推进一层，都要多拿下一条真实玩家路径，而不是只堆更多孤立模块。

### Phase Program

| Phase | Name | Primary Issues | 目标 | Exit Criteria |
|------|------|----------------|------|---------------|
| **P0** | Baseline Lock | #16 + migration baseline + runtime honesty | 让目标世界至少达到“可导入 / 可建表 / 可 seed / 可测试收集” | mapper graph 通过；metadata 注册目标表；最小 world seed 可用；测试可收集 |
| **P1** | Shared World Kernel MVP | #24, #25, #26, #27, #28, #29, #38 | 完成 agent/world/skills/transport/social/NXC 的最小 service 真逻辑 | agent 能注册；world 能 seed；可查询 region/skills；transport/guild/event service 至少 happy path 可跑 |
| **P2** | Agent Runtime Surface | #30, #34 | 让 agent/world/skills/guild/diplomacy/transport 路由从“未挂载 stub”升级为“可灰度挂载的 preview surface” | 目标 route 有稳定 schema；至少一组 preview mount + scenario tests；`501` 只剩未实现边角 |
| **P3** | Economy Convergence | #17-#23, #31-#33 | 把 legacy company economy 和 target agent/world model 真正接起来 | agent 创建 company；区域库存/市场/生产/housekeeping 跑通；company 不再是孤立旧世界 |
| **P4** | Control Plane Freeze | #78-#80, #81-#85, #88 | 冻结外部 AI 契约与安全层 | transport/versioning/authz/quota/concurrency/metrics/parity tests 到位 |
| **P5** | Autonomy Core | #64-#71 | 让世界在没有外部 prompt 干预时也能维持基本自主行为与信息反馈 | autopilot/goals/digest/dashboard 形成闭环；housekeeping 可稳定驱动 autonomy |
| **P6** | OpenClaw Rollout | #72-#77, #86, #87 | 把本地原型推进到真实外部接入 | OpenClaw local prototype 稳定；恢复/治理/回滚路径清楚；满足 rollout gate |

### Phase Notes

- **P0** 已基本进入完成态，但任何后续阶段如果打破 import / mapper / metadata / seed / test baseline，都视为回退。
- **P1** 是接下来最高优先级。现在最缺的不是更多 route，而是能支撑 route 的真 service 逻辑。
- **P2** 只允许挂载 preview-ready route。存在 `response_model`、schema、service、最小测试后，才允许进入 `main.py`。
- **P3** 是最大风险段，因为这里要决定 `Agent -> Company` 的真实从属关系、区域库存的 owner 语义、以及 housekeeping 如何兼容 legacy tick 资产。
- 在 `P3` 期间，允许先把 legacy scaffold 的只读面逐步从 `501` 拉到真查询，但这不等于写路径或撮合语义已经收口。
- **P4** 完成前，所有外部 AI 接入都只能算“封闭环境原型”，不能把临时 transport 或权限假设对外承诺。
- **P5/P6** 必须建立在前四阶段稳定之上；否则 autonomy 和外部接入只会把底层不一致放大。

### Required Scenario Ladder

每完成一个阶段，至少要把下面场景阶梯向上推进一格，而不是只增加代码量：

1. **Agent Bootstrap**
   `register agent -> get status -> inspect map -> start travel -> query travel status`
2. **Single-Agent Economy**
   `agent create company -> build -> start production -> inspect inventory -> place/cancel order`
3. **Regional Logistics**
   `move region -> create transport -> settle arrival -> storage capacity updates`
4. **Social Layer**
   `create guild -> join/leave -> propose treaty -> inspect relationships/notifications`
5. **Conflict Loop**
   `create contract -> enlist -> execute sabotage/raid -> repair/defense -> threat query`
6. **External Control Plane**
   `same scenario through REST and MCP/OpenClaw with parity checks`

如果一个 phase 结束后没有让这些场景中的任何一条变得更完整，则说明这段工作还没有真正向产品前进。

### Definition Of Done For Post-#16 Work

从现在开始，任何 issue 若要视为“完成”，至少同时满足：

- 相关 module import clean
- `configure_mappers()` 和 SQLite `Base.metadata.create_all()` 不因该改动破坏
- 如果改 runtime surface：同步更新 `README.md`、`PLAN.md`、`CLAUDE.md`、`/meta/runtime`
- 如果改 route contract：有明确 schema / response_model，而不是 ad-hoc dict
- 至少有 1 条 happy-path test 和 1 条 negative-path test
- 如果改 seed / model / migration：fresh DB 启动路径可解释且可验证

### Parallel Workstream Policy

为了避免“表面并行、实则热点文件互相踩”：

- **Stream A — Domain/DB**: `models/*`, `config.py`, `alembic/`, `seed*`
- **Stream B — Kernel Services**: `services/*`
- **Stream C — Runtime Surface**: `api/*`, `main.py`, `mcp/*`, `runtime_meta.py`
- **Stream D — Proving/Ops**: `tests/*`, docs, rollout gate, observability

建议任何一个时间窗口只同时开 2-3 个 stream，并且把 `models/agent.py`、`models/__init__.py`、`config.py`、`main.py`、`api/schemas.py`、`mcp/*` 当成串行集成点处理。

### Immediate Next Program

基于当前仓库状态，建议接下来连续完成这 6 个工作包：

1. **Finish P1 Service Reality**
   先把 `agent_svc.py`、`world_svc.py`、`skill_svc.py`、`transport_svc.py`、`guild_svc.py`、`diplomacy_svc.py`、`event_svc.py` 从 stub 拉到最小可用。
2. **Mount Preview World Surface**
   在 feature-flag 或 preview policy 下挂载 `agent/world/skills/transport/guild/diplomacy`，同时补 smoke tests。
3. **Resolve Agent-Company Ownership**
   明确 `founder_agent_id`、company lifecycle、company-region semantics，并把 legacy company API 调整为 target model 的一个子表面。
4. **Unify Inventory/Market Region Semantics**
   把 `company_id / agent_id / region_id` 三元 owner 语义贯穿 inventory、orders、trades、transport。
5. **Freeze Contract Layer**
   先完成 `#81/#82` 的最小版，不再让 auth、MCP transport、error shape 继续漂。
6. **Open The Autonomy Path**
   在 world kernel 稳定后再接 `#64-#71`，确保 autonomy 不是在 stub 世界里“自嗨”。

---

## Layer 0: Foundation (阻塞型, 1 CC)

| Issue | Title | Status | Files |
|-------|-------|--------|-------|
| [#16](https://github.com/zp184764679/agentropolis/issues/16) | Model Layer Overhaul + Config + Schemas + Auth | ⬜ CREATED | 13 new + 10 modified + 4 non-model |

> **必须先完成 #16，其余所有 issue 依赖它**

---

## Layer 1: Services (13 并行 tracks + #23 orchestrator)

### Core Services (7)

| Issue | Title | Status | Depends On | Key File |
|-------|-------|--------|------------|----------|
| [#17](https://github.com/zp184764679/agentropolis/issues/17) | Inventory Service | ⬜ CREATED | #16 | `services/inventory_svc.py` |
| [#18](https://github.com/zp184764679/agentropolis/issues/18) | Company Service | ⬜ CREATED | #16, #17 | `services/company_svc.py` |
| [#19](https://github.com/zp184764679/agentropolis/issues/19) | NPC Consumption | ⬜ CREATED | #16, #17 | `services/consumption.py` |
| [#20](https://github.com/zp184764679/agentropolis/issues/20) | Production Service | ⬜ CREATED | #16, #17, #19 | `services/production.py` |
| [#21](https://github.com/zp184764679/agentropolis/issues/21) | Market Engine | ⬜ CREATED | #16, #17, #18 | `services/market_engine.py` |
| [#22](https://github.com/zp184764679/agentropolis/issues/22) | Leaderboard | ⬜ CREATED | #16 | `services/leaderboard.py` |
| [#23](https://github.com/zp184764679/agentropolis/issues/23) | Game Engine | ⬜ CREATED | #16-#22 all | `services/game_engine.py` + `main.py` |

### World Services (3)

| Issue | Title | Status | Depends On | Key File |
|-------|-------|--------|------------|----------|
| [#24](https://github.com/zp184764679/agentropolis/issues/24) | Agent Service + Vitals | ⬜ CREATED | #16, #17 | `services/agent_svc.py` + `agent_vitals.py` |
| [#25](https://github.com/zp184764679/agentropolis/issues/25) | World Service + Seed World | ⬜ CREATED | #16 | `services/world_svc.py` + `seed_world.py` |
| [#26](https://github.com/zp184764679/agentropolis/issues/26) | Skill Service | ⬜ CREATED | #16 | `services/skill_svc.py` + `seed.py` |

### Economy Services (1)

| Issue | Title | Status | Depends On | Key File |
|-------|-------|--------|------------|----------|
| [#27](https://github.com/zp184764679/agentropolis/issues/27) | Transport + Tax + NPC Shop | ⬜ CREATED | #16, #17, #25 | `transport_svc.py` + `tax_svc.py` + `npc_shop_svc.py` |

### Social Services (1)

| Issue | Title | Status | Depends On | Key File |
|-------|-------|--------|------------|----------|
| [#28](https://github.com/zp184764679/agentropolis/issues/28) | Guild + Diplomacy | ⬜ CREATED | #16, #24 | `guild_svc.py` + `diplomacy_svc.py` |

### Event Services (1)

| Issue | Title | Status | Depends On | Key File |
|-------|-------|--------|------------|----------|
| [#29](https://github.com/zp184764679/agentropolis/issues/29) | World Events + Currency | ⬜ CREATED | #16 | `event_svc.py` + `currency_svc.py` |

### NXC Services (1)

| Issue | Title | Status | Depends On | Key File |
|-------|-------|--------|------------|----------|
| [#38](https://github.com/zp184764679/agentropolis/issues/38) | NXC Mining Service | ⬜ CREATED | #16, #20 | `services/nxc_mining_svc.py` |

---

## Layer 2: API Routes (并行, 5 CC)

| Issue | Title | Status | Depends On | Key File |
|-------|-------|--------|------------|----------|
| [#30](https://github.com/zp184764679/agentropolis/issues/30) | Agent + World Endpoints | ⬜ CREATED | #24, #25, #26 | `api/agent.py` + `api/world.py` |
| [#31](https://github.com/zp184764679/agentropolis/issues/31) | Market + Inventory Endpoints | ⬜ CREATED | #17, #21, #22 | `api/market.py` + `api/inventory.py` |
| [#32](https://github.com/zp184764679/agentropolis/issues/32) | Production + Company Endpoints | ⬜ CREATED | #18, #20 | `api/production.py` + `api/company.py` |
| [#33](https://github.com/zp184764679/agentropolis/issues/33) | Game + Leaderboard Endpoints | ⬜ CREATED | #22, #29 | `api/game.py` |
| [#34](https://github.com/zp184764679/agentropolis/issues/34) | Skills + Transport + Guild + Diplomacy | ⬜ CREATED | #26, #27, #28 | 4 new API files |

---

## Layer 3: Integration (2-3 CC)

| Issue | Title | Status | Depends On | Key File |
|-------|-------|--------|------------|----------|
| [#35](https://github.com/zp184764679/agentropolis/issues/35) | MCP Tools (initial preview baseline; later rewritten to 14 modules / 60 tools) | ⬜ CREATED | All services + APIs | `mcp/` |
| [#36](https://github.com/zp184764679/agentropolis/issues/36) | Test Suite | ⬜ CREATED | All services | `tests/` |
| [#37](https://github.com/zp184764679/agentropolis/issues/37) | CLI + Alembic Migrations | ⬜ CREATED | #16, #25 | `cli.py` + `alembic/` |

---

## Dependency Graph (Execution Order)

```
#16 Foundation ─────────────────────────────────────────────────┐
  │                                                             │
  ├─→ #17 inventory_svc ──┬─→ #18 company_svc ──┐              │
  │                       ├─→ #19 consumption ───┤              │
  │                       ├─→ #21 market_engine ─┤              │
  │                       └─→ #24 agent_svc ─────┤              │
  │                                              │              │
  ├─→ #22 leaderboard ──────────────────────────┤              │
  ├─→ #25 world_svc ─────────────────────────────┤              │
  ├─→ #26 skill_svc ─────────────────────────────┤              │
  ├─→ #29 events+currency ──────────────────────┤              │
  │                                              │              │
  │   #19 consumption ──→ #20 production ────────┤              │
  │   #20 production ───→ #38 nxc_mining_svc ────┤              │
  │   #25 world_svc ────→ #27 transport+tax+shop ┤              │
  │   #24 agent_svc ────→ #28 guild+diplomacy ───┤              │
  │                                              │              │
  │                              #23 game_engine ←┘ (needs all) │
  │                                                             │
  │   ┌─ #30 API agent+world                                   │
  │   ├─ #31 API market+inventory                               │
  ├─→ ├─ #32 API production+company     (after their services) │
  │   ├─ #33 API game+leaderboard                               │
  │   └─ #34 API social+transport                               │
  │                                                             │
  │   ┌─ #35 MCP tools               (after service + API face) │
  │   ├─ #36 Tests                   (after services)           │
  └─→ └─ #37 CLI+Alembic             (after #16 + #25) ────────┘
```

## Optimal Execution Waves

| Wave | Issues | CC Instances | 前置 |
|------|--------|:---:|------|
| **Wave 1** | #16 | 1 | None |
| **Wave 2** | #17, #22, #25, #26, #29, #41 | 6 | #16 done |
| **Wave 3** | #18, #19, #24, #42 | 4 | #17 done |
| **Wave 4** | #20, #21, #27, #28, #39, #40, #45, #46 | 8 | Wave 3 done |
| **Wave 5** | #23, #30-#34, #38, #43, #44, #48, #49, #51, #52, #53, #54, #55 | 14 | respective dependencies done |
| **Wave 6** | #35, #36, #37, #47, #50 | 5 | respective dependencies done |
| **Wave 6.5** | #78 → #79 → #80 | 3 (串行) | #16 done |
| **Wave 7A** | #64, #65, #66, #67 | 4 | Wave 6 done |
| **Wave 7B** | #68, #69, #71 | 3 | Wave 7A done (+ #35 for #69) |
| **Wave 7C** | #70 | 1 | #64 + #68 done |

---

## Cross-Cutting Capability Buckets (Not Yet Mapped To Issue IDs)

> 下列能力对“双目标共享内核”是必要项，但目前尚未单独拆成 issue。它们不是锦上添花，而是外部 AI 接入和长期运营的前置条件。

### 1. Control Contract

- REST/MCP versioning policy
- Freeze one MCP transport contract for external clients
- Idempotency key / retry safety for all state-mutating actions
- Unified error taxonomy: auth, validation, conflict, retryable, rate-limited, degraded
- Migration-phase preview/control-plane failures must expose a stable `X-Agentropolis-Error-Code` header and mirrored JSON `error_code`
- Pagination / cursor contract for high-cardinality feeds
- Partial failure / async acceptance semantics

### 2. AuthZ / Abuse / Budget Guard

- Agent / Company / Guild / Admin 的资源权限边界
- MCP tool scopes and dangerous-operation gating
- Per-agent, per-tool, per-IP quota
- Spending caps, daily/hourly budgets, emergency freeze / read-only mode

### 3. Execution Model

- 明确 request path vs background job vs housekeeping phase
- Retry, dedupe, dead-letter, compensation policy
- Periodic tasks 的 failure handling 与 backfill policy
- 外部 AI 命令的 sync/async acknowledgement 约定

### 4. Observability

- Structured logging
- Request / MCP / housekeeping metrics
- Slow query / queue lag / lock contention visibility
- Economy health dashboard: source/sink, inflation, inventory starvation, stuck orders
- Agent behavior metrics: success rate, tool failure rate, autopilot interventions

### 5. Economy Governance

- Tunable parameter registry
- Feature flags / staged rollout for economy changes
- Balance-change review checklist
- Economic regression scenarios and acceptance thresholds

### 6. State Recovery

- World snapshot / replay
- Backup / restore runbook
- Data repair / backfill scripts
- Migration rollback constraints and irreversible-change policy

### 7. Interface Parity Testing

- REST vs MCP parity tests for shared service functions
- Auth scope coverage tests
- Contract compatibility tests for external clients

## Proposed Control-Plane Backlog (#81+, Not Yet Created)

> 下列编号是建议保留给下一批 cross-cutting issues 的候选 backlog。
> 它们目前**不是**已创建的 GitHub issues，不计入顶部 `Total Issues`，也不能直接 `gh issue view`。
> 作用是把“必须补但尚未 issue 化”的能力，从概念清单收敛成可执行工作包。

### Proposed Issues

| Proposed ID | Title | Scope | Recommended Depends On | Key Files |
|-------------|-------|-------|------------------------|-----------|
| `#81` | Control Contract Baseline | 冻结 MCP transport、REST/MCP versioning、idempotency、error taxonomy、pagination、async acceptance semantics | #16, #30-#35 | `api/schemas.py`, `mcp/server.py`, `main.py`, `README.md` |
| `#82` | Authorization & Tool Scope Model | Agent/Company/Guild/Admin authz、tool scopes、dangerous operation gates | #16, #30-#35, #81 | `api/auth.py`, `deps.py`, `mcp/*`, `api/*` |
| `#83` | Abuse & Budget Guard | quota、per-tool limits、spending caps、kill switch、read-only mode | #78-#80, #82 | `config.py`, `deps.py`, `middleware/*`, `services/*`, `main.py` |
| `#84` | Execution Semantics & Job Model | sync vs async command contract、retry/dedupe/dead-letter、housekeeping failure/backfill policy | #23, #39-#44, #50, #64-#71, #81 | `services/game_engine.py`, `services/*`, `main.py`, `docs/` |
| `#85` | Observability Baseline | structured logs、metrics、traces、queue/lock visibility、economy health dashboard baseline | #23, #78-#80, #84 | `main.py`, `services/game_engine.py`, `services/*`, `config.py` |
| `#86` | Economy Governance & Tunables | parameter registry、feature flags、balance review checklist、economic regression scenarios | #16, #23, #29, #38, #85 | `config.py`, `services/seed.py`, `services/*`, `tests/` |
| `#87` | State Recovery & Repair Tooling | snapshot/replay、backup/restore runbook、repair/backfill scripts、migration rollback policy | #16, #23, #37, #84 | `cli.py`, `alembic/`, `scripts/*`, `services/*` |
| `#88` | REST/MCP Contract Parity Test Suite | parity tests、scope coverage、external client compatibility checks | #81, #82, #84, #85 | `tests/contract/*`, `tests/e2e/*`, `mcp/*`, `api/*` |

### Suggested Sequencing

| Stage | Proposed Issues | Why |
|-------|-----------------|-----|
| **Contract Freeze** | #81, #82 | 先冻结 transport、versioning、permission 语义，避免外部接入前持续漂移 |
| **Safety Layer** | #83, #84 | 把 abuse/budget guard 和执行语义从隐性约定变成系统行为 |
| **Operate Safely** | #85, #86, #87 | 补 observability、调参治理、事故恢复 |
| **Prove Consistency** | #88 | 用 parity tests 把 REST/MCP/shared service 三层绑紧 |

### Rollout Policy

- `#72-#77 OpenClaw Integration` 可以在 `#81-#84` 之前做本地原型联调
- 面向外部玩家、持续运行 agent、公开文档承诺前，至少应完成 `#81`, `#82`, `#83`, `#85`, `#87`, `#88`
- 若 `#84` 未完成，所有 async/周期任务语义只能视为实验性，不应对外承诺稳定行为

### Draft Issue Specs

Detailed draft files also exist under `.github/` for copy-paste into GitHub:
- `issue_control_contract_baseline.md`
- `issue_authorization_tool_scopes.md`
- `issue_abuse_budget_guard.md`
- `issue_execution_semantics_jobs.md`
- `issue_observability_baseline.md`
- `issue_economy_governance.md`
- `issue_state_recovery.md`
- `issue_contract_parity_tests.md`

#### Draft `#81` — Control Contract Baseline

- **Goal**: 冻结外部客户端的最小稳定契约，避免 REST/MCP transport、错误语义、幂等等核心行为持续漂移。
- **In Scope**: 选定单一 MCP transport；定义 API/MCP versioning；为所有 state-mutating actions 规定 idempotency 行为；统一 error taxonomy；定义 pagination / async acceptance contract；更新 README 与接入文档。
- **Out Of Scope**: 新增业务玩法；扩大量工具数量；引入复杂 RBAC 细节。
- **Acceptance**:
  - 存在一份对外 contract spec，覆盖 REST 与 MCP
  - README、PLAN、实现入口对 MCP transport 的表述一致
  - 所有写操作都标注 idempotent / non-idempotent / async accepted 语义
  - error code / error shape 可被外部客户端稳定消费

#### Draft `#82` — Authorization & Tool Scope Model

- **Goal**: 把“能连上 API key”提升为“有明确资源边界和 tool scope 的权限系统”。
- **In Scope**: Agent / Company / Guild / Admin actor model；acting-as 规则；REST route scopes；MCP tool scopes；dangerous-operation confirmation / gating；权限拒绝错误模型。
- **Out Of Scope**: 细粒度组织后台；复杂 UI 权限面板。
- **Acceptance**:
  - 关键资源都有 owner / actor / allowed action 定义
  - MCP tools 不再默认“有 key 就全能调用”
  - 至少覆盖交易、生产、运输、公会、运维级操作的 scope
  - 存在 scope coverage tests

#### Draft `#83` — Abuse & Budget Guard

- **Goal**: 为持续运行的外部 AI 加上配额、预算和紧急制动，避免错误 agent 把世界或账本打穿。
- **In Scope**: per-agent / per-tool / per-IP quota；spending caps；budget exhaustion behavior；kill switch；read-only / degraded mode；unsafe operation denylist。
- **Out Of Scope**: 完整风控平台；复杂信誉分系统。
- **Acceptance**:
  - 可以对单 agent 或单 tool 执行限流和封禁
  - 可配置预算上限触发阻断而非静默失败
  - 存在全局只读或外部接入熔断开关
  - 有针对 429 / 403 / degraded mode 的集成测试

#### Draft `#84` — Execution Semantics & Job Model

- **Goal**: 把命令执行、housekeeping、周期任务、失败补偿这些隐性机制显式化，避免客户端和服务端对时序理解不一致。
- **In Scope**: sync vs async command contract；accepted/pending/completed/failed 状态语义；retry / dedupe / dead-letter policy；housekeeping failure handling；backfill rules；周期任务的 observability hooks。
- **Out Of Scope**: 引入大型消息队列平台；完整 workflow engine。
- **Acceptance**:
  - 文档能明确回答“一个调用什么时候算成功”
  - 周期任务失败后有 retry 或人工修复路径
  - housekeeping 不再是黑盒 sweep，而有 phase-level result contract
  - async/周期任务语义在 REST 与 MCP 中一致

当前 repo 基线已经落到：
- `/meta/execution` 提供显式 job model、retry/backfill policy、recent jobs、latest phase results
- housekeeping log 记录 `trigger_kind`、`execution_job_id`、`phase_results`
- admin-only async acceptance 固定在 `/meta/execution/jobs/*`
- missed housekeeping intervals 会按 `game_state.last_tick_at` 自动回填，并受 `EXECUTION_MAX_BACKFILL_SWEEPS` 限制

#### Draft `#85` — Observability Baseline

- **Goal**: 让系统能被运营、排障和调优，而不是只靠日志 grep。
- **In Scope**: structured logs；request / MCP / housekeeping metrics；queue lag / lock contention / slow query visibility；economy health 指标；agent behavior / autopilot intervention metrics；最小告警基线。
- **Out Of Scope**: 完整 BI 平台；复杂商业报表。
- **Acceptance**:
  - 关键请求和后台任务都有统一 trace/log context
  - 至少能观察 API 错误率、MCP 调用失败率、housekeeping 时长、锁冲突、经济失衡指标
  - 有最小 dashboard 或导出接口供外部监控系统采集
  - rollout gate 可基于指标判断是否放量

#### Draft `#86` — Economy Governance & Tunables

- **Goal**: 把经济平衡从“改 seed / 改常量”升级为“可治理、可回滚、可评审”的参数系统。
- **In Scope**: tunable parameter registry；feature flags；balance change checklist；经济回归场景；source/sink 健康阈值；主要参数的 owner 说明。
- **Out Of Scope**: 自动调参 AI；复杂 live-ops 后台。
- **Acceptance**:
  - 核心经济参数有集中登记和默认值来源
  - 经济改动可以分阶段 rollout
  - 至少有一组经济回归测试场景
  - source/sink / inflation / starvation 等关键指标有验收阈值

#### Draft `#87` — State Recovery & Repair Tooling

- **Goal**: 当经济状态、周期任务或数据迁移出问题时，有恢复和修复手段，而不是只能手改数据库。
- **In Scope**: snapshot / replay strategy；backup / restore runbook；repair/backfill scripts；migration rollback constraints；不可逆变更清单；最小事故演练文档。
- **Out Of Scope**: 跨地域灾备；企业级 RPO/RTO 承诺。
- **Acceptance**:
  - 存在至少一条可执行的备份恢复路径
  - 可以重放或补算关键 housekeeping / market / economy 状态
  - 迁移和 backfill 有明确安全边界
  - 发生数据漂移时有 documented repair flow

#### Draft `#88` — REST/MCP Contract Parity Test Suite

- **Goal**: 用测试锁住“同一 service、双接口”的承诺，避免 REST 和 MCP 各自漂移。
- **In Scope**: REST/MCP parity tests；auth scope coverage；contract compatibility fixtures；关键读写路径的 golden test cases；外部 client smoke tests。
- **Out Of Scope**: 全量 UI 测试；非关键路径的 exhaustive fuzzing。
- **Acceptance**:
  - 至少覆盖交易、库存、生产、旅行、通知、策略配置等主路径
  - 同一操作经 REST 与 MCP 触发时，状态变化和错误语义一致
  - contract-breaking change 能在 CI 中直接暴露
  - OpenClaw 接入 smoke tests 复用同一套 contract fixture

---

## File Ownership (防冲突)

> 默认每个 issue 只修改自己的主文件。
> 只有在下文明确标注 `extend` / `integration` / `upgrade` / `rewrite` / `shared owner` 的共享文件，才允许跨 issue 修改。
> 未在 PLAN 中显式声明的跨文件改动，一律视为越界。

| File | Owner Issue |
|------|-------------|
| `models/*` (all) | #16 |
| `config.py` | #16 |
| `api/schemas.py` | #16 |
| `api/auth.py` | #16 |
| `deps.py` | #16 |
| `services/inventory_svc.py` | #17 |
| `services/company_svc.py` | #18 |
| `services/consumption.py` | #19 |
| `services/production.py` | #20 |
| `services/market_engine.py` | #21 |
| `services/leaderboard.py` | #22 |
| `services/game_engine.py` | #23 |
| `services/agent_svc.py` | #24 |
| `services/agent_vitals.py` | #24 |
| `services/world_svc.py` | #25 |
| `services/seed_world.py` | #25 |
| `services/skill_svc.py` | #26 |
| `services/seed.py` (skill defs) | #26 |
| `services/transport_svc.py` | #27 |
| `services/tax_svc.py` | #27 |
| `services/npc_shop_svc.py` | #27 |
| `services/guild_svc.py` | #28 |
| `services/diplomacy_svc.py` | #28 |
| `services/event_svc.py` | #29 |
| `services/currency_svc.py` | #29 |
| `models/nexus_state.py` | #16 |
| `services/nxc_mining_svc.py` | #38 |
| `api/agent.py` | #30 |
| `api/world.py` | #30 |
| `api/market.py` | #31 |
| `api/inventory.py` | #31 |
| `api/production.py` | #32 |
| `api/company.py` | #32 |
| `api/game.py` | #33 |
| `api/skills.py` | #34 |
| `api/transport.py` | #34 |
| `api/guild.py` | #34 |
| `api/diplomacy.py` | #34 |
| `main.py` (routers) | #23, #30, #34 |
| `mcp/*` | #35 |
| `tests/*` | #36 |
| `cli.py` + `alembic/` | #37 |

### Shared / Explicit Exceptions

| File | Shared Owner / Allowed Follow-up Issues |
|------|-----------------------------------------|
| `models/agent.py` | #16 base; #56, #64, #66 add relationships |
| `models/__init__.py` | #16 base; #56, #64, #66 register new models/enums |
| `config.py` | #16 base; #56, #64, #78 add scoped settings |
| `api/schemas.py` | #16 base; #56 extend training-related schemas |
| `services/game_engine.py` | #23 base; #39, #40, #41, #42, #43, #44, #50, #57, #58, #71 add housekeeping/training phases |
| `main.py` | #23/#30/#34 base; #56, #65, #67, #68, #70, #80 add routers/middleware/handlers |
| `deps.py` | #16 base; #78 add concurrency hooks |
| `mcp/*` | #35 base; #69 upgrade AI core interface; #72 expand/rewrite agent-centric tool surface; #74 update `mcp/server.py` |

---

## NXC (Nexus Crystal) 经济系统

> Bitcoin 式稀缺代币驱动一切经济行为。终极产业链输出。

### 核心参数

| 参数 | 值 |
|------|-----|
| 硬顶 | 21,000,000 NXC |
| 精炼输入 | STL:3 + MCH:1 + C:5 |
| 精炼周期 | 300 秒 (5 分钟) |
| 初始基础产出 | 50 NXC/周期 (独自精炼时) |
| 减半间隔 | 2016 周期 = 168h = 1 周 |
| 精炼厂成本 | 50,000,000 copper + BLD:20 + MCH:10 |
| 精炼厂技能要求 | Engineering Lv3 |
| 目标排放/小时 | 100 NXC |

### NXC 消耗池 (Sinks)

| 场景 | NXC 数量 | 效果 |
|------|---------|------|
| 创建公会 | 50 NXC | 公会成立门槛 |
| 解锁高级建筑 | 10-100 NXC | 精英建筑需要 NXC |
| 解锁传奇技能(Lv5) | 25 NXC | 技能系统终极升级 |
| 区域控制权(未来) | 100 NXC/周 | 地盘争夺 |

### 对各 Issue 的影响

| Issue | NXC 相关变更 |
|-------|-------------|
| **#16** | +NexusCrystalState 模型, +ResourceCategory.CURRENCY, +nxc_cost 字段, +NXC 种子数据 |
| **#20** | settle_building 对 nexus_refinery 做特殊处理, 调用 nxc_mining_svc.calculate_nxc_yield |
| **#22** | 新增 NXC 排行榜 (主排行榜按 NXC 持有量) |
| **#23** | housekeeping 新增: 难度调节 + 减半检查 + active_refineries 更新 |
| **#26** | Engineering Lv5 解锁需消耗 NXC (25 NXC) |
| **#28** | 创建公会需消耗 NXC (50 NXC) |
| **#38** | 产出计算, 难度调节, 减半, 硬顶, 全局状态查询 |

---

## Layer 1.5: Design Gap Issues (#39-#55)

> 对比 PrUn、EVE Online 等经济模拟游戏审查后发现的 17 个设计缺口。代码 stub 已创建。

### P0 — 经济循环完整性

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#39](https://github.com/zp184764679/agentropolis/issues/39) | Employment & Wages | ⬜ CREATED | #16,#17,#18,#24 | `services/employment_svc.py` |
| [#40](https://github.com/zp184764679/agentropolis/issues/40) | Player Contract (Escrow) | ⬜ CREATED | #16,#17,#24 | `models/player_contract.py`, `services/contract_svc.py` |
| [#41](https://github.com/zp184764679/agentropolis/issues/41) | Notification & Event Feed | ⬜ CREATED | #16 only | `models/notification.py`, `services/notification_svc.py` |
| [#42](https://github.com/zp184764679/agentropolis/issues/42) | Perishable Goods Decay | ⬜ CREATED | #16,#17 | `services/decay_svc.py` |

### P1 — 深度与平衡

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#43](https://github.com/zp184764679/agentropolis/issues/43) | Event Effects Application | ⬜ CREATED | #16,#29 | `services/event_svc.py` (extend) |
| [#44](https://github.com/zp184764679/agentropolis/issues/44) | Building Natural Decay | ⬜ CREATED | #16,#20 | `services/maintenance_svc.py` |
| [#45](https://github.com/zp184764679/agentropolis/issues/45) | Agent Direct Trade | ⬜ CREATED | #16,#17,#24 | `services/direct_trade_svc.py` |
| [#46](https://github.com/zp184764679/agentropolis/issues/46) | Reputation Effects | ⬜ CREATED | #16,#24 | `services/reputation_svc.py` |
| [#47](https://github.com/zp184764679/agentropolis/issues/47) | NPC Shop Dynamic Pricing | ⬜ CREATED | #16,#27,#46 | `services/npc_shop_svc.py` (extend) |

### P2 — 丰富度

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#48](https://github.com/zp184764679/agentropolis/issues/48) | Agent Carry Capacity | ⬜ CREATED | #16,#25,#26 | `services/world_svc.py` (extend) |
| [#49](https://github.com/zp184764679/agentropolis/issues/49) | Treaty Mechanical Effects | ⬜ CREATED | #16,#28 | `services/treaty_effects_svc.py` |
| [#50](https://github.com/zp184764679/agentropolis/issues/50) | Regional Infrastructure | ⬜ CREATED | #16,#25,#27 | `models/regional_project.py`, `services/regional_project_svc.py` |
| [#51](https://github.com/zp184764679/agentropolis/issues/51) | Multi-tier Workforce | ⬜ CREATED | #16,#17,#18,#19 | `models/company.py`, `services/consumption.py` (extend) |
| [#52](https://github.com/zp184764679/agentropolis/issues/52) | Market Order Type | ⬜ CREATED | #16,#21 | `models/order.py`, `services/market_engine.py` (extend) |
| [#53](https://github.com/zp184764679/agentropolis/issues/53) | Guild Level & Upgrade | ⬜ CREATED | #16,#28 | `services/guild_svc.py` (extend) |

### P3 — 未来

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#54](https://github.com/zp184764679/agentropolis/issues/54) | Career Path Effects | ⬜ CREATED | #16,#24,#26 | `services/career_svc.py` |
| [#55](https://github.com/zp184764679/agentropolis/issues/55) | Storage Capacity Limits | ⬜ CREATED | #16,#17 | `services/storage_svc.py` |

### Design Gap 依赖图

```
#16 ─── #41 Notifications (无其他依赖，最早开始)
  │
  ├── #17 ─── #42 Perishable Decay
  │     ├── #18 + #24 ─── #39 Employment
  │     │            ├─── #40 Contracts
  │     │            ├─── #45 Direct Trade
  │     │            └─── #46 Reputation ──→ #47 NPC Dynamic Pricing
  │     ├── #25 + #26 ─── #48 Carry Capacity
  │     ├── #27 ──────── #47 NPC Dynamic Pricing
  │     ├── #28 ──────── #49 Treaty Effects / #53 Guild Levels
  │     ├── #29 ──────── #43 Event Effects
  │     ├── #20 ──────── #44 Building Decay
  │     ├── #19 ──────── #51 Multi-tier Workforce
  │     └── #21 ──────── #52 Market Orders
  ├── #25 + #27 ──── #50 Regional Projects
  ├── #24 + #26 ──── #54 Career Paths
  └── #17 ─────────── #55 Storage Capacity
```

### Design Gap 文件所有权

| File | Owner Issue |
|------|-------------|
| `services/employment_svc.py` | #39 |
| `models/player_contract.py` | #40 |
| `services/contract_svc.py` | #40 |
| `models/notification.py` | #41 |
| `services/notification_svc.py` | #41 |
| `services/decay_svc.py` | #42 |
| `services/maintenance_svc.py` | #44 |
| `services/direct_trade_svc.py` | #45 |
| `services/reputation_svc.py` | #46 |
| `services/treaty_effects_svc.py` | #49 |
| `models/regional_project.py` | #50 |
| `services/regional_project_svc.py` | #50 |
| `services/career_svc.py` | #54 |
| `services/storage_svc.py` | #55 |

### Design Gap 共享扩展文件

| File | Shared Owner / Allowed Follow-up Issues |
|------|-----------------------------------------|
| `services/event_svc.py` | #29 base; #43 extension |
| `services/npc_shop_svc.py` | #27 base; #47 extension |
| `services/world_svc.py` | #25 base; #48 extension |
| `models/company.py` | #16 base; #51 extension |
| `services/consumption.py` | #19 base; #51 extension |
| `services/market_engine.py` | #21 base; #52 extension |
| `services/guild_svc.py` | #28 base; #53 extension |
| `services/game_engine.py` | #23 base; #39, #40, #41, #42, #43, #44, #50 integrate housekeeping hooks |

### Housekeeping 新增步骤 (game_engine.py)

现有 10 步 + 新增 7 步:

| # | 函数 | Owner |
|---|------|-------|
| 11 | `settle_all_wages()` | #39 |
| 12 | `expire_contracts()` | #40 |
| 13 | `prune_old_notifications()` | #41 |
| 14 | `settle_all_perishable_decay()` | #42 |
| 15 | `apply_active_event_effects()` | #43 |
| 16 | `settle_all_building_decay()` | #44 |
| 17 | `settle_project_completions()` | #50 |

---

## Training System — 让"调教AI"成为核心玩法

> 给 Agent 添加可配置策略、决策日志、行为特质三层系统，让同等级的 Agent 因玩家策略差异产生截然不同的表现。
> 注: #56-#58 当前状态表示“原型代码已完成”; 若在主线重放执行，仍以 #16 Foundation 为集成基底。

### Issues

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#56](https://github.com/zp184764679/agentropolis/issues/56) | Strategy Profile — 教条配置与机械效果 | ✅ DONE | #16 | `models/strategy_profile.py`, `services/strategy_svc.py`, `api/strategy.py` |
| [#57](https://github.com/zp184764679/agentropolis/issues/57) | Decision Journal — 决策日志与复盘分析 | ✅ DONE | #16, #56 | `models/decision_log.py`, `services/decision_log_svc.py`, `services/training_hooks.py`, `api/decisions.py` |
| [#58](https://github.com/zp184764679/agentropolis/issues/58) | Agent Traits — 行为特质与荣誉系统 | ✅ DONE | #16, #57 | `models/agent_trait.py`, `services/trait_svc.py` |

### 执行顺序

```
#56 Strategy Profile → #57 Decision Journal → #58 Agent Traits
(串行：B 依赖 A 的 model，C 依赖 B 的 decision_log)
```

### File Ownership (Training System)

| File | Owner Issue |
|------|-------------|
| `models/strategy_profile.py` | #56 |
| `services/strategy_svc.py` | #56 |
| `api/strategy.py` | #56 |
| `models/decision_log.py` | #57 |
| `services/decision_log_svc.py` | #57 |
| `services/training_hooks.py` | #57 |
| `api/decisions.py` | #57 |
| `models/agent_trait.py` | #58 |
| `services/trait_svc.py` | #58 |

### 集成点汇总

- **models/agent.py**: `strategy_profile`, `decision_logs`, `traits` 三个 relationship
- **models/__init__.py**: 注册 StrategyProfile, AgentDecisionLog, AgentTrait + 相关 enums
- **services/warfare_svc.py**: `_gather_combat_modifiers()` 汇集教条+特质修正
- **services/game_engine.py**: Phase E — `resolve_pending_decisions` (每轮) + `evaluate_agent_traits` (每10轮)
- **api/schemas.py**: StrategyProfile*, DecisionLog*, AgentTrait*, AgentPublicProfile schemas
- **config.py**: DECISION_RESOLVE_DELAY_SECONDS, DECISION_MAX_RESOLVE_BATCH, TRAIT_DECAY_DAYS
- **main.py**: strategy_router, decisions_router

---

## Autonomy Engine — AI 自主行为引擎 (#64-#71)

> 混合架构 (方案 C): 服务器做规则执行和数据聚合，所有"聪明的事"由玩家的 AI 完成。
> 目标客群: OpenClaw 用户（有自己 Claude/GPT agent 的玩家）。
> 核心体验: 玩家的 AI 通过 MCP tools 操控游戏中的 agent，24/7 自主决策。

### 架构

```
┌─────────────────────────────┐
│  玩家的 AI Agent (Claude)    │  ← 智能决策层 (客户端)
│  - 分析市场、规划路线        │
│  - 决定买卖、生产、旅行      │
│  - 设定 standing orders      │
└──────────┬──────────────────┘
           │ MCP core tools (38) / REST API
           ▼
┌─────────────────────────────┐
│    Agentropolis Server       │  ← 世界引擎 (服务器)
│  - World Engine (经济/物理)   │
│  - Autopilot (兜底生存)      │
│  - Digest Service (事件汇总) │
└─────────────────────────────┘
```

### Issues

#### P0 — 核心

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#64](https://github.com/zp184764679/agentropolis/issues/64) | Server Autopilot — Reflex + Standing Orders | ⬜ CREATED | #16,#17,#24,#27 | `models/autonomy.py`, `services/autopilot.py` |
| [#65](https://github.com/zp184764679/agentropolis/issues/65) | Rich Information APIs — AI Decision Data | ⬜ CREATED | #17,#21,#22,#25 | `services/market_analysis_svc.py`, `api/market_analysis.py` |
| [#67](https://github.com/zp184764679/agentropolis/issues/67) | Activity Digest / Morning Briefing | ⬜ CREATED | #57,#41,#22,#29 | `services/digest_svc.py`, `api/digest.py` |
| [#69](https://github.com/zp184764679/agentropolis/issues/69) | MCP Tool Suite — AI Agent Core Interface | ⬜ CREATED | #35, all services | `mcp/*` |

#### P1 — 控制

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#66](https://github.com/zp184764679/agentropolis/issues/66) | Goal Tracking System | ⬜ CREATED | #16,#17,#26 | `models/autonomy.py`, `services/goal_svc.py` |
| [#68](https://github.com/zp184764679/agentropolis/issues/68) | Autonomy Config API | ⬜ CREATED | #64 | `api/autonomy.py` |
| [#71](https://github.com/zp184764679/agentropolis/issues/71) | Housekeeping Integration | ⬜ CREATED | #23,#64,#66 | `services/game_engine.py` |

#### P2 — 深度

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#70](https://github.com/zp184764679/agentropolis/issues/70) | Real-time Activity Dashboard API | ⬜ CREATED | #64,#68 | `api/dashboard.py` |

### 执行波次

| Wave | Issues | CC 数 | 前置 |
|------|--------|:---:|------|
| **Wave A** (基础) | #64 Autopilot + #65 Info APIs + #66 Goals + #67 Digest | 4 | 各自依赖的服务 |
| **Wave B** (控制) | #68 Config API + #69 MCP Tools + #71 Integration | 3 | Wave A (+ #35 for #69) |
| **Wave C** (深度) | #70 Dashboard | 1 | #64 + #68 |

### 文件所有权

| File | Owner Issue |
|------|-------------|
| `models/autonomy.py` | #64, #66 |
| `services/autopilot.py` | #64 |
| `services/market_analysis_svc.py` | #65 |
| `api/market_analysis.py` | #65 |
| `models/autonomy.py` (goals) | #66 |
| `services/goal_svc.py` | #66 |
| `services/digest_svc.py` | #67 |
| `api/digest.py` | #67 |
| `api/autonomy.py` | #68 |
| `mcp/*` (升级) | #69 |
| `api/dashboard.py` | #70 |
| `services/game_engine.py` | #23 base; #71 autonomy integration |

### Housekeeping 新增步骤 (#71)

| Phase | 函数 | 频率 | Owner |
|-------|------|------|-------|
| A | `run_all_reflexes()` | 每轮 | #64 |
| S | `run_all_standing_orders()` | 每5轮 | #64 |
| G | `compute_all_goal_progress()` | 每30轮 | #66 |
| D | Digest data aggregation | 每轮 | #67 |

### 当前实现口径（P5 本地预览）

- `AutonomyState.standing_orders` 是唯一真源；`StrategyProfile.standing_orders` 仅保留为公开 scouting mirror
- Standing orders 当前只支持 `buy_rules` / `sell_rules`
- `source="npc"` 等未支持规则必须稳定失败，不能静默降级
- `#69` 先落本地预览 MCP core surface；`#72` 现已重排为 repo-truthful 的 14 模块 / 60 tools 本地原型，并固定 `streamable-http`，不再保留旧的 strict-55 / SSE 口径

### 集成点

- **models/agent.py**: `autonomy_state`, `goals` 两个 relationship
- **models/__init__.py**: 注册 AutonomyState, AgentGoal, GoalType, GoalStatus
- **config.py**: AUTOPILOT_* 配置项
- **main.py**: autonomy_router, dashboard_router, digest_router, market_analysis_router

---

## Layer 4: OpenClaw Integration (3-4 CC)

> 让 OpenClaw 代理能作为 Agentropolis Agent 完整参与世界。面向外部玩家，非自用。
> 本层允许在本地或封闭环境先做联调原型，但外部公开接入必须满足上文 `External Rollout Gate`。

### Core Integration

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#72](https://github.com/zp184764679/agentropolis/issues/72) | MCP Tools Expansion — Repo-Truthful 14 Modules / 60 Tools | ⬜ CREATED | #30-#34 (all APIs) | `mcp/*` (14 tool modules) |
| [#73](https://github.com/zp184764679/agentropolis/issues/73) | Agentropolis World Skill — MCP-First With Mounted REST Fallback | ⬜ CREATED | #30-#34 | `skills/agentropolis-world/SKILL.md` + `references/*` |
| [#74](https://github.com/zp184764679/agentropolis/issues/74) | Agent Brain Decision Framework — System Prompt | ⬜ CREATED | #72 | `prompts/agent-brain.md`, `mcp/server.py` |
| [#75](https://github.com/zp184764679/agentropolis/issues/75) | OpenClaw Configuration Templates & Registration Flow | ⬜ CREATED | #72 | `openclaw/*` |

### Deployment & Testing

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#76](https://github.com/zp184764679/agentropolis/issues/76) | Multi-Agent Deployment Orchestration | ⬜ CREATED | #75 | `docker-compose.multi-agent.yml`, `scripts/*` |
| [#77](https://github.com/zp184764679/agentropolis/issues/77) | End-to-End Integration Test — Full Agent Lifecycle | ⬜ CREATED | #72, #74 | `tests/e2e/*` |

### File Ownership

| File | Owner Issue |
|------|-------------|
| `mcp/tools_agent.py` | #72 |
| `mcp/tools_world.py` | #72 |
| `mcp/tools_market.py` | #72 (rewrite from #35) |
| `mcp/tools_production.py` | #72 (rewrite from #35) |
| `mcp/tools_inventory.py` | #72 (rewrite from #35) |
| `mcp/tools_company.py` | #72 (rewrite from #35) |
| `mcp/tools_intel.py` | #72 (rewrite from #35) |
| `mcp/tools_npc.py` | #72 |
| `mcp/tools_social.py` | #72 |
| `mcp/tools_transport.py` | #72 |
| `mcp/tools_warfare.py` | #72 |
| `mcp/tools_strategy.py` | #72 |
| `mcp/tools_notifications.py` | #72 |
| `mcp/tools_skills.py` | #72 |
| `mcp/server.py` | #72 + #74 |
| `skills/agentropolis-world/SKILL.md` | #73 |
| `skills/agentropolis-world/references/tool-matrix.md` | #73 |
| `skills/agentropolis-world/references/rest-fallback-map.md` | #73 |
| `prompts/agent-brain.md` | #74 |
| `openclaw/*` | #75 |
| `docker-compose.multi-agent.yml` | #76 |
| `scripts/register_agents.py` | #76 |
| `scripts/monitor_agents.py` | #76 |
| `tests/e2e/*` | #77 |

### Dependency Graph

```
#30-#34 APIs ──→ #72 MCP Tools (60 tools) ──→ #74 Agent Brain
                  │                              │
                  └──→ #73 SKILL.md              └──→ #75 OpenClaw Config ──→ #76 Multi-Agent Deploy
                                                       │
                                                       └──→ #77 E2E Tests
```

### Execution Waves (追加)

| Wave | Issues | CC 数 | 前置 |
|------|--------|:---:|------|
| **OpenClaw Wave 1** | #72, #73 | 2 | Wave 5 (APIs) done; 仅限本地/封闭环境原型 |
| **OpenClaw Wave 2** | #74, #75 | 2 | #72 done |
| **OpenClaw Wave 3** | #76, #77 | 2 | #75 done (#77 另外需要 #74); 外部 rollout 仍受 gate 约束 |

### Wave 1 Repo-Truth Rules

- `streamable-http` 是唯一 MCP transport；不再保留 `/mcp/sse` 或 dual-transport 口径
- `mcp/server.py` 继续采用静态注册；runtime metadata、测试、文档都要以这份静态注册表为准
- `#72` 的完成定义是 repo-truthful 的 14 模块 / 60 tools 本地预览面，不要求兼容早期 38-tool 命名
- auth split 固定为：
  - `agent_api_key`: `agent/world/company/transport/skills/social/warfare/strategy/notifications/intel`
  - `company_api_key`: `inventory/market/production`
- `npc` 与 `notifications` 当前允许作为 MCP-only local-preview groups 存在，不要求同步挂载 REST route
- `#73` 的 skill 保持简洁，MCP-first；只对当前已挂载的 REST 前缀声明 fallback，不在本波次增加 `agents/openai.yaml`
- `#74-#77` 的当前 repo 目标是“本地/封闭环境可验证的 OpenClaw 原型资产”，包括 prompt、模板、注册 manifest、monitor snapshot、compose 与 e2e；这仍然不等于 public rollout
- 当前 repo 也允许顺手补 proposed `#86/#87` 的最小基线：tunables registry、world snapshot、derived-state repair；这些是 rollout gate 的前置资产，不代表完整 live-ops 平台已完成
- 当前 repo 也允许顺手补 proposed `#85` 的最小观测面：`/meta/observability` 可提供进程内 request metrics、economy health summary、latest housekeeping snapshot；这仍不是完整生产级 telemetry
- 当前 repo 也允许把 rollout gate 进一步具体化为 `/meta/rollout-readiness`、contract snapshot、gate-check 脚本和 operator runbook；这样每一轮外部接入原型都能自检而不是凭记忆判断
- 当前 repo 也允许继续把这些资产打包成 review bundle，作为封闭环境验收和后续 GitHub 审查输入；bundle 至少应包含 contract snapshot、alerts snapshot、observability snapshot、rollout readiness、gate summary、world snapshot；这属于 rollout scaffolding，不改变玩法面

### MCP Tool 清单 (60 tools, repo-truthful local preview)

| 模块 | Tool 数 | Auth 模式 | 说明 |
|------|---------|-----------|------|
| `tools_agent.py` | 6 | public + agent | `register_agent`, `get_agent_status`, `eat`, `drink`, `rest`, `get_agent_profile` |
| `tools_world.py` | 5 | agent | `get_world_map`, `get_region_info`, `get_route`, `start_travel`, `get_travel_status` |
| `tools_inventory.py` | 3 | company + public | `get_inventory`, `get_inventory_item`, `get_resource_info` |
| `tools_market.py` | 8 | company | `get_market_prices`, `get_order_book`, `get_price_history`, `get_trade_history`, `place_buy_order`, `place_sell_order`, `cancel_order`, `get_my_orders` |
| `tools_npc.py` | 2 | agent | `list_region_shops`, `get_shop_effective_prices`; 当前仅 MCP local-preview |
| `tools_production.py` | 5 | company | `get_recipes`, `get_building_types`, `build_building`, `start_production`, `stop_production` |
| `tools_company.py` | 4 | agent | `create_company`, `get_company`, `get_company_workers`, `get_company_buildings` |
| `tools_transport.py` | 3 | agent | `create_transport`, `get_transport_status`, `get_my_transports` |
| `tools_skills.py` | 2 | agent | `get_skill_definitions`, `get_my_skills` |
| `tools_social.py` | 7 | agent | `create_guild`, `get_guild`, `list_guilds`, `join_guild`, `leave_guild`, `treaty_tool`, `relationship_tool` |
| `tools_warfare.py` | 4 | agent | `create_contract`, `list_contracts`, `contract_action_tool`, `get_region_threats` |
| `tools_strategy.py` | 4 | agent | `strategy_profile_tool`, `autonomy_tool`, `digest_tool`, `briefing_tool` |
| `tools_notifications.py` | 2 | agent | `get_notifications`, `mark_notification_read`; 当前仅 MCP local-preview |
| `tools_intel.py` | 5 | public + agent | `get_market_intel`, `get_route_intel`, `get_opportunities`, `get_game_status`, `get_leaderboard` |
| **总计** | **60** | mixed | 14 个静态模块；`npc` / `notifications` 当前无 mounted REST fallback |

### Grouped Tool Notes

- `treaty_tool(action=propose|accept|list)`
- `relationship_tool(action=list|set)`
- `contract_action_tool(action=get|enlist|activate|cancel|execute)`
- `strategy_profile_tool(action=get|update|scout)`
- `autonomy_tool(action=get_config|update_config|get_standing_orders|update_standing_orders|list_goals|create_goal|update_goal)`
- `digest_tool(action=get|ack)`
- `briefing_tool(section=dashboard|decisions|analysis|public_standing_orders)`

### 验证方式

1. `docker compose up -d` 启动 Agentropolis
2. 仅以 `streamable-http` 配置本地 MCP 连接；不再使用 SSE 示例
3. 本地 agent 发现 14 个 modules / 60 tools
4. `register_agent -> create_company -> get_recipes -> build_building -> get_market_prices -> autonomy_tool -> digest_tool -> briefing_tool`
5. 用同一条路径做 1 组 MCP/REST parity 检查（例如 autonomy config / digest / dashboard）
6. 验证 `npc` 与 `notifications` 属于 MCP-only local-preview groups，没有 mounted REST fallback
7. `skills/agentropolis-world/SKILL.md` 只引用 `tool-matrix.md` 与 `rest-fallback-map.md`，且本波次不引入 `agents/openai.yaml`
8. `prompts/agent-brain.md`、`openclaw/*`、`docker-compose.multi-agent.yml`、`scripts/register_agents.py`、`scripts/monitor_agents.py` 与 `tests/e2e/*` 在 repo 内可验证，并与 `/meta/runtime` 的路径声明一致

---

## Concurrency Guard — 并发排队系统 (#78-#80)

> 应用层三层并发控制：Rate Limiter → Global Semaphore → Striped Entity Lock。
> 解决连接池耗尽、死锁、无速率限制三大风险。

### 架构

```
请求 → [Rate Limiter 中间件] → [Global Semaphore] → [Striped Entity Lock] → DB
         每 Agent 限流              全局并发上限          每实体串行化
         429 Too Many Requests      503 Service Unavail    防止同实体竞态
```

### Issues

| Issue | Title | Status | Depends On | Key Files |
|-------|-------|--------|------------|-----------|
| [#78](https://github.com/zp184764679/agentropolis/issues/78) | Concurrency Guard Core — StripedLock + GlobalSemaphore | ⬜ CREATED | #16 | `services/concurrency.py`, `config.py`, `deps.py` |
| [#79](https://github.com/zp184764679/agentropolis/issues/79) | Rate Limit Middleware — Sliding Window | ⬜ CREATED | #78 | `middleware/__init__.py`, `middleware/rate_limit.py` |
| [#80](https://github.com/zp184764679/agentropolis/issues/80) | Concurrency Integration — main.py + Exception Handlers | ⬜ CREATED | #78, #79 | `main.py` |

### 执行顺序

```
#78 (核心) → #79 (中间件) → #80 (集成)
```

### 文件所有权

| File | Owner Issue |
|------|-------------|
| `services/concurrency.py` | #78 |
| `middleware/__init__.py` | #79 |
| `middleware/rate_limit.py` | #79 |
| `tests/test_concurrency.py` | #78 |
| `config.py` | #16 base; #78 concurrency settings |
| `deps.py` | #16 base; #78 guard entry points |
| `main.py` | base routing owners; #80 middleware + exception integration |

### 配置新增 (config.py, #78)

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CONCURRENCY_MAX_CONCURRENT` | 25 | 全局最大并发（< pool 30） |
| `CONCURRENCY_STRIPE_COUNT` | 256 | Striped lock 桶数 |
| `CONCURRENCY_LOCK_TIMEOUT` | 5.0s | 实体锁超时 → 429 |
| `CONCURRENCY_SLOT_TIMEOUT` | 10.0s | 全局信号量超时 → 503 |
| `HOUSEKEEPING_RESERVED_SLOTS` | 5 | Housekeeping 预留槽位 |
| `RATE_LIMIT_WINDOW_SECONDS` | 60 | 滑动窗口大小 |

### 测试 (tests/test_concurrency.py, 16 tests)

**单元测试 (11)**: StripedLock/Semaphore/multi_lock/Guard/RateLimiter 纯 asyncio 测试
**集成测试 (5)**: 并发扣款/并行验证/503/429 HTTP 级别测试

### 当前 repo 实现口径

- 所有带 `X-API-Key` 或 `X-Control-Plane-Token` 的请求都会先经过应用层并发守卫
- 并发守卫分三层：
  1. sliding-window rate limit
  2. authenticated request global slot gate
  3. authenticated write-only entity locks
- housekeeping 使用独立预留槽位；认证 HTTP 请求不会占用这些预留容量
- 匿名 public reads 不进入 authenticated concurrency gate
- 当前实现仍是 process-local baseline，不包含 Redis / 分布式锁；这是 `P4` 的本地冻结版本，不是最终横向扩展方案
- `/meta/runtime`、`/meta/observability`、`/meta/rollout-readiness`、`/meta/alerts` 都必须反映这层并发状态，而不能只在代码里存在
- 当前 repo 也已经补了 `#81` 的最小基线：`/meta/contract`、`X-Agentropolis-Contract-Version`、稳定 auth error codes、REST/MCP scope catalogs；这仍然是 local-preview contract freeze，不等于 public rollout 已开放

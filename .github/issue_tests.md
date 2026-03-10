## Overview

Implement comprehensive test suite — unit tests, integration tests, and property-based tests.

## Files

- **Create**: `tests/conftest.py` (if not exists, update if exists)
- **Create**: `tests/test_inventory_svc.py`
- **Create**: `tests/test_company_svc.py`
- **Create**: `tests/test_consumption.py`
- **Create**: `tests/test_production.py`
- **Create**: `tests/test_market_engine.py`
- **Create**: `tests/test_agent_svc.py`
- **Create**: `tests/test_world_svc.py`
- **Create**: `tests/test_skill_svc.py`
- **Create**: `tests/test_transport_svc.py`
- **Create**: `tests/test_guild_svc.py`
- **Create**: `tests/test_api_agent.py`
- **Create**: `tests/test_api_market.py`
- **Create**: `tests/test_integration.py`

## Test Infrastructure (conftest.py)

```python
# Use SQLite in-memory for tests (async)
# Fixtures: db_session, seeded_session (with seed data + seed_world)
# Helper: create_test_agent(), create_test_company()
# All tests use `now` parameter injection (no datetime mocking)
```

## Key Test Scenarios

### inventory_svc
- add_resource creates row on first add
- add_resource increments on subsequent adds
- remove_resource raises on insufficient
- reserve/unreserve maintains invariants
- polymorphic owner (company vs agent)
- regional isolation (A region inventory != B region)

### company_svc
- register creates company + CEO employment + buildings + inventory
- debit_balance raises on insufficient
- net_worth calculation
- bankruptcy detection

### consumption
- NPC consumption settles correctly over time
- Satisfaction recovery when fully supplied
- Satisfaction decay when undersupplied
- Worker attrition at satisfaction=0
- Integer deduction (no fractional inventory)

### production
- Progress accumulates based on real time
- Rate halved below 50% satisfaction
- Outputs produced on completion
- Inputs insufficient → building goes IDLE
- Skill check on start_production
- XP awarded on completion

### market_engine
- BUY matches lowest SELL (price-time priority)
- Execution at maker price
- Self-trade prevention
- Regional isolation
- GTC vs IOC
- Tax collection
- Balance/inventory correctly transferred

### agent_svc
- Registration generates unique API key
- Vitals decay over time
- eat/drink/rest restore vitals
- Death at health=0
- Respawn with penalty

### world_svc
- Dijkstra shortest path
- Travel start/settle/status
- 80+ regions seeded correctly
- Portal connections

### Property-based (hypothesis)
- For any sequence of buy/sell orders: total balance is conserved (minus tax)
- For any inventory operations: invariants hold
- Satisfaction is always in [0, 100]

## Acceptance Criteria

- [ ] `pytest` passes with 0 failures
- [ ] Each service has dedicated test file
- [ ] At least 2 integration tests (full flow)
- [ ] Property-based tests for market engine
- [ ] Test coverage > 80% for services
- [ ] All tests use SQLite in-memory (no PostgreSQL needed)

## Dependencies

- **Depends on**: ALL services implemented
- **Blocks**: None

## Overview

Implement NPC consumption service — lazy time-based settlement of Company NPC worker upkeep.

**Key change**: No more Worker model. Consumption operates on `Company.npc_worker_count`, `Company.npc_satisfaction`, `Company.last_consumption_at` directly.

## Files

- **Modify**: `src/agentropolis/services/consumption.py`
- **DO NOT TOUCH**: Model files, other services

## Function Signatures (Final)

```python
async def settle_npc_consumption(
    session: AsyncSession, company_id: int, now: datetime | None = None,
) -> dict:
    """Settle NPC worker consumption based on elapsed time.

    1. Load Company (FOR UPDATE) — read npc_worker_count, npc_satisfaction, last_consumption_at
    2. elapsed = now - last_consumption_at (seconds)
    3. rat_needed = npc_worker_count * WORKER_RAT_PER_SECOND * elapsed
       dw_needed  = npc_worker_count * WORKER_DW_PER_SECOND * elapsed
    4. Load RAT/DW inventory for this company+region (FOR UPDATE)
       rat_consumed = min(available_rat, rat_needed)
       dw_consumed  = min(available_dw, dw_needed)
    5. Deduct from inventory (integer amounts, floor to int)
    6. Calculate supply ratio:
       rat_ratio = rat_consumed / rat_needed if rat_needed > 0 else 1.0
       dw_ratio  = dw_consumed / dw_needed if dw_needed > 0 else 1.0
       supply_ratio = min(rat_ratio, dw_ratio)
    7. Update satisfaction:
       if supply_ratio >= 1.0: recover (cap 100)
       else: decay proportionally (floor 0)
    8. If npc_satisfaction == 0: attrition
       workers_lost = floor(npc_worker_count * WORKER_ATTRITION_RATE)
       npc_worker_count -= workers_lost
    9. Update last_consumption_at = now

    Returns: {"elapsed_seconds", "rat_consumed", "dw_consumed",
              "npc_satisfaction", "workers_lost"}
    """

async def settle_all_npc_consumption(
    session: AsyncSession, now: datetime | None = None,
) -> dict:
    """Settle for all active companies. Used by housekeeping.
    Returns: {"companies_processed", "total_rat_consumed", "total_dw_consumed", "total_workers_lost"}
    """
```

## Implementation Rules

1. Company fields used (NOT Worker model — Worker is deleted):
   - `company.npc_worker_count` (int)
   - `company.npc_satisfaction` (float 0-100)
   - `company.last_consumption_at` (datetime)
   - `company.region_id` (for inventory lookup)
2. Inventory lookup: `inventory_svc.remove_resource(company_id=X, resource_id=RAT_ID, region_id=company.region_id, amount=consumed)`
3. Satisfaction recovery rate: `SATISFACTION_RECOVERY_PER_SECOND * elapsed` (from config)
4. Satisfaction decay rate: `SATISFACTION_DECAY_PER_SECOND * elapsed * (1 - supply_ratio)` (from config)
5. Attrition only when satisfaction exactly 0
6. If `last_consumption_at is None`, set it to `now` and return (first settlement)
7. All service functions accept optional `now` parameter for testability
8. Integer arithmetic for inventory (floor fractional consumption to int)

## Satisfaction Rules

```
if supply_ratio >= 1.0:
    satisfaction = min(100.0, satisfaction + RECOVERY_RATE * elapsed)
else:
    satisfaction = max(0.0, satisfaction - DECAY_RATE * elapsed * (1 - supply_ratio))

if satisfaction == 0.0:
    lost = floor(npc_worker_count * ATTRITION_RATE)
    npc_worker_count -= lost
```

## Acceptance Criteria

- [ ] Lazy settlement based on elapsed time
- [ ] FOR UPDATE on Company and Inventory rows
- [ ] Correct supply ratio calculation
- [ ] Satisfaction recovery and decay
- [ ] Worker attrition at satisfaction=0
- [ ] Integer inventory deductions
- [ ] `now` parameter for testability
- [ ] settle_all iterates all active companies

## Dependencies

- **Depends on**: #16 (Foundation), #17 (inventory_svc)
- **Blocks**: #20 (production needs satisfaction), #22 (game_engine)

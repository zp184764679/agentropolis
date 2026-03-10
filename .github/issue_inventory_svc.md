## Overview

Implement the inventory service — resource stockpile management with regional + polymorphic owner support.

**Key changes from original stub**: Inventory is now regional (`region_id`) and supports both Company and Agent ownership (polymorphic: exactly one of `company_id`/`agent_id` must be set). All quantities are **integer** (no floats).

## Files

- **Modify**: `src/agentropolis/services/inventory_svc.py`
- **DO NOT TOUCH**: Any model files, schemas, auth, config (owned by #16)

## Function Signatures (Final)

```python
async def add_resource(
    session: AsyncSession, *, company_id: int | None = None, agent_id: int | None = None,
    resource_id: int, region_id: int, amount: int,
) -> int:
    """Add resources to inventory. Creates row if not exists. Returns new quantity."""

async def remove_resource(
    session: AsyncSession, *, company_id: int | None = None, agent_id: int | None = None,
    resource_id: int, region_id: int, amount: int,
) -> int:
    """Remove resources. Raises ValueError if insufficient available. Returns new quantity."""

async def reserve_resource(
    session: AsyncSession, *, company_id: int | None = None, agent_id: int | None = None,
    resource_id: int, region_id: int, amount: int,
) -> int:
    """Reserve resources for sell orders. Returns new reserved amount.
    Raises ValueError if insufficient available (quantity - reserved)."""

async def unreserve_resource(
    session: AsyncSession, *, company_id: int | None = None, agent_id: int | None = None,
    resource_id: int, region_id: int, amount: int,
) -> int:
    """Release reserved resources. Returns new reserved amount."""

async def get_inventory(
    session: AsyncSession, *, company_id: int | None = None, agent_id: int | None = None,
    region_id: int | None = None,
) -> list[dict]:
    """Get inventory items. If region_id=None, returns all regions.
    Returns: [{"resource_id", "ticker", "name", "quantity", "reserved", "available", "region_id"}]"""

async def get_resource_quantity(
    session: AsyncSession, *, company_id: int | None = None, agent_id: int | None = None,
    resource_id: int, region_id: int,
) -> dict:
    """Get quantity info for specific resource.
    Returns: {"quantity": int, "reserved": int, "available": int}"""
```

## Implementation Rules

1. All mutations MUST use `SELECT ... FOR UPDATE` to prevent races
2. Validate exactly one of `company_id`/`agent_id` is provided (raise ValueError otherwise)
3. `add_resource`: upsert — create Inventory row if not exists, increment if exists
4. `remove_resource`: only deduct from `available` (quantity - reserved), raise if insufficient
5. `reserve_resource`: increase `reserved`, ensure `reserved <= quantity`
6. `unreserve_resource`: decrease `reserved`, floor at 0
7. Look up resource by `resource_id` (int), NOT ticker string — callers resolve ticker→id before calling
8. All amounts are positive integers, raise ValueError if amount <= 0

## Invariants (must hold after every operation)

- `quantity >= 0`
- `reserved >= 0`
- `reserved <= quantity`
- `available = quantity - reserved >= 0`

## Acceptance Criteria

- [ ] All 6 functions implemented
- [ ] FOR UPDATE locking on all mutations
- [ ] Polymorphic owner validation (exactly one of company_id/agent_id)
- [ ] Regional scoping (region_id on all operations)
- [ ] Integer quantities throughout (no float)
- [ ] Upsert behavior on add_resource
- [ ] ValueError on insufficient quantity/available
- [ ] Unit tests pass

## Dependencies

- **Depends on**: #16 (Foundation)
- **Blocks**: #18 (company_svc), #19 (consumption), #20 (production), #21 (market_engine)

"""Transport service - inter-region logistics."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models import Agent, Company, Inventory, Resource, TransportOrder, TransportStatus
from agentropolis.services.world_svc import find_path

TRANSPORT_COST_MULTIPLIERS: dict[str, float] = {
    "backpack": 1.0,
    "courier": 1.3,
    "wagon": 0.85,
}


def _estimate_transport_cost_from_path(
    path: dict,
    items: dict[str, int],
    transport_type: str,
) -> int:
    total_weight = sum(int(quantity) for quantity in items.values())
    cost_multiplier = TRANSPORT_COST_MULTIPLIERS.get(transport_type, 1.0)
    base_minutes = max(1, path["total_time_seconds"] // 60)
    return max(1, int(round(total_weight * base_minutes * cost_multiplier)))


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _serialize_transport(transport: TransportOrder) -> dict:
    return {
        "transport_id": transport.id,
        "owner_agent_id": transport.owner_agent_id,
        "owner_company_id": transport.owner_company_id,
        "from_region_id": transport.from_region_id,
        "to_region_id": transport.to_region_id,
        "status": transport.status.value,
        "items": transport.items or {},
        "cost": int(transport.cost),
        "departed_at": transport.departed_at.isoformat() if transport.departed_at else None,
        "arrives_at": transport.arrives_at.isoformat() if transport.arrives_at else None,
    }


async def _get_resource_map(
    session: AsyncSession,
    tickers: set[str],
) -> dict[str, Resource]:
    result = await session.execute(
        select(Resource).where(Resource.ticker.in_(tuple(sorted(tickers))))
    )
    resources = {resource.ticker: resource for resource in result.scalars().all()}
    missing = sorted(tickers - set(resources))
    if missing:
        raise ValueError(f"Unknown resources: {', '.join(missing)}")
    return resources


async def _get_inventory_row(
    session: AsyncSession,
    *,
    company_id: int | None,
    agent_id: int | None,
    region_id: int,
    resource_id: int,
) -> Inventory | None:
    result = await session.execute(
        select(Inventory)
        .where(
            Inventory.company_id == company_id,
            Inventory.agent_id == agent_id,
            Inventory.region_id == region_id,
            Inventory.resource_id == resource_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _get_or_create_inventory_row(
    session: AsyncSession,
    *,
    company_id: int | None,
    agent_id: int | None,
    region_id: int,
    resource_id: int,
) -> Inventory:
    inventory = await _get_inventory_row(
        session,
        company_id=company_id,
        agent_id=agent_id,
        region_id=region_id,
        resource_id=resource_id,
    )
    if inventory is None:
        inventory = Inventory(
            company_id=company_id,
            agent_id=agent_id,
            region_id=region_id,
            resource_id=resource_id,
            quantity=0,
            reserved=0,
        )
        session.add(inventory)
        await session.flush()
    return inventory


async def _validate_owner(
    session: AsyncSession,
    *,
    agent_id: int | None,
    company_id: int | None,
    from_region_id: int,
) -> Agent | Company:
    if (agent_id is None) == (company_id is None):
        raise ValueError("Exactly one of agent_id or company_id must be provided")

    if agent_id is not None:
        result = await session.execute(
            select(Agent).where(Agent.id == agent_id).with_for_update()
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")
        if agent.current_region_id != from_region_id:
            raise ValueError(
                f"Agent {agent_id} must be in region {from_region_id} to create transport"
            )
        return agent

    result = await session.execute(
        select(Company).where(Company.id == company_id).with_for_update()
    )
    company = result.scalar_one_or_none()
    if company is None:
        raise ValueError(f"Company {company_id} not found")
    if not company.is_active:
        raise ValueError(f"Company {company_id} is inactive")
    return company


async def create_transport(
    session: AsyncSession,
    from_region_id: int,
    to_region_id: int,
    items: dict[str, int],
    transport_type: str = "backpack",
    *,
    agent_id: int | None = None,
    company_id: int | None = None,
) -> dict:
    """Create a transport order. Deducts items from origin inventory.

    Returns: {"transport_id", "cost", "departed_at", "arrives_at"}
    """
    if not items:
        raise ValueError("Transport items cannot be empty")

    normalized_items = {
        ticker: int(quantity)
        for ticker, quantity in items.items()
        if int(quantity) > 0
    }
    if not normalized_items:
        raise ValueError("Transport items must contain positive quantities")

    path = await find_path(session, from_region_id, to_region_id)
    cost = _estimate_transport_cost_from_path(path, normalized_items, transport_type)
    owner = await _validate_owner(
        session,
        agent_id=agent_id,
        company_id=company_id,
        from_region_id=from_region_id,
    )

    resources = await _get_resource_map(session, set(normalized_items))
    source_rows: list[Inventory] = []
    total_weight = 0
    for ticker, quantity in normalized_items.items():
        resource = resources[ticker]
        inventory = await _get_inventory_row(
            session,
            company_id=company_id,
            agent_id=agent_id,
            region_id=from_region_id,
            resource_id=resource.id,
        )
        if inventory is None:
            raise ValueError(
                f"No inventory for {ticker} in region {from_region_id}"
            )
        available = float(inventory.quantity) - float(inventory.reserved)
        if available < quantity:
            raise ValueError(
                f"Insufficient {ticker}: need {quantity}, available {available:.0f}"
            )
        source_rows.append(inventory)
        total_weight += quantity

    if isinstance(owner, Agent):
        if int(owner.personal_balance) < cost:
            raise ValueError(
                f"Agent {owner.id} has insufficient balance for transport cost {cost}"
            )
        owner.personal_balance = int(owner.personal_balance) - cost
        owner.last_active_at = _coerce_now()
    else:
        if float(owner.balance) < cost:
            raise ValueError(
                f"Company {owner.id} has insufficient balance for transport cost {cost}"
            )
        owner.balance = float(owner.balance) - cost

    for inventory, ticker in zip(source_rows, normalized_items, strict=False):
        inventory.quantity = float(inventory.quantity) - normalized_items[ticker]

    now = _coerce_now()
    transport = TransportOrder(
        owner_agent_id=agent_id,
        owner_company_id=company_id,
        from_region_id=from_region_id,
        to_region_id=to_region_id,
        items=normalized_items,
        total_weight=total_weight,
        transport_type=transport_type,
        cost=cost,
        status=TransportStatus.IN_TRANSIT,
        departed_at=now,
        arrives_at=now + timedelta(seconds=path["total_time_seconds"]),
    )
    session.add(transport)
    await session.flush()
    return _serialize_transport(transport)


async def estimate_transport_cost(
    session: AsyncSession,
    *,
    from_region_id: int,
    to_region_id: int,
    items: dict[str, int],
    transport_type: str = "backpack",
) -> int:
    """Estimate transport creation cost without mutating state."""
    normalized_items = {
        ticker: int(quantity)
        for ticker, quantity in items.items()
        if int(quantity) > 0
    }
    if not normalized_items:
        raise ValueError("Transport items must contain positive quantities")
    path = await find_path(session, from_region_id, to_region_id)
    return _estimate_transport_cost_from_path(path, normalized_items, transport_type)


async def settle_transport_arrivals(
    session: AsyncSession, now: datetime | None = None
) -> int:
    """Settle all arrived transports, delivering items. Returns count."""
    now = _coerce_now(now)
    result = await session.execute(
        select(TransportOrder)
        .where(
            TransportOrder.status == TransportStatus.IN_TRANSIT,
            TransportOrder.arrives_at <= now,
        )
        .with_for_update()
    )
    transports = list(result.scalars().all())
    if not transports:
        return 0

    all_tickers: set[str] = set()
    for transport in transports:
        all_tickers.update((transport.items or {}).keys())
    resources = await _get_resource_map(session, all_tickers)

    for transport in transports:
        total_quantity = sum(int(quantity) for quantity in (transport.items or {}).values())
        from agentropolis.services.storage_svc import check_storage_available

        has_storage = await check_storage_available(
            session,
            total_quantity,
            transport.to_region_id,
            company_id=transport.owner_company_id,
            agent_id=transport.owner_agent_id,
        )
        if not has_storage:
            continue
        for ticker, quantity in (transport.items or {}).items():
            resource = resources[ticker]
            destination = await _get_or_create_inventory_row(
                session,
                company_id=transport.owner_company_id,
                agent_id=transport.owner_agent_id,
                region_id=transport.to_region_id,
                resource_id=resource.id,
            )
            destination.quantity = float(destination.quantity) + int(quantity)

        transport.status = TransportStatus.DELIVERED

    await session.flush()
    return len(transports)


async def get_transport_status(session: AsyncSession, transport_id: int) -> dict:
    """Get transport order status."""
    result = await session.execute(
        select(TransportOrder).where(TransportOrder.id == transport_id)
    )
    transport = result.scalar_one_or_none()
    if transport is None:
        raise ValueError(f"Transport {transport_id} not found")
    return _serialize_transport(transport)


async def get_my_transports(
    session: AsyncSession, agent_id: int | None = None, company_id: int | None = None
) -> list[dict]:
    """Get all transport orders for an owner."""
    if (agent_id is None) == (company_id is None):
        raise ValueError("Exactly one of agent_id or company_id must be provided")

    query = select(TransportOrder).order_by(TransportOrder.created_at.desc())
    if agent_id is not None:
        query = query.where(TransportOrder.owner_agent_id == agent_id)
    else:
        query = query.where(TransportOrder.owner_company_id == company_id)

    result = await session.execute(query)
    return [_serialize_transport(transport) for transport in result.scalars().all()]

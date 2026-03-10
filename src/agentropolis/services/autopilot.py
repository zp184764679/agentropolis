"""Autonomy runtime service: reflexes, standing orders, and config helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import math
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.preview_guard import allow_internal_preview_family_mutation
from agentropolis.api.preview_guard import allow_internal_company_family_mutation
from agentropolis.config import settings
from agentropolis.models import (
    Agent,
    AutonomyMode,
    AutonomyState,
    DecisionType,
    StrategyProfile,
    TravelQueue,
)
from agentropolis.services import notification_svc
from agentropolis.services.agent_svc import drink, eat, rest
from agentropolis.services.company_svc import get_active_company_model
from agentropolis.services.decision_log_svc import record_decision
from agentropolis.services.inventory_svc import get_resource_quantity_in_region
from agentropolis.services.market_engine import (
    get_my_orders,
    get_order_book,
    place_buy_order,
    place_sell_order,
)

logger = logging.getLogger(__name__)

_SUPPORTED_SOURCES = {None, "market"}


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _append_reflex_log(state: AutonomyState, entry: dict) -> None:
    log_entries = list(state.reflex_log or [])
    log_entries.append(entry)
    state.reflex_log = log_entries[-settings.AUTOPILOT_MAX_REFLEX_LOG_ENTRIES :]


def _needs_budget_reset(state: AutonomyState, now: datetime) -> bool:
    started = state.hour_window_started_at
    if started is None:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return now - started >= timedelta(hours=1)


def _serialize_config(state: AutonomyState) -> dict:
    return {
        "agent_id": state.agent_id,
        "autopilot_enabled": bool(state.autopilot_enabled),
        "mode": state.mode,
        "spending_limit_per_hour": int(state.spending_limit_per_hour),
        "spending_this_hour": int(state.spending_this_hour),
        "hour_window_started_at": _isoformat(state.hour_window_started_at),
        "last_reflex_at": _isoformat(state.last_reflex_at),
        "last_standing_orders_at": _isoformat(state.last_standing_orders_at),
        "last_digest_at": _isoformat(state.last_digest_at),
    }


def _serialize_standing_orders(state: AutonomyState) -> dict:
    return {
        "buy_rules": list((state.standing_orders or {}).get("buy_rules", [])),
        "sell_rules": list((state.standing_orders or {}).get("sell_rules", [])),
    }


def _normalize_mode(mode: str) -> str:
    try:
        return AutonomyMode(mode).value
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in AutonomyMode)
        raise ValueError(f"Unsupported autonomy mode '{mode}'. Allowed: {allowed}") from exc


def _normalize_standing_orders(standing_orders: dict | None) -> dict:
    payload = dict(standing_orders or {})
    normalized = {"buy_rules": [], "sell_rules": []}

    for raw_rule in payload.get("buy_rules", []) or []:
        resource = str(raw_rule.get("resource", "")).upper().strip()
        below_price = float(raw_rule.get("below_price", 0))
        max_qty = float(raw_rule.get("max_qty", 0))
        source = raw_rule.get("source")
        if source is not None:
            source = str(source).lower()
        if not resource:
            raise ValueError("Standing-order buy rule requires resource")
        if below_price <= 0 or max_qty <= 0:
            raise ValueError("Standing-order buy rule requires below_price > 0 and max_qty > 0")
        if source not in _SUPPORTED_SOURCES:
            raise ValueError(f"Standing-order source '{source}' is not supported")
        normalized["buy_rules"].append(
            {
                "resource": resource,
                "below_price": below_price,
                "max_qty": max_qty,
                **({"source": source} if source else {}),
            }
        )

    for raw_rule in payload.get("sell_rules", []) or []:
        resource = str(raw_rule.get("resource", "")).upper().strip()
        above_price = float(raw_rule.get("above_price", 0))
        min_qty = float(raw_rule.get("min_qty", 0))
        if not resource:
            raise ValueError("Standing-order sell rule requires resource")
        if above_price <= 0 or min_qty <= 0:
            raise ValueError("Standing-order sell rule requires above_price > 0 and min_qty > 0")
        normalized["sell_rules"].append(
            {
                "resource": resource,
                "above_price": above_price,
                "min_qty": min_qty,
            }
        )

    return normalized


def _needed_units(current: float, target: float, restore_per_unit: float) -> int:
    missing = max(target - float(current), 0.0)
    if missing <= 0:
        return 0
    return max(1, int(math.ceil(missing / max(restore_per_unit, 1.0))))


async def _load_or_create_strategy_profile(
    session: AsyncSession,
    agent_id: int,
) -> StrategyProfile:
    result = await session.execute(
        select(StrategyProfile).where(StrategyProfile.agent_id == agent_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = StrategyProfile(agent_id=agent_id)
        session.add(profile)
        await session.flush()
    return profile


async def ensure_autonomy_state(session: AsyncSession, agent_id: int) -> AutonomyState:
    result = await session.execute(
        select(AutonomyState).where(AutonomyState.agent_id == agent_id)
    )
    state = result.scalar_one_or_none()
    if state is not None:
        return state

    profile = await _load_or_create_strategy_profile(session, agent_id)
    state = AutonomyState(
        agent_id=agent_id,
        autopilot_enabled=False,
        mode=AutonomyMode.MANUAL.value,
        standing_orders=_normalize_standing_orders(profile.standing_orders or {}),
        spending_limit_per_hour=settings.AUTOPILOT_DEFAULT_SPENDING_LIMIT_PER_HOUR,
        spending_this_hour=0,
        hour_window_started_at=_coerce_now(),
        reflex_log=[],
        state={},
    )
    session.add(state)
    await session.flush()
    return state


async def get_autonomy_config(session: AsyncSession, agent_id: int) -> dict:
    state = await ensure_autonomy_state(session, agent_id)
    return _serialize_config(state)


async def update_autonomy_config(
    session: AsyncSession,
    agent_id: int,
    *,
    autopilot_enabled: bool | None = None,
    mode: str | None = None,
    spending_limit_per_hour: int | None = None,
) -> dict:
    state = await ensure_autonomy_state(session, agent_id)
    if autopilot_enabled is not None:
        state.autopilot_enabled = bool(autopilot_enabled)
    if mode is not None:
        state.mode = _normalize_mode(mode)
    if spending_limit_per_hour is not None:
        if spending_limit_per_hour < 0:
            raise ValueError("spending_limit_per_hour must be >= 0")
        state.spending_limit_per_hour = int(spending_limit_per_hour)
    await session.flush()
    return _serialize_config(state)


async def get_standing_orders(session: AsyncSession, agent_id: int) -> dict:
    state = await ensure_autonomy_state(session, agent_id)
    return _serialize_standing_orders(state)


async def update_standing_orders(
    session: AsyncSession,
    agent_id: int,
    standing_orders: dict | None,
) -> dict:
    state = await ensure_autonomy_state(session, agent_id)
    normalized = _normalize_standing_orders(standing_orders)
    state.standing_orders = normalized

    profile = await _load_or_create_strategy_profile(session, agent_id)
    profile.standing_orders = normalized if any(normalized.values()) else None
    profile.version = int(profile.version or 0) + 1

    await session.flush()
    return _serialize_standing_orders(state)


async def acknowledge_digest(
    session: AsyncSession,
    agent_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    state = await ensure_autonomy_state(session, agent_id)
    timestamp = _coerce_now(now)
    state.last_digest_at = timestamp
    await session.flush()
    return {
        "agent_id": agent_id,
        "acknowledged_at": timestamp.isoformat(),
    }


async def _is_traveling(session: AsyncSession, agent_id: int) -> bool:
    result = await session.execute(
        select(TravelQueue.id).where(TravelQueue.agent_id == agent_id)
    )
    return result.scalar_one_or_none() is not None


async def run_all_reflexes(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict:
    timestamp = _coerce_now(now)
    result = await session.execute(
        select(AutonomyState, Agent)
        .join(Agent, Agent.id == AutonomyState.agent_id)
        .where(
            AutonomyState.autopilot_enabled.is_(True),
            AutonomyState.mode.in_(
                (AutonomyMode.REFLEX_ONLY.value, AutonomyMode.ASSISTED.value)
            ),
            Agent.is_active.is_(True),
            Agent.is_alive.is_(True),
        )
        .order_by(AutonomyState.agent_id.asc())
    )
    rows = result.all()

    actions = 0
    failures = 0
    notifications = 0

    for state, agent in rows:
        hunger = float(agent.hunger)
        thirst = float(agent.thirst)
        energy = float(agent.energy)

        try:
            if hunger <= settings.AUTOPILOT_HUNGER_THRESHOLD:
                amount = _needed_units(
                    hunger,
                    settings.AUTOPILOT_HUNGER_TARGET,
                    settings.AGENT_EAT_HUNGER_RESTORE,
                )
                if amount > 0:
                    await eat(session, agent.id, amount=amount)
                    actions += 1
                    _append_reflex_log(
                        state,
                        {
                            "at": timestamp.isoformat(),
                            "action": "eat",
                            "amount": amount,
                        },
                    )

            if thirst <= settings.AUTOPILOT_THIRST_THRESHOLD:
                amount = _needed_units(
                    thirst,
                    settings.AUTOPILOT_THIRST_TARGET,
                    settings.AGENT_DRINK_THIRST_RESTORE,
                )
                if amount > 0:
                    await drink(session, agent.id, amount=amount)
                    actions += 1
                    _append_reflex_log(
                        state,
                        {
                            "at": timestamp.isoformat(),
                            "action": "drink",
                            "amount": amount,
                        },
                    )

            if energy <= settings.AUTOPILOT_ENERGY_THRESHOLD and not await _is_traveling(session, agent.id):
                await rest(session, agent.id)
                actions += 1
                _append_reflex_log(
                    state,
                    {
                        "at": timestamp.isoformat(),
                        "action": "rest",
                    },
                )
            state.last_reflex_at = timestamp
        except ValueError as exc:
            failures += 1
            notifications += 1
            await notification_svc.notify(
                session,
                agent.id,
                "autopilot_reflex_failed",
                "Autopilot reflex failed",
                str(exc),
                data={"agent_id": agent.id, "phase": "reflex"},
            )
            _append_reflex_log(
                state,
                {
                    "at": timestamp.isoformat(),
                    "action": "reflex_failed",
                    "detail": str(exc),
                },
            )
            state.last_reflex_at = timestamp

    await session.flush()
    return {
        "agents_processed": len(rows),
        "actions": actions,
        "failures": failures,
        "notifications": notifications,
    }


def _best_price(order_book: dict, side: str) -> float | None:
    entries = order_book.get("asks" if side == "ask" else "bids", [])
    if not entries:
        return None
    return float(entries[0]["price"])


def _has_open_order(open_orders: list[dict], *, resource: str, side: str) -> bool:
    normalized_side = side.upper()
    for order in open_orders:
        if (
            order["order_type"] == normalized_side
            and order["resource"] == resource
            and order["status"] in {"OPEN", "PARTIALLY_FILLED"}
        ):
            return True
    return False


async def run_all_standing_orders(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    current_tick: int | None = None,
) -> dict:
    timestamp = _coerce_now(now)
    result = await session.execute(
        select(AutonomyState, Agent)
        .join(Agent, Agent.id == AutonomyState.agent_id)
        .where(
            AutonomyState.autopilot_enabled.is_(True),
            AutonomyState.mode == AutonomyMode.ASSISTED.value,
            Agent.is_active.is_(True),
            Agent.is_alive.is_(True),
        )
        .order_by(AutonomyState.agent_id.asc())
    )
    rows = result.all()

    buy_orders_created = 0
    sell_orders_created = 0
    skipped_no_company = 0
    skipped_budget = 0
    failures = 0

    order_book_cache: dict[str, dict] = {}

    for state, agent in rows:
        if _needs_budget_reset(state, timestamp):
            state.spending_this_hour = 0
            state.hour_window_started_at = timestamp

        company = await get_active_company_model(session, agent.id)
        if company is None:
            skipped_no_company += 1
            state.last_standing_orders_at = timestamp
            _append_reflex_log(
                state,
                {
                    "at": timestamp.isoformat(),
                    "action": "standing_orders_skipped",
                    "detail": "no_active_company",
                },
            )
            continue

        standing_orders = _serialize_standing_orders(state)
        open_orders = await get_my_orders(session, company.id, status="OPEN")
        processed_rules = 0

        for buy_rule in standing_orders["buy_rules"]:
            if processed_rules >= settings.AUTOPILOT_MAX_RULES_PER_SWEEP:
                break
            processed_rules += 1
            resource = buy_rule["resource"]
            if _has_open_order(open_orders, resource=resource, side="BUY"):
                continue
            try:
                order_book = order_book_cache.get(resource)
                if order_book is None:
                    order_book = await get_order_book(session, resource)
                    order_book_cache[resource] = order_book
                best_ask = _best_price(order_book, "ask")
                if best_ask is None or best_ask > float(buy_rule["below_price"]):
                    continue

                remaining_budget = max(
                    int(state.spending_limit_per_hour) - int(state.spending_this_hour),
                    0,
                )
                if remaining_budget <= 0:
                    skipped_budget += 1
                    continue

                max_affordable = math.floor(
                    min(
                        float(buy_rule["max_qty"]),
                        float(company.balance) / float(buy_rule["below_price"]),
                        remaining_budget / float(buy_rule["below_price"]),
                    )
                )
                if max_affordable <= 0:
                    skipped_budget += 1
                    continue

                await allow_internal_company_family_mutation(
                    session,
                    company.id,
                    "company_market",
                    operation="place_buy_order",
                    spend_amount=float(buy_rule["below_price"]) * max_affordable,
                )
                order_id = await place_buy_order(
                    session,
                    company.id,
                    resource,
                    float(max_affordable),
                    float(buy_rule["below_price"]),
                    current_tick=current_tick,
                )
                state.spending_this_hour = int(state.spending_this_hour) + int(
                    round(float(buy_rule["below_price"]) * max_affordable)
                )
                await record_decision(
                    session,
                    agent.id,
                    DecisionType.TRADE,
                    f"Autopilot buy order for {resource}",
                    context_snapshot={
                        "resource": resource,
                        "price": float(buy_rule["below_price"]),
                        "quantity": float(max_affordable),
                        "order_type": "BUY",
                        "origin": "standing_order",
                    },
                    reference_type="order",
                    reference_id=order_id,
                    region_id=company.region_id,
                    amount_copper=int(round(float(buy_rule["below_price"]) * max_affordable)),
                )
                buy_orders_created += 1
                open_orders.append(
                    {
                        "order_id": order_id,
                        "order_type": "BUY",
                        "resource": resource,
                        "status": "OPEN",
                    }
                )
            except (ValueError, HTTPException) as exc:
                failures += 1
                _append_reflex_log(
                    state,
                    {
                        "at": timestamp.isoformat(),
                        "action": "standing_buy_failed",
                        "resource": resource,
                        "detail": str(exc),
                    },
                )

        for sell_rule in standing_orders["sell_rules"]:
            if processed_rules >= settings.AUTOPILOT_MAX_RULES_PER_SWEEP:
                break
            processed_rules += 1
            resource = sell_rule["resource"]
            if _has_open_order(open_orders, resource=resource, side="SELL"):
                continue
            try:
                order_book = order_book_cache.get(resource)
                if order_book is None:
                    order_book = await get_order_book(session, resource)
                    order_book_cache[resource] = order_book
                best_bid = _best_price(order_book, "bid")
                if best_bid is None or best_bid < float(sell_rule["above_price"]):
                    continue

                quantity_snapshot = await get_resource_quantity_in_region(
                    session,
                    company.id,
                    resource,
                    region_id=company.region_id,
                )
                available = float(quantity_snapshot["available"])
                order_qty = min(available, float(sell_rule["min_qty"]))
                if order_qty <= 0:
                    continue

                await allow_internal_company_family_mutation(
                    session,
                    company.id,
                    "company_market",
                    operation="place_sell_order",
                )
                order_id = await place_sell_order(
                    session,
                    company.id,
                    resource,
                    float(order_qty),
                    float(sell_rule["above_price"]),
                    current_tick=current_tick,
                )
                await record_decision(
                    session,
                    agent.id,
                    DecisionType.TRADE,
                    f"Autopilot sell order for {resource}",
                    context_snapshot={
                        "resource": resource,
                        "price": float(sell_rule["above_price"]),
                        "quantity": float(order_qty),
                        "order_type": "SELL",
                        "origin": "standing_order",
                    },
                    reference_type="order",
                    reference_id=order_id,
                    region_id=company.region_id,
                    amount_copper=int(round(float(sell_rule["above_price"]) * order_qty)),
                )
                sell_orders_created += 1
                open_orders.append(
                    {
                        "order_id": order_id,
                        "order_type": "SELL",
                        "resource": resource,
                        "status": "OPEN",
                    }
                )
            except (ValueError, HTTPException) as exc:
                failures += 1
                _append_reflex_log(
                    state,
                    {
                        "at": timestamp.isoformat(),
                        "action": "standing_sell_failed",
                        "resource": resource,
                        "detail": str(exc),
                    },
                )

        state.last_standing_orders_at = timestamp

    await session.flush()
    return {
        "agents_processed": len(rows),
        "buy_orders_created": buy_orders_created,
        "sell_orders_created": sell_orders_created,
        "skipped_no_company": skipped_no_company,
        "skipped_budget": skipped_budget,
        "failures": failures,
    }

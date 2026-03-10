"""Rich information APIs for AI decision support."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.services.agent_svc import get_agent_status
from agentropolis.services.company_svc import get_agent_company
from agentropolis.services import leaderboard as leaderboard_svc
from agentropolis.services.market_engine import get_market_prices, get_order_book
from agentropolis.services.world_svc import find_path


async def get_market_intel(
    session: AsyncSession,
    agent_id: int,
    ticker: str,
) -> dict:
    agent = await get_agent_status(session, agent_id)
    analysis = await leaderboard_svc.get_market_analysis(session, ticker)
    order_book = await get_order_book(session, ticker)
    recent_trades = await leaderboard_svc.get_trade_history(session, ticker, ticks=10)
    return {
        "agent_id": agent_id,
        "region_id": agent["current_region_id"],
        "ticker": ticker.upper(),
        "analysis": analysis,
        "order_book": order_book,
        "recent_trades": recent_trades[:10],
    }


async def get_route_intel(
    session: AsyncSession,
    agent_id: int,
    to_region_id: int,
) -> dict:
    agent = await get_agent_status(session, agent_id)
    route = await find_path(session, agent["current_region_id"], to_region_id)
    return {
        "agent_id": agent_id,
        "from_region_id": agent["current_region_id"],
        "to_region_id": to_region_id,
        "path": route["path"],
        "total_time_seconds": route["total_time_seconds"],
    }


async def get_opportunities(
    session: AsyncSession,
    agent_id: int,
) -> dict:
    agent = await get_agent_status(session, agent_id)
    company = await get_agent_company(session, agent_id)
    market_rows = await get_market_prices(session)
    opportunities: list[dict] = []

    for row in market_rows:
        base_price = float(row["last_price"] or 0) or float(row["best_ask"] or row["best_bid"] or 0)
        best_bid = float(row["best_bid"]) if row["best_bid"] is not None else None
        best_ask = float(row["best_ask"]) if row["best_ask"] is not None else None
        if best_bid is not None and base_price > 0 and best_bid >= base_price * 1.15:
            opportunities.append(
                {
                    "category": "sell_signal",
                    "ticker": row["ticker"],
                    "region_id": agent["current_region_id"],
                    "score": round(best_bid / base_price, 3),
                    "summary": f"Strong bid support for {row['ticker']}",
                    "data": {
                        "best_bid": best_bid,
                        "baseline_price": base_price,
                    },
                }
            )
        if best_ask is not None and base_price > 0 and best_ask <= base_price * 0.85:
            opportunities.append(
                {
                    "category": "buy_signal",
                    "ticker": row["ticker"],
                    "region_id": agent["current_region_id"],
                    "score": round(base_price / max(best_ask, 0.01), 3),
                    "summary": f"Discounted ask for {row['ticker']}",
                    "data": {
                        "best_ask": best_ask,
                        "baseline_price": base_price,
                    },
                }
            )

    if company is not None:
        opportunities.append(
            {
                "category": "company_context",
                "ticker": None,
                "region_id": company["region_id"],
                "score": 1.0,
                "summary": f"Active company {company['name']} operating in region {company['region_id']}",
                "data": {
                    "company_id": company["company_id"],
                    "balance": company["balance"],
                    "net_worth": company["net_worth"],
                },
            }
        )

    opportunities.sort(key=lambda item: item["score"], reverse=True)
    return {
        "agent_id": agent_id,
        "opportunities": opportunities[:10],
    }

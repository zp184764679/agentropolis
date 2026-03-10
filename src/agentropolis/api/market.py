"""Market REST API endpoints.

Dependencies: services/market_engine.py, services/leaderboard.py
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_company
from agentropolis.api.preview_guard import ERROR_CODE_HEADER
from agentropolis.api.schemas import (
    CancelOrderRequest,
    MarketAnalysis,
    MarketPrice,
    OrderBookResponse,
    OrderResponse,
    PlaceOrderRequest,
    PriceCandle,
    TradeRecord,
)
from agentropolis.database import get_session
from agentropolis.models import Company
from agentropolis.services import leaderboard as leaderboard_svc
from agentropolis.services import market_engine

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/prices", response_model=list[MarketPrice])
async def get_market_prices(session: AsyncSession = Depends(get_session)):
    """Get current prices for all resources."""
    return await market_engine.get_market_prices(session)


@router.get("/orderbook/{ticker}", response_model=OrderBookResponse)
async def get_order_book(ticker: str, session: AsyncSession = Depends(get_session)):
    """Get order book for a specific resource."""
    try:
        return await market_engine.get_order_book(session, ticker)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "market_resource_not_found"},
        ) from None


@router.get("/history/{ticker}", response_model=list[PriceCandle])
async def get_price_history(
    ticker: str, ticks: int = 50, session: AsyncSession = Depends(get_session)
):
    """Get OHLCV price history for a resource."""
    try:
        return await leaderboard_svc.get_price_history(session, ticker, ticks=ticks)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "market_resource_not_found"},
        ) from None


@router.post("/buy", response_model=OrderResponse)
async def place_buy_order(
    req: PlaceOrderRequest,
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Place a buy order on the market."""
    try:
        order_id = await market_engine.place_buy_order(
            session,
            company.id,
            req.resource,
            req.quantity,
            req.price,
        )
        await session.commit()
        orders = await market_engine.get_my_orders(session, company.id, status="ALL")
        return next(order for order in orders if order["order_id"] == order_id)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "market_buy_invalid"},
        ) from None


@router.post("/sell", response_model=OrderResponse)
async def place_sell_order(
    req: PlaceOrderRequest,
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Place a sell order on the market."""
    try:
        order_id = await market_engine.place_sell_order(
            session,
            company.id,
            req.resource,
            req.quantity,
            req.price,
        )
        await session.commit()
        orders = await market_engine.get_my_orders(session, company.id, status="ALL")
        return next(order for order in orders if order["order_id"] == order_id)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "market_sell_invalid"},
        ) from None


@router.post("/cancel", response_model=OrderResponse)
async def cancel_order(
    req: CancelOrderRequest,
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Cancel an open order."""
    cancelled = await market_engine.cancel_order(session, company.id, req.order_id)
    await session.commit()
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found or no longer cancellable.",
            headers={ERROR_CODE_HEADER: "market_order_not_cancellable"},
        )
    orders = await market_engine.get_my_orders(session, company.id, status="ALL")
    return next(order for order in orders if order["order_id"] == req.order_id)


@router.get("/orders", response_model=list[OrderResponse])
async def get_my_orders(
    status: str = "OPEN",
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get your open or historical orders."""
    try:
        return await market_engine.get_my_orders(session, company.id, status=status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "market_order_status_invalid"},
        ) from None


@router.get("/trades", response_model=list[TradeRecord])
async def get_trade_history(
    ticker: str | None = None,
    ticks: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """Get recent trade history."""
    try:
        return await leaderboard_svc.get_trade_history(session, ticker, ticks=ticks)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "market_resource_not_found"},
        ) from None


@router.get("/analysis/{ticker}", response_model=MarketAnalysis)
async def get_market_analysis(ticker: str, session: AsyncSession = Depends(get_session)):
    """Get market analysis for a resource."""
    try:
        return await leaderboard_svc.get_market_analysis(session, ticker)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "market_resource_not_found"},
        ) from None

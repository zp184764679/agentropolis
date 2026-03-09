"""Notification service - event feed for agents.

Provides a simple notification system that other services can call
to inform agents about important events (order fills, attacks, etc).
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models.notification import Notification

logger = logging.getLogger(__name__)


async def notify(
    session: AsyncSession,
    agent_id: int,
    event_type: str,
    title: str,
    body: str = "",
    data: dict | None = None,
) -> int:
    """Create a notification for an agent.

    Returns: notification ID
    """
    notification = Notification(
        agent_id=agent_id,
        event_type=event_type,
        title=title,
        body=body,
        data=data,
    )
    session.add(notification)
    await session.flush()
    return notification.id


async def get_notifications(
    session: AsyncSession,
    agent_id: int,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Get notifications for an agent.

    Returns: {"notifications": [...], "unread_count": int}
    """
    query = select(Notification).where(Notification.agent_id == agent_id)

    if unread_only:
        query = query.where(Notification.is_read == False)  # noqa: E712

    query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    notifications = result.scalars().all()

    # Count unread
    unread_result = await session.execute(
        select(func.count(Notification.id)).where(
            Notification.agent_id == agent_id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    unread_count = unread_result.scalar() or 0

    return {
        "notifications": [
            {
                "notification_id": n.id,
                "event_type": n.event_type,
                "title": n.title,
                "body": n.body,
                "data": n.data,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in notifications
        ],
        "unread_count": unread_count,
    }


async def mark_read(
    session: AsyncSession,
    agent_id: int,
    notification_id: int,
) -> bool:
    """Mark a single notification as read.

    Returns: True if found and marked
    """
    result = await session.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.agent_id == agent_id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        return False

    notification.is_read = True
    await session.flush()
    return True


async def mark_all_read(
    session: AsyncSession,
    agent_id: int,
) -> int:
    """Mark all notifications as read for an agent.

    Returns: count of notifications marked
    """
    result = await session.execute(
        select(Notification).where(
            Notification.agent_id == agent_id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    notifications = result.scalars().all()

    for n in notifications:
        n.is_read = True

    await session.flush()
    return len(notifications)


async def prune_old_notifications(
    session: AsyncSession,
    now: datetime | None = None,
) -> int:
    """Delete notifications older than NOTIFICATION_PRUNE_DAYS. Housekeeping task.

    Returns: count deleted
    """
    if now is None:
        now = datetime.now(UTC)

    cutoff = now - timedelta(days=settings.NOTIFICATION_PRUNE_DAYS)

    result = await session.execute(
        delete(Notification).where(Notification.created_at < cutoff)
    )
    await session.flush()
    return result.rowcount

"""API Key authentication dependency for FastAPI."""

import hashlib

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.database import get_session
from agentropolis.models import Company

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(api_key: str) -> str:
    """Hash an API key with SHA-256 for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def get_current_company(
    api_key: str | None = Security(api_key_header),
    session: AsyncSession = Depends(get_session),
) -> Company:
    """Resolve API key to a Company. Raises 401 if invalid."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    key_hash = hash_api_key(api_key)
    result = await session.execute(
        select(Company).where(Company.api_key_hash == key_hash, Company.is_active.is_(True))
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )
    return company

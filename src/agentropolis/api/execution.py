"""Execution semantics and asynchronous job introspection endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.preview_guard import ERROR_CODE_HEADER, require_control_plane_admin
from agentropolis.api.schemas import (
    ExecutionBackfillRequest,
    ExecutionJobListResponse,
    ExecutionJobResponse,
    ExecutionRepairRequest,
    ExecutionSnapshotResponse,
)
from agentropolis.database import get_session
from agentropolis.services.concurrency import (
    acquire_entity_locks,
    control_plane_global_lock_key,
    execution_job_lock_key,
)
from agentropolis.services.execution_svc import (
    EXECUTION_ERROR_CODES,
    build_execution_snapshot,
    enqueue_derived_state_repair_from_admin,
    enqueue_housekeeping_backfill_from_admin,
    list_execution_jobs,
    retry_execution_job_from_admin,
)

router = APIRouter(prefix="/meta/execution", tags=["execution"])


def _request_context(request: Request) -> tuple[str | None, str | None]:
    request_id = getattr(request.state, "request_id", None)
    client_fingerprint = getattr(request.state, "client_fingerprint", None)
    return request_id, client_fingerprint


def _execution_error(
    *,
    status_code: int,
    detail: str,
    error_code: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={ERROR_CODE_HEADER: error_code},
    )


@router.get("", response_model=ExecutionSnapshotResponse)
async def read_execution_snapshot(session: AsyncSession = Depends(get_session)):
    return await build_execution_snapshot(session)


@router.get("/jobs", response_model=ExecutionJobListResponse)
async def read_execution_jobs(
    limit: int = Query(default=20, ge=0, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    _admin_actor: str = Depends(require_control_plane_admin),
    session: AsyncSession = Depends(get_session),
):
    return {"jobs": await list_execution_jobs(session, limit=limit, status=status_filter)}


@router.post(
    "/jobs/housekeeping-backfill",
    response_model=ExecutionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_housekeeping_backfill(
    request: Request,
    req: ExecutionBackfillRequest,
    admin_actor: str = Depends(require_control_plane_admin),
    session: AsyncSession = Depends(get_session),
):
    request_id, client_fingerprint = _request_context(request)
    period_end = datetime.fromisoformat(req.period_end) if req.period_end else None
    try:
        async with acquire_entity_locks([control_plane_global_lock_key()]):
            payload = await enqueue_housekeeping_backfill_from_admin(
                session,
                requested_tick=req.requested_tick,
                period_end=period_end,
                admin_actor=admin_actor,
                request_id=request_id,
                client_fingerprint=client_fingerprint,
                reason_code=req.reason_code,
                note=req.note,
            )
            await session.commit()
            return payload
    except ValueError as exc:
        await session.rollback()
        raise _execution_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            error_code="execution_job_invalid",
        ) from None
    except Exception:
        await session.rollback()
        raise


@router.post(
    "/jobs/repair-derived-state",
    response_model=ExecutionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_repair_job(
    request: Request,
    req: ExecutionRepairRequest,
    admin_actor: str = Depends(require_control_plane_admin),
    session: AsyncSession = Depends(get_session),
):
    request_id, client_fingerprint = _request_context(request)
    async with acquire_entity_locks([control_plane_global_lock_key()]):
        payload = await enqueue_derived_state_repair_from_admin(
            session,
            admin_actor=admin_actor,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=req.reason_code,
            note=req.note,
        )
        await session.commit()
        return payload


@router.post(
    "/jobs/{job_id}/retry",
    response_model=ExecutionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_execution_job(
    request: Request,
    job_id: int,
    req: ExecutionRepairRequest,
    admin_actor: str = Depends(require_control_plane_admin),
    session: AsyncSession = Depends(get_session),
):
    request_id, client_fingerprint = _request_context(request)
    try:
        async with acquire_entity_locks(
            [control_plane_global_lock_key(), execution_job_lock_key(job_id)]
        ):
            payload = await retry_execution_job_from_admin(
                session,
                job_id=job_id,
                admin_actor=admin_actor,
                request_id=request_id,
                client_fingerprint=client_fingerprint,
                reason_code=req.reason_code,
                note=req.note,
            )
            await session.commit()
            return payload
    except LookupError:
        await session.rollback()
        raise _execution_error(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EXECUTION_ERROR_CODES["execution_job_not_found"],
            error_code="execution_job_not_found",
        ) from None
    except ValueError:
        await session.rollback()
        raise _execution_error(
            status_code=status.HTTP_409_CONFLICT,
            detail=EXECUTION_ERROR_CODES["execution_job_not_retryable"],
            error_code="execution_job_not_retryable",
        ) from None
    except Exception:
        await session.rollback()
        raise

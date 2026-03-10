"""Execution semantics, job queue, retry, and backfill helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.database import async_session
from agentropolis.models import (
    ControlPlaneAuditLog,
    ExecutionJob,
    ExecutionJobStatus,
    ExecutionJobType,
    ExecutionTriggerKind,
    GameState,
    HousekeepingLog,
)

logger = logging.getLogger(__name__)

EXECUTION_ERROR_CODES = {
    "execution_job_not_found": "Requested execution job was not found.",
    "execution_job_not_retryable": "Requested execution job is not in a retryable state.",
    "execution_job_invalid": "Execution job request is invalid.",
    "execution_backfill_limit_exceeded": "Requested housekeeping backfill exceeds the configured safety limit.",
}

_ACTIVE_JOB_STATUSES = (
    ExecutionJobStatus.ACCEPTED.value,
    ExecutionJobStatus.PENDING.value,
    ExecutionJobStatus.RUNNING.value,
    ExecutionJobStatus.FAILED.value,
)
_RETRYABLE_JOB_STATUSES = (
    ExecutionJobStatus.FAILED.value,
    ExecutionJobStatus.DEAD_LETTER.value,
)


def _utc_now(now: datetime | None = None) -> datetime:
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


def _normalize_trigger_kind(value: str | None) -> str:
    if value is None:
        return ExecutionTriggerKind.MANUAL.value
    return str(value)


def _normalize_job_type(value: str) -> str:
    normalized = str(value)
    allowed = {item.value for item in ExecutionJobType}
    if normalized not in allowed:
        raise ValueError(f"Unsupported execution job type: {normalized}")
    return normalized


def _normalize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


def _normalize_period_end(period_end: str | datetime | None, fallback: datetime) -> datetime:
    if period_end is None:
        return fallback
    if isinstance(period_end, datetime):
        return _utc_now(period_end)
    return _utc_now(datetime.fromisoformat(period_end))


def _serialize_job(job: ExecutionJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "trigger_kind": job.trigger_kind,
        "dedupe_key": job.dedupe_key,
        "payload": dict(job.payload or {}),
        "result_summary": job.result_summary,
        "attempt_history": list(job.attempt_history or []),
        "attempts": int(job.attempts or 0),
        "max_attempts": int(job.max_attempts or 0),
        "available_at": _isoformat(job.available_at),
        "started_at": _isoformat(job.started_at),
        "finished_at": _isoformat(job.finished_at),
        "last_error": job.last_error,
        "dead_letter_reason": job.dead_letter_reason,
        "accepted_at": _isoformat(job.created_at),
        "updated_at": _isoformat(job.updated_at),
    }


async def _record_admin_action(
    session: AsyncSession,
    action: str,
    *,
    actor: str,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        ControlPlaneAuditLog(
            action=action,
            actor=actor,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
            payload=payload or {},
        )
    )
    await session.flush()


async def _find_active_dedupe_job(
    session: AsyncSession,
    dedupe_key: str,
) -> ExecutionJob | None:
    result = await session.execute(
        select(ExecutionJob)
        .where(ExecutionJob.dedupe_key == dedupe_key)
        .where(ExecutionJob.status.in_(_ACTIVE_JOB_STATUSES))
        .order_by(ExecutionJob.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def enqueue_execution_job(
    session: AsyncSession,
    *,
    job_type: str,
    trigger_kind: str | None = None,
    dedupe_key: str | None = None,
    payload: dict[str, Any] | None = None,
    available_at: datetime | None = None,
    max_attempts: int | None = None,
) -> tuple[dict[str, Any], bool]:
    normalized_type = _normalize_job_type(job_type)
    normalized_payload = _normalize_payload(payload)
    normalized_max_attempts = int(max_attempts or settings.EXECUTION_JOB_MAX_ATTEMPTS)
    if normalized_max_attempts <= 0:
        raise ValueError("Execution job max_attempts must be > 0")

    if dedupe_key:
        existing = await _find_active_dedupe_job(session, dedupe_key)
        if existing is not None:
            return _serialize_job(existing), False

    job = ExecutionJob(
        job_type=normalized_type,
        status=ExecutionJobStatus.ACCEPTED.value,
        trigger_kind=_normalize_trigger_kind(trigger_kind),
        dedupe_key=dedupe_key,
        payload=normalized_payload,
        attempt_history=[],
        attempts=0,
        max_attempts=normalized_max_attempts,
        available_at=_utc_now(available_at) if available_at is not None else None,
    )
    session.add(job)
    await session.flush()
    return _serialize_job(job), True


async def enqueue_housekeeping_backfill_job(
    session: AsyncSession,
    *,
    requested_tick: int,
    period_end: datetime | None = None,
    dedupe_key: str | None = None,
    trigger_kind: str = ExecutionTriggerKind.BACKFILL.value,
) -> tuple[dict[str, Any], bool]:
    payload = {
        "requested_tick": int(requested_tick),
        "period_end": _utc_now(period_end).isoformat() if period_end is not None else None,
    }
    return await enqueue_execution_job(
        session,
        job_type=ExecutionJobType.HOUSEKEEPING_BACKFILL.value,
        trigger_kind=trigger_kind,
        dedupe_key=dedupe_key or f"housekeeping-backfill:{int(requested_tick)}",
        payload=payload,
    )


async def enqueue_derived_state_repair_job(
    session: AsyncSession,
    *,
    dedupe_key: str | None = None,
    trigger_kind: str = ExecutionTriggerKind.MANUAL.value,
) -> tuple[dict[str, Any], bool]:
    return await enqueue_execution_job(
        session,
        job_type=ExecutionJobType.DERIVED_STATE_REPAIR.value,
        trigger_kind=trigger_kind,
        dedupe_key=dedupe_key or "derived-state-repair",
        payload={},
    )


async def schedule_missed_housekeeping_backfills(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    effective_now = _utc_now(now)
    state = await session.get(GameState, 1)
    if state is None or state.last_tick_at is None:
        return {
            "missed_sweeps": 0,
            "enqueued": 0,
            "deduped": 0,
            "capped": False,
        }

    interval_seconds = max(int(state.tick_interval_seconds or settings.TICK_INTERVAL_SECONDS), 1)
    last_tick_at = _utc_now(state.last_tick_at)
    elapsed_seconds = max((effective_now - last_tick_at).total_seconds(), 0.0)
    missed_sweeps = int(elapsed_seconds // interval_seconds)
    if missed_sweeps <= 0:
        return {
            "missed_sweeps": 0,
            "enqueued": 0,
            "deduped": 0,
            "capped": False,
        }

    capped_missed = min(missed_sweeps, int(settings.EXECUTION_MAX_BACKFILL_SWEEPS))
    enqueued = 0
    deduped = 0
    for offset in range(1, capped_missed + 1):
        period_end = last_tick_at + timedelta(seconds=interval_seconds * offset)
        _, created = await enqueue_housekeeping_backfill_job(
            session,
            requested_tick=int(state.current_tick or 0) + offset,
            period_end=period_end,
            trigger_kind=ExecutionTriggerKind.BACKFILL.value,
        )
        if created:
            enqueued += 1
        else:
            deduped += 1

    return {
        "missed_sweeps": missed_sweeps,
        "enqueued": enqueued,
        "deduped": deduped,
        "capped": missed_sweeps > capped_missed,
    }


async def list_execution_jobs(
    session: AsyncSession,
    *,
    limit: int = 20,
    status: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(ExecutionJob).order_by(ExecutionJob.id.desc()).limit(max(limit, 0))
    if status is not None:
        stmt = stmt.where(ExecutionJob.status == status)
    result = await session.execute(stmt)
    return [_serialize_job(job) for job in result.scalars().all()]


async def _promote_due_accepted_jobs(session: AsyncSession, *, now: datetime) -> int:
    result = await session.execute(
        select(ExecutionJob)
        .where(ExecutionJob.status == ExecutionJobStatus.ACCEPTED.value)
        .where(
            (ExecutionJob.available_at.is_(None))
            | (ExecutionJob.available_at <= now)
        )
        .order_by(ExecutionJob.available_at.asc().nullsfirst(), ExecutionJob.id.asc())
        .limit(int(settings.EXECUTION_JOB_DRAIN_LIMIT))
    )
    promoted = 0
    for job in result.scalars().all():
        job.status = ExecutionJobStatus.PENDING.value
        promoted += 1
    if promoted:
        await session.flush()
    return promoted


async def _claim_due_job(session: AsyncSession, *, now: datetime) -> ExecutionJob | None:
    result = await session.execute(
        select(ExecutionJob)
        .where(
            ExecutionJob.status.in_(
                (
                    ExecutionJobStatus.PENDING.value,
                    ExecutionJobStatus.FAILED.value,
                )
            )
        )
        .where(
            (ExecutionJob.available_at.is_(None))
            | (ExecutionJob.available_at <= now)
        )
        .order_by(ExecutionJob.available_at.asc().nullsfirst(), ExecutionJob.id.asc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None
    job.status = ExecutionJobStatus.RUNNING.value
    job.started_at = now
    job.finished_at = None
    job.attempts = int(job.attempts or 0) + 1
    await session.flush()
    return job


def _append_attempt(job: ExecutionJob, *, now: datetime, status: str, detail: str | None = None) -> None:
    history = list(job.attempt_history or [])
    history.append(
        {
            "attempt": int(job.attempts or 0),
            "status": status,
            "at": now.isoformat(),
            **({"detail": detail} if detail else {}),
        }
    )
    job.attempt_history = history


async def _mark_job_completed(
    session: AsyncSession,
    job: ExecutionJob,
    *,
    now: datetime,
    result_summary: dict[str, Any],
) -> None:
    job.status = ExecutionJobStatus.COMPLETED.value
    job.finished_at = now
    job.available_at = None
    job.result_summary = result_summary
    job.last_error = None
    job.dead_letter_reason = None
    _append_attempt(job, now=now, status=ExecutionJobStatus.COMPLETED.value)
    await session.flush()


async def _mark_job_failed(
    session: AsyncSession,
    job: ExecutionJob,
    *,
    now: datetime,
    detail: str,
) -> None:
    job.last_error = detail
    retry_delay = timedelta(seconds=int(settings.EXECUTION_JOB_RETRY_DELAY_SECONDS))
    attempts = int(job.attempts or 0)
    if attempts >= int(job.max_attempts or settings.EXECUTION_JOB_MAX_ATTEMPTS):
        job.status = ExecutionJobStatus.DEAD_LETTER.value
        job.finished_at = now
        job.available_at = None
        job.dead_letter_reason = detail
        _append_attempt(job, now=now, status=ExecutionJobStatus.DEAD_LETTER.value, detail=detail)
    else:
        job.status = ExecutionJobStatus.FAILED.value
        job.finished_at = now
        job.available_at = now + retry_delay
        _append_attempt(job, now=now, status=ExecutionJobStatus.FAILED.value, detail=detail)
    await session.flush()


async def _run_job_handler(
    session: AsyncSession,
    job: ExecutionJob,
    *,
    now: datetime,
) -> dict[str, Any]:
    if job.job_type == ExecutionJobType.HOUSEKEEPING_BACKFILL.value:
        from agentropolis.services.game_engine import run_housekeeping_sweep

        payload = dict(job.payload or {})
        requested_tick = int(payload["requested_tick"])
        period_end = _normalize_period_end(payload.get("period_end"), now)
        return await run_housekeeping_sweep(
            session,
            now=period_end,
            tick_number=requested_tick,
            trigger_kind=ExecutionTriggerKind.BACKFILL.value,
            execution_job_id=job.id,
        )
    if job.job_type == ExecutionJobType.DERIVED_STATE_REPAIR.value:
        from agentropolis.services.recovery_svc import repair_derived_state

        result = await repair_derived_state(session)
        return {
            "repair": result,
            "trigger_kind": job.trigger_kind,
        }
    raise ValueError(f"Unsupported execution job type: {job.job_type}")


async def run_due_execution_jobs(
    *,
    now: datetime | None = None,
    limit: int | None = None,
    session_factory=async_session,
) -> dict[str, Any]:
    effective_now = _utc_now(now)
    drain_limit = int(limit or settings.EXECUTION_JOB_DRAIN_LIMIT)
    promoted = 0
    processed = 0
    completed = 0
    failed = 0
    dead_lettered = 0
    jobs: list[dict[str, Any]] = []

    async with session_factory() as session:
        promoted = await _promote_due_accepted_jobs(session, now=effective_now)
        await session.commit()

    for _ in range(max(drain_limit, 0)):
        async with session_factory() as claim_session:
            job = await _claim_due_job(claim_session, now=effective_now)
            if job is None:
                await claim_session.rollback()
                break
            job_id = job.id
            await claim_session.commit()

        processed += 1
        try:
            async with session_factory() as work_session:
                job = await work_session.get(ExecutionJob, job_id)
                assert job is not None
                result_summary = await _run_job_handler(
                    work_session,
                    job,
                    now=effective_now,
                )
                await _mark_job_completed(
                    work_session,
                    job,
                    now=effective_now,
                    result_summary=result_summary,
                )
                await work_session.commit()
                await work_session.refresh(job)
                completed += 1
                jobs.append(_serialize_job(job))
        except Exception as exc:
            logger.exception("Execution job %s failed", job_id)
            async with session_factory() as fail_session:
                job = await fail_session.get(ExecutionJob, job_id)
                assert job is not None
                await _mark_job_failed(
                    fail_session,
                    job,
                    now=effective_now,
                    detail=str(exc),
                )
                await fail_session.commit()
                await fail_session.refresh(job)
                if job.status == ExecutionJobStatus.DEAD_LETTER.value:
                    dead_lettered += 1
                else:
                    failed += 1
                jobs.append(_serialize_job(job))

    return {
        "promoted": promoted,
        "processed": processed,
        "completed": completed,
        "failed": failed,
        "dead_lettered": dead_lettered,
        "jobs": jobs,
    }


async def retry_execution_job(
    session: AsyncSession,
    job_id: int,
) -> dict[str, Any]:
    job = await session.get(ExecutionJob, job_id)
    if job is None:
        raise LookupError("Execution job not found.")
    if job.status not in _RETRYABLE_JOB_STATUSES:
        raise ValueError("Execution job is not retryable.")

    job.status = ExecutionJobStatus.ACCEPTED.value
    job.trigger_kind = ExecutionTriggerKind.RETRY.value
    job.available_at = _utc_now()
    job.started_at = None
    job.finished_at = None
    job.last_error = None
    job.dead_letter_reason = None
    await session.flush()
    await session.refresh(job)
    return _serialize_job(job)


async def build_execution_snapshot(
    session: AsyncSession,
    *,
    recent_limit: int = 20,
) -> dict[str, Any]:
    by_status = {
        row[0]: int(row[1] or 0)
        for row in (
            await session.execute(
                select(ExecutionJob.status, func.count(ExecutionJob.id)).group_by(ExecutionJob.status)
            )
        ).all()
    }
    by_type = {
        row[0]: int(row[1] or 0)
        for row in (
            await session.execute(
                select(ExecutionJob.job_type, func.count(ExecutionJob.id)).group_by(ExecutionJob.job_type)
            )
        ).all()
    }
    recent_jobs = await list_execution_jobs(session, limit=recent_limit)
    latest_housekeeping = (
        await session.execute(
            select(HousekeepingLog).order_by(HousekeepingLog.sweep_count.desc()).limit(1)
        )
    ).scalar_one_or_none()

    return {
        "job_states": [item.value for item in ExecutionJobStatus],
        "job_types": [item.value for item in ExecutionJobType],
        "counts": {
            "by_status": by_status,
            "by_type": by_type,
            "pending_or_accepted": sum(
                by_status.get(status, 0)
                for status in (
                    ExecutionJobStatus.ACCEPTED.value,
                    ExecutionJobStatus.PENDING.value,
                )
            ),
            "dead_letters": by_status.get(ExecutionJobStatus.DEAD_LETTER.value, 0),
        },
        "retry_policy": {
            "max_attempts_default": int(settings.EXECUTION_JOB_MAX_ATTEMPTS),
            "retry_delay_seconds": int(settings.EXECUTION_JOB_RETRY_DELAY_SECONDS),
        },
        "backfill_policy": {
            "max_backfill_sweeps": int(settings.EXECUTION_MAX_BACKFILL_SWEEPS),
            "source_of_truth": "game_state.last_tick_at_vs_runtime_now",
            "manual_repair_path": [
                "/meta/execution/jobs/housekeeping-backfill",
                "/meta/execution/jobs/{job_id}/retry",
                "agentropolis repair-derived-state",
            ],
        },
        "housekeeping_phase_contract": {
            "phase_results_logged": True,
            "phase_max_attempts": int(settings.EXECUTION_PHASE_MAX_ATTEMPTS),
            "latest_sweep": (
                {
                    "sweep_count": latest_housekeeping.sweep_count,
                    "trigger_kind": latest_housekeeping.trigger_kind,
                    "execution_job_id": latest_housekeeping.execution_job_id,
                    "error_count": latest_housekeeping.error_count,
                    "phase_results": latest_housekeeping.phase_results or {},
                    "completed_at": _isoformat(latest_housekeeping.completed_at),
                }
                if latest_housekeeping is not None
                else None
            ),
        },
        "recent_jobs": recent_jobs,
    }


async def enqueue_housekeeping_backfill_from_admin(
    session: AsyncSession,
    *,
    requested_tick: int,
    period_end: datetime | None,
    admin_actor: str,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if requested_tick <= 0:
        raise ValueError("requested_tick must be > 0")
    created_job, created = await enqueue_housekeeping_backfill_job(
        session,
        requested_tick=requested_tick,
        period_end=period_end,
        trigger_kind=ExecutionTriggerKind.MANUAL.value,
    )
    await _record_admin_action(
        session,
        "execution_enqueue_housekeeping_backfill",
        actor=admin_actor,
        request_id=request_id,
        client_fingerprint=client_fingerprint,
        reason_code=reason_code,
        note=note,
        payload={
            "requested_tick": requested_tick,
            "created": created,
            "job_id": created_job["job_id"],
        },
    )
    return created_job


async def enqueue_derived_state_repair_from_admin(
    session: AsyncSession,
    *,
    admin_actor: str,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    created_job, created = await enqueue_derived_state_repair_job(session)
    await _record_admin_action(
        session,
        "execution_enqueue_derived_state_repair",
        actor=admin_actor,
        request_id=request_id,
        client_fingerprint=client_fingerprint,
        reason_code=reason_code,
        note=note,
        payload={"created": created, "job_id": created_job["job_id"]},
    )
    return created_job


async def retry_execution_job_from_admin(
    session: AsyncSession,
    *,
    job_id: int,
    admin_actor: str,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    job = await retry_execution_job(session, job_id)
    await _record_admin_action(
        session,
        "execution_retry_job",
        actor=admin_actor,
        request_id=request_id,
        client_fingerprint=client_fingerprint,
        reason_code=reason_code,
        note=note,
        payload={"job_id": job_id},
    )
    return job

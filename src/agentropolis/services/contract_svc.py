"""Player Contract service - escrow-backed player-to-player contracts.

Proposer puts up escrow. Acceptor agrees. On fulfillment, escrow + reward transfer.
On expiry/cancellation, escrow returns minus reputation penalty.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models.agent import Agent
from agentropolis.models.player_contract import ContractType, PlayerContract, PlayerContractStatus

logger = logging.getLogger(__name__)


async def propose_contract(
    session: AsyncSession,
    proposer_agent_id: int,
    contract_type: str,
    region_id: int,
    title: str,
    terms: dict,
    escrow_amount: int,
    reward_amount: int,
    deadline_seconds: int = 86400,
) -> dict:
    """Propose a new contract. Freezes escrow from proposer's balance.

    Returns: {"contract_id", "status", "escrow_amount"}
    Raises: ValueError if insufficient balance
    """
    # Validate contract type
    try:
        ct = ContractType(contract_type)
    except ValueError as err:
        raise ValueError(f"Invalid contract type: {contract_type}") from err

    # Lock proposer and check balance
    result = await session.execute(
        select(Agent).where(Agent.id == proposer_agent_id).with_for_update()
    )
    proposer = result.scalar_one_or_none()
    if proposer is None:
        raise ValueError(f"Agent {proposer_agent_id} not found")

    total_escrow = escrow_amount + reward_amount
    if proposer.personal_balance < total_escrow:
        raise ValueError(
            f"Insufficient balance: need {total_escrow}, have {proposer.personal_balance}"
        )

    # Freeze escrow
    proposer.personal_balance -= total_escrow

    now = datetime.now(UTC)
    contract = PlayerContract(
        contract_type=ct,
        proposer_agent_id=proposer_agent_id,
        region_id=region_id,
        title=title,
        terms=terms,
        escrow_amount=escrow_amount,
        reward_amount=reward_amount,
        status=PlayerContractStatus.PROPOSED,
        deadline=now + timedelta(seconds=deadline_seconds),
    )
    session.add(contract)
    await session.flush()

    return {
        "contract_id": contract.id,
        "status": contract.status.value,
        "escrow_amount": total_escrow,
    }


async def accept_contract(
    session: AsyncSession,
    acceptor_agent_id: int,
    contract_id: int,
) -> dict:
    """Accept a proposed contract.

    Returns: {"contract_id", "status", "acceptor_agent_id"}
    """
    result = await session.execute(
        select(PlayerContract).where(PlayerContract.id == contract_id).with_for_update()
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise ValueError(f"Contract {contract_id} not found")

    if contract.status != PlayerContractStatus.PROPOSED:
        raise ValueError(f"Contract {contract_id} is not in PROPOSED state")

    if contract.proposer_agent_id == acceptor_agent_id:
        raise ValueError("Cannot accept your own contract")

    contract.acceptor_agent_id = acceptor_agent_id
    contract.status = PlayerContractStatus.ACCEPTED
    contract.accepted_at = datetime.now(UTC)
    await session.flush()

    return {
        "contract_id": contract_id,
        "status": contract.status.value,
        "acceptor_agent_id": acceptor_agent_id,
    }


async def fulfill_contract(
    session: AsyncSession,
    agent_id: int,
    contract_id: int,
) -> dict:
    """Mark a contract as fulfilled. Releases escrow to acceptor.

    Only proposer can mark as fulfilled.
    Returns: {"contract_id", "status", "reward_paid"}
    """
    result = await session.execute(
        select(PlayerContract).where(PlayerContract.id == contract_id).with_for_update()
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise ValueError(f"Contract {contract_id} not found")

    if contract.status != PlayerContractStatus.ACCEPTED:
        raise ValueError(f"Contract {contract_id} is not in ACCEPTED state")

    if contract.proposer_agent_id != agent_id:
        raise ValueError("Only the proposer can mark a contract as fulfilled")

    if contract.acceptor_agent_id is None:
        raise ValueError("Contract has no acceptor")

    # Transfer reward to acceptor
    result = await session.execute(
        select(Agent).where(Agent.id == contract.acceptor_agent_id).with_for_update()
    )
    acceptor = result.scalar_one()
    acceptor.personal_balance += contract.escrow_amount + contract.reward_amount

    # Give reputation boost
    acceptor.reputation = min(100.0, acceptor.reputation + settings.REPUTATION_TRADE_BONUS)

    contract.status = PlayerContractStatus.FULFILLED
    contract.completed_at = datetime.now(UTC)
    await session.flush()

    return {
        "contract_id": contract_id,
        "status": contract.status.value,
        "reward_paid": contract.escrow_amount + contract.reward_amount,
    }


async def cancel_contract(
    session: AsyncSession,
    agent_id: int,
    contract_id: int,
) -> dict:
    """Cancel a contract. Returns escrow to proposer. Reputation penalty if accepted.

    Returns: {"contract_id", "status", "escrow_returned"}
    """
    result = await session.execute(
        select(PlayerContract).where(PlayerContract.id == contract_id).with_for_update()
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise ValueError(f"Contract {contract_id} not found")

    if contract.status not in (PlayerContractStatus.PROPOSED, PlayerContractStatus.ACCEPTED):
        raise ValueError(f"Contract {contract_id} cannot be cancelled in {contract.status} state")

    if contract.proposer_agent_id != agent_id:
        raise ValueError("Only the proposer can cancel a contract")

    # Return escrow to proposer
    result = await session.execute(
        select(Agent).where(Agent.id == contract.proposer_agent_id).with_for_update()
    )
    proposer = result.scalar_one()
    proposer.personal_balance += contract.escrow_amount + contract.reward_amount

    # Reputation penalty if already accepted
    if contract.status == PlayerContractStatus.ACCEPTED:
        proposer.reputation = max(
            -100.0, proposer.reputation + settings.REPUTATION_CONTRACT_BREACH_PENALTY
        )

    contract.status = PlayerContractStatus.CANCELLED
    contract.completed_at = datetime.now(UTC)
    await session.flush()

    return {
        "contract_id": contract_id,
        "status": contract.status.value,
        "escrow_returned": contract.escrow_amount + contract.reward_amount,
    }


async def expire_contracts(
    session: AsyncSession,
    now: datetime | None = None,
) -> dict:
    """Expire overdue contracts. Returns escrow to proposers. Housekeeping task.

    Returns: {"expired_count", "total_escrow_returned"}
    """
    if now is None:
        now = datetime.now(UTC)

    result = await session.execute(
        select(PlayerContract)
        .where(
            PlayerContract.status.in_([
                PlayerContractStatus.PROPOSED,
                PlayerContractStatus.ACCEPTED,
            ]),
            PlayerContract.deadline <= now,
        )
        .with_for_update()
    )
    contracts = list(result.scalars().all())

    total_returned = 0
    for contract in contracts:
        # Return escrow to proposer
        result = await session.execute(
            select(Agent).where(Agent.id == contract.proposer_agent_id).with_for_update()
        )
        proposer = result.scalar_one()
        refund = contract.escrow_amount + contract.reward_amount
        proposer.personal_balance += refund
        total_returned += refund

        contract.status = PlayerContractStatus.EXPIRED
        contract.completed_at = now

    await session.flush()

    return {
        "expired_count": len(contracts),
        "total_escrow_returned": total_returned,
    }


async def get_contract(
    session: AsyncSession,
    contract_id: int,
) -> dict:
    """Get contract details."""
    result = await session.execute(
        select(PlayerContract).where(PlayerContract.id == contract_id)
    )
    c = result.scalar_one_or_none()
    if c is None:
        raise ValueError(f"Contract {contract_id} not found")

    return {
        "contract_id": c.id,
        "contract_type": c.contract_type.value,
        "proposer_agent_id": c.proposer_agent_id,
        "acceptor_agent_id": c.acceptor_agent_id,
        "region_id": c.region_id,
        "title": c.title,
        "terms": c.terms,
        "escrow_amount": c.escrow_amount,
        "reward_amount": c.reward_amount,
        "status": c.status.value,
        "deadline": c.deadline.isoformat() if c.deadline else None,
        "created_at": c.created_at.isoformat(),
    }


async def list_contracts(
    session: AsyncSession,
    region_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    """List contracts, optionally filtered by region and status."""
    query = select(PlayerContract)
    if region_id is not None:
        query = query.where(PlayerContract.region_id == region_id)
    if status is not None:
        query = query.where(PlayerContract.status == PlayerContractStatus(status))

    result = await session.execute(query.order_by(PlayerContract.created_at.desc()))
    contracts = result.scalars().all()

    return [
        {
            "contract_id": c.id,
            "contract_type": c.contract_type.value,
            "proposer_agent_id": c.proposer_agent_id,
            "acceptor_agent_id": c.acceptor_agent_id,
            "region_id": c.region_id,
            "title": c.title,
            "status": c.status.value,
            "escrow_amount": c.escrow_amount,
            "reward_amount": c.reward_amount,
            "deadline": c.deadline.isoformat() if c.deadline else None,
            "created_at": c.created_at.isoformat(),
        }
        for c in contracts
    ]

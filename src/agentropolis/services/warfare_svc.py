"""Warfare service - mercenary contracts, combat, building sabotage, transport raids.

Core game loop:
  Hoard resources → Post contract (escrow bounty) → Mercenaries enlist → Execute attack
  → Building disabled / transport lost → Supply drops → Price spikes → Sell for profit

All combat is deterministic (no randomness). Power is calculated from skill levels and health.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agentropolis.config import settings
from agentropolis.models.agent import Agent
from agentropolis.models.building import Building, BuildingStatus
from agentropolis.models.company import Company
from agentropolis.models.mercenary_contract import (
    ContractParticipant,
    ContractStatus,
    MercenaryContract,
    MissionType,
    ParticipantRole,
    ParticipantStatus,
)
from agentropolis.models.region import Region, SafetyTier
from agentropolis.models.transport_order import TransportOrder, TransportStatus
from agentropolis.services.treaty_effects_svc import (
    check_mutual_defense,
    check_warfare_blocked,
    get_mutual_defense_allies,
    get_treaty_between,
)

logger = logging.getLogger(__name__)

# Reputation penalties per region safety tier
REPUTATION_PENALTY = {
    SafetyTier.WILDERNESS: -5.0,
    SafetyTier.RESOURCE: -10.0,
    SafetyTier.BORDER: -20.0,
    SafetyTier.CORE: None,  # combat forbidden
}

COMBAT_XP_BASE = 20


def _normalize_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


# ─── Combat Power Calculations ──────────────────────────────────────────────


def _agent_combat_power(
    agent: Agent,
    melee_level: int,
    *,
    attack_mult: float = 1.0,
    defense_mult: float = 1.0,
    trait_attack_bonus: float = 0.0,
    trait_defense_bonus: float = 0.0,
    role: str = "attacker",
) -> float:
    """Calculate an agent's combat power from melee skill, health, and strategy modifiers.

    Strategy profile (doctrine) and trait bonuses are applied here:
    - attack_mult/defense_mult come from StrategyProfile.combat_doctrine
    - trait_attack_bonus/trait_defense_bonus come from AgentTrait (WARMONGER/IRON_WALL)
    """
    base_power = melee_level * 10 + agent.health * 0.3

    if role == "attacker":
        return base_power * attack_mult * (1.0 + trait_attack_bonus)
    else:
        return base_power * defense_mult * (1.0 + trait_defense_bonus)


def _get_skill_level(agent: Agent, skill_name: str) -> int:
    """Get an agent's level in a given skill (0 if not learned)."""
    for skill in agent.skills:
        if skill.skill_name == skill_name:
            return skill.level
    return 0


async def _gather_combat_modifiers(
    session: AsyncSession, agent_ids: list[int]
) -> dict[int, dict]:
    """Gather strategy profile + trait modifiers for a set of agents.

    Returns {agent_id: {"attack_mult", "defense_mult", "trait_attack_bonus", "trait_defense_bonus"}}
    """
    from agentropolis.services.strategy_svc import get_combat_modifiers, get_profile
    from agentropolis.services.trait_svc import get_combat_trait_modifiers

    modifiers: dict[int, dict] = {}
    for aid in agent_ids:
        profile = await get_profile(session, aid)
        combat_mods = get_combat_modifiers(profile)
        trait_mods = await get_combat_trait_modifiers(session, aid)
        modifiers[aid] = {
            "attack_mult": combat_mods["attack_mult"],
            "defense_mult": combat_mods["defense_mult"],
            "trait_attack_bonus": trait_mods["attack_bonus"],
            "trait_defense_bonus": trait_mods["defense_bonus"],
        }
    return modifiers


def calculate_sabotage(
    attackers: list[tuple[Agent, int]],
    defenders: list[tuple[Agent, int]],
    building_durability: float,
    leader_tactics_level: int = 0,
    fortification_level: int = 0,
    attacker_modifiers: dict[int, dict] | None = None,
    defender_modifiers: dict[int, dict] | None = None,
) -> dict:
    """Calculate sabotage battle outcome. Deterministic, no randomness.

    Args:
        attackers: list of (Agent, melee_level) tuples
        defenders: list of (Agent, melee_level) tuples (garrison)
        building_durability: current durability 0-100
        leader_tactics_level: highest Tactics skill among attackers
        fortification_level: highest Fortification skill among defenders
        attacker_modifiers: {agent_id: {"attack_mult", "trait_attack_bonus", ...}}
        defender_modifiers: {agent_id: {"defense_mult", "trait_defense_bonus", ...}}

    Returns:
        dict with damage values and outcome
    """
    atk_mods = attacker_modifiers or {}
    def_mods = defender_modifiers or {}

    attacker_power = sum(
        _agent_combat_power(
            a, ml,
            role="attacker",
            **{k: v for k, v in atk_mods.get(a.id, {}).items()
               if k in ("attack_mult", "defense_mult", "trait_attack_bonus", "trait_defense_bonus")},
        )
        for a, ml in attackers
    )
    attacker_power += leader_tactics_level * 5  # leader bonus

    defender_power = sum(
        _agent_combat_power(
            d, ml,
            role="defender",
            **{k: v for k, v in def_mods.get(d.id, {}).items()
               if k in ("attack_mult", "defense_mult", "trait_attack_bonus", "trait_defense_bonus")},
        )
        for d, ml in defenders
    )
    defender_power += building_durability * 0.5
    defender_power += fortification_level * 8  # fortification bonus

    total_power = attacker_power + defender_power
    if total_power <= 0:
        total_power = 1  # avoid division by zero

    damage_ratio = attacker_power / total_power

    n_attackers = len(attackers)
    n_defenders = max(len(defenders), 1)

    building_damage = damage_ratio * settings.WARFARE_BASE_SABOTAGE_DAMAGE * n_attackers
    attacker_hp_loss = (1 - damage_ratio) * settings.WARFARE_BASE_COUNTER_DAMAGE / n_attackers
    defender_hp_loss = damage_ratio * settings.WARFARE_BASE_ATTACK_DAMAGE / n_defenders

    return {
        "attacker_power": attacker_power,
        "defender_power": defender_power,
        "damage_ratio": round(damage_ratio, 4),
        "building_damage": round(building_damage, 2),
        "attacker_hp_loss": round(attacker_hp_loss, 2),
        "defender_hp_loss": round(defender_hp_loss, 2),
    }


def calculate_raid(
    raiders: list[tuple[Agent, int]],
    escorts: list[tuple[Agent, int]],
    raider_modifiers: dict[int, dict] | None = None,
    escort_modifiers: dict[int, dict] | None = None,
) -> dict:
    """Calculate transport raid outcome. Deterministic.

    Args:
        raiders: list of (Agent, melee_level) tuples
        escorts: list of (Agent, melee_level) tuples
        raider_modifiers: {agent_id: {"attack_mult", "trait_attack_bonus", ...}}
        escort_modifiers: {agent_id: {"defense_mult", "trait_defense_bonus", ...}}

    Returns:
        dict with intercept_ratio and success flag
    """
    r_mods = raider_modifiers or {}
    e_mods = escort_modifiers or {}

    raider_power = sum(
        _agent_combat_power(
            a, ml,
            role="attacker",
            **{k: v for k, v in r_mods.get(a.id, {}).items()
               if k in ("attack_mult", "defense_mult", "trait_attack_bonus", "trait_defense_bonus")},
        )
        for a, ml in raiders
    )
    escort_power = sum(
        _agent_combat_power(
            e, ml,
            role="defender",
            **{k: v for k, v in e_mods.get(e.id, {}).items()
               if k in ("attack_mult", "defense_mult", "trait_attack_bonus", "trait_defense_bonus")},
        )
        for e, ml in escorts
    ) + 20  # base defense

    total = raider_power + escort_power
    if total <= 0:
        total = 1

    intercept_ratio = raider_power / total
    success = intercept_ratio > settings.WARFARE_RAID_SUCCESS_THRESHOLD

    raider_hp_loss = 0.0
    escort_hp_loss = 0.0
    if success:
        escort_hp_loss = intercept_ratio * 15.0 / max(len(escorts), 1)
        raider_hp_loss = (1 - intercept_ratio) * 10.0 / max(len(raiders), 1)
    else:
        raider_hp_loss = (1 - intercept_ratio) * 25.0 / max(len(raiders), 1)
        escort_hp_loss = intercept_ratio * 5.0 / max(len(escorts), 1)

    return {
        "raider_power": raider_power,
        "escort_power": escort_power,
        "intercept_ratio": round(intercept_ratio, 4),
        "success": success,
        "raider_hp_loss": round(raider_hp_loss, 2),
        "escort_hp_loss": round(escort_hp_loss, 2),
        "loot_fraction": round(intercept_ratio, 2) if success else 0.0,
    }


# ─── Contract Management ────────────────────────────────────────────────────


async def create_contract(
    session: AsyncSession,
    employer_agent_id: int,
    mission_type: str,
    target_region_id: int,
    reward_per_agent: int,
    max_agents: int,
    *,
    target_building_id: int | None = None,
    target_transport_id: int | None = None,
    mission_duration_seconds: int = 300,
    expires_in_seconds: int = 3600,
    now: datetime | None = None,
) -> dict:
    """Create a mercenary contract with escrowed bounty.

    Deducts escrow_total = reward_per_agent * max_agents from employer balance.
    """
    now = now or datetime.now(UTC)

    # Load employer with FOR UPDATE
    result = await session.execute(
        select(Agent).where(Agent.id == employer_agent_id).with_for_update()
    )
    employer = result.scalar_one_or_none()
    if not employer:
        raise ValueError("Employer agent not found")
    if not employer.is_alive:
        raise ValueError("Dead agents cannot create contracts")

    # Validate target region
    result = await session.execute(
        select(Region).where(Region.id == target_region_id)
    )
    region = result.scalar_one_or_none()
    if not region:
        raise ValueError("Target region not found")
    if region.safety_tier == SafetyTier.CORE:
        raise ValueError("Combat is forbidden in CORE regions")

    # Validate mission type
    mission = MissionType(mission_type)

    target_building_owner_agent_id: int | None = None
    target_transport_owner_agent_id: int | None = None

    # Validate target
    if mission in (MissionType.SABOTAGE_BUILDING, MissionType.DEFEND_BUILDING):
        if not target_building_id:
            raise ValueError(f"target_building_id required for {mission}")
        result = await session.execute(
            select(Building).where(Building.id == target_building_id)
        )
        building = result.scalar_one_or_none()
        if not building:
            raise ValueError("Target building not found")
        if building.region_id != target_region_id:
            raise ValueError("Building is not in the target region")
        target_building_owner_agent_id = building.agent_id

    if mission in (MissionType.RAID_TRANSPORT, MissionType.ESCORT_TRANSPORT):
        if not target_transport_id:
            raise ValueError(f"target_transport_id required for {mission}")
        result = await session.execute(
            select(TransportOrder).where(TransportOrder.id == target_transport_id)
        )
        transport = result.scalar_one_or_none()
        if not transport:
            raise ValueError("Target transport not found")
        if transport.owner_agent_id is not None:
            target_transport_owner_agent_id = transport.owner_agent_id
        elif transport.owner_company_id is not None:
            result = await session.execute(
                select(Agent).join(Company, Company.founder_agent_id == Agent.id).where(
                    Company.id == transport.owner_company_id
                )
            )
            owner_agent = result.scalar_one_or_none()
            if owner_agent is not None:
                target_transport_owner_agent_id = owner_agent.id

    blocked_defender_id = target_building_owner_agent_id or target_transport_owner_agent_id
    if blocked_defender_id is not None:
        is_blocked = await _check_treaty_block(session, employer_agent_id, blocked_defender_id)
        if is_blocked:
            raise ValueError("Active treaty blocks warfare against this target")

    # Calculate and deduct escrow
    escrow_total = reward_per_agent * max_agents
    if escrow_total <= 0:
        raise ValueError("Escrow must be positive")
    if employer.personal_balance < escrow_total:
        raise ValueError(
            f"Insufficient balance: need {escrow_total}, have {employer.personal_balance}"
        )

    employer.personal_balance -= escrow_total

    contract = MercenaryContract(
        employer_agent_id=employer_agent_id,
        mission_type=mission,
        target_building_id=target_building_id,
        target_region_id=target_region_id,
        target_transport_id=target_transport_id,
        reward_per_agent=reward_per_agent,
        max_agents=max_agents,
        escrow_total=escrow_total,
        mission_duration_seconds=mission_duration_seconds,
        expires_at=now + timedelta(seconds=expires_in_seconds),
        status=ContractStatus.OPEN,
    )
    session.add(contract)
    await session.flush()

    mutual_defense_contracts = 0
    if mission == MissionType.SABOTAGE_BUILDING and target_building_owner_agent_id is not None:
        mutual_defense_contracts = await _spawn_mutual_defense_contracts(
            session,
            defender_agent_id=target_building_owner_agent_id,
            target_building_id=target_building_id,
            target_region_id=target_region_id,
            now=now,
        )

    logger.info("Contract %d created by agent %d, escrow=%d", contract.id, employer_agent_id, escrow_total)

    # Decision log: creating a contract is a strategic combat decision
    from agentropolis.services.training_hooks import log_combat_decision

    await log_combat_decision(
        session, employer_agent_id,
        role="attacker" if mission in (MissionType.SABOTAGE_BUILDING, MissionType.RAID_TRANSPORT) else "defender",
        contract_id=contract.id,
        mission_type=mission.value,
        region_id=target_region_id,
        reward=0,
        result=None,
    )

    return {
        "contract_id": contract.id,
        "mission_type": contract.mission_type.value,
        "target_region_id": contract.target_region_id,
        "reward_per_agent": contract.reward_per_agent,
        "max_agents": contract.max_agents,
        "escrow_total": contract.escrow_total,
        "expires_at": contract.expires_at.isoformat(),
        "status": contract.status.value,
        "mutual_defense_contracts_created": mutual_defense_contracts,
    }


async def enlist_in_contract(
    session: AsyncSession,
    agent_id: int,
    contract_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    """Enlist an agent as a mercenary in a contract."""
    now = now or datetime.now(UTC)

    # Load contract
    result = await session.execute(
        select(MercenaryContract)
        .where(MercenaryContract.id == contract_id)
        .options(selectinload(MercenaryContract.participants))
        .with_for_update()
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise ValueError("Contract not found")
    if contract.status != ContractStatus.OPEN:
        raise ValueError(f"Contract is {contract.status}, not open for enlistment")
    if (_normalize_timestamp(contract.expires_at) or now) < now:
        raise ValueError("Contract has expired")
    if contract.employer_agent_id == agent_id:
        raise ValueError("Cannot enlist in your own contract")

    # Check agent
    result = await session.execute(
        select(Agent).where(Agent.id == agent_id).options(selectinload(Agent.skills))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise ValueError("Agent not found")
    if not agent.is_alive:
        raise ValueError("Dead agents cannot enlist")

    # Check not already enlisted
    for p in contract.participants:
        if p.agent_id == agent_id:
            raise ValueError("Already enlisted in this contract")

    # Check max agents
    current_count = len([p for p in contract.participants if p.status == ParticipantStatus.ENLISTED])
    if current_count >= contract.max_agents:
        raise ValueError("Contract is full")

    # Determine role
    role = ParticipantRole.ATTACKER
    if contract.mission_type in (MissionType.DEFEND_BUILDING, MissionType.ESCORT_TRANSPORT):
        role = ParticipantRole.DEFENDER

    participant = ContractParticipant(
        contract_id=contract_id,
        agent_id=agent_id,
        role=role,
        status=ParticipantStatus.ENLISTED,
    )
    session.add(participant)
    await session.flush()

    return {
        "contract_id": contract_id,
        "agent_id": agent_id,
        "role": role.value,
        "status": ParticipantStatus.ENLISTED.value,
        "enlisted_count": current_count + 1,
        "max_agents": contract.max_agents,
    }


async def activate_contract(
    session: AsyncSession,
    contract_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    """Activate a contract (employer only, transitions OPEN → ACTIVE)."""
    now = now or datetime.now(UTC)

    result = await session.execute(
        select(MercenaryContract)
        .where(MercenaryContract.id == contract_id)
        .options(selectinload(MercenaryContract.participants))
        .with_for_update()
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise ValueError("Contract not found")
    if contract.status != ContractStatus.OPEN:
        raise ValueError(f"Contract is {contract.status}, cannot activate")
    if (_normalize_timestamp(contract.expires_at) or now) < now:
        raise ValueError("Contract has expired")

    enlisted = [p for p in contract.participants if p.status == ParticipantStatus.ENLISTED]
    if not enlisted:
        raise ValueError("No mercenaries enlisted")

    contract.status = ContractStatus.ACTIVE
    contract.activated_at = now

    for p in enlisted:
        p.status = ParticipantStatus.ACTIVE

    await session.flush()

    return {
        "contract_id": contract.id,
        "status": contract.status.value,
        "activated_at": contract.activated_at.isoformat(),
        "active_agents": len(enlisted),
    }


async def cancel_contract(
    session: AsyncSession,
    agent_id: int,
    contract_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    """Cancel a contract. Only the employer can cancel. Refunds escrow minus fee."""
    now = now or datetime.now(UTC)

    result = await session.execute(
        select(MercenaryContract)
        .where(MercenaryContract.id == contract_id)
        .with_for_update()
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise ValueError("Contract not found")
    if contract.employer_agent_id != agent_id:
        raise ValueError("Only the employer can cancel a contract")
    if contract.status not in (ContractStatus.OPEN, ContractStatus.ACTIVE):
        raise ValueError(f"Contract is {contract.status}, cannot cancel")

    # Calculate refund (minus cancellation fee)
    fee = int(contract.escrow_total * settings.WARFARE_CONTRACT_CANCEL_FEE_PCT)
    refund = contract.escrow_total - fee

    # Refund employer
    result = await session.execute(
        select(Agent).where(Agent.id == agent_id).with_for_update()
    )
    employer = result.scalar_one_or_none()
    if employer:
        employer.personal_balance += refund

    contract.status = ContractStatus.CANCELLED
    contract.completed_at = now

    await session.flush()

    return {
        "contract_id": contract.id,
        "status": ContractStatus.CANCELLED.value,
        "refund": refund,
        "fee": fee,
    }


# ─── Combat Execution ───────────────────────────────────────────────────────


async def _check_treaty_block(session: AsyncSession, attacker_id: int, defender_owner_id: int) -> bool:
    treaties = await get_treaty_between(session, attacker_id, defender_owner_id)
    return check_warfare_blocked(treaties)


async def _spawn_mutual_defense_contracts(
    session: AsyncSession,
    *,
    defender_agent_id: int,
    target_building_id: int | None,
    target_region_id: int,
    now: datetime,
) -> int:
    allies = await get_mutual_defense_allies(session, defender_agent_id)
    created = 0
    for ally_id in allies:
        treaties = await get_treaty_between(session, defender_agent_id, ally_id)
        if not check_mutual_defense(treaties):
            continue
        existing = await session.execute(
            select(MercenaryContract).where(
                MercenaryContract.employer_agent_id == ally_id,
                MercenaryContract.mission_type == MissionType.DEFEND_BUILDING,
                MercenaryContract.target_building_id == target_building_id,
                MercenaryContract.status.in_([ContractStatus.OPEN, ContractStatus.ACTIVE]),
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        session.add(
            MercenaryContract(
                employer_agent_id=ally_id,
                mission_type=MissionType.DEFEND_BUILDING,
                target_building_id=target_building_id,
                target_region_id=target_region_id,
                reward_per_agent=0,
                max_agents=settings.WARFARE_MAX_GARRISON_PER_BUILDING,
                escrow_total=0,
                mission_duration_seconds=0,
                expires_at=now + timedelta(hours=6),
                status=ContractStatus.OPEN,
                result_summary={"source": "mutual_defense"},
            )
        )
        created += 1
    if created:
        await session.flush()
    return created


async def execute_sabotage(
    session: AsyncSession,
    contract_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    """Execute a building sabotage mission.

    Applies deterministic combat formula, damages building, applies HP/XP/reputation changes.
    """
    now = now or datetime.now(UTC)

    # Load contract with participants
    result = await session.execute(
        select(MercenaryContract)
        .where(MercenaryContract.id == contract_id)
        .options(
            selectinload(MercenaryContract.participants).selectinload(ContractParticipant.agent).selectinload(Agent.skills),
            selectinload(MercenaryContract.target_building),
        )
        .with_for_update()
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise ValueError("Contract not found")
    if contract.status != ContractStatus.ACTIVE:
        raise ValueError(f"Contract is {contract.status}, must be ACTIVE to execute")
    if contract.mission_type != MissionType.SABOTAGE_BUILDING:
        raise ValueError("Contract is not a sabotage mission")

    # Check region safety
    result = await session.execute(
        select(Region).where(Region.id == contract.target_region_id)
    )
    region = result.scalar_one_or_none()
    if region and region.safety_tier == SafetyTier.CORE:
        raise ValueError("Combat is forbidden in CORE regions")

    # Load target building with FOR UPDATE
    result = await session.execute(
        select(Building).where(Building.id == contract.target_building_id).with_for_update()
    )
    building = result.scalar_one_or_none()
    if not building:
        raise ValueError("Target building not found")

    if building.agent_id is not None:
        has_treaty = await _check_treaty_block(session, contract.employer_agent_id, building.agent_id)
        if has_treaty:
            raise ValueError("Active treaty blocks warfare against this target")

    # Gather attackers
    active_attackers = [
        p for p in contract.participants
        if p.status == ParticipantStatus.ACTIVE and p.role == ParticipantRole.ATTACKER
    ]
    if not active_attackers:
        raise ValueError("No active attackers")

    attacker_data = []
    leader_tactics = 0
    for p in active_attackers:
        agent = p.agent
        melee = _get_skill_level(agent, "Melee")
        tactics = _get_skill_level(agent, "Tactics")
        leader_tactics = max(leader_tactics, tactics)
        attacker_data.append((agent, melee))

    # Gather defenders (garrison — agents assigned to defend this building via other contracts)
    defender_data = []
    fortification = 0
    # Check for active DEFEND_BUILDING contracts on this building
    defend_result = await session.execute(
        select(MercenaryContract)
        .where(
            MercenaryContract.target_building_id == building.id,
            MercenaryContract.mission_type == MissionType.DEFEND_BUILDING,
            MercenaryContract.status == ContractStatus.ACTIVE,
        )
        .options(
            selectinload(MercenaryContract.participants).selectinload(ContractParticipant.agent).selectinload(Agent.skills)
        )
    )
    defend_contracts = defend_result.scalars().all()
    for dc in defend_contracts:
        for dp in dc.participants:
            if dp.status == ParticipantStatus.ACTIVE and dp.role == ParticipantRole.DEFENDER:
                agent = dp.agent
                melee = _get_skill_level(agent, "Melee")
                fort = _get_skill_level(agent, "Fortification")
                fortification = max(fortification, fort)
                defender_data.append((agent, melee))

    # Gather strategy + trait combat modifiers
    all_agent_ids = [a.id for a, _ in attacker_data] + [d.id for d, _ in defender_data]
    combat_mods = await _gather_combat_modifiers(session, all_agent_ids)
    atk_mods = {a.id: combat_mods.get(a.id, {}) for a, _ in attacker_data}
    def_mods = {d.id: combat_mods.get(d.id, {}) for d, _ in defender_data}

    # Calculate combat
    combat = calculate_sabotage(
        attackers=attacker_data,
        defenders=defender_data,
        building_durability=building.durability,
        leader_tactics_level=leader_tactics,
        fortification_level=fortification,
        attacker_modifiers=atk_mods,
        defender_modifiers=def_mods,
    )

    # Apply building damage
    old_durability = building.durability
    building.durability = max(0.0, building.durability - combat["building_damage"])
    if building.durability <= 0:
        building.status = BuildingStatus.DISABLED
    building.last_durability_at = now

    # Apply attacker HP loss and XP
    for p in active_attackers:
        agent = p.agent
        agent.health = max(0.0, agent.health - combat["attacker_hp_loss"])
        p.health_lost = combat["attacker_hp_loss"]
        p.xp_earned = COMBAT_XP_BASE
        if agent.health <= 0:
            agent.is_alive = False
            agent.personal_balance = int(agent.personal_balance * (1 - settings.AGENT_RESPAWN_PENALTY))
            p.status = ParticipantStatus.FAILED
        else:
            p.status = ParticipantStatus.SUCCEEDED

    # Apply defender HP loss
    for dc in defend_contracts:
        for dp in dc.participants:
            if dp.status == ParticipantStatus.ACTIVE and dp.role == ParticipantRole.DEFENDER:
                dp.agent.health = max(0.0, dp.agent.health - combat["defender_hp_loss"])
                dp.health_lost = combat["defender_hp_loss"]
                dp.xp_earned = COMBAT_XP_BASE
                if dp.agent.health <= 0:
                    dp.agent.is_alive = False
                    dp.agent.personal_balance = int(dp.agent.personal_balance * (1 - settings.AGENT_RESPAWN_PENALTY))
                    dp.status = ParticipantStatus.FAILED
                else:
                    dp.status = ParticipantStatus.SUCCEEDED

    # Reputation penalty for attackers' employer
    rep_penalty = REPUTATION_PENALTY.get(region.safety_tier if region else SafetyTier.WILDERNESS, -5.0)
    if rep_penalty is not None:
        result = await session.execute(
            select(Agent).where(Agent.id == contract.employer_agent_id).with_for_update()
        )
        employer = result.scalar_one_or_none()
        if employer:
            employer.reputation += rep_penalty

    # Pay mercenaries
    for p in active_attackers:
        if p.status == ParticipantStatus.SUCCEEDED:
            p.reward_paid = contract.reward_per_agent
            p.agent.personal_balance += contract.reward_per_agent

    # Mark contract completed
    contract.status = ContractStatus.COMPLETED
    contract.completed_at = now
    contract.result_summary = {
        "combat": combat,
        "building_damage_applied": round(old_durability - building.durability, 2),
        "building_new_durability": building.durability,
        "building_disabled": building.durability <= 0,
        "attackers_survived": sum(1 for p in active_attackers if p.status == ParticipantStatus.SUCCEEDED),
        "defenders_count": len(defender_data),
    }

    await session.flush()

    # ── Decision log hooks ──
    from agentropolis.services.training_hooks import log_combat_decision

    for p in active_attackers:
        await log_combat_decision(
            session, p.agent.id,
            role="attacker",
            contract_id=contract.id,
            mission_type="sabotage_building",
            region_id=contract.target_region_id,
            reward=p.reward_paid or 0,
            enemy_count=len(defender_data),
            ally_count=len(active_attackers),
            result="victory" if p.status == ParticipantStatus.SUCCEEDED else "defeat",
            damage_dealt=combat["building_damage"] / max(len(active_attackers), 1),
            damage_taken=combat["attacker_hp_loss"],
        )
    for dc in defend_contracts:
        for dp in dc.participants:
            if dp.role == ParticipantRole.DEFENDER:
                await log_combat_decision(
                    session, dp.agent.id,
                    role="defender",
                    contract_id=contract.id,
                    mission_type="sabotage_building",
                    region_id=contract.target_region_id,
                    reward=0,
                    enemy_count=len(active_attackers),
                    ally_count=len(defender_data),
                    result="victory" if building.durability > 0 else "defeat",
                    damage_dealt=combat["defender_hp_loss"],
                    damage_taken=combat["attacker_hp_loss"],
                )

    logger.info(
        "Sabotage executed: contract=%d building=%d damage=%.1f durability=%.1f→%.1f",
        contract.id, building.id, combat["building_damage"], old_durability, building.durability,
    )

    return contract.result_summary


async def execute_transport_raid(
    session: AsyncSession,
    contract_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    """Execute a transport raid mission.

    If successful, cargo is proportionally seized and transport is marked LOST.
    """
    now = now or datetime.now(UTC)

    # Load contract
    result = await session.execute(
        select(MercenaryContract)
        .where(MercenaryContract.id == contract_id)
        .options(
            selectinload(MercenaryContract.participants).selectinload(ContractParticipant.agent).selectinload(Agent.skills),
        )
        .with_for_update()
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise ValueError("Contract not found")
    if contract.status != ContractStatus.ACTIVE:
        raise ValueError(f"Contract is {contract.status}, must be ACTIVE")
    if contract.mission_type != MissionType.RAID_TRANSPORT:
        raise ValueError("Contract is not a raid mission")

    # Load transport
    result = await session.execute(
        select(TransportOrder)
        .where(TransportOrder.id == contract.target_transport_id)
        .with_for_update()
    )
    transport = result.scalar_one_or_none()
    if not transport:
        raise ValueError("Target transport not found")
    if transport.status != TransportStatus.IN_TRANSIT:
        raise ValueError(f"Transport is {transport.status}, must be IN_TRANSIT")

    # Gather raiders
    active_raiders = [
        p for p in contract.participants
        if p.status == ParticipantStatus.ACTIVE and p.role == ParticipantRole.ATTACKER
    ]
    if not active_raiders:
        raise ValueError("No active raiders")

    raider_data = [(p.agent, _get_skill_level(p.agent, "Melee")) for p in active_raiders]

    # Gather escorts (active ESCORT_TRANSPORT contracts for this transport)
    escort_data = []
    escort_result = await session.execute(
        select(MercenaryContract)
        .where(
            MercenaryContract.target_transport_id == transport.id,
            MercenaryContract.mission_type == MissionType.ESCORT_TRANSPORT,
            MercenaryContract.status == ContractStatus.ACTIVE,
        )
        .options(
            selectinload(MercenaryContract.participants).selectinload(ContractParticipant.agent).selectinload(Agent.skills)
        )
    )
    escort_contracts = escort_result.scalars().all()
    for ec in escort_contracts:
        for ep in ec.participants:
            if ep.status == ParticipantStatus.ACTIVE and ep.role == ParticipantRole.DEFENDER:
                escort_data.append((ep.agent, _get_skill_level(ep.agent, "Melee")))

    # Gather strategy + trait combat modifiers
    all_raid_ids = [a.id for a, _ in raider_data] + [e.id for e, _ in escort_data]
    raid_mods = await _gather_combat_modifiers(session, all_raid_ids)
    r_mods = {a.id: raid_mods.get(a.id, {}) for a, _ in raider_data}
    esc_mods = {e.id: raid_mods.get(e.id, {}) for e, _ in escort_data}

    # Calculate raid
    combat = calculate_raid(
        raiders=raider_data, escorts=escort_data,
        raider_modifiers=r_mods, escort_modifiers=esc_mods,
    )

    # Apply results
    looted_items: dict[str, int] = {}
    if combat["success"]:
        # Transport is intercepted — cargo proportionally looted
        transport.status = TransportStatus.LOST
        loot_frac = combat["loot_fraction"]
        for ticker, qty in (transport.items or {}).items():
            looted_qty = int(qty * loot_frac)
            if looted_qty > 0:
                looted_items[ticker] = looted_qty

    # Apply HP changes
    for p in active_raiders:
        p.agent.health = max(0.0, p.agent.health - combat["raider_hp_loss"])
        p.health_lost = combat["raider_hp_loss"]
        p.xp_earned = COMBAT_XP_BASE
        if p.agent.health <= 0:
            p.agent.is_alive = False
            p.agent.personal_balance = int(p.agent.personal_balance * (1 - settings.AGENT_RESPAWN_PENALTY))
            p.status = ParticipantStatus.FAILED
        else:
            p.status = ParticipantStatus.SUCCEEDED if combat["success"] else ParticipantStatus.FAILED

    # Apply escort HP
    for ec in escort_contracts:
        for ep in ec.participants:
            if ep.status == ParticipantStatus.ACTIVE and ep.role == ParticipantRole.DEFENDER:
                ep.agent.health = max(0.0, ep.agent.health - combat["escort_hp_loss"])
                ep.health_lost = combat["escort_hp_loss"]
                ep.xp_earned = COMBAT_XP_BASE
                if ep.agent.health <= 0:
                    ep.agent.is_alive = False
                    ep.status = ParticipantStatus.FAILED
                else:
                    ep.status = ParticipantStatus.SUCCEEDED if not combat["success"] else ParticipantStatus.FAILED

    # Reputation penalty
    region_result = await session.execute(
        select(Region).where(Region.id == contract.target_region_id)
    )
    region = region_result.scalar_one_or_none()
    rep_penalty = REPUTATION_PENALTY.get(region.safety_tier if region else SafetyTier.WILDERNESS, -5.0)
    if rep_penalty is not None:
        result = await session.execute(
            select(Agent).where(Agent.id == contract.employer_agent_id).with_for_update()
        )
        employer = result.scalar_one_or_none()
        if employer:
            employer.reputation += rep_penalty

    # Pay mercenaries if successful
    if combat["success"]:
        for p in active_raiders:
            if p.status == ParticipantStatus.SUCCEEDED:
                p.reward_paid = contract.reward_per_agent
                p.agent.personal_balance += contract.reward_per_agent

    # Complete contract
    contract.status = ContractStatus.COMPLETED if combat["success"] else ContractStatus.FAILED
    contract.completed_at = now
    contract.result_summary = {
        "combat": combat,
        "looted_items": looted_items,
        "transport_lost": combat["success"],
        "raiders_survived": sum(1 for p in active_raiders if p.status == ParticipantStatus.SUCCEEDED),
    }

    # Refund escrow if raid failed
    if not combat["success"]:
        result = await session.execute(
            select(Agent).where(Agent.id == contract.employer_agent_id).with_for_update()
        )
        employer = result.scalar_one_or_none()
        if employer:
            # Partial refund (minus fee)
            fee = int(contract.escrow_total * settings.WARFARE_CONTRACT_CANCEL_FEE_PCT)
            employer.personal_balance += contract.escrow_total - fee

    await session.flush()

    # ── Decision log hooks ──
    from agentropolis.services.training_hooks import log_combat_decision

    for p in active_raiders:
        await log_combat_decision(
            session, p.agent.id,
            role="attacker",
            contract_id=contract.id,
            mission_type="raid_transport",
            region_id=contract.target_region_id,
            reward=p.reward_paid or 0,
            enemy_count=len(escort_data),
            ally_count=len(active_raiders),
            result="victory" if combat["success"] and p.status == ParticipantStatus.SUCCEEDED else "defeat",
            damage_dealt=combat["escort_hp_loss"],
            damage_taken=combat["raider_hp_loss"],
        )
    for ec in escort_contracts:
        for ep in ec.participants:
            if ep.role == ParticipantRole.DEFENDER:
                await log_combat_decision(
                    session, ep.agent.id,
                    role="defender",
                    contract_id=contract.id,
                    mission_type="raid_transport",
                    region_id=contract.target_region_id,
                    reward=0,
                    enemy_count=len(active_raiders),
                    ally_count=len(escort_data),
                    result="victory" if not combat["success"] else "defeat",
                    damage_dealt=combat["raider_hp_loss"],
                    damage_taken=combat["escort_hp_loss"],
                )

    logger.info(
        "Transport raid: contract=%d transport=%d success=%s",
        contract.id, transport.id, combat["success"],
    )

    return contract.result_summary


# ─── Garrison / Defense ─────────────────────────────────────────────────────


async def garrison_building(
    session: AsyncSession,
    agent_id: int,
    building_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    """Assign an agent to garrison (defend) a building.

    Creates or joins a DEFEND_BUILDING contract for this building.
    """
    now = now or datetime.now(UTC)

    # Validate agent
    result = await session.execute(
        select(Agent).where(Agent.id == agent_id).options(selectinload(Agent.skills))
    )
    agent = result.scalar_one_or_none()
    if not agent or not agent.is_alive:
        raise ValueError("Agent not found or dead")

    # Validate building
    result = await session.execute(
        select(Building).where(Building.id == building_id).with_for_update()
    )
    building = result.scalar_one_or_none()
    if not building:
        raise ValueError("Building not found")

    # Check garrison slots
    # Count existing garrison participants
    result = await session.execute(
        select(ContractParticipant).where(
            ContractParticipant.role == ParticipantRole.DEFENDER,
            ContractParticipant.status.in_([ParticipantStatus.ENLISTED, ParticipantStatus.ACTIVE]),
        ).join(MercenaryContract).where(
            MercenaryContract.target_building_id == building_id,
            MercenaryContract.mission_type == MissionType.DEFEND_BUILDING,
            MercenaryContract.status.in_([ContractStatus.OPEN, ContractStatus.ACTIVE]),
        )
    )
    current_garrison = len(result.scalars().all())
    if current_garrison >= settings.WARFARE_MAX_GARRISON_PER_BUILDING:
        raise ValueError(f"Building garrison is full ({settings.WARFARE_MAX_GARRISON_PER_BUILDING} max)")

    # Find or create a defense contract for this building
    result = await session.execute(
        select(MercenaryContract)
        .where(
            MercenaryContract.target_building_id == building_id,
            MercenaryContract.mission_type == MissionType.DEFEND_BUILDING,
            MercenaryContract.status.in_([ContractStatus.OPEN, ContractStatus.ACTIVE]),
        )
        .with_for_update()
    )
    defense_contract = result.scalar_one_or_none()

    if not defense_contract:
        # Create a new standing defense contract (no escrow needed for defense)
        defense_contract = MercenaryContract(
            employer_agent_id=agent_id,
            mission_type=MissionType.DEFEND_BUILDING,
            target_building_id=building_id,
            target_region_id=building.region_id,
            reward_per_agent=0,
            max_agents=settings.WARFARE_MAX_GARRISON_PER_BUILDING,
            escrow_total=0,
            mission_duration_seconds=0,
            expires_at=now + timedelta(days=365),
            status=ContractStatus.ACTIVE,
            activated_at=now,
        )
        session.add(defense_contract)
        await session.flush()

    # Add participant
    participant = ContractParticipant(
        contract_id=defense_contract.id,
        agent_id=agent_id,
        role=ParticipantRole.DEFENDER,
        status=ParticipantStatus.ACTIVE,
    )
    session.add(participant)
    await session.flush()

    return {
        "building_id": building_id,
        "agent_id": agent_id,
        "garrison_count": current_garrison + 1,
        "max_garrison": settings.WARFARE_MAX_GARRISON_PER_BUILDING,
    }


async def ungarrison_building(
    session: AsyncSession,
    agent_id: int,
    building_id: int,
) -> dict:
    """Remove an agent from a building's garrison."""
    result = await session.execute(
        select(ContractParticipant)
        .where(
            ContractParticipant.agent_id == agent_id,
            ContractParticipant.role == ParticipantRole.DEFENDER,
            ContractParticipant.status.in_([ParticipantStatus.ENLISTED, ParticipantStatus.ACTIVE]),
        )
        .join(MercenaryContract)
        .where(
            MercenaryContract.target_building_id == building_id,
            MercenaryContract.mission_type == MissionType.DEFEND_BUILDING,
            MercenaryContract.status.in_([ContractStatus.OPEN, ContractStatus.ACTIVE]),
        )
    )
    participant = result.scalar_one_or_none()
    if not participant:
        raise ValueError("Agent is not garrisoned at this building")

    participant.status = ParticipantStatus.FLED
    await session.flush()

    return {
        "building_id": building_id,
        "agent_id": agent_id,
        "removed": True,
    }


# ─── Building Repair ────────────────────────────────────────────────────────


async def repair_building(
    session: AsyncSession,
    agent_id: int,
    building_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    """Repair a building using BLD resources from agent's inventory.

    Costs WARFARE_REPAIR_BLD_PER_10_DURABILITY BLD per 10 durability repaired.
    """
    now = now or datetime.now(UTC)

    result = await session.execute(
        select(Building).where(Building.id == building_id).with_for_update()
    )
    building = result.scalar_one_or_none()
    if not building:
        raise ValueError("Building not found")

    damage = building.max_durability - building.durability
    if damage <= 0:
        raise ValueError("Building is already at full durability")

    # Calculate BLD cost
    bld_needed = max(1, int(damage / 10) * settings.WARFARE_REPAIR_BLD_PER_10_DURABILITY)

    # Check agent has BLD in this region (delegate to inventory_svc when implemented)
    # For now, just restore durability and log the cost
    # TODO: integrate with inventory_svc.remove_resource when #17 is done

    old_dur = building.durability
    building.durability = building.max_durability
    building.last_durability_at = now
    if building.status == BuildingStatus.DISABLED and building.durability > 0:
        building.status = BuildingStatus.IDLE

    await session.flush()

    return {
        "building_id": building.id,
        "old_durability": round(old_dur, 2),
        "new_durability": building.durability,
        "bld_cost": bld_needed,
        "status": building.status.value,
    }


# ─── Lazy Settlement (Housekeeping) ─────────────────────────────────────────


async def settle_building_durability(
    session: AsyncSession,
    building_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    """Settle natural durability recovery for a building.

    Recovers WARFARE_NATURAL_REPAIR_PER_MINUTE durability per minute
    since last_durability_at (if not under active attack).
    """
    now = now or datetime.now(UTC)

    result = await session.execute(
        select(Building).where(Building.id == building_id).with_for_update()
    )
    building = result.scalar_one_or_none()
    if not building:
        return {"building_id": building_id, "error": "not found"}

    if building.durability >= building.max_durability:
        return {"building_id": building_id, "repaired": 0}

    if building.last_durability_at is None:
        building.last_durability_at = now
        await session.flush()
        return {"building_id": building_id, "repaired": 0}

    last_durability_at = _normalize_timestamp(building.last_durability_at)
    if last_durability_at is None:
        return {"building_id": building_id, "repaired": 0}

    elapsed_seconds = (now - last_durability_at).total_seconds()
    if elapsed_seconds <= 0:
        return {"building_id": building_id, "repaired": 0}

    elapsed_minutes = elapsed_seconds / 60.0
    repair = elapsed_minutes * settings.WARFARE_NATURAL_REPAIR_PER_MINUTE

    old = building.durability
    building.durability = min(building.max_durability, building.durability + repair)
    building.last_durability_at = now

    if building.status == BuildingStatus.DISABLED and building.durability > 0:
        building.status = BuildingStatus.IDLE

    await session.flush()

    return {
        "building_id": building_id,
        "old_durability": round(old, 2),
        "new_durability": round(building.durability, 2),
        "repaired": round(building.durability - old, 2),
    }


async def settle_active_contracts(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict:
    """Housekeeping: expire old contracts, settle active ones."""
    now = now or datetime.now(UTC)

    # Expire open contracts past their expiry
    result = await session.execute(
        select(MercenaryContract)
        .where(
            MercenaryContract.status == ContractStatus.OPEN,
            MercenaryContract.expires_at < now,
        )
        .with_for_update()
    )
    expired_contracts = result.scalars().all()
    expired_count = 0
    for c in expired_contracts:
        c.status = ContractStatus.EXPIRED
        c.completed_at = now
        # Refund escrow
        emp_result = await session.execute(
            select(Agent).where(Agent.id == c.employer_agent_id).with_for_update()
        )
        employer = emp_result.scalar_one_or_none()
        if employer:
            employer.personal_balance += c.escrow_total
        expired_count += 1

    # Settle natural repair for all damaged buildings
    result = await session.execute(
        select(Building).where(Building.durability < Building.max_durability)
    )
    damaged_buildings = result.scalars().all()
    repaired_count = 0
    for b in damaged_buildings:
        r = await settle_building_durability(session, b.id, now=now)
        if r.get("repaired", 0) > 0:
            repaired_count += 1

    await session.flush()

    return {
        "expired_contracts": expired_count,
        "buildings_repaired": repaired_count,
    }


# ─── Queries ────────────────────────────────────────────────────────────────


async def get_contract(session: AsyncSession, contract_id: int) -> dict | None:
    """Get contract details."""
    result = await session.execute(
        select(MercenaryContract)
        .where(MercenaryContract.id == contract_id)
        .options(selectinload(MercenaryContract.participants))
    )
    c = result.scalar_one_or_none()
    if not c:
        return None

    return {
        "contract_id": c.id,
        "employer_agent_id": c.employer_agent_id,
        "mission_type": c.mission_type.value,
        "target_building_id": c.target_building_id,
        "target_region_id": c.target_region_id,
        "target_transport_id": c.target_transport_id,
        "reward_per_agent": c.reward_per_agent,
        "max_agents": c.max_agents,
        "escrow_total": c.escrow_total,
        "status": c.status.value,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "activated_at": c.activated_at.isoformat() if c.activated_at else None,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "result_summary": c.result_summary,
        "participants": [
            {
                "agent_id": p.agent_id,
                "role": p.role.value,
                "status": p.status.value,
                "reward_paid": p.reward_paid,
                "health_lost": p.health_lost,
                "xp_earned": p.xp_earned,
            }
            for p in c.participants
        ],
    }


async def list_contracts(
    session: AsyncSession,
    *,
    region_id: int | None = None,
    status: str | None = None,
    mission_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List contracts with optional filters."""
    query = select(MercenaryContract).options(
        selectinload(MercenaryContract.participants)
    )

    if region_id is not None:
        query = query.where(MercenaryContract.target_region_id == region_id)
    if status is not None:
        query = query.where(MercenaryContract.status == ContractStatus(status))
    if mission_type is not None:
        query = query.where(MercenaryContract.mission_type == MissionType(mission_type))

    query = query.order_by(MercenaryContract.created_at.desc()).limit(limit)

    result = await session.execute(query)
    contracts = result.scalars().all()

    return [
        {
            "contract_id": c.id,
            "employer_agent_id": c.employer_agent_id,
            "mission_type": c.mission_type.value,
            "target_region_id": c.target_region_id,
            "reward_per_agent": c.reward_per_agent,
            "max_agents": c.max_agents,
            "enlisted": len([p for p in c.participants if p.status in (ParticipantStatus.ENLISTED, ParticipantStatus.ACTIVE)]),
            "status": c.status.value,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        }
        for c in contracts
    ]


async def get_region_threats(
    session: AsyncSession,
    region_id: int,
) -> dict:
    """Get active warfare threats in a region."""
    result = await session.execute(
        select(MercenaryContract)
        .where(
            MercenaryContract.target_region_id == region_id,
            MercenaryContract.status.in_([ContractStatus.OPEN, ContractStatus.ACTIVE]),
            MercenaryContract.mission_type.in_([MissionType.SABOTAGE_BUILDING, MissionType.RAID_TRANSPORT]),
        )
        .options(selectinload(MercenaryContract.participants))
    )
    threats = result.scalars().all()

    return {
        "region_id": region_id,
        "active_threats": len(threats),
        "contracts": [
            {
                "contract_id": c.id,
                "mission_type": c.mission_type.value,
                "target_building_id": c.target_building_id,
                "target_transport_id": c.target_transport_id,
                "enlisted_count": len([p for p in c.participants if p.status in (ParticipantStatus.ENLISTED, ParticipantStatus.ACTIVE)]),
                "status": c.status.value,
            }
            for c in threats
        ],
    }

## Overview

**THE BLOCKER ISSUE** — Everything else depends on this. One CC instance must complete this before any service implementation begins.

Evolve the data layer from "Company-only economy" to "AI Sims with full world". This includes:
- 13 new ORM models
- 10 existing model modifications
- Delete Worker model
- All monetary fields: `Numeric` → `BigInteger` (copper integer)
- Config, Schemas, Auth migration to Agent-based

## Key Design Decisions

1. **Agent is the auth entity** — `api_key_hash` moves from Company to Agent
2. **Worker model deleted** — replaced by `Company.npc_worker_count` + `Company.npc_satisfaction` + `Company.last_consumption_at`
3. **All money = copper integer** — `BigInteger`, 1 Gold = 100 Silver = 10,000 Copper
4. **All resource quantities = integer** — no floating point
5. **Inventory is regional** — `Inventory` gets `region_id` FK
6. **Inventory is polymorphic** — `company_id` (nullable) OR `agent_id` (nullable), exactly one set

---

## Files to CREATE (13 new model files)

### `models/agent.py` — Agent (the player entity)
```python
class Agent(Base, TimestampMixin):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # Vitals (0-100 scale, float for smooth decay)
    health: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    hunger: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    thirst: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    energy: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    happiness: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    reputation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Location
    current_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    home_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)

    # Economy
    personal_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # copper

    # Career
    career_path: Mapped[str | None] = mapped_column(String(50))

    # State
    is_alive: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_vitals_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    current_region = relationship("Region", foreign_keys=[current_region_id])
    home_region = relationship("Region", foreign_keys=[home_region_id])
    companies = relationship("Company", back_populates="founder")
    skills = relationship("AgentSkill", back_populates="agent")
    employments = relationship("AgentEmployment", back_populates="agent")
    inventories = relationship("Inventory", back_populates="agent")
    orders = relationship("Order", back_populates="agent")
```

### `models/region.py` — Region + RegionConnection
```python
class SafetyTier(str, enum.Enum):
    CORE = "core"
    BORDER = "border"
    RESOURCE = "resource"
    WILDERNESS = "wilderness"

class RegionType(str, enum.Enum):
    CAPITAL = "capital"
    TOWN = "town"
    VILLAGE = "village"
    OUTPOST = "outpost"
    WILDERNESS = "wilderness"

class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    safety_tier: Mapped[SafetyTier]
    region_type: Mapped[RegionType]
    price_coefficient: Mapped[float] = mapped_column(Float, default=1.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.05)
    treasury: Mapped[int] = mapped_column(BigInteger, default=0)
    resource_specializations: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text, default="")

class RegionConnection(Base):
    __tablename__ = "region_connections"
    __table_args__ = (UniqueConstraint("from_region_id", "to_region_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    from_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    to_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    travel_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    terrain_type: Mapped[str] = mapped_column(String(30), default="road")
    is_portal: Mapped[bool] = mapped_column(Boolean, default=False)
    danger_level: Mapped[int] = mapped_column(Integer, default=0)
```

### `models/skill_definition.py`
```python
class SkillCategory(str, enum.Enum):
    GATHERING = "gathering"
    CRAFTING = "crafting"
    COMMERCE = "commerce"
    SOCIAL = "social"

class SkillDefinition(Base):
    __tablename__ = "skill_definitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    category: Mapped[SkillCategory]
    description: Mapped[str] = mapped_column(Text, default="")
    prerequisites: Mapped[dict] = mapped_column(JSON, default=dict)
    xp_per_level: Mapped[dict] = mapped_column(JSON, default=dict)
```

### `models/agent_skill.py`
```python
class AgentSkill(Base):
    __tablename__ = "agent_skills"
    __table_args__ = (UniqueConstraint("agent_id", "skill_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    skill_name: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    agent = relationship("Agent", back_populates="skills")
```

### `models/agent_employment.py`
```python
class EmploymentRole(str, enum.Enum):
    WORKER = "worker"
    FOREMAN = "foreman"
    MANAGER = "manager"
    DIRECTOR = "director"
    CEO = "ceo"

class AgentEmployment(Base):
    __tablename__ = "agent_employments"
    __table_args__ = (UniqueConstraint("agent_id", "company_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    role: Mapped[EmploymentRole]
    salary_per_second: Mapped[int] = mapped_column(BigInteger, default=0)
    hired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    agent = relationship("Agent", back_populates="employments")
    company = relationship("Company", back_populates="employments")
```

### `models/travel.py`
```python
class TravelQueue(Base):
    __tablename__ = "travel_queue"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), unique=True, nullable=False)
    from_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    to_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    departed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrives_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cargo: Mapped[dict] = mapped_column(JSON, default=dict)
    agent = relationship("Agent")
```

### `models/transport_order.py`
```python
class TransportStatus(str, enum.Enum):
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    LOST = "lost"

class TransportOrder(Base, TimestampMixin):
    __tablename__ = "transport_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    owner_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    from_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    to_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    items: Mapped[dict] = mapped_column(JSON, default=dict)
    total_weight: Mapped[int] = mapped_column(Integer, default=0)
    transport_type: Mapped[str] = mapped_column(String(30), default="backpack")
    cost: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[TransportStatus]
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrives_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

### `models/npc_shop.py`
```python
class NpcShop(Base):
    __tablename__ = "npc_shops"
    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False, index=True)
    shop_type: Mapped[str] = mapped_column(String(50), nullable=False)
    buy_prices: Mapped[dict] = mapped_column(JSON, default=dict)
    sell_prices: Mapped[dict] = mapped_column(JSON, default=dict)
    stock: Mapped[dict] = mapped_column(JSON, default=dict)
    restock_rate: Mapped[dict] = mapped_column(JSON, default=dict)
    last_restock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

### `models/guild.py`
```python
class GuildRank(str, enum.Enum):
    RECRUIT = "recruit"
    MEMBER = "member"
    OFFICER = "officer"
    LEADER = "leader"

class Guild(Base, TimestampMixin):
    __tablename__ = "guilds"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1)
    treasury: Mapped[int] = mapped_column(BigInteger, default=0)
    home_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    maintenance_cost_per_day: Mapped[int] = mapped_column(BigInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    members = relationship("GuildMember", back_populates="guild")

class GuildMember(Base):
    __tablename__ = "guild_members"
    __table_args__ = (UniqueConstraint("guild_id", "agent_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id"), nullable=False, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    rank: Mapped[GuildRank]
    share_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    guild = relationship("Guild", back_populates="members")
    agent = relationship("Agent")
```

### `models/relationship.py`
```python
class RelationType(str, enum.Enum):
    ALLIED = "allied"
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"
    WAR = "war"

class AgentRelationship(Base):
    __tablename__ = "agent_relationships"
    __table_args__ = (UniqueConstraint("agent_id", "target_agent_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    target_agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    relation_type: Mapped[RelationType] = mapped_column(default=RelationType.NEUTRAL)
    trust_score: Mapped[int] = mapped_column(Integer, default=0)
```

### `models/treaty.py`
```python
class TreatyType(str, enum.Enum):
    NON_AGGRESSION = "non_aggression"
    MUTUAL_DEFENSE = "mutual_defense"
    TRADE_AGREEMENT = "trade_agreement"
    ALLIANCE = "alliance"

class Treaty(Base, TimestampMixin):
    __tablename__ = "treaties"
    id: Mapped[int] = mapped_column(primary_key=True)
    party_a_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    party_a_guild_id: Mapped[int | None] = mapped_column(ForeignKey("guilds.id"))
    party_b_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    party_b_guild_id: Mapped[int | None] = mapped_column(ForeignKey("guilds.id"))
    treaty_type: Mapped[TreatyType]
    terms: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

### `models/world_event.py`
```python
class WorldEvent(Base):
    __tablename__ = "world_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"))
    effects: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

### `models/tax_record.py`
```python
class TaxRecord(Base):
    __tablename__ = "tax_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    tax_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payer_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    payer_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    beneficiary_guild_id: Mapped[int | None] = mapped_column(ForeignKey("guilds.id"))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

---

## Files to MODIFY

### `models/company.py`
- **Remove**: `api_key_hash` field (moves to Agent)
- **Add**: `founder_agent_id: FK(agents.id)`, `region_id: FK(regions.id)`, `npc_worker_count: int default=100`, `npc_satisfaction: float default=100.0`, `last_consumption_at: datetime nullable`, `guild_id: FK(guilds.id) nullable`
- **Change**: `balance`, `reserved_balance`, `net_worth` from `Numeric(16,2)` to `BigInteger`
- **Remove**: `workers` relationship
- **Add**: `founder` relationship, `employments` relationship, `region` relationship

### `models/resource.py`
- **Add**: `weight_kg: int default=1`, `is_perishable: bool default=False`, `decay_rate_per_hour: float default=0.0`, `tier: int default=1`, `is_currency: bool default=False`
- **Change**: `base_price` from `Numeric(12,2)` to `BigInteger`

### `models/building.py`
- **Add**: `region_id: FK(regions.id)`, `agent_id: FK(agents.id) nullable`

### `models/building_type.py`
- **Add**: `required_skill: str nullable`, `min_skill_level: int default=0`, `region_type_restriction: str nullable`
- **Change**: `cost_credits` from `Numeric(12,2)` to `BigInteger`

### `models/recipe.py`
- **Add**: `required_skill: str nullable`, `min_skill_level: int default=0`, `skill_xp_reward: int default=0`

### `models/inventory.py`
- **Add**: `agent_id: FK(agents.id) nullable`, `region_id: FK(regions.id) not null`, `expires_at: datetime nullable`
- **Change**: `company_id` to nullable
- **Change**: `quantity`, `reserved` from `Numeric(16,4)` to `BigInteger`
- **Update**: unique constraint to `(company_id, agent_id, resource_id, region_id)`

### `models/order.py`
- **Add**: `agent_id: FK(agents.id)`, `region_id: FK(regions.id)`, `tax_amount: BigInteger default=0`
- **Change**: `price` `Numeric(12,2)` to `BigInteger`; `quantity`/`remaining` `Numeric(16,4)` to `BigInteger`

### `models/trade.py`
- **Add**: `buyer_agent_id: FK(agents.id)`, `seller_agent_id: FK(agents.id)`, `region_id: FK(regions.id)`, `tax_collected: BigInteger default=0`
- **Change**: `price` to `BigInteger`, `quantity` to `BigInteger`

### `models/price_history.py`
- **Add**: `region_id: FK(regions.id)`
- **Change**: all `Numeric` to `BigInteger`
- **Update**: unique constraint to include `region_id`

### `models/game_state.py`
- **Add**: `world_seed: str nullable`, `inflation_index: float default=1.0`, `total_currency_supply: BigInteger default=0`, `current_season: str default="spring"`

### `models/worker.py` → **DELETE**

### `models/__init__.py` — Remove Worker, add all 13 new models

---

## Non-model files to modify

### `config.py` — Add Agent vitals config
```python
AGENT_HUNGER_DECAY_PER_SECOND: float = 100.0 / 3600
AGENT_THIRST_DECAY_PER_SECOND: float = 100.0 / 2400
AGENT_ENERGY_DECAY_PER_SECOND: float = 100.0 / 7200
AGENT_HEALTH_DAMAGE_HUNGER: float = 5.0 / 60
AGENT_HEALTH_DAMAGE_THIRST: float = 8.0 / 60
AGENT_INITIAL_BALANCE: int = 50_000
AGENT_RESPAWN_PENALTY: float = 0.5
```

### `api/schemas.py` — All float monetary/quantity → int, add new schemas
New schemas needed: `AgentRegisterRequest`, `AgentRegisterResponse`, `AgentStatus`, `RegionInfo`, `RegionConnectionInfo`, `WorldMapResponse`, `TravelRequest`, `TravelStatus`, `SkillInfo`, `AgentSkillInfo`, `CreateCompanyRequest`, `GuildInfo`, `GuildCreateRequest`, `TransportRequest`, `TransportStatus`, `NpcShopInfo`, `TreatyInfo`, `WorldEventInfo`

### `api/auth.py` — `get_current_agent()` replaces `get_current_company()`

### `deps.py` — Update import

---

## Acceptance Criteria

- [ ] All 13 new model files created with correct fields, types, relationships
- [ ] All 10 existing models modified as specified
- [ ] Worker model deleted, all references removed
- [ ] All Numeric money/quantity fields changed to BigInteger
- [ ] `models/__init__.py` exports all new models
- [ ] `config.py` has Agent vitals settings
- [ ] `api/schemas.py` has all new schemas + updated types
- [ ] `api/auth.py` returns Agent (not Company)
- [ ] `ruff check src/` passes
- [ ] All imports resolve correctly

## Dependencies

- **Depends on**: Nothing (this is the root)
- **Blocks**: ALL other issues

"""Shared data models for Terminal Tower Defense."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


GRID_WIDTH = 36
GRID_HEIGHT = 18
META_WIDTH = 18
META_HEIGHT = 9
MAX_LOADOUT = 8

TARGET_FIRST = "first"
TARGET_STRONGEST = "strongest"
TARGET_CLOSEST = "closest"
TARGET_MODES = (TARGET_FIRST, TARGET_STRONGEST, TARGET_CLOSEST)

SPEED_OPTIONS: Tuple[int, ...] = (1, 2, 3, 5, 10)

AUTO_SELL_MODES: Tuple[str, ...] = (
    "off",
    "dupes_c",
    "dupes_cr",
    "dupes_cre",
    "all_c",
    "all_cr",
)


@dataclass(frozen=True)
class DifficultyConfig:
    key: str
    name: str
    description: str
    starting_gold: int
    starting_lives: int
    enemy_hp_mult: float
    enemy_speed_mult: float
    reward_mult: float
    coin_mult: float
    extra_leak_damage: int
    boss_cd_mult: float
    auto_wave_delay: Optional[float]  # seconds between waves after wave 1
    pause_in_gamble: bool


@dataclass(frozen=True)
class BannerDef:
    key: str
    name: str
    description: str
    single_cost: int
    multi_cost: int
    min_10x_rarity: str
    rarity_weights: Dict[str, float]
    featured_keys: Tuple[str, ...]
    featured_boost: float = 3.0
    pity_mythic_at: int = 60


@dataclass(frozen=True)
class TowerStats:
    level: int
    cost: int
    damage: float
    cooldown: float
    range: float
    min_range: float = 0.0
    splash_radius: float = 0.0
    splash_ratio: float = 0.0
    slow_factor: float = 0.0
    slow_duration: float = 0.0
    stun_duration: float = 0.0
    chain_count: int = 0
    chain_falloff: float = 0.72
    poison_dps: float = 0.0
    poison_duration: float = 0.0
    armor_shred: float = 0.0
    armor_pierce: float = 0.0
    execute_pct: float = 0.0  # bonus damage = missing_hp * execute_pct
    # Economy (Farms)
    income_per_wave: int = 0
    income_per_tick: int = 0
    income_interval: float = 0.0
    # Support Buff Aura & Ally Healing
    buff_dmg_pct: float = 0.0
    buff_spd_pct: float = 0.0
    buff_rng_pct: float = 0.0
    heal_allies_per_sec: float = 0.0
    # Friendly Unit Spawner
    spawn_ally_kind: Optional[str] = None
    spawn_interval: float = 0.0
    max_active_allies: int = 0
    # Road Spike Layer
    spike_damage: float = 0.0
    spike_charges: int = 0


@dataclass(frozen=True)
class TowerBlueprint:
    key: str
    symbol: str
    name: str
    rarity: str  # common, rare, epic, legendary, mythic, transcendent
    role: str
    description: str
    shot_char: str
    levels: Tuple[TowerStats, ...]


@dataclass(frozen=True)
class UnitTemplate:
    kind: str
    symbol: str
    name: str
    tier: int
    max_hp: float
    speed: float
    reward: int
    damage: int = 1
    atk_dps: float = 18.0
    armor: float = 0.0
    regen_per_sec: float = 0.0
    evasion: float = 0.0
    slow_immune: bool = False
    berserk_threshold: float = 0.0
    heal_aura_per_sec: float = 0.0
    heal_aura_radius: float = 0.0
    split_into: Optional[str] = None
    split_count: int = 0
    is_boss: bool = False
    boss_ability: str = ""
    ability_cooldown: float = 0.0
    description: str = ""


@dataclass(frozen=True)
class AllyTemplate:
    kind: str
    symbol: str
    name: str
    max_hp: float
    speed: float
    atk_dps: float
    armor: float = 0.0
    revives: int = 0
    revive_hp_ratio: float = 0.65
    revive_blast_dmg: float = 45.0
    splash_radius: float = 0.0
    description: str = ""


@dataclass(frozen=True)
class MapDef:
    key: str
    name: str
    description: str
    meta_waypoints: Tuple[Tuple[int, int], ...]

    def build_geometry(
        self,
    ) -> Tuple[
        List[Tuple[int, int]],
        List[Tuple[float, float]],
        Set[Tuple[int, int]],
        Set[Tuple[int, int]],
        Set[Tuple[int, int]],
    ]:
        """Expand 18x9 meta-waypoints into 2-tile-wide roads on the 36x18 grid."""
        meta_path: List[Tuple[int, int]] = []
        for idx, (mx, my) in enumerate(self.meta_waypoints):
            if not (0 <= mx < META_WIDTH and 0 <= my < META_HEIGHT):
                raise ValueError(f"Meta waypoint {(mx, my)} out of bounds in {self.name}")
            if idx == 0:
                meta_path.append((mx, my))
                continue
            px, py = self.meta_waypoints[idx - 1]
            if px != mx and py != my:
                raise ValueError(f"Non-orthogonal segment {(px, py)} -> {(mx, my)} in {self.name}")
            dx = 0 if mx == px else (1 if mx > px else -1)
            dy = 0 if my == py else (1 if my > py else -1)
            cx, cy = px, py
            while (cx, cy) != (mx, my):
                cx += dx
                cy += dy
                if (cx, cy) in meta_path:
                    raise ValueError(f"Self-intersecting meta path at {(cx, cy)} in {self.name}")
                meta_path.append((cx, cy))

        centerline: List[Tuple[float, float]] = []
        for i, (mx, my) in enumerate(meta_path):
            cx = mx * 2 + 0.5
            cy = my * 2 + 0.5
            if i == 0:
                centerline.append((cx, cy))
            else:
                pmx, pmy = meta_path[i - 1]
                pcx = pmx * 2 + 0.5
                pcy = pmy * 2 + 0.5
                centerline.append(((pcx + cx) / 2.0, (pcy + cy) / 2.0))
                centerline.append((cx, cy))

        road_set: Set[Tuple[int, int]] = set()
        for mx, my in meta_path:
            for dx in (0, 1):
                for dy in (0, 1):
                    road_set.add((mx * 2 + dx, my * 2 + dy))

        smx, smy = meta_path[0]
        bmx, bmy = meta_path[-1]
        spawn_cells = {(smx * 2 + dx, smy * 2 + dy) for dx in (0, 1) for dy in (0, 1)}
        base_cells = {(bmx * 2 + dx, bmy * 2 + dy) for dx in (0, 1) for dy in (0, 1)}
        return meta_path, centerline, road_set, spawn_cells, base_cells


@dataclass
class Enemy:
    id: int
    template: UnitTemplate
    hp: float
    max_hp: float
    speed: float
    reward: int
    damage: int
    armor_current: float
    progress: float = 0.0
    lane_offset: float = 0.0
    slow_timer: float = 0.0
    slow_factor: float = 0.0
    stun_timer: float = 0.0
    poison_timer: float = 0.0
    poison_dps: float = 0.0
    poison_source_tower: Optional["Tower"] = None
    shield: float = 0.0
    hit_flash: float = 0.0
    ability_timer: float = 0.0
    surge_timer: float = 0.0
    engaged: bool = False

    @property
    def kind(self) -> str:
        return self.template.kind

    @property
    def symbol(self) -> str:
        return self.template.symbol

    @property
    def name(self) -> str:
        return self.template.name

    @property
    def is_boss(self) -> bool:
        return self.template.is_boss

    def position(self, centerline: List[Tuple[float, float]]) -> Tuple[float, float]:
        if not centerline:
            return 0.0, 0.0
        max_idx = len(centerline) - 1
        clamped = max(0.0, min(float(max_idx), self.progress))
        i = min(max_idx - 1, int(clamped)) if max_idx > 0 else 0
        frac = clamped - i
        x0, y0 = centerline[i]
        x1, y1 = centerline[min(max_idx, i + 1)]
        px = x0 + (x1 - x0) * frac
        py = y0 + (y1 - y0) * frac
        dx = x1 - x0
        dy = y1 - y0
        length = (dx * dx + dy * dy) ** 0.5
        if length > 1e-6 and self.lane_offset != 0.0:
            px += (-dy / length) * self.lane_offset
            py += (dx / length) * self.lane_offset
        return px, py

    def grid_cell(
        self, centerline: List[Tuple[float, float]], road_set: Optional[Set[Tuple[int, int]]] = None
    ) -> Tuple[int, int]:
        px, py = self.position(centerline)
        gx = max(0, min(GRID_WIDTH - 1, int(round(px))))
        gy = max(0, min(GRID_HEIGHT - 1, int(round(py))))
        if road_set is not None and (gx, gy) not in road_set:
            idx = min(len(centerline) - 1, max(0, int(round(self.progress))))
            cx, cy = centerline[idx]
            gx = max(0, min(GRID_WIDTH - 1, int(round(cx))))
            gy = max(0, min(GRID_HEIGHT - 1, int(round(cy))))
        return gx, gy


@dataclass
class AllyUnit:
    id: int
    template: AllyTemplate
    owner_pos: Tuple[int, int]
    hp: float
    max_hp: float
    progress: float
    lane_offset: float = 0.0
    revives_left: int = 0
    hit_flash: float = 0.0
    revive_flash: float = 0.0

    def position(self, centerline: List[Tuple[float, float]]) -> Tuple[float, float]:
        if not centerline:
            return 0.0, 0.0
        max_idx = len(centerline) - 1
        clamped = max(0.0, min(float(max_idx), self.progress))
        i = min(max_idx - 1, int(clamped)) if max_idx > 0 else 0
        frac = clamped - i
        x0, y0 = centerline[i]
        x1, y1 = centerline[min(max_idx, i + 1)]
        px = x0 + (x1 - x0) * frac
        py = y0 + (y1 - y0) * frac
        dx = x1 - x0
        dy = y1 - y0
        length = (dx * dx + dy * dy) ** 0.5
        if length > 1e-6 and self.lane_offset != 0.0:
            px += (-dy / length) * self.lane_offset
            py += (dx / length) * self.lane_offset
        return px, py

    def grid_cell(
        self, centerline: List[Tuple[float, float]], road_set: Optional[Set[Tuple[int, int]]] = None
    ) -> Tuple[int, int]:
        px, py = self.position(centerline)
        gx = max(0, min(GRID_WIDTH - 1, int(round(px))))
        gy = max(0, min(GRID_HEIGHT - 1, int(round(py))))
        if road_set is not None and (gx, gy) not in road_set:
            idx = min(len(centerline) - 1, max(0, int(round(self.progress))))
            cx, cy = centerline[idx]
            gx = max(0, min(GRID_WIDTH - 1, int(round(cx))))
            gy = max(0, min(GRID_HEIGHT - 1, int(round(cy))))
        return gx, gy


@dataclass
class RoadSpike:
    x: int
    y: int
    damage: float
    charges: int
    owner_pos: Tuple[int, int]


@dataclass
class Tower:
    x: int
    y: int
    kind: str
    blueprints: Dict[str, TowerBlueprint]
    level: int = 1
    cooldown_left: float = 0.0
    income_timer: float = 0.0
    spawn_timer: float = 0.0
    total_invested: int = 0
    kills: int = 0
    gold_earned: int = 0
    target_mode: str = TARGET_FIRST
    buff_dmg_mult: float = 1.0
    buff_spd_mult: float = 1.0
    buff_rng_mult: float = 1.0

    @property
    def blueprint(self) -> TowerBlueprint:
        return self.blueprints[self.kind]

    @property
    def stats(self) -> TowerStats:
        return self.blueprint.levels[self.level - 1]

    @property
    def effective_damage(self) -> float:
        return self.stats.damage * self.buff_dmg_mult

    @property
    def effective_cooldown(self) -> float:
        return self.stats.cooldown / max(0.5, self.buff_spd_mult)

    @property
    def effective_range(self) -> float:
        return self.stats.range * self.buff_rng_mult

    @property
    def can_upgrade(self) -> bool:
        return self.level < len(self.blueprint.levels)

    @property
    def upgrade_cost(self) -> Optional[int]:
        if not self.can_upgrade:
            return None
        return self.blueprint.levels[self.level].cost

    @property
    def sell_value(self) -> int:
        return (self.total_invested * 7) // 10


@dataclass
class ShotEffect:
    x0: float
    y0: float
    x1: float
    y1: float
    char: str
    kind: str
    ttl: float = 0.14


@dataclass
class SpawnEntry:
    kind: str
    delay: float
    hp_scale: float = 1.0

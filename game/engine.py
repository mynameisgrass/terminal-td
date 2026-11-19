"""Core simulation engine for Terminal Tower Defense."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from game.data.difficulties import DIFFICULTIES
from game.data.maps import MAPS
from game.data.towers import STARTER_LOADOUT, TOWER_BLUEPRINTS
from game.data.units import ALLY_TEMPLATES, UNIT_TEMPLATES
from game.data.waves import WAVE_DEFINITIONS, build_wave_queue
from game.models import (
    GRID_HEIGHT,
    GRID_WIDTH,
    MAX_LOADOUT,
    SPEED_OPTIONS,
    TARGET_CLOSEST,
    TARGET_FIRST,
    TARGET_MODES,
    TARGET_STRONGEST,
    AllyTemplate,
    AllyUnit,
    DifficultyConfig,
    Enemy,
    MapDef,
    RoadSpike,
    ShotEffect,
    SpawnEntry,
    Tower,
    UnitTemplate,
)

if TYPE_CHECKING:
    from game.profile import PlayerProfile


LANE_OFFSETS: Tuple[float, ...] = (-0.42, 0.0, 0.42)


class GameState:
    """Mutable state for one battle run of Terminal Tower Defense."""

    def __init__(
        self,
        map_index: int = 0,
        difficulty_key: str = "normal",
        loadout: Optional[List[str]] = None,
        profile: Optional["PlayerProfile"] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.rng = rng or random.Random()
        self.profile = profile
        self.width = GRID_WIDTH
        self.height = GRID_HEIGHT

        if difficulty_key not in DIFFICULTIES:
            difficulty_key = "normal"
        self.difficulty: DifficultyConfig = DIFFICULTIES[difficulty_key]

        raw_loadout = loadout if loadout is not None else (profile.loadout if profile else list(STARTER_LOADOUT))
        clean = [k for k in raw_loadout if k in TOWER_BLUEPRINTS][:MAX_LOADOUT]
        self.loadout: List[str] = clean or list(STARTER_LOADOUT)

        self.map_index = map_index % len(MAPS)
        self.map_def: MapDef = MAPS[self.map_index]
        (
            self.meta_path,
            self.centerline,
            self.road_set,
            self.spawn_cells,
            self.base_cells,
        ) = self.map_def.build_geometry()

        self.gold: int = self.difficulty.starting_gold
        self.lives: int = self.difficulty.starting_lives
        self.score: int = 0
        self.coins_earned: int = 0
        self.wave: int = 0
        self.max_waves: int = len(WAVE_DEFINITIONS)
        self.endless: bool = False

        self.towers: Dict[Tuple[int, int], Tower] = {}
        self.enemies: List[Enemy] = []
        self.allies: List[AllyUnit] = []
        self.spikes: Dict[Tuple[int, int], RoadSpike] = {}
        self.spawn_queue: List[SpawnEntry] = []
        self.spawn_timer: float = 0.0
        self.shots: List[ShotEffect] = []

        self.wave_active: bool = False
        self.next_wave_timer: Optional[float] = None
        self.auto_start: bool = False
        self.wave_rush_cooldown: float = 0.0
        self.paused: bool = False
        self.speed_mult: int = 1
        self.game_over: bool = False
        self.victory: bool = False

        self.cursor_x: int = 8
        self.cursor_y: int = 8
        self._snap_cursor_to_buildable()

        self.selected_tower_kind: str = self.loadout[0]
        self.logs: List[str] = [
            f"{self.difficulty.name} | {self.map_def.name} | [N] Start/Prestart Wave | [V] Auto-Start"
        ]
        self._next_entity_id: int = 1

    def _award_coins(self, base_coins: int) -> int:
        gained = max(1, int(round(base_coins * self.difficulty.coin_mult)))
        self.coins_earned += gained
        if self.profile is not None:
            self.profile.coins += gained
            self.profile.best_wave = max(self.profile.best_wave, self.wave)
            self.profile.save()
        return gained

    def _snap_cursor_to_buildable(self) -> None:
        if self.can_build_at(self.cursor_x, self.cursor_y):
            return
        for y in range(self.height):
            for x in range(self.width):
                if self.can_build_at(x, y):
                    self.cursor_x, self.cursor_y = x, y
                    return

    def log(self, message: str) -> None:
        self.logs.append(message)
        if len(self.logs) > 10:
            self.logs = self.logs[-10:]

    def cycle_speed(self) -> int:
        idx = SPEED_OPTIONS.index(self.speed_mult) if self.speed_mult in SPEED_OPTIONS else 0
        self.speed_mult = SPEED_OPTIONS[(idx + 1) % len(SPEED_OPTIONS)]
        self.log(f"Game speed: {self.speed_mult}x")
        return self.speed_mult

    def toggle_auto_start(self) -> bool:
        self.auto_start = not self.auto_start
        self.log(f"Auto-Start Waves: {'ON' if self.auto_start else 'OFF'}")
        if self.auto_start and not self.wave_active and not self.game_over and not (self.victory and not self.endless):
            if self.wave == 0 or (self.next_wave_timer is not None and self.next_wave_timer > 0.3):
                self.next_wave_timer = 0.25
        return self.auto_start

    def switch_map(self, delta: int = 1) -> bool:
        if self.wave > 0 or self.towers:
            self.log("Cannot switch map after placing towers or starting.")
            return False
        self.map_index = (self.map_index + delta) % len(MAPS)
        self.map_def = MAPS[self.map_index]
        (
            self.meta_path,
            self.centerline,
            self.road_set,
            self.spawn_cells,
            self.base_cells,
        ) = self.map_def.build_geometry()
        self._snap_cursor_to_buildable()
        self.log(f"Switched map to {self.map_def.name}.")
        return True

    def move_cursor(self, dx: int, dy: int) -> None:
        self.cursor_x = max(0, min(self.width - 1, self.cursor_x + dx))
        self.cursor_y = max(0, min(self.height - 1, self.cursor_y + dy))

    def can_build_at(self, x: int, y: int) -> bool:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        if (x, y) in self.road_set:
            return False
        if (x, y) in self.towers:
            return False
        return True

    def recompute_buffs(self) -> None:
        buffers = [
            t
            for t in self.towers.values()
            if t.stats.buff_dmg_pct > 0 or t.stats.buff_spd_pct > 0 or t.stats.buff_rng_pct > 0
        ]
        for tower in self.towers.values():
            best_dmg = 0.0
            best_spd = 0.0
            best_rng = 0.0
            for buf in buffers:
                if buf.x == tower.x and buf.y == tower.y:
                    continue
                dist = math.hypot(tower.x - buf.x, tower.y - buf.y)
                if dist <= buf.stats.range:
                    best_dmg = max(best_dmg, buf.stats.buff_dmg_pct)
                    best_spd = max(best_spd, buf.stats.buff_spd_pct)
                    best_rng = max(best_rng, buf.stats.buff_rng_pct)
            tower.buff_dmg_mult = 1.0 + best_dmg
            tower.buff_spd_mult = 1.0 + best_spd
            tower.buff_rng_mult = 1.0 + best_rng

    def build_tower(self, x: int, y: int, kind: str) -> bool:
        if self.game_over:
            return False
        if kind not in TOWER_BLUEPRINTS:
            return False
        if kind not in self.loadout:
            self.log(f"{TOWER_BLUEPRINTS[kind].name} is not in your 8-unit Loadout!")
            return False
        if (x, y) in self.road_set:
            self.log("Cannot build on the road!")
            return False
        if (x, y) in self.towers:
            self.log("Occupied! [U] Upgrade or [X] Sell.")
            return False
        bp = TOWER_BLUEPRINTS[kind]
        cost = bp.levels[0].cost
        if self.gold < cost:
            self.log(f"Need ${cost} for {bp.name} (have ${self.gold}).")
            return False
        self.gold -= cost
        t = Tower(
            x=x,
            y=y,
            kind=kind,
            blueprints=TOWER_BLUEPRINTS,
            level=1,
            total_invested=cost,
            income_timer=bp.levels[0].income_interval,
            spawn_timer=0.5 if bp.levels[0].spawn_ally_kind else 0.0,
        )
        self.towers[(x, y)] = t
        self.recompute_buffs()
        self.log(f"Built {bp.name} at ({x},{y}) for ${cost}.")
        return True

    def upgrade_tower(self, x: int, y: int) -> bool:
        if self.game_over:
            return False
        tower = self.towers.get((x, y))
        if tower is None:
            self.log("No tower here to upgrade.")
            return False
        cost = tower.upgrade_cost
        if cost is None:
            self.log(f"{tower.blueprint.name} is already MAX level (Lv{tower.level})!")
            return False
        if self.gold < cost:
            self.log(f"Need ${cost} to upgrade {tower.blueprint.name}.")
            return False
        self.gold -= cost
        tower.level += 1
        tower.total_invested += cost
        self.recompute_buffs()
        self.log(f"Upgraded {tower.blueprint.name} to Lv{tower.level} (${cost}).")
        return True

    def sell_tower(self, x: int, y: int) -> bool:
        if self.game_over:
            return False
        tower = self.towers.pop((x, y), None)
        if tower is None:
            self.log("No tower here to sell.")
            return False
        refund = tower.sell_value
        self.gold += refund
        self.allies = [a for a in self.allies if a.owner_pos != (x, y)]
        self.recompute_buffs()
        self.log(f"Sold {tower.blueprint.name} Lv{tower.level} for +${refund}.")
        return True

    def cycle_tower_targeting(self, x: int, y: int) -> bool:
        tower = self.towers.get((x, y))
        if tower is None:
            return False
        idx = TARGET_MODES.index(tower.target_mode)
        tower.target_mode = TARGET_MODES[(idx + 1) % len(TARGET_MODES)]
        self.log(f"{tower.blueprint.name} targeting: {tower.target_mode}.")
        return True

    def _collect_farm_wave_income(self) -> int:
        farm_gold = 0
        for t in self.towers.values():
            if t.stats.income_per_wave > 0:
                farm_gold += t.stats.income_per_wave
                t.gold_earned += t.stats.income_per_wave
        return farm_gold

    def start_next_wave(self, forced: bool = False) -> bool:
        """Start next wave, or prestart/rush the next wave early if one is already active!"""
        if self.game_over:
            return False
        if self.victory and not self.endless:
            return False

        # Prestart / Wave Rush during an active wave!
        if self.wave_active:
            if not self.endless and self.wave >= self.max_waves:
                self.log(f"Final wave {self.wave} is already active!")
                return False
            if self.wave_rush_cooldown > 0:
                self.log(f"Wait {self.wave_rush_cooldown:.1f}s before prestarting next wave.")
                return False
            self.wave += 1
            new_entries = build_wave_queue(self.wave)
            self.spawn_queue.extend(new_entries)
            rush_bonus = 15 + self.wave * 3 + self._collect_farm_wave_income()
            self.gold += rush_bonus
            self.score += rush_bonus * 2
            self.wave_rush_cooldown = 1.5
            self.log(f"PRESTART Wave {self.wave}! (+${rush_bonus} rush bonus, {len(new_entries)} foes added)")
            return True

        early_bonus = 0
        if not forced and self.next_wave_timer is not None and self.next_wave_timer > 1.0:
            early_bonus = min(35, int(self.next_wave_timer))
            self.gold += early_bonus

        self.next_wave_timer = None
        self.wave += 1
        self.spawn_queue = build_wave_queue(self.wave)
        self.spawn_timer = 0.0
        self.wave_active = True
        self.wave_rush_cooldown = 1.5
        self.paused = False

        bonus_txt = f" (+${early_bonus} early)" if early_bonus > 0 else ""
        prefix = "FORCED " if forced else ""
        self.log(f"{prefix}Wave {self.wave} started! ({len(self.spawn_queue)} foes){bonus_txt}")
        return True

    def enter_endless(self) -> bool:
        if not self.victory or self.game_over:
            return False
        self.endless = True
        self.victory = False
        if self.auto_start:
            self.next_wave_timer = 0.4
        elif self.difficulty.auto_wave_delay is not None:
            self.next_wave_timer = self.difficulty.auto_wave_delay
        self.log(f"Endless Mode unlocked! Press [N] for Wave {self.wave + 1}.")
        return True

    def active_bosses(self) -> List[Enemy]:
        return [e for e in self.enemies if e.is_boss and e.hp > 0]

    def lead_enemy(self) -> Optional[Enemy]:
        if not self.enemies:
            return None
        return max(self.enemies, key=lambda e: e.progress)

    def _spawn_enemy(
        self,
        kind: str,
        hp_scale: float = 1.0,
        progress: float = 0.0,
        lane_offset: Optional[float] = None,
    ) -> Enemy:
        tpl: UnitTemplate = UNIT_TEMPLATES[kind]
        hp = tpl.max_hp * hp_scale * self.difficulty.enemy_hp_mult
        speed = tpl.speed * self.difficulty.enemy_speed_mult
        reward = max(1, int(round(tpl.reward * self.difficulty.reward_mult)))
        leak_dmg = tpl.damage + self.difficulty.extra_leak_damage
        lane = (
            lane_offset
            if lane_offset is not None
            else LANE_OFFSETS[self._next_entity_id % len(LANE_OFFSETS)]
        )
        cd = tpl.ability_cooldown * self.difficulty.boss_cd_mult if tpl.boss_ability else 0.0
        enemy = Enemy(
            id=self._next_entity_id,
            template=tpl,
            hp=hp,
            max_hp=hp,
            speed=speed,
            reward=reward,
            damage=leak_dmg,
            armor_current=tpl.armor,
            progress=progress,
            lane_offset=lane,
            ability_timer=cd,
        )
        self._next_entity_id += 1
        self.enemies.append(enemy)
        return enemy

    def _spawn_ally(self, owner: Tower, kind: str) -> Optional[AllyUnit]:
        tpl: Optional[AllyTemplate] = ALLY_TEMPLATES.get(kind)
        if tpl is None:
            return None
        max_prog = float(len(self.centerline) - 1)
        lane = LANE_OFFSETS[self._next_entity_id % len(LANE_OFFSETS)]
        ally = AllyUnit(
            id=self._next_entity_id,
            template=tpl,
            owner_pos=(owner.x, owner.y),
            hp=tpl.max_hp,
            max_hp=tpl.max_hp,
            progress=max_prog,
            lane_offset=lane,
            revives_left=tpl.revives,
        )
        self._next_entity_id += 1
        self.allies.append(ally)
        return ally

    def _select_target(self, tower: Tower, exclude_ids: Optional[Set[int]] = None) -> Optional[Enemy]:
        tx, ty = float(tower.x), float(tower.y)
        r = tower.effective_range
        min_r = tower.stats.min_range
        in_range: List[Tuple[float, Enemy]] = []
        for e in self.enemies:
            if e.hp <= 0:
                continue
            if exclude_ids and e.id in exclude_ids:
                continue
            ex, ey = e.position(self.centerline)
            dist = math.hypot(ex - tx, ey - ty)
            if min_r <= dist <= r:
                in_range.append((dist, e))
        if not in_range:
            return None
        if tower.target_mode == TARGET_STRONGEST:
            return max(in_range, key=lambda pair: (pair[1].hp + pair[1].shield, pair[1].progress))[1]
        if tower.target_mode == TARGET_CLOSEST:
            return min(in_range, key=lambda pair: pair[0])[1]
        return max(in_range, key=lambda pair: pair[1].progress)[1]

    def _apply_damage(
        self,
        enemy: Enemy,
        raw_amount: float,
        source_tower: Optional[Tower],
        armor_pierce: float = 0.0,
        ignore_armor: bool = False,
        can_evade: bool = False,
        execute_pct: float = 0.0,
    ) -> float:
        if enemy.hp <= 0 or raw_amount <= 0:
            return 0.0
        if can_evade and enemy.template.evasion > 0.0:
            if self.rng.random() < enemy.template.evasion:
                return 0.0

        bonus = 0.0
        if execute_pct > 0.0:
            missing = max(0.0, enemy.max_hp - enemy.hp)
            bonus = min(raw_amount * 3.0, missing * execute_pct)

        total_raw = raw_amount + bonus
        if ignore_armor:
            dmg = total_raw
        else:
            eff_armor = enemy.armor_current * (1.0 - max(0.0, min(1.0, armor_pierce)))
            dmg = max(1.0, total_raw - eff_armor)

        if enemy.shield > 0:
            absorbed = min(enemy.shield, dmg)
            enemy.shield -= absorbed
            dmg -= absorbed

        if dmg > 0:
            enemy.hp -= dmg
            enemy.hit_flash = 0.12

        if enemy.hp <= 0:
            if source_tower is not None:
                source_tower.kills += 1
            self.gold += enemy.reward
            self.score += enemy.reward * 2
            if enemy.is_boss:
                coins = self._award_coins(14 + self.wave * 2)
                self.log(f"BOSS SLAIN: {enemy.name}! +{coins} Coins!")
            self._handle_death_split(enemy)
        return dmg

    def _handle_death_split(self, enemy: Enemy) -> None:
        tpl = enemy.template
        if not tpl.split_into or tpl.split_count <= 0:
            return
        if tpl.split_into not in UNIT_TEMPLATES:
            return
        for i in range(tpl.split_count):
            offset = LANE_OFFSETS[i % len(LANE_OFFSETS)]
            prog = max(0.0, enemy.progress - 0.25 * i)
            self._spawn_enemy(tpl.split_into, hp_scale=1.0, progress=prog, lane_offset=offset)

    def _trigger_boss_ability(self, boss: Enemy) -> None:
        ab = boss.template.boss_ability
        if ab == "surge":
            boss.surge_timer = 2.6
            self.log(f"{boss.name} uses SPEED SURGE!")
        elif ab == "spawn_spiders":
            for i in range(2):
                self._spawn_enemy("spider", progress=max(0.0, boss.progress - 0.6 - 0.3 * i))
            self.log(f"{boss.name} hatched 2 Dire Spiders!")
        elif ab == "inferno":
            for ally in list(self.allies):
                if abs(ally.progress - boss.progress) <= 3.0:
                    ally.hp -= 120.0
                    ally.hit_flash = 0.2
            self.log(f"{boss.name} unleashed INFERNO WAVE!")
        elif ab == "shield":
            boss.shield = min(1400.0, boss.shield + 600.0)
            self.log(f"{boss.name} raised an Obsidian Shield (+600)!")
        elif ab == "necromancy":
            for i in range(3):
                self._spawn_enemy("skeleton", progress=max(0.0, boss.progress - 0.5 - 0.4 * i))
            self.log(f"{boss.name} summoned 3 Skeletons!")
        elif ab == "void":
            boss.shield = min(2200.0, boss.shield + 950.0)
            for i in range(2):
                self._spawn_enemy("assassin", progress=max(0.0, boss.progress - 0.5 * (i + 1)))
            self.log(f"{boss.name} tore open a Void Rift!")

    def _handle_ally_second_life(self, ally: AllyUnit) -> bool:
        if ally.revives_left <= 0:
            return False
        ally.revives_left -= 1
        ally.hp = ally.max_hp * ally.template.revive_hp_ratio
        ally.revive_flash = 0.6
        ax, ay = ally.position(self.centerline)
        for enemy in list(self.enemies):
            if enemy.hp <= 0:
                continue
            ex, ey = enemy.position(self.centerline)
            if math.hypot(ex - ax, ey - ay) <= 2.4:
                self._apply_damage(enemy, ally.template.revive_blast_dmg, None, ignore_armor=True)
        self.log(f"{ally.template.name} triggered SECOND LIFE ({ally.revives_left} left)!")
        return True

    def tick(self, dt: float, in_modal: bool = False) -> None:
        if self.paused or self.game_over or (self.victory and not self.endless):
            return
        if in_modal and self.difficulty.pause_in_gamble:
            return

        if not self.wave_active:
            if self.auto_start and self.next_wave_timer is None:
                self.next_wave_timer = 0.25
            if self.next_wave_timer is not None:
                timer_dt = dt * (min(self.speed_mult, 4) if self.auto_start else 1)
                self.next_wave_timer -= timer_dt
                if self.next_wave_timer <= 0:
                    self.start_next_wave(forced=not self.auto_start)
            return

        if self.wave_rush_cooldown > 0:
            self.wave_rush_cooldown = max(0.0, self.wave_rush_cooldown - dt)

        sim_dt = dt * self.speed_mult
        steps = max(1, int(math.ceil(sim_dt / 0.05)))
        step_dt = sim_dt / steps
        for _ in range(steps):
            self._step(step_dt)
            if self.game_over:
                break

    def _step(self, dt: float) -> None:
        for shot in self.shots:
            shot.ttl -= dt
        self.shots = [s for s in self.shots if s.ttl > 0]

        if self.spawn_queue:
            self.spawn_timer -= dt
            while self.spawn_queue and self.spawn_timer <= 0:
                entry = self.spawn_queue.pop(0)
                self._spawn_enemy(entry.kind, hp_scale=entry.hp_scale)
                if self.spawn_queue:
                    self.spawn_timer += self.spawn_queue[0].delay

        # Farms, Spawners, Spike Factories, Ally-Healing Support Towers
        for tower in self.towers.values():
            st = tower.stats
            if st.income_per_tick > 0 and st.income_interval > 0:
                tower.income_timer -= dt
                if tower.income_timer <= 0:
                    tower.income_timer += st.income_interval
                    self.gold += st.income_per_tick
                    tower.gold_earned += st.income_per_tick
            if st.heal_allies_per_sec > 0 and self.allies:
                for ally in self.allies:
                    if ally.hp <= 0 or ally.hp >= ally.max_hp:
                        continue
                    ax, ay = ally.position(self.centerline)
                    if math.hypot(ax - tower.x, ay - tower.y) <= tower.effective_range:
                        ally.hp = min(ally.max_hp, ally.hp + st.heal_allies_per_sec * dt)
            if st.spawn_ally_kind and st.spawn_interval > 0:
                active_owned = sum(
                    1 for a in self.allies if a.owner_pos == (tower.x, tower.y) and a.hp > 0
                )
                if active_owned < st.max_active_allies:
                    tower.spawn_timer -= dt
                    if tower.spawn_timer <= 0:
                        tower.spawn_timer = st.spawn_interval
                        self._spawn_ally(tower, st.spawn_ally_kind)
            if st.spike_damage > 0 and st.spike_charges > 0:
                if tower.cooldown_left > 0:
                    tower.cooldown_left = max(0.0, tower.cooldown_left - dt)
                if tower.cooldown_left <= 0:
                    nearby_road = [
                        (rx, ry)
                        for (rx, ry) in self.road_set
                        if math.hypot(rx - tower.x, ry - tower.y) <= tower.effective_range
                        and (rx, ry) not in self.spikes
                    ]
                    if nearby_road:
                        rx, ry = self.rng.choice(nearby_road)
                        self.spikes[(rx, ry)] = RoadSpike(
                            x=rx,
                            y=ry,
                            damage=st.spike_damage * tower.buff_dmg_mult,
                            charges=st.spike_charges,
                            owner_pos=(tower.x, tower.y),
                        )
                        tower.cooldown_left = tower.effective_cooldown

        # Enemy heal auras
        healers = [e for e in self.enemies if e.hp > 0 and e.template.heal_aura_per_sec > 0]
        for healer in healers:
            hx, hy = healer.position(self.centerline)
            rad = healer.template.heal_aura_radius
            heal_amt = healer.template.heal_aura_per_sec * dt
            for ally_e in self.enemies:
                if ally_e.hp <= 0 or ally_e.hp >= ally_e.max_hp:
                    continue
                ax, ay = ally_e.position(self.centerline)
                if math.hypot(ax - hx, ay - hy) <= rad:
                    ally_e.hp = min(ally_e.max_hp, ally_e.hp + heal_amt)

        # Friendly AllyUnits vs Enemies
        for e in self.enemies:
            e.engaged = False

        for ally in list(self.allies):
            if ally.hp <= 0:
                continue
            if ally.hit_flash > 0:
                ally.hit_flash = max(0.0, ally.hit_flash - dt)
            if ally.revive_flash > 0:
                ally.revive_flash = max(0.0, ally.revive_flash - dt)

            nearby = [
                e for e in self.enemies if e.hp > 0 and abs(e.progress - ally.progress) <= 0.95
            ]
            if nearby:
                target_e = max(nearby, key=lambda e: e.progress)
                target_e.engaged = True
                if ally.template.splash_radius > 0:
                    ax, ay = ally.position(self.centerline)
                    for e in list(nearby):
                        ex, ey = e.position(self.centerline)
                        if math.hypot(ex - ax, ey - ay) <= ally.template.splash_radius:
                            self._apply_damage(e, ally.template.atk_dps * dt, None, armor_pierce=0.35)
                else:
                    self._apply_damage(target_e, ally.template.atk_dps * dt, None, armor_pierce=0.25)

                incoming = max(2.0, target_e.template.atk_dps - ally.template.armor) * dt
                ally.hp -= incoming
                ally.hit_flash = 0.1
                if ally.hp <= 0:
                    self._handle_ally_second_life(ally)
            else:
                if ally.progress > 0.35:
                    ally.progress = max(0.35, ally.progress - ally.template.speed * dt)

        self.allies = [a for a in self.allies if a.hp > 0]

        # Move enemies
        reached_goal: List[Enemy] = []
        max_progress = float(len(self.centerline) - 1)
        for enemy in list(self.enemies):
            if enemy.hp <= 0:
                continue
            if enemy.hit_flash > 0:
                enemy.hit_flash = max(0.0, enemy.hit_flash - dt)
            if enemy.slow_timer > 0:
                enemy.slow_timer = max(0.0, enemy.slow_timer - dt)
                if enemy.slow_timer == 0:
                    enemy.slow_factor = 0.0
            if enemy.stun_timer > 0:
                enemy.stun_timer = max(0.0, enemy.stun_timer - dt)
            if enemy.surge_timer > 0:
                enemy.surge_timer = max(0.0, enemy.surge_timer - dt)

            if enemy.template.regen_per_sec > 0 and enemy.hp < enemy.max_hp:
                enemy.hp = min(enemy.max_hp, enemy.hp + enemy.template.regen_per_sec * dt)

            if enemy.poison_timer > 0:
                enemy.poison_timer = max(0.0, enemy.poison_timer - dt)
                self._apply_damage(
                    enemy, enemy.poison_dps * dt, enemy.poison_source_tower, ignore_armor=True
                )
                if enemy.hp <= 0:
                    continue

            if enemy.template.boss_ability:
                enemy.ability_timer -= dt
                if enemy.ability_timer <= 0:
                    enemy.ability_timer = enemy.template.ability_cooldown * self.difficulty.boss_cd_mult
                    self._trigger_boss_ability(enemy)

            if not enemy.engaged and enemy.stun_timer <= 0:
                eff_speed = enemy.speed * (1.0 - enemy.slow_factor)
                if (
                    enemy.template.berserk_threshold > 0
                    and (enemy.hp / enemy.max_hp) <= enemy.template.berserk_threshold
                ):
                    eff_speed *= 1.6
                if enemy.surge_timer > 0:
                    eff_speed *= 1.65

                prev_cell = enemy.grid_cell(self.centerline, self.road_set)
                enemy.progress += eff_speed * dt
                new_cell = enemy.grid_cell(self.centerline, self.road_set)
                if new_cell in self.spikes and new_cell != prev_cell:
                    spike = self.spikes[new_cell]
                    owner_t = self.towers.get(spike.owner_pos)
                    self._apply_damage(enemy, spike.damage, owner_t, armor_pierce=1.0)
                    spike.charges -= 1
                    if spike.charges <= 0:
                        self.spikes.pop(new_cell, None)
                    if enemy.hp <= 0:
                        continue

            if enemy.progress >= max_progress:
                reached_goal.append(enemy)

        if reached_goal:
            for enemy in reached_goal:
                self.lives = max(0, self.lives - enemy.damage)
                self.log(f"{enemy.name} breached the base! (-{enemy.damage} HP)")
            reached_ids = {e.id for e in reached_goal}
            self.enemies = [e for e in self.enemies if e.id not in reached_ids]
            if self.lives <= 0:
                self.game_over = True
                self.wave_active = False
                self.next_wave_timer = None
                coins = self._award_coins(max(10, self.wave * 8))
                self.log(f"DEFEAT! Earned +{coins} Coins for your effort.")
                return

        # Combat towers fire
        for tower in self.towers.values():
            st = tower.stats
            if st.damage <= 0 or st.spike_damage > 0:
                continue
            if tower.cooldown_left > 0:
                tower.cooldown_left = max(0.0, tower.cooldown_left - dt)
            if tower.cooldown_left > 0 or not self.enemies:
                continue
            target = self._select_target(tower)
            if target is None:
                continue

            tower.cooldown_left = tower.effective_cooldown
            tx, ty = float(tower.x), float(tower.y)
            ex, ey = target.position(self.centerline)
            self.shots.append(
                ShotEffect(x0=tx, y0=ty, x1=ex, y1=ey, char=tower.blueprint.shot_char, kind=tower.kind)
            )

            eff_dmg = tower.effective_damage
            is_aoe = st.splash_radius > 0
            dealt = self._apply_damage(
                target,
                eff_dmg,
                tower,
                armor_pierce=st.armor_pierce,
                can_evade=not is_aoe,
                execute_pct=st.execute_pct,
            )

            if dealt > 0 and st.armor_shred > 0 and target.hp > 0:
                target.armor_current = max(0.0, target.armor_current - st.armor_shred)

            if st.stun_duration > 0 and target.hp > 0 and not target.is_boss:
                target.stun_timer = max(target.stun_timer, st.stun_duration)

            if st.poison_dps > 0 and target.hp > 0:
                scaled_dps = st.poison_dps * tower.buff_dmg_mult
                if scaled_dps >= target.poison_dps or target.poison_timer <= 0:
                    target.poison_dps = scaled_dps
                    target.poison_source_tower = tower
                target.poison_timer = max(target.poison_timer, st.poison_duration)

            if st.slow_factor > 0 and target.hp > 0 and not target.template.slow_immune:
                if st.slow_factor >= target.slow_factor:
                    target.slow_factor = st.slow_factor
                target.slow_timer = max(target.slow_timer, st.slow_duration)

            if st.splash_radius > 0:
                splash_dmg = eff_dmg * st.splash_ratio
                for other in list(self.enemies):
                    if other.id == target.id or other.hp <= 0:
                        continue
                    ox, oy = other.position(self.centerline)
                    if math.hypot(ox - ex, oy - ey) <= st.splash_radius:
                        s_dealt = self._apply_damage(
                            other,
                            splash_dmg,
                            tower,
                            armor_pierce=st.armor_pierce,
                            execute_pct=st.execute_pct,
                        )
                        if s_dealt > 0 and st.armor_shred > 0 and other.hp > 0:
                            other.armor_current = max(0.0, other.armor_current - st.armor_shred)
                        if st.slow_factor > 0 and other.hp > 0 and not other.template.slow_immune:
                            if st.slow_factor >= other.slow_factor:
                                other.slow_factor = st.slow_factor
                            other.slow_timer = max(other.slow_timer, st.slow_duration)
                        if st.poison_dps > 0 and other.hp > 0:
                            other.poison_dps = max(other.poison_dps, st.poison_dps * tower.buff_dmg_mult)
                            other.poison_timer = max(other.poison_timer, st.poison_duration)
                            other.poison_source_tower = tower

            if st.chain_count > 1:
                hit_ids: Set[int] = {target.id}
                curr_x, curr_y = ex, ey
                curr_dmg = eff_dmg * st.chain_falloff
                for _ in range(st.chain_count - 1):
                    candidates = [e for e in self.enemies if e.hp > 0 and e.id not in hit_ids]
                    if not candidates:
                        break
                    nxt = min(
                        candidates,
                        key=lambda e: math.hypot(
                            e.position(self.centerline)[0] - curr_x,
                            e.position(self.centerline)[1] - curr_y,
                        ),
                    )
                    nx, ny = nxt.position(self.centerline)
                    if math.hypot(nx - curr_x, ny - curr_y) > 3.8:
                        break
                    hit_ids.add(nxt.id)
                    self.shots.append(
                        ShotEffect(
                            x0=curr_x, y0=curr_y, x1=nx, y1=ny, char=tower.blueprint.shot_char, kind=tower.kind
                        )
                    )
                    self._apply_damage(
                        nxt, curr_dmg, tower, armor_pierce=st.armor_pierce, execute_pct=st.execute_pct
                    )
                    if st.stun_duration > 0 and nxt.hp > 0 and not nxt.is_boss:
                        nxt.stun_timer = max(nxt.stun_timer, st.stun_duration * 0.7)
                    if st.poison_dps > 0 and nxt.hp > 0:
                        nxt.poison_dps = max(nxt.poison_dps, st.poison_dps * tower.buff_dmg_mult)
                        nxt.poison_timer = max(nxt.poison_timer, st.poison_duration)
                        nxt.poison_source_tower = tower
                    curr_x, curr_y = nx, ny
                    curr_dmg *= st.chain_falloff

        self.enemies = [e for e in self.enemies if e.hp > 0]

        # Wave completion
        if self.wave_active and not self.spawn_queue and not self.enemies:
            self.wave_active = False
            farm_gold = self._collect_farm_wave_income()
            bonus = 25 + self.wave * 6 + farm_gold
            self.gold += bonus
            self.score += bonus * 3
            coins = self._award_coins(14 + self.wave * 3)

            if not self.endless and self.wave >= self.max_waves:
                self.victory = True
                self.next_wave_timer = None
                win_coins = self._award_coins(300)
                if self.profile is not None:
                    self.profile.total_wins += 1
                    self.profile.save()
                self.log(
                    f"VICTORY! All {self.max_waves} waves conquered! +${bonus} Gold | +{coins + win_coins} Coins!"
                )
            else:
                if self.auto_start:
                    self.next_wave_timer = 0.4
                    self.log(f"Wave {self.wave} cleared (+${bonus}, +{coins}c)! Auto-starting next...")
                else:
                    self.next_wave_timer = self.difficulty.auto_wave_delay
                    farm_note = f" (incl ${farm_gold} Farm)" if farm_gold > 0 else ""
                    if self.next_wave_timer is not None:
                        self.log(
                            f"Wave {self.wave} cleared (+${bonus}{farm_note}, +{coins}c)! Next in {int(self.next_wave_timer)}s [N]"
                        )
                    else:
                        self.log(
                            f"Wave {self.wave} cleared (+${bonus}{farm_note}, +{coins}c)! Press [N] for next."
                        )

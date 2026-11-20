"""Persistent player profile: Coins, Unit Inventory, max-8 Loadout, Auto-Sell & Pity."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from game.data.progression import (
    FUSION_BY_KEY,
    PERK_BY_KEY,
    star_upgrade_coin_cost,
    unit_qualifies_for_perk,
)
from game.data.rarities import RARITIES, RARITY_ORDER, STARTING_COINS
from game.data.towers import STARTER_LOADOUT, TOWER_BLUEPRINTS, TOWER_ORDER
from game.models import AUTO_SELL_MODES, MAX_LOADOUT, MAX_PERK_LOADOUT, MAX_UNIT_STAR


DEFAULT_SAVE_PATH = os.environ.get(
    "TD_SAVE_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "save.json"),
)

AUTO_SELL_LABELS: Dict[str, str] = {
    "off": "OFF",
    "dupes_c": "Dupes: Common",
    "dupes_cr": "Dupes: C+Rare",
    "dupes_cre": "Dupes: C+R+Epic",
    "dupes_all": "Dupes: EVERY",
    "all_c": "ALL Common",
    "all_cr": "ALL C+Rare",
}


@dataclass
class PlayerProfile:
    coins: int = STARTING_COINS
    inventory: Dict[str, int] = field(default_factory=dict)
    loadout: List[str] = field(default_factory=list)
    unit_stars: Dict[str, int] = field(default_factory=dict)
    active_perks: List[Dict[str, Any]] = field(default_factory=list)
    auto_sell_mode: str = "off"
    pity_counter: int = 0
    total_summons: int = 0
    total_wins: int = 0
    best_wave: int = 0
    save_path: Optional[str] = DEFAULT_SAVE_PATH

    @classmethod
    def new_default(cls, save_path: Optional[str] = DEFAULT_SAVE_PATH) -> "PlayerProfile":
        inv = {k: 1 for k in STARTER_LOADOUT}
        return cls(
            coins=STARTING_COINS,
            inventory=inv,
            loadout=list(STARTER_LOADOUT),
            save_path=save_path,
        )

    @classmethod
    def load(cls, save_path: Optional[str] = DEFAULT_SAVE_PATH) -> "PlayerProfile":
        if not save_path or not os.path.exists(save_path):
            prof = cls.new_default(save_path=save_path)
            prof.save()
            return prof
        try:
            with open(save_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            inv = {
                k: int(v)
                for k, v in raw.get("inventory", {}).items()
                if k in TOWER_BLUEPRINTS and int(v) > 0
            }
            if not inv:
                inv = {k: 1 for k in STARTER_LOADOUT}
            raw_perks = [
                p
                for p in raw.get("active_perks", [])
                if isinstance(p, dict) and p.get("perk_key") in PERK_BY_KEY and int(p.get("runs_left", 0)) > 0
            ]
            slot_bonus = sum(
                int(p.get("value", 0))
                for p in raw_perks
                if p.get("perk_type") == "slot_bonus" and int(p.get("runs_left", 0)) > 0
            )
            eff_max = min(MAX_PERK_LOADOUT, MAX_LOADOUT + slot_bonus)
            loadout = [
                k for k in raw.get("loadout", []) if k in inv and k in TOWER_BLUEPRINTS
            ][:eff_max]
            seen = set()
            clean_loadout = []
            for k in loadout:
                if k not in seen:
                    seen.add(k)
                    clean_loadout.append(k)
            if not clean_loadout:
                clean_loadout = list(inv.keys())[:eff_max]
            unit_stars = {
                k: max(1, min(MAX_UNIT_STAR, int(v)))
                for k, v in raw.get("unit_stars", {}).items()
                if k in TOWER_BLUEPRINTS and int(v) > 1
            }
            asm = raw.get("auto_sell_mode", "off")
            if asm not in AUTO_SELL_MODES:
                asm = "off"
            return cls(
                coins=max(0, int(raw.get("coins", STARTING_COINS))),
                inventory=inv,
                loadout=clean_loadout,
                unit_stars=unit_stars,
                active_perks=raw_perks,
                auto_sell_mode=asm,
                pity_counter=max(0, int(raw.get("pity_counter", 0))),
                total_summons=max(0, int(raw.get("total_summons", 0))),
                total_wins=max(0, int(raw.get("total_wins", 0))),
                best_wave=max(0, int(raw.get("best_wave", 0))),
                save_path=save_path,
            )
        except (OSError, ValueError, TypeError):
            return cls.new_default(save_path=save_path)

    def save(self) -> None:
        if not self.save_path:
            return
        try:
            os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
            data = {
                "coins": self.coins,
                "inventory": self.inventory,
                "loadout": self.loadout,
                "unit_stars": self.unit_stars,
                "active_perks": self.active_perks,
                "auto_sell_mode": self.auto_sell_mode,
                "pity_counter": self.pity_counter,
                "total_summons": self.total_summons,
                "total_wins": self.total_wins,
                "best_wave": self.best_wave,
            }
            with open(self.save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def owned_total(self) -> int:
        return sum(self.inventory.values())

    def owned_unique_keys(self) -> List[str]:
        return [k for k in TOWER_ORDER if self.inventory.get(k, 0) > 0]

    def cycle_auto_sell(self) -> str:
        idx = AUTO_SELL_MODES.index(self.auto_sell_mode)
        self.auto_sell_mode = AUTO_SELL_MODES[(idx + 1) % len(AUTO_SELL_MODES)]
        self.save()
        return self.auto_sell_mode

    def star_of(self, key: str) -> int:
        return max(1, min(MAX_UNIT_STAR, int(self.unit_stars.get(key, 1))))

    def effective_max_loadout(self) -> int:
        bonus = sum(
            int(p.get("value", 0))
            for p in self.active_perks
            if p.get("perk_type") == "slot_bonus" and int(p.get("runs_left", 0)) > 0
        )
        return min(MAX_PERK_LOADOUT, MAX_LOADOUT + bonus)

    def should_auto_sell(self, key: str, owned_before: int) -> bool:
        mode = self.auto_sell_mode
        if mode == "off" or key not in TOWER_BLUEPRINTS:
            return False
        rar = TOWER_BLUEPRINTS[key].rarity
        if mode == "dupes_c":
            return owned_before > 0 and rar == "common"
        if mode == "dupes_cr":
            return owned_before > 0 and rar in ("common", "rare")
        if mode == "dupes_cre":
            return owned_before > 0 and rar in ("common", "rare", "epic")
        if mode == "dupes_all":
            return owned_before > 0
        if mode == "all_c":
            return rar == "common" and self.owned_total() >= 1
        if mode == "all_cr":
            return rar in ("common", "rare") and self.owned_total() >= 1
        return False

    def add_unit(self, key: str, count: int = 1) -> None:
        if key not in TOWER_BLUEPRINTS:
            return
        self.inventory[key] = self.inventory.get(key, 0) + count
        if len(self.loadout) < self.effective_max_loadout() and key not in self.loadout:
            self.loadout.append(key)

    def toggle_loadout(self, key: str) -> Tuple[bool, str]:
        if self.inventory.get(key, 0) <= 0:
            return False, "You don't own that unit."
        bp = TOWER_BLUEPRINTS[key]
        max_slots = self.effective_max_loadout()
        if key in self.loadout:
            if len(self.loadout) <= 1:
                return False, "Must keep at least 1 unit in your Loadout!"
            self.loadout.remove(key)
            self.save()
            return True, f"Unequipped {bp.name}."
        if len(self.loadout) >= max_slots:
            return False, f"Loadout full (max {max_slots})! Unequip a unit first."
        self.loadout.append(key)
        self.save()
        return True, f"Equipped {bp.name} into slot {len(self.loadout)}!"

    def sell_unit(self, key: str, qty: int = 1) -> Tuple[bool, int, str]:
        owned = self.inventory.get(key, 0)
        if owned < qty or qty <= 0:
            return False, 0, "Not enough copies to sell."
        if self.owned_total() - qty < 1:
            return False, 0, "Cannot sell your very last unit!"
        bp = TOWER_BLUEPRINTS[key]
        gain = RARITIES[bp.rarity].sell_coins * qty
        new_count = owned - qty
        if new_count <= 0:
            self.inventory.pop(key, None)
            if key in self.loadout:
                self.loadout.remove(key)
                if not self.loadout:
                    fallback = next(iter(self.inventory.keys()), None)
                    if fallback:
                        self.loadout.append(fallback)
        else:
            self.inventory[key] = new_count
        self.coins += gain
        self.save()
        return True, gain, f"Sold {qty}x {bp.name} for +{gain} Coins!"

    def sell_all_duplicates(self) -> Tuple[int, int]:
        sold = 0
        gained = 0
        for key in list(self.inventory.keys()):
            cnt = self.inventory[key]
            if cnt > 1:
                dupes = cnt - 1
                bp = TOWER_BLUEPRINTS[key]
                gained += RARITIES[bp.rarity].sell_coins * dupes
                sold += dupes
                self.inventory[key] = 1
        if sold > 0:
            self.coins += gained
            self.save()
        return sold, gained

    def upgrade_unit_star(self, key: str, use_dupe: bool = True) -> Tuple[bool, str]:
        owned = self.inventory.get(key, 0)
        if owned <= 0 or key not in TOWER_BLUEPRINTS:
            return False, "You don't own this unit."
        cur_star = self.star_of(key)
        if cur_star >= MAX_UNIT_STAR:
            return False, f"{TOWER_BLUEPRINTS[key].name} is already MAX ★{MAX_UNIT_STAR}!"
        bp = TOWER_BLUEPRINTS[key]
        has_dupe = use_dupe and owned >= 2
        cost = star_upgrade_coin_cost(bp.rarity, cur_star + 1, has_dupe)
        if self.coins < cost:
            return False, f"Need {cost} Coins to Star-Up {bp.name} (have {self.coins})."
        self.coins -= cost
        if has_dupe:
            self.inventory[key] = owned - 1
        self.unit_stars[key] = cur_star + 1
        self.save()
        dupe_txt = " (used 1 dupe -50%)" if has_dupe else ""
        return True, f"{bp.name} upgraded to ★{cur_star + 1} for {cost}c{dupe_txt}!"

    def craft_fusion(self, recipe_key: str) -> Tuple[bool, str]:
        recipe = FUSION_BY_KEY.get(recipe_key)
        if recipe is None or recipe.output_key not in TOWER_BLUEPRINTS:
            return False, "Unknown fusion recipe."
        cnt_a = self.inventory.get(recipe.ing_a, 0)
        cnt_b = self.inventory.get(recipe.ing_b, 0)
        bp_a = TOWER_BLUEPRINTS[recipe.ing_a]
        bp_b = TOWER_BLUEPRINTS[recipe.ing_b]
        bp_out = TOWER_BLUEPRINTS[recipe.output_key]
        if recipe.ing_a == recipe.ing_b:
            if cnt_a < 2:
                return False, f"Need 2x {bp_a.name} to fuse."
        elif cnt_a < 1 or cnt_b < 1:
            return False, f"Need {bp_a.name} + {bp_b.name} to fuse {bp_out.name}."
        if self.coins < recipe.coin_cost:
            return False, f"Need {recipe.coin_cost} Coins (have {self.coins})."

        self.coins -= recipe.coin_cost
        for ing in (recipe.ing_a, recipe.ing_b):
            rem = self.inventory.get(ing, 0) - 1
            if rem <= 0:
                self.inventory.pop(ing, None)
                self.unit_stars.pop(ing, None)
                if ing in self.loadout:
                    self.loadout.remove(ing)
            else:
                self.inventory[ing] = rem

        self.inventory[recipe.output_key] = self.inventory.get(recipe.output_key, 0) + 1
        if len(self.loadout) < self.effective_max_loadout() and recipe.output_key not in self.loadout:
            self.loadout.append(recipe.output_key)
        if not self.loadout:
            fallback = next(iter(self.inventory.keys()), None)
            if fallback:
                self.loadout.append(fallback)
        self.save()
        return True, f"FUSION SUCCESS! Forged [{RARITIES[bp_out.rarity].label}] {bp_out.name}!"

    def sacrifice_for_perk(self, perk_key: str, unit_key: str) -> Tuple[bool, str]:
        perk = PERK_BY_KEY.get(perk_key)
        if perk is None:
            return False, "Unknown Altar offering."
        owned = self.inventory.get(unit_key, 0)
        if owned <= 0 or unit_key not in TOWER_BLUEPRINTS:
            return False, "You don't own that unit."
        if self.owned_total() <= 1:
            return False, "Cannot sacrifice your very last unit!"
        bp = TOWER_BLUEPRINTS[unit_key]
        star = self.star_of(unit_key)
        ok, err = unit_qualifies_for_perk(perk, bp, star)
        if not ok:
            return False, err

        if perk.perk_type == "slot_bonus":
            cur_slots = sum(int(p.get("value", 0)) for p in self.active_perks if p.get("perk_type") == "slot_bonus")
            if cur_slots >= 2:
                # Refresh duration on existing slot buffs instead of wasting
                for p in self.active_perks:
                    if p.get("perk_type") == "slot_bonus":
                        p["runs_left"] = max(int(p.get("runs_left", 0)), perk.duration_runs + (1 if star >= 3 else 0))
                rem = owned - 1
                self._consume_one_copy(unit_key, rem)
                self.save()
                return True, f"Sacrificed {bp.name} (★{star}) to extend +2 Slots!"

        # Compute scaled bonus value & runs
        val: float = perk.value
        runs = perk.duration_runs + (1 if star >= 3 else 0)
        rar_idx = RARITY_ORDER.index(bp.rarity)
        if perk.key == "war_chest" and rar_idx >= RARITY_ORDER.index("mythic"):
            val = 225
        elif perk.key == "titan_heart" and rar_idx >= RARITY_ORDER.index("legendary"):
            val = 18
        elif perk.key == "fortune_crown" and rar_idx >= RARITY_ORDER.index("mythic"):
            val = 0.60
        elif perk.key == "chrono_overclock" and bp.rarity == "transcendent":
            val = 0.28

        rem = owned - 1
        self._consume_one_copy(unit_key, rem)

        if perk.perk_type == "slot_bonus":
            self.active_perks.append(
                {
                    "perk_key": perk.key,
                    "name": perk.name,
                    "perk_type": perk.perk_type,
                    "value": int(val),
                    "runs_left": runs,
                    "source_name": bp.name,
                }
            )
        else:
            existing = next((p for p in self.active_perks if p.get("perk_key") == perk.key), None)
            if existing is not None:
                existing["value"] = max(float(existing.get("value", 0)), float(val))
                existing["runs_left"] = max(int(existing.get("runs_left", 0)), runs)
                existing["source_name"] = bp.name
            else:
                self.active_perks.append(
                    {
                        "perk_key": perk.key,
                        "name": perk.name,
                        "perk_type": perk.perk_type,
                        "value": val,
                        "runs_left": runs,
                        "source_name": bp.name,
                    }
                )
        self.save()
        return True, f"ALTAR BLESSING: Sacrificed {bp.name} ★{star} -> {perk.name} for {runs} runs!"

    def _consume_one_copy(self, key: str, rem: int) -> None:
        if rem <= 0:
            self.inventory.pop(key, None)
            self.unit_stars.pop(key, None)
            if key in self.loadout:
                self.loadout.remove(key)
                if not self.loadout:
                    fallback = next(iter(self.inventory.keys()), None)
                    if fallback:
                        self.loadout.append(fallback)
        else:
            self.inventory[key] = rem

    def consume_perks_for_run(self) -> Dict[str, Any]:
        """Snapshot active perks for the upcoming battle and decrement runs_left by 1."""
        snap: Dict[str, Any] = {
            "slot_bonus": 0,
            "start_gold": 0,
            "extra_lives": 0,
            "dmg_mult": 1.0,
            "spd_mult": 1.0,
            "coin_mult": 1.0,
            "cost_mult": 1.0,
            "labels": [],
        }
        next_perks: List[Dict[str, Any]] = []
        for p in self.active_perks:
            runs = int(p.get("runs_left", 0))
            if runs <= 0:
                continue
            ptype = p.get("perk_type")
            val = float(p.get("value", 0))
            if ptype == "slot_bonus":
                snap["slot_bonus"] += int(val)
            elif ptype == "start_gold":
                snap["start_gold"] += int(val)
            elif ptype == "extra_lives":
                snap["extra_lives"] += int(val)
            elif ptype == "dps_overclock":
                snap["dmg_mult"] += val
                snap["spd_mult"] += val * 0.75
            elif ptype == "coin_mult":
                snap["coin_mult"] += val
            elif ptype == "cost_discount":
                snap["cost_mult"] = max(0.65, snap["cost_mult"] - val)
            snap["labels"].append(f"{p.get('name')} ({runs}r)")
            new_runs = runs - 1
            if new_runs > 0:
                updated = dict(p)
                updated["runs_left"] = new_runs
                next_perks.append(updated)
        self.active_perks = next_perks
        eff_max = self.effective_max_loadout()
        if len(self.loadout) > eff_max:
            self.loadout = self.loadout[:eff_max]
        self.save()
        return snap

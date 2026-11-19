"""Persistent player profile: Coins, Unit Inventory, max-8 Loadout, Auto-Sell & Pity."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from typing import Dict, List, Optional, Tuple

from game.data.rarities import RARITIES, STARTING_COINS
from game.data.towers import STARTER_LOADOUT, TOWER_BLUEPRINTS, TOWER_ORDER
from game.models import AUTO_SELL_MODES, MAX_LOADOUT


DEFAULT_SAVE_PATH = os.environ.get(
    "TD_SAVE_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "save.json"),
)

AUTO_SELL_LABELS: Dict[str, str] = {
    "off": "OFF",
    "dupes_c": "Dupes: Common",
    "dupes_cr": "Dupes: C+Rare",
    "dupes_cre": "Dupes: C+R+Epic",
    "all_c": "ALL Common",
    "all_cr": "ALL C+Rare",
}


@dataclass
class PlayerProfile:
    coins: int = STARTING_COINS
    inventory: Dict[str, int] = field(default_factory=dict)
    loadout: List[str] = field(default_factory=list)
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
            loadout = [
                k for k in raw.get("loadout", []) if k in inv and k in TOWER_BLUEPRINTS
            ][:MAX_LOADOUT]
            seen = set()
            clean_loadout = []
            for k in loadout:
                if k not in seen:
                    seen.add(k)
                    clean_loadout.append(k)
            if not clean_loadout:
                clean_loadout = list(inv.keys())[:MAX_LOADOUT]
            asm = raw.get("auto_sell_mode", "off")
            if asm not in AUTO_SELL_MODES:
                asm = "off"
            return cls(
                coins=max(0, int(raw.get("coins", STARTING_COINS))),
                inventory=inv,
                loadout=clean_loadout,
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
        if mode == "all_c":
            return rar == "common" and self.owned_total() >= 1
        if mode == "all_cr":
            return rar in ("common", "rare") and self.owned_total() >= 1
        return False

    def add_unit(self, key: str, count: int = 1) -> None:
        if key not in TOWER_BLUEPRINTS:
            return
        self.inventory[key] = self.inventory.get(key, 0) + count
        if len(self.loadout) < MAX_LOADOUT and key not in self.loadout:
            self.loadout.append(key)

    def toggle_loadout(self, key: str) -> Tuple[bool, str]:
        if self.inventory.get(key, 0) <= 0:
            return False, "You don't own that unit."
        bp = TOWER_BLUEPRINTS[key]
        if key in self.loadout:
            if len(self.loadout) <= 1:
                return False, "Must keep at least 1 unit in your Loadout!"
            self.loadout.remove(key)
            self.save()
            return True, f"Unequipped {bp.name}."
        if len(self.loadout) >= MAX_LOADOUT:
            return False, f"Loadout full (max {MAX_LOADOUT})! Unequip a unit first."
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

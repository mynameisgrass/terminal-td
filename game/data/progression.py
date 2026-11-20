"""Fusion recipes, Star-Up upgrade costs, and Sacrifice Altar run perks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from game.data.rarities import RARITY_ORDER
from game.models import TowerBlueprint


@dataclass(frozen=True)
class FusionRecipe:
    key: str
    output_key: str
    ing_a: str
    ing_b: str
    coin_cost: int
    description: str


FUSION_RECIPES: Tuple[FusionRecipe, ...] = (
    FusionRecipe(
        key="fuse_cryo_cannon",
        output_key="cryo_cannon",
        ing_a="demoman",
        ing_b="frost_mage",
        coin_cost=100,
        description="Demoman + Frostling -> Freeze Artillery",
    ),
    FusionRecipe(
        key="fuse_plasma_sniper",
        output_key="plasma_sniper",
        ing_a="scout",
        ing_b="sniper",
        coin_cost=140,
        description="Scout + Sniper -> Armor-Shred Sniper",
    ),
    FusionRecipe(
        key="fuse_accelerator",
        output_key="accelerator",
        ing_a="electro",
        ing_b="commander",
        coin_cost=280,
        description="Electro + Commander -> Plasma Beam DPS",
    ),
    FusionRecipe(
        key="fuse_zenith_forge",
        output_key="zenith_forge",
        ing_a="golden_bank",
        ing_b="chronomancer",
        coin_cost=600,
        description="Golden Vault + Chronomancer -> Cosmic Vault",
    ),
    FusionRecipe(
        key="fuse_prism_overlord",
        output_key="prism_overlord",
        ing_a="sun_temple",
        ing_b="accelerator",
        coin_cost=700,
        description="Sun Avatar + Accelerator -> Hyper 7-Beam",
    ),
    FusionRecipe(
        key="fuse_eclipse_titan",
        output_key="eclipse_titan",
        ing_a="abyss_reaper",
        ing_b="titan_forge",
        coin_cost=700,
        description="Abyss Reaper + Titan Forge -> Fusion Titan",
    ),
    FusionRecipe(
        key="fuse_monarch_core",
        output_key="monarch_core",
        ing_a="void_monarch",
        ing_b="quantum_bank",
        coin_cost=900,
        description="Void Monarch + Quantum Core -> APEX MONARCH CORE",
    ),
)

FUSION_BY_KEY: Dict[str, FusionRecipe] = {r.key: r for r in FUSION_RECIPES}


# Star Upgrade (★1 -> ★5): +12% DMG, +6% ATK SPD, +5% Income per Star above ★1
STAR_BASE_COSTS: Dict[int, int] = {
    2: 150,
    3: 320,
    4: 650,
    5: 1200,
}

RARITY_STAR_MULT: Dict[str, float] = {
    "common": 0.6,
    "rare": 0.8,
    "epic": 1.0,
    "legendary": 1.25,
    "mythic": 1.6,
    "transcendent": 2.0,
}


def star_upgrade_coin_cost(rarity: str, next_star: int, has_dupe: bool) -> int:
    base = STAR_BASE_COSTS.get(next_star, 1200)
    mult = RARITY_STAR_MULT.get(rarity, 1.0)
    full = int(round((base * mult) / 10.0)) * 10
    return max(20, (full + 1) // 2) if has_dupe else max(30, full)


@dataclass(frozen=True)
class SacrificePerkDef:
    key: str
    name: str
    perk_type: str  # slot_bonus, start_gold, extra_lives, dps_overclock, coin_mult, cost_discount
    value: float
    duration_runs: int
    min_rarity: str
    preferred_units: Tuple[str, ...]
    min_star_override: int
    description: str


SACRIFICE_PERKS: Tuple[SacrificePerkDef, ...] = (
    SacrificePerkDef(
        key="monarch_slot",
        name="Monarch's Decree (+1 Slot)",
        perk_type="slot_bonus",
        value=1,
        duration_runs=3,
        min_rarity="transcendent",
        preferred_units=("monarch_core",),
        min_star_override=2,
        description="Sacrifice Monarch Core (or Lv2+★ Transcendent) -> +1 Loadout Slot for 3 runs (max +2)!",
    ),
    SacrificePerkDef(
        key="war_chest",
        name="Treasury Offering (+$150 Gold)",
        perk_type="start_gold",
        value=150,
        duration_runs=3,
        min_rarity="legendary",
        preferred_units=(),
        min_star_override=1,
        description="Sacrifice Legendary+ (or ★3+ Epic) -> +$150 Start Gold (+$225 Mythic+) for 3 runs!",
    ),
    SacrificePerkDef(
        key="titan_heart",
        name="Titan Bloodline (+12 Lives)",
        perk_type="extra_lives",
        value=12,
        duration_runs=3,
        min_rarity="epic",
        preferred_units=(),
        min_star_override=1,
        description="Sacrifice Epic+ -> +12 Max Base Lives (+18 Legendary+) for 3 runs!",
    ),
    SacrificePerkDef(
        key="chrono_overclock",
        name="Chrono Overclock (+20% DMG/15% SPD)",
        perk_type="dps_overclock",
        value=0.20,
        duration_runs=3,
        min_rarity="mythic",
        preferred_units=(),
        min_star_override=2,
        description="Sacrifice Mythic+ (or ★2+ Legendary) -> +20% DMG & +15% ATK SPD for 3 runs!",
    ),
    SacrificePerkDef(
        key="fortune_crown",
        name="Fortune Crown (+40% Coins)",
        perk_type="coin_mult",
        value=0.40,
        duration_runs=3,
        min_rarity="legendary",
        preferred_units=(),
        min_star_override=1,
        description="Sacrifice Legendary+ -> +40% Bonus Coin Rewards (+60% Mythic+) for 3 runs!",
    ),
    SacrificePerkDef(
        key="architect_seal",
        name="Architect Seal (-12% Gold Costs)",
        perk_type="cost_discount",
        value=0.12,
        duration_runs=3,
        min_rarity="epic",
        preferred_units=(),
        min_star_override=3,
        description="Sacrifice Epic+ (or ★3+ Rare) -> -12% Tower Build & Upgrade Costs for 3 runs!",
    ),
)

PERK_BY_KEY: Dict[str, SacrificePerkDef] = {p.key: p for p in SACRIFICE_PERKS}


def unit_qualifies_for_perk(perk: SacrificePerkDef, bp: TowerBlueprint, star_level: int) -> Tuple[bool, str]:
    if bp.key in perk.preferred_units:
        return True, ""
    r_idx = RARITY_ORDER.index(bp.rarity)
    req_idx = RARITY_ORDER.index(perk.min_rarity)
    if perk.key == "monarch_slot":
        if bp.rarity == "transcendent" and star_level >= perk.min_star_override:
            return True, ""
        return False, f"Requires Monarch Core or ★{perk.min_star_override}+ Transcendent unit."
    if r_idx >= req_idx:
        return True, ""
    # Allow 1 tier lower if upgraded to high Star rank
    if r_idx == req_idx - 1 and star_level >= max(2, perk.min_star_override):
        return True, ""
    return False, f"Requires {perk.min_rarity.title()}+ unit."

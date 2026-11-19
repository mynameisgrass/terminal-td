"""Gacha Unit Summoning (Multiple Banners, Pity, Auto-Sell) + In-Match Gold Tavern."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import TYPE_CHECKING, List, Optional, Tuple

from game.data.banners import BANNERS
from game.data.rarities import RARITIES, RARITY_ORDER
from game.data.towers import TOWER_BLUEPRINTS, TOWER_ORDER
from game.models import BannerDef
from game.profile import PlayerProfile

if TYPE_CHECKING:
    from game.engine import GameState


SLOT_SYMBOLS: Tuple[str, ...] = ("7", "*", "$", "A", "C", "X")
BET_AMOUNTS: Tuple[int, ...] = (25, 50, 100, 250)
CRATE_COST = 80


@dataclass
class SummonPull:
    key: str
    name: str
    rarity: str
    role: str
    is_new: bool
    auto_sold_coins: int = 0


@dataclass
class SummonBatchResult:
    ok: bool
    cost: int
    banner_name: str
    pulls: List[SummonPull]
    auto_sold_count: int
    auto_sold_coins: int
    message: str


def _weighted_unit_pool(banner: BannerDef, min_rarity: str = "common") -> List[Tuple[str, float]]:
    min_idx = RARITY_ORDER.index(min_rarity)
    allowed = set(RARITY_ORDER[min_idx:])
    featured = set(banner.featured_keys)

    by_rar: dict[str, List[str]] = {r: [] for r in allowed}
    for k in TOWER_ORDER:
        r = TOWER_BLUEPRINTS[k].rarity
        if r in allowed:
            by_rar[r].append(k)

    pool: List[Tuple[str, float]] = []
    for r, keys in by_rar.items():
        rw = banner.rarity_weights.get(r, 0.0)
        if rw <= 0 or not keys:
            continue
        raw_weights = [(banner.featured_boost if k in featured else 1.0) for k in keys]
        total_rw = sum(raw_weights)
        for k, w in zip(keys, raw_weights):
            pool.append((k, rw * (w / total_rw)))
    return pool


def _roll_one_unit(
    rng: random.Random, banner: BannerDef, min_rarity: str = "common"
) -> str:
    pool = _weighted_unit_pool(banner, min_rarity=min_rarity)
    if not pool:
        pool = _weighted_unit_pool(banner, min_rarity="common")
    keys = [p[0] for p in pool]
    weights = [p[1] for p in pool]
    return rng.choices(keys, weights=weights, k=1)[0]


def _execute_summon(
    profile: PlayerProfile,
    banner_key: str,
    count: int,
    rng: random.Random,
) -> SummonBatchResult:
    banner = BANNERS.get(banner_key, BANNERS["standard"])
    cost = banner.single_cost if count == 1 else banner.multi_cost
    if profile.coins < cost:
        return SummonBatchResult(
            False, 0, banner.name, [], 0, 0, f"Need {cost} Coins (have {profile.coins})."
        )

    profile.coins -= cost
    pulls: List[SummonPull] = []
    auto_sold_count = 0
    auto_sold_coins = 0

    for i in range(count):
        profile.pity_counter += 1
        if profile.pity_counter >= banner.pity_mythic_at:
            min_rar = "mythic"
        elif count >= 10 and i == count - 1:
            min_rar = banner.min_10x_rarity
        else:
            min_rar = "common"

        key = _roll_one_unit(rng, banner, min_rarity=min_rar)
        bp = TOWER_BLUEPRINTS[key]
        if bp.rarity in ("mythic", "transcendent"):
            profile.pity_counter = 0

        owned_before = profile.inventory.get(key, 0)
        is_new = owned_before == 0

        if profile.should_auto_sell(key, owned_before):
            sold_val = RARITIES[bp.rarity].sell_coins
            profile.coins += sold_val
            auto_sold_count += 1
            auto_sold_coins += sold_val
            pulls.append(
                SummonPull(
                    key=key,
                    name=bp.name,
                    rarity=bp.rarity,
                    role=bp.role,
                    is_new=False,
                    auto_sold_coins=sold_val,
                )
            )
        else:
            profile.add_unit(key, 1)
            pulls.append(
                SummonPull(
                    key=key,
                    name=bp.name,
                    rarity=bp.rarity,
                    role=bp.role,
                    is_new=is_new,
                    auto_sold_coins=0,
                )
            )

    profile.total_summons += count
    profile.save()

    best = max(pulls, key=lambda p: RARITY_ORDER.index(p.rarity))
    auto_note = f" | Auto-sold {auto_sold_count} (+{auto_sold_coins}c)" if auto_sold_count > 0 else ""
    msg = (
        f"{count}x on {banner.name}: Best {best.name} ({RARITIES[best.rarity].label})!{auto_note}"
    )
    return SummonBatchResult(
        True, cost, banner.name, pulls, auto_sold_count, auto_sold_coins, msg
    )


def summon_one(
    profile: PlayerProfile,
    banner_key: str = "standard",
    rng: Optional[random.Random] = None,
) -> SummonBatchResult:
    return _execute_summon(profile, banner_key, 1, rng or random.Random())


def summon_ten(
    profile: PlayerProfile,
    banner_key: str = "standard",
    rng: Optional[random.Random] = None,
) -> SummonBatchResult:
    return _execute_summon(profile, banner_key, 10, rng or random.Random())


# ================= In-Match Gold Tavern =================


@dataclass
class GambleResult:
    ok: bool
    net_gold: int
    headline: str
    detail: str
    reels: Optional[Tuple[str, str, str]] = None
    dice: Optional[Tuple[int, int]] = None


def play_slots(state: "GameState", bet: int, rng: Optional[random.Random] = None) -> GambleResult:
    r = rng or random
    if state.game_over:
        return GambleResult(False, 0, "Game Over", "Cannot gamble after defeat.")
    if bet <= 0 or state.gold < bet:
        return GambleResult(False, 0, "Not enough gold!", f"Need ${bet} (have ${state.gold}).")

    state.gold -= bet
    reels = (r.choice(SLOT_SYMBOLS), r.choice(SLOT_SYMBOLS), r.choice(SLOT_SYMBOLS))
    a, b, c = reels

    payout = 0
    if a == b == c == "7":
        payout = bet * 10
        headline = f"[{a}|{b}|{c}] TRIPLE 7 JACKPOT!"
    elif a == b == c:
        payout = bet * 4
        headline = f"[{a}|{b}|{c}] THREE OF A KIND!"
    elif reels.count("7") == 2:
        payout = bet * 2
        headline = f"[{a}|{b}|{c}] DOUBLE 7s!"
    elif a == b or b == c or a == c:
        payout = (bet * 7) // 5
        headline = f"[{a}|{b}|{c}] Nice Pair!"
    else:
        headline = f"[{a}|{b}|{c}] House wins."

    state.gold += payout
    net = payout - bet
    detail = f"Bet ${bet} -> Won ${payout} ({'+' if net >= 0 else ''}${net})"
    state.log(f"Slots: {headline} ({detail})")
    return GambleResult(True, net, headline, detail, reels=reels)


def play_dice(
    state: "GameState", bet: int, choice: str, rng: Optional[random.Random] = None
) -> GambleResult:
    r = rng or random
    if state.game_over:
        return GambleResult(False, 0, "Game Over", "Cannot gamble after defeat.")
    if choice not in ("low", "high", "seven"):
        return GambleResult(False, 0, "Invalid bet", "Choose low, high, or seven.")
    if bet <= 0 or state.gold < bet:
        return GambleResult(False, 0, "Not enough gold!", f"Need ${bet} (have ${state.gold}).")

    state.gold -= bet
    d1, d2 = r.randint(1, 6), r.randint(1, 6)
    total = d1 + d2

    payout = 0
    if choice == "low" and total <= 6:
        payout = bet * 2
    elif choice == "high" and total >= 8:
        payout = bet * 2
    elif choice == "seven" and total == 7:
        payout = (bet * 9) // 2

    state.gold += payout
    net = payout - bet
    win_txt = "WIN!" if payout > 0 else "MISS!"
    headline = f"Rolled [{d1}]+[{d2}] = {total} ({choice.upper()}) -> {win_txt}"
    detail = f"Bet ${bet} -> Won ${payout} ({'+' if net >= 0 else ''}${net})"
    state.log(f"Dice: {headline}")
    return GambleResult(True, net, headline, detail, dice=(d1, d2))


def play_crate(state: "GameState", rng: Optional[random.Random] = None) -> GambleResult:
    r = rng or random
    if state.game_over:
        return GambleResult(False, 0, "Game Over", "Cannot gamble after defeat.")
    if state.gold < CRATE_COST:
        return GambleResult(
            False, 0, "Not enough gold!", f"Crate costs ${CRATE_COST} (have ${state.gold})."
        )

    state.gold -= CRATE_COST
    roll = r.random()

    if roll < 0.15:
        payout = 200
        state.gold += payout
        net = payout - CRATE_COST
        res = GambleResult(True, net, "MEGA VAULT!", f"Found +${payout}! (Net +${net})")
    elif roll < 0.40:
        payout = 115
        state.gold += payout
        net = payout - CRATE_COST
        res = GambleResult(True, net, "Gold Stash!", f"Found +${payout}! (Net +${net})")
    elif roll < 0.60:
        upgradable = [t for t in state.towers.values() if t.can_upgrade]
        if upgradable:
            chosen = r.choice(upgradable)
            chosen.level += 1
            state.recompute_buffs()
            res = GambleResult(
                True,
                -CRATE_COST,
                "Field Forge!",
                f"Free upgrade: {chosen.blueprint.name} ({chosen.x},{chosen.y}) -> Lv{chosen.level}!",
            )
        else:
            payout = 110
            state.gold += payout
            net = payout - CRATE_COST
            res = GambleResult(True, net, "Forge Rebate!", f"No upgradable towers -> +${payout}!")
    elif roll < 0.85:
        payout = 45
        state.gold += payout
        net = payout - CRATE_COST
        res = GambleResult(True, net, "Scrap Metal", f"Salvaged ${payout} (Net -${abs(net)}).")
    else:
        res = GambleResult(True, -CRATE_COST, "MIMIC TRAP!", f"Lost ${CRATE_COST}!")

    state.log(f"Crate: {res.headline} {res.detail}")
    return res

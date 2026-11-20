"""Gacha rarity tiers, pull rates, and Coin economy constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


SINGLE_SUMMON_COST = 100
MULTI_SUMMON_COST = 900
STARTING_COINS = 500


@dataclass(frozen=True)
class RarityInfo:
    key: str
    label: str
    short: str
    weight: float
    sell_coins: int


RARITIES: Dict[str, RarityInfo] = {
    "common": RarityInfo("common", "Common", "C", weight=46.0, sell_coins=18),
    "rare": RarityInfo("rare", "Rare", "R", weight=28.0, sell_coins=40),
    "epic": RarityInfo("epic", "Epic", "E", weight=16.0, sell_coins=95),
    "legendary": RarityInfo("legendary", "Legendary", "L", weight=7.5, sell_coins=220),
    "mythic": RarityInfo("mythic", "Mythic", "M", weight=2.0, sell_coins=550),
    "transcendent": RarityInfo("transcendent", "Transcendent", "T", weight=0.5, sell_coins=1400),
}

RARITY_ORDER: Tuple[str, ...] = (
    "common",
    "rare",
    "epic",
    "legendary",
    "mythic",
    "transcendent",
)

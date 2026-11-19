"""Game data catalogs (banners, maps, towers, units, rarities, waves, difficulties)."""

from game.data.banners import BANNERS, BANNER_ORDER
from game.data.difficulties import DIFFICULTIES, DIFFICULTY_ORDER
from game.data.maps import MAPS
from game.data.rarities import (
    MULTI_SUMMON_COST,
    RARITIES,
    RARITY_ORDER,
    SINGLE_SUMMON_COST,
    STARTING_COINS,
)
from game.data.towers import STARTER_LOADOUT, TOWER_BLUEPRINTS, TOWER_ORDER
from game.data.units import ALLY_TEMPLATES, UNIT_ORDER, UNIT_TEMPLATES
from game.data.waves import WAVE_DEFINITIONS, build_wave_queue

__all__ = [
    "ALLY_TEMPLATES",
    "BANNERS",
    "BANNER_ORDER",
    "DIFFICULTIES",
    "DIFFICULTY_ORDER",
    "MAPS",
    "MULTI_SUMMON_COST",
    "RARITIES",
    "RARITY_ORDER",
    "SINGLE_SUMMON_COST",
    "STARTER_LOADOUT",
    "STARTING_COINS",
    "TOWER_BLUEPRINTS",
    "TOWER_ORDER",
    "UNIT_ORDER",
    "UNIT_TEMPLATES",
    "WAVE_DEFINITIONS",
    "build_wave_queue",
]

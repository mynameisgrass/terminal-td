"""Wave definitions (30 curated campaign waves + Endless scaling)."""

from __future__ import annotations

from typing import List, Tuple

from game.models import SpawnEntry


WAVE_DEFINITIONS: Tuple[Tuple[Tuple[str, int, float], ...], ...] = (
    # 1-5
    (("goblin", 8, 0.85),),
    (("rat", 12, 0.42), ("mite", 8, 0.35), ("goblin", 6, 0.70)),
    (("kobold", 8, 0.58), ("slime", 5, 0.95), ("bat", 6, 0.52)),
    (("skeleton", 10, 0.48), ("imp", 7, 0.52), ("wolf", 6, 0.45), ("sapper", 4, 0.65)),
    (("goblin", 10, 0.42), ("orc", 6, 0.75), ("boss_warlord", 1, 1.50)),

    # 6-10
    (("bandit", 9, 0.52), ("gnoll", 8, 0.68), ("zombie", 5, 0.95)),
    (("spider", 12, 0.45), ("cultist", 5, 0.90), ("harpy", 8, 0.48), ("shadow_hound", 5, 0.50)),
    (("brute", 6, 1.05), ("orc", 12, 0.50), ("fallen", 5, 0.85), ("plague_bearer", 4, 0.95)),
    (("knight", 5, 1.00), ("zombie", 8, 0.70), ("assassin", 7, 0.50)),
    (("spider", 14, 0.38), ("cultist", 5, 0.80), ("boss_brood", 1, 1.60)),

    # 11-15
    (("golem", 5, 1.25), ("shaman", 5, 0.85), ("berserker", 8, 0.60)),
    (("mage", 9, 0.58), ("wyvern", 9, 0.52), ("blood_mage", 4, 0.85)),
    (("tank", 6, 1.10), ("assassin", 12, 0.40), ("steel_golem", 4, 1.15)),
    (("fallen", 10, 0.55), ("brute", 8, 0.80), ("boss_warden", 1, 1.80)),
    (("knight", 10, 0.55), ("tank", 5, 0.95), ("boss_titan", 1, 1.80)),

    # 16-20
    (("paladin", 6, 0.90), ("demon", 8, 0.60), ("steel_golem", 5, 1.05)),
    (("vampire", 10, 0.50), ("hydra", 5, 1.10), ("lich", 4, 1.00)),
    (("colossus", 6, 1.20), ("dragonling", 10, 0.52), ("void_stalker", 7, 0.55)),
    (("behemoth", 6, 1.15), ("paladin", 9, 0.65), ("chrono_knight", 5, 0.85)),
    (("skeleton", 18, 0.25), ("vampire", 8, 0.55), ("boss_necromancer", 1, 2.00)),

    # 21-25
    (("hydra", 7, 0.95), ("colossus", 6, 1.05), ("boss_dragon", 1, 1.80)),
    (("assassin", 18, 0.30), ("void_stalker", 12, 0.40), ("behemoth", 7, 0.95)),
    (("paladin", 10, 0.55), ("blood_mage", 7, 0.70), ("boss_colossus", 1, 2.00)),
    (("colossus", 8, 0.95), ("chrono_knight", 8, 0.70), ("demon", 14, 0.40), ("boss_dragon", 1, 2.00)),
    (("knight", 12, 0.40), ("behemoth", 6, 0.90), ("boss_colossus", 1, 2.20), ("boss_void", 1, 3.00)),

    # 26-30: Transcendent Endgame
    (("chrono_knight", 10, 0.55), ("void_stalker", 14, 0.35), ("hydra", 8, 0.85)),
    (("behemoth", 10, 0.85), ("colossus", 10, 0.85), ("lich", 8, 0.70)),
    (("chrono_knight", 12, 0.45), ("dragonling", 14, 0.38), ("boss_chronos", 1, 2.20)),
    (("boss_dragon", 2, 2.50), ("boss_void", 1, 3.00), ("behemoth", 10, 0.70)),
    (("chrono_knight", 14, 0.40), ("boss_chronos", 1, 2.40), ("boss_omega", 1, 3.20)),
)


def build_wave_queue(wave_num: int) -> List[SpawnEntry]:
    entries: List[SpawnEntry] = []
    if wave_num <= len(WAVE_DEFINITIONS):
        groups = WAVE_DEFINITIONS[wave_num - 1]
        for kind, count, interval in groups:
            for i in range(count):
                delay = 0.2 if (not entries and i == 0) else interval
                entries.append(SpawnEntry(kind=kind, delay=delay, hp_scale=1.0))
        return entries

    extra = wave_num - len(WAVE_DEFINITIONS)
    # Smooth playable endless scaling without exploding entity counts or billion-HP stalls
    hp_scale = (1.14 ** min(extra, 15)) * (1.0 + max(0, extra - 15) * 0.35)
    c_scale = min(extra, 18)
    groups: Tuple[Tuple[str, int, float], ...] = (
        ("void_stalker", 12 + c_scale, 0.28),
        ("chrono_knight", 10 + (c_scale * 2) // 3, 0.38),
        ("colossus", 6 + c_scale // 2, 0.65),
        ("behemoth", 5 + c_scale // 2, 0.75),
        ("boss_chronos" if extra % 2 == 1 else "boss_omega", min(5, 1 + extra // 5), 2.00),
    )
    for kind, count, interval in groups:
        for i in range(count):
            delay = 0.2 if (not entries and i == 0) else interval
            entries.append(SpawnEntry(kind=kind, delay=delay, hp_scale=hp_scale))
    return entries

"""Difficulty presets balanced so Hard & Nightmare truly demand strategy & strong loadouts."""

from __future__ import annotations

from typing import Dict, Tuple

from game.models import DifficultyConfig


DIFFICULTIES: Dict[str, DifficultyConfig] = {
    "easy": DifficultyConfig(
        key="easy",
        name="Easy",
        description="Forgiving HP/speed, manual start, 1.0x Coin rewards",
        starting_gold=230,
        starting_lives=25,
        enemy_hp_mult=0.90,
        enemy_speed_mult=0.95,
        reward_mult=1.10,
        coin_mult=1.0,
        extra_leak_damage=0,
        boss_cd_mult=1.15,
        auto_wave_delay=None,
        pause_in_gamble=True,
    ),
    "normal": DifficultyConfig(
        key="normal",
        name="Normal",
        description="Solid challenge, 20s timer, 1.3x Coin rewards",
        starting_gold=175,
        starting_lives=20,
        enemy_hp_mult=1.25,
        enemy_speed_mult=1.05,
        reward_mult=1.00,
        coin_mult=1.3,
        extra_leak_damage=0,
        boss_cd_mult=1.0,
        auto_wave_delay=20.0,
        pause_in_gamble=True,
    ),
    "hard": DifficultyConfig(
        key="hard",
        name="Hard",
        description="1.85x HP, faster mobs, 12s force-start, 1.8x Coins",
        starting_gold=150,
        starting_lives=15,
        enemy_hp_mult=1.85,
        enemy_speed_mult=1.18,
        reward_mult=0.95,
        coin_mult=1.8,
        extra_leak_damage=0,
        boss_cd_mult=0.85,
        auto_wave_delay=12.0,
        pause_in_gamble=False,
    ),
    "nightmare": DifficultyConfig(
        key="nightmare",
        name="Nightmare",
        description="BRUTAL: 2.8x HP, 1.32x spd, +1 leak dmg, 7s timer, 2.6x Coins!",
        starting_gold=140,
        starting_lives=10,
        enemy_hp_mult=2.80,
        enemy_speed_mult=1.32,
        reward_mult=0.90,
        coin_mult=2.6,
        extra_leak_damage=1,
        boss_cd_mult=0.72,
        auto_wave_delay=7.0,
        pause_in_gamble=False,
    ),
}

DIFFICULTY_ORDER: Tuple[str, ...] = ("easy", "normal", "hard", "nightmare")

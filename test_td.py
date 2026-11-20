"""Comprehensive tests for Terminal Tower Defense (Banners, Auto-Sell, 5x/10x, Auto-Start, Prestart, PTY)."""

from __future__ import annotations

import fcntl
import os
import pty
import random
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.data.banners import BANNERS, BANNER_ORDER  # noqa: E402
from game.data.difficulties import DIFFICULTIES  # noqa: E402
from game.data.maps import MAPS  # noqa: E402
from game.data.rarities import RARITIES, RARITY_ORDER  # noqa: E402
from game.data.towers import STARTER_LOADOUT, TOWER_BLUEPRINTS, TOWER_ORDER  # noqa: E402
from game.data.units import ALLY_TEMPLATES, UNIT_ORDER, UNIT_TEMPLATES  # noqa: E402
from game.data.waves import WAVE_DEFINITIONS, build_wave_queue  # noqa: E402
from game.engine import GameState  # noqa: E402
from game.gambling import summon_one, summon_ten  # noqa: E402
from game.models import GRID_HEIGHT, GRID_WIDTH, MAX_LOADOUT  # noqa: E402
from game.profile import PlayerProfile  # noqa: E402


class TestCatalogs(unittest.TestCase):
    def test_unit_and_tower_counts(self) -> None:
        self.assertEqual(len(UNIT_ORDER), 52)
        self.assertEqual(len(UNIT_ORDER), len(UNIT_TEMPLATES))
        bosses = [u for u in UNIT_TEMPLATES.values() if u.is_boss]
        self.assertEqual(len(bosses), 10)
        self.assertEqual(len(TOWER_ORDER), 48)
        self.assertEqual(len(ALLY_TEMPLATES), 11)
        self.assertEqual(len(WAVE_DEFINITIONS), 30)
        self.assertEqual(len(BANNER_ORDER), 4)
        for k in TOWER_ORDER:
            self.assertEqual(len(TOWER_BLUEPRINTS[k].levels), 5)

    def test_all_52_units_reachable_in_campaign(self) -> None:
        seen = set()
        for w in range(1, len(WAVE_DEFINITIONS) + 1):
            for entry in build_wave_queue(w):
                seen.add(entry.kind)
        changed = True
        while changed:
            changed = False
            for kind in list(seen):
                tpl = UNIT_TEMPLATES[kind]
                if tpl.split_into and tpl.split_into not in seen:
                    seen.add(tpl.split_into)
                    changed = True
                if tpl.boss_ability == "spawn_spiders" and "spider" not in seen:
                    seen.add("spider")
                    changed = True
                if tpl.boss_ability == "necromancy" and "skeleton" not in seen:
                    seen.add("skeleton")
                    changed = True
                if tpl.boss_ability == "void" and "assassin" not in seen:
                    seen.add("assassin")
                    changed = True
        self.assertEqual(seen, set(UNIT_ORDER))

    def test_big_36x18_wide_road_maps(self) -> None:
        self.assertEqual(GRID_WIDTH, 36)
        self.assertEqual(GRID_HEIGHT, 18)
        self.assertEqual(len(MAPS), 5)
        for m in MAPS:
            meta_path, centerline, road_set, spawn_cells, base_cells = m.build_geometry()
            self.assertGreaterEqual(len(meta_path), 24)
            self.assertEqual(len(road_set), len(meta_path) * 4)
            self.assertEqual(len(spawn_cells), 4)
            self.assertEqual(len(base_cells), 4)
            for x, y in road_set:
                self.assertTrue(0 <= x < GRID_WIDTH)
                self.assertTrue(0 <= y < GRID_HEIGHT)


class TestBannersAutoSellAndLoadout(unittest.TestCase):
    def test_banners_auto_sell_pity_and_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            save_path = os.path.join(tmp, "save.json")
            prof = PlayerProfile.new_default(save_path=save_path)
            self.assertEqual(prof.coins, 1000)
            self.assertEqual(len(prof.loadout), len(STARTER_LOADOUT))

            # Enable auto-sell for all Commons & Rares
            prof.auto_sell_mode = "all_cr"
            rng = random.Random(42)
            res = summon_ten(prof, banner_key="warfare", rng=rng)
            # 1000 coins < 1125 warfare 10x -> should reject cleanly
            self.assertFalse(res.ok)

            prof.coins = 5000
            res = summon_ten(prof, banner_key="warfare", rng=rng)
            self.assertTrue(res.ok)
            self.assertEqual(len(res.pulls), 10)
            # 10th pull must be Epic+
            self.assertGreaterEqual(
                RARITY_ORDER.index(res.pulls[9].rarity), RARITY_ORDER.index("epic")
            )
            # Any common/rare pulls must have auto-sold for coins!
            cr_pulls = [p for p in res.pulls if p.rarity in ("common", "rare")]
            self.assertEqual(res.auto_sold_count, len(cr_pulls))
            self.assertEqual(
                res.auto_sold_coins,
                sum(RARITIES[p.rarity].sell_coins for p in cr_pulls),
            )

            # Mythic Rush banner has 0% commons & guarantees Legendary+ on 10x
            res_mr = summon_ten(prof, banner_key="mythic_rush", rng=rng)
            self.assertTrue(res_mr.ok)
            self.assertTrue(all(p.rarity != "common" for p in res_mr.pulls))
            self.assertGreaterEqual(
                RARITY_ORDER.index(res_mr.pulls[9].rarity), RARITY_ORDER.index("legendary")
            )

            # Pity triggers Mythic+ when reaching banner.pity_mythic_at
            prof.pity_counter = BANNERS["standard"].pity_mythic_at - 1
            r_pity = summon_one(prof, banner_key="standard", rng=rng)
            self.assertTrue(r_pity.ok)
            self.assertIn(r_pity.pulls[0].rarity, ("mythic", "transcendent"))
            self.assertEqual(prof.pity_counter, 0)

            self.assertLessEqual(len(prof.loadout), MAX_LOADOUT)
            reloaded = PlayerProfile.load(save_path=save_path)
            self.assertEqual(reloaded.auto_sell_mode, "all_cr")
            self.assertEqual(reloaded.coins, prof.coins)


class TestSpeedAutoStartPrestartAndUnits(unittest.TestCase):
    def test_speed_5x_10x_and_auto_start_and_prestart(self) -> None:
        state = GameState(
            map_index=0,
            difficulty_key="easy",
            loadout=["scout", "farm", "executioner", "medic_camp", "eternal_phoenix"],
        )
        # Speed cycle: 1 -> 2 -> 3 -> 5 -> 10 -> 1
        self.assertEqual(state.speed_mult, 1)
        self.assertEqual(state.cycle_speed(), 2)
        self.assertEqual(state.cycle_speed(), 3)
        self.assertEqual(state.cycle_speed(), 5)
        self.assertEqual(state.cycle_speed(), 10)
        self.assertEqual(state.cycle_speed(), 1)

        # Auto-start Wave 1 automatically
        self.assertTrue(state.toggle_auto_start())
        state.tick(0.3)
        self.assertTrue(state.wave_active)
        self.assertEqual(state.wave, 1)

        # Prestart Wave 2 during active Wave 1 after cooldown expires
        state.tick(1.6)
        gold_before = state.gold
        self.assertTrue(state.start_next_wave())
        self.assertEqual(state.wave, 2)
        self.assertGreater(state.gold, gold_before)

    def test_eternal_phoenix_3_lives_medic_heal_and_executioner(self) -> None:
        state = GameState(
            map_index=0,
            difficulty_key="normal",
            loadout=["eternal_phoenix", "medic_camp", "executioner"],
        )
        state.gold = 5000
        self.assertTrue(state.build_tower(3, 2, "eternal_phoenix"))
        self.assertTrue(state.build_tower(2, 2, "medic_camp"))
        self.assertTrue(state.build_tower(1, 2, "executioner"))

        # Test Eternal Phoenix 3 Second Lives
        ep_tower = state.towers[(3, 2)]
        ally = state._spawn_ally(ep_tower, "immortal_phoenix")
        assert ally is not None
        self.assertEqual(ally.revives_left, 3)

        ally.progress = 20.0
        enemy = state._spawn_enemy("knight", progress=20.0)
        ally.hp = 1.0
        state.wave_active = True
        state.tick(0.2)
        self.assertEqual(ally.revives_left, 2)
        self.assertGreater(ally.hp, 100.0)

        # Test Executioner missing-HP bonus damage
        boss = state._spawn_enemy("boss_warlord", progress=5.0)
        boss.hp = boss.max_hp * 0.2
        hp_before = boss.hp
        state._apply_damage(boss, 50.0, state.towers[(1, 2)], armor_pierce=1.0, execute_pct=0.15)
        self.assertGreater(hp_before - boss.hp, 100.0)

    def test_5_level_upgrades(self) -> None:
        state = GameState(map_index=0, difficulty_key="easy", loadout=["scout"])
        state.gold = 5000
        self.assertTrue(state.build_tower(2, 2, "scout"))
        for expected_lv in (2, 3, 4, 5):
            self.assertTrue(state.upgrade_tower(2, 2))
            self.assertEqual(state.towers[(2, 2)].level, expected_lv)
        self.assertFalse(state.upgrade_tower(2, 2))

    def test_high_tier_low_cost_high_dmg_units(self) -> None:
        cheap_high = [
            "shadow_blade",
            "crimson_mage",
            "longbow_master",
            "eclipse_reaper",
            "star_striker",
            "astral_lance",
        ]
        for k in cheap_high:
            bp = TOWER_BLUEPRINTS[k]
            lv1 = bp.levels[0]
            self.assertIn(bp.rarity, ("epic", "legendary", "mythic", "transcendent"))
            self.assertLessEqual(lv1.cost, 150)
            self.assertGreaterEqual(lv1.damage, 45)
            # Balanced: single-target only (no splash, no chain)
            self.assertEqual(lv1.splash_radius, 0.0)
            self.assertEqual(lv1.chain_count, 0)

        # Verify can be built right on Wave 1 in Hard mode ($150 starting gold!)
        state = GameState(map_index=0, difficulty_key="hard", loadout=cheap_high)
        self.assertEqual(state.gold, 150)
        self.assertTrue(state.build_tower(2, 2, "astral_lance"))
        self.assertEqual(state.gold, 0)
        enemy = state._spawn_enemy("knight", progress=2.0)  # 12 armor
        state.wave_active = True
        state.tick(0.1)
        # Astral Lance deals 190 piercing damage & shreds 6 armor
        self.assertLess(enemy.hp, enemy.max_hp - 150)
        self.assertLess(enemy.armor_current, 12.0)

    def test_mass_build_and_mass_upgrade_rect(self) -> None:
        state = GameState(map_index=0, difficulty_key="easy", loadout=["scout"])
        state.gold = 225  # 4 scouts ($200) + $25 left
        # (1,2)..(3,3) has 6 buildable plots on Grand Serpentine; budget allows 4
        built = state.mass_build_rect(1, 2, 3, 3, "scout")
        self.assertEqual(built, 4)
        self.assertEqual(state.gold, 25)
        self.assertEqual(len(state.towers), 4)

        # Give gold for 2 upgrades ($55 each = $110)
        state.gold = 120
        upgraded = state.mass_upgrade_rect(1, 2, 3, 3)
        self.assertEqual(upgraded, 2)
        self.assertEqual(state.gold, 10)
        levels = sorted(t.level for t in state.towers.values())
        self.assertEqual(levels, [1, 1, 2, 2])


class TestFullScreenPTY(unittest.TestCase):
    def _run_pty(self, rows: int, cols: int, keys: bytes) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            master_fd, slave_fd = pty.openpty()
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

            td_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "td.py")
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["TD_SAVE_PATH"] = os.path.join(tmp, "test_save.json")

            proc = subprocess.Popen(
                [sys.executable, td_path],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                close_fds=True,
            )
            os.close(slave_fd)

            buf = bytearray()

            def drain(dur: float) -> None:
                end = time.monotonic() + dur
                while time.monotonic() < end:
                    r, _, _ = select.select([master_fd], [], [], 0.04)
                    if r:
                        try:
                            chunk = os.read(master_fd, 65536)
                            if not chunk:
                                break
                            buf.extend(chunk)
                        except OSError:
                            break

            try:
                drain(0.25)
                for ch in keys.split(b"|"):
                    os.write(master_fd, ch)
                    drain(0.16)
                proc.wait(timeout=4.0)
                drain(0.1)
            finally:
                os.close(master_fd)
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

            self.assertEqual(proc.returncode, 0)
            return buf.decode("utf-8", errors="ignore")

    def test_fullscreen_160x45_banners_autosell_speed10x_autostart_prestart(self) -> None:
        # Gacha (g) -> switch banner (\t) -> toggle auto-sell (a) -> 1x summon (1) -> back (g) -> start (\n) -> mass-place box (z|dd| ) -> paint brush (c|s|c) -> speed 10x (ffff) -> auto-start (v) -> wait/prestart (n) -> quit (q)
        out = self._run_pty(45, 160, b"g|\t|a|1|g|\n|z|dd| |c|s|c|ffff|v|n|q")
        self.assertIn("Warfare & Boss-Killer", out)
        self.assertIn("Auto-Sell: Dupes: Common", out)
        self.assertIn("MASS-PLACE", out)
        self.assertIn("PAINT:ON", out)
        self.assertIn("10x", out)
        self.assertIn("AUTO:ON", out)

    def test_compact_80x24_camera_battle(self) -> None:
        out = self._run_pty(24, 80, b"\n|ddd |n|q")
        self.assertIn("CAMPAIGN SETUP", out)
        self.assertIn("LOADOUT [1-8] & INSPECTOR", out)


if __name__ == "__main__":
    unittest.main()

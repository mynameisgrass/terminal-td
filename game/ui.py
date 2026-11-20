"""Full-screen adaptive Curses UI: Lobby, Unit Gacha, 8-Slot Inventory, Battle, Boss HP Bars."""

from __future__ import annotations

import curses
import math
import time
from typing import Dict, List, Optional, Tuple

from game.data.banners import BANNERS, BANNER_ORDER
from game.data.difficulties import DIFFICULTIES, DIFFICULTY_ORDER
from game.data.maps import MAPS
from game.data.progression import (
    FUSION_RECIPES,
    SACRIFICE_PERKS,
    star_upgrade_coin_cost,
    unit_qualifies_for_perk,
)
from game.data.rarities import RARITIES, RARITY_ORDER
from game.data.towers import TOWER_BLUEPRINTS, TOWER_ORDER
from game.data.units import ALLY_TEMPLATES, UNIT_ORDER, UNIT_TEMPLATES
from game.engine import GameState
from game.gambling import (
    BET_AMOUNTS,
    CRATE_COST,
    GambleResult,
    SummonBatchResult,
    play_crate,
    play_dice,
    play_slots,
    summon_one,
    summon_ten,
)
from game.models import MAX_LOADOUT, MAX_UNIT_STAR, AllyUnit, Enemy, Tower
from game.profile import AUTO_SELL_LABELS, PlayerProfile


MIN_COLS = 78
MIN_ROWS = 22

# Color pair IDs
CP_DEFAULT = 1
CP_PATH = 2
CP_SPAWN = 3
CP_BASE = 4
CP_COMMON = 5
CP_RARE = 6
CP_EPIC = 7
CP_LEGENDARY = 8
CP_MYTHIC = 9
CP_TRANSCENDENT = 22
CP_ENEMY = 10
CP_ENEMY_SLOW = 11
CP_ENEMY_POISON = 12
CP_ENEMY_HIT = 13
CP_BOSS = 14
CP_ALLY = 15
CP_HUD = 16
CP_RANGE = 17
CP_DIM = 18
CP_GOOD = 19
CP_WARN = 20
CP_GOLD = 21


def init_colors() -> bool:
    if not curses.has_colors():
        return False
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK

    curses.init_pair(CP_DEFAULT, curses.COLOR_WHITE, bg)
    curses.init_pair(CP_PATH, curses.COLOR_YELLOW, bg)
    curses.init_pair(CP_SPAWN, curses.COLOR_MAGENTA, bg)
    curses.init_pair(CP_BASE, curses.COLOR_GREEN, bg)

    curses.init_pair(CP_COMMON, curses.COLOR_WHITE, bg)
    curses.init_pair(CP_RARE, curses.COLOR_CYAN, bg)
    curses.init_pair(CP_EPIC, curses.COLOR_MAGENTA, bg)
    curses.init_pair(CP_LEGENDARY, curses.COLOR_YELLOW, bg)
    curses.init_pair(CP_MYTHIC, curses.COLOR_RED, bg)
    curses.init_pair(CP_TRANSCENDENT, curses.COLOR_CYAN, curses.COLOR_BLUE)

    curses.init_pair(CP_ENEMY, curses.COLOR_RED, bg)
    curses.init_pair(CP_ENEMY_SLOW, curses.COLOR_CYAN, bg)
    curses.init_pair(CP_ENEMY_POISON, curses.COLOR_GREEN, bg)
    curses.init_pair(CP_ENEMY_HIT, curses.COLOR_WHITE, curses.COLOR_RED)
    curses.init_pair(CP_BOSS, curses.COLOR_YELLOW, curses.COLOR_RED)
    curses.init_pair(CP_ALLY, curses.COLOR_CYAN, bg)
    curses.init_pair(CP_HUD, curses.COLOR_CYAN, bg)
    curses.init_pair(CP_RANGE, curses.COLOR_BLUE, bg)
    curses.init_pair(CP_DIM, curses.COLOR_WHITE, bg)
    curses.init_pair(CP_GOOD, curses.COLOR_GREEN, bg)
    curses.init_pair(CP_WARN, curses.COLOR_YELLOW, bg)
    curses.init_pair(CP_GOLD, curses.COLOR_YELLOW, bg)
    return True


def rarity_cp(rarity: str) -> int:
    return {
        "common": CP_COMMON,
        "rare": CP_RARE,
        "epic": CP_EPIC,
        "legendary": CP_LEGENDARY,
        "mythic": CP_MYTHIC,
        "transcendent": CP_TRANSCENDENT,
    }.get(rarity, CP_DEFAULT)


def safe_addstr(
    win: curses.window,
    y: int,
    x: int,
    text: str,
    attr: int = 0,
    bounds: Optional[Tuple[int, int]] = None,
) -> None:
    max_y, max_x = bounds if bounds is not None else win.getmaxyx()
    if y < 0 or y >= max_y or x >= max_x:
        return
    if x < 0:
        text = text[-x:]
        x = 0
    avail = max_x - x
    if avail <= 0 or not text:
        return
    if y == max_y - 1 and x + len(text) >= max_x:
        text = text[: max(0, avail - 1)]
    else:
        text = text[:avail]
    if not text:
        return
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def draw_box(win: curses.window, y: int, x: int, h: int, w: int, title: str = "", attr: int = 0) -> None:
    if h < 2 or w < 2:
        return
    horiz = "-" * max(0, w - 2)
    safe_addstr(win, y, x, f"+{horiz}+", attr)
    for row in range(1, h - 1):
        safe_addstr(win, y + row, x, "|", attr)
        safe_addstr(win, y + row, x + w - 1, "|", attr)
    safe_addstr(win, y + h - 1, x, f"+{horiz}+", attr)
    if title and w > 6:
        t = f" {title[: w - 6]} "
        safe_addstr(win, y, x + 2, t, attr | curses.A_BOLD)


def clear_rect(win: curses.window, y: int, x: int, h: int, w: int, attr: int = 0) -> None:
    blank = " " * max(0, w)
    for r in range(h):
        safe_addstr(win, y + r, x, blank, attr)


def render_hp_bar(hp: float, max_hp: float, width: int = 16) -> str:
    if max_hp <= 0:
        return "[" + ("." * width) + "]"
    ratio = max(0.0, min(1.0, hp / max_hp))
    filled = int(round(ratio * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def micro_hp_char(hp: float, max_hp: float) -> str:
    ratio = hp / max_hp if max_hp > 0 else 0.0
    if ratio > 0.75:
        return "#"
    if ratio > 0.50:
        return "+"
    if ratio > 0.25:
        return "-"
    return "."


def get_range_cells(state: GameState) -> set[Tuple[int, int]]:
    cx, cy = state.cursor_x, state.cursor_y
    tower = state.towers.get((cx, cy))
    if tower is not None:
        r = tower.effective_range
        min_r = tower.stats.min_range
    elif state.can_build_at(cx, cy) and state.selected_tower_kind in TOWER_BLUEPRINTS:
        st = TOWER_BLUEPRINTS[state.selected_tower_kind].levels[0]
        r = st.range
        min_r = st.min_range
    else:
        return set()

    cells: set[Tuple[int, int]] = set()
    for y in range(state.height):
        for x in range(state.width):
            d = math.hypot(x - cx, y - cy)
            if min_r <= d <= r:
                cells.add((x, y))
    return cells


class UIState:
    def __init__(self) -> None:
        self.mode: str = "setup"  # setup, gacha, inventory, forge, play, tavern, bestiary
        self.return_mode: str = "setup"
        self.setup_diff_idx: int = 1  # Normal
        self.setup_map_idx: int = 0
        self.banner_idx: int = 0
        self.inv_cursor: int = 0
        self.inv_scroll: int = 0
        self.inv_msg: str = ""
        self.forge_tab: int = 0  # 0=Fusion, 1=Sacrifice Altar
        self.forge_fusion_idx: int = 0
        self.forge_perk_idx: int = 0
        self.forge_unit_idx: int = 0
        self.forge_msg: str = ""
        self.gacha_result: Optional[SummonBatchResult] = None
        self.bet_idx: int = 1
        self.tavern_result: Optional[GambleResult] = None
        self.bestiary_scroll: int = 0
        self.cam_x: int = 0
        self.cam_y: int = 0
        self.mass_anchor: Optional[Tuple[int, int]] = None
        self.paint_mode: bool = False


# ================= FULL-SCREEN SETUP / LOBBY =================


def render_setup(stdscr: curses.window, profile: PlayerProfile, ui: UIState, has_colors: bool) -> None:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    def cp(pair_id: int, extra: int = 0) -> int:
        return (curses.color_pair(pair_id) if has_colors else 0) | extra

    if max_y < MIN_ROWS or max_x < MIN_COLS:
        msg = f"Terminal too small ({max_x}x{max_y}). Need at least {MIN_COLS}x{MIN_ROWS}."
        safe_addstr(stdscr, max_y // 2, max(0, (max_x - len(msg)) // 2), msg, curses.A_BOLD)
        stdscr.refresh()
        return

    # Full-screen top banner
    title = (
        f" TERMINAL TOWER DEFENSE | Coins: {profile.coins} | Owned Units: {profile.owned_total()}"
        f" | Wins: {profile.total_wins} | Best Wave: {profile.best_wave}"
    )
    safe_addstr(stdscr, 0, 0, title.ljust(max_x)[:max_x], cp(CP_HUD, curses.A_BOLD))

    left_w = max(44, (max_x * 58) // 100)
    right_w = max_x - left_w - 1
    body_h = max_y - 3

    # Left: Campaign Setup
    draw_box(stdscr, 1, 0, body_h, left_w, "CAMPAIGN SETUP (36x18 WIDE-ROAD MAPS)", cp(CP_HUD, curses.A_BOLD))
    lx = 2
    lw = left_w - 4

    safe_addstr(stdscr, 3, lx, "DIFFICULTY [Up/Down or 1-4]:", cp(CP_GOLD, curses.A_BOLD))
    for idx, dkey in enumerate(DIFFICULTY_ORDER):
        d = DIFFICULTIES[dkey]
        sel = idx == ui.setup_diff_idx
        mark = ">>" if sel else "  "
        timer = f"{int(d.auto_wave_delay)}s timer" if d.auto_wave_delay else "Manual"
        line = (
            f"{mark}[{idx + 1}] {d.name:<9} ${d.starting_gold:<3} {d.starting_lives:<2}HP"
            f" {d.enemy_hp_mult:.2f}xHP {timer:<9} ({d.coin_mult:.1f}xCoins)"
        )
        attr = cp(CP_GOOD if sel else CP_DEFAULT, curses.A_BOLD if sel else 0)
        if sel:
            attr |= curses.A_REVERSE
        safe_addstr(stdscr, 4 + idx, lx, line[:lw], attr)

    sel_diff = DIFFICULTIES[DIFFICULTY_ORDER[ui.setup_diff_idx]]
    safe_addstr(stdscr, 9, lx, f"Info: {sel_diff.description}"[:lw], cp(CP_DIM))

    safe_addstr(stdscr, 11, lx, "MAP [Left/Right or M]:", cp(CP_GOLD, curses.A_BOLD))
    m = MAPS[ui.setup_map_idx]
    safe_addstr(
        stdscr,
        12,
        lx + 2,
        f"< {ui.setup_map_idx + 1}/{len(MAPS)}: {m.name} >",
        cp(CP_WARN, curses.A_BOLD),
    )
    safe_addstr(stdscr, 13, lx + 2, m.description[: lw - 2], cp(CP_DEFAULT))

    safe_addstr(stdscr, 15, lx, "MENU SHORTCUTS:", cp(CP_HUD, curses.A_BOLD))
    safe_addstr(stdscr, 16, lx + 2, "[Enter / Space]  START BATTLE", cp(CP_GOOD, curses.A_BOLD))
    safe_addstr(stdscr, 17, lx + 2, "[G]              UNIT SUMMON GACHA (Gamble Coins for Units!)", cp(CP_GOLD, curses.A_BOLD))
    safe_addstr(stdscr, 18, lx + 2, "[I]              INVENTORY, STAR-UP & LOADOUT (Equip / Sell / ★1-5)", cp(CP_HUD, curses.A_BOLD))
    safe_addstr(stdscr, 19, lx + 2, "[F]              FUSION & SACRIFICE ALTAR (Craft Monarchs & Perks!)", cp(CP_WARN, curses.A_BOLD))
    safe_addstr(stdscr, 20, lx + 2, f"[B]              BESTIARY (52 Enemies, 10 Bosses, {len(ALLY_TEMPLATES)} Allies)", cp(CP_DEFAULT))
    safe_addstr(stdscr, 21, lx + 2, "[Q]              Quit", cp(CP_DIM))

    if profile.active_perks and body_h >= 24:
        p_txt = "ALTAR PERKS: " + " | ".join(
            f"{p['name']} ({p['runs_left']}r)" for p in profile.active_perks
        )
        safe_addstr(stdscr, 23, lx, p_txt[:lw], cp(CP_GOLD, curses.A_BOLD))

    # Right: Current Dynamic Loadout (8..10 slots with Monarch Perk)
    eff_slots = profile.effective_max_loadout()
    rx = left_w + 1
    draw_box(stdscr, 1, rx, body_h, right_w, f"EQUIPPED LOADOUT ({len(profile.loadout)}/{eff_slots})", cp(CP_GOLD, curses.A_BOLD))
    ix = rx + 2
    iw = right_w - 4
    compact_rows = body_h < 22 or eff_slots > 8
    for slot in range(eff_slots):
        row_y = 3 + slot if compact_rows else 3 + slot * 2
        if row_y >= body_h:
            break
        key_lbl = "0" if slot == 9 else str(slot + 1)
        if slot < len(profile.loadout):
            ukey = profile.loadout[slot]
            bp = TOWER_BLUEPRINTS[ukey]
            rinfo = RARITIES[bp.rarity]
            cnt = profile.inventory.get(ukey, 1)
            star = profile.star_of(ukey)
            line = f"[{key_lbl}] {bp.symbol} {bp.name:<12} ★{star} [{rinfo.short}] ${bp.levels[0].cost:<3} ({bp.role})"
            safe_addstr(stdscr, row_y, ix, line[:iw], cp(rarity_cp(bp.rarity), curses.A_BOLD))
            if not compact_rows and row_y + 1 < body_h:
                safe_addstr(stdscr, row_y + 1, ix + 4, f"x{cnt} owned | {bp.description}"[: iw - 4], cp(CP_DIM))
        else:
            safe_addstr(stdscr, row_y, ix, f"[{key_lbl}] <Empty Slot - Press [I] to equip>", cp(CP_DIM, curses.A_DIM))

    footer = " Tip: Gamble Coins in [G], Star-Up in [I], Fuse Monarchs & Sacrifice for Perks in [F]!"
    safe_addstr(stdscr, max_y - 1, 0, footer[: max_x - 1], cp(CP_HUD))
    stdscr.refresh()


# ================= UNIT SUMMON GACHA SCREEN =================


def render_gacha(stdscr: curses.window, profile: PlayerProfile, ui: UIState, has_colors: bool) -> None:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    def cp(pair_id: int, extra: int = 0) -> int:
        return (curses.color_pair(pair_id) if has_colors else 0) | extra

    banner = BANNERS[BANNER_ORDER[ui.banner_idx % len(BANNER_ORDER)]]
    as_label = AUTO_SELL_LABELS.get(profile.auto_sell_mode, "OFF")

    top = (
        f" UNIT SUMMON GACHA | Coins: {profile.coins} | Mythic Pity: {profile.pity_counter}/{banner.pity_mythic_at}"
        f" | Auto-Sell: {as_label} | Owned: {profile.owned_total()}"
    )
    safe_addstr(stdscr, 0, 0, top.ljust(max_x)[:max_x], cp(CP_GOLD, curses.A_BOLD))

    draw_box(
        stdscr,
        1,
        0,
        max_y - 2,
        max_x,
        f"BANNER {ui.banner_idx + 1}/{len(BANNER_ORDER)}: {banner.name} ({len(TOWER_ORDER)} UNITS)",
        cp(CP_HUD, curses.A_BOLD),
    )

    # Banner selector pills
    pills = "  ".join(
        f"[*{BANNERS[bk].name}*]" if i == ui.banner_idx else f" {BANNERS[bk].name} "
        for i, bk in enumerate(BANNER_ORDER)
    )
    safe_addstr(stdscr, 2, 3, f"< [Left/Right/Tab] {pills}"[: max_x - 6], cp(CP_WARN, curses.A_BOLD))
    safe_addstr(stdscr, 3, 3, banner.description[: max_x - 6], cp(CP_DEFAULT))

    rw = banner.rarity_weights
    rates_line = (
        f"Rates: C:{rw['common']:.0f}% | R:{rw['rare']:.0f}% | E:{rw['epic']:.0f}%"
        f" | Leg:{rw['legendary']:.1f}% | Myth:{rw['mythic']:.1f}% | Transc:{rw['transcendent']:.1f}%"
    )
    safe_addstr(stdscr, 4, 3, rates_line[: max_x - 6], cp(CP_DIM))
    safe_addstr(
        stdscr,
        5,
        3,
        f"[1] 1x Summon ({banner.single_cost}c)   [2] 10x Summon ({banner.multi_cost}c, 10th={banner.min_10x_rarity.title()}+)   [A] Auto-Sell: {as_label}"[: max_x - 6],
        cp(CP_GOOD, curses.A_BOLD),
    )
    safe_addstr(
        stdscr,
        6,
        3,
        "[I] Inventory & Loadout   [Esc / G] Back to Lobby",
        cp(CP_HUD),
    )
    safe_addstr(stdscr, 7, 1, "-" * (max_x - 2), cp(CP_DIM, curses.A_DIM))

    res = ui.gacha_result
    if res is None:
        safe_addstr(
            stdscr,
            9,
            3,
            "Choose a Banner above and press [1] or [2]! Toggle [A] Auto-Sell to auto-convert low pulls to Coins!",
            cp(CP_WARN),
        )
    elif not res.ok:
        safe_addstr(stdscr, 9, 3, res.message[: max_x - 6], cp(CP_ENEMY, curses.A_BOLD))
    else:
        safe_addstr(stdscr, 9, 3, res.message[: max_x - 6], cp(CP_GOLD, curses.A_BOLD))
        for idx, p in enumerate(res.pulls):
            if 11 + idx >= max_y - 2:
                break
            rinfo = RARITIES[p.rarity]
            if p.auto_sold_coins > 0:
                tag = f" [AUTO-SOLD +{p.auto_sold_coins}c]"
            elif p.is_new:
                tag = " [NEW!]"
            else:
                tag = f" (Sell +{rinfo.sell_coins}c)"
            line = f"  {idx + 1:>2}. [{rinfo.label:<12}] {p.name:<16} - {p.role:<18}{tag}"
            safe_addstr(stdscr, 11 + idx, 3, line[: max_x - 6], cp(rarity_cp(p.rarity), curses.A_BOLD))

    stdscr.refresh()


# ================= INVENTORY & 8-SLOT LOADOUT SCREEN =================


def render_inventory(stdscr: curses.window, profile: PlayerProfile, ui: UIState, has_colors: bool) -> None:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    def cp(pair_id: int, extra: int = 0) -> int:
        return (curses.color_pair(pair_id) if has_colors else 0) | extra

    top = f" INVENTORY & LOADOUT ({len(profile.loadout)}/{profile.effective_max_loadout()}) | Coins: {profile.coins} | Total Owned: {profile.owned_total()}"
    safe_addstr(stdscr, 0, 0, top.ljust(max_x)[:max_x], cp(CP_HUD, curses.A_BOLD))

    left_w = max(44, (max_x * 55) // 100)
    right_w = max_x - left_w - 1
    body_h = max_y - 3

    # Show owned units first, then unowned
    ordered = sorted(
        TOWER_ORDER,
        key=lambda k: (0 if profile.inventory.get(k, 0) > 0 else 1, -RARITY_ORDER.index(TOWER_BLUEPRINTS[k].rarity), k),
    )
    ui.inv_cursor = max(0, min(len(ordered) - 1, ui.inv_cursor))
    visible = max(4, body_h - 3)
    if ui.inv_cursor < ui.inv_scroll:
        ui.inv_scroll = ui.inv_cursor
    elif ui.inv_cursor >= ui.inv_scroll + visible:
        ui.inv_scroll = ui.inv_cursor - visible + 1

    draw_box(stdscr, 1, 0, body_h, left_w, "ALL UNITS (OWNED & LOCKED)", cp(CP_HUD, curses.A_BOLD))
    for row in range(visible):
        idx = ui.inv_scroll + row
        if idx >= len(ordered):
            break
        k = ordered[idx]
        bp = TOWER_BLUEPRINTS[k]
        rinfo = RARITIES[bp.rarity]
        cnt = profile.inventory.get(k, 0)
        star = profile.star_of(k)
        eq_tag = "[EQ]" if k in profile.loadout else "    "
        own_txt = f"x{cnt:<2}" if cnt > 0 else "---"
        st_txt = f"★{star}" if cnt > 0 else "  "
        line = f"{'>' if idx == ui.inv_cursor else ' '} {eq_tag} {own_txt} {st_txt} [{rinfo.short}] {bp.symbol} {bp.name:<13} ({bp.role})"
        attr = cp(rarity_cp(bp.rarity) if cnt > 0 else CP_DIM, curses.A_BOLD if cnt > 0 else curses.A_DIM)
        if idx == ui.inv_cursor:
            attr |= curses.A_REVERSE
        safe_addstr(stdscr, 2 + row, 2, line[: left_w - 4], attr)

    # Right side: Unit Details & 8-slot bar
    rx = left_w + 1
    draw_box(stdscr, 1, rx, body_h, right_w, "UNIT INSPECTOR & SELL", cp(CP_GOLD, curses.A_BOLD))
    ix = rx + 2
    iw = right_w - 4
    sel_key = ordered[ui.inv_cursor]
    bp = TOWER_BLUEPRINTS[sel_key]
    rinfo = RARITIES[bp.rarity]
    cnt = profile.inventory.get(sel_key, 0)
    star = profile.star_of(sel_key)
    has_dupe = cnt >= 2
    star_txt = f"★{star}/{MAX_UNIT_STAR} (+{(star-1)*12}% DMG/+{(star-1)*6}% SPD)"

    safe_addstr(stdscr, 3, ix, f"{bp.name} [{rinfo.label}] {star_txt}"[:iw], cp(rarity_cp(bp.rarity), curses.A_BOLD))
    up_cost_str = (
        f"Next ★{star + 1}: {star_upgrade_coin_cost(bp.rarity, star + 1, has_dupe)}c"
        + (" (1 dupe -50%)" if has_dupe else " (Coins)")
        if cnt > 0 and star < MAX_UNIT_STAR
        else ("MAX ★5" if cnt > 0 else "Locked")
    )
    safe_addstr(stdscr, 4, ix, f"Owned: {cnt} | Sell: {rinfo.sell_coins}c | {up_cost_str}"[:iw], cp(CP_GOLD))
    safe_addstr(stdscr, 5, ix, bp.description[:iw], cp(CP_DEFAULT))
    for lv_i, st in enumerate(bp.levels):
        line = f"Lv{lv_i + 1} ${st.cost:<4} DMG:{int(st.damage):<4} CD:{st.cooldown:.2f}s RNG:{st.range:.1f}"
        safe_addstr(stdscr, 7 + lv_i, ix, line[:iw], cp(CP_DIM))

    safe_addstr(stdscr, 12, rx + 1, "-" * (right_w - 2), cp(CP_DIM, curses.A_DIM))
    safe_addstr(stdscr, 13, ix, f"LOADOUT ({len(profile.loadout)}/{profile.effective_max_loadout()}):", cp(CP_HUD, curses.A_BOLD))
    for s_i, lk in enumerate(profile.loadout):
        if 14 + s_i >= body_h - 3:
            break
        lbp = TOWER_BLUEPRINTS[lk]
        safe_addstr(stdscr, 14 + s_i, ix + 1, f"{s_i + 1}. {lbp.name} ★{profile.star_of(lk)} ({lbp.role})"[: iw - 1], cp(rarity_cp(lbp.rarity)))

    if ui.inv_msg:
        safe_addstr(stdscr, body_h - 2, ix, ui.inv_msg[:iw], cp(CP_GOOD, curses.A_BOLD))

    controls = " [Up/Down] Select  [Space] Equip  [U] Star-Up(★1-5)  [S] Sell 1  [A] Sell Dupes  [F] Forge/Altar  [Esc/I] Back"
    safe_addstr(stdscr, max_y - 1, 0, controls[: max_x - 1], cp(CP_HUD))
    stdscr.refresh()


# ================= FUSION & SACRIFICE ALTAR SCREEN =================


def render_forge(stdscr: curses.window, profile: PlayerProfile, ui: UIState, has_colors: bool) -> None:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    def cp(pair_id: int, extra: int = 0) -> int:
        return (curses.color_pair(pair_id) if has_colors else 0) | extra

    top = f" FUSION & SACRIFICE ALTAR | Coins: {profile.coins} | Loadout Cap: {profile.effective_max_loadout()} | [Tab] Switch Panel"
    safe_addstr(stdscr, 0, 0, top.ljust(max_x)[:max_x], cp(CP_GOLD, curses.A_BOLD))

    left_w = max(42, (max_x * 48) // 100)
    right_w = max_x - left_w - 1
    body_h = max_y - 3

    # Left: Recipe Fusions
    l_title = "* RECIPE FUSION (FORGE MONARCHS) *" if ui.forge_tab == 0 else "RECIPE FUSION [Tab]"
    draw_box(stdscr, 1, 0, body_h, left_w, l_title, cp(CP_GOOD if ui.forge_tab == 0 else CP_HUD, curses.A_BOLD))
    ui.forge_fusion_idx = max(0, min(len(FUSION_RECIPES) - 1, ui.forge_fusion_idx))
    lw = left_w - 4
    y_cur = 3
    for idx, rec in enumerate(FUSION_RECIPES):
        if y_cur + 2 >= body_h:
            break
        sel = ui.forge_tab == 0 and idx == ui.forge_fusion_idx
        bp_out = TOWER_BLUEPRINTS[rec.output_key]
        bp_a = TOWER_BLUEPRINTS[rec.ing_a]
        bp_b = TOWER_BLUEPRINTS[rec.ing_b]
        ca = profile.inventory.get(rec.ing_a, 0)
        cb = profile.inventory.get(rec.ing_b, 0)
        ready = ca >= 1 and cb >= 1 and profile.coins >= rec.coin_cost
        mark = ">>" if sel else "  "
        head = f"{mark}{bp_out.name} [{RARITIES[bp_out.rarity].short}] ({rec.coin_cost}c)"
        attr = cp(CP_GOOD if ready else CP_DIM, curses.A_BOLD if sel or ready else 0)
        if sel:
            attr |= curses.A_REVERSE
        safe_addstr(stdscr, y_cur, 2, head[:lw], attr)
        sub = f"   {bp_a.name}(x{ca}) + {bp_b.name}(x{cb}) -> Own:{profile.inventory.get(rec.output_key, 0)}"
        safe_addstr(stdscr, y_cur + 1, 2, sub[:lw], cp(CP_DEFAULT if ca >= 1 and cb >= 1 else CP_DIM))
        y_cur += 2

    # Right: Sacrifice Altar
    rx = left_w + 1
    r_title = "* SACRIFICE ALTAR (3-RUN PERKS) *" if ui.forge_tab == 1 else "SACRIFICE ALTAR [Tab]"
    draw_box(stdscr, 1, rx, body_h, right_w, r_title, cp(CP_WARN if ui.forge_tab == 1 else CP_HUD, curses.A_BOLD))
    ix = rx + 2
    iw = right_w - 4
    ui.forge_perk_idx = max(0, min(len(SACRIFICE_PERKS) - 1, ui.forge_perk_idx))
    ry = 3
    for idx, perk in enumerate(SACRIFICE_PERKS):
        if ry + 1 >= body_h - 6:
            break
        sel = ui.forge_tab == 1 and idx == ui.forge_perk_idx
        attr = cp(CP_GOLD if sel else CP_DEFAULT, curses.A_BOLD if sel else 0)
        if sel:
            attr |= curses.A_REVERSE
        safe_addstr(stdscr, ry, ix, f"{'>>' if sel else '  '}{perk.name}"[:iw], attr)
        safe_addstr(stdscr, ry + 1, ix + 2, perk.description[: iw - 2], cp(CP_DIM))
        ry += 2

    # Qualifying Sacrifice Unit selector
    sel_perk = SACRIFICE_PERKS[ui.forge_perk_idx]
    qual = [
        k
        for k in TOWER_ORDER
        if profile.inventory.get(k, 0) > 0
        and unit_qualifies_for_perk(sel_perk, TOWER_BLUEPRINTS[k], profile.star_of(k))[0]
    ]
    safe_addstr(stdscr, max(ry, body_h - 6), rx + 1, "-" * (right_w - 2), cp(CP_DIM, curses.A_DIM))
    uy = max(ry + 1, body_h - 5)
    if qual:
        ui.forge_unit_idx %= len(qual)
        uk = qual[ui.forge_unit_idx]
        ubp = TOWER_BLUEPRINTS[uk]
        u_line = f"Sacrifice [< / >]: {ubp.name} ★{profile.star_of(uk)} (x{profile.inventory[uk]}) [{ui.forge_unit_idx + 1}/{len(qual)}]"
        safe_addstr(stdscr, uy, ix, u_line[:iw], cp(CP_GOOD, curses.A_BOLD))
    else:
        safe_addstr(stdscr, uy, ix, "No qualifying unit in inventory for this perk yet.", cp(CP_ENEMY))

    if profile.active_perks:
        act = "Active: " + " | ".join(f"{p['name']}({p['runs_left']}r)" for p in profile.active_perks)
        safe_addstr(stdscr, uy + 1, ix, act[:iw], cp(CP_GOLD))
    if ui.forge_msg:
        safe_addstr(stdscr, body_h - 1, ix, ui.forge_msg[:iw], cp(CP_GOOD, curses.A_BOLD))

    controls = " [Tab] Switch Panel  [Up/Down] Select Recipe/Perk  [Left/Right] Pick Sacrifice Unit  [Space/Enter] Fuse/Sacrifice  [Esc/F] Back"
    safe_addstr(stdscr, max_y - 1, 0, controls[: max_x - 1], cp(CP_HUD))
    stdscr.refresh()


# ================= IN-MATCH MODALS =================


def render_tavern_modal(stdscr: curses.window, state: GameState, ui: UIState, has_colors: bool) -> None:
    max_y, max_x = stdscr.getmaxyx()

    def cp(pair_id: int, extra: int = 0) -> int:
        return (curses.color_pair(pair_id) if has_colors else 0) | extra

    bw = min(68, max_x - 4)
    bh = 17
    bx = (max_x - bw) // 2
    by = max(1, (max_y - bh) // 2)

    clear_rect(stdscr, by, bx, bh, bw, cp(CP_DEFAULT))
    draw_box(stdscr, by, bx, bh, bw, "TAVERN GOLD GAMBLE (MATCH GOLD)", cp(CP_GOLD, curses.A_BOLD))

    bet = state.gold if ui.bet_idx == len(BET_AMOUNTS) else BET_AMOUNTS[ui.bet_idx]
    tinfo = ""
    if not state.difficulty.pause_in_gamble and not state.wave_active and state.next_wave_timer is not None:
        tinfo = f"  |  LIVE TIMER: {state.next_wave_timer:.1f}s!"
    safe_addstr(stdscr, by + 1, bx + 3, f"Match Gold: ${state.gold}   Bet: ${bet}{tinfo}", cp(CP_GOLD, curses.A_BOLD))

    bet_str = "Bet: " + " ".join(
        f"[{i + 1}:*${a}*]" if ui.bet_idx == i else f"[{i + 1}:${a}]" for i, a in enumerate(BET_AMOUNTS)
    ) + (" [5:*ALL*]" if ui.bet_idx == len(BET_AMOUNTS) else " [5:ALL]")
    safe_addstr(stdscr, by + 3, bx + 3, bet_str[: bw - 6], cp(CP_HUD))

    safe_addstr(stdscr, by + 5, bx + 3, "[S] SPIN SLOTS   (777=10x | 3-kind=4x | 77=2x | pair=1.4x)", cp(CP_DEFAULT))
    safe_addstr(stdscr, by + 6, bx + 3, "[H] DICE HIGH    (2d6 >= 8 -> 2x)", cp(CP_DEFAULT))
    safe_addstr(stdscr, by + 7, bx + 3, "[L] DICE LOW     (2d6 <= 6 -> 2x)", cp(CP_DEFAULT))
    safe_addstr(stdscr, by + 8, bx + 3, "[7] LUCKY SEVEN  (2d6 == 7 -> 4.5x)", cp(CP_DEFAULT))
    safe_addstr(stdscr, by + 9, bx + 3, f"[C] MYSTERY CRATE (${CRATE_COST}: $200 vault / free upgrade / mimic!)", cp(CP_WARN))
    safe_addstr(stdscr, by + 11, bx + 2, "-" * (bw - 4), cp(CP_DIM, curses.A_DIM))

    if ui.tavern_result is not None:
        res = ui.tavern_result
        col = cp(CP_GOOD if res.net_gold > 0 else (CP_ENEMY if res.net_gold < 0 else CP_WARN), curses.A_BOLD)
        safe_addstr(stdscr, by + 12, bx + 3, res.headline[: bw - 6], col)
        safe_addstr(stdscr, by + 13, bx + 3, res.detail[: bw - 6], cp(CP_DEFAULT))
    else:
        safe_addstr(stdscr, by + 12, bx + 3, "Note: To gamble Coins for new Defender Units, go to Lobby [R] -> [G]!", cp(CP_DIM))

    safe_addstr(stdscr, by + 15, bx + 3, "[G / Esc] Back to Battle", cp(CP_HUD, curses.A_BOLD))


def render_bestiary_modal(stdscr: curses.window, ui: UIState, has_colors: bool) -> None:
    max_y, max_x = stdscr.getmaxyx()

    def cp(pair_id: int, extra: int = 0) -> int:
        return (curses.color_pair(pair_id) if has_colors else 0) | extra

    bw = min(90, max_x - 2)
    bh = min(26, max_y - 2)
    bx = (max_x - bw) // 2
    by = max(1, (max_y - bh) // 2)

    clear_rect(stdscr, by, bx, bh, bw, cp(CP_DEFAULT))
    draw_box(
        stdscr,
        by,
        bx,
        bh,
        bw,
        f"BESTIARY ({len(UNIT_ORDER)} ENEMIES/BOSSES + {len(ALLY_TEMPLATES)} FRIENDLY UNITS)",
        cp(CP_HUD, curses.A_BOLD),
    )

    rows_data: List[Tuple[str, int]] = []
    for k in UNIT_ORDER:
        u = UNIT_TEMPLATES[k]
        tag = "BOSS" if u.is_boss else f"T{u.tier}  "
        arm = f"A:{int(u.armor):<2}" if u.armor > 0 else "A:0 "
        line = f"{tag} [{u.symbol}] {u.name:<18} HP:{int(u.max_hp):<5} SPD:{u.speed:.1f} {arm} ${u.reward:<3} {u.description}"
        rows_data.append((line, cp(CP_BOSS if u.is_boss else CP_DEFAULT, curses.A_BOLD if u.is_boss else 0)))
    for ak, a in ALLY_TEMPLATES.items():
        rev = f"2ND-LIFE" if a.revives > 0 else f"A:{int(a.armor):<2}    "
        line = f"ALLY [{a.symbol}] {a.name:<18} HP:{int(a.max_hp):<5} DPS:{int(a.atk_dps):<3} {rev} {a.description}"
        rows_data.append((line, cp(CP_ALLY, curses.A_BOLD)))

    visible_rows = bh - 4
    max_scroll = max(0, len(rows_data) - visible_rows)
    ui.bestiary_scroll = max(0, min(max_scroll, ui.bestiary_scroll))

    for r in range(visible_rows):
        idx = ui.bestiary_scroll + r
        if idx >= len(rows_data):
            break
        txt, attr = rows_data[idx]
        safe_addstr(stdscr, by + 1 + r, bx + 2, txt[: bw - 4], attr)

    safe_addstr(
        stdscr,
        by + bh - 2,
        bx + 2,
        f"[Up/Down] Scroll ({ui.bestiary_scroll + 1}-{min(len(rows_data), ui.bestiary_scroll + visible_rows)}/{len(rows_data)})   [B / Esc] Close",
        cp(CP_HUD, curses.A_BOLD),
    )


# ================= FULL-SCREEN BATTLE RENDERER =================


def pick_tile_size(state: GameState, map_w: int, map_h: int) -> Tuple[int, int]:
    """Choose largest tile (w, h) that fits full 36x18 map in terminal, else (2,1) with camera."""
    inner_w = map_w - 2
    inner_h = map_h - 2
    for tw, th in ((4, 2), (3, 2), (3, 1), (2, 1)):
        if state.width * tw <= inner_w and state.height * th <= inner_h:
            return tw, th
    return 2, 1


def render_game(stdscr: curses.window, state: GameState, ui: UIState, has_colors: bool) -> None:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    if max_y < MIN_ROWS or max_x < MIN_COLS:
        msg = f"Terminal too small: {max_x}x{max_y} (need {MIN_COLS}x{MIN_ROWS})."
        safe_addstr(stdscr, max_y // 2, max(0, (max_x - len(msg)) // 2), msg, curses.A_BOLD)
        stdscr.refresh()
        return

    def cp(pair_id: int, extra: int = 0) -> int:
        return (curses.color_pair(pair_id) if has_colors else 0) | extra

    panel_w = min(44, max(36, (max_x * 28) // 100))
    map_w = max_x - panel_w - 1
    map_h = max_y - 8
    tw, th = pick_tile_size(state, map_w, map_h)

    view_cols = min(state.width, (map_w - 2) // tw)
    view_rows = min(state.height, (map_h - 2) // th)

    if state.cursor_x < ui.cam_x:
        ui.cam_x = state.cursor_x
    elif state.cursor_x >= ui.cam_x + view_cols:
        ui.cam_x = state.cursor_x - view_cols + 1
    ui.cam_x = max(0, min(state.width - view_cols, ui.cam_x))

    if state.cursor_y < ui.cam_y:
        ui.cam_y = state.cursor_y
    elif state.cursor_y >= ui.cam_y + view_rows:
        ui.cam_y = state.cursor_y - view_rows + 1
    ui.cam_y = max(0, min(state.height - view_rows, ui.cam_y))

    # --- 1. Full-width Top Header ---
    wave_lbl = f"{state.wave}/{state.max_waves}" if not state.endless else f"{state.wave}*"
    st_lbl = "PAUSED" if state.paused else ("ACTIVE" if state.wave_active else "READY")
    if state.game_over:
        st_lbl = "DEFEAT"
    elif state.victory:
        st_lbl = "VICTORY"

    auto_lbl = "AUTO:ON" if state.auto_start else "AUTO:OFF"
    paint_lbl = " | PAINT:ON" if ui.paint_mode else ""
    header = (
        f" TD | {state.map_def.name} [{state.difficulty.name}] | W:{wave_lbl} ({st_lbl})"
        f" | ${state.gold} | HP:{state.lives} | +{state.coins_earned}c | Scr:{state.score} | {state.speed_mult}x | {auto_lbl}{paint_lbl}"
    )
    safe_addstr(stdscr, 0, 0, header.ljust(max_x)[:max_x], cp(CP_HUD, curses.A_BOLD))

    # --- 2. Full-width Boss HP Bar / Threat Bar / Mass-Place Bar ---
    mass_candidates: List[Tuple[int, int]] = []
    mass_index_map: Dict[Tuple[int, int], int] = {}
    mass_rect: Optional[Tuple[int, int, int, int]] = None
    if ui.mass_anchor is not None:
        ax, ay = ui.mass_anchor
        mass_rect = (
            min(ax, state.cursor_x),
            min(ay, state.cursor_y),
            max(ax, state.cursor_x),
            max(ay, state.cursor_y),
        )
        mass_candidates = state.rect_build_candidates(ax, ay, state.cursor_x, state.cursor_y)
        mass_index_map = {pos: idx for idx, pos in enumerate(mass_candidates)}

    bosses = state.active_bosses()
    if ui.mass_anchor is not None:
        bp = TOWER_BLUEPRINTS[state.selected_tower_kind]
        unit_cost = bp.levels[0].cost
        afford_cnt = min(len(mass_candidates), state.gold // unit_cost if unit_cost > 0 else 0)
        total_cost = len(mass_candidates) * unit_cost
        mline = (
            f" MASS-PLACE ({ui.mass_anchor[0]},{ui.mass_anchor[1]})->({state.cursor_x},{state.cursor_y})"
            f" | {len(mass_candidates)} plots (${total_cost}, afford {afford_cnt}x {bp.name})"
            f" | [Space] Build  [U] Upgr Box  [Z/Esc] Cancel"
        )
        safe_addstr(stdscr, 1, 0, mline.ljust(max_x)[:max_x], cp(CP_GOOD, curses.A_BOLD))
    elif bosses:
        b = max(bosses, key=lambda e: e.progress)
        bar_w = min(30, max(14, max_x // 4))
        bar = render_hp_bar(b.hp, b.max_hp, bar_w)
        sh_txt = f" +{int(b.shield)}SH" if b.shield > 0 else ""
        cnt_txt = f" (x{len(bosses)})" if len(bosses) > 1 else ""
        bline = f" BOSS: {b.name}{cnt_txt} {bar} {int(b.hp)}/{int(b.max_hp)}{sh_txt} | Arm:{int(b.armor_current)}"
        safe_addstr(stdscr, 1, 0, bline.ljust(max_x)[:max_x], cp(CP_BOSS, curses.A_BOLD))
    elif state.wave_active:
        lead = state.lead_enemy()
        if lead is not None:
            bar = render_hp_bar(lead.hp, lead.max_hp, min(22, max(12, max_x // 5)))
            rem = len(state.enemies) + len(state.spawn_queue)
            lline = f" LEAD: {lead.name} {bar} {int(lead.hp)}/{int(lead.max_hp)} HP | Foes: {rem} | Allies: {len(state.allies)} | [N] Prestart Next"
            safe_addstr(stdscr, 1, 0, lline.ljust(max_x)[:max_x], cp(CP_WARN, curses.A_BOLD))
        else:
            safe_addstr(stdscr, 1, 0, " Spawning wave... | [N] Prestart Next".ljust(max_x)[:max_x], cp(CP_DIM))
    elif not state.wave_active and state.next_wave_timer is not None and not state.game_over and not state.victory:
        bonus = max(0, min(35, int(state.next_wave_timer)))
        tline = f" FORCE-START IN {state.next_wave_timer:4.1f}s -- [N] +${bonus} early | [V] Auto-Wave | [G] Tavern"
        tcol = cp(CP_ENEMY if state.next_wave_timer <= 4.0 else CP_WARN, curses.A_BOLD)
        safe_addstr(stdscr, 1, 0, tline.ljust(max_x)[:max_x], tcol)
    else:
        rline = f" READY -- [N] Wave {state.wave + 1} | [V] Auto-Wave | [F] Speed(1-10x) | [G] Tavern | [R] Lobby/Gacha"
        safe_addstr(stdscr, 1, 0, rline.ljust(max_x)[:max_x], cp(CP_GOOD))

    # --- 3. Full-Screen Map Viewport ---
    map_y = 2
    scroll_tag = f" [{ui.cam_x},{ui.cam_y}]" if (view_cols < state.width or view_rows < state.height) else f" ({tw}x{th})"
    draw_box(stdscr, map_y, 0, map_h, map_w, f"MAP: {state.map_def.name}{scroll_tag}", cp(CP_HUD))

    range_cells = get_range_cells(state)

    cell_enemies: Dict[Tuple[int, int], List[Enemy]] = {}
    road_set = state.road_set
    for enemy in state.enemies:
        if enemy._px or enemy._py:
            cell = (int(round(enemy._px)), int(round(enemy._py)))
            if cell not in road_set:
                cell = enemy.grid_cell(state.centerline, road_set)
        else:
            cell = enemy.grid_cell(state.centerline, road_set)
        cell_enemies.setdefault(cell, []).append(enemy)

    cell_allies: Dict[Tuple[int, int], List[AllyUnit]] = {}
    for ally in state.allies:
        if ally._px or ally._py:
            cell = (int(round(ally._px)), int(round(ally._py)))
            if cell not in road_set:
                cell = ally.grid_cell(state.centerline, road_set)
        else:
            cell = ally.grid_cell(state.centerline, road_set)
        cell_allies.setdefault(cell, []).append(ally)

    frame_bounds = (max_y, max_x)

    shot_cells: Dict[Tuple[int, int], Tuple[str, str]] = {}
    for shot in state.shots:
        steps = max(2, int(math.hypot(shot.x1 - shot.x0, shot.y1 - shot.y0) * 2))
        for i in range(1, steps):
            t = i / steps
            sx = int(round(shot.x0 + (shot.x1 - shot.x0) * t))
            sy = int(round(shot.y0 + (shot.y1 - shot.y0) * t))
            if 0 <= sx < state.width and 0 <= sy < state.height:
                shot_cells[(sx, sy)] = (shot.char, shot.kind)

    for vy in range(view_rows):
        y = ui.cam_y + vy
        for vx in range(view_cols):
            x = ui.cam_x + vx
            pos = (x, y)
            is_cursor = x == state.cursor_x and y == state.cursor_y
            in_range = pos in range_cells
            px = 1 + vx * tw
            py = map_y + 1 + vy * th

            # Determine row0 and optional row1 text
            row0 = ".".ljust(tw)
            row1 = " " * tw
            attr = cp(CP_DIM, curses.A_DIM)

            if pos in state.spawn_cells:
                row0 = ("S>" if tw <= 2 else "S>>").ljust(tw)[:tw]
                row1 = ("SPA" if th >= 2 else "").ljust(tw)[:tw]
                attr = cp(CP_SPAWN, curses.A_BOLD)
            elif pos in state.base_cells:
                row0 = ("<>" if tw <= 2 else "<#>").ljust(tw)[:tw]
                row1 = ("HQ " if th >= 2 else "").ljust(tw)[:tw]
                attr = cp(CP_BASE, curses.A_BOLD)
            elif pos in state.road_set:
                row0 = ":" * tw
                row1 = ":" * tw
                attr = cp(CP_PATH, curses.A_BOLD if in_range else curses.A_DIM)

            if pos in state.spikes and pos not in cell_enemies:
                row0 = ("x" * tw)[:tw]
                attr = cp(CP_WARN, curses.A_BOLD)

            if pos in state.towers:
                tower = state.towers[pos]
                r_col = rarity_cp(tower.blueprint.rarity)
                if tw >= 3:
                    row0 = f"[{tower.blueprint.symbol}]"[:tw].ljust(tw)
                    row1 = f"L{tower.level}{'+' if tower.buff_dmg_mult > 1.0 or tower.buff_spd_mult > 1.0 else ' '}".ljust(tw)[:tw]
                else:
                    row0 = f"{tower.blueprint.symbol}{tower.level}"
                attr = cp(r_col, curses.A_BOLD)
            elif pos in cell_enemies:
                elist = cell_enemies[pos]
                lead = max(elist, key=lambda e: (1 if e.is_boss else 0, e.template.tier, e.progress))
                cnt_or_hp = str(min(9, len(elist))) if len(elist) > 1 else micro_hp_char(lead.hp, lead.max_hp)
                if tw >= 3 and th >= 2:
                    row0 = f" {lead.symbol}{str(min(9, len(elist))) if len(elist) > 1 else ' '}".ljust(tw)[:tw]
                    row1 = render_hp_bar(lead.hp, lead.max_hp, max(1, tw - 2))[:tw]
                else:
                    row0 = f"{lead.symbol}{cnt_or_hp}".ljust(tw)[:tw]
                if lead.hit_flash > 0:
                    attr = cp(CP_ENEMY_HIT, curses.A_BOLD)
                elif lead.is_boss:
                    attr = cp(CP_BOSS, curses.A_BOLD)
                elif lead.poison_timer > 0:
                    attr = cp(CP_ENEMY_POISON, curses.A_BOLD)
                elif lead.slow_timer > 0:
                    attr = cp(CP_ENEMY_SLOW, curses.A_BOLD)
                else:
                    attr = cp(CP_ENEMY, curses.A_BOLD)
            elif pos in cell_allies:
                alist = cell_allies[pos]
                a0 = alist[0]
                if tw >= 3 and th >= 2:
                    row0 = f"^{a0.template.symbol}{'2' if a0.revives_left > 0 else ' '}".ljust(tw)[:tw]
                    row1 = render_hp_bar(a0.hp, a0.max_hp, max(1, tw - 2))[:tw]
                else:
                    row0 = f"^{a0.template.symbol}".ljust(tw)[:tw]
                attr = cp(CP_GOLD if a0.revive_flash > 0 else CP_ALLY, curses.A_BOLD)
            elif pos in shot_cells:
                schar, skind = shot_cells[pos]
                row0 = f" {schar} "[:tw] if tw >= 3 else f"{schar} "
                attr = cp(rarity_cp(TOWER_BLUEPRINTS[skind].rarity), curses.A_BOLD)
            elif pos in mass_index_map:
                bp = TOWER_BLUEPRINTS[state.selected_tower_kind]
                m_idx = mass_index_map[pos]
                can_pay = (m_idx + 1) * bp.levels[0].cost <= state.gold
                row0 = f"{bp.symbol}?"[:tw].ljust(tw)
                row1 = ("$$" if can_pay else "--").ljust(tw)[:tw] if th >= 2 else row1
                attr = cp(CP_GOOD if can_pay else CP_WARN, curses.A_BOLD)
            elif in_range and pos not in state.road_set:
                row0 = ("+" + " " * (tw - 1))[:tw]
                attr = cp(CP_RANGE, curses.A_BOLD)

            if mass_rect is not None and mass_rect[0] <= x <= mass_rect[2] and mass_rect[1] <= y <= mass_rect[3] and pos in state.towers:
                attr |= curses.A_UNDERLINE

            if is_cursor:
                attr |= curses.A_REVERSE

            safe_addstr(stdscr, py, px, row0, attr, frame_bounds)
            if th >= 2:
                safe_addstr(stdscr, py + 1, px, row1, attr, frame_bounds)

    # --- 4. Right Side Panel (Equipped 8-Slot Loadout + Inspector) ---
    panel_x = map_w + 1
    draw_box(stdscr, map_y, panel_x, map_h, panel_w, "LOADOUT [1-8] & INSPECTOR", cp(CP_HUD))
    ix = panel_x + 2
    iw = panel_w - 4

    for idx, kind in enumerate(state.loadout):
        bp = TOWER_BLUEPRINTS[kind]
        cost = state._tower_cost(bp.levels[0].cost)
        sel = state.selected_tower_kind == kind
        mark = ">" if sel else " "
        attr = cp(rarity_cp(bp.rarity), curses.A_BOLD) if state.gold >= cost else cp(CP_DIM, curses.A_DIM)
        if sel:
            attr |= curses.A_UNDERLINE
        key_lbl = "0" if idx == 9 else str(idx + 1)
        star = state.unit_stars.get(kind, 1)
        st_tag = f"★{star}" if star > 1 else "  "
        line = f"{mark}[{key_lbl}] {bp.symbol} {bp.name:<11}{st_tag}${cost:<3} ({bp.role[:7]})"
        safe_addstr(stdscr, map_y + 1 + idx, ix, line[:iw], attr)

    div_y = map_y + 1 + max(len(state.loadout), 1)
    safe_addstr(stdscr, div_y, panel_x + 1, "-" * (panel_w - 2), cp(CP_DIM, curses.A_DIM))

    iy = div_y + 1
    panel_bottom = map_y + map_h - 1

    def insp(row_off: int, text: str, attr: int = 0) -> None:
        if iy + row_off < panel_bottom:
            safe_addstr(stdscr, iy + row_off, ix, text[:iw], attr)

    cpos = (state.cursor_x, state.cursor_y)
    hovered_tower: Optional[Tower] = state.towers.get(cpos)
    if hovered_tower is not None:
        st = hovered_tower.stats
        insp(
            0,
            f"{hovered_tower.blueprint.name} Lv{hovered_tower.level} ★{hovered_tower.star_level} ({hovered_tower.x},{hovered_tower.y})",
            cp(rarity_cp(hovered_tower.blueprint.rarity), curses.A_BOLD),
        )
        if st.income_per_wave > 0:
            insp(1, f"Income: +${st.income_per_wave}/wave +${st.income_per_tick}/tick", cp(CP_GOLD))
            insp(2, f"Total Gold Earned: ${hovered_tower.gold_earned}", cp(CP_DEFAULT))
        elif st.spawn_ally_kind:
            atpl = ALLY_TEMPLATES[st.spawn_ally_kind]
            insp(1, f"Spawns: {atpl.name} (every {st.spawn_interval:.1f}s)", cp(CP_ALLY))
            insp(2, f"Max Active: {st.max_active_allies} | {atpl.description}", cp(CP_DIM))
        else:
            insp(
                1,
                f"DMG:{int(hovered_tower.effective_damage)} RNG:{hovered_tower.effective_range:.1f} CD:{hovered_tower.effective_cooldown:.2f}s",
                cp(CP_DEFAULT),
            )
            buff_txt = ""
            if hovered_tower.buff_dmg_mult > 1.0 or hovered_tower.buff_spd_mult > 1.0 or hovered_tower.buff_rng_mult > 1.0:
                buff_txt = " [BUFFED!]"
            insp(
                2,
                f"Kills:{hovered_tower.kills} Tgt:{hovered_tower.target_mode}{buff_txt}",
                cp(CP_GOOD if buff_txt else CP_DEFAULT),
            )
        if hovered_tower.can_upgrade:
            ucost = hovered_tower.upgrade_cost or 0
            u_attr = cp(CP_GOOD, curses.A_BOLD) if state.gold >= ucost else cp(CP_WARN)
            insp(3, f"[U] Upgr->Lv{hovered_tower.level + 1} (${ucost})", u_attr)
        else:
            insp(3, "MAX LEVEL!", cp(CP_GOOD, curses.A_BOLD))
        insp(4, f"[X] Sell (+${hovered_tower.sell_value})", cp(CP_WARN))
    elif cpos in cell_enemies:
        lead = max(cell_enemies[cpos], key=lambda e: (1 if e.is_boss else 0, e.hp))
        insp(0, f"{lead.name} ({len(cell_enemies[cpos])} here)", cp(CP_ENEMY, curses.A_BOLD))
        insp(1, f"{render_hp_bar(lead.hp, lead.max_hp, 12)} {int(lead.hp)}/{int(lead.max_hp)}", cp(CP_DEFAULT))
        tags = []
        if lead.armor_current > 0:
            tags.append(f"Arm:{int(lead.armor_current)}")
        if lead.shield > 0:
            tags.append(f"SH:{int(lead.shield)}")
        if lead.slow_timer > 0:
            tags.append("SLOW")
        if lead.poison_timer > 0:
            tags.append("BURN/ACID")
        insp(2, (" ".join(tags) or "No buffs"), cp(CP_WARN))
        insp(3, lead.template.description, cp(CP_DIM))
    elif cpos in cell_allies:
        a = cell_allies[cpos][0]
        insp(0, f"Ally: {a.template.name}", cp(CP_ALLY, curses.A_BOLD))
        insp(1, f"{render_hp_bar(a.hp, a.max_hp, 12)} {int(a.hp)}/{int(a.max_hp)}", cp(CP_DEFAULT))
        insp(2, f"2nd-Life left: {a.revives_left} | DPS:{int(a.template.atk_dps)}", cp(CP_GOLD))
    elif cpos in state.spawn_cells:
        insp(0, "Enemy Spawn Gate (S>)", cp(CP_SPAWN, curses.A_BOLD))
    elif cpos in state.base_cells:
        insp(0, "Core Fortress (<>)", cp(CP_BASE, curses.A_BOLD))
        insp(1, f"Lives: {state.lives}", cp(CP_DEFAULT))
    elif cpos in state.road_set:
        insp(0, f"2-Lane Road ({state.cursor_x},{state.cursor_y})", cp(CP_PATH, curses.A_BOLD))
        insp(1, "Enemies & Friendly Units fight here.", cp(CP_DIM))
    elif state.selected_tower_kind in TOWER_BLUEPRINTS:
        bp = TOWER_BLUEPRINTS[state.selected_tower_kind]
        st = bp.levels[0]
        insp(0, f"Plot ({state.cursor_x},{state.cursor_y}) -> {bp.name}", cp(CP_GOOD, curses.A_BOLD))
        insp(1, bp.description, cp(CP_DIM))
        insp(2, f"${st.cost} DMG:{int(st.damage)} R:{st.range:.1f} CD:{st.cooldown:.2f}s", cp(CP_DEFAULT))
        insp(3, "[Space/Enter] Build Unit", cp(CP_GOOD))

    # --- 5. Full-width Bottom Controls & Log ---
    bot_y = map_y + map_h
    c1 = "[Arrows/WASD] Move  [1-8] Loadout  [Space] Build/Upgr  [Z] Mass-Box  [C] Paint  [U] Upgr  [X] Sell"
    c2 = "[N] Wave/Prestart  [V] Auto-Wave  [F] Speed(1-10x)  [T] Target  [G] Tavern  [B] Codex  [P] Pause  [R] Lobby  [Q] Quit"
    safe_addstr(stdscr, bot_y, 0, c1[:max_x], cp(CP_HUD))
    safe_addstr(stdscr, bot_y + 1, 0, c2[:max_x], cp(CP_HUD))

    draw_box(stdscr, bot_y + 2, 0, 4, max_x, "BATTLE LOG", cp(CP_DIM))
    for i, msg in enumerate(state.logs[-2:]):
        safe_addstr(stdscr, bot_y + 3 + i, 2, msg[: max_x - 4], cp(CP_DEFAULT))

    # --- 6. Modals / End Banners ---
    if ui.mode == "tavern":
        render_tavern_modal(stdscr, state, ui, has_colors)
    elif ui.mode == "bestiary":
        render_bestiary_modal(stdscr, ui, has_colors)
    elif state.game_over or state.victory:
        bw = min(52, max_x - 4)
        bh = 5
        bx = (max_x - bw) // 2
        by = map_y + max(1, (map_h - bh) // 2)
        title = " VICTORY! " if state.victory else " GAME OVER "
        bcol = cp(CP_GOOD if state.victory else CP_ENEMY, curses.A_BOLD)
        clear_rect(stdscr, by, bx, bh, bw, cp(CP_DEFAULT))
        draw_box(stdscr, by, bx, bh, bw, title, bcol)
        safe_addstr(stdscr, by + 1, bx + 3, f"Waves: {state.wave}  Score: {state.score}  Coins Earned: +{state.coins_earned}"[: bw - 6], cp(CP_GOLD, curses.A_BOLD))
        if state.victory:
            safe_addstr(stdscr, by + 2, bx + 3, "[E] Continue Endless Mode", cp(CP_HUD, curses.A_BOLD))
        else:
            safe_addstr(stdscr, by + 2, bx + 3, "Your fortress has fallen!", cp(CP_WARN))
        safe_addstr(stdscr, by + 3, bx + 3, "[R] Return to Lobby/Gacha   [Q] Quit", cp(CP_DEFAULT))

    stdscr.refresh()


# ================= INPUT HANDLERS =================


def handle_setup_key(
    profile: PlayerProfile, ui: UIState, key: int
) -> Tuple[bool, Optional[GameState]]:
    if key in (ord("q"), ord("Q")):
        return True, None
    if key in (ord("g"), ord("G")):
        ui.return_mode = "setup"
        ui.mode = "gacha"
        return False, None
    if key in (ord("i"), ord("I")):
        ui.inv_msg = ""
        ui.return_mode = "setup"
        ui.mode = "inventory"
        return False, None
    if key in (ord("f"), ord("F")):
        ui.forge_msg = ""
        ui.return_mode = "setup"
        ui.mode = "forge"
        return False, None
    if key in (ord("b"), ord("B")):
        ui.return_mode = "setup"
        ui.mode = "bestiary"
        return False, None
    if key in (curses.KEY_UP, ord("w"), ord("W"), ord("k"), ord("K")):
        ui.setup_diff_idx = (ui.setup_diff_idx - 1) % len(DIFFICULTY_ORDER)
    elif key in (curses.KEY_DOWN, ord("s"), ord("S"), ord("j"), ord("J")):
        ui.setup_diff_idx = (ui.setup_diff_idx + 1) % len(DIFFICULTY_ORDER)
    elif key in (ord("1"), ord("2"), ord("3"), ord("4")):
        ui.setup_diff_idx = key - ord("1")
    elif key in (curses.KEY_LEFT, ord("a"), ord("A"), ord("h"), ord("H")):
        ui.setup_map_idx = (ui.setup_map_idx - 1) % len(MAPS)
    elif key in (curses.KEY_RIGHT, ord("d"), ord("D"), ord("l"), ord("L"), ord("m"), ord("M")):
        ui.setup_map_idx = (ui.setup_map_idx + 1) % len(MAPS)
    elif key in (ord("\n"), ord("\r"), curses.KEY_ENTER, ord(" ")):
        diff_key = DIFFICULTY_ORDER[ui.setup_diff_idx]
        run_perks = profile.consume_perks_for_run()
        ui.mode = "play"
        ui.return_mode = "play"
        return False, GameState(
            map_index=ui.setup_map_idx,
            difficulty_key=diff_key,
            profile=profile,
            run_perks=run_perks,
        )
    return False, None


def handle_gacha_key(profile: PlayerProfile, ui: UIState, key: int) -> bool:
    if key in (ord("q"), ord("Q")):
        return True
    if key in (ord("g"), ord("G"), 27):
        ui.mode = "setup"
        return False
    if key in (ord("i"), ord("I")):
        ui.inv_msg = ""
        ui.mode = "inventory"
        return False
    if key in (curses.KEY_LEFT, ord("h"), ord("H")):
        ui.banner_idx = (ui.banner_idx - 1) % len(BANNER_ORDER)
        return False
    if key in (curses.KEY_RIGHT, ord("l"), ord("L"), 9):  # 9 = Tab
        ui.banner_idx = (ui.banner_idx + 1) % len(BANNER_ORDER)
        return False
    if key in (ord("a"), ord("A")):
        profile.cycle_auto_sell()
        return False

    banner_key = BANNER_ORDER[ui.banner_idx % len(BANNER_ORDER)]
    if key == ord("1"):
        ui.gacha_result = summon_one(profile, banner_key=banner_key)
    elif key == ord("2"):
        ui.gacha_result = summon_ten(profile, banner_key=banner_key)
    return False


def handle_inventory_key(profile: PlayerProfile, ui: UIState, key: int) -> bool:
    if key in (ord("q"), ord("Q")):
        return True
    if key in (ord("i"), ord("I"), 27):
        ui.mode = "setup"
        return False
    if key in (ord("g"), ord("G")):
        ui.mode = "gacha"
        return False
    if key in (ord("f"), ord("F")):
        ui.forge_msg = ""
        ui.mode = "forge"
        return False

    ordered = sorted(
        TOWER_ORDER,
        key=lambda k: (0 if profile.inventory.get(k, 0) > 0 else 1, -RARITY_ORDER.index(TOWER_BLUEPRINTS[k].rarity), k),
    )
    if key in (curses.KEY_UP, ord("w"), ord("W"), ord("k"), ord("K")):
        ui.inv_cursor = max(0, ui.inv_cursor - 1)
    elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
        ui.inv_cursor = min(len(ordered) - 1, ui.inv_cursor + 1)
    elif key in (ord(" "), ord("\n"), ord("\r"), curses.KEY_ENTER, ord("e"), ord("E")):
        _, ui.inv_msg = profile.toggle_loadout(ordered[ui.inv_cursor])
    elif key in (ord("u"), ord("U")):
        _, ui.inv_msg = profile.upgrade_unit_star(ordered[ui.inv_cursor], use_dupe=True)
    elif key in (ord("s"), ord("S"), ord("x"), ord("X")):
        _, _, ui.inv_msg = profile.sell_unit(ordered[ui.inv_cursor], 1)
    elif key in (ord("a"), ord("A")):
        sold, gained = profile.sell_all_duplicates()
        ui.inv_msg = f"Sold {sold} duplicate units for +{gained} Coins!" if sold > 0 else "No duplicates to sell."
    return False


def handle_forge_key(profile: PlayerProfile, ui: UIState, key: int) -> bool:
    if key in (ord("q"), ord("Q")):
        return True
    if key in (ord("f"), ord("F"), 27):
        ui.mode = "setup"
        return False
    if key in (ord("i"), ord("I")):
        ui.mode = "inventory"
        return False
    if key == 9:  # Tab
        ui.forge_tab = 1 - ui.forge_tab
        return False
    if key in (curses.KEY_UP, ord("w"), ord("W"), ord("k"), ord("K")):
        if ui.forge_tab == 0:
            ui.forge_fusion_idx = (ui.forge_fusion_idx - 1) % len(FUSION_RECIPES)
        else:
            ui.forge_perk_idx = (ui.forge_perk_idx - 1) % len(SACRIFICE_PERKS)
            ui.forge_unit_idx = 0
    elif key in (curses.KEY_DOWN, ord("s"), ord("S"), ord("j"), ord("J")):
        if ui.forge_tab == 0:
            ui.forge_fusion_idx = (ui.forge_fusion_idx + 1) % len(FUSION_RECIPES)
        else:
            ui.forge_perk_idx = (ui.forge_perk_idx + 1) % len(SACRIFICE_PERKS)
            ui.forge_unit_idx = 0
    elif ui.forge_tab == 1 and key in (curses.KEY_LEFT, ord("a"), ord("A"), ord("h"), ord("H")):
        ui.forge_unit_idx = max(0, ui.forge_unit_idx - 1)
    elif ui.forge_tab == 1 and key in (curses.KEY_RIGHT, ord("d"), ord("D"), ord("l"), ord("L")):
        ui.forge_unit_idx += 1
    elif key in (ord(" "), ord("\n"), ord("\r"), curses.KEY_ENTER):
        if ui.forge_tab == 0:
            _, ui.forge_msg = profile.craft_fusion(FUSION_RECIPES[ui.forge_fusion_idx].key)
        else:
            sel_perk = SACRIFICE_PERKS[ui.forge_perk_idx]
            qual = [
                k
                for k in TOWER_ORDER
                if profile.inventory.get(k, 0) > 0
                and unit_qualifies_for_perk(sel_perk, TOWER_BLUEPRINTS[k], profile.star_of(k))[0]
            ]
            if not qual:
                ui.forge_msg = "No qualifying unit to sacrifice!"
            else:
                uk = qual[ui.forge_unit_idx % len(qual)]
                _, ui.forge_msg = profile.sacrifice_for_perk(sel_perk.key, uk)
    return False


def handle_tavern_key(state: GameState, ui: UIState, key: int) -> bool:
    if key in (ord("g"), ord("G"), 27):
        ui.mode = "play"
        return False
    if key in (ord("q"), ord("Q")):
        return True
    if key in (ord("1"), ord("2"), ord("3"), ord("4"), ord("5")):
        ui.bet_idx = key - ord("1")
        return False

    bet = state.gold if ui.bet_idx == len(BET_AMOUNTS) else BET_AMOUNTS[ui.bet_idx]
    if key in (ord("s"), ord("S")):
        ui.tavern_result = play_slots(state, bet)
    elif key in (ord("h"), ord("H")):
        ui.tavern_result = play_dice(state, bet, "high")
    elif key in (ord("l"), ord("L")):
        ui.tavern_result = play_dice(state, bet, "low")
    elif key == ord("7"):
        ui.tavern_result = play_dice(state, bet, "seven")
    elif key in (ord("c"), ord("C")):
        ui.tavern_result = play_crate(state)
    return False


def handle_bestiary_key(ui: UIState, key: int) -> bool:
    if key in (ord("b"), ord("B"), 27):
        ui.mode = ui.return_mode
        return False
    if key in (ord("q"), ord("Q")):
        return True
    if key in (curses.KEY_UP, ord("w"), ord("W"), ord("k"), ord("K")):
        ui.bestiary_scroll = max(0, ui.bestiary_scroll - 1)
    elif key in (curses.KEY_DOWN, ord("s"), ord("S"), ord("j"), ord("J")):
        ui.bestiary_scroll += 1
    elif key == curses.KEY_PPAGE:
        ui.bestiary_scroll = max(0, ui.bestiary_scroll - 10)
    elif key == curses.KEY_NPAGE:
        ui.bestiary_scroll += 10
    return False


def handle_play_key(state: GameState, ui: UIState, key: int) -> Tuple[bool, GameState]:
    if key in (ord("q"), ord("Q")):
        return True, state
    if key in (ord("r"), ord("R")):
        ui.mass_anchor = None
        ui.paint_mode = False
        ui.mode = "setup"
        return False, state
    if key == 27:  # Esc cancels mass-place / paint
        if ui.mass_anchor is not None or ui.paint_mode:
            ui.mass_anchor = None
            ui.paint_mode = False
            state.log("Cancelled Mass-Place / Paint.")
        return False, state
    if key in (ord("g"), ord("G")):
        ui.mode = "tavern"
        return False, state
    if key in (ord("b"), ord("B")):
        ui.return_mode = "play"
        ui.mode = "bestiary"
        return False, state

    if state.victory and key in (ord("e"), ord("E")):
        state.enter_endless()
        return False, state

    moved = False
    if key in (curses.KEY_LEFT, ord("a"), ord("A"), ord("h"), ord("H")):
        state.move_cursor(-1, 0)
        moved = True
    elif key in (curses.KEY_RIGHT, ord("d"), ord("D"), ord("l"), ord("L")):
        state.move_cursor(1, 0)
        moved = True
    elif key in (curses.KEY_UP, ord("w"), ord("W"), ord("k"), ord("K")):
        state.move_cursor(0, -1)
        moved = True
    elif key in (curses.KEY_DOWN, ord("s"), ord("S"), ord("j"), ord("J")):
        state.move_cursor(0, 1)
        moved = True

    if moved and ui.paint_mode and not state.game_over:
        bp = TOWER_BLUEPRINTS.get(state.selected_tower_kind)
        if bp and state.can_build_at(state.cursor_x, state.cursor_y) and state.gold >= bp.levels[0].cost:
            state.build_tower(state.cursor_x, state.cursor_y, state.selected_tower_kind)
        return False, state

    if ord("1") <= key <= ord("9"):
        idx = key - ord("1")
        if idx < len(state.loadout):
            state.selected_tower_kind = state.loadout[idx]
    elif key == ord("0") and len(state.loadout) >= 10:
        state.selected_tower_kind = state.loadout[9]

    elif key in (ord("z"), ord("Z")):
        if ui.mass_anchor is None:
            ui.paint_mode = False
            ui.mass_anchor = (state.cursor_x, state.cursor_y)
            state.log(f"Mass-Place anchor at ({state.cursor_x},{state.cursor_y}). Move cursor & press [Space] to build or [U] to upgrade.")
        else:
            ui.mass_anchor = None
            state.log("Mass-Place cancelled.")

    elif key in (ord("c"), ord("C")):
        ui.mass_anchor = None
        ui.paint_mode = not ui.paint_mode
        state.log(f"Paint Brush: {'ON (move cursor to auto-build)' if ui.paint_mode else 'OFF'}")
        if ui.paint_mode:
            bp = TOWER_BLUEPRINTS.get(state.selected_tower_kind)
            if bp and state.can_build_at(state.cursor_x, state.cursor_y) and state.gold >= bp.levels[0].cost:
                state.build_tower(state.cursor_x, state.cursor_y, state.selected_tower_kind)

    elif key in (ord(" "), ord("\n"), ord("\r"), curses.KEY_ENTER):
        if ui.mass_anchor is not None:
            ax, ay = ui.mass_anchor
            state.mass_build_rect(ax, ay, state.cursor_x, state.cursor_y, state.selected_tower_kind)
            ui.mass_anchor = None
        else:
            pos = (state.cursor_x, state.cursor_y)
            if pos in state.towers:
                state.upgrade_tower(*pos)
            else:
                state.build_tower(state.cursor_x, state.cursor_y, state.selected_tower_kind)

    elif key in (ord("u"), ord("U")):
        if ui.mass_anchor is not None:
            ax, ay = ui.mass_anchor
            state.mass_upgrade_rect(ax, ay, state.cursor_x, state.cursor_y)
            ui.mass_anchor = None
        else:
            state.upgrade_tower(state.cursor_x, state.cursor_y)

    elif key in (ord("x"), ord("X"), curses.KEY_BACKSPACE, 127, 8, curses.KEY_DC):
        state.sell_tower(state.cursor_x, state.cursor_y)

    elif key in (ord("t"), ord("T")):
        state.cycle_tower_targeting(state.cursor_x, state.cursor_y)

    elif key in (ord("n"), ord("N")):
        state.start_next_wave()

    elif key in (ord("v"), ord("V")):
        state.toggle_auto_start()

    elif key in (ord("p"), ord("P")):
        if not state.game_over:
            state.paused = not state.paused
            state.log("Paused." if state.paused else "Resumed.")

    elif key in (ord("f"), ord("F")):
        state.cycle_speed()

    elif key in (ord("m"), ord("M")):
        state.switch_map(1)

    return False, state


def run_app(stdscr: curses.window, quick_start: bool = False) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.nodelay(True)
    stdscr.keypad(True)
    stdscr.timeout(33)

    has_colors = init_colors()
    profile = PlayerProfile.load()
    ui = UIState()
    state = GameState(profile=profile)
    if quick_start:
        ui.mode = "play"
        ui.return_mode = "play"
    last_time = time.monotonic()

    while True:
        now = time.monotonic()
        dt = min(0.1, max(0.0, now - last_time))
        last_time = now

        key = stdscr.getch()
        while key != -1:
            if ui.mode == "setup":
                quit_now, new_state = handle_setup_key(profile, ui, key)
                if quit_now:
                    return
                if new_state is not None:
                    state = new_state
                    ui.tavern_result = None
            elif ui.mode == "gacha":
                if handle_gacha_key(profile, ui, key):
                    return
            elif ui.mode == "inventory":
                if handle_inventory_key(profile, ui, key):
                    return
            elif ui.mode == "forge":
                if handle_forge_key(profile, ui, key):
                    return
            elif ui.mode == "tavern":
                if handle_tavern_key(state, ui, key):
                    return
            elif ui.mode == "bestiary":
                if handle_bestiary_key(ui, key):
                    return
            else:
                quit_now, state = handle_play_key(state, ui, key)
                if quit_now:
                    return
            key = stdscr.getch()

        if ui.mode in ("play", "tavern") or (ui.mode == "bestiary" and ui.return_mode == "play"):
            state.tick(dt, in_modal=(ui.mode in ("tavern", "bestiary")))

        if ui.mode == "setup":
            render_setup(stdscr, profile, ui, has_colors)
        elif ui.mode == "gacha":
            render_gacha(stdscr, profile, ui, has_colors)
        elif ui.mode == "inventory":
            render_inventory(stdscr, profile, ui, has_colors)
        elif ui.mode == "forge":
            render_forge(stdscr, profile, ui, has_colors)
        elif ui.mode == "bestiary" and ui.return_mode == "setup":
            stdscr.erase()
            render_bestiary_modal(stdscr, ui, has_colors)
            stdscr.refresh()
        else:
            render_game(stdscr, state, ui, has_colors)
        time.sleep(0.015)

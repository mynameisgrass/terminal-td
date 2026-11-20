// Core TD + Gacha + Profile engine for Web & iOS
(function () {
  const D = window.TD_DATA;
  const SAVE_KEY = "terminal_td_ios_save_v1";
  const LANE_OFFSETS = [-0.42, 0.0, 0.42];
  const SPEED_OPTIONS = [1, 2, 3, 5, 10];
  const AUTO_SELL_MODES = ["off", "dupes_c", "dupes_cr", "dupes_cre", "dupes_all", "all_c", "all_cr"];
  const AUTO_SELL_LABELS = {
    off: "OFF",
    dupes_c: "Dupes: Common",
    dupes_cr: "Dupes: C+Rare",
    dupes_cre: "Dupes: C+R+Epic",
    dupes_all: "Dupes: EVERY",
    all_c: "ALL Common",
    all_cr: "ALL C+Rare",
  };
  const TARGET_MODES = ["first", "strongest", "closest"];
  const MAX_ACTIVE_ENEMIES_SPAWN = 120;
  const MAX_ACTIVE_ALLIES = 36;
  const MAX_SHOT_EFFECTS = 45;
  const BUCKET_W = 18;
  const BUCKET_H = 9;
  const NUM_BUCKETS = BUCKET_W * BUCKET_H;

  function createProfile() {
    const fallback = () => {
      const inv = {};
      for (const k of D.STARTER_LOADOUT) inv[k] = 1;
      return {
        coins: D.STARTING_COINS,
        inventory: inv,
        loadout: [...D.STARTER_LOADOUT],
        unit_stars: {},
        active_perks: [],
        auto_sell_mode: "off",
        pity_counter: 0,
        total_summons: 0,
        total_wins: 0,
        best_wave: 0,
      };
    };

    try {
      const rawStr = localStorage.getItem(SAVE_KEY);
      if (!rawStr) {
        const p = fallback();
        saveProfile(p);
        return p;
      }
      const raw = JSON.parse(rawStr);
      const inv = {};
      for (const [k, v] of Object.entries(raw.inventory || {})) {
        if (D.TOWERS[k] && Number(v) > 0) inv[k] = Math.floor(Number(v));
      }
      if (Object.keys(inv).length === 0) {
        for (const k of D.STARTER_LOADOUT) inv[k] = 1;
      }
      const activePerks = Array.isArray(raw.active_perks)
        ? raw.active_perks.filter((p) => p && Number(p.runs_left) > 0)
        : [];
      const slotBonus = activePerks.reduce(
        (s, p) => (p.perk_type === "slot_bonus" ? s + Number(p.value || 0) : s),
        0
      );
      const effMax = Math.min(D.MAX_PERK_LOADOUT || 10, D.MAX_LOADOUT + slotBonus);
      const seen = new Set();
      const loadout = [];
      for (const k of raw.loadout || []) {
        if (inv[k] > 0 && D.TOWERS[k] && !seen.has(k) && loadout.length < effMax) {
          seen.add(k);
          loadout.push(k);
        }
      }
      if (loadout.length === 0) {
        for (const k of Object.keys(inv).slice(0, effMax)) loadout.push(k);
      }
      const unitStars = {};
      for (const [k, v] of Object.entries(raw.unit_stars || {})) {
        if (D.TOWERS[k] && Number(v) > 1) {
          unitStars[k] = Math.min(D.MAX_UNIT_STAR || 5, Math.max(1, Math.floor(Number(v))));
        }
      }
      const asm = AUTO_SELL_MODES.includes(raw.auto_sell_mode) ? raw.auto_sell_mode : "off";
      return {
        coins: Math.max(0, Math.floor(Number(raw.coins ?? D.STARTING_COINS))),
        inventory: inv,
        loadout,
        unit_stars: unitStars,
        active_perks: activePerks,
        auto_sell_mode: asm,
        pity_counter: Math.max(0, Math.floor(Number(raw.pity_counter || 0))),
        total_summons: Math.max(0, Math.floor(Number(raw.total_summons || 0))),
        total_wins: Math.max(0, Math.floor(Number(raw.total_wins || 0))),
        best_wave: Math.max(0, Math.floor(Number(raw.best_wave || 0))),
      };
    } catch (_) {
      return fallback();
    }
  }

  function saveProfile(profile) {
    try {
      localStorage.setItem(SAVE_KEY, JSON.stringify(profile));
    } catch (_) {}
  }

  function ownedTotal(profile) {
    return Object.values(profile.inventory).reduce((a, b) => a + b, 0);
  }

  function starOf(profile, key) {
    return Math.min(D.MAX_UNIT_STAR || 5, Math.max(1, Math.floor(Number((profile.unit_stars && profile.unit_stars[key]) || 1))));
  }

  function effectiveMaxLoadout(profile) {
    const bonus = (profile.active_perks || []).reduce(
      (s, p) => (p.perk_type === "slot_bonus" && Number(p.runs_left) > 0 ? s + Number(p.value || 0) : s),
      0
    );
    return Math.min(D.MAX_PERK_LOADOUT || 10, D.MAX_LOADOUT + bonus);
  }

  function starUpgradeCoinCost(rarity, nextStar, hasDupe) {
    const base = (D.STAR_BASE_COSTS && D.STAR_BASE_COSTS[nextStar]) || 1200;
    const mult = (D.RARITY_STAR_MULT && D.RARITY_STAR_MULT[rarity]) || 1.0;
    const full = Math.round((base * mult) / 10) * 10;
    return hasDupe ? Math.max(20, Math.ceil(full / 2)) : Math.max(30, full);
  }

  function unitQualifiesForPerk(perk, bp, starLevel) {
    if ((perk.preferred_units || []).includes(bp.key)) return { ok: true, msg: "" };
    const rIdx = D.RARITY_ORDER.indexOf(bp.rarity);
    const reqIdx = D.RARITY_ORDER.indexOf(perk.min_rarity);
    if (perk.key === "monarch_slot") {
      if (bp.rarity === "transcendent" && starLevel >= perk.min_star_override) return { ok: true, msg: "" };
      return { ok: false, msg: `Requires Monarch Core or ★${perk.min_star_override}+ Transcendent unit.` };
    }
    if (rIdx >= reqIdx) return { ok: true, msg: "" };
    if (rIdx === reqIdx - 1 && starLevel >= Math.max(2, perk.min_star_override || 2)) return { ok: true, msg: "" };
    return { ok: false, msg: `Requires ${D.RARITIES[perk.min_rarity].label}+ unit.` };
  }

  function shouldAutoSell(profile, key, ownedBefore) {
    const mode = profile.auto_sell_mode;
    if (mode === "off" || !D.TOWERS[key]) return false;
    const rar = D.TOWERS[key].rarity;
    if (mode === "dupes_c") return ownedBefore > 0 && rar === "common";
    if (mode === "dupes_cr") return ownedBefore > 0 && (rar === "common" || rar === "rare");
    if (mode === "dupes_cre") return ownedBefore > 0 && ["common", "rare", "epic"].includes(rar);
    if (mode === "dupes_all") return ownedBefore > 0;
    if (mode === "all_c") return rar === "common" && ownedTotal(profile) >= 1;
    if (mode === "all_cr") return (rar === "common" || rar === "rare") && ownedTotal(profile) >= 1;
    return false;
  }

  function cycleAutoSell(profile) {
    const idx = AUTO_SELL_MODES.indexOf(profile.auto_sell_mode);
    profile.auto_sell_mode = AUTO_SELL_MODES[(idx + 1) % AUTO_SELL_MODES.length];
    saveProfile(profile);
    return profile.auto_sell_mode;
  }

  function toggleLoadout(profile, key) {
    if (!profile.inventory[key]) return { ok: false, msg: "You don't own that unit." };
    const bp = D.TOWERS[key];
    const maxSlots = effectiveMaxLoadout(profile);
    const idx = profile.loadout.indexOf(key);
    if (idx >= 0) {
      if (profile.loadout.length <= 1) return { ok: false, msg: "Keep at least 1 unit in Loadout!" };
      profile.loadout.splice(idx, 1);
      saveProfile(profile);
      return { ok: true, msg: `Unequipped ${bp.name}.` };
    }
    if (profile.loadout.length >= maxSlots) {
      return { ok: false, msg: `Loadout full (max ${maxSlots})!` };
    }
    profile.loadout.push(key);
    saveProfile(profile);
    return { ok: true, msg: `Equipped ${bp.name} into slot ${profile.loadout.length}!` };
  }

  function sellUnit(profile, key, qty = 1) {
    const owned = profile.inventory[key] || 0;
    if (owned < qty || qty <= 0) return { ok: false, msg: "Not enough copies." };
    if (ownedTotal(profile) - qty < 1) return { ok: false, msg: "Cannot sell your very last unit!" };
    const bp = D.TOWERS[key];
    const gain = D.RARITIES[bp.rarity].sell_coins * qty;
    const rem = owned - qty;
    if (rem <= 0) {
      delete profile.inventory[key];
      const lidx = profile.loadout.indexOf(key);
      if (lidx >= 0) {
        profile.loadout.splice(lidx, 1);
        if (profile.loadout.length === 0) {
          const first = Object.keys(profile.inventory)[0];
          if (first) profile.loadout.push(first);
        }
      }
    } else {
      profile.inventory[key] = rem;
    }
    profile.coins += gain;
    saveProfile(profile);
    return { ok: true, gain, msg: `Sold ${qty}x ${bp.name} for +${gain} Coins!` };
  }

  function sellAllDuplicates(profile) {
    let sold = 0;
    let gained = 0;
    for (const k of Object.keys(profile.inventory)) {
      const c = profile.inventory[k];
      if (c > 1) {
        const dupes = c - 1;
        gained += D.RARITIES[D.TOWERS[k].rarity].sell_coins * dupes;
        sold += dupes;
        profile.inventory[k] = 1;
      }
    }
    if (sold > 0) {
      profile.coins += gained;
      saveProfile(profile);
    }
    return { sold, gained };
  }

  function _consumeOneCopy(profile, key) {
    const rem = (profile.inventory[key] || 0) - 1;
    if (rem <= 0) {
      delete profile.inventory[key];
      if (profile.unit_stars) delete profile.unit_stars[key];
      const lidx = profile.loadout.indexOf(key);
      if (lidx >= 0) {
        profile.loadout.splice(lidx, 1);
        if (profile.loadout.length === 0) {
          const first = Object.keys(profile.inventory)[0];
          if (first) profile.loadout.push(first);
        }
      }
    } else {
      profile.inventory[key] = rem;
    }
  }

  function upgradeUnitStar(profile, key, useDupe = true) {
    const owned = profile.inventory[key] || 0;
    if (owned <= 0 || !D.TOWERS[key]) return { ok: false, msg: "You don't own this unit." };
    const curStar = starOf(profile, key);
    const maxStar = D.MAX_UNIT_STAR || 5;
    if (curStar >= maxStar) return { ok: false, msg: `${D.TOWERS[key].name} is already MAX ★${maxStar}!` };
    const bp = D.TOWERS[key];
    const hasDupe = useDupe && owned >= 2;
    const cost = starUpgradeCoinCost(bp.rarity, curStar + 1, hasDupe);
    if (profile.coins < cost) return { ok: false, msg: `Need ${cost}c to Star-Up ${bp.name} (have ${profile.coins}c).` };
    profile.coins -= cost;
    if (hasDupe) profile.inventory[key] = owned - 1;
    if (!profile.unit_stars) profile.unit_stars = {};
    profile.unit_stars[key] = curStar + 1;
    saveProfile(profile);
    return { ok: true, msg: `${bp.name} upgraded to ★${curStar + 1} (${cost}c${hasDupe ? ", 1 dupe -50%" : ""})!` };
  }

  function craftFusion(profile, recipeKey) {
    const recipe = (D.FUSION_RECIPES || []).find((r) => r.key === recipeKey);
    if (!recipe || !D.TOWERS[recipe.output_key]) return { ok: false, msg: "Unknown fusion recipe." };
    const ca = profile.inventory[recipe.ing_a] || 0;
    const cb = profile.inventory[recipe.ing_b] || 0;
    const bpa = D.TOWERS[recipe.ing_a];
    const bpb = D.TOWERS[recipe.ing_b];
    const bpo = D.TOWERS[recipe.output_key];
    if (recipe.ing_a === recipe.ing_b ? ca < 2 : ca < 1 || cb < 1) {
      return { ok: false, msg: `Need ${bpa.name} + ${bpb.name} to fuse ${bpo.name}.` };
    }
    if (profile.coins < recipe.coin_cost) {
      return { ok: false, msg: `Need ${recipe.coin_cost}c to craft ${bpo.name}!` };
    }
    profile.coins -= recipe.coin_cost;
    _consumeOneCopy(profile, recipe.ing_a);
    _consumeOneCopy(profile, recipe.ing_b);
    profile.inventory[recipe.output_key] = (profile.inventory[recipe.output_key] || 0) + 1;
    if (profile.loadout.length < effectiveMaxLoadout(profile) && !profile.loadout.includes(recipe.output_key)) {
      profile.loadout.push(recipe.output_key);
    }
    saveProfile(profile);
    if (window.TDAudio) window.TDAudio.playGacha(true);
    return { ok: true, msg: `FUSION SUCCESS! Forged [${D.RARITIES[bpo.rarity].label}] ${bpo.name}!` };
  }

  function sacrificeForPerk(profile, perkKey, unitKey) {
    const perk = (D.SACRIFICE_PERKS || []).find((p) => p.key === perkKey);
    if (!perk) return { ok: false, msg: "Unknown Altar perk." };
    const owned = profile.inventory[unitKey] || 0;
    if (owned <= 0 || !D.TOWERS[unitKey]) return { ok: false, msg: "Unit not owned." };
    if (ownedTotal(profile) <= 1) return { ok: false, msg: "Cannot sacrifice your very last unit!" };
    const bp = D.TOWERS[unitKey];
    const star = starOf(profile, unitKey);
    const q = unitQualifiesForPerk(perk, bp, star);
    if (!q.ok) return { ok: false, msg: q.msg };
    if (!profile.active_perks) profile.active_perks = [];

    const runs = perk.duration_runs + (star >= 3 ? 1 : 0);
    if (perk.perk_type === "slot_bonus") {
      const curSlots = profile.active_perks.reduce((s, p) => (p.perk_type === "slot_bonus" ? s + Number(p.value || 0) : s), 0);
      if (curSlots >= 2) {
        for (const p of profile.active_perks) {
          if (p.perk_type === "slot_bonus") p.runs_left = Math.max(Number(p.runs_left || 0), runs);
        }
        _consumeOneCopy(profile, unitKey);
        saveProfile(profile);
        return { ok: true, msg: `Sacrificed ${bp.name} ★${star} to extend +2 Slots!` };
      }
    }

    let val = Number(perk.value);
    const rIdx = D.RARITY_ORDER.indexOf(bp.rarity);
    if (perk.key === "war_chest" && rIdx >= D.RARITY_ORDER.indexOf("mythic")) val = 225;
    else if (perk.key === "titan_heart" && rIdx >= D.RARITY_ORDER.indexOf("legendary")) val = 18;
    else if (perk.key === "fortune_crown" && rIdx >= D.RARITY_ORDER.indexOf("mythic")) val = 0.6;
    else if (perk.key === "chrono_overclock" && bp.rarity === "transcendent") val = 0.28;

    _consumeOneCopy(profile, unitKey);
    if (perk.perk_type === "slot_bonus") {
      profile.active_perks.push({
        perk_key: perk.key,
        name: perk.name,
        perk_type: perk.perk_type,
        value: Math.round(val),
        runs_left: runs,
        source_name: bp.name,
      });
    } else {
      const ex = profile.active_perks.find((p) => p.perk_key === perk.key);
      if (ex) {
        ex.value = Math.max(Number(ex.value || 0), val);
        ex.runs_left = Math.max(Number(ex.runs_left || 0), runs);
        ex.source_name = bp.name;
      } else {
        profile.active_perks.push({
          perk_key: perk.key,
          name: perk.name,
          perk_type: perk.perk_type,
          value: val,
          runs_left: runs,
          source_name: bp.name,
        });
      }
    }
    saveProfile(profile);
    if (window.TDAudio) window.TDAudio.playUpgrade();
    return { ok: true, msg: `ALTAR BLESSING: Sacrificed ${bp.name} ★${star} -> ${perk.name} (${runs} runs)!` };
  }

  function consumePerksForRun(profile) {
    const snap = {
      slot_bonus: 0,
      start_gold: 0,
      extra_lives: 0,
      dmg_mult: 1.0,
      spd_mult: 1.0,
      coin_mult: 1.0,
      cost_mult: 1.0,
      labels: [],
    };
    const nextPerks = [];
    for (const p of profile.active_perks || []) {
      const runs = Math.floor(Number(p.runs_left || 0));
      if (runs <= 0) continue;
      const val = Number(p.value || 0);
      if (p.perk_type === "slot_bonus") snap.slot_bonus += Math.round(val);
      else if (p.perk_type === "start_gold") snap.start_gold += Math.round(val);
      else if (p.perk_type === "extra_lives") snap.extra_lives += Math.round(val);
      else if (p.perk_type === "dps_overclock") {
        snap.dmg_mult += val;
        snap.spd_mult += val * 0.75;
      } else if (p.perk_type === "coin_mult") snap.coin_mult += val;
      else if (p.perk_type === "cost_discount") snap.cost_mult = Math.max(0.65, snap.cost_mult - val);
      snap.labels.push(`${p.name} (${runs}r)`);
      if (runs - 1 > 0) nextPerks.push({ ...p, runs_left: runs - 1 });
    }
    profile.active_perks = nextPerks;
    const effMax = effectiveMaxLoadout(profile);
    if (profile.loadout.length > effMax) profile.loadout = profile.loadout.slice(0, effMax);
    saveProfile(profile);
    return snap;
  }

  function rollBannerUnit(banner, minRarity) {
    const minIdx = D.RARITY_ORDER.indexOf(minRarity);
    const allowed = new Set(D.RARITY_ORDER.slice(minIdx));
    const featured = new Set(banner.featured_keys || []);
    const byRar = {};
    for (const r of allowed) byRar[r] = [];
    for (const k of D.TOWER_ORDER) {
      const r = D.TOWERS[k].rarity;
      if (allowed.has(r)) byRar[r].push(k);
    }
    const pool = [];
    let totalW = 0;
    for (const [r, keys] of Object.entries(byRar)) {
      const rw = banner.rarity_weights[r] || 0;
      if (rw <= 0 || keys.length === 0) continue;
      const weights = keys.map((k) => (featured.has(k) ? banner.featured_boost : 1));
      const sumW = weights.reduce((a, b) => a + b, 0);
      for (let i = 0; i < keys.length; i++) {
        const w = rw * (weights[i] / sumW);
        pool.push([keys[i], w]);
        totalW += w;
      }
    }
    let roll = Math.random() * totalW;
    for (const [k, w] of pool) {
      roll -= w;
      if (roll <= 0) return k;
    }
    return pool[pool.length - 1][0];
  }

  function summonBanner(profile, bannerKey, count) {
    const banner = D.BANNERS[bannerKey] || D.BANNERS.standard;
    const cost = count === 1 ? banner.single_cost : banner.multi_cost;
    if (profile.coins < cost) {
      return { ok: false, pulls: [], message: `Need ${cost} Coins (have ${profile.coins}).` };
    }
    profile.coins -= cost;
    const pulls = [];
    let autoSoldCount = 0;
    let autoSoldCoins = 0;
    let hasHigh = false;

    for (let i = 0; i < count; i++) {
      profile.pity_counter += 1;
      let minRar = "common";
      if (profile.pity_counter >= banner.pity_mythic_at) minRar = "mythic";
      else if (count >= 10 && i === count - 1) minRar = banner.min_10x_rarity;

      const key = rollBannerUnit(banner, minRar);
      const bp = D.TOWERS[key];
      if (bp.rarity === "mythic" || bp.rarity === "transcendent") {
        profile.pity_counter = 0;
        hasHigh = true;
      } else if (bp.rarity === "legendary") {
        hasHigh = true;
      }

      const ownedBefore = profile.inventory[key] || 0;
      const isNew = ownedBefore === 0;
      if (shouldAutoSell(profile, key, ownedBefore)) {
        const sc = D.RARITIES[bp.rarity].sell_coins;
        profile.coins += sc;
        autoSoldCount++;
        autoSoldCoins += sc;
        pulls.push({ key, name: bp.name, rarity: bp.rarity, role: bp.role, isNew: false, autoSoldCoins: sc });
      } else {
        profile.inventory[key] = ownedBefore + 1;
        if (profile.loadout.length < D.MAX_LOADOUT && !profile.loadout.includes(key)) {
          profile.loadout.push(key);
        }
        pulls.push({ key, name: bp.name, rarity: bp.rarity, role: bp.role, isNew, autoSoldCoins: 0 });
      }
    }
    profile.total_summons += count;
    saveProfile(profile);
    if (window.TDAudio) window.TDAudio.playGacha(hasHigh);

    const best = pulls.reduce((a, b) =>
      D.RARITY_ORDER.indexOf(b.rarity) > D.RARITY_ORDER.indexOf(a.rarity) ? b : a
    );
    const autoNote = autoSoldCount > 0 ? ` | Auto-sold ${autoSoldCount} (+${autoSoldCoins}c)` : "";
    return {
      ok: true,
      pulls,
      autoSoldCount,
      autoSoldCoins,
      message: `${count}x ${banner.name}: Best ${best.name} (${D.RARITIES[best.rarity].label})!${autoNote}`,
    };
  }

  function buildWaveQueue(waveNum) {
    const entries = [];
    if (waveNum <= D.WAVES.length) {
      for (const [kind, count, interval] of D.WAVES[waveNum - 1]) {
        for (let i = 0; i < count; i++) {
          entries.push({ kind, delay: entries.length === 0 && i === 0 ? 0.2 : interval, hpScale: 1 });
        }
      }
      return entries;
    }
    const extra = waveNum - D.WAVES.length;
    const hpScale = Math.pow(1.14, Math.min(extra, 15)) * (1 + Math.max(0, extra - 15) * 0.35);
    const cScale = Math.min(extra, 18);
    const groups = [
      ["void_stalker", 14 + cScale, 0.25],
      ["chrono_knight", 10 + cScale, 0.36],
      ["colossus", 8 + Math.floor(cScale / 2), 0.65],
      ["behemoth", 7 + Math.floor(cScale / 2), 0.75],
      [extra % 2 === 1 ? "boss_chronos" : "boss_omega", Math.min(5, 1 + Math.floor(extra / 5)), 1.9],
    ];
    for (const [kind, count, interval] of groups) {
      for (let i = 0; i < count; i++) {
        entries.push({ kind, delay: entries.length === 0 && i === 0 ? 0.2 : interval, hpScale });
      }
    }
    return entries;
  }

  class GameBattle {
    constructor(mapIndex, difficultyKey, profile, runPerks = null) {
      this.profile = profile;
      this.width = D.GRID_WIDTH;
      this.height = D.GRID_HEIGHT;
      this.difficulty = D.DIFFICULTIES[difficultyKey] || D.DIFFICULTIES.normal;
      this.mapDef = D.MAPS[mapIndex % D.MAPS.length];
      this.centerline = this.mapDef.centerline;
      this.roadSet = new Set(this.mapDef.road_cells.map(([x, y]) => `${x},${y}`));
      this.spawnSet = new Set(this.mapDef.spawn_cells.map(([x, y]) => `${x},${y}`));
      this.baseSet = new Set(this.mapDef.base_cells.map(([x, y]) => `${x},${y}`));

      const perks = runPerks || {};
      this.perkDmgMult = Number(perks.dmg_mult || 1.0);
      this.perkSpdMult = Number(perks.spd_mult || 1.0);
      this.perkCoinMult = Number(perks.coin_mult || 1.0);
      this.perkCostMult = Number(perks.cost_mult || 1.0);
      this.perkLabels = perks.labels || [];
      this.unitStars = { ...(profile.unit_stars || {}) };

      const effMaxSlots = Math.min(D.MAX_PERK_LOADOUT || 10, D.MAX_LOADOUT + Math.round(Number(perks.slot_bonus || 0)));
      this.loadout = profile.loadout.slice(0, effMaxSlots);
      this.selectedTowerKind = this.loadout[0];

      this.gold = this.difficulty.starting_gold + Math.round(Number(perks.start_gold || 0));
      this.lives = this.difficulty.starting_lives + Math.round(Number(perks.extra_lives || 0));
      this.maxLives = this.lives;
      this.score = 0;
      this.coinsEarned = 0;
      this.wave = 0;
      this.maxWaves = D.WAVES.length;
      this.endless = false;

      this.towers = new Map();
      this.enemies = [];
      this.allies = [];
      this.spikes = new Map();
      this.spawnQueue = [];
      this.spawnTimer = 0;
      this.shots = [];
      this.effects = []; // explosion / pulse rings
      this.floatTexts = []; // +$10, -190, REVIVE!

      this.waveActive = false;
      this.nextWaveTimer = null;
      this.autoStart = false;
      this.waveRushCooldown = 0;
      this.paused = false;
      this.speedMult = 1;
      this.gameOver = false;
      this.victory = false;
      this.selectedCell = null;
      this.nextId = 1;
      this._pxOut = 0;
      this._pyOut = 0;
      this._qBuf = [];
      this.buckets = Array.from({ length: NUM_BUCKETS }, () => []);
      this._buildPathLut();
      this.logs = [`${this.difficulty.name} on ${this.mapDef.name}. Tap grass to build, tap Wave to begin!`];
    }

    log(msg) {
      this.logs.push(msg);
      if (this.logs.length > 8) this.logs.shift();
    }

    towerCost(rawCost) {
      if (this.perkCostMult >= 0.999) return rawCost;
      return Math.max(10, Math.round((rawCost * this.perkCostMult) / 5) * 5);
    }

    awardCoins(base) {
      const gained = Math.max(1, Math.round(base * this.difficulty.coin_mult * this.perkCoinMult));
      this.coinsEarned += gained;
      this.profile.coins += gained;
      this.profile.best_wave = Math.max(this.profile.best_wave, this.wave);
      saveProfile(this.profile);
      return gained;
    }

    canBuildAt(x, y) {
      if (x < 0 || x >= this.width || y < 0 || y >= this.height) return false;
      const key = `${x},${y}`;
      return !this.roadSet.has(key) && !this.towers.has(key);
    }

    recomputeBuffs() {
      const buffers = [];
      for (const t of this.towers.values()) {
        const st = this.towerStats(t);
        if (st.buff_dmg_pct > 0 || st.buff_spd_pct > 0 || st.buff_rng_pct > 0) buffers.push(t);
      }
      for (const t of this.towers.values()) {
        let bd = 0, bs = 0, br = 0;
        for (const buf of buffers) {
          if (buf === t) continue;
          const bst = this.towerStats(buf);
          if (Math.hypot(t.x - buf.x, t.y - buf.y) <= bst.range) {
            bd = Math.max(bd, bst.buff_dmg_pct);
            bs = Math.max(bs, bst.buff_spd_pct);
            br = Math.max(br, bst.buff_rng_pct);
          }
        }
        t.buffDmg = 1 + bd;
        t.buffSpd = 1 + bs;
        t.buffRng = 1 + br;
      }
    }

    towerStats(t) {
      return D.TOWERS[t.kind].levels[t.level - 1];
    }

    buildTower(x, y, kind) {
      if (this.gameOver || !this.canBuildAt(x, y)) return false;
      const bp = D.TOWERS[kind];
      if (!bp) return false;
      const cost = this.towerCost(bp.levels[0].cost);
      if (this.gold < cost) {
        this.log(`Need $${cost} for ${bp.name} (have $${this.gold}).`);
        return false;
      }
      this.gold -= cost;
      const starLevel = Math.min(D.MAX_UNIT_STAR || 5, Math.max(1, Math.floor(Number(this.unitStars[kind] || 1))));
      const t = {
        x, y, kind, level: 1,
        starLevel,
        starDmgMult: 1 + 0.12 * (starLevel - 1),
        starSpdMult: 1 + 0.06 * (starLevel - 1),
        starIncMult: 1 + 0.05 * (starLevel - 1),
        cooldownLeft: 0,
        incomeTimer: bp.levels[0].income_interval || 0,
        spawnTimer: bp.levels[0].spawn_ally_kind ? 0.4 : 0,
        totalInvested: cost,
        kills: 0,
        goldEarned: 0,
        targetMode: "first",
        angle: 0,
        buffDmg: 1, buffSpd: 1, buffRng: 1,
      };
      this.towers.set(`${x},${y}`, t);
      this.recomputeBuffs();
      this.selectedCell = { x, y };
      this.log(`Built ${bp.name} ($${cost}).`);
      if (window.TDAudio) window.TDAudio.playPlace();
      return true;
    }

    upgradeTower(x, y) {
      const t = this.towers.get(`${x},${y}`);
      if (!t || this.gameOver) return false;
      const bp = D.TOWERS[t.kind];
      if (t.level >= bp.levels.length) return false;
      const cost = this.towerCost(bp.levels[t.level].cost);
      if (this.gold < cost) {
        this.log(`Need $${cost} to upgrade ${bp.name}.`);
        return false;
      }
      this.gold -= cost;
      t.level += 1;
      t.totalInvested += cost;
      this.recomputeBuffs();
      this.log(`Upgraded ${bp.name} -> Lv${t.level}!`);
      if (window.TDAudio) window.TDAudio.playUpgrade();
      return true;
    }

    sellTower(x, y) {
      const key = `${x},${y}`;
      const t = this.towers.get(key);
      if (!t || this.gameOver) return false;
      this.towers.delete(key);
      const refund = Math.floor((t.totalInvested * 7) / 10);
      this.gold += refund;
      this.allies = this.allies.filter((a) => a.ownerKey !== key);
      this.recomputeBuffs();
      this.selectedCell = null;
      this.log(`Sold ${D.TOWERS[t.kind].name} for +$${refund}.`);
      if (window.TDAudio) window.TDAudio.playCoin();
      return true;
    }

    cycleTargetMode(x, y) {
      const t = this.towers.get(`${x},${y}`);
      if (!t) return null;
      t.targetMode = TARGET_MODES[(TARGET_MODES.indexOf(t.targetMode) + 1) % TARGET_MODES.length];
      return t.targetMode;
    }

    cycleSpeed() {
      this.speedMult = SPEED_OPTIONS[(SPEED_OPTIONS.indexOf(this.speedMult) + 1) % SPEED_OPTIONS.length];
      this.log(`Speed: ${this.speedMult}x`);
      return this.speedMult;
    }

    toggleAutoStart() {
      this.autoStart = !this.autoStart;
      this.log(`Auto-Start Waves: ${this.autoStart ? "ON" : "OFF"}`);
      if (this.autoStart && !this.waveActive && !this.gameOver && !(this.victory && !this.endless)) {
        if (this.wave === 0 || (this.nextWaveTimer !== null && this.nextWaveTimer > 0.3)) {
          this.nextWaveTimer = 0.25;
        }
      }
      return this.autoStart;
    }

    collectFarmIncome() {
      let sum = 0;
      for (const t of this.towers.values()) {
        const st = this.towerStats(t);
        if (st.income_per_wave > 0) {
          const inc = Math.round(st.income_per_wave * (t.starIncMult || 1));
          sum += inc;
          t.goldEarned += inc;
          this.emitFloat(t.x + 0.5, t.y, `+$${inc}`, "#fbbf24", 0.9);
        }
      }
      return sum;
    }

    startNextWave(forced = false) {
      if (this.gameOver || (this.victory && !this.endless)) return false;

      if (this.waveActive) {
        if (!this.endless && this.wave >= this.maxWaves) return false;
        if (this.waveRushCooldown > 0) return false;
        this.wave += 1;
        const added = buildWaveQueue(this.wave);
        this.spawnQueue.push(...added);
        const bonus = 15 + this.wave * 3 + this.collectFarmIncome();
        this.gold += bonus;
        this.score += bonus * 2;
        this.waveRushCooldown = 1.5;
        this.log(`PRESTART Wave ${this.wave}! +$${bonus} rush Gold!`);
        return true;
      }

      let earlyBonus = 0;
      if (!forced && this.nextWaveTimer !== null && this.nextWaveTimer > 1) {
        earlyBonus = Math.min(35, Math.floor(this.nextWaveTimer));
        this.gold += earlyBonus;
      }
      this.nextWaveTimer = null;
      this.wave += 1;
      this.spawnQueue = buildWaveQueue(this.wave);
      this.spawnTimer = 0;
      this.waveActive = true;
      this.waveRushCooldown = 1.5;
      this.paused = false;
      this.log(`Wave ${this.wave} started! (${this.spawnQueue.length} foes)${earlyBonus > 0 ? ` +$${earlyBonus}` : ""}`);
      return true;
    }

    enterEndless() {
      if (!this.victory || this.gameOver) return false;
      this.endless = true;
      this.victory = false;
      this.nextWaveTimer = this.autoStart ? 0.4 : this.difficulty.auto_wave_delay;
      this.log("ENDLESS MODE UNLOCKED!");
      return true;
    }

    _buildPathLut() {
      const cl = this.centerline;
      const n = cl.length;
      this._maxProg = n - 1;
      this._pathLut = [];
      for (let i = 0; i < n; i++) {
        const [x0, y0] = cl[i];
        const [x1, y1] = cl[Math.min(n - 1, i + 1)];
        const dx = x1 - x0;
        const dy = y1 - y0;
        const len = Math.hypot(dx, dy);
        const nx = len > 1e-6 ? -dy / len : 0;
        const ny = len > 1e-6 ? dx / len : 0;
        this._pathLut.push([x0, y0, dx, dy, nx, ny]);
      }
    }

    _computePos(progress, laneOffset) {
      const maxIdx = this._maxProg;
      const c = progress <= 0 ? 0 : progress >= maxIdx ? maxIdx : progress;
      const i = c >= maxIdx - 1 ? maxIdx - 1 : c | 0;
      const frac = c - i;
      const seg = this._pathLut[i];
      this._pxOut = seg[0] + seg[2] * frac + seg[4] * (laneOffset || 0);
      this._pyOut = seg[1] + seg[3] * frac + seg[5] * (laneOffset || 0);
    }

    entityPos(progress, laneOffset) {
      this._computePos(progress, laneOffset);
      return [this._pxOut, this._pyOut];
    }

    rebuildSpatialGrid() {
      const buckets = this.buckets;
      for (let i = 0; i < NUM_BUCKETS; i++) buckets[i].length = 0;
      for (let i = 0; i < this.enemies.length; i++) {
        const e = this.enemies[i];
        if (e.hp <= 0) continue;
        let bx = (e._px * 0.5) | 0;
        let by = (e._py * 0.5) | 0;
        if (bx < 0) bx = 0;
        else if (bx >= BUCKET_W) bx = BUCKET_W - 1;
        if (by < 0) by = 0;
        else if (by >= BUCKET_H) by = BUCKET_H - 1;
        buckets[by * BUCKET_W + bx].push(e);
      }
    }

    _queryEnemies(cx, cy, radius) {
      const out = this._qBuf;
      out.length = 0;
      let bx0 = ((cx - radius) * 0.5) | 0;
      let bx1 = ((cx + radius) * 0.5) | 0;
      let by0 = ((cy - radius) * 0.5) | 0;
      let by1 = ((cy + radius) * 0.5) | 0;
      if (bx0 < 0) bx0 = 0;
      if (by0 < 0) by0 = 0;
      if (bx1 >= BUCKET_W) bx1 = BUCKET_W - 1;
      if (by1 >= BUCKET_H) by1 = BUCKET_H - 1;
      const buckets = this.buckets;
      for (let by = by0; by <= by1; by++) {
        const rowOff = by * BUCKET_W;
        for (let bx = bx0; bx <= bx1; bx++) {
          const b = buckets[rowOff + bx];
          for (let k = 0; k < b.length; k++) out.push(b[k]);
        }
      }
      return out;
    }

    spawnEnemy(kind, hpScale = 1, progress = 0, laneOffset = null) {
      const tpl = D.UNITS[kind];
      const hp = tpl.max_hp * hpScale * this.difficulty.enemy_hp_mult;
      const lane = laneOffset !== null ? laneOffset : LANE_OFFSETS[this.nextId % LANE_OFFSETS.length];
      const [px, py] = this.entityPos(progress, lane);
      const e = {
        id: this.nextId++,
        tpl,
        hp,
        maxHp: hp,
        speed: tpl.speed * this.difficulty.enemy_speed_mult,
        reward: Math.max(1, Math.round(tpl.reward * this.difficulty.reward_mult)),
        damage: tpl.damage + this.difficulty.extra_leak_damage,
        armorCurrent: tpl.armor,
        progress,
        laneOffset: lane,
        _px: px,
        _py: py,
        slowTimer: 0, slowFactor: 0,
        stunTimer: 0,
        poisonTimer: 0, poisonDps: 0, poisonSource: null,
        shield: 0,
        hitFlash: 0,
        abilityTimer: tpl.boss_ability ? tpl.ability_cooldown * this.difficulty.boss_cd_mult : 0,
        surgeTimer: 0,
        engaged: false,
      };
      this.enemies.push(e);
      if (tpl.is_boss && window.TDAudio) window.TDAudio.playBoss();
      return e;
    }

    spawnAlly(owner, kind) {
      if (this.allies.length >= MAX_ACTIVE_ALLIES) return null;
      const tpl = D.ALLIES[kind];
      if (!tpl) return null;
      const prog = this._maxProg;
      const lane = LANE_OFFSETS[this.nextId % LANE_OFFSETS.length];
      this._computePos(prog, lane);
      const ally = {
        id: this.nextId++,
        tpl,
        ownerKey: `${owner.x},${owner.y}`,
        hp: tpl.max_hp,
        maxHp: tpl.max_hp,
        progress: prog,
        laneOffset: lane,
        _px: this._pxOut,
        _py: this._pyOut,
        revivesLeft: tpl.revives,
        hitFlash: 0,
        reviveFlash: 0,
      };
      this.allies.push(ally);
      return ally;
    }

    applyDamage(enemy, raw, tower, armorPierce = 0, ignoreArmor = false, canEvade = false, executePct = 0) {
      if (enemy.hp <= 0 || raw <= 0) return 0;
      if (canEvade && enemy.tpl.evasion > 0 && Math.random() < enemy.tpl.evasion) {
        const [ex, ey] = this.entityPos(enemy.progress, enemy.laneOffset);
        this.emitFloat(ex + 0.5, ey, "DODGE", "#94a3b8", 0.45);
        return 0;
      }
      let bonus = 0;
      if (executePct > 0) {
        bonus = Math.min(raw * 3, Math.max(0, enemy.maxHp - enemy.hp) * executePct);
      }
      const totalRaw = raw + bonus;
      let dmg = ignoreArmor
        ? totalRaw
        : Math.max(1, totalRaw - enemy.armorCurrent * (1 - Math.max(0, Math.min(1, armorPierce))));

      if (enemy.shield > 0) {
        const abs = Math.min(enemy.shield, dmg);
        enemy.shield -= abs;
        dmg -= abs;
      }
      if (dmg > 0) {
        enemy.hp -= dmg;
        enemy.hitFlash = 0.12;
      }
      if (enemy.hp <= 0) {
        if (tower) tower.kills += 1;
        this.gold += enemy.reward;
        this.score += enemy.reward * 2;
        if (enemy.tpl.is_boss) {
          const coins = this.awardCoins(6 + this.wave);
          this.log(`BOSS SLAIN: ${enemy.tpl.name}! +${coins} Coins!`);
        }
        if (enemy.tpl.split_into && enemy.tpl.split_count > 0) {
          for (let i = 0; i < enemy.tpl.split_count; i++) {
            this.spawnEnemy(enemy.tpl.split_into, 1, Math.max(0, enemy.progress - 0.25 * i), LANE_OFFSETS[i % 3]);
          }
        }
      }
      return dmg;
    }

    triggerBossAbility(boss) {
      const ab = boss.tpl.boss_ability;
      const [bx, by] = this.entityPos(boss.progress, boss.laneOffset);
      if (ab === "surge") {
        boss.surgeTimer = 2.6;
        this.log(`${boss.tpl.name}: SPEED SURGE!`);
      } else if (ab === "spawn_spiders") {
        for (let i = 0; i < 2; i++) this.spawnEnemy("spider", 1, Math.max(0, boss.progress - 0.6 - 0.3 * i));
        this.log(`${boss.tpl.name}: Hatched Spiders!`);
      } else if (ab === "inferno") {
        for (const a of this.allies) {
          if (Math.abs(a.progress - boss.progress) <= 3.0) {
            a.hp -= 120;
            a.hitFlash = 0.2;
          }
        }
        this.emitEffect(bx + 0.5, by + 0.5, 3.0, "#f97316", 0.35);
        this.log(`${boss.tpl.name}: INFERNO WAVE!`);
      } else if (ab === "shield") {
        boss.shield = Math.min(1400, boss.shield + 600);
        this.log(`${boss.tpl.name}: Obsidian Shield (+600)!`);
      } else if (ab === "necromancy") {
        for (let i = 0; i < 3; i++) this.spawnEnemy("skeleton", 1, Math.max(0, boss.progress - 0.5 - 0.4 * i));
        this.log(`${boss.tpl.name}: Raised 3 Skeletons!`);
      } else if (ab === "void") {
        boss.shield = Math.min(2200, boss.shield + 950);
        for (let i = 0; i < 2; i++) this.spawnEnemy("assassin", 1, Math.max(0, boss.progress - 0.5 * (i + 1)));
        this.emitEffect(bx + 0.5, by + 0.5, 2.8, "#c084fc", 0.4);
        this.log(`${boss.tpl.name}: VOID RIFT!`);
      }
    }

    tick(dt, inModal = false) {
      if (this.paused || this.gameOver || (this.victory && !this.endless)) return;
      if (inModal && this.difficulty.pause_in_gamble) return;

      for (const s of this.shots) s.ttl -= dt;
      this.shots = this.shots.filter((s) => s.ttl > 0);
      for (const ef of this.effects) ef.ttl -= dt;
      this.effects = this.effects.filter((ef) => ef.ttl > 0);
      for (const ft of this.floatTexts) {
        ft.ttl -= dt;
        ft.y -= dt * 0.8;
      }
      this.floatTexts = this.floatTexts.filter((ft) => ft.ttl > 0);

      if (!this.waveActive) {
        if (this.autoStart && this.nextWaveTimer === null) this.nextWaveTimer = 0.25;
        if (this.nextWaveTimer !== null) {
          this.nextWaveTimer -= dt * (this.autoStart ? Math.min(this.speedMult, 4) : 1);
          if (this.nextWaveTimer <= 0) this.startNextWave(!this.autoStart);
        }
        return;
      }

      if (this.waveRushCooldown > 0) this.waveRushCooldown = Math.max(0, this.waveRushCooldown - dt);

      const simDt = dt * this.speedMult;
      const steps = Math.min(4, Math.max(1, Math.ceil(simDt / 0.10)));
      const stepDt = simDt / steps;
      for (let i = 0; i < steps; i++) {
        this.step(stepDt, i === steps - 1);
        if (this.gameOver) break;
      }
    }

    emitShot(x0, y0, x1, y1, rarity, kind) {
      if (this.shots.length >= MAX_SHOT_EFFECTS) return;
      this.shots.push({ x0, y0, x1, y1, rarity, kind, ttl: 0.14, maxTtl: 0.14 });
    }

    emitEffect(x, y, r, color, ttl = 0.22) {
      if (this.effects.length >= 22) return;
      this.effects.push({ x, y, r, color, ttl, maxTtl: ttl });
    }

    emitFloat(x, y, text, color, ttl = 0.7) {
      if (this.floatTexts.length >= 24) return;
      this.floatTexts.push({ x, y, text, color, ttl });
    }

    _fireTowerOnce(t, st, effDmg, effRSq, minRSq, emitVisuals) {
      const effR = st.range * t.buffRng;
      const nearby = this._queryEnemies(t.x, t.y, effR);
      let target = null;
      let bestMetric = t.targetMode === "closest" ? 1e12 : -1;

      for (let i = 0; i < nearby.length; i++) {
        const e = nearby[i];
        if (e.hp <= 0) continue;
        const dx = e._px - t.x, dy = e._py - t.y;
        const dSq = dx * dx + dy * dy;
        if (dSq < minRSq || dSq > effRSq) continue;
        if (t.targetMode === "strongest") {
          const val = e.hp + e.shield;
          if (val > bestMetric) { bestMetric = val; target = e; }
        } else if (t.targetMode === "closest") {
          if (dSq < bestMetric) { bestMetric = dSq; target = e; }
        } else {
          if (e.progress > bestMetric) { bestMetric = e.progress; target = e; }
        }
      }
      if (!target) return false;

      const tx = target._px, ty = target._py;
      t.angle = Math.atan2(ty - t.y, tx - t.x);

      if (emitVisuals) {
        this.emitShot(t.x + 0.5, t.y + 0.5, tx + 0.5, ty + 0.5, D.TOWERS[t.kind].rarity, t.kind);
        if (window.TDAudio && Math.random() < 0.28) window.TDAudio.playShoot(t.kind);
      }

      const dealt = this.applyDamage(
        target, effDmg, t, st.armor_pierce, false, st.splash_radius === 0, st.execute_pct
      );
      if (dealt > 0 && st.armor_shred > 0 && target.hp > 0) {
        target.armorCurrent = Math.max(0, target.armorCurrent - st.armor_shred);
      }
      if (st.stun_duration > 0 && target.hp > 0 && !target.tpl.is_boss) {
        target.stunTimer = Math.max(target.stunTimer, st.stun_duration);
      }
      if (st.poison_dps > 0 && target.hp > 0) {
        const sd = st.poison_dps * t.buffDmg;
        if (sd >= target.poisonDps || target.poisonTimer <= 0) {
          target.poisonDps = sd;
          target.poisonSource = t;
        }
        target.poisonTimer = Math.max(target.poisonTimer, st.poison_duration);
      }
      if (st.slow_factor > 0 && target.hp > 0 && !target.tpl.slow_immune) {
        target.slowFactor = Math.max(target.slowFactor, st.slow_factor);
        target.slowTimer = Math.max(target.slowTimer, st.slow_duration);
      }

      if (st.splash_radius > 0) {
        if (emitVisuals) {
          this.emitEffect(tx + 0.5, ty + 0.5, st.splash_radius, st.slow_factor > 0 ? "#38bdf8" : "#f97316", 0.22);
        }
        const srSq = st.splash_radius * st.splash_radius;
        const sDmg = effDmg * st.splash_ratio;
        const splNearby = this._queryEnemies(tx, ty, st.splash_radius);
        for (let i = 0; i < splNearby.length; i++) {
          const other = splNearby[i];
          if (other.id === target.id || other.hp <= 0) continue;
          const dx = other._px - tx, dy = other._py - ty;
          if (dx * dx + dy * dy <= srSq) {
            const sd = this.applyDamage(other, sDmg, t, st.armor_pierce, false, false, st.execute_pct);
            if (sd > 0 && st.armor_shred > 0 && other.hp > 0) {
              other.armorCurrent = Math.max(0, other.armorCurrent - st.armor_shred);
            }
            if (st.slow_factor > 0 && other.hp > 0 && !other.tpl.slow_immune) {
              other.slowFactor = Math.max(other.slowFactor, st.slow_factor);
              other.slowTimer = Math.max(other.slowTimer, st.slow_duration);
            }
            if (st.poison_dps > 0 && other.hp > 0) {
              other.poisonDps = Math.max(other.poisonDps, st.poison_dps * t.buffDmg);
              other.poisonTimer = Math.max(other.poisonTimer, st.poison_duration);
              other.poisonSource = t;
            }
          }
        }
      }

      if (st.chain_count > 1) {
        const hitIds = new Set([target.id]);
        let cx = tx, cy = ty;
        let cdmg = effDmg * st.chain_falloff;
        for (let c = 1; c < st.chain_count; c++) {
          let bestN = null, bestDSq = 14.44; // 3.8^2
          const cands = this._queryEnemies(cx, cy, 3.8);
          for (let i = 0; i < cands.length; i++) {
            const cand = cands[i];
            if (cand.hp <= 0 || hitIds.has(cand.id)) continue;
            const dx = cand._px - cx, dy = cand._py - cy;
            const dSq = dx * dx + dy * dy;
            if (dSq <= bestDSq) {
              bestDSq = dSq; bestN = cand;
            }
          }
          if (!bestN) break;
          hitIds.add(bestN.id);
          if (emitVisuals) {
            this.emitShot(cx + 0.5, cy + 0.5, bestN._px + 0.5, bestN._py + 0.5, D.TOWERS[t.kind].rarity, t.kind);
          }
          this.applyDamage(bestN, cdmg, t, st.armor_pierce, false, false, st.execute_pct);
          if (st.stun_duration > 0 && bestN.hp > 0 && !bestN.tpl.is_boss) {
            bestN.stunTimer = Math.max(bestN.stunTimer, st.stun_duration * 0.7);
          }
          cx = bestN._px; cy = bestN._py; cdmg *= st.chain_falloff;
        }
      }
      return true;
    }

    step(dt, emitVisuals = true) {
      if (this.spawnQueue.length > 0 && this.enemies.length < MAX_ACTIVE_ENEMIES_SPAWN) {
        this.spawnTimer -= dt;
        while (this.spawnQueue.length > 0 && this.spawnTimer <= 0 && this.enemies.length < MAX_ACTIVE_ENEMIES_SPAWN) {
          const ent = this.spawnQueue.shift();
          this.spawnEnemy(ent.kind, ent.hpScale);
          if (this.spawnQueue.length > 0) this.spawnTimer += this.spawnQueue[0].delay;
        }
      }

      // Farms, Spawners, Spikes, Ally Healing
      for (const t of this.towers.values()) {
        const st = this.towerStats(t);
        if (st.income_per_tick > 0 && st.income_interval > 0) {
          t.incomeTimer -= dt;
          if (t.incomeTimer <= 0) {
            t.incomeTimer += st.income_interval;
            const inc = Math.round(st.income_per_tick * (t.starIncMult || 1));
            this.gold += inc;
            t.goldEarned += inc;
            if (emitVisuals) this.emitFloat(t.x + 0.5, t.y, `+$${inc}`, "#fbbf24", 0.7);
          }
        }
        if (st.heal_allies_per_sec > 0 && this.allies.length > 0) {
          const effR = st.range * t.buffRng;
          const effRSq = effR * effR;
          for (const a of this.allies) {
            if (a.hp <= 0 || a.hp >= a.maxHp) continue;
            if (a._px === undefined) {
              this._computePos(a.progress, a.laneOffset);
              a._px = this._pxOut; a._py = this._pyOut;
            }
            const dx = a._px - t.x, dy = a._py - t.y;
            if (dx * dx + dy * dy <= effRSq) {
              a.hp = Math.min(a.maxHp, a.hp + st.heal_allies_per_sec * dt);
            }
          }
        }
        if (st.spawn_ally_kind && st.spawn_interval > 0) {
          const tKey = `${t.x},${t.y}`;
          let owned = 0;
          for (const a of this.allies) {
            if (a.ownerKey === tKey && a.hp > 0) owned++;
          }
          if (owned < st.max_active_allies) {
            t.spawnTimer -= dt;
            if (t.spawnTimer <= 0) {
              t.spawnTimer = st.spawn_interval;
              this.spawnAlly(t, st.spawn_ally_kind);
            }
          }
        }
        if (st.spike_damage > 0 && st.spike_charges > 0) {
          t.cooldownLeft = Math.max(0, t.cooldownLeft - dt);
          if (t.cooldownLeft <= 0) {
            const effRSq = (st.range * t.buffRng) ** 2;
            const avail = [];
            for (const rc of this.mapDef.road_cells) {
              const rk = `${rc[0]},${rc[1]}`;
              if (!this.spikes.has(rk)) {
                const dx = rc[0] - t.x, dy = rc[1] - t.y;
                if (dx * dx + dy * dy <= effRSq) avail.push(rc);
              }
            }
            if (avail.length > 0) {
              const pick = avail[Math.floor(Math.random() * avail.length)];
              this.spikes.set(`${pick[0]},${pick[1]}`, {
                x: pick[0],
                y: pick[1],
                damage: st.spike_damage * t.buffDmg,
                charges: st.spike_charges,
                ownerKey: `${t.x},${t.y}`,
              });
              t.cooldownLeft = st.cooldown / Math.max(0.5, t.buffSpd);
            }
          }
        }
      }

      // Precompute enemy positions once per sub-step + build spatial hash
      for (let i = 0; i < this.enemies.length; i++) {
        const e = this.enemies[i];
        e.engaged = false;
        this._computePos(e.progress, e.laneOffset);
        e._px = this._pxOut;
        e._py = this._pyOut;
      }
      this.rebuildSpatialGrid();

      // Enemy heal auras via spatial grid
      for (let i = 0; i < this.enemies.length; i++) {
        const h = this.enemies[i];
        if (h.hp <= 0 || h.tpl.heal_aura_per_sec <= 0) continue;
        const r = h.tpl.heal_aura_radius;
        const rSq = r * r;
        const nearby = this._queryEnemies(h._px, h._py, r);
        for (let k = 0; k < nearby.length; k++) {
          const a = nearby[k];
          if (a.hp <= 0 || a.hp >= a.maxHp) continue;
          const dx = a._px - h._px, dy = a._py - h._py;
          if (dx * dx + dy * dy <= rSq) {
            a.hp = Math.min(a.maxHp, a.hp + h.tpl.heal_aura_per_sec * dt);
          }
        }
      }

      // Friendly AllyUnits vs Enemies via spatial grid
      for (let i = 0; i < this.allies.length; i++) {
        const a = this.allies[i];
        if (a.hp <= 0) continue;
        a.hitFlash = Math.max(0, a.hitFlash - dt);
        a.reviveFlash = Math.max(0, a.reviveFlash - dt);
        this._computePos(a.progress, a.laneOffset);
        const ax = this._pxOut, ay = this._pyOut;
        a._px = ax; a._py = ay;
        const clash = this._queryEnemies(ax, ay, 2.5);
        let tgt = null;
        for (let k = 0; k < clash.length; k++) {
          const e = clash[k];
          if (e.hp > 0 && Math.abs(e.progress - a.progress) <= 0.95) {
            if (!tgt || e.progress > tgt.progress) tgt = e;
          }
        }
        if (tgt) {
          tgt.engaged = true;
          if (a.tpl.splash_radius > 0) {
            const srSq = a.tpl.splash_radius * a.tpl.splash_radius;
            const spl = this._queryEnemies(ax, ay, Math.max(2.5, a.tpl.splash_radius + 0.5));
            for (let k = 0; k < spl.length; k++) {
              const e = spl[k];
              if (e.hp <= 0 || Math.abs(e.progress - a.progress) > 0.95) continue;
              const dx = e._px - ax, dy = e._py - ay;
              if (dx * dx + dy * dy <= srSq) {
                this.applyDamage(e, a.tpl.atk_dps * dt, null, 0.35);
              }
            }
          } else {
            this.applyDamage(tgt, a.tpl.atk_dps * dt, null, 0.25);
          }
          a.hp -= Math.max(2, tgt.tpl.atk_dps - a.tpl.armor) * dt;
          a.hitFlash = 0.1;
          if (a.hp <= 0 && a.revivesLeft > 0) {
            a.revivesLeft -= 1;
            a.hp = a.maxHp * a.tpl.revive_hp_ratio;
            a.reviveFlash = 0.7;
            const blast = this._queryEnemies(ax, ay, 2.5);
            for (let k = 0; k < blast.length; k++) {
              const e = blast[k];
              if (e.hp <= 0) continue;
              const dx = e._px - ax, dy = e._py - ay;
              if (dx * dx + dy * dy <= 5.76) {
                this.applyDamage(e, a.tpl.revive_blast_dmg, null, 0, true);
              }
            }
            this.emitEffect(ax + 0.5, ay + 0.5, 2.5, "#fbbf24", 0.4);
            this.emitFloat(ax + 0.5, ay, "2ND LIFE!", "#fbbf24", 0.9);
            this.log(`${a.tpl.name} triggered SECOND LIFE!`);
            if (window.TDAudio) window.TDAudio.playRevive();
          }
        } else if (a.progress > 0.35) {
          a.progress = Math.max(0.35, a.progress - a.tpl.speed * dt);
          this._computePos(a.progress, a.laneOffset);
          a._px = this._pxOut; a._py = this._pyOut;
        }
      }
      this.allies = this.allies.filter((a) => a.hp > 0);

      // Move enemies
      const maxProg = this._maxProg;
      const breached = [];
      for (let i = 0; i < this.enemies.length; i++) {
        const e = this.enemies[i];
        if (e.hp <= 0) continue;
        e.hitFlash = Math.max(0, e.hitFlash - dt);
        if (e.slowTimer > 0) {
          e.slowTimer = Math.max(0, e.slowTimer - dt);
          if (e.slowTimer === 0) e.slowFactor = 0;
        }
        e.stunTimer = Math.max(0, e.stunTimer - dt);
        e.surgeTimer = Math.max(0, e.surgeTimer - dt);

        if (e.tpl.regen_per_sec > 0 && e.hp < e.maxHp) {
          e.hp = Math.min(e.maxHp, e.hp + e.tpl.regen_per_sec * dt);
        }
        if (e.poisonTimer > 0) {
          e.poisonTimer = Math.max(0, e.poisonTimer - dt);
          this.applyDamage(e, e.poisonDps * dt, e.poisonSource, 0, true);
          if (e.hp <= 0) continue;
        }
        if (e.tpl.boss_ability) {
          e.abilityTimer -= dt;
          if (e.abilityTimer <= 0) {
            e.abilityTimer = e.tpl.ability_cooldown * this.difficulty.boss_cd_mult;
            this.triggerBossAbility(e);
          }
        }

        if (!e.engaged && e.stunTimer <= 0) {
          let spd = e.speed * (1 - e.slowFactor);
          if (e.tpl.berserk_threshold > 0 && e.hp / e.maxHp <= e.tpl.berserk_threshold) spd *= 1.6;
          if (e.surgeTimer > 0) spd *= 1.65;
          const ck0 = `${Math.round(e._px)},${Math.round(e._py)}`;
          e.progress += spd * dt;
          this._computePos(e.progress, e.laneOffset);
          const px1 = this._pxOut, py1 = this._pyOut;
          e._px = px1;
          e._py = py1;
          if (this.spikes.size > 0) {
            const ck1 = `${Math.round(px1)},${Math.round(py1)}`;
            if (ck1 !== ck0 && this.spikes.has(ck1)) {
              const sp = this.spikes.get(ck1);
              this.applyDamage(e, sp.damage, this.towers.get(sp.ownerKey), 1);
              sp.charges -= 1;
              if (sp.charges <= 0) this.spikes.delete(ck1);
              if (e.hp <= 0) continue;
            }
          }
        }
        if (e.progress >= maxProg) breached.push(e);
      }

      if (breached.length > 0) {
        const bIds = new Set();
        for (const e of breached) {
          bIds.add(e.id);
          this.lives = Math.max(0, this.lives - e.damage);
          this.log(`${e.tpl.name} breached HQ! (-${e.damage} HP)`);
        }
        this.enemies = this.enemies.filter((e) => !bIds.has(e.id));
        if (this.lives <= 0) {
          this.gameOver = true;
          this.waveActive = false;
          this.nextWaveTimer = null;
          const coins = this.awardCoins(Math.max(4, this.wave * 2));
          this.log(`DEFEAT! Earned +${coins} Coins.`);
          return;
        }
      }

      // Rebuild spatial grid with updated enemy positions before towers fire
      this.rebuildSpatialGrid();

      // Towers fire (SpatialGrid + Multi-Shot Cooldown Accumulator + capped visuals)
      for (const t of this.towers.values()) {
        const st = this.towerStats(t);
        if (st.damage <= 0 || st.spike_damage > 0) continue;
        t.cooldownLeft -= dt;
        if (t.cooldownLeft > 0 || this.enemies.length === 0) continue;

        const spdMult = t.buffSpd * (t.starSpdMult || 1) * this.perkSpdMult;
        const dmgMult = t.buffDmg * (t.starDmgMult || 1) * this.perkDmgMult;
        const effCd = Math.max(0.05, st.cooldown / Math.max(0.5, spdMult));
        const shotsReady = Math.min(4, 1 + Math.floor(-t.cooldownLeft / effCd));
        const effDmg = st.damage * dmgMult;
        const effR = st.range * t.buffRng;
        const effRSq = effR * effR;
        const minRSq = st.min_range * st.min_range;
        let fired = 0;

        for (let s = 0; s < shotsReady; s++) {
          const ok = this._fireTowerOnce(t, st, effDmg, effRSq, minRSq, emitVisuals && s === 0);
          if (!ok) break;
          fired++;
        }
        if (fired > 0) {
          t.cooldownLeft = Math.max(0, t.cooldownLeft + fired * effCd);
        } else {
          t.cooldownLeft = 0;
        }
      }

      this.enemies = this.enemies.filter((e) => e.hp > 0);

      // Wave complete
      if (this.waveActive && this.spawnQueue.length === 0 && this.enemies.length === 0) {
        this.waveActive = false;
        const farmGold = this.collectFarmIncome();
        const bonus = 25 + this.wave * 6 + farmGold;
        this.gold += bonus;
        this.score += bonus * 3;
        const coins = this.awardCoins(4 + this.wave);

        if (!this.endless && this.wave >= this.maxWaves) {
          this.victory = true;
          this.nextWaveTimer = null;
          const winCoins = this.awardCoins(120);
          this.profile.total_wins += 1;
          saveProfile(this.profile);
          this.log(`VICTORY! +$${bonus} Gold | +${coins + winCoins} Coins!`);
        } else {
          this.nextWaveTimer = this.autoStart ? 0.4 : this.difficulty.auto_wave_delay;
          this.log(`Wave ${this.wave} cleared! +$${bonus} Gold, +${coins} Coins!`);
        }
      }
    }
  }

  window.TDEngine = {
    AUTO_SELL_LABELS,
    createProfile,
    saveProfile,
    ownedTotal,
    starOf,
    effectiveMaxLoadout,
    starUpgradeCoinCost,
    unitQualifiesForPerk,
    cycleAutoSell,
    toggleLoadout,
    sellUnit,
    sellAllDuplicates,
    upgradeUnitStar,
    craftFusion,
    sacrificeForPerk,
    consumePerksForRun,
    summonBanner,
    GameBattle,
  };
})();

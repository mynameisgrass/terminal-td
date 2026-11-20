// Core TD + Gacha + Profile engine for Web & iOS
(function () {
  const D = window.TD_DATA;
  const SAVE_KEY = "terminal_td_ios_save_v1";
  const LANE_OFFSETS = [-0.42, 0.0, 0.42];
  const SPEED_OPTIONS = [1, 2, 3, 5, 10];
  const AUTO_SELL_MODES = ["off", "dupes_c", "dupes_cr", "dupes_cre", "all_c", "all_cr"];
  const AUTO_SELL_LABELS = {
    off: "OFF",
    dupes_c: "Dupes: Common",
    dupes_cr: "Dupes: C+Rare",
    dupes_cre: "Dupes: C+R+Epic",
    all_c: "ALL Common",
    all_cr: "ALL C+Rare",
  };
  const TARGET_MODES = ["first", "strongest", "closest"];

  function createProfile() {
    const fallback = () => {
      const inv = {};
      for (const k of D.STARTER_LOADOUT) inv[k] = 1;
      return {
        coins: D.STARTING_COINS,
        inventory: inv,
        loadout: [...D.STARTER_LOADOUT],
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
      const seen = new Set();
      const loadout = [];
      for (const k of raw.loadout || []) {
        if (inv[k] > 0 && D.TOWERS[k] && !seen.has(k) && loadout.length < D.MAX_LOADOUT) {
          seen.add(k);
          loadout.push(k);
        }
      }
      if (loadout.length === 0) {
        for (const k of Object.keys(inv).slice(0, D.MAX_LOADOUT)) loadout.push(k);
      }
      const asm = AUTO_SELL_MODES.includes(raw.auto_sell_mode) ? raw.auto_sell_mode : "off";
      return {
        coins: Math.max(0, Math.floor(Number(raw.coins ?? D.STARTING_COINS))),
        inventory: inv,
        loadout,
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

  function shouldAutoSell(profile, key, ownedBefore) {
    const mode = profile.auto_sell_mode;
    if (mode === "off" || !D.TOWERS[key]) return false;
    const rar = D.TOWERS[key].rarity;
    if (mode === "dupes_c") return ownedBefore > 0 && rar === "common";
    if (mode === "dupes_cr") return ownedBefore > 0 && (rar === "common" || rar === "rare");
    if (mode === "dupes_cre") return ownedBefore > 0 && ["common", "rare", "epic"].includes(rar);
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
    const idx = profile.loadout.indexOf(key);
    if (idx >= 0) {
      if (profile.loadout.length <= 1) return { ok: false, msg: "Keep at least 1 unit in Loadout!" };
      profile.loadout.splice(idx, 1);
      saveProfile(profile);
      return { ok: true, msg: `Unequipped ${bp.name}.` };
    }
    if (profile.loadout.length >= D.MAX_LOADOUT) {
      return { ok: false, msg: `Loadout full (max ${D.MAX_LOADOUT})!` };
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
    const hpScale = Math.pow(1.28, extra);
    const groups = [
      ["void_stalker", 14 + extra, 0.3],
      ["chrono_knight", 10 + extra, 0.42],
      ["colossus", 8 + Math.floor(extra / 2), 0.75],
      ["behemoth", 7 + Math.floor(extra / 2), 0.85],
      [extra % 2 === 1 ? "boss_chronos" : "boss_omega", 1 + Math.floor(extra / 3), 2.2],
    ];
    for (const [kind, count, interval] of groups) {
      for (let i = 0; i < count; i++) {
        entries.push({ kind, delay: entries.length === 0 && i === 0 ? 0.2 : interval, hpScale });
      }
    }
    return entries;
  }

  class GameBattle {
    constructor(mapIndex, difficultyKey, profile) {
      this.profile = profile;
      this.width = D.GRID_WIDTH;
      this.height = D.GRID_HEIGHT;
      this.difficulty = D.DIFFICULTIES[difficultyKey] || D.DIFFICULTIES.normal;
      this.mapDef = D.MAPS[mapIndex % D.MAPS.length];
      this.centerline = this.mapDef.centerline;
      this.roadSet = new Set(this.mapDef.road_cells.map(([x, y]) => `${x},${y}`));
      this.spawnSet = new Set(this.mapDef.spawn_cells.map(([x, y]) => `${x},${y}`));
      this.baseSet = new Set(this.mapDef.base_cells.map(([x, y]) => `${x},${y}`));

      this.loadout = profile.loadout.slice(0, D.MAX_LOADOUT);
      this.selectedTowerKind = this.loadout[0];

      this.gold = this.difficulty.starting_gold;
      this.lives = this.difficulty.starting_lives;
      this.maxLives = this.difficulty.starting_lives;
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
      this.logs = [`${this.difficulty.name} on ${this.mapDef.name}. Tap grass to build, tap Wave to begin!`];
    }

    log(msg) {
      this.logs.push(msg);
      if (this.logs.length > 8) this.logs.shift();
    }

    awardCoins(base) {
      const gained = Math.max(1, Math.round(base * this.difficulty.coin_mult));
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
      const cost = bp.levels[0].cost;
      if (this.gold < cost) {
        this.log(`Need $${cost} for ${bp.name} (have $${this.gold}).`);
        return false;
      }
      this.gold -= cost;
      const t = {
        x, y, kind, level: 1,
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
      const cost = bp.levels[t.level].cost;
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
          sum += st.income_per_wave;
          t.goldEarned += st.income_per_wave;
          this.emitFloat(t.x + 0.5, t.y, `+$${st.income_per_wave}`, "#fbbf24", 0.9);
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

    entityPos(progress, laneOffset) {
      const cl = this.centerline;
      const maxIdx = cl.length - 1;
      const c = Math.max(0, Math.min(maxIdx, progress));
      const i = Math.min(maxIdx - 1, Math.floor(c));
      const frac = c - i;
      const [x0, y0] = cl[i];
      const [x1, y1] = cl[Math.min(maxIdx, i + 1)];
      let px = x0 + (x1 - x0) * frac;
      let py = y0 + (y1 - y0) * frac;
      const dx = x1 - x0;
      const dy = y1 - y0;
      const len = Math.hypot(dx, dy);
      if (len > 1e-6 && laneOffset) {
        px += (-dy / len) * laneOffset;
        py += (dx / len) * laneOffset;
      }
      return [px, py];
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
      const tpl = D.ALLIES[kind];
      if (!tpl) return null;
      const ally = {
        id: this.nextId++,
        tpl,
        ownerKey: `${owner.x},${owner.y}`,
        hp: tpl.max_hp,
        maxHp: tpl.max_hp,
        progress: this.centerline.length - 1,
        laneOffset: LANE_OFFSETS[this.nextId % LANE_OFFSETS.length],
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
          const coins = this.awardCoins(14 + this.wave * 2);
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
      const steps = Math.max(1, Math.ceil(simDt / 0.05));
      const stepDt = simDt / steps;
      for (let i = 0; i < steps; i++) {
        this.step(stepDt, i === steps - 1);
        if (this.gameOver) break;
      }
    }

    emitShot(x0, y0, x1, y1, rarity, kind) {
      if (this.shots.length >= 65) return;
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

    step(dt, emitVisuals = true) {
      if (this.spawnQueue.length > 0) {
        this.spawnTimer -= dt;
        while (this.spawnQueue.length > 0 && this.spawnTimer <= 0) {
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
            this.gold += st.income_per_tick;
            t.goldEarned += st.income_per_tick;
            this.emitFloat(t.x + 0.5, t.y, `+$${st.income_per_tick}`, "#fbbf24", 0.7);
          }
        }
        if (st.heal_allies_per_sec > 0 && this.allies.length > 0) {
          const effR = st.range * t.buffRng;
          const effRSq = effR * effR;
          for (const a of this.allies) {
            if (a.hp <= 0 || a.hp >= a.maxHp) continue;
            const [ax, ay] = this.entityPos(a.progress, a.laneOffset);
            const dx = ax - t.x, dy = ay - t.y;
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

      // Precompute enemy positions once per sub-step
      for (const e of this.enemies) {
        e.engaged = false;
        const [px, py] = this.entityPos(e.progress, e.laneOffset);
        e._px = px;
        e._py = py;
      }

      // Enemy heal auras
      for (const h of this.enemies) {
        if (h.hp <= 0 || h.tpl.heal_aura_per_sec <= 0) continue;
        const rSq = h.tpl.heal_aura_radius * h.tpl.heal_aura_radius;
        for (const a of this.enemies) {
          if (a.hp <= 0 || a.hp >= a.maxHp) continue;
          const dx = a._px - h._px, dy = a._py - h._py;
          if (dx * dx + dy * dy <= rSq) {
            a.hp = Math.min(a.maxHp, a.hp + h.tpl.heal_aura_per_sec * dt);
          }
        }
      }

      // Friendly AllyUnits vs Enemies
      for (const a of this.allies) {
        if (a.hp <= 0) continue;
        a.hitFlash = Math.max(0, a.hitFlash - dt);
        a.reviveFlash = Math.max(0, a.reviveFlash - dt);
        let tgt = null;
        for (const e of this.enemies) {
          if (e.hp > 0 && Math.abs(e.progress - a.progress) <= 0.95) {
            if (!tgt || e.progress > tgt.progress) tgt = e;
          }
        }
        if (tgt) {
          tgt.engaged = true;
          const [ax, ay] = this.entityPos(a.progress, a.laneOffset);
          if (a.tpl.splash_radius > 0) {
            const srSq = a.tpl.splash_radius * a.tpl.splash_radius;
            for (const e of this.enemies) {
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
            for (const e of this.enemies) {
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
        }
      }
      this.allies = this.allies.filter((a) => a.hp > 0);

      // Move enemies
      const maxProg = this.centerline.length - 1;
      const breached = [];
      for (const e of this.enemies) {
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
          const [px1, py1] = this.entityPos(e.progress, e.laneOffset);
          e._px = px1;
          e._py = py1;
          const ck1 = `${Math.round(px1)},${Math.round(py1)}`;
          if (ck1 !== ck0 && this.spikes.has(ck1)) {
            const sp = this.spikes.get(ck1);
            this.applyDamage(e, sp.damage, this.towers.get(sp.ownerKey), 1);
            sp.charges -= 1;
            if (sp.charges <= 0) this.spikes.delete(ck1);
            if (e.hp <= 0) continue;
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
          const coins = this.awardCoins(Math.max(10, this.wave * 8));
          this.log(`DEFEAT! Earned +${coins} Coins.`);
          return;
        }
      }

      // Towers fire (zero-allocation targeting + capped visuals)
      for (const t of this.towers.values()) {
        const st = this.towerStats(t);
        if (st.damage <= 0 || st.spike_damage > 0) continue;
        t.cooldownLeft = Math.max(0, t.cooldownLeft - dt);
        if (t.cooldownLeft > 0 || this.enemies.length === 0) continue;

        const effR = st.range * t.buffRng;
        const effRSq = effR * effR;
        const minRSq = st.min_range * st.min_range;
        let target = null;
        let bestMetric = t.targetMode === "closest" ? 1e12 : -1;

        for (const e of this.enemies) {
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
        if (!target) continue;

        const tx = target._px, ty = target._py;
        t.angle = Math.atan2(ty - t.y, tx - t.x);
        t.cooldownLeft = st.cooldown / Math.max(0.5, t.buffSpd);

        if (emitVisuals) {
          this.emitShot(t.x + 0.5, t.y + 0.5, tx + 0.5, ty + 0.5, D.TOWERS[t.kind].rarity, t.kind);
          if (window.TDAudio && Math.random() < 0.28) window.TDAudio.playShoot(t.kind);
        }

        const effDmg = st.damage * t.buffDmg;
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
          for (const other of this.enemies) {
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
            for (const cand of this.enemies) {
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
      }

      this.enemies = this.enemies.filter((e) => e.hp > 0);

      // Wave complete
      if (this.waveActive && this.spawnQueue.length === 0 && this.enemies.length === 0) {
        this.waveActive = false;
        const farmGold = this.collectFarmIncome();
        const bonus = 25 + this.wave * 6 + farmGold;
        this.gold += bonus;
        this.score += bonus * 3;
        const coins = this.awardCoins(14 + this.wave * 3);

        if (!this.endless && this.wave >= this.maxWaves) {
          this.victory = true;
          this.nextWaveTimer = null;
          const winCoins = this.awardCoins(300);
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
    cycleAutoSell,
    toggleLoadout,
    sellUnit,
    sellAllDuplicates,
    summonBanner,
    GameBattle,
  };
})();

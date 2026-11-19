// UI Controller for Bastion TD (Web & Native iOS WKWebView)
(function () {
  const D = window.TD_DATA;
  const E = window.TDEngine;
  const R = window.TDRenderer;

  const profile = E.createProfile();
  let selectedDiff = "normal";
  let selectedMapIdx = 0;
  let selectedBanner = D.BANNER_ORDER[0];
  let currentTab = "lobby";
  let battle = null;
  let hoverCell = null;
  let lastFrame = performance.now();
  let modalMode = null; // null, "tavern", "end"
  let tavernBet = 50;
  let tavernMsg = "Bet match Gold on Slots, Dice 2d6, or $80 Mystery Crates!";

  const $ = (id) => document.getElementById(id);

  function refreshTopbar() {
    $("hud-coins").textContent = `Coins: ${profile.coins}`;
    $("hud-stats").textContent = `Wins: ${profile.total_wins} | W:${profile.best_wave}`;
  }

  function switchTab(tab) {
    currentTab = tab;
    const inBattle = tab === "battle";
    $("lobby-topbar").style.display = inBattle ? "none" : "flex";
    $("lobby-navbar").style.display = inBattle ? "none" : "flex";

    for (const s of document.querySelectorAll(".screen")) s.classList.remove("active");
    $(`screen-${tab}`).classList.add("active");

    for (const btn of document.querySelectorAll("#lobby-navbar .btn")) {
      btn.classList.toggle("active", btn.dataset.tab === tab);
    }

    refreshTopbar();
    if (tab === "lobby") renderLobby();
    if (tab === "gacha") renderGacha();
    if (tab === "inventory") renderInventory();
    if (tab === "bestiary") renderBestiary();
    if (tab === "battle") renderBattleHUD();
  }

  // ========== LOBBY ==========
  function renderLobby() {
    const dl = $("diff-list");
    dl.innerHTML = "";
    for (const dk of D.DIFFICULTY_ORDER) {
      const d = D.DIFFICULTIES[dk];
      const div = document.createElement("div");
      div.className = `option-row ${selectedDiff === dk ? "selected" : ""}`;
      const timerTxt = d.auto_wave_delay ? `${d.auto_wave_delay}s timer` : "Manual";
      div.innerHTML = `
        <div>
          <strong>${d.name}</strong>
          <div class="subtext">${d.description}</div>
        </div>
        <div class="pill coins">${d.coin_mult}x Coins · ${timerTxt}</div>
      `;
      div.onclick = () => {
        selectedDiff = dk;
        renderLobby();
      };
      dl.appendChild(div);
    }

    const ml = $("map-list");
    ml.innerHTML = "";
    D.MAPS.forEach((m, idx) => {
      const div = document.createElement("div");
      div.className = `option-row ${selectedMapIdx === idx ? "selected" : ""}`;
      div.innerHTML = `
        <div>
          <strong>${m.name}</strong>
          <div class="subtext">${m.description}</div>
        </div>
        <div class="pill">${m.centerline.length} tiles</div>
      `;
      div.onclick = () => {
        selectedMapIdx = idx;
        renderLobby();
      };
      ml.appendChild(div);
    });

    const ll = $("lobby-loadout");
    ll.innerHTML = "";
    for (let i = 0; i < D.MAX_LOADOUT; i++) {
      const card = document.createElement("div");
      if (i < profile.loadout.length) {
        const k = profile.loadout[i];
        const bp = D.TOWERS[k];
        card.className = `unit-card rar-${bp.rarity}`;
        card.innerHTML = `
          <div style="display:flex;justify-content:space-between;">
            <strong>[${bp.symbol}] ${bp.name}</strong>
            <span>$${bp.levels[0].cost}</span>
          </div>
          <div class="subtext">${D.RARITIES[bp.rarity].label} · ${bp.role}</div>
        `;
      } else {
        card.className = "unit-card";
        card.innerHTML = `<strong>Slot ${i + 1} Empty</strong><div class="subtext">Equip in Loadout tab</div>`;
      }
      ll.appendChild(card);
    }
  }

  // ========== GACHA ==========
  function renderGacha() {
    const b = D.BANNERS[selectedBanner];
    $("gacha-pity").textContent = `Mythic Pity: ${profile.pity_counter}/${b.pity_mythic_at}`;
    $("btn-autosell").textContent = `Auto-Sell: ${E.AUTO_SELL_LABELS[profile.auto_sell_mode]}`;

    const tabs = $("banner-tabs");
    tabs.innerHTML = "";
    for (const bk of D.BANNER_ORDER) {
      const bn = D.BANNERS[bk];
      const btn = document.createElement("button");
      btn.className = `btn sm ${selectedBanner === bk ? "active" : ""}`;
      btn.textContent = bn.name;
      btn.onclick = () => {
        selectedBanner = bk;
        renderGacha();
      };
      tabs.appendChild(btn);
    }

    $("banner-desc").textContent = b.description;
    const rw = b.rarity_weights;
    $("banner-rates").textContent =
      `Rates: C ${rw.common}% · R ${rw.rare}% · E ${rw.epic}% · Leg ${rw.legendary}% · Myth ${rw.mythic}% · Transc ${rw.transcendent}%`;
    $("btn-roll-1").textContent = `1x Summon (${b.single_cost}c)`;
    $("btn-roll-10").textContent = `10x Summon (${b.multi_cost}c, 10th=${b.min_10x_rarity.toUpperCase()}+)`;
  }

  function showPulls(res) {
    refreshTopbar();
    renderGacha();
    $("gacha-result-title").textContent = res.message;
    const grid = $("gacha-pulls");
    grid.innerHTML = "";
    if (!res.ok) return;
    for (const p of res.pulls) {
      const card = document.createElement("div");
      card.className = `unit-card rar-${p.rarity}`;
      const badge =
        p.autoSoldCoins > 0
          ? `<span style="color:#fbbf24;">AUTO-SOLD +${p.autoSoldCoins}c</span>`
          : p.isNew
          ? `<span style="color:#4ade80;">NEW!</span>`
          : `<span class="subtext">Owned</span>`;
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <strong>${p.name}</strong>
          ${badge}
        </div>
        <div class="subtext">${D.RARITIES[p.rarity].label} · ${p.role}</div>
      `;
      grid.appendChild(card);
    }
  }

  // ========== INVENTORY & LOADOUT ==========
  function renderInventory() {
    $("inv-header").textContent = `Inventory & Loadout (${profile.loadout.length}/${D.MAX_LOADOUT})`;
    const ordered = [...D.TOWER_ORDER].sort((a, b) => {
      const oa = (profile.inventory[a] || 0) > 0 ? 0 : 1;
      const ob = (profile.inventory[b] || 0) > 0 ? 0 : 1;
      if (oa !== ob) return oa - ob;
      return D.RARITY_ORDER.indexOf(D.TOWERS[b].rarity) - D.RARITY_ORDER.indexOf(D.TOWERS[a].rarity);
    });

    const grid = $("inv-grid");
    grid.innerHTML = "";
    for (const k of ordered) {
      const bp = D.TOWERS[k];
      const cnt = profile.inventory[k] || 0;
      const eq = profile.loadout.includes(k);
      const sellCoins = D.RARITIES[bp.rarity].sell_coins;
      const card = document.createElement("div");
      card.className = `unit-card rar-${bp.rarity}`;
      card.style.opacity = cnt > 0 ? "1" : "0.45";
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
          <strong>[${bp.symbol}] ${bp.name} ${cnt > 0 ? `(x${cnt})` : "(Locked)"}</strong>
          <span class="subtext">${D.RARITIES[bp.rarity].label} · $${bp.levels[0].cost}</span>
        </div>
        <div class="subtext">${bp.role} — ${bp.description}</div>
        <div class="subtext">Lv1 DMG:${bp.levels[0].damage} CD:${bp.levels[0].cooldown}s RNG:${bp.levels[0].range}</div>
      `;
      if (cnt > 0) {
        const actions = document.createElement("div");
        actions.className = "pill-row";
        actions.style.marginTop = "4px";
        const eqBtn = document.createElement("button");
        eqBtn.className = `btn sm ${eq ? "good" : "primary"}`;
        eqBtn.textContent = eq ? "Equipped" : "Equip";
        eqBtn.onclick = () => {
          const r = E.toggleLoadout(profile, k);
          $("inv-msg").textContent = r.msg;
          renderInventory();
        };
        const sellBtn = document.createElement("button");
        sellBtn.className = "btn sm gold";
        sellBtn.textContent = `Sell 1 (+${sellCoins}c)`;
        sellBtn.onclick = () => {
          const r = E.sellUnit(profile, k, 1);
          $("inv-msg").textContent = r.msg;
          refreshTopbar();
          renderInventory();
        };
        actions.appendChild(eqBtn);
        actions.appendChild(sellBtn);
        card.appendChild(actions);
      }
      grid.appendChild(card);
    }
  }

  // ========== BESTIARY ==========
  function renderBestiary() {
    const g = $("bestiary-grid");
    if (g.childElementCount > 0) return;
    for (const k of D.UNIT_ORDER) {
      const u = D.UNITS[k];
      const div = document.createElement("div");
      div.className = `unit-card ${u.is_boss ? "rar-mythic" : ""}`;
      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;">
          <strong>[${u.symbol}] ${u.name}</strong>
          <span class="subtext">${u.is_boss ? "BOSS" : `Tier ${u.tier}`} · HP:${u.max_hp} · Arm:${u.armor}</span>
        </div>
        <div class="subtext">${u.description}</div>
      `;
      g.appendChild(div);
    }
    for (const [k, a] of Object.entries(D.ALLIES)) {
      const div = document.createElement("div");
      div.className = "unit-card rar-rare";
      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;">
          <strong>ALLY [${a.symbol}] ${a.name}</strong>
          <span class="subtext">HP:${a.max_hp} · DPS:${a.atk_dps} · Revives:${a.revives}</span>
        </div>
        <div class="subtext">${a.description}</div>
      `;
      g.appendChild(div);
    }
  }

  // ========== BATTLE UI ==========
  function renderBattleDock() {
    if (!battle) return;
    const dock = $("battle-dock");
    dock.innerHTML = "";
    for (const k of battle.loadout) {
      const bp = D.TOWERS[k];
      const cost = bp.levels[0].cost;
      const btn = document.createElement("button");
      btn.className = `dock-unit rar-${bp.rarity} ${battle.selectedTowerKind === k ? "selected" : ""}`;
      btn.style.opacity = battle.gold >= cost ? "1" : "0.55";
      btn.innerHTML = `
        <div style="font-weight:800;font-size:12px;">[${bp.symbol}] ${bp.name}</div>
        <div class="subtext">$${cost} · ${bp.role.split(" ")[0]}</div>
      `;
      btn.onclick = () => {
        battle.selectedTowerKind = k;
        renderBattleDock();
      };
      dock.appendChild(btn);
    }
  }

  function renderBattleHUD() {
    if (!battle) return;
    const wLbl = battle.endless ? `${battle.wave}*` : `${battle.wave}/${battle.maxWaves}`;
    $("b-wave").textContent = `W: ${wLbl}`;
    $("b-gold").textContent = `$${battle.gold}`;
    $("b-hp").textContent = `HP: ${battle.lives}`;
    $("b-coins").textContent = `+${battle.coinsEarned}c`;
    $("btn-speed").textContent = `${battle.speedMult}x`;
    $("btn-autowave").textContent = `Auto: ${battle.autoStart ? "ON" : "OFF"}`;
    $("btn-autowave").className = `btn sm ${battle.autoStart ? "good" : ""}`;
    $("btn-pause").textContent = battle.paused ? "Resume" : "Pause";

    if (battle.waveActive) {
      $("btn-wave").textContent = battle.waveRushCooldown > 0 ? `Wave ${battle.wave} Active` : `Prestart W${battle.wave + 1} (+$$)`;
    } else if (battle.nextWaveTimer !== null) {
      $("btn-wave").textContent = `Wave ${battle.wave + 1} (${battle.nextWaveTimer.toFixed(1)}s)`;
    } else {
      $("btn-wave").textContent = `Start Wave ${battle.wave + 1}`;
    }

    // Boss HP Bar
    const bosses = battle.enemies.filter((e) => e.tpl.is_boss && e.hp > 0);
    if (bosses.length > 0) {
      const b = bosses.reduce((a, c) => (c.progress > a.progress ? c : a));
      $("boss-bar").classList.add("show");
      $("boss-name").textContent = `BOSS: ${b.tpl.name}${bosses.length > 1 ? ` (x${bosses.length})` : ""}`;
      $("boss-fill").style.width = `${Math.max(0, Math.min(100, (b.hp / b.maxHp) * 100))}%`;
      $("boss-hp-txt").textContent = `${Math.ceil(b.hp)}/${Math.ceil(b.maxHp)}${b.shield > 0 ? ` +${Math.ceil(b.shield)}SH` : ""}`;
    } else {
      $("boss-bar").classList.remove("show");
    }

    // Selected Tower Inspector
    const sel = battle.selectedCell;
    const tower = sel ? battle.towers.get(`${sel.x},${sel.y}`) : null;
    if (tower) {
      const bp = D.TOWERS[tower.kind];
      const st = battle.towerStats(tower);
      $("inspector-bar").classList.add("show");
      $("insp-title").textContent = `${bp.name} Lv${tower.level}`;
      if (st.income_per_wave > 0) {
        $("insp-stats").textContent = `+$${st.income_per_wave}/w +$${st.income_per_tick}/t (Earned $${tower.goldEarned})`;
      } else {
        const effD = Math.round(st.damage * tower.buffDmg);
        const effR = (st.range * tower.buffRng).toFixed(1);
        const effCd = (st.cooldown / Math.max(0.5, tower.buffSpd)).toFixed(2);
        $("insp-stats").textContent = `DMG:${effD} RNG:${effR} CD:${effCd}s Kills:${tower.kills}`;
      }
      if (tower.level < bp.levels.length) {
        const uc = bp.levels[tower.level].cost;
        $("btn-insp-upgr").style.display = "inline-block";
        $("btn-insp-upgr").textContent = `Upgr Lv${tower.level + 1} ($${uc})`;
      } else {
        $("btn-insp-upgr").style.display = "none";
      }
      $("btn-insp-tgt").textContent = `Target: ${tower.targetMode}`;
      $("btn-insp-sell").textContent = `Sell (+$${Math.floor((tower.totalInvested * 7) / 10)})`;
    } else {
      $("inspector-bar").classList.remove("show");
    }

    // Victory / Defeat modal
    if ((battle.gameOver || battle.victory) && modalMode !== "end") {
      openEndModal();
    }
  }

  function openTavernModal() {
    modalMode = "tavern";
    const body = $("modal-body");
    const renderT = () => {
      body.innerHTML = `
        <h3 style="margin-top:0;color:#fbbf24;">Tavern Gold Gamble (Match Gold: $${battle.gold})</h3>
        <div class="pill-row" style="margin-bottom:10px;">
          ${[25, 50, 100, 250].map((a) => `<button class="btn sm ${tavernBet === a ? "active" : ""}" data-bet="${a}">$${a}</button>`).join("")}
        </div>
        <div class="pill-row" style="margin-bottom:10px;">
          <button class="btn primary" id="t-slots">Slots (up to 10x)</button>
          <button class="btn good" id="t-high">Dice High (2x)</button>
          <button class="btn good" id="t-low">Dice Low (2x)</button>
          <button class="btn gold" id="t-seven">Lucky 7 (4.5x)</button>
          <button class="btn bad" id="t-crate">Mystery Crate ($80)</button>
        </div>
        <p style="min-height:22px;color:#e2e8f0;">${tavernMsg}</p>
        <button class="btn" id="t-close">Back to Battle</button>
      `;
      body.querySelectorAll("[data-bet]").forEach((btn) => {
        btn.onclick = () => { tavernBet = Number(btn.dataset.bet); renderT(); };
      });
      $("t-slots").onclick = () => {
        if (battle.gold < tavernBet) { tavernMsg = `Need $${tavernBet}!`; renderT(); return; }
        battle.gold -= tavernBet;
        const syms = ["7", "*", "$", "A", "C", "X"];
        const r = [0, 1, 2].map(() => syms[Math.floor(Math.random() * syms.length)]);
        let pay = 0;
        if (r[0] === "7" && r[1] === "7" && r[2] === "7") pay = tavernBet * 10;
        else if (r[0] === r[1] && r[1] === r[2]) pay = tavernBet * 4;
        else if (r.filter((x) => x === "7").length === 2) pay = tavernBet * 2;
        else if (r[0] === r[1] || r[1] === r[2] || r[0] === r[2]) pay = Math.floor((tavernBet * 7) / 5);
        battle.gold += pay;
        tavernMsg = `[${r.join("|")}] Bet $${tavernBet} -> Won $${pay}!`;
        renderBattleHUD(); renderT();
      };
      const doDice = (choice) => {
        if (battle.gold < tavernBet) { tavernMsg = `Need $${tavernBet}!`; renderT(); return; }
        battle.gold -= tavernBet;
        const d1 = 1 + Math.floor(Math.random() * 6);
        const d2 = 1 + Math.floor(Math.random() * 6);
        const tot = d1 + d2;
        let pay = 0;
        if (choice === "high" && tot >= 8) pay = tavernBet * 2;
        if (choice === "low" && tot <= 6) pay = tavernBet * 2;
        if (choice === "seven" && tot === 7) pay = Math.floor((tavernBet * 9) / 2);
        battle.gold += pay;
        tavernMsg = `Rolled [${d1}]+[${d2}] = ${tot} -> Won $${pay}!`;
        renderBattleHUD(); renderT();
      };
      $("t-high").onclick = () => doDice("high");
      $("t-low").onclick = () => doDice("low");
      $("t-seven").onclick = () => doDice("seven");
      $("t-crate").onclick = () => {
        if (battle.gold < 80) { tavernMsg = "Need $80 for Crate!"; renderT(); return; }
        battle.gold -= 80;
        const roll = Math.random();
        if (roll < 0.15) { battle.gold += 200; tavernMsg = "MEGA VAULT! +$200 Gold!"; }
        else if (roll < 0.45) { battle.gold += 115; tavernMsg = "Gold Stash! +$115 Gold!"; }
        else if (roll < 0.65) {
          const ups = [...battle.towers.values()].filter((t) => t.level < D.TOWERS[t.kind].levels.length);
          if (ups.length > 0) {
            const pick = ups[Math.floor(Math.random() * ups.length)];
            pick.level += 1; battle.recomputeBuffs();
            tavernMsg = `Field Forge! Free upgrade: ${D.TOWERS[pick.kind].name} -> Lv${pick.level}!`;
          } else { battle.gold += 110; tavernMsg = "Forge Rebate! +$110 Gold!"; }
        } else if (roll < 0.85) { battle.gold += 45; tavernMsg = "Scrap Metal: +$45 Gold."; }
        else { tavernMsg = "MIMIC TRAP! Lost $80!"; }
        renderBattleHUD(); renderT();
      };
      $("t-close").onclick = () => { modalMode = null; $("modal-backdrop").classList.remove("show"); };
    };
    renderT();
    $("modal-backdrop").classList.add("show");
  }

  function openEndModal() {
    modalMode = "end";
    const body = $("modal-body");
    const isWin = battle.victory;
    body.innerHTML = `
      <h2 style="margin-top:0;color:${isWin ? "#22c55e" : "#ef4444"};">${isWin ? "VICTORY!" : "DEFEAT"}</h2>
      <p>Waves Cleared: <strong>${battle.wave}</strong> · Score: <strong>${battle.score}</strong> · Coins Earned: <strong style="color:#fbbf24;">+${battle.coinsEarned}c</strong></p>
      <div class="pill-row">
        ${isWin ? `<button class="btn primary" id="end-endless">Continue Endless Mode</button>` : ""}
        <button class="btn good" id="end-lobby">Return to Lobby & Gacha</button>
      </div>
    `;
    if (isWin) {
      $("end-endless").onclick = () => {
        battle.enterEndless();
        modalMode = null;
        $("modal-backdrop").classList.remove("show");
        renderBattleHUD();
      };
    }
    $("end-lobby").onclick = () => {
      modalMode = null;
      $("modal-backdrop").classList.remove("show");
      battle = null;
      switchTab("lobby");
    };
    $("modal-backdrop").classList.add("show");
  }

  // ========== EVENT WIRING ==========
  document.querySelectorAll("#lobby-navbar .btn").forEach((btn) => {
    btn.onclick = () => switchTab(btn.dataset.tab);
  });

  $("btn-mute").onclick = () => {
    const m = window.TDAudio.toggleMute();
    $("btn-mute").textContent = m ? "SFX: OFF" : "SFX: ON";
  };

  $("btn-roll-1").onclick = () => showPulls(E.summonBanner(profile, selectedBanner, 1));
  $("btn-roll-10").onclick = () => showPulls(E.summonBanner(profile, selectedBanner, 10));
  $("btn-autosell").onclick = () => {
    E.cycleAutoSell(profile);
    renderGacha();
  };
  $("btn-sell-dupes").onclick = () => {
    const r = E.sellAllDuplicates(profile);
    $("inv-msg").textContent = r.sold > 0 ? `Sold ${r.sold} duplicates for +${r.gained} Coins!` : "No duplicates to sell.";
    refreshTopbar();
    renderInventory();
  };

  $("btn-start-battle").onclick = () => {
    battle = new E.GameBattle(selectedMapIdx, selectedDiff, profile);
    modalMode = null;
    $("modal-backdrop").classList.remove("show");
    switchTab("battle");
    renderBattleDock();
    renderBattleHUD();
  };

  $("btn-wave").onclick = () => {
    if (battle) { battle.startNextWave(); renderBattleHUD(); renderBattleDock(); }
  };
  $("btn-autowave").onclick = () => {
    if (battle) { battle.toggleAutoStart(); renderBattleHUD(); }
  };
  $("btn-speed").onclick = () => {
    if (battle) { battle.cycleSpeed(); renderBattleHUD(); }
  };
  $("btn-pause").onclick = () => {
    if (battle) { battle.paused = !battle.paused; renderBattleHUD(); }
  };
  $("btn-tavern").onclick = () => {
    if (battle) openTavernModal();
  };
  $("btn-exit-battle").onclick = () => {
    battle = null;
    modalMode = null;
    $("modal-backdrop").classList.remove("show");
    switchTab("lobby");
  };

  $("btn-insp-upgr").onclick = () => {
    if (battle && battle.selectedCell) {
      battle.upgradeTower(battle.selectedCell.x, battle.selectedCell.y);
      renderBattleHUD();
      renderBattleDock();
    }
  };
  $("btn-insp-tgt").onclick = () => {
    if (battle && battle.selectedCell) {
      battle.cycleTargetMode(battle.selectedCell.x, battle.selectedCell.y);
      renderBattleHUD();
    }
  };
  $("btn-insp-sell").onclick = () => {
    if (battle && battle.selectedCell) {
      battle.sellTower(battle.selectedCell.x, battle.selectedCell.y);
      renderBattleHUD();
      renderBattleDock();
    }
  };
  $("btn-insp-close").onclick = () => {
    if (battle) { battle.selectedCell = null; renderBattleHUD(); }
  };

  const canvas = $("battle-canvas");
  canvas.addEventListener("pointermove", (ev) => {
    if (!battle) return;
    hoverCell = R.canvasToGrid(canvas, battle, ev.clientX, ev.clientY);
  });
  canvas.addEventListener("pointerdown", (ev) => {
    if (!battle) return;
    const cell = R.canvasToGrid(canvas, battle, ev.clientX, ev.clientY);
    if (!cell) return;
    const key = `${cell.x},${cell.y}`;
    if (battle.towers.has(key)) {
      battle.selectedCell = cell;
    } else if (battle.canBuildAt(cell.x, cell.y)) {
      if (battle.buildTower(cell.x, cell.y, battle.selectedTowerKind)) {
        renderBattleDock();
      } else {
        battle.selectedCell = cell;
      }
    } else {
      battle.selectedCell = null;
    }
    renderBattleHUD();
  });

  // Main 60 FPS loop
  let hudTick = 0;
  function loop(now) {
    const dt = Math.min(0.05, Math.max(0, (now - lastFrame) / 1000));
    lastFrame = now;
    if (currentTab === "battle" && battle) {
      battle.tick(dt, modalMode === "tavern");
      R.drawBattle(canvas, battle, hoverCell);
      hudTick += dt;
      if (hudTick >= 0.12) {
        hudTick = 0;
        renderBattleHUD();
        renderBattleDock();
      }
    }
    requestAnimationFrame(loop);
  }

  switchTab("lobby");
  requestAnimationFrame(loop);
})();

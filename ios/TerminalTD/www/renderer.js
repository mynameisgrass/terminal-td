// High-DPI HTML5 2D Canvas renderer for Terminal Tower Defense (Web & iOS)
(function () {
  const D = window.TD_DATA;
  const RARITY_COLOR = {
    common: "#cbd5e1",
    rare: "#38bdf8",
    epic: "#c084fc",
    legendary: "#fbbf24",
    mythic: "#f87171",
    transcendent: "#2dd4bf",
  };

  function drawBattle(canvas, battle, hoverCell) {
    if (!canvas || !battle) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 10 || rect.height < 10) return;

    const targetW = Math.floor(rect.width * dpr);
    const targetH = Math.floor(rect.height * dpr);
    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
    }

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const W = rect.width;
    const H = rect.height;
    const tile = Math.floor(Math.min(W / battle.width, H / battle.height));
    const ox = Math.floor((W - tile * battle.width) / 2);
    const oy = Math.floor((H - tile * battle.height) / 2);

    ctx.fillStyle = "#09131d";
    ctx.fillRect(0, 0, W, H);

    // 1. Grass checkerboard
    for (let y = 0; y < battle.height; y++) {
      for (let x = 0; x < battle.width; x++) {
        const key = `${x},${y}`;
        const px = ox + x * tile;
        const py = oy + y * tile;
        if (battle.spawnSet.has(key)) {
          ctx.fillStyle = "#581c87";
        } else if (battle.baseSet.has(key)) {
          ctx.fillStyle = "#14532d";
        } else if (battle.roadSet.has(key)) {
          ctx.fillStyle = (x + y) % 2 === 0 ? "#44382c" : "#3f3428";
        } else {
          ctx.fillStyle = (x + y) % 2 === 0 ? "#132920" : "#10231b";
        }
        ctx.fillRect(px, py, tile, tile);

        if (!battle.roadSet.has(key)) {
          ctx.strokeStyle = "rgba(255,255,255,0.035)";
          ctx.lineWidth = 1;
          ctx.strokeRect(px + 0.5, py + 0.5, tile - 1, tile - 1);
        }
      }
    }

    // 2. Smooth road centerline stripe
    if (battle.centerline.length > 1) {
      ctx.save();
      ctx.strokeStyle = "rgba(251, 191, 36, 0.22)";
      ctx.lineWidth = Math.max(1.5, tile * 0.1);
      ctx.setLineDash([tile * 0.35, tile * 0.35]);
      ctx.beginPath();
      for (let i = 0; i < battle.centerline.length; i++) {
        const [cx, cy] = battle.centerline[i];
        const sx = ox + (cx + 0.5) * tile;
        const sy = oy + (cy + 0.5) * tile;
        if (i === 0) ctx.moveTo(sx, sy);
        else ctx.lineTo(sx, sy);
      }
      ctx.stroke();
      ctx.restore();
    }

    // Spawn & Base badges
    const first = battle.mapDef.spawn_cells[0];
    const last = battle.mapDef.base_cells[0];
    ctx.fillStyle = "#e9d5ff";
    ctx.font = `bold ${Math.max(10, Math.floor(tile * 0.55))}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("SPAWN", ox + (first[0] + 1) * tile, oy + (first[1] + 1) * tile);
    ctx.fillStyle = "#bbf7d0";
    ctx.fillText("HQ", ox + (last[0] + 1) * tile, oy + (last[1] + 1) * tile);

    // 3. Road Spikes
    for (const sp of battle.spikes.values()) {
      const cx = ox + (sp.x + 0.5) * tile;
      const cy = oy + (sp.y + 0.5) * tile;
      ctx.fillStyle = "#fbbf24";
      for (let i = -1; i <= 1; i += 2) {
        ctx.beginPath();
        ctx.arc(cx + i * tile * 0.18, cy + i * tile * 0.12, tile * 0.1, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 4. Range preview circle
    const focus = battle.selectedCell || hoverCell;
    if (focus) {
      const t = battle.towers.get(`${focus.x},${focus.y}`);
      let r = 0, minR = 0, col = "#38bdf8";
      if (t) {
        const st = battle.towerStats(t);
        r = st.range * t.buffRng;
        minR = st.min_range;
        col = RARITY_COLOR[D.TOWERS[t.kind].rarity] || "#38bdf8";
      } else if (battle.canBuildAt(focus.x, focus.y) && battle.selectedTowerKind) {
        const st = D.TOWERS[battle.selectedTowerKind].levels[0];
        r = st.range;
        minR = st.min_range;
        col = RARITY_COLOR[D.TOWERS[battle.selectedTowerKind].rarity] || "#38bdf8";
      }
      if (r > 0) {
        const cx = ox + (focus.x + 0.5) * tile;
        const cy = oy + (focus.y + 0.5) * tile;
        ctx.save();
        ctx.fillStyle = "rgba(56, 189, 248, 0.10)";
        ctx.strokeStyle = col;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(cx, cy, r * tile, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        if (minR > 0) {
          ctx.strokeStyle = "rgba(248, 113, 113, 0.65)";
          ctx.beginPath();
          ctx.arc(cx, cy, minR * tile, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.restore();
      }
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(ox + focus.x * tile + 1, oy + focus.y * tile + 1, tile - 2, tile - 2);
    }

    // 5. Towers
    for (const t of battle.towers.values()) {
      const bp = D.TOWERS[t.kind];
      const rCol = RARITY_COLOR[bp.rarity] || "#cbd5e1";
      const cx = ox + (t.x + 0.5) * tile;
      const cy = oy + (t.y + 0.5) * tile;

      // Base pad
      ctx.fillStyle = "#1e293b";
      ctx.strokeStyle = rCol;
      ctx.lineWidth = Math.max(1.5, tile * 0.08);
      ctx.beginPath();
      ctx.roundRect(ox + t.x * tile + 2, oy + t.y * tile + 2, tile - 4, tile - 4, 4);
      ctx.fill();
      ctx.stroke();

      // Rotating barrel for combat units
      const st = battle.towerStats(t);
      if (st.damage > 0) {
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(t.angle || 0);
        ctx.fillStyle = rCol;
        ctx.fillRect(0, -tile * 0.1, tile * 0.42, tile * 0.2);
        ctx.restore();
      }

      // Symbol + level dots
      ctx.fillStyle = rCol;
      ctx.font = `bold ${Math.max(9, Math.floor(tile * 0.48))}px ui-monospace, monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(bp.symbol, cx, cy);

      // Level pips at bottom of tower
      for (let lv = 0; lv < t.level; lv++) {
        ctx.fillStyle = "#fbbf24";
        ctx.fillRect(ox + t.x * tile + 3 + lv * Math.max(3, tile * 0.16), oy + (t.y + 1) * tile - 4, Math.max(2, tile * 0.11), 2);
      }

      if (t.buffDmg > 1 || t.buffSpd > 1 || t.buffRng > 1) {
        ctx.fillStyle = "#4ade80";
        ctx.beginPath();
        ctx.arc(ox + (t.x + 1) * tile - 4, oy + t.y * tile + 4, Math.max(2, tile * 0.1), 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 6. Friendly Road Units (walking Base -> Spawn)
    for (const a of battle.allies) {
      const [ax, ay] = battle.entityPos(a.progress, a.laneOffset);
      const px = ox + (ax + 0.5) * tile;
      const py = oy + (ay + 0.5) * tile;
      const rad = Math.max(4, tile * 0.34);

      ctx.fillStyle = a.reviveFlash > 0 ? "#fbbf24" : (a.hitFlash > 0 ? "#ffffff" : "#22d3ee");
      ctx.strokeStyle = "#083344";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(px, py, rad, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "#082f49";
      ctx.font = `bold ${Math.max(8, Math.floor(tile * 0.42))}px ui-monospace, monospace`;
      ctx.fillText(a.tpl.symbol, px, py + 0.5);

      // Ally HP bar
      const bw = Math.max(12, tile * 0.85);
      const ratio = Math.max(0, Math.min(1, a.hp / a.maxHp));
      ctx.fillStyle = "rgba(0,0,0,0.75)";
      ctx.fillRect(px - bw / 2, py - rad - 5, bw, 3);
      ctx.fillStyle = a.revivesLeft > 0 ? "#fbbf24" : "#22d3ee";
      ctx.fillRect(px - bw / 2, py - rad - 5, bw * ratio, 3);
    }

    // 7. Enemies & Bosses with HP & Shield bars
    for (const e of battle.enemies) {
      const [ex, ey] = battle.entityPos(e.progress, e.laneOffset);
      const px = ox + (ex + 0.5) * tile;
      const py = oy + (ey + 0.5) * tile;
      const rad = e.tpl.is_boss ? Math.max(7, tile * 0.52) : Math.max(4, tile * (0.28 + e.tpl.tier * 0.04));

      let fill = "#ef4444";
      if (e.hitFlash > 0) fill = "#ffffff";
      else if (e.tpl.is_boss) fill = "#f59e0b";
      else if (e.poisonTimer > 0) fill = "#22c55e";
      else if (e.slowTimer > 0) fill = "#38bdf8";
      else if (e.tpl.tier >= 4) fill = "#a855f7";
      else if (e.tpl.tier === 3) fill = "#f97316";

      ctx.fillStyle = fill;
      ctx.strokeStyle = e.tpl.is_boss ? "#fef08a" : "#1e1b4b";
      ctx.lineWidth = e.tpl.is_boss ? 2.2 : 1.2;
      ctx.beginPath();
      ctx.arc(px, py, rad, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "#0f172a";
      ctx.font = `bold ${Math.max(8, Math.floor(rad * 1.15))}px ui-monospace, monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(e.tpl.symbol, px, py + 0.5);

      // HP bar + Shield bar
      const bw = e.tpl.is_boss ? Math.max(24, tile * 1.4) : Math.max(12, tile * 0.9);
      const ratio = Math.max(0, Math.min(1, e.hp / e.maxHp));
      ctx.fillStyle = "rgba(0,0,0,0.8)";
      ctx.fillRect(px - bw / 2, py - rad - 6, bw, 3.5);
      ctx.fillStyle = ratio > 0.5 ? "#22c55e" : (ratio > 0.25 ? "#facc15" : "#ef4444");
      ctx.fillRect(px - bw / 2, py - rad - 6, bw * ratio, 3.5);
      if (e.shield > 0) {
        const sRatio = Math.min(1, e.shield / e.maxHp);
        ctx.fillStyle = "#38bdf8";
        ctx.fillRect(px - bw / 2, py - rad - 9, bw * sRatio, 2);
      }
    }

    // 8. Shot Tracers & Explosion Rings
    for (const s of battle.shots) {
      ctx.save();
      ctx.globalAlpha = Math.max(0.2, s.ttl / s.maxTtl);
      ctx.strokeStyle = RARITY_COLOR[s.rarity] || "#fde047";
      ctx.lineWidth = s.kind === "railgun" || s.kind === "astral_lance" || s.kind === "orbital_relay" ? 3 : 1.8;
      ctx.beginPath();
      ctx.moveTo(ox + s.x0 * tile, oy + s.y0 * tile);
      ctx.lineTo(ox + s.x1 * tile, oy + s.y1 * tile);
      ctx.stroke();
      ctx.restore();
    }

    for (const ef of battle.effects) {
      const p = 1 - ef.ttl / ef.maxTtl;
      ctx.save();
      ctx.globalAlpha = Math.max(0, (1 - p) * 0.55);
      ctx.strokeStyle = ef.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(ox + ef.x * tile, oy + ef.y * tile, ef.r * tile * (0.35 + p * 0.65), 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    for (const ft of battle.floatTexts) {
      ctx.save();
      ctx.globalAlpha = Math.min(1, ft.ttl * 2);
      ctx.fillStyle = ft.color;
      ctx.font = `bold ${Math.max(10, Math.floor(tile * 0.5))}px system-ui, sans-serif`;
      ctx.fillText(ft.text, ox + ft.x * tile, oy + ft.y * tile);
      ctx.restore();
    }
  }

  function canvasToGrid(canvas, battle, clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const tile = Math.floor(Math.min(rect.width / battle.width, rect.height / battle.height));
    const ox = Math.floor((rect.width - tile * battle.width) / 2);
    const oy = Math.floor((rect.height - tile * battle.height) / 2);
    const gx = Math.floor((clientX - rect.left - ox) / tile);
    const gy = Math.floor((clientY - rect.top - oy) / tile);
    if (gx < 0 || gx >= battle.width || gy < 0 || gy >= battle.height) return null;
    return { x: gx, y: gy };
  }

  window.TDRenderer = { drawBattle, canvasToGrid, RARITY_COLOR };
})();

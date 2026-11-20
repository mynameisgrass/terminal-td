// High-Performance 60 FPS ASCII Grid Canvas Renderer with Static Offscreen Layer Cache
(function () {
  const D = window.TD_DATA;
  const RARITY_COLOR = {
    common: "#d1d5db",
    rare: "#38bdf8",
    epic: "#c084fc",
    legendary: "#fbbf24",
    mythic: "#f87171",
    transcendent: "#2dd4bf",
  };

  let staticCanvas = null;
  let staticKey = "";

  function asciiBar(hp, maxHp, width) {
    if (maxHp <= 0) return "[" + ".".repeat(width) + "]";
    const ratio = Math.max(0, Math.min(1, hp / maxHp));
    const fill = Math.round(ratio * width);
    return "[" + "#".repeat(fill) + "-".repeat(width - fill) + "]";
  }

  function microHpChar(hp, maxHp) {
    const r = maxHp > 0 ? hp / maxHp : 0;
    if (r > 0.75) return "#";
    if (r > 0.5) return "+";
    if (r > 0.25) return "-";
    return ".";
  }

  function ensureStaticLayer(battle, W, H, dpr, tile, ox, oy) {
    const key = `${battle.mapDef.key}|${W}|${H}|${dpr}|${tile}`;
    if (staticCanvas && staticKey === key) return staticCanvas;

    if (!staticCanvas) staticCanvas = document.createElement("canvas");
    staticCanvas.width = Math.floor(W * dpr);
    staticCanvas.height = Math.floor(H * dpr);
    staticKey = key;

    const sctx = staticCanvas.getContext("2d");
    sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sctx.fillStyle = "#040907";
    sctx.fillRect(0, 0, W, H);

    sctx.strokeStyle = "#1e4d3a";
    sctx.lineWidth = 1;
    sctx.strokeRect(ox - 1, oy - 1, tile * battle.width + 2, tile * battle.height + 2);

    sctx.font = `bold ${Math.max(8, Math.floor(tile * 0.54))}px ui-monospace, "SF Mono", Menlo, Consolas, monospace`;
    sctx.textAlign = "center";
    sctx.textBaseline = "middle";

    for (let y = 0; y < battle.height; y++) {
      for (let x = 0; x < battle.width; x++) {
        const ck = `${x},${y}`;
        const px = ox + x * tile;
        const py = oy + y * tile;
        const cx = px + tile / 2;
        const cy = py + tile / 2;

        if (battle.spawnSet.has(ck)) {
          sctx.fillStyle = "#220a33";
          sctx.fillRect(px, py, tile, tile);
          sctx.fillStyle = "#e879f9";
          sctx.fillText("S>", cx, cy);
        } else if (battle.baseSet.has(ck)) {
          sctx.fillStyle = "#082917";
          sctx.fillRect(px, py, tile, tile);
          sctx.fillStyle = "#4ade80";
          sctx.fillText("<>", cx, cy);
        } else if (battle.roadSet.has(ck)) {
          sctx.fillStyle = "#1c170f";
          sctx.fillRect(px, py, tile, tile);
          sctx.fillStyle = "#85642d";
          sctx.fillText("::", cx, cy);
        } else {
          sctx.fillStyle = (x + y) % 2 === 0 ? "#06100c" : "#050d0a";
          sctx.fillRect(px, py, tile, tile);
          sctx.fillStyle = "#1b4332";
          sctx.fillText(".", cx, cy);
        }
      }
    }
    return staticCanvas;
  }

  function drawBattle(canvas, battle, hoverCell, pendingBuild) {
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
    const W = rect.width;
    const H = rect.height;
    const tile = Math.max(8, Math.min(Math.floor(W / battle.width), Math.floor(H / battle.height)));
    const ox = Math.floor((W - tile * battle.width) / 2);
    const oy = Math.floor((H - tile * battle.height) / 2);

    // 1. Blit pre-rendered static map in 1 single drawImage call
    const bg = ensureStaticLayer(battle, W, H, dpr, tile, ox, oy);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(bg, 0, 0);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const monoFont = `bold ${Math.max(8, Math.floor(tile * 0.56))}px ui-monospace, "SF Mono", Menlo, Consolas, monospace`;
    const smallFont = `bold ${Math.max(7, Math.floor(tile * 0.40))}px ui-monospace, "SF Mono", Menlo, Consolas, monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    // 2. Range '+' overlay (only bounding box around focused tile!)
    const focus = pendingBuild || battle.selectedCell || hoverCell;
    if (focus) {
      const ft = battle.towers.get(`${focus.x},${focus.y}`);
      let r = 0, minR = 0, col = "#38bdf8";
      if (ft) {
        const st = battle.towerStats(ft);
        r = st.range * ft.buffRng;
        minR = st.min_range;
        col = RARITY_COLOR[D.TOWERS[ft.kind].rarity] || "#38bdf8";
      } else if (battle.canBuildAt(focus.x, focus.y) && battle.selectedTowerKind) {
        const st = D.TOWERS[battle.selectedTowerKind].levels[0];
        r = st.range;
        minR = st.min_range;
        col = RARITY_COLOR[D.TOWERS[battle.selectedTowerKind].rarity] || "#38bdf8";
      }
      if (r > 0) {
        const ceilR = Math.ceil(r);
        const rSq = r * r;
        const minRSq = minR * minR;
        const x0 = Math.max(0, focus.x - ceilR);
        const x1 = Math.min(battle.width - 1, focus.x + ceilR);
        const y0 = Math.max(0, focus.y - ceilR);
        const y1 = Math.min(battle.height - 1, focus.y + ceilR);
        ctx.font = monoFont;
        for (let y = y0; y <= y1; y++) {
          for (let x = x0; x <= x1; x++) {
            const dx = x - focus.x, dy = y - focus.y;
            const dSq = dx * dx + dy * dy;
            if (dSq < minRSq || dSq > rSq) continue;
            const ck = `${x},${y}`;
            const px = ox + x * tile;
            const py = oy + y * tile;
            if (battle.roadSet.has(ck)) {
              ctx.fillStyle = "#2e2412";
              ctx.fillRect(px, py, tile, tile);
              ctx.fillStyle = "#fbbf24";
              ctx.fillText("::", px + tile / 2, py + tile / 2);
            } else if (!battle.towers.has(ck)) {
              ctx.fillStyle = "#0a1f2b";
              ctx.fillRect(px, py, tile, tile);
              ctx.fillStyle = col;
              ctx.fillText("+", px + tile / 2, py + tile / 2);
            }
          }
        }
      }
    }

    // 3. Road Spikes
    ctx.font = smallFont;
    if (battle.spikes.size > 0) {
      ctx.fillStyle = "#fbbf24";
      for (const sp of battle.spikes.values()) {
        ctx.fillText("xx", ox + (sp.x + 0.5) * tile, oy + (sp.y + 0.5) * tile);
      }
    }

    // 4. Towers
    for (const t of battle.towers.values()) {
      const bp = D.TOWERS[t.kind];
      const rCol = RARITY_COLOR[bp.rarity] || "#d1d5db";
      const px = ox + t.x * tile;
      const py = oy + t.y * tile;

      ctx.fillStyle = "#081410";
      ctx.fillRect(px + 1, py + 1, tile - 2, tile - 2);
      ctx.strokeStyle = rCol;
      ctx.lineWidth = 1;
      ctx.strokeRect(px + 1, py + 1, tile - 2, tile - 2);

      ctx.fillStyle = rCol;
      ctx.fillText(`${bp.symbol}${t.level}`, px + tile / 2, py + tile / 2);

      if (t.buffDmg > 1 || t.buffSpd > 1 || t.buffRng > 1) {
        ctx.fillStyle = "#4ade80";
        ctx.fillText("+", px + tile - Math.max(4, tile * 0.2), py + Math.max(4, tile * 0.22));
      }
    }

    // 5. Pending Ghost Blueprint (Mindustry-style click-and-confirm preview!)
    if (pendingBuild && battle.selectedTowerKind && battle.canBuildAt(pendingBuild.x, pendingBuild.y)) {
      const bp = D.TOWERS[battle.selectedTowerKind];
      const canAfford = battle.gold >= bp.levels[0].cost;
      const px = ox + pendingBuild.x * tile;
      const py = oy + pendingBuild.y * tile;
      ctx.fillStyle = canAfford ? "rgba(74, 222, 128, 0.22)" : "rgba(248, 113, 113, 0.22)";
      ctx.fillRect(px + 1, py + 1, tile - 2, tile - 2);
      ctx.strokeStyle = canAfford ? "#4ade80" : "#f87171";
      ctx.lineWidth = 2;
      ctx.strokeRect(px + 1, py + 1, tile - 2, tile - 2);
      ctx.fillStyle = canAfford ? "#4ade80" : "#f87171";
      ctx.fillText(`${bp.symbol}?`, px + tile / 2, py + tile / 2);
    } else if (focus) {
      ctx.strokeStyle = "#4ade80";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(ox + focus.x * tile + 0.5, oy + focus.y * tile + 0.5, tile - 1, tile - 1);
    }

    // 6. Friendly Road Units
    for (const a of battle.allies) {
      const [ax, ay] = battle.entityPos(a.progress, a.laneOffset);
      const cx = ox + (ax + 0.5) * tile;
      const cy = oy + (ay + 0.5) * tile;
      ctx.fillStyle = "rgba(4, 24, 30, 0.85)";
      ctx.fillRect(cx - tile * 0.42, cy - tile * 0.38, tile * 0.84, tile * 0.76);
      ctx.fillStyle = a.reviveFlash > 0 ? "#fbbf24" : (a.hitFlash > 0 ? "#ffffff" : "#22d3ee");
      ctx.fillText(`^${a.tpl.symbol}`, cx, cy);
      ctx.fillStyle = a.revivesLeft > 0 ? "#fbbf24" : "#22d3ee";
      ctx.fillText(asciiBar(a.hp, a.maxHp, 3), cx, cy - tile * 0.48);
    }

    // 7. Enemies & Bosses
    for (const e of battle.enemies) {
      const cx = ox + (e._px + 0.5) * tile;
      const cy = oy + (e._py + 0.5) * tile;

      let col = "#f87171";
      if (e.hitFlash > 0) col = "#ffffff";
      else if (e.tpl.is_boss) col = "#fde047";
      else if (e.poisonTimer > 0) col = "#4ade80";
      else if (e.slowTimer > 0) col = "#38bdf8";
      else if (e.tpl.tier >= 4) col = "#c084fc";
      else if (e.tpl.tier === 3) col = "#fb923c";

      if (e.tpl.is_boss) {
        ctx.fillStyle = "#450a0a";
        ctx.fillRect(cx - tile * 0.58, cy - tile * 0.48, tile * 1.16, tile * 0.96);
        ctx.strokeStyle = "#fde047";
        ctx.lineWidth = 1.5;
        ctx.strokeRect(cx - tile * 0.58, cy - tile * 0.48, tile * 1.16, tile * 0.96);
        ctx.fillStyle = col;
        ctx.font = monoFont;
        ctx.fillText(`[${e.tpl.symbol}]`, cx, cy);
        ctx.fillStyle = "#fde047";
        ctx.font = smallFont;
        ctx.fillText(asciiBar(e.hp, e.maxHp, 5), cx, cy - tile * 0.65);
      } else {
        ctx.fillStyle = "rgba(18, 6, 6, 0.85)";
        ctx.fillRect(cx - tile * 0.4, cy - tile * 0.35, tile * 0.8, tile * 0.7);
        ctx.fillStyle = col;
        ctx.fillText(`${e.tpl.symbol}${microHpChar(e.hp, e.maxHp)}`, cx, cy);
      }

      if (e.shield > 0) {
        ctx.fillStyle = "#38bdf8";
        ctx.fillText("[SH]", cx, cy + tile * 0.55);
      }
    }

    // 8. Capped ASCII Shot Trails
    for (const s of battle.shots) {
      const char = (D.TOWERS[s.kind] && D.TOWERS[s.kind].shot_char) || "*";
      ctx.globalAlpha = Math.max(0.25, s.ttl / s.maxTtl);
      ctx.fillStyle = RARITY_COLOR[s.rarity] || "#fde047";
      const dist = Math.hypot(s.x1 - s.x0, s.y1 - s.y0);
      const count = Math.max(2, Math.min(6, Math.round(dist * 1.1)));
      for (let i = 1; i <= count; i++) {
        const t = i / count;
        ctx.fillText(char, ox + (s.x0 + (s.x1 - s.x0) * t) * tile, oy + (s.y0 + (s.y1 - s.y0) * t) * tile);
      }
    }

    // 9. Capped ASCII Explosion Bursts
    for (const ef of battle.effects) {
      const p = 1 - ef.ttl / ef.maxTtl;
      const rad = ef.r * tile * (0.35 + p * 0.65);
      ctx.globalAlpha = Math.max(0, (1 - p) * 0.85);
      ctx.fillStyle = ef.color;
      for (let a = 0; a < 8; a++) {
        const ang = (a * Math.PI) / 4;
        ctx.fillText(a % 2 === 0 ? "*" : "+", ox + ef.x * tile + Math.cos(ang) * rad, oy + ef.y * tile + Math.sin(ang) * rad);
      }
    }

    // 10. Floating Combat Text
    for (const ft of battle.floatTexts) {
      ctx.globalAlpha = Math.min(1, ft.ttl * 2);
      ctx.fillStyle = ft.color;
      ctx.fillText(ft.text, ox + ft.x * tile, oy + ft.y * tile);
    }
    ctx.globalAlpha = 1;
  }

  function canvasToGrid(canvas, battle, clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const tile = Math.max(8, Math.min(Math.floor(rect.width / battle.width), Math.floor(rect.height / battle.height)));
    const ox = Math.floor((rect.width - tile * battle.width) / 2);
    const oy = Math.floor((rect.height - tile * battle.height) / 2);
    const gx = Math.floor((clientX - rect.left - ox) / tile);
    const gy = Math.floor((clientY - rect.top - oy) / tile);
    if (gx < 0 || gx >= battle.width || gy < 0 || gy >= battle.height) return null;
    return { x: gx, y: gy };
  }

  window.TDRenderer = { drawBattle, canvasToGrid, RARITY_COLOR };
})();

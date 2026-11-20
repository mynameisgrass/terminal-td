// 60 FPS Retro-Terminal ASCII Grid Canvas Renderer (iOS 14+ & Web)
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
    const tileW = Math.floor(W / battle.width);
    const tileH = Math.floor(H / battle.height);
    const tile = Math.max(8, Math.min(tileW, tileH));
    const ox = Math.floor((W - tile * battle.width) / 2);
    const oy = Math.floor((H - tile * battle.height) / 2);

    ctx.fillStyle = "#040907";
    ctx.fillRect(0, 0, W, H);

    // Outer ASCII frame around the 36x18 grid
    ctx.strokeStyle = "#1e4d3a";
    ctx.lineWidth = 1;
    ctx.strokeRect(ox - 1, oy - 1, tile * battle.width + 2, tile * battle.height + 2);

    const focus = battle.selectedCell || hoverCell;
    let rangeR = 0, rangeMinR = 0, rangeCol = "#38bdf8";
    if (focus) {
      const ft = battle.towers.get(`${focus.x},${focus.y}`);
      if (ft) {
        const st = battle.towerStats(ft);
        rangeR = st.range * ft.buffRng;
        rangeMinR = st.min_range;
        rangeCol = RARITY_COLOR[D.TOWERS[ft.kind].rarity] || "#38bdf8";
      } else if (battle.canBuildAt(focus.x, focus.y) && battle.selectedTowerKind) {
        const st = D.TOWERS[battle.selectedTowerKind].levels[0];
        rangeR = st.range;
        rangeMinR = st.min_range;
        rangeCol = RARITY_COLOR[D.TOWERS[battle.selectedTowerKind].rarity] || "#38bdf8";
      }
    }

    const monoFont = `bold ${Math.max(8, Math.floor(tile * 0.56))}px ui-monospace, "SF Mono", Menlo, Consolas, monospace`;
    const smallFont = `bold ${Math.max(7, Math.floor(tile * 0.40))}px ui-monospace, "SF Mono", Menlo, Consolas, monospace`;
    ctx.font = monoFont;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    // 1. Grid Tiles (Grass, 2-Lane Road, Spawn, HQ, Range '+')
    for (let y = 0; y < battle.height; y++) {
      for (let x = 0; x < battle.width; x++) {
        const key = `${x},${y}`;
        const px = ox + x * tile;
        const py = oy + y * tile;
        const cx = px + tile / 2;
        const cy = py + tile / 2;

        const inRange =
          focus && rangeR > 0 && (() => {
            const d = Math.hypot(x - focus.x, y - focus.y);
            return d >= rangeMinR && d <= rangeR;
          })();

        if (battle.spawnSet.has(key)) {
          ctx.fillStyle = "#220a33";
          ctx.fillRect(px, py, tile, tile);
          ctx.fillStyle = "#e879f9";
          ctx.fillText("S>", cx, cy);
        } else if (battle.baseSet.has(key)) {
          ctx.fillStyle = "#082917";
          ctx.fillRect(px, py, tile, tile);
          ctx.fillStyle = "#4ade80";
          ctx.fillText("<>", cx, cy);
        } else if (battle.roadSet.has(key)) {
          ctx.fillStyle = inRange ? "#2e2412" : "#1c170f";
          ctx.fillRect(px, py, tile, tile);
          ctx.fillStyle = inRange ? "#fbbf24" : "#85642d";
          ctx.fillText("::", cx, cy);
        } else {
          ctx.fillStyle = inRange ? "#0a1f2b" : ((x + y) % 2 === 0 ? "#06100c" : "#050d0a");
          ctx.fillRect(px, py, tile, tile);
          if (inRange) {
            ctx.fillStyle = rangeCol;
            ctx.fillText("+", cx, cy);
          } else {
            ctx.fillStyle = "#1b4332";
            ctx.fillText(".", cx, cy);
          }
        }
      }
    }

    // 2. Road Spikes (ASCII 'xx')
    ctx.font = smallFont;
    for (const sp of battle.spikes.values()) {
      ctx.fillStyle = "#fbbf24";
      ctx.fillText("xx", ox + (sp.x + 0.5) * tile, oy + (sp.y + 0.5) * tile);
    }

    // 3. Towers ([A1], [$3], etc.)
    for (const t of battle.towers.values()) {
      const bp = D.TOWERS[t.kind];
      const rCol = RARITY_COLOR[bp.rarity] || "#d1d5db";
      const px = ox + t.x * tile;
      const py = oy + t.y * tile;
      const cx = px + tile / 2;
      const cy = py + tile / 2;

      ctx.fillStyle = "#081410";
      ctx.fillRect(px + 1, py + 1, tile - 2, tile - 2);
      ctx.strokeStyle = rCol;
      ctx.lineWidth = 1;
      ctx.strokeRect(px + 1, py + 1, tile - 2, tile - 2);

      ctx.fillStyle = rCol;
      ctx.font = smallFont;
      ctx.fillText(`${bp.symbol}${t.level}`, cx, cy);

      if (t.buffDmg > 1 || t.buffSpd > 1 || t.buffRng > 1) {
        ctx.fillStyle = "#4ade80";
        ctx.fillText("+", px + tile - Math.max(4, tile * 0.2), py + Math.max(4, tile * 0.22));
      }
    }

    // 4. Friendly Road Units (^P, ^W, ^*)
    for (const a of battle.allies) {
      const [ax, ay] = battle.entityPos(a.progress, a.laneOffset);
      const cx = ox + (ax + 0.5) * tile;
      const cy = oy + (ay + 0.5) * tile;
      const col = a.reviveFlash > 0 ? "#fbbf24" : (a.hitFlash > 0 ? "#ffffff" : "#22d3ee");

      ctx.fillStyle = "rgba(4, 24, 30, 0.85)";
      ctx.fillRect(cx - tile * 0.42, cy - tile * 0.38, tile * 0.84, tile * 0.76);
      ctx.fillStyle = col;
      ctx.font = smallFont;
      ctx.fillText(`^${a.tpl.symbol}`, cx, cy);

      // Micro ASCII HP indicator above ally
      ctx.fillStyle = a.revivesLeft > 0 ? "#fbbf24" : "#22d3ee";
      ctx.fillText(asciiBar(a.hp, a.maxHp, 3), cx, cy - tile * 0.48);
    }

    // 5. Enemies & Bosses (ASCII glyph + ASCII HP bar)
    for (const e of battle.enemies) {
      const [ex, ey] = battle.entityPos(e.progress, e.laneOffset);
      const cx = ox + (ex + 0.5) * tile;
      const cy = oy + (ey + 0.5) * tile;

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
        ctx.font = smallFont;
        ctx.fillText(`${e.tpl.symbol}${microHpChar(e.hp, e.maxHp)}`, cx, cy);
      }

      if (e.shield > 0) {
        ctx.fillStyle = "#38bdf8";
        ctx.font = smallFont;
        ctx.fillText("[SH]", cx, cy + tile * 0.55);
      }
    }

    // 6. ASCII Shot Trails (*, ^, ~, |, !)
    for (const s of battle.shots) {
      const char = (D.TOWERS[s.kind] && D.TOWERS[s.kind].shot_char) || "*";
      const col = RARITY_COLOR[s.rarity] || "#fde047";
      const dist = Math.hypot(s.x1 - s.x0, s.y1 - s.y0);
      const count = Math.max(2, Math.min(8, Math.round(dist * 1.4)));
      ctx.save();
      ctx.globalAlpha = Math.max(0.25, s.ttl / s.maxTtl);
      ctx.fillStyle = col;
      ctx.font = smallFont;
      for (let i = 1; i <= count; i++) {
        const t = i / count;
        const sx = ox + (s.x0 + (s.x1 - s.x0) * t) * tile;
        const sy = oy + (s.y0 + (s.y1 - s.y0) * t) * tile;
        ctx.fillText(char, sx, sy);
      }
      ctx.restore();
    }

    // 7. ASCII Explosion Bursts
    for (const ef of battle.effects) {
      const p = 1 - ef.ttl / ef.maxTtl;
      const rad = ef.r * tile * (0.35 + p * 0.65);
      ctx.save();
      ctx.globalAlpha = Math.max(0, (1 - p) * 0.85);
      ctx.fillStyle = ef.color;
      ctx.font = smallFont;
      for (let a = 0; a < 8; a++) {
        const ang = (a * Math.PI) / 4;
        const ex = ox + ef.x * tile + Math.cos(ang) * rad;
        const ey = oy + ef.y * tile + Math.sin(ang) * rad;
        ctx.fillText(a % 2 === 0 ? "*" : "+", ex, ey);
      }
      ctx.restore();
    }

    // 8. Cursor / Selected Tile Highlight
    if (focus) {
      ctx.strokeStyle = "#4ade80";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(ox + focus.x * tile + 0.5, oy + focus.y * tile + 0.5, tile - 1, tile - 1);
    }

    // 9. Floating ASCII Combat Text
    for (const ft of battle.floatTexts) {
      ctx.save();
      ctx.globalAlpha = Math.min(1, ft.ttl * 2);
      ctx.fillStyle = ft.color;
      ctx.font = smallFont;
      ctx.fillText(ft.text, ox + ft.x * tile, oy + ft.y * tile);
      ctx.restore();
    }
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

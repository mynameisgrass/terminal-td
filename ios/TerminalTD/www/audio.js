// Lightweight Web Audio SFX & iOS Haptic bridge (zero external audio files needed)
(function () {
  let ctx = null;
  let muted = false;

  function ensureCtx() {
    if (muted) return null;
    if (!ctx && (window.AudioContext || window.webkitAudioContext)) {
      const AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC();
    }
    if (ctx && ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }
    return ctx;
  }

  function tone(freq, dur, type = "triangle", gainVal = 0.06, slideTo = null) {
    const c = ensureCtx();
    if (!c) return;
    const now = c.currentTime;
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, now);
    if (slideTo) osc.frequency.exponentialRampToValueAtTime(Math.max(30, slideTo), now + dur);
    g.gain.setValueAtTime(gainVal, now);
    g.gain.exponentialRampToValueAtTime(0.0001, now + dur);
    osc.connect(g);
    g.connect(c.destination);
    osc.start(now);
    osc.stop(now + dur);
  }

  function haptic(style = "light") {
    try {
      if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.haptic) {
        window.webkit.messageHandlers.haptic.postMessage(style);
      }
    } catch (_) {}
  }

  window.TDAudio = {
    isMuted: () => muted,
    toggleMute: () => {
      muted = !muted;
      return muted;
    },
    haptic,
    playPlace: () => {
      tone(340, 0.07, "triangle", 0.07, 520);
      haptic("light");
    },
    playUpgrade: () => {
      tone(440, 0.08, "triangle", 0.07, 740);
      setTimeout(() => tone(660, 0.10, "sine", 0.07, 920), 60);
      haptic("medium");
    },
    playShoot: (kind) => {
      if (kind === "railgun" || kind === "sniper" || kind === "astral_lance") {
        tone(680, 0.09, "sawtooth", 0.04, 140);
      } else if (kind === "electro" || kind === "tesla_coil") {
        tone(820, 0.06, "square", 0.03, 300);
      } else if (kind === "demoman" || kind === "mortar" || kind === "war_machine") {
        tone(140, 0.12, "sawtooth", 0.06, 45);
      } else {
        tone(420, 0.035, "triangle", 0.025, 220);
      }
    },
    playBoss: () => {
      tone(110, 0.35, "sawtooth", 0.09, 75);
      setTimeout(() => tone(95, 0.40, "sawtooth", 0.09, 60), 180);
      haptic("heavy");
    },
    playRevive: () => {
      tone(523, 0.14, "sine", 0.08, 1046);
      haptic("medium");
    },
    playGacha: (highRarity) => {
      tone(440, 0.1, "triangle", 0.07, 660);
      setTimeout(() => tone(660, 0.12, "triangle", 0.07, 880), 80);
      if (highRarity) {
        setTimeout(() => tone(880, 0.22, "sine", 0.09, 1320), 170);
        haptic("heavy");
      } else {
        haptic("light");
      }
    },
    playCoin: () => tone(980, 0.07, "sine", 0.05, 1318),
  };
})();

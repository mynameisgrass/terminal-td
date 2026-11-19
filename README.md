# Bastion TD (Terminal + Web + iOS)

A full-featured **Gacha Tower Defense** game playable in your **Terminal**, **Web Browser**, or natively on **iPhone (`.ipa`)**.

## Features
- **48 Collectible Gacha Defender Units** across 6 rarities (`Common` → `Transcendent`), each with **5 Upgrade Levels**
- **4 Summon Banners** (`Standard`, `Warfare & Boss-Killer`, `Summoners & Support`, `Mythic Chaos`), **Mythic Pity**, and configurable **Auto-Sell**
- **8-Slot Loadout & Inventory** with duplicate selling for Coins
- **52 Enemies & 10 Bosses** across **30 Campaign Waves** + Endless Mode
- **11 Friendly Road Units** (Barracks, Phoenix Knights with **Second Life** revives, Immortal Phoenixes with **3 Second Lives**, Battle Tanks, Colossal Mechs)
- **Support Buffs, Gold Farms, Road Spikes, Execute, Armor Shred, Chain Lightning**
- **5 Large `36x18` Wide-Road Maps** & **4 Difficulties** (`Easy`, `Normal`, `Hard`, `Nightmare` with force-start timers)
- **`1x / 2x / 3x / 5x / 10x` Speed**, **Auto-Start Waves**, **Prestart Wave Rush**, and **Gold Tavern**

## Play in Terminal
```bash
python3 td.py
```

## Play in Browser
Open `ios/TerminalTD/www/index.html` (or serve `ios/TerminalTD/www/` with `python3 -m http.server`).

## Install on iPhone (`.ipa`)
Every push to `main` runs `.github/workflows/ios-ipa.yml` on `macos-14`, builds `BastionTD-unsigned.ipa`, and attaches it to **Releases** & **Workflow Artifacts**.
Install the `.ipa` on your iPhone using **Sideloadly**, **AltStore**, **SideStore**, or **TrollStore**.

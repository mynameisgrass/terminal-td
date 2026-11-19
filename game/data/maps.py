"""Big map definitions on an 18x9 meta-grid (36x18 grid with 2-tile-wide roads)."""

from __future__ import annotations

from typing import Tuple

from game.models import MapDef


MAPS: Tuple[MapDef, ...] = (
    MapDef(
        key="grand_serpentine",
        name="Grand Serpentine",
        description="Massive 96-tile winding highway with deep killzones",
        meta_waypoints=(
            (0, 0),
            (2, 0),
            (2, 7),
            (5, 7),
            (5, 1),
            (8, 1),
            (8, 7),
            (11, 7),
            (11, 1),
            (14, 1),
            (14, 7),
            (17, 7),
        ),
    ),
    MapDef(
        key="iron_canyon",
        name="Iron Canyon",
        description="Wide sweeping valley bends built for high-DPS & buffers",
        meta_waypoints=(
            (0, 4),
            (3, 4),
            (3, 0),
            (7, 0),
            (7, 8),
            (11, 8),
            (11, 1),
            (15, 1),
            (15, 5),
            (17, 5),
        ),
    ),
    MapDef(
        key="spiral_citadel",
        name="Spiral Citadel",
        description="Colossal 176-tile spiral fortress to the inner core",
        meta_waypoints=(
            (0, 0),
            (17, 0),
            (17, 8),
            (1, 8),
            (1, 2),
            (15, 2),
            (15, 6),
            (3, 6),
            (3, 4),
            (12, 4),
        ),
    ),
    MapDef(
        key="twin_crossings",
        name="Twin Crossings",
        description="Parallel lanes ideal for Commander, DJ & Mortar crossfire",
        meta_waypoints=(
            (0, 1),
            (4, 1),
            (4, 7),
            (7, 7),
            (7, 1),
            (10, 1),
            (10, 7),
            (13, 7),
            (13, 2),
            (17, 2),
        ),
    ),
    MapDef(
        key="coliseum_loop",
        name="Coliseum Arena",
        description="Grand arena loop surrounding a central command island",
        meta_waypoints=(
            (0, 4),
            (2, 4),
            (2, 1),
            (15, 1),
            (15, 7),
            (5, 7),
            (5, 3),
            (12, 3),
            (12, 5),
            (8, 5),
        ),
    ),
)

"""
Shared constants for Felsted School BeamNG:Drive map generation — v3.0.

Geographic data sourced from OpenStreetMap, SRTM-30m, OS Open Data, and
Strava elevation segments.  Felsted School, Stebbing Road, Great Dunmow,
Essex CM6 3LL.  Grid ref TL679206.
"""

import math
from pathlib import Path

# ── Identity ───────────────────────────────────────────────────────────────────
MAP_NAME    = "felsted"
MAP_TITLE   = "Felsted School"
MAP_VERSION = "3.0.0"
MAP_DESC    = (
    "Felsted School campus, Essex, England — a 90-acre independent school "
    "founded in 1564.  2 km × 2 km world at 2 m terrain resolution.  "
    "Road geometry, buildings, and water from OpenStreetMap; terrain from "
    "SRTM-30m elevation data (River Chelmer valley 40 m → campus 76 m → "
    "North Essex hills 84 m)."
)
MAP_AUTHOR = "felsted-ng-drive"

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent.resolve()
DATA_DIR     = ROOT / "data"
LEVELS_DIR   = ROOT / "levels" / MAP_NAME
TERRAIN_DIR  = LEVELS_DIR / "terrainGrid"

OSM_CACHE    = DATA_DIR / "felsted_osm.json"
SRTM_CACHE   = DATA_DIR / "felsted_srtm_32x32.json"

# ── GPS anchor ────────────────────────────────────────────────────────────────
# Centre of main school building façade; map is 2 048 m square around it.
CENTER_LAT = 51.8588   # 51°51'32"N
CENTER_LON =  0.4371   # 0°26'14"E

# Bounding box for OSM / elevation API queries (S, W, N, E).
# Slightly wider than the world so all terrain edges have data.
BBOX = (51.840, 0.410, 51.880, 0.465)

# ── Projection ────────────────────────────────────────────────────────────────
_LAT_SCALE = 111_139.0
_LON_SCALE = 111_139.0 * math.cos(math.radians(CENTER_LAT))  # ≈ 68 620 m/°


def gps_to_world(lat: float, lon: float) -> tuple[float, float]:
    """Return BeamNG world (X east, Y north) in metres from map centre."""
    return (lon - CENTER_LON) * _LON_SCALE, (lat - CENTER_LAT) * _LAT_SCALE


def world_to_gps(x: float, y: float) -> tuple[float, float]:
    return CENTER_LAT + y / _LAT_SCALE, CENTER_LON + x / _LON_SCALE


# ── Terrain grid ──────────────────────────────────────────────────────────────
# 1024 × 1024 cells; (BLOCK_SIZE+1)² vertex grid; 2 m/cell → 2 048 m world.
BLOCK_SIZE  = 1024
SQUARE_SIZE = 2.0
GRID_SIZE   = BLOCK_SIZE + 1           # 1 025 vertices per side
WORLD_HALF  = BLOCK_SIZE * SQUARE_SIZE / 2   # ±1 024 m from centre

MAX_TERRAIN_HEIGHT = 200.0   # metres; all heights encoded against this

# Key real-world spot heights (metres ASL) from SRTM-30m + Strava segments:
CAMPUS_ELEV = 76.0   # main campus plateau (SRTM measured 79 m; Strava 76 m)
VALLEY_ELEV = 40.0   # River Chelmer thalweg (SRTM min in area)
HILL_N_ELEV = 84.0   # north-west ridge (SRTM max in area)


# ── World ↔ heightmap helpers ─────────────────────────────────────────────────

def world_to_hm(wx: float, wy: float) -> tuple[int, int]:
    """World (X, Y) → heightmap (row, col).  Row 0 = north edge."""
    col = int((wx + WORLD_HALF) / SQUARE_SIZE)
    row = int((WORLD_HALF - wy) / SQUARE_SIZE)
    return max(0, min(BLOCK_SIZE, row)), max(0, min(BLOCK_SIZE, col))


def hm_to_world(row: int, col: int) -> tuple[float, float]:
    wx = col * SQUARE_SIZE - WORLD_HALF + SQUARE_SIZE / 2
    wy = WORLD_HALF - row * SQUARE_SIZE - SQUARE_SIZE / 2
    return wx, wy

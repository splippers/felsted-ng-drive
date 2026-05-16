"""
Shared constants for Felsted School BeamNG:Drive map generation.

Geographic data sourced from OpenStreetMap, OS Open Data, and Strava elevation
segments.  Felsted School, Stebbing Road, Great Dunmow, Essex CM6 3LL.
Grid ref TL679206.
"""

import math

# ── Identity ───────────────────────────────────────────────────────────────────
MAP_NAME  = "felsted"
MAP_TITLE = "Felsted School"
MAP_DESC  = (
    "Felsted School campus, Essex, England — a 90-acre independent school "
    "founded in 1564.  Faithfully recreated from OpenStreetMap road geometry "
    "and SRTM elevation data.  Features Stebbing Road, the chapel approach, "
    "campus loop, car parks, and the sports fields."
)
MAP_AUTHOR  = "felsted-ng-drive"
MAP_VERSION = "0.1.0"

# ── GPS anchor ────────────────────────────────────────────────────────────────
# Centre of main school building; chosen so the campus sits in the middle of
# the 2 km × 2 km world.
CENTER_LAT = 51.8588   # 51°51'32"N
CENTER_LON =  0.4371   # 0°26'14"E

# Bounding box used when querying OSM / elevation APIs (S, W, N, E).
# Adds ~1.3 km of countryside on every side around the 600 m campus.
BBOX = (51.845, 0.415, 51.875, 0.460)

# ── Projection ────────────────────────────────────────────────────────────────
# Flat-Earth equirectangular projection centred on (CENTER_LAT, CENTER_LON).
_LAT_SCALE = 111_139.0                                    # m / degree latitude
_LON_SCALE = 111_139.0 * math.cos(math.radians(CENTER_LAT))  # m / degree longitude ≈ 68 620


def gps_to_world(lat: float, lon: float) -> tuple[float, float]:
    """Return BeamNG world (X east, Y north) in metres from map centre."""
    x = (lon - CENTER_LON) * _LON_SCALE
    y = (lat - CENTER_LAT) * _LAT_SCALE
    return x, y


def world_to_gps(x: float, y: float) -> tuple[float, float]:
    """Inverse of gps_to_world."""
    lon = CENTER_LON + x / _LON_SCALE
    lat = CENTER_LAT + y / _LAT_SCALE
    return lat, lon


# ── Terrain grid ──────────────────────────────────────────────────────────────
# Torque3D terrain: BLOCK_SIZE × BLOCK_SIZE cells;
#                   (BLOCK_SIZE + 1)² vertex grid.
# World footprint = BLOCK_SIZE × SQUARE_SIZE metres each axis.
BLOCK_SIZE  = 512    # must be a power of 2
SQUARE_SIZE = 4.0    # metres per cell edge  →  512 × 4 = 2 048 m square world
GRID_SIZE   = BLOCK_SIZE + 1           # 513 vertices per side
WORLD_HALF  = BLOCK_SIZE * SQUARE_SIZE / 2   # ±1 024 m from centre

# Height encoding: 0 → 0 m,  65535 → MAX_TERRAIN_HEIGHT m.
MAX_TERRAIN_HEIGHT = 200.0   # must exceed any real terrain value

# Key real-world elevations (metres ASL, from Strava / OS):
CAMPUS_ELEV = 76.0   # main campus plateau
VALLEY_ELEV = 51.0   # River Chelmer valley (lowest on map)
HILL_N_ELEV = 88.0   # gentle hill NW of campus


# ── World-coordinate helpers ──────────────────────────────────────────────────
def world_to_hm(wx: float, wy: float) -> tuple[int, int]:
    """
    Convert BeamNG world (X, Y) to heightmap (row, col).
    Row 0 = north edge, row BLOCK_SIZE = south edge.
    Col 0 = west edge, col BLOCK_SIZE = east edge.
    """
    col = int((wx + WORLD_HALF) / SQUARE_SIZE)
    row = int((WORLD_HALF - wy) / SQUARE_SIZE)
    col = max(0, min(BLOCK_SIZE, col))
    row = max(0, min(BLOCK_SIZE, row))
    return row, col


def hm_to_world(row: int, col: int) -> tuple[float, float]:
    """Inverse of world_to_hm (returns cell-centre world coordinates)."""
    wx = col * SQUARE_SIZE - WORLD_HALF + SQUARE_SIZE / 2
    wy = WORLD_HALF - row * SQUARE_SIZE - SQUARE_SIZE / 2
    return wx, wy

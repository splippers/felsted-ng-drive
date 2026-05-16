"""
Terrain heightmap generator for Felsted School.

Elevation data from two sources (tried in order):
  1. Online: OpenTopoData SRTM-30m API (real data, requires internet).
  2. Offline: procedural model tuned to match known spot elevations from
     Strava segment data (Stebbing Road climb: 51–76 m over 1.29 km) and
     OS/Felsted parish plan records.

The output is a float32 NumPy array of shape (GRID_SIZE, GRID_SIZE) where
each element is an absolute elevation in metres.  The array is in image
convention: row 0 = north edge, row N = south edge.
"""

from __future__ import annotations

import math
import logging
import urllib.request
import json

import numpy as np
from scipy.ndimage import gaussian_filter, zoom

from tools.constants import (
    BLOCK_SIZE, GRID_SIZE, SQUARE_SIZE, WORLD_HALF,
    CAMPUS_ELEV, VALLEY_ELEV, HILL_N_ELEV,
    CENTER_LAT, CENTER_LON, BBOX,
    world_to_hm,
)

log = logging.getLogger(__name__)

_OPENTOPODATA = "https://api.opentopodata.org/v1/srtm30m"
_BATCH = 100   # max locations per OpenTopoData request


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gaussian_bump(grid: np.ndarray, row: int, col: int,
                   radius_m: float, delta: float) -> None:
    """Add a Gaussian hill (+) or depression (–) to grid in-place."""
    radius_px = radius_m / SQUARE_SIZE
    rr = np.arange(GRID_SIZE, dtype=np.float32)[:, None]
    cc = np.arange(GRID_SIZE, dtype=np.float32)[None, :]
    dist2 = (rr - row) ** 2 + (cc - col) ** 2
    grid += delta * np.exp(-dist2 / (2 * radius_px ** 2))


def _road_grade_cut(grid: np.ndarray,
                    wx_start: float, wy_start: float,
                    wx_end:   float, wy_end:   float,
                    elev_start: float, elev_end: float,
                    influence_m: float = 24.0) -> None:
    """
    Blend the terrain along a straight road segment toward a linear grade.
    Removes dramatic bumps directly on the road surface.
    """
    rs, cs = world_to_hm(wx_start, wy_start)
    re, ce = world_to_hm(wx_end,   wy_end)
    steps  = max(abs(re - rs), abs(ce - cs), 1)
    influence_px = influence_m / SQUARE_SIZE

    for i in range(steps + 1):
        t    = i / steps
        r    = int(rs + (re - rs) * t)
        c    = int(cs + (ce - cs) * t)
        elev = elev_start + (elev_end - elev_start) * t

        rlo = max(0, r - int(influence_px * 2))
        rhi = min(GRID_SIZE, r + int(influence_px * 2) + 1)
        clo = max(0, c - int(influence_px * 2))
        chi = min(GRID_SIZE, c + int(influence_px * 2) + 1)

        rr  = np.arange(rlo, rhi)[:, None]
        cc  = np.arange(clo, chi)[None, :]
        d2  = (rr - r) ** 2 + (cc - c) ** 2
        blend = np.exp(-d2 / (2 * influence_px ** 2))
        grid[rlo:rhi, clo:chi] = (
            grid[rlo:rhi, clo:chi] * (1 - blend) + elev * blend
        )


# ── Procedural terrain ────────────────────────────────────────────────────────

def generate_synthetic() -> np.ndarray:
    """
    Build a procedurally generated elevation array matching known spot heights.

    Returns float32 (GRID_SIZE, GRID_SIZE) in metres.
    """
    rng  = np.random.default_rng(42)
    grid = np.full((GRID_SIZE, GRID_SIZE), CAMPUS_ELEV, dtype=np.float32)

    # ── Large-scale rolling Essex countryside ──────────────────────────────
    xs = np.linspace(0, 1, GRID_SIZE, dtype=np.float32)
    ys = np.linspace(0, 1, GRID_SIZE, dtype=np.float32)
    xx, yy = np.meshgrid(xs, ys, indexing="ij")

    grid += 6.0 * np.sin(xx * math.pi * 2.5 + 0.3) * np.cos(yy * math.pi * 2.1 + 0.7)
    grid += 4.0 * np.cos(xx * math.pi * 4.2 + 1.1) * np.sin(yy * math.pi * 3.8 + 0.2)
    grid += 2.5 * np.sin(xx * math.pi * 7.1 + 2.3) * np.cos(yy * math.pi * 5.5 + 1.8)
    grid += 1.0 * np.cos(xx * math.pi * 11.3)       * np.sin(yy * math.pi * 9.7 + 0.4)
    grid += 0.4 * rng.standard_normal((GRID_SIZE, GRID_SIZE)).astype(np.float32)

    # ── River Chelmer valley – runs roughly SW→SE through southern third ──
    # In image coords row 0=north, so row 0.72 (72%) ≈ south portion.
    river_row = int(0.72 * GRID_SIZE)
    river_sigma = 50.0 / SQUARE_SIZE   # 50 m half-width
    rows = np.arange(GRID_SIZE, dtype=np.float32)[:, None]
    river_mask = np.exp(-((rows - river_row) ** 2) / (2 * river_sigma ** 2))
    grid -= (CAMPUS_ELEV - VALLEY_ELEV) * river_mask

    # Valley handled by the Gaussian mask above; no extra meander loop needed.

    # ── North hill (NW of campus) ──────────────────────────────────────────
    r, c = world_to_hm(-350, 600)
    _gaussian_bump(grid, r, c, 400.0, HILL_N_ELEV - CAMPUS_ELEV)

    r, c = world_to_hm(420, 680)
    _gaussian_bump(grid, r, c, 280.0, (HILL_N_ELEV - 4) - CAMPUS_ELEV)

    # ── Campus plateau – blend toward 76 m ────────────────────────────────
    r_cam, c_cam = world_to_hm(0, 0)
    rows_g = np.arange(GRID_SIZE, dtype=np.float32)[:, None]
    cols_g = np.arange(GRID_SIZE, dtype=np.float32)[None, :]
    campus_sigma = 280.0 / SQUARE_SIZE
    dist2 = (rows_g - r_cam) ** 2 + (cols_g - c_cam) ** 2
    campus_blend = np.exp(-dist2 / (2 * campus_sigma ** 2))
    grid = grid * (1.0 - campus_blend * 0.9) + CAMPUS_ELEV * (campus_blend * 0.9)

    # ── Stebbing Road grade cut (real: 51–76 m over 1.29 km) ─────────────
    _road_grade_cut(grid, -260, -1024, -260, -200,
                    elev_start=62.0, elev_end=72.0)
    _road_grade_cut(grid, -260, -200, -250, 500,
                    elev_start=72.0, elev_end=80.0)

    # ── Entrance drive cut ────────────────────────────────────────────────
    _road_grade_cut(grid, -260, -200, 0, -50,
                    elev_start=72.0, elev_end=75.5)

    # ── Smooth everything (mild low-pass to remove grid noise) ───────────
    grid = gaussian_filter(grid, sigma=1.2)

    # ── Re-apply campus plateau after smoothing ───────────────────────────
    grid = grid * (1.0 - campus_blend * 0.5) + CAMPUS_ELEV * (campus_blend * 0.5)

    return grid.astype(np.float32)


# ── Online fetch ──────────────────────────────────────────────────────────────

def _fetch_elevations_batch(lats: list[float], lons: list[float]) -> list[float]:
    locations = "|".join(f"{la:.6f},{lo:.6f}" for la, lo in zip(lats, lons))
    url = f"{_OPENTOPODATA}?locations={locations}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
        return [pt["elevation"] for pt in data["results"]]
    except Exception as exc:
        log.warning("OpenTopoData batch failed: %s", exc)
        return [CAMPUS_ELEV] * len(lats)


def fetch_srtm_grid(coarse: int = 32) -> np.ndarray:
    """
    Download a coarse_×coarse_ grid of SRTM-30m elevations covering BBOX,
    then zoom+interpolate to (GRID_SIZE, GRID_SIZE).

    Returns float32 (GRID_SIZE, GRID_SIZE) in metres.
    """
    s, w, n, e = BBOX
    lats = np.linspace(s, n, coarse).tolist()
    lons = np.linspace(w, e, coarse).tolist()

    flat_lats = [la for la in lats for _ in lons]
    flat_lons = [lo for _ in lats for lo in lons]

    elevs: list[float] = []
    for i in range(0, len(flat_lats), _BATCH):
        elevs.extend(_fetch_elevations_batch(flat_lats[i:i+_BATCH],
                                              flat_lons[i:i+_BATCH]))

    coarse_grid = np.array(elevs, dtype=np.float32).reshape(coarse, coarse)
    # Note: lats go S→N; row 0 in image = north → flip vertically
    coarse_grid = np.flipud(coarse_grid)

    factor = GRID_SIZE / coarse
    full   = zoom(coarse_grid, factor, order=3)
    full   = gaussian_filter(full, sigma=2.0)
    return full[:GRID_SIZE, :GRID_SIZE].astype(np.float32)


# ── Public API ────────────────────────────────────────────────────────────────

def build_elevation(online: bool = False) -> np.ndarray:
    """
    Return an elevation array (float32, metres) of shape (GRID_SIZE, GRID_SIZE).
    Falls back to procedural generation if online fetch fails or is disabled.
    """
    if online:
        log.info("Fetching SRTM elevation from OpenTopoData …")
        try:
            grid = fetch_srtm_grid(coarse=32)
            log.info("SRTM grid fetched OK, elevation range %.1f–%.1f m",
                     grid.min(), grid.max())
            return grid
        except Exception as exc:
            log.warning("SRTM fetch failed (%s); falling back to synthetic.", exc)

    log.info("Generating synthetic terrain …")
    grid = generate_synthetic()
    log.info("Synthetic terrain done, elevation range %.1f–%.1f m",
             grid.min(), grid.max())
    return grid


def elev_at_world(grid: np.ndarray, wx: float, wy: float) -> float:
    """Bilinear sample of elevation array at world coordinates (X, Y)."""
    from tools.constants import WORLD_HALF, SQUARE_SIZE, BLOCK_SIZE
    cf = (wx + WORLD_HALF) / SQUARE_SIZE
    rf = (WORLD_HALF - wy) / SQUARE_SIZE
    c0 = max(0, min(BLOCK_SIZE - 1, int(cf)))
    r0 = max(0, min(BLOCK_SIZE - 1, int(rf)))
    c1, r1 = min(BLOCK_SIZE, c0 + 1), min(BLOCK_SIZE, r0 + 1)
    tc, tr = cf - c0, rf - r0
    return float(
        grid[r0, c0] * (1-tr) * (1-tc) +
        grid[r0, c1] * (1-tr) *    tc  +
        grid[r1, c0] *    tr  * (1-tc) +
        grid[r1, c1] *    tr  *    tc
    )

#!/usr/bin/env python3
"""
Felsted School BeamNG:Drive map generator.

Usage
─────
    # Offline (deterministic, no network):
    python tools/generate.py

    # Online (fetches real OSM roads + SRTM elevation):
    python tools/generate.py --online

    # Package the result as a deployable mod zip:
    python tools/generate.py --zip

Output files
────────────
    levels/felsted/main.level.json       BeamNG scene graph
    levels/felsted/terrainGrid/felsted.ter   Binary terrain
    levels/felsted/terrainGrid/felsted_height.png  PNG fallback heightmap
    levels/felsted/preview.png           Thumbnail for the level browser
    felsted.zip  (with --zip)            Ready-to-install mod archive

Deploy
──────
    Copy felsted.zip to:
      Windows: %USERPROFILE%\\Documents\\BeamNG.drive\\mods\\
      Linux:   ~/BeamNG.drive/mods/
    Then restart BeamNG and select "Felsted School" from the map list.

If the terrain appears flat on first load, open World Editor →
Terrain Editor → Import Heightmap and point it at:
    levels/felsted/terrainGrid/felsted_height.png
(max height = 200 m).
"""

from __future__ import annotations

import argparse
import logging
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

from tools.heightmap    import build_elevation, elev_at_world
from tools.terrain_file import write_ter, write_heightmap_png, write_preview_png
from tools.osm_roads    import build_roads
from tools.level_builder import build_level
from tools.constants    import MAP_NAME

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

LEVELS_DIR    = ROOT / "levels" / MAP_NAME
TERRAIN_DIR   = LEVELS_DIR / "terrainGrid"
LEVEL_JSON    = LEVELS_DIR / "main.level.json"
TER_FILE      = TERRAIN_DIR / f"{MAP_NAME}.ter"
HEIGHT_PNG    = TERRAIN_DIR / f"{MAP_NAME}_height.png"
PREVIEW_PNG   = LEVELS_DIR / "preview.png"
MOD_ZIP       = ROOT / f"{MAP_NAME}.zip"


def main(online: bool = False, pack_zip: bool = False) -> None:
    log.info("=== Felsted School map generator ===")

    # 1. Elevation / terrain ─────────────────────────────────────────────────
    log.info("Step 1/4 – build elevation grid")
    elev = build_elevation(online=online)
    elev_fn = lambda wx, wy: elev_at_world(elev, wx, wy)

    # 2. Terrain files ───────────────────────────────────────────────────────
    log.info("Step 2/4 – write terrain files")
    TERRAIN_DIR.mkdir(parents=True, exist_ok=True)
    write_ter(TER_FILE, elev)
    write_heightmap_png(HEIGHT_PNG, elev)
    write_preview_png(PREVIEW_PNG, elev)

    # 3. Road network ────────────────────────────────────────────────────────
    log.info("Step 3/4 – build road network")
    roads = build_roads(elevation_fn=elev_fn, online=online)

    # 4. Level JSON ──────────────────────────────────────────────────────────
    log.info("Step 4/4 – write main.level.json")
    build_level(roads, LEVEL_JSON)

    log.info("Generation complete.")

    if pack_zip:
        _pack_zip()


def _pack_zip() -> None:
    log.info("Packaging mod zip → %s", MOD_ZIP)
    # Collect all files under levels/
    files = list((ROOT / "levels").rglob("*"))
    files = [f for f in files if f.is_file()]

    with zipfile.ZipFile(MOD_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arc = f.relative_to(ROOT)
            zf.write(f, arc)

    size_mb = MOD_ZIP.stat().st_size / 1_048_576
    log.info("Zip written (%.1f MB): %s", size_mb, MOD_ZIP)
    log.info("Install: copy %s to your BeamNG mods/ folder.", MOD_ZIP.name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate Felsted School BeamNG map")
    ap.add_argument("--online",  action="store_true",
                    help="Fetch live OSM roads and SRTM elevation data")
    ap.add_argument("--zip",     action="store_true",
                    help="Package output as felsted.zip mod archive")
    args = ap.parse_args()
    main(online=args.online, pack_zip=args.zip)

#!/usr/bin/env python3
"""
Felsted School BeamNG:Drive map generator — v3.0 (photoreal).

Usage
─────
    # Default: use cached OSM + SRTM + satellite data
    python3 tools/generate.py

    # Download satellite imagery (ESRI WorldImagery, zoom 17 ~0.74 m/px)
    python3 tools/generate.py --satellite

    # Higher-res satellite (zoom 18, ~0.37 m/px, ~4× slower download)
    python3 tools/generate.py --satellite --zoom 18

    # Full online refresh: OSM + SRTM + satellite
    python3 tools/generate.py --online --satellite

    # Package as felsted.zip mod archive
    python3 tools/generate.py --zip

Output
──────
    levels/felsted/main.level.json                   BeamNG scene graph
    levels/felsted/terrainGrid/felsted.ter            Binary terrain (1025×1025)
    levels/felsted/terrainGrid/felsted_height.png     PNG fallback heightmap
    levels/felsted/preview.png                        Level-browser thumbnail
    levels/felsted/art/terrain/satellite/satellite.png  Aerial photo ground texture
    levels/felsted/art/shapes/buildings/bld_*.dae    3D building meshes
    felsted.zip (--zip)                               Deployable mod archive

Photoreal notes
───────────────
    • Ground texture: ESRI WorldImagery tiles composited into one 4096×4096 PNG.
      The TerrainMaterial scale=2048 maps the image 1:1 over the 2048 m world.
    • Buildings: OSM footprints extruded to estimated heights as COLLADA meshes.
    • Railway: Witham–Dunmow branch (GER, closed 1953) shown as gravel trackbed.
    • Historical photos: drop georectified JPEGs into art/decals/historic/ and
      add them as ScenarioObject decals in the World Editor.

Deploy
──────
    Copy felsted.zip to:
      Windows: %USERPROFILE%\\Documents\\BeamNG.drive\\mods\\
      Linux:   ~/BeamNG.drive/mods/
    Restart BeamNG → Free Roam → Felsted School.
"""

from __future__ import annotations

import argparse
import logging
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

from tools.constants     import MAP_NAME, MAP_VERSION, LEVELS_DIR, TERRAIN_DIR
from tools.heightmap     import build_elevation, elev_at_world
from tools.terrain_file  import (write_ter, write_heightmap_png, write_preview_png,
                                  SATELLITE_LAYER_TEX)
from tools.osm_roads     import build_roads
from tools.osm_parse     import load as parse_osm
from tools.buildings     import build_building_objects
from tools.buildings3d   import build_building_meshes
from tools.water         import build_water_objects
from tools.vegetation    import build_vegetation_objects
from tools.railway       import build_railway_objects
from tools.level_builder import build_level

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

LEVEL_JSON = LEVELS_DIR / "main.level.json"
TER_FILE   = TERRAIN_DIR / f"{MAP_NAME}.ter"
HEIGHT_PNG = TERRAIN_DIR / f"{MAP_NAME}_height.png"
PREVIEW    = LEVELS_DIR  / "preview.png"
MOD_ZIP    = ROOT / f"{MAP_NAME}.zip"


def main(
    online:          bool = False,
    pack_zip:        bool = False,
    do_satellite:    bool = False,
    satellite_zoom:  int  = 17,
) -> None:
    log.info("=== Felsted School map generator v%s (photoreal) ===", MAP_VERSION)

    # 1. Elevation ─────────────────────────────────────────────────────────────
    log.info("Step 1/6 – build elevation (1025×1025, 2 m/cell, SRTM-30m base)")
    elev    = build_elevation(online=online)
    elev_fn = lambda wx, wy: elev_at_world(elev, wx, wy)

    # 2. Satellite texture ─────────────────────────────────────────────────────
    sat_path = Path(SATELLITE_LAYER_TEX.replace("levels/felsted/", str(LEVELS_DIR) + "/"))
    has_sat  = sat_path.exists()

    if do_satellite and not has_sat:
        log.info("Step 2/6 – download satellite imagery (zoom=%d)", satellite_zoom)
        from tools.satellite import build_satellite_texture, write_satellite_material
        build_satellite_texture(zoom=satellite_zoom)
        write_satellite_material()
        has_sat = sat_path.exists()
    elif has_sat:
        log.info("Step 2/6 – satellite texture already present, skipping download")
    else:
        log.info("Step 2/6 – no satellite texture (run --satellite to download)")

    # 3. Terrain files ─────────────────────────────────────────────────────────
    log.info("Step 3/6 – write terrain files (satellite_layer=%s)", has_sat)
    TERRAIN_DIR.mkdir(parents=True, exist_ok=True)
    write_ter(TER_FILE, elev, use_satellite=has_sat)
    write_heightmap_png(HEIGHT_PNG, elev)
    write_preview_png(PREVIEW, elev)

    # 4. OSM scene objects ─────────────────────────────────────────────────────
    log.info("Step 4/6 – parse OSM data and build scene objects")
    osm        = parse_osm()
    roads      = build_roads(elevation_fn=elev_fn, online=online)
    buildings  = build_building_objects(osm, elev_fn)
    water      = build_water_objects(osm, elev_fn)
    vegetation = build_vegetation_objects(osm, elev_fn)

    # 5. 3D building meshes + railway ─────────────────────────────────────────
    log.info("Step 5/6 – generate 3D building meshes and railway")
    bld_meshes = build_building_meshes(osm, elev_fn)
    railway    = build_railway_objects(osm, elev_fn)

    # 6. Level JSON ────────────────────────────────────────────────────────────
    log.info("Step 6/6 – write main.level.json")
    build_level(
        roads           = roads,
        buildings       = buildings,
        water           = water,
        vegetation      = vegetation,
        building_meshes = bld_meshes,
        railway         = railway,
        out_path        = LEVEL_JSON,
    )

    log.info("Generation complete (v%s).", MAP_VERSION)

    if pack_zip:
        _pack_zip()


def _pack_zip() -> None:
    log.info("Packaging mod zip → %s", MOD_ZIP)
    files = [f for f in (ROOT / "levels").rglob("*") if f.is_file()]
    with zipfile.ZipFile(MOD_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.relative_to(ROOT))
    log.info("Zip written (%.1f MB): %s", MOD_ZIP.stat().st_size/1_048_576, MOD_ZIP)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=f"Felsted School BeamNG map generator v{MAP_VERSION}")
    ap.add_argument("--online",    action="store_true",
                    help="Refresh OSM roads + SRTM elevation from live APIs")
    ap.add_argument("--satellite", action="store_true",
                    help="Download ESRI WorldImagery satellite tiles")
    ap.add_argument("--zoom",      type=int, default=17,
                    help="Tile zoom level for satellite download (17=0.74m/px, 18=0.37m/px)")
    ap.add_argument("--zip",       action="store_true",
                    help="Package output as felsted.zip mod archive")
    args = ap.parse_args()
    main(online=args.online, pack_zip=args.zip,
         do_satellite=args.satellite, satellite_zoom=args.zoom)

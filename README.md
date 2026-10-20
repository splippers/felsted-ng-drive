# felsted-ng-drive

A BeamNG:Drive map of **Felsted School** campus, Essex, England (CM6 3LL).

Felsted School is a 90-acre independent school founded in 1564, set in rolling
North Essex countryside at ~76 m ASL, west of the A120 between Braintree and
Dunmow.

## What's in the map

| Feature | Source |
|---|---|
| Terrain (40–77 m ASL in-world) | Environment Agency LiDAR Composite DTM 2 m (OGL) |
| Stebbing Road (main approach) | Research from OS, Strava segment, satellite |
| Campus entrance drive | School campus map PDF |
| Chapel forecourt spur | School campus map PDF |
| Campus loop road | School campus map PDF |
| Car park (south gate) | Satellite / campus map |
| Sports fields access road | Satellite |
| Braintree Road (B1008) approach | OSM |
| Service road (rear of buildings) | Satellite |
| 4 vehicle spawn points | Campus landmarks |
| River Chelmer valley (south) | LiDAR DTM |

Terrain is sourced from the **Environment Agency LiDAR Composite Digital
Terrain Model** (2 m resolution, ±15 cm vertical RMSE, Open Government
Licence), fetched as GeoTIFF from the Defra Data Services Platform WCS
endpoint.  The 30 m SRTM model remains as an automatic fallback.

Run `python3 tools/generate.py --online` to replace the static road network with
live OSM geometry; add `--lidar` to download fresh LiDAR terrain.

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Generate map assets (offline, no network needed)
python3 tools/generate.py

# Package as BeamNG mod zip
python3 tools/generate.py --zip

# Download Environment Agency LiDAR DTM 2 m terrain (recommended, one-off ~25 MB)
python3 tools/generate.py --lidar

# Fetch real OSM roads + LiDAR terrain, then package
python3 tools/generate.py --online --lidar --zip
```

Then copy `felsted.zip` to your BeamNG mods folder:

- **Windows**: `%USERPROFILE%\Documents\BeamNG.drive\mods\`
- **Linux**: `~/BeamNG.drive/mods/`

Restart BeamNG and pick **Felsted School** from the Free Roam map list.

## Terrain source priority

`tools/heightmap.py` picks the best available base, with automatic fallback:

| Priority | Source | Resolution | Cache |
|---|---|---|---|
| 1 | **EA LiDAR Composite DTM** | 2 m | `data/felsted_lidar_1025.npy` |
| 2 | SRTM | 30 m | `data/felsted_srtm_32x32.json` |
| 3 | Live OpenTopoData SRTM | 30 m | — |
| 4 | Synthetic procedural model | — | — |

LiDAR and SRTM bases are **resampled by latitude/longitude onto the world
grid** (never stretched), so terrain features line up with OSM geometry.
On a LiDAR base the synthetic road cuts, campus plateau blend, and large
fBm noise are all skipped — the real survey already contains every road
camber, kerb, and the river valley.

`tools/lidar.py` converts WGS84 → OSGB36 (EPSG:27700) with a 7-parameter
Helmert transform plus the OS polynomial grid series.  The projection
matches the OS published worked example to 0.3 mm and PROJ to 1 mm
(≈2 m residual vs OSTN15, the usual Helmert limitation).

## Terrain fallback

If the terrain loads flat, the `.ter` binary format may differ from your
BeamNG version.  Import the 16-bit heightmap manually:

1. Open **World Editor** (F11)
2. Select the **TerrainBlock** in the scene tree
3. Tools → **Import Heightmap**
4. Select `levels/felsted/terrainGrid/felsted_height.png`
5. Set max height = **200 m**

## Spawn points

| Name | Location |
|---|---|
| `spawn_main_entrance` | Stebbing Road gate (south gate) |
| `spawn_car_park` | South car park |
| `spawn_campus_centre` | Main building forecourt |
| `spawn_sports_fields` | North-east sports pitches |

## Repository layout

```
tools/
  constants.py        GPS↔world projection, terrain parameters
  heightmap.py        LiDAR / SRTM / procedural + lat-lon resampling
  lidar.py            EA LiDAR DTM WCS fetch, GeoTIFF read, OSGB36 transform
  terrain_file.py     Binary .ter writer + PNG heightmap export
  osm_roads.py        OSM Overpass fetch + static fallback road network
  level_builder.py    Assembles main.level.json scene graph
  generate.py         CLI entry point
levels/
  felsted/
    info.json                   Map metadata (spawn points, description)
    main.level.json             BeamNG scene graph  ← generated
    preview.png                 Level browser thumbnail  ← generated
    terrainGrid/
      felsted.ter               Binary terrain  ← generated
      felsted_height.png        16-bit heightmap (editor import)  ← generated
    art/
      terrains/felsted_grass/   Terrain material definition
tests/
  test_constants.py   Coordinate projection unit tests
  test_heightmap.py   Elevation generation tests
  test_lidar.py       LiDAR DTM fetch, OSGB36 transforms, alignment tests
  test_terrain_file.py  .ter binary format tests
  test_osm_roads.py   Road network tests
  test_osm_parse.py   OSM data parsing tests
  test_level_builder.py  Level JSON assembly tests
  test_buildings.py   Building object tests
  test_buildings3d.py  3D building mesh tests
  test_water.py       Water body tests
  test_railway.py     Railway tests
  test_satellite.py   Satellite tile tests
```

## Running tests

```bash
pip install pytest
python3 -m pytest tests/ -v
```

All 253 tests pass.

## Geographic data sources

- **Environment Agency LiDAR Composite DTM 2 m** (Open Government Licence) — terrain
- **OpenStreetMap** contributors (ODbL) — road geometry, buildings, water
- **SRTM 30 m** (NASA / USGS) — fallback elevation via opentopodata.org
- **Felsted School campus map** — building layout reference
- **Strava** segment #2489774 (Stebbing Road) — elevation profile ground truth
- **Felsted Parish Plan** (Uttlesford DC, 2014) — landscape context

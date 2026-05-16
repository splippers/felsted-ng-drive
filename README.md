# felsted-ng-drive

A BeamNG:Drive map of **Felsted School** campus, Essex, England (CM6 3LL).

Felsted School is a 90-acre independent school founded in 1564, set in rolling
North Essex countryside at ~76 m ASL, west of the A120 between Braintree and
Dunmow.

## What's in the map

| Feature | Source |
|---|---|
| Terrain (48–92 m ASL) | Procedural model tuned to SRTM / Strava spot heights |
| Stebbing Road (main approach) | Research from OS, Strava segment, satellite |
| Campus entrance drive | School campus map PDF |
| Chapel forecourt spur | School campus map PDF |
| Campus loop road | School campus map PDF |
| Car park (south gate) | Satellite / campus map |
| Sports fields access road | Satellite |
| Braintree Road (B1008) approach | OSM |
| Service road (rear of buildings) | Satellite |
| 4 vehicle spawn points | Campus landmarks |
| River Chelmer valley (south) | Elevation data |

Run `python3 tools/generate.py --online` to replace the static road network with
live OSM geometry and SRTM elevation data.

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Generate map assets (offline, no network needed)
python3 tools/generate.py

# Package as BeamNG mod zip
python3 tools/generate.py --zip

# Fetch real OSM roads + SRTM elevation
python3 tools/generate.py --online --zip
```

Then copy `felsted.zip` to your BeamNG mods folder:

- **Windows**: `%USERPROFILE%\Documents\BeamNG.drive\mods\`
- **Linux**: `~/BeamNG.drive/mods/`

Restart BeamNG and pick **Felsted School** from the Free Roam map list.

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
  heightmap.py        Procedural + SRTM elevation generation
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
  test_terrain_file.py  .ter binary format tests
  test_osm_roads.py   Road network tests
  test_level_builder.py  Level JSON assembly tests
```

## Running tests

```bash
pip install pytest
python3 -m pytest tests/ -v
```

All 73 tests pass.

## Geographic data sources

- **OpenStreetMap** contributors (ODbL) — road geometry
- **SRTM 30m** (NASA / USGS) — elevation via opentopodata.org
- **Felsted School campus map** — building layout reference
- **Strava** segment #2489774 (Stebbing Road) — elevation profile ground truth
- **Felsted Parish Plan** (Uttlesford DC, 2014) — landscape context

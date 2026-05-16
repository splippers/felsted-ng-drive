"""
Historical railway infrastructure — v3.0.

The Witham–Dunmow branch line (Great Eastern Railway, opened 1869, closed 1953)
passed through Felsted.  Felsted Station stood ~0.7 km south-west of the school,
at approx. world coords (-420, -320).

The trackbed is encoded as a gravel-surface DecalRoad plus an embankment
terrain-cut marker.  Historical note: the line was single-track, approx. 3 m
ballast width.  Platform remains and station building (now a private house)
are listed in historic OSM data.

World coordinate reference (X east, Y north):
  Felsted Station: (-420, -320)   ← world coords from GPS 51.8521°N, 0.4268°E
  Exit east:      (+900, -340)    ← trackbed exits map NE toward Rayne
  Exit west:      (-950, -290)    ← trackbed exits map W toward Stebbing/Dunmow

OSM historic ways (if present in cache) are also included.
"""

from __future__ import annotations

import uuid
import logging
from typing import Callable

from tools.osm_parse import OsmData
from tools.constants import WORLD_HALF

log = logging.getLogger(__name__)

# ── Hardcoded trackbed nodes ──────────────────────────────────────────────────
# Nodes are [wx, wy, z, width] — width is DecalRoad half-width in metres.
# Z values follow natural terrain grade (valley floor ~50–60 m ASL here).
# The line descended from Felsted village southward into the Chelmer valley.

_FELSTED_BRANCH_NODES: list[list[float]] = [
    [-1024.0, -286.0, 59.0, 4.0],  # west map edge (toward Dunmow/Stebbing)
    [ -720.0, -295.0, 57.0, 4.0],
    [ -540.0, -308.0, 55.5, 4.0],
    [ -420.0, -318.0, 54.0, 4.0],  # Felsted Station site
    [ -310.0, -325.0, 53.5, 4.0],
    [ -160.0, -330.0, 53.0, 4.0],  # crosses Stebbing Brook
    [   40.0, -328.0, 52.5, 4.0],
    [  220.0, -322.0, 52.0, 4.0],
    [  440.0, -318.0, 52.0, 4.0],
    [  650.0, -315.0, 53.0, 4.0],
    [  870.0, -316.0, 54.0, 4.0],
    [ 1024.0, -318.0, 55.0, 4.0],  # east map edge (toward Rayne/Witham)
]

# Felsted Station platform marker (TSStatic placeholder)
_STATION_WX = -420.0
_STATION_WY = -318.0


def build_railway_objects(
    osm_data: OsmData,
    elevation_fn: Callable[[float, float], float],
) -> list[dict]:
    """
    Return a list of scene objects representing the historical railway:
      - DecalRoad for the trackbed (gravel/ballast surface)
      - WaterBlock stub for the culvert under Stebbing Brook (not needed but noted)
      - TSStatic marker at the station site
    """
    objects: list[dict] = []

    # ── Trackbed DecalRoad ─────────────────────────────────────────────────────
    nodes_with_terrain = []
    for n in _FELSTED_BRANCH_NODES:
        wx, wy, z_hardcoded, w = n
        # Blend hardcoded z with real terrain to avoid floating/buried track
        z_terrain = elevation_fn(wx, wy)
        z = z_hardcoded * 0.6 + z_terrain * 0.4
        nodes_with_terrain.append([wx, wy, z, w])

    objects.append({
        "class":           "DecalRoad",
        "name":            "railway_felsted_branch",
        "material":        "road_gravel_01",
        "overObjects":     False,
        "breakAngle":      3.0,
        "renderPriority":  10,
        "persistentId":    str(uuid.uuid4()),
        "nodes":           nodes_with_terrain,
        "_historical_note": "GER Witham–Dunmow branch, closed 1953",
    })

    # ── Station site marker ───────────────────────────────────────────────────
    z_station = elevation_fn(_STATION_WX, _STATION_WY)
    objects.append({
        "class":        "TSStatic",
        "name":         "felsted_station_site",
        "shapeName":    "levels/felsted/art/shapes/station_marker.dae",
        "position":     [_STATION_WX, _STATION_WY, z_station],
        "scale":        [1.0, 1.0, 1.0],
        "rotation":     [0.0, 0.0, 0.0, 1.0],
        "persistentId": str(uuid.uuid4()),
        "_note": "Felsted Station (GER, closed 1953). Platform ~50 m south of this point.",
    })

    # ── OSM historic railway ways (if present) ────────────────────────────────
    osm_railway_count = 0
    for way in _osm_historic_railways(osm_data, elevation_fn):
        objects.append(way)
        osm_railway_count += 1

    log.info(
        "Railway: 1 trackbed + 1 station marker + %d OSM historic ways",
        osm_railway_count,
    )
    return objects


def _osm_historic_railways(
    osm_data: OsmData,
    elevation_fn: Callable[[float, float], float],
) -> list[dict]:
    """Extract historic=railway ways from OSM data (if cached)."""
    from tools.constants import gps_to_world
    results = []
    try:
        raw = osm_data._raw  # type: ignore[attr-defined]
    except AttributeError:
        return results

    for way in raw.get("elements", []):
        if way.get("type") != "way":
            continue
        tags = way.get("tags", {})
        if tags.get("historic") not in ("railway", "station") and \
           tags.get("railway") not in ("disused", "abandoned", "historic"):
            continue
        nodes = way.get("nodes_resolved", [])
        if len(nodes) < 2:
            continue
        world_nodes = []
        for lat, lon in nodes:
            wx, wy = gps_to_world(lat, lon)
            if abs(wx) > WORLD_HALF + 50 or abs(wy) > WORLD_HALF + 50:
                continue
            z = elevation_fn(wx, wy)
            world_nodes.append([wx, wy, z, 4.0])
        if len(world_nodes) < 2:
            continue
        results.append({
            "class":        "DecalRoad",
            "name":         f"osm_railway_{way['id']}",
            "material":     "road_gravel_01",
            "persistentId": str(uuid.uuid4()),
            "nodes":        world_nodes,
        })
    return results


# ── Public accessors for tests ─────────────────────────────────────────────────

FELSTED_BRANCH_NODES = _FELSTED_BRANCH_NODES
STATION_POS = (_STATION_WX, _STATION_WY)

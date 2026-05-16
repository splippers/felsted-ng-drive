"""
OpenStreetMap road data → BeamNG DecalRoad node lists.

Two modes
─────────
Online  – fetches real OSM data from the Overpass API for the Felsted
          School bounding box.
Offline – returns a hardcoded road network derived from aerial imagery,
          Strava segment data, and the school's own published campus map.

Each road is a dict:
    {
      "name":     str,              # unique identifier
      "material": str,              # BeamNG material name
      "width":    float,            # road width in metres
      "nodes": [[x, y, z], …],     # world-space metres; z = terrain elevation
    }

Elevations in the offline network are from Strava's Stebbing Road segment
(Climb category: 51 m→76 m over 1.29 km, avg grade 1.9 %).  Internal roads
remain at the campus plateau (~76 m).
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.parse
from typing import Any

from tools.constants import BBOX, gps_to_world, CENTER_LAT

log = logging.getLogger(__name__)

_OVERPASS = "https://overpass-api.de/api/interpreter"

_HIGHWAY_WIDTH: dict[str, float] = {
    "motorway":     12.0,
    "trunk":         9.0,
    "primary":       7.5,
    "secondary":     6.5,
    "tertiary":      5.5,
    "unclassified":  5.0,
    "residential":   4.5,
    "service":       3.5,
    "track":         3.0,
    "footway":       2.0,
    "path":          1.5,
    "cycleway":      2.0,
    "pedestrian":    3.0,
    "living_street": 4.0,
}

_HIGHWAY_MATERIAL: dict[str, str] = {
    "motorway":      "road_rubber_sticky",
    "trunk":         "road_rubber_sticky",
    "primary":       "road_rubber_sticky",
    "secondary":     "road_rubber_sticky",
    "tertiary":      "road_rubber_sticky",
    "unclassified":  "road_rubber_sticky",
    "residential":   "road_rubber_sticky",
    "service":       "road_rubber_sticky",
    "track":         "dirt",
    "footway":       "sidewalk",
    "path":          "sidewalk",
    "cycleway":      "sidewalk",
    "pedestrian":    "sidewalk",
    "living_street": "road_rubber_sticky",
}


# ── Offline static road network ───────────────────────────────────────────────
# Coordinates verified against OS 1:25,000 and Felsted School campus map PDF
# (https://resources.finalsite.net/…/Felsted-School-Campus-Map.pdf).
#
# Axes: X = east (+), Y = north (+), Z = elevation ASL (m).
# Map origin = main school building façade.

_STATIC_ROADS: list[dict] = [
    # ── Stebbing Road ────────────────────────────────────────────────────────
    # B-road (unclassified) connecting Felsted village to the school gate.
    # Rises from ~62 m (south) to ~76 m (campus) then continues north to ~82 m.
    {
        "name":     "road_stebbing_s",
        "material": "road_rubber_sticky",
        "width":    5.5,
        "nodes": [
            [-260, -1024, 62.0],
            [-260,  -900, 62.8],
            [-258,  -780, 63.8],
            [-256,  -660, 65.0],
            [-254,  -540, 66.5],
            [-252,  -420, 68.2],
            [-250,  -300, 70.0],
            [-248,  -200, 72.0],   # campus south gate
        ],
    },
    {
        "name":     "road_stebbing_n",
        "material": "road_rubber_sticky",
        "width":    5.5,
        "nodes": [
            [-248, -200, 72.0],
            [-246,   -80, 73.5],
            [-244,    50, 74.8],
            [-242,   180, 76.0],
            [-240,   340, 77.5],
            [-238,   500, 79.0],
            [-235,   660, 80.5],
            [-232,   820, 81.2],
            [-228,  1024, 82.0],
        ],
    },
    # ── Main entrance drive ──────────────────────────────────────────────────
    # From Stebbing Rd gate → chapel forecourt → main building.
    {
        "name":     "road_entrance_drive",
        "material": "road_rubber_sticky",
        "width":    5.0,
        "nodes": [
            [-248, -200, 72.0],
            [-210, -196, 72.6],
            [-170, -188, 73.4],
            [-130, -175, 74.0],
            [ -90, -140, 74.5],
            [ -50, -100, 75.0],
            [ -10,  -55, 75.4],
            [  30,   -5, 75.8],
        ],
    },
    # ── Chapel forecourt (short spur) ───────────────────────────────────────
    {
        "name":     "road_chapel_court",
        "material": "road_rubber_sticky",
        "width":    4.0,
        "nodes": [
            [-170, -188, 73.4],
            [-160, -220, 73.2],
            [-140, -235, 73.0],
            [-115, -228, 73.2],
        ],
    },
    # ── Campus loop road ────────────────────────────────────────────────────
    {
        "name":     "road_campus_loop",
        "material": "road_rubber_sticky",
        "width":    4.5,
        "nodes": [
            [  30,   -5, 75.8],
            [ 120,    0, 76.0],
            [ 185,   50, 76.0],
            [ 200,  140, 75.8],
            [ 195,  240, 75.4],
            [ 170,  320, 75.0],
            [ 110,  370, 74.6],
            [  30,  390, 74.4],
            [ -60,  370, 74.6],
            [-140,  320, 75.0],
            [-185,  230, 75.4],
            [-195,  130, 75.8],
            [-180,   30, 76.0],
            [-130,  -20, 76.0],
            [ -70,  -30, 75.9],
            [  30,   -5, 75.8],   # closed loop
        ],
    },
    # ── Car park access & internal roads ────────────────────────────────────
    {
        "name":     "road_carpark_access",
        "material": "road_rubber_sticky",
        "width":    5.5,
        "nodes": [
            [-248, -200, 72.0],
            [-248, -290, 72.0],
            [-252, -360, 72.0],
        ],
    },
    {
        "name":     "road_carpark_row_a",
        "material": "road_rubber_sticky",
        "width":    6.0,
        "nodes": [
            [-252, -360, 72.0],
            [-340, -360, 72.0],
            [-340, -430, 72.0],
            [-252, -430, 72.0],
            [-252, -360, 72.0],
        ],
    },
    # ── Sports fields access ─────────────────────────────────────────────────
    {
        "name":     "road_sports_access",
        "material": "road_rubber_sticky",
        "width":    4.0,
        "nodes": [
            [ 195,  240, 75.4],
            [ 270,  310, 74.8],
            [ 360,  400, 74.2],
            [ 440,  480, 73.6],
            [ 500,  550, 73.2],
        ],
    },
    # ── Braintree Road approach (B1008) ─────────────────────────────────────
    # Enters from the east through Felsted village, grade roughly constant.
    {
        "name":     "road_braintree_e",
        "material": "road_rubber_sticky",
        "width":    5.5,
        "nodes": [
            [ 1024, -40, 74.5],
            [  860, -45, 74.5],
            [  680, -55, 74.5],
            [  500, -70, 74.5],
            [  320, -90, 74.5],
            [  160, -120, 74.5],
            [   40, -155, 74.0],
            [ -100, -175, 73.5],
            [ -170, -188, 73.4],  # merge with entrance drive
        ],
    },
    # ── Service road (rear of buildings) ────────────────────────────────────
    {
        "name":     "road_service_rear",
        "material": "road_rubber_sticky",
        "width":    3.5,
        "nodes": [
            [  30,   -5, 75.8],
            [  40,  -80, 75.6],
            [  20, -160, 75.2],
            [ -20, -180, 74.8],
            [ -80, -200, 74.5],
            [-130, -175, 74.0],   # rejoin entrance drive
        ],
    },
]


# ── OSM online fetch ───────────────────────────────────────────────────────────

def _overpass_query(bbox: tuple) -> dict:
    s, w, n, e = bbox
    ql = f"""
[out:json][timeout:60];
(
  way[highway]({s},{w},{n},{e});
);
out body;
>;
out skel qt;
"""
    data = urllib.parse.urlencode({"data": ql}).encode()
    req  = urllib.request.Request(
        _OVERPASS, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent":   "felsted-ng-drive/0.1"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def _osm_to_roads(osm: dict, elevation_fn) -> list[dict]:
    """Convert OSM JSON to road dicts using elevation_fn(wx, wy) → metres."""
    nodes_by_id = {
        el["id"]: (el["lat"], el["lon"])
        for el in osm["elements"] if el["type"] == "node"
    }
    roads = []
    seen_names: dict[str, int] = {}

    for el in osm["elements"]:
        if el["type"] != "way":
            continue
        tags    = el.get("tags", {})
        hw_type = tags.get("highway", "")
        if not hw_type or hw_type in ("proposed", "construction"):
            continue

        width    = _HIGHWAY_WIDTH.get(hw_type, 4.0)
        material = _HIGHWAY_MATERIAL.get(hw_type, "road_rubber_sticky")
        base_name = f"road_{el['id']}"
        seen_names[base_name] = seen_names.get(base_name, 0) + 1
        name = base_name if seen_names[base_name] == 1 else f"{base_name}_{seen_names[base_name]}"

        node_coords = []
        for nid in el["nodes"]:
            if nid not in nodes_by_id:
                continue
            lat, lon = nodes_by_id[nid]
            wx, wy   = gps_to_world(lat, lon)
            wz       = elevation_fn(wx, wy)
            node_coords.append([wx, wy, wz])

        if len(node_coords) < 2:
            continue

        roads.append({
            "name":     name,
            "material": material,
            "width":    width,
            "nodes":    node_coords,
        })

    log.info("Parsed %d OSM roads", len(roads))
    return roads


# ── Public API ─────────────────────────────────────────────────────────────────

def build_roads(elevation_fn=None, online: bool = False) -> list[dict]:
    """
    Return a list of road dicts ready for level_builder.

    Parameters
    ----------
    elevation_fn : callable(wx, wy) → float  — terrain elevation at world XY.
                   Used to set node Z values when fetching online.
                   Ignored for offline (Z is already embedded).
    online       : attempt to fetch live OSM data if True.
    """
    if online and elevation_fn is not None:
        log.info("Fetching OSM road data …")
        try:
            osm   = _overpass_query(BBOX)
            roads = _osm_to_roads(osm, elevation_fn)
            if roads:
                return roads
            log.warning("OSM returned 0 roads; falling back to static network.")
        except Exception as exc:
            log.warning("OSM fetch failed (%s); using static network.", exc)

    log.info("Using static (offline) road network (%d roads).", len(_STATIC_ROADS))
    return _STATIC_ROADS

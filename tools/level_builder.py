"""
Assemble the BeamNG main.level.json scene graph from terrain and road data.

BeamNG uses a Torque3D-derived JSON level format.  The top-level object is a
SimGroup called MissionGroup; all scene objects are nested inside it.  All
numeric properties are represented as JSON numbers (not quoted strings).

Key scene objects generated:
  • LevelInfo          – sky, fog, ambient settings
  • TerrainBlock       – references the .ter file
  • Sun                – directional light + shadows
  • SimGroup "Spawn"   – SpawnSphere nodes (vehicle start positions)
  • SimGroup "Roads"   – DecalRoad objects derived from OSM / static network
  • SimGroup "Props"   – placeholder for future TSStatic buildings / trees
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from tools.constants import (
    MAP_NAME, MAP_TITLE,
    BLOCK_SIZE, SQUARE_SIZE, CAMPUS_ELEV,
)

log = logging.getLogger(__name__)

# ── Deterministic UUID helper ──────────────────────────────────────────────────
_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _uid(name: str) -> str:
    return str(uuid.uuid5(_NS, f"felsted.{name}"))


# ── Scene-object constructors ──────────────────────────────────────────────────

def _obj(cls: str, name: str, **props) -> dict[str, Any]:
    return {"class": cls, "name": name, "persistentId": _uid(name), **props}


def _group(name: str, *children) -> dict[str, Any]:
    o = _obj("SimGroup", name)
    o["children"] = list(children)
    return o


def _level_info() -> dict:
    return _obj(
        "LevelInfo", "LevelInfo",
        visibleDistance=1500,
        fogColor=[0.6, 0.65, 0.7, 1.0],
        fogDensity=0.0,
        fogDensityOffset=700.0,
        canvasClearColor=[0, 0, 0, 255],
        ambientLightColor=[0.15, 0.15, 0.20, 1.0],
    )


def _terrain_block() -> dict:
    return _obj(
        "TerrainBlock", "Terrain",
        position=[0, 0, 0],
        rotation=[1, 0, 0, 0],
        scale=[1, 1, 1],
        squareSize=SQUARE_SIZE,
        terrainFile=f"levels/{MAP_NAME}/terrainGrid/{MAP_NAME}.ter",
        baseTexSize=256,
        overrideGroundModel=False,
        physicsProxyType="Trimesh",
        castDynamicShadows=False,
        maxDetailDistance=200,
        screenError=16,
    )


def _sun() -> dict:
    return _obj(
        "Sun", "TheSun",
        azimuth=214,        # SSW sun angle, typical UK summer afternoon
        elevation=45,
        color=[0.95, 0.92, 0.88, 1.0],
        ambient=[0.16, 0.17, 0.20, 1.0],
        shadowDistance=500,
        shadowSoftness=0.15,
        numSplits=4,
        logWeight=0.91,
        attenuationRatio=[0.0, 1.0, 1.0],
    )


def _scatter_sky() -> dict:
    return _obj(
        "ScatterSky", "ScatterSky",
        skyBrightness=25,
        sunSize=1.0,
        colorizeAmount=0.2,
        colorize=[0.6, 0.8, 1.0],
        rayleighScattering=0.0035,
        mieScattering=0.0045,
        exposure=1.0,
        nightColor=[0.02, 0.02, 0.08, 1.0],
        windSpeed=1.0,
    )


def _spawn_sphere(name: str, x: float, y: float, z: float,
                  yaw_deg: float = 0.0, radius: float = 3.0) -> dict:
    """
    yaw_deg: clockwise from north (0° = north, 90° = east).
    Converts to BeamNG's axis-angle quaternion [qx, qy, qz, qw].
    """
    import math
    half = math.radians(yaw_deg) / 2
    qz   = math.sin(half)
    qw   = math.cos(half)
    return _obj(
        "SpawnSphere", name,
        position=[round(x, 2), round(y, 2), round(z + 0.5, 2)],
        rotation=[0.0, 0.0, round(qz, 4), round(qw, 4)],
        radius=radius,
        sphereWeight=100,
        indoorWeight=0,
        outdoorWeight=100,
    )


def _decal_road(road: dict) -> dict:
    """Convert a road dict (from osm_roads) into a DecalRoad scene object."""
    nodes = [
        [round(n[0], 2), round(n[1], 2), round(n[2], 2), road["width"]]
        for n in road["nodes"]
    ]
    return _obj(
        "DecalRoad", road["name"],
        material=road["material"],
        renderPriority=10,
        textureLength=5,
        drivability=1,
        improvedSpline=True,
        breakAngle=3,
        depthBias=-0.001,
        nodes=nodes,
    )


# ── Spawn points (fixed landmarks) ────────────────────────────────────────────
# Positions derived from campus map and research data.
_SPAWN_POINTS = [
    # name, world X, world Y, elev, yaw (° CW from north)
    ("spawn_main_entrance",  -248, -200, 72.5,  90),   # by Stebbing Rd gate, facing east
    ("spawn_car_park",       -296, -395, 72.5, 180),   # car park, facing south
    ("spawn_campus_centre",     0,    0, 76.5,   0),   # main building forecourt, north
    ("spawn_sports_fields",   450,  490, 73.5, 270),   # sports pitches, facing west
]


# ── Public API ─────────────────────────────────────────────────────────────────

def build_level(roads: list[dict], out_path: Path | str) -> None:
    """
    Write the main.level.json scene graph.

    Parameters
    ----------
    roads    : list of road dicts from osm_roads.build_roads()
    out_path : destination file path
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    spawn_group = _group(
        "Spawn",
        *[_spawn_sphere(name, x, y, z, yaw)
          for name, x, y, z, yaw in _SPAWN_POINTS],
    )

    roads_group = _group(
        "Roads",
        *[_decal_road(r) for r in roads],
    )

    props_group = _group("Props")   # placeholder for TSStatic buildings

    mission_group = _group(
        "MissionGroup",
        _level_info(),
        _scatter_sky(),
        _sun(),
        _terrain_block(),
        spawn_group,
        roads_group,
        props_group,
    )

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(mission_group, f, indent=2)

    log.info("Wrote %s (%d roads, %d spawn points)",
             out_path, len(roads), len(_SPAWN_POINTS))

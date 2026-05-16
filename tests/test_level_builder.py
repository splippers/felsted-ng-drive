"""Tests for the BeamNG level JSON assembly — v3.0."""

import json
import pytest
from pathlib import Path

from tools.level_builder import build_level, _SPAWN_POINTS
from tools.osm_roads import _STATIC_ROADS
from tools.osm_parse import OsmData
from tools.buildings import build_building_objects
from tools.water import build_water_objects
from tools.vegetation import build_vegetation_objects
from tools.constants import SQUARE_SIZE


_ELEV = lambda wx, wy: 76.0


@pytest.fixture(scope="module")
def level(tmp_path_factory):
    p = tmp_path_factory.mktemp("lvl") / "main.level.json"
    buildings  = build_building_objects(OsmData(), _ELEV)
    water      = build_water_objects(OsmData(), _ELEV)
    vegetation = build_vegetation_objects(OsmData(), _ELEV)
    build_level(_STATIC_ROADS, buildings, water, vegetation, out_path=p)
    return json.loads(p.read_text())


def _all_objects(obj, acc=None):
    if acc is None: acc = []
    acc.append(obj)
    for child in obj.get("children", []):
        _all_objects(child, acc)
    return acc


def _by_class(level, cls):
    return [o for o in _all_objects(level) if o.get("class") == cls]


class TestTopLevel:
    def test_is_sim_group(self, level):
        assert level["class"] == "SimGroup"

    def test_name(self, level):
        assert level["name"] == "MissionGroup"

    def test_has_children(self, level):
        assert len(level.get("children", [])) > 0

    def test_persistent_id_uuid(self, level):
        pid = level["persistentId"]
        assert len(pid) == 36
        assert pid.count("-") == 4

    def test_unique_persistent_ids(self, level):
        ids = [o["persistentId"] for o in _all_objects(level)
               if "persistentId" in o]
        assert len(ids) == len(set(ids))


class TestRequiredObjects:
    def test_terrain_block(self, level):
        assert len(_by_class(level, "TerrainBlock")) == 1

    def test_sun(self, level):
        assert len(_by_class(level, "Sun")) == 1

    def test_scatter_sky(self, level):
        assert len(_by_class(level, "ScatterSky")) == 1

    def test_level_info(self, level):
        assert len(_by_class(level, "LevelInfo")) == 1

    def test_spawn_spheres(self, level):
        assert len(_by_class(level, "SpawnSphere")) > 0

    def test_decal_roads(self, level):
        assert len(_by_class(level, "DecalRoad")) > 0

    def test_water_blocks(self, level):
        assert len(_by_class(level, "WaterBlock")) > 0

    def test_ts_static_buildings(self, level):
        assert len(_by_class(level, "TSStatic")) > 0


class TestTerrainBlock:
    def test_terrain_file(self, level):
        t = _by_class(level, "TerrainBlock")[0]
        assert "terrainFile" in t
        assert t["terrainFile"].endswith("felsted.ter")

    def test_square_size_2m(self, level):
        t = _by_class(level, "TerrainBlock")[0]
        assert t["squareSize"] == SQUARE_SIZE == 2.0

    def test_high_base_tex_size(self, level):
        t = _by_class(level, "TerrainBlock")[0]
        assert t["baseTexSize"] >= 256

    def test_fine_screen_error(self, level):
        t = _by_class(level, "TerrainBlock")[0]
        assert t["screenError"] <= 16


class TestSpawnSpheres:
    def test_eight_spawns(self, level):
        assert len(_by_class(level, "SpawnSphere")) == len(_SPAWN_POINTS) == 8

    def test_spawn_names(self, level):
        spawns = {o["name"] for o in _by_class(level, "SpawnSphere")}
        assert "spawn_main_entrance"  in spawns
        assert "spawn_campus_centre" in spawns
        assert "spawn_sports_fields" in spawns
        assert "spawn_chapel_approach" in spawns

    def test_spawn_positions_lists(self, level):
        for s in _by_class(level, "SpawnSphere"):
            assert isinstance(s["position"], list)
            assert len(s["position"]) == 3

    def test_spawn_elevations_plausible(self, level):
        for s in _by_class(level, "SpawnSphere"):
            z = s["position"][2]
            assert 40.0 < z < 110.0


class TestSun:
    def test_uk_latitude_sun(self, level):
        sun = _by_class(level, "Sun")[0]
        # UK summer afternoon: azimuth ~200-230°, elevation ~35-55°
        assert 180 <= sun["azimuth"] <= 250
        assert 30  <= sun["elevation"] <= 60


class TestDecalRoads:
    def test_road_count(self, level):
        roads = [o for o in _by_class(level, "DecalRoad")
                 if not o["name"].startswith(("footprint_", "pitch_", "stream_",
                                               "river_", "pond_"))]
        assert len(roads) >= len(_STATIC_ROADS)

    def test_road_nodes_four_elements(self, level):
        for r in _by_class(level, "DecalRoad")[:20]:
            for n in r["nodes"]:
                assert len(n) == 4, f"{r['name']} node {n} not [x,y,z,w]"

    def test_road_material_strings(self, level):
        for r in _by_class(level, "DecalRoad"):
            assert isinstance(r["material"], str)

    def test_json_serialisable(self, level):
        assert json.dumps(level) is not None

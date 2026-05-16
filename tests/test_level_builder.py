"""Tests for the BeamNG level JSON assembly."""

import json
import tempfile
from pathlib import Path

import pytest
from tools.level_builder import build_level, _SPAWN_POINTS
from tools.osm_roads import _STATIC_ROADS


@pytest.fixture(scope="module")
def level_json(tmp_path_factory):
    p = tmp_path_factory.mktemp("level") / "main.level.json"
    build_level(_STATIC_ROADS, p)
    with p.open() as f:
        return json.load(f)


def _all_objects(obj, acc=None):
    """Flatten the full object tree into a list."""
    if acc is None:
        acc = []
    acc.append(obj)
    for child in obj.get("children", []):
        _all_objects(child, acc)
    return acc


class TestLevelStructure:
    def test_top_level_is_sim_group(self, level_json):
        assert level_json["class"] == "SimGroup"

    def test_mission_group_name(self, level_json):
        assert level_json["name"] == "MissionGroup"

    def test_has_children(self, level_json):
        assert "children" in level_json
        assert len(level_json["children"]) > 0

    def test_persistent_id_present(self, level_json):
        assert "persistentId" in level_json
        assert len(level_json["persistentId"]) == 36  # UUID format

    def test_unique_persistent_ids(self, level_json):
        all_objs = _all_objects(level_json)
        ids = [o["persistentId"] for o in all_objs if "persistentId" in o]
        assert len(ids) == len(set(ids)), "Duplicate persistentIds found"


class TestRequiredObjects:
    def _classes(self, level_json):
        return {o["class"] for o in _all_objects(level_json)}

    def test_has_terrain_block(self, level_json):
        assert "TerrainBlock" in self._classes(level_json)

    def test_has_sun(self, level_json):
        assert "Sun" in self._classes(level_json)

    def test_has_scatter_sky(self, level_json):
        assert "ScatterSky" in self._classes(level_json)

    def test_has_level_info(self, level_json):
        assert "LevelInfo" in self._classes(level_json)

    def test_has_spawn_spheres(self, level_json):
        assert "SpawnSphere" in self._classes(level_json)

    def test_has_decal_roads(self, level_json):
        assert "DecalRoad" in self._classes(level_json)


class TestTerrainBlock:
    def _terrain(self, level_json):
        return next(o for o in _all_objects(level_json)
                    if o["class"] == "TerrainBlock")

    def test_terrain_file_path(self, level_json):
        t = self._terrain(level_json)
        assert "terrainFile" in t
        assert t["terrainFile"].endswith("felsted.ter")

    def test_square_size(self, level_json):
        t = self._terrain(level_json)
        from tools.constants import SQUARE_SIZE
        assert t["squareSize"] == SQUARE_SIZE

    def test_position_at_origin(self, level_json):
        t = self._terrain(level_json)
        assert t["position"] == [0, 0, 0]


class TestSpawnSpheres:
    def _spawns(self, level_json):
        return [o for o in _all_objects(level_json)
                if o["class"] == "SpawnSphere"]

    def test_correct_count(self, level_json):
        assert len(self._spawns(level_json)) == len(_SPAWN_POINTS)

    def test_spawn_names_match(self, level_json):
        names = {o["name"] for o in self._spawns(level_json)}
        for expected_name, *_ in _SPAWN_POINTS:
            assert expected_name in names

    def test_spawn_positions_are_lists(self, level_json):
        for spawn in self._spawns(level_json):
            pos = spawn["position"]
            assert isinstance(pos, list)
            assert len(pos) == 3

    def test_spawn_elevations_plausible(self, level_json):
        for spawn in self._spawns(level_json):
            z = spawn["position"][2]
            assert 40.0 < z < 110.0, f"Spawn {spawn['name']} Z={z} implausible"


class TestDecalRoads:
    def _roads(self, level_json):
        return [o for o in _all_objects(level_json)
                if o["class"] == "DecalRoad"]

    def test_road_count_matches_input(self, level_json):
        assert len(self._roads(level_json)) == len(_STATIC_ROADS)

    def test_road_nodes_are_lists(self, level_json):
        for road in self._roads(level_json):
            assert isinstance(road["nodes"], list)
            assert all(isinstance(n, list) for n in road["nodes"])

    def test_road_nodes_four_elements(self, level_json):
        """Each node is [x, y, z, width]."""
        for road in self._roads(level_json):
            for node in road["nodes"]:
                assert len(node) == 4, \
                    f"{road['name']} node {node} should have 4 elements"

    def test_road_has_material(self, level_json):
        for road in self._roads(level_json):
            assert "material" in road
            assert isinstance(road["material"], str)

    def test_json_serialisable(self, level_json):
        # Already loaded as dict; re-serialise to catch any non-JSON types
        assert json.dumps(level_json) is not None

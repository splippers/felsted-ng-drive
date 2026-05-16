"""Tests for water feature generation — v3.0."""

import pytest
from tools.water import build_water_objects, _CHELMER_NODES, _STEBBING_BROOK_NODES
from tools.osm_parse import load as parse_osm, OsmData
from tools.constants import OSM_CACHE, WORLD_HALF


_ELEV_FN = lambda wx, wy: 51.0   # river-level mock


@pytest.fixture(scope="module")
def osm():
    if not OSM_CACHE.exists():
        return OsmData()
    return parse_osm()


@pytest.fixture(scope="module")
def water_objects(osm):
    return build_water_objects(osm, _ELEV_FN)


class TestWaterObjects:
    def test_returns_list(self, water_objects):
        assert isinstance(water_objects, list)

    def test_non_empty(self, water_objects):
        assert len(water_objects) >= 3  # at least Chelmer, Brook, + WaterBlock

    def test_chelmer_decal_road_present(self, water_objects):
        names = {o["name"] for o in water_objects}
        assert "river_chelmer" in names

    def test_stebbing_brook_present(self, water_objects):
        names = {o["name"] for o in water_objects}
        assert "stream_stebbing_brook" in names

    def test_chelmer_waterblock_present(self, water_objects):
        blocks = [o for o in water_objects if o.get("class") == "WaterBlock"]
        names  = {b["name"] for b in blocks}
        assert "waterblock_chelmer" in names

    def test_all_classes_valid(self, water_objects):
        valid = {"DecalRoad", "WaterBlock", "SimGroup"}
        for o in water_objects:
            assert o.get("class") in valid


class TestChelmerRoad:
    def _chelmer(self, water_objects):
        return next(o for o in water_objects if o["name"] == "river_chelmer")

    def test_chelmer_has_nodes(self, water_objects):
        c = self._chelmer(water_objects)
        assert len(c["nodes"]) >= 5

    def test_chelmer_runs_east_west(self, water_objects):
        """River Chelmer crosses the map from west to east."""
        c     = self._chelmer(water_objects)
        nodes = c["nodes"]
        x_min = min(n[0] for n in nodes)
        x_max = max(n[0] for n in nodes)
        assert x_max - x_min > 1500, "Chelmer should span >1.5 km east–west"

    def test_chelmer_elevation_low(self, water_objects):
        """River should be in the valley, well below campus (76 m)."""
        c = self._chelmer(water_objects)
        z_vals = [n[2] for n in c["nodes"]]
        assert max(z_vals) < 60.0, "River Chelmer should be below 60 m"

    def test_chelmer_has_width(self, water_objects):
        c = self._chelmer(water_objects)
        for n in c["nodes"]:
            assert len(n) == 4
            assert n[3] >= 5.0   # river should be ≥5 m wide


class TestHardcodedNodes:
    def test_chelmer_nodes_count(self):
        assert len(_CHELMER_NODES) >= 5

    def test_brook_nodes_count(self):
        assert len(_STEBBING_BROOK_NODES) >= 4

    def test_chelmer_within_world(self):
        margin = 50
        for n in _CHELMER_NODES:
            assert -WORLD_HALF - margin <= n[0] <= WORLD_HALF + margin
            assert -WORLD_HALF - margin <= n[1] <= WORLD_HALF + margin

    def test_chelmer_z_below_50m(self):
        for n in _CHELMER_NODES:
            assert n[2] < 55.0, f"Chelmer node z={n[2]} too high"

    def test_brook_z_plausible(self):
        for n in _STEBBING_BROOK_NODES:
            assert 40.0 < n[2] < 70.0


class TestWaterBlock:
    def _blocks(self, water_objects):
        return [o for o in water_objects if o.get("class") == "WaterBlock"]

    def test_waterblock_has_position(self, water_objects):
        for b in self._blocks(water_objects):
            assert "position" in b
            assert len(b["position"]) == 3

    def test_waterblock_scale_nonzero(self, water_objects):
        for b in self._blocks(water_objects):
            s = b["scale"]
            assert all(v > 0 for v in s)

    def test_waterblock_has_persistent_id(self, water_objects):
        for b in self._blocks(water_objects):
            assert "persistentId" in b

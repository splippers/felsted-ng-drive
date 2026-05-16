"""Tests for road network builder — v3.0 (OSM + static fallback)."""

import pytest
from tools.osm_roads import build_roads, _STATIC_ROADS
from tools.constants import WORLD_HALF, OSM_CACHE


@pytest.fixture(scope="module")
def roads_osm():
    """Roads from cached OSM data (skips if cache absent)."""
    if not OSM_CACHE.exists():
        pytest.skip("OSM cache absent")
    elev_fn = lambda wx, wy: 76.0
    return build_roads(elevation_fn=elev_fn, online=False)


@pytest.fixture(scope="module")
def roads_static():
    return _STATIC_ROADS


# ── Static fallback ────────────────────────────────────────────────────────────

class TestStaticRoads:
    def test_non_empty(self, roads_static):
        assert len(roads_static) >= 6

    def test_required_roads(self, roads_static):
        names = {r["name"] for r in roads_static}
        assert "road_stebbing_s"    in names
        assert "road_entrance_drive" in names
        assert "road_campus_loop"   in names

    def test_road_schema(self, roads_static):
        for r in roads_static:
            assert "name" in r
            assert "material" in r
            assert "width" in r
            assert "nodes" in r

    def test_stebbing_rises_northward(self, roads_static):
        sr = next(r for r in roads_static if r["name"] == "road_stebbing_s")
        z  = [n[2] for n in sr["nodes"]]
        assert z[0] < z[-1]

    def test_nodes_within_world(self, roads_static):
        margin = 60
        for r in roads_static:
            for n in r["nodes"]:
                assert -WORLD_HALF - margin <= n[0] <= WORLD_HALF + margin
                assert -WORLD_HALF - margin <= n[1] <= WORLD_HALF + margin

    def test_elevations_plausible(self, roads_static):
        for r in roads_static:
            for n in r["nodes"]:
                assert 40.0 < n[2] < 110.0

    def test_widths_positive(self, roads_static):
        for r in roads_static:
            assert r["width"] > 0

    def test_minimum_two_nodes(self, roads_static):
        for r in roads_static:
            assert len(r["nodes"]) >= 2


# ── OSM road network ───────────────────────────────────────────────────────────

class TestOsmRoads:
    def test_more_roads_than_static(self, roads_osm):
        assert len(roads_osm) > len(_STATIC_ROADS)

    def test_schema(self, roads_osm):
        for r in roads_osm[:20]:
            assert "name" in r
            assert "material" in r
            assert "width" in r
            assert len(r["nodes"]) >= 2

    def test_node_xyz_three_elements(self, roads_osm):
        for r in roads_osm[:20]:
            for n in r["nodes"]:
                assert len(n) == 3

    def test_nodes_within_world(self, roads_osm):
        margin = 150
        for r in roads_osm[:50]:
            for n in r["nodes"]:
                assert -WORLD_HALF - margin <= n[0] <= WORLD_HALF + margin
                assert -WORLD_HALF - margin <= n[1] <= WORLD_HALF + margin

    def test_elevations_use_terrain(self, roads_osm):
        """All Z values should be ~76 m (our flat mock elevation_fn)."""
        for r in roads_osm[:20]:
            for n in r["nodes"]:
                assert abs(n[2] - 76.0) < 0.01

    def test_road_names_unique(self, roads_osm):
        names = [r["name"] for r in roads_osm]
        assert len(names) == len(set(names)), "Duplicate road names"

    def test_materials_are_strings(self, roads_osm):
        for r in roads_osm:
            assert isinstance(r["material"], str)
            assert len(r["material"]) > 0

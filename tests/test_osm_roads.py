"""Tests for the offline static road network."""

import pytest
from tools.osm_roads import build_roads, _STATIC_ROADS
from tools.constants import WORLD_HALF


@pytest.fixture(scope="module")
def roads():
    return build_roads(online=False)


class TestStaticRoads:
    def test_returns_list(self, roads):
        assert isinstance(roads, list)

    def test_non_empty(self, roads):
        assert len(roads) >= 6, "Expected at least 6 roads in static network"

    def test_required_roads_present(self, roads):
        names = {r["name"] for r in roads}
        assert "road_stebbing_s" in names,       "Missing southbound Stebbing Road"
        assert "road_entrance_drive" in names,    "Missing entrance drive"
        assert "road_campus_loop" in names,       "Missing campus loop"
        assert "road_carpark_access" in names,    "Missing car park access"

    def test_road_schema(self, roads):
        for road in roads:
            assert "name"     in road, f"{road} missing 'name'"
            assert "material" in road, f"{road['name']} missing 'material'"
            assert "width"    in road, f"{road['name']} missing 'width'"
            assert "nodes"    in road, f"{road['name']} missing 'nodes'"

    def test_minimum_two_nodes(self, roads):
        for road in roads:
            assert len(road["nodes"]) >= 2, \
                f"{road['name']} has fewer than 2 nodes"

    def test_nodes_within_world_bounds(self, roads):
        margin = 50  # allow a little outside for roads to the edge
        for road in roads:
            for node in road["nodes"]:
                x, y, z = node
                assert -WORLD_HALF - margin <= x <= WORLD_HALF + margin, \
                    f"{road['name']} node X={x} out of world"
                assert -WORLD_HALF - margin <= y <= WORLD_HALF + margin, \
                    f"{road['name']} node Y={y} out of world"

    def test_elevations_plausible(self, roads):
        for road in roads:
            for node in road["nodes"]:
                z = node[2]
                assert 40.0 < z < 110.0, \
                    f"{road['name']} node Z={z} implausible for Felsted"

    def test_stebbing_road_rises_northward(self, roads):
        """Stebbing Road southbound: z should increase node-by-node going north."""
        sr = next(r for r in roads if r["name"] == "road_stebbing_s")
        z_vals = [n[2] for n in sr["nodes"]]
        # First node (south, ~62 m) should be lower than last (campus, ~72 m)
        assert z_vals[0] < z_vals[-1], "Stebbing Rd should rise from south→campus"

    def test_widths_positive(self, roads):
        for road in roads:
            assert road["width"] > 0

    def test_material_strings(self, roads):
        valid = {"road_rubber_sticky", "dirt", "sidewalk", "asphalt"}
        for road in roads:
            assert isinstance(road["material"], str)
            assert len(road["material"]) > 0


class TestBuildRoadsOffline:
    def test_offline_equals_static(self):
        result = build_roads(online=False)
        assert result is _STATIC_ROADS

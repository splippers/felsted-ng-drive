"""Tests for building object generation — v3.0."""

import pytest
from tools.buildings import build_building_objects, _NAMED_FALLBACKS
from tools.osm_parse import load as parse_osm, OsmData
from tools.constants import OSM_CACHE, WORLD_HALF


_ELEV_FN = lambda wx, wy: 76.0


@pytest.fixture(scope="module")
def osm():
    if not OSM_CACHE.exists():
        pytest.skip("OSM cache absent")
    return parse_osm()


@pytest.fixture(scope="module")
def bld_objects(osm):
    return build_building_objects(osm, _ELEV_FN)


class TestBuildingMarkers:
    def test_returns_tuple(self, bld_objects):
        assert isinstance(bld_objects, tuple)
        assert len(bld_objects) == 2

    def test_markers_non_empty(self, bld_objects):
        markers, _ = bld_objects
        assert len(markers) > 0

    def test_all_markers_ts_static(self, bld_objects):
        markers, _ = bld_objects
        for m in markers:
            assert m["class"] == "TSStatic"

    def test_markers_have_position(self, bld_objects):
        markers, _ = bld_objects
        for m in markers:
            assert "position" in m
            assert len(m["position"]) == 3

    def test_markers_within_world(self, bld_objects):
        markers, _ = bld_objects
        margin = 100
        for m in markers:
            x, y, z = m["position"]
            assert -WORLD_HALF - margin <= x <= WORLD_HALF + margin
            assert -WORLD_HALF - margin <= y <= WORLD_HALF + margin

    def test_chapel_marker_present(self, bld_objects):
        markers, _ = bld_objects
        names = {m["name"] for m in markers}
        assert any("chapel" in n.lower() or "Chapel" in n for n in names)

    def test_unique_marker_names(self, bld_objects):
        markers, _ = bld_objects
        names = [m["name"] for m in markers]
        assert len(names) == len(set(names))

    def test_markers_have_persistent_id(self, bld_objects):
        markers, _ = bld_objects
        for m in markers:
            assert "persistentId" in m
            assert len(m["persistentId"]) == 36

    def test_marker_elevations_plausible(self, bld_objects):
        markers, _ = bld_objects
        for m in markers:
            z = m["position"][2]
            # Our flat mock returns 76 m for everything
            assert abs(z - 76.0) < 0.01


class TestBuildingFootprints:
    def test_footprints_non_empty(self, bld_objects):
        _, footprints = bld_objects
        assert len(footprints) > 0

    def test_all_footprints_decal_road(self, bld_objects):
        _, footprints = bld_objects
        for fp in footprints:
            assert fp["class"] == "DecalRoad"

    def test_footprints_closed_loop(self, bld_objects):
        """Each footprint should start and end at the same XY position."""
        _, footprints = bld_objects
        for fp in footprints:
            nodes = fp["nodes"]
            assert len(nodes) >= 4, f"{fp['name']} has < 4 nodes"
            assert nodes[0][:2] == nodes[-1][:2], \
                f"{fp['name']} footprint is not closed"

    def test_footprint_nodes_four_elements(self, bld_objects):
        _, footprints = bld_objects
        for fp in footprints:
            for n in fp["nodes"]:
                assert len(n) == 4

    def test_footprints_have_persistent_id(self, bld_objects):
        _, footprints = bld_objects
        for fp in footprints:
            assert "persistentId" in fp


class TestNamedFallbacks:
    def test_fallbacks_cover_key_buildings(self):
        assert "Felsted School Chapel"    in _NAMED_FALLBACKS
        assert "Felsted School Sports Centre" in _NAMED_FALLBACKS
        assert "Music School"             in _NAMED_FALLBACKS

    def test_fallbacks_within_campus(self):
        for name, (wx, wy) in _NAMED_FALLBACKS.items():
            assert -500 < wx < 500, f"{name} x={wx} seems off-campus"
            assert -500 < wy < 500, f"{name} y={wy} seems off-campus"

    def test_empty_osm_uses_fallbacks(self):
        """Empty OSM data should still produce markers from _NAMED_FALLBACKS."""
        markers, _ = build_building_objects(OsmData(), _ELEV_FN)
        assert len(markers) == len(_NAMED_FALLBACKS)
        names = {m["name"] for m in markers}
        for key in _NAMED_FALLBACKS:
            assert any(key.replace(" ", "_")[:32] in n for n in names)

"""Tests for historical railway infrastructure — v3.0."""

import pytest
from tools.railway import (
    build_railway_objects,
    FELSTED_BRANCH_NODES,
    STATION_POS,
)
from tools.osm_parse import OsmData
from tools.constants import WORLD_HALF


_ELEV_FN = lambda wx, wy: 55.0   # valley floor elevation mock


@pytest.fixture(scope="module")
def railway_objects():
    return build_railway_objects(OsmData(), _ELEV_FN)


class TestBranchNodes:
    def test_minimum_nodes(self):
        assert len(FELSTED_BRANCH_NODES) >= 8

    def test_spans_full_width(self):
        """Trackbed should enter and exit the west and east map edges."""
        xs = [n[0] for n in FELSTED_BRANCH_NODES]
        assert min(xs) <= -WORLD_HALF
        assert max(xs) >= WORLD_HALF

    def test_nodes_have_four_elements(self):
        for n in FELSTED_BRANCH_NODES:
            assert len(n) == 4, f"Node {n} should be [wx, wy, z, width]"

    def test_track_elevation_plausible(self):
        """Felsted branch ran through the valley at 50–65 m ASL."""
        zs = [n[2] for n in FELSTED_BRANCH_NODES]
        assert all(45.0 < z < 70.0 for z in zs), f"z values: {zs}"

    def test_track_width_positive(self):
        for n in FELSTED_BRANCH_NODES:
            assert n[3] > 0

    def test_station_within_world(self):
        wx, wy = STATION_POS
        assert -WORLD_HALF <= wx <= WORLD_HALF
        assert -WORLD_HALF <= wy <= WORLD_HALF

    def test_station_south_of_campus(self):
        """Felsted Station was south-west and at lower elevation than the school."""
        wx, wy = STATION_POS
        assert wy < 0   # south of campus centre


class TestRailwayObjects:
    def test_returns_list(self, railway_objects):
        assert isinstance(railway_objects, list)

    def test_non_empty(self, railway_objects):
        assert len(railway_objects) >= 2   # at least trackbed + station marker

    def test_trackbed_present(self, railway_objects):
        names = {o["name"] for o in railway_objects}
        assert "railway_felsted_branch" in names

    def test_station_marker_present(self, railway_objects):
        names = {o["name"] for o in railway_objects}
        assert "felsted_station_site" in names

    def test_trackbed_is_decal_road(self, railway_objects):
        tb = next(o for o in railway_objects if o["name"] == "railway_felsted_branch")
        assert tb["class"] == "DecalRoad"

    def test_trackbed_has_nodes(self, railway_objects):
        tb = next(o for o in railway_objects if o["name"] == "railway_felsted_branch")
        assert len(tb["nodes"]) >= 8

    def test_trackbed_nodes_four_elements(self, railway_objects):
        tb = next(o for o in railway_objects if o["name"] == "railway_felsted_branch")
        for n in tb["nodes"]:
            assert len(n) == 4

    def test_station_is_ts_static(self, railway_objects):
        st = next(o for o in railway_objects if o["name"] == "felsted_station_site")
        assert st["class"] == "TSStatic"

    def test_station_elevation_uses_elev_fn(self, railway_objects):
        """Station z should be blended with _ELEV_FN output (~55 m)."""
        st = next(o for o in railway_objects if o["name"] == "felsted_station_site")
        z  = st["position"][2]
        assert 40.0 < z < 70.0

    def test_all_persistent_ids_unique(self, railway_objects):
        ids = [o["persistentId"] for o in railway_objects
               if "persistentId" in o]
        assert len(ids) == len(set(ids))

    def test_trackbed_uses_gravel_material(self, railway_objects):
        tb = next(o for o in railway_objects if o["name"] == "railway_felsted_branch")
        assert "gravel" in tb["material"].lower()

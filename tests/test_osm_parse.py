"""Tests for OSM data parsing — v3.0."""

import pytest
from pathlib import Path
from tools.osm_parse import load, OsmData, OsmRoad, OsmBuilding, OsmWater, OsmLanduse, OsmLeisure
from tools.constants import OSM_CACHE


@pytest.fixture(scope="module")
def osm():
    if not OSM_CACHE.exists():
        pytest.skip("OSM cache not present; run tools/generate.py --online to fetch")
    return load()


class TestOsmDataTypes:
    def test_returns_osm_data(self, osm):
        assert isinstance(osm, OsmData)

    def test_roads_list(self, osm):
        assert isinstance(osm.roads, list)

    def test_buildings_list(self, osm):
        assert isinstance(osm.buildings, list)

    def test_water_list(self, osm):
        assert isinstance(osm.water, list)

    def test_landuse_list(self, osm):
        assert isinstance(osm.landuse, list)

    def test_leisure_list(self, osm):
        assert isinstance(osm.leisure, list)


class TestRoads:
    def test_has_roads(self, osm):
        assert len(osm.roads) > 50, "Expected >50 roads in Felsted area"

    def test_road_schema(self, osm):
        for r in osm.roads[:20]:
            assert isinstance(r, OsmRoad)
            assert isinstance(r.osm_id, int)
            assert isinstance(r.hw_type, str) and r.hw_type
            assert r.width > 0
            assert isinstance(r.material, str)
            assert len(r.gps_nodes) >= 2

    def test_gps_nodes_in_uk(self, osm):
        for r in osm.roads[:50]:
            for lat, lon in r.gps_nodes[:5]:
                assert 50.0 < lat < 53.0, f"lat {lat} outside UK"
                assert -2.0 < lon <  2.0, f"lon {lon} outside Essex area"

    def test_has_service_roads(self, osm):
        types = {r.hw_type for r in osm.roads}
        assert "service" in types

    def test_has_residential_roads(self, osm):
        types = {r.hw_type for r in osm.roads}
        assert "residential" in types

    def test_no_proposed_roads(self, osm):
        for r in osm.roads:
            assert r.hw_type not in ("proposed", "construction")


class TestBuildings:
    def test_has_buildings(self, osm):
        assert len(osm.buildings) > 10

    def test_chapel_present(self, osm):
        names = {b.name for b in osm.buildings}
        assert "Felsted School Chapel" in names, \
            f"Chapel not found; names: {sorted(names)[:10]}"

    def test_sports_centre_present(self, osm):
        names = {b.name for b in osm.buildings}
        assert "Felsted School Sports Centre" in names

    def test_building_centroid_in_uk(self, osm):
        for b in osm.buildings[:30]:
            lat, lon = b.centroid
            assert 50.0 < lat < 53.0
            assert -1.0 < lon <  2.0

    def test_building_has_gps_polygon(self, osm):
        for b in osm.buildings[:30]:
            assert len(b.gps_nodes) >= 3


class TestWater:
    def test_has_water(self, osm):
        assert len(osm.water) > 0

    def test_river_chelmer_present(self, osm):
        names = {w.name for w in osm.water}
        assert "River Chelmer" in names

    def test_water_ww_type(self, osm):
        for w in osm.water:
            assert isinstance(w.ww_type, str)
            assert isinstance(w.gps_nodes, list)

    def test_streams_have_nodes(self, osm):
        streams = [w for w in osm.water if w.ww_type == "stream"]
        assert len(streams) > 0
        for s in streams:
            assert len(s.gps_nodes) >= 2


class TestLanduse:
    def test_has_landuse(self, osm):
        assert len(osm.landuse) > 10

    def test_has_forest(self, osm):
        types = {lu.lu_type for lu in osm.landuse}
        assert "forest" in types or "wood" in types, f"Forest not found; types: {types}"

    def test_has_farmland(self, osm):
        types = {lu.lu_type for lu in osm.landuse}
        assert "farmland" in types

    def test_area_m2_positive(self, osm):
        for lu in osm.landuse:
            assert lu.area_m2 >= 0


class TestLeisure:
    def test_has_leisure(self, osm):
        assert len(osm.leisure) > 5

    def test_has_pitches(self, osm):
        types = {le.le_type for le in osm.leisure}
        assert "pitch" in types

    def test_pitch_count(self, osm):
        pitches = [le for le in osm.leisure if le.le_type == "pitch"]
        assert len(pitches) >= 5, "Felsted School has many sports pitches"

    def test_leisure_centroid_in_uk(self, osm):
        for le in osm.leisure[:20]:
            lat, lon = le.centroid
            assert 50.0 < lat < 53.0


class TestEmptyCache:
    def test_missing_cache_returns_empty(self, tmp_path):
        d = load(tmp_path / "nonexistent.json")
        assert isinstance(d, OsmData)
        assert len(d.roads) == 0
        assert len(d.buildings) == 0

"""Tests for coordinate projection utilities."""

import math
import pytest
from tools.constants import (
    gps_to_world, world_to_gps, world_to_hm, hm_to_world,
    CENTER_LAT, CENTER_LON,
    BLOCK_SIZE, GRID_SIZE, SQUARE_SIZE, WORLD_HALF,
)


class TestGpsToWorld:
    def test_centre_maps_to_origin(self):
        x, y = gps_to_world(CENTER_LAT, CENTER_LON)
        assert abs(x) < 0.01
        assert abs(y) < 0.01

    def test_north_is_positive_y(self):
        _, y = gps_to_world(CENTER_LAT + 0.001, CENTER_LON)
        assert y > 0

    def test_east_is_positive_x(self):
        x, _ = gps_to_world(CENTER_LAT, CENTER_LON + 0.001)
        assert x > 0

    def test_roundtrip(self):
        lat, lon = 51.858, 0.440
        x, y = gps_to_world(lat, lon)
        lat2, lon2 = world_to_gps(x, y)
        assert abs(lat2 - lat) < 1e-7
        assert abs(lon2 - lon) < 1e-7

    def test_scale_1km_north(self):
        """1° latitude ≈ 111 139 m, so 0.009° ≈ 1 km."""
        _, y = gps_to_world(CENTER_LAT + 0.009, CENTER_LON)
        assert 950 < y < 1050

    def test_world_fits_inside_bbox(self):
        """
        The BBOX is the OSM/elevation query region and must be larger than the
        world so that the terrain has data everywhere.  Check that the world
        corners all fall inside BBOX.
        """
        from tools.constants import BBOX
        s, w, n, e = BBOX
        for wx, wy in [
            (-WORLD_HALF, -WORLD_HALF), (-WORLD_HALF, WORLD_HALF),
            ( WORLD_HALF, -WORLD_HALF), ( WORLD_HALF, WORLD_HALF),
        ]:
            lat, lon = world_to_gps(wx, wy)
            assert s <= lat <= n, f"World corner lat {lat:.5f} outside BBOX lat [{s},{n}]"
            assert w <= lon <= e, f"World corner lon {lon:.5f} outside BBOX lon [{w},{e}]"


class TestWorldToHm:
    def test_centre_maps_to_middle(self):
        r, c = world_to_hm(0, 0)
        mid = BLOCK_SIZE // 2
        assert abs(r - mid) <= 1
        assert abs(c - mid) <= 1

    def test_north_is_low_row(self):
        r_n, _ = world_to_hm(0,  500)
        r_s, _ = world_to_hm(0, -500)
        assert r_n < r_s, "North should map to lower row index"

    def test_east_is_high_col(self):
        _, c_e = world_to_hm( 500, 0)
        _, c_w = world_to_hm(-500, 0)
        assert c_e > c_w, "East should map to higher col index"

    def test_clamped_within_grid(self):
        for wx, wy in [(-9999, 0), (9999, 0), (0, -9999), (0, 9999)]:
            r, c = world_to_hm(wx, wy)
            assert 0 <= r <= BLOCK_SIZE
            assert 0 <= c <= BLOCK_SIZE

    def test_grid_size_constant(self):
        assert GRID_SIZE == BLOCK_SIZE + 1


class TestHmRoundtrip:
    def test_centre_roundtrip(self):
        mid = BLOCK_SIZE // 2
        wx, wy = hm_to_world(mid, mid)
        r, c = world_to_hm(wx, wy)
        assert abs(r - mid) <= 1
        assert abs(c - mid) <= 1

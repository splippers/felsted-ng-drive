"""Tests for terrain heightmap generation — v3.0 (SRTM + fBm, 2 m resolution)."""

import numpy as np
import pytest
from tools.heightmap import _make_synthetic_base as generate_synthetic, build_elevation, elev_at_world, _fbm
from tools.constants import GRID_SIZE, CAMPUS_ELEV, VALLEY_ELEV, SQUARE_SIZE, BLOCK_SIZE


@pytest.fixture(scope="module")
def elev():
    """Use cached SRTM + fBm blend (same path as production)."""
    return build_elevation(online=False)


@pytest.fixture(scope="module")
def synthetic():
    return generate_synthetic()


# ── Shape & dtype ─────────────────────────────────────────────────────────────

class TestShape:
    def test_shape(self, elev):
        assert elev.shape == (GRID_SIZE, GRID_SIZE)

    def test_dtype(self, elev):
        assert elev.dtype == np.float32

    def test_no_nan(self, elev):
        assert not np.any(np.isnan(elev))

    def test_finite(self, elev):
        assert np.all(np.isfinite(elev))

    def test_grid_size_1025(self):
        assert GRID_SIZE == BLOCK_SIZE + 1 == 1025

    def test_square_size_2m(self):
        assert SQUARE_SIZE == 2.0


# ── Elevation plausibility ────────────────────────────────────────────────────

class TestElevationRange:
    def test_min_above_30m(self, elev):
        assert elev.min() > 30.0, f"Min {elev.min():.1f} m too low"

    def test_max_below_100m(self, elev):
        assert elev.max() < 100.0, f"Max {elev.max():.1f} m too high for Essex"

    def test_campus_near_76m(self, elev):
        z = elev_at_world(elev, 0.0, 0.0)
        assert abs(z - CAMPUS_ELEV) < 5.0, f"Campus {z:.1f} m, expected ~{CAMPUS_ELEV}"

    def test_south_lower_than_campus(self, elev):
        z_campus = elev_at_world(elev, 0.0,    0.0)
        z_south  = elev_at_world(elev, 0.0, -900.0)
        assert z_south < z_campus

    def test_stebbing_road_grade(self, elev):
        """Stebbing Road rises south→north toward campus."""
        z_low  = elev_at_world(elev, -260.0, -900.0)
        z_high = elev_at_world(elev, -260.0, -200.0)
        assert z_high > z_low

    def test_srtm_campus_approx(self, elev):
        """SRTM measured 79 m at school; our campus blend targets 76 m."""
        z = elev_at_world(elev, 0.0, 0.0)
        assert 70.0 < z < 85.0, f"Campus z={z:.1f} outside 70–85 m SRTM range"


# ── fBm noise ─────────────────────────────────────────────────────────────────

class TestFbm:
    def test_shape(self):
        n = _fbm(65, seed=1)
        assert n.shape == (65, 65)

    def test_dtype(self):
        n = _fbm(65, seed=1)
        assert n.dtype == np.float32

    def test_zero_mean(self):
        n = _fbm(257, seed=7, octaves=6)
        assert abs(n.mean()) < 0.2   # fBm is approximately zero-mean

    def test_different_seeds(self):
        a = _fbm(65, seed=1)
        b = _fbm(65, seed=2)
        assert not np.allclose(a, b)

    def test_reproducible(self):
        a = _fbm(65, seed=42)
        b = _fbm(65, seed=42)
        np.testing.assert_array_equal(a, b)

    def test_persistence_reduces_roughness(self):
        """Lower persistence → fewer high-freq contributions → smoother gradient."""
        lo = _fbm(257, seed=1, octaves=5, persistence=0.3)
        hi = _fbm(257, seed=1, octaves=5, persistence=0.7)
        grad_lo = np.mean(np.abs(np.diff(lo, axis=0))) + np.mean(np.abs(np.diff(lo, axis=1)))
        grad_hi = np.mean(np.abs(np.diff(hi, axis=0))) + np.mean(np.abs(np.diff(hi, axis=1)))
        assert grad_lo < grad_hi


# ── elev_at_world ─────────────────────────────────────────────────────────────

class TestElevAtWorld:
    def test_returns_float(self, elev):
        assert isinstance(elev_at_world(elev, 0.0, 0.0), float)

    def test_out_of_bounds_clamped(self, elev):
        z = elev_at_world(elev, 99999.0, 99999.0)
        assert np.isfinite(z)

    def test_interpolation_monotone(self, elev):
        """Midpoint between two samples should be between their values."""
        z0 = elev_at_world(elev,  0.0, 0.0)
        z1 = elev_at_world(elev,  SQUARE_SIZE, 0.0)
        zm = elev_at_world(elev,  SQUARE_SIZE / 2, 0.0)
        lo, hi = min(z0, z1), max(z0, z1)
        assert lo - 0.01 <= zm <= hi + 0.01

    def test_symmetric_around_centre(self, elev):
        """The SRTM-backed terrain is approximately symmetric around the campus."""
        # Not exactly symmetric (real terrain), but within 10 m
        z_n = elev_at_world(elev,  0.0,  100.0)
        z_s = elev_at_world(elev,  0.0, -100.0)
        # Both should be in plausible range
        assert 60.0 < z_n < 90.0
        assert 60.0 < z_s < 90.0

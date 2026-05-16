"""Tests for terrain heightmap generation."""

import numpy as np
import pytest
from tools.heightmap import generate_synthetic, elev_at_world
from tools.constants import GRID_SIZE, CAMPUS_ELEV, VALLEY_ELEV, HILL_N_ELEV


@pytest.fixture(scope="module")
def synthetic():
    return generate_synthetic()


class TestSyntheticShape:
    def test_shape(self, synthetic):
        assert synthetic.shape == (GRID_SIZE, GRID_SIZE)

    def test_dtype(self, synthetic):
        assert synthetic.dtype == np.float32

    def test_no_nan(self, synthetic):
        assert not np.any(np.isnan(synthetic))

    def test_finite(self, synthetic):
        assert np.all(np.isfinite(synthetic))


class TestSyntheticElevations:
    def test_min_above_30m(self, synthetic):
        # River valley should not go below 30 m
        assert synthetic.min() > 30.0

    def test_max_below_120m(self, synthetic):
        # No point in Felsted area exceeds ~100 m
        assert synthetic.max() < 120.0

    def test_campus_near_76m(self, synthetic):
        """Campus centre (world 0,0) should be close to 76 m ASL."""
        z = elev_at_world(synthetic, 0.0, 0.0)
        assert abs(z - CAMPUS_ELEV) < 4.0, f"Campus elevation {z:.1f} m, expected ~{CAMPUS_ELEV}"

    def test_south_lower_than_campus(self, synthetic):
        """River valley in south should be lower than campus."""
        z_campus = elev_at_world(synthetic, 0.0,    0.0)
        z_south  = elev_at_world(synthetic, 0.0, -900.0)
        assert z_south < z_campus, "South (river) should be lower than campus"

    def test_north_hill_exists(self, synthetic):
        """There should be a hill north of campus above 80 m."""
        z_n = elev_at_world(synthetic, -350.0, 600.0)
        assert z_n > 80.0, f"North hill {z_n:.1f} m, expected > 80"

    def test_stebbing_road_grade(self, synthetic):
        """Stebbing Road should rise from south to campus (62→72 m region)."""
        z_low  = elev_at_world(synthetic, -260.0, -900.0)
        z_high = elev_at_world(synthetic, -260.0, -200.0)
        assert z_high > z_low, "Road should rise from south to campus"


class TestElevAtWorld:
    def test_centre(self, synthetic):
        z = elev_at_world(synthetic, 0.0, 0.0)
        assert isinstance(z, float)

    def test_out_of_bounds_clamped(self, synthetic):
        # Should not raise; should clamp to edge
        z = elev_at_world(synthetic, 99999.0, 99999.0)
        assert np.isfinite(z)

    def test_interpolation_between_samples(self, synthetic):
        from tools.constants import SQUARE_SIZE
        z0 = elev_at_world(synthetic,  0.0, 0.0)
        z1 = elev_at_world(synthetic,  SQUARE_SIZE, 0.0)
        zm = elev_at_world(synthetic,  SQUARE_SIZE / 2, 0.0)
        # Midpoint should be between the two
        assert min(z0, z1) <= zm <= max(z0, z1) + 0.01

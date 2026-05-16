"""Tests for .ter binary file writing and PNG heightmap output."""

import struct
import tempfile
from pathlib import Path

import numpy as np
import pytest

from tools.terrain_file import write_ter, write_heightmap_png, write_preview_png
from tools.constants import BLOCK_SIZE, GRID_SIZE, MAX_TERRAIN_HEIGHT


@pytest.fixture
def flat_elev():
    """Flat terrain at 76 m."""
    return np.full((GRID_SIZE, GRID_SIZE), 76.0, dtype=np.float32)


@pytest.fixture
def ramp_elev():
    """Linear ramp from 50 m (west) to 90 m (east)."""
    row = np.linspace(50.0, 90.0, GRID_SIZE, dtype=np.float32)
    return np.tile(row, (GRID_SIZE, 1))


class TestWriteTer:
    def _read_ter(self, path: Path) -> dict:
        with path.open("rb") as f:
            magic   = f.read(4)
            version = struct.unpack("<I", f.read(4))[0]
            bsize   = struct.unpack("<I", f.read(4))[0]
            nlayers = struct.unpack("<I", f.read(4))[0]
            n_verts = (bsize + 1) ** 2
            heights = np.frombuffer(f.read(n_verts * 2), dtype="<u2")
            flags   = np.frombuffer(f.read(n_verts),     dtype="u1")
        return dict(magic=magic, version=version, bsize=bsize,
                    nlayers=nlayers, heights=heights, flags=flags)

    def test_magic_header(self, flat_elev, tmp_path):
        p = tmp_path / "test.ter"
        write_ter(p, flat_elev)
        d = self._read_ter(p)
        assert d["magic"] == b"TERR"

    def test_version(self, flat_elev, tmp_path):
        p = tmp_path / "test.ter"
        write_ter(p, flat_elev)
        d = self._read_ter(p)
        assert d["version"] == 2

    def test_block_size(self, flat_elev, tmp_path):
        p = tmp_path / "test.ter"
        write_ter(p, flat_elev)
        d = self._read_ter(p)
        assert d["bsize"] == BLOCK_SIZE

    def test_num_layers(self, flat_elev, tmp_path):
        p = tmp_path / "test.ter"
        write_ter(p, flat_elev)
        d = self._read_ter(p)
        assert d["nlayers"] == 1

    def test_height_count(self, flat_elev, tmp_path):
        p = tmp_path / "test.ter"
        write_ter(p, flat_elev)
        d = self._read_ter(p)
        assert len(d["heights"]) == GRID_SIZE ** 2

    def test_flat_terrain_constant_heights(self, flat_elev, tmp_path):
        p = tmp_path / "flat.ter"
        write_ter(p, flat_elev)
        d = self._read_ter(p)
        assert d["heights"].min() == d["heights"].max()

    def test_height_encoding_range(self, flat_elev, tmp_path):
        """76 m / 200 m × 65535 ≈ 24 903."""
        p = tmp_path / "flat.ter"
        write_ter(p, flat_elev)
        d = self._read_ter(p)
        expected = int(76.0 / MAX_TERRAIN_HEIGHT * 65535)
        assert abs(int(d["heights"][0]) - expected) <= 1

    def test_ramp_heights_monotonic(self, ramp_elev, tmp_path):
        p = tmp_path / "ramp.ter"
        write_ter(p, ramp_elev)
        d = self._read_ter(p)
        # Heights across a row should be monotonically increasing
        row_heights = d["heights"][:GRID_SIZE]
        assert all(row_heights[i] <= row_heights[i+1]
                   for i in range(len(row_heights)-1))

    def test_flags_all_zero(self, flat_elev, tmp_path):
        p = tmp_path / "flat.ter"
        write_ter(p, flat_elev)
        d = self._read_ter(p)
        assert d["flags"].max() == 0

    def test_creates_parent_dirs(self, flat_elev, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "terrain.ter"
        write_ter(deep, flat_elev)
        assert deep.exists()

    def test_wrong_shape_raises(self, tmp_path):
        bad = np.zeros((100, 100), dtype=np.float32)
        with pytest.raises(ValueError):
            write_ter(tmp_path / "bad.ter", bad)


class TestWriteHeightmapPng:
    def test_creates_file(self, flat_elev, tmp_path):
        p = tmp_path / "h.png"
        write_heightmap_png(p, flat_elev)
        assert p.exists()

    def test_png_is_readable(self, flat_elev, tmp_path):
        from PIL import Image
        p = tmp_path / "h.png"
        write_heightmap_png(p, flat_elev)
        img = Image.open(p)
        assert img is not None


class TestWritePreviewPng:
    def test_creates_rgb_png(self, flat_elev, tmp_path):
        from PIL import Image
        p = tmp_path / "preview.png"
        write_preview_png(p, flat_elev)
        img = Image.open(p)
        assert img.mode == "RGB"
        assert img.size == (512, 512)

"""
Generate placeholder terrain textures (grass diffuse + flat normal map).
Run once; the generator does NOT call this automatically — BeamNG can
substitute any compatible 512×512 texture if you have better art assets.
"""

import numpy as np
from PIL import Image
from pathlib import Path

OUT = Path(__file__).parent


def _grass_diffuse(size: int = 512) -> None:
    rng = np.random.default_rng(1)
    # Base mid-green
    r = np.full((size, size), 72,  dtype=np.uint8)
    g = np.full((size, size), 110, dtype=np.uint8)
    b = np.full((size, size), 45,  dtype=np.uint8)
    # Subtle noise
    noise = rng.integers(-18, 18, (size, size), dtype=np.int16)
    r = np.clip(r.astype(np.int16) + noise // 2, 50, 120).astype(np.uint8)
    g = np.clip(g.astype(np.int16) + noise,       80, 160).astype(np.uint8)
    b = np.clip(b.astype(np.int16) + noise // 3,  20,  80).astype(np.uint8)
    img = Image.fromarray(np.stack([r, g, b], axis=-1), mode="RGB")
    img.save(OUT / "diffuse.png")
    print("Wrote diffuse.png")


def _flat_normal(size: int = 512) -> None:
    r = np.full((size, size), 128, dtype=np.uint8)
    g = np.full((size, size), 128, dtype=np.uint8)
    b = np.full((size, size), 255, dtype=np.uint8)
    img = Image.fromarray(np.stack([r, g, b], axis=-1), mode="RGB")
    img.save(OUT / "normal.png")
    print("Wrote normal.png")


if __name__ == "__main__":
    _grass_diffuse()
    _flat_normal()
    print("Done.")

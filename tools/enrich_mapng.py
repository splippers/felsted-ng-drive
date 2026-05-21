#!/usr/bin/env python3
"""
enrich_mapng.py — Enrich a mapng-generated Felsted.zip with OSM detail.

Reads   : Felsted.zip  (mapng-generated, loads in-game)
Writes  : Felsted_enriched.zip  (same map + new content groups)

New content
───────────
  Buildings/   ← 126 OSM building footprints extruded to 3-D COLLADA DAE
  Railway/     ← Witham–Dunmow branch trackbed (GER, closed 1953)
  OSM_Water/   ← River Chelmer, Stebbing Brook, OSM streams & ponds
  OSM_Paths/   ← 191 footways + 24 bridleways through campus and village
  OSM_Forest/  ← woodland / forest areas as BeamNG Forest groups

Coordinate system
─────────────────
  mapng centre : 51.8582 N, 0.4378 E  (from Felsted.zip info.json)
  Terrain      : 1 024 × 1 024 cells, 2 m/cell → ±1 024 m world
  Heights      : calibrated from theTerrain.terrainheightmap.png using road
                 node Z values embedded in the source zip

Usage
─────
    cd /mnt/SANDIEGO/Projects/felsted-ng-drive
    python3 tools/enrich_mapng.py
    python3 tools/enrich_mapng.py --input Felsted.zip --output Felsted_enriched.zip
    python3 tools/enrich_mapng.py --satellite
    python3 tools/enrich_mapng.py --photos /home/jon/felsted-archive
    python3 tools/enrich_mapng.py --satellite --photos /home/jon/felsted-archive
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import math
import sqlite3
import struct
import time
import urllib.request
import uuid
import zipfile
import zlib
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image

ROOT = Path(__file__).parent.parent
log  = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# mapng coordinate system
# ─────────────────────────────────────────────────────────────────────────────
_MAPNG_LAT  = 51.8582
_MAPNG_LON  = 0.4378
_N          = 1024                              # terrain cells per side
_SQ         = 2.0                              # metres / cell
_WORLD_HALF = _N * _SQ / 2                    # 1 024 m

_LAT_M = 111_139.0
_LON_M = _LAT_M * math.cos(math.radians(_MAPNG_LAT))   # ≈ 68 593 m/°


def gps_to_world(lat: float, lon: float) -> tuple[float, float]:
    return (lon - _MAPNG_LON) * _LON_M, (lat - _MAPNG_LAT) * _LAT_M


def in_world(wx: float, wy: float, margin: float = 80.0) -> bool:
    return (
        -_WORLD_HALF - margin <= wx <= _WORLD_HALF + margin and
        -_WORLD_HALF - margin <= wy <= _WORLD_HALF + margin
    )


# generator centre is (51.8588, 0.4371); for same GPS point:
#   mapng_x ≈ gen_x − 48,  mapng_y ≈ gen_y + 67
_GEN_DX, _GEN_DY = -48.0, +67.0

def gen_to_mapng(gx: float, gy: float) -> tuple[float, float]:
    return gx + _GEN_DX, gy + _GEN_DY


# ─────────────────────────────────────────────────────────────────────────────
# Heightmap: read PNG → calibrate maxHeight → elevation function
# ─────────────────────────────────────────────────────────────────────────────

def _load_hm(png_bytes: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(png_bytes))
    # mapng exports RGBA 8-bit (R=G=B=height, A=255); also handle greyscale.
    if img.mode in ('RGBA', 'RGB'):
        arr = np.array(img.split()[0], dtype=np.float32)   # R channel, 0-255
    elif img.mode == 'I':
        arr = np.array(img, dtype=np.float32)               # 16-bit grey
    else:
        arr = np.array(img.convert('L'), dtype=np.float32)  # 8-bit grey
    return arr


def _calibrate(hm: np.ndarray, pts: list[tuple[float, float, float]]) -> float:
    """Median estimate of maxHeight from (wx, wy, z) road-node calibration pts."""
    hm_max = float(hm.max()) or 255.0
    h, w = hm.shape
    estimates = []
    for wx, wy, z in pts:
        col = max(0, min(w - 1, int((wx + _WORLD_HALF) / _SQ)))
        row = max(0, min(h - 1, int((_WORLD_HALF - wy) / _SQ)))
        raw = float(hm[row, col])
        if raw > hm_max * 0.05:
            estimates.append(z * hm_max / raw)
    if not estimates:
        log.warning("No calibration points found; defaulting maxHeight = 20 m")
        return 20.0
    maxh = sorted(estimates)[len(estimates) // 2]
    log.info("maxHeight = %.2f m (hm_max=%.0f, %d calibration nodes)",
             maxh, hm_max, len(estimates))
    return maxh


def _elev_fn(hm: np.ndarray, maxh: float) -> Callable[[float, float], float]:
    hm_max = float(hm.max()) or 255.0
    rows, cols = hm.shape
    def elev(wx: float, wy: float) -> float:
        c = max(0, min(cols - 1, int((wx + _WORLD_HALF) / _SQ)))
        r = max(0, min(rows - 1, int((_WORLD_HALF - wy) / _SQ)))
        return float(hm[r, c]) / hm_max * maxh
    return elev


def _collect_calib(zf: zipfile.ZipFile) -> list[tuple[float, float, float]]:
    """Extract (wx, wy, z) from all DecalRoad nodes in the working zip."""
    pts: list[tuple[float, float, float]] = []
    for name in zf.namelist():
        if 'Decal_Roads/' not in name or not name.endswith('/items.level.json'):
            continue
        for line in zf.read(name).decode().strip().split('\n'):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            for node in obj.get('nodes', []):
                if len(node) >= 3:
                    pts.append((float(node[0]), float(node[1]), float(node[2])))
    return pts


# ─────────────────────────────────────────────────────────────────────────────
# OSM data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_osm(path: Path) -> dict:
    raw = json.loads(path.read_text())
    nodes_by_id = {
        e['id']: (e['lat'], e['lon'])
        for e in raw['elements'] if e['type'] == 'node'
    }
    buildings, waterways, landuse, leisure, highways = [], [], [], [], []
    seen: set[int] = set()
    for el in raw['elements']:
        if el['type'] != 'way':
            continue
        wid = el['id']
        if wid in seen:
            continue
        seen.add(wid)
        tags = el.get('tags', {})
        gps  = [nodes_by_id[n] for n in el.get('nodes', []) if n in nodes_by_id]
        if len(gps) < 2:
            continue
        if 'building' in tags:
            buildings.append({'id': wid, 'tags': tags, 'gps': gps})
        elif 'waterway' in tags or tags.get('natural') == 'water':
            waterways.append({'id': wid, 'tags': tags, 'gps': gps})
        elif 'landuse' in tags or tags.get('natural') in ('wood', 'scrub'):
            landuse.append({'id': wid, 'tags': tags, 'gps': gps})
        elif 'leisure' in tags:
            leisure.append({'id': wid, 'tags': tags, 'gps': gps})
        elif 'highway' in tags:
            highways.append({'id': wid, 'tags': tags, 'gps': gps})
    return dict(buildings=buildings, waterways=waterways,
                landuse=landuse, leisure=leisure, highways=highways)


# ─────────────────────────────────────────────────────────────────────────────
# COLLADA DAE generator (local-space: origin at building centroid)
# ─────────────────────────────────────────────────────────────────────────────

_BUILDING_HEIGHTS = {
    'school': 12.0, 'university': 12.0, 'chapel': 18.0, 'church': 18.0,
    'cathedral': 22.0, 'residential': 8.0, 'house': 7.0,
    'semidetached_house': 7.0, 'detached': 7.0,
    'apartments': 12.0, 'commercial': 10.0, 'retail': 6.0,
    'industrial': 8.0, 'warehouse': 10.0, 'office': 12.0,
    'garage': 3.5, 'shed': 3.0, 'pavilion': 8.0, 'yes': 8.0,
}


def _poly_area_sign(pts: list[tuple[float, float]]) -> float:
    n = len(pts)
    a = sum(pts[i][0] * pts[(i+1)%n][1] - pts[(i+1)%n][0] * pts[i][1]
            for i in range(n))
    return a / 2.0


def _ear_clip(pts: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    n = len(pts)
    if n < 3:
        return []
    idx = list(range(n))
    tris: list[tuple[int, int, int]] = []
    sign = _poly_area_sign(pts)

    def _in_tri(p, a, b, c):
        def s(p1, p2, p3):
            return (p1[0]-p3[0])*(p2[1]-p3[1]) - (p2[0]-p3[0])*(p1[1]-p3[1])
        d1, d2, d3 = s(p,a,b), s(p,b,c), s(p,c,a)
        return not ((d1<0 or d2<0 or d3<0) and (d1>0 or d2>0 or d3>0))

    guard = n * n + 10
    while len(idx) > 3 and guard > 0:
        guard -= 1
        for i in range(len(idx)):
            pi, ci, ni = idx[(i-1)%len(idx)], idx[i], idx[(i+1)%len(idx)]
            a, b, c = pts[pi], pts[ci], pts[ni]
            cross = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
            if (sign > 0 and cross < 0) or (sign < 0 and cross > 0):
                continue
            if any(_in_tri(pts[j], a, b, c)
                   for j in idx if j not in (pi, ci, ni)):
                continue
            tris.append((pi, ci, ni))
            idx.pop(i)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))  # type: ignore[arg-type]
    return tris


def _write_dae(poly_local: list[tuple[float, float]],
               height: float, name: str) -> str:
    """Return COLLADA XML for an extruded building polygon in local space."""
    n = len(poly_local)
    if n < 3:
        return ''
    # bottom ring z=0, top ring z=height
    verts = [(x, y, 0.0) for x, y in poly_local] + \
            [(x, y, height) for x, y in poly_local]
    tris: list[tuple[int, int, int]] = []
    # walls
    for i in range(n):
        j = (i + 1) % n
        tris += [(i, j, j+n), (i, j+n, i+n)]
    # roof
    roof = _ear_clip(poly_local)
    if _poly_area_sign(poly_local) < 0:
        tris += [(a+n, c+n, b+n) for a, b, c in roof]
    else:
        tris += [(a+n, b+n, c+n) for a, b, c in roof]

    vert_str = ' '.join(f'{v[0]:.3f} {v[1]:.3f} {v[2]:.3f}' for v in verts)
    tri_str  = ' '.join(f'{a} {b} {c}' for a, b, c in tris)
    gid = f'geo_{name[:28]}'
    mid = 'Mat_bld'
    return f"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>
  <library_materials>
    <material id="{mid}" name="building">
      <instance_effect url="#{mid}_fx"/>
    </material>
  </library_materials>
  <library_effects>
    <effect id="{mid}_fx">
      <profile_COMMON><technique sid="common">
        <phong>
          <diffuse><color>0.72 0.65 0.55 1</color></diffuse>
          <specular><color>0.04 0.04 0.04 1</color></specular>
        </phong>
      </technique></profile_COMMON>
    </effect>
  </library_effects>
  <library_geometries>
    <geometry id="{gid}" name="{name[:64]}">
      <mesh>
        <source id="{gid}_p">
          <float_array id="{gid}_pa" count="{len(verts)*3}">{vert_str}</float_array>
          <technique_common>
            <accessor source="#{gid}_pa" count="{len(verts)}" stride="3">
              <param name="X" type="float"/><param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <vertices id="{gid}_v"><input semantic="POSITION" source="#{gid}_p"/></vertices>
        <triangles count="{len(tris)}" material="{mid}">
          <input semantic="VERTEX" source="#{gid}_v" offset="0"/>
          <p>{tri_str}</p>
        </triangles>
      </mesh>
    </geometry>
  </library_geometries>
  <library_visual_scenes>
    <visual_scene id="Scene" name="Scene">
      <node id="Bld" name="{name[:64]}" type="NODE">
        <instance_geometry url="#{gid}">
          <bind_material><technique_common>
            <instance_material symbol="{mid}" target="#{mid}"/>
          </technique_common></bind_material>
        </instance_geometry>
      </node>
    </visual_scene>
  </library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>"""


# ─────────────────────────────────────────────────────────────────────────────
# Billboard DAE (for photo overlays)
# ─────────────────────────────────────────────────────────────────────────────

def _write_billboard_dae(photo_id: int, tex_zip_path: str,
                         w: float = 3.0, h: float = 2.0) -> str:
    """COLLADA for a textured vertical plane, w×h metres, local space.

    The plane lies in the XZ plane (faces ±Y / north–south).
    tex_zip_path is the in-zip path BeamNG will load, e.g.
    '/levels/Felsted/art/billboards/p_42.jpg'.
    """
    gid = f'geo_bb_{photo_id}'
    mid = f'Mat_bb_{photo_id}'
    iid = f'Img_bb_{photo_id}'
    hw  = w / 2.0
    # Vertices: BL, BR, TR, TL  (XZ plane, Y=0)
    vert_str = f'{-hw:.3f} 0 0  {hw:.3f} 0 0  {hw:.3f} 0 {h:.3f}  {-hw:.3f} 0 {h:.3f}'
    # UV: bottom-left origin
    uv_str   = '0 1  1 1  1 0  0 0'
    # Two triangles: 0,1,2 and 0,2,3
    tri_str  = '0 0 1 1 2 2  0 0 2 2 3 3'
    return f"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>
  <library_images>
    <image id="{iid}" name="{iid}">
      <init_from>{tex_zip_path}</init_from>
    </image>
  </library_images>
  <library_materials>
    <material id="{mid}" name="billboard_{photo_id}">
      <instance_effect url="#{mid}_fx"/>
    </material>
  </library_materials>
  <library_effects>
    <effect id="{mid}_fx">
      <profile_COMMON>
        <newparam sid="{iid}_surf"><surface type="2D"><init_from>{iid}</init_from></surface></newparam>
        <newparam sid="{iid}_samp"><sampler2D><source>{iid}_surf</source></sampler2D></newparam>
        <technique sid="common">
          <lambert>
            <diffuse><texture texture="{iid}_samp" texcoord="UVMap"/></diffuse>
          </lambert>
        </technique>
      </profile_COMMON>
    </effect>
  </library_effects>
  <library_geometries>
    <geometry id="{gid}" name="billboard_{photo_id}">
      <mesh>
        <source id="{gid}_p">
          <float_array id="{gid}_pa" count="12">{vert_str}</float_array>
          <technique_common>
            <accessor source="#{gid}_pa" count="4" stride="3">
              <param name="X" type="float"/><param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <source id="{gid}_uv">
          <float_array id="{gid}_uva" count="8">{uv_str}</float_array>
          <technique_common>
            <accessor source="#{gid}_uva" count="4" stride="2">
              <param name="S" type="float"/><param name="T" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <vertices id="{gid}_v"><input semantic="POSITION" source="#{gid}_p"/></vertices>
        <triangles count="2" material="{mid}">
          <input semantic="VERTEX"   source="#{gid}_v"  offset="0"/>
          <input semantic="TEXCOORD" source="#{gid}_uv" offset="1" set="0"/>
          <p>{tri_str}</p>
        </triangles>
      </mesh>
    </geometry>
  </library_geometries>
  <library_visual_scenes>
    <visual_scene id="Scene" name="Scene">
      <node id="Billboard_{photo_id}" name="billboard_{photo_id}" type="NODE">
        <instance_geometry url="#{gid}">
          <bind_material><technique_common>
            <instance_material symbol="{mid}" target="#{mid}">
              <bind_vertex_input semantic="UVMap" input_semantic="TEXCOORD" input_set="0"/>
            </instance_material>
          </technique_common></bind_material>
        </instance_geometry>
      </node>
    </visual_scene>
  </library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>"""


def gen_photos(archive_root: Path, elev: Callable) \
        -> tuple[list[dict], dict[str, str], dict[str, bytes]]:
    """Read geolocated photos from the felsted-archive SQLite DB.

    Returns:
        billboard_objects  — list of TSStatic scene items
        billboard_daes     — {zip_path: dae_xml}
        photo_blobs        — {zip_path: raw_bytes}  (the image files to bundle)
    """
    db_path    = archive_root / 'data' / 'archive.db'
    upload_dir = archive_root / 'pics' / 'uploads'

    if not db_path.exists():
        log.warning('Photos: archive DB not found at %s', db_path)
        return [], {}, {}

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, filename, path, title, year, lat, lng, photo_use "
        "FROM pics WHERE lat IS NOT NULL AND lng IS NOT NULL "
        "  AND lat != 0 AND lng != 0 AND path LIKE '/pics/uploads/%'"
    ).fetchall()
    con.close()

    objects:  list[dict]       = []
    daes:     dict[str, str]   = {}
    blobs:    dict[str, bytes] = {}
    skipped = 0

    for row in rows:
        pid  = row['id']
        lat, lng = float(row['lat']), float(row['lng'])
        wx, wy   = gps_to_world(lat, lng)
        if not in_world(wx, wy, margin=20.0):
            skipped += 1
            continue

        fname     = row['filename']
        src_file  = upload_dir / fname
        if not src_file.exists():
            log.debug('Photo %d: file missing at %s, skipping', pid, src_file)
            skipped += 1
            continue

        # Destination paths inside the zip
        ext          = src_file.suffix.lower() or '.jpg'
        tex_zip      = f'levels/Felsted/art/billboards/p_{pid}{ext}'
        dae_zip      = f'levels/Felsted/art/shapes/billboards/bb_{pid}.dae'
        tex_in_game  = f'/levels/Felsted/art/billboards/p_{pid}{ext}'

        blobs[tex_zip] = src_file.read_bytes()
        daes[dae_zip]  = _write_billboard_dae(pid, tex_in_game)

        wz      = elev(wx, wy)
        use     = row['photo_use'] or 'billboard'
        title   = row['title'] or fname
        year    = row['year']
        note    = f'{title} ({year})' if year else title

        objects.append({
            'class':        'TSStatic',
            'name':         f'photo_bb_{pid}',
            'persistentId': _uid(),
            'shapeName':    f'/levels/Felsted/art/shapes/billboards/bb_{pid}.dae',
            'position':     [round(wx, 2), round(wy, 2), round(wz, 2)],
            'scale':        [1.0, 1.0, 1.0],
            'rotation':     [1.0, 0.0, 0.0, 0.0],
            'collisionType': 'None',
            'playAmbient':   False,
            '_use':          use,
            '_note':         note,
        })

    log.info('Photos: %d billboards placed, %d skipped', len(objects), skipped)
    return objects, daes, blobs


# ─────────────────────────────────────────────────────────────────────────────
# Object generators
# ─────────────────────────────────────────────────────────────────────────────

def _uid() -> str:
    return str(uuid.uuid4())


def gen_buildings(osm: dict, elev: Callable) -> tuple[list[dict], dict[str, str]]:
    """
    Returns (scene_objects, {dae_zip_path: dae_xml_string}).
    Each TSStatic is placed at the building centroid; DAE is local-space.
    """
    objects: list[dict] = []
    daes:    dict[str, str] = {}
    skipped = 0
    for bld in osm['buildings']:
        gps = bld['gps']
        if len(gps) < 4:
            skipped += 1
            continue
        poly_w = [gps_to_world(la, lo) for la, lo in gps]
        if poly_w[0] == poly_w[-1]:
            poly_w = poly_w[:-1]
        if len(poly_w) < 3:
            skipped += 1
            continue
        cx = sum(p[0] for p in poly_w) / len(poly_w)
        cy = sum(p[1] for p in poly_w) / len(poly_w)
        if not in_world(cx, cy):
            skipped += 1
            continue
        cz = elev(cx, cy)
        # local-space footprint (subtract centroid)
        local = [(p[0] - cx, p[1] - cy) for p in poly_w]
        btype  = bld['tags'].get('building', 'yes').lower()
        height = float(bld['tags'].get('height', 0)) or \
                 float(bld['tags'].get('building:levels', 0)) * 3.2 or \
                 _BUILDING_HEIGHTS.get(btype, 8.0)
        safe_id  = str(bld['id'])
        dae_path = f'levels/Felsted/art/shapes/buildings/bld_{safe_id}.dae'
        xml = _write_dae(local, height, bld['tags'].get('name', f'bld_{safe_id}'))
        if not xml:
            skipped += 1
            continue
        daes[dae_path] = xml
        objects.append({
            'class':      'TSStatic',
            'name':       f'bld_{safe_id}',
            'persistentId': _uid(),
            'shapeName':  f'/levels/Felsted/art/shapes/buildings/bld_{safe_id}.dae',
            'position':   [round(cx, 2), round(cy, 2), round(cz, 2)],
            'scale':      [1.0, 1.0, 1.0],
            'rotation':   [1.0, 0.0, 0.0, 0.0],
            'collisionType': 'Visible',
            'playAmbient':   False,
            'allowPlayerStep': False,
        })
    log.info('Buildings: %d meshes, %d skipped', len(objects), skipped)
    return objects, daes


def gen_railway(elev: Callable) -> list[dict]:
    """Witham–Dunmow branch trackbed DecalRoad (GER, closed 1953)."""
    # Hardcoded nodes are in generator coordinate space; apply gen_to_mapng offset.
    _GEN_NODES = [
        [-1024, -286, 4.0], [-720, -295, 4.0], [-540, -308, 4.0],
        [-420,  -318, 4.0], [-310, -325, 4.0], [-160, -330, 4.0],
        [  40,  -328, 4.0], [ 220, -322, 4.0], [ 440, -318, 4.0],
        [ 650,  -315, 4.0], [ 870, -316, 4.0], [1024, -318, 4.0],
    ]
    nodes = []
    for gx, gy, _z in _GEN_NODES:
        mx, my = gen_to_mapng(gx, gy)
        nodes.append([round(mx, 1), round(my, 1), round(elev(mx, my), 3), 4.0])
    # Station marker
    sx, sy = gen_to_mapng(-420, -318)
    sz = elev(sx, sy)
    return [
        {
            'class':          'DecalRoad',
            'name':           'railway_felsted_branch',
            'persistentId':   _uid(),
            'material':       'road_gravel_01',
            'renderPriority': 10,
            'textureLength':  6,
            'drivability':    0,
            'breakAngle':     3.0,
            'overObjects':    False,
            'nodes':          nodes,
        },
        {
            'class':        'BeamNGTrigger',
            'name':         'felsted_station_marker',
            'persistentId': _uid(),
            'position':     [round(sx, 1), round(sy, 1), round(sz + 0.1, 3)],
            'rotation':     [1, 0, 0, 0],
            'scale':        [4, 4, 3],
            'triggerType':  'Sphere',
            'luaFunction':  '',
            '_note':        'Felsted Station, GER, closed 1953',
        },
    ]


def gen_water(osm: dict, elev: Callable) -> list[dict]:
    objects: list[dict] = []

    # River Chelmer — hardcoded nodes in generator coords
    _CHELMER_GEN = [
        [-1024,-650], [-800,-680], [-580,-720], [-350,-750],
        [-100, -770], [ 150,-760], [ 400,-740], [ 650,-700],
        [ 900, -650], [1024,-620],
    ]
    chelmer_nodes = []
    for gx, gy in _CHELMER_GEN:
        mx, my = gen_to_mapng(gx, gy)
        z = elev(mx, my) - 0.3
        chelmer_nodes.append([round(mx,1), round(my,1), round(z,3), 10.0])
    objects.append({
        'class': 'DecalRoad', 'name': 'river_chelmer',
        'persistentId': _uid(), 'material': 'water',
        'renderPriority': 20, 'textureLength': 20, 'drivability': 0,
        'nodes': chelmer_nodes,
    })
    # WaterBlock over the Chelmer
    cmx, cmy = gen_to_mapng(-150, -720)
    objects.append({
        'class': 'WaterBlock', 'name': 'waterblock_chelmer',
        'persistentId': _uid(),
        'position': [round(cmx,1), round(cmy,1), round(elev(cmx,cmy)-0.2, 3)],
        'rotation': [1, 0, 0, 0],
        'scale':    [2200, 60, 4.0],
        'baseColor': [0.15, 0.35, 0.55, 0.85], 'clarity': 0.5,
    })

    # Stebbing Brook — hardcoded nodes in generator coords
    _BROOK_GEN = [
        [-320,-1024], [-310,-850], [-290,-700], [-275,-580],
        [-262,-450],  [-258,-300], [-255,-200],
    ]
    brook_nodes = []
    for gx, gy in _BROOK_GEN:
        mx, my = gen_to_mapng(gx, gy)
        z = elev(mx, my) - 0.3
        brook_nodes.append([round(mx,1), round(my,1), round(z,3), 4.0])
    objects.append({
        'class': 'DecalRoad', 'name': 'stream_stebbing_brook',
        'persistentId': _uid(), 'material': 'water',
        'renderPriority': 20, 'textureLength': 8, 'drivability': 0,
        'nodes': brook_nodes,
    })

    # OSM streams and ponds
    for wf in osm['waterways']:
        tags   = wf['tags']
        ww     = tags.get('waterway', '')
        is_area = tags.get('natural') == 'water'
        if is_area:
            pts = [gps_to_world(la, lo) for la, lo in wf['gps']]
            cx  = sum(p[0] for p in pts) / len(pts)
            cy  = sum(p[1] for p in pts) / len(pts)
            if not in_world(cx, cy):
                continue
            area = abs(_poly_area(pts))
            side = max(10.0, area ** 0.5)
            objects.append({
                'class': 'WaterBlock', 'name': f'pond_{wf["id"]}',
                'persistentId': _uid(),
                'position': [round(cx,1), round(cy,1), round(elev(cx,cy)-0.2, 3)],
                'rotation': [1, 0, 0, 0], 'scale': [round(side,1), round(side,1), 2.0],
                'baseColor': [0.1, 0.3, 0.5, 0.8], 'clarity': 0.6,
            })
        elif ww in ('stream', 'drain', 'ditch'):
            width = {'stream': 3.0, 'drain': 2.0, 'ditch': 1.5}.get(ww, 2.0)
            nodes = []
            for la, lo in wf['gps']:
                wx, wy = gps_to_world(la, lo)
                if not in_world(wx, wy):
                    continue
                nodes.append([round(wx,2), round(wy,2), round(elev(wx,wy)-0.3, 3), width])
            if len(nodes) >= 2:
                objects.append({
                    'class': 'DecalRoad', 'name': f'stream_{wf["id"]}',
                    'persistentId': _uid(), 'material': 'water',
                    'renderPriority': 20, 'textureLength': 6, 'drivability': 0,
                    'nodes': nodes,
                })
    log.info('Water: %d objects', len(objects))
    return objects


_PATH_MATERIAL = {
    'footway':   'sidewalk',
    'path':      'sidewalk',
    'pedestrian':'sidewalk',
    'bridleway': 'dirt',
    'steps':     'sidewalk',
}
_PATH_WIDTH = {
    'footway': 1.5, 'path': 1.5, 'pedestrian': 2.5,
    'bridleway': 2.0, 'steps': 1.5,
}


def gen_paths(osm: dict, elev: Callable) -> list[dict]:
    """Footways and bridleways not already in the base map's 17 named roads."""
    objects: list[dict] = []
    for hw in osm['highways']:
        hw_type = hw['tags'].get('highway', '')
        if hw_type not in _PATH_MATERIAL:
            continue
        mat   = _PATH_MATERIAL[hw_type]
        width = _PATH_WIDTH[hw_type]
        nodes = []
        for la, lo in hw['gps']:
            wx, wy = gps_to_world(la, lo)
            if not in_world(wx, wy):
                continue
            nodes.append([round(wx,2), round(wy,2), round(elev(wx,wy)+0.02, 3), width])
        if len(nodes) >= 2:
            objects.append({
                'class':          'DecalRoad',
                'name':           f'path_{hw["id"]}',
                'persistentId':   _uid(),
                'material':       mat,
                'renderPriority': 8,
                'textureLength':  4,
                'drivability':    1,
                'breakAngle':     3,
                'depthBias':      -0.001,
                'nodes':          nodes,
            })
    log.info('Paths: %d footways/bridleways', len(objects))
    return objects


def gen_forest(osm: dict, elev: Callable) -> list[dict]:
    """Woodland and forest areas as BeamNG Forest + ForestItemData pairs."""
    objects: list[dict] = []
    forest_types = ('forest', 'wood', 'scrub')
    for lu in osm['landuse']:
        lu_type = lu['tags'].get('landuse') or lu['tags'].get('natural', '')
        if lu_type not in forest_types:
            continue
        pts = [gps_to_world(la, lo) for la, lo in lu['gps']]
        cx  = sum(p[0] for p in pts) / len(pts)
        cy  = sum(p[1] for p in pts) / len(pts)
        if not in_world(cx, cy):
            continue
        area = abs(_poly_area(pts))
        if area < 200:
            continue
        side = round(area ** 0.5, 1)
        cz   = elev(cx, cy)
        tag  = f'forest_{lu["id"]}'
        objects.append({
            'class': 'SimGroup', 'name': tag, 'persistentId': _uid(),
            'children': [
                {
                    'class': 'ForestItemData', 'name': f'{tag}_item',
                    'persistentId': _uid(),
                    'shapeFile':  'art/shapes/trees/defaulttree.dae',
                    'colorsHaveAlpha': True,
                    'maxScale': 8.0, 'minScale': 4.0, 'windScale': 0.3,
                },
                {
                    'class': 'Forest', 'name': f'{tag}_inst',
                    'persistentId': _uid(),
                    'position':   [round(cx,1), round(cy,1), round(cz,1)],
                    'scale':      [side, side, 1.0],
                    'dataBlocks': [f'{tag}_item'],
                },
            ],
        })
    log.info('Forest: %d woodland groups', len(objects))
    return objects


def _poly_area(pts: list[tuple[float, float]]) -> float:
    n = len(pts)
    if n < 3:
        return 0.0
    return sum(pts[i][0]*pts[(i+1)%n][1] - pts[(i+1)%n][0]*pts[i][1]
               for i in range(n)) / 2.0


# ─────────────────────────────────────────────────────────────────────────────
# NDJSON helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ndjson(objs: list[dict]) -> bytes:
    return b'\n'.join(json.dumps(o, separators=(',', ':')).encode() for o in objs)


def _group_entry(name: str, parent: str = 'MissionGroup') -> dict:
    return {'class': 'SimGroup', 'name': name,
            'persistentId': _uid(), '__parent': parent}


def _items_with_parent(objs: list[dict], parent: str) -> bytes:
    tagged = [{**o, '__parent': parent} for o in objs]
    return _ndjson(tagged)


# ─────────────────────────────────────────────────────────────────────────────
# Satellite imagery
# ─────────────────────────────────────────────────────────────────────────────

_TILE_PX    = 256
_TILE_CACHE = ROOT / 'data' / 'tiles' / 'esri'
_ESRI_URL   = ('https://server.arcgisonline.com/ArcGIS/rest/services'
               '/World_Imagery/MapServer/tile/{z}/{y}/{x}')


def _deg2tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    n = 2 ** zoom
    tx = int((lon + 180.0) / 360.0 * n)
    ty = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return tx, ty


def _tile_lon_left(tx: int, zoom: int) -> float:
    return tx / (2 ** zoom) * 360.0 - 180.0


def _tile_merc_top(ty: int, zoom: int) -> float:
    return math.pi * (1.0 - 2.0 * ty / 2 ** zoom)


def _merc_y(lat: float) -> float:
    return math.asinh(math.tan(math.radians(lat)))


def _download_tile(tx: int, ty: int, zoom: int) -> Optional[np.ndarray]:
    cache = _TILE_CACHE / str(zoom) / str(ty) / f'{tx}.jpg'
    if cache.exists():
        data = cache.read_bytes()
    else:
        url = _ESRI_URL.format(z=zoom, y=ty, x=tx)
        for attempt in range(4):
            try:
                req = urllib.request.Request(
                    url, headers={'User-Agent': 'felsted-ng-drive/3.0'})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                time.sleep(0.08)
                break
            except Exception as exc:
                log.warning('Tile %d/%d/%d attempt %d: %s', zoom, ty, tx, attempt, exc)
                time.sleep(1.5 * (attempt + 1))
        else:
            return None
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    try:
        img = Image.open(io.BytesIO(data)).convert('RGB')
        return np.asarray(img, dtype=np.uint8)
    except Exception as exc:
        log.warning('Tile decode %d/%d/%d: %s', zoom, ty, tx, exc)
        return None


def _write_png_rgb(arr: np.ndarray) -> bytes:
    """Encode uint8 (H, W, 3) array as PNG bytes using stdlib only."""
    h, w, _ = arr.shape
    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (struct.pack('>I', len(data)) + payload
                + struct.pack('>I', zlib.crc32(payload) & 0xFFFFFFFF))
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    raw  = b''.join(b'\x00' + row.tobytes() for row in arr)
    idat = chunk(b'IDAT', zlib.compress(raw, 6))
    iend = chunk(b'IEND', b'')
    return b'\x89PNG\r\n\x1a\n' + ihdr + idat + iend


def build_satellite(zoom: int = 17, out_size: int = 4096) -> bytes:
    """
    Download ESRI WorldImagery tiles for the mapng world extent and return
    a stitched, cropped, resized satellite PNG as bytes.

    zoom=17 → ~0.74 m/px at 51.86°N   (default, ~30 tiles, fast)
    zoom=18 → ~0.37 m/px              (higher quality, ~4× tiles)
    """
    # World GPS bbox
    def w2gps(wx, wy):
        return _MAPNG_LAT + wy / _LAT_M, _MAPNG_LON + wx / _LON_M

    lat_n, lon_w = w2gps(-_WORLD_HALF,  _WORLD_HALF)
    lat_s, lon_e = w2gps( _WORLD_HALF, -_WORLD_HALF)

    tx_nw, ty_nw = _deg2tile(lat_n, lon_w, zoom)
    tx_se, ty_se = _deg2tile(lat_s, lon_e, zoom)
    tx_min, tx_max = min(tx_nw, tx_se), max(tx_nw, tx_se)
    ty_min, ty_max = min(ty_nw, ty_se), max(ty_nw, ty_se)
    n_x, n_y = tx_max - tx_min + 1, ty_max - ty_min + 1
    log.info('Satellite: %d×%d = %d tiles at zoom %d', n_x, n_y, n_x * n_y, zoom)

    canvas_h = n_y * _TILE_PX
    canvas_w = n_x * _TILE_PX
    canvas = np.full((canvas_h, canvas_w, 3), 64, dtype=np.uint8)

    total = n_x * n_y
    done  = 0
    for iy, ty in enumerate(range(ty_min, ty_max + 1)):
        for ix, tx in enumerate(range(tx_min, tx_max + 1)):
            tile = _download_tile(tx, ty, zoom)
            if tile is not None:
                r0, c0 = iy * _TILE_PX, ix * _TILE_PX
                canvas[r0:r0+_TILE_PX, c0:c0+_TILE_PX] = tile[:_TILE_PX, :_TILE_PX]
                done += 1
        if (iy + 1) % 5 == 0 or iy == n_y - 1:
            log.info('  row %d/%d  (%d/%d tiles)', iy + 1, n_y, done, total)

    # Crop to exact GPS bbox
    def gps_to_px(lat, lon):
        lon_l = _tile_lon_left(tx_min, zoom)
        lon_r = _tile_lon_left(tx_max + 1, zoom)
        col   = int((lon - lon_l) / (lon_r - lon_l) * canvas_w)
        mt    = _tile_merc_top(ty_min, zoom)
        mb    = _tile_merc_top(ty_max + 1, zoom)
        row   = int((mt - _merc_y(lat)) / (mt - mb) * canvas_h)
        return max(0, min(canvas_h-1, row)), max(0, min(canvas_w-1, col))

    rn, cw = gps_to_px(lat_n, lon_w)
    rs, ce = gps_to_px(lat_s, lon_e)
    rn, rs = min(rn, rs), max(rn, rs)
    cw, ce = min(cw, ce), max(cw, ce)
    cropped = canvas[rn:rs+1, cw:ce+1]
    log.info('Cropped to %d×%d px', cropped.shape[1], cropped.shape[0])

    # Resize to out_size × out_size
    from scipy.ndimage import zoom as spzoom
    if cropped.shape[0] < 2 or cropped.shape[1] < 2:
        log.error('Crop too small — check tile download')
        resized = np.full((out_size, out_size, 3), 80, dtype=np.uint8)
    else:
        fh = out_size / cropped.shape[0]
        fw = out_size / cropped.shape[1]
        channels = [
            np.clip(spzoom(cropped[:, :, c].astype(np.float32), (fh, fw), order=1),
                    0, 255)
            for c in range(3)
        ]
        resized = np.stack(channels, axis=2).astype(np.uint8)

    log.info('Satellite texture ready (%d×%d)', out_size, out_size)
    return _write_png_rgb(resized)


def _patch_terrain_material(mat_json_bytes: bytes) -> bytes:
    """
    Update the DefaultMaterial in main.materials.json to use the satellite
    PNG as its base colour texture, tiled once over the 2048 m world.
    """
    mats = json.loads(mat_json_bytes)
    for key, val in mats.items():
        if val.get('class') == 'TerrainMaterial' and \
                'DefaultMaterial' in val.get('internalName', ''):
            val['baseColorBaseTex']     = '/levels/Felsted/art/terrain/satellite/satellite.png'
            val['baseColorBaseTexSize'] = 2048
            # Zero out detail / macro blending so the aerial image shows cleanly
            val['baseColorDetailStrength'] = [0, 0]
            val['baseColorMacroStrength']  = [0, 0]
            log.info('Patched terrain material: %s', key)
            break
    return json.dumps(mats, indent=2).encode()


# ─────────────────────────────────────────────────────────────────────────────
# Main enrichment
# ─────────────────────────────────────────────────────────────────────────────

def _local_image_to_terrain_png(src: Path, out_size: int = 4096) -> bytes:
    """Resize any local image to out_size×out_size RGB PNG for terrain drape."""
    img = Image.open(src).convert('RGB')
    img = img.resize((out_size, out_size), Image.LANCZOS)
    log.info('Terrain photo: %s → %d×%d', src.name, out_size, out_size)
    return _write_png_rgb(np.array(img, dtype=np.uint8))


def enrich(input_zip: Path, output_zip: Path, osm_path: Path,
           satellite: bool = False, sat_zoom: int = 17,
           archive_root: Optional[Path] = None,
           terrain_photo: Optional[Path] = None) -> None:
    log.info('Reading %s', input_zip)
    with zipfile.ZipFile(input_zip, 'r') as zf:
        png_bytes = zf.read('levels/Felsted/theTerrain.terrainheightmap.png')
        calib_pts = _collect_calib(zf)
        source_names = zf.namelist()
        source_data  = {n: zf.read(n) for n in source_names}

    # ── Heightmap calibration ─────────────────────────────────────────────────
    hm   = _load_hm(png_bytes)
    maxh = _calibrate(hm, calib_pts)
    elev = _elev_fn(hm, maxh)

    # ── Generate content ──────────────────────────────────────────────────────
    log.info('Loading OSM data from %s', osm_path)
    osm = _load_osm(osm_path)

    bld_objects, bld_daes = gen_buildings(osm, elev)
    rail_objects           = gen_railway(elev)
    water_objects          = gen_water(osm, elev)
    path_objects           = gen_paths(osm, elev)
    forest_objects         = gen_forest(osm, elev)

    photo_objects, photo_daes, photo_blobs = [], {}, {}
    if archive_root is not None:
        photo_objects, photo_daes, photo_blobs = gen_photos(archive_root, elev)

    # ── Terrain texture (satellite download or local photo) ───────────────────
    sat_png_bytes = None
    if terrain_photo is not None:
        log.info('Step: using local terrain photo: %s', terrain_photo)
        sat_png_bytes = _local_image_to_terrain_png(terrain_photo)
    elif satellite:
        log.info('Step: downloading satellite tiles (zoom=%d)…', sat_zoom)
        sat_png_bytes = build_satellite(zoom=sat_zoom)

    # ── Read existing MissionGroup items ──────────────────────────────────────
    mg_path = 'levels/Felsted/main/MissionGroup/items.level.json'
    mg_lines = source_data[mg_path].decode().strip().split('\n')

    # Append new SimGroup entries for each new group
    new_groups = ['Buildings', 'Railway', 'OSM_Water', 'OSM_Paths', 'OSM_Forest']
    if photo_objects:
        new_groups.append('Photos')
    for g in new_groups:
        mg_lines.append(json.dumps(_group_entry(g), separators=(',', ':')))

    # ── Assemble new zip ──────────────────────────────────────────────────────
    mat_path = 'levels/Felsted/art/terrains/main.materials.json'
    log.info('Writing %s', output_zip)
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Copy all original files, patching where needed
        for name, data in source_data.items():
            if name == mg_path:
                zf.writestr(name, '\n'.join(mg_lines))
            elif name == mat_path and sat_png_bytes:
                zf.writestr(name, _patch_terrain_material(data))
            else:
                zf.writestr(name, data)

        # Satellite PNG + flat normal map
        if sat_png_bytes:
            zf.writestr('levels/Felsted/art/terrain/satellite/satellite.png',
                        sat_png_bytes)
            flat = np.full((4, 4, 3), (128, 128, 255), dtype=np.uint8)
            zf.writestr('levels/Felsted/art/terrain/satellite/flat_n.png',
                        _write_png_rgb(flat))
            log.info('  satellite texture : 4096×4096 px, zoom=%d', sat_zoom)

        base = 'levels/Felsted/main/MissionGroup'

        # Buildings
        if bld_objects:
            zf.writestr(f'{base}/Buildings/items.level.json',
                        _items_with_parent(bld_objects, 'Buildings'))
            for dae_path, dae_xml in bld_daes.items():
                zf.writestr(dae_path, dae_xml)

        # Railway
        if rail_objects:
            zf.writestr(f'{base}/Railway/items.level.json',
                        _items_with_parent(rail_objects, 'Railway'))

        # Water
        if water_objects:
            zf.writestr(f'{base}/OSM_Water/items.level.json',
                        _items_with_parent(water_objects, 'OSM_Water'))

        # Paths
        if path_objects:
            zf.writestr(f'{base}/OSM_Paths/items.level.json',
                        _items_with_parent(path_objects, 'OSM_Paths'))

        # Forest
        if forest_objects:
            # Forest contains nested SimGroups; write children with correct __parent
            forest_items = []
            for fg in forest_objects:
                fg_item = {k: v for k, v in fg.items() if k != 'children'}
                fg_item['__parent'] = 'OSM_Forest'
                forest_items.append(fg_item)
                for child in fg.get('children', []):
                    forest_items.append({**child, '__parent': fg['name']})
            zf.writestr(f'{base}/OSM_Forest/items.level.json',
                        _ndjson(forest_items))

        # Photos — billboard DAEs + bundled image files
        if photo_objects:
            zf.writestr(f'{base}/Photos/items.level.json',
                        _items_with_parent(photo_objects, 'Photos'))
            for dae_path, dae_xml in photo_daes.items():
                zf.writestr(dae_path, dae_xml)
            for blob_path, blob_data in photo_blobs.items():
                zf.writestr(blob_path, blob_data)

    size_mb = output_zip.stat().st_size / 1_048_576
    log.info('Done — %s  (%.1f MB)', output_zip.name, size_mb)
    log.info('  buildings : %d meshes + DAEs', len(bld_objects))
    log.info('  railway   : %d objects', len(rail_objects))
    log.info('  water     : %d objects', len(water_objects))
    log.info('  paths     : %d footways/bridleways', len(path_objects))
    log.info('  forest    : %d woodland groups', len(forest_objects))
    log.info('  photos    : %d billboards', len(photo_objects))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description='Enrich Felsted mapng zip with OSM detail')
    ap.add_argument('--input',  default=str(ROOT / 'Felsted.zip'),
                    help='Source mapng zip (default: Felsted.zip)')
    ap.add_argument('--output', default=str(ROOT / 'Felsted_enriched.zip'),
                    help='Output zip (default: Felsted_enriched.zip)')
    ap.add_argument('--osm',       default=str(ROOT / 'data' / 'felsted_osm.json'),
                    help='OSM JSON cache')
    ap.add_argument('--satellite', action='store_true',
                    help='Download ESRI WorldImagery and drape over terrain')
    ap.add_argument('--zoom',      type=int, default=17,
                    help='Tile zoom level (17=0.74m/px, 18=0.37m/px, default 17)')
    ap.add_argument('--photos',        default=None,
                    help='Path to felsted-archive root (contains data/archive.db); '
                         'embeds geolocated photos as in-world billboards')
    ap.add_argument('--terrain-photo', default=None,
                    help='Local image to drape over terrain instead of downloading '
                         'satellite tiles (e.g. a historical aerial photograph)')
    args = ap.parse_args()
    archive      = Path(args.photos)        if args.photos        else None
    terrain_img  = Path(args.terrain_photo) if args.terrain_photo else None
    enrich(Path(args.input), Path(args.output), Path(args.osm),
           satellite=args.satellite, sat_zoom=args.zoom,
           archive_root=archive, terrain_photo=terrain_img)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s  %(levelname)-7s  %(message)s',
                        datefmt='%H:%M:%S')
    main()

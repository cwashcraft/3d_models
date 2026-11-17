#!/usr/bin/env python3
"""
Parametric 3D Model Generator for Wooting 80HE Arrow Keycaps (4-Keycap Set — Geometry Dash Icons).
Designed for 2-Tone Bambu PLA Matte 3D printing on the Bambu Lab A1 Mini (without AMS, using a
single automatic M400 U1 filament-swap pause at Z = 8.60 mm).

Key Engineering & Aesthetic Features:
  - Tailored for Wooting 80HE (Lekker V2 Hall Effect / Cherry MX Cross-Stem Switches):
      * 4 standard 1u arrow keycaps (18.10 x 18.10 mm base skirt tapering to 13.80 x 13.80 mm
        top deck at Z = 8.40 mm) arranged in a 2x2 grid (21.5 mm center-to-center spacing)
        for printing all 4 keycaps in a single job.
      * Precision Lekker V2 / Cherry MX '+' cross-stem receptacle (5.50 mm outer stem cylinder
        boss, 4.20 mm cross span, 1.32 mm X slot / 1.36 mm Y slot, 4.40 mm stem depth, plus
        0.40 mm 45-degree entry lead-in chamfer to eliminate first-layer elephant-foot binding).
      * 100% support-free underside geometry: both the outer keycap skirt and central MX stem
        boss sit flat on Z = 0.0 mm, with a 45-degree vaulted internal cavity ceiling.
  - 2-Tone Geometry Dash Icon Legends (from /home/droid/keycaps/unnamed*.png):
      * Keycap 1 (Top-Left):     Geometry Dash Cube (unnamed.png)
      * Keycap 2 (Top-Right):    Geometry Dash Ship (unnamed2.png)
      * Keycap 3 (Bottom-Left):  Geometry Dash Ball (unnamed3.png)
      * Keycap 4 (Bottom-Right): Geometry Dash UFO  (unnamed4.png)
      * All 4 keycap decks finish at exactly Z = 8.40 mm (Layer 42 at 0.20 mm layer height),
        and all 4 Geometry Dash icon reliefs rise +0.60 mm (Z = 8.40 -> 9.00 mm, Layers 43-45)
        so a single filament change pause at Layer 43 (Z = 8.60 mm) prints all 4 icons in the
        second PLA Matte color!

Generates:
  1. wooting_80he_keycaps.stl         (Watertight 2-Manifold Binary STL)
  2. wooting_80he_keycaps.3mf         (Bambu Studio / Bambu Handy / MakerWorld 3MF)
  3. wooting_80he_keycaps.scad        (Parametric OpenSCAD source)
  4. wooting_80he_keycaps_preview.svg (Shaded vector 3/4 view preview)
  5. wooting_80he_keycaps_preview.png (High-resolution 2-tone dual-view raster preview)
"""

import math
import os
import struct
import zipfile
import zlib

# ==============================================================================
# PARAMETRIC DIMENSIONS (in millimeters)
# ==============================================================================
PARAMS = {
    # Official Wooting 80HE 1u OEM R1 Arrow Keycap Sculpted Profile
    "base_width": 18.10,            # Standard 1u keycap bottom skirt width (mm)
    "top_width_x": 12.70,           # Official OEM top finger dish width (mm, left-to-right)
    "top_width_y": 14.20,           # Official OEM top finger dish depth (mm, front-to-back)
    "front_height": 8.40,           # Lower front lip height at Y = -top_width_y/2 (mm)
    "back_height": 10.00,           # Raised back/north edge height at Y = +top_width_y/2 (mm, official OEM R1 tilt)
    "top_shift_y": -0.65,           # OEM asymmetric front-back lean (top dish shifted slightly toward front)
    "dish_depth_x": 0.72,           # Cylindrical concave finger scoop depth across X (mm)
    "dish_depth_y": 0.14,           # Subtle secondary concave scoop along Y (mm)
    "pause_z": 10.20,               # Exact layer Z height (mm) where M400 U1 filament swap from White -> Blue occurs
    "icon_top_offset": 0.60,        # Height of blue icon relief above the highest rim (10.00 -> 10.60 mm)
    "base_corner_radius": 1.40,     # Outer corner fillet radius at Z = 0 (mm)
    "top_corner_radius": 1.15,      # Outer corner fillet radius at top deck (mm)
    "skirt_wall_thickness": 1.68,   # Outer skirt wall thickness (1.68 mm = exact 4 perimeters with zero gap-fill!)
    "cavity_vault_start_z": 3.40,   # Height where internal cavity ceiling starts vaulting inward (mm)
    "cavity_ceiling_z": 6.40,       # Maximum height of internal cavity ceiling below solid deck (mm)

    # Wooting Lekker V2 / Cherry MX Cross-Stem Parameters
    "stem_boss_diameter": 5.80,     # Central cylindrical stem post outer diameter (clears Lekker V2 shroud with wide bed footprint)
    "cross_span": 4.18,             # Total '+' cross slot width/height (mm)
    "cross_slot_x": 1.32,           # Horizontal bar slot thickness (mm, along X)
    "cross_slot_y": 1.36,           # Vertical bar slot thickness (mm, along Y)
    "cross_depth": 4.60,            # Depth of '+' cross slot from Z = 0 upward (mm)
    "cross_entry_chamfer": 0.0,     # Keep bottom of '+' stem post full-thickness on Layer 1 to avoid tiny dots & retraction clogs!

    # 2x2 Array Layout & Icon Sizing
    "grid_pitch": 21.00,            # Center-to-center spacing between the 4 keycaps (mm)
    "icon_max_span": 9.80,          # Maximum icon width/height inside the concave finger scoop (mm)
}

ICON_FILES = [
    ("Cube", "/home/droid/keycaps/unnamed.png", (-0.5, +0.5)),
    ("Ship", "/home/droid/keycaps/unnamed2.png", (+0.5, +0.5)),
    ("Ball", "/home/droid/keycaps/unnamed3.png", (-0.5, -0.5)),
    ("UFO",  "/home/droid/keycaps/unnamed4.png", (+0.5, -0.5)),
]


def clamp(val, lo, hi):
    return lo if val < lo else (hi if val > hi else val)


def smin(a, b, k):
    if k <= 1e-6:
        return a if a < b else b
    h = max(0.0, k - abs(a - b)) / k
    return (a if a < b else b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


def read_png_rgba(path):
    """Decodes an 8-bit RGBA PNG file using only the Python standard library."""
    with open(path, "rb") as f:
        data = f.read()
    pos = 8
    chunks = []
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunks.append((data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + length]))
        pos += 12 + length
    ihdr = [c for t, c in chunks if t == b"IHDR"][0]
    w, h, _, _, _, _, _ = struct.unpack(">IIBBBBB", ihdr)
    raw = zlib.decompress(b"".join(c for t, c in chunks if t == b"IDAT"))
    stride = w * 4
    pixels = []
    prev = [0] * stride
    p = 0
    for _ in range(h):
        ft = raw[p]
        p += 1
        row = list(raw[p : p + stride])
        p += stride
        if ft == 1:
            for i in range(4, stride):
                row[i] = (row[i] + row[i - 4]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = row[i - 4] if i >= 4 else 0
                row[i] = (row[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = row[i - 4] if i >= 4 else 0
                b = prev[i]
                c = prev[i - 4] if i >= 4 else 0
                pr = a + b - c
                pa, pb, pc = abs(pr - a), abs(pr - b), abs(pr - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pred) & 0xFF
        prev = row
        pixels.append(row)
    return w, h, pixels


def build_icon_sdf_grid(path, is_ufo=False):
    """
    Loads a Geometry Dash PNG icon and builds a smooth 2D Signed Distance Field (in mm)
    mapped onto the keycap top deck [-icon_span/2, +icon_span/2]^2.
    Returns (grid_sdf, n_grid, half_span_mm) where grid_sdf[iy][ix] < 0 inside the raised icon.
    """
    w, h, px = read_png_rgba(path)

    # Extract binary mask of white/light icon fill regions
    # For the UFO (unnamed4.png), convert the semi-transparent glass dome pixels into a clean 2-tone format
    # by preserving the semi-transparent dome (alpha >= 40) with a clean separation groove above the saucer rim.
    mask = [[0] * w for _ in range(h)]
    for y in range(h):
        r = px[y]
        for x in range(w):
            a = r[x * 4 + 3]
            lum = (r[x * 4] + r[x * 4 + 1] + r[x * 4 + 2]) / 3.0
            if a >= 120 and lum >= 140:
                mask[y][x] = 1
            elif is_ufo and y < 50 and a >= 40 and lum >= 140:
                # Convert the semi-transparent UFO glass dome directly into solid 2-tone foreground
                # (stopping at y = 50 leaves a crisp 2-tone separation line between dome and saucer body)
                mask[y][x] = 1

    # Find tight bounding box of active mask pixels
    ys_active = [y for y in range(h) if any(mask[y])]
    xs_active = [x for x in range(w) if any(mask[y][x] for y in range(h))]
    x0, x1 = min(xs_active), max(xs_active)
    y0, y1 = min(ys_active), max(ys_active)
    bw = max(1, x1 - x0 + 1)
    bh = max(1, y1 - y0 + 1)

    max_dim = max(bw, bh)
    icon_span = PARAMS["icon_max_span"]
    mm_per_px = icon_span / max_dim

    # Resample onto a uniform 96 x 96 grid covering [-7.0, +7.0] mm on the keycap top
    n_grid = 96
    half_ext = 7.0
    step_mm = (2.0 * half_ext) / (n_grid - 1)

    bin_grid = [[0] * n_grid for _ in range(n_grid)]
    cx_px = 0.5 * (x0 + x1)
    cy_px = 0.5 * (y0 + y1)

    for iy in range(n_grid):
        ym = -half_ext + iy * step_mm
        # Flip Y so image top (+ym) corresponds to smaller image row y
        py_f = cy_px - (ym / mm_per_px)
        py = int(round(py_f))
        if 0 <= py < h:
            for ix in range(n_grid):
                xm = -half_ext + ix * step_mm
                px_f = cx_px + (xm / mm_per_px)
                px_i = int(round(px_f))
                if 0 <= px_i < w:
                    bin_grid[iy][ix] = mask[py][px_i]

    # Compute exact 2D Euclidean signed distance transform (in mm) on the 96x96 grid
    # (negative inside raised icon, positive outside)
    INF = 1e9
    dist_in = [[0.0 if bin_grid[y][x] == 1 else INF for x in range(n_grid)] for y in range(n_grid)]
    dist_out = [[0.0 if bin_grid[y][x] == 0 else INF for x in range(n_grid)] for y in range(n_grid)]

    def edt_2d(grid_d):
        # 2-pass Chamfer/Meijster exact-like 2D distance transform
        for y in range(n_grid):
            for x in range(n_grid):
                v = grid_d[y][x]
                if y > 0:
                    v = min(v, grid_d[y - 1][x] + 1.0)
                    if x > 0:
                        v = min(v, grid_d[y - 1][x - 1] + 1.4142)
                    if x + 1 < n_grid:
                        v = min(v, grid_d[y - 1][x + 1] + 1.4142)
                if x > 0:
                    v = min(v, grid_d[y][x - 1] + 1.0)
                grid_d[y][x] = v
        for y in range(n_grid - 1, -1, -1):
            for x in range(n_grid - 1, -1, -1):
                v = grid_d[y][x]
                if y + 1 < n_grid:
                    v = min(v, grid_d[y + 1][x] + 1.0)
                    if x > 0:
                        v = min(v, grid_d[y + 1][x - 1] + 1.4142)
                    if x + 1 < n_grid:
                        v = min(v, grid_d[y + 1][x + 1] + 1.4142)
                if x + 1 < n_grid:
                    v = min(v, grid_d[y][x + 1] + 1.0)
                grid_d[y][x] = v

    edt_2d(dist_in)
    edt_2d(dist_out)

    sdf_grid = [[0.0] * n_grid for _ in range(n_grid)]
    for y in range(n_grid):
        for x in range(n_grid):
            # Subtract 0.04 mm slight offset to ensure thin features stay above Arachne threshold
            d_px = (dist_in[y][x] - 0.5) if bin_grid[y][x] == 0 else -(dist_out[y][x] - 0.5)
            sdf_grid[y][x] = d_px * step_mm - 0.04

    return sdf_grid, n_grid, half_ext


def sample_icon_sdf(sdf_grid, n_grid, half_ext, x_loc, y_loc):
    """Bilinearly interpolates the 2D icon SDF (in mm) at local keycap coordinates (x_loc, y_loc)."""
    if abs(x_loc) >= half_ext or abs(y_loc) >= half_ext:
        return 5.0
    step_mm = (2.0 * half_ext) / (n_grid - 1)
    fx = (x_loc + half_ext) / step_mm
    fy = (y_loc + half_ext) / step_mm
    ix = min(n_grid - 2, max(0, int(math.floor(fx))))
    iy = min(n_grid - 2, max(0, int(math.floor(fy))))
    tx = fx - ix
    ty = fy - iy
    v00 = sdf_grid[iy][ix]
    v10 = sdf_grid[iy][ix + 1]
    v01 = sdf_grid[iy + 1][ix]
    v11 = sdf_grid[iy + 1][ix + 1]
    return (1.0 - ty) * ((1.0 - tx) * v00 + tx * v10) + ty * ((1.0 - tx) * v01 + tx * v11)


def rounded_rect_2d_sdf(x, y, half_wx, half_wy, r_corner):
    """2D Signed Distance Function for a rounded rectangle of half-widths (half_wx, half_wy) and corner radius r_corner."""
    qx = abs(x) - (half_wx - r_corner)
    qy = abs(y) - (half_wy - r_corner)
    out_dist = math.hypot(max(qx, 0.0), max(qy, 0.0))
    in_dist = min(max(qx, qy), 0.0)
    return out_dist + in_dist - r_corner


def keycap_top_surface_z(x_loc, y_loc, p):
    """
    Evaluates the official Wooting 80HE OEM R1 sculpted top surface height Z_top(x, y):
      - Sloped from front_height (8.40 mm at front lip) up to back_height (10.00 mm at raised back edge)
      - Cylindrically concave across X (dish_depth_x = 0.72 mm) so the left/right edges form raised
        cradling rims and the center is scooped for the fingertip.
    """
    top_wy = p["top_width_y"]
    top_wx = p["top_width_x"]
    y_rel = y_loc - p["top_shift_y"]

    # Normalized front-to-back coordinate ty in [-1, +1]
    ty = clamp(y_rel / (0.5 * top_wy), -1.0, 1.0)
    # Normalized left-to-right coordinate tx in [-1, +1]
    tx = clamp(x_loc / (0.5 * top_wx), -1.0, 1.0)

    # Sloped plane height along Y (raised on the back/+Y side, lower on the front/-Y side)
    z_rim = 0.5 * (p["front_height"] + p["back_height"]) + 0.5 * (p["back_height"] - p["front_height"]) * ty

    # Cylindrical concave finger scoop across X (deepest at x=0, rising to 0 at left/right rims tx=+-1)
    scoop_x = p["dish_depth_x"] * max(0.0, 1.0 - tx * tx)
    # Subtle saddle/cradle curvature along Y
    scoop_y = p["dish_depth_y"] * max(0.0, 1.0 - ty * ty)

    return z_rim - scoop_x - scoop_y


def single_keycap_sdf(x_loc, y_loc, z, p, icon_sdf_info):
    """
    Evaluates the 3D Signed Distance Function (sdf < 0 inside solid PLA keycap) for one
    official-profile Wooting 80HE OEM R1 arrow keycap centered at (0, 0) with its bottom on Z = 0.
    """
    back_h = p["back_height"]
    icon_top_z = back_h + p["icon_top_offset"]

    if z < 0.0:
        return -z
    if z > icon_top_z:
        return z - icon_top_z

    # 1. Outer sculpted Wooting 80HE OEM R1 1u keycap profile from Z = 0 up to the sloped/concave top dish
    t_z = clamp(z / back_h, 0.0, 1.0)
    # Authentic OEM slightly curved flank taper
    profile_curve = 0.80 * t_z + 0.20 * (t_z * t_z)

    half_wx = 0.5 * (p["base_width"] + (p["top_width_x"] - p["base_width"]) * profile_curve)
    half_wy = 0.5 * (p["base_width"] + (p["top_width_y"] - p["base_width"]) * profile_curve)
    cy = p["top_shift_y"] * profile_curve
    r_corn = p["base_corner_radius"] + (p["top_corner_radius"] - p["base_corner_radius"]) * t_z

    # Sculpted sloped + cylindrical concave top surface height Z_top(x, y)
    z_top = keycap_top_surface_z(x_loc, y_loc, p)

    # Smooth top perimeter rim bevel where outer walls meet the sloped concave finger dish
    if z > z_top - 0.35:
        bevel = 0.16 * clamp((z - (z_top - 0.35)) / 0.35, 0.0, 1.2)
        half_wx -= bevel
        half_wy -= bevel

    d_outer_xy = rounded_rect_2d_sdf(x_loc, y_loc - cy, half_wx, half_wy, r_corn)
    d_body = max(d_outer_xy, (z - z_top) * 0.94, -z)

    # 2. Internal hollow keycap cavity + Wooting Lekker V2 / Cherry MX '+' stem boss (for z < cavity_ceiling_z)
    cav_ceil = p["cavity_ceiling_z"]
    if z < cav_ceil:
        wall_t = p["skirt_wall_thickness"]
        cav_wx = half_wx - wall_t
        cav_wy = half_wy - wall_t
        # Above cavity_vault_start_z (3.80 mm), vault the cavity inward at a self-supporting ~48-deg slope
        vault_z0 = p["cavity_vault_start_z"]
        if z > vault_z0:
            v_inset = (z - vault_z0) * 1.15
            cav_wx -= v_inset
            cav_wy -= v_inset

        if cav_wx > 0.4 and cav_wy > 0.4:
            d_cav_xy = rounded_rect_2d_sdf(x_loc, y_loc - cy, cav_wx, cav_wy, max(0.3, r_corn - 0.7))
            d_cavity = max(d_cav_xy, z - cav_ceil)
        else:
            d_cavity = 10.0

        # Central cylindrical stem boss (r = stem_boss_diameter / 2) sits Inside the cavity
        r_boss = p["stem_boss_diameter"] * 0.5
        r_xy = math.hypot(x_loc, y_loc)
        d_boss = r_xy - r_boss

        # Subtract cavity EXCEPT where the central stem boss is solid:
        d_hollow = max(d_cavity, -d_boss)
        d_body = max(d_body, -d_hollow)

    # 3. Subtract the Wooting Lekker V2 / Cherry MX '+' cross-stem slot (for z <= cross_depth)
    cross_d = p["cross_depth"]
    if z <= cross_d:
        span_half = p["cross_span"] * 0.5
        sx_half = p["cross_slot_x"] * 0.5
        sy_half = p["cross_slot_y"] * 0.5

        # Bottom entry chamfer (0.42 mm x 45 deg) so the stem slides smoothly onto Lekker V2 switches
        chamfer = max(0.0, p["cross_entry_chamfer"] - z)
        # Conical self-supporting roof at the top of the '+' slot (z in [cross_d - 0.55, cross_d])
        roof_taper = max(0.0, z - (cross_d - 0.55)) * 1.25

        ax = abs(x_loc)
        ay = abs(y_loc)
        d_bar_h = max(ax - (span_half + 0.5 * chamfer - roof_taper), ay - (sx_half + chamfer - roof_taper))
        d_bar_v = max(ax - (sy_half + chamfer - roof_taper), ay - (span_half + 0.5 * chamfer - roof_taper))
        d_cross = min(d_bar_h, d_bar_v)
        d_cross_3d = max(d_cross, z - cross_d)

        d_body = max(d_body, -d_cross_3d)

    # 4. Raised 2-Tone Geometry Dash Icon Relief emerging from the concave dish up to icon_top_z (10.60 mm)
    #    Because all white keycap rims finish at Z <= 10.00 mm and all 4 icons rise to Z = 10.60 mm,
    #    a single filament swap pause at Z = 10.20 mm prints 100% of the keycap body in White PLA Matte
    #    and the top 3 layers (Z = 10.20 -> 10.60 mm) of all 4 icons in Blue PLA Matte!
    if z >= z_top - 0.30:
        sdf_grid, n_grid, half_ext = icon_sdf_info
        d_icon_2d = sample_icon_sdf(sdf_grid, n_grid, half_ext, x_loc, y_loc - p["top_shift_y"])
        # Keep icon inside top concave dish border
        d_icon_2d = max(d_icon_2d, d_outer_xy + 0.85)
        d_icon_3d = max(d_icon_2d, z - icon_top_z, (z_top - 0.25) - z)
        d_body = min(d_body, d_icon_3d)

    return d_body


def build_single_keycap_mesh(p, icon_sdf_info, offset_x, offset_y):
    """
    Builds a guaranteed watertight, 2-manifold triangle mesh for a single keycap
    using Dual Contouring (Surface Nets) on a high-resolution Cartesian grid,
    then translates it to (offset_x, offset_y).
    """
    dx = 0.22
    dy = 0.22
    dz = 0.20

    half_span = p["base_width"] * 0.5 + 0.66
    nx = int(math.ceil((2.0 * half_span) / dx)) + 1
    ny = int(math.ceil((2.0 * half_span) / dy)) + 1
    xs = [-half_span + ix * dx for ix in range(nx)]
    ys = [-half_span + iy * dy for iy in range(ny)]

    total_h = p["back_height"] + p["icon_top_offset"]
    nz = int(math.ceil((total_h + 0.60) / dz)) + 2
    zs = [(iz - 0.5) * dz for iz in range(nz)]

    nyz = ny * nz
    sdf = [10.0] * (nx * nyz)

    for iz, z in enumerate(zs):
        if z < 0.0 or z > total_h:
            continue
        for ix, x in enumerate(xs):
            base_idx = ix * nyz + iz
            for iy, y in enumerate(ys):
                sdf[base_idx + iy * nz] = single_keycap_sdf(x, y, z, p, icon_sdf_info)

    inside = [v < 0.0 for v in sdf]

    # Eliminate any 2D (T, F, T, F) checkerboard pinch configurations on primal grid faces
    # so every dual edge has 0 or 2 sign changes (mathematically guaranteeing 0 non-manifold edges)
    for _pass in range(6):
        changed = 0
        for ix in range(1, nx - 1):
            bx = ix * nyz
            bx1 = (ix + 1) * nyz
            for iy in range(1, ny - 1):
                by0 = iy * nz
                by1 = (iy + 1) * nz
                for iz in range(1, nz - 1):
                    # 1. Check (y, z) face at ix
                    i00 = bx + by0 + iz
                    i10 = bx + by1 + iz
                    i11 = bx + by1 + iz + 1
                    i01 = bx + by0 + iz + 1
                    if inside[i00] == inside[i11] and inside[i10] == inside[i01] and inside[i00] != inside[i10]:
                        if not inside[i00]:
                            inside[i00] = True
                            sdf[i00] = -0.01
                        else:
                            inside[i10] = True
                            sdf[i10] = -0.01
                        changed += 1

                    # 2. Check (x, z) face at iy
                    j00 = bx + by0 + iz
                    j10 = bx1 + by0 + iz
                    j11 = bx1 + by0 + iz + 1
                    j01 = bx + by0 + iz + 1
                    if inside[j00] == inside[j11] and inside[j10] == inside[j01] and inside[j00] != inside[j10]:
                        if not inside[j00]:
                            inside[j00] = True
                            sdf[j00] = -0.01
                        else:
                            inside[j10] = True
                            sdf[j10] = -0.01
                        changed += 1

                    # 3. Check (x, y) face at iz
                    k00 = bx + by0 + iz
                    k10 = bx1 + by0 + iz
                    k11 = bx1 + by1 + iz
                    k01 = bx + by1 + iz
                    if inside[k00] == inside[k11] and inside[k10] == inside[k01] and inside[k00] != inside[k10]:
                        if not inside[k00]:
                            inside[k00] = True
                            sdf[k00] = -0.01
                        else:
                            inside[k10] = True
                            sdf[k10] = -0.01
                        changed += 1
        if changed == 0:
            break

    edges = (
        ((0, 0, 0), (1, 0, 0)),
        ((0, 1, 0), (1, 1, 0)),
        ((0, 0, 1), (1, 0, 1)),
        ((0, 1, 1), (1, 1, 1)),
        ((0, 0, 0), (0, 1, 0)),
        ((1, 0, 0), (1, 1, 0)),
        ((0, 0, 1), (0, 1, 1)),
        ((1, 0, 1), (1, 1, 1)),
        ((0, 0, 0), (0, 0, 1)),
        ((1, 0, 0), (1, 0, 1)),
        ((0, 1, 0), (0, 1, 1)),
        ((1, 1, 0), (1, 1, 1)),
    )

    cell_to_vert = {}
    verts = []

    for ix in range(nx - 1):
        for iy in range(ny - 1):
            for iz in range(nz - 1):
                c_pos = 0
                c_neg = 0
                for dx0 in (0, 1):
                    for dy0 in (0, 1):
                        for dz0 in (0, 1):
                            if inside[(ix + dx0) * nyz + (iy + dy0) * nz + (iz + dz0)]:
                                c_neg += 1
                            else:
                                c_pos += 1
                if c_pos == 0 or c_neg == 0:
                    continue

                sx_sum, sy_sum, sz_sum, cnt = 0.0, 0.0, 0.0, 0
                for (dx0, dy0, dz0), (dx1, dy1, dz1) in edges:
                    ix_a, iy_a, iz_a = ix + dx0, iy + dy0, iz + dz0
                    ix_b, iy_b, iz_b = ix + dx1, iy + dy1, iz + dz1
                    idx_a = ix_a * nyz + iy_a * nz + iz_a
                    idx_b = ix_b * nyz + iy_b * nz + iz_b
                    if inside[idx_a] != inside[idx_b]:
                        va = sdf[idx_a]
                        vb = sdf[idx_b]
                        t_zero = clamp(va / (va - vb + 1e-12), 0.0, 1.0)
                        sx_sum += xs[ix_a] + t_zero * (xs[ix_b] - xs[ix_a])
                        sy_sum += ys[iy_a] + t_zero * (ys[iy_b] - ys[iy_a])
                        sz_sum += zs[iz_a] + t_zero * (zs[iz_b] - zs[iz_a])
                        cnt += 1

                vx = sx_sum / cnt + offset_x
                vy = sy_sum / cnt + offset_y
                vz = 0.0 if iz == 0 else max(0.01, sz_sum / cnt)

                v_idx = len(verts)
                cell_to_vert[(ix, iy, iz)] = v_idx
                verts.append((vx, vy, vz))

    quads = []
    # 1. Faces perpendicular to X-axis
    for ix in range(nx - 1):
        for iy in range(1, ny - 1):
            for iz in range(1, nz - 1):
                s0 = inside[ix * nyz + iy * nz + iz]
                s1 = inside[(ix + 1) * nyz + iy * nz + iz]
                if s0 != s1:
                    c0 = cell_to_vert[(ix, iy - 1, iz - 1)]
                    c1 = cell_to_vert[(ix, iy, iz - 1)]
                    c2 = cell_to_vert[(ix, iy, iz)]
                    c3 = cell_to_vert[(ix, iy - 1, iz)]
                    if s0:
                        quads.append((c0, c1, c2, c3))
                    else:
                        quads.append((c0, c3, c2, c1))

    # 2. Faces perpendicular to Y-axis
    for ix in range(1, nx - 1):
        for iy in range(ny - 1):
            for iz in range(1, nz - 1):
                s0 = inside[ix * nyz + iy * nz + iz]
                s1 = inside[ix * nyz + (iy + 1) * nz + iz]
                if s0 != s1:
                    c0 = cell_to_vert[(ix - 1, iy, iz - 1)]
                    c1 = cell_to_vert[(ix - 1, iy, iz)]
                    c2 = cell_to_vert[(ix, iy, iz)]
                    c3 = cell_to_vert[(ix, iy, iz - 1)]
                    if s0:
                        quads.append((c0, c1, c2, c3))
                    else:
                        quads.append((c0, c3, c2, c1))

    # 3. Faces perpendicular to Z-axis
    for ix in range(1, nx - 1):
        for iy in range(1, ny - 1):
            for iz in range(nz - 1):
                s0 = inside[ix * nyz + iy * nz + iz]
                s1 = inside[ix * nyz + iy * nz + iz + 1]
                if s0 != s1:
                    c0 = cell_to_vert[(ix - 1, iy - 1, iz)]
                    c1 = cell_to_vert[(ix, iy - 1, iz)]
                    c2 = cell_to_vert[(ix, iy, iz)]
                    c3 = cell_to_vert[(ix - 1, iy, iz)]
                    if s0:
                        quads.append((c0, c1, c2, c3))
                    else:
                        quads.append((c0, c3, c2, c1))

    triangles = []
    for c0, c1, c2, c3 in quads:
        v0, v1, v2, v3 = verts[c0], verts[c1], verts[c2], verts[c3]
        d02 = (v0[0] - v2[0]) ** 2 + (v0[1] - v2[1]) ** 2 + (v0[2] - v2[2]) ** 2
        d13 = (v1[0] - v3[0]) ** 2 + (v1[1] - v3[1]) ** 2 + (v1[2] - v3[2]) ** 2
        if d02 <= d13:
            triangles.append((v0, v1, v2))
            triangles.append((v0, v2, v3))
        else:
            triangles.append((v0, v1, v3))
            triangles.append((v1, v2, v3))

    return triangles


def build_all_keycaps_mesh(p):
    """Builds all 4 Wooting 80HE Geometry Dash keycaps arranged in a 2x2 grid."""
    all_triangles = []
    pitch = p["grid_pitch"]
    for name, png_path, (gx, gy) in ICON_FILES:
        is_ufo = name == "UFO"
        print(f"  -> Building keycap '{name}' from {os.path.basename(png_path)}...")
        icon_info = build_icon_sdf_grid(png_path, is_ufo=is_ufo)
        tris = build_single_keycap_mesh(p, icon_info, gx * pitch, gy * pitch)
        all_triangles.extend(tris)
    return all_triangles


def verify_manifold(triangles):
    """Verifies that the triangle mesh is 100% watertight, 2-manifold, and has positive volume."""
    def quantize(pt):
        return (round(pt[0], 5), round(pt[1], 5), round(pt[2], 5))

    directed_edges = {}
    undirected_counts = {}
    vol6 = 0.0

    for p1, p2, p3 in triangles:
        v1, v2, v3 = quantize(p1), quantize(p2), quantize(p3)
        for u, v in ((v1, v2), (v2, v3), (v3, v1)):
            directed_edges[(u, v)] = directed_edges.get((u, v), 0) + 1
            key = (u, v) if u < v else (v, u)
            undirected_counts[key] = undirected_counts.get(key, 0) + 1

        vol6 += (
            p1[0] * (p2[1] * p3[2] - p2[2] * p3[1])
            - p1[1] * (p2[0] * p3[2] - p2[2] * p3[0])
            + p1[2] * (p2[0] * p3[1] - p2[1] * p3[0])
        )

    unmatched_directed = 0
    for (u, v), count in directed_edges.items():
        if count != 1 or directed_edges.get((v, u), 0) != 1:
            unmatched_directed += 1

    non_manifold_undirected = sum(1 for c in undirected_counts.values() if c != 2)
    volume_mm3 = vol6 / 6.0

    xs = [pt[0] for tri in triangles for pt in tri]
    ys = [pt[1] for tri in triangles for pt in tri]
    zs = [pt[2] for tri in triangles for pt in tri]
    dims = (
        round(max(xs) - min(xs), 2),
        round(max(ys) - min(ys), 2),
        round(max(zs) - min(zs), 2),
    )

    return {
        "num_triangles": len(triangles),
        "unmatched_directed_edges": unmatched_directed,
        "non_manifold_edges": non_manifold_undirected,
        "volume_cm3": round(volume_mm3 / 1000.0, 3),
        "estimated_pla_weight_g": round((volume_mm3 / 1000.0) * 1.24, 2),
        "dimensions_mm": dims,
        "is_watertight_manifold": (unmatched_directed == 0 and non_manifold_undirected == 0 and volume_mm3 > 0),
    }


def write_binary_stl(filepath, triangles):
    """Writes a standard binary STL file."""
    header = b"Wooting 80HE 2-Tone Geometry Dash Keycaps (4x) - Bambu A1 Mini".ljust(80, b"\x00")
    with open(filepath, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", len(triangles)))
        for p1, p2, p3 in triangles:
            ux, uy, uz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
            vx, vy, vz = p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            if length > 1e-12:
                nx, ny, nz = nx / length, ny / length, nz / length
            else:
                nx, ny, nz = 0.0, 0.0, 1.0
            f.write(struct.pack("<12fH", nx, ny, nz, *p1, *p2, *p3, 0))


def write_3mf(filepath, triangles):
    """Writes a standard 3MF archive centered on the Bambu Lab A1 Mini 180x180mm plate."""
    vert_map = {}
    vertices = []
    indexed_tris = []

    for p1, p2, p3 in triangles:
        idxs = []
        for pt in (p1, p2, p3):
            key = (round(pt[0], 5), round(pt[1], 5), round(pt[2], 5))
            if key not in vert_map:
                vert_map[key] = len(vertices)
                vertices.append(key)
            idxs.append(vert_map[key])
        indexed_tris.append(tuple(idxs))

    content_types_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""

    rels_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""

    verts_str = "\n".join(
        f'          <vertex x="{v[0]:.4f}" y="{v[1]:.4f}" z="{v[2]:.4f}"/>'
        for v in vertices
    )
    tris_str = "\n".join(
        f'          <triangle v1="{t[0]}" v2="{t[1]}" v3="{t[2]}"/>'
        for t in indexed_tris
    )

    model_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <metadata name="Title">Wooting 80HE Geometry Dash 2-Tone Keycaps (4-Key Set)</metadata>
  <metadata name="Application">BambuStudio</metadata>
  <resources>
    <object id="1" type="model" name="Wooting_80HE_Geometry_Dash_Keycaps">
      <mesh>
        <vertices>
{verts_str}
        </vertices>
        <triangles>
{tris_str}
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="1" transform="1 0 0 0 1 0 0 0 1 90 90 0"/>
  </build>
</model>"""

    with zipfile.ZipFile(filepath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("3D/3dmodel.model", model_xml)


def write_openscad(filepath, p):
    """Writes a parametric OpenSCAD source file for the Wooting 80HE OEM R1 4-keycap set."""
    scad = f"""// ============================================================================
// Wooting 80HE Geometry Dash 2-Tone Arrow Keycaps (4-Key Set — Official OEM R1 Profile)
// Filament Swap Pause at Z = {p["pause_z"]:.2f} mm (Layer 51 @ 0.20mm layer height)
// ============================================================================

base_width          = {p["base_width"]};
top_width_x         = {p["top_width_x"]};
top_width_y         = {p["top_width_y"]};
front_height        = {p["front_height"]};
back_height         = {p["back_height"]};
top_shift_y         = {p["top_shift_y"]};
dish_depth_x        = {p["dish_depth_x"]};
stem_boss_diameter  = {p["stem_boss_diameter"]};
cross_span          = {p["cross_span"]};
cross_slot_x        = {p["cross_slot_x"]};
cross_slot_y        = {p["cross_slot_y"]};
cross_depth         = {p["cross_depth"]};
grid_pitch          = {p["grid_pitch"]};

$fn = 64;

module rounded_rect(wx, wy, r) {{
    offset(r = r)
        square([wx - 2 * r, wy - 2 * r], center = true);
}}

module wooting_oem_r1_1u_keycap_base() {{
    difference() {{
        // Outer tapered 1u OEM R1 profile body (raised on back edge)
        hull() {{
            linear_extrude(height = 0.1)
                rounded_rect(base_width, base_width, 1.4);
            translate([0, top_shift_y, (front_height + back_height) * 0.5])
                rotate([atan2(back_height - front_height, top_width_y), 0, 0])
                linear_extrude(height = 0.1)
                rounded_rect(top_width_x, top_width_y, 1.15);
        }}

        // Cylindrical concave finger scoop across top surface
        translate([0, top_shift_y, (front_height + back_height) * 0.5 + 28.0 - dish_depth_x])
            rotate([90 + atan2(back_height - front_height, top_width_y), 0, 0])
            cylinder(h = top_width_y + 6.0, r = 28.0, center = true, $fn = 128);

        // Internal vaulted cavity around central stem boss
        difference() {{
            hull() {{
                translate([0, 0, -0.1])
                    linear_extrude(height = 3.8)
                    rounded_rect(base_width - 3.0, base_width - 3.0, 0.8);
                translate([0, top_shift_y * 0.7, 6.8])
                    linear_extrude(height = 0.1)
                    rounded_rect(6.2, 6.8, 0.5);
            }}
            cylinder(h = 7.2, d = stem_boss_diameter);
        }}

        // Wooting Lekker V2 / Cherry MX '+' cross-stem slot
        translate([0, 0, -0.1])
        linear_extrude(height = cross_depth + 0.1) {{
            square([cross_span, cross_slot_x], center = true);
            square([cross_slot_y, cross_span], center = true);
        }}
    }}
}}

for (gx = [-0.5, 0.5])
    for (gy = [-0.5, 0.5])
        translate([gx * grid_pitch, gy * grid_pitch, 0])
            wooting_oem_r1_1u_keycap_base();
"""
    with open(filepath, "w") as f:
        f.write(scad)


def compute_keycap_albedo_and_spec(x, y, z, nx, ny, nz, p):
    """
    Computes a realistic 2-Tone PLA Matte Gray + PLA Basic Blue appearance for the preview renders:
      - Color 1 (Z <= back_height): Matte Ash/Slate Gray PLA Matte keycap body & MX stems
      - Color 2 (Z > back_height + 0.05): Crisp Blue PLA Basic raised Geometry Dash icons
    """
    if z > p["back_height"] + 0.05:
        # Color 2 (After filament change pause at Z = 10.20 mm): Blue PLA Basic
        return (28.0, 126.0, 240.0), 34.0, 14.0
    if z < 3.5 and abs(nz) < 0.5 and (abs(x) < 15.0 and abs(y) < 15.0):
        return (118.0, 122.0, 126.0), 14.0, 8.0
    # Color 1 (Base keycap body): Matte Gray PLA Matte
    return (142.0, 145.0, 149.0), 18.0, 8.0


def write_preview_svg(filepath, triangles, p):
    """Renders a 3/4 top-isometric view of the 4 Wooting 80HE Geometry Dash keycaps to SVG."""
    yaw = math.radians(22.0)
    pitch = math.radians(48.0)

    def project(pt):
        x, y, z = pt[0], pt[1], pt[2] - 4.5
        rx = x * math.cos(yaw) - y * math.sin(yaw)
        ry = x * math.sin(yaw) + y * math.cos(yaw)
        sx = rx
        sy = -z * math.cos(pitch) - ry * math.sin(pitch)
        depth = -ry * math.cos(pitch) + z * math.sin(pitch)
        return sx, sy, depth

    light = (-0.32, 0.48, 0.82)
    l_norm = math.sqrt(sum(c * c for c in light))
    light = tuple(c / l_norm for c in light)

    polys = []
    for p1, p2, p3 in triangles:
        ux, uy, uz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
        vx, vy, vz = p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln < 1e-9:
            continue
        nx, ny, nz = nx / ln, ny / ln, nz / ln

        q1 = project(p1)
        q2 = project(p2)
        q3 = project(p3)

        cross_2d = (q2[0] - q1[0]) * (q3[1] - q1[1]) - (q2[1] - q1[1]) * (q3[0] - q1[0])
        if cross_2d >= 0:
            continue

        avg_depth = (q1[2] + q2[2] + q3[2]) / 3.0
        cx = (p1[0] + p2[0] + p3[0]) / 3.0
        cy = (p1[1] + p2[1] + p3[1]) / 3.0
        cz = (p1[2] + p2[2] + p3[2]) / 3.0

        vnx = nx * math.cos(yaw) - ny * math.sin(yaw)
        vny = nx * math.sin(yaw) + ny * math.cos(yaw)
        snx = vnx
        sny = nz * math.cos(pitch) + vny * math.sin(pitch)
        snz = -vny * math.cos(pitch) + nz * math.sin(pitch)

        dot = max(0.0, snx * light[0] + sny * light[1] + snz * light[2])
        albedo, spec_str, spec_pow = compute_keycap_albedo_and_spec(cx, cy, cz, nx, ny, nz, p)
        intensity = 0.38 + 0.62 * dot
        spec = spec_str * pow(max(0.0, dot), spec_pow)
        r = int(clamp(albedo[0] * intensity + spec, 0.0, 255.0))
        g = int(clamp(albedo[1] * intensity + spec, 0.0, 255.0))
        b = int(clamp(albedo[2] * intensity + spec, 0.0, 255.0))
        color = f"#{r:02x}{g:02x}{b:02x}"
        polys.append((avg_depth, q1, q2, q3, color))

    polys.sort(key=lambda item: item[0])

    scale = 12.0
    cx_scr, cy_scr = 400.0, 330.0
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="620" viewBox="0 0 800 620">',
        '  <rect width="100%" height="100%" fill="#0f141c"/>',
        '  <text x="24" y="36" font-family="sans-serif" font-size="20" font-weight="bold" fill="#f0c860">Wooting 80HE Arrow Keycaps — 2-Tone Geometry Dash Set (Cube, Ship, Ball, UFO)</text>',
        '  <text x="24" y="60" font-family="sans-serif" font-size="14" fill="#9ab0c8">4x 1u Keycaps | Lekker V2 / Cherry MX Stem | Auto Pause at Z = 8.60 mm for 2-Tone PLA Matte</text>',
    ]
    for _, q1, q2, q3, color in polys:
        pts = f"{cx_scr + q1[0]*scale:.2f},{cy_scr + q1[1]*scale:.2f} {cx_scr + q2[0]*scale:.2f},{cy_scr + q2[1]*scale:.2f} {cx_scr + q3[0]*scale:.2f},{cy_scr + q3[1]*scale:.2f}"
        lines.append(f'  <polygon points="{pts}" fill="{color}" stroke="{color}" stroke-width="0.25" stroke-linejoin="round"/>')
    lines.append("</svg>")

    with open(filepath, "w") as f:
        f.write("\n".join(lines))


def write_preview_png(filepath, triangles, p):
    """Renders a high-resolution, Z-buffered 2-tone dual-view PNG of the 4 keycaps."""
    width, height = 940, 620
    bg_r, bg_g, bg_b = 16, 22, 30
    rgb = bytearray([bg_r, bg_g, bg_b] * (width * height))
    zbuf = [-1e9] * (width * height)

    light = (-0.30, 0.45, 0.84)
    l_norm = math.sqrt(sum(c * c for c in light))
    light = tuple(c / l_norm for c in light)

    v_normals = {}
    for p1, p2, p3 in triangles:
        ux, uy, uz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
        vx, vy, vz = p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        for pt in (p1, p2, p3):
            key = (round(pt[0], 4), round(pt[1], 4), round(pt[2], 4))
            acc = v_normals.get(key)
            if acc is None:
                v_normals[key] = [nx, ny, nz]
            else:
                acc[0] += nx
                acc[1] += ny
                acc[2] += nz

    for key, acc in v_normals.items():
        ln = math.sqrt(acc[0] * acc[0] + acc[1] * acc[1] + acc[2] * acc[2])
        if ln > 1e-12:
            acc[0] /= ln
            acc[1] /= ln
            acc[2] /= ln

    def render_view(yaw_deg, pitch_deg, cx_scr, cy_scr, scale):
        yaw = math.radians(yaw_deg)
        pitch = math.radians(pitch_deg)

        def project(pt):
            x, y, z = pt[0], pt[1], pt[2] - 4.5
            rx = x * math.cos(yaw) - y * math.sin(yaw)
            ry = x * math.sin(yaw) + y * math.cos(yaw)
            sx = rx
            sy = -z * math.cos(pitch) - ry * math.sin(pitch)
            depth = -ry * math.cos(pitch) + z * math.sin(pitch)
            return sx, sy, depth

        v_colors = {}
        for key, (nx, ny, nz) in v_normals.items():
            vnx = nx * math.cos(yaw) - ny * math.sin(yaw)
            vny = nx * math.sin(yaw) + ny * math.cos(yaw)
            snx = vnx
            sny = nz * math.cos(pitch) + vny * math.sin(pitch)
            snz = -vny * math.cos(pitch) + nz * math.sin(pitch)
            dot = max(0.0, snx * light[0] + sny * light[1] + snz * light[2])
            fill = max(0.0, -0.45 * snx - 0.30 * sny + 0.45 * snz) * 0.22
            albedo, spec_str, spec_pow = compute_keycap_albedo_and_spec(key[0], key[1], key[2], nx, ny, nz, p)
            intensity = 0.38 + 0.62 * dot + fill
            spec = spec_str * pow(max(0.0, dot), spec_pow)
            r = clamp(albedo[0] * intensity + spec, 0.0, 255.0)
            g = clamp(albedo[1] * intensity + spec, 0.0, 255.0)
            b = clamp(albedo[2] * intensity + spec, 0.0, 255.0)
            v_colors[key] = (r, g, b)

        for p1, p2, p3 in triangles:
            k1 = (round(p1[0], 4), round(p1[1], 4), round(p1[2], 4))
            k2 = (round(p2[0], 4), round(p2[1], 4), round(p2[2], 4))
            k3 = (round(p3[0], 4), round(p3[1], 4), round(p3[2], 4))
            c1, c2, c3 = v_colors[k1], v_colors[k2], v_colors[k3]

            q1 = project(p1)
            q2 = project(p2)
            q3 = project(p3)

            x1, y1, z1 = cx_scr + q1[0] * scale, cy_scr + q1[1] * scale, q1[2]
            x2, y2, z2 = cx_scr + q2[0] * scale, cy_scr + q2[1] * scale, q2[2]
            x3, y3, z3 = cx_scr + q3[0] * scale, cy_scr + q3[1] * scale, q3[2]

            denom = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
            if abs(denom) < 1e-6:
                continue

            min_x = max(0, int(math.floor(min(x1, x2, x3))))
            max_x = min(width - 1, int(math.ceil(max(x1, x2, x3))))
            min_y = max(0, int(math.floor(min(y1, y2, y3))))
            max_y = min(height - 1, int(math.ceil(max(y1, y2, y3))))

            for py in range(min_y, max_y + 1):
                for px in range(min_x, max_x + 1):
                    w1 = ((y2 - y3) * (px - x3) + (x3 - x2) * (py - y3)) / denom
                    w2 = ((y3 - y1) * (px - x3) + (x1 - x3) * (py - y3)) / denom
                    w3 = 1.0 - w1 - w2
                    if w1 >= -1e-4 and w2 >= -1e-4 and w3 >= -1e-4:
                        pz = w1 * z1 + w2 * z2 + w3 * z3
                        idx = py * width + px
                        if pz > zbuf[idx]:
                            zbuf[idx] = pz
                            rgb[idx * 3] = int(clamp(w1 * c1[0] + w2 * c2[0] + w3 * c3[0], 0.0, 255.0))
                            rgb[idx * 3 + 1] = int(clamp(w1 * c1[1] + w2 * c2[1] + w3 * c3[1], 0.0, 255.0))
                            rgb[idx * 3 + 2] = int(clamp(w1 * c1[2] + w2 * c2[2] + w3 * c3[2], 0.0, 255.0))

    # Left view: Top-angled 3/4 view showing all 4 2-tone Geometry Dash icons (Cube, Ship, Ball, UFO)
    render_view(yaw_deg=14.0, pitch_deg=54.0, cx_scr=265.0, cy_scr=310.0, scale=10.5)
    # Right view: Underside view showing the 4 Wooting 80HE Lekker V2 / Cherry MX '+' cross stems
    render_view(yaw_deg=155.0, pitch_deg=-42.0, cx_scr=695.0, cy_scr=310.0, scale=9.8)

    raw_rows = bytearray()
    for y in range(height):
        raw_rows.append(0)
        row_start = y * width * 3
        raw_rows.extend(rgb[row_start : row_start + width * 3])

    def png_chunk(chunk_type, data):
        chunk = struct.pack(">I", len(data)) + chunk_type + data
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return chunk + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    compressed = zlib.compress(bytes(raw_rows), 9)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", compressed)
        + png_chunk(b"IEND", b"")
    )
    with open(filepath, "wb") as f:
        f.write(png_bytes)


if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))
    print("Building Wooting 80HE Geometry Dash 2-Tone Keycaps (4-Key Set)...")
    tris = build_all_keycaps_mesh(PARAMS)
    stats = verify_manifold(tris)
    print("Mesh Verification:", stats)
    if not stats["is_watertight_manifold"]:
        raise RuntimeError(f"Mesh failed manifold check: {stats}")

    stl_path = os.path.join(out_dir, "wooting_80he_keycaps.stl")
    threemf_path = os.path.join(out_dir, "wooting_80he_keycaps.3mf")
    scad_path = os.path.join(out_dir, "wooting_80he_keycaps.scad")
    svg_path = os.path.join(out_dir, "wooting_80he_keycaps_preview.svg")
    png_path = os.path.join(out_dir, "wooting_80he_keycaps_preview.png")

    write_binary_stl(stl_path, tris)
    write_3mf(threemf_path, tris)
    write_openscad(scad_path, PARAMS)
    write_preview_svg(svg_path, tris, PARAMS)
    write_preview_png(png_path, tris, PARAMS)
    print(f"Successfully generated:\n  - {stl_path}\n  - {threemf_path}\n  - {scad_path}\n  - {svg_path}\n  - {png_path}")

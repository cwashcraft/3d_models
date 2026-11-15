#!/usr/bin/env python3
"""
Parametric 3D Model Generator for a Keeshond Dog (inspired by dog.jpg & AKC breed standard).
Designed for FDM 3D printing on Bambu Lab A1 Mini / Bambu Studio / MakerWorld.

Anatomical & Breed Features:
  - Square-proportioned spitz body with deep chest, slight waist tuck-up, and level back
  - Voluminous lion-like neck ruff (mane) & shoulder shawl with subtle flowing groom locks
  - Clean, chiseled fox-like wedge head with defined stop, tapered muzzle, and almond eyes
  - Erect, high-set, sharply pointed triangular spitz ears with concave inner auricles
  - Happy slightly-open mouth with lower teeth and tongue lolling slightly to the right side (as in dog.jpg)
  - High-set, richly plumed spitz tail curled tightly forward over the back
  - Anatomical canine forelegs and hind legs (thigh + fluffy trousers -> stifle -> hock -> pastern -> cat-like paws)

Generates:
  1. keeshond_dog.stl         (Watertight 2-Manifold Binary STL)
  2. keeshond_dog.3mf         (Bambu Studio / Bambu Handy / MakerWorld 3MF)
  3. keeshond_dog.scad        (Parametric OpenSCAD source)
  4. keeshond_dog_preview.svg (Shaded vector preview)
  5. keeshond_dog_preview.png (High-resolution Phong + continuous fur-shaded raster preview)
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
    "scale_factor": 1.0,           # Overall uniform scale factor (1.0 = ~26 x 52 x 44 mm)
    "voxel_size": 0.30,            # Fine SDF surface extraction grid resolution (mm)

    # Square Spitz Body & Lion Ruff
    "withers_height": 29.5,        # Height at withers/shoulders (mm)
    "body_length": 28.5,           # Point of shoulder to ischium/buttocks (mm)
    "chest_width": 17.6,           # Width across ribcage/shoulders (mm)
    "ruff_radius": 10.6,           # Radius of lion-like neck ruff / mane (mm)

    # Chiseled Fox-Like Head, Muzzle & Triangular Ears
    "skull_width": 13.0,           # Width of wedge cranium + cheek coat (mm)
    "muzzle_length": 7.0,          # Length of tapered fox-like snout from stop (mm)
    "ear_height": 5.3,             # Height of small erect pointed triangular spitz ears (mm)
    "tongue_length": 2.8,          # Length of sideways-lolling tongue (mm)

    # Tightly Curled Plumed Tail & Legs
    "tail_plume_radius": 4.6,      # Radius of curled spitz tail plume (mm)
    "leg_radius": 2.35,            # Radius of trim lower legs (mm)
}


def smin(a, b, k):
    """Quadratic polynomial smooth minimum for organic SDF blending."""
    if k <= 1e-6:
        return a if a < b else b
    h = max(0.0, k - abs(a - b)) / k
    return (a if a < b else b) - h * h * k * 0.25


def smax(a, b, k):
    """Smooth maximum (for organic carving/hollows)."""
    return -smin(-a, -b, k)


def clamp(val, lo, hi):
    return lo if val < lo else (hi if val > hi else val)


def smoothstep(edge0, edge1, x):
    t = clamp((x - edge0) / (edge1 - edge0 + 1e-12), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def build_keeshond_dog_sdf(p):
    """
    Evaluates a high-detail Signed Distance Field (SDF) of an anatomically proportioned
    Keeshond dog, then extracts a guaranteed watertight 2-manifold triangle mesh.
    """
    s = p["scale_factor"]
    h = p["voxel_size"] * s

    x_min, x_max = -15.5 * s, 15.5 * s
    y_min, y_max = -24.5 * s, 30.0 * s
    z_min, z_max = 0.0, 46.5 * s

    nx = int(math.ceil((x_max - x_min) / h)) + 1
    ny = int(math.ceil((y_max - y_min) / h)) + 1
    nz = int(math.ceil((z_max - z_min) / h)) + 2

    xs = [x_min + i * h for i in range(nx)]
    ys = [y_min + j * h for j in range(ny)]
    zs = [(k - 0.5) * h for k in range(nz)]

    n_total = nx * ny * nz
    sdf = [100.0] * n_total

    def idx_range(vmin, vmax, v0, step, n_max):
        i0 = max(1, int(math.floor((vmin - v0) / step)))
        i1 = min(n_max - 2, int(math.ceil((vmax - v0) / step)))
        return range(i0, i1 + 1)

    def z_range(zmin_val, zmax_val):
        k0 = max(1, int(math.floor(zmin_val / h + 0.5)))
        k1 = min(nz - 2, int(math.ceil(zmax_val / h + 0.5)))
        return range(k0, k1 + 1)

    # --------------------------------------------------------------------------
    # Helper 1: Smooth Ellipsoid with optional gentle fur-lock fluting
    # --------------------------------------------------------------------------
    def add_ellipsoid(cx, cy, cz, rx, ry, rz, blend_k, taper_y=0.0, taper_z=0.0, flute_amp=0.0, flute_freq=16.0):
        margin = blend_k + flute_amp + h * 2.5
        rx_r = idx_range(cx - rx - margin, cx + rx + margin, x_min, h, nx)
        ry_r = idx_range(cy - ry - margin, cy + ry + margin, y_min, h, ny)
        rz_r = z_range(max(0.0, cz - rz - margin), cz + rz + margin)

        r_avg = (rx + ry + rz) / 3.0
        inv_rx, inv_ry, inv_rz = 1.0 / rx, 1.0 / ry, 1.0 / rz

        for i in rx_r:
            x = xs[i]
            dx0 = x - cx
            base_i = i * ny * nz
            for j in ry_r:
                y = ys[j]
                dy = (y - cy) * inv_ry
                sy_scale = max(0.50, 1.0 + taper_y * dy)
                base_ij = base_i + j * nz
                for k in rz_r:
                    z = zs[k]
                    dz0 = (z - cz) * inv_rz
                    sz_scale = max(0.50, 1.0 + taper_z * dz0)
                    dx = dx0 / (rx * sy_scale * sz_scale)
                    dz = dz0 / sy_scale
                    d_norm = math.sqrt(dx * dx + dy * dy + dz * dz)
                    d = (d_norm - 1.0) * r_avg
                    if flute_amp > 0.0 and abs(d) < r_avg * 0.45:
                        ang = math.atan2(dx0, y - cy + 1e-6)
                        d -= flute_amp * math.cos(flute_freq * ang) * max(0.0, 1.0 - dz0 * dz0)
                    cur = sdf[base_ij + k]
                    sdf[base_ij + k] = smin(cur, d, blend_k)

    # --------------------------------------------------------------------------
    # Helper 2: Subtract Ellipsoid (for mouth opening, ear hollows, nostrils)
    # --------------------------------------------------------------------------
    def carve_ellipsoid(cx, cy, cz, rx, ry, rz, blend_k):
        margin = blend_k + h * 2.5
        rx_r = idx_range(cx - rx - margin, cx + rx + margin, x_min, h, nx)
        ry_r = idx_range(cy - ry - margin, cy + ry + margin, y_min, h, ny)
        rz_r = z_range(max(0.0, cz - rz - margin), cz + rz + margin)

        r_avg = (rx + ry + rz) / 3.0
        inv_rx, inv_ry, inv_rz = 1.0 / rx, 1.0 / ry, 1.0 / rz

        for i in rx_r:
            dx = (xs[i] - cx) * inv_rx
            base_i = i * ny * nz
            for j in ry_r:
                dy = (ys[j] - cy) * inv_ry
                dxy2 = dx * dx + dy * dy
                if dxy2 > 4.0:
                    continue
                base_ij = base_i + j * nz
                for k in rz_r:
                    dz = (zs[k] - cz) * inv_rz
                    d = (math.sqrt(dxy2 + dz * dz) - 1.0) * r_avg
                    cur = sdf[base_ij + k]
                    sdf[base_ij + k] = smax(cur, -d, blend_k)

    # --------------------------------------------------------------------------
    # Helper 3: Anisotropic Tapered Capsule (A -> B) with X/Z aspect ratio
    # --------------------------------------------------------------------------
    def add_capsule(ax, ay, az, bx, by, bz, ra, rb, blend_k, mid_swell=0.0, scale_x=1.0, scale_z=1.0, flute_amp=0.0, flute_freq=14.0):
        r_max = max(ra, rb) * max(scale_x, scale_z) * (1.0 + max(0.0, mid_swell)) + flute_amp
        margin = r_max + blend_k + h * 2.5
        rx_r = idx_range(min(ax, bx) - margin, max(ax, bx) + margin, x_min, h, nx)
        ry_r = idx_range(min(ay, by) - margin, max(ay, by) + margin, y_min, h, ny)
        rz_r = z_range(max(0.0, min(az, bz) - margin), max(az, bz) + margin)

        abx, aby, abz = bx - ax, by - ay, bz - az
        ab_len2 = abx * abx + aby * aby + abz * abz
        inv_sx, inv_sz = 1.0 / scale_x, 1.0 / scale_z

        for i in rx_r:
            x = xs[i]
            pax = x - ax
            base_i = i * ny * nz
            for j in ry_r:
                y = ys[j]
                pay = y - ay
                pxy_dot = pax * abx + pay * aby
                base_ij = base_i + j * nz
                for k in rz_r:
                    z = zs[k]
                    paz = z - az
                    if ab_len2 > 1e-8:
                        t = clamp((pxy_dot + paz * abz) / ab_len2, 0.0, 1.0)
                    else:
                        t = 0.0
                    qx = (pax - t * abx) * inv_sx
                    qy = pay - t * aby
                    qz = (paz - t * abz) * inv_sz
                    r_t = (ra + t * (rb - ra)) * (1.0 + mid_swell * 4.0 * t * (1.0 - t))
                    dist = math.sqrt(qx * qx + qy * qy + qz * qz)
                    if flute_amp > 0.0 and abs(dist - r_t) < r_t * 0.45:
                        ang = math.atan2(qx, qz + 1e-6)
                        r_t += flute_amp * math.cos(flute_freq * ang + 3.0 * t)
                    d_cap = dist - r_t

                    cur = sdf[base_ij + k]
                    sdf[base_ij + k] = smin(cur, d_cap, blend_k)

    # --------------------------------------------------------------------------
    # Helper 4: Sharp Triangular Spitz Ear (3-vertex hull with concave inner hollow)
    # --------------------------------------------------------------------------
    def add_triangular_ear(p_inner, p_outer, p_tip, r_base, r_tip, blend_k):
        xs_e = (p_inner[0], p_outer[0], p_tip[0])
        ys_e = (p_inner[1], p_outer[1], p_tip[1])
        zs_e = (p_inner[2], p_outer[2], p_tip[2])
        margin = r_base + blend_k + h * 2.5
        rx_r = idx_range(min(xs_e) - margin, max(xs_e) + margin, x_min, h, nx)
        ry_r = idx_range(min(ys_e) - margin, max(ys_e) + margin, y_min, h, ny)
        rz_r = z_range(max(0.0, min(zs_e) - margin), max(zs_e) + margin)

        # Precompute triangle basis (A = p_inner, B = p_outer, C = p_tip)
        ax, ay, az = p_inner
        bx, by, bz = p_outer
        cx, cy, cz = p_tip
        v0x, v0y, v0z = bx - ax, by - ay, bz - az
        v1x, v1y, v1z = cx - ax, cy - ay, cz - az
        d00 = v0x * v0x + v0y * v0y + v0z * v0z
        d01 = v0x * v1x + v0y * v1y + v0z * v1z
        d11 = v1x * v1x + v1y * v1y + v1z * v1z
        denom = d00 * d11 - d01 * d01 + 1e-12

        for i in rx_r:
            x = xs[i]
            base_i = i * ny * nz
            for j in ry_r:
                y = ys[j]
                base_ij = base_i + j * nz
                for k in rz_r:
                    z = zs[k]
                    v2x, v2y, v2z = x - ax, y - ay, z - az
                    d20 = v2x * v0x + v2y * v0y + v2z * v0z
                    d21 = v2x * v1x + v2y * v1y + v2z * v1z
                    u = (d11 * d20 - d01 * d21) / denom
                    v = (d00 * d21 - d01 * d20) / denom
                    # Clamp barycentric coordinates (u, v) to triangle u >= 0, v >= 0, u + v <= 1
                    u = max(0.0, u)
                    v = max(0.0, v)
                    if u + v > 1.0:
                        s_uv = u + v
                        u /= s_uv
                        v /= s_uv
                    qx = ax + u * v0x + v * v1x
                    qy = ay + u * v0y + v * v1y
                    qz = az + u * v0z + v * v1z
                    dist = math.sqrt((x - qx) ** 2 + (y - qy) ** 2 + (z - qz) ** 2)
                    # Thickness tapers cleanly toward tip (v -> 1) and edges
                    r_here = r_base * (1.0 - 0.68 * v) + r_tip * (0.68 * v)
                    d = dist - r_here
                    cur = sdf[base_ij + k]
                    sdf[base_ij + k] = smin(cur, d, blend_k)

    # ==========================================================================
    # 1. SQUARE-PROPORTIONED SPITZ BODY, DEEP CHEST & VOLUMINOUS LION RUFF
    # ==========================================================================
    cw = (p["chest_width"] * 0.5) * s
    rr = p["ruff_radius"] * s

    # Deep ribcage / briskets (front torso) -> slight waist tuck-up -> croup (rear torso)
    # Note the slight downward slope of the topline from withers to croup per AKC standard
    add_capsule(
        0.0, 5.8 * s, 19.2 * s,
        0.0, -9.8 * s, 18.2 * s,
        cw * 0.96, cw * 0.84,
        blend_k=2.0 * s, mid_swell=0.06, scale_x=0.96, scale_z=1.08,
        flute_amp=0.14 * s, flute_freq=18.0
    )
    # Rounded croup / rump
    add_ellipsoid(
        0.0, -11.5 * s, 18.5 * s,
        cw * 0.84, 6.6 * s, 7.6 * s,
        blend_k=1.8 * s, flute_amp=0.12 * s, flute_freq=16.0
    )

    # Signature Keeshond Lion-Like Neck Ruff / Mane (broad, plush collar around neck & shoulders)
    add_ellipsoid(
        0.0, 8.2 * s, 22.2 * s,
        rr * 1.02, 7.8 * s, rr * 0.96,
        blend_k=2.2 * s, taper_y=-0.06, taper_z=-0.08,
        flute_amp=0.18 * s, flute_freq=20.0
    )
    # Deep front chest apron (brisket ruff hanging gracefully between the forelegs)
    add_ellipsoid(
        0.0, 10.6 * s, 16.6 * s,
        rr * 0.78, 5.8 * s, 6.2 * s,
        blend_k=2.0 * s, taper_z=0.15,
        flute_amp=0.16 * s, flute_freq=16.0
    )

    # ==========================================================================
    # 2. ANATOMICAL FORE- AND HIND-LEGS + CAT-LIKE PAWS ON Z = 0
    # ==========================================================================
    lr = p["leg_radius"] * s
    for side in (-1.0, 1.0):
        # --- FORELEGS (shoulder -> elbow -> straight trim forearm -> pastern -> cat paw) ---
        fx_sh, fy_sh, fz_sh = side * 4.2 * s, 8.2 * s, 15.0 * s
        fx_el, fy_el, fz_el = side * 4.0 * s, 7.8 * s, 10.2 * s
        fx_wr, fy_wr, fz_wr = side * 3.7 * s, 8.5 * s, 3.0 * s
        fx_an, fy_an, fz_an = side * 3.6 * s, 9.1 * s, 1.25 * s
        fx_pw, fy_pw, fz_pw = side * 3.5 * s, 11.0 * s, 1.10 * s

        # Upper arm + rear feathering at elbow
        add_capsule(fx_sh, fy_sh, fz_sh, fx_el, fy_el, fz_el, lr * 1.55, lr * 1.22, blend_k=1.4 * s, scale_x=0.92, scale_z=1.08)
        # Straight, fine-boned forearm (with subtle rear feather fringe)
        add_capsule(fx_el, fy_el, fz_el, fx_wr, fy_wr, fz_wr, lr * 1.15, lr * 0.92, blend_k=0.65 * s, scale_x=0.90, scale_z=1.08)
        add_capsule(side * 4.0 * s, 6.7 * s, 10.5 * s, side * 3.8 * s, 7.2 * s, 5.2 * s, lr * 0.78, lr * 0.45, blend_k=0.75 * s)
        # Pastern to ankle
        add_capsule(fx_wr, fy_wr, fz_wr, fx_an, fy_an, fz_an, lr * 0.90, lr * 0.86, blend_k=0.45 * s)
        # Compact, arched cat-like front paw
        add_capsule(fx_an, fy_an, fz_an, fx_pw, fy_pw, fz_pw, lr * 0.90, lr * 0.96, blend_k=0.42 * s, scale_x=1.08, scale_z=0.82)
        # 4 neat front toes per paw
        for toe_dx, toe_dy, toe_r in (
            (-1.25 * s, 1.25 * s, 0.68 * s),
            (-0.42 * s, 1.55 * s, 0.72 * s),
            (0.42 * s, 1.55 * s, 0.72 * s),
            (1.25 * s, 1.25 * s, 0.68 * s),
        ):
            add_capsule(
                fx_pw + toe_dx * 0.65, fy_pw - 0.1 * s, 0.95 * s,
                fx_pw + toe_dx, fy_pw + toe_dy, 0.82 * s,
                toe_r, toe_r * 0.92, blend_k=0.18 * s
            )

        # --- HIND LEGS (muscular thigh + fluffy "trousers" -> stifle -> hock -> metatarsus -> paw) ---
        bx_hp, by_hp, bz_hp = side * 4.8 * s, -10.2 * s, 16.0 * s
        bx_st, by_st, bz_st = side * 4.9 * s, -8.2 * s, 10.5 * s
        bx_hk, by_hk, bz_hk = side * 4.6 * s, -12.2 * s, 5.6 * s
        bx_an, by_an, bz_an = side * 4.5 * s, -11.6 * s, 1.25 * s
        bx_pw, by_pw, bz_pw = side * 4.5 * s, -9.7 * s, 1.10 * s

        # Upper thigh + signature Keeshond fluffy "trousers" (breeching down to the hock)
        add_capsule(bx_hp, by_hp, bz_hp, bx_st, by_st, bz_st, lr * 1.95, lr * 1.48, blend_k=1.6 * s, scale_x=0.92, scale_z=1.12)
        add_capsule(side * 5.1 * s, -13.2 * s, 15.2 * s, side * 4.8 * s, -12.6 * s, 7.5 * s, lr * 1.55, lr * 0.85, blend_k=1.3 * s, flute_amp=0.12 * s, flute_freq=10.0)
        # Lower thigh (stifle to hock joint)
        add_capsule(bx_st, by_st, bz_st, bx_hk, by_hk, bz_hk, lr * 1.38, lr * 0.98, blend_k=0.75 * s, scale_x=0.88, scale_z=1.08)
        # Vertical rear pastern / metatarsus (hock to ankle—clean & trim below the hock)
        add_capsule(bx_hk, by_hk, bz_hk, bx_an, by_an, bz_an, lr * 0.92, lr * 0.84, blend_k=0.45 * s)
        # Compact cat-like hind paw + 4 neat toes
        add_capsule(bx_an, by_an, bz_an, bx_pw, by_pw, bz_pw, lr * 0.86, lr * 0.92, blend_k=0.42 * s, scale_x=1.06, scale_z=0.82)
        for toe_dx, toe_dy, toe_r in (
            (-1.18 * s, 1.20 * s, 0.65 * s),
            (-0.39 * s, 1.48 * s, 0.68 * s),
            (0.39 * s, 1.48 * s, 0.68 * s),
            (1.18 * s, 1.20 * s, 0.65 * s),
        ):
            add_capsule(
                bx_pw + toe_dx * 0.65, by_pw - 0.1 * s, 0.95 * s,
                bx_pw + toe_dx, by_pw + toe_dy, 0.82 * s,
                toe_r, toe_r * 0.92, blend_k=0.18 * s
            )

    # ==========================================================================
    # 3. CHISELED FOX-LIKE WEDGE HEAD, MUZZLE, ALMOND EYES & SIDEWAYS TONGUE
    # ==========================================================================
    sw = (p["skull_width"] * 0.5) * s
    hc_y = 13.5 * s
    hc_z = 29.2 * s

    # Neck column rising from the shoulder ruff into the base of the skull
    add_capsule(0.0, 9.2 * s, 23.0 * s, 0.0, hc_y - 0.8 * s, hc_z - 1.2 * s, 7.2 * s, 6.4 * s, blend_k=1.8 * s)

    # Fox-like wedge cranium (wider at the cheek ruff behind the eyes, tapering cleanly forward)
    add_ellipsoid(
        0.0, hc_y, hc_z,
        sw * 1.06, sw * 1.02, sw * 0.96,
        blend_k=1.6 * s, taper_y=-0.18, taper_z=-0.08
    )
    # Soft, sweeping cheek ruff framing the lower sides of the head (smooth cape, no warts!)
    for side in (-1.0, 1.0):
        add_capsule(
            side * 4.8 * s, hc_y + 0.5 * s, hc_z - 1.2 * s,
            side * 7.2 * s, hc_y - 2.2 * s, hc_z - 4.5 * s,
            3.2 * s, 2.2 * s, blend_k=1.6 * s, scale_x=0.85, scale_z=1.10
        )

    # Defined brow & Keeshond "spectacles" orbital arch above the almond eyes
    for side in (-1.0, 1.0):
        add_capsule(
            side * 1.1 * s, hc_y + 5.2 * s, hc_z + 1.8 * s,
            side * 3.8 * s, hc_y + 4.1 * s, hc_z + 1.1 * s,
            0.95 * s, 0.82 * s, blend_k=0.65 * s
        )

    # Clean, Chiseled Fox-Like Upper Muzzle / Snout (with well-defined stop below brow)
    muz_len = p["muzzle_length"] * s
    stop_y = hc_y + 4.6 * s
    stop_z = hc_z - 0.8 * s
    nose_y = stop_y + muz_len
    nose_z = stop_z - 1.8 * s

    add_capsule(
        0.0, stop_y - 0.6 * s, stop_z,
        0.0, nose_y - 0.6 * s, nose_z + 0.15 * s,
        3.55 * s, 1.85 * s, blend_k=0.95 * s, scale_x=0.96, scale_z=0.92
    )

    # Slightly Open Happy Mouth Cavity & Neat Tapered Lower Jaw (matching dog.jpg)
    carve_ellipsoid(
        0.0, nose_y - 1.5 * s, nose_z - 1.25 * s,
        1.95 * s, 2.85 * s, 1.15 * s, blend_k=0.25 * s
    )
    add_capsule(
        0.0, stop_y - 0.4 * s, stop_z - 2.6 * s,
        0.0, nose_y - 1.35 * s, nose_z - 2.15 * s,
        2.65 * s, 1.45 * s, blend_k=0.65 * s, scale_x=0.94, scale_z=0.85
    )

    # Delicate lower teeth arch (4 tiny incisors + 2 small canines visible inside lower jaw)
    for tooth_x, tooth_y_off, tooth_r in (
        (-0.98 * s, -1.45 * s, 0.30 * s),
        (-0.55 * s, -1.18 * s, 0.25 * s),
        (-0.18 * s, -1.10 * s, 0.25 * s),
        (0.18 * s, -1.10 * s, 0.25 * s),
        (0.55 * s, -1.18 * s, 0.25 * s),
        (0.98 * s, -1.45 * s, 0.30 * s),
    ):
        add_ellipsoid(
            tooth_x, nose_y + tooth_y_off, nose_z - 1.50 * s,
            tooth_r, tooth_r, 0.42 * s, blend_k=0.08 * s
        )

    # Sculpted Black Nose Leather at tip of snout + nostrils
    add_ellipsoid(
        0.0, nose_y + 0.1 * s, nose_z + 0.48 * s,
        1.45 * s, 1.12 * s, 1.08 * s, blend_k=0.28 * s
    )
    for side in (-1.0, 1.0):
        carve_ellipsoid(
            side * 0.52 * s, nose_y + 0.95 * s, nose_z + 0.42 * s,
            0.30 * s, 0.35 * s, 0.36 * s, blend_k=0.08 * s
        )

    # Cute Sideways-Lolling Tongue hanging naturally over the right lower lip (+X, viewer's left in dog.jpg)
    tl = p["tongue_length"] * s
    add_capsule(
        0.35 * s, nose_y - 1.65 * s, nose_z - 1.35 * s,
        1.35 * s, nose_y - 1.05 * s, nose_z - 1.75 * s,
        0.92 * s, 1.04 * s, blend_k=0.28 * s, scale_x=1.05, scale_z=0.68
    )
    add_capsule(
        1.35 * s, nose_y - 1.05 * s, nose_z - 1.75 * s,
        1.25 * s + tl * 0.25, nose_y - 0.55 * s, nose_z - 2.75 * s,
        1.04 * s, 0.92 * s, blend_k=0.28 * s, mid_swell=0.08, scale_x=1.08, scale_z=0.62
    )

    # Obliquely Set Almond Eyes with Subtle Eyelid Rims
    for side in (-1.0, 1.0):
        ex, ey, ez = side * 2.65 * s, hc_y + 5.15 * s, hc_z + 0.45 * s
        # Slight orbital socket recess
        carve_ellipsoid(ex, ey + 0.15 * s, ez, 1.25 * s, 1.05 * s, 1.05 * s, blend_k=0.22 * s)
        # Almond eyeball
        add_ellipsoid(ex, ey, ez, 1.05 * s, 0.98 * s, 0.95 * s, blend_k=0.12 * s)

    # ==========================================================================
    # 4. SMALL, ERECT, HIGH-SET, POINTED TRIANGULAR SPITZ EARS (AKC Standard)
    # ==========================================================================
    eh = p["ear_height"] * s
    for side in (-1.0, 1.0):
        # Inner base, outer base, and pointed tip nestled into the plush crown coat
        p_in = (side * 2.1 * s, hc_y + 0.5 * s, hc_z + 4.4 * s)
        p_out = (side * 5.3 * s, hc_y - 0.8 * s, hc_z + 3.2 * s)
        p_tip = (side * 4.1 * s, hc_y + 0.7 * s, hc_z + 4.4 * s + eh)
        add_triangular_ear(p_in, p_out, p_tip, r_base=1.60 * s, r_tip=0.55 * s, blend_k=0.85 * s)

        # Carve shallow forward-facing triangular auricle hollow (concha)
        carve_ellipsoid(
            side * 3.75 * s, hc_y + 0.90 * s, hc_z + 4.1 * s + eh * 0.36,
            1.05 * s, 0.85 * s, eh * 0.34, blend_k=0.28 * s
        )

    # ==========================================================================
    # 5. HIGH-SET, TIGHTLY CURLED PLUMED SPITZ TAIL OVER THE BACK
    #    Lies flat and snug against the back in a double-curl plume as per AKC standard
    # ==========================================================================
    tpr = p["tail_plume_radius"] * s
    tail_arc = [
        (0.0, -15.6 * s, 20.0 * s, tpr * 0.65),
        (0.2 * s, -18.2 * s, 24.5 * s, tpr * 0.82),
        (0.5 * s, -16.8 * s, 29.2 * s, tpr * 0.96),
        (0.8 * s, -13.0 * s, 31.2 * s, tpr * 1.02),
        (1.1 * s, -8.5 * s, 29.5 * s, tpr * 0.92),
        (1.4 * s, -5.0 * s, 25.5 * s, tpr * 0.72),
    ]
    for idx in range(len(tail_arc) - 1):
        x0, y0, z0, r0 = tail_arc[idx]
        x1, y1, z1, r1 = tail_arc[idx + 1]
        add_capsule(
            x0, y0, z0, x1, y1, z1, r0, r1,
            blend_k=1.1 * s, mid_swell=0.08, scale_x=1.12, scale_z=0.95,
            flute_amp=0.22 * s, flute_freq=14.0
        )

    # ==========================================================================
    # 6. ENFORCE STRICT OUTER BOUNDARY & FLAT Z=0 BUILD PLATE
    # ==========================================================================
    for i in range(nx):
        base_i = i * ny * nz
        for j in range(ny):
            base_ij = base_i + j * nz
            val_k1 = sdf[base_ij + 1]
            if val_k1 < 0.0:
                sdf[base_ij + 0] = -val_k1
            else:
                sdf[base_ij + 0] = max(h, val_k1 + h)
            sdf[base_ij + (nz - 1)] = 100.0

    for i in (0, nx - 1):
        base_i = i * ny * nz
        for j in range(ny):
            base_ij = base_i + j * nz
            for k in range(nz):
                sdf[base_ij + k] = 100.0

    for i in range(nx):
        base_i = i * ny * nz
        for j in (0, ny - 1):
            base_ij = base_i + j * nz
            for k in range(nz):
                sdf[base_ij + k] = 100.0

    # ==========================================================================
    # 7. TOPOLOGY-REPAIRED SURFACE NET EXTRACTION (100% Watertight 2-Manifold)
    # ==========================================================================
    inside = [val < 0.0 for val in sdf]

    visited = [False] * n_total
    best_comp = []
    for idx_start in range(n_total):
        if inside[idx_start] and not visited[idx_start]:
            comp = []
            stack = [idx_start]
            visited[idx_start] = True
            while stack:
                cur = stack.pop()
                comp.append(cur)
                k = cur % nz
                rem = cur // nz
                j = rem % ny
                i = rem // ny
                if i > 0:
                    nb = cur - ny * nz
                    if inside[nb] and not visited[nb]:
                        visited[nb] = True
                        stack.append(nb)
                if i + 1 < nx:
                    nb = cur + ny * nz
                    if inside[nb] and not visited[nb]:
                        visited[nb] = True
                        stack.append(nb)
                if j > 0:
                    nb = cur - nz
                    if inside[nb] and not visited[nb]:
                        visited[nb] = True
                        stack.append(nb)
                if j + 1 < ny:
                    nb = cur + nz
                    if inside[nb] and not visited[nb]:
                        visited[nb] = True
                        stack.append(nb)
                if k > 0:
                    nb = cur - 1
                    if inside[nb] and not visited[nb]:
                        visited[nb] = True
                        stack.append(nb)
                if k + 1 < nz:
                    nb = cur + 1
                    if inside[nb] and not visited[nb]:
                        visited[nb] = True
                        stack.append(nb)
            if len(comp) > len(best_comp):
                best_comp = comp

    inside = [False] * n_total
    for c_idx in best_comp:
        inside[c_idx] = True

    nyz = ny * nz
    while True:
        fixed = 0
        for i in range(1, nx - 2):
            bi = i * nyz
            for j in range(1, ny - 2):
                bij = bi + j * nz
                for k in range(1, nz - 2):
                    idx0 = bij + k
                    a = inside[idx0]
                    b = inside[idx0 + nyz]
                    c = inside[idx0 + nyz + nz]
                    d = inside[idx0 + nz]
                    if a == c and b == d and a != b:
                        if not a:
                            inside[idx0] = True
                            sdf[idx0] = -1e-4
                        else:
                            inside[idx0 + nyz] = True
                            sdf[idx0 + nyz] = -1e-4
                        fixed += 1

                    a = inside[idx0]
                    b = inside[idx0 + nyz]
                    c = inside[idx0 + nyz + 1]
                    d = inside[idx0 + 1]
                    if a == c and b == d and a != b:
                        if not a:
                            inside[idx0] = True
                            sdf[idx0] = -1e-4
                        else:
                            inside[idx0 + nyz] = True
                            sdf[idx0 + nyz] = -1e-4
                        fixed += 1

                    a = inside[idx0]
                    b = inside[idx0 + nz]
                    c = inside[idx0 + nz + 1]
                    d = inside[idx0 + 1]
                    if a == c and b == d and a != b:
                        if not a:
                            inside[idx0] = True
                            sdf[idx0] = -1e-4
                        else:
                            inside[idx0 + nz] = True
                            sdf[idx0 + nz] = -1e-4
                        fixed += 1
        if fixed == 0:
            break

    for idx0 in range(n_total):
        if inside[idx0] and sdf[idx0] >= 0.0:
            sdf[idx0] = -1e-4
        elif (not inside[idx0]) and sdf[idx0] <= 0.0:
            sdf[idx0] = 1e-4

    cell_edges = [
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
    ]

    cell_to_vert = {}
    verts = []
    pinned_bottom = []

    for i in range(nx - 1):
        bi = i * nyz
        for j in range(ny - 1):
            bij = bi + j * nz
            for k in range(nz - 1):
                c000 = inside[bij + k]
                if (
                    inside[bij + k + 1] == c000
                    and inside[bij + nz + k] == c000
                    and inside[bij + nz + k + 1] == c000
                    and inside[bij + nyz + k] == c000
                    and inside[bij + nyz + k + 1] == c000
                    and inside[bij + nyz + nz + k] == c000
                    and inside[bij + nyz + nz + k + 1] == c000
                ):
                    continue

                sx_sum, sy_sum, sz_sum = 0.0, 0.0, 0.0
                cnt = 0
                for (dx0, dy0, dz0), (dx1, dy1, dz1) in cell_edges:
                    idx_a = (i + dx0) * nyz + (j + dy0) * nz + (k + dz0)
                    idx_b = (i + dx1) * nyz + (j + dy1) * nz + (k + dz1)
                    if inside[idx_a] != inside[idx_b]:
                        va = sdf[idx_a]
                        vb = sdf[idx_b]
                        t = va / (va - vb)
                        t = max(0.05, min(0.95, t))
                        px = xs[i + dx0] + t * (xs[i + dx1] - xs[i + dx0])
                        py = ys[j + dy0] + t * (ys[j + dy1] - ys[j + dy0])
                        pz = zs[k + dz0] + t * (zs[k + dz1] - zs[k + dz0])
                        sx_sum += px
                        sy_sum += py
                        sz_sum += pz
                        cnt += 1

                vx = sx_sum / cnt
                vy = sy_sum / cnt
                vz = 0.0 if k == 0 else max(0.02 * h, sz_sum / cnt)

                v_idx = len(verts)
                cell_to_vert[(i, j, k)] = v_idx
                verts.append([vx, vy, vz])
                pinned_bottom.append(k == 0)

    quads = []

    for i in range(nx - 1):
        bi = i * nyz
        for j in range(1, ny - 1):
            bij = bi + j * nz
            for k in range(1, nz - 1):
                s0 = inside[bij + k]
                s1 = inside[bij + nyz + k]
                if s0 != s1:
                    c0 = cell_to_vert[(i, j - 1, k - 1)]
                    c1 = cell_to_vert[(i, j, k - 1)]
                    c2 = cell_to_vert[(i, j, k)]
                    c3 = cell_to_vert[(i, j - 1, k)]
                    if s0:
                        quads.append((c0, c1, c2, c3))
                    else:
                        quads.append((c0, c3, c2, c1))

    for i in range(1, nx - 1):
        bi = i * nyz
        for j in range(ny - 1):
            bij = bi + j * nz
            for k in range(1, nz - 1):
                s0 = inside[bij + k]
                s1 = inside[bij + nz + k]
                if s0 != s1:
                    c0 = cell_to_vert[(i - 1, j, k - 1)]
                    c1 = cell_to_vert[(i - 1, j, k)]
                    c2 = cell_to_vert[(i, j, k)]
                    c3 = cell_to_vert[(i, j, k - 1)]
                    if s0:
                        quads.append((c0, c1, c2, c3))
                    else:
                        quads.append((c0, c3, c2, c1))

    for i in range(1, nx - 1):
        bi = i * nyz
        for j in range(1, ny - 1):
            bij = bi + j * nz
            for k in range(nz - 1):
                s0 = inside[bij + k]
                s1 = inside[bij + k + 1]
                if s0 != s1:
                    c0 = cell_to_vert[(i - 1, j - 1, k)]
                    c1 = cell_to_vert[(i, j - 1, k)]
                    c2 = cell_to_vert[(i, j, k)]
                    c3 = cell_to_vert[(i - 1, j, k)]
                    if s0:
                        quads.append((c0, c1, c2, c3))
                    else:
                        quads.append((c0, c3, c2, c1))

    adj = [[] for _ in range(len(verts))]
    for c0, c1, c2, c3 in quads:
        adj[c0].extend((c1, c3))
        adj[c1].extend((c0, c2))
        adj[c2].extend((c1, c3))
        adj[c3].extend((c2, c0))

    for weight in (0.45, -0.47, 0.45, -0.47, 0.40, -0.42, 0.35, -0.36):
        new_verts = []
        for v_idx, (vx, vy, vz) in enumerate(verts):
            nbs = adj[v_idx]
            if not nbs:
                new_verts.append([vx, vy, vz])
                continue
            inv_n = 1.0 / len(nbs)
            ax = sum(verts[n][0] for n in nbs) * inv_n
            ay = sum(verts[n][1] for n in nbs) * inv_n
            az = sum(verts[n][2] for n in nbs) * inv_n
            nx_v = vx + weight * (ax - vx)
            ny_v = vy + weight * (ay - vy)
            nz_v = 0.0 if pinned_bottom[v_idx] else max(0.01, vz + weight * (az - vz))
            new_verts.append([nx_v, ny_v, nz_v])
        verts = new_verts

    triangles = []
    for c0, c1, c2, c3 in quads:
        v0 = tuple(verts[c0])
        v1 = tuple(verts[c1])
        v2 = tuple(verts[c2])
        v3 = tuple(verts[c3])
        d02 = (v0[0] - v2[0]) ** 2 + (v0[1] - v2[1]) ** 2 + (v0[2] - v2[2]) ** 2
        d13 = (v1[0] - v3[0]) ** 2 + (v1[1] - v3[1]) ** 2 + (v1[2] - v3[2]) ** 2
        if d02 <= d13:
            triangles.append((v0, v1, v2))
            triangles.append((v0, v2, v3))
        else:
            triangles.append((v0, v1, v3))
            triangles.append((v1, v2, v3))

    return triangles


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
        round(max(xs) - min(xs), 1),
        round(max(ys) - min(ys), 1),
        round(max(zs) - min(zs), 1),
    )

    return {
        "num_triangles": len(triangles),
        "unmatched_directed_edges": unmatched_directed,
        "non_manifold_edges": non_manifold_undirected,
        "volume_cm3": round(volume_mm3 / 1000.0, 3),
        "dimensions_mm": dims,
        "is_watertight_manifold": (unmatched_directed == 0 and non_manifold_undirected == 0 and volume_mm3 > 0),
    }


def write_binary_stl(filepath, triangles):
    """Writes a standard binary STL file."""
    header = b"Keeshond Dog (dog.jpg) - Bambu Lab A1 Mini 3D Print Model".ljust(80, b"\x00")
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
  <metadata name="Title">Keeshond Dog Figurine (dog.jpg)</metadata>
  <metadata name="Application">BambuStudio</metadata>
  <resources>
    <object id="1" type="model" name="Keeshond_Dog">
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
    """Writes a parametric OpenSCAD source file for the Keeshond Dog."""
    scad = f"""// ============================================================================
// Keeshond Dog (inspired by dog.jpg & AKC Breed Standard) - Parametric OpenSCAD
// Print Orientation: Standing on 4 paws flat on Z = 0 build plate
// ============================================================================

scale_factor      = {p["scale_factor"]};
chest_width       = {p["chest_width"]};
body_length       = {p["body_length"]};
ruff_radius       = {p["ruff_radius"]};
skull_width       = {p["skull_width"]};
muzzle_length     = {p["muzzle_length"]};
ear_height        = {p["ear_height"]};
tongue_length     = {p["tongue_length"]};
tail_plume_radius = {p["tail_plume_radius"]};
leg_radius        = {p["leg_radius"]};

$fn = 48;

module round_capsule(a, b, ra, rb) {{
    hull() {{
        translate(a) sphere(r=ra);
        translate(b) sphere(r=rb);
    }}
}}

scale([scale_factor, scale_factor, scale_factor])
intersection() {{
    translate([-50, -50, 0]) cube([100, 100, 80]);
    union() {{
        // Square-proportioned Spitz Torso & Lion-Like Neck Ruff
        round_capsule([0, 5.8, 19.2], [0, -9.8, 18.2], chest_width*0.48, chest_width*0.42);
        translate([0, 8.2, 22.2]) scale([ruff_radius*1.02, 7.8, ruff_radius*0.96]) sphere(r=1);
        translate([0, 10.6, 16.6]) scale([ruff_radius*0.78, 5.8, 6.2]) sphere(r=1);

        // Chiseled Fox-Like Wedge Head, Snout & Lolling Tongue
        translate([0, 13.5, 29.2]) scale([skull_width*0.53, skull_width*0.51, skull_width*0.48]) sphere(r=1);
        round_capsule([0, 17.5, 28.4], [0, 18.1 + muzzle_length, 26.75], 3.55, 1.85);
        round_capsule([0, 17.7, 25.8], [0, 17.35 + muzzle_length, 24.45], 2.65, 1.45);
        round_capsule([0.4, 16.6 + muzzle_length, 25.35], [1.9, 17.25 + muzzle_length, 24.95], 1.02, 1.15);
        round_capsule([1.9, 17.25 + muzzle_length, 24.95], [1.6 + tongue_length*0.45, 17.85 + muzzle_length, 23.65], 1.15, 1.05);

        // Triangular Erect Ears & 4 Feathered Legs
        for (side = [-1, 1]) {{
            hull() {{
                translate([side*2.3, 13.9, 34.0]) sphere(r=1.45);
                translate([side*5.2, 12.7, 32.8]) sphere(r=1.45);
                translate([side*4.4, 14.1, 34.0 + ear_height]) sphere(r=0.48);
            }}
            round_capsule([side*4.2, 8.2, 15.0], [side*3.6, 9.1, 1.25], leg_radius*1.4, leg_radius*0.86);
            round_capsule([side*3.6, 9.1, 1.25], [side*3.5, 11.0, 1.10], leg_radius*0.90, leg_radius*0.96);
            round_capsule([side*4.8, -10.2, 16.0], [side*4.6, -12.2, 5.6], leg_radius*1.8, leg_radius*0.98);
            round_capsule([side*4.6, -12.2, 5.6], [side*4.5, -11.6, 1.25], leg_radius*0.92, leg_radius*0.84);
            round_capsule([side*4.5, -11.6, 1.25], [side*4.5, -9.7, 1.10], leg_radius*0.86, leg_radius*0.92);
        }}

        // Tightly Curled Plume Tail Over Back
        round_capsule([0, -15.6, 20.0], [0.5, -16.8, 29.2], tail_plume_radius*0.65, tail_plume_radius*0.96);
        round_capsule([0.5, -16.8, 29.2], [0.8, -13.0, 31.2], tail_plume_radius*0.96, tail_plume_radius*1.02);
        round_capsule([0.8, -13.0, 31.2], [1.4, -5.0, 25.5], tail_plume_radius*1.02, tail_plume_radius*0.72);
    }}
}}
"""
    with open(filepath, "w") as f:
        f.write(scad)


def compute_keeshond_albedo_and_spec(x, y, z, p):
    """
    Computes a continuous, breed-accurate RGB albedo + specular parameters at 3D point (x, y, z)
    matching the AKC Keeshond standard and dog.jpg:
      - Smooth agouti silver-grey/charcoal-tipped coat with fine procedural fur-strand texture
      - Warm silver-cream lion's ruff (mane) & diagonal "shoulder harness" flash
      - Pale cream/silver orbital "spectacles" around dark brown almond eyes
      - Delicate dark pencil line slanting from outer eye corner toward lower ear corner
      - Velvety charcoal-black triangular ears and tapered dark muzzle mask
      - Pink sideways-lolling tongue and white lower teeth inside open mouth
      - Solid cream lower legs/paws and white/silver tail plume with a black tip
    """
    s = p["scale_factor"]
    hc_y = 13.5 * s
    hc_z = 29.2 * s
    stop_y = hc_y + 4.6 * s
    stop_z = hc_z - 0.8 * s
    nose_y = stop_y + p["muzzle_length"] * s
    nose_z = stop_z - 1.8 * s
    ax = abs(x)

    # Fine procedural fur strand micro-variation (gives soft, realistic coat texture instead of flat plastic)
    fur_strand = (
        0.50 * math.sin((x * 3.8 + y * 1.4 - z * 2.1) / s)
        + 0.30 * math.cos((x * 6.5 - y * 3.2 + z * 4.4) / s)
        + 0.20 * math.sin((y * 5.2 + z * 6.1) / s)
    )

    # 1. Glossy Dark Brown Almond Eyes
    for side in (-1.0, 1.0):
        ex, ey, ez = side * 2.65 * s, hc_y + 5.15 * s, hc_z + 0.45 * s
        d_eye = math.sqrt((x - ex) ** 2 + (y - ey) ** 2 + (z - ez) ** 2)
        if d_eye <= 1.06 * s and y > ey + 0.05 * s:
            return (24.0, 17.0, 14.0), 220.0, 18.0
        # Black eye rims
        if d_eye <= 1.24 * s and y > ey - 0.10 * s:
            return (26.0, 24.0, 24.0), 30.0, 8.0

    # 2. Jet Black Nose Leather at Tip of Snout
    d_nose = math.sqrt((x / 1.55) ** 2 + ((y - (nose_y + 0.05 * s)) / 1.25) ** 2 + ((z - (nose_z + 0.45 * s)) / 1.18) ** 2)
    if d_nose <= 1.05 * s:
        return (22.0, 22.0, 25.0), 115.0, 10.0

    # 3. Pink Sideways-Lolling Tongue (on +X side of lower snout)
    if x > 0.85 * s and y > nose_y - 2.6 * s and z < nose_z - 0.85 * s and z > nose_z - 3.6 * s:
        return (226.0, 118.0, 130.0), 45.0, 8.0

    # 4. Bright White Lower Teeth Row inside Open Mouth
    if ax < 1.20 * s and y > nose_y - 1.85 * s and y < nose_y - 0.80 * s and z > nose_z - 1.95 * s and z < nose_z - 1.05 * s:
        return (242.0, 239.0, 232.0), 60.0, 10.0

    # Palette colors (R, G, B)
    cream = (228.0 + 7.0 * fur_strand, 218.0 + 7.0 * fur_strand, 200.0 + 6.0 * fur_strand)
    silver = (178.0 + 10.0 * fur_strand, 172.0 + 10.0 * fur_strand, 162.0 + 9.0 * fur_strand)
    charcoal = (52.0 + 8.0 * fur_strand, 50.0 + 8.0 * fur_strand, 52.0 + 8.0 * fur_strand)
    velvet_black = (34.0 + 4.0 * fur_strand, 32.0 + 4.0 * fur_strand, 33.0 + 4.0 * fur_strand)

    def mix_rgb(c1, c2, t):
        t = clamp(t, 0.0, 1.0)
        return (
            c1[0] + (c2[0] - c1[0]) * t,
            c1[1] + (c2[1] - c1[1]) * t,
            c1[2] + (c2[2] - c1[2]) * t,
        )

    # Start with base coat: Agouti silver-grey saddle with charcoal-tipped guard hairs
    # Darker along the dorsal spine and upper flanks, blending smoothly into silver-cream
    agouti_wave = 0.5 + 0.5 * math.sin((y * 0.42 + z * 0.28 + 0.35 * fur_strand) / s)
    base_col = mix_rgb(silver, charcoal, 0.35 + 0.45 * agouti_wave)

    # Smoothly blend in the lush Silver-Cream Lion Ruff & Chest Apron + Diagonal "Shoulder Harness" Flash
    # Ruff covers neck/chest (y in [2.5, 16.5], z in [11, 29]), plus diagonal shoulder flash down toward elbow
    d_ruff = math.sqrt(((x / 11.5) ** 2) + (((y - 9.2 * s) / 6.8) ** 2) + (((z - 20.5 * s) / 8.5) ** 2))
    ruff_w = 1.0 - smoothstep(0.65 * s, 1.25 * s, d_ruff)
    # Shoulder harness flash (diagonal cream band from base of neck ruff toward elbow at y~6, z~13)
    flash_dist = abs((y - 6.5 * s) + 0.65 * (z - 16.5 * s))
    flash_w = (1.0 - smoothstep(1.2 * s, 3.2 * s, flash_dist)) * smoothstep(11.0 * s, 15.0 * s, z) * (1.0 - smoothstep(21.0 * s, 24.0 * s, z))
    cream_coat_w = max(ruff_w, flash_w * 0.85)
    base_col = mix_rgb(base_col, cream, cream_coat_w)

    # Smoothly blend in Solid Cream Lower Legs & Paws (below wrists/hocks, z < 9.5) and Fluffy Hind Trousers
    leg_cream_w = 1.0 - smoothstep(6.2 * s, 10.5 * s, z)
    trouser_cream_w = (1.0 - smoothstep(-10.5 * s, -7.5 * s, y)) * (1.0 - smoothstep(15.5 * s, 19.5 * s, z)) * 0.78
    base_col = mix_rgb(base_col, cream, max(leg_cream_w, trouser_cream_w))

    # Smoothly blend in Rich White/Cream Plumed Tail curled over the back (with Black Tip!)
    if y < -2.0 * s and z > 22.0 * s:
        tail_w = smoothstep(22.0 * s, 25.0 * s, z) * (1.0 - smoothstep(-2.0 * s, 1.0 * s, y))
        # Black tip of the curled tail resting near the front-right of the plume (y in [-9.5, -3.5], z in [24, 30])
        d_tail_tip = math.sqrt(((x - 1.2 * s) / 3.2) ** 2 + ((y - (-6.2 * s)) / 3.5) ** 2 + ((z - 26.8 * s) / 3.2) ** 2)
        tip_black_w = 1.0 - smoothstep(0.65 * s, 1.25 * s, d_tail_tip)
        tail_col = mix_rgb(cream, velvet_black, tip_black_w * 0.92)
        base_col = mix_rgb(base_col, tail_col, tail_w)

    # Head, Cheek Ruff, Keeshond "Spectacles", Dark Muzzle Mask & Velvety Black Ears
    if y > hc_y - 3.5 * s and z > 21.5 * s:
        head_w = smoothstep(hc_y - 3.5 * s, hc_y - 0.5 * s, y) * smoothstep(21.5 * s, 24.5 * s, z)
        # Base head color is warm silver-cream / buff on cheeks and forehead
        head_col = mix_rgb(silver, cream, 0.65)

        # 1) Pale Silver-Cream Orbital "Spectacles" Rings around each eye
        ex, ey, ez = 2.65 * s, hc_y + 5.15 * s, hc_z + 0.45 * s
        d_orb = math.sqrt(((ax - ex) / 2.2) ** 2 + ((y - ey) / 2.0) ** 2 + ((z - ez) / 1.85) ** 2)
        spec_ring_w = 1.0 - smoothstep(0.55 * s, 1.15 * s, d_orb)
        head_col = mix_rgb(head_col, cream, spec_ring_w * 0.90)

        # 2) Signature Keeshond "Spectacles" Pencil Line slanting from outer eye corner (ax=3.5, y=18.2, z=29.6)
        #    back and up toward the lower outer ear corner (ax=5.0, y=13.2, z=32.4)
        t_line = clamp(((hc_y + 4.8 * s) - y) / (5.0 * s), 0.0, 1.0)
        lx = (3.45 + 1.55 * t_line) * s
        lz = (hc_z + 0.35 + 2.65 * t_line) * s
        d_line = math.sqrt((ax - lx) ** 2 + (z - lz) ** 2)
        pencil_w = (1.0 - smoothstep(0.28 * s, 0.78 * s, d_line)) * smoothstep(hc_y - 0.8 * s, hc_y + 0.5 * s, y) * (1.0 - smoothstep(hc_y + 4.6 * s, hc_y + 5.4 * s, y))
        head_col = mix_rgb(head_col, velvet_black, pencil_w * 0.88)

        # 3) Dark Muzzle Mask (covering snout, lower jaw, and nasal bridge up between the eyes)
        d_muzzle = math.sqrt(((ax / 3.45) ** 2) + (((z - (stop_z - 0.8 * s)) / 3.4) ** 2))
        muz_mask_w = smoothstep(hc_y + 3.4 * s, hc_y + 5.2 * s, y) * (1.0 - smoothstep(0.78 * s, 1.22 * s, d_muzzle))
        # Keep the pale spectacles rings bright around the eyes
        muz_mask_w *= (1.0 - 0.75 * spec_ring_w)
        head_col = mix_rgb(head_col, velvet_black, muz_mask_w * 0.94)

        # 4) Velvety Dark Charcoal-Black Pointed Triangular Ears (outer & upper ear above skull)
        ear_plane = (z - (hc_z + 3.4 * s)) + 0.38 * (ax - 2.2 * s)
        ear_w = smoothstep(0.0, 1.4 * s, ear_plane) * smoothstep(1.9 * s, 2.7 * s, ax)
        head_col = mix_rgb(head_col, velvet_black, ear_w * 0.95)

        base_col = mix_rgb(base_col, head_col, head_w)

    return base_col, 14.0, 6.0


def write_preview_svg(filepath, triangles, p):
    """Renders a clean 3/4 front portrait view of the Keeshond Dog to SVG."""
    yaw = math.radians(150.0)
    pitch = math.radians(24.0)

    def project(pt):
        x, y, z = pt
        rx = x * math.cos(yaw) - y * math.sin(yaw)
        ry = x * math.sin(yaw) + y * math.cos(yaw)
        sx = rx
        sy = -z * math.cos(pitch) - ry * math.sin(pitch)
        depth = -ry * math.cos(pitch) + z * math.sin(pitch)
        return sx, sy, depth

    light = (-0.36, 0.66, 0.65)
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
        albedo, spec_str, spec_pow = compute_keeshond_albedo_and_spec(cx, cy, cz, p)
        intensity = 0.34 + 0.66 * dot
        spec = spec_str * pow(max(0.0, dot), spec_pow)
        r = int(clamp(albedo[0] * intensity + spec, 0.0, 255.0))
        g = int(clamp(albedo[1] * intensity + spec, 0.0, 255.0))
        b = int(clamp(albedo[2] * intensity + spec, 0.0, 255.0))
        color = f"#{r:02x}{g:02x}{b:02x}"
        polys.append((avg_depth, q1, q2, q3, color))

    polys.sort(key=lambda item: item[0])

    scale = 10.6
    cx_scr, cy_scr = 400.0, 430.0
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600">',
        '  <rect width="100%" height="100%" fill="#f4f1ea"/>',
        '  <text x="24" y="36" font-family="sans-serif" font-size="20" font-weight="bold" fill="#222">Keeshond Dog Figurine (from dog.jpg) — 3D Print Model</text>',
        '  <text x="24" y="60" font-family="sans-serif" font-size="14" fill="#555">Square Spitz Profile | Fox-Like Wedge Head &amp; Spectacles | Lion Neck Ruff | Curled Plume Tail</text>',
    ]
    for _, q1, q2, q3, color in polys:
        pts = f"{cx_scr + q1[0]*scale:.2f},{cy_scr + q1[1]*scale:.2f} {cx_scr + q2[0]*scale:.2f},{cy_scr + q2[1]*scale:.2f} {cx_scr + q3[0]*scale:.2f},{cy_scr + q3[1]*scale:.2f}"
        lines.append(f'  <polygon points="{pts}" fill="{color}" stroke="{color}" stroke-width="0.35" stroke-linejoin="round"/>')
    lines.append("</svg>")

    with open(filepath, "w") as f:
        f.write("\n".join(lines))


def write_preview_png(filepath, triangles, p):
    """Renders a high-resolution, per-vertex Gouraud/Phong shaded 3/4 view of the Keeshond Dog."""
    width, height = 800, 600
    bg_r, bg_g, bg_b = 244, 241, 234
    rgb = bytearray([bg_r, bg_g, bg_b] * (width * height))
    zbuf = [-1e9] * (width * height)

    yaw = math.radians(150.0)
    pitch = math.radians(24.0)

    def project(pt):
        x, y, z = pt
        rx = x * math.cos(yaw) - y * math.sin(yaw)
        ry = x * math.sin(yaw) + y * math.cos(yaw)
        sx = rx
        sy = -z * math.cos(pitch) - ry * math.sin(pitch)
        depth = -ry * math.cos(pitch) + z * math.sin(pitch)
        return sx, sy, depth

    light = (-0.36, 0.66, 0.65)
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

    v_colors = {}
    for key, acc in v_normals.items():
        ln = math.sqrt(acc[0] * acc[0] + acc[1] * acc[1] + acc[2] * acc[2])
        if ln > 1e-12:
            acc[0] /= ln
            acc[1] /= ln
            acc[2] /= ln
        nx, ny, nz = acc
        vnx = nx * math.cos(yaw) - ny * math.sin(yaw)
        vny = nx * math.sin(yaw) + ny * math.cos(yaw)
        snx = vnx
        sny = nz * math.cos(pitch) + vny * math.sin(pitch)
        snz = -vny * math.cos(pitch) + nz * math.sin(pitch)
        dot = max(0.0, snx * light[0] + sny * light[1] + snz * light[2])
        # Rim/fill light for soft studio portrait look
        fill = max(0.0, -0.5 * snx - 0.3 * sny + 0.4 * snz) * 0.14
        albedo, spec_str, spec_pow = compute_keeshond_albedo_and_spec(key[0], key[1], key[2], p)
        intensity = 0.34 + 0.66 * dot + fill
        spec = spec_str * pow(max(0.0, dot), spec_pow)
        r = clamp(albedo[0] * intensity + spec, 0.0, 255.0)
        g = clamp(albedo[1] * intensity + spec, 0.0, 255.0)
        b = clamp(albedo[2] * intensity + spec, 0.0, 255.0)
        v_colors[key] = (r, g, b)

    scale = 11.2
    cx_scr, cy_scr = 400.0, 445.0

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
    tris = build_keeshond_dog_sdf(PARAMS)
    stats = verify_manifold(tris)
    print("Mesh Verification:", stats)
    if not stats["is_watertight_manifold"]:
        raise RuntimeError(f"Mesh failed manifold check: {stats}")

    stl_path = os.path.join(out_dir, "keeshond_dog.stl")
    threemf_path = os.path.join(out_dir, "keeshond_dog.3mf")
    scad_path = os.path.join(out_dir, "keeshond_dog.scad")
    svg_path = os.path.join(out_dir, "keeshond_dog_preview.svg")
    png_path = os.path.join(out_dir, "keeshond_dog_preview.png")

    write_binary_stl(stl_path, tris)
    write_3mf(threemf_path, tris)
    write_openscad(scad_path, PARAMS)
    write_preview_svg(svg_path, tris, PARAMS)
    write_preview_png(png_path, tris, PARAMS)
    print(f"Successfully generated:\n  - {stl_path}\n  - {threemf_path}\n  - {scad_path}\n  - {svg_path}\n  - {png_path}")

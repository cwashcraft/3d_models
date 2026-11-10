#!/usr/bin/env python3
"""
Parametric 3D Model Generator for a Cute Tiny Jumping Spider (Salticidae).
Designed for support-free FDM 3D printing on Bambu Lab A1 Mini / MakerWorld.

Generates:
  1. tiny_jumping_spider.stl         (Watertight 2-Manifold Binary STL)
  2. tiny_jumping_spider.3mf         (Bambu Studio / Bambu Handy / MakerWorld 3MF)
  3. tiny_jumping_spider.scad        (Parametric OpenSCAD source)
  4. tiny_jumping_spider_preview.svg (Isometric shaded vector preview)
  5. tiny_jumping_spider_preview.png (Multi-material shaded raster preview with big glossy eyes)

Coordinate System (Print Orientation - flat on build plate Z = 0, no supports needed):
  X: Left (-) to Right (+), centered at X = 0
  Y: Back/Abdomen (-) to Front/Face (+), centered near Y = 0
  Z: Build plate (Z = 0) to top of head/eyes (Z = +height)
"""

import math
import os
import struct
import zipfile
import zlib

# ==============================================================================
# PARAMETRIC DIMENSIONS (in millimeters)
# Adjust these values and re-run `python3 generate_jumping_spider.py` to customize!
# ==============================================================================
PARAMS = {
    "scale_factor": 1.0,           # Overall uniform scale factor (1.0 = ~37 x 32 x 12 mm)
    "voxel_size": 0.26,            # Fine SDF surface extraction grid resolution (mm)

    # Cephalothorax (head / prosoma)
    "head_width": 11.6,            # Width of boxy-rounded jumping spider head (mm)
    "head_length": 10.6,           # Length of cephalothorax (mm)
    "head_height": 11.0,           # Total height of cephalothorax dome from Z=0 (mm)
    "head_center_y": 3.5,          # Y center of cephalothorax (mm)

    # Abdomen (opisthosoma)
    "abdomen_width": 12.2,         # Width of plump oval abdomen (mm)
    "abdomen_length": 13.6,        # Length of abdomen (mm)
    "abdomen_height": 10.6,        # Height of abdomen from Z=0 (mm)
    "abdomen_center_y": -6.8,      # Y center of abdomen (mm)

    # Characteristic Salticidae eyes (anterior median + anterior lateral + lateral)
    "ame_radius": 1.80,            # Huge front-center "Lucas" eyes radius (mm)
    "ale_radius": 1.08,            # Front-outer eyes radius (mm)
    "ple_radius": 0.92,            # Side-rear eyes radius (mm)

    # Legs & Pedipalps (pure round articulated tubes - no blocky curtains!)
    "leg_thickness": 1.42,         # Base radius of round jumping spider legs (mm)
    "pedipalp_radius": 1.35,       # Radius of front fuzzy feeler pedipalps (mm)
}


def smin(a, b, k):
    """Quadratic polynomial smooth minimum for organic SDF blending."""
    if k <= 1e-6:
        return a if a < b else b
    h = max(0.0, k - abs(a - b)) / k
    return (a if a < b else b) - h * h * k * 0.25


def smax(a, b, k):
    """Smooth maximum (for organic carving/grooves)."""
    return -smin(-a, -b, k)


def build_jumping_spider_sdf(p):
    """
    Evaluates a high-detail Signed Distance Field (SDF) of a tiny jumping spider
    with purely round, organic articulated legs (no blocky under-curtains), then extracts
    a guaranteed watertight 2-manifold triangle mesh via topology-repaired Surface Nets.
    """
    s = p["scale_factor"]
    h = p["voxel_size"] * s

    # Bounding domain in mm (with outer margin so boundary is strictly outside)
    x_min, x_max = -20.5 * s, 20.5 * s
    y_min, y_max = -18.0 * s, 17.5 * s
    z_min, z_max = 0.0, 13.8 * s

    nx = int(math.ceil((x_max - x_min) / h)) + 1
    ny = int(math.ceil((y_max - y_min) / h)) + 1
    nz = int(math.ceil((z_max - z_min) / h)) + 2  # k=0 is below Z=0, k=1 is above Z=0

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
    # Helper 1: Smooth Ellipsoid with optional bottom support bevel to Z = 0
    # --------------------------------------------------------------------------
    def add_ellipsoid(cx, cy, cz, rx, ry, rz, blend_k, support_to_bed=False, taper_x=0.0):
        margin = blend_k + h * 2.5
        rx_r = idx_range(cx - rx - margin, cx + rx + margin, x_min, h, nx)
        ry_r = idx_range(cy - ry - margin, cy + ry + margin, y_min, h, ny)
        z_low = 0.0 if support_to_bed else (cz - rz - margin)
        rz_r = z_range(z_low, cz + rz + margin)

        r_avg = (rx + ry + rz) / 3.0
        inv_rx, inv_ry, inv_rz = 1.0 / rx, 1.0 / ry, 1.0 / rz

        for i in rx_r:
            x = xs[i]
            dx0 = x - cx
            base_i = i * ny * nz
            for j in ry_r:
                y = ys[j]
                dy = (y - cy) * inv_ry
                width_scale = 1.0 + taper_x * dy
                dx = dx0 / (rx * max(0.6, width_scale))
                dxy2 = dx * dx + dy * dy
                if dxy2 > 4.0:
                    continue
                base_ij = base_i + j * nz
                for k in rz_r:
                    z = zs[k]
                    if support_to_bed and z < cz:
                        dz = (z - cz) / (rz * 1.16)
                        d_norm = math.sqrt(dxy2 + dz * dz)
                    else:
                        dz = (z - cz) * inv_rz
                        d_norm = math.sqrt(dxy2 + dz * dz)
                    d = (d_norm - 1.0) * r_avg
                    cur = sdf[base_ij + k]
                    sdf[base_ij + k] = smin(cur, d, blend_k)

    # --------------------------------------------------------------------------
    # Helper 2: Pure Round Tapered Capsule (A -> B) with organic mid-belly swell
    #   No curtains or flat fins underneath!
    # --------------------------------------------------------------------------
    def add_round_capsule(ax, ay, az, bx, by, bz, ra, rb, blend_k, mid_swell=0.0):
        r_max = max(ra, rb) * (1.0 + max(0.0, mid_swell))
        margin = r_max + blend_k + h * 2.5
        rx_r = idx_range(min(ax, bx) - margin, max(ax, bx) + margin, x_min, h, nx)
        ry_r = idx_range(min(ay, by) - margin, max(ay, by) + margin, y_min, h, ny)
        rz_r = z_range(max(0.0, min(az, bz) - margin), max(az, bz) + margin)

        abx, aby, abz = bx - ax, by - ay, bz - az
        ab_len2 = abx * abx + aby * aby + abz * abz

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
                        t = max(0.0, min(1.0, (pxy_dot + paz * abz) / ab_len2))
                    else:
                        t = 0.0
                    qx = pax - t * abx
                    qy = pay - t * aby
                    qz = paz - t * abz
                    # Smooth organic muscle belly profile along the segment: 4*t*(1-t) peaks at t=0.5
                    r_t = (ra + t * (rb - ra)) * (1.0 + mid_swell * 4.0 * t * (1.0 - t))
                    d_cap = math.sqrt(qx * qx + qy * qy + qz * qz) - r_t

                    cur = sdf[base_ij + k]
                    sdf[base_ij + k] = smin(cur, d_cap, blend_k)

    # --------------------------------------------------------------------------
    # Helper 3: Carve subtle joint ring crease between leg segments
    #   Makes each leg look articulated (distinct femur / patella / tibia / tarsus)
    # --------------------------------------------------------------------------
    def carve_joint_crease(jx, jy, jz, tx_dir, ty_dir, tz_dir, seg_radius, crease_depth=0.22):
        t_len = math.sqrt(tx_dir * tx_dir + ty_dir * ty_dir + tz_dir * tz_dir)
        if t_len < 1e-8:
            return
        tx_dir, ty_dir, tz_dir = tx_dir / t_len, ty_dir / t_len, tz_dir / t_len
        margin = seg_radius * 1.5 + h * 2.0
        rx_r = idx_range(jx - margin, jx + margin, x_min, h, nx)
        ry_r = idx_range(jy - margin, jy + margin, y_min, h, ny)
        rz_r = z_range(max(0.0, jz - margin), jz + margin)

        ring_major = seg_radius * 1.02
        ring_minor = crease_depth * s

        for i in rx_r:
            dx = xs[i] - jx
            base_i = i * ny * nz
            for j in ry_r:
                dy = ys[j] - jy
                base_ij = base_i + j * nz
                for k in rz_r:
                    dz = zs[k] - jz
                    along = dx * tx_dir + dy * ty_dir + dz * tz_dir
                    perp2 = max(0.0, dx * dx + dy * dy + dz * dz - along * along)
                    perp = math.sqrt(perp2)
                    d_torus = math.hypot(perp - ring_major, along) - ring_minor
                    cur = sdf[base_ij + k]
                    sdf[base_ij + k] = smax(cur, -d_torus, 0.12 * s)

    # --------------------------------------------------------------------------
    # Helper 4: Eye Dome + Raised Socket Rim (gives unmistakable Lucas-style eyes)
    # --------------------------------------------------------------------------
    def add_eye_with_rim(ex, ey, ez, nx_dir, ny_dir, nz_dir, radius):
        n_len = math.sqrt(nx_dir * nx_dir + ny_dir * ny_dir + nz_dir * nz_dir)
        nx_dir, ny_dir, nz_dir = nx_dir / n_len, ny_dir / n_len, nz_dir / n_len

        margin = radius * 1.6 + h * 2.5
        rx_r = idx_range(ex - margin, ex + margin, x_min, h, nx)
        ry_r = idx_range(ey - margin, ey + margin, y_min, h, ny)
        rz_r = z_range(ez - margin, ez + margin)

        for i in rx_r:
            x = xs[i]
            dx = x - ex
            base_i = i * ny * nz
            for j in ry_r:
                y = ys[j]
                dy = y - ey
                base_ij = base_i + j * nz
                for k in rz_r:
                    z = zs[k]
                    dz = z - ez
                    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                    d_ball = dist - radius

                    along = dx * nx_dir + dy * ny_dir + dz * nz_dir
                    perp2 = max(0.0, dist * dist - along * along)
                    perp = math.sqrt(perp2)
                    ring_r = math.hypot(perp - radius * 1.02, along + radius * 0.18) - (radius * 0.24)
                    groove_r = math.hypot(perp - radius * 0.88, along - radius * 0.22) - (radius * 0.14)

                    cur = sdf[base_ij + k]
                    cur = smin(cur, ring_r, 0.25 * s)
                    cur = smax(cur, -groove_r, 0.12 * s)
                    sdf[base_ij + k] = smin(cur, d_ball, 0.15 * s)

    # ==========================================================================
    # 1. CEPHALOTHORAX (Boxy-Rounded High-Domed Salticidae Head)
    # ==========================================================================
    hc_y = p["head_center_y"] * s
    hw = (p["head_width"] * 0.5) * s
    hl = (p["head_length"] * 0.5) * s
    hh = (p["head_height"] * 0.5) * s

    add_ellipsoid(0.0, hc_y, hh * 1.02, hw, hl, hh, blend_k=0.8 * s, support_to_bed=True, taper_x=0.14)
    add_ellipsoid(0.0, hc_y + 2.1 * s, hh * 1.38, hw * 0.86, hl * 0.58, hh * 0.55, blend_k=1.2 * s, support_to_bed=False)
    for side in (-1.0, 1.0):
        add_round_capsule(
            side * 0.6 * s, hc_y + 4.9 * s, 9.0 * s,
            side * 3.8 * s, hc_y + 4.1 * s, 8.7 * s,
            0.76 * s, 0.66 * s, blend_k=0.55 * s
        )

    # ==========================================================================
    # 2. PLUMP OVAL ABDOMEN + PEDICEL WAIST + DORSAL CHEVRONS + SPINNERETS
    # ==========================================================================
    ac_y = p["abdomen_center_y"] * s
    aw = (p["abdomen_width"] * 0.5) * s
    al = (p["abdomen_length"] * 0.5) * s
    ah = (p["abdomen_height"] * 0.5) * s

    add_ellipsoid(0.0, ac_y, ah * 1.0, aw, al, ah, blend_k=0.9 * s, support_to_bed=True, taper_x=-0.08)
    add_round_capsule(0.0, -1.6 * s, 2.5 * s, 0.0, 0.9 * s, 2.8 * s, 3.0 * s, 3.2 * s, blend_k=1.1 * s)

    chevron_ys = [-4.2 * s, -6.4 * s, -8.6 * s, -10.6 * s]
    chevron_ws = [3.8 * s, 4.2 * s, 3.5 * s, 2.4 * s]
    chevron_zs = [9.7 * s, 10.1 * s, 9.4 * s, 8.0 * s]
    for cy_band, cw_band, cz_band in zip(chevron_ys, chevron_ws, chevron_zs):
        for side in (-1.0, 1.0):
            add_round_capsule(
                0.0, cy_band + 0.85 * s, cz_band,
                side * cw_band, cy_band - 0.55 * s, cz_band - 1.15 * s,
                0.52 * s, 0.40 * s, blend_k=0.42 * s
            )

    for side in (-1.0, 1.0):
        add_round_capsule(
            side * 1.15 * s, ac_y - al + 1.2 * s, 1.8 * s,
            side * 1.05 * s, ac_y - al - 0.85 * s, 2.8 * s,
            1.05 * s, 0.72 * s, blend_k=0.55 * s
        )

    # ==========================================================================
    # 3. CHELICERAE (Front Jaws) & FUZZY PEDIPALPS ("Mittens" - Pure Round Tubes)
    # ==========================================================================
    for side in (-1.0, 1.0):
        # Stout vertical chelicerae directly beneath the huge front eyes
        add_round_capsule(
            side * 1.35 * s, hc_y + 5.0 * s, 4.6 * s,
            side * 1.20 * s, hc_y + 5.2 * s, 1.15 * s,
            1.30 * s, 1.02 * s, blend_k=0.50 * s, mid_swell=0.10
        )
        # Plump curved pedipalps flanking the chelicerae and resting on Z=0 in front
        px0, py0, pz0 = side * 3.3 * s, hc_y + 4.2 * s, 2.6 * s
        px1, py1, pz1 = side * 3.9 * s, hc_y + 6.5 * s, 3.2 * s
        px2, py2, pz2 = side * 2.3 * s, hc_y + 8.0 * s, 1.25 * s
        pr = p["pedipalp_radius"] * s
        add_round_capsule(px0, py0, pz0, px1, py1, pz1, pr * 0.82, pr * 0.96, blend_k=0.45 * s, mid_swell=0.08)
        add_round_capsule(px1, py1, pz1, px2, py2, pz2, pr * 0.98, pr * 1.12, blend_k=0.35 * s, mid_swell=0.18)

    # ==========================================================================
    # 4. SIGNATURE 8 JUMPING SPIDER EYES (4 Front Row + 4 Side Row)
    # ==========================================================================
    ame_r = p["ame_radius"] * s
    ale_r = p["ale_radius"] * s
    ple_r = p["ple_radius"] * s

    for side in (-1.0, 1.0):
        add_eye_with_rim(
            side * 1.85 * s, hc_y + 5.15 * s, 6.75 * s,
            side * 0.16, 0.97, 0.16, ame_r
        )
        add_eye_with_rim(
            side * 4.25 * s, hc_y + 4.25 * s, 7.15 * s,
            side * 0.48, 0.85, 0.20, ale_r
        )
        add_eye_with_rim(
            side * 5.20 * s, hc_y + 2.10 * s, 7.70 * s,
            side * 0.92, 0.25, 0.30, ple_r * 0.62
        )
        add_eye_with_rim(
            side * 5.30 * s, hc_y - 0.15 * s, 7.55 * s,
            side * 0.90, -0.15, 0.40, ple_r
        )

    # ==========================================================================
    # 5. EIGHT ORGANIC, ROUND ARTICULATED JUMPING SPIDER LEGS (ZERO BLOCKINESS!)
    #    Each leg consists of 4 distinct round anatomical segments:
    #      1. Coxa (hip socket emerging low on the cephalothorax at Z = 1.65mm)
    #      2. Femur (plump muscular thigh rising at ~40° to the knee at Z = 5.4mm)
    #      3. Patella + Tibia (tapering lower leg angling down at ~44° to the ankle)
    #      4. Metatarsus + Tarsus (cute rounded spider paw pad resting on Z = 0)
    #    Because Coxa and Ankle rest on Z = 0 and the round tubes meet at ~42°,
    #    there is NO blocky curtain underneath—just clean round cylindrical legs!
    # ==========================================================================
    lr = p["leg_thickness"] * s
    # Each tuple: (coxa_xyz, knee_xyz, tibia_mid_xyz, ankle_xyz, paw_xyz, scale_r)
    leg_specs = [
        # Pair 1 (Front legs - reaching forward & outward in a friendly wave)
        (
            (4.5 * s, 5.8 * s, 1.75 * s),
            (8.6 * s, 8.8 * s, 5.35 * s),
            (11.6 * s, 11.2 * s, 3.25 * s),
            (13.8 * s, 12.9 * s, 1.25 * s),
            (15.6 * s, 14.3 * s, 1.05 * s),
            1.08,
        ),
        # Pair 2 (Mid-front legs - wide poised stance)
        (
            (5.1 * s, 3.8 * s, 1.70 * s),
            (10.0 * s, 5.0 * s, 5.15 * s),
            (13.2 * s, 5.8 * s, 3.15 * s),
            (15.6 * s, 6.4 * s, 1.20 * s),
            (17.5 * s, 6.9 * s, 1.00 * s),
            1.00,
        ),
        # Pair 3 (Mid-back legs - sweeping outward)
        (
            (5.0 * s, 1.6 * s, 1.70 * s),
            (9.8 * s, -0.6 * s, 5.05 * s),
            (13.0 * s, -1.9 * s, 3.10 * s),
            (15.4 * s, -2.9 * s, 1.20 * s),
            (17.3 * s, -3.7 * s, 1.00 * s),
            0.98,
        ),
        # Pair 4 (Rear jumping legs - muscular hind legs sweeping back)
        (
            (4.4 * s, -0.4 * s, 1.75 * s),
            (8.8 * s, -5.2 * s, 5.45 * s),
            (11.6 * s, -8.8 * s, 3.30 * s),
            (13.8 * s, -11.5 * s, 1.25 * s),
            (15.4 * s, -13.7 * s, 1.05 * s),
            1.10,
        ),
    ]

    for coxa_pt, knee_pt, mid_pt, ankle_pt, paw_pt, r_mult in leg_specs:
        r_base = lr * r_mult
        for side in (-1.0, 1.0):
            cx0, cy0, cz0 = side * coxa_pt[0], coxa_pt[1], coxa_pt[2]
            kx, ky, kz = side * knee_pt[0], knee_pt[1], knee_pt[2]
            mx, my, mz = side * mid_pt[0], mid_pt[1], mid_pt[2]
            ax, ay, az = side * ankle_pt[0], ankle_pt[1], ankle_pt[2]
            px, py, pz = side * paw_pt[0], paw_pt[1], paw_pt[2]

            # 1. Coxa / Trochanter bump at body socket
            add_ellipsoid(
                cx0 * 0.95, cy0, cz0 + 0.35 * s,
                r_base * 1.15, r_base * 1.15, r_base * 1.10,
                blend_k=0.45 * s, support_to_bed=True
            )

            # 2. Plump muscular Femur (coxa -> elevated knee, with natural muscle belly swell)
            add_round_capsule(
                cx0, cy0, cz0, kx, ky, kz,
                r_base * 0.96, r_base * 1.05,
                blend_k=0.38 * s, mid_swell=0.16
            )

            # 3. Patella (rounded knee cap joint)
            add_ellipsoid(
                kx, ky, kz,
                r_base * 1.08, r_base * 1.08, r_base * 1.06,
                blend_k=0.25 * s, support_to_bed=False
            )

            # 4. Upper Tibia (knee -> tibia-metatarsus joint, with subtle muscle swell)
            add_round_capsule(
                kx, ky, kz, mx, my, mz,
                r_base * 0.96, r_base * 0.84,
                blend_k=0.30 * s, mid_swell=0.12
            )

            # 5. Metatarsus (tibia-mid -> ankle on bed)
            add_round_capsule(
                mx, my, mz, ax, ay, az,
                r_base * 0.82, r_base * 0.74,
                blend_k=0.28 * s, mid_swell=0.06
            )

            # 6. Tarsus (cute rounded spider paw pad resting flat on Z=0)
            add_round_capsule(
                ax, ay, az, px, py, pz,
                r_base * 0.76, r_base * 0.90,
                blend_k=0.32 * s, mid_swell=0.14
            )

            # Subtle articulated joint creases at Knee (Patella) and Mid-Tibia
            carve_joint_crease(
                kx, ky, kz,
                mx - cx0, my - cy0, mz - cz0,
                r_base * 1.04, crease_depth=0.18
            )
            carve_joint_crease(
                mx, my, mz,
                ax - kx, ay - ky, az - kz,
                r_base * 0.83, crease_depth=0.15
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

    # Keep only the main connected component of `inside` voxels
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

    # Repair any rare checkerboard primal faces (T, F, T, F)
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

    # Multi-pass volume-preserving Taubin fairing for silky-smooth organic curvature
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
    return {
        "num_triangles": len(triangles),
        "unmatched_directed_edges": unmatched_directed,
        "non_manifold_edges": non_manifold_undirected,
        "volume_cm3": round(volume_mm3 / 1000.0, 3),
        "is_watertight_manifold": (unmatched_directed == 0 and non_manifold_undirected == 0 and volume_mm3 > 0),
    }


def write_binary_stl(filepath, triangles):
    """Writes a standard binary STL file."""
    header = b"Tiny Jumping Spider (Salticidae) - Support-Free Bambu Ready".ljust(80, b"\x00")
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
  <metadata name="Title">Tiny Jumping Spider (Support-Free Print)</metadata>
  <metadata name="Application">BambuStudio</metadata>
  <resources>
    <object id="1" type="model" name="Tiny_Jumping_Spider">
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
    """Writes a parametric OpenSCAD source file for the Tiny Jumping Spider."""
    scad = f"""// ============================================================================
// Tiny Jumping Spider (Salticidae) - Parametric OpenSCAD Source
// Support-Free Print Orientation: Flat on Z = 0 build plate
// Purely round articulated capsule legs (coxa -> femur -> patella -> tibia -> paw)
// ============================================================================

scale_factor     = {p["scale_factor"]};
head_width       = {p["head_width"]};
head_length      = {p["head_length"]};
head_height      = {p["head_height"]};
head_center_y    = {p["head_center_y"]};

abdomen_width    = {p["abdomen_width"]};
abdomen_length   = {p["abdomen_length"]};
abdomen_height   = {p["abdomen_height"]};
abdomen_center_y = {p["abdomen_center_y"]};

ame_radius       = {p["ame_radius"]};
ale_radius       = {p["ale_radius"]};
ple_radius       = {p["ple_radius"]};
leg_thickness    = {p["leg_thickness"]};
pedipalp_radius  = {p["pedipalp_radius"]};

$fn = 48;

module round_capsule(a, b, ra, rb) {{
    hull() {{
        translate(a) sphere(r=ra);
        translate(b) sphere(r=rb);
    }}
}}

scale([scale_factor, scale_factor, scale_factor])
intersection() {{
    translate([-50, -50, 0]) cube([100, 100, 50]); // Flat base at Z = 0
    union() {{
        // Cephalothorax
        hull() {{
            translate([0, head_center_y, head_height*0.5])
                scale([head_width/2, head_length/2, head_height/2]) sphere(r=1);
            translate([0, head_center_y + 2.1, head_height*0.68])
                scale([head_width*0.43, head_length*0.29, head_height*0.27]) sphere(r=1);
            translate([0, head_center_y, 0])
                scale([head_width*0.38, head_length*0.38, 0.2]) cylinder(r=1, h=1);
        }}

        // Abdomen
        hull() {{
            translate([0, abdomen_center_y, abdomen_height*0.5])
                scale([abdomen_width/2, abdomen_length/2, abdomen_height/2]) sphere(r=1);
            translate([0, abdomen_center_y, 0])
                scale([abdomen_width*0.40, abdomen_length*0.40, 0.2]) cylinder(r=1, h=1);
        }}

        // 8 Jumping Spider Eyes (AME, ALE, PME, PLE)
        for (side = [-1, 1]) {{
            translate([side * 1.85, head_center_y + 5.15, 6.75]) sphere(r=ame_radius);
            translate([side * 4.25, head_center_y + 4.25, 7.15]) sphere(r=ale_radius);
            translate([side * 5.20, head_center_y + 2.10, 7.70]) sphere(r=ple_radius*0.62);
            translate([side * 5.30, head_center_y - 0.15, 7.55]) sphere(r=ple_radius);

            // Chelicerae & Pedipalps
            round_capsule([side*1.35, head_center_y+5.0, 4.6], [side*1.2, head_center_y+5.2, 1.15], 1.30, 1.02);
            round_capsule([side*3.3, head_center_y+4.2, 2.6], [side*3.9, head_center_y+6.5, 3.2], pedipalp_radius*0.82, pedipalp_radius*0.96);
            round_capsule([side*3.9, head_center_y+6.5, 3.2], [side*2.3, head_center_y+8.0, 1.25], pedipalp_radius*0.98, pedipalp_radius*1.12);

            // 4 Pairs of Round Articulated Legs
            round_capsule([side*4.5, 5.8, 1.75], [side*8.6, 8.8, 5.35], leg_thickness*1.04, leg_thickness*1.12);
            round_capsule([side*8.6, 8.8, 5.35], [side*11.6, 11.2, 3.25], leg_thickness*1.04, leg_thickness*0.90);
            round_capsule([side*11.6, 11.2, 3.25], [side*13.8, 12.9, 1.25], leg_thickness*0.88, leg_thickness*0.80);
            round_capsule([side*13.8, 12.9, 1.25], [side*15.6, 14.3, 1.05], leg_thickness*0.82, leg_thickness*0.96);

            round_capsule([side*5.1, 3.8, 1.70], [side*10.0, 5.0, 5.15], leg_thickness*0.96, leg_thickness*1.05);
            round_capsule([side*10.0, 5.0, 5.15], [side*13.2, 5.8, 3.15], leg_thickness*0.96, leg_thickness*0.84);
            round_capsule([side*13.2, 5.8, 3.15], [side*15.6, 6.4, 1.20], leg_thickness*0.82, leg_thickness*0.74);
            round_capsule([side*15.6, 6.4, 1.20], [side*17.5, 6.9, 1.00], leg_thickness*0.76, leg_thickness*0.90);

            round_capsule([side*5.0, 1.6, 1.70], [side*9.8, -0.6, 5.05], leg_thickness*0.94, leg_thickness*1.02);
            round_capsule([side*9.8, -0.6, 5.05], [side*13.0, -1.9, 3.10], leg_thickness*0.94, leg_thickness*0.82);
            round_capsule([side*13.0, -1.9, 3.10], [side*15.4, -2.9, 1.20], leg_thickness*0.80, leg_thickness*0.72);
            round_capsule([side*15.4, -2.9, 1.20], [side*17.3, -3.7, 1.00], leg_thickness*0.74, leg_thickness*0.88);

            round_capsule([side*4.4, -0.4, 1.75], [side*8.8, -5.2, 5.45], leg_thickness*1.06, leg_thickness*1.15);
            round_capsule([side*8.8, -5.2, 5.45], [side*11.6, -8.8, 3.30], leg_thickness*1.06, leg_thickness*0.92);
            round_capsule([side*11.6, -8.8, 3.30], [side*13.8, -11.5, 1.25], leg_thickness*0.90, leg_thickness*0.82);
            round_capsule([side*13.8, -11.5, 1.25], [side*15.4, -13.7, 1.05], leg_thickness*0.84, leg_thickness*0.98);
        }}
    }}
}}
"""
    with open(filepath, "w") as f:
        f.write(scad)


def classify_spider_region(cx, cy, cz, p):
    """Classifies triangle centroid into Eye / Chevron / Body for rich preview rendering."""
    s = p["scale_factor"]
    hc_y = p["head_center_y"] * s
    ax = abs(cx)

    eyes = [
        (1.85 * s, hc_y + 5.15 * s, 6.75 * s, p["ame_radius"] * s * 0.92),
        (4.25 * s, hc_y + 4.25 * s, 7.15 * s, p["ale_radius"] * s * 0.92),
        (5.20 * s, hc_y + 2.10 * s, 7.70 * s, p["ple_radius"] * s * 0.58),
        (5.30 * s, hc_y - 0.15 * s, 7.55 * s, p["ple_radius"] * s * 0.90),
    ]
    for ex, ey, ez, er in eyes:
        if (ax - ex) ** 2 + (cy - ey) ** 2 + (cz - ez) ** 2 <= (er + 0.18 * s) ** 2:
            if ax > ex - 0.35 * s and (cy > ey + 0.15 * s or ax > 4.6 * s):
                return "eye"

    if cy < -3.0 * s and cz > 8.4 * s and ax < 4.5 * s:
        return "chevron"

    return "body"


def write_preview_svg(filepath, triangles, p):
    """Renders a high-detail isometric 3/4 front view of the Tiny Jumping Spider to SVG."""
    yaw = math.radians(146.0)
    pitch = math.radians(26.0)

    def project(pt):
        x, y, z = pt
        rx = x * math.cos(yaw) - y * math.sin(yaw)
        ry = x * math.sin(yaw) + y * math.cos(yaw)
        sx = rx
        sy = -z * math.cos(pitch) - ry * math.sin(pitch)
        depth = -ry * math.cos(pitch) + z * math.sin(pitch)
        return sx, sy, depth

    light = (-0.42, 0.72, 0.55)
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
        region = classify_spider_region(cx, cy, cz, p)
        if region == "eye":
            spec = pow(max(0.0, dot), 14.0)
            r = int(min(255, 22 + 55 * dot + 210 * spec))
            g = int(min(255, 28 + 65 * dot + 210 * spec))
            b = int(min(255, 38 + 80 * dot + 215 * spec))
        elif region == "chevron":
            intensity = 0.30 + 0.70 * dot
            r = int(min(255, 195 * intensity + 22))
            g = int(min(255, 138 * intensity + 16))
            b = int(min(255, 88 * intensity + 12))
        else:
            intensity = 0.28 + 0.72 * dot
            r = int(min(255, 148 * intensity + 22))
            g = int(min(255, 106 * intensity + 18))
            b = int(min(255, 76 * intensity + 15))

        color = f"#{r:02x}{g:02x}{b:02x}"
        polys.append((avg_depth, q1, q2, q3, color))

    polys.sort(key=lambda item: item[0])

    scale = 15.0
    cx_scr, cy_scr = 400.0, 315.0
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="560" viewBox="0 0 800 560">',
        '  <rect width="100%" height="100%" fill="#f4f5f7"/>',
        '  <text x="24" y="36" font-family="sans-serif" font-size="20" font-weight="bold" fill="#222">Tiny Jumping Spider (Salticidae) — Round Articulated Legs</text>',
        '  <text x="24" y="60" font-family="sans-serif" font-size="14" fill="#555">Footprint: 35 x 31 x 11.2 mm | 8 Sculpted Eyes + Pedipalps + 8 Segmented Round Legs | Watertight 2-Manifold</text>',
    ]
    for _, q1, q2, q3, color in polys:
        pts = f"{cx_scr + q1[0]*scale:.2f},{cy_scr + q1[1]*scale:.2f} {cx_scr + q2[0]*scale:.2f},{cy_scr + q2[1]*scale:.2f} {cx_scr + q3[0]*scale:.2f},{cy_scr + q3[1]*scale:.2f}"
        lines.append(f'  <polygon points="{pts}" fill="{color}" stroke="{color}" stroke-width="0.35" stroke-linejoin="round"/>')
    lines.append("</svg>")

    with open(filepath, "w") as f:
        f.write("\n".join(lines))


def write_preview_png(filepath, triangles, p):
    """Renders a crisp, z-buffered 3/4 front view of the Tiny Jumping Spider with smooth Phong vertex normals."""
    width, height = 800, 560
    bg_r, bg_g, bg_b = 244, 245, 247
    rgb = bytearray([bg_r, bg_g, bg_b] * (width * height))
    zbuf = [-1e9] * (width * height)

    yaw = math.radians(146.0)
    pitch = math.radians(26.0)

    def project(pt):
        x, y, z = pt
        rx = x * math.cos(yaw) - y * math.sin(yaw)
        ry = x * math.sin(yaw) + y * math.cos(yaw)
        sx = rx
        sy = -z * math.cos(pitch) - ry * math.sin(pitch)
        depth = -ry * math.cos(pitch) + z * math.sin(pitch)
        return sx, sy, depth

    light = (-0.42, 0.72, 0.55)
    l_norm = math.sqrt(sum(c * c for c in light))
    light = tuple(c / l_norm for c in light)

    # Compute smooth vertex normals for realistic shading
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

    scale = 15.6
    cx_scr, cy_scr = 400.0, 315.0

    for p1, p2, p3 in triangles:
        k1 = (round(p1[0], 4), round(p1[1], 4), round(p1[2], 4))
        k2 = (round(p2[0], 4), round(p2[1], 4), round(p2[2], 4))
        k3 = (round(p3[0], 4), round(p3[1], 4), round(p3[2], 4))
        n1, n2, n3 = v_normals[k1], v_normals[k2], v_normals[k3]
        nx = (n1[0] + n2[0] + n3[0]) / 3.0
        ny = (n1[1] + n2[1] + n3[1]) / 3.0
        nz = (n1[2] + n2[2] + n3[2]) / 3.0
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln < 1e-9:
            continue
        nx, ny, nz = nx / ln, ny / ln, nz / ln

        q1 = project(p1)
        q2 = project(p2)
        q3 = project(p3)

        x1, y1, z1 = cx_scr + q1[0] * scale, cy_scr + q1[1] * scale, q1[2]
        x2, y2, z2 = cx_scr + q2[0] * scale, cy_scr + q2[1] * scale, q2[2]
        x3, y3, z3 = cx_scr + q3[0] * scale, cy_scr + q3[1] * scale, q3[2]

        denom = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
        if abs(denom) < 1e-6:
            continue

        cx = (p1[0] + p2[0] + p3[0]) / 3.0
        cy = (p1[1] + p2[1] + p3[1]) / 3.0
        cz = (p1[2] + p2[2] + p3[2]) / 3.0

        vnx = nx * math.cos(yaw) - ny * math.sin(yaw)
        vny = nx * math.sin(yaw) + ny * math.cos(yaw)
        snx = vnx
        sny = nz * math.cos(pitch) + vny * math.sin(pitch)
        snz = -vny * math.cos(pitch) + nz * math.sin(pitch)

        dot = max(0.0, snx * light[0] + sny * light[1] + snz * light[2])
        region = classify_spider_region(cx, cy, cz, p)
        if region == "eye":
            spec = pow(max(0.0, dot), 16.0)
            r = int(min(255, 18 + 48 * dot + 220 * spec))
            g = int(min(255, 24 + 58 * dot + 220 * spec))
            b = int(min(255, 35 + 75 * dot + 225 * spec))
        elif region == "chevron":
            intensity = 0.30 + 0.70 * dot
            r = int(min(255, 195 * intensity + 22))
            g = int(min(255, 138 * intensity + 16))
            b = int(min(255, 88 * intensity + 12))
        else:
            intensity = 0.28 + 0.72 * dot
            r = int(min(255, 148 * intensity + 22))
            g = int(min(255, 106 * intensity + 18))
            b = int(min(255, 76 * intensity + 15))

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
                        rgb[idx * 3] = r
                        rgb[idx * 3 + 1] = g
                        rgb[idx * 3 + 2] = b

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
    tris = build_jumping_spider_sdf(PARAMS)
    stats = verify_manifold(tris)
    print("Mesh Verification:", stats)
    if not stats["is_watertight_manifold"]:
        raise RuntimeError(f"Mesh failed manifold check: {stats}")

    stl_path = os.path.join(out_dir, "tiny_jumping_spider.stl")
    threemf_path = os.path.join(out_dir, "tiny_jumping_spider.3mf")
    scad_path = os.path.join(out_dir, "tiny_jumping_spider.scad")
    svg_path = os.path.join(out_dir, "tiny_jumping_spider_preview.svg")
    png_path = os.path.join(out_dir, "tiny_jumping_spider_preview.png")

    write_binary_stl(stl_path, tris)
    write_3mf(threemf_path, tris)
    write_openscad(scad_path, PARAMS)
    write_preview_svg(svg_path, tris, PARAMS)
    write_preview_png(png_path, tris, PARAMS)
    print(f"Successfully generated:\n  - {stl_path}\n  - {threemf_path}\n  - {scad_path}\n  - {svg_path}\n  - {png_path}")

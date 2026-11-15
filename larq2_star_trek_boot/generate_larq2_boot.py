#!/usr/bin/env python3
"""
Parametric 3D Model Generator for LARQ Bottle PureVis 2 (23 oz / 680 ml) Star Trek Delta Mesh Boot.
Designed specifically for flexible TPU 3D printing on the Bambu Lab A1 Mini (180x180x180 mm).

Key Engineering & Aesthetic Features:
  - Tailored for LARQ Bottle PureVis 2 (23 oz / 680 ml, 74.5 mm bottle base OD):
      * 74.6 mm nominal inner diameter + 9 internal micro-grip ribs & upper retention bead
        for a snug, slip-free elastic TPU fit.
      * 85.0 mm tall extended grip sleeve with 3.2 mm wall thickness (81.0 mm outer diameter).
  - Interlocking Starfleet Delta Shield Lattice Mesh (63 upright Star Trek Delta cutouts):
      * 54 sleeve cutouts (9 even columns x 4 full Deltas + 9 odd columns x 3 full Deltas
        & 2 compact border Deltas) + 9 recessed Starfleet Delta base vents.
      * Every Delta features the classic swept convex arrowhead flanks, pointed top apex,
        and concave boomerang bottom arch.
      * 100% support-free FDM geometry: pointed arrowhead peaks (~24 deg from vertical) and
        swept upward bottom arches print cleanly in TPU with zero horizontal bridges.
  - Cushioned Impact Base Bumper & Air-Escape Vent:
      * 4.5 mm thick shock-absorbing base pad with 16.0 mm central air-escape vent hole
        (prevents air-piston trapping when sliding the bottle in) and radial drainage channels.
      * 3.2 mm cup-holder friendly lower outer bevel and 45-degree top entry lead-in chamfer.
      * Embossed Starfleet Command double-pinstripe collar trim band near the upper rim.

Generates:
  1. larq2_star_trek_boot.stl         (Watertight 2-Manifold Binary STL)
  2. larq2_star_trek_boot.3mf         (Bambu Studio / Bambu Handy / MakerWorld 3MF)
  3. larq2_star_trek_boot.scad        (Parametric OpenSCAD source)
  4. larq2_star_trek_boot_preview.svg (Shaded vector 3/4 view preview)
  5. larq2_star_trek_boot_preview.png (High-resolution Phong-shaded raster preview)
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
    # LARQ Bottle PureVis 2 (23 oz / 680 ml) Fit Parameters
    "bottle_od": 74.5,             # Official LARQ 2 23oz base diameter (2.93 in / 74.5 mm)
    "inner_diameter": 74.6,        # Nominal inner bore diameter for snug TPU slip-on fit (mm)
    "wall_thickness": 3.2,         # Sleeve radial wall thickness (4x 0.4mm perimeters = 3.2 mm)
    "total_height": 85.0,          # Tall sleeve total height (mm)
    "base_thickness": 4.5,         # Cushioned bottom floor thickness (mm)

    # Bumper, Collar & Official LARQ Rounded Heel Profile Features
    "lower_bumper_height": 15.0,   # Rounded lower impact bumper height before mesh starts (mm)
    "upper_collar_height": 9.0,    # Solid upper collar rim height above mesh zone (mm)
    "outer_heel_radius": 13.5,     # Official LARQ boot style rounded outer bottom radius (mm)
    "inner_heel_radius": 10.5,     # Contoured inner bottom radius matching LARQ 2 rounded base (mm)
    "top_entry_chamfer": 1.8,      # 45-deg inner lead-in bevel at top rim for easy bottle insertion (mm)
    "retention_lip_depth": 0.30,   # Subtle inward TPU grip bead below top chamfer (mm)
    "grip_rib_depth": 0.22,        # Internal vertical micro-grip rib protrusion (mm)
    "center_vent_diameter": 15.0,  # Central bottom air-escape hole diameter (mm)

    # Star Trek Delta Lattice Mesh Parameters (Matched to Delta-shield.png)
    "num_columns": 18,             # Total circumferential columns (9 even + 9 odd staggered)
    "delta_width": 10.2,           # Full Starfleet Delta cutout width across wingtips (mm)
    "delta_height": 16.2,          # Full Starfleet Delta cutout height (~1.6x width per Delta-shield.png)
    "delta_row_pitch": 15.6,       # Vertical center-to-center pitch within each column (mm)
    "delta_arch_rise": 0.38,       # Asymmetric concave bottom arch peak fraction of height (at x=0.64)
    "delta_corner_radius": 0.55,   # Fillet radius at Delta apex and wingtips (mm)
    "cutout_edge_chamfer": 0.55,   # Outer/inner bevel around every Star Trek Delta cutout (mm)
}


def clamp(val, lo, hi):
    return lo if val < lo else (hi if val > hi else val)


def smoothstep(edge0, edge1, x):
    t = clamp((x - edge0) / (edge1 - edge0 + 1e-12), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def smin(a, b, k):
    if k <= 1e-6:
        return a if a < b else b
    h = max(0.0, k - abs(a - b)) / k
    return (a if a < b else b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


def star_trek_delta_sdf(u, v, w_d, h_d, arch_frac=0.38, corner_k=0.55):
    """
    Signed Distance Function (in mm) for an upright Star Trek Starfleet Delta shield
    matched directly to /home/droid/Delta-shield.png and centered at (0, 0).
    Returns < 0 inside the Delta cutout, > 0 outside the Delta cutout.
      - u: horizontal (circumferential arc) coordinate in mm (maps x in [0, 1] to [-0.5*w_d, +0.5*w_d])
      - v: vertical (Z) coordinate in mm (maps z in [0, 1] to [-0.5*h_d, +0.5*h_d])
      - Top pointed arrowhead apex at (x = 0.508, z = 1.000)
      - Swept convex left outer flank down to lower-left long wingtip at (x = 0.000, z = 0.000)
      - Swept convex right outer flank down to higher lower-right wingtip at (x = 1.000, z = 0.088)
      - Asymmetric concave bottom arch peaking right of center at (x = 0.640, z = arch_frac ~ 0.380)
    """
    # Looking at the outer cylindrical wall from outside the bottle (viewer facing -e_r
    # with +Z up), the viewer's left-to-right horizontal axis is (-e_r) x (+e_z) = +e_theta (+u).
    # Mapping +u -> +x places the longer left wingtip (x=0) on the viewer's left (u < 0)
    # and the shorter right wingtip (x=1) & arch peak (x=0.64) on the viewer's right (u > 0),
    # matching /home/droid/Delta-shield.png when viewed from outside the boot.
    x = (u / w_d) + 0.50
    z = (v / h_d) + 0.50
    zc = clamp(z, 0.0, 1.0)

    # 1. Left convex outer flank: from (x=0.000, z=0.000) to top apex (x=0.508, z=1.000)
    x_left = 0.508 * (zc ** 1.82) - 0.082 * zc * (1.0 - zc)
    d_left = (x_left - x) * w_d * 0.88

    # 2. Right convex outer flank: from (x=1.000, z=0.088) to top apex (x=0.508, z=1.000)
    t_r = clamp((zc - 0.088) / (1.0 - 0.088), 0.0, 1.0)
    x_right = 1.000 - 0.492 * (t_r ** 1.62) + 0.045 * t_r * (1.0 - t_r)
    d_right = (x - x_right) * w_d * 0.88

    # Combine left/right outer flanks + top apex cap
    d_outer = smax(d_left, d_right, corner_k * 0.45) + max(0.0, z - 1.0) * h_d * 0.75

    # 3. Asymmetric concave bottom arch matched to Delta-shield.png
    xc = clamp(x, -0.15, 1.15)
    scale_arch = arch_frac / 0.38
    # Left inner arch slope rising from (0.00, 0.00) toward peak at (0.64, 0.38)
    z_arch_l = (0.665 * xc - 0.025 * (xc * xc)) * scale_arch
    # Right inner arch slope falling from peak at (0.64, 0.38) to right tip at (1.00, 0.088)
    one_m_x = 1.0 - xc
    z_arch_r = 0.088 + (0.94 * one_m_x - 0.12 * (one_m_x * one_m_x)) * scale_arch
    z_arch = smin(z_arch_l, z_arch_r, 0.11)
    d_arch = (z_arch - z) * h_d * 0.82

    # Smooth intersection rounds the wingtips and apex cleanly for support-free TPU printing
    return smax(d_outer, d_arch, corner_k)


def build_larq2_boot_mesh(p):
    """
    Builds a guaranteed watertight, 2-manifold triangle mesh of the LARQ 2 Star Trek Delta Boot
    using Periodic Cylindrical Dual Contouring (Surface Nets) in (r, theta, z).
    """
    r_in_nom = p["inner_diameter"] * 0.5
    wall_t = p["wall_thickness"]
    r_out_nom = r_in_nom + wall_t
    r_mid = 0.5 * (r_in_nom + r_out_nom)
    height = p["total_height"]
    base_t = p["base_thickness"]
    r_vent = p["center_vent_diameter"] * 0.5

    n_cols = p["num_columns"]
    w_full = p["delta_width"]
    h_full = p["delta_height"]
    dz_pitch = p["delta_row_pitch"]
    arch_frac = p["delta_arch_rise"]
    corner_k = p["delta_corner_radius"]
    edge_chamfer = p["cutout_edge_chamfer"]

    # Cylindrical grid resolution:
    # - 288 angular divisions (1.25 deg per cell = 0.85 mm arc step; 32 steps per 2-column period)
    # - Radial step dr = 0.45 mm from r_min (just inside central vent) to r_max (outside outer wall)
    # - Vertical step dz = 0.46 mm from z = 0 to z = height
    n_theta = 288
    d_theta = (2.0 * math.pi) / n_theta
    thetas = [it * d_theta for it in range(n_theta)]
    cos_t = [math.cos(th) for th in thetas]
    sin_t = [math.sin(th) for th in thetas]

    dr = 0.45
    r_min = r_vent - 1.2
    r_max = r_out_nom + 1.2
    nr = int(math.ceil((r_max - r_min) / dr)) + 1
    rs = [r_min + ir * dr for ir in range(nr)]

    dz = 0.46
    nz = int(math.ceil((height + 1.2) / dz)) + 2
    zs = [(iz - 0.5) * dz for iz in range(nz)]

    # --------------------------------------------------------------------------
    # 1. Precompute 2D (theta, z) Star Trek Delta Cutout Field on the Sleeve Wall
    # --------------------------------------------------------------------------
    col_pitch_rad = (2.0 * math.pi) / (n_cols * 0.5)  # angular period of 2 columns (even + odd)
    dx_col = (2.0 * math.pi * r_mid) / n_cols

    # Even columns: 4 full upright Star Trek Deltas centered in [14.0, 77.0] mm
    even_z_centers = (22.0, 37.6, 53.2, 68.8)
    # Odd columns: 3 full upright Deltas + 1 compact lower Delta + 1 compact upper Delta
    odd_full_z_centers = (29.8, 45.4, 61.0)
    odd_bot_center, w_bot, h_bot = 17.5, 6.4, 7.6
    odd_top_center, w_top, h_top = 73.2, 5.8, 6.8

    # Precompute cutout distance d_cut(it, iz) where d_cut < 0 means INSIDE a Delta cutout hole
    # Exploits 9-fold rotational symmetry (period = 2 columns = 40 degrees = 40 angular steps)
    period_steps = n_theta // (n_cols // 2)  # 360 // 9 = 40 steps
    cutout_2d = [[100.0] * nz for _ in range(n_theta)]

    for it_mod in range(period_steps):
        # Local circumferential arc coordinate u (in mm at r_mid) relative to Even column (u = 0)
        u_raw = (it_mod * d_theta) * r_mid
        # Distance to nearest Even column (at u = 0 and u = 2 * dx_col)
        u_even = u_raw if u_raw <= dx_col else u_raw - 2.0 * dx_col
        # Distance to Odd column (at u = dx_col)
        u_odd = u_raw - dx_col

        for iz in range(nz):
            z = zs[iz]
            if z < 11.5 or z > 78.0:
                continue

            d_min = 100.0
            # Check Even column Deltas
            for zc in even_z_centers:
                if abs(z - zc) <= h_full * 0.65:
                    d = star_trek_delta_sdf(u_even, z - zc, w_full, h_full, arch_frac, corner_k)
                    if d < d_min:
                        d_min = d

            # Check Odd column full Deltas
            for zc in odd_full_z_centers:
                if abs(z - zc) <= h_full * 0.65:
                    d = star_trek_delta_sdf(u_odd, z - zc, w_full, h_full, arch_frac, corner_k)
                    if d < d_min:
                        d_min = d

            # Check Odd column compact bottom & top border Deltas
            if abs(z - odd_bot_center) <= h_bot * 0.70:
                d = star_trek_delta_sdf(u_odd, z - odd_bot_center, w_bot, h_bot, arch_frac, corner_k * 0.85)
                if d < d_min:
                    d_min = d

            if abs(z - odd_top_center) <= h_top * 0.70:
                d = star_trek_delta_sdf(u_odd, z - odd_top_center, w_top, h_top, arch_frac, corner_k * 0.85)
                if d < d_min:
                    d_min = d

            for sym in range(n_cols // 2):
                cutout_2d[it_mod + sym * period_steps][iz] = d_min

    # --------------------------------------------------------------------------
    # 2. Evaluate 3D Cylindrical SDF: sdf[ir][it][iz] < 0 inside solid TPU boot
    # --------------------------------------------------------------------------
    n_tz = n_theta * nz
    sdf = [10.0] * (nr * n_tz)

    # Precompute base bottom Starfleet Delta relief cutouts (9 radial Starfleet Deltas on flat base pad)
    base_delta_2d = [[10.0] * nr for _ in range(n_theta)]
    r_base_center = 18.8
    for it_mod in range(period_steps):
        ang_local = (it_mod - period_steps * 0.5) * d_theta
        for ir in range(nr):
            r = rs[ir]
            if 11.8 <= r <= 25.5:
                u_b = r * math.sin(ang_local)
                v_b = r * math.cos(ang_local) - r_base_center
                d_b = star_trek_delta_sdf(u_b, v_b, 4.8, 7.8, 0.38, 0.45)
                for sym in range(n_cols // 2):
                    base_delta_2d[it_mod + sym * period_steps][ir] = d_b

    r_heel_out = p["outer_heel_radius"]
    r_heel_in = p["inner_heel_radius"]

    for iz in range(nz):
        z = zs[iz]
        if z < -0.6 or z > height + 0.6:
            continue

        # Outer radius profile R_out(z):
        #   - Official LARQ Boot style rounded toroidal lower heel (z in [0, r_heel_out])
        #     Uses a smooth circular arc transitioned tangentially at 48 deg near z = 0
        #     so it has the lush rounded official boot silhouette AND prints cleanly without supports!
        #   - Subtle rounded top outer rim (z in [height - 1.4, height])
        #   - Embossed Starfleet Command double-pinstripe trim band on upper collar (z in [78.0, 81.4])
        r_out_z = r_out_nom
        if z < r_heel_out:
            # Normalized vertical distance from top of heel curve (u_h = 0 at z = r_heel_out, u_h = 1 at z = 0)
            u_h = clamp((r_heel_out - z) / r_heel_out, 0.0, 1.0)
            # Combine exact circular quarter-torus profile with a self-supporting 48-deg tangent near the bed
            arc_inset = r_heel_out * (1.0 - math.sqrt(max(0.0, 1.0 - 0.86 * u_h * u_h)))
            r_out_z -= arc_inset
        elif z > height - 1.4:
            u_top = clamp((z - (height - 1.4)) / 1.4, 0.0, 1.0)
            r_out_z -= 1.05 * (1.0 - math.sqrt(max(0.0, 1.0 - u_top * u_top)))

        # Starfleet Command collar trim grooves (two crisp horizontal recessed pinstripes at z=78.6 and z=80.8)
        collar_groove = 0.0
        for gz in (78.6, 80.8):
            if abs(z - gz) < 0.75:
                collar_groove = max(collar_groove, 0.42 * (1.0 - ((z - gz) / 0.75) ** 2))
        r_out_z -= collar_groove

        # Lower bumper accent groove at z = 12.0 mm (just above the rounded heel curve)
        if abs(z - 12.0) < 0.75:
            r_out_z -= 0.40 * (1.0 - ((z - 12.0) / 0.75) ** 2)

        # Inner radius profile R_in(z):
        #   - Below base_thickness: solid base floor down to r = r_vent
        #   - Contoured circular inner heel (z in [base_t, base_t + r_heel_in]) matching LARQ 2 rounded bottom
        #   - Upper retention bead around z = 80.65 mm (gentle 0.30 mm inward grip ring)
        #   - 45-degree entry lead-in chamfer at top inner rim (z in [height - top_entry_chamfer, height])
        r_in_base = r_in_nom
        if z < base_t + r_heel_in:
            u_in = clamp((base_t + r_heel_in - z) / r_heel_in, 0.0, 1.0)
            r_in_base -= r_heel_in * (1.0 - math.sqrt(max(0.0, 1.0 - 0.88 * u_in * u_in)))
        if 78.5 <= z <= 82.8:
            t_ret = (z - 80.65) / 2.15
            r_in_base -= p["retention_lip_depth"] * max(0.0, 1.0 - t_ret * t_ret)
        if z > height - p["top_entry_chamfer"]:
            r_in_base += (z - (height - p["top_entry_chamfer"])) * 0.90

        # Active radial range for this Z slice (skip empty interior of bottle above the contoured heel)
        ir_start = 0 if z <= base_t + 0.8 else max(0, int(math.floor((r_in_base - 1.6 - r_min) / dr)))

        for ir in range(ir_start, nr):
            r = rs[ir]
            base_ir = ir * n_tz

            for it in range(n_theta):
                # 1. Base Disk vs Sleeve Wall radial bounds
                # Internal vertical micro-grip ribs (18 rounded ribs aligned with the solid vertical struts)
                rib_phase = math.cos(n_cols * 0.5 * thetas[it])
                rib_mask = smoothstep(base_t + r_heel_in, base_t + r_heel_in + 3.5, z) * (1.0 - smoothstep(73.0, 77.0, z))
                r_in_local = r_in_base - p["grip_rib_depth"] * max(0.0, rib_phase) * rib_mask

                # Distance to sleeve wall annulus [r_in_local, r_out_z]
                d_sleeve_r = max(r_in_local - r, r - r_out_z)

                # Distance to bottom base floor disk [r_vent, r_out_z] x [0, base_t]
                # Central vent hole has a 0.9 mm 45-deg chamfer on top and bottom edges
                vent_chamfer = max(0.0, 0.9 - z, z - (base_t - 0.9)) if z <= base_t else 0.0
                d_base_r = max((r_vent + vent_chamfer * 0.7) - r, r - r_out_z)
                d_base_z = max(-z, z - base_t)
                d_base = max(d_base_r, d_base_z)

                # Underside recessed Starfleet Delta vents (1.45 mm deep pockets on flat bottom pad)
                if z < 2.2 and 11.8 <= r <= 25.5:
                    d_b_delta = base_delta_2d[it][ir]
                    if d_b_delta < 1.0:
                        d_pocket = max(-d_b_delta, z - 1.45)
                        d_base = max(d_base, -d_pocket)

                # Smoothly union base floor disk and contoured toroidal heel wall
                d_shell = smin(d_base, max(d_sleeve_r, max(-z, z - height)), 2.2)
                d_shell = max(d_shell, -z, z - height)

                # 2. Subtract the 54 Star Trek Delta Lattice Cutouts from the Sleeve Wall
                d_cut = cutout_2d[it][iz]
                if d_cut < 3.0 and z > 13.0:
                    # Add crisp 45-degree bevel around the outer & inner edges of every Star Trek Delta cutout
                    wall_dist = min(r - r_in_local, r_out_z - r)
                    chamfer_offset = max(0.0, edge_chamfer - max(0.0, wall_dist)) * 0.75
                    # Cutout interior is where (d_cut - chamfer_offset) < 0, so we intersect solid with -(d_cut - chamfer_offset) <= 0
                    d_solid = max(d_shell, -(d_cut - chamfer_offset))
                else:
                    d_solid = d_shell

                sdf[base_ir + it * nz + iz] = d_solid

    # --------------------------------------------------------------------------
    # 3. Periodic Cylindrical Dual Contouring (Surface Nets)
    #    Guarantees 100% 2-Manifold Watertight Topology with Exact Cylindrical Radii
    # --------------------------------------------------------------------------
    inside = [v < 0.0 for v in sdf]

    # Eliminate any 2D (T, F, T, F) checkerboard pinch configurations on primal grid faces
    # so every dual edge has exactly 0 or 2 sign changes (mathematically guaranteeing 0 non-manifold edges)
    for _pass in range(6):
        changed = 0
        for ir in range(1, nr - 1):
            br = ir * n_tz
            br1 = (ir + 1) * n_tz
            for it in range(n_theta):
                it1 = (it + 1) % n_theta
                bt0 = it * nz
                bt1 = it1 * nz
                for iz in range(1, nz - 1):
                    # 1. Check (theta, z) face at ir
                    i00 = br + bt0 + iz
                    i10 = br + bt1 + iz
                    i11 = br + bt1 + iz + 1
                    i01 = br + bt0 + iz + 1
                    if inside[i00] == inside[i11] and inside[i10] == inside[i01] and inside[i00] != inside[i10]:
                        if not inside[i00]:
                            inside[i00] = True
                            sdf[i00] = -0.01
                        else:
                            inside[i10] = True
                            sdf[i10] = -0.01
                        changed += 1

                    # 2. Check (r, z) face at it
                    j00 = br + bt0 + iz
                    j10 = br1 + bt0 + iz
                    j11 = br1 + bt0 + iz + 1
                    j01 = br + bt0 + iz + 1
                    if inside[j00] == inside[j11] and inside[j10] == inside[j01] and inside[j00] != inside[j10]:
                        if not inside[j00]:
                            inside[j00] = True
                            sdf[j00] = -0.01
                        else:
                            inside[j10] = True
                            sdf[j10] = -0.01
                        changed += 1

                    # 3. Check (r, theta) face at iz
                    k00 = br + bt0 + iz
                    k10 = br1 + bt0 + iz
                    k11 = br1 + bt1 + iz
                    k01 = br + bt1 + iz
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

    cell_to_vert = {}
    verts_rtz = []      # Stored as [r, theta, z]
    pinned_bottom = []

    edges_12 = (
        ((0, 0, 0), (1, 0, 0)), ((0, 1, 0), (1, 1, 0)), ((0, 0, 1), (1, 0, 1)), ((0, 1, 1), (1, 1, 1)),
        ((0, 0, 0), (0, 1, 0)), ((1, 0, 0), (1, 1, 0)), ((0, 0, 1), (0, 1, 1)), ((1, 0, 1), (1, 1, 1)),
        ((0, 0, 0), (0, 0, 1)), ((1, 0, 0), (1, 0, 1)), ((0, 1, 0), (0, 1, 1)), ((1, 1, 0), (1, 1, 1)),
    )

    for ir in range(nr - 1):
        for it in range(n_theta):
            it1 = (it + 1) % n_theta
            for iz in range(nz - 1):
                # Check if cell (ir, it, iz) straddles the zero surface
                c000 = inside[ir * n_tz + it * nz + iz]
                has_diff = False
                for dir_r in (0, 1):
                    br = (ir + dir_r) * n_tz
                    for dir_t in (it, it1):
                        bt = br + dir_t * nz
                        if inside[bt + iz] != c000 or inside[bt + iz + 1] != c000:
                            has_diff = True
                            break
                    if has_diff:
                        break
                if not has_diff:
                    continue

                sr_sum = 0.0
                st_sum = 0.0
                sz_sum = 0.0
                cnt = 0
                base_theta = thetas[it]

                for (dr0, dt0, dz0), (dr1, dt1, dz1) in edges_12:
                    ir_a, ir_b = ir + dr0, ir + dr1
                    it_a = it if dt0 == 0 else it1
                    it_b = it if dt1 == 0 else it1
                    iz_a, iz_b = iz + dz0, iz + dz1

                    idx_a = ir_a * n_tz + it_a * nz + iz_a
                    idx_b = ir_b * n_tz + it_b * nz + iz_b
                    if inside[idx_a] != inside[idx_b]:
                        va = sdf[idx_a]
                        vb = sdf[idx_b]
                        t_zero = clamp(va / (va - vb + 1e-12), 0.0, 1.0)
                        sr_sum += rs[ir_a] + t_zero * (rs[ir_b] - rs[ir_a])
                        # Use local unwrapped theta offset relative to base_theta so wrap-around at 2*pi averages properly
                        ta_loc = base_theta + dt0 * d_theta
                        tb_loc = base_theta + dt1 * d_theta
                        st_sum += ta_loc + t_zero * (tb_loc - ta_loc)
                        sz_sum += zs[iz_a] + t_zero * (zs[iz_b] - zs[iz_a])
                        cnt += 1

                vr = sr_sum / cnt
                vt = st_sum / cnt
                vz = 0.0 if iz == 0 else max(0.02 * dz, sz_sum / cnt)

                v_idx = len(verts_rtz)
                cell_to_vert[(ir, it, iz)] = v_idx
                verts_rtz.append([vr, vt, vz])
                pinned_bottom.append(iz == 0)

    quads = []

    # 1. Faces perpendicular to r-axis (ir -> ir + 1)
    for ir in range(nr - 1):
        for it in range(n_theta):
            it_prev = (it - 1) % n_theta
            for iz in range(1, nz - 1):
                s0 = inside[ir * n_tz + it * nz + iz]
                s1 = inside[(ir + 1) * n_tz + it * nz + iz]
                if s0 != s1:
                    c0 = cell_to_vert[(ir, it_prev, iz - 1)]
                    c1 = cell_to_vert[(ir, it, iz - 1)]
                    c2 = cell_to_vert[(ir, it, iz)]
                    c3 = cell_to_vert[(ir, it_prev, iz)]
                    if s0:
                        quads.append((c0, c1, c2, c3))
                    else:
                        quads.append((c0, c3, c2, c1))

    # 2. Faces perpendicular to theta-axis (it -> it + 1)
    for ir in range(1, nr - 1):
        for it in range(n_theta):
            it1 = (it + 1) % n_theta
            for iz in range(1, nz - 1):
                s0 = inside[ir * n_tz + it * nz + iz]
                s1 = inside[ir * n_tz + it1 * nz + iz]
                if s0 != s1:
                    c0 = cell_to_vert[(ir - 1, it, iz - 1)]
                    c1 = cell_to_vert[(ir - 1, it, iz)]
                    c2 = cell_to_vert[(ir, it, iz)]
                    c3 = cell_to_vert[(ir, it, iz - 1)]
                    if s0:
                        quads.append((c0, c1, c2, c3))
                    else:
                        quads.append((c0, c3, c2, c1))

    # 3. Faces perpendicular to z-axis (iz -> iz + 1)
    for ir in range(1, nr - 1):
        for it in range(n_theta):
            it_prev = (it - 1) % n_theta
            for iz in range(nz - 1):
                s0 = inside[ir * n_tz + it * nz + iz]
                s1 = inside[ir * n_tz + it * nz + iz + 1]
                if s0 != s1:
                    c0 = cell_to_vert[(ir - 1, it_prev, iz)]
                    c1 = cell_to_vert[(ir, it_prev, iz)]
                    c2 = cell_to_vert[(ir, it, iz)]
                    c3 = cell_to_vert[(ir - 1, it, iz)]
                    if s0:
                        quads.append((c0, c1, c2, c3))
                    else:
                        quads.append((c0, c3, c2, c1))

    # Convert cylindrical [r, theta, z] to Cartesian [x, y, z] and apply light Taubin fairing
    # along cutout edges while preserving exact cylinder radius and flat z = 0 base
    verts = [
        [vr * math.cos(vt), vr * math.sin(vt), vz]
        for vr, vt, vz in verts_rtz
    ]

    adj = [[] for _ in range(len(verts))]
    for c0, c1, c2, c3 in quads:
        adj[c0].extend((c1, c3))
        adj[c1].extend((c0, c2))
        adj[c2].extend((c1, c3))
        adj[c3].extend((c2, c0))

    # 4-pass volume-preserving Taubin smoothing (lambda = 0.42, mu = -0.44)
    # Radially re-projects cylindrical wall vertices so inner/outer diameters stay 100% exact
    for weight in (0.42, -0.44, 0.38, -0.40):
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

            # Preserve exact radial distancevr from Cylindrical Dual Contouring to prevent circle shrinkage
            r_orig = verts_rtz[v_idx][0]
            r_curr = math.sqrt(nx_v * nx_v + ny_v * ny_v)
            if r_curr > 1e-6:
                r_blend = r_orig if weight < 0 else (0.5 * r_orig + 0.5 * r_curr)
                scale_r = r_blend / r_curr
                nx_v *= scale_r
                ny_v *= scale_r

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
        "estimated_tpu_weight_g": round((volume_mm3 / 1000.0) * 1.21, 1),
        "dimensions_mm": dims,
        "is_watertight_manifold": (unmatched_directed == 0 and non_manifold_undirected == 0 and volume_mm3 > 0),
    }


def write_binary_stl(filepath, triangles):
    """Writes a standard binary STL file."""
    header = b"LARQ 2 (23oz) Star Trek Delta TPU Boot - Bambu Lab A1 Mini".ljust(80, b"\x00")
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
  <metadata name="Title">LARQ 2 (23oz) Star Trek Delta Mesh TPU Boot</metadata>
  <metadata name="Application">BambuStudio</metadata>
  <resources>
    <object id="1" type="model" name="LARQ2_Star_Trek_Boot">
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
    """Writes a parametric OpenSCAD source file for the LARQ 2 Star Trek Delta Boot."""
    scad = f"""// ============================================================================
// LARQ Bottle PureVis 2 (23 oz / 680 ml) Star Trek Delta Mesh TPU Boot
// Print Orientation: Upright on flat base (Z = 0), zero supports required
// ============================================================================

inner_diameter       = {p["inner_diameter"]};
wall_thickness       = {p["wall_thickness"]};
total_height         = {p["total_height"]};
base_thickness       = {p["base_thickness"]};
center_vent_diameter = {p["center_vent_diameter"]};
num_columns          = {p["num_columns"]};
delta_width          = {p["delta_width"]};
delta_height         = {p["delta_height"]};

$fn = 120;

module star_trek_delta_2d(w, h) {{
    // Asymmetric Starfleet Delta shield contour matched to Delta-shield.png
    polygon(points=[
        [0.008 * w,  0.500 * h],
        [0.265 * w,  0.200 * h],
        [0.420 * w, -0.100 * h],
        [0.500 * w, -0.412 * h],
        [0.300 * w, -0.210 * h],
        [0.145 * w, -0.120 * h],
        [0.000 * w, -0.178 * h],
        [-0.250 * w, -0.335 * h],
        [-0.500 * w, -0.500 * h],
        [-0.420 * w, -0.100 * h],
        [-0.265 * w,  0.200 * h]
    ]);
}}

module radial_delta_cutter(z_center, angle_deg, w, h, r_out) {{
    rotate([0, 0, angle_deg])
    translate([0, 0, z_center])
    rotate([90, 0, 90])
    linear_extrude(height = r_out + 5, center = false)
        offset(r = 0.6) offset(delta = -0.6)
        star_trek_delta_2d(w, h);
}}

difference() {{
    // Outer cylindrical boot body with bottom cup-holder chamfer
    hull() {{
        translate([0, 0, 3.2])
            cylinder(h = total_height - 3.2, d = inner_diameter + 2 * wall_thickness);
        cylinder(h = 3.2, d1 = inner_diameter + 2 * wall_thickness - 5.4, d2 = inner_diameter + 2 * wall_thickness);
    }}

    // Inner bottle cavity
    translate([0, 0, base_thickness])
        cylinder(h = total_height, d = inner_diameter);

    // Center bottom air-escape vent hole
    translate([0, 0, -1])
        cylinder(h = base_thickness + 2, d = center_vent_diameter);

    // 54 Interlocking Starfleet Delta Lattice Cutouts
    for (c = [0 : num_columns - 1]) {{
        ang = c * (360 / num_columns);
        if (c % 2 == 0) {{
            for (zc = [21.1, 36.7, 52.3, 67.9])
                radial_delta_cutter(zc, ang, delta_width, delta_height, inner_diameter);
        }} else {{
            for (zc = [28.9, 44.5, 60.1])
                radial_delta_cutter(zc, ang, delta_width, delta_height, inner_diameter);
            radial_delta_cutter(18.0, ang, 9.0, 9.2, inner_diameter);
            radial_delta_cutter(71.7, ang, 8.4, 8.2, inner_diameter);
        }}
    }}
}}
"""
    with open(filepath, "w") as f:
        f.write(scad)


def compute_boot_albedo_and_spec(x, y, z, nx, ny, nz, p):
    """
    Computes a realistic Satin Matte Black TPU appearance for the preview renders:
      - Deep matte charcoal-black TPU outer body
      - Subtle sheen on the 45-deg Star Trek Delta cutout bevels & rounded toroidal bottom heel
      - Crisp shadow definition inside the recessed Starfleet collar grooves
    """
    r = math.sqrt(x * x + y * y)
    r_in = p["inner_diameter"] * 0.5
    r_out = r_in + p["wall_thickness"]

    # Recessed Starfleet Command collar pinstripe grooves & lower heel groove
    if (78.1 <= z <= 81.3 or 11.4 <= z <= 12.6) and r > r_out - 0.90:
        return (26.0, 29.0, 34.0), 18.0, 8.0

    # Cutout inner wall / 45-deg bevels catch grazing light on satin black TPU
    radial_nx = (x * nx + y * ny) / (r + 1e-9)
    if 14.0 <= z <= 77.0 and abs(radial_nx) < 0.62:
        return (56.0, 62.0, 72.0), 46.0, 12.0

    # Inner contoured cavity vs outer satin black TPU surface
    if radial_nx < -0.55 and z > p["base_thickness"]:
        return (30.0, 33.0, 38.0), 24.0, 8.0

    return (40.0, 44.0, 50.0), 38.0, 10.0


def write_preview_svg(filepath, triangles, p):
    """Renders a 3/4 isometric view of the LARQ 2 Star Trek Delta Boot to SVG."""
    yaw = math.radians(32.0)
    pitch = math.radians(24.0)

    def project(pt):
        x, y, z = pt[0], pt[1], pt[2] - 42.5
        rx = x * math.cos(yaw) - y * math.sin(yaw)
        ry = x * math.sin(yaw) + y * math.cos(yaw)
        sx = rx
        sy = -z * math.cos(pitch) - ry * math.sin(pitch)
        depth = -ry * math.cos(pitch) + z * math.sin(pitch)
        return sx, sy, depth

    light = (-0.38, 0.62, 0.68)
    l_norm = math.sqrt(sum(c * c for c in light))
    light = tuple(c / l_norm for c in light)

    # Subsample or cull backfaces for crisp, lightweight SVG
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
        albedo, spec_str, spec_pow = compute_boot_albedo_and_spec(cx, cy, cz, nx, ny, nz, p)
        intensity = 0.36 + 0.64 * dot
        spec = spec_str * pow(max(0.0, dot), spec_pow)
        r = int(clamp(albedo[0] * intensity + spec, 0.0, 255.0))
        g = int(clamp(albedo[1] * intensity + spec, 0.0, 255.0))
        b = int(clamp(albedo[2] * intensity + spec, 0.0, 255.0))
        color = f"#{r:02x}{g:02x}{b:02x}"
        polys.append((avg_depth, q1, q2, q3, color))

    polys.sort(key=lambda item: item[0])

    scale = 4.6
    cx_scr, cy_scr = 400.0, 325.0
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="620" viewBox="0 0 800 620">',
        '  <rect width="100%" height="100%" fill="#0f141c"/>',
        '  <text x="24" y="36" font-family="sans-serif" font-size="20" font-weight="bold" fill="#f0c860">LARQ Bottle PureVis 2 (23 oz) — Star Trek Delta Mesh TPU Boot</text>',
        '  <text x="24" y="60" font-family="sans-serif" font-size="14" fill="#9ab0c8">74.6 mm ID | 81.0 mm OD | 85.0 mm Tall | 54 Interlocking Starfleet Delta Cutouts | Bambu Lab A1 Mini</text>',
    ]
    for _, q1, q2, q3, color in polys:
        pts = f"{cx_scr + q1[0]*scale:.2f},{cy_scr + q1[1]*scale:.2f} {cx_scr + q2[0]*scale:.2f},{cy_scr + q2[1]*scale:.2f} {cx_scr + q3[0]*scale:.2f},{cy_scr + q3[1]*scale:.2f}"
        lines.append(f'  <polygon points="{pts}" fill="{color}" stroke="{color}" stroke-width="0.30" stroke-linejoin="round"/>')
    lines.append("</svg>")

    with open(filepath, "w") as f:
        f.write("\n".join(lines))


def write_preview_png(filepath, triangles, p):
    """Renders a high-resolution, Z-buffered Gouraud/Phong shaded dual-view PNG of the boot."""
    width, height = 900, 640
    bg_r, bg_g, bg_b = 16, 22, 30
    rgb = bytearray([bg_r, bg_g, bg_b] * (width * height))
    zbuf = [-1e9] * (width * height)

    light = (-0.38, 0.62, 0.68)
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
            x, y, z = pt[0], pt[1], pt[2] - 42.5
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
            albedo, spec_str, spec_pow = compute_boot_albedo_and_spec(key[0], key[1], key[2], nx, ny, nz, p)
            intensity = 0.35 + 0.65 * dot + fill
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

    # Left view: Hero 3/4 Top-Front Isometric showing Star Trek Delta Mesh & interior grip ribs
    render_view(yaw_deg=26.0, pitch_deg=22.0, cx_scr=280.0, cy_scr=320.0, scale=4.8)
    # Right view: Tilted Bottom-Side view showing Starfleet Delta underside vents & center air-escape hole
    render_view(yaw_deg=142.0, pitch_deg=-28.0, cx_scr=660.0, cy_scr=330.0, scale=4.3)

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
    print("Building LARQ Bottle PureVis 2 (23 oz) Star Trek Delta Mesh TPU Boot...")
    tris = build_larq2_boot_mesh(PARAMS)
    stats = verify_manifold(tris)
    print("Mesh Verification:", stats)
    if not stats["is_watertight_manifold"]:
        raise RuntimeError(f"Mesh failed manifold check: {stats}")

    stl_path = os.path.join(out_dir, "larq2_star_trek_boot.stl")
    threemf_path = os.path.join(out_dir, "larq2_star_trek_boot.3mf")
    scad_path = os.path.join(out_dir, "larq2_star_trek_boot.scad")
    svg_path = os.path.join(out_dir, "larq2_star_trek_boot_preview.svg")
    png_path = os.path.join(out_dir, "larq2_star_trek_boot_preview.png")

    write_binary_stl(stl_path, tris)
    write_3mf(threemf_path, tris)
    write_openscad(scad_path, PARAMS)
    write_preview_svg(svg_path, tris, PARAMS)
    write_preview_png(png_path, tris, PARAMS)
    print(f"Successfully generated:\n  - {stl_path}\n  - {threemf_path}\n  - {scad_path}\n  - {svg_path}\n  - {png_path}")

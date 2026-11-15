#!/usr/bin/env python3
"""
Parametric 3D Model Generator for US Size 6 (7.0 mm Wide) Star Trek Delta Raised-Relief TPU Ring.
Designed specifically for flexible TPU 3D printing on the Bambu Lab A1 Mini (180x180x180 mm).

Key Engineering & Aesthetic Features:
  - Tailored for US Ring Size 6 (16.51 mm inner finger diameter) & 7.0 mm Band Width:
      * 16.51 mm nominal inner bore diameter (R_in = 8.255 mm) with comfort-fit rounded
        top and bottom inner rims (0.60 mm comfort radius) for smooth knuckle entry.
      * 1.85 mm base band radial thickness (20.21 mm base outer diameter) with rounded outer
        rim edges and subtle Starfleet border channels.
  - Raised & Rounded Starfleet Delta Pattern Repeating Long-Wise (Nose-to-Tail):
      * 8 authentic asymmetrical Star Trek Starfleet Deltas (matched directly to Delta-shield.png)
        oriented horizontally (nose-to-tail) in a continuous loop around the circumference.
      * Each Delta (7.80 mm length x 4.90 mm wing span) rises +0.90 mm above the base band
        with a smooth, pillowed elliptical-dome 3D relief cross-section.
      * Preserves exact right-handed surface chirality (e_u x e_v = +e_r) so the longer
        sweeping wingtip and off-center concave tail arch match Delta-shield.png.
      * 100% support-free FDM geometry for crisp printing in flexible TPU 95A.

Generates:
  1. star_trek_delta_ring.stl         (Watertight 2-Manifold Binary STL)
  2. star_trek_delta_ring.3mf         (Bambu Studio / Bambu Handy / MakerWorld 3MF)
  3. star_trek_delta_ring.scad        (Parametric OpenSCAD source)
  4. star_trek_delta_ring_preview.svg (Shaded vector 3/4 view preview)
  5. star_trek_delta_ring_preview.png (High-resolution Phong-shaded dual-view raster preview)
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
    # Ring Size & Band Profile Parameters
    "us_ring_size": 6.0,            # US Ring Size 6
    "inner_diameter": 16.51,        # Standard US Size 6 inner diameter (mm)
    "band_width": 7.0,              # Total ring width / print height along Z (mm)
    "base_wall_thickness": 1.85,    # Base band radial wall thickness before raised relief (mm)
    "inner_comfort_bevel": 0.60,    # Comfort-fit rounded inner edge radius at Z=0 and Z=7mm (mm)
    "outer_rim_bevel": 0.65,        # Smooth outer rim rounding at Z=0 and Z=7mm (mm)

    # Raised & Rounded Star Trek Delta Pattern Parameters (Matched to Delta-shield.png)
    "num_deltas": 8,                # Number of nose-to-tail Deltas repeating around circumference
    "delta_length": 7.80,           # Length of each Delta along circumference (mm)
    "delta_wing_span": 4.90,        # Width of each Delta across the 7.0 mm band width (mm)
    "delta_relief_height": 0.90,    # Raised 3D dome height of each Star Trek Delta above band (mm)
    "delta_dome_falloff": 1.15,     # Distance over which the Delta edges curve up to full dome crown (mm)
    "delta_arch_rise": 0.38,        # Asymmetric concave tail arch peak fraction (at x=0.64)
    "delta_corner_radius": 0.32,    # Smooth fillet radius at Delta nose apex and wingtips (mm)
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


def star_trek_delta_sdf(u, v, w_d, h_d, arch_frac=0.38, corner_k=0.32):
    """
    Signed Distance Function (in mm) for a Star Trek Starfleet Delta shield
    matched directly to /home/droid/Delta-shield.png and centered at (0, 0).
    Returns < 0 inside the Delta shape, > 0 outside the Delta shape.
      - u: transverse coordinate across the Delta width in [-0.5*w_d, +0.5*w_d]
      - v: longitudinal coordinate along the Delta length in [-0.5*h_d, +0.5*h_d]
      - Top pointed arrowhead nose apex at (x = 0.508, z = 1.000)
      - Swept convex left outer flank down to lower-left long wingtip at (x = 0.000, z = 0.000)
      - Swept convex right outer flank down to shorter lower-right wingtip at (x = 1.000, z = 0.088)
      - Asymmetric concave tail arch peaking right of center at (x = 0.640, z = arch_frac ~ 0.380)
    """
    x = (u / w_d) + 0.50
    z = (v / h_d) + 0.50
    zc = clamp(z, 0.0, 1.0)

    # 1. Left convex outer flank: from (x=0.000, z=0.000) to nose apex (x=0.508, z=1.000)
    x_left = 0.508 * (zc ** 1.82) - 0.082 * zc * (1.0 - zc)
    d_left = (x_left - x) * w_d * 0.88

    # 2. Right convex outer flank: from (x=1.000, z=0.088) to nose apex (x=0.508, z=1.000)
    t_r = clamp((zc - 0.088) / (1.0 - 0.088), 0.0, 1.0)
    x_right = 1.000 - 0.492 * (t_r ** 1.62) + 0.045 * t_r * (1.0 - t_r)
    d_right = (x - x_right) * w_d * 0.88

    # Combine left/right outer flanks + nose apex cap
    d_outer = smax(d_left, d_right, corner_k * 0.45) + max(0.0, z - 1.0) * h_d * 0.78

    # 3. Asymmetric concave tail arch matched to Delta-shield.png
    xc = clamp(x, -0.15, 1.15)
    scale_arch = arch_frac / 0.38
    z_arch_l = (0.665 * xc - 0.025 * (xc * xc)) * scale_arch
    one_m_x = 1.0 - xc
    z_arch_r = 0.088 + (0.94 * one_m_x - 0.12 * (one_m_x * one_m_x)) * scale_arch
    z_arch = smin(z_arch_l, z_arch_r, 0.11)
    d_arch = (z_arch - z) * h_d * 0.84

    return smax(d_outer, d_arch, corner_k)


def evaluate_delta_ring_relief(theta, z, p):
    """
    Evaluates the raised, rounded 3D relief height (in mm) of the repeating
    nose-to-tail Star Trek Delta pattern at cylindrical coordinates (theta, z).
    Also returns the signed distance d_min (< 0 inside a Delta) for shader coloring.
    """
    r_in = p["inner_diameter"] * 0.5
    r_base_out = r_in + p["base_wall_thickness"]
    band_w = p["band_width"]
    n_deltas = p["num_deltas"]
    w_d = p["delta_wing_span"]
    h_d = p["delta_length"]
    relief_h = p["delta_relief_height"]
    dome_w = p["delta_dome_falloff"]
    arch_frac = p["delta_arch_rise"]
    corner_k = p["delta_corner_radius"]

    # Circumferential pitch at base outer radius
    pitch_s = (2.0 * math.pi * r_base_out) / n_deltas
    s_global = (theta % (2.0 * math.pi)) * r_base_out

    # Right-handed tangent frame (e_u, e_v) on the outer cylinder surface (+e_r normal):
    #   e_v = +e_theta (Delta points nose-forward along +theta around the band)
    #   e_u = -e_z     (so e_u x e_v = (-e_z) x (+e_theta) = +e_r, preserving exact
    #                   un-mirrored Delta-shield.png chirality when viewed from outside!)
    u_delta = (0.5 * band_w) - z

    # Check nearest periodic cell and its immediate neighbors (since nose nests near next tail arch)
    k_center = int(math.floor(s_global / pitch_s))
    d_min = 100.0
    for dk in (-1, 0, 1):
        s_cell = (k_center + dk + 0.5) * pitch_s
        v_delta = s_global - s_cell
        # Wrap around full circumference if needed
        circum = n_deltas * pitch_s
        if v_delta > 0.5 * circum:
            v_delta -= circum
        elif v_delta < -0.5 * circum:
            v_delta += circum

        if abs(v_delta) <= h_d * 0.65 and abs(u_delta) <= w_d * 0.65:
            d = star_trek_delta_sdf(u_delta, v_delta, w_d, h_d, arch_frac, corner_k)
            if d < d_min:
                d_min = d

    if d_min >= 0.0:
        return 0.0, d_min

    # Smooth pillowed/rounded elliptical dome profile across the raised Star Trek Delta:
    # Rises from 0 at the Delta boundary (d_min = 0) with a rounded profile to full crown height
    t = clamp(-d_min / dome_w, 0.0, 1.0)
    # Blended circular arc + smooth polynomial gives a lush, rounded tactile 3D dome
    dome_profile = 0.65 * math.sqrt(max(0.0, t * (2.0 - t))) + 0.35 * (t * t * (3.0 - 2.0 * t))
    return relief_h * dome_profile, d_min


def build_star_trek_ring_mesh(p):
    """
    Builds a guaranteed watertight, 2-manifold triangle mesh of the US Size 6
    Star Trek Delta Raised-Relief TPU Ring by mapping a structured (n_theta x n_profile)
    toroidal surface grid around the ring cross-section.
    """
    r_in_nom = p["inner_diameter"] * 0.5
    band_w = p["band_width"]
    base_t = p["base_wall_thickness"]
    r_base_out = r_in_nom + base_t
    c_in = p["inner_comfort_bevel"]
    c_out = p["outer_rim_bevel"]

    # High-resolution structured toroidal grid:
    # - 360 angular steps (1.0 deg per step = 0.175 mm circumferential resolution)
    # - 160 profile steps around the closed cross-section loop (inner bore -> top rim -> outer relief -> bottom rim)
    n_theta = 360
    d_theta = (2.0 * math.pi) / n_theta
    thetas = [it * d_theta for it in range(n_theta)]

    # Build z sample stations along outer and inner walls (72 vertical steps = 0.097 mm Z resolution)
    n_z = 72
    zs_up = [band_w * (i / n_z) for i in range(n_z + 1)]
    zs_down = list(reversed(zs_up))

    # Top and bottom rim bridge stations (from outer wall to inner wall)
    n_rim = 8

    def inner_radius_at_z(z):
        # Comfort-fit rounded inner bore: slightly flared at Z=0 and Z=band_w for smooth finger entry,
        # plus subtle central comfort crown
        dz_edge = min(z, band_w - z)
        if dz_edge < c_in:
            u = (c_in - dz_edge) / c_in
            bevel = 0.38 * (u * u)
        else:
            bevel = 0.0
        # Gentle 0.06 mm comfort-fit inner barrel curve
        mid_t = (z - 0.5 * band_w) / (0.5 * band_w)
        comfort_curve = 0.06 * (mid_t * mid_t)
        return r_in_nom + bevel + comfort_curve

    def base_outer_radius_at_z(z):
        dz_edge = min(z, band_w - z)
        if dz_edge < c_out:
            u = (c_out - dz_edge) / c_out
            rim_drop = 0.42 * (u * u)
        else:
            rim_drop = 0.0
        # Subtle recessed frame groove at z = 0.82 mm and z = band_w - 0.82 mm framing the Delta track
        groove_dist = min(abs(z - 0.82), abs(z - (band_w - 0.82)))
        groove = 0.10 * math.exp(-((groove_dist / 0.18) ** 2))
        return r_base_out - rim_drop - groove

    # Construct closed cross-sectional profile loop for each theta:
    #   Segment A (outer wall, z from 0 to band_w): indices 0 .. n_z
    #   Segment B (top rim bridge at z = band_w, r from r_out(band_w) to r_in(band_w)): indices 1 .. n_rim-1
    #   Segment C (inner wall, z from band_w down to 0): indices 0 .. n_z
    #   Segment D (bottom rim bridge at z = 0, r from r_in(0) to r_out(0)): indices 1 .. n_rim-1
    n_prof = (n_z + 1) + (n_rim - 1) + (n_z + 1) + (n_rim - 1)
    verts = []

    for it, th in enumerate(thetas):
        cos_t = math.cos(th)
        sin_t = math.sin(th)

        r_out_0 = base_outer_radius_at_z(0.0)
        r_in_0 = inner_radius_at_z(0.0)
        r_out_top = base_outer_radius_at_z(band_w)
        r_in_top = inner_radius_at_z(band_w)

        # Segment A: Outer wall (z = 0 -> band_w) with raised/rounded Star Trek Delta relief
        for z in zs_up:
            r_base = base_outer_radius_at_z(z)
            h_rel, _ = evaluate_delta_ring_relief(th, z, p)
            r_tot = r_base + h_rel
            verts.append((r_tot * cos_t, r_tot * sin_t, z))

        # Segment B: Top rim at z = band_w (rounded cap from outer rim to inner bore)
        for j in range(1, n_rim):
            frac = j / n_rim
            r_interp = r_out_top + frac * (r_in_top - r_out_top)
            z_cap = band_w
            verts.append((r_interp * cos_t, r_interp * sin_t, z_cap))

        # Segment C: Inner comfort-fit bore (z = band_w -> 0)
        for z in zs_down:
            r_in = inner_radius_at_z(z)
            verts.append((r_in * cos_t, r_in * sin_t, z))

        # Segment D: Bottom rim at z = 0 (flat bed-adhesion ring from inner bore to outer rim)
        for j in range(1, n_rim):
            frac = j / n_rim
            r_interp = r_in_0 + frac * (r_out_0 - r_in_0)
            verts.append((r_interp * cos_t, r_interp * sin_t, 0.0))

    triangles = []
    for it in range(n_theta):
        it_next = (it + 1) % n_theta
        base0 = it * n_prof
        base1 = it_next * n_prof
        for ip in range(n_prof):
            ip_next = (ip + 1) % n_prof
            v00 = verts[base0 + ip]
            v10 = verts[base1 + ip]
            v11 = verts[base1 + ip_next]
            v01 = verts[base0 + ip_next]
            # Outward-pointing winding for right-handed toroidal loop (outer Z up, inner Z down)
            triangles.append((v00, v10, v11))
            triangles.append((v00, v11, v01))

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
        round(max(xs) - min(xs), 2),
        round(max(ys) - min(ys), 2),
        round(max(zs) - min(zs), 2),
    )

    return {
        "num_triangles": len(triangles),
        "unmatched_directed_edges": unmatched_directed,
        "non_manifold_edges": non_manifold_undirected,
        "volume_cm3": round(volume_mm3 / 1000.0, 3),
        "estimated_tpu_weight_g": round((volume_mm3 / 1000.0) * 1.21, 2),
        "dimensions_mm": dims,
        "is_watertight_manifold": (unmatched_directed == 0 and non_manifold_undirected == 0 and volume_mm3 > 0),
    }


def write_binary_stl(filepath, triangles):
    """Writes a standard binary STL file."""
    header = b"Star Trek Delta TPU Ring (US Size 6, 7mm) - Bambu Lab A1 Mini".ljust(80, b"\x00")
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
  <metadata name="Title">Star Trek Delta Raised-Relief TPU Ring (US Size 6, 7mm Width)</metadata>
  <metadata name="Application">BambuStudio</metadata>
  <resources>
    <object id="1" type="model" name="Star_Trek_Delta_Ring_Size6">
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
    """Writes a parametric OpenSCAD source file for the Star Trek Delta TPU Ring."""
    scad = f"""// ============================================================================
// Star Trek Delta Raised-Relief TPU Ring (US Size 6 — 16.51 mm ID, 7.0 mm Width)
// 8 Asymmetric Starfleet Deltas (matched to Delta-shield.png) repeating nose-to-tail
// ============================================================================

inner_diameter      = {p["inner_diameter"]};
band_width          = {p["band_width"]};
base_wall_thickness = {p["base_wall_thickness"]};
num_deltas          = {p["num_deltas"]};
delta_length        = {p["delta_length"]};
delta_wing_span     = {p["delta_wing_span"]};
delta_relief_height = {p["delta_relief_height"]};

$fn = 144;

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

r_in = inner_diameter / 2;
r_out = r_in + base_wall_thickness;

difference() {{
    union() {{
        // Base comfort-fit ring band
        cylinder(h = band_width, r = r_out);

        // 8 Raised & rounded Star Trek Deltas oriented long-wise around the band
        for (i = [0 : num_deltas - 1]) {{
            rotate([0, 0, i * (360 / num_deltas)])
            translate([r_out - 0.2, 0, band_width / 2])
            rotate([0, 90, 0])
            rotate([0, 0, 90])
            linear_extrude(height = delta_relief_height + 0.2, scale = 0.82)
                offset(r = 0.35) offset(delta = -0.35)
                star_trek_delta_2d(delta_wing_span, delta_length);
        }}
    }}
    translate([0, 0, -0.5])
        cylinder(h = band_width + 1.0, r = r_in);
}}
"""
    with open(filepath, "w") as f:
        f.write(scad)


def compute_ring_albedo_and_spec(x, y, z, nx, ny, nz, p):
    """
    Computes a Satin Black TPU + Highlighted Raised Starfleet Delta appearance for the preview:
      - Deep matte charcoal-black TPU base ring band & comfort-fit interior
      - Crisp satin highlight on the raised, pillowed Star Trek Delta domes so the
        repeating nose-to-tail Delta pattern stands out clearly in the preview
    """
    r = math.sqrt(x * x + y * y)
    r_in = p["inner_diameter"] * 0.5
    r_base_out = r_in + p["base_wall_thickness"]

    if r < r_in + 0.55:
        # Smooth comfort-fit interior
        return (32.0, 35.0, 40.0), 26.0, 10.0

    # Check if vertex is on a raised Star Trek Delta
    dr = r - r_base_out
    if dr > 0.06:
        # Raised, rounded Star Trek Delta relief: highlighted metallic-satin slate/gold tint for visibility,
        # or realistic satin sheen on black TPU
        t_rel = clamp(dr / p["delta_relief_height"], 0.0, 1.0)
        return (
            48.0 + 36.0 * t_rel,
            54.0 + 38.0 * t_rel,
            64.0 + 42.0 * t_rel,
        ), 68.0, 16.0

    return (38.0, 42.0, 48.0), 36.0, 10.0


def write_preview_svg(filepath, triangles, p):
    """Renders a 3/4 isometric view of the Star Trek Delta TPU Ring to SVG."""
    yaw = math.radians(24.0)
    pitch = math.radians(28.0)
    z_mid = p["band_width"] * 0.5

    def project(pt):
        x, y, z = pt[0], pt[1], pt[2] - z_mid
        rx = x * math.cos(yaw) - y * math.sin(yaw)
        ry = x * math.sin(yaw) + y * math.cos(yaw)
        sx = rx
        sy = -z * math.cos(pitch) - ry * math.sin(pitch)
        depth = -ry * math.cos(pitch) + z * math.sin(pitch)
        return sx, sy, depth

    light = (-0.36, 0.60, 0.71)
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
        albedo, spec_str, spec_pow = compute_ring_albedo_and_spec(cx, cy, cz, nx, ny, nz, p)
        intensity = 0.36 + 0.64 * dot
        spec = spec_str * pow(max(0.0, dot), spec_pow)
        r = int(clamp(albedo[0] * intensity + spec, 0.0, 255.0))
        g = int(clamp(albedo[1] * intensity + spec, 0.0, 255.0))
        b = int(clamp(albedo[2] * intensity + spec, 0.0, 255.0))
        color = f"#{r:02x}{g:02x}{b:02x}"
        polys.append((avg_depth, q1, q2, q3, color))

    polys.sort(key=lambda item: item[0])

    scale = 24.0
    cx_scr, cy_scr = 400.0, 330.0
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="620" viewBox="0 0 800 620">',
        '  <rect width="100%" height="100%" fill="#0f141c"/>',
        '  <text x="24" y="36" font-family="sans-serif" font-size="20" font-weight="bold" fill="#f0c860">Star Trek Delta Raised-Relief TPU Ring (US Size 6 — 7.0 mm Width)</text>',
        '  <text x="24" y="60" font-family="sans-serif" font-size="14" fill="#9ab0c8">16.51 mm ID | 7.0 mm Wide | 8 Nose-to-Tail Rounded Starfleet Deltas | Bambu Lab A1 Mini</text>',
    ]
    for _, q1, q2, q3, color in polys:
        pts = f"{cx_scr + q1[0]*scale:.2f},{cy_scr + q1[1]*scale:.2f} {cx_scr + q2[0]*scale:.2f},{cy_scr + q2[1]*scale:.2f} {cx_scr + q3[0]*scale:.2f},{cy_scr + q3[1]*scale:.2f}"
        lines.append(f'  <polygon points="{pts}" fill="{color}" stroke="{color}" stroke-width="0.35" stroke-linejoin="round"/>')
    lines.append("</svg>")

    with open(filepath, "w") as f:
        f.write("\n".join(lines))


def write_preview_png(filepath, triangles, p):
    """Renders a high-resolution, Z-buffered Gouraud/Phong shaded dual-view PNG of the ring."""
    width, height = 900, 620
    bg_r, bg_g, bg_b = 16, 22, 30
    rgb = bytearray([bg_r, bg_g, bg_b] * (width * height))
    zbuf = [-1e9] * (width * height)
    z_mid = p["band_width"] * 0.5

    light = (-0.35, 0.58, 0.73)
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

    def render_view(yaw_deg, pitch_deg, roll_deg, cx_scr, cy_scr, scale):
        yaw = math.radians(yaw_deg)
        pitch = math.radians(pitch_deg)
        roll = math.radians(roll_deg)

        def transform_vec(vx, vy, vz):
            rx = vx * math.cos(yaw) - vy * math.sin(yaw)
            ry = vx * math.sin(yaw) + vy * math.cos(yaw)
            sx0 = rx
            sy0 = -vz * math.cos(pitch) - ry * math.sin(pitch)
            depth = -ry * math.cos(pitch) + vz * math.sin(pitch)
            sx = sx0 * math.cos(roll) - sy0 * math.sin(roll)
            sy = sx0 * math.sin(roll) + sy0 * math.cos(roll)
            return sx, sy, depth

        def project(pt):
            return transform_vec(pt[0], pt[1], pt[2] - z_mid)

        v_colors = {}
        for key, (nx, ny, nz) in v_normals.items():
            snx, sny, snz = transform_vec(nx, ny, nz)
            sny = -sny
            dot = max(0.0, snx * light[0] + sny * light[1] + snz * light[2])
            fill = max(0.0, -0.45 * snx - 0.30 * sny + 0.45 * snz) * 0.25
            albedo, spec_str, spec_pow = compute_ring_albedo_and_spec(key[0], key[1], key[2], nx, ny, nz, p)
            intensity = 0.36 + 0.64 * dot + fill
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

    # Left view: 3/4 Isometric view showing the comfort-fit band & repeating raised Starfleet Deltas
    render_view(yaw_deg=22.0, pitch_deg=32.0, roll_deg=0.0, cx_scr=255.0, cy_scr=310.0, scale=18.5)
    # Right view: Upright jewelry-display view (rotated so the front Delta points straight UP like Delta-shield.png!)
    render_view(yaw_deg=0.0, pitch_deg=14.0, roll_deg=-90.0, cx_scr=665.0, cy_scr=310.0, scale=18.5)

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
    print("Building Star Trek Delta Raised-Relief TPU Ring (US Size 6, 7.0 mm Width)...")
    tris = build_star_trek_ring_mesh(PARAMS)
    stats = verify_manifold(tris)
    print("Mesh Verification:", stats)
    if not stats["is_watertight_manifold"]:
        raise RuntimeError(f"Mesh failed manifold check: {stats}")

    stl_path = os.path.join(out_dir, "star_trek_delta_ring.stl")
    threemf_path = os.path.join(out_dir, "star_trek_delta_ring.3mf")
    scad_path = os.path.join(out_dir, "star_trek_delta_ring.scad")
    svg_path = os.path.join(out_dir, "star_trek_delta_ring_preview.svg")
    png_path = os.path.join(out_dir, "star_trek_delta_ring_preview.png")

    write_binary_stl(stl_path, tris)
    write_3mf(threemf_path, tris)
    write_openscad(scad_path, PARAMS)
    write_preview_svg(svg_path, tris, PARAMS)
    write_preview_png(png_path, tris, PARAMS)
    print(f"Successfully generated:\n  - {stl_path}\n  - {threemf_path}\n  - {scad_path}\n  - {svg_path}\n  - {png_path}")

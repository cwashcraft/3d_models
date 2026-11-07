#!/usr/bin/env python3
"""
Parametric 3D Model Generator for Craftsman V20 Handheld Vacuum (CMCVH001B) Wall Mount.
Mimics the two-arm cradle wall hanger design.
Generates:
  1. craftsman_v20_vacuum_mount.stl  (Binary STL)
  2. craftsman_v20_vacuum_mount.3mf  (Bambu Studio / Bambu Handy / MakerWorld 3MF)
  3. craftsman_v20_vacuum_mount.scad (Parametric OpenSCAD source)
  4. preview.svg                     (Isometric + Orthographic technical drawing preview)

Coordinate System (Print Orientation - flat on backplate):
  X: Left (-) to Right (+), centered at X = 0
  Y: Bottom (-) to Top (+), centered at Y = 0
  Z: Back wall face (Z = 0) extending outward to arm tips (Z = +total_Z)
"""

import math
import os
import struct
import zipfile

# ==============================================================================
# PARAMETRIC DIMENSIONS (in millimeters)
# Adjust these values and re-run `python3 generate_vacuum_mount.py` to customize!
# ==============================================================================
PARAMS = {
    # Main cradle geometry (fits the Craftsman V20 CMCVH001B upper battery-base neck)
    "inner_gap_width": 84.0,       # Distance between the inside faces of the two arms (mm)
    "arm_thickness": 11.0,         # Thickness (width in X) of each arm (mm)
    "backplate_width": 114.0,      # Total width of the wall backplate (mm)
    "backplate_height": 62.0,      # Total height of the wall backplate (mm)
    "backplate_thickness": 8.0,    # Base thickness of the backplate on the wall (mm)

    # Center recessed screw channel on backplate
    "center_recess_width": 38.0,   # Width of the thinner center channel between arms (mm)
    "center_recess_depth": 2.5,    # Depth of center channel step (mm)

    # Arm profile (extending from Z = backplate_thickness to Z = total_depth)
    "arm_reach": 92.0,             # How far the arms stick out from the backplate face (mm)
    "arm_base_height": 42.0,       # Vertical height of the arm where it meets the backplate (mm)
    "arm_mid_height": 34.0,        # Vertical height of the arm along the cradle saddle (mm)
    "arm_tip_height": 44.0,        # Vertical height of the front upturned hook (mm)
    "hook_length": 13.0,           # Front-to-back length of the upturned front lip (mm)

    # Inner cradle ledge (the recessed step on the inside top of each arm)
    "ledge_width": 4.5,            # How far the inner step is inset into each arm (mm)
    "ledge_drop": 7.0,             # How deep the inner cradle pocket drops below the outer wall (mm)
    "ledge_back_offset": 12.0,     # Distance from backplate where the inner pocket starts (mm)

    # Mounting screw holes (2 countersunk holes for #8 or #10 wood/drywall screws)
    "hole_spacing_y": 32.0,        # Vertical center-to-center distance between top & bottom screw holes (mm)
    "screw_shaft_dia": 4.8,        # Through-hole diameter for screw threads (mm)
    "countersink_dia": 9.6,        # Outer diameter of countersink cone (mm)
    "countersink_depth": 3.2,      # Depth of countersink cone (mm)

    # Edge chamfer / bevel for smooth finish
    "chamfer": 1.2,                # Edge chamfer size (mm)
}


# ==============================================================================
# 3D MESH BUILDER (Watertight / 2-Manifold Guaranteed via Exact Grid Tessellation)
# ==============================================================================

def build_watertight_mount(p):
    """
    Constructs a guaranteed 2-manifold, watertight triangle mesh of the vacuum mount.
    We use a structured 2D (X, Y) topological grid extruded from Z=0 with exact upper
    surface heights Z_top(x, y) and lower surface heights Z_bot(x, y), plus radial
    rings for the countersunk screw holes.
    """
    inner_w = p["inner_gap_width"]
    arm_t = p["arm_thickness"]
    bp_w = p["backplate_width"]
    bp_h = p["backplate_height"]
    bp_t = p["backplate_thickness"]
    rec_w = p["center_recess_width"]
    rec_d = p["center_recess_depth"]

    arm_reach = p["arm_reach"]
    arm_base_h = p["arm_base_height"]
    arm_mid_h = p["arm_mid_height"]
    arm_tip_h = p["arm_tip_height"]
    hook_len = p["hook_length"]

    ledge_w = p["ledge_width"]
    ledge_drop = p["ledge_drop"]
    ledge_back = p["ledge_back_offset"]

    hole_dy = p["hole_spacing_y"]
    r_shaft = p["screw_shaft_dia"] / 2.0
    r_cs = p["countersink_dia"] / 2.0
    cs_depth = p["countersink_depth"]

    # Instead of a single Z-extrusion (since arms overhang in Z while their Y-height changes),
    # note that in **SIDE/PROJECTION coordinates**:
    # Look at the geometry:
    # 1. Backplate sits on Z in [0, bp_t], X in [-bp_w/2, +bp_w/2], Y in [-bp_h/2, +bp_h/2].
    #    - Center recess is in X in [-rec_w/2, +rec_w/2], where Z_front = bp_t - rec_d.
    #    - Two countersunk holes at X = 0, Y = +hole_dy/2 and Y = -hole_dy/2, going through Z in [0, bp_t - rec_d].
    # 2. Left and Right Arms sit strictly in X intervals:
    #    - Left arm:  X in [-(inner_w/2 + arm_t), -inner_w/2]
    #      Split into outer wall: X in [-(inner_w/2 + arm_t), -(inner_w/2 + ledge_w)]
    #      and inner ledge step:  X in [-(inner_w/2 + ledge_w), -inner_w/2]
    #    - Right arm: X in [+inner_w/2, +(inner_w/2 + arm_t)]
    #      Split into inner ledge step: X in [+inner_w/2, +(inner_w/2 + ledge_w)]
    #      and outer wall:              X in [+(inner_w/2 + ledge_w), +(inner_w/2 + arm_t)]
    #
    # Notice! Every region of X is a clean extrusion along X of a 2D (Z, Y) profile,
    # EXCEPT the screw holes which are circular in (X, Y) inside the center recess [-rec_w/2, +rec_w/2]!
    # Let's verify this!
    # - In X in [-rec_w/2, +rec_w/2]: the profile in (Z, Y) is simply a flat rectangle
    #   Z in [0, bp_t - rec_d], Y in [-bp_h/2, +bp_h/2], with two countersunk holes along Z!
    # - For |X| > rec_w/2: there are NO holes, and the geometry is 100% piecewise-extruded along X
    #   with clean (Z, Y) cross-sections!
    #
    # Let's double check this! If we decompose X into strips:
    # Strip 0 (Center with holes): X in [-rec_w/2, +rec_w/2], Y in [-bp_h/2, +bp_h/2], Z in [0, bp_t - rec_d].
    # For |X| >= rec_w/2, we can use a shared (Z, Y) 2D grid across all X stations!
    # Even better: if every X-station shares the exact same (Z, Y) grid vertices on the boundary
    # X = -rec_w/2 and X = +rec_w/2, the entire mesh is 100% conformally connected and watertight!

    triangles = []

    def add_tri(p1, p2, p3):
        # Ignore degenerate zero-area triangles
        ux, uy, uz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
        vx, vy, vz = p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        if nx * nx + ny * ny + nz * nz > 1e-12:
            triangles.append((p1, p2, p3))

    def add_quad(p1, p2, p3, p4):
        """Adds quad (p1, p2, p3, p4) counter-clockwise when viewed from outside."""
        add_tri(p1, p2, p3)
        add_tri(p1, p3, p4)

    # Let's design a unified, exact 3D voxel/prism decomposition OR a 2D (X, Z) heightfield!
    # Wait: is the mount a two-sided heightfield in Y (i.e. Y_bot(X, Z) <= Y <= Y_top(X, Z))
    # everywhere except the two screw holes?
    # Let's check!
    # At any (X, Z) on the backplate or arms:
    # - On the backplate (0 <= Z <= bp_t):
    #   Y goes from Y_bot = -bp_h/2 to Y_top = +bp_h/2!
    # - On the arms (bp_t <= Z <= bp_t + arm_reach):
    #   At any (X, Z) inside the left or right arm:
    #   Y goes from a single Y_bot(X, Z) to a single Y_top(X, Z)!
    # WAIT A SECOND! Look at `model.jpg`:
    # Does the arm have any overhangs in Y? NO! At every (X, Z) point on the arm:
    # - The bottom of the arm slopes smoothly up from the bottom of the backplate to the front tip.
    # - The top of the arm is horizontal (with the recessed inner ledge and the upturned front hook lip).
    # So at EVERY (X, Z) point on the arms, Y is a single interval [Y_bot(X, Z), Y_top(X, Z)]!
    # Wait—what about the screw holes? The screw holes are in the center of the backplate (|X| < rec_w/2, 0 <= Z <= bp_t - rec_d).
    # What if we build:
    # 1. The Center Backplate Section (`|X| <= rec_w/2`, `0 <= Z <= bp_t - rec_d`, `-bp_h/2 <= Y <= +bp_h/2`)
    #    with the two countersunk screw holes oriented along Z.
    # 2. The Left Wing (`-bp_w/2 <= X <= -rec_w/2`) and Right Wing (`+rec_w/2 <= X <= +bp_w/2`),
    #    which have NO holes and where for every (X, Z) in the wing/arm footprint, Y is simply `[Y_bot(X, Z), Y_top(X, Z)]`!
    #
    # Let's verify this! Is that true?!
    # Let's check every feature of the Left and Right Wings in `model.jpg`:
    # - Outer flange of backplate: `-bp_w/2 <= X <= -(inner_w/2 + arm_t)`, `0 <= Z <= bp_t`.
    #   Here `Y_bot = -bp_h/2`, `Y_top = +bp_h/2`.
    # - Outer wall of Left Arm: `-(inner_w/2 + arm_t) <= X <= -(inner_w/2 + ledge_w)`.
    #   - For `0 <= Z <= bp_t` (backplate part): `Y_bot = -bp_h/2`, `Y_top = +bp_h/2` (or flush with arm top).
    #   - For `bp_t <= Z <= bp_t + arm_reach` (arm part):
    #     `Y_top(Z)` is the outer arm top profile (with front hook at tip),
    #     `Y_bot(Z)` is the sloped bottom edge of the arm!
    # - Inner ledge of Left Arm: `-(inner_w/2 + ledge_w) <= X <= -inner_w/2`.
    #   - For `0 <= Z <= bp_t`: backplate height `[-bp_h/2, +bp_h/2]`.
    #   - For `bp_t <= Z <= bp_t + arm_reach`:
    #     In the middle pocket (`bp_t + ledge_back <= Z <= bp_t + arm_reach - hook_len`),
    #     `Y_top(Z)` drops by `ledge_drop` (`7 mm`) to form the inner cradle step shown in `model.jpg`!
    #     And at the front hook (`bp_t + arm_reach - hook_len <= Z <= bp_t + arm_reach`),
    #     `Y_top(Z)` rises up to the full hook height!
    # - Inner shoulder of backplate between arm and center recess:
    #   `-inner_w/2 <= X <= -rec_w/2`, `0 <= Z <= bp_t`.
    #   Here `Y_bot = -bp_h/2`, `Y_top = +bp_h/2`.
    #   Wait: looking closely at `model.jpg`, between the two arms (`-inner_w/2 <= X <= +inner_w/2`),
    #   there are two vertical reinforcement ribs flanking the screw hole (`rec_w/2` to `inner_w/2`),
    #   and the recessed screw channel in the very center (`-rec_w/2 <= X <= +rec_w/2`)!
    #
    # That means for `|X| >= rec_w/2`, the ENTIRE wing + arm + inner ledge + front hook + backplate flange + vertical rib
    # is 100% defined by a 2D (X, Z) domain where Y spans `[Y_bot(X, Z), Y_top(X, Z)]`!
    # And at the interface `X = -rec_w/2` and `X = +rec_w/2`, the cross-section is simply the rectangle
    # `Z in [0, bp_t]`, `Y in [-bp_h/2, +bp_h/2]`, where `Z in [0, bp_t - rec_d]` connects to the Center Backplate Section!

    # Let's check the vertical alignment of the arms on the backplate in `model.jpg`:
    # Look at the left image in `model.jpg`:
    # - The top of the backplate is slightly higher than the main horizontal arm top, OR the top of the arm base flares up to meet near the top of the backplate, and the bottom of the arm base starts above the bottom of the backplate (leaving a small lip at the bottom of the backplate too), with a curved/angled gusset under the arm!
    # Let's trace the exact profile in `model.jpg`:
    # - Backplate height: `Y` from `-31.0` to `+31.0` (`62 mm` total).
    # - Top of backplate: `Y = +31.0`.
    # - Where the arm meets the backplate (`Z = bp_t = 8.0`):
    #   - The top of the arm has an angled chamfer/fillet down from `Y = +26.0` (at `Z = bp_t`) to `Y = +20.0` (at `Z = bp_t + 12.0`).
    #   - Along the main cradle run (`Z` from `bp_t + 12.0` to `bp_t + arm_reach - hook_len`),
    #     - The outer wall top is at `Y = +20.0`.
    #     - The inner ledge top is at `Y = +20.0 - ledge_drop = +13.0`!
    #   - At the front hook (`Z` from `bp_t + arm_reach - hook_len` to `bp_t + arm_reach`),
    #     - Both outer wall and inner ledge rise up to `Y = +27.0` (a `7 mm` uptick above the outer wall, and `14 mm` above the inner cradle ledge!), with a smooth chamfered front tip.
    #   - Along the bottom of the arm:
    #     - At `Z = bp_t`, there is a lower gusset starting at `Y = -25.0`, angling up to `Y = -18.0` at `Z = bp_t + 10.0`, and then gently tapering upward to `Y = -14.0` at the front tip `Z = bp_t + arm_reach`!
    # Look at `model.jpg` again—that matches the silhouette of the red part in the photo down to every single detail:
    # 1. Backplate flange extending slightly left/right past the arms and slightly above/below the arm base.
    # 2. Vertical rib on each side of the center screw recess.
    # 3. Recessed center channel with countersunk screw hole(s).
    # 4. Arm top with a rear step/slope near the wall, a dropped inner pocket ledge along the middle of the arm, and a matching upturned hook at the front tip.
    # 5. Arm bottom with a small structural gusset at the wall base and a gentle upward taper toward the front tip.

    # Let's make sure the mesh generation is 100% rock-solid, vertex-welded, and 2-manifold!
    # How do we guarantee zero non-manifold edges and zero T-junctions?
    # Let's build the entire part on a single, unified, conformal 3D grid or slice decomposition!
    # Wait: can we build the Left Wing, Right Wing, and Center Section so that at `X = -rec_w/2` and `X = +rec_w/2` they share the exact same Y and Z vertices?
    # Yes! Let's trace how:
    # Suppose in the Center Section (`-rec_w/2 <= X <= +rec_w/2`), `Z` goes from `0` to `z_rec = bp_t - rec_d`.
    # On the plane `X = +rec_w/2` (and `X = -rec_w/2`), the Center Section occupies:
    # `Z in [0, z_rec]`, `Y in [-bp_h/2, +bp_h/2]`.
    # Its boundary at `X = +rec_w/2` has vertices along:
    # - `Z = 0`, `Y in [y_0, y_1, ..., y_M]`
    # - `Z = z_rec`, `Y in [y_0, y_1, ..., y_M]`
    # - `Y = -bp_h/2`, `Z in [0, z_rec]`
    # - `Y = +bp_h/2`, `Z in [0, z_rec]`
    # Wait: if the Wing is triangulated as `Y in [Y_bot(X, Z), Y_top(X, Z)]` over `(X, Z)`, then on `X = +rec_w/2`, the Wing only has vertices at `Y = Y_bot = -bp_h/2` and `Y = Y_top = +bp_h/2` (no intermediate Y vertices), whereas the Center Section might have intermediate Y vertices if we split Y into Top Hole and Bottom Hole!
    # Can the Center Section ALSO have NO intermediate Y vertices on `X = +/- rec_w/2`?
    # YES! Look:
    # In the `(X, Y)` plane of the Center Section (`X in [-rec_w/2, +rec_w/2]`, `Y in [-bp_h/2, +bp_h/2]`):
    # The outer perimeter of the Center Section at `X = -rec_w/2` and `X = +rec_w/2` only needs 3 Y-coordinates:
    # `Y = -bp_h/2`, `Y = 0.0`, `Y = +bp_h/2` (or even just `-bp_h/2` and `+bp_h/2` if we connect both hole rings to the 4 outer corners + midpoints)!
    # Even simpler: if we include `Y = 0.0` (or whatever Y-levels we want) in BOTH or if we only put intermediate Y vertices on the interior, there are ZERO T-junctions on `X = +/- rec_w/2`!

    # Wait—let's check! If the Wing has only `Y_bot` and `Y_top` at each `(X, Z)`, what happens where `Y_top(X, Z)` has a vertical step in `X` (like at `X = -(inner_w/2 + ledge_w)` where the inner ledge drops by `ledge_drop`)?
    # In a 2D `(X, Z)` grid where each cell `[x_i, x_{i+1}] x [z_j, z_{j+1}]` has its own `Y_top` and `Y_bot` at the 4 corners of the cell:
    # Across a step in `X` (say at `x = x_step`), on the left of `x_step`, `Y_top` is `Y_top_left(z)`, and on the right of `x_step`, `Y_top` is `Y_top_right(z)`.
    # Along the vertical wall at `x = x_step`, for each `z`-segment `[z_j, z_{j+1}]`, the left face has edge `(z_j, Y_top_left(z_j)) -> (z_{j+1}, Y_top_left(z_{j+1}))` and the right face has edge `(z_j, Y_top_right(z_j)) -> (z_{j+1}, Y_top_right(z_{j+1}))`.
    # The vertical step wall simply bridges `(z_j, Y_top_right(z_j)) - (z_{j+1}, Y_top_right(z_{j+1})) - (z_{j+1}, Y_top_left(z_{j+1})) - (z_j, Y_top_left(z_j))`!
    # Every single edge is shared by EXACTLY 2 triangles!
    # Wait: what about the front/back ends in Z (`z = 0`, `z = bp_t`, `z = bp_t + arm_reach`) where a strip starts or ends?
    # At `z = bp_t`, for `X` outside the arms (e.g., outer flange `X < -(inner_w/2 + arm_t)` or inner rib `-inner_w/2 < X < -rec_w/2`), the solid stops at `z = bp_t`!
    # Meanwhile, for `X` inside the arm (`-(inner_w/2 + arm_t) <= X <= -inner_w/2`), the solid continues for `z > bp_t`, with `Y_top(z)` and `Y_bot(z)` inside `[ -bp_h/2, +bp_h/2 ]`!
    # Hold on! At `z = bp_t`, inside the arm X-range, the backplate has `Y in [-bp_h/2, +bp_h/2]`, while the arm at `z = bp_t+` has `Y in [Y_bot_arm, Y_top_arm]` which is a sub-interval of `[-bp_h/2, +bp_h/2]`!
    # And on the side of the arm (`X = -inner_w/2` and `X = -(inner_w/2 + arm_t)`), at `z = bp_t`, the backplate spans `[-bp_h/2, +bp_h/2]`, whereas the arm side wall only spans `[Y_bot_arm(z), Y_top_arm(z)]`!
    # If at `z = bp_t` the backplate vertical edge goes straight from `-bp_h/2` to `+bp_h/2` in one segment, while the arm side wall attaches to `[Y_bot_arm(bp_t), Y_top_arm(bp_t)]`, that would be a T-junction along the vertical line `(X_arm, Y, z = bp_t)` UNLESS the backplate also has Y-nodes at `Y_bot_arm(bp_t)` and `Y_top_arm(bp_t)`!

    # BINGO! That insight is why a 3D structured cell complex `(X_i, Y_j, Z_k)` (or deformed 3D hexahedral mesh) is SO much cleaner and 100% immune to T-junctions!
    # Let's think about that!
    # What if we represent the mount as a collection of 3D hexahedral blocks (bricks) on a shared `(i, j, k)` topological grid, where node `(i, j, k)` has coordinates `(X(i,j,k), Y(i,j,k), Z(i,j,k))`?
    # Let's check! In a 3D grid of hexahedral cells `(i, j, k)`:
    # - Some cells are SOLID (`active = True`), and some cells are EMPTY (`active = False`).
    # - A face between cell `A` and cell `B` is emitted as 2 triangles IF AND ONLY IF one cell is SOLID and the other is EMPTY!
    # - Because every active cell shares the EXACT same corner vertex indices `(i, j, k)` with its neighbors, and every boundary quad is split along a consistent diagonal, a mesh generated from boundary faces of a 3D hexahedral complex is MATHEMATICALLY GUARANTEED to be 100% watertight, 2-manifold, zero-self-intersection, and zero-T-junction!

    # WAIT A SECOND! Pause and appreciate how clean that is!
    # Let's verify if we can express the ENTIRE Craftsman V20 Vacuum Wall Mount (including the sloped arm bottom, upturned front hook, recessed inner cradle step, recessed center screw channel, and countersunk screw holes) as a deformed 3D hexahedral mesh!
    # Let's check every single feature:
    # 1. X-grid (`i`):
    #    - `x0 = -bp_w/2` (-57.0): Left edge of backplate
    #    - `x1 = -(inner_w/2 + arm_t)` (-53.0): Outer face of left arm
    #    - `x2 = -(inner_w/2 + ledge_w)` (-46.5): Inner step of left arm
    #    - `x3 = -inner_w/2` (-42.0): Inner face of left arm
    #    - `x4 = -rec_w/2` (-19.0): Left edge of center screw recess
    #    - `x5 = +rec_w/2` (+19.0): Right edge of center screw recess
    #    - `x6 = +inner_w/2` (+42.0): Inner face of right arm
    #    - `x7 = +(inner_w/2 + ledge_w)` (+46.5): Inner step of right arm
    #    - `x8 = +(inner_w/2 + arm_t)` (+53.0): Outer face of right arm
    #    - `x9 = +bp_w/2` (+57.0): Right edge of backplate
    #    Plus we can add thin chamfer strips (`1.2 mm`) at the key X transitions for smooth beveled edges!
    #
    # 2. Z-grid (`k`):
    #    - `z0 = 0.0`: Back wall plane
    #    - `z1 = bp_t - cs_depth` (2.3): Bottom of countersink cone
    #    - `z2 = bp_t - rec_d` (5.5): Face of center screw recess
    #    - `z3 = bp_t` (8.0): Front face of backplate / base of arms
    #    - `z4 = bp_t + ledge_back` (20.0): Start of inner cradle pocket
    #    - `z5 = bp_t + arm_reach - hook_len - 3.0` (84.0): End of inner cradle pocket / start of hook ramp
    #    - `z6 = bp_t + arm_reach - hook_len` (87.0): Top of front hook inner face
    #    - `z7 = bp_t + arm_reach - 2.0` (98.0): Front hook top flat end
    #    - `z8 = bp_t + arm_reach` (100.0): Front tip of arms (chamfered)
    #
    # 3. Y-grid (`j`):
    #    Wait: as `Z` increases along the arm (`z3` to `z8`), the bottom of the arm slopes UP, and the top of the arm steps DOWN into the cradle and UP at the hook!
    #    Can we keep fixed Y-layers `j` in the topological grid and deform their `Y(j, k)` coordinates along `Z` (`k`), OR use discrete Y-layers that turn on/off, OR both?
    #    Let's trace!
    #    Suppose in Y we have layers:
    #    - `j = 0..1`: Bottom flange of backplate (`Y` from `-bp_h/2` to `Y_arm_bot(z)`) — active only in backplate (`k < k_arm_start`)!
    #    - `j = 1..2`: Main arm body (`Y` from `Y_arm_bot(z)` to `Y_ledge_floor(z)`) — active in backplate AND entire arm (`x` in arms)!
    #    - `j = 2..3`: Ledge / Cradle wall layer (`Y` from `Y_ledge_floor(z)` to `Y_outer_top(z)`) — active in backplate, outer arm wall, arm rear shoulder, and front hook, and INACTIVE in the inner ledge pocket (`x in [x2, x3]` and `[x6, x7]`, `z in [z4, z5]`)!
    #    - `j = 3..4`: Hook tip / Upper backplate layer (`Y` from `Y_outer_top(z)` to `Y_hook_top(z)`) — active in backplate, arm rear shoulder (`z3..z4`), and front hook (`z5..z8`), and INACTIVE in the middle of the arm!
    #    - `j = 4..5`: Top flange of backplate (`Y` from `Y_hook_top(z)` to `+bp_h/2`) — active only in backplate (`k < k_arm_start`)!
    #
    # HOLD EVERYTHING! Read those 5 Y-layers (`j = 0..5`) again!
    # Let's check if every layer has strictly positive height (`Y(j+1, k) > Y(j, k)`) for EVERY `k`:
    # Let's pick the 6 Y-functions of `z`:
    # - `Y_0(z) = -bp_h / 2` = `-31.0` (constant)
    # - `Y_1(z)` = Bottom edge of the arm!
    #   - For `0 <= z <= bp_t`: `Y_1(z) = -24.0`
    #   - For `bp_t < z <= bp_t + 10`: slopes up from `-24.0` to `-17.0` (rear lower gusset!)
    #   - For `bp_t + 10 < z <= bp_t + arm_reach`: tapers smoothly up from `-17.0` to `-13.0` at the front tip!
    # - `Y_2(z)` = Floor of the inner cradle ledge!
    #   - Constant `Y_2(z) = +13.0` (or smoothly contoured)
    # - `Y_3(z)` = Top of the outer arm wall!
    #   - Constant `Y_3(z) = +20.0` (so `Y_3 - Y_2 = 7.0 mm` = `ledge_drop`!)
    # - `Y_4(z)` = Top of the front hook & rear upper arm shoulder!
    #   - Constant `Y_4(z) = +26.5` (so `Y_4 - Y_3 = 6.5 mm` hook rise above outer wall, and `13.5 mm` total hook height above the inner cradle ledge!)
    # - `Y_5(z) = +bp_h / 2` = `+31.0` (constant)
    #
    # Look at those 6 functions `Y_0(z) < Y_1(z) < Y_2(z) < Y_3(z) < Y_4(z) < Y_5(z)`:
    # At EVERY `z` from `0` to `100 mm`:
    # `-31.0 < Y_1(z) (in [-24, -13]) < +13.0 < +20.0 < +26.5 < +31.0`!
    # They NEVER cross or touch! Every single Y-layer `j in {0, 1, 2, 3, 4}` has strictly positive thickness everywhere!
    # AND look what we can do by smoothly varying `Y_k(z)` along `z`:
    # - Between `z3` (`8 mm`) and `z4` (`20 mm`), the top of the arm (`Y_4(z)`) can slope smoothly from `+26.5` down to `+21.5` if we want an angled rear transition, OR step cleanly at `z4`!
    # - Even better: at the front hook (`z5` to `z8`), `Y_4(z)` can have a smooth ramp up on the inside of the hook and a bevel on the front tip (`z7` to `z8`)!
    # - What about the countersunk screw holes in the center section (`x in [x4, x5]`, `z in [z0, z2]`)?
    #   In the center section (`x in [x4, x5]`), ONLY the backplate (`z in [z0, z2]`) is active! Nothing is in front of `z2` (`z > z2` is completely empty in `x in [x4, x5]`).
    #   So we can seamlessly replace the center block `x in [x4, x5]`, `y in [Y_0, Y_5]`, `z in [z0, z2]` with a custom meshed block containing the 2 circular countersunk holes whose outer perimeter matches the exact grid nodes along `x = x4`, `x = x5`, `y = Y_0`, and `y = Y_5`, and `z = z0, z1, z2`!

    # Let's double-check that!
    # On the left/right boundaries of the center recess (`x = x4 = -rec_w/2` and `x = x5 = +rec_w/2`), what are the grid nodes of the hexahedral grid?
    # - In `Z`: `z0 = 0.0`, `z1 = z_cs_start`, `z2 = bp_t - rec_d` (plus `z3 = bp_t` for the rib step above `z2`).
    # - In `Y`: `Y_0 = -31.0`, `Y_1 = -24.0`, `Y_2 = +13.0`, `Y_3 = +20.0`, `Y_4 = +26.5`, `Y_5 = +31.0`!
    # Wait: if we also add `Y = 0.0` into the `Y` grid (splitting `Y_1..Y_2` at `Y = 0.0`), then:
    # - The bottom screw hole (centered at `X = 0, Y = -16.0`, radius `4.8 mm`, so `Y in [-20.8, -11.2]`) lies ENTIRELY inside the single Y-interval `[Y_1 = -24.0, Y_mid = 0.0]`!
    # -Wait: what about the top screw hole (centered at `X = 0, Y = +16.0`, radius `4.8 mm`, so `Y in [+11.2, +20.8]`)?
    # If we shift `Y_2` and `Y_3` OR if we check where the screw hole is in `model.jpg`:
    # LOOK AT `model.jpg` (left photo)!
    # How many screws are in `model.jpg`?!
    # Look closely at the left photo in `model.jpg`!
    # There is ONE screw in the upper-middle of the recess (`Y` around `+12 mm`), and wait—is there a second screw hole below it, covered by the shadow or lower down?
    # Let's zoom in or inspect `model.jpg` carefully!
    # In the left image of `model.jpg`:
    # You can clearly see a Phillips pan-head / countersunk screw near the top-center of the recessed channel. And below it, at the bottom of the recessed channel (partially in shadow between the arms), is there a lower hole or is it a 2-hole vertical pattern?
    # Let's check the vertical position of the visible screw in `model.jpg`:
    # The visible screw is at roughly 1/3 down from the top of the backplate (around `Y = +10 mm`), and a matching bottom hole at 1/3 up from the bottom of the backplate is at `Y = -10 mm` (or `Y = +/- 12 mm`).
    # Wait: why would `Y_2` (`+13.0`) and `Y_3` (`+20.0`) interfere with the center block at `x in [x4, x5]`?
    # They ONLY touch `x = x4` and `x = x5` along the vertical lines `(x = +/- rec_w/2, z in [z0, z2])`!
    # In the 2D rectangle `X in [-rec_w/2, +rec_w/2]`, `Y in [-bp_h/2, +bp_h/2]`, the two circular holes are in the INTERIOR (`X` in `[-4.8, +4.8]`, far away from `X = +/- 19.0`)!
    # That means on the boundary of the rectangle `X in [-19, +19] x Y in [-31, +31]`, we can have ANY boundary vertices we want along `X = -19` and `X = +19` (specifically `Y_0, Y_1, Y_2, Y_3, Y_4, Y_5`), and connect them inward to the 2 circular holes in the interior!
    # Let's verify that!
    # Since the holes have radius `r_cs = 4.8 mm` (centered at `X = 0`), and the center zone extends to `X = -19.0` and `X = +19.0`, there is more than `14 mm` of flat margin between the outer edge of the countersink (`X = +/- 4.8`) and the vertical walls at `X = +/- 19.0`!
    # So we can put an intermediate box around each hole (say `X in [-10, +10]`), where:
    # - Outside `X in [-10, +10]` (i.e. `X in [-19, -10]` and `X in [+10, +19]`), it's just the regular hexahedral grid with `Y_0..Y_5`!
    # - Inside `X in [-10, +10]`, we split `Y` cleanly at `Y_split = 0.0` into TWO square hole blocks:
    #   - Bottom hole block: `X in [-10, +10]`, `Y in [-31, 0]`, containing the bottom circular hole at `(0, -14.0)`!
    #   - Top hole block: `X in [-10, +10]`, `Y in [0, +31]`, containing the top circular hole at `(0, +14.0)`!
    #   - And on the boundary `X = -10` and `X = +10`, the boundary vertices of the two hole blocks are simply `Y = [-31.0, -24.0, 0.0, +13.0, +20.0, +26.5, +31.0]`!
    #
    # STOP AND ADMIRE THAT!
    # Let's trace that geometry:
    # 1. Every boundary point on `X = -10`, `X = +10`, `Y = -31`, `Y = 0`, `Y = +31` of the two hole blocks is explicitly connected by radial fans to the circular hole ring (`N_circle = 48` points)!
    # 2. Outside `X in [-10, +10]`, the entire rest of the 3D model is a single hexahedral grid using those EXACT same `Y` levels `[-31.0, -24.0, 0.0, +13.0, +20.0, +26.5, +31.0]`!
    # 3. Every single vertex, edge, and face between the hole blocks and the hexahedral grid matches 1-to-1!

    # Let's test this in Python and write a manifold checker (`check_manifold(triangles)`) that verifies:
    # - Every directed edge `(u, v)` has a matching reverse directed edge `(v, u)`
    # - Total unmatched edges == 0
    # - Total edges shared by != 2 triangles == 0
    # - Signed volume > 0 (all normals pointing outward)

    # Let's refine the exact coordinates and features of the hexahedral grid so the model looks sleek, strong, and faithful to `model.jpg`.

    # --- X Grid Stations ---
    # Backplate half-width: bp_w / 2 = 57.0
    # Outer face of arm: inner_w / 2 + arm_t = 42.0 + 11.0 = 53.0
    # Inner ledge step of arm: inner_w / 2 + ledge_w = 42.0 + 4.5 = 46.5
    # Inner face of arm: inner_w / 2 = 42.0
    # Edge of center recess: rec_w / 2 = 19.0
    # Hole zone boundary: hole_box_x = 10.0
    x_right = [
        10.0,                           # i_r0: Hole box right edge
        rec_w / 2.0,                    # i_r1: Center recess right wall (19.0)
        inner_w / 2.0,                  # i_r2: Inner face of right arm (42.0)
        inner_w / 2.0 + ledge_w,        # i_r3: Inner ledge step of right arm (46.5)
        inner_w / 2.0 + arm_t,          # i_r4: Outer face of right arm (53.0)
        bp_w / 2.0,                     # i_r5: Right outer edge of backplate (57.0)
    ]
    x_grid = [-x for x in reversed(x_right)] + x_right
    # Indices in x_grid (length 12, so 11 X-intervals 0..10):
    # x_grid[0]  = -57.0 (left backplate edge)
    # x_grid[1]  = -53.0 (left arm outer face)
    # x_grid[2]  = -46.5 (left arm ledge step)
    # x_grid[3]  = -42.0 (left arm inner face)
    # x_grid[4]  = -19.0 (left recess wall)
    # x_grid[5]  = -10.0 (left hole box edge)
    # --- hole box is X-interval 5: [-10.0, +10.0] ---
    # x_grid[6]  = +10.0 (right hole box edge)
    # x_grid[7]  = +19.0 (right recess wall)
    # x_grid[8]  = +42.0 (right arm inner face)
    # x_grid[9]  = +46.5 (right arm ledge step)
    # x_grid[10] = +53.0 (right arm outer face)
    # x_grid[11] = +57.0 (right backplate edge)

    # --- Z Grid Stations ---
    z_rec = bp_t - rec_d                # 8.0 - 2.5 = 5.5 mm (center recess thickness)
    z_cs = z_rec - cs_depth             # 5.5 - 3.2 = 2.3 mm (countersink cone bottom)
    # Let's add multiple Z stations along the arm so the bottom taper, rear gusset, and front hook ramp are smooth!
    z_arm_end = bp_t + arm_reach        # 8.0 + 92.0 = 100.0 mm
    z_hook_start = z_arm_end - hook_len # 100.0 - 13.0 = 87.0 mm
    z_ledge_start = bp_t + ledge_back   # 8.0 + 12.0 = 20.0 mm

    z_grid = [
        0.0,                            # k=0: Wall face
        z_cs,                           # k=1: Countersink bottom (2.3)
        z_rec,                          # k=2: Center recess front face (5.5)
        bp_t,                           # k=3: Backplate front face (8.0)
        bp_t + 6.0,                     # k=4: Mid rear gusset (14.0)
        z_ledge_start,                  # k=5: End of rear gusset / start of inner cradle pocket (20.0)
        40.0,                           # k=6: Mid arm 1
        62.0,                           # k=7: Mid arm 2
        z_hook_start - 2.5,             # k=8: End of inner cradle pocket / base of hook ramp (84.5)
        z_hook_start,                   # k=9: Front hook inner crest (87.0)
        z_arm_end - 2.0,                # k=10: Front hook top flat end (98.0)
        z_arm_end,                      # k=11: Front tip of arm (100.0)
    ]
    # 12 Z-stations -> 11 Z-intervals (k = 0..10)

    # --- Y Grid Stations as a function of Z index k ---
    # We have 7 Y-stations (j = 0..6 -> 6 Y-intervals j = 0..5):
    # j=0: Bottom of backplate (-31.0)
    # j=1: Bottom edge of arm (sloping from -25.0 at wall to -13.0 at tip)
    # j=2: Center split line Y = 0.0 (separates bottom and top screw hole boxes)
    # j=3: Inner cradle ledge floor (+13.0)
    # j=4: Outer arm wall top (+20.0)
    # j=5: Front hook top & rear arm top shoulder (+26.5, beveled at tip k=11 to +24.5)
    # j=6: Top of backplate (+31.0)

    def get_y_stations(k):
        z = z_grid[k]
        y0 = -bp_h / 2.0  # -31.0

        # Smooth bottom profile of the arm:
        # At k<=3 (z<=8.0): -25.0 (includes lower gusset base)
        # At k=4 (z=14.0): -19.5 (gusset curve)
        # At k=5 (z=20.0): -17.0 (main arm bottom start)
        # From z=20.0 to z=100.0: tapers linearly from -17.0 to -12.5
        if z <= bp_t:
            y1 = -25.0
        elif z <= bp_t + 6.0:
            t = (z - bp_t) / 6.0
            y1 = -25.0 + t * (-19.5 - (-25.0))
        elif z <= z_ledge_start:
            t = (z - (bp_t + 6.0)) / (z_ledge_start - (bp_t + 6.0))
            y1 = -19.5 + t * (-17.0 - (-19.5))
        else:
            t = (z - z_ledge_start) / (z_arm_end - z_ledge_start)
            y1 = -17.0 + t * (-12.5 - (-17.0))

        y2 = 0.0
        y3 = 20.0 - ledge_drop  # +13.0 (inner cradle ledge floor)
        y4 = 20.0               # +20.0 (outer arm wall top)

        # Top of hook / rear shoulder:
        # At k<=3 (z<=8.0): +26.5
        # At k=4 (z=14.0): +25.0
        # At k=5 (z=20.0): +23.5 (rear top shoulder taper)
        # At k=8 (z=84.5): +24.5
        # At k=9 (z=87.0): +27.0 (front hook height)
        # At k=10 (z=98.0): +27.0
        # At k=11 (z=100.0): +25.0 (front tip top bevel)
        if z <= bp_t:
            y5 = 26.5
        elif z <= z_ledge_start:
            t = (z - bp_t) / (z_ledge_start - bp_t)
            y5 = 26.5 - t * 3.0
        elif z < z_hook_start:
            y5 = 24.5
        elif z <= z_arm_end - 2.0:
            y5 = 27.0
        else:
            y5 = 25.0

        y6 = bp_h / 2.0   # +31.0
        return [y0, y1, y2, y3, y4, y5, y6]

    nx = len(x_grid) - 1  # 11 cells in X (0..10)
    ny = 6                # 6 cells in Y (0..5)
    nz = len(z_grid) - 1  # 11 cells in Z (0..10)

    # Determine which hexahedral cells (i, j, k) are active (excluding the hole box i == 5, which is meshed specially)
    def is_cell_active(i, j, k):
        # Hole box (i == 5, X in [-10, +10]) is handled by the radial hole mesher for k in {0, 1},
        # and is empty for k >= 2. However, for adjacency checks from i=4 and i=6:
        if i == 5:
            return k in (0, 1)

        # Backplate region: k in {0, 1, 2} (Z in [0, 8.0])
        if k in (0, 1):
            # Full backplate is solid everywhere for Z in [0, 5.5]
            return True
        if k == 2:
            # Z in [5.5, 8.0]: solid everywhere EXCEPT the center recess (i in {4, 5, 6}, i.e., X in [-19, +19])
            # Wait: x_grid[4] = -19.0, x_grid[7] = +19.0, so i in {4, 5, 6} is inside [-19, +19]!
            return i not in (4, 5, 6)

        # Arms region: k >= 3 (Z > 8.0)
        # Left arm is i in {1, 2} (X in [-53.0, -42.0])
        #   - i == 1: outer wall of left arm (X in [-53.0, -46.5])
        #   - i == 2: inner ledge of left arm (X in [-46.5, -42.0])
        # Right arm is i in {8, 9} (X in [+42.0, +53.0])
        #   - i == 8: inner ledge of right arm (X in [+42.0, +46.5])
        #   - i == 9: outer wall of right arm (X in [+46.5, +53.0])
        is_outer_arm = i in (1, 9)
        is_inner_ledge = i in (2, 8)
        if not (is_outer_arm or is_inner_ledge):
            return False

        # Vertical (Y) extent of arms:
        # j=0 (-31 to Y_bot) and j=5 (Y_hook to +31) are only on the backplate, never on the arms
        if j in (0, 5):
            return False

        # j=1 (Y_bot to 0) and j=2 (0 to +13.0) are the lower & middle body of the arm -> always solid along the arm!
        if j in (1, 2):
            return True

        # j=3 (+13.0 to +20.0): upper arm wall above the inner cradle ledge
        # - Solid on the outer arm walls (i in {1, 9}) for the entire arm length!
        # - On the inner ledge (i in {2, 8}):
        #   - Solid near the backplate (k in {3, 4}, Z in [8, 20])
        #   - EMPTY in the middle pocket (k in {5, 6, 7, 8}, Z in [20, 87.0]) -> creates the recessed inner ledge!
        #   - Solid at the front hook (k in {9, 10}, Z in [87, 100])
        if j == 3:
            if is_outer_arm:
                return True
            else:
                return k in (3, 4, 9, 10)

        # j=4 (+20.0 to Y_hook): top rear shoulder and front hook lip
        # - Solid at the rear shoulder against the backplate (k in {3, 4}, Z in [8, 20])
        # - Solid at the front upturned hook (k in {9, 10}, Z in [87, 100])
        if j == 4:
            return k in (3, 4, 9, 10)

        return False

    def vertex(i, j, k):
        x = x_grid[i]
        y = get_y_stations(k)[j]
        z = z_grid[k]
        return (x, y, z)

    # Emit boundary faces for all hexahedral cells (except i == 5 which is emitted by the hole mesher)
    for i in range(nx):
        if i == 5:
            continue
        for j in range(ny):
            for k in range(nz):
                if not is_cell_active(i, j, k):
                    continue

                # Check 6 neighbors:
                # 1. -X face (neighbor i-1)
                if i == 0 or not is_cell_active(i - 1, j, k):
                    add_quad(
                        vertex(i, j, k),
                        vertex(i, j, k + 1),
                        vertex(i, j + 1, k + 1),
                        vertex(i, j + 1, k),
                    )
                # 2. +X face (neighbor i+1)
                if i == nx - 1 or not is_cell_active(i + 1, j, k):
                    add_quad(
                        vertex(i + 1, j, k),
                        vertex(i + 1, j + 1, k),
                        vertex(i + 1, j + 1, k + 1),
                        vertex(i + 1, j, k + 1),
                    )
                # 3. -Y face (neighbor j-1)
                if j == 0 or not is_cell_active(i, j - 1, k):
                    add_quad(
                        vertex(i, j, k),
                        vertex(i + 1, j, k),
                        vertex(i + 1, j, k + 1),
                        vertex(i, j, k + 1),
                    )
                # 4. +Y face (neighbor j+1)
                if j == ny - 1 or not is_cell_active(i, j + 1, k):
                    add_quad(
                        vertex(i, j + 1, k),
                        vertex(i, j + 1, k + 1),
                        vertex(i + 1, j + 1, k + 1),
                        vertex(i + 1, j + 1, k),
                    )
                # 5. -Z face (neighbor k-1)
                if k == 0 or not is_cell_active(i, j, k - 1):
                    add_quad(
                        vertex(i, j, k),
                        vertex(i, j + 1, k),
                        vertex(i + 1, j + 1, k),
                        vertex(i + 1, j, k),
                    )
                # 6. +Z face (neighbor k+1)
                if k == nz - 1 or not is_cell_active(i, j, k + 1):
                    add_quad(
                        vertex(i, j, k + 1),
                        vertex(i + 1, j, k + 1),
                        vertex(i + 1, j + 1, k + 1),
                        vertex(i, j + 1, k + 1),
                    )

    # Now mesh the Center Hole Box (i == 5, X in [-10.0, +10.0], k in {0, 1}, Z in [0, z_rec])!
    # We split Y at j=2 (Y = 0.0) into:
    # - Bottom hole block: j in {0, 1}, Y in [y0 (-31.0), y2 (0.0)], hole centered at (0.0, -hole_dy/2 = -16.0)
    #   Wait: let's make sure the bottom hole at Y = -16.0 is well inside [y0=-31.0, y2=0.0] and its perimeter
    #   matches the left/right boundary vertices at Y = [y0 (-31.0), y1 (-25.0), y2 (0.0)]!
    # - Top hole block: j in {2, 3, 4, 5}, Y in [y2 (0.0), y6 (+31.0)], hole centered at (0.0, +hole_dy/2 = +16.0),
    #   and its outer perimeter matches the left/right boundary vertices at Y = [y2 (0.0), y3 (+13.0), y4 (+20.0), y5 (+26.5), y6 (+31.0)]!
    y_at_0 = get_y_stations(0)  # Note: for k=0,1,2 (z <= bp_t), get_y_stations(k) is identical!

    def mesh_hole_subblock(y_list, hole_cy, is_bottom_block, is_top_block):
        """
        Meshes a rectangular region X in [-10, +10], Y in [y_list[0], y_list[-1]], Z in [z0, z1, z2]
        with a countersunk circular hole at (0.0, hole_cy).
        The outer rectangle perimeter has exact vertices:
          - Right edge (X = +10): (10, y_list[0..M])
          - Top edge   (Y = y_list[-1]): (10, y_top) -> (-10, y_top)
          - Left edge  (X = -10): (-10, y_list[M..0])
          - Bottom edge(Y = y_list[0]): (-10, y_bot) -> (10, y_bot)
        """
        # Build counter-clockwise outer perimeter vertices in (X, Y) starting from bottom-right (10, y_list[0])
        perim = []
        # Right edge (going up: y_list[0] -> y_list[-1])
        for y in y_list[:-1]:
            perim.append((10.0, y))
        # Top edge (going left: +10 -> -10)
        perim.append((10.0, y_list[-1]))
        perim.append((0.0, y_list[-1]))
        # Left edge (going down: y_list[-1] -> y_list[0])
        for y in reversed(y_list[1:]):
            perim.append((-10.0, y))
        # Bottom edge (going right: -10 -> +10)
        perim.append((-10.0, y_list[0]))
        perim.append((0.0, y_list[0]))

        n_perim = len(perim)
        # Subdivide each circular ring into a multiple of n_perim so every perimeter segment maps cleanly to a fan of circle points!
        segs_per_edge = 4
        n_circ = n_perim * segs_per_edge

        def circle_pt(idx, radius):
            # Angle aligned with perimeter point idx
            # Compute angle of the corresponding perimeter point around (0, hole_cy) and interpolate smoothly!
            edge_i = idx // segs_per_edge
            sub_t = (idx % segs_per_edge) / float(segs_per_edge)
            p_a = perim[edge_i]
            p_b = perim[(edge_i + 1) % n_perim]
            px = p_a[0] + sub_t * (p_b[0] - p_a[0])
            py = p_a[1] + sub_t * (p_b[1] - p_a[1])
            ang = math.atan2(py - hole_cy, px - 0.0)
            return (radius * math.cos(ang), hole_cy + radius * math.sin(ang))

        # Verify angles are strictly increasing around the circle:
        # Since (0, hole_cy) is strictly inside the convex rectangle [-10, 10] x [y_list[0], y_list[-1]],
        # walking counter-clockwise around the perimeter produces strictly increasing polar angles!

        # 1. Back face at Z = z_grid[0] (0.0), radius = r_shaft
        # Normal points in -Z, so wind clockwise when viewed from +Z
        z0 = z_grid[0]
        z1 = z_grid[1]
        z2 = z_grid[2]

        for e_i in range(n_perim):
            pa = perim[e_i]
            pb = perim[(e_i + 1) % n_perim]
            c_start = e_i * segs_per_edge
            # Fan from pa to circle segments [c_start .. c_start + segs_per_edge], then triangle (pa, c_end, pb)
            for s in range(segs_per_edge):
                ca_s = circle_pt(c_start + s, r_shaft)
                cb_s = circle_pt((c_start + s + 1) % n_circ, r_shaft)
                # Back face (-Z) at z0:
                add_tri((pa[0], pa[1], z0), (ca_s[0], ca_s[1], z0), (cb_s[0], cb_s[1], z0))

                ca_c = circle_pt(c_start + s, r_cs)
                cb_c = circle_pt((c_start + s + 1) % n_circ, r_cs)
                # Front face (+Z) at z2:
                add_tri((pa[0], pa[1], z2), (cb_c[0], cb_c[1], z2), (ca_c[0], ca_c[1], z2))

            c_end_shaft = circle_pt((c_start + segs_per_edge) % n_circ, r_shaft)
            c_end_cs = circle_pt((c_start + segs_per_edge) % n_circ, r_cs)
            # Closing triangle of the edge sector:
            # Back face (-Z) at z0:
            add_tri((pa[0], pa[1], z0), (c_end_shaft[0], c_end_shaft[1], z0), (pb[0], pb[1], z0))
            # Front face (+Z) at z2:
            add_tri((pa[0], pa[1], z2), (pb[0], pb[1], z2), (c_end_cs[0], c_end_cs[1], z2))

        # 2. Inner hole bore & countersink walls:
        for idx in range(n_circ):
            nxt = (idx + 1) % n_circ
            ca_s = circle_pt(idx, r_shaft)
            cb_s = circle_pt(nxt, r_shaft)
            ca_c = circle_pt(idx, r_cs)
            cb_c = circle_pt(nxt, r_cs)

            # Cylindrical shaft wall from z0 to z1 (normal points inward toward hole center):
            add_quad(
                (ca_s[0], ca_s[1], z0),
                (ca_s[0], ca_s[1], z1),
                (cb_s[0], cb_s[1], z1),
                (cb_s[0], cb_s[1], z0),
            )
            # Conical countersink wall from z1 (r_shaft) to z2 (r_cs):
            add_quad(
                (ca_s[0], ca_s[1], z1),
                (ca_c[0], ca_c[1], z2),
                (cb_c[0], cb_c[1], z2),
                (cb_s[0], cb_s[1], z1),
            )

        # 3. Outer bottom wall at Y = -bp_h/2 (if is_bottom_block) and outer top wall at Y = +bp_h/2 (if is_top_block)
        # Note: X = -10 and X = +10 are internal interfaces shared with hexahedral cells i=4 and i=6 (which are solid for k=0,1),
        # and Y = 0.0 is an internal interface shared between the bottom hole block and top hole block!
        # Wait: because the bottom edge of bottom_block has midpoint (0, y_list[0]) and top edge of top_block has midpoint (0, y_list[-1]),
        # let's emit the exterior bottom wall (Y = -31.0) and exterior top wall (Y = +31.0) for k in {0, 1}:
        if is_bottom_block:
            yb = y_list[0]
            for kx in range(2):
                za, zb = z_grid[kx], z_grid[kx + 1]
                # Segment 1: (-10, yb) to (0, yb)
                add_quad((-10.0, yb, za), (0.0, yb, za), (0.0, yb, zb), (-10.0, yb, zb))
                # Segment 2: (0, yb) to (+10, yb)
                add_quad((0.0, yb, za), (10.0, yb, za), (10.0, yb, zb), (0.0, yb, zb))

        if is_top_block:
            yt = y_list[-1]
            for kx in range(2):
                za, zb = z_grid[kx], z_grid[kx + 1]
                # Segment 1: (+10, yt) to (0, yt)
                add_quad((10.0, yt, za), (0.0, yt, za), (0.0, yt, zb), (10.0, yt, zb))
                # Segment 2: (0, yt) to (-10, yt)
                add_quad((0.0, yt, za), (-10.0, yt, za), (-10.0, yt, zb), (0.0, yt, zb))

    # Mesh bottom hole subblock (j = 0..2 -> y_at_0[0..2] = [-31.0, -25.0, 0.0])
    mesh_hole_subblock(y_at_0[0:3], -hole_dy / 2.0, is_bottom_block=True, is_top_block=False)
    # Mesh top hole subblock (j = 2..6 -> y_at_0[2..6] = [0.0, 13.0, 20.0, 26.5, 31.0])
    mesh_hole_subblock(y_at_0[2:7], +hole_dy / 2.0, is_bottom_block=False, is_top_block=True)

    return triangles


def verify_manifold(triangles):
    """Verifies that the triangle mesh is 100% closed, 2-manifold, and has positive volume."""
    def quantize(pt):
        return (round(pt[0], 5), round(pt[1], 5), round(pt[2], 5))

    directed_edges = {}
    undirected_counts = {}
    vol6 = 0.0

    for p1, p2, p3 in triangles:
        q1, q2, q3 = quantize(p1), quantize(p2), quantize(p3)
        for u, v in ((q1, q2), (q2, q3), (q3, q1)):
            directed_edges[(u, v)] = directed_edges.get((u, v), 0) + 1
            key = tuple(sorted((u, v)))
            undirected_counts[key] = undirected_counts.get(key, 0) + 1

        # Signed 6*volume contribution
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
        "volume_cm3": volume_mm3 / 1000.0,
        "is_watertight_manifold": (unmatched_directed == 0 and non_manifold_undirected == 0 and volume_mm3 > 0),
    }


def write_binary_stl(filepath, triangles):
    """Writes a standard binary STL file."""
    header = b"Craftsman V20 Handheld Vacuum Wall Mount - Bambu Ready".ljust(80, b"\x00")
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
    """Writes a standard 3MF archive compatible with Bambu Studio, MakerWorld, and Bambu Handy."""
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

    # Position on standard 256x256 Bambu build plate (centered at X=128, Y=128, Z=0)
    model_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <metadata name="Title">Craftsman V20 Handheld Vacuum Wall Mount</metadata>
  <metadata name="Application">BambuStudio</metadata>
  <resources>
    <object id="1" type="model" name="Craftsman_V20_Vacuum_Mount">
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
    <item objectid="1" transform="1 0 0 0 1 0 0 0 1 128 128 0"/>
  </build>
</model>"""

    with zipfile.ZipFile(filepath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("3D/3dmodel.model", model_xml)


def write_openscad(filepath, p):
    """Writes a clean, fully parametric OpenSCAD file for future customization."""
    scad = f"""// ============================================================================
// Craftsman V20 Handheld Vacuum (CMCVH001B) Wall Mount - Parametric OpenSCAD
// Matches the 2-arm cradle wall hanger design.
// Print Orientation: Flat on the backplate (Z = 0 on build plate, no supports!)
// ============================================================================

inner_gap_width     = {p["inner_gap_width"]};
arm_thickness       = {p["arm_thickness"]};
backplate_width     = {p["backplate_width"]};
backplate_height    = {p["backplate_height"]};
backplate_thickness = {p["backplate_thickness"]};
center_recess_width = {p["center_recess_width"]};
center_recess_depth = {p["center_recess_depth"]};

arm_reach           = {p["arm_reach"]};
hook_length         = {p["hook_length"]};
ledge_width         = {p["ledge_width"]};
ledge_drop          = {p["ledge_drop"]};
ledge_back_offset   = {p["ledge_back_offset"]};

hole_spacing_y      = {p["hole_spacing_y"]};
screw_shaft_dia     = {p["screw_shaft_dia"]};
countersink_dia     = {p["countersink_dia"]};
countersink_depth   = {p["countersink_depth"]};

$fn = 64;

module arm_outer_profile() {{
    // 2D profile in (Z_arm, Y)
    polygon(points=[
        [0, -25.0],
        [6.0, -19.5],
        [ledge_back_offset, -17.0],
        [arm_reach, -12.5],
        [arm_reach, 25.0],
        [arm_reach - 2.0, 27.0],
        [arm_reach - hook_len, 27.0],
        [arm_reach - hook_len, 20.0],
        [ledge_back_offset, 20.0],
        [6.0, 26.5],
        [0, 26.5]
    ]);
}}

module arm_inner_ledge_cutout() {{
    // Cuts the inner step ledge pocket
    translate([0, 20.0 - ledge_drop, bp_t + ledge_back_offset])
        cube([ledge_width + 1.0, 15.0, arm_reach - ledge_back_offset - hook_len]);
}}

bp_t = backplate_thickness;

difference() {{
    union() {{
        // Backplate
        translate([-backplate_width/2, -backplate_height/2, 0])
            cube([backplate_width, backplate_height, backplate_thickness]);

        // Left Arm
        translate([-(inner_gap_width/2 + arm_thickness), 0, bp_t])
            rotate([90, 0, 90])
                linear_extrude(height=arm_thickness)
                    arm_outer_profile();

        // Right Arm
        translate([inner_gap_width/2, 0, bp_t])
            rotate([90, 0, 90])
                linear_extrude(height=arm_thickness)
                    arm_outer_profile();
    }}

    // Center recessed screw channel
    translate([-center_recess_width/2, -backplate_height/2 - 1, bp_t - center_recess_depth])
        cube([center_recess_width, backplate_height + 2, center_recess_depth + 1]);

    // Left Arm inner ledge step
    translate([-(inner_gap_width/2 + ledge_width), 20.0 - ledge_drop, bp_t + ledge_back_offset])
        cube([ledge_width + 0.1, 15.0, arm_reach - ledge_back_offset - hook_len]);

    // Right Arm inner ledge step
    translate([inner_gap_width/2 - 0.1, 20.0 - ledge_drop, bp_t + ledge_back_offset])
        cube([ledge_width + 0.1, 15.0, arm_reach - ledge_back_offset - hook_len]);

    // Two countersunk mounting screw holes
    for (sy = [-hole_spacing_y/2, hole_spacing_y/2]) {{
        translate([0, sy, -0.1])
            cylinder(d=screw_shaft_dia, h=bp_t + 1);
        translate([0, sy, bp_t - center_recess_depth - countersink_depth])
            cylinder(d1=screw_shaft_dia, d2=countersink_dia, h=countersink_depth + 0.05);
    }}
}}
"""
    with open(filepath, "w") as f:
        f.write(scad)


def write_preview_svg(filepath, triangles):
    """Renders a shaded isometric 3D view of the generated mesh to an SVG file."""
    # Rotate model so it is viewed from an isometric wall-mounted angle (matching model.jpg!)
    # In our model: X is left-right, Y is down-up, Z is wall-to-front.
    # Let's project (X, Z, Y) from an oblique front-left angle:
    yaw = math.radians(-32.0)
    pitch = math.radians(22.0)

    def project(pt):
        x, y, z = pt
        # Horizontal plane is (x, z), vertical axis is y
        rx = x * math.cos(yaw) + z * math.sin(yaw)
        rz = -x * math.sin(yaw) + z * math.cos(yaw)
        sx = rx
        sy = -y * math.cos(pitch) + rz * math.sin(pitch)
        depth = y * math.sin(pitch) + rz * math.cos(pitch)
        return sx, sy, depth

    light = (-0.35, 0.65, 0.67)
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

        # Backface culling in screen space
        cross_2d = (q2[0] - q1[0]) * (q3[1] - q1[1]) - (q2[1] - q1[1]) * (q3[0] - q1[0])
        if cross_2d >= 0:
            continue

        avg_depth = (q1[2] + q2[2] + q3[2]) / 3.0
        dot = max(0.0, nx * light[0] + ny * light[1] + nz * light[2])
        intensity = 0.32 + 0.68 * dot
        # Craftsman Red shading
        r = int(min(255, 225 * intensity + 15))
        g = int(min(255, 32 * intensity + 5))
        b = int(min(255, 42 * intensity + 8))
        color = f"#{r:02x}{g:02x}{b:02x}"
        polys.append((avg_depth, q1, q2, q3, color))

    polys.sort(key=lambda item: item[0])

    scale = 3.6
    cx, cy = 400.0, 290.0
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="540" viewBox="0 0 800 540">',
        '  <rect width="100%" height="100%" fill="#f4f5f7"/>',
        '  <text x="24" y="36" font-family="sans-serif" font-size="20" font-weight="bold" fill="#222">Craftsman V20 Handheld Vacuum Wall Mount (3D Mesh Preview)</text>',
        '  <text x="24" y="60" font-family="sans-serif" font-size="14" fill="#555">Inner Cradle Width: 84.0 mm | Arm Reach: 92.0 mm | Backplate: 114 x 62 x 8 mm | Watertight 2-Manifold</text>',
    ]
    for _, q1, q2, q3, color in polys:
        pts = f"{cx + q1[0]*scale:.2f},{cy + q1[1]*scale:.2f} {cx + q2[0]*scale:.2f},{cy + q2[1]*scale:.2f} {cx + q3[0]*scale:.2f},{cy + q3[1]*scale:.2f}"
        lines.append(f'  <polygon points="{pts}" fill="{color}" stroke="{color}" stroke-width="0.4" stroke-linejoin="round"/>')
    lines.append("</svg>")

    with open(filepath, "w") as f:
        f.write("\n".join(lines))


def write_preview_png(filepath, triangles):
    """Renders a shaded isometric 3D view + side/top orthographic views to a PNG file using pure Python (zlib + struct)."""
    import zlib

    width, height = 800, 520
    # Initialize background buffer (#f4f5f7) and z-buffer
    bg_r, bg_g, bg_b = 244, 245, 247
    rgb = bytearray([bg_r, bg_g, bg_b] * (width * height))
    zbuf = [-1e9] * (width * height)

    yaw = math.radians(-32.0)
    pitch = math.radians(22.0)

    def project(pt):
        x, y, z = pt
        rx = x * math.cos(yaw) + z * math.sin(yaw)
        rz = -x * math.sin(yaw) + z * math.cos(yaw)
        sx = rx
        sy = -y * math.cos(pitch) + rz * math.sin(pitch)
        depth = y * math.sin(pitch) + rz * math.cos(pitch)
        return sx, sy, depth

    light = (-0.35, 0.65, 0.67)
    l_norm = math.sqrt(sum(c * c for c in light))
    light = tuple(c / l_norm for c in light)

    scale = 3.8
    cx, cy = 410.0, 275.0

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

        x1, y1, z1 = cx + q1[0] * scale, cy + q1[1] * scale, q1[2]
        x2, y2, z2 = cx + q2[0] * scale, cy + q2[1] * scale, q2[2]
        x3, y3, z3 = cx + q3[0] * scale, cy + q3[1] * scale, q3[2]

        denom = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
        if abs(denom) < 1e-6:
            continue

        dot = max(0.0, nx * light[0] + ny * light[1] + nz * light[2])
        intensity = 0.28 + 0.72 * dot
        r = int(min(255, 225 * intensity + 15))
        g = int(min(255, 28 * intensity + 6))
        b = int(min(255, 38 * intensity + 8))

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
                        # Highlight triangle edges slightly near boundary? Keep clean solid shading
                        rgb[idx * 3] = r
                        rgb[idx * 3 + 1] = g
                        rgb[idx * 3 + 2] = b

    # Encode RGB buffer as PNG
    raw_rows = bytearray()
    for y in range(height):
        raw_rows.append(0)  # Filter type 0 (None)
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
    tris = build_watertight_mount(PARAMS)
    stats = verify_manifold(tris)
    print("Mesh Verification:", stats)
    if not stats["is_watertight_manifold"]:
        raise RuntimeError(f"Mesh failed manifold check: {stats}")

    stl_path = os.path.join(out_dir, "craftsman_v20_vacuum_mount.stl")
    threemf_path = os.path.join(out_dir, "craftsman_v20_vacuum_mount.3mf")
    scad_path = os.path.join(out_dir, "craftsman_v20_vacuum_mount.scad")
    svg_path = os.path.join(out_dir, "craftsman_v20_vacuum_mount_preview.svg")
    png_path = os.path.join(out_dir, "craftsman_v20_vacuum_mount_preview.png")

    write_binary_stl(stl_path, tris)
    write_3mf(threemf_path, tris)
    write_openscad(scad_path, PARAMS)
    write_preview_svg(svg_path, tris)
    write_preview_png(png_path, tris)
    print(f"Successfully generated:\n  - {stl_path}\n  - {threemf_path}\n  - {scad_path}\n  - {svg_path}\n  - {png_path}")

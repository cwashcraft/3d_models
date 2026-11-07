// ============================================================================
// Craftsman V20 Handheld Vacuum (CMCVH001B) Wall Mount - Parametric OpenSCAD
// Matches the 2-arm cradle wall hanger design.
// Print Orientation: Flat on the backplate (Z = 0 on build plate, no supports!)
// ============================================================================

inner_gap_width     = 84.0;
arm_thickness       = 11.0;
backplate_width     = 114.0;
backplate_height    = 62.0;
backplate_thickness = 8.0;
center_recess_width = 38.0;
center_recess_depth = 2.5;

arm_reach           = 92.0;
hook_length         = 13.0;
ledge_width         = 4.5;
ledge_drop          = 7.0;
ledge_back_offset   = 12.0;

hole_spacing_y      = 32.0;
screw_shaft_dia     = 4.8;
countersink_dia     = 9.6;
countersink_depth   = 3.2;

$fn = 64;

module arm_outer_profile() {
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
}

module arm_inner_ledge_cutout() {
    // Cuts the inner step ledge pocket
    translate([0, 20.0 - ledge_drop, bp_t + ledge_back_offset])
        cube([ledge_width + 1.0, 15.0, arm_reach - ledge_back_offset - hook_len]);
}

bp_t = backplate_thickness;

difference() {
    union() {
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
    }

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
    for (sy = [-hole_spacing_y/2, hole_spacing_y/2]) {
        translate([0, sy, -0.1])
            cylinder(d=screw_shaft_dia, h=bp_t + 1);
        translate([0, sy, bp_t - center_recess_depth - countersink_depth])
            cylinder(d1=screw_shaft_dia, d2=countersink_dia, h=countersink_depth + 0.05);
    }
}

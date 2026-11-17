// ============================================================================
// LARQ Bottle PureVis 2 (23 oz / 680 ml) Star Trek Delta Mesh TPU Boot
// Print Orientation: Upright on flat base (Z = 0), zero supports required
// ============================================================================

inner_diameter       = 74.6;
wall_thickness       = 3.2;
total_height         = 85.0;
base_thickness       = 4.5;
center_vent_diameter = 15.0;
num_columns          = 18;
delta_width          = 10.2;
delta_height         = 16.2;

$fn = 120;

module star_trek_delta_2d(w, h) {
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
}

module radial_delta_cutter(z_center, angle_deg, w, h, r_out) {
    rotate([0, 0, angle_deg])
    translate([0, 0, z_center])
    rotate([90, 0, 90])
    linear_extrude(height = r_out + 5, center = false)
        offset(r = 0.6) offset(delta = -0.6)
        star_trek_delta_2d(w, h);
}

difference() {
    // Outer cylindrical boot body with bottom cup-holder chamfer
    hull() {
        translate([0, 0, 3.2])
            cylinder(h = total_height - 3.2, d = inner_diameter + 2 * wall_thickness);
        cylinder(h = 3.2, d1 = inner_diameter + 2 * wall_thickness - 5.4, d2 = inner_diameter + 2 * wall_thickness);
    }

    // Inner bottle cavity
    translate([0, 0, base_thickness])
        cylinder(h = total_height, d = inner_diameter);

    // Center bottom air-escape vent hole
    translate([0, 0, -1])
        cylinder(h = base_thickness + 2, d = center_vent_diameter);

    // 54 Interlocking Starfleet Delta Lattice Cutouts
    for (c = [0 : num_columns - 1]) {
        ang = c * (360 / num_columns);
        if (c % 2 == 0) {
            for (zc = [21.1, 36.7, 52.3, 67.9])
                radial_delta_cutter(zc, ang, delta_width, delta_height, inner_diameter);
        } else {
            for (zc = [28.9, 44.5, 60.1])
                radial_delta_cutter(zc, ang, delta_width, delta_height, inner_diameter);
            radial_delta_cutter(18.0, ang, 9.0, 9.2, inner_diameter);
            radial_delta_cutter(71.7, ang, 8.4, 8.2, inner_diameter);
        }
    }
}

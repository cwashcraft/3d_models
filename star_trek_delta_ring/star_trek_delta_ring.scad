// ============================================================================
// Star Trek Delta Raised-Relief TPU Ring (US Size 6 — 16.51 mm ID, 7.0 mm Width)
// 8 Asymmetric Starfleet Deltas (matched to Delta-shield.png) repeating nose-to-tail
// ============================================================================

inner_diameter      = 16.51;
band_width          = 7.0;
base_wall_thickness = 1.85;
num_deltas          = 8;
delta_length        = 7.8;
delta_wing_span     = 4.9;
delta_relief_height = 0.9;

$fn = 144;

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

r_in = inner_diameter / 2;
r_out = r_in + base_wall_thickness;

difference() {
    union() {
        // Base comfort-fit ring band
        cylinder(h = band_width, r = r_out);

        // 8 Raised & rounded Star Trek Deltas oriented long-wise around the band
        for (i = [0 : num_deltas - 1]) {
            rotate([0, 0, i * (360 / num_deltas)])
            translate([r_out - 0.2, 0, band_width / 2])
            rotate([0, 90, 0])
            rotate([0, 0, 90])
            linear_extrude(height = delta_relief_height + 0.2, scale = 0.82)
                offset(r = 0.35) offset(delta = -0.35)
                star_trek_delta_2d(delta_wing_span, delta_length);
        }
    }
    translate([0, 0, -0.5])
        cylinder(h = band_width + 1.0, r = r_in);
}

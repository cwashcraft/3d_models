// ============================================================================
// Wooting 80HE Geometry Dash 2-Tone Arrow Keycaps (4-Key Set — Official OEM R1 Profile)
// Filament Swap Pause at Z = 10.20 mm (Layer 51 @ 0.20mm layer height)
// ============================================================================

base_width          = 18.1;
top_width_x         = 12.7;
top_width_y         = 14.2;
front_height        = 8.4;
back_height         = 10.0;
top_shift_y         = -0.65;
dish_depth_x        = 0.72;
stem_boss_diameter  = 5.8;
cross_span          = 4.18;
cross_slot_x        = 1.32;
cross_slot_y        = 1.36;
cross_depth         = 4.6;
grid_pitch          = 21.0;

$fn = 64;

module rounded_rect(wx, wy, r) {
    offset(r = r)
        square([wx - 2 * r, wy - 2 * r], center = true);
}

module wooting_oem_r1_1u_keycap_base() {
    difference() {
        // Outer tapered 1u OEM R1 profile body (raised on back edge)
        hull() {
            linear_extrude(height = 0.1)
                rounded_rect(base_width, base_width, 1.4);
            translate([0, top_shift_y, (front_height + back_height) * 0.5])
                rotate([atan2(back_height - front_height, top_width_y), 0, 0])
                linear_extrude(height = 0.1)
                rounded_rect(top_width_x, top_width_y, 1.15);
        }

        // Cylindrical concave finger scoop across top surface
        translate([0, top_shift_y, (front_height + back_height) * 0.5 + 28.0 - dish_depth_x])
            rotate([90 + atan2(back_height - front_height, top_width_y), 0, 0])
            cylinder(h = top_width_y + 6.0, r = 28.0, center = true, $fn = 128);

        // Internal vaulted cavity around central stem boss
        difference() {
            hull() {
                translate([0, 0, -0.1])
                    linear_extrude(height = 3.8)
                    rounded_rect(base_width - 3.0, base_width - 3.0, 0.8);
                translate([0, top_shift_y * 0.7, 6.8])
                    linear_extrude(height = 0.1)
                    rounded_rect(6.2, 6.8, 0.5);
            }
            cylinder(h = 7.2, d = stem_boss_diameter);
        }

        // Wooting Lekker V2 / Cherry MX '+' cross-stem slot
        translate([0, 0, -0.1])
        linear_extrude(height = cross_depth + 0.1) {
            square([cross_span, cross_slot_x], center = true);
            square([cross_slot_y, cross_span], center = true);
        }
    }
}

for (gx = [-0.5, 0.5])
    for (gy = [-0.5, 0.5])
        translate([gx * grid_pitch, gy * grid_pitch, 0])
            wooting_oem_r1_1u_keycap_base();

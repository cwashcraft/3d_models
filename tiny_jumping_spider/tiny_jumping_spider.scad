// ============================================================================
// Tiny Jumping Spider (Salticidae) - Parametric OpenSCAD Source
// Support-Free Print Orientation: Flat on Z = 0 build plate
// Purely round articulated capsule legs (coxa -> femur -> patella -> tibia -> paw)
// ============================================================================

scale_factor     = 1.0;
head_width       = 11.6;
head_length      = 10.6;
head_height      = 11.0;
head_center_y    = 3.5;

abdomen_width    = 12.2;
abdomen_length   = 13.6;
abdomen_height   = 10.6;
abdomen_center_y = -6.8;

ame_radius       = 1.8;
ale_radius       = 1.08;
ple_radius       = 0.92;
leg_thickness    = 1.42;
pedipalp_radius  = 1.35;

$fn = 48;

module round_capsule(a, b, ra, rb) {
    hull() {
        translate(a) sphere(r=ra);
        translate(b) sphere(r=rb);
    }
}

scale([scale_factor, scale_factor, scale_factor])
intersection() {
    translate([-50, -50, 0]) cube([100, 100, 50]); // Flat base at Z = 0
    union() {
        // Cephalothorax
        hull() {
            translate([0, head_center_y, head_height*0.5])
                scale([head_width/2, head_length/2, head_height/2]) sphere(r=1);
            translate([0, head_center_y + 2.1, head_height*0.68])
                scale([head_width*0.43, head_length*0.29, head_height*0.27]) sphere(r=1);
            translate([0, head_center_y, 0])
                scale([head_width*0.38, head_length*0.38, 0.2]) cylinder(r=1, h=1);
        }

        // Abdomen
        hull() {
            translate([0, abdomen_center_y, abdomen_height*0.5])
                scale([abdomen_width/2, abdomen_length/2, abdomen_height/2]) sphere(r=1);
            translate([0, abdomen_center_y, 0])
                scale([abdomen_width*0.40, abdomen_length*0.40, 0.2]) cylinder(r=1, h=1);
        }

        // 8 Jumping Spider Eyes (AME, ALE, PME, PLE)
        for (side = [-1, 1]) {
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
        }
    }
}

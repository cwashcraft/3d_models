// ============================================================================
// Keeshond Dog (inspired by dog.jpg & AKC Breed Standard) - Parametric OpenSCAD
// Print Orientation: Standing on 4 paws flat on Z = 0 build plate
// ============================================================================

scale_factor      = 1.0;
chest_width       = 17.6;
body_length       = 28.5;
ruff_radius       = 10.6;
skull_width       = 12.6;
muzzle_length     = 7.4;
ear_height        = 7.6;
tongue_length     = 3.4;
tail_plume_radius = 4.6;
leg_radius        = 2.35;

$fn = 48;

module round_capsule(a, b, ra, rb) {
    hull() {
        translate(a) sphere(r=ra);
        translate(b) sphere(r=rb);
    }
}

scale([scale_factor, scale_factor, scale_factor])
intersection() {
    translate([-50, -50, 0]) cube([100, 100, 80]);
    union() {
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
        for (side = [-1, 1]) {
            hull() {
                translate([side*2.3, 13.9, 34.0]) sphere(r=1.45);
                translate([side*5.2, 12.7, 32.8]) sphere(r=1.45);
                translate([side*4.4, 14.1, 34.0 + ear_height]) sphere(r=0.48);
            }
            round_capsule([side*4.2, 8.2, 15.0], [side*3.6, 9.1, 1.25], leg_radius*1.4, leg_radius*0.86);
            round_capsule([side*3.6, 9.1, 1.25], [side*3.5, 11.0, 1.10], leg_radius*0.90, leg_radius*0.96);
            round_capsule([side*4.8, -10.2, 16.0], [side*4.6, -12.2, 5.6], leg_radius*1.8, leg_radius*0.98);
            round_capsule([side*4.6, -12.2, 5.6], [side*4.5, -11.6, 1.25], leg_radius*0.92, leg_radius*0.84);
            round_capsule([side*4.5, -11.6, 1.25], [side*4.5, -9.7, 1.10], leg_radius*0.86, leg_radius*0.92);
        }

        // Tightly Curled Plume Tail Over Back
        round_capsule([0, -15.6, 20.0], [0.5, -16.8, 29.2], tail_plume_radius*0.65, tail_plume_radius*0.96);
        round_capsule([0.5, -16.8, 29.2], [0.8, -13.0, 31.2], tail_plume_radius*0.96, tail_plume_radius*1.02);
        round_capsule([0.8, -13.0, 31.2], [1.4, -5.0, 25.5], tail_plume_radius*1.02, tail_plume_radius*0.72);
    }
}

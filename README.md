# 3D Models Repository

Collection of custom parametric 3D-printable models, OpenSCAD sources, and Bambu Lab A1 Mini wireless deployment utilities.

## Models

| Model | Directory | Description |
| :--- | :--- | :--- |
| **Craftsman V20 Handheld Vacuum Wall Mount (`CMCVH001B`)** | [`craftsman_v20_vacuum_mount/`](craftsman_v20_vacuum_mount/) | Two-arm wall cradle with recessed inner ledges and retention hooks for the Craftsman V20 cordless handheld vacuum. |
| **Tiny Jumping Spider (*Salticidae*)** | [`tiny_jumping_spider/`](tiny_jumping_spider/) | Cute miniature jumping spider with 8 sculpted eyes, fuzzy pedipalps, dorsal abdomen chevrons, and 8 round articulated legs. |
| **LARQ Bottle PureVis 2 (`23 oz`) Star Trek Delta Mesh Boot** | [`larq2_star_trek_boot/`](larq2_star_trek_boot/) | Flexible TPU protective bottle sleeve (`74.6 mm` ID × `85.0 mm` tall) with `54` interlocking Starfleet Delta cutouts, underside Delta vents, and central air-escape hole for the Bambu Lab A1 Mini. |
| **Star Trek Delta Raised-Relief TPU Ring (`US Size 6.5`, `7 mm` Width)** | [`star_trek_delta_ring/`](star_trek_delta_ring/) | Comfort-fit TPU band (`17.05 mm` ID × `7.0 mm` wide) with `8` raised, pillowed Starfleet Delta shields repeating nose-to-tail around the circumference. |
| **Wooting 80HE Arrow Keycaps — 2-Tone Geometry Dash Set (`4x 1u OEM R1`)** | [`wooting_80he_keycaps/`](wooting_80he_keycaps/) | Sculpted OEM R1 arrow keycaps (`Cube`, `Ship`, `Ball`, `UFO`) with sloped/cylindrically concave finger dishes, Lekker V2 (`+`) stems, and automatic `M400 U1` filament-swap pause (`Z = 10.20 mm`) for 2-tone White + Blue PLA Matte printing without AMS. |

## Shared Scripts & Documentation

- **[`scripts/deploy_to_printer.py`](scripts/deploy_to_printer.py)** — Generic build, headless Bambu Studio slicer (`v02.08.02.61`), and wireless FTPS uploader (`port 990`) that can slice and deploy any model folder (`--model-dir <folder>`) directly to a Bambu Lab A1 Mini.
- **[`scripts/check_print_status.py`](scripts/check_print_status.py)** — Generic live MQTT print status checker (`port 8883`) + built-in camera JPEG snapshot grabber (`port 6000`) that pushes photo updates to `ntfy.sh`.
- **[`KB.md`](KB.md)** — Knowledge base covering Bambu Lab A1 Mini hardware/slicing presets, MakerWorld `.3mf` requirements, headless Bambu Studio CLI automation, and direct wireless FTPS printing.

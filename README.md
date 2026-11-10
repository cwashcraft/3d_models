# 3D Models Repository

Collection of custom parametric 3D-printable models, OpenSCAD sources, and Bambu Lab A1 Mini wireless deployment utilities.

## Models

| Model | Directory | Description |
| :--- | :--- | :--- |
| **Craftsman V20 Handheld Vacuum Wall Mount (`CMCVH001B`)** | [`craftsman_v20_vacuum_mount/`](craftsman_v20_vacuum_mount/) | Two-arm wall cradle with recessed inner ledges and retention hooks for the Craftsman V20 cordless handheld vacuum. |
| **Tiny Jumping Spider (*Salticidae*)** | [`tiny_jumping_spider/`](tiny_jumping_spider/) | Cute miniature jumping spider with 8 sculpted eyes, fuzzy pedipalps, dorsal abdomen chevrons, and 8 round articulated legs. |

## Shared Scripts & Documentation

- **[`scripts/deploy_to_printer.py`](scripts/deploy_to_printer.py)** — Generic build, headless Bambu Studio slicer (`v02.08.02.61`), and wireless FTPS uploader (`port 990`) that can slice and deploy any model folder (`--model-dir <folder>`) directly to a Bambu Lab A1 Mini.
- **[`scripts/check_print_status.py`](scripts/check_print_status.py)** — Generic live MQTT print status checker (`port 8883`) + built-in camera JPEG snapshot grabber (`port 6000`) that pushes photo updates to `ntfy.sh`.
- **[`KB.md`](KB.md)** — Knowledge base covering Bambu Lab A1 Mini hardware/slicing presets, MakerWorld `.3mf` requirements, headless Bambu Studio CLI automation, and direct wireless FTPS printing.

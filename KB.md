# 3D Modeling & Bambu Lab / MakerWorld Knowledge Base

This knowledge base documents lessons learned, technical workflows, troubleshooting solutions, and headless CLI automation for designing 3D models and exporting valid `.3mf` / `.stl` files for **Bambu Studio**, **MakerWorld**, and **Bambu Handy** (specifically targeting the **Bambu Lab A1 mini**).

---

## 1. Bambu Lab A1 Mini Hardware & Slicing Reference

| Specification | Value | Notes |
| :--- | :--- | :--- |
| **Printer Model Name** | `Bambu Lab A1 mini` | Exact string required in `Metadata/project_settings.config` |
| **Internal Model ID** | `N1` | Required in `Metadata/slice_info.config` (`printer_model_id`) |
| **Build Volume** | `180 × 180 × 180 mm` | Center of bed is `(90, 90, 0)` |
| **Default Nozzle** | `0.4 mm` | Standard preset: `Bambu Lab A1 mini 0.4 nozzle` |
| **Default Build Plate** | `Textured PEI Plate` | Note: A1 mini does **not** support `Cool Plate` or `Engineering Plate` for PETG |
| **Recommended Filaments** | `PETG`, `PLA`, `PLA+`, `TPU` | Open-frame printer (avoid high-warp ABS/ASA) |

### Recommended Structural / Wall-Mount Print Settings (`0.20mm Strength @BBL A1M`)
- **Layer Height:** `0.20 mm`
- **Wall Loops:** `4` to `5` (critical for cantilever arms and screw countersinks)
- **Sparse Infill Density:** `25% – 35%`
- **Sparse Infill Pattern:** `gyroid`
- **Supports:** `0` (Disabled when part is designed to print flat on its backplate with overhangs `>45°`)

---

## 2. MakerWorld `.3mf` Upload Troubleshooting

### Error 1: `"The file is 0 bytes"` on MakerWorld Upload
**Causes & Solutions:**
1. **GitHub Web Download Pitfall:** Right-clicking a file link in GitHub's file browser and selecting *"Save Link As..."* downloads an HTML page or a `0 byte` stub instead of the binary `.3mf`. Always click into the file page on GitHub and click the **"Download raw file"** button (or `git pull` locally).
2. **"Print Profile (.3mf)" vs. "Raw Model Files" Upload Slot:**
   - MakerWorld's **Print Profile** uploader strictly expects a Bambu Studio container (`Metadata/project_settings.config`, `Metadata/model_settings.config`, `Metadata/slice_info.config`, and `3D/Objects/object_1.model`).
   - A generic geometry-only `.3mf` (containing only `3D/3dmodel.model`) will fail validation in the Print Profile slot and should either be uploaded under **Raw Model Files** (alongside `.stl`) or exported through Bambu Studio.

### Error 2: `"The printer in the 3mf is not supported"`
**Cause:**
- Running `bambu-studio --export-3mf out.3mf input.stl` from the CLI **without** loading a resolved Bambu Lab machine profile leaves `"printer_model": ""` (blank) and defaults to a generic `200 × 200 mm` Marlin profile in `Metadata/project_settings.config`. MakerWorld rejects any `.3mf` whose printer model is blank or non-Bambu.

**Solution:**
- Always pass fully resolved (flattened inheritance) JSON presets for the target Bambu printer (`--load-settings "<machine.json>;<process.json>" --load-filaments "<filament.json>"`) and ensure `<metadata key="printer_model_id" value="N1"/>` is present in `Metadata/slice_info.config`.

### Error 3: `"Plate 1: Cool Plate does not support filament 1"` During CLI Slicing
**Cause:**
- When slicing PETG via the Bambu Studio CLI, the default fallback bed type (`Cool Plate`) conflicts with PETG's bed temperature requirements on the A1 mini.

**Solution:**
- Explicitly set `"curr_bed_type": "Textured PEI Plate"` in both the machine and process JSON settings before invoking `bambu-studio`.

---

## 3. Headless Bambu Studio CLI Workflow on Linux

### Installation on Debian/Ubuntu (`x86_64`)
1. Download the official Ubuntu 24.04 AppImage from [bambulab/BambuStudio Releases](https://github.com/bambulab/BambuStudio/releases):
   ```bash
   curl -L -o /home/droid/BambuStudio.AppImage \
     "https://github.com/bambulab/BambuStudio/releases/download/v02.09.01.70/BambuStudio_ubu24-v02.09.01.70-20261103183404.AppImage"
   chmod +x /home/droid/BambuStudio.AppImage
   sudo ln -sf /home/droid/BambuStudio.AppImage /usr/local/bin/bambu-studio
   ```
2. Install required system libraries:
   ```bash
   sudo apt-get update && sudo apt-get install -y \
     fuse3 libfuse2t64 libgtk-3-0t64 libwebkit2gtk-4.1-0 \
     libglu1-mesa libgl1 libegl1 libgbm1 libosmesa6 xvfb xauth
   ```

### Resolving Bambu Studio Preset Inheritance for CLI Use
Bambu Studio's internal profile JSONs (located inside the AppImage at `resources/profiles/BBL/{machine,process,filament}/`) use an `"inherits"` chain. The CLI `--load-settings` flag requires **flattened** JSON files where parent keys are merged into the child preset:
- **Machine:** `Bambu Lab A1 mini 0.4 nozzle.json` (inherits from `fdm_bbl_3dp_001_common.json`)
- **Process:** `0.20mm Strength @BBL A1M.json`
- **Filament:** `Bambu PETG Basic @BBL A1M 0.4 nozzle.json`

### Exporting a MakerWorld-Ready `.3mf` Headlessly
```bash
xvfb-run -a bambu-studio \
  --load-settings "a1m_machine.json;a1m_process.json" \
  --load-filaments "a1m_filament.json" \
  --arrange 1 \
  --ensure-on-bed \
  --export-3mf craftsman_v20_vacuum_mount.3mf \
  craftsman_v20_vacuum_mount.stl
```

---

## 4. Parametric 3D Mesh Generation Guidelines (`generate_vacuum_mount.py`)

When generating custom mechanical brackets in pure Python without external CAD dependencies:
1. **2-Manifold Watertight Guarantee:**
   - Use a conformal 3D hexahedral cell complex `(i, j, k)` where internal faces between adjacent active cells are culled and every boundary quad is split consistently.
   - For circular features (such as countersunk screw holes), match the outer perimeter nodes of the hole sub-block 1-to-1 with the surrounding hexahedral grid nodes so zero T-junctions can occur.
2. **Automated Verification (`verify_manifold`):**
   - Always check every generated mesh before writing `.stl` / `.3mf`:
     - `unmatched_directed_edges == 0` (every half-edge `(u, v)` has an exact opposite `(v, u)`)
     - `non_manifold_edges == 0` (every undirected edge is shared by exactly 2 triangles)
     - `volume_cm3 > 0` (all surface normals point outward)
3. **Craftsman V20 Handheld Vacuum (`CMCVH001B`) Wall Mount Key Dimensions:**
   - **Inner Gap Width:** `84.0 mm` (clears the upper neck below the V20 battery shoe while supporting the flared battery housing)
   - **Arm Thickness:** `11.0 mm` each
   - **Arm Reach:** `92.0 mm` from backplate face (`100.0 mm` total depth including `8.0 mm` backplate)
   - **Inner Cradle Step Ledge:** `4.5 mm` wide × `7.0 mm` deep inset along the inside top of each arm
   - **Front Retention Hook:** `13.0 mm` long upturned lip (`7.0 mm` above outer wall, `14.0 mm` above inner ledge)
   - **Mounting Holes:** Two `#8 / #10` countersunk screw holes (`4.8 mm` through-hole, `9.6 mm` countersink diameter, `32.0 mm` vertical center-to-center spacing) in a `38.0 mm` wide recessed backplate channel.

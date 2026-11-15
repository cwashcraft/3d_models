#!/usr/bin/env python3
"""
Generic Wireless Deploy & Print Script for Bambu Lab A1 Mini (`scripts/deploy_to_printer.py`).

What this script does in one command for ANY model folder in this repository:
  1. Optionally runs a model generator script (e.g., `generate_*.py`) if present in the target folder.
  2. Runs headless `bambu-studio` (`v02.08.02.61`) with the official Bambu Lab A1 Mini (0.4mm nozzle)
     machine, process (`0.20mm Strength @BBL A1M`, 4 walls, 25% gyroid infill), and filament presets
     to slice the `.stl` model and produce both:
       - `<model_name>.3mf` (MakerWorld / Bambu Studio project file)
       - `<model_name>.gcode.3mf` (Fully sliced G-code package ready for the A1 Mini)
  3. Uploads `<model_name>.gcode.3mf` directly to your Bambu Lab A1 Mini over Wi-Fi
     via implicit FTPS (port 990, user `bblp`, password = your 8-digit Access Code).

Usage:
  python3 scripts/deploy_to_printer.py --model-dir craftsman_v20_vacuum_mount --ip 192.168.1.191 --access-code 13929394
"""

import argparse
import glob
import hashlib
import json
import os
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import zipfile


def resolve_bambu_presets(appimage_path, filament_choice="PLA", enable_supports=False):
    """Extracts and flattens the official Bambu Lab A1 mini presets from the AppImage."""
    tmp_dir = tempfile.mkdtemp(prefix="bambu_presets_")
    subprocess.run(
        [appimage_path, "--appimage-extract", "resources/profiles/BBL/*"],
        cwd=tmp_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    base_dir = os.path.join(tmp_dir, "squashfs-root", "resources", "profiles", "BBL")

    def resolve_preset(subdir, name):
        path = os.path.join(base_dir, subdir, name if name.endswith(".json") else name + ".json")
        if not os.path.exists(path):
            for root, _, files in os.walk(os.path.join(base_dir, subdir)):
                if (name + ".json") in files:
                    path = os.path.join(root, name + ".json")
                    break
        with open(path, "r") as f:
            data = json.load(f)
        res = {}
        if "inherits" in data and data["inherits"]:
            res.update(resolve_preset(subdir, data["inherits"]))
        if "include" in data and isinstance(data["include"], list):
            for inc in data["include"]:
                res.update(resolve_preset(subdir, inc))
        res.update(data)
        res.pop("include", None)
        return res

    machine = resolve_preset("machine", "Bambu Lab A1 mini 0.4 nozzle")
    machine["printer_settings_id"] = "Bambu Lab A1 mini 0.4 nozzle"
    machine["curr_bed_type"] = "Textured PEI Plate"

    if filament_choice.upper() == "PLA":
        process = resolve_preset("process", "0.16mm Optimal @BBL A1M")
        process["print_settings_id"] = "0.16mm Optimal @BBL A1M"
        process["curr_bed_type"] = "Textured PEI Plate"
        process["wall_loops"] = "2"
        process["sparse_infill_density"] = "20%"
        process["sparse_infill_pattern"] = "gyroid"
        process["wall_generator"] = "arachne"
        # MakerWorld upright keycap profile best practices for A1 mini:
        # 1. Zero-gap 7mm outer + inner brim + 0.20mm/0.50mm slow first layer (20 mm/s) on 65C PEI plate
        process["elefant_foot_compensation"] = "0"
        process["brim_type"] = "outer_and_inner"
        process["brim_width"] = "7"
        process["brim_object_gap"] = "0"
        process["initial_layer_print_height"] = "0.20"
        process["initial_layer_line_width"] = "0.50"
        process["initial_layer_speed"] = "20"
        process["initial_layer_infill_speed"] = "35"
        # 2. Throttled wall speeds (50 mm/s outer / 70 mm/s inner) so high-speed jerk never knocks loose a keycap
        process["outer_wall_speed"] = "50"
        process["inner_wall_speed"] = "70"
        process["sparse_infill_speed"] = "80"
        process["internal_solid_infill_speed"] = "60"
        process["gap_infill_speed"] = "40"
        process["top_surface_speed"] = "40"
        process["reduce_crossing_wall"] = "1"
        process["max_travel_detour_distance"] = "100%"
    else:
        process = resolve_preset("process", "0.20mm Strength @BBL A1M")
        process["print_settings_id"] = "0.20mm Strength @BBL A1M"
        process["curr_bed_type"] = "Textured PEI Plate"
        process["wall_loops"] = "4"
        process["sparse_infill_density"] = "25%"
        process["sparse_infill_pattern"] = "gyroid"

    if enable_supports:
        process["enable_support"] = "1"
        process["support_type"] = "normal(auto)"
        process["support_style"] = "snug"
        process["support_on_build_plate_only"] = "1"
        process["support_threshold_angle"] = "40"
        process["support_top_z_distance"] = "0.24"
        process["support_bottom_z_distance"] = "0.2"
        process["support_object_xy_distance"] = "0.4"
        process["support_interface_top_layers"] = "2"
        process["support_interface_spacing"] = "0.4"
        process["brim_type"] = "outer_only"
        process["brim_width"] = "5"
        process["brim_object_gap"] = "0.12"
    else:
        process["enable_support"] = "0"

    if filament_choice.upper() == "PETG":
        fil_name = "Bambu PETG Basic @BBL A1M 0.4 nozzle"
        tray_idx = "GFG00"
        fil_type = "PETG"
    elif filament_choice.upper() == "TPU":
        fil_name = "Bambu TPU 95A @BBL A1M"
        tray_idx = "GFU01"
        fil_type = "TPU"
    else:
        fil_name = "Bambu PLA Matte @BBL A1M"
        tray_idx = "GFA01"
        fil_type = "PLA"

    filament = resolve_preset("filament", fil_name)
    filament["filament_settings_id"] = [fil_name]
    filament["filament_colour"] = ["#1E1E20" if fil_type == "TPU" else "#8E9089"]
    if fil_type == "PLA":
        filament["textured_plate_temp"] = ["65"]
        filament["textured_plate_temp_initial_layer"] = ["65"]
        filament["Close_fan_the_first_x_layers"] = ["2"]
        filament["slow_down_layer_time"] = ["12"]
        filament["slow_down_min_speed"] = ["20"]

    if fil_type == "TPU":
        # Anti-stringing TPU optimizations for lattice/mesh geometry on A1 mini:
        # 1. Route travel moves inside solid walls instead of crossing open cutouts/bore
        process["reduce_crossing_wall"] = "1"
        process["max_travel_detour_distance"] = "100%"
        # 2. Use Arachne variable-width walls to eliminate tiny gap-fill squirts & extra retractions
        process["wall_generator"] = "arachne"
        process["seam_position"] = "nearest"
        process["role_base_wipe_speed"] = "0"
        process["wipe_speed"] = "100%"
        # 3. Disable Z-hop (lifting vertically off molten TPU pulls elastic strings across cutouts)
        machine["z_hop"] = ["0"]
        machine["z_hop_types"] = ["Normal Lift"]
        filament["filament_z_hop"] = ["0"]
        filament["filament_z_hop_types"] = ["Normal Lift"]
        # 4. Stronger, faster direct-drive retraction + 70% fast pre-wipe retraction
        machine["retraction_length"] = ["1.2"]
        machine["retraction_speed"] = ["35"]
        machine["deretraction_speed"] = ["25"]
        machine["retract_before_wipe"] = ["70%"]
        machine["wipe"] = ["1"]
        machine["wipe_distance"] = ["2"]
        machine["retraction_minimum_travel"] = ["0.8"]
        filament["filament_retraction_length"] = ["1.2"]
        filament["filament_retraction_speed"] = ["35"]
        filament["filament_deretraction_speed"] = ["25"]
        filament["filament_retract_before_wipe"] = ["70%"]
        filament["filament_wipe"] = ["1"]
        filament["filament_wipe_distance"] = ["2"]
        filament["filament_retraction_minimum_travel"] = ["0.8"]
        # 5. Lower nozzle temperature (215C print / 220C first layer) & controlled volumetric flow
        filament["nozzle_temperature"] = ["215"]
        filament["nozzle_temperature_initial_layer"] = ["220"]
        filament["filament_max_volumetric_speed"] = ["3.2"]
    elif fil_type == "PLA":
        # Keep official Bambu PLA Basic temperatures (220C nozzle / 220C initial layer) to prevent heat-creep or clogging;
        # only enable reduce_crossing_wall so travels stay inside the keycap walls.
        process["reduce_crossing_wall"] = "1"
        process["max_travel_detour_distance"] = "100%"

    m_path = os.path.join(tmp_dir, "machine.json")
    p_path = os.path.join(tmp_dir, "process.json")
    f_path = os.path.join(tmp_dir, "filament.json")
    with open(m_path, "w") as fp:
        json.dump(machine, fp, indent=2)
    with open(p_path, "w") as fp:
        json.dump(process, fp, indent=2)
    with open(f_path, "w") as fp:
        json.dump(filament, fp, indent=2)

    return tmp_dir, m_path, p_path, f_path, fil_name, tray_idx, fil_type


def inject_pause_at_z(gcode_str, pause_z):
    """
    Injects a Bambu Lab filament-change pause (M400 U1) at the first layer change
    whose Z_HEIGHT is >= pause_z (within 0.05 mm tolerance).
    """
    lines = gcode_str.splitlines(keepends=True)
    out = []
    injected = False
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        out.append(line)
        if not injected and line.startswith("; CHANGE_LAYER"):
            # Look ahead a few lines for ; Z_HEIGHT: <val>
            for j in range(i + 1, min(i + 6, n)):
                if lines[j].startswith("; Z_HEIGHT:"):
                    try:
                        z_val = float(lines[j].split(":")[1].strip())
                        if z_val >= pause_z - 0.04:
                            # Copy up to and including the Z_HEIGHT and LAYER_HEIGHT lines
                            while i < j:
                                i += 1
                                out.append(lines[i])
                            if i + 1 < n and lines[i + 1].startswith("; LAYER_HEIGHT:"):
                                i += 1
                                out.append(lines[i])
                            out.append(f"; === AUTO FILAMENT CHANGE PAUSE AT Z = {z_val:.2f} mm (2-Tone Swap) ===\n")
                            out.append("M400 U1\n")
                            injected = True
                    except ValueError:
                        pass
                    break
        i += 1
    return "".join(out), injected


def build_and_slice(model_dir, stl_file, appimage_path, filament_choice="PLA", enable_supports=False, pause_z=None):
    # Check if a generator script (generate_*.py) exists in model_dir
    gen_scripts = sorted(glob.glob(os.path.join(model_dir, "generate_*.py")))
    existing_stls = sorted(glob.glob(os.path.join(model_dir, "*.stl")))
    if gen_scripts and (not existing_stls or os.path.getmtime(gen_scripts[0]) > os.path.getmtime(existing_stls[0])):
        print(f"[1/3] Running generator script: {os.path.basename(gen_scripts[0])}...")
        subprocess.run([sys.executable, gen_scripts[0]], check=True)

    if not stl_file:
        stls = sorted(glob.glob(os.path.join(model_dir, "*.stl")))
        if not stls:
            raise FileNotFoundError(f"No .stl file found in {model_dir}")
        stl_path = stls[0]
    else:
        stl_path = os.path.abspath(stl_file)

    base_name = os.path.splitext(os.path.basename(stl_path))[0]
    project_3mf = os.path.join(model_dir, f"{base_name}.3mf")
    sliced_3mf = os.path.join(model_dir, f"{base_name}.gcode.3mf")
    png_candidates = sorted(glob.glob(os.path.join(model_dir, "*preview*.png")))

    sup_str = " + Breakaway Supports & 5mm Brim" if enable_supports else ""
    print(f"[2/3] Slicing '{os.path.basename(stl_path)}' for Bambu Lab A1 mini ({filament_choice.upper()}, 4 walls, 25% Gyroid{sup_str})...")
    tmp_dir, m_path, p_path, f_path, fil_name, tray_idx, fil_type = resolve_bambu_presets(
        appimage_path, filament_choice, enable_supports=enable_supports
    )

    run_env = os.environ.copy()
    run_env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    subprocess.run(
        [
            "xvfb-run",
            "-a",
            appimage_path,
            "--load-settings",
            f"{m_path};{p_path}",
            "--load-filaments",
            f_path,
            "--arrange",
            "1",
            "--ensure-on-bed",
            "--slice",
            "0",
            "--export-3mf",
            sliced_3mf,
            stl_path,
        ],
        env=run_env,
        check=True,
    )

    with zipfile.ZipFile(sliced_3mf, "r") as zin:
        items = {name: zin.read(name) for name in zin.namelist()}

    if png_candidates:
        with open(png_candidates[0], "rb") as fp:
            png_bytes = fp.read()
        items["Metadata/plate_1.png"] = png_bytes
        items["Metadata/plate_1_small.png"] = png_bytes
        items["Metadata/top_1.png"] = png_bytes
        items["Metadata/pick_1.png"] = png_bytes

        ct = items["[Content_Types].xml"].decode("utf-8")
        if 'Extension="png"' not in ct:
            ct = ct.replace("</Types>", '  <Default Extension="png" ContentType="image/png"/>\n</Types>')
        items["[Content_Types].xml"] = ct.encode("utf-8")

    cfg = json.loads(items["Metadata/project_settings.config"].decode("utf-8"))
    cfg["inherits_group"] = [
        "0.20mm Strength @BBL A1M",
        fil_name,
        "Bambu Lab A1 mini 0.4 nozzle",
    ]
    items["Metadata/project_settings.config"] = json.dumps(cfg, indent=4).encode("utf-8")

    s_info = items["Metadata/slice_info.config"].decode("utf-8")
    s_info = s_info.replace('key="printer_model_id" value=""', 'key="printer_model_id" value="N1"')
    items["Metadata/slice_info.config"] = s_info.encode("utf-8")

    if pause_z is not None and "Metadata/plate_1.gcode" in items:
        gcode_str = items["Metadata/plate_1.gcode"].decode("utf-8", errors="replace")
        new_gcode_str, injected = inject_pause_at_z(gcode_str, pause_z)
        if injected:
            new_gcode_bytes = new_gcode_str.encode("utf-8")
            items["Metadata/plate_1.gcode"] = new_gcode_bytes
            items["Metadata/plate_1.gcode.md5"] = hashlib.md5(new_gcode_bytes).hexdigest().encode("utf-8")
            print(f"  -> Injected automatic filament-swap pause (M400 U1) at Z = {pause_z:.2f} mm!")
        else:
            print(f"  -> [Warning] Could not find layer change at Z >= {pause_z:.2f} mm for pause injection.")

    with zipfile.ZipFile(sliced_3mf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
        for name, data in items.items():
            if name == "3D/Objects/object_1.model":
                continue
            zout.writestr(name, data)

    with zipfile.ZipFile(project_3mf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zproj:
        for name, data in items.items():
            if name.endswith(".gcode") or name.endswith(".gcode.md5"):
                continue
            zproj.writestr(name, data)

    subprocess.run(["rm", "-rf", tmp_dir], check=False)
    print(f"  -> Generated project 3MF: {project_3mf} ({os.path.getsize(project_3mf) / 1024:.1f} KB)")
    print(f"  -> Generated sliced 3MF:  {sliced_3mf} ({os.path.getsize(sliced_3mf) / 1024:.1f} KB)")
    return sliced_3mf


def upload_via_ftps(printer_ip, access_code, local_filepath):
    """Uploads the sliced .gcode.3mf file to the A1 Mini over implicit FTPS (port 990)."""
    remote_filename = os.path.basename(local_filepath)
    print(f"[3/3] Uploading {remote_filename} to Bambu Lab A1 Mini at {printer_ip}:990 ...")

    subprocess.run(
        [
            "curl",
            "-k",
            "--ftp-ssl",
            "--user",
            f"bblp:{access_code}",
            "-T",
            local_filepath,
            f"ftps://{printer_ip}:990/{remote_filename}",
        ],
        check=True,
    )
    print(f"  -> Upload complete! '{remote_filename}' is now on your A1 Mini!")
    print("  -> On your A1 Mini touchscreen, tap 'Print Files' to start printing immediately.")


def start_print_via_mqtt(printer_ip, access_code, serial, local_filepath, use_ams=False):
    """Triggers a print job on the Bambu Lab A1 Mini over local MQTT TLS (port 8883)."""
    remote_filename = os.path.basename(local_filepath)
    subtask_name = os.path.splitext(os.path.splitext(remote_filename)[0])[0]
    md5_hex = hashlib.md5(open(local_filepath, "rb").read()).hexdigest()

    def enc_len(length):
        out = bytearray()
        while True:
            byte = length % 128
            length //= 128
            if length > 0:
                byte |= 0x80
            out.append(byte)
            if length == 0:
                break
        return bytes(out)

    def enc_str(s):
        b = s.encode("utf-8")
        return struct.pack(">H", len(b)) + b

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    raw_sock = socket.create_connection((printer_ip, 8883), timeout=10)
    sock = ctx.wrap_socket(raw_sock, server_hostname=printer_ip)

    var_hdr = enc_str("MQTT") + bytes([4, 0xC2, 0, 60])
    payload = enc_str("agy_print_starter") + enc_str("bblp") + enc_str(access_code)
    sock.sendall(bytes([0x10]) + enc_len(len(var_hdr) + len(payload)) + var_hdr + payload)
    sock.recv(4)

    sub_payload = struct.pack(">H", 1) + enc_str(f"device/{serial}/report") + bytes([0])
    sock.sendall(bytes([0x82]) + enc_len(len(sub_payload)) + sub_payload)
    sock.recv(5)

    req_topic = f"device/{serial}/request"
    cmd_payload = {
        "print": {
            "sequence_id": str(int(time.time()) % 100000),
            "command": "project_file",
            "param": "Metadata/plate_1.gcode",
            "project_id": "0",
            "profile_id": "0",
            "task_id": "0",
            "subtask_id": "0",
            "subtask_name": subtask_name,
            "file": "",
            "url": f"file:///sdcard/{remote_filename}",
            "md5": md5_hex,
            "timelapse": False,
            "bed_type": "auto",
            "bed_levelling": True,
            "flow_cali": False,
            "vibration_cali": False,
            "layer_inspect": False,
            "ams_mapping": [0] if use_ams else [254],
            "use_ams": bool(use_ams),
        }
    }
    req_json = json.dumps(cmd_payload).encode("utf-8")
    pub_pkt = enc_str(req_topic) + req_json
    sock.sendall(bytes([0x30]) + enc_len(len(pub_pkt)) + pub_pkt)
    time.sleep(1.5)
    sock.close()
    print(f"  -> Sent MQTT 'project_file' print start command for '{remote_filename}' (use_ams={use_ams})!")


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_model_dir = os.path.join(repo_root, "craftsman_v20_vacuum_mount")

    parser = argparse.ArgumentParser(description="Build, slice, and deploy any 3D model to Bambu Lab A1 Mini")
    parser.add_argument("--model-dir", default=default_model_dir, help="Path to the model folder (default: craftsman_v20_vacuum_mount)")
    parser.add_argument("--stl", default=None, help="Specific .stl file to slice (auto-detected from --model-dir if omitted)")
    parser.add_argument("--ip", default=os.environ.get("BAMBU_IP", "192.168.1.191"), help="A1 Mini LAN IP address")
    parser.add_argument("--access-code", default=os.environ.get("BAMBU_ACCESS_CODE", "76646398"), help="A1 Mini 8-digit access code")
    parser.add_argument("--serial", default=os.environ.get("BAMBU_SERIAL", "0309CA491801315"), help="A1 Mini serial number")
    parser.add_argument("--filament", default=os.environ.get("BAMBU_FILAMENT", "PLA"), choices=["PLA", "PETG", "TPU", "pla", "petg", "tpu"], help="Filament preset (PLA, PETG, or TPU)")
    parser.add_argument("--supports", action="store_true", help="Enable breakaway supports and 5mm outer brim")
    parser.add_argument("--pause-z", type=float, default=None, help="Inject automatic M400 U1 filament-swap pause at the specified Z height (mm)")
    parser.add_argument("--slice-only", action="store_true", help="Build and slice locally without uploading to printer")
    parser.add_argument("--print-now", action="store_true", help="Start printing via MQTT after uploading")
    parser.add_argument("--print-only", action="store_true", help="Start printing already-uploaded .gcode.3mf via MQTT without re-uploading")
    args = parser.parse_args()

    model_dir = os.path.abspath(args.model_dir)
    appimage_path = "/home/droid/BambuStudio.AppImage"
    use_supports = args.supports or ("jumping_spider" in os.path.basename(model_dir))
    pause_z = args.pause_z
    if pause_z is None and "keycap" in os.path.basename(model_dir):
        pause_z = 10.12
    use_ams = (args.filament.upper() != "TPU") and (pause_z is None)

    if args.print_only:
        gcodes = sorted(glob.glob(os.path.join(model_dir, "*.gcode.3mf")))
        if not gcodes:
            raise FileNotFoundError(f"No .gcode.3mf found in {model_dir}")
        start_print_via_mqtt(args.ip, args.access_code, args.serial, gcodes[0], use_ams=use_ams)
        return

    sliced_3mf = build_and_slice(
        model_dir, args.stl, appimage_path, args.filament, enable_supports=use_supports, pause_z=pause_z
    )

    if args.slice_only or not args.ip or not args.access_code:
        if not args.slice_only:
            print("\n[Note] Printer IP / Access Code not provided yet. Skipping wireless FTPS upload.")
            print("To upload directly to your A1 Mini over Wi-Fi, run:")
            print("  python3 scripts/deploy_to_printer.py --model-dir <FOLDER> --ip <PRINTER_IP> --access-code <8_DIGIT_CODE>")
        return

    upload_via_ftps(args.ip, args.access_code, sliced_3mf)
    if args.print_now:
        start_print_via_mqtt(args.ip, args.access_code, args.serial, sliced_3mf, use_ams=use_ams)


if __name__ == "__main__":
    main()

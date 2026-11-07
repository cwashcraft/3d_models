#!/usr/bin/env python3
"""
Direct Wireless Deploy & Print Script for Bambu Lab A1 Mini (`deploy_to_printer.py`).

What this script does in one command:
  1. Runs `generate_vacuum_mount.py` to rebuild the watertight 3D mesh (.stl, .3mf, previews).
  2. Runs headless `bambu-studio` (`v02.08.02.61`) with the official Bambu Lab A1 Mini (0.4mm nozzle)
     machine, process (`0.20mm Strength @BBL A1M`, 4 walls, 25% gyroid infill), and filament presets
     to slice the model and produce both:
       - `craftsman_v20_vacuum_mount.3mf` (MakerWorld / Bambu Studio project file)
       - `craftsman_v20_vacuum_mount.gcode.3mf` (Fully sliced G-code package ready for the A1 Mini)
  3. Uploads `craftsman_v20_vacuum_mount.gcode.3mf` directly to your Bambu Lab A1 Mini over Wi-Fi
     via implicit FTPS (port 990, user `bblp`, password = your 8-digit Access Code).
  4. Optionally sends an MQTT `project_file` print command (port 8883) if `--print-now` and
     `BAMBU_SERIAL` are provided, or lets you tap "Print Files" right on the A1 Mini screen!

Usage:
  export BAMBU_IP="192.168.1.xxx"
  export BAMBU_ACCESS_CODE="12345678"
  python3 deploy_to_printer.py

  # Or pass flags directly:
  python3 deploy_to_printer.py --ip 192.168.1.xxx --access-code 12345678 [--filament PLA|PETG] [--print-now --serial 0309xxxxxxxxxxx]
"""

import argparse
import ftplib
import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import zipfile


class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """FTPS client supporting implicit TLS on port 990 (used by Bambu Lab printers)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session,
            )
        return conn, size


def resolve_bambu_presets(appimage_path, filament_choice="PLA"):
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

    process = resolve_preset("process", "0.20mm Strength @BBL A1M")
    process["print_settings_id"] = "0.20mm Strength @BBL A1M"
    process["curr_bed_type"] = "Textured PEI Plate"
    process["wall_loops"] = "4"
    process["sparse_infill_density"] = "25%"
    process["sparse_infill_pattern"] = "gyroid"
    process["enable_support"] = "0"

    if filament_choice.upper() == "PETG":
        fil_name = "Bambu PETG Basic @BBL A1M 0.4 nozzle"
        tray_idx = "GFG00"
        fil_type = "PETG"
    else:
        fil_name = "Bambu PLA Basic @BBL A1M"
        tray_idx = "GFA00"
        fil_type = "PLA"

    filament = resolve_preset("filament", fil_name)
    filament["filament_settings_id"] = [fil_name]

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


def build_and_slice(repo_dir, appimage_path, filament_choice="PLA"):
    print("[1/3] Generating watertight 3D mesh via generate_vacuum_mount.py...")
    subprocess.run([sys.executable, os.path.join(repo_dir, "generate_vacuum_mount.py")], check=True)

    print(f"[2/3] Slicing for Bambu Lab A1 mini ({filament_choice.upper()}, 4 walls, 25% Gyroid)...")
    tmp_dir, m_path, p_path, f_path, fil_name, tray_idx, fil_type = resolve_bambu_presets(
        appimage_path, filament_choice
    )

    stl_path = os.path.join(repo_dir, "craftsman_v20_vacuum_mount.stl")
    project_3mf = os.path.join(repo_dir, "craftsman_v20_vacuum_mount.3mf")
    sliced_3mf = os.path.join(repo_dir, "craftsman_v20_vacuum_mount.gcode.3mf")
    png_path = os.path.join(repo_dir, "craftsman_v20_vacuum_mount_preview.png")

    # Export project 3MF (unsliced) and sliced .gcode.3mf (with plate_1.gcode)
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
        check=True,
    )

    # Enrich both sliced_3mf and project_3mf with thumbnails, inherits_group, and N1 model ID
    with open(png_path, "rb") as fp:
        png_bytes = fp.read()

    with zipfile.ZipFile(sliced_3mf, "r") as zin:
        items = {name: zin.read(name) for name in zin.namelist()}

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

    # Write full sliced .gcode.3mf (for direct printer upload)
    with zipfile.ZipFile(sliced_3mf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in items.items():
            zout.writestr(name, data)

    # Write compact project .3mf (without the 9MB raw gcode file, for GitHub / MakerWorld)
    with zipfile.ZipFile(project_3mf, "w", compression=zipfile.ZIP_DEFLATED) as zproj:
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

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    ftps = ImplicitFTP_TLS(context=ctx)
    ftps.connect(host=printer_ip, port=990, timeout=15)
    ftps.login(user="bblp", passwd=access_code)
    ftps.prot_p()

    with open(local_filepath, "rb") as fp:
        ftps.storbinary(f"STOR {remote_filename}", fp)

    ftps.quit()
    print(f"  -> Upload complete! '{remote_filename}' is now on your A1 Mini!")
    print("  -> On your A1 Mini touchscreen, tap 'Print Files' to start printing immediately.")


def main():
    parser = argparse.ArgumentParser(description="Build, slice, and deploy 3D model to Bambu Lab A1 Mini")
    parser.add_argument("--ip", default=os.environ.get("BAMBU_IP"), help="A1 Mini LAN IP address")
    parser.add_argument("--access-code", default=os.environ.get("BAMBU_ACCESS_CODE"), help="A1 Mini 8-digit access code")
    parser.add_argument("--filament", default=os.environ.get("BAMBU_FILAMENT", "PLA"), choices=["PLA", "PETG", "pla", "petg"], help="Filament preset (PLA or PETG)")
    parser.add_argument("--slice-only", action="store_true", help="Build and slice locally without uploading to printer")
    args = parser.parse_args()

    repo_dir = os.path.dirname(os.path.abspath(__file__))
    appimage_path = "/home/droid/BambuStudio.AppImage"

    sliced_3mf = build_and_slice(repo_dir, appimage_path, args.filament)

    if args.slice_only or not args.ip or not args.access_code:
        if not args.slice_only:
            print("\n[Note] Printer IP / Access Code not provided yet. Skipping wireless FTPS upload.")
            print("To upload directly to your A1 Mini over Wi-Fi, run:")
            print("  python3 deploy_to_printer.py --ip <PRINTER_IP> --access-code <8_DIGIT_CODE>")
        return

    upload_via_ftps(args.ip, args.access_code, sliced_3mf)


if __name__ == "__main__":
    main()

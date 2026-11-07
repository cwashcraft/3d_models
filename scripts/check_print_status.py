#!/usr/bin/env python3
"""
Queries live print telemetry (MQTT port 8883) and captures a live JPEG frame
from the Bambu Lab A1 Mini's built-in camera (TLS port 6000), then pushes
a status notification with the attached camera snapshot to ntfy.sh.

Usage:
  export BAMBU_IP="192.168.1.xxx"
  export BAMBU_ACCESS_CODE="12345678"
  export BAMBU_SERIAL="0309xxxxxxxxxxx"
  export NTFY_TOPIC="cwashcraft-a1mini"
  python3 check_print_status.py
"""
import argparse
import json
import os
import re
import socket
import ssl
import struct
import subprocess
import time


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


def get_printer_status(host, access_code, serial, port=8883, user="bblp"):
    """Connects to the A1 Mini's local MQTT broker and requests a pushall telemetry report."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    raw_sock = socket.create_connection((host, port), timeout=10)
    sock = ctx.wrap_socket(raw_sock, server_hostname=host)

    var_hdr = enc_str("MQTT") + bytes([4, 0xC2, 0, 60])
    payload = enc_str("agy_status_checker") + enc_str(user) + enc_str(access_code)
    sock.sendall(bytes([0x10]) + enc_len(len(var_hdr) + len(payload)) + var_hdr + payload)
    sock.recv(4)

    sub_payload = struct.pack(">H", 1) + enc_str(f"device/{serial}/report") + bytes([0])
    sock.sendall(bytes([0x82]) + enc_len(len(sub_payload)) + sub_payload)
    sock.recv(5)

    req_topic = f"device/{serial}/request"
    req_json = json.dumps(
        {"pushing": {"sequence_id": "1", "command": "pushall", "version": 1, "push_target": 1}}
    ).encode()
    pub_pkt = enc_str(req_topic) + req_json
    sock.sendall(bytes([0x30]) + enc_len(len(pub_pkt)) + pub_pkt)

    sock.settimeout(3.0)
    data = b""
    start = time.time()
    while time.time() - start < 3.5:
        try:
            c = sock.recv(65536)
            if not c:
                break
            data += c
        except socket.timeout:
            break
    sock.close()

    result = {}
    for m in re.finditer(rb"\{\"print\":", data):
        pos = m.start()
        txt = data[pos:].decode("utf-8", errors="ignore")
        depth = 0
        for i, ch in enumerate(txt):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(txt[: i + 1])
                        p = obj.get("print", {})
                        if "gcode_state" in p:
                            for k in [
                                "gcode_state",
                                "mc_percent",
                                "mc_remaining_time",
                                "layer_num",
                                "total_layer_num",
                                "nozzle_temper",
                                "nozzle_target_temper",
                                "bed_temper",
                                "bed_target_temper",
                                "subtask_name",
                                "print_error",
                                "stg_cur",
                            ]:
                                if k in p:
                                    result[k] = p[k]
                    except Exception:
                        pass
                    break
    return result


def capture_camera_snapshot(host, access_code, filepath="/tmp/camera_snapshot.jpg", port=6000, user="bblp"):
    """Captures a live JPEG frame from the A1 Mini's built-in camera on TLS port 6000."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    raw_sock = socket.create_connection((host, port), timeout=10)
    sock = ctx.wrap_socket(raw_sock, server_hostname=host)
    auth_pkt = (
        struct.pack("<I", 0x40)
        + struct.pack("<I", 0x3000)
        + b"\x00" * 8
        + user.encode("ascii").ljust(32, b"\x00")
        + access_code.encode("ascii").ljust(32, b"\x00")
    )
    sock.sendall(auth_pkt)
    sock.settimeout(8.0)

    buf = b""
    saved = False
    while len(buf) < 600000:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
        soi = buf.find(b"\xff\xd8\xff")
        if soi != -1:
            eoi = buf.find(b"\xff\xd9", soi)
            if eoi != -1:
                jpg = buf[soi : eoi + 2]
                with open(filepath, "wb") as f:
                    f.write(jpg)
                saved = True
                break
    sock.close()
    return filepath if saved else None


def main():
    parser = argparse.ArgumentParser(description="Check Bambu Lab A1 Mini print status and push camera snapshot to ntfy.sh")
    parser.add_argument("--ip", default=os.environ.get("BAMBU_IP", "192.168.1.191"), help="A1 Mini LAN IP address")
    parser.add_argument("--access-code", default=os.environ.get("BAMBU_ACCESS_CODE", "13929394"), help="A1 Mini 8-digit access code")
    parser.add_argument("--serial", default=os.environ.get("BAMBU_SERIAL", "0309CA491801315"), help="A1 Mini serial number")
    parser.add_argument("--ntfy-topic", default=os.environ.get("NTFY_TOPIC", "cwashcraft-a1mini"), help="ntfy.sh topic name")
    parser.add_argument("--snapshot-out", default="/home/droid/camera_snapshot.jpg", help="Output path for captured JPEG frame")
    args = parser.parse_args()

    st = get_printer_status(args.ip, args.access_code, args.serial)
    print(json.dumps(st, indent=2))
    snap = capture_camera_snapshot(args.ip, args.access_code, filepath=args.snapshot_out)

    if st and args.ntfy_topic:
        state = st.get("gcode_state", "UNKNOWN")
        pct = st.get("mc_percent", 0)
        layer = st.get("layer_num", 0)
        total_layers = st.get("total_layer_num", 500)
        rem_min = st.get("mc_remaining_time", 0)
        noz = st.get("nozzle_temper", 0.0)
        bed = st.get("bed_temper", 0.0)
        err = st.get("print_error", 0)

        hrs, mins = divmod(int(rem_min), 60)
        msg = (
            f"State: {state} | Progress: {pct}% (Layer {layer}/{total_layers}) | "
            f"Remaining: {hrs}h {mins:02d}m | Nozzle: {noz:.1f}C | Bed: {bed:.1f}C | Errors: {err}"
        )
        cmd = [
            "curl",
            "-s",
            "-H",
            f"Title: Bambu A1 Mini: {pct}% (Layer {layer}/{total_layers})",
            "-H",
            f"Message: {msg}",
            "-H",
            f"Priority: {'high' if err != 0 else 'default'}",
        ]
        if snap:
            cmd.extend(["-T", snap, "-H", "Filename: camera_snapshot.jpg"])
        else:
            cmd.extend(["-d", msg])
        cmd.append(f"https://ntfy.sh/{args.ntfy_topic}")
        subprocess.run(cmd, check=False)
        print(f"\nSent ntfy.sh update with camera snapshot to https://ntfy.sh/{args.ntfy_topic}")


if __name__ == "__main__":
    main()

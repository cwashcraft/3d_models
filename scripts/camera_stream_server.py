#!/usr/bin/env python3
"""
Live MJPEG Web Stream Server for Bambu Lab A1 Mini Camera (TLS Port 6000 -> HTTP Port 8080).
Open http://localhost:8080/ in any web browser for a real-time MJPEG video feed.
"""

import http.server
import os
import socket
import socketserver
import ssl
import struct

PRINTER_IP = os.environ.get("BAMBU_IP", "192.168.1.191")
ACCESS_CODE = os.environ.get("BAMBU_ACCESS_CODE", "13929394")
PORT = int(os.environ.get("STREAM_PORT", "8080"))


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class CameraStreamHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = b"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Bambu Lab A1 Mini - Live Camera Stream</title>
  <style>
    body { background: #141619; color: #f0f2f5; font-family: sans-serif; text-align: center; margin: 0; padding: 24px; }
    h2 { margin-top: 0; font-weight: 600; }
    img { max-width: 95vw; max-height: 85vh; border-radius: 10px; box-shadow: 0 8px 28px rgba(0,0,0,0.5); border: 2px solid #2d3139; }
  </style>
</head>
<body>
  <h2>Bambu Lab A1 Mini &#8212; Live Camera Feed (192.168.1.191)</h2>
  <img src="/stream.mjpg" alt="Live Camera Stream" />
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if self.path.startswith("/stream.mjpg"):
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            raw_sock = socket.create_connection((PRINTER_IP, 6000), timeout=10)
            sock = ctx.wrap_socket(raw_sock, server_hostname=PRINTER_IP)
            auth_pkt = (
                struct.pack("<I", 0x40)
                + struct.pack("<I", 0x3000)
                + b"\x00" * 8
                + b"bblp".ljust(32, b"\x00")
                + ACCESS_CODE.encode("ascii").ljust(32, b"\x00")
            )
            sock.sendall(auth_pkt)
            sock.settimeout(10.0)

            buf = b""
            try:
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                    while True:
                        soi = buf.find(b"\xff\xd8\xff")
                        if soi == -1:
                            break
                        eoi = buf.find(b"\xff\xd9", soi)
                        if eoi == -1:
                            break
                        jpg = buf[soi : eoi + 2]
                        buf = buf[eoi + 2 :]
                        header = (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            + f"Content-Length: {len(jpg)}\r\n\r\n".encode("ascii")
                        )
                        self.wfile.write(header + jpg + b"\r\n")
                        self.wfile.flush()
            except Exception:
                pass
            finally:
                sock.close()
            return

        self.send_error(404)


if __name__ == "__main__":
    server = ThreadedHTTPServer(("0.0.0.0", PORT), CameraStreamHandler)
    print(f"Live MJPEG stream running at http://0.0.0.0:{PORT}/ (and http://localhost:{PORT}/stream.mjpg)")
    server.serve_forever()

#!/usr/bin/env python3
"""Small web server for IPSC 靶監看.

Serves this folder on port 8765 to the whole home network, so an iPad or phone
on the same Wi-Fi can open http://<this Mac's IP>:8765/. It also answers
/lan-ip.json with this Mac's current LAN address, which the page shows in its
header so you know what to type on the iPad.

Usage: python3 serve.py [port]
"""
import json
import os
import socket
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
HERE = os.path.dirname(os.path.abspath(__file__))


def lan_ips():
    """This Mac's IPv4 addresses on the local network, the default route's first."""
    ips = []
    try:
        # A UDP "connect" sends nothing; it only picks the outgoing interface.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    for iface in ("en0", "en1", "en2", "en3"):
        try:
            ip = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True,
                                text=True, timeout=1).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            ip = ""
        if ip and ip not in ips:
            ips.append(ip)
    return [ip for ip in ips if not ip.startswith("127.")]


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/lan-ip.json":
            body = json.dumps({"ips": lan_ips(), "port": PORT}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), partial(Handler, directory=HERE))
    print(f"IPSC 靶監看: http://localhost:{PORT}/  區網: " +
          ", ".join(f"http://{ip}:{PORT}/" for ip in lan_ips()), flush=True)
    server.serve_forever()

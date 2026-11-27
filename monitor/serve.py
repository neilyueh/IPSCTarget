#!/usr/bin/env python3
"""Small web server for IPSC 靶監看.

Serves this folder on port 8765 to the whole home network, so an iPad or phone
on the same Wi-Fi can open http://<this Mac's IP>:8765/. It also answers
/lan-ip.json with this Mac's current LAN address, which the page shows in its
header so you know what to type on the iPad.

It also relays commands: the iPad cannot use Bluetooth, so its buttons POST to
/relay/cmd, the page open in Chrome on this Mac (the "controller") picks them up
from /relay/poll, sends them to the target over Bluetooth and POSTs the outcome
to /relay/result, which the iPad reads back from /relay/result?id=N.

And it keeps the iPad's targets the same as the Mac's: the Mac page POSTs its
targets (list, names, zoom, which target is showing, hits) to /relay/state on
every change, and the iPad long-polls /relay/state?v=N for a newer version.

Usage: python3 serve.py [port]
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
HERE = os.path.dirname(os.path.abspath(__file__))

# Command relay state (see module docstring).
relay_lock = threading.Condition()
relay = {"next_id": 1, "queue": [], "inflight": [], "results": {}, "controller_seen": 0.0, "waiting": 0,
         # The Mac page's targets (list, names, zoom, which target is showing, hits),
         # POSTed to /relay/state on every change; iPads long-poll it to stay in sync.
         "state": None, "state_v": 0,
         "gen": 0}   # bumped when the Mac page says it is closing (/relay/bye)
CONTROLLER_TIMEOUT = 4.0   # seconds without a poll before the Mac page counts as closed
POLL_WAIT = 20.0           # a poll is held open this long when there is nothing to do
ACK_TIMEOUT = 2.5          # the page polls again right after taking commands; if it
                           # doesn't, it was closed and the commands were lost
NO_CONTROLLER = "Mac 上的網頁沒開（請在 Mac 的 Chrome 開 localhost:%d）"


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


def controller_alive():
    return relay["waiting"] > 0 or time.time() - relay["controller_seen"] < CONTROLLER_TIMEOUT


def reap():
    """Call with relay_lock held. A poll whose page was already closed hands its
    commands to nobody: fail them and stop counting that page as open."""
    now = time.time()
    if relay["inflight"] and now - relay["inflight"][0][1] > ACK_TIMEOUT:
        for cmd, _ in relay["inflight"]:
            relay["results"][cmd["id"]] = {"done": True, "ok": False, "msg": NO_CONTROLLER % PORT}
        relay["inflight"] = []
        relay["controller_seen"] = 0.0
        relay["waiting"] = 0
    if relay["queue"] and not controller_alive():
        for cmd in relay["queue"]:
            relay["results"][cmd["id"]] = {"done": True, "ok": False, "msg": NO_CONTROLLER % PORT}
        relay["queue"] = []


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Make browsers check for a newer page on every load (a plain reload is
        # enough after an update); unchanged files still come back as 304.
        if not self.path.startswith("/relay/") and not self.path.startswith("/lan-ip.json"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def query(self):
        q = self.path.partition("?")[2]
        return dict(kv.partition("=")[::2] for kv in q.split("&") if kv)

    def do_GET(self):
        route = self.path.split("?")[0]
        if route == "/lan-ip.json":
            self.send_json({"ips": lan_ips(), "port": PORT})
            return
        if route == "/relay/status":
            with relay_lock:
                reap()
                self.send_json({"controller": controller_alive()})
            return
        if route == "/relay/state":
            # iPad: wait until the Mac's state is newer than version v (long poll).
            try:
                v = int(self.query().get("v", "0"))
            except ValueError:
                v = 0
            with relay_lock:
                relay_lock.wait_for(lambda: relay["state_v"] != v, timeout=POLL_WAIT)
                reap()
                self.send_json({"v": relay["state_v"], "state": relay["state"],
                                "controller": controller_alive()})
            return
        if route == "/relay/poll":
            # The Mac page asks for new commands; each command goes to one page only.
            # Long poll: held open until a command arrives, so it needs no timers on
            # the page (Chrome slows those down in background tabs).
            with relay_lock:
                relay["inflight"] = []      # polling again acknowledges the last batch
                relay["waiting"] += 1
                gen = relay["gen"]
                try:
                    relay_lock.wait_for(lambda: relay["queue"] or relay["gen"] != gen, timeout=POLL_WAIT)
                finally:
                    if relay["gen"] == gen:     # else the page already said it closed
                        relay["waiting"] = max(0, relay["waiting"] - 1)
                        relay["controller_seen"] = time.time()
                if relay["gen"] != gen:
                    self.send_json({"cmds": []})
                    return
                cmds, relay["queue"] = relay["queue"], []
                now = time.time()
                relay["inflight"] = [(c, now) for c in cmds]
            self.send_json({"cmds": cmds})
            return
        if route == "/relay/result":
            try:
                cid = int(self.query().get("id", "0"))
            except ValueError:
                cid = 0
            with relay_lock:
                reap()
                res = relay["results"].get(cid)
            self.send_json(res or {"done": False})
            return
        super().do_GET()

    def do_POST(self):
        route = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            limit = 4 << 20 if route == "/relay/state" else 65536   # state carries every hit
            data = json.loads(self.rfile.read(n) or b"{}") if n <= limit else {}
        except (ValueError, json.JSONDecodeError):
            data = {}
        if route == "/relay/cmd":
            with relay_lock:
                reap()
                if not controller_alive():
                    self.send_json({"error": "no_controller"}, 503)
                    return
                cid = relay["next_id"]
                relay["next_id"] += 1
                relay["queue"].append({"id": cid, "ip": str(data.get("ip", "")),
                                       "act": str(data.get("act", "")), "arg": data.get("arg")})
                # Keep only recent results.
                for old in [k for k in relay["results"] if k < cid - 200]:
                    del relay["results"][old]
                relay_lock.notify_all()
            self.send_json({"id": cid})
            return
        if route == "/relay/bye":
            # The Mac page is closing: count it as gone now, so iPads hear at once.
            with relay_lock:
                relay["gen"] += 1
                relay["waiting"] = 0
                relay["controller_seen"] = 0.0
                relay["state_v"] += 1
                reap()
                relay_lock.notify_all()
            self.send_json({"ok": True})
            return
        if route == "/relay/state":
            with relay_lock:
                relay["state"] = data if isinstance(data, dict) and data.get("targets") is not None else None
                relay["state_v"] += 1
                relay["controller_seen"] = max(relay["controller_seen"], time.time())
                relay_lock.notify_all()
            self.send_json({"ok": True})
            return
        if route == "/relay/result":
            try:
                cid = int(data.get("id", 0))
            except (TypeError, ValueError):
                cid = 0
            with relay_lock:
                kind = data.get("kind")
                relay["results"][cid] = {"done": True, "ok": bool(data.get("ok")),
                                         "msg": str(data.get("msg", "")),
                                         "kind": kind if isinstance(kind, int) else None}
            self.send_json({"ok": True})
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        # Goes to ~/Library/Logs/ipsctarget-web.log under launchd: shows whether
        # requests from the iPad reach this Mac at all.
        if not self.path.startswith(("/lan-ip.json", "/relay/")):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), partial(Handler, directory=HERE))
    print(f"IPSC 靶監看: http://localhost:{PORT}/  區網: " +
          ", ".join(f"http://{ip}:{PORT}/" for ip in lan_ips()), flush=True)
    server.serve_forever()

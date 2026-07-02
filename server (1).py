#!/usr/bin/env python3
"""
Local server for the TSE Day-0 Discovery Tool.

What it does
------------
1. Serves the HTML tool (and any other files in this folder) over http://localhost:8000
2. POST /save        — appends each completed session as ONE row to a single
                       combined file: tse_discovery_sessions.csv
3. Resumable sessions (in-progress, keyed by your name + customer name):
   - POST /session/save   {id, state}   upsert into tse_sessions_state.json
   - GET  /session/list                 list saved sessions (newest first)
   - GET  /session/get?id=...           fetch one saved session to resume

Run it
------
    cd <folder containing this file and the HTML>
    python3 server.py

Then open the URL it prints, e.g.:
    http://localhost:8000/TSE-Day0-Discovery-Tool_2026-06-25_v5.html

Stop with Ctrl+C.
"""

import csv
import json
import os
from urllib.parse import urlparse, parse_qs
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = 8000
HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "tse_discovery_sessions.csv")
STATE_PATH = os.path.join(HERE, "tse_sessions_state.json")


def _load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    # ── helpers ────────────────────────────────────────────────────────────
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── routing ──────────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        if path == "/session/list":
            store = _load_state()
            sessions = sorted(store.values(), key=lambda s: s.get("updatedAt", ""), reverse=True)
            slim = [{k: s.get(k) for k in ("id", "label", "company", "name", "date", "screen", "step", "updatedAt")} for s in sessions]
            self._send_json(200, {"success": True, "sessions": slim})
            return
        if path == "/session/get":
            qs = parse_qs(urlparse(self.path).query)
            sid = (qs.get("id") or [""])[0]
            store = _load_state()
            if sid in store:
                self._send_json(200, {"success": True, "state": store[sid]})
            else:
                self._send_json(404, {"success": False, "error": "Session not found"})
            return
        # otherwise serve files normally
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        try:
            if path == "/save":
                self._handle_csv_save(self._read_json())
            elif path == "/session/save":
                self._handle_session_save(self._read_json())
            else:
                self._send_json(404, {"success": False, "error": "Unknown endpoint"})
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {path} failed: {e}")
            self._send_json(500, {"success": False, "error": str(e)})

    # ── handlers ────────────────────────────────────────────────────────────
    def _handle_csv_save(self, data):
        row = data.get("row", [])
        columns = data.get("columns", [])
        if not isinstance(row, list) or not row:
            raise ValueError("Missing or empty 'row'")
        file_exists = os.path.exists(CSV_PATH) and os.path.getsize(CSV_PATH) > 0
        with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if not file_exists and columns:
                writer.writerow(columns)
            writer.writerow(["" if v is None else str(v) for v in row])
        count = self._csv_count()
        print(f"  ✓ Saved result — combined file now has {count} session(s)")
        self._send_json(200, {"success": True, "file": os.path.basename(CSV_PATH), "rows": count})

    def _handle_session_save(self, data):
        sid = data.get("id")
        state = data.get("state")
        if not sid or not isinstance(state, dict):
            raise ValueError("Missing 'id' or 'state'")
        store = _load_state()
        store[sid] = state
        _save_state(store)
        print(f"  ✓ Saved in-progress session '{sid}' ({len(store)} stored)")
        self._send_json(200, {"success": True, "id": sid, "count": len(store)})

    def _csv_count(self):
        try:
            with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
                return max(0, sum(1 for _ in f) - 1)
        except OSError:
            return 0


def main():
    os.chdir(HERE)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("TSE Day-0 Discovery Tool — local server")
    print(f"  Serving folder : {HERE}")
    print(f"  Results file   : {CSV_PATH}")
    print(f"  Sessions file  : {STATE_PATH}")
    print(f"  Open           : http://localhost:{PORT}/")
    print("  (pick the TSE-Day0-Discovery-Tool_*.html file from the listing)")
    print("  Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()

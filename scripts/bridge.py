from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class FileBridgeServer:
    def __init__(self, root_dir: str, allow_write: bool = False, host: str = "127.0.0.1", port: int = 5001):
        self.root = Path(root_dir).expanduser().resolve()
        self.allow_write = allow_write
        self.host = host
        self.port = port
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, raw_path: str) -> Path:
        candidate = (self.root / raw_path.lstrip("/\\")).resolve()
        if not str(candidate).startswith(str(self.root)):
            raise PermissionError("path escapes bridge root")
        return candidate

    def serve(self) -> None:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, body: dict) -> None:
                data = json.dumps(body, indent=2).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path != "/read":
                    return self._send(404, {"ok": False, "error": "not found"})
                qs = parse_qs(parsed.query)
                raw_path = (qs.get("path") or [""])[0]
                try:
                    target = server._resolve(raw_path)
                    self._send(200, {"ok": True, "path": str(target), "data": target.read_text(encoding="utf-8")})
                except Exception as exc:
                    self._send(400, {"ok": False, "error": str(exc)})

            def do_POST(self):
                parsed = urlparse(self.path)
                if parsed.path != "/write":
                    return self._send(404, {"ok": False, "error": "not found"})
                if not server.allow_write:
                    return self._send(403, {"ok": False, "error": "write disabled"})
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                raw_path = str(body.get("path", ""))
                data = str(body.get("data", ""))
                try:
                    target = server._resolve(raw_path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(data, encoding="utf-8")
                    self._send(200, {"ok": True, "path": str(target)})
                except Exception as exc:
                    self._send(400, {"ok": False, "error": str(exc)})

            def log_message(self, format, *args):
                return

        httpd = HTTPServer((self.host, self.port), Handler)
        print(f"File bridge listening on http://{self.host}:{self.port} root={self.root}")
        httpd.serve_forever()

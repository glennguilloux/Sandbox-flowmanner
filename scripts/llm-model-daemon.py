#!/usr/bin/env python3
"""
llm-model-daemon — Host-side HTTP API for the LLM model manager.

Runs on the homelab host (NOT inside Docker). Provides a simple REST API
that the FlowManner backend container calls to list, status-check, and
swap the active llama-server model.

Listens on 0.0.0.0:9723 — reachable from Docker containers via
http://10.0.4.1:9723 (same gateway as llama.cpp at :11434).

All model operations delegate to /opt/flowmanner/scripts/llm-model-manager.sh,
which handles YAML parsing, systemd override generation, and health checks.
"""

from __future__ import annotations

import subprocess
import json
import logging
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] llm-model-daemon: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

SCRIPT = "/opt/flowmanner/scripts/llm-model-manager.sh"
HOST = "0.0.0.0"
PORT = 9723


def run_script(*args: str, timeout: int = 180) -> tuple[int, str, str]:
    """Run the model manager script, return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            [SCRIPT, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"Script timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, data: dict | list | str):
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _log_request(self):
        log.info("%s %s", self.command, self.path)

    def do_GET(self):
        self._log_request()
        path = urlparse(self.path).path

        if path == "/health":
            self._json(200, {"status": "ok"})
            return

        if path == "/models":
            code, stdout, stderr = run_script("list")
            if code == 0:
                try:
                    self._json(200, json.loads(stdout))
                except json.JSONDecodeError:
                    self._json(
                        500, {"error": "Invalid JSON from script", "raw": stdout}
                    )
            else:
                self._json(500, {"error": stderr or stdout})
            return

        if path == "/status":
            code, stdout, stderr = run_script("status")
            if code == 0:
                try:
                    self._json(200, json.loads(stdout))
                except json.JSONDecodeError:
                    self._json(
                        500, {"error": "Invalid JSON from script", "raw": stdout}
                    )
            else:
                self._json(500, {"error": stderr or stdout})
            return

        self._json(404, {"error": f"Unknown path: {path}"})

    def do_POST(self):
        self._log_request()
        path = urlparse(self.path).path

        if path == "/activate":
            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode() if content_length else "{}"

            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._json(400, {"error": "Invalid JSON body"})
                return

            model_id = payload.get("model_id")
            if not model_id:
                self._json(400, {"error": "Missing 'model_id' in request body"})
                return

            log.info("Activating model: %s", model_id)
            code, stdout, stderr = run_script("activate", model_id, timeout=180)
            if code == 0:
                try:
                    data = json.loads(stdout)
                    self._json(200, data)
                except json.JSONDecodeError:
                    self._json(
                        200,
                        {"status": "activated", "model_id": model_id, "raw": stdout},
                    )
            else:
                log.error("Activation failed (code %d): %s", code, stderr)
                self._json(
                    500,
                    {
                        "error": "Failed to activate model",
                        "exit_code": code,
                        "stderr": stderr,
                        "stdout": stdout,
                    },
                )
            return

        self._json(404, {"error": f"Unknown path: {path}"})

    def log_message(self, format, *args):  # noqa: A002
        # Suppress default access logs (we log ourselves in do_GET/do_POST)
        pass


def main():
    server = HTTPServer((HOST, PORT), Handler)
    log.info("llm-model-daemon listening on %s:%d", HOST, PORT)
    log.info("Delegating to: %s", SCRIPT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()

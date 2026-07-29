"""Receive authenticated UNO Q frame bundles and store them atomically.

The receiver stores ciphertext packets only. It never receives the run key and
cannot reconstruct a face without a separately authorized recovery workflow.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SOFTWARE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SOFTWARE_ROOT / "python"))

from unoq_lorenz.laptop_sink import (  # noqa: E402
    ReceivedBundleStore,
    load_receiver_token,
    verify_request_auth,
)


class BundleReceiverServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        store: ReceivedBundleStore,
        token: bytes,
        max_bytes: int,
        max_clock_skew_seconds: int,
    ) -> None:
        super().__init__(server_address, BundleReceiverHandler)
        self.bundle_store = store
        self.receiver_token = token
        self.max_bytes = max_bytes
        self.max_clock_skew_seconds = max_clock_skew_seconds


class BundleReceiverHandler(BaseHTTPRequestHandler):
    server: BundleReceiverServer
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        self._send_json(
            200,
            {
                "ok": True,
                "service": "unoq-laptop-packet-receiver",
                "stores_plaintext": False,
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/bundles":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        if content_type.strip().lower() != "application/json":
            self._send_json(415, {"ok": False, "error": "content_type"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send_json(411, {"ok": False, "error": "content_length"})
            return
        if content_length <= 0 or content_length > self.server.max_bytes:
            self._send_json(413, {"ok": False, "error": "body_size"})
            return
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            self._send_json(400, {"ok": False, "error": "incomplete_body"})
            return
        auth_headers = {
            name: self.headers.get(name, "")
            for name in (
                "X-UNOQ-Auth",
                "X-UNOQ-Timestamp",
                "X-UNOQ-SHA256",
                "X-UNOQ-Signature",
            )
        }
        try:
            digest = verify_request_auth(
                self.server.receiver_token,
                body,
                auth_headers,
                max_clock_skew_seconds=self.server.max_clock_skew_seconds,
            )
        except ValueError:
            self._send_json(401, {"ok": False, "error": "authentication"})
            return
        try:
            stored = self.server.bundle_store.store(body, digest)
        except FileExistsError:
            self._send_json(409, {"ok": False, "error": "frame_conflict"})
            return
        except ValueError:
            self._send_json(422, {"ok": False, "error": "bundle_validation"})
            return
        self._send_json(
            200 if stored.duplicate else 201,
            {
                "ok": True,
                "duplicate": stored.duplicate,
                "run_id": stored.run_id,
                "frame_id": stored.frame_id,
                "packet_count": stored.packet_count,
                "sha256": stored.sha256,
            },
        )

    def log_message(self, format_string: str, *args: object) -> None:
        # The default access line is useful, but request headers and bodies are
        # deliberately never logged.
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), format_string % args)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Store authenticated UNO Q ciphertext bundles on this laptop. "
            "Allow the port only on a trusted/private firewall profile."
        )
    )
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.home() / "Documents" / "UNOQ-Captures",
    )
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=20_000_000)
    parser.add_argument("--max-clock-skew-seconds", type=int, default=300)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be within [1, 65535]")
    if args.max_bytes < 1024:
        raise SystemExit("--max-bytes must be at least 1024")
    if not 30 <= args.max_clock_skew_seconds <= 3600:
        raise SystemExit("--max-clock-skew-seconds must be within [30, 3600]")
    token = load_receiver_token(args.token_file)
    store = ReceivedBundleStore(args.output_dir)
    server = BundleReceiverServer(
        (args.bind, args.port),
        store=store,
        token=token,
        max_bytes=args.max_bytes,
        max_clock_skew_seconds=args.max_clock_skew_seconds,
    )
    print(f"UNO Q laptop receiver: http://{args.bind}:{args.port}/v1/bundles")
    print(f"Health check: http://127.0.0.1:{args.port}/health")
    print(f"Ciphertext output: {args.output_dir.resolve()}")
    print("No run key or plaintext image is accepted by this service.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReceiver stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

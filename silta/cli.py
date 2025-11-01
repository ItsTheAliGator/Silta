from __future__ import annotations

import argparse
import json
import signal
import threading
from typing import Dict, Optional, Tuple

from .client import FlowClient, DEFAULT_BACK_HOTKEY, DEFAULT_TOGGLE_HOTKEY
from .server import FlowServer
from .utils import LOG, Arguments, DependencyError, configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Share mouse/keyboard between two machines using pure Python",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--log-level", default="INFO", help="Python logging level")

    subparsers = parser.add_subparsers(dest="mode")

    srv = subparsers.add_parser("server", help="Run on the computer that should receive input")
    srv.add_argument("--host", default="0.0.0.0", help="Interface to bind")
    srv.add_argument("--port", type=int, default=59873, help="TCP port to listen on")
    srv.add_argument("--auth-token", help="Shared secret; must match the client")

    cli = subparsers.add_parser("client", help="Run on the computer whose mouse/keyboard you touch")
    cli.add_argument("--server", required=True, help="Server hostname or IP")
    cli.add_argument("--port", type=int, default=59873, help="Server TCP port")
    cli.add_argument("--auth-token", help="Shared secret; must match the server")
    cli.add_argument(
        "--edge-profile",
        help="Path to JSON file mapping screen edges to server targets",
    )
    cli.add_argument(
        "--edge",
        default="left",
        choices=["right", "left", "top", "bottom", "auto", "none"],
        help="Screen edge that activates remote control (auto watches all edges)",
    )
    cli.add_argument("--edge-margin", type=int, default=3, help="Pixels near the edge to trigger")
    cli.add_argument("--edge-delay", type=float, default=0.35, help="Seconds pointer must stay on edge")
    cli.add_argument(
        "--toggle-hotkey",
        default=DEFAULT_TOGGLE_HOTKEY,
        help="Hotkey to start forwarding (pynput syntax)",
    )
    cli.add_argument(
        "--back-hotkey",
        default=DEFAULT_BACK_HOTKEY,
        help="Hotkey to return control to the local machine",
    )
    cli.add_argument("--heartbeat", type=float, default=10.0, help="Heartbeat interval in seconds")
    cli.add_argument(
        "--local-cursor",
        default="auto",
        choices=["auto", "hide", "warp", "visible"],
        help="Behavior of the local cursor while remote control is active",
    )
    cli.add_argument(
        "--return-margin",
        type=int,
        default=8,
        help="Margin in pixels on the remote screen that triggers automatic return",
    )

    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run protocol self-tests and exit",
    )

    return parser


def run_self_test() -> None:
    from .keys import translate_key_for_pyautogui
    from .protocol import (
        build_client_hello,
        build_server_welcome,
        validate_client_hello,
        validate_server_welcome,
    )
    from .utils import json_dumps

    sample_keys = ["a", "<cmd>", "<shift>", "<option>", "<space>"]
    for key in sample_keys:
        translated = translate_key_for_pyautogui(key)
        assert isinstance(translated, str)
        assert translated
    hello = build_client_hello("self-test")
    validate_client_hello(dict(hello), "self-test")
    validate_server_welcome(build_server_welcome())
    payload = {"type": "move", "dx": 4, "dy": -2}
    encoded = json_dumps(payload)
    decoded = json.loads(encoded.decode("utf-8"))
    assert decoded == payload
    print("Self-test passed: protocol helpers look sane.")


def load_edge_profile(
    path: str, default_port: int, default_token: Optional[str]
) -> Dict[str, Tuple[str, int, Optional[str]]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except OSError as exc:
        raise ValueError(f"Unable to read edge profile '{path}': {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Edge profile must be a JSON object mapping edges to server configs")

    valid_edges = {"left", "right", "top", "bottom", "default"}
    profiles = {}
    for edge_name, config in raw.items():
        if not isinstance(edge_name, str):
            raise ValueError("Edge names in profile must be strings")
        normalized_edge = edge_name.lower()
        if normalized_edge not in valid_edges:
            raise ValueError(f"Unsupported edge name '{edge_name}' in edge profile")
        if not isinstance(config, dict):
            raise ValueError(f"Edge profile entry for '{edge_name}' must be a JSON object")

        host = config.get("host") or config.get("server")
        if not host or not isinstance(host, str):
            raise ValueError(f"Edge profile entry for '{edge_name}' is missing a valid 'host'")

        port_value = config.get("port", default_port)
        try:
            port = int(port_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Edge profile entry for '{edge_name}' specifies an invalid port") from exc

        token_value = config.get("auth_token", config.get("token", default_token))
        if token_value is not None and not isinstance(token_value, str):
            raise ValueError(f"Edge profile entry for '{edge_name}' specifies an invalid auth token")

        profiles[normalized_edge] = (host, port, token_value)

    return profiles


def install_signal_handlers(server: Optional[FlowServer] = None, stop_event: Optional[threading.Event] = None) -> None:
    def handler(signum, frame):  # noqa: ARG001
        LOG.info("Received signal %s", signum)
        if server:
            server.shutdown()
        if stop_event:
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handler)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.log_level)

    if args.self_test:
        run_self_test()
        return

    if not args.mode:
        parser.error("the following arguments are required: mode")

    try:
        if args.mode == "server":
            server = FlowServer(args.host, args.port, args.auth_token)
            install_signal_handlers(server=server)
            server.serve_forever()
            return

        if args.mode == "client":
            edge_profiles = None
            if args.edge_profile:
                try:
                    edge_profiles = load_edge_profile(args.edge_profile, args.port, args.auth_token)
                except ValueError as exc:
                    parser.error(str(exc))
            client = FlowClient(
                server_host=args.server,
                server_port=args.port,
                token=args.auth_token,
                edge_profiles=edge_profiles,
                edge=None if args.edge == "none" else args.edge,
                edge_margin=args.edge_margin,
                edge_delay=args.edge_delay,
                toggle_hotkey=args.toggle_hotkey,
                back_hotkey=args.back_hotkey,
                heartbeat=args.heartbeat,
                local_cursor_mode=args.local_cursor,
                return_margin=args.return_margin,
            )
            install_signal_handlers(stop_event=client._stop)  # type: ignore[attr-defined]
            client.run()
            return

        parser.error(f"Unknown mode: {args.mode}")
    except DependencyError as exc:
        LOG.error("%s", exc)
        raise SystemExit(1) from exc

"""Command-line entry point for wyoming_audiocpp_asr."""

from __future__ import annotations

import argparse
import logging
import sys

from wyoming import __version__ as wyoming_version

from .config import (
    DEFAULT_URI,
    DEFAULT_WEB_SERVER_HOST,
    DEFAULT_WEB_SERVER_PORT,
    Config,
)
from .server import create_tcp_server

BASIC_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wyoming-audiocpp-asr",
        description="Wyoming ASR service bridging to audio.cpp",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config.json (default: config.json)",
    )
    parser.add_argument(
        "--asr-uri",
        default=DEFAULT_URI,
        help="Wyoming TCP bind uri, tcp://host:port (default: %(default)s)",
    )
    parser.add_argument(
        "--audiocpp-uri",
        help="Base URI of the audio.cpp HTTP server (default from config.json)",
    )
    parser.add_argument(
        "--zeroconf",
        action="store_true",
        help="Register the service via mDNS _wyoming._tcp.local. discovery "
        "(requires the 'zeroconf' optional dependencies)",
    )
    parser.add_argument(
        "--asr-web-server",
        action="store_true",
        help="Also run the demo browser web server (requires the 'web' "
        "optional dependencies)",
    )
    parser.add_argument(
        "--asr-web-server-host",
        default=DEFAULT_WEB_SERVER_HOST,
        help="Interface for the demo web server (default: %(default)s)",
    )
    parser.add_argument(
        "--asr-web-server-port",
        type=int,
        default=DEFAULT_WEB_SERVER_PORT,
        help="Port for the demo web server (default: %(default)s)",
    )
    parser.add_argument(
        "--asr-web-server-allow",
        action="append",
        metavar="ADDRESS",
        default=[],
        help="Only serve the demo web server to this IP address or CIDR range, "
        "rejecting everything else (repeatable). When set, the server binds "
        "0.0.0.0 so remote clients can reach it.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--log-format",
        default=BASIC_FORMAT,
        help="Logging format (default: basic format)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s (wyoming {wyoming_version})",
    )
    return parser


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format=args.log_format,
    )

    config = Config.from_args(
        args.config,
        asr_uri=args.asr_uri,
        audiocpp_uri=args.audiocpp_uri,
        enable_zeroconf=args.zeroconf or None,
        asr_web_server=args.asr_web_server or None,
        asr_web_server_host=args.asr_web_server_host,
        asr_web_server_port=args.asr_web_server_port,
        asr_web_server_allow=args.asr_web_server_allow or None,
    )
    logging.getLogger("wyoming_audiocpp_asr").info("Wyoming %s | audio.cpp %s", config.asr_uri, config.audiocpp_uri)
    # Demo web server first: a missing 'web' install or an unavailable port
    # should fail now, before the Wyoming server starts.
    if config.asr_web_server:
        try:
            from .web_server import make_asr_web_server, parse_allow_list, run_web_server
        except ImportError as err:
            parser.error(
                f"--asr-web-server requires the 'web' optional dependencies ({err})"
            )

        if config.asr_web_server_allow:
            # Checked here so a typo is a startup error. Left to the middleware
            # it would parse to nothing and silently reject every request.
            try:
                parse_allow_list(config.asr_web_server_allow)
            except ValueError as err:
                parser.error(f"invalid --asr-web-server-allow value ({err})")

        # With an allow list the UI must be reachable by remote clients, so
        # bind all interfaces and filter by peer address instead.
        host = (
            "0.0.0.0" if config.asr_web_server_allow else config.asr_web_server_host
        )
        try:
            run_web_server(
                make_asr_web_server(config), host=host, port=config.asr_web_server_port
            )
        except OSError as err:
            parser.error(
                f"Could not start web UI on {host}:{config.asr_web_server_port} ({err})"
            )

    try:
        create_tcp_server(config)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())

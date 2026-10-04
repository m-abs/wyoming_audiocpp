"""Command-line entry point for wyoming_audiocpp_tts.

The default is to start a Wyoming TCP service (server.py) that speaks the
Wyoming event protocol so Home Assistant and Rhasspy can discover it via mDNS.
The Flask HTTP server (tts_server.py) is kept only as an optional demo, started
with ``--web-server``; importing it here would couple the default entry point to
the optional ``web`` dependencies.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Config

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wyoming-audiocpp-tts",
        description="Wyoming TTS service bridging to audio.cpp",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config.json (default: config.json)",
    )
    parser.add_argument(
        "--audiocpp-uri",
        help="Base URI of the audio.cpp HTTP server (default from config.json)",
    )

    # Wyoming TCP service (the default entry point).
    parser.add_argument(
        "--tts-uri",
        default="tcp://0.0.0.0:11201",
        help="Wyoming TCP bind, tcp://host:port (default: tcp://0.0.0.0:11201)",
    )
    parser.add_argument(
        "--zeroconf",
        action="store_true",
        help="Register mDNS _wyoming._tcp.local. discovery (default off)",
    )

    # Optional demo web server.
    parser.add_argument(
        "--tts-web-server",
        action="store_true",
        help="Run the demo browser web server in a background thread "
        "(requires the 'web' optional dependencies)",
    )
    parser.add_argument(
        "--tts-web-server-host",
        default="127.0.0.1",
        help="Interface for the demo web server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--tts-web-server-port",
        type=int,
        default=5001,
        help="Port for the demo web server (default: 5001)",
    )
    parser.add_argument(
        "--tts-web-server-allow",
        action="append",
        metavar="ADDRESS",
        help="Only serve the demo web server to this IP/CIDR (repeatable). "
        "The UI has no authentication, so restrict it whenever the bind address "
        "is reachable by anything but the intended client.",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log DEBUG messages",
    )
    parser.add_argument(
        "--log-format",
        default=logging.BASIC_FORMAT,
        help="Format for log messages",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"wyoming-audiocpp-tts {__version__}",
        help="Print version and exit",
    )
    return parser



def parse_args(argv=None) -> argparse.Namespace:
    parser = build_parser()
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format=args.log_format,
    )

    try:
        config = Config.from_args(
            args.config,
            audiocpp_uri=args.audiocpp_uri,
            tts_uri=args.tts_uri,
            enable_zeroconf=args.zeroconf or None,
            tts_web_server=args.tts_web_server or None,
            tts_web_server_host=args.tts_web_server_host,
            tts_web_server_port=args.tts_web_server_port,
            tts_web_server_allow=args.tts_web_server_allow,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    logging.getLogger("wyoming_audiocpp_tts").info("Wyoming %s | audio.cpp %s", config.tts_uri, config.audiocpp_uri)
    # Optional demo web server, in a background thread, started before the
    # Wyoming server: it only reads config, and a missing dependency or a bad
    # port should fail now rather than after the wait.
    if config.tts_web_server:
        try:
            from . import tts_server, web_server
            from .web_server import make_tts_web_server, parse_allow_list, run_web_server
        except ImportError as err:
            print(f"error: --tts-web-server requires the 'web' optional dependencies ({err})", file=sys.stderr)
            return 2

        if config.tts_web_server_allow:
            try:
                parse_allow_list(args.tts_web_server_allow)
            except ValueError as exc:
                print(f"error: invalid --tts-web-server-allow value ({exc})", file=sys.stderr)
                return 2

        try:
            flask_app = tts_server.create_app(config)
            web_app = make_tts_web_server(config, flask_app)
            thread = run_web_server(
                web_app, args.tts_web_server_host, args.tts_web_server_port, allow_list=args.tts_web_server_allow
            )
        except OSError as exc:
            print(
                f"error: could not start demo web server on "
                f"{args.tts_web_server_host}:{args.tts_web_server_port} ({exc})",
                file=sys.stderr,
            )
            return 2

    # Start the Wyoming TCP server (the default entry point).
    from .server import create_tcp_server

    create_tcp_server(config)
    return 0




if __name__ == "__main__":
    sys.exit(main())

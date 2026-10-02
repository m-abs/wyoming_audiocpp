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

__version__ = "0.1.0"


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
        "--asr-model",
        help="audio.cpp model id used for transcription (default from config.json)",
    )
    parser.add_argument(
        "--audiocpp-uri",
        help="Base URI of the audio.cpp HTTP server (default from config.json)",
    )
    _add_voice_scalar_args(parser)
    _add_voice_extra_args(parser)

    # Wyoming TCP service (the default entry point).
    parser.add_argument(
        "--uri",
        default="tcp://0.0.0.0:10200",
        help="Wyoming TCP bind, tcp://host:port (default: tcp://0.0.0.0:10200)",
    )
    parser.add_argument(
        "--zeroconf",
        action="store_true",
        help="Register mDNS _wyoming._tcp.local. discovery (default off)",
    )

    # Optional demo web server.
    parser.add_argument(
        "--web-server",
        action="store_true",
        help="Run the demo browser web server in a background thread "
        "(requires the 'web' optional dependencies)",
    )
    parser.add_argument(
        "--web-server-host",
        default="127.0.0.1",
        help="Interface for the demo web server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--web-server-port",
        type=int,
        default=5001,
        help="Port for the demo web server (default: 5001)",
    )
    parser.add_argument(
        "--web-server-allow",
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


def _add_voice_scalar_args(parser: argparse.ArgumentParser) -> None:
    """Add scalar ``--tts-voice0-<field>`` flags for the single default voice.

    Fields mirror the ``VoiceConfig`` scalars (``model``, ``name``,
    ``language``, ``speed``, ``instruct``).
    """
    for field in ("model", "name", "language", "speed", "instruct"):
        parser.add_argument(
            f"--tts-voice0-{field}",
            help=f"Override the {field} for the default TTS voice",
        )


def _add_voice_extra_args(parser: argparse.ArgumentParser) -> None:
    """Add ``--tts-voice0-extra-<key>`` arguments for any provided audio.cpp options.

    Any ``--tts-voice0-extra-<key>=<value>`` flag is collected into a single
    ``tts_voice0_extra`` dict (option name -> value, skipping ``None``).
    """
    known = {"seed", "format", "lang", "role", "response_format", "n"}
    for key in known:
        parser.add_argument(f"--tts-voice0-extra-{key}", help=f"audio.cpp extra {key}")


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
            asr_model=args.asr_model,
            audiocpp_uri=args.audiocpp_uri,
            uri=args.uri,
            enable_zeroconf=args.zeroconf,
            web_server=args.web_server,
            web_server_host=args.web_server_host,
            web_server_port=args.web_server_port,
            web_server_allow=args.web_server_allow,
            voice_overrides=_voice_overrides(args),
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Optional demo web server, in a background thread, started before the
    # Wyoming server: it only reads config, and a missing dependency or a bad
    # port should fail now rather than after the wait.
    if args.web_server:
        try:
            from . import tts_server, web_server
            from .web_server import make_tts_web_server, parse_allow_list, run_web_server
        except ImportError as err:
            print(f"error: --web-server requires the 'web' optional dependencies ({err})", file=sys.stderr)
            return 2

        if args.web_server_allow:
            try:
                parse_allow_list(args.web_server_allow)
            except ValueError as exc:
                print(f"error: invalid --web-server-allow value ({exc})", file=sys.stderr)
                return 2

        try:
            flask_app = tts_server.create_app(config)
            web_app = make_tts_web_server(config, flask_app)
            thread = run_web_server(
                web_app, args.web_server_host, args.web_server_port, allow_list=args.web_server_allow
            )
        except OSError as exc:
            print(
                f"error: could not start demo web server on "
                f"{args.web_server_host}:{args.web_server_port} ({exc})",
                file=sys.stderr,
            )
            return 2

    # Start the Wyoming TCP server (the default entry point).
    from .server import create_tcp_server

    create_tcp_server(config)
    return 0


def _voice_overrides(args) -> dict:
    """Build the voice override dict from the parsed CLI namespace.

    Keys mirror the config field names prefixed with ``tts_voice0_``; scalar
    fields override their config value, and any ``--tts-voice0-extra-<key>``
    flags are collected into a single ``tts_voice0_extra`` dict (option name ->
    value, skipping ``None``).
    """
    voice_overrides: dict = {}
    for field in ("model", "name", "language", "speed", "instruct"):
        value = getattr(args, f"tts_voice0_{field}", None)
        if value is not None:
            voice_overrides[f"tts_voice0_{field}"] = value
    extra = {}
    for key, value in vars(args).items():
        if key.startswith("tts_voice0_extra_") and value is not None:
            extra[key[len("tts_voice0_extra_"):]] = value
    if extra:
        voice_overrides["tts_voice0_extra"] = extra
    return voice_overrides


if __name__ == "__main__":
    sys.exit(main())

"""Command-line entry point for wyoming_audiocpp_asr."""

from __future__ import annotations

import argparse
import logging

from .config import Config


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
        "--audiocpp-uri",
        help="Base URI of the audio.cpp HTTP server (default from config.json)",
    )
    parser.add_argument(
        "--model",
        help="audio.cpp model id to use (default: hviske from config.json)",
    )
    parser.add_argument(
        "--language",
        help="Language hint for audio.cpp (default from config.json)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Interface to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=11301,
        help="Port to listen on (default: 11301)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO)",
    )
    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = Config.from_args(args.config, audiocpp_uri=args.audiocpp_uri, model=args.model, language=args.language)

    from .asr_server import create_app

    app = create_app(config)
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()

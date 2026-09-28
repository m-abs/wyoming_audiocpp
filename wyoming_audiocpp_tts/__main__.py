"""Command-line entry point for wyoming_audiocpp-tts."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Config


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
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Interface to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=11201,
        help="Port to listen on (default: 11201)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO)",
    )
    return parser


def _add_voice_scalar_args(parser: argparse.ArgumentParser) -> None:
    """Add scalar ``--tts-voice0-<field>`` flags for the single default voice.

    Fields are ``model``, ``name``, ``language``, ``speed`` and ``instruct``;
    ``None`` defaults keep the ``config.json`` value (see ``Config.from_args``).
    Any of these flags present replaces the file-supplied voice.
    """
    for field in ("model", "name", "language", "speed", "instruct"):
        parser.add_argument(
            f"--tts-voice0-{field}",
            default=None,
            help=f"Voice {field} (default from config.json)",
        )


def _add_voice_extra_args(parser: argparse.ArgumentParser) -> None:
    """Add ``--tts-voice0-extra-<key>`` arguments for any provided audio.cpp options.

    The keys are discovered from ``argv`` so the user can pass any audio.cpp
    ``options`` field (``seed``, ``response_format``, ``voice_ref``, ...) without
    editing the parser ahead of time. Duplicate keys are not re-added.
    """
    prefix = "--tts-voice0-extra-"
    keys = []
    for token in sys.argv[1:]:
        if token.startswith(prefix):
            key = token[len(prefix):]
            if key and key not in keys:
                keys.append(key)
    for key in keys:
        parser.add_argument(
            f"{prefix}{key}",
            default=None,
            help=f"Extra audio.cpp option for the voice (e.g. --tts-voice0-extra-seed 42)",
        )


def parse_args(argv=None) -> argparse.Namespace:
    parser = build_parser()
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = Config.from_args(
            args.config,
            asr_model=args.asr_model,
            audiocpp_uri=args.audiocpp_uri,
            voice_overrides=_voice_overrides(args),
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    from .tts_server import create_app

    app = create_app(config)
    app.run(host=args.host, port=args.port)
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

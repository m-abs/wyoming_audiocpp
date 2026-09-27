"""Wyoming event wire protocol.

Wyoming services exchange events over a byte stream using this framing:

* a JSON line with ``{"type": "...", "data_length": N}`` (no ``data`` key),
* followed by ``N`` raw bytes holding the JSON encoding of ``data``.

The data bytes *replace* the header's data entirely. This is a faithful copy of
the protocol used by the ``wyoming`` package so our service interoperates with
any Wyoming client (Rhasspy, Home Assistant, ...).
"""

from __future__ import annotations

import io
import os

import json
from typing import Any, Dict, Optional

TYPE = "type"
DATA_LENGTH = "data_length"
NEWLINE = b"\n"

_CHUNK = 512


def encode(data: Dict[str, Any]) -> bytes:
    """Serialize a Wyoming event's ``data`` to its wire representation.

    ``data`` is the payload mapping (the Wyoming ``Event.data``), not the whole
    event. Returns the header line followed by the raw data bytes.
    """
    data_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")

    header = json.dumps({TYPE: "", DATA_LENGTH: len(data_bytes)}, ensure_ascii=False)
    header += NEWLINE.decode("ascii")

    return header.encode("utf-8") + data_bytes


def _read_line(stream: Any) -> Optional[bytes]:
    """Read one line (including the trailing newline) from ``stream``.

    Works with any binary stream exposing ``read`` (files, sockets, buffers).
    Returns ``None`` when the stream is closed before any data is read.
    """
    buf = b""
    while NEWLINE not in buf:
        chunk = stream.read(_CHUNK)
        if not chunk:
            return None
        buf += chunk
    newline = buf.index(NEWLINE)
    # Rewind past the consumed header line so the next ``read`` continues
    # with the chunk's data payload.
    stream.seek(0, os.SEEK_SET)
    stream.seek(buf.index(NEWLINE) + 1, os.SEEK_SET)
    return buf[: newline + 1]


def decode(stream: Any) -> Optional[Dict[str, Any]]:
    """Read one event's data from ``stream``.

    ``stream`` is a binary stream (a file, a socket, a buffer) or raw ``bytes``.

    Returns the data dict, or ``None`` when the stream is closed.
    """
    if isinstance(stream, (bytes, bytearray)):
        stream = io.BytesIO(stream)

    line = _read_line(stream)
    if line is None:
        return None

    try:
        header = json.loads(line)
    except ValueError:
        return None

    length = header.get(DATA_LENGTH)
    if not length:
        return {}

    raw = stream.read(length)
    if len(raw) != length:
        # Truncated payload: the stream closed before the full chunk was
        # received, so treat it as a broken stream.
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        return None

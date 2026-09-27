"""Tests for the Wyoming wire protocol."""

from wyoming_audiocpp_asr import wire


def test_encode_decode_roundtrip():
    data = {"text": "héllo", "count": 3, "nested": {"a": True}}
    stream = wire.decode(wire.encode(data))
    assert stream == data


def test_decode_eof_returns_none():
    import io

    assert wire.decode(io.BytesIO(b"")) is None


def test_decode_empty_data_returns_empty_dict():
    import io

    stream = wire.decode(io.BytesIO(b'{"type": "", "data_length": 0}\n'))
    assert stream == {}


def test_encode_contains_length_field():
    result = wire.encode({"a": 1})
    assert b'"data_length"' in result
    assert result.endswith(b'{"a": 1}')


def test_decode_partial_data_returns_none():
    import io

    # Header claims 100 bytes but stream ends after 10.
    stream = io.BytesIO(b'{"type": "", "data_length": 100}\n{"a": 1}')
    assert wire.decode(stream) is None

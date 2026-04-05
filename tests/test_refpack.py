"""Tests for RefPack compression/decompression."""

from cnc_zh_map_maker import refpack


def test_is_refpack_compressed_ear_header():
    data = b"EAR\x00" + b"\x00" * 100
    assert refpack.is_refpack_compressed(data) is True


def test_is_refpack_compressed_raw():
    data = b"\x00\xFB" + b"\x00" * 100
    assert refpack.is_refpack_compressed(data) is True


def test_not_compressed():
    data = b"CkMp" + b"\x00" * 100
    assert refpack.is_refpack_compressed(data) is False


def test_compress_decompress_roundtrip():
    original = b"Hello World! " * 100 + b"This is test data " * 50
    compressed = refpack.compress(original)
    assert len(compressed) < len(original), "Compression should reduce size"

    decompressed = refpack.decompress(compressed)
    assert decompressed == original, "Roundtrip should preserve data"


def test_compress_decompress_repeating():
    original = bytes([i % 256 for i in range(10000)])
    compressed = refpack.compress(original)
    decompressed = refpack.decompress(compressed)
    assert decompressed == original


def test_compress_decompress_small():
    original = b"ABCD"
    compressed = refpack.compress(original)
    decompressed = refpack.decompress(compressed)
    assert decompressed == original

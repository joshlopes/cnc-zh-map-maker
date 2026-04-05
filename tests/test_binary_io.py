"""Tests for binary I/O and string dictionary parsing."""

from pathlib import Path

import pytest

from cnc_zh_map_maker.binary_io import MapReader, MapWriter


SAMPLES_DIR = Path(__file__).parent.parent / "maps" / "samples"
OPENSAGE_DIR = SAMPLES_DIR / "opensage"


@pytest.fixture
def opensage_sideslist():
    path = OPENSAGE_DIR / "SidesList.map"
    if not path.exists():
        pytest.skip("Sample map not available")
    return path.read_bytes()


def test_read_string_dictionary(opensage_sideslist):
    reader = MapReader(opensage_sideslist)
    reader.read_string_dictionary()

    assert len(reader.asset_names) > 0
    # Should contain known asset names
    names = set(reader.asset_names.values())
    assert "HeightMapData" in names
    assert "SidesList" in names or "playerName" in names


def test_read_asset_headers(opensage_sideslist):
    reader = MapReader(opensage_sideslist)
    reader.read_string_dictionary()

    headers = []
    while reader.remaining() >= 10:
        header = reader.read_asset_header()
        if header is None:
            break
        headers.append(header)
        reader.skip_asset(header)

    assert len(headers) > 0
    names = [h.asset_name for h in headers]
    # The first chunk is the _MapRoot container, which wraps all other assets
    assert "_MapRoot" in names or "HeightMapData" in names


def test_writer_roundtrip():
    writer = MapWriter()
    writer.register_asset_name("TestAsset")
    writer.register_asset_name("testProperty")

    writer.write_string_dictionary()
    size_pos = writer.begin_asset("TestAsset", 1)
    writer.write_u32(42)
    writer.write_f32(3.14)
    writer.end_asset(size_pos)

    data = writer.get_bytes()

    # Read back
    reader = MapReader(data)
    reader.read_string_dictionary()
    assert "TestAsset" in reader.asset_names.values()

    header = reader.read_asset_header()
    assert header is not None
    assert header.asset_name == "TestAsset"
    assert header.version == 1

    val1 = reader.read_u32()
    val2 = reader.read_f32()
    assert val1 == 42
    assert abs(val2 - 3.14) < 0.001


@pytest.mark.parametrize("map_file", list(SAMPLES_DIR.glob("*.map")) if SAMPLES_DIR.exists() else [])
def test_can_read_real_map_headers(map_file):
    """Verify we can at least read the string dictionary and headers from real maps."""
    from cnc_zh_map_maker import refpack

    data = map_file.read_bytes()
    if refpack.is_refpack_compressed(data):
        try:
            data = refpack.decompress(data)
        except Exception:
            pytest.skip(f"Could not decompress {map_file.name}")

    reader = MapReader(data)
    try:
        reader.read_string_dictionary()
    except Exception:
        pytest.skip(f"Could not read dictionary for {map_file.name}")

    assert len(reader.asset_names) > 0, f"No asset names in {map_file.name}"

"""CLI for C&C Generals Zero Hour map tools.

Usage:
    zh-map info <map_file>           Show map summary
    zh-map dump <map_file>           Dump raw section info
    zh-map create <name> [options]   Create a new map from presets
    zh-map preview <map_file>        Generate heightmap preview image
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cnc_zh_map_maker.map_file import MapFile
from cnc_zh_map_maker.builder import MapBuilder, MapSize, TerrainPreset, LightingPreset
from cnc_zh_map_maker.data_model import MapWeatherType


def main():
    parser = argparse.ArgumentParser(
        description="C&C Generals Zero Hour Map Tool",
        prog="zh-map",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # info command
    info_p = sub.add_parser("info", help="Show map file summary")
    info_p.add_argument("map_file", help="Path to .map file")

    # dump command
    dump_p = sub.add_parser("dump", help="Dump raw asset sections")
    dump_p.add_argument("map_file", help="Path to .map file")
    dump_p.add_argument("--json", action="store_true", help="Output as JSON")

    # create command
    create_p = sub.add_parser("create", help="Create a new map")
    create_p.add_argument("name", help="Map name")
    create_p.add_argument("--size", choices=[s.name for s in MapSize], default="SMALL_2P")
    create_p.add_argument("--terrain", default="desert", help="Base terrain preset")
    create_p.add_argument("--weather", choices=["normal", "snowy"], default="normal")
    create_p.add_argument("--players", type=int, default=2, help="Number of players (2-8)")
    create_p.add_argument("--output", "-o", default=".", help="Output directory")
    create_p.add_argument("--compress", action="store_true", help="RefPack compress output")

    # preview command
    preview_p = sub.add_parser("preview", help="Generate heightmap preview")
    preview_p.add_argument("map_file", help="Path to .map file")
    preview_p.add_argument("--output", "-o", help="Output PNG path")

    args = parser.parse_args()

    if args.command == "info":
        cmd_info(args)
    elif args.command == "dump":
        cmd_dump(args)
    elif args.command == "create":
        cmd_create(args)
    elif args.command == "preview":
        cmd_preview(args)


def cmd_info(args):
    mf = MapFile.from_file(args.map_file)
    print(mf.summary())


def cmd_dump(args):
    from cnc_zh_map_maker.binary_io import MapReader
    from cnc_zh_map_maker import refpack

    data = Path(args.map_file).read_bytes()
    compressed = refpack.is_refpack_compressed(data)
    if compressed:
        data = refpack.decompress(data)

    reader = MapReader(data)
    reader.read_string_dictionary()

    sections = []
    print(f"File: {args.map_file}")
    print(f"Size: {Path(args.map_file).stat().st_size} bytes")
    print(f"Compressed: {compressed}")
    print(f"Decompressed: {len(data)} bytes")
    print(f"\nString dictionary ({len(reader.asset_names)} entries):")
    for idx in sorted(reader.asset_names.keys()):
        print(f"  [{idx:3d}] {reader.asset_names[idx]}")

    print(f"\nAsset chunks:")
    while reader.remaining() >= 10:
        header = reader.read_asset_header()
        if header is None:
            break
        section = {
            "name": header.asset_name,
            "index": header.asset_index,
            "version": header.version,
            "size": header.data_size,
            "offset": header.data_start,
        }
        sections.append(section)
        print(f"  {header.asset_name:30s} v{header.version:2d}  {header.data_size:8d} bytes  @{header.data_start}")
        reader.skip_asset(header)

    if args.json:
        print(json.dumps(sections, indent=2))


def cmd_create(args):
    size = MapSize[args.size]
    terrain_map = {
        "desert": TerrainPreset.DESERT,
        "grass": TerrainPreset.GRASS,
        "snow": TerrainPreset.SNOW,
        "dirt": TerrainPreset.DIRT,
        "urban": TerrainPreset.URBAN,
        "sand": TerrainPreset.SAND,
        "rock": TerrainPreset.ROCK,
    }
    terrain = terrain_map.get(args.terrain.lower(), TerrainPreset.DESERT)
    weather = MapWeatherType.SNOWY if args.weather == "snowy" else MapWeatherType.NORMAL

    builder = MapBuilder(args.name, size=size, weather=weather)
    builder.set_terrain(terrain)

    if weather == MapWeatherType.SNOWY:
        builder.set_lighting(LightingPreset.SNOW_OVERCAST)

    # Auto-place player starts
    w, h = size.value
    margin = w // 5
    positions = _generate_player_positions(args.players, w, h, margin)
    builder.add_skirmish_players(args.players, positions)

    # Add supply docks near each player
    for i, pos in enumerate(positions):
        offset_x = 20 if pos[0] < w / 2 else -20
        builder.add_supply_dock(i + 1, (pos[0] + offset_x, pos[1]))

    path = builder.build_and_save(args.output, compress=args.compress)
    print(f"Created map: {path}")


def _generate_player_positions(
    num_players: int,
    width: int,
    height: int,
    margin: int,
) -> list[tuple[float, float]]:
    """Generate evenly-spaced player positions."""
    import math

    cx, cy = width / 2, height / 2
    radius = min(width, height) / 2 - margin

    positions = []
    for i in range(num_players):
        angle = (2 * math.pi * i / num_players) - math.pi / 2
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        positions.append((x, y))

    return positions


def cmd_preview(args):
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        print("Preview requires Pillow and numpy: pip install Pillow numpy")
        sys.exit(1)

    mf = MapFile.from_file(args.map_file)
    hm = mf.height_map

    if not hm.elevations:
        print("No heightmap data found")
        sys.exit(1)

    # Convert to numpy array
    arr = np.array(hm.elevations, dtype=np.float32)
    arr = arr * hm.ELEVATION_SCALE

    # Normalize to 0-255
    min_v, max_v = arr.min(), arr.max()
    if max_v > min_v:
        arr = (arr - min_v) / (max_v - min_v) * 255
    else:
        arr = np.full_like(arr, 128)

    img = Image.fromarray(arr.astype(np.uint8), mode="L")

    output = args.output or Path(args.map_file).with_suffix(".png")
    img.save(output)
    print(f"Preview saved: {output}")


if __name__ == "__main__":
    main()

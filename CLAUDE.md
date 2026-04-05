# C&C Generals Zero Hour Map Maker

## Project Overview

Python library and CLI for reading, writing, and generating Command & Conquer: Generals Zero Hour map files (.map format).

## Architecture

```
src/cnc_zh_map_maker/
  __init__.py          - Exports MapFile, MapBuilder
  refpack.py           - EA RefPack compression/decompression
  binary_io.py         - Low-level binary reader/writer for SAGE format
  data_model.py        - All data structures (HeightMapData, BlendTileData, etc.)
  map_file.py          - MapFile class: parse and serialize .map files
  builder.py           - MapBuilder: high-level fluent API for creating maps
  cli.py               - CLI tool (zh-map info/dump/create/preview)
```

## Key Concepts

- Maps use EA's SAGE engine binary format with `CkMp` magic
- Compressed maps use RefPack (EAR\0 header)
- Binary format: string dictionary → nested asset chunks (index + version + size + payload)
- HeightMap elevations: u16 values, scaled by 0.0390625 for world-space height
- Tile grids are (heightmap_width - 1) × (heightmap_height - 1)

## Running Tests

```bash
python3 -m pytest tests/ -v
```

## Creating a Map (Python API)

```python
from cnc_zh_map_maker import MapBuilder
from cnc_zh_map_maker.builder import MapSize, TerrainPreset

builder = MapBuilder("Desert Clash", size=MapSize.SMALL_2P)
builder.set_terrain(TerrainPreset.DESERT)
builder.add_player_start(1, (30, 30))
builder.add_player_start(2, (120, 120))
builder.add_supply_dock(1, (40, 30))
builder.add_supply_dock(2, (110, 120))
builder.add_hill(center=(75, 75), radius=30, height=15.0)
builder.add_trees((50, 50, 100, 100), count=20, seed=42)
builder.build_and_save("output/")
```

## CLI Usage

```bash
zh-map info maps/samples/SomeMap.map
zh-map dump maps/samples/SomeMap.map
zh-map create "My Map" --size MEDIUM_4P --terrain desert --players 4
```

## Format Documentation

See `docs/MAP_FORMAT.md` for the complete binary format specification.

## Sample Maps

`maps/samples/` contains downloaded maps for testing:
- `opensage/` - Minimal test fixtures from OpenSAGE project
- `*.map` - Community ranked maps from TheSuperHackers

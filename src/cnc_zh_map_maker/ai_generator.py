"""AI-powered map generation from natural language descriptions.

Uses Claude API to convert user descriptions into MapBuilder code,
then executes it to produce a map file.
"""

from __future__ import annotations

import json
import re
import traceback
from pathlib import Path
from typing import Optional

from cnc_zh_map_maker.builder import (
    MapBuilder,
    MapSize,
    TerrainPreset,
    LightingPreset,
    OBJECTS,
)
from cnc_zh_map_maker.data_model import MapWeatherType
from cnc_zh_map_maker.map_file import MapFile

SYSTEM_PROMPT = """\
You are a C&C Generals Zero Hour map designer. Given a description, output ONLY valid Python code \
that uses the MapBuilder API to create the map. No markdown, no explanation, just code.

The code MUST:
1. Create a MapBuilder with a creative name and appropriate size
2. Set terrain and lighting
3. Add player starts with add_skirmish_players()
4. Add supply docks near each player
5. Add terrain features (hills, valleys, cliffs, plateaus)
6. Add objects (trees, rocks, buildings, tech buildings)
7. End with: map_file = builder.build()

Available API:

```
from cnc_zh_map_maker.builder import MapBuilder, MapSize, TerrainPreset, LightingPreset
from cnc_zh_map_maker.data_model import MapWeatherType

# Sizes: TINY_2P(100x100), SMALL_2P(150x150), MEDIUM_2P(200x200),
#        MEDIUM_4P(250x250), LARGE_4P(300x300), LARGE_8P(400x400), HUGE_8P(500x500)
# Terrains: DESERT, GRASS, SNOW, DIRT, URBAN, SAND, ROCK, MUD
# Lighting: DEFAULT, DESERT_AFTERNOON, FOREST_MORNING, URBAN_NIGHT, SNOW_OVERCAST
# Weather: MapWeatherType.NORMAL, MapWeatherType.SNOWY

builder = MapBuilder("Map Name", size=MapSize.SMALL_2P, weather=MapWeatherType.NORMAL)
builder.set_terrain(TerrainPreset.DESERT)
builder.add_terrain(TerrainPreset.ROCK)  # additional blend texture
builder.set_lighting(LightingPreset.DESERT_AFTERNOON)
builder.set_base_elevation(14.0)  # world units, default ~15.6

# Topology
builder.add_hill(center=(x, y), radius=25, height=15.0, falloff=2.0)  # 1=cone, 2=smooth, 3=very smooth
builder.add_valley(center=(x, y), radius=20, depth=10.0, falloff=2.0)
builder.add_cliff(start=(x1, y1), end=(x2, y2), height=12.0, width=8)
builder.add_plateau(center=(x, y), radius=30, height=18.0)

# Players (positions in grid coords, not world coords)
positions = [(30, 30), (120, 120)]  # must be within map bounds
builder.add_skirmish_players(2, positions)  # auto-creates AI waypoints
builder.add_supply_dock(player_num, (x, y))  # near each player start

# Objects
builder.add_object("TypeName", (x, y), angle=0, owner="")
builder.add_trees((x1, y1, x2, y2), count=20, seed=42)
builder.add_rocks((x1, y1, x2, y2), count=10, seed=42)
builder.add_civilian_buildings((x1, y1, x2, y2), count=5, seed=42)
builder.add_tech_building("TechOilDerrick", (x, y), angle=-45)
builder.add_tech_building("TechHospital", (x, y))

# Tech building types: TechOilDerrick, TechOilRefinery, TechArtilleryPlatform, TechHospital

map_file = builder.build()
```

RULES:
- All coordinates must be within map bounds (0 to width/height)
- Place player starts with margin from edges (at least 15% of map size)
- Each player needs 1-2 supply docks within 25 units of their start
- Use seed parameter for random scatter functions for reproducibility
- Mirror the layout for fairness in competitive maps
- Add variety: mix hills, valleys, and flat areas
- Place tech buildings equidistant from all players
- Garrisonable buildings near chokepoints
- The variable MUST be called map_file at the end
"""


def generate_map_from_description(
    description: str,
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
) -> tuple[MapFile, str, str]:
    """Generate a map from a natural language description.

    Args:
        description: User's map description
        api_key: Anthropic API key
        model: Claude model to use

    Returns:
        (map_file, map_name, generated_code)

    Raises:
        Exception on API or code execution errors
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": description}
        ],
    )

    code = message.content[0].text

    # Strip markdown code fences if present
    code = re.sub(r"^```python\s*\n?", "", code, flags=re.MULTILINE)
    code = re.sub(r"^```\s*$", "", code, flags=re.MULTILINE)
    code = code.strip()

    # Ensure required imports are present
    if "from cnc_zh_map_maker" not in code:
        imports = (
            "from cnc_zh_map_maker.builder import MapBuilder, MapSize, TerrainPreset, LightingPreset\n"
            "from cnc_zh_map_maker.data_model import MapWeatherType\n\n"
        )
        code = imports + code

    # Execute the generated code
    namespace = {}
    exec(code, namespace)

    map_file = namespace.get("map_file")
    if map_file is None:
        raise ValueError("Generated code did not produce a 'map_file' variable")

    if not isinstance(map_file, MapFile):
        raise ValueError(f"'map_file' is {type(map_file)}, expected MapFile")

    map_name = map_file.world_info.map_name or "Generated Map"

    return map_file, map_name, code


def generate_map_offline(
    description: str,
) -> tuple[MapFile, str]:
    """Generate a map without AI, using keyword matching for simple presets.

    Fallback when no API key is available.
    """
    desc = description.lower()

    # Detect player count
    num_players = 2
    for n in [8, 6, 4, 2]:
        if str(n) in desc or f"{n}-player" in desc or f"{n} player" in desc:
            num_players = n
            break

    # Detect size
    if num_players >= 6:
        size = MapSize.LARGE_8P
    elif num_players >= 4:
        size = MapSize.MEDIUM_4P
    elif "large" in desc or "big" in desc:
        size = MapSize.MEDIUM_2P
    elif "tiny" in desc or "small" in desc:
        size = MapSize.TINY_2P
    else:
        size = MapSize.SMALL_2P

    # Detect terrain
    terrain = TerrainPreset.GRASS
    lighting = LightingPreset.DEFAULT
    weather = MapWeatherType.NORMAL

    if any(w in desc for w in ["desert", "sand", "arid", "dry"]):
        terrain = TerrainPreset.DESERT
        lighting = LightingPreset.DESERT_AFTERNOON
    elif any(w in desc for w in ["snow", "ice", "winter", "frozen", "arctic"]):
        terrain = TerrainPreset.SNOW
        lighting = LightingPreset.SNOW_OVERCAST
        weather = MapWeatherType.SNOWY
    elif any(w in desc for w in ["urban", "city", "town"]):
        terrain = TerrainPreset.URBAN
        lighting = LightingPreset.URBAN_NIGHT if "night" in desc else LightingPreset.DEFAULT
    elif any(w in desc for w in ["forest", "green", "grass", "jungle"]):
        terrain = TerrainPreset.GRASS
        lighting = LightingPreset.FOREST_MORNING

    # Build map name from description
    words = description.split()[:4]
    map_name = " ".join(w.capitalize() for w in words) if words else "Generated Map"

    w, h = size.value
    margin = int(w * 0.18)
    import math

    builder = MapBuilder(map_name, size=size, weather=weather)
    builder.set_terrain(terrain)
    builder.set_lighting(lighting)
    builder.set_base_elevation(14.0)

    # Generate player positions in a circle
    cx, cy = w / 2, h / 2
    radius = min(w, h) / 2 - margin
    positions = []
    for i in range(num_players):
        angle = (2 * math.pi * i / num_players) - math.pi / 2
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        positions.append((x, y))

    builder.add_skirmish_players(num_players, positions)

    # Supply docks
    for i, (px, py) in enumerate(positions):
        dx = 20 if px < cx else -20
        builder.add_supply_dock(i + 1, (px + dx, py))

    # Central feature
    if any(w in desc for w in ["hill", "mountain", "plateau", "mesa"]):
        builder.add_plateau(center=(cx, cy), radius=w // 8, height=20.0)
    else:
        builder.add_hill(center=(cx, cy), radius=w // 6, height=12.0, falloff=2.0)

    # Hills near bases
    for px, py in positions:
        builder.add_hill(center=(px, py), radius=15, height=5.0, falloff=2.5)

    # Tech buildings
    if num_players == 2:
        builder.add_tech_building("TechOilDerrick", (cx, cy - 20), angle=-45)
        builder.add_tech_building("TechOilDerrick", (cx, cy + 20), angle=-45)
    else:
        for i in range(num_players):
            angle = (2 * math.pi * i / num_players) + math.pi / num_players
            tx = cx + radius * 0.5 * math.cos(angle)
            ty = cy + radius * 0.5 * math.sin(angle)
            builder.add_tech_building("TechOilDerrick", (tx, ty), angle=-45)

    # Trees and rocks
    builder.add_trees((margin, margin, w - margin, h - margin), count=num_players * 10, seed=42)
    builder.add_rocks((cx - 30, cy - 30, cx + 30, cy + 30), count=8, seed=42)

    # Civilian buildings in center
    builder.add_civilian_buildings(
        (cx - 20, cy - 20, cx + 20, cy + 20), count=min(4, num_players), seed=42
    )

    return builder.build(), map_name

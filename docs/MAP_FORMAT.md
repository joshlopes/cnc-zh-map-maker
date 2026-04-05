# C&C Generals Zero Hour .map File Format

## Overview

The SAGE engine (used by C&C Generals, Zero Hour, BFME series) stores map data in a binary
chunk-based format. Files use the `.map` extension and can be either uncompressed or
RefPack-compressed.

## Compression

Maps may be wrapped in EA's RefPack (QFS) compression:

- **Uncompressed**: Starts with `CkMp` magic (4 bytes: `43 6b 4d 70`)
- **Compressed**: Starts with `EAR\0` header (4 bytes: `45 41 52 00`) followed by RefPack stream
- **Raw RefPack**: Starts with `0x10 0xFB` (flags + magic), followed by 3-byte big-endian decompressed size

After decompression, all maps have the same `CkMp` internal structure.

## File Structure

```
┌──────────────────────┐
│ Magic: "CkMp" (4B)   │
├──────────────────────┤
│ String Dictionary     │  ← Maps integer indices to ASCII name strings
├──────────────────────┤
│ Root Asset Container  │  ← Index 1, wraps all sections
│ ├─ HeightMapData      │
│ ├─ BlendTileData      │
│ ├─ WorldInfo          │
│ ├─ SidesList          │
│ ├─ ObjectsList        │
│ ├─ WaypointsList      │
│ ├─ GlobalLighting     │
│ ├─ PolygonTriggers    │
│ ├─ PlayerScriptsList  │
│ └─ (other sections)   │
└──────────────────────┘
```

## String Dictionary

Immediately after `CkMp`, the string dictionary stores all asset/property names referenced
throughout the file. Entries are stored in **descending index order**.

### Format

Two variants exist. In OpenSAGE's serialization, entries use u16-prefixed strings with
a u32 count header. In practice (observed in real map files), entries use a simpler format:

```
Repeated entries (descending index order, no explicit count):
┌─────────────┬──────────┬───────────────┐
│ Index (u32) │ Len (u8) │ ASCII Name    │
│ little-end  │          │ (no null-term) │
└─────────────┴──────────┴───────────────┘
```

- Indices count down from N to 2 (index 1 is the implicit root container)
- Names are ASCII strings without null terminators
- Typical dictionaries have 50-100 entries
- The dictionary ends when the pattern breaks (first asset chunk follows)

### Example

```hex
52 00 00 00   0d   57 61 79 70 6f 69 6e 74 73 4c 69 73 74
  index=82    len=13          "WaypointsList"

51 00 00 00   0e   47 6c 6f 62 61 6c 4c 69 67 68 74 69 6e 67
  index=81    len=14          "GlobalLighting"
```

## Asset Chunk Format

Each asset section (HeightMapData, ObjectsList, etc.) follows this header format:

```
┌──────────────────┬──────────────┬──────────────────┬─────────────┐
│ Asset Index (u32) │ Version (u16) │ Data Size (u32)  │ Payload ... │
│ → lookup in dict │ format ver    │ bytes of payload │             │
└──────────────────┴──────────────┴──────────────────┴─────────────┘
```

- **Asset Index**: References the string dictionary to identify the section type
- **Version**: Format version (determines which fields are present)
- **Data Size**: Exact byte count of the payload that follows
- Assets can be nested (e.g., SidesList contains Player and Team sub-assets)

## Core Sections

### HeightMapData (version 5)

Terrain elevation grid.

| Field | Type | Description |
|-------|------|-------------|
| Width | u32 | Grid width in cells |
| Height | u32 | Grid height in cells |
| BorderWidth | u32 | Border size |
| NumBorders | u32 | Number of border corners |
| Borders[] | u32 x,y pairs | Border corner positions |
| Area | u32 | Width × Height validation |
| Elevations[y][x] | u16 (v5+) or u8 (v4-) | Elevation values |

**Elevation scaling**:
- **Generals/ZH (v < 5)**: u8 values (0-255) × 0.625 = max 159.375 world units
- **BFME+ (v >= 5)**: u16 values (0-65535) × 0.0390625 = max 2560 world units
- Water level is approximately elevation value 16 (10.0 world units in ZH)
- **MapXYFactor = 10**: each heightmap cell = 10 world units horizontally
- Maximum recommended terrain height: 316 units
- Slopes > ~89.99° are impassable to ground units

### BlendTileData (version 6-14+)

Terrain textures and passability. Grid dimensions are `(HeightMap.Width-1) × (HeightMap.Height-1)`.

| Field | Type | Description |
|-------|------|-------------|
| NumTiles | u32 | Total tile count |
| NumTextures | u32 | Number of texture definitions |
| Textures[] | struct | Texture name + cell info |
| Tiles[y][x] | u16 | Base texture index per tile |
| Blends[y][x] | u32 | Blend transition values |
| ThreeWayBlends[y][x] | u32 | 3-way blend values |
| CliffTextures[y][x] | u32 | Cliff texture indices |
| Impassable[y][x] | bit | Ground impassability |
| ImpassableToPlayers[y][x] | bit | Player-only impassability |
| ImpassableToAir[y][x] | bit | Air unit impassability |
| ExtraPassable[y][x] | bit | Override passability |
| Flammability[y][x] | enum | Fire behavior |
| Buildable[y][x] | bool | Can place buildings |

**Texture entry**: `CellStart(u32) + CellCount(u32) + CellSize(u32) + NameLen(u16) + Name`

Common texture names: `AsphaltType1`, `GrassType1`, `SnowType1`, `SandType1`, `RockType1`,
`CliffType2`, `MudType1`, `AsphaltType2`

### WorldInfo (version 1)

Map metadata stored as property collection.

| Property | Type | Description |
|----------|------|-------------|
| mapName | ASCII string | Display name |
| weather | u32 | 1=Normal, 2=Snowy |
| compression | u32 | 0=None, 1=RefPack |

### ObjectsList (version 1)

Placed map objects (buildings, trees, props, units).

| Field | Type | Description |
|-------|------|-------------|
| NumObjects | u32 | Object count |
| Per object: | | |
| Position | 3×f32 | X, Y, Z world coordinates |
| Angle | f32 | Rotation in radians |
| RoadType | u32 | Road classification flags |
| TypeName | u16+ASCII | Object type identifier |
| NumProperties | u16 | Property count |
| Properties[] | typed | Key-value pairs |

Common object properties:
- `originalOwner` (ASCII): Player name or "" for neutral
- `objectInitialHealth` (f32): Starting health percentage
- `objectEnabled` (bool): Whether object is active
- `objectIndestructible` (bool): Cannot be destroyed
- `objectUnsellable` (bool): Cannot be sold
- `uniqueID` (u32): Unique object identifier

### SidesList

Player and team definitions.

**Player properties:**
- `playerName` (ASCII): Internal name (e.g., "Human_Player", "Computer_Player_1")
- `playerDisplayName` (Unicode): Display name
- `playerIsHuman` (bool): Human or AI
- `playerFaction` (ASCII): e.g., "FactionAmerica", "FactionChina", "FactionGLA"
- `playerAllies` (ASCII): Space-separated allied player names
- `playerEnemies` (ASCII): Space-separated enemy player names
- `playerColor` (u32): ARGB color value

**Available factions:**
| Faction | String |
|---------|--------|
| USA | FactionAmerica |
| China | FactionChina |
| GLA | FactionGLA |
| USA Air Force | FactionAmericaAirForceGeneral |
| USA Laser | FactionAmericaLaserGeneral |
| USA Super Weapon | FactionAmericaSuperWeaponGeneral |
| China Nuke | FactionChinaNukeGeneral |
| China Tank | FactionChinaTankGeneral |
| China Infantry | FactionChinaInfantryGeneral |
| GLA Toxin | FactionGLAToxinGeneral |
| GLA Stealth | FactionGLAStealthGeneral |
| GLA Demolition | FactionGLADemolitionGeneral |

### WaypointsList

Named positions for spawns, AI paths, and scripting.

Special waypoint names:
- `Player_1_Start` through `Player_8_Start`: Spawn positions
- `SupplyCenter_N`: Supply depot locations
- Custom names for AI movement paths

### GlobalLighting (version 7)

Lighting settings for each time of day (Morning, Afternoon, Evening, Night).

Per time-of-day:
- Ambient color (3×f32 RGB)
- Sun color (3×f32 RGB)
- Accent1 color (3×f32 RGB)
- Accent2 color (3×f32 RGB)
- Sun direction (3×f32 XYZ vector)

Plus shadow color (4×u8 ARGB).

### PolygonTriggers

Polygonal area triggers for scripting, water zones, etc.

## Property Types

Properties use a type-length-value encoding:

| Type ID | Name | Size |
|---------|------|------|
| 0 | Boolean | 1 byte |
| 1 | UInt32 | 4 bytes |
| 2 | Int32 | 4 bytes |
| 3 | ASCII String | u16 length + bytes |
| 4 | Unicode String | u16 char_count + UTF-16LE bytes |
| 5 | Float32 | 4 bytes |

Property format: `type(u8) + key_index(u16) + value`

## Map File Organization

On disk, maps are stored in folders:
```
Maps/
  MapName/
    MapName.map      ← The binary map file
    MapName.tga      ← Preview thumbnail (required, same name)
```

Installation path:
- `My Documents/Command & Conquer Generals Zero Hour Data/Maps/`

## Map Design Guidelines

### Dimensions
- Maximum recommended for AI: **400×400** heightmap cells
- Minimum base area per player: **1000×1000 feet** (100×100 cells)
- Border width: 10-20 cells (area outside is invisible in-game)

### AI Waypoints (Required for Skirmish)
Maps must include these waypoints for AI to function:
- `Player_N_Start` — Spawn position per player
- `InnerPerimeterN` — Polygon trigger defining buildable base zone
- `OuterPerimeterN` — Polygon trigger for enemy detection
- `CombatZone` — Covers all non-base territory
- `SkirmishWorld` — Encompasses entire playable area
- `CenterN`, `FlankN`, `BackDoorN` — Attack path waypoints per player

### Resource Balance
- Supply piles: max $3,750 each
- Supply docks: max $30,000 each
- Standard: ~2 supply docks per player
- Tech buildings (oil derricks, hospitals) placed **outside bases** as contested objectives
- Civilian bunkers: 1-2 per player area

### Competitive Standards
- Symmetrical resource access for all players
- At least 3 attack paths per player (center, flank, backdoor)
- No faction-specific buildings on neutral map
- Oil derricks rotated -45° for flag visibility

## References

- [OpenSAGE](https://github.com/OpenSAGE/OpenSAGE) - Open-source SAGE engine reimplementation (C#)
- [OpenSAGE Docs](https://opensage.readthedocs.io/) - SAGE format documentation
- [C&C Labs WorldBuilder](https://www.cnclabs.com/maps/generals/worldbuilder/) - Official map editor docs
- [TheSuperHackers/GeneralsRankedMaps](https://github.com/TheSuperHackers/GeneralsRankedMaps) - Community ranked maps

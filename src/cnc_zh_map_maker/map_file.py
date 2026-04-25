"""MapFile: read and write C&C Generals Zero Hour .map files.

Handles both compressed (RefPack/EAR) and uncompressed (CkMp) formats.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from cnc_zh_map_maker import refpack
from cnc_zh_map_maker.binary_io import MapReader, MapWriter
from cnc_zh_map_maker.data_model import (
    BlendTileData,
    BlendTileTexture,
    ColorARGB,
    ColorRGB,
    GlobalLighting,
    HeightMapBorder,
    HeightMapData,
    LightingConfiguration,
    MapObject,
    MapWeatherType,
    MapCompressionType,
    Player,
    PlayerScriptsList,
    PolygonTrigger,
    SidesList,
    Team,
    TimeOfDay,
    Vec3,
    Waypoint,
    WaypointPath,
    WaypointsList,
    WorldInfo,
)


@dataclass
class MapFile:
    """A complete C&C Generals Zero Hour map file."""

    world_info: WorldInfo = field(default_factory=WorldInfo)
    height_map: HeightMapData = field(default_factory=HeightMapData)
    blend_tile_data: BlendTileData = field(default_factory=BlendTileData)
    objects: list[MapObject] = field(default_factory=list)
    waypoints: WaypointsList = field(default_factory=WaypointsList)
    sides: SidesList = field(default_factory=SidesList)
    lighting: GlobalLighting = field(default_factory=GlobalLighting)
    polygon_triggers: list[PolygonTrigger] = field(default_factory=list)
    scripts: PlayerScriptsList = field(default_factory=PlayerScriptsList)

    # Raw data for sections we don't fully parse yet
    _raw_sections: dict[str, bytes] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str | Path) -> MapFile:
        """Load a .map file from disk."""
        data = Path(path).read_bytes()
        return cls.from_bytes(data)

    @classmethod
    def from_bytes(cls, data: bytes) -> MapFile:
        """Parse a .map file from raw bytes."""
        # Decompress if needed
        if refpack.is_refpack_compressed(data):
            data = refpack.decompress(data)

        reader = MapReader(data)
        reader.read_string_dictionary()

        map_file = cls()

        # Parse asset chunks sequentially
        while reader.remaining() >= 10:  # u32 + u16 + u32 minimum
            header = reader.read_asset_header()
            if header is None:
                break

            end_pos = header.data_start + header.data_size

            try:
                if header.asset_name == "HeightMapData":
                    map_file.height_map = _parse_height_map(reader, header)
                elif header.asset_name == "BlendTileData":
                    map_file.blend_tile_data = _parse_blend_tile_data(reader, header)
                elif header.asset_name == "WorldInfo":
                    map_file.world_info = _parse_world_info(reader, header)
                elif header.asset_name == "ObjectsList":
                    map_file.objects = _parse_objects_list(reader, header)
                elif header.asset_name == "WaypointsList":
                    map_file.waypoints = _parse_waypoints_list(reader, header)
                elif header.asset_name == "SidesList":
                    map_file.sides = _parse_sides_list(reader, header)
                elif header.asset_name == "GlobalLighting":
                    map_file.lighting = _parse_global_lighting(reader, header)
                elif header.asset_name == "PolygonTriggers":
                    map_file.polygon_triggers = _parse_polygon_triggers(reader, header)
                elif header.asset_name == "PlayerScriptsList":
                    # Complex - store raw for now
                    reader.seek(header.data_start)
                    map_file._raw_sections[header.asset_name] = reader.read_bytes(header.data_size)
                else:
                    # Store unknown sections as raw bytes
                    reader.seek(header.data_start)
                    map_file._raw_sections[header.asset_name] = reader.read_bytes(header.data_size)
            except Exception as e:
                # On parse error, store raw and continue
                reader.seek(header.data_start)
                raw = reader.read_bytes(max(0, end_pos - reader.tell()))
                map_file._raw_sections[header.asset_name] = raw

            # Ensure we're at the right position for next chunk
            reader.seek(end_pos)

        return map_file

    def to_bytes(self, compress: bool = False) -> bytes:
        """Serialize to .map format bytes."""
        writer = _write_map(self)
        data = writer.get_bytes()
        if compress:
            data = refpack.compress(data)
        return data

    def save(self, path: str | Path, compress: bool = False) -> None:
        """Write to a .map file on disk."""
        data = self.to_bytes(compress=compress)
        Path(path).write_bytes(data)

    def summary(self) -> str:
        """Return a human-readable summary of the map."""
        lines = [
            f"Map: {self.world_info.map_name}",
            f"Weather: {self.world_info.weather.name}",
            f"Heightmap: {self.height_map.width}x{self.height_map.height}",
            f"Textures: {len(self.blend_tile_data.textures)}",
            f"Objects: {len(self.objects)}",
            f"Waypoints: {len(self.waypoints.waypoints)}",
            f"Players: {len(self.sides.players)}",
            f"Teams: {len(self.sides.teams)}",
            f"Polygon triggers: {len(self.polygon_triggers)}",
        ]

        # List player starts
        starts = [w for w in self.waypoints.waypoints if "Start" in w.name]
        if starts:
            lines.append("Player starts:")
            for w in starts:
                lines.append(f"  {w.name}: ({w.position.x:.0f}, {w.position.y:.0f})")

        # List factions
        for p in self.sides.players:
            if p.name and p.faction:
                lines.append(f"  {p.name}: {p.faction} ({'Human' if p.is_human else 'CPU'})")

        return "\n".join(lines)


# ── Parsers ────────────────────────────────────────────────────────────────

def _parse_height_map(reader: MapReader, header) -> HeightMapData:
    hm = HeightMapData()
    hm.width = reader.read_u32()
    hm.height = reader.read_u32()
    hm.border_width = reader.read_u32()

    # Borders
    num_borders = reader.read_u32()
    for _ in range(num_borders):
        border = HeightMapBorder()
        if header.version >= 6:
            border.corner1_x = reader.read_u32()
            border.corner1_y = reader.read_u32()
        border.x = reader.read_u32()
        border.y = reader.read_u32()
        hm.borders.append(border)

    # Area validation
    area = reader.read_u32()

    # Read elevation grid
    hm.elevations = []
    for y in range(hm.height):
        row = []
        for x in range(hm.width):
            if header.version >= 5:
                row.append(reader.read_u16())
            else:
                row.append(reader.read_u8())
        hm.elevations.append(row)

    return hm


def _parse_blend_tile_data(reader: MapReader, header) -> BlendTileData:
    bt = BlendTileData()
    bt.num_tiles = reader.read_u32()

    # Textures
    num_textures = reader.read_u32()
    cell_start = 0
    for _ in range(num_textures):
        tex = BlendTileTexture()
        tex.cell_start = reader.read_u32()
        tex.cell_count = reader.read_u32()
        tex.cell_size = reader.read_u32()
        tex.name = reader.read_ascii_string()
        bt.textures.append(tex)

    # The actual tile data follows - dimensions derived from heightmap
    # Tiles are (width-1) x (height-1) relative to the heightmap
    # We'll read what we can based on num_tiles
    # For now, store position and skip detailed parsing
    return bt


def _parse_world_info(reader: MapReader, header) -> WorldInfo:
    wi = WorldInfo()
    num_properties = reader.read_u16()
    for _ in range(num_properties):
        try:
            key, prop_type, value = reader.read_asset_property()
            if key == "mapName":
                wi.map_name = value
            elif key == "weather":
                wi.weather = MapWeatherType(value) if isinstance(value, int) else MapWeatherType.NORMAL
            elif key == "compression":
                wi.compression = MapCompressionType(value) if isinstance(value, int) else MapCompressionType.NONE
        except Exception:
            break
    return wi


def _parse_objects_list(reader: MapReader, header) -> list[MapObject]:
    objects = []
    num_objects = reader.read_u32()
    for _ in range(num_objects):
        obj = MapObject()
        # Position: 3 floats
        obj.position = Vec3(reader.read_f32(), reader.read_f32(), reader.read_f32())
        # Angle: 1 float
        obj.angle = reader.read_f32()
        # Road type flags
        _road_type = reader.read_u32()
        # Type name
        obj.type_name = reader.read_ascii_string()
        # Properties
        num_props = reader.read_u16()
        for _ in range(num_props):
            try:
                key, prop_type, value = reader.read_asset_property()
                obj.properties[key] = value
                if key == "originalOwner":
                    obj.owner = value
                elif key == "objectInitialHealth":
                    obj.initial_health = value
                elif key == "objectEnabled":
                    obj.is_enabled = value
                elif key == "objectIndestructible":
                    obj.is_indestructible = value
                elif key == "objectUnsellable":
                    obj.is_unsellable = value
                elif key == "objectPowered":
                    obj.is_powered = value
                elif key == "objectTargetable":
                    obj.is_targetable = value
            except Exception:
                break
        objects.append(obj)
    return objects


def _parse_waypoints_list(reader: MapReader, header) -> WaypointsList:
    wl = WaypointsList()
    num_paths = reader.read_u32()
    for _ in range(num_paths):
        # Each path has start/end waypoint IDs and intermediate waypoints
        # But in ZH, it's actually a flat list of waypoints
        pass
    # Alternative parse: read as individual waypoints
    # The actual format stores waypoint paths, each containing waypoint references
    return wl


def _parse_sides_list(reader: MapReader, header) -> SidesList:
    sl = SidesList()
    # SidesList contains nested Player and Team assets
    # For now, do basic parsing
    return sl


def _parse_global_lighting(reader: MapReader, header) -> GlobalLighting:
    gl = GlobalLighting()
    # Lighting has time-of-day configurations
    # Basic parsing
    return gl


def _parse_polygon_triggers(reader: MapReader, header) -> list[PolygonTrigger]:
    triggers = []
    # Basic structure: count + polygon definitions
    return triggers


# ── Writer ─────────────────────────────────────────────────────────────────

# All the standard asset names needed for a ZH map
_STANDARD_ASSET_NAMES = [
    # Top-level sections
    "HeightMapData", "BlendTileData", "WorldInfo", "ObjectsList",
    "WaypointsList", "SidesList", "GlobalLighting", "PolygonTriggers",
    "PlayerScriptsList", "Teams", "BuildLists",
    # WorldInfo properties
    "mapName", "compression", "weather",
    # Object properties
    "originalOwner", "objectLayer", "uniqueID", "objectTargetable",
    "objectRecruitableAI", "objectPowered", "objectUnsellable",
    "objectIndestructible", "objectEnabled", "objectInitialHealth",
    "Object",
    # Player/Side properties
    "playerName", "playerIsHuman", "playerDisplayName", "playerFaction",
    "playerAllies", "playerEnemies", "playerColor",
    # Waypoint properties
    "waypointName", "waypointID",
    # Team properties
    "teamName", "teamOwner", "teamIsSingleton", "teamDescription",
    # Script properties
    "ScriptGroup", "ScriptList", "Script", "ScriptAction", "Condition",
    "OrCondition", "ScriptActionFalse",
    # Script conditions/actions
    "CONDITION_TRUE", "CONDITION_FALSE", "NO_OP", "DEBUG_MESSAGE_BOX",
    "DEBUG_STRING",
    "SKIRMISH_PLAYER_HAS_BEEN_ATTACKED_BY_PLAYER",
    "SKIRMISH_PLAYER_FACTION", "HAS_FINISHED_AUDIO",
    "CAMERA_MOVEMENT_FINISHED", "BRIDGE_BROKEN",
    "SKIRMISH_SUPPLIES_VALUE_WITHIN_DISTANCE", "ENEMY_SIGHTED",
    "PLAYER_HAS_CREDITS", "UNIT_HEALTH",
    "TEAM_SOME_HAVE_OBJECT_STATUS",
    "PLAYER_REPAIR_NAMED_STRUCTURE",
    # Team unit properties
    "teamUnitType1", "teamUnitMinCount1", "teamUnitMaxCount1",
    "teamUnitType2", "teamUnitMinCount2", "teamUnitMaxCount2",
    "teamUnitType3", "teamUnitMinCount3", "teamUnitMaxCount3",
    "teamUnitType4", "teamUnitMinCount4", "teamUnitMaxCount4",
    "teamUnitType5", "teamUnitMinCount5", "teamUnitMaxCount5",
    "teamUnitType6", "teamUnitMinCount6", "teamUnitMaxCount6",
    "teamUnitType7", "teamUnitMinCount7", "teamUnitMaxCount7",
    "teamHome", "teamProductionPriority",
    "teamExecutesActionsOnCreate", "teamMaxInstances",
    "teamProductionPrioritySuccessIncrease",
    "teamProductionPriorityFailureDecrease",
    "teamInitialIdleFrames",
    # Lighting properties
    "lightingMorning", "lightingAfternoon", "lightingEvening", "lightingNight",
    # Path labels
    "PathLabel",
]


def _write_map(map_file: MapFile) -> MapWriter:
    """Serialize a MapFile to binary format."""
    writer = MapWriter()

    # Register all needed asset names
    for name in _STANDARD_ASSET_NAMES:
        writer.register_asset_name(name)

    # Register any additional names from map data
    for tex in map_file.blend_tile_data.textures:
        if tex.name:
            writer.register_asset_name(tex.name)
    for obj in map_file.objects:
        if obj.type_name:
            writer.register_asset_name(obj.type_name)
        if obj.owner:
            writer.register_asset_name(obj.owner)

    # Write string dictionary
    writer.write_string_dictionary()

    # Open the implicit _MapRoot wrapper (asset_index 1). Every working ZH
    # map nests its chunks inside this container — without it the engine
    # rejects the file. The wrapper has no name in the dictionary; we write
    # its header by hand with index=1, version=1.
    writer.write_u32(1)              # _MapRoot asset index
    writer.write_u16(1)              # _MapRoot version
    root_size_pos = writer.stream.tell()
    writer.write_u32(0)              # placeholder for size, patched at end

    # Nested chunks (order matches what the engine emits)
    _write_height_map(writer, map_file.height_map)
    _write_blend_tile_data(writer, map_file.blend_tile_data, map_file.height_map)
    _write_world_info(writer, map_file.world_info)
    _write_sides_list(writer, map_file.sides)
    _write_objects_list(writer, map_file.objects)
    _write_waypoints_list(writer, map_file.waypoints)
    _write_player_scripts(writer, map_file.scripts)
    _write_global_lighting(writer, map_file.lighting)
    _write_polygon_triggers(writer, map_file.polygon_triggers)

    # Any raw sections we round-tripped from a parse we don't fully understand
    for name, data in map_file._raw_sections.items():
        if name in writer.asset_names:
            size_pos = writer.begin_asset(name, 1)
            writer.write_bytes(data)
            writer.end_asset(size_pos)

    # Patch _MapRoot size now that we know how much we've written
    end_pos = writer.stream.tell()
    root_data_size = end_pos - root_size_pos - 4
    writer.stream.seek(root_size_pos)
    writer.write_u32(root_data_size)
    writer.stream.seek(end_pos)

    return writer


def _write_height_map(writer: MapWriter, hm: HeightMapData) -> None:
    size_pos = writer.begin_asset("HeightMapData", 5)

    writer.write_u32(hm.width)
    writer.write_u32(hm.height)
    writer.write_u32(hm.border_width)

    writer.write_u32(len(hm.borders))
    for border in hm.borders:
        writer.write_u32(border.x)
        writer.write_u32(border.y)

    writer.write_u32(hm.area)

    for y in range(hm.height):
        for x in range(hm.width):
            writer.write_u16(hm.elevations[y][x])

    writer.end_asset(size_pos)


def _write_blend_tile_data(writer: MapWriter, bt: BlendTileData, hm: HeightMapData) -> None:
    size_pos = writer.begin_asset("BlendTileData", 14)

    writer.write_u32(bt.num_tiles)

    # Textures
    writer.write_u32(len(bt.textures))
    for tex in bt.textures:
        writer.write_u32(tex.cell_start)
        writer.write_u32(tex.cell_count)
        writer.write_u32(tex.cell_size)
        writer.write_ascii_string(tex.name)

    # Tile data - dimensions are (heightmap_width - 1) x (heightmap_height - 1)
    tile_w = max(0, hm.width - 1)
    tile_h = max(0, hm.height - 1)

    # Base tiles
    for y in range(tile_h):
        for x in range(tile_w):
            if y < len(bt.tiles) and x < len(bt.tiles[y]):
                writer.write_u16(bt.tiles[y][x])
            else:
                writer.write_u16(0)

    # Blends
    for y in range(tile_h):
        for x in range(tile_w):
            if y < len(bt.blends) and x < len(bt.blends[y]):
                writer.write_u32(bt.blends[y][x])
            else:
                writer.write_u32(0)

    # Three-way blends
    for y in range(tile_h):
        for x in range(tile_w):
            if y < len(bt.three_way_blends) and x < len(bt.three_way_blends[y]):
                writer.write_u32(bt.three_way_blends[y][x])
            else:
                writer.write_u32(0)

    # Cliff textures
    for y in range(tile_h):
        for x in range(tile_w):
            if y < len(bt.cliff_textures) and x < len(bt.cliff_textures[y]):
                writer.write_u32(bt.cliff_textures[y][x])
            else:
                writer.write_u32(0)

    # Passability flags (packed as single-bit boolean arrays)
    _write_bool_grid(writer, bt.impassable, tile_w, tile_h)
    _write_bool_grid(writer, bt.impassable_to_players, tile_w, tile_h)
    _write_bool_grid(writer, bt.impassable_to_air, tile_w, tile_h)
    _write_bool_grid(writer, bt.extra_passable, tile_w, tile_h)

    writer.end_asset(size_pos)


def _write_bool_grid(writer: MapWriter, grid: list[list[bool]], w: int, h: int) -> None:
    """Write a 2D boolean array as a packed bit array."""
    bits = bytearray()
    current_byte = 0
    bit_pos = 0

    for y in range(h):
        for x in range(w):
            val = grid[y][x] if (y < len(grid) and x < len(grid[y])) else False
            if val:
                current_byte |= (1 << bit_pos)
            bit_pos += 1
            if bit_pos == 8:
                bits.append(current_byte)
                current_byte = 0
                bit_pos = 0

    if bit_pos > 0:
        bits.append(current_byte)

    writer.write_u32(len(bits))
    writer.write_bytes(bytes(bits))


def _write_world_info(writer: MapWriter, wi: WorldInfo) -> None:
    size_pos = writer.begin_asset("WorldInfo", 1)

    # Count properties
    num_props = 3  # mapName, weather, compression
    writer.write_u16(num_props)

    writer.write_property_ascii("mapName", wi.map_name)
    writer.write_property_u32("weather", wi.weather.value)
    writer.write_property_u32("compression", wi.compression.value)

    writer.end_asset(size_pos)


def _write_sides_list(writer: MapWriter, sides: SidesList) -> None:
    size_pos = writer.begin_asset("SidesList", 1)

    # Write players
    writer.write_u32(len(sides.players))
    for player in sides.players:
        num_props = 7
        writer.write_u16(num_props)

        writer.write_property_ascii("playerName", player.name)
        writer.write_property_bool("playerIsHuman", player.is_human)
        writer.write_property_unicode("playerDisplayName", player.display_name)
        writer.write_property_ascii("playerFaction", player.faction)
        writer.write_property_ascii("playerAllies", player.allies)
        writer.write_property_ascii("playerEnemies", player.enemies)
        writer.write_property_u32("playerColor", player.color)

    # Write teams
    writer.write_u32(len(sides.teams))
    for team in sides.teams:
        num_props = 4
        writer.write_u16(num_props)

        writer.write_property_ascii("teamName", team.name)
        writer.write_property_ascii("teamOwner", team.owner)
        writer.write_property_bool("teamIsSingleton", team.is_singleton)
        writer.write_property_ascii("teamDescription", team.description)

    writer.end_asset(size_pos)


def _write_objects_list(writer: MapWriter, objects: list[MapObject]) -> None:
    size_pos = writer.begin_asset("ObjectsList", 1)

    writer.write_u32(len(objects))
    for obj in objects:
        # Position
        writer.write_f32(obj.position.x)
        writer.write_f32(obj.position.y)
        writer.write_f32(obj.position.z)
        # Angle
        writer.write_f32(obj.angle)
        # Road type
        writer.write_u32(0)
        # Type name
        writer.write_ascii_string(obj.type_name)
        # Properties
        prop_count = 1  # At least originalOwner
        if obj.initial_health != 100.0:
            prop_count += 1
        if not obj.is_enabled:
            prop_count += 1

        writer.write_u16(prop_count)
        writer.write_property_ascii("originalOwner", obj.owner or "")

        if obj.initial_health != 100.0:
            writer.write_property_f32("objectInitialHealth", obj.initial_health)
        if not obj.is_enabled:
            writer.write_property_bool("objectEnabled", obj.is_enabled)

    writer.end_asset(size_pos)


def _write_waypoints_list(writer: MapWriter, wl: WaypointsList) -> None:
    size_pos = writer.begin_asset("WaypointsList", 1)

    writer.write_u32(len(wl.paths))
    # Write waypoint paths (connections)
    for path in wl.paths:
        writer.write_u32(path.start_waypoint_id)
        writer.write_u32(path.end_waypoint_id)

    # Write individual waypoints
    writer.write_u32(len(wl.waypoints))
    for wp in wl.waypoints:
        num_props = 2
        writer.write_u16(num_props)
        writer.write_property_ascii("waypointName", wp.name)
        writer.write_property_u32("waypointID", wp.id)
        # Position
        writer.write_f32(wp.position.x)
        writer.write_f32(wp.position.y)
        writer.write_f32(wp.position.z)

    writer.end_asset(size_pos)


def _write_global_lighting(writer: MapWriter, gl: GlobalLighting) -> None:
    size_pos = writer.begin_asset("GlobalLighting", 7)

    writer.write_u32(gl.time.value)

    # Write lighting configs for each time of day
    for tod in TimeOfDay:
        config = gl.configurations.get(tod, LightingConfiguration())
        # Ambient
        writer.write_f32(config.ambient.r)
        writer.write_f32(config.ambient.g)
        writer.write_f32(config.ambient.b)
        # Sun color
        writer.write_f32(config.sun_color.r)
        writer.write_f32(config.sun_color.g)
        writer.write_f32(config.sun_color.b)
        # Accent 1
        writer.write_f32(config.accent1_color.r)
        writer.write_f32(config.accent1_color.g)
        writer.write_f32(config.accent1_color.b)
        # Accent 2
        writer.write_f32(config.accent2_color.r)
        writer.write_f32(config.accent2_color.g)
        writer.write_f32(config.accent2_color.b)
        # Sun direction
        writer.write_f32(config.sun_direction.x)
        writer.write_f32(config.sun_direction.y)
        writer.write_f32(config.sun_direction.z)

    # Shadow color
    writer.write_u8(gl.shadow_color.a)
    writer.write_u8(gl.shadow_color.r)
    writer.write_u8(gl.shadow_color.g)
    writer.write_u8(gl.shadow_color.b)

    writer.end_asset(size_pos)


def _write_player_scripts(writer: MapWriter, scripts) -> None:
    """Write a minimal PlayerScriptsList chunk.

    Real ZH skirmish maps always include this chunk. The engine uses it for
    AI behaviour. An empty PlayerScriptsList (with one empty ScriptList per
    player slot) is enough to satisfy the loader and let the default skirmish
    AI take over for computer players. We write the simplest valid form:
    the PlayerScriptsList chunk header followed by a single nested ScriptList
    chunk with zero ScriptGroups.
    """
    size_pos = writer.begin_asset("PlayerScriptsList", 1)

    # One nested ScriptList chunk — empty (0 script groups, 0 scripts)
    sl_size_pos = writer.begin_asset("ScriptList", 1)
    writer.write_u32(0)   # ScriptGroup count
    writer.write_u32(0)   # Script count (top-level scripts directly in the list)
    writer.end_asset(sl_size_pos)

    writer.end_asset(size_pos)


def _write_polygon_triggers(writer: MapWriter, triggers: list[PolygonTrigger]) -> None:
    size_pos = writer.begin_asset("PolygonTriggers", 1)

    writer.write_u32(len(triggers))
    for trigger in triggers:
        writer.write_ascii_string(trigger.name)
        writer.write_ascii_string(trigger.layer)
        writer.write_u32(trigger.id)
        writer.write_u32(len(trigger.points))
        for px, py in trigger.points:
            writer.write_f32(px)
            writer.write_f32(py)
        writer.write_u8(1 if trigger.is_water else 0)
        writer.write_u8(1 if trigger.is_river else 0)

    writer.end_asset(size_pos)

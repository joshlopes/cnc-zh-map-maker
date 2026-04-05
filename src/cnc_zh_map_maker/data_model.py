"""Data model for C&C Generals Zero Hour map files.

Defines all the structured data types that represent map content.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


# ── Enums ──────────────────────────────────────────────────────────────────

class MapWeatherType(enum.IntEnum):
    NORMAL = 1
    SNOWY = 2


class MapCompressionType(enum.IntEnum):
    NONE = 0
    REFPACK = 1


class TimeOfDay(enum.IntEnum):
    MORNING = 1
    AFTERNOON = 2
    EVENING = 3
    NIGHT = 4


class Flammability(enum.IntEnum):
    FIRE_RESISTANT = 0
    GRASS = 1
    HIGHLY_FLAMMABLE = 2
    UNDEFINED = 3


class Faction(str, enum.Enum):
    """Zero Hour factions."""
    USA = "FactionAmerica"
    CHINA = "FactionChina"
    GLA = "FactionGLA"
    # Generals subfactions
    USA_AIR_FORCE = "FactionAmericaAirForceGeneral"
    USA_LASER = "FactionAmericaLaserGeneral"
    USA_SUPER_WEAPON = "FactionAmericaSuperWeaponGeneral"
    CHINA_NUKE = "FactionChinaNukeGeneral"
    CHINA_TANK = "FactionChinaTankGeneral"
    CHINA_INFANTRY = "FactionChinaInfantryGeneral"
    GLA_TOXIN = "FactionGLAToxinGeneral"
    GLA_STEALTH = "FactionGLAStealthGeneral"
    GLA_DEMOLITION = "FactionGLADemolitionGeneral"
    CIVILIAN = "FactionCivilian"
    OBSERVER = "FactionObserver"


# ── WorldInfo ──────────────────────────────────────────────────────────────

@dataclass
class WorldInfo:
    """Map metadata."""
    map_name: str = ""
    weather: MapWeatherType = MapWeatherType.NORMAL
    compression: MapCompressionType = MapCompressionType.NONE


# ── HeightMap ──────────────────────────────────────────────────────────────

@dataclass
class HeightMapBorder:
    """Border corner definition."""
    x: int = 0
    y: int = 0
    corner1_x: int = 0  # v6+
    corner1_y: int = 0  # v6+


@dataclass
class HeightMapData:
    """Terrain elevation grid.

    Elevations are u16 values scaled by ELEVATION_SCALE (0.0390625)
    to get world-space heights. A value of 0x10 (16) is water level.
    Max value 65535 = 2560 world units.
    """
    ELEVATION_SCALE = 0.0390625  # 1/25.6

    width: int = 0
    height: int = 0
    border_width: int = 0
    borders: list[HeightMapBorder] = field(default_factory=list)
    elevations: list[list[int]] = field(default_factory=list)  # [y][x] of u16

    @property
    def area(self) -> int:
        return self.width * self.height

    def get_elevation(self, x: int, y: int) -> float:
        """Get world-space elevation at grid position."""
        return self.elevations[y][x] * self.ELEVATION_SCALE

    def set_elevation(self, x: int, y: int, world_height: float) -> None:
        """Set elevation from world-space height."""
        self.elevations[y][x] = max(0, min(65535, int(world_height / self.ELEVATION_SCALE)))


# ── BlendTileData ──────────────────────────────────────────────────────────

@dataclass
class BlendTileTexture:
    """A terrain texture definition."""
    cell_start: int = 0
    cell_count: int = 0
    cell_size: int = 0
    name: str = ""


@dataclass
class BlendTileData:
    """Terrain texture and passability data."""
    num_tiles: int = 0
    textures: list[BlendTileTexture] = field(default_factory=list)
    tiles: list[list[int]] = field(default_factory=list)  # [y][x] base texture indices
    blends: list[list[int]] = field(default_factory=list)  # [y][x] blend values
    three_way_blends: list[list[int]] = field(default_factory=list)
    cliff_textures: list[list[int]] = field(default_factory=list)
    impassable: list[list[bool]] = field(default_factory=list)
    impassable_to_players: list[list[bool]] = field(default_factory=list)
    impassable_to_air: list[list[bool]] = field(default_factory=list)
    buildable: list[list[bool]] = field(default_factory=list)
    flammability: list[list[Flammability]] = field(default_factory=list)
    extra_passable: list[list[bool]] = field(default_factory=list)


# ── Objects ────────────────────────────────────────────────────────────────

@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class MapObject:
    """A placed object on the map (building, unit, tree, prop, etc.)."""
    position: Vec3 = field(default_factory=Vec3)
    angle: float = 0.0  # Radians
    type_name: str = ""
    owner: str = ""  # Player name or empty for neutral
    properties: dict[str, object] = field(default_factory=dict)
    # Common properties from the Properties collection:
    is_targetable: bool = True
    is_enabled: bool = True
    initial_health: float = 100.0
    is_indestructible: bool = False
    is_unsellable: bool = False
    is_powered: bool = True


# ── Waypoints ──────────────────────────────────────────────────────────────

@dataclass
class Waypoint:
    """A named position on the map.

    Special waypoint names:
    - "Player_1_Start" through "Player_8_Start": spawn positions
    - "SupplyCenter_N": supply dock locations
    - Named paths for AI movement
    """
    name: str = ""
    position: Vec3 = field(default_factory=Vec3)
    id: int = 0


@dataclass
class WaypointPath:
    """A connection between waypoints for pathfinding."""
    start_waypoint_id: int = 0
    end_waypoint_id: int = 0


@dataclass
class WaypointsList:
    waypoints: list[Waypoint] = field(default_factory=list)
    paths: list[WaypointPath] = field(default_factory=list)


# ── Players / Sides ───────────────────────────────────────────────────────

@dataclass
class Player:
    """A player definition in the map."""
    name: str = ""
    display_name: str = ""
    is_human: bool = False
    faction: str = ""
    allies: str = ""  # Space-separated player names
    enemies: str = ""  # Space-separated player names
    color: int = 0  # ARGB packed
    is_skirmish: bool = True


@dataclass
class Team:
    """An AI team definition."""
    name: str = ""
    owner: str = ""
    is_singleton: bool = False
    description: str = ""


@dataclass
class SidesList:
    """All player and team definitions."""
    players: list[Player] = field(default_factory=list)
    teams: list[Team] = field(default_factory=list)


# ── Lighting ──────────────────────────────────────────────────────────────

@dataclass
class ColorRGB:
    r: float = 1.0
    g: float = 1.0
    b: float = 1.0


@dataclass
class ColorARGB:
    a: int = 255
    r: int = 0
    g: int = 0
    b: int = 0


@dataclass
class LightingConfiguration:
    """Lighting settings for a time of day."""
    ambient: ColorRGB = field(default_factory=ColorRGB)
    sun_color: ColorRGB = field(default_factory=ColorRGB)
    accent1_color: ColorRGB = field(default_factory=ColorRGB)
    accent2_color: ColorRGB = field(default_factory=ColorRGB)
    sun_direction: Vec3 = field(default_factory=lambda: Vec3(0.5, 0.5, -0.7))


@dataclass
class GlobalLighting:
    """Map lighting settings across all times of day."""
    time: TimeOfDay = TimeOfDay.AFTERNOON
    configurations: dict[TimeOfDay, LightingConfiguration] = field(default_factory=dict)
    shadow_color: ColorARGB = field(default_factory=lambda: ColorARGB(128, 0, 0, 0))


# ── Polygon Triggers ──────────────────────────────────────────────────────

@dataclass
class PolygonTrigger:
    """A polygonal area trigger on the map."""
    name: str = ""
    layer: str = ""
    id: int = 0
    points: list[tuple[float, float]] = field(default_factory=list)  # (x, y) pairs
    is_water: bool = False
    is_river: bool = False


# ── Scripts ────────────────────────────────────────────────────────────────

@dataclass
class ScriptCondition:
    condition_type: str = "CONDITION_TRUE"
    parameters: list[object] = field(default_factory=list)


@dataclass
class ScriptAction:
    action_type: str = "NO_OP"
    parameters: list[object] = field(default_factory=list)


@dataclass
class Script:
    name: str = ""
    is_active: bool = True
    is_subroutine: bool = False
    deactivate_upon_success: bool = False
    conditions: list[ScriptCondition] = field(default_factory=list)
    actions: list[ScriptAction] = field(default_factory=list)
    false_actions: list[ScriptAction] = field(default_factory=list)


@dataclass
class ScriptGroup:
    name: str = ""
    is_active: bool = True
    is_subroutine: bool = False
    scripts: list[Script] = field(default_factory=list)


@dataclass
class PlayerScriptsList:
    script_groups: list[ScriptGroup] = field(default_factory=list)

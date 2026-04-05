"""High-level map builder API for creating C&C Generals Zero Hour maps.

Usage:
    builder = MapBuilder("My Desert Map", size=MapSize.LARGE_4P)
    builder.set_terrain("AsphaltType1")
    builder.add_hill(center=(200, 200), radius=50, height=30.0)
    builder.add_player_start(1, (100, 100))
    builder.add_player_start(2, (300, 300))
    builder.add_supply_dock(1, (120, 100))
    builder.add_supply_dock(2, (280, 300))
    builder.add_object("CivBuilding_SmallHouse", (200, 150))
    map_file = builder.build()
    map_file.save("maps/My Desert Map/My Desert Map.map")
"""

from __future__ import annotations

import enum
import math
import random
from dataclasses import dataclass
from pathlib import Path

from cnc_zh_map_maker.data_model import (
    BlendTileData,
    BlendTileTexture,
    ColorARGB,
    ColorRGB,
    Faction,
    GlobalLighting,
    HeightMapBorder,
    HeightMapData,
    LightingConfiguration,
    MapCompressionType,
    MapObject,
    MapWeatherType,
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
from cnc_zh_map_maker.map_file import MapFile


class MapSize(enum.Enum):
    """Standard map sizes (width x height in heightmap cells)."""
    TINY_2P = (100, 100)       # ~Small 1v1
    SMALL_2P = (150, 150)      # Standard 1v1
    MEDIUM_2P = (200, 200)     # Large 1v1
    MEDIUM_4P = (250, 250)     # Standard 2v2
    LARGE_4P = (300, 300)      # Large 2v2
    LARGE_8P = (400, 400)      # Standard 4v4
    HUGE_8P = (500, 500)       # Large 4v4


class TerrainPreset(str, enum.Enum):
    """Common terrain texture presets."""
    DESERT = "AsphaltType1"
    GRASS = "GrassType1"
    SNOW = "SnowType1"
    DIRT = "CliffType2"
    URBAN = "AsphaltType2"
    SAND = "SandType1"
    ROCK = "RockType1"
    MUD = "MudType1"


class LightingPreset(enum.Enum):
    """Pre-configured lighting setups."""
    DESERT_AFTERNOON = "desert_afternoon"
    FOREST_MORNING = "forest_morning"
    URBAN_NIGHT = "urban_night"
    SNOW_OVERCAST = "snow_overcast"
    DEFAULT = "default"


# Player colors (ARGB)
PLAYER_COLORS = [
    0xFF0000FF,  # Blue
    0xFFFF0000,  # Red
    0xFF00FF00,  # Green
    0xFFFFFF00,  # Yellow
    0xFF00FFFF,  # Cyan
    0xFFFF00FF,  # Magenta
    0xFFFF8000,  # Orange
    0xFF8000FF,  # Purple
]


# Common Zero Hour objects by category
OBJECTS = {
    # Civilian buildings
    "civilian": [
        "CivBuilding_SmallHouse",
        "CivBuilding_BigHouse",
        "CivBuilding_ApartmentComplex",
        "CivBuilding_Warehouse",
        "CivBuilding_Church",
        "CivBuilding_GasStation",
        "CivBuilding_Hospital",
    ],
    # Trees and vegetation
    "trees": [
        "GenericTree01",
        "GenericTree02",
        "GenericTree03",
        "TreeDesert01",
        "TreeDesert02",
        "TreeTropical01",
        "TreeSnow01",
        "Bush01",
        "Bush02",
    ],
    # Props and decoration
    "props": [
        "Barrel01",
        "Crate01",
        "BarricadeMetal",
        "BarricadeConcrete",
        "LampPost01",
        "Billboard01",
        "FencePost01",
        "FenceSection01",
        "ElectricalTower",
        "PowerLine01",
    ],
    # Neutral structures (garrisonable)
    "garrisonable": [
        "TechBuilding_CommandCenter",
        "TechBuilding_Hospital",
        "TechBuilding_Prison",
    ],
    # Rocks and terrain features
    "rocks": [
        "Rock01",
        "Rock02",
        "Rock03",
        "Boulder01",
        "Boulder02",
    ],
    # Supply-related
    "supply": [
        "SupplyDock",
        "SupplyWarehouse",
    ],
    # Tech buildings
    "tech": [
        "TechOilDerrick",
        "TechOilRefinery",
        "TechArtilleryPlatform",
        "TechHospital",
    ],
}


@dataclass
class _PendingHill:
    center: tuple[float, float]
    radius: float
    height: float
    falloff: float = 1.0  # 1.0 = linear, 2.0 = smooth


@dataclass
class _PendingCliff:
    start: tuple[float, float]
    end: tuple[float, float]
    height: float
    width: float


@dataclass
class _PendingValley:
    center: tuple[float, float]
    radius: float
    depth: float
    falloff: float = 1.0


class MapBuilder:
    """Fluent builder for creating Zero Hour maps."""

    def __init__(
        self,
        name: str,
        size: MapSize | tuple[int, int] = MapSize.SMALL_2P,
        weather: MapWeatherType = MapWeatherType.NORMAL,
    ):
        self.name = name
        self.weather = weather

        if isinstance(size, MapSize):
            self._width, self._height = size.value
        else:
            self._width, self._height = size

        self._base_elevation: int = 400  # Default flat elevation (~15.6 world units)
        self._base_terrain = TerrainPreset.DESERT.value
        self._additional_terrains: list[str] = []
        self._hills: list[_PendingHill] = []
        self._valleys: list[_PendingValley] = []
        self._cliffs: list[_PendingCliff] = []
        self._objects: list[MapObject] = []
        self._waypoints: list[Waypoint] = []
        self._waypoint_paths: list[WaypointPath] = []
        self._players: list[Player] = []
        self._teams: list[Team] = []
        self._polygon_triggers: list[PolygonTrigger] = []
        self._lighting_preset = LightingPreset.DEFAULT
        self._custom_lighting: GlobalLighting | None = None
        self._next_waypoint_id = 0
        self._next_object_uid = 1

    # ── Terrain ────────────────────────────────────────────────────────

    def set_base_elevation(self, world_height: float) -> MapBuilder:
        """Set the base flat elevation in world units."""
        self._base_elevation = int(world_height / HeightMapData.ELEVATION_SCALE)
        return self

    def set_terrain(self, terrain: str | TerrainPreset) -> MapBuilder:
        """Set the base terrain texture."""
        self._base_terrain = terrain.value if isinstance(terrain, TerrainPreset) else terrain
        return self

    def add_terrain(self, terrain: str | TerrainPreset) -> MapBuilder:
        """Add an additional terrain texture for blending."""
        name = terrain.value if isinstance(terrain, TerrainPreset) else terrain
        if name not in self._additional_terrains:
            self._additional_terrains.append(name)
        return self

    # ── Topology ───────────────────────────────────────────────────────

    def add_hill(
        self,
        center: tuple[float, float],
        radius: float,
        height: float,
        falloff: float = 2.0,
    ) -> MapBuilder:
        """Add a hill to the terrain.

        Args:
            center: (x, y) position in grid coordinates
            radius: Radius of the hill in grid cells
            height: Height in world units (added to base elevation)
            falloff: Smoothness (1.0=linear cone, 2.0=smooth, 3.0=very smooth)
        """
        self._hills.append(_PendingHill(center, radius, height, falloff))
        return self

    def add_valley(
        self,
        center: tuple[float, float],
        radius: float,
        depth: float,
        falloff: float = 2.0,
    ) -> MapBuilder:
        """Add a valley/depression to the terrain."""
        self._valleys.append(_PendingValley(center, radius, depth, falloff))
        return self

    def add_cliff(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        height: float,
        width: float = 5.0,
    ) -> MapBuilder:
        """Add a cliff/ridge along a line."""
        self._cliffs.append(_PendingCliff(start, end, height, width))
        return self

    def add_plateau(
        self,
        center: tuple[float, float],
        radius: float,
        height: float,
        edge_width: float = 10.0,
    ) -> MapBuilder:
        """Add a flat-topped plateau."""
        # Implemented as a very steep hill with flat top
        self._hills.append(_PendingHill(center, radius, height, 0.3))
        return self

    # ── Objects ─────────────────────────────────────────────────────────

    def add_object(
        self,
        type_name: str,
        position: tuple[float, float],
        angle: float = 0.0,
        owner: str = "",
        z: float | None = None,
    ) -> MapBuilder:
        """Place an object on the map.

        Args:
            type_name: Object type (e.g. "CivBuilding_SmallHouse")
            position: (x, y) in world coordinates
            angle: Rotation in degrees (converted to radians internally)
            owner: Player name or "" for neutral/civilian
            z: Z coordinate, or None to auto-calculate from heightmap
        """
        obj = MapObject(
            position=Vec3(position[0], position[1], z or 0.0),
            angle=math.radians(angle),
            type_name=type_name,
            owner=owner,
        )
        obj.properties["uniqueID"] = self._next_object_uid
        self._next_object_uid += 1
        self._objects.append(obj)
        return self

    def add_trees(
        self,
        area: tuple[float, float, float, float],
        count: int = 20,
        tree_types: list[str] | None = None,
        seed: int | None = None,
    ) -> MapBuilder:
        """Scatter trees randomly in an area.

        Args:
            area: (x1, y1, x2, y2) bounding rectangle
            count: Number of trees
            tree_types: List of tree type names, or None for defaults
            seed: Random seed for reproducibility
        """
        rng = random.Random(seed)
        types = tree_types or OBJECTS["trees"]
        x1, y1, x2, y2 = area

        for _ in range(count):
            x = rng.uniform(x1, x2)
            y = rng.uniform(y1, y2)
            angle = rng.uniform(0, 360)
            tree_type = rng.choice(types)
            self.add_object(tree_type, (x, y), angle=angle)

        return self

    def add_rocks(
        self,
        area: tuple[float, float, float, float],
        count: int = 10,
        seed: int | None = None,
    ) -> MapBuilder:
        """Scatter rocks randomly in an area."""
        rng = random.Random(seed)
        types = OBJECTS["rocks"]
        x1, y1, x2, y2 = area

        for _ in range(count):
            x = rng.uniform(x1, x2)
            y = rng.uniform(y1, y2)
            self.add_object(rng.choice(types), (x, y), angle=rng.uniform(0, 360))

        return self

    def add_civilian_buildings(
        self,
        area: tuple[float, float, float, float],
        count: int = 5,
        seed: int | None = None,
    ) -> MapBuilder:
        """Place civilian buildings in an area."""
        rng = random.Random(seed)
        types = OBJECTS["civilian"]
        x1, y1, x2, y2 = area

        for _ in range(count):
            x = rng.uniform(x1, x2)
            y = rng.uniform(y1, y2)
            angle = rng.choice([0, 90, 180, 270])
            self.add_object(rng.choice(types), (x, y), angle=angle)

        return self

    # ── Players & Spawns ───────────────────────────────────────────────

    def add_player_start(
        self,
        player_number: int,
        position: tuple[float, float],
        faction: str | Faction = "",
    ) -> MapBuilder:
        """Add a player starting position.

        Args:
            player_number: 1-8
            position: (x, y) in world coordinates
            faction: Default faction or "" for any
        """
        wp_name = f"Player_{player_number}_Start"
        wp = Waypoint(
            name=wp_name,
            position=Vec3(position[0], position[1], 0.0),
            id=self._next_waypoint_id,
        )
        self._next_waypoint_id += 1
        self._waypoints.append(wp)

        # Create the player definition
        faction_str = faction.value if isinstance(faction, Faction) else faction
        color = PLAYER_COLORS[(player_number - 1) % len(PLAYER_COLORS)]

        player = Player(
            name=f"Human_Player" if player_number == 1 else f"Computer_Player_{player_number - 1}",
            display_name=f"Player {player_number}",
            is_human=(player_number == 1),
            faction=faction_str,
            color=color,
            is_skirmish=True,
        )
        self._players.append(player)

        # Add basic team
        team = Team(
            name=f"team{player.name}",
            owner=player.name,
        )
        self._teams.append(team)

        return self

    def add_skirmish_players(
        self,
        num_players: int,
        positions: list[tuple[float, float]],
        with_ai_waypoints: bool = True,
    ) -> MapBuilder:
        """Add multiple skirmish player starts at once.

        Automatically sets up the Neutral player, all player slots,
        and optionally AI-required waypoints (combat zone, perimeters, attack paths).
        """
        if len(positions) < num_players:
            raise ValueError(f"Need {num_players} positions, got {len(positions)}")

        for i in range(num_players):
            self.add_player_start(i + 1, positions[i])

        if with_ai_waypoints:
            self._add_ai_waypoints(num_players, positions)

        return self

    def _add_ai_waypoints(
        self,
        num_players: int,
        positions: list[tuple[float, float]],
    ) -> None:
        """Add AI-required waypoints for skirmish maps.

        Creates: CombatZone, SkirmishWorld polygon triggers,
        InnerPerimeter/OuterPerimeter per player, and attack path waypoints.
        """
        cx, cy = self._width / 2, self._height / 2

        # SkirmishWorld polygon trigger (entire map)
        margin = 5
        self._polygon_triggers.append(PolygonTrigger(
            name="SkirmishWorld",
            id=len(self._polygon_triggers) + 1,
            points=[
                (margin, margin),
                (self._width - margin, margin),
                (self._width - margin, self._height - margin),
                (margin, self._height - margin),
            ],
        ))

        # CombatZone (playable area minus borders)
        border = self._width // 10
        self._polygon_triggers.append(PolygonTrigger(
            name="CombatZone",
            id=len(self._polygon_triggers) + 1,
            points=[
                (border, border),
                (self._width - border, border),
                (self._width - border, self._height - border),
                (border, self._height - border),
            ],
        ))

        # Per-player perimeters and attack paths
        base_radius = self._width // 8
        for i, pos in enumerate(positions[:num_players]):
            player_num = i + 1
            px, py = pos

            # Inner perimeter (base building zone)
            self._polygon_triggers.append(PolygonTrigger(
                name=f"InnerPerimeter{player_num}",
                id=len(self._polygon_triggers) + 1,
                points=[
                    (px - base_radius, py - base_radius),
                    (px + base_radius, py - base_radius),
                    (px + base_radius, py + base_radius),
                    (px - base_radius, py + base_radius),
                ],
            ))

            # Outer perimeter (enemy detection zone)
            outer = base_radius * 2
            self._polygon_triggers.append(PolygonTrigger(
                name=f"OuterPerimeter{player_num}",
                id=len(self._polygon_triggers) + 1,
                points=[
                    (px - outer, py - outer),
                    (px + outer, py - outer),
                    (px + outer, py + outer),
                    (px - outer, py + outer),
                ],
            ))

            # Attack path waypoints toward center
            self.add_waypoint(f"Center{player_num}", (cx, cy))
            # Flank: 90 degrees offset from center direction
            dx, dy = cx - px, cy - py
            self.add_waypoint(f"Flank{player_num}", (cx + dy * 0.3, cy - dx * 0.3))
            self.add_waypoint(f"BackDoor{player_num}", (cx - dy * 0.3, cy + dx * 0.3))

    # ── Supply ─────────────────────────────────────────────────────────

    def add_supply_dock(
        self,
        player_number: int,
        position: tuple[float, float],
        supplies: int = 40000,
    ) -> MapBuilder:
        """Add a supply dock near a player start."""
        self.add_object(
            "SupplyDock",
            position,
            owner="",  # Neutral
        )
        return self

    def add_tech_building(
        self,
        type_name: str,
        position: tuple[float, float],
        angle: float = 0.0,
    ) -> MapBuilder:
        """Add a tech building (oil derrick, hospital, etc.)."""
        self.add_object(type_name, position, angle=angle)
        return self

    # ── Waypoints ──────────────────────────────────────────────────────

    def add_waypoint(
        self,
        name: str,
        position: tuple[float, float],
    ) -> int:
        """Add a named waypoint. Returns the waypoint ID."""
        wp = Waypoint(
            name=name,
            position=Vec3(position[0], position[1], 0.0),
            id=self._next_waypoint_id,
        )
        self._next_waypoint_id += 1
        self._waypoints.append(wp)
        return wp.id

    # ── Lighting ───────────────────────────────────────────────────────

    def set_lighting(self, preset: LightingPreset) -> MapBuilder:
        """Set lighting from a preset."""
        self._lighting_preset = preset
        return self

    def set_custom_lighting(self, lighting: GlobalLighting) -> MapBuilder:
        """Set fully custom lighting."""
        self._custom_lighting = lighting
        return self

    # ── Build ──────────────────────────────────────────────────────────

    def build(self) -> MapFile:
        """Build the final MapFile from all configured settings."""
        mf = MapFile()

        # WorldInfo
        mf.world_info = WorldInfo(
            map_name=self.name,
            weather=self.weather,
            compression=MapCompressionType.NONE,
        )

        # HeightMap
        mf.height_map = self._build_heightmap()

        # BlendTileData
        mf.blend_tile_data = self._build_blend_tiles()

        # Objects
        mf.objects = self._objects

        # Resolve Z coordinates from heightmap
        for obj in mf.objects:
            if obj.position.z == 0.0:
                gx = int(obj.position.x)
                gy = int(obj.position.y)
                gx = max(0, min(gx, mf.height_map.width - 1))
                gy = max(0, min(gy, mf.height_map.height - 1))
                obj.position.z = mf.height_map.get_elevation(gx, gy)

        # Waypoints
        mf.waypoints = WaypointsList(
            waypoints=self._waypoints,
            paths=self._waypoint_paths,
        )

        # Resolve waypoint Z from heightmap
        for wp in mf.waypoints.waypoints:
            if wp.position.z == 0.0:
                gx = int(wp.position.x)
                gy = int(wp.position.y)
                gx = max(0, min(gx, mf.height_map.width - 1))
                gy = max(0, min(gy, mf.height_map.height - 1))
                wp.position.z = mf.height_map.get_elevation(gx, gy)

        # Players
        # Always add Neutral player first
        neutral = Player(
            name="",
            display_name="Neutral",
            is_human=False,
            faction="FactionCivilian",
            color=0xFF808080,
        )
        mf.sides = SidesList(
            players=[neutral] + self._players,
            teams=self._teams,
        )

        # Lighting
        mf.lighting = self._build_lighting()

        # Polygon triggers
        mf.polygon_triggers = self._polygon_triggers

        # Scripts (empty for skirmish maps)
        mf.scripts = PlayerScriptsList()

        return mf

    def build_and_save(
        self,
        output_dir: str | Path | None = None,
        compress: bool = False,
    ) -> Path:
        """Build and save to the standard map folder structure.

        Creates: <output_dir>/<name>/<name>.map
        """
        mf = self.build()

        if output_dir is None:
            output_dir = Path(".")

        map_dir = Path(output_dir) / self.name
        map_dir.mkdir(parents=True, exist_ok=True)

        map_path = map_dir / f"{self.name}.map"
        mf.save(map_path, compress=compress)

        # Also generate the TGA preview (placeholder - solid color)
        self._generate_preview_tga(map_dir / f"{self.name}.tga")

        return map_path

    # ── Internal builders ──────────────────────────────────────────────

    def _build_heightmap(self) -> HeightMapData:
        hm = HeightMapData(
            width=self._width,
            height=self._height,
            border_width=2,
        )

        # Borders (playable area rectangle)
        hm.borders = [
            HeightMapBorder(x=0, y=0),
            HeightMapBorder(x=self._width - 1, y=0),
            HeightMapBorder(x=self._width - 1, y=self._height - 1),
            HeightMapBorder(x=0, y=self._height - 1),
        ]

        # Initialize flat terrain
        hm.elevations = [
            [self._base_elevation] * self._width
            for _ in range(self._height)
        ]

        # Apply hills
        for hill in self._hills:
            self._apply_hill(hm, hill)

        # Apply valleys
        for valley in self._valleys:
            self._apply_valley(hm, valley)

        # Apply cliffs
        for cliff in self._cliffs:
            self._apply_cliff(hm, cliff)

        return hm

    def _apply_hill(self, hm: HeightMapData, hill: _PendingHill) -> None:
        cx, cy = hill.center
        r = hill.radius
        h = int(hill.height / HeightMapData.ELEVATION_SCALE)

        x_min = max(0, int(cx - r))
        x_max = min(hm.width, int(cx + r) + 1)
        y_min = max(0, int(cy - r))
        y_max = min(hm.height, int(cy + r) + 1)

        for y in range(y_min, y_max):
            for x in range(x_min, x_max):
                dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                if dist < r:
                    t = 1.0 - (dist / r)
                    factor = t ** hill.falloff if hill.falloff != 1.0 else t
                    hm.elevations[y][x] = min(65535, hm.elevations[y][x] + int(h * factor))

    def _apply_valley(self, hm: HeightMapData, valley: _PendingValley) -> None:
        cx, cy = valley.center
        r = valley.radius
        d = int(valley.depth / HeightMapData.ELEVATION_SCALE)

        x_min = max(0, int(cx - r))
        x_max = min(hm.width, int(cx + r) + 1)
        y_min = max(0, int(cy - r))
        y_max = min(hm.height, int(cy + r) + 1)

        for y in range(y_min, y_max):
            for x in range(x_min, x_max):
                dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                if dist < r:
                    t = 1.0 - (dist / r)
                    factor = t ** valley.falloff if valley.falloff != 1.0 else t
                    hm.elevations[y][x] = max(0, hm.elevations[y][x] - int(d * factor))

    def _apply_cliff(self, hm: HeightMapData, cliff: _PendingCliff) -> None:
        sx, sy = cliff.start
        ex, ey = cliff.end
        h = int(cliff.height / HeightMapData.ELEVATION_SCALE)
        w = cliff.width

        dx = ex - sx
        dy = ey - sy
        length = math.sqrt(dx * dx + dy * dy)
        if length < 0.001:
            return

        nx = -dy / length  # Normal direction
        ny = dx / length

        for y in range(hm.height):
            for x in range(hm.width):
                # Project point onto cliff line
                px = x - sx
                py = y - sy
                along = (px * dx + py * dy) / length
                if along < -w or along > length + w:
                    continue

                perp = px * nx + py * ny  # Distance from line

                if abs(perp) < w:
                    # On the "high" side of the cliff
                    if perp > 0:
                        factor = 1.0 - (perp / w)
                        hm.elevations[y][x] = min(65535, hm.elevations[y][x] + int(h * factor))

    def _build_blend_tiles(self) -> BlendTileData:
        bt = BlendTileData()
        tile_w = self._width - 1
        tile_h = self._height - 1
        bt.num_tiles = tile_w * tile_h

        # Add base terrain texture
        base_tex = BlendTileTexture(
            cell_start=0,
            cell_count=64,  # 4x4 macro cells, each 4x4 = 16 sub-cells
            cell_size=4,
            name=self._base_terrain,
        )
        bt.textures = [base_tex]

        # Add additional terrains
        cell_start = 64
        for terrain_name in self._additional_terrains:
            tex = BlendTileTexture(
                cell_start=cell_start,
                cell_count=64,
                cell_size=4,
                name=terrain_name,
            )
            bt.textures.append(tex)
            cell_start += 64

        # Initialize tile arrays - all base texture
        bt.tiles = [[0] * tile_w for _ in range(tile_h)]
        bt.blends = [[0] * tile_w for _ in range(tile_h)]
        bt.three_way_blends = [[0] * tile_w for _ in range(tile_h)]
        bt.cliff_textures = [[0] * tile_w for _ in range(tile_h)]
        bt.impassable = [[False] * tile_w for _ in range(tile_h)]
        bt.impassable_to_players = [[False] * tile_w for _ in range(tile_h)]
        bt.impassable_to_air = [[False] * tile_w for _ in range(tile_h)]
        bt.buildable = [[True] * tile_w for _ in range(tile_h)]
        bt.extra_passable = [[False] * tile_w for _ in range(tile_h)]

        return bt

    def _build_lighting(self) -> GlobalLighting:
        if self._custom_lighting:
            return self._custom_lighting

        presets = {
            LightingPreset.DEFAULT: _default_lighting,
            LightingPreset.DESERT_AFTERNOON: _desert_afternoon_lighting,
            LightingPreset.FOREST_MORNING: _forest_morning_lighting,
            LightingPreset.URBAN_NIGHT: _urban_night_lighting,
            LightingPreset.SNOW_OVERCAST: _snow_overcast_lighting,
        }

        builder = presets.get(self._lighting_preset, _default_lighting)
        return builder()

    def _generate_preview_tga(self, path: Path) -> None:
        """Generate a simple TGA preview image for the map."""
        # Simple uncompressed 128x128 TGA
        w, h = 128, 128
        header = bytearray(18)
        header[2] = 2  # Uncompressed true color
        header[12] = w & 0xFF
        header[13] = (w >> 8) & 0xFF
        header[14] = h & 0xFF
        header[15] = (h >> 8) & 0xFF
        header[16] = 24  # 24-bit color
        header[17] = 0x20  # Top-left origin

        # Generate a simple heightmap preview
        pixels = bytearray()
        for y in range(h):
            for x in range(w):
                # Map preview coordinates to heightmap
                hx = int(x * self._width / w)
                hy = int(y * self._height / h)
                hx = min(hx, self._width - 1)
                hy = min(hy, self._height - 1)

                elevation = self._base_elevation
                # Apply terrain features for preview
                green = min(255, max(0, int(elevation * 255 / 1024)))
                pixels.extend([green // 2, green, green // 3])  # BGR

        path.write_bytes(bytes(header) + bytes(pixels))


# ── Lighting presets ───────────────────────────────────────────────────────

def _default_lighting() -> GlobalLighting:
    gl = GlobalLighting(time=TimeOfDay.AFTERNOON)
    for tod in TimeOfDay:
        gl.configurations[tod] = LightingConfiguration(
            ambient=ColorRGB(0.3, 0.3, 0.35),
            sun_color=ColorRGB(0.9, 0.85, 0.75),
            accent1_color=ColorRGB(0.2, 0.2, 0.3),
            accent2_color=ColorRGB(0.15, 0.15, 0.2),
            sun_direction=Vec3(0.5, 0.5, -0.7),
        )
    return gl


def _desert_afternoon_lighting() -> GlobalLighting:
    gl = GlobalLighting(time=TimeOfDay.AFTERNOON)
    gl.configurations[TimeOfDay.AFTERNOON] = LightingConfiguration(
        ambient=ColorRGB(0.4, 0.35, 0.25),
        sun_color=ColorRGB(1.0, 0.9, 0.7),
        accent1_color=ColorRGB(0.3, 0.25, 0.15),
        accent2_color=ColorRGB(0.2, 0.15, 0.1),
        sun_direction=Vec3(0.6, 0.4, -0.7),
    )
    # Copy to other times with variations
    for tod in [TimeOfDay.MORNING, TimeOfDay.EVENING, TimeOfDay.NIGHT]:
        gl.configurations[tod] = LightingConfiguration(
            ambient=ColorRGB(0.3, 0.25, 0.2),
            sun_color=ColorRGB(0.8, 0.7, 0.5),
            accent1_color=ColorRGB(0.2, 0.15, 0.1),
            accent2_color=ColorRGB(0.15, 0.1, 0.08),
            sun_direction=Vec3(0.5, 0.5, -0.7),
        )
    return gl


def _forest_morning_lighting() -> GlobalLighting:
    gl = GlobalLighting(time=TimeOfDay.MORNING)
    gl.configurations[TimeOfDay.MORNING] = LightingConfiguration(
        ambient=ColorRGB(0.25, 0.35, 0.25),
        sun_color=ColorRGB(0.9, 0.95, 0.8),
        accent1_color=ColorRGB(0.15, 0.25, 0.15),
        accent2_color=ColorRGB(0.1, 0.15, 0.1),
        sun_direction=Vec3(0.3, 0.6, -0.7),
    )
    for tod in [TimeOfDay.AFTERNOON, TimeOfDay.EVENING, TimeOfDay.NIGHT]:
        gl.configurations[tod] = gl.configurations[TimeOfDay.MORNING]
    return gl


def _urban_night_lighting() -> GlobalLighting:
    gl = GlobalLighting(time=TimeOfDay.NIGHT)
    gl.configurations[TimeOfDay.NIGHT] = LightingConfiguration(
        ambient=ColorRGB(0.1, 0.1, 0.15),
        sun_color=ColorRGB(0.3, 0.3, 0.4),
        accent1_color=ColorRGB(0.05, 0.05, 0.1),
        accent2_color=ColorRGB(0.03, 0.03, 0.05),
        sun_direction=Vec3(0.0, 0.0, -1.0),
    )
    for tod in [TimeOfDay.MORNING, TimeOfDay.AFTERNOON, TimeOfDay.EVENING]:
        gl.configurations[tod] = gl.configurations[TimeOfDay.NIGHT]
    return gl


def _snow_overcast_lighting() -> GlobalLighting:
    gl = GlobalLighting(time=TimeOfDay.AFTERNOON)
    gl.configurations[TimeOfDay.AFTERNOON] = LightingConfiguration(
        ambient=ColorRGB(0.45, 0.45, 0.5),
        sun_color=ColorRGB(0.6, 0.6, 0.7),
        accent1_color=ColorRGB(0.3, 0.3, 0.35),
        accent2_color=ColorRGB(0.2, 0.2, 0.25),
        sun_direction=Vec3(0.3, 0.3, -0.9),
    )
    for tod in [TimeOfDay.MORNING, TimeOfDay.EVENING, TimeOfDay.NIGHT]:
        gl.configurations[tod] = gl.configurations[TimeOfDay.AFTERNOON]
    return gl

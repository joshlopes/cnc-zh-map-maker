"""Tests for the high-level map builder."""

from cnc_zh_map_maker.builder import MapBuilder, MapSize, TerrainPreset, LightingPreset
from cnc_zh_map_maker.data_model import MapWeatherType, Faction


def test_basic_2p_map():
    builder = MapBuilder("Test Map", size=MapSize.TINY_2P)
    builder.set_terrain(TerrainPreset.DESERT)
    builder.add_player_start(1, (20, 20))
    builder.add_player_start(2, (80, 80))
    builder.add_supply_dock(1, (30, 20))
    builder.add_supply_dock(2, (70, 80))

    mf = builder.build()

    assert mf.world_info.map_name == "Test Map"
    assert mf.height_map.width == 100
    assert mf.height_map.height == 100
    assert len(mf.sides.players) == 3  # Neutral + 2 players
    assert len(mf.waypoints.waypoints) == 2  # 2 player starts
    assert len(mf.objects) == 2  # 2 supply docks


def test_heightmap_hills():
    builder = MapBuilder("Hill Test", size=(50, 50))
    builder.add_hill(center=(25, 25), radius=15, height=20.0)

    mf = builder.build()

    # Center should be higher than edges
    center_elev = mf.height_map.get_elevation(25, 25)
    edge_elev = mf.height_map.get_elevation(0, 0)
    assert center_elev > edge_elev


def test_heightmap_valley():
    builder = MapBuilder("Valley Test", size=(50, 50))
    builder.set_base_elevation(20.0)
    builder.add_valley(center=(25, 25), radius=15, depth=10.0)

    mf = builder.build()

    center_elev = mf.height_map.get_elevation(25, 25)
    edge_elev = mf.height_map.get_elevation(0, 0)
    assert center_elev < edge_elev


def test_objects_placed():
    builder = MapBuilder("Object Test", size=(50, 50))
    builder.add_object("CivBuilding_SmallHouse", (20, 20), angle=90)
    builder.add_trees((10, 10, 40, 40), count=5, seed=42)

    mf = builder.build()
    assert len(mf.objects) == 6  # 1 building + 5 trees


def test_skirmish_players():
    builder = MapBuilder("4P Test", size=MapSize.MEDIUM_4P)
    positions = [(50, 50), (200, 50), (50, 200), (200, 200)]
    builder.add_skirmish_players(4, positions)

    mf = builder.build()
    assert len(mf.sides.players) == 5  # Neutral + 4
    # 4 player starts + 12 AI attack path waypoints (3 per player)
    assert len(mf.waypoints.waypoints) == 16


def test_serialization_roundtrip():
    builder = MapBuilder("Roundtrip Test", size=MapSize.TINY_2P)
    builder.add_player_start(1, (20, 20))
    builder.add_player_start(2, (80, 80))

    mf = builder.build()
    data = mf.to_bytes()
    assert data[:4] == b"CkMp"
    assert len(data) > 100


def test_snow_map():
    builder = MapBuilder("Snow Test", size=MapSize.TINY_2P, weather=MapWeatherType.SNOWY)
    builder.set_terrain(TerrainPreset.SNOW)
    builder.set_lighting(LightingPreset.SNOW_OVERCAST)

    mf = builder.build()
    assert mf.world_info.weather == MapWeatherType.SNOWY


def test_blend_tile_dimensions():
    builder = MapBuilder("Blend Test", size=(50, 50))
    builder.set_terrain(TerrainPreset.GRASS)
    builder.add_terrain(TerrainPreset.DIRT)

    mf = builder.build()
    assert len(mf.blend_tile_data.textures) == 2
    assert len(mf.blend_tile_data.tiles) == 49  # height - 1
    assert len(mf.blend_tile_data.tiles[0]) == 49  # width - 1

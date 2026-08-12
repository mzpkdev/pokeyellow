"""Linked-ROM proofs for the passive Pallet Town and Route 1 color layer."""

from __future__ import annotations

import pytest

from tools.rom_tests.emulator import Emulator
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT, result_directory
from tools.rom_tests.tests.unit.full_color.test_phase2_scheduler_rom import (
    Phase2Rom,
    _farcall_from_wram,
    _linked_overworld_tile_attributes,
    numeric_symbols,
)
from tools.rom_tests.tests.unit.full_color.test_phase2_vblank_routing_rom import (
    ENTRY_ROM_BANK,
    ENTRY_WRAM_BANK,
    _run_actual_vblank,
)


RBGPI = 0xFF68
RBGPD = 0xFF69
RBGP = 0xFF47
BOOTROM_DISABLE = 0xFF50
RSVBK = 0xFF70
RVBK = 0xFF4F
VBG_MAP_0 = 0x9800
TILEMAP_AREA = 32 * 32
PALLET_TOWN = 0
VIRIDIAN_CITY = 1
SAFFRON_CITY = 0x0A
ROUTE_1 = 0x0C
ROUTE_6 = 0x11
CELADON_MART_1F = 0x7A
CELADON_MART_ROOF = 0x7E
MART = 2
FOREST = 3
CAVERN = 17
SHIP_PORT = 14
PLATEAU = 23
BEACH_HOUSE = 24
VIRIDIAN_FOREST = 0x33
MT_MOON_1F = 0x3B
VERMILION_DOCK = 0x5E
INDIGO_PLATEAU = 0x09
SUMMER_BEACH_HOUSE = 0xF8
REDRAW_COL = 1
REDRAW_ROW = 2
PAD_RIGHT = 1 << 4
YELLOW_NORMAL_BGP = 0xE4
SET_PAL_OVERWORLD = 9
SCREEN_WIDTH = 20
SCREEN_HEIGHT = 18
PRODUCTS = ("pokeyellow", "pokeyellow_debug", "pokeyellow_vc")
FOUNDATION_PRODUCTS = (*PRODUCTS, "pokeyellow_phase2_audit")


@pytest.fixture(name="phase2_rom", params=PRODUCTS)
def phase2_rom_fixture(request: pytest.FixtureRequest):
    product = request.param
    rom = REPOSITORY_ROOT / f"{product}.gbc"
    sym = REPOSITORY_ROOT / f"{product}.sym"
    emulator = Emulator(
        rom=rom,
        symbols=sym,
        results=result_directory(request.node.nodeid) / product,
        cgb=True,
    )
    instance = Phase2Rom(emulator, numeric_symbols(sym))
    dma_stub = bytes((0x3E, 0xC3, 0xE0, 0x46, 0x3E, 0x28, 0x3D, 0x20, 0xFD, 0xC9))
    for offset, value in enumerate(dma_stub):
        emulator.pyboy.memory[0xFF80 + offset] = value
    try:
        yield instance
    finally:
        emulator.close()


@pytest.fixture(name="foundation_rom", params=FOUNDATION_PRODUCTS)
def foundation_rom_fixture(request: pytest.FixtureRequest):
    product = request.param
    rom = REPOSITORY_ROOT / f"{product}.gbc"
    sym = REPOSITORY_ROOT / f"{product}.sym"
    emulator = Emulator(
        rom=rom,
        symbols=sym,
        results=result_directory(request.node.nodeid) / product,
        cgb=True,
    )
    try:
        yield Phase2Rom(emulator, numeric_symbols(sym))
    finally:
        emulator.close()


def _linked_bytes(rom: Phase2Rom, start: str, end: str) -> bytes:
    bank = rom.emulator.symbol_banks[start]
    assert rom.emulator.symbol_banks[end] == bank
    address = rom.emulator.symbols[start]
    size = rom.emulator.symbols[end] - address
    offset = address if bank == 0 else bank * 0x4000 + address - 0x4000
    return rom.emulator.rom.read_bytes()[offset : offset + size]


def _linked_palette_entry(rom: Phase2Rom, index: int) -> bytes:
    bank = rom.emulator.symbol_banks["CGBBasePalettes"]
    address = rom.emulator.symbols["CGBBasePalettes"] + index * 8
    offset = address if bank == 0 else bank * 0x4000 + address - 0x4000
    return rom.emulator.rom.read_bytes()[offset : offset + 8]


def _linked_overworld_bg_palettes(
    rom: Phase2Rom,
    map_id: int,
    *,
    y_coord: int,
) -> bytes:
    palettes = bytearray(
        _linked_bytes(
            rom,
            "FullColorOverworldBGPalettes",
            "FullColorOverworldBGPalettesEnd",
        )
    )
    assignments = _linked_bytes(
        rom,
        "FullColorOverworldRoofAssignments",
        "FullColorOverworldRoofAssignmentsEnd",
    )
    roof_palettes = _linked_bytes(
        rom,
        "FullColorOverworldRoofPalettes",
        "FullColorOverworldRoofPalettesEnd",
    )
    region_rules = _linked_bytes(
        rom,
        "FullColorOverworldRoofRegionRules",
        "FullColorOverworldRoofRegionRulesEnd",
    )
    assert len(palettes) == 64
    assert 0 <= map_id < len(assignments)
    roof_identity = assignments[map_id]
    for offset in range(0, len(region_rules), 4):
        rule_map, y_split, upper_roof, lower_roof = region_rules[offset : offset + 4]
        if rule_map == map_id:
            roof_identity = upper_roof if y_coord < y_split else lower_roof
            break
    roof_start = roof_identity * 4
    roof_middle_colors = roof_palettes[roof_start : roof_start + 4]
    assert len(roof_middle_colors) == 4
    palettes[6 * 8 + 2 : 6 * 8 + 6] = roof_middle_colors
    return bytes(palettes)


def _apply_dmg_palette_mapping(payload: bytes, bgp: int) -> bytes:
    transformed = bytearray()
    for palette_start in range(0, len(payload), 8):
        palette = payload[palette_start : palette_start + 8]
        mapping = bgp
        for _ in range(4):
            color = mapping & 0b11
            transformed.extend(palette[color * 2 : color * 2 + 2])
            mapping >>= 2
    return bytes(transformed)


def _write_palette(rom: Phase2Rom, payload: bytes) -> None:
    assert len(payload) == 64
    emu = rom.emulator.pyboy
    prior = emu.memory[RBGPI]
    try:
        for index, value in enumerate(payload):
            emu.memory[RBGPI] = index
            emu.memory[RBGPD] = value
    finally:
        emu.memory[RBGPI] = prior


def _write_vram(rom: Phase2Rom, bank: int, address: int, payload: bytes) -> None:
    emu = rom.emulator.pyboy
    prior = emu.memory[RVBK]
    emu.memory[RVBK] = bank
    try:
        for offset, value in enumerate(payload):
            emu.memory[address + offset] = value
    finally:
        emu.memory[RVBK] = prior


def _write_player_data(rom: Phase2Rom, symbol: str, value: int) -> None:
    emu = rom.emulator.pyboy
    prior = emu.memory[RSVBK]
    emu.memory[RSVBK] = 1
    try:
        emu.memory[rom.emulator.symbols[symbol]] = value
    finally:
        emu.memory[RSVBK] = prior


def _read_player_data(rom: Phase2Rom, symbol: str) -> int:
    emu = rom.emulator.pyboy
    prior = emu.memory[RSVBK]
    emu.memory[RSVBK] = 1
    try:
        return emu.memory[rom.emulator.symbols[symbol]]
    finally:
        emu.memory[RSVBK] = prior


def _activate_passive_map(rom: Phase2Rom, map_id: int = PALLET_TOWN) -> None:
    emu = rom.emulator.pyboy
    rom.call("InitRendererOwnership")
    emu.memory[rom.emulator.symbols["wCurMap"]] = map_id
    _write_player_data(rom, "wUnusedObtainedBadges", 0)
    emu.memory[0xFF40] &= 0x7F
    rom.call("PassiveFullColorApplyMap")


@pytest.mark.parametrize(
    ("tileset", "map_id"),
    (
        (FOREST, VIRIDIAN_FOREST),
        (CAVERN, MT_MOON_1F),
        (SHIP_PORT, VERMILION_DOCK),
        (PLATEAU, INDIGO_PLATEAU),
        (BEACH_HOUSE, SUMMER_BEACH_HOUSE),
    ),
    ids=("forest", "cavern", "ship-port", "plateau", "beach-house"),
)
def test_authored_phase4_candidates_remain_outside_production_predicate(
    phase2_rom: Phase2Rom, tileset: int, map_id: int
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    phase2_rom.call("InitRendererOwnership")
    emu.memory[symbols["wCurMap"]] = map_id
    emu.memory[symbols["wCurMapTileset"]] = tileset
    _write_player_data(phase2_rom, "wUnusedObtainedBadges", 0)
    emu.memory[0xFF40] &= 0x7F
    _write_vram(phase2_rom, 1, VBG_MAP_0, b"\x07" * TILEMAP_AREA)

    result, flags = phase2_rom.call("PassiveFullColorIsSliceMap")
    assert result == 1
    assert not flags & 0x80  # Z is clear: authored data does not grant admission.

    phase2_rom.call("PassiveFullColorApplyMap")

    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x00"
    assert phase2_rom.emulator.read_vram_bank(1, VBG_MAP_0, TILEMAP_AREA) == (
        b"\x00" * TILEMAP_AREA
    )


def test_product_option_toggles_only_saved_renderer_preference_bit(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    _write_player_data(phase2_rom, "wUnusedObtainedBadges", 0xA0)
    emu.memory[symbols["hJoy5"]] = PAD_RIGHT

    phase2_rom.call("OptionsMenu_ColorMode")

    prior = emu.memory[RSVBK]
    emu.memory[RSVBK] = 1
    try:
        assert emu.memory[symbols["wUnusedObtainedBadges"]] == 0xA1
    finally:
        emu.memory[RSVBK] = prior


def test_saved_yellow_preference_blocks_map_publish_and_clears_all_attributes(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    phase2_rom.call("InitRendererOwnership")
    emu.memory[symbols["wCurMap"]] = PALLET_TOWN
    _write_player_data(phase2_rom, "wUnusedObtainedBadges", 0x81)
    emu.memory[0xFF40] &= 0x7F
    _write_vram(phase2_rom, 1, VBG_MAP_0, b"\x07" * TILEMAP_AREA)

    phase2_rom.call("PassiveFullColorApplyMap")

    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x00"
    assert phase2_rom.emulator.read_vram_bank(1, VBG_MAP_0, TILEMAP_AREA) == (
        b"\x00" * TILEMAP_AREA
    )


def test_menu_close_in_yellow_mode_restores_authoritative_pallet_palette(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    phase2_rom.call("InitRendererOwnership")
    emu.memory[symbols["wCurMap"]] = PALLET_TOWN
    emu.memory[symbols["wOnSGB"]] = 1
    emu.memory[symbols["hOnCGB"]] = 1
    emu.memory[RBGP] = YELLOW_NORMAL_BGP
    emu.memory[0xFF40] &= 0x7F

    # Pallet is palette ID 1 in Yellow's linked CGB base-palette authority.
    expected_yellow_pallet = _linked_palette_entry(phase2_rom, 1)
    _write_player_data(phase2_rom, "wLastBGP", YELLOW_NORMAL_BGP)
    _write_player_data(phase2_rom, "wUnusedObtainedBadges", 0)
    phase2_rom.call("PassiveFullColorApplyMap")
    stale_donor_palette = phase2_rom.emulator.read_palette_ram()
    _write_vram(phase2_rom, 1, VBG_MAP_0, b"\x07" * TILEMAP_AREA)
    _write_player_data(phase2_rom, "wUnusedObtainedBadges", 1)

    assert stale_donor_palette[:8] != expected_yellow_pallet
    assert _read_player_data(phase2_rom, "wLastBGP") == emu.memory[RBGP]
    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x01"

    # Production has unmapped the boot ROM before this home-bank CopyData path.
    emu.memory[BOOTROM_DISABLE] = 1
    _farcall_from_wram(
        phase2_rom,
        "PassiveFullColorRestoreAfterMenu",
        entry_bank=5,
    )

    assert phase2_rom.emulator.read_palette_ram()[:8] == expected_yellow_pallet
    assert phase2_rom.emulator.read_vram_bank(1, VBG_MAP_0, TILEMAP_AREA) == (
        b"\x00" * TILEMAP_AREA
    )
    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x00"


def test_overlay_presentation_stays_latched_after_color_preference_changes(
    phase2_rom: Phase2Rom,
) -> None:
    _activate_passive_map(phase2_rom)
    _write_player_data(phase2_rom, "wUnusedObtainedBadges", 1)

    _, flags = phase2_rom.call("PassiveFullColorShouldColorOverlay")

    assert flags & 0x10
    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x01"


def test_inactive_live_activation_publishes_wrapped_visible_rows_before_color(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    attributes = _linked_overworld_tile_attributes(phase2_rom)
    palettes = _linked_bytes(
        phase2_rom, "FullColorOverworldBGPalettes", "FullColorOverworldBGPalettesEnd"
    )
    tiles = bytes(
        (index * 29 + 7) & 0xFF for index in range(SCREEN_WIDTH * SCREEN_HEIGHT)
    )
    pointer = 0x9BF5  # bottom row, x=21: exercises both horizontal and vertical wrap
    phase2_rom.call("InitRendererOwnership")
    emu.memory[symbols["wCurMap"]] = PALLET_TOWN
    _write_player_data(phase2_rom, "wUnusedObtainedBadges", 0)
    phase2_rom.write_fixed(symbols["wTileMap"], tiles)
    phase2_rom.write_fixed(
        symbols["wMapViewVRAMPointer"], bytes((pointer & 0xFF, pointer >> 8))
    )
    _write_vram(phase2_rom, 1, VBG_MAP_0, b"\x07" * TILEMAP_AREA)
    phase2_rom.call("PassiveFullColorWriteActive", a=0)
    phase2_rom.call("PassiveFullColorTranslateTileMap")
    phase2_rom.call("PassiveFullColorWriteState", b=4, c=SCREEN_HEIGHT)

    phase2_rom.call("PassiveFullColorVBlank", de=0)
    neutral = phase2_rom.emulator.read_palette_ram()
    assert all(neutral[index * 8 : index * 8 + 8] == neutral[:8] for index in range(8))
    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x00"

    expected_by_address: dict[int, int] = {}
    for row in range(SCREEN_HEIGHT):
        y = ((pointer - VBG_MAP_0) // 32 + row) & 31
        x = (pointer - VBG_MAP_0) & 31
        for column in range(SCREEN_WIDTH):
            address = VBG_MAP_0 + y * 32 + ((x + column) & 31)
            expected_by_address[address] = attributes[
                tiles[row * SCREEN_WIDTH + column]
            ]

    for remaining in range(SCREEN_HEIGHT - 2, -1, -2):
        phase2_rom.call("PassiveFullColorVBlank", de=0)
        assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x00"
        assert phase2_rom.emulator.read_palette_ram() == neutral
        assert phase2_rom.read_wram2("wPassiveFullColorClearChunks") == bytes(
            (remaining,)
        )

    actual = phase2_rom.emulator.read_vram_bank(1, VBG_MAP_0, TILEMAP_AREA)
    assert all(
        actual[address - VBG_MAP_0] == value
        for address, value in expected_by_address.items()
    )
    offscreen = next(
        address
        for address in range(VBG_MAP_0, VBG_MAP_0 + TILEMAP_AREA)
        if address not in expected_by_address
    )
    assert actual[offscreen - VBG_MAP_0] == 7
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x06"

    phase2_rom.call("PassiveFullColorVBlank", de=0)
    assert phase2_rom.emulator.read_palette_ram() == palettes
    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x01"
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x00"


def test_cold_boot_map_zero_cannot_activate_without_a_real_map_publish(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    rom_palette = _linked_bytes(
        phase2_rom, "FullColorOverworldBGPalettes", "FullColorOverworldBGPalettesEnd"
    )
    sentinel_palette = bytes((index * 5 + 7) & 0x7F for index in range(64))
    sentinel_attributes = bytes((index * 3 + 1) & 7 for index in range(TILEMAP_AREA))
    phase2_rom.call("InitRendererOwnership")
    emu.memory[phase2_rom.emulator.symbols["wCurMap"]] = PALLET_TOWN
    _write_palette(phase2_rom, sentinel_palette)
    _write_vram(phase2_rom, 1, VBG_MAP_0, sentinel_attributes)

    phase2_rom.call("PassiveFullColorVBlank", de=0)

    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x00"
    assert phase2_rom.emulator.read_palette_ram() == sentinel_palette
    assert phase2_rom.emulator.read_vram_bank(1, VBG_MAP_0, TILEMAP_AREA) == (
        sentinel_attributes
    )
    assert sentinel_palette != rom_palette


@pytest.mark.parametrize("map_id", (PALLET_TOWN, VIRIDIAN_CITY, ROUTE_1))
def test_lcd_off_map_publish_keeps_yellow_owner_and_mirrors_all_1024_tiles(
    phase2_rom: Phase2Rom,
    map_id: int,
) -> None:
    emu = phase2_rom.emulator.pyboy
    tiles = bytes((index * 37 + 11) & 0xFF for index in range(TILEMAP_AREA))
    attributes = _linked_overworld_tile_attributes(phase2_rom)
    palettes = _linked_overworld_bg_palettes(phase2_rom, map_id, y_coord=0)
    phase2_rom.call("InitRendererOwnership")
    emu.memory[phase2_rom.emulator.symbols["wCurMap"]] = map_id
    emu.memory[0xFF40] &= 0x7F
    _write_vram(phase2_rom, 0, VBG_MAP_0, tiles)
    _write_vram(phase2_rom, 1, VBG_MAP_0, b"\x07" * TILEMAP_AREA)

    phase2_rom.call("PassiveFullColorApplyMap")

    assert phase2_rom.read_wram2("wRendererOwner") == bytes(
        (phase2_rom.constants["RENDERER_YELLOW"],)
    )
    assert phase2_rom.read_wram2("wRendererPhase") == bytes(
        (phase2_rom.constants["YELLOW_ACTIVE"],)
    )
    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x01"
    assert phase2_rom.emulator.read_palette_ram() == palettes
    assert phase2_rom.emulator.read_vram_bank(0, VBG_MAP_0, TILEMAP_AREA) == tiles
    assert phase2_rom.emulator.read_vram_bank(1, VBG_MAP_0, TILEMAP_AREA) == bytes(
        attributes[tile] for tile in tiles
    )


def test_viridian_publish_commits_linked_map_specific_roof_colors(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    pallet = _linked_overworld_bg_palettes(phase2_rom, PALLET_TOWN, y_coord=0)
    viridian = _linked_overworld_bg_palettes(phase2_rom, VIRIDIAN_CITY, y_coord=0)
    assignments = _linked_bytes(
        phase2_rom,
        "FullColorOverworldRoofAssignments",
        "FullColorOverworldRoofAssignmentsEnd",
    )
    roof_palettes = _linked_bytes(
        phase2_rom,
        "FullColorOverworldRoofPalettes",
        "FullColorOverworldRoofPalettesEnd",
    )
    roof_start = assignments[VIRIDIAN_CITY] * 4

    assert viridian[6 * 8 + 2 : 6 * 8 + 6] == roof_palettes[roof_start : roof_start + 4]
    assert viridian[6 * 8 + 2 : 6 * 8 + 6] != pallet[6 * 8 + 2 : 6 * 8 + 6]

    phase2_rom.call("InitRendererOwnership")
    emu.memory[phase2_rom.emulator.symbols["wCurMap"]] = VIRIDIAN_CITY
    _write_player_data(phase2_rom, "wUnusedObtainedBadges", 0)
    emu.memory[0xFF40] &= 0x7F
    phase2_rom.call("PassiveFullColorApplyMap")

    assert phase2_rom.emulator.read_palette_ram() == viridian


def test_route6_rule_drives_every_near_boundary_palette_and_region_token(
    foundation_rom: Phase2Rom,
) -> None:
    emu = foundation_rom.emulator.pyboy
    assignments = _linked_bytes(
        foundation_rom,
        "FullColorOverworldRoofAssignments",
        "FullColorOverworldRoofAssignmentsEnd",
    )
    roof_palettes = _linked_bytes(
        foundation_rom,
        "FullColorOverworldRoofPalettes",
        "FullColorOverworldRoofPalettesEnd",
    )
    rules = _linked_bytes(
        foundation_rom,
        "FullColorOverworldRoofRegionRules",
        "FullColorOverworldRoofRegionRulesEnd",
    )
    assert rules == bytes((ROUTE_6, 2, assignments[SAFFRON_CITY], assignments[ROUTE_6]))

    for y_coord, roof_map_id, region in (
        (0, SAFFRON_CITY, 0),
        (1, SAFFRON_CITY, 0),
        (2, ROUTE_6, 1),
        (3, ROUTE_6, 1),
    ):
        expected = _linked_overworld_bg_palettes(
            foundation_rom, ROUTE_6, y_coord=y_coord
        )
        roof_start = assignments[roof_map_id] * 4
        assert expected[6 * 8 + 2 : 6 * 8 + 6] == roof_palettes[
            roof_start : roof_start + 4
        ]

        foundation_rom.call("InitRendererOwnership")
        emu.memory[foundation_rom.emulator.symbols["wCurMap"]] = ROUTE_6
        emu.memory[foundation_rom.emulator.symbols["wCurMapTileset"]] = 0
        emu.memory[foundation_rom.emulator.symbols["wYCoord"]] = y_coord
        _write_player_data(foundation_rom, "wUnusedObtainedBadges", 0)
        emu.memory[0xFF40] &= 0x7F
        foundation_rom.call("PassiveFullColorApplyMap")

        assert foundation_rom.emulator.read_palette_ram() == expected
        assert foundation_rom.read_wram2("wPassiveFullColorRoofRegion") == bytes(
            (region,)
        )


def test_celadon_override_lookup_covers_every_matching_and_nonmatching_tile(
    foundation_rom: Phase2Rom,
) -> None:
    emu = foundation_rom.emulator.pyboy
    symbols = foundation_rom.emulator.symbols
    attributes = _linked_bytes(
        foundation_rom,
        "FullColorPokecenterTileAttributes",
        "FullColorPokecenterTileAttributesEnd",
    )
    assert len(attributes) == 0x100
    cases = (
        (CELADON_MART_ROOF, frozenset(range(0x4B, 0x50)), 3),
        (CELADON_MART_1F, frozenset((0x07, 0x08, 0x17, 0x18)), 4),
    )
    emu.memory[RSVBK] = 1
    emu.memory[symbols["wCurMapTileset"]] = MART
    for map_id, overridden_tiles, override in cases:
        emu.memory[symbols["wCurMap"]] = map_id
        for tile_id in range(0x100):
            expected = override if tile_id in overridden_tiles else attributes[tile_id]
            actual, _ = foundation_rom.call(
                "PassiveFullColorAttributeForTileWRAM1",
                a=tile_id,
                b=0xA5,
                c=0x5A,
                de=0xBEEF,
                hl=0x1234,
            )
            assert actual == expected, f"map={map_id:#04x}, tile={tile_id:#04x}"
            registers = emu.register_file
            assert (
                registers.B,
                registers.C,
                registers.D << 8 | registers.E,
                registers.HL,
            ) == (
                0xA5,
                0x5A,
                0xBEEF,
                0x1234,
            )
            assert emu.memory[RSVBK] == 1


def test_runtime_data_change_does_not_widen_or_narrow_admission(
    foundation_rom: Phase2Rom,
) -> None:
    emu = foundation_rom.emulator.pyboy
    symbols = foundation_rom.emulator.symbols
    cases = (
        (ROUTE_6, 0, True),
        (CELADON_MART_1F, MART, True),
        (CELADON_MART_ROOF, MART, True),
        (VIRIDIAN_FOREST, FOREST, False),
        (MT_MOON_1F, CAVERN, False),
        (VERMILION_DOCK, SHIP_PORT, False),
        (INDIGO_PLATEAU, PLATEAU, False),
        (SUMMER_BEACH_HOUSE, BEACH_HOUSE, False),
    )
    emu.memory[RSVBK] = 1
    emu.memory[symbols["wUnusedObtainedBadges"]] = 0
    for map_id, tileset, admitted in cases:
        emu.memory[symbols["wCurMap"]] = map_id
        emu.memory[symbols["wCurMapTileset"]] = tileset
        _, flags = foundation_rom.call("PassiveFullColorIsSliceMap")
        assert bool(flags & 0x80) is admitted

    emu.memory[symbols["wCurMap"]] = ROUTE_6
    emu.memory[symbols["wCurMapTileset"]] = 0
    emu.memory[symbols["wUnusedObtainedBadges"]] = 1
    _, flags = foundation_rom.call("PassiveFullColorIsSliceMap")
    assert not flags & 0x80


@pytest.mark.parametrize(
    ("mode", "source", "destination", "expected_addresses"),
    (
        (
            REDRAW_ROW,
            bytes((index * 9 + 3) & 0xFF for index in range(40)),
            0x9820,
            tuple(range(0x9820, 0x9820 + 20)) + tuple(range(0x9840, 0x9840 + 20)),
        ),
        (
            REDRAW_COL,
            bytes((index * 11 + 5) & 0xFF for index in range(36)),
            0x9812,
            tuple(
                address
                for row in range(18)
                for address in (0x9812 + row * 32, 0x9813 + row * 32)
            ),
        ),
    ),
)
def test_real_vblank_runs_yellow_bank0_redraw_before_exact_passive_attributes(
    phase2_rom: Phase2Rom,
    mode: int,
    source: bytes,
    destination: int,
    expected_addresses: tuple[int, ...],
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    attributes = _linked_overworld_tile_attributes(phase2_rom)
    _activate_passive_map(phase2_rom)
    phase2_rom.write_fixed(symbols["wRedrawRowOrColumnSrcTiles"], source)
    emu.memory[symbols["hRedrawRowOrColumnDest"]] = destination & 0xFF
    emu.memory[symbols["hRedrawRowOrColumnDest"] + 1] = destination >> 8
    if mode == REDRAW_ROW:
        phase2_rom.call("PassiveFullColorPrepareRedrawAttributes")
    else:
        phase2_rom.call("PassiveFullColorPrepareColumnAttributes")
    assert phase2_rom.read_wram2("wPassiveFullColorDeferredRedrawState") == bytes(
        (0x80 | mode,)
    )
    _write_vram(phase2_rom, 0, VBG_MAP_0, b"\x55" * TILEMAP_AREA)
    _write_vram(phase2_rom, 1, VBG_MAP_0, b"\xee" * TILEMAP_AREA)
    emu.memory[symbols["hRedrawRowOrColumnMode"]] = mode

    yellow_observation = _run_actual_vblank(phase2_rom)

    assert "RedrawRowOrColumn" in yellow_observation.call_sites
    assert emu.memory[symbols["hRedrawRowOrColumnMode"]] == 0
    assert phase2_rom.read_wram2("wPassiveFullColorDeferredRedrawState") == bytes(
        (mode,)
    )
    assert (
        bytes(
            phase2_rom.emulator.read_vram_bank(0, address, 1)[0]
            for address in expected_addresses
        )
        == source
    )
    assert bytes(
        phase2_rom.emulator.read_vram_bank(1, address, 1)[0]
        for address in expected_addresses
    ) == b"\xee" * len(expected_addresses)

    _run_actual_vblank(phase2_rom)

    assert emu.memory[symbols["hRedrawRowOrColumnMode"]] == 0
    assert phase2_rom.read_wram2("wPassiveFullColorDeferredRedrawState") == b"\x00"
    assert (
        bytes(
            phase2_rom.emulator.read_vram_bank(0, address, 1)[0]
            for address in expected_addresses
        )
        == source
    )
    assert bytes(
        phase2_rom.emulator.read_vram_bank(1, address, 1)[0]
        for address in expected_addresses
    ) == bytes(attributes[tile] for tile in source)


def test_connection_palette_waits_for_yellow_redraw_and_deferred_mirror(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    source = bytes((index * 13 + 7) & 0xFF for index in range(40))
    destination = 0x9820
    expected_addresses = tuple(range(destination, destination + 20)) + tuple(
        range(destination + 32, destination + 32 + 20)
    )
    attributes = _linked_overworld_tile_attributes(phase2_rom)
    pallet_palettes = _linked_overworld_bg_palettes(phase2_rom, PALLET_TOWN, y_coord=0)
    viridian_palettes = _linked_overworld_bg_palettes(
        phase2_rom, VIRIDIAN_CITY, y_coord=35
    )

    _activate_passive_map(phase2_rom, PALLET_TOWN)
    assert phase2_rom.emulator.read_palette_ram() == pallet_palettes
    emu.memory[0xFF40] |= 0x80
    emu.memory[symbols["wCurMap"]] = VIRIDIAN_CITY
    emu.memory[symbols["wYCoord"]] = 35
    phase2_rom.call("PassiveFullColorHandleConnection")

    phase2_rom.write_fixed(symbols["wRedrawRowOrColumnSrcTiles"], source)
    emu.memory[symbols["hRedrawRowOrColumnDest"]] = destination & 0xFF
    emu.memory[symbols["hRedrawRowOrColumnDest"] + 1] = destination >> 8
    phase2_rom.call("PassiveFullColorPrepareRedrawAttributes")
    _write_vram(phase2_rom, 0, VBG_MAP_0, b"\x55" * TILEMAP_AREA)
    _write_vram(phase2_rom, 1, VBG_MAP_0, b"\xee" * TILEMAP_AREA)
    emu.memory[symbols["hRedrawRowOrColumnMode"]] = REDRAW_ROW

    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x01"
    assert phase2_rom.read_wram2("wPassiveFullColorDeferredRedrawState") == bytes(
        (0x80 | REDRAW_ROW,)
    )

    yellow_frame = _run_actual_vblank(phase2_rom)

    assert "RedrawRowOrColumn" in yellow_frame.call_sites
    assert phase2_rom.emulator.read_palette_ram() == pallet_palettes
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x01"
    assert phase2_rom.read_wram2("wPassiveFullColorDeferredRedrawState") == bytes(
        (REDRAW_ROW,)
    )
    assert (
        bytes(
            phase2_rom.emulator.read_vram_bank(0, address, 1)[0]
            for address in expected_addresses
        )
        == source
    )
    assert bytes(
        phase2_rom.emulator.read_vram_bank(1, address, 1)[0]
        for address in expected_addresses
    ) == b"\xee" * len(expected_addresses)

    _run_actual_vblank(phase2_rom)

    assert phase2_rom.emulator.read_palette_ram() == pallet_palettes
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x01"
    assert phase2_rom.read_wram2("wPassiveFullColorDeferredRedrawState") == b"\x00"
    assert bytes(
        phase2_rom.emulator.read_vram_bank(1, address, 1)[0]
        for address in expected_addresses
    ) == bytes(attributes[tile] for tile in source)

    _run_actual_vblank(phase2_rom)

    assert phase2_rom.emulator.read_palette_ram() == viridian_palettes
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x00"


def test_pending_palette_refresh_commits_exact_payload_on_next_vblank_only(
    phase2_rom: Phase2Rom,
) -> None:
    expected = _linked_overworld_bg_palettes(phase2_rom, ROUTE_1, y_coord=0)
    damaged = bytes(value ^ 0x1F for value in expected)
    _activate_passive_map(phase2_rom, ROUTE_1)
    _write_palette(phase2_rom, damaged)
    phase2_rom.write_wram2("wPassiveFullColorPaletteInvalidated", 1)

    phase2_rom.call("PassiveFullColorHandleConnection")

    assert phase2_rom.emulator.read_palette_ram() == damaged
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x01"
    phase2_rom.call("PassiveFullColorVBlank", de=0)
    assert phase2_rom.emulator.read_palette_ram() == expected
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x00"
    assert phase2_rom.read_wram2("wPassiveFullColorPaletteInvalidated") == b"\x00"


def test_route6_crossing_queues_and_commits_new_roof_region(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    phase2_rom.call("InitRendererOwnership")
    emu.memory[symbols["wCurMap"]] = ROUTE_6
    emu.memory[symbols["wCurMapTileset"]] = 0
    emu.memory[symbols["wYCoord"]] = 1
    _write_player_data(phase2_rom, "wUnusedObtainedBadges", 0)
    emu.memory[0xFF40] &= 0x7F
    phase2_rom.call("PassiveFullColorApplyMap")

    saffron = _linked_overworld_bg_palettes(phase2_rom, ROUTE_6, y_coord=1)
    vermilion = _linked_overworld_bg_palettes(phase2_rom, ROUTE_6, y_coord=2)
    assert phase2_rom.emulator.read_palette_ram() == saffron
    assert phase2_rom.read_wram2("wPassiveFullColorRoofRegion") == b"\x00"

    emu.memory[symbols["wYCoord"]] = 2
    phase2_rom.call("PassiveFullColorLoadGBPal")

    assert phase2_rom.emulator.read_palette_ram() == saffron
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x01"
    phase2_rom.call("PassiveFullColorVBlank", de=0)
    assert phase2_rom.emulator.read_palette_ram() == vermilion
    assert phase2_rom.read_wram2("wPassiveFullColorRoofRegion") == b"\x01"
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x00"


@pytest.mark.parametrize("bgp", (0x00, 0x1B, 0xE4, 0xFF))
def test_fades_transform_all_eight_authored_palettes(
    phase2_rom: Phase2Rom,
    bgp: int,
) -> None:
    emu = phase2_rom.emulator.pyboy
    expected_base = _linked_overworld_bg_palettes(phase2_rom, ROUTE_1, y_coord=0)
    _activate_passive_map(phase2_rom, ROUTE_1)
    symbols = phase2_rom.emulator.symbols
    emu.memory[symbols["hOnCGB"]] = 1
    emu.memory[RBGP] = bgp
    emu.memory[symbols["wLastBGP"]] = bgp ^ 0xFF

    phase2_rom.call("UpdateCGBPal_BGP", b=0x5A, c=0xA5, de=0xC123, hl=0xC456)

    assert phase2_rom.emulator.read_palette_ram() == _apply_dmg_palette_mapping(
        expected_base, bgp
    )
    regs = emu.register_file
    assert (regs.B, regs.C, regs.D, regs.E, regs.HL) == (
        0x5A,
        0xA5,
        0xC1,
        0x23,
        0xC456,
    )
    assert phase2_rom.read_wram2("wPassiveFullColorPaletteInvalidated") == b"\x00"


def test_suspended_overlay_fade_keeps_yellow_palette_writer_authoritative(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    banks = phase2_rom.emulator.symbol_banks
    bgp = 0x1B
    palette_ids = (1, 2, 3, 4)
    _activate_passive_map(phase2_rom, ROUTE_1)
    authored = phase2_rom.emulator.read_palette_ram()
    pointers = b"".join(
        (symbols["CGBBasePalettes"] + index * 8).to_bytes(2, "little")
        for index in palette_ids
    )
    phase2_rom.write_fixed(symbols["wCGBBasePalPointers"], pointers)
    phase2_rom.write_wram2("wPassiveFullColorOverlaySuspended", 1)
    phase2_rom.write_wram2("wPassiveFullColorPaletteInvalidated", 0)
    emu.memory[symbols["hOnCGB"]] = 1
    emu.memory[RBGP] = bgp
    emu.memory[symbols["wLastBGP"]] = bgp ^ 0xFF
    events: list[str] = []
    observed = (
        "_UpdateCGBPal_BGP",
        "PassiveFullColorTransferFadedPalettes",
        "PassiveFullColorRecordPalettePublished",
    )
    for name in observed:
        emu.hook_register(
            banks[name],
            symbols[name],
            lambda _context, label=name: events.append(label),
            name,
        )
    try:
        phase2_rom.call("UpdateCGBPal_BGP")
    finally:
        for name in reversed(observed):
            emu.hook_deregister(banks[name], symbols[name])

    yellow = _apply_dmg_palette_mapping(
        b"".join(_linked_palette_entry(phase2_rom, index) for index in palette_ids),
        bgp,
    )
    assert events == ["_UpdateCGBPal_BGP"]
    assert phase2_rom.emulator.read_palette_ram() == yellow + authored[32:]
    assert emu.memory[symbols["wLastBGP"]] == bgp
    assert phase2_rom.read_wram2("wPassiveFullColorPaletteInvalidated") == b"\x01"


def test_yellow_attribute_packet_suspends_overlays_until_explicit_resume(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    _activate_passive_map(phase2_rom, ROUTE_1)
    emu.memory[0xFF40] &= 0x7F

    phase2_rom.call("LoadBGMapAttributes", c=5)  # party menu packet

    assert phase2_rom.read_wram2("wPassiveFullColorAttributesInvalidated") == b"\x01"
    assert phase2_rom.read_wram2("wPassiveFullColorOverlaySuspended") == b"\x01"
    _, flags = phase2_rom.call("PassiveFullColorShouldColorOverlay")
    assert not flags & 0x10

    phase2_rom.call("PassiveFullColorResumeOverlays")
    _, flags = phase2_rom.call("PassiveFullColorShouldColorOverlay")
    assert flags & 0x10
    assert phase2_rom.read_wram2("wPassiveFullColorAttributesInvalidated") == b"\x01"

    phase2_rom.call("PassiveFullColorRestoreAfterMenu")
    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x01"
    assert phase2_rom.read_wram2("wPassiveFullColorAttributesInvalidated") == b"\x00"
    assert phase2_rom.read_wram2("wPassiveFullColorOverlaySuspended") == b"\x00"


def test_scoped_redraw_protection_suppresses_whole_screen_attribute_packet(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    _activate_passive_map(phase2_rom, ROUTE_1)
    emu.memory[0xFF40] &= 0x7F
    original = phase2_rom.emulator.read_vram_bank(1, 0x9800, 32 * 32)

    phase2_rom.write_wram2("wPassiveFullColorBGAttributesProtected", 1)
    phase2_rom.call("LoadBGMapAttributes", c=5)

    assert phase2_rom.emulator.read_vram_bank(1, 0x9800, 32 * 32) == original
    assert phase2_rom.read_wram2("wPassiveFullColorAttributesInvalidated") == b"\x00"


def test_protected_default_palette_command_reaches_writer_without_publishing(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    banks = phase2_rom.emulator.symbol_banks
    _activate_passive_map(phase2_rom, ROUTE_1)
    authored = phase2_rom.emulator.read_palette_ram()
    emu.memory[symbols["wCurMapTileset"]] = 0
    emu.memory[symbols["wDefaultPaletteCommand"]] = SET_PAL_OVERWORLD
    emu.memory[symbols["wOnSGB"]] = 1
    emu.memory[symbols["hOnCGB"]] = 1
    emu.memory[BOOTROM_DISABLE] = 1
    protected_at_writer: list[bytes] = []

    def observe_writer(_: object) -> None:
        protected_at_writer.append(
            phase2_rom.read_wram2("wPassiveFullColorBGPaletteProtected")
        )

    emu.hook_register(
        banks["TransferCurBGPData"],
        symbols["TransferCurBGPData"],
        observe_writer,
        None,
    )
    try:
        phase2_rom.call("PassiveFullColorRunDefaultPaletteCommand")
    finally:
        emu.hook_deregister(banks["TransferCurBGPData"], symbols["TransferCurBGPData"])

    assert protected_at_writer == [b"\x01"] * 4
    assert phase2_rom.emulator.read_palette_ram() == authored
    assert phase2_rom.read_wram2("wPassiveFullColorBGPaletteProtected") == b"\x00"
    assert phase2_rom.read_wram2("wPassiveFullColorPaletteInvalidated") == b"\x00"


@pytest.mark.parametrize("writer", ("TransferBGPPals", "TransferCurBGPData"))
def test_yellow_bg_palette_writers_invalidate_authored_palette_authority(
    phase2_rom: Phase2Rom,
    writer: str,
) -> None:
    emu = phase2_rom.emulator.pyboy
    _activate_passive_map(phase2_rom, ROUTE_1)
    assert phase2_rom.read_wram2("wPassiveFullColorPaletteInvalidated") == b"\x00"

    emu.memory[0xFF40] &= 0x7F
    phase2_rom.call(writer)

    assert phase2_rom.read_wram2("wPassiveFullColorPaletteInvalidated") == b"\x01"


def test_generation_mismatch_deactivates_persistently_across_low_byte_wrap(
    phase2_rom: Phase2Rom,
) -> None:
    expected = _linked_bytes(
        phase2_rom, "FullColorOverworldBGPalettes", "FullColorOverworldBGPalettesEnd"
    )
    damaged = bytes(value ^ 0x1F for value in expected)
    _activate_passive_map(phase2_rom)
    recorded_generation = phase2_rom.read_wram2("wPassiveFullColorGeneration")[0]
    phase2_rom.write_wram2(
        "wRendererGeneration", bytes(((recorded_generation + 1) & 0xFF, 0, 0, 0))
    )
    phase2_rom.write_wram2("wPassiveFullColorPalettePending", 1)

    phase2_rom.call("PassiveFullColorVBlank", de=0)

    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x00"
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x00"
    assert phase2_rom.read_wram2("wPassiveFullColorClearChunks") == b"\x00"

    # A later generation can share the recorded low byte after 256 handoffs.
    # The mismatch must have made the stale passive state permanently inert.
    phase2_rom.write_wram2("wRendererGeneration", bytes((recorded_generation, 1, 0, 0)))
    _write_palette(phase2_rom, damaged)
    phase2_rom.call("PassiveFullColorVBlank", de=0)

    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x00"
    assert phase2_rom.emulator.read_palette_ram() == damaged


def test_exit_makes_stale_attributes_inert_then_clears_every_bank1_address(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    symbols = phase2_rom.emulator.symbols
    _activate_passive_map(phase2_rom)
    _write_vram(phase2_rom, 1, VBG_MAP_0, b"\x07" * TILEMAP_AREA)
    emu.memory[symbols["wCurMap"]] = 0x33  # VIRIDIAN_FOREST, outside the slice

    phase2_rom.call("PassiveFullColorHandleConnection")
    assert phase2_rom.read_wram2("wPassiveFullColorActive") == b"\x00"
    assert phase2_rom.read_wram2("wPassiveFullColorClearChunks") == b"\x20"

    phase2_rom.call("PassiveFullColorVBlank", de=0)
    palette = phase2_rom.emulator.read_palette_ram()
    assert all(
        palette[index * 8 : index * 8 + 8] == palette[:8] for index in range(8)
    ), palette.hex()
    assert phase2_rom.read_wram2("wPassiveFullColorPalettePending") == b"\x00"
    assert phase2_rom.read_wram2("wPassiveFullColorClearChunks") == b"\x20"
    for _ in range(32):
        phase2_rom.call("PassiveFullColorVBlank", de=0)
    assert phase2_rom.read_wram2("wPassiveFullColorClearChunks") == b"\x00"
    assert phase2_rom.emulator.read_vram_bank(1, VBG_MAP_0, TILEMAP_AREA) == (
        b"\x00" * TILEMAP_AREA
    )


def test_actual_passive_vblank_restores_machine_state_and_keeps_yellow_owner(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    _activate_passive_map(phase2_rom)
    observation = _run_actual_vblank(phase2_rom)

    assert observation.stack_pointer == 0xFFFC
    assert observation.rsvbk == ENTRY_WRAM_BANK
    assert observation.rvbk & 1 == 1
    assert observation.loaded_rom_bank == ENTRY_ROM_BANK
    assert observation.interrupt_enable & 0x1F == 1
    assert observation.interrupt_flags & 0x1F == 1 << 4
    assert phase2_rom.read_wram2("wRendererOwner") == bytes(
        (phase2_rom.constants["RENDERER_YELLOW"],)
    )
    assert emu.memory[phase2_rom.emulator.symbols["wUpdateSpritesEnabled"]] != 0

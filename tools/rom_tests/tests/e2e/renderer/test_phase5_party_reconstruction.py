"""Natural-input proof of the audit-only poisoned Party round trip."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tools.rom_tests.emulator import Emulator
from tools.rom_tests.scenarios.oaks_lab import complete_oaks_lab_intro
from tools.rom_tests.scenarios.renderer_mode import move_cursor_to
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT, result_directory
from tools.rom_tests.tests.unit.full_color.test_phase2_scheduler_rom import numeric_symbols


PAD_START_MENU = 0xCB
MAX_WAIT_FRAMES = 360
MACHINE_CANARY_BANK = 7
MACHINE_CANARY_ADDRESS = 0xDFC0
MACHINE_CANARY = bytes((0xA5 ^ index) for index in range(16))
POISONED_TILE_DATA = 0xD3
POISONED_ATTRIBUTES = 0x6D
VBG_MAP_0 = 0x9800
VBG_MAP_1 = 0x9C00
SCREEN_WIDTH = 20
SCREEN_HEIGHT = 18
VTILESET = 0x9000
TILESET_BYTES = 0x600


def _wait(emulator: Emulator, predicate, description: str) -> None:
    for _ in range(MAX_WAIT_FRAMES):
        if predicate():
            return
        emulator.tick()
    raise AssertionError(
        f"timed out waiting for {description}: "
        f"PC={emulator.pyboy.register_file.PC:#06x}, "
        f"SP={emulator.pyboy.register_file.SP:#06x}, "
        f"stack={bytes(emulator.pyboy.memory[emulator.pyboy.register_file.SP + i] for i in range(12)).hex()}, "
        f"LCDC={emulator.pyboy.memory[0xFF40]:#04x}, "
        f"owner={emulator.read('wRendererOwner')}, "
        f"phase={emulator.read('wRendererPhase')}, "
        f"control={emulator.read('wFullColorPhase5ScenarioControl')}, "
        f"scenario={emulator.read('wFullColorPhase5Scenario')}, "
        f"state={emulator.read('wFullColorPhase5ScenarioState')}, "
        f"result={emulator.read('wFullColorPhase5ScenarioResult')}, "
        f"barrier={emulator.read('wFullColorPhase5BarrierState')}, "
        f"stable={emulator.read('wFullColorPhase5StableFrames')}"
    )


def _generation(emulator: Emulator) -> int:
    return int.from_bytes(emulator.read_bytes("wRendererGeneration", 4), "little")


def _linked_rom_bytes(emulator: Emulator, start: str, end: str) -> bytes:
    bank = emulator.symbol_banks[start]
    assert emulator.symbol_banks[end] == bank
    address = emulator.symbols[start]
    size = emulator.symbols[end] - address
    offset = address if bank == 0 else bank * 0x4000 + address - 0x4000
    return emulator.rom.read_bytes()[offset:offset + size]


def _banked_rom_bytes(emulator: Emulator, bank: int, address: int, size: int) -> bytes:
    offset = address if bank == 0 else bank * 0x4000 + address - 0x4000
    return emulator.rom.read_bytes()[offset:offset + size]


def _transformed_palette(source: bytes) -> bytes:
    transformed = bytearray()
    for low, high in zip(source[::2], source[1::2], strict=True):
        transformed.extend((0x1F - (low & 0x1F), (high & 0x7C) ^ 0x7C))
    return bytes(transformed)


def _visible_vram(emulator: Emulator, bank: int, base: int = VBG_MAP_0) -> bytes:
    return b"".join(
        emulator.read_vram_bank(
            bank, base + row * 32, SCREEN_WIDTH,
        )
        for row in range(SCREEN_HEIGHT)
    )


def _rgb555(color: bytes) -> tuple[int, int, int]:
    value = int.from_bytes(color, "little")
    return tuple(((value >> shift) & 0x1F) << 3 for shift in (0, 5, 10))


def _render_background(
    tiles: bytes,
    attributes: bytes,
    palettes: bytes,
    graphics: tuple[bytes, bytes],
    lcdc: int,
) -> Image.Image:
    image = Image.new("RGB", (SCREEN_WIDTH * 8, SCREEN_HEIGHT * 8))
    output = image.load()
    for index, (tile, attribute) in enumerate(zip(tiles, attributes, strict=True)):
        signed_tile = tile if tile < 0x80 else tile - 0x100
        address = tile * 16 if lcdc & 0x10 else 0x1000 + signed_tile * 16
        pattern = graphics[(attribute >> 3) & 1][address:address + 16]
        for y in range(8):
            source_y = 7 - y if attribute & 0x40 else y
            low, high = pattern[source_y * 2:source_y * 2 + 2]
            for x in range(8):
                source_x = 7 - x if attribute & 0x20 else x
                bit = 7 - source_x
                color = ((high >> bit) & 1) << 1 | ((low >> bit) & 1)
                palette = (attribute & 7) * 8 + color * 2
                output[(index % SCREEN_WIDTH) * 8 + x, (index // SCREEN_WIDTH) * 8 + y] = (
                    _rgb555(palettes[palette:palette + 2])
                )
    return image


def _oam_pixels(oam: bytes) -> set[tuple[int, int]]:
    covered: set[tuple[int, int]] = set()
    for offset in range(0, len(oam), 4):
        y, x = oam[offset] - 16, oam[offset + 1] - 8
        if oam[offset] == 0 or oam[offset + 1] == 0:
            continue
        covered.update(
            (pixel_x, pixel_y)
            for pixel_y in range(max(0, y), min(SCREEN_HEIGHT * 8, y + 8))
            for pixel_x in range(max(0, x), min(SCREEN_WIDTH * 8, x + 8))
        )
    return covered


def _write_machine_canary(emulator: Emulator) -> None:
    pyboy = emulator.pyboy
    saved_svbk = pyboy.memory[0xFF70]
    pyboy.memory[0xFF70] = MACHINE_CANARY_BANK
    try:
        for offset, value in enumerate(MACHINE_CANARY):
            pyboy.memory[MACHINE_CANARY_ADDRESS + offset] = value
    finally:
        pyboy.memory[0xFF70] = saved_svbk


def _read_machine_canary(emulator: Emulator) -> bytes:
    pyboy = emulator.pyboy
    saved_svbk = pyboy.memory[0xFF70]
    pyboy.memory[0xFF70] = MACHINE_CANARY_BANK
    try:
        return bytes(
            pyboy.memory[MACHINE_CANARY_ADDRESS + offset]
            for offset in range(len(MACHINE_CANARY))
        )
    finally:
        pyboy.memory[0xFF70] = saved_svbk


def test_phase5_party_round_trip_uses_start_and_party_input() -> None:
    product = "pokeyellow_phase2_audit"
    results = result_directory("phase5-party-natural-input")
    constants = numeric_symbols(REPOSITORY_ROOT / f"{product}.sym")
    emulator = Emulator(
        rom=REPOSITORY_ROOT / f"{product}.gbc",
        symbols=REPOSITORY_ROOT / f"{product}.sym",
        results=results,
        cgb=True,
    )
    try:
        complete_oaks_lab_intro(emulator)
        _wait(
            emulator,
            lambda: emulator.read("wRendererOwner")
            == constants["RENDERER_FULL_COLOR_OVERWORLD"],
            "retained Color owner in Pallet/Route 1",
        )
        initial_generation = _generation(emulator)
        pyboy = emulator.pyboy
        loaded_bank = emulator.symbols["hLoadedROMBank"]
        font_source = _linked_rom_bytes(emulator, "FontGraphics", "FontGraphicsEnd")
        expected_font = b"".join(bytes((value, value)) for value in font_source)
        expected_textbox = _linked_rom_bytes(
            emulator, "TextBoxGraphics", "TextBoxGraphicsEnd",
        )
        expected_hp_status = _linked_rom_bytes(
            emulator, "HpBarAndStatusGraphics", "HpBarAndStatusGraphicsEnd",
        )
        expected_color_attributes = _linked_rom_bytes(
            emulator,
            "FullColorOverworldTileAttributes",
            "FullColorOverworldTileAttributesEnd",
        )
        expected_color_bg_palettes = _linked_rom_bytes(
            emulator, "FullColorOverworldBGPalettes", "FullColorOverworldBGPalettesEnd",
        )
        expected_color_obj_palettes = _linked_rom_bytes(
            emulator, "FullColorCanaryOBJPalettes", "FullColorCanaryOBJPalettesEnd",
        )
        machine_sites: dict[str, list[tuple[int, int, int, int, int]]] = {
            name: []
            for name in (
                "FullColorPhase5PartyHandoffToYellowStart",
                "FullColorPhase5PartyHandoffToYellowEnd",
                "FullColorPhase5PartyHandoffToColorStart",
                "FullColorPhase5PartyHandoffToColorEnd",
                "FullColorPhase5VBlankOrigin",
                "FullColorPhase5VBlankHandlerEnd",
            )
        }
        deadline_counts = {
            "FullColorPhase5PartyHandoffToYellowDeadline": 0,
            "FullColorPhase5PartyHandoffToColorDeadline": 0,
        }
        yellow_presentation: dict[str, bytes] = {}
        color_presentation: dict[str, bytes | int] = {}
        producer_names = (
            "LoadFontTilePatterns",
            "LoadTextBoxTilePatterns",
            "LoadHpBarAndStatusTilePatterns",
            "ClearSprites",
            "LoadMonPartySpriteGfxLCDAlreadyDisabled",
            "WriteMonPartySpriteOAM",
            "RunPaletteCommand",
            "LoadBGMapAttributes",
        )
        producer_calls = dict.fromkeys(producer_names, 0)
        producer_order: list[str] = []
        color_producer_names = (
            "LoadMapHeader",
            "InitMapSprites",
            "LoadTileBlockMap",
            "LoadTilesetTilePatternData",
            "LoadCurrentMapView",
            "ReconstructFullColorMapEntry",
            "LoadPlayerSpriteGraphics",
            "PrepareFullColorOAMDataForOwnedVBlank",
        )
        color_producer_calls = dict.fromkeys(color_producer_names, 0)
        color_producer_order: list[str] = []
        forbidden_calls = {
            name: 0
            for name in (
                "RestoreScreenTilesAndReloadTilePatterns",
                "LoadScreenTilesFromBuffer1",
                "LoadScreenTilesFromBuffer2",
                "LoadScreenTilesFromBuffer2DisableBGTransfer",
                "PassiveFullColorScheduleAttributeRestore",
                "PassiveFullColorRestoreAfterMenu",
                "PassiveFullColorHomogenizeBGPalettes",
                "PassiveFullColorCommitPalettes",
                "PassiveFullColorCommitVisibleAttributes",
            )
        }
        vblank_stage = ["before"]
        vblank_frames = {
            stage: {"origin": [], "end": []}
            for stage in ("before", "after")
        }

        def record_machine_site(name: str):
            def record(_: object) -> None:
                machine_sites[name].append((
                    pyboy.memory[loaded_bank],
                    pyboy.register_file.SP,
                    pyboy.memory[0xFF70],
                    pyboy.memory[0xFFFF],
                    pyboy.memory[0xFF0F],
                ))
                stage = vblank_stage[0]
                if stage in vblank_frames:
                    if name == "FullColorPhase5VBlankOrigin":
                        vblank_frames[stage]["origin"].append(
                            machine_sites[name][-1][:4]
                        )
                    elif name == "FullColorPhase5VBlankHandlerEnd":
                        vblank_frames[stage]["end"].append(
                            machine_sites[name][-1][:4]
                        )

            return record

        def count_deadline(name: str):
            def count(_: object) -> None:
                deadline_counts[name] += 1
                if name == "FullColorPhase5PartyHandoffToColorDeadline":
                    assert pyboy.memory[0xFF40] & 0x80 == 0
                    tileset_bank = emulator.read("wTilesetBank")
                    tileset_pointer = int.from_bytes(
                        emulator.read_bytes("wTilesetGfxPtr", 2), "little",
                    )
                    color_presentation.update({
                        "tileset_bank": tileset_bank,
                        "tileset_pointer": tileset_pointer,
                        "tileset_source": _banked_rom_bytes(
                            emulator, tileset_bank, tileset_pointer, TILESET_BYTES,
                        ),
                        "tileset_gfx": emulator.read_vram_bank(
                            0, VTILESET, TILESET_BYTES,
                        ),
                        "logical_tiles": emulator.read_bytes(
                            "wTileMap", SCREEN_WIDTH * SCREEN_HEIGHT,
                        ),
                        "visible_tiles": _visible_vram(emulator, 0, VBG_MAP_0),
                        "visible_attributes": _visible_vram(emulator, 1, VBG_MAP_0),
                        "bg_palette_state": emulator.read_bytes(
                            "wFullColorBGPaletteBase", 128,
                        ),
                        "obj_palette_state": emulator.read_bytes(
                            "wFullColorOBJPaletteBase", 128,
                        ),
                        "bg_hardware_palettes": emulator.read_palette_ram(),
                        "obj_hardware_palettes": emulator.read_palette_ram(
                            object_palettes=True,
                        ),
                        "shadow_oam": emulator.read_bytes("wShadowOAM", 160),
                            "hardware_oam": emulator.read_memory(0xFE00, 160),
                            "graphics0": emulator.read_vram_bank(0, 0x8000, 0x1800),
                            "graphics1": emulator.read_vram_bank(1, 0x8000, 0x1800),
                            "lcdc": pyboy.memory[0xFF40],
                    })
                    return
                if name != "FullColorPhase5PartyHandoffToYellowDeadline":
                    return
                assert pyboy.memory[0xFF40] & 0x80 == 0
                assert pyboy.memory[0xFF40] & 0x60 == 0x60
                assert pyboy.memory[0xFF4A] == 0
                assert pyboy.memory[0xFF4B] == 7
                vfont = emulator.symbols["vFont"]
                vchars2 = emulator.symbols["vChars2"]
                yellow_presentation.update({
                    "font": emulator.read_vram_bank(0, vfont, len(expected_font)),
                    "textbox_prefix": emulator.read_vram_bank(0, vchars2 + 0x600, 0x20),
                    "hp_status": emulator.read_vram_bank(
                        0, vchars2 + 0x620, len(expected_hp_status),
                    ),
                    "logical_tiles": emulator.read_bytes(
                        "wTileMap", SCREEN_WIDTH * SCREEN_HEIGHT,
                    ),
                    "hidden_bg_tiles": _visible_vram(emulator, 0, VBG_MAP_0),
                    "visible_tiles": _visible_vram(emulator, 0, VBG_MAP_1),
                    "visible_attributes": _visible_vram(emulator, 1, VBG_MAP_1),
                    "shadow_oam": emulator.read_bytes("wShadowOAM", 160),
                    "saved_party_oam": emulator.read_bytes(
                        "wMonPartySpritesSavedOAM", 96,
                    ),
                    "hardware_oam": emulator.read_memory(0xFE00, 160),
                })

            return count

        def count_producer(name: str):
            def count(_: object) -> None:
                if (
                    emulator.read("wFullColorPhase5ScenarioControl")
                    == constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN"]
                    and emulator.read("wRendererPhase")
                    == constants["YELLOW_RECONSTRUCTING"]
                ):
                    producer_calls[name] += 1
                    producer_order.append(name)

            return count

        def count_color_producer(name: str):
            def count(_: object) -> None:
                if (
                    emulator.read("wFullColorPhase5ScenarioControl")
                    == constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN"]
                    and emulator.read("wRendererPhase")
                    == constants["OVERWORLD_RECONSTRUCTING"]
                ):
                    color_producer_calls[name] += 1
                    color_producer_order.append(name)

            return count

        def count_forbidden(name: str):
            def count(_: object) -> None:
                forbidden_calls[name] += 1

            return count

        hooks: list[tuple[int, int]] = []
        for name in machine_sites:
            key = (emulator.symbol_banks[name], emulator.symbols[name])
            pyboy.hook_register(*key, record_machine_site(name), None)
            hooks.append(key)
        for name in deadline_counts:
            key = (emulator.symbol_banks[name], emulator.symbols[name])
            pyboy.hook_register(*key, count_deadline(name), None)
            hooks.append(key)
        _write_machine_canary(emulator)

        # Establish ordinary retained-overworld VBlank machine state before the
        # menu changes owner. The handler must return to its exact caller state.
        emulator.tick(2)
        assert vblank_frames["before"]["end"]
        color_oracle = {
            "logical_tiles": emulator.read_bytes(
                "wTileMap", SCREEN_WIDTH * SCREEN_HEIGHT,
            ),
            "visible_tiles": _visible_vram(emulator, 0, VBG_MAP_0),
            "visible_attributes": _visible_vram(emulator, 1, VBG_MAP_0),
            "bg_palettes": emulator.read_palette_ram(),
            "obj_palettes": emulator.read_palette_ram(object_palettes=True),
            "tileset_gfx": emulator.read_vram_bank(0, VTILESET, TILESET_BYTES),
        }
        emulator.save_screenshot("phase5-party-color-oracle.png")
        vblank_stage[0] = "route"

        emulator.pyboy.button("start", delay=10)
        _wait(
            emulator,
            lambda: emulator.read("wMaxMenuItem") in (6, 7)
            and emulator.read("wMenuWatchedKeys") == PAD_START_MENU,
            "natural Start menu",
        )
        pokemon_index = 1 if emulator.read("wMaxMenuItem") == 7 else 0
        move_cursor_to(
            emulator,
            "wCurrentMenuItem",
            pokemon_index,
            description="the Start-menu Pokemon item",
        )
        emulator.write(
            "wFullColorPhase5Scenario",
            constants["FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_YELLOW"],
        )
        emulator.write(
            "wFullColorPhase5ScenarioMutation",
            constants["FULL_COLOR_PHASE5_MUTATION_NONE"],
        )
        emulator.write(
            "wFullColorPhase5ScenarioControl",
            constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
        )
        # From the armed input edge onward, both directions must use fresh
        # logical/ROM producers, never saved-screen or passive repair authority.
        for name in forbidden_calls:
            key = (emulator.symbol_banks[name], emulator.symbols[name])
            pyboy.hook_register(*key, count_forbidden(name), None)
            hooks.append(key)
        for name in producer_names:
            key = (emulator.symbol_banks[name], emulator.symbols[name])
            pyboy.hook_register(*key, count_producer(name), None)
            hooks.append(key)
        for name in color_producer_names:
            key = (emulator.symbol_banks[name], emulator.symbols[name])
            pyboy.hook_register(*key, count_color_producer(name), None)
            hooks.append(key)

        emulator.pyboy.button("a", delay=10)
        _wait(
            emulator,
            lambda: emulator.read("wFullColorPhase5ScenarioState")
            == constants["FULL_COLOR_PHASE5_SCENARIO_STATE_STABLE"]
            and emulator.read("wFullColorPhase5StableFrames") == 5,
            "five stable Yellow Party frames",
        )
        assert _generation(emulator) == initial_generation + 1
        assert emulator.read("wRendererOwner") == constants["RENDERER_YELLOW"]
        assert emulator.read("wRendererPhase") == constants["YELLOW_ACTIVE"]
        assert emulator.read("wFullColorPartyReturnPending") == 1
        assert emulator.read("wFullColorPhase5PoisonMask") == constants[
            "FULL_COLOR_PHASE5_LEDGER_ALL"
        ]
        assert emulator.read("wFullColorPhase5YellowLedgerMask") == constants[
            "FULL_COLOR_PHASE5_LEDGER_ALL"
        ]
        assert emulator.read("wFullColorPhase5ScenarioFlags") == 0xFF
        assert producer_calls == {
            "LoadFontTilePatterns": 1,
            "LoadTextBoxTilePatterns": 1,
            "LoadHpBarAndStatusTilePatterns": 1,
            "ClearSprites": 1,
            "LoadMonPartySpriteGfxLCDAlreadyDisabled": 1,
            "WriteMonPartySpriteOAM": emulator.read("wPartyCount"),
            # One HP-bar command per mon plus the final Party-wide command.
            "RunPaletteCommand": emulator.read("wPartyCount") + 1,
            "LoadBGMapAttributes": 1,
        }
        assert producer_order.index("LoadFontTilePatterns") < producer_order.index(
            "LoadTextBoxTilePatterns"
        ) < producer_order.index("LoadHpBarAndStatusTilePatterns")
        assert producer_order.index("ClearSprites") < producer_order.index(
            "WriteMonPartySpriteOAM"
        )
        assert yellow_presentation["font"] == expected_font
        assert yellow_presentation["textbox_prefix"] == expected_textbox[:0x20]
        assert yellow_presentation["hp_status"] == expected_hp_status
        assert yellow_presentation["visible_tiles"] == yellow_presentation["logical_tiles"]
        assert yellow_presentation["hidden_bg_tiles"] == (
            bytes((POISONED_TILE_DATA,)) * SCREEN_WIDTH * SCREEN_HEIGHT
        )
        assert yellow_presentation["logical_tiles"][3 * SCREEN_WIDTH:16 * SCREEN_WIDTH] == (
            bytes((0x7F,)) * 13 * SCREEN_WIDTH
        )
        assert yellow_presentation["visible_attributes"] != (
            bytes((POISONED_ATTRIBUTES,)) * SCREEN_WIDTH * SCREEN_HEIGHT
        )
        shadow_oam = yellow_presentation["shadow_oam"]
        assert shadow_oam == yellow_presentation["hardware_oam"]
        assert yellow_presentation["saved_party_oam"] == shadow_oam[:96]
        party_oam_extent = emulator.read("wPartyCount") * 4 * 4
        assert any(shadow_oam[:party_oam_extent])
        assert shadow_oam[party_oam_extent:] == bytes(160 - party_oam_extent)
        for offset in range(0, party_oam_extent, 4):
            tile_id = shadow_oam[offset + 2]
            tile_bank = (shadow_oam[offset + 3] >> 3) & 1
            assert emulator.read_vram_bank(
                tile_bank, 0x8000 + tile_id * 16, 16,
            ) != bytes((POISONED_TILE_DATA,)) * 16
        # Yellow's Party palette is intentionally monochrome, but the stable
        # frame must contain both foreground glyph/icon pixels and background.
        assert len(set(
            pyboy.screen.image.convert("RGB").get_flattened_data()
        )) >= 2
        emulator.save_screenshot("phase5-party-yellow-stable.png")

        emulator.pyboy.button("b", delay=10)
        _wait(
            emulator,
            lambda: emulator.read("wFullColorPhase5ScenarioState")
            == constants["FULL_COLOR_PHASE5_SCENARIO_STATE_COMPLETE"]
            and emulator.read("wFullColorPhase5StableFrames") == 5,
            "fresh Color map and five stable return frames",
        )
        assert _generation(emulator) == initial_generation + 2
        assert emulator.read("wRendererOwner") == constants[
            "RENDERER_FULL_COLOR_OVERWORLD"
        ]
        assert emulator.read("wRendererPhase") == constants["OVERWORLD_ACTIVE"]
        assert emulator.read("wRendererAdmissionOpen") == 1
        assert emulator.read("wFullColorPartyReturnPending") == 0
        assert emulator.read("wFullColorPhase5ScenarioResult") == constants[
            "FULL_COLOR_PHASE5_SCENARIO_RESULT_PASSED"
        ]
        assert emulator.read("wFullColorPhase5ColorLedgerMask") == constants[
            "FULL_COLOR_PHASE5_LEDGER_ALL"
        ]
        assert emulator.read_palette_ram() == expected_color_bg_palettes
        assert emulator.read_palette_ram(object_palettes=True) == expected_color_obj_palettes
        assert color_producer_calls == dict.fromkeys(color_producer_names, 1)
        assert color_producer_order == list(color_producer_names)
        assert color_presentation["tileset_gfx"] == color_presentation["tileset_source"]
        assert color_presentation["logical_tiles"] == color_oracle["logical_tiles"]
        assert color_presentation["visible_tiles"] == color_presentation["logical_tiles"]
        expected_return_attributes = bytes(
            expected_color_attributes[tile]
            for tile in color_presentation["logical_tiles"]
        )
        assert color_presentation["visible_attributes"] == expected_return_attributes
        # The retained overworld can have animation/replacement bytes in the
        # pre-handoff physical map that intentionally differ from its logical
        # authority.  Returning from Party must discard that stale physical
        # image and rebuild the active map from the unchanged logical map.
        stale_physical_tiles = {
            index
            for index, (physical, logical) in enumerate(zip(
                color_oracle["visible_tiles"], color_oracle["logical_tiles"],
            ))
            if physical != logical
        }
        assert stale_physical_tiles
        assert color_presentation["visible_tiles"] != color_oracle["visible_tiles"]
        assert color_presentation["bg_palette_state"] == (
            expected_color_bg_palettes + _transformed_palette(expected_color_bg_palettes)
        )
        assert color_presentation["obj_palette_state"] == (
            expected_color_obj_palettes + _transformed_palette(expected_color_obj_palettes)
        )
        assert color_presentation["bg_hardware_palettes"] == expected_color_bg_palettes
        assert color_presentation["obj_hardware_palettes"] == expected_color_obj_palettes
        assert color_presentation["shadow_oam"] == color_presentation["hardware_oam"]
        assert pyboy.memory[0xFF43] == emulator.read("hSCX")
        assert pyboy.memory[0xFF42] == emulator.read("hSCY")
        assert pyboy.memory[0xFF4A] == emulator.read("hWY")
        assert pyboy.memory[0xFF4B] == 7
        vblank_stage[0] = "after"
        emulator.tick(2)
        assert vblank_frames["after"]["end"]
        for frames in vblank_frames.values():
            assert frames["origin"]
            assert set(frames["end"]) <= set(frames["origin"])
        for start, end in (
            (
                "FullColorPhase5PartyHandoffToYellowStart",
                "FullColorPhase5PartyHandoffToYellowEnd",
            ),
            (
                "FullColorPhase5PartyHandoffToColorStart",
                "FullColorPhase5PartyHandoffToColorEnd",
            ),
        ):
            assert len(machine_sites[start]) == len(machine_sites[end]) == 1
            assert machine_sites[start] == machine_sites[end]
        assert deadline_counts == {
            "FullColorPhase5PartyHandoffToYellowDeadline": 1,
            "FullColorPhase5PartyHandoffToColorDeadline": 1,
        }
        assert forbidden_calls == dict.fromkeys(forbidden_calls, 0)
        assert _read_machine_canary(emulator) == MACHINE_CANARY
        color_frame = pyboy.screen.image.convert("RGB")
        completed_tiles = _visible_vram(emulator, 0, VBG_MAP_0)
        completed_attributes = _visible_vram(emulator, 1, VBG_MAP_0)
        completed_palettes = emulator.read_palette_ram()
        completed_oam = emulator.read_memory(0xFE00, 160)
        software_background = _render_background(
            completed_tiles,
            completed_attributes,
            completed_palettes,
            (
                emulator.read_vram_bank(0, 0x8000, 0x1800),
                emulator.read_vram_bank(1, 0x8000, 0x1800),
            ),
            pyboy.memory[0xFF40],
        )
        covered_by_oam = _oam_pixels(completed_oam)
        actual_pixels = color_frame.load()
        expected_pixels = software_background.load()
        assert all(
            actual_pixels[x, y] == expected_pixels[x, y]
            for y in range(SCREEN_HEIGHT * 8)
            for x in range(SCREEN_WIDTH * 8)
            if (x, y) not in covered_by_oam
        )
        assert color_oracle["tileset_gfx"] == color_presentation["tileset_gfx"]
        emulator.save_screenshot("phase5-party-color-stable.png")
    except BaseException:
        emulator.save_screenshot("phase5-party-natural-input-failure.png")
        raise
    finally:
        for bank, address in locals().get("hooks", ()):
            emulator.pyboy.hook_deregister(bank, address)
        emulator.close()


def test_phase5_party_skipped_font_stays_poisoned_and_never_presents() -> None:
    product = "pokeyellow_phase2_audit"
    constants = numeric_symbols(REPOSITORY_ROOT / f"{product}.sym")
    emulator = Emulator(
        rom=REPOSITORY_ROOT / f"{product}.gbc",
        symbols=REPOSITORY_ROOT / f"{product}.sym",
        results=result_directory("phase5-party-skipped-font"),
        cgb=True,
    )
    hooks: list[tuple[int, int]] = []
    try:
        complete_oaks_lab_intro(emulator)
        _wait(
            emulator,
            lambda: emulator.read("wRendererOwner")
            == constants["RENDERER_FULL_COLOR_OVERWORLD"],
            "retained Color owner before skipped-font Party entry",
        )
        emulator.pyboy.button("start", delay=10)
        _wait(
            emulator,
            lambda: emulator.read("wMaxMenuItem") in (6, 7)
            and emulator.read("wMenuWatchedKeys") == PAD_START_MENU,
            "natural Start menu before skipped-font Party entry",
        )
        pokemon_index = 1 if emulator.read("wMaxMenuItem") == 7 else 0
        move_cursor_to(
            emulator,
            "wCurrentMenuItem",
            pokemon_index,
            description="the Start-menu Pokemon item",
        )
        emulator.write(
            "wFullColorPhase5Scenario",
            constants["FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_YELLOW"],
        )
        emulator.write(
            "wFullColorPhase5ScenarioMutation",
            constants["FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM"],
        )
        emulator.write(
            "wFullColorPhase5ScenarioControl",
            constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
        )
        calls = dict.fromkeys((
            "LoadFontTilePatterns",
            "LoadTextBoxTilePatterns",
            "LoadHpBarAndStatusTilePatterns",
            "ClearSprites",
            "LoadMonPartySpriteGfxLCDAlreadyDisabled",
            "WriteMonPartySpriteOAM",
        ), 0)
        deadline_count = [0]

        def count_call(name: str):
            def count(_: object) -> None:
                if (
                    emulator.read("wFullColorPhase5ScenarioControl")
                    == constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN"]
                ):
                    calls[name] += 1

            return count

        for name in calls:
            key = (emulator.symbol_banks[name], emulator.symbols[name])
            emulator.pyboy.hook_register(*key, count_call(name), None)
            hooks.append(key)
        deadline = "FullColorPhase5PartyHandoffToYellowDeadline"
        key = (emulator.symbol_banks[deadline], emulator.symbols[deadline])
        emulator.pyboy.hook_register(
            *key, lambda _: deadline_count.__setitem__(0, deadline_count[0] + 1), None,
        )
        hooks.append(key)

        emulator.pyboy.button("a", delay=10)
        _wait(
            emulator,
            lambda: emulator.read("wFullColorPhase5ScenarioState")
            == constants["FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED"],
            "skipped-font reconstruction failure before presentation",
        )

        expected_textbox = _linked_rom_bytes(
            emulator, "TextBoxGraphics", "TextBoxGraphicsEnd",
        )
        expected_hp_status = _linked_rom_bytes(
            emulator, "HpBarAndStatusGraphics", "HpBarAndStatusGraphicsEnd",
        )
        vfont = emulator.symbols["vFont"]
        vchars2 = emulator.symbols["vChars2"]
        assert calls == {
            "LoadFontTilePatterns": 0,
            "LoadTextBoxTilePatterns": 1,
            "LoadHpBarAndStatusTilePatterns": 1,
            "ClearSprites": 1,
            "LoadMonPartySpriteGfxLCDAlreadyDisabled": 1,
            "WriteMonPartySpriteOAM": emulator.read("wPartyCount"),
        }
        assert emulator.read_vram_bank(0, vfont, 0x800) == bytes(
            (POISONED_TILE_DATA,)
        ) * 0x800
        assert emulator.read_vram_bank(0, vchars2 + 0x600, 0x20) == expected_textbox[:0x20]
        assert emulator.read_vram_bank(
            0, vchars2 + 0x620, len(expected_hp_status),
        ) == expected_hp_status
        assert emulator.read("wFullColorPhase5ScenarioFlags") == 0xFE
        assert emulator.read("wFullColorPhase5YellowLedgerMask") == (
            constants["FULL_COLOR_PHASE5_LEDGER_ALL"]
            ^ constants["FULL_COLOR_PHASE5_LEDGER_TILES_REPLACEMENTS"]
        )
        assert deadline_count == [0]
        assert emulator.read("wFullColorPhase5BarrierState") == 0
        assert emulator.read("wRendererAdmissionOpen") == 0
        assert emulator.read("wFullColorPartyReturnPending") == 1
        assert emulator.pyboy.memory[0xFF40] & 0x80 == 0
    except BaseException:
        emulator.save_screenshot("phase5-party-skipped-font-failure.png")
        raise
    finally:
        for bank, address in hooks:
            emulator.pyboy.hook_deregister(bank, address)
        emulator.close()


@pytest.mark.parametrize(
    ("mutation", "expected_calls"),
    (
        ("FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM", 0),
        ("FULL_COLOR_PHASE5_MUTATION_WRONG_BANK", 1),
        ("FULL_COLOR_PHASE5_MUTATION_STALE_AUTHORITY", 1),
    ),
)
def test_phase5_party_color_tileset_hostiles_fail_before_presentation(
    mutation: str, expected_calls: int,
) -> None:
    product = "pokeyellow_phase2_audit"
    constants = numeric_symbols(REPOSITORY_ROOT / f"{product}.sym")
    emulator = Emulator(
        rom=REPOSITORY_ROOT / f"{product}.gbc",
        symbols=REPOSITORY_ROOT / f"{product}.sym",
        results=result_directory(f"phase5-party-color-tileset-{mutation.lower()}"),
        cgb=True,
    )
    hooks: list[tuple[int, int]] = []
    try:
        complete_oaks_lab_intro(emulator)
        _wait(
            emulator,
            lambda: emulator.read("wRendererOwner")
            == constants["RENDERER_FULL_COLOR_OVERWORLD"],
            "retained Color owner before Color-tileset hostile",
        )
        _write_machine_canary(emulator)
        # Establish the retained VBlank return snapshot used by the machine-
        # state reconstruction ledger before changing owner.
        emulator.tick(2)
        expected_bank = emulator.read("wTilesetBank")
        expected_pointer = int.from_bytes(
            emulator.read_bytes("wTilesetGfxPtr", 2), "little",
        )
        expected_tileset = _banked_rom_bytes(
            emulator, expected_bank, expected_pointer, TILESET_BYTES,
        )

        emulator.pyboy.button("start", delay=10)
        _wait(
            emulator,
            lambda: emulator.read("wMaxMenuItem") in (6, 7)
            and emulator.read("wMenuWatchedKeys") == PAD_START_MENU,
            "natural Start menu before Color-tileset hostile",
        )
        pokemon_index = 1 if emulator.read("wMaxMenuItem") == 7 else 0
        move_cursor_to(
            emulator,
            "wCurrentMenuItem",
            pokemon_index,
            description="the Start-menu Pokemon item",
        )
        emulator.write(
            "wFullColorPhase5Scenario",
            constants["FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_YELLOW"],
        )
        emulator.write(
            "wFullColorPhase5ScenarioMutation",
            constants["FULL_COLOR_PHASE5_MUTATION_NONE"],
        )
        emulator.write(
            "wFullColorPhase5ScenarioControl",
            constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
        )
        emulator.pyboy.button("a", delay=10)
        _wait(
            emulator,
            lambda: emulator.read("wFullColorPhase5ScenarioState")
            == constants["FULL_COLOR_PHASE5_SCENARIO_STATE_STABLE"],
            "stable Yellow Party before Color-tileset hostile",
        )

        producer_calls = {"start": 0, "return": 0, "transfer": 0}
        lifecycle_calls = {name: 0 for name in (
            "FullColorPhase5PartyHandoffToColorStart",
            "FullColorPhase5PartyHandoffToColorEnd",
            "FullColorPhase5PartyReconstructColorStart",
            "FullColorPhase5PartyHandoffToColorFailedSelected",
            "FullColorPhase5PartyHandoffToColorFailedOutside",
            "FullColorPhase5PartyHandoffToColorDeferredSelected",
            "FullColorPhase5PartyHandoffToColorNotRunning",
        )}
        deadline_calls = [0]
        inside_tileset_producer = [False]

        def inject_at_producer_start(_: object) -> None:
            producer_calls["start"] += 1
            inside_tileset_producer[0] = True
            # Keep the natural Yellow-to-Color handoff valid, then select and
            # inject the hostile condition at the exact fresh-authority seam.
            # The reconstruction gate must reject it before presentation.
            emulator.write("wFullColorPhase5ScenarioMutation", constants[mutation])
            if mutation == "FULL_COLOR_PHASE5_MUTATION_WRONG_BANK":
                emulator.write("wTilesetBank", (emulator.read("wTilesetBank") + 1) & 0xFF)
                return
            if mutation == "FULL_COLOR_PHASE5_MUTATION_STALE_AUTHORITY":
                emulator.write(
                    "wTilesetGfxPtr", (emulator.read("wTilesetGfxPtr") + 1) & 0xFF,
                )
                return
            # Concrete skipped-producer injection: return to the exact linked
            # caller continuation before any source/bank/VRAM instruction runs.
            regs = emulator.pyboy.register_file
            stack = regs.SP
            return_address = (
                emulator.pyboy.memory[stack]
                | emulator.pyboy.memory[(stack + 1) & 0xFFFF] << 8
            )
            regs.SP = (stack + 2) & 0xFFFF
            regs.PC = return_address
            inside_tileset_producer[0] = False

        def count_producer_return(_: object) -> None:
            producer_calls["return"] += 1

        def count_tileset_transfer(_: object) -> None:
            if inside_tileset_producer[0]:
                producer_calls["transfer"] += 1
                inside_tileset_producer[0] = False

        name = "FullColorPhase5PartyColorTilesetProducerStart"
        key = (emulator.symbol_banks[name], emulator.symbols[name])
        emulator.pyboy.hook_register(*key, inject_at_producer_start, None)
        hooks.append(key)
        name = "FullColorPhase5PartyColorTilesetProducerReturn"
        key = (emulator.symbol_banks[name], emulator.symbols[name])
        emulator.pyboy.hook_register(*key, count_producer_return, None)
        hooks.append(key)
        name = "FarCopyData"
        key = (emulator.symbol_banks[name], emulator.symbols[name])
        emulator.pyboy.hook_register(*key, count_tileset_transfer, None)
        hooks.append(key)
        deadline = "FullColorPhase5PartyHandoffToColorDeadline"
        key = (emulator.symbol_banks[deadline], emulator.symbols[deadline])
        emulator.pyboy.hook_register(
            *key, lambda _: deadline_calls.__setitem__(0, deadline_calls[0] + 1), None,
        )
        hooks.append(key)
        for lifecycle_name in lifecycle_calls:
            key = (
                emulator.symbol_banks[lifecycle_name],
                emulator.symbols[lifecycle_name],
            )
            emulator.pyboy.hook_register(
                *key,
                lambda _, name=lifecycle_name: lifecycle_calls.__setitem__(
                    name, lifecycle_calls[name] + 1,
                ),
                None,
            )
            hooks.append(key)

        emulator.pyboy.button("b", delay=10)
        _wait(
            emulator,
            lambda: producer_calls["start"] == 1
            and emulator.read("wFullColorPhase5ScenarioState")
            == constants["FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED"],
            "Color-tileset hostile failure before presentation",
        )

        assert lifecycle_calls["FullColorPhase5PartyHandoffToColorEnd"] == 1, repr(
            lifecycle_calls
        )
        assert producer_calls == {
            "start": 1,
            "return": 1,
            "transfer": expected_calls,
        }, lifecycle_calls
        assert deadline_calls == [0]
        actual_tileset = emulator.read_vram_bank(0, VTILESET, TILESET_BYTES)
        assert actual_tileset != expected_tileset
        if mutation == "FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM":
            assert actual_tileset == bytes((POISONED_TILE_DATA,)) * TILESET_BYTES
            assert emulator.read("wFullColorPhase5ColorLedgerMask") == (
                constants["FULL_COLOR_PHASE5_LEDGER_ALL"]
                ^ constants["FULL_COLOR_PHASE5_LEDGER_TILES_REPLACEMENTS"]
            )
        elif mutation == "FULL_COLOR_PHASE5_MUTATION_WRONG_BANK":
            assert emulator.read("wTilesetBank") == (expected_bank + 1) & 0xFF
        else:
            assert int.from_bytes(
                emulator.read_bytes("wTilesetGfxPtr", 2), "little",
            ) == (expected_pointer & 0xFF00) | ((expected_pointer + 1) & 0xFF)
        assert emulator.read("wRendererAdmissionOpen") == 0
        assert emulator.read("wFullColorPartyReturnPending") == 1
        assert emulator.read("wFullColorPhase5BarrierState") == 0
        assert emulator.pyboy.memory[0xFF40] & 0x80 == 0
    except BaseException:
        emulator.save_screenshot("phase5-party-color-tileset-hostile-failure.png")
        raise
    finally:
        for bank, address in hooks:
            emulator.pyboy.hook_deregister(bank, address)
        emulator.close()


@pytest.mark.parametrize(
    ("hostile", "mutation", "target_half"),
    (
        ("skip-first-half", "FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM", 0),
        ("skip-second-half", "FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM", 1),
        ("wrong-bank", "FULL_COLOR_PHASE5_MUTATION_WRONG_BANK", 0),
        ("wrong-source", "FULL_COLOR_PHASE5_MUTATION_STALE_AUTHORITY", 0),
        ("wrong-destination", "FULL_COLOR_PHASE5_MUTATION_STALE_AUTHORITY", 0),
    ),
)
def test_phase5_party_color_player_copy_hostiles_fail_before_presentation(
    hostile: str, mutation: str, target_half: int,
) -> None:
    """Alter each real LCD-off player copy without exposing a partial frame."""

    product = "pokeyellow_phase2_audit"
    constants = numeric_symbols(REPOSITORY_ROOT / f"{product}.sym")
    emulator = Emulator(
        rom=REPOSITORY_ROOT / f"{product}.gbc",
        symbols=REPOSITORY_ROOT / f"{product}.sym",
        results=result_directory(f"phase5-party-color-player-{hostile}"),
        cgb=True,
    )
    hooks: list[tuple[int, int]] = []
    try:
        complete_oaks_lab_intro(emulator)
        _wait(
            emulator,
            lambda: emulator.read("wRendererOwner")
            == constants["RENDERER_FULL_COLOR_OVERWORLD"],
            "retained Color owner before player-copy hostile",
        )
        emulator.tick(2)
        expected_bank = emulator.symbol_banks["RedSprite"]
        expected_source = emulator.symbols["RedSprite"]
        expected_player = _banked_rom_bytes(
            emulator, expected_bank, expected_source, 0x180,
        )

        emulator.pyboy.button("start", delay=10)
        _wait(
            emulator,
            lambda: emulator.read("wMaxMenuItem") in (6, 7)
            and emulator.read("wMenuWatchedKeys") == PAD_START_MENU,
            "natural Start menu before player-copy hostile",
        )
        pokemon_index = 1 if emulator.read("wMaxMenuItem") == 7 else 0
        move_cursor_to(
            emulator,
            "wCurrentMenuItem",
            pokemon_index,
            description="the Start-menu Pokemon item",
        )
        emulator.write(
            "wFullColorPhase5Scenario",
            constants["FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_YELLOW"],
        )
        emulator.write(
            "wFullColorPhase5ScenarioMutation",
            constants["FULL_COLOR_PHASE5_MUTATION_NONE"],
        )
        emulator.write(
            "wFullColorPhase5ScenarioControl",
            constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
        )
        emulator.pyboy.button("a", delay=10)
        _wait(
            emulator,
            lambda: emulator.read("wFullColorPhase5ScenarioState")
            == constants["FULL_COLOR_PHASE5_SCENARIO_STATE_STABLE"],
            "stable Yellow Party before player-copy hostile",
        )

        copy_calls: list[tuple[int, int, int, int]] = []
        injection: list[tuple[int, int, int, int]] = []
        player_producer_active = [False]
        deadline_calls = [0]
        delay_while_hidden = [0]
        unrelated: dict[str, bytes] = {}

        def enter_player_producer(_: object) -> None:
            player_producer_active[0] = True
            emulator.write("wFullColorPhase5ScenarioMutation", constants[mutation])
            unrelated.update({
                "tileset": emulator.read_vram_bank(0, VTILESET, TILESET_BYTES),
                "tiles": _visible_vram(emulator, 0, VBG_MAP_0),
                "attributes": _visible_vram(emulator, 1, VBG_MAP_0),
                "palettes": emulator.read_palette_ram(),
            })

        def alter_player_copy(_: object) -> None:
            if not player_producer_active[0]:
                return
            regs = emulator.pyboy.register_file
            source = regs.D << 8 | regs.E
            destination = regs.HL
            copy_index = len(copy_calls)
            copy_calls.append((regs.B, source, destination, regs.C))
            if copy_index != target_half:
                return
            injection.append((regs.B, source, destination, regs.C))
            if hostile.startswith("skip-"):
                stack = regs.SP
                return_address = (
                    emulator.pyboy.memory[stack]
                    | emulator.pyboy.memory[(stack + 1) & 0xFFFF] << 8
                )
                regs.SP = (stack + 2) & 0xFFFF
                regs.PC = return_address
            elif hostile == "wrong-bank":
                regs.B = (regs.B + 1) & 0xFF
            elif hostile == "wrong-source":
                source = (source + 1) & 0xFFFF
                regs.D, regs.E = source >> 8, source & 0xFF
            else:
                destination = (destination + 0x10) & 0xFFFF
                regs.HL = destination

        def count_hidden_delay(_: object) -> None:
            if player_producer_active[0] and not emulator.pyboy.memory[0xFF40] & 0x80:
                delay_while_hidden[0] += 1

        for name, callback in (
            ("LoadPlayerSpriteGraphics", enter_player_producer),
            ("CopyVideoDataAlternate", alter_player_copy),
            ("DelayFrame", count_hidden_delay),
        ):
            key = (emulator.symbol_banks[name], emulator.symbols[name])
            emulator.pyboy.hook_register(*key, callback, None)
            hooks.append(key)
        deadline = "FullColorPhase5PartyHandoffToColorDeadline"
        key = (emulator.symbol_banks[deadline], emulator.symbols[deadline])
        emulator.pyboy.hook_register(
            *key, lambda _: deadline_calls.__setitem__(0, deadline_calls[0] + 1), None,
        )
        hooks.append(key)

        emulator.pyboy.button("b", delay=10)
        _wait(
            emulator,
            lambda: len(injection) == 1
            and emulator.read("wFullColorPhase5ScenarioState")
            == constants["FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED"],
            f"{hostile} player-copy failure before presentation",
        )

        assert copy_calls == [
            (expected_bank, expected_source, 0x8000, 0x0C),
            (expected_bank, expected_source + 0xC0, 0x8800, 0x0C),
        ]
        assert injection == [copy_calls[target_half]]
        first = emulator.read_vram_bank(0, 0x8000, 0xC0)
        second = emulator.read_vram_bank(0, 0x8800, 0xC0)
        poison = bytes((POISONED_TILE_DATA,)) * 0xC0
        if hostile == "skip-first-half":
            assert first == poison
            assert second == expected_player[0xC0:]
        elif hostile == "skip-second-half":
            assert first == expected_player[:0xC0]
            assert second == poison
        elif hostile == "wrong-bank":
            wrong = _banked_rom_bytes(
                emulator, (expected_bank + 1) & 0xFF, expected_source, 0xC0,
            )
            assert first == wrong != expected_player[:0xC0]
            assert second == expected_player[0xC0:]
        elif hostile == "wrong-source":
            assert first == _banked_rom_bytes(
                emulator, expected_bank, expected_source + 1, 0xC0,
            )
            assert first != expected_player[:0xC0]
            assert second == expected_player[0xC0:]
        else:
            assert first[:0x10] == poison[:0x10]
            assert first[0x10:] == expected_player[:0xB0]
            assert second == expected_player[0xC0:]

        # The player producer is last: corrupting it cannot disturb the already
        # rebuilt map, attributes, tileset, or authored hardware palettes.
        assert emulator.read_vram_bank(0, VTILESET, TILESET_BYTES) == unrelated["tileset"]
        assert _visible_vram(emulator, 0, VBG_MAP_0) == unrelated["tiles"]
        assert _visible_vram(emulator, 1, VBG_MAP_0) == unrelated["attributes"]
        assert emulator.read_palette_ram() == unrelated["palettes"]
        assert delay_while_hidden == [0]
        assert deadline_calls == [0]
        assert emulator.read("wRendererAdmissionOpen") == 0
        assert emulator.read("wFullColorPartyReturnPending") == 1
        assert emulator.read("wFullColorPhase5BarrierState") == 0
        assert emulator.pyboy.memory[0xFF40] & 0x80 == 0
    except BaseException:
        emulator.save_screenshot(f"phase5-party-color-player-{hostile}-failure.png")
        raise
    finally:
        for bank, address in hooks:
            emulator.pyboy.hook_deregister(bank, address)
        emulator.close()

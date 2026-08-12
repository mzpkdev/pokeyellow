"""Natural visual regression for Oak's Lab's Color-mode save confirmation."""

from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path

from PIL import Image, ImageChops

from tools.rom_tests.emulator import Emulator
from tools.rom_tests.scenarios.new_game import reach_bedroom_overworld
from tools.rom_tests.scenarios.oaks_lab import (
    OAKS_LAB,
    SCRIPT_OAKSLAB_PLAYER_DONT_GO_AWAY,
    walk_from_bedroom_to_oak,
)
from tools.rom_tests.scenarios.renderer_mode import move_cursor_to
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT, result_directory


LAB_TILESET = 5  # Oak's Lab uses Yellow's DOJO tileset.
START_MENU_SAVE_INDEX = 3  # A fresh game has no Pokédex entry.
TWO_OPTION_MENU = 0x14
PAD_A_OR_B = 0x03
WINDOW_MAP = 0x9C00
BACKGROUND_MAP = 0x9800
TILE_DATA = 0x8000
TILE_DATA_SIZE = 0x1800
RLCDC = 0xFF40
RWY = 0xFF4A
RWX = 0xFF4B
SCREEN_WIDTH = 20
SCREEN_HEIGHT = 18
PALETTE_MASK = 0x07
TEXT_PALETTE = 7
MOVING_WATER_TILE = 0x14
PRESENTED_MAP_UPDATE_SPRITES_ENTRY = 4

# PrintText's bottom dialogue box plus SaveTheGame_YesOrNo's hlcoord 0,7 box.
SAVE_UI_RECTS = ((0, 12, 20, 18), (0, 7, 6, 12))


def _linked_bytes(product: str, symbol: str, size: int) -> bytes:
    symbol_lines = (REPOSITORY_ROOT / f"{product}.sym").read_text(
        encoding="utf-8"
    ).splitlines()
    addresses = Emulator._parse_symbols(symbol_lines)
    banks = Emulator._parse_symbol_banks(symbol_lines)
    address = addresses[symbol]
    offset = banks[symbol] * 0x4000 + (address & 0x3FFF)
    return (REPOSITORY_ROOT / f"{product}.gbc").read_bytes()[offset : offset + size]


def _window_plane(emulator: Emulator, bank: int) -> bytes:
    return _tilemap_plane(emulator, bank, WINDOW_MAP)


def _tilemap_plane(emulator: Emulator, bank: int, base: int) -> bytes:
    return b"".join(
        emulator.read_vram_bank(bank, base + row * 32, SCREEN_WIDTH)
        for row in range(SCREEN_HEIGHT)
    )


def _tile_graphics(emulator: Emulator) -> tuple[bytes, bytes]:
    return tuple(
        emulator.read_vram_bank(bank, TILE_DATA, TILE_DATA_SIZE) for bank in (0, 1)
    )


def _graphics_offset(tile: int, lcdc: int) -> int:
    if lcdc & 0x10:
        return tile * 16
    signed_tile = tile if tile < 0x80 else tile - 0x100
    return 0x1000 + signed_tile * 16


def _used_graphics_bytes(
    tiles: bytes,
    attributes: bytes,
    lcdc: int,
) -> frozenset[tuple[int, int]]:
    used: set[tuple[int, int]] = set()
    for tile, attribute in zip(tiles, attributes, strict=True):
        bank = attribute >> 3 & 1
        offset = _graphics_offset(tile, lcdc)
        used.update(
            (bank, byte_offset) for byte_offset in range(offset, offset + 16)
        )
    return frozenset(used)


def _map_presentation(emulator: Emulator) -> dict[str, object]:
    lcdc = emulator.pyboy.memory[RLCDC]
    map_base = WINDOW_MAP if lcdc & 0x08 else BACKGROUND_MAP
    tiles = _tilemap_plane(emulator, 0, map_base)
    attributes = _tilemap_plane(emulator, 1, map_base)
    palettes = emulator.read_palette_ram()
    graphics = _tile_graphics(emulator)
    return {
        "frame": emulator.capture_screen(),
        "render": _render_tilemap_region(
            tiles,
            attributes,
            palettes,
            graphics,
            lcdc,
            (0, 0, SCREEN_WIDTH, SCREEN_HEIGHT),
        ),
        "tiles": tiles,
        "attributes": attributes,
        "palettes": palettes,
        "graphics": graphics,
        "tilemap": emulator.read_memory(
            emulator.symbols["wTileMap"], SCREEN_WIDTH * SCREEN_HEIGHT
        ),
        "lcdc": lcdc,
        "map_base": map_base,
        "wy": emulator.pyboy.memory[RWY],
        "wx": emulator.pyboy.memory[RWX],
    }


def _ui_cell_indexes() -> tuple[int, ...]:
    return tuple(
        row * SCREEN_WIDTH + column
        for left, top, right, bottom in SAVE_UI_RECTS
        for row in range(top, bottom)
        for column in range(left, right)
    )


def _rgb555(color: bytes) -> tuple[int, int, int]:
    value = int.from_bytes(color, "little")
    # PyBoy presents each CGB RGB555 channel in its upper five RGB888 bits.
    return tuple(((value >> shift) & 0x1F) << 3 for shift in (0, 5, 10))


def _tile_color_zero_pixels(
    emulator: Emulator,
    tile: int,
    attribute: int,
) -> tuple[tuple[int, int], ...]:
    if emulator.pyboy.memory[RLCDC] & 0x10:
        address = 0x8000 + tile * 16
    else:
        signed_tile = tile if tile < 0x80 else tile - 0x100
        address = 0x9000 + signed_tile * 16
    tile_data = emulator.read_vram_bank((attribute >> 3) & 1, address, 16)
    pixels = []
    for output_y in range(8):
        source_y = 7 - output_y if attribute & 0x40 else output_y
        low, high = tile_data[source_y * 2 : source_y * 2 + 2]
        for output_x in range(8):
            source_x = 7 - output_x if attribute & 0x20 else output_x
            bit = 7 - source_x
            color = ((high >> bit) & 1) << 1 | ((low >> bit) & 1)
            if color == 0:
                pixels.append((output_x, output_y))
    return tuple(pixels)


def _render_tilemap_region(
    tiles: bytes,
    attributes: bytes,
    palettes: bytes,
    graphics: tuple[bytes, bytes],
    lcdc: int,
    rect: tuple[int, int, int, int],
) -> Image.Image:
    left, top, right, bottom = rect
    image = Image.new("RGB", ((right - left) * 8, (bottom - top) * 8))
    pixels = image.load()
    for row in range(top, bottom):
        for column in range(left, right):
            index = row * SCREEN_WIDTH + column
            tile = tiles[index]
            attribute = attributes[index]
            offset = _graphics_offset(tile, lcdc)
            tile_data = graphics[(attribute >> 3) & 1][offset : offset + 16]
            for output_y in range(8):
                source_y = 7 - output_y if attribute & 0x40 else output_y
                low, high = tile_data[source_y * 2 : source_y * 2 + 2]
                for output_x in range(8):
                    source_x = 7 - output_x if attribute & 0x20 else output_x
                    bit = 7 - source_x
                    color = ((high >> bit) & 1) << 1 | ((low >> bit) & 1)
                    palette_offset = (attribute & PALETTE_MASK) * 8 + color * 2
                    pixels[
                        (column - left) * 8 + output_x,
                        (row - top) * 8 + output_y,
                    ] = _rgb555(palettes[palette_offset : palette_offset + 2])
    return image


def _mismatches(actual: bytes, expected: bytes) -> list[dict[str, int]]:
    return [
        {
            "column": index % SCREEN_WIDTH,
            "row": index // SCREEN_WIDTH,
            "actual": actual_value,
            "expected": expected_value,
        }
        for index, (actual_value, expected_value) in enumerate(
            zip(actual, expected, strict=True)
        )
        if actual_value != expected_value
    ]


def _replace_byte(data: bytes, index: int, value: int) -> bytes:
    mutated = bytearray(data)
    mutated[index] = value
    return bytes(mutated)


def _assert_authorized_moving_water_state(
    expected: bytes,
    actual: bytes,
    *,
    boundary: str,
) -> None:
    mismatches = [
        {
            "offset": offset,
            "expected": expected_value,
            "actual": actual_value,
        }
        for offset, (expected_value, actual_value) in enumerate(
            zip(expected, actual, strict=True)
        )
        if expected_value != actual_value
    ]
    assert not mismatches, (
        f"bank-0 tile $14 changed outside UpdateMovingBgTiles at {boundary}: "
        f"{mismatches}"
    )


def test_moving_water_first_entry_rejects_drift_from_captured_baseline() -> None:
    captured_baseline = bytes(range(16))
    hostile_first_entry = _replace_byte(
        captured_baseline,
        7,
        captured_baseline[7] ^ 0xFF,
    )
    try:
        _assert_authorized_moving_water_state(
            captured_baseline,
            hostile_first_entry,
            boundary="first hooked entry after captured baseline",
        )
    except AssertionError as error:
        assert "outside UpdateMovingBgTiles" in str(error)
    else:
        raise AssertionError("untraced first-entry tile-$14 drift was accepted")


def _mutate_palette(data: bytes, palette: int) -> bytes:
    mutated = bytearray(data)
    for index in range(palette * 8, palette * 8 + 8):
        mutated[index] ^= 0x1F
    return bytes(mutated)


def _mutate_visible_graphics(
    tiles: bytes,
    attributes: bytes,
    graphics: tuple[bytes, bytes],
    lcdc: int,
) -> tuple[bytes, bytes]:
    bank = attributes[0] >> 3 & 1
    offset = _graphics_offset(tiles[0], lcdc)
    mutated = list(graphics)
    mutated[bank] = _replace_byte(
        mutated[bank], offset, mutated[bank][offset] ^ 0xFF
    )
    return tuple(mutated)


def _is_save_confirmation(emulator: Emulator) -> bool:
    return (
        emulator.read("wCurMap") == OAKS_LAB
        and emulator.read("wBattleAndStartSavedMenuItem") == START_MENU_SAVE_INDEX
        and emulator.read("wTextBoxID") == TWO_OPTION_MENU
        and emulator.read("wTopMenuItemY") == 8
        and emulator.read("wTopMenuItemX") == 1
        and emulator.read("wMaxMenuItem") == 1
        and emulator.read("wMenuWatchedKeys") == PAD_A_OR_B
        and emulator.read("wCurrentMenuItem") == 0
    )


def _is_presented_oaks_lab_map(emulator: Emulator) -> bool:
    return (
        emulator.read("wCurMap") == OAKS_LAB
        and emulator.read("wOaksLabCurScript")
        == SCRIPT_OAKSLAB_PLAYER_DONT_GO_AWAY
        and emulator.read("wPassiveFullColorActive") == 1
        and emulator.read("wJoyIgnore") == 0
        and emulator.read("wUpdateSpritesEnabled") == 1
        and emulator.pyboy.memory[RLCDC] & 0x80 != 0
        and emulator.pyboy.memory[RWY] >= 144
    )


def test_natural_color_oaks_lab_save_confirmation_is_true_white() -> None:
    product = "pokeyellow"
    results = result_directory(
        "test_full_color_oaks_lab_save_confirmation.py::oak-lab-save-confirmation"
    )
    emulator = Emulator(
        rom=Path(REPOSITORY_ROOT / f"{product}.gbc"),
        symbols=Path(REPOSITORY_ROOT / f"{product}.sym"),
        results=results,
        cgb=True,
    )
    expected_palettes = _linked_bytes(product, "FullColorIndoorBGPalettes", 64)
    expected_attributes = _linked_bytes(product, "FullColorGymTileAttributes", 256)
    animator_hook_cleanup = ExitStack()

    try:
        reach_bedroom_overworld(emulator)
        walk_from_bedroom_to_oak(emulator)
        emulator.advance_until(
            lambda: emulator.read("wCurMap") == OAKS_LAB,
            button="a",
            max_presses=80,
            description="Oak's natural escort into his lab",
        )
        emulator.advance_until(
            lambda: emulator.read("wOaksLabCurScript")
            == SCRIPT_OAKSLAB_PLAYER_DONT_GO_AWAY,
            button="a",
            max_presses=80,
            description="Oak's Lab starter-selection control",
        )

        expected_underlying: dict[str, object] = {}
        expected_update_sprites_calls = 0

        def capture_completed_underlying_map(_: object) -> None:
            nonlocal expected_update_sprites_calls
            if not _is_presented_oaks_lab_map(emulator):
                return
            expected_update_sprites_calls += 1
            # Yellow advances sprite state, prepares shadow OAM on VBlank, and
            # publishes it through OAM DMA on the following VBlank. PyBoy's
            # completed framebuffer exposes that scanout at this fourth entry.
            if (
                expected_update_sprites_calls
                == PRESENTED_MAP_UPDATE_SPRITES_ENTRY
            ):
                expected_underlying.update(_map_presentation(emulator))

        update_sprites_hook = (
            emulator.symbol_banks["UpdateSprites"],
            emulator.symbols["UpdateSprites"],
        )
        emulator.pyboy.hook_register(
            *update_sprites_hook,
            capture_completed_underlying_map,
            "capture completed pre-Start Oak's Lab frame",
        )
        try:
            for _ in range(180):
                if expected_underlying:
                    break
                emulator.tick()
        finally:
            emulator.pyboy.hook_deregister(*update_sprites_hook)
        assert expected_underlying, "pre-Start sprite/VBlank boundary was not reached"
        assert emulator.read("wCurMap") == OAKS_LAB
        assert emulator.read("wCurMapTileset") == LAB_TILESET
        assert emulator.read("wUnusedObtainedBadges") & 1 == 0
        assert emulator.read("wPassiveFullColorActive") == 1

        underlying_lcdc = expected_underlying["lcdc"]
        underlying_map = expected_underlying["map_base"]
        expected_underlying_tiles = expected_underlying["tiles"]
        expected_underlying_attributes = expected_underlying["attributes"]
        expected_underlying_palettes = expected_underlying["palettes"]
        expected_underlying_graphics = expected_underlying["graphics"]
        expected_underlying_tilemap = expected_underlying["tilemap"]
        expected_underlying_render = expected_underlying["render"]
        expected_underlying_frame = expected_underlying["frame"]
        assert isinstance(underlying_lcdc, int)
        assert isinstance(underlying_map, int)
        assert isinstance(expected_underlying_tiles, bytes)
        assert isinstance(expected_underlying_attributes, bytes)
        assert isinstance(expected_underlying_palettes, bytes)
        assert isinstance(expected_underlying_graphics, tuple)
        assert isinstance(expected_underlying_tilemap, bytes)
        assert isinstance(expected_underlying_render, Image.Image)
        assert isinstance(expected_underlying_frame, Image.Image)

        moving_water_offset = _graphics_offset(
            MOVING_WATER_TILE,
            underlying_lcdc,
        )

        def read_moving_water_tile() -> bytes:
            return emulator.read_vram_bank(
                0,
                TILE_DATA + moving_water_offset,
                16,
            )

        animator_entry = (
            emulator.symbol_banks["UpdateMovingBgTiles"],
            emulator.symbols["UpdateMovingBgTiles"],
        )
        animator_return = (
            emulator.symbol_banks["VBlank.yellowOAMOperations"],
            emulator.symbols["VBlank.yellowOAMOperations"],
        )
        animator_callsite = animator_return[1] - 3
        expected_call = bytes(
            (
                0xCD,
                animator_entry[1] & 0xFF,
                animator_entry[1] >> 8,
            )
        )
        actual_call = emulator.read_memory(animator_callsite, len(expected_call))
        assert actual_call == expected_call, (
            "VBlank.yellowOAMOperations is no longer the exact return boundary "
            f"after call UpdateMovingBgTiles: {actual_call.hex()}"
        )

        baseline_moving_water = expected_underlying_graphics[0][
            moving_water_offset : moving_water_offset + 16
        ]
        _assert_authorized_moving_water_state(
            baseline_moving_water,
            read_moving_water_tile(),
            boundary="animator hook installation after captured baseline",
        )
        animator_trace: dict[str, object] = {
            "baseline": baseline_moving_water,
            "authorized": baseline_moving_water,
            "active": None,
            "invocations": [],
            "first_entry_continuous": False,
        }

        def enter_moving_water_animator(_: object) -> None:
            active = animator_trace["active"]
            assert active is None, "nested UpdateMovingBgTiles invocation"
            authorized = animator_trace["authorized"]
            assert isinstance(authorized, bytes)
            current = read_moving_water_tile()
            invocations = animator_trace["invocations"]
            assert isinstance(invocations, list)
            _assert_authorized_moving_water_state(
                authorized,
                current,
                boundary=f"invocation {len(invocations)} entry",
            )
            if not invocations:
                baseline = animator_trace["baseline"]
                assert isinstance(baseline, bytes)
                _assert_authorized_moving_water_state(
                    baseline,
                    current,
                    boundary="first hooked entry after captured baseline",
                )
                animator_trace["first_entry_continuous"] = True
            animator_trace["active"] = {
                "entry_frame": emulator.frame,
                "before": current,
                "write_count": 0,
            }

        def observe_moving_water_write(_: object) -> None:
            active = animator_trace["active"]
            assert isinstance(active, dict), (
                "UpdateMovingBgTiles water write occurred outside its observed entry"
            )
            active["write_count"] = int(active["write_count"]) + 1

        def leave_moving_water_animator(_: object) -> None:
            active = animator_trace["active"]
            if active is None:
                # Overlay-only VBlanks jump to this label without calling the
                # animator. They are not producer windows.
                return
            assert isinstance(active, dict)
            before = active["before"]
            assert isinstance(before, bytes)
            after = read_moving_water_tile()
            write_count = int(active["write_count"])
            if after != before:
                assert write_count == 16, (
                    "tile $14 changed without all 16 exact water-write "
                    f"instructions: {write_count}"
                )
            else:
                assert write_count == 0, (
                    "water-write instructions ran without changing tile $14: "
                    f"{write_count}"
                )
            invocations = animator_trace["invocations"]
            assert isinstance(invocations, list)
            invocations.append(
                {
                    "entry_frame": active["entry_frame"],
                    "return_frame": emulator.frame,
                    "before_hex": before.hex(),
                    "after_hex": after.hex(),
                    "water_write_count": write_count,
                }
            )
            animator_trace["authorized"] = after
            animator_trace["active"] = None

        water_write_sites = (
            emulator.symbols["UpdateMovingBgTiles.right"] + 2,
            emulator.symbols["UpdateMovingBgTiles.left"] + 2,
        )
        write_opcodes = tuple(
            emulator.read_memory(write_site, 1)[0]
            for write_site in water_write_sites
        )
        assert write_opcodes == (0x22, 0x22), (
            "moving-water hooks no longer identify the exact ld [hli], a "
            f"instructions: {write_opcodes}"
        )
        emulator.pyboy.hook_register(
            *animator_entry,
            enter_moving_water_animator,
            "UpdateMovingBgTiles entry",
        )
        animator_hook_cleanup.callback(
            emulator.pyboy.hook_deregister,
            *animator_entry,
        )
        emulator.pyboy.hook_register(
            *animator_return,
            leave_moving_water_animator,
            "UpdateMovingBgTiles exact return",
        )
        animator_hook_cleanup.callback(
            emulator.pyboy.hook_deregister,
            *animator_return,
        )
        for write_site in water_write_sites:
            emulator.pyboy.hook_register(
                animator_entry[0],
                write_site,
                observe_moving_water_write,
                "UpdateMovingBgTiles tile-$14 write",
            )
            animator_hook_cleanup.callback(
                emulator.pyboy.hook_deregister,
                animator_entry[0],
                write_site,
            )

        mutation_renders = {
            "tile": _render_tilemap_region(
                _replace_byte(
                    expected_underlying_tiles,
                    0,
                    expected_underlying_tiles[0] ^ 0xFF,
                ),
                expected_underlying_attributes,
                expected_underlying_palettes,
                expected_underlying_graphics,
                underlying_lcdc,
                (0, 0, SCREEN_WIDTH, SCREEN_HEIGHT),
            ),
            "attribute": _render_tilemap_region(
                expected_underlying_tiles,
                _replace_byte(
                    expected_underlying_attributes,
                    0,
                    expected_underlying_attributes[0] ^ 0x01,
                ),
                expected_underlying_palettes,
                expected_underlying_graphics,
                underlying_lcdc,
                (0, 0, SCREEN_WIDTH, SCREEN_HEIGHT),
            ),
            "palette": _render_tilemap_region(
                expected_underlying_tiles,
                expected_underlying_attributes,
                _mutate_palette(
                    expected_underlying_palettes,
                    expected_underlying_attributes[0] & PALETTE_MASK,
                ),
                expected_underlying_graphics,
                underlying_lcdc,
                (0, 0, SCREEN_WIDTH, SCREEN_HEIGHT),
            ),
            "graphics": _render_tilemap_region(
                expected_underlying_tiles,
                expected_underlying_attributes,
                expected_underlying_palettes,
                _mutate_visible_graphics(
                    expected_underlying_tiles,
                    expected_underlying_attributes,
                    expected_underlying_graphics,
                    underlying_lcdc,
                ),
                underlying_lcdc,
                (0, 0, SCREEN_WIDTH, SCREEN_HEIGHT),
            ),
        }
        mutation_diff_bboxes = {
            name: ImageChops.difference(render, expected_underlying_render).getbbox()
            for name, render in mutation_renders.items()
        }
        assert all(mutation_diff_bboxes.values()), mutation_diff_bboxes
        expected_underlying_frame.save(results / "expected-underlying-map-frame.png")
        expected_underlying_render.save(results / "expected-underlying-map-render.png")

        emulator.press("start", wait_frames=60)
        move_cursor_to(
            emulator,
            "wCurrentMenuItem",
            START_MENU_SAVE_INDEX,
            description="the fresh-game Start-menu Save item",
        )
        emulator.tick(5)
        before_image = emulator.capture_screen()
        before_attributes = _window_plane(emulator, 1)
        before_image.save(results / "before-start-menu-save.png")

        emulator.press("a", wait_frames=60)
        emulator.advance_until(
            lambda: _is_save_confirmation(emulator),
            button="a",
            max_presses=3,
            description="Save Yes/No confirmation",
        )
        emulator.tick()
        assert _is_save_confirmation(emulator)
        assert emulator.pyboy.memory[RWY] == 0
        assert emulator.pyboy.memory[RWX] == 7

        actual_image = emulator.capture_screen()
        actual_tiles = _window_plane(emulator, 0)
        actual_attributes = _window_plane(emulator, 1)
        hardware_palettes = emulator.read_palette_ram()
        ui_indexes = _ui_cell_indexes()
        expected_ui_attributes = bytes(
            expected_attributes[actual_tiles[i]] for i in ui_indexes
        )
        actual_ui_attributes = bytes(actual_attributes[i] for i in ui_indexes)
        attribute_mismatches = [
            {
                "column": index % SCREEN_WIDTH,
                "row": index // SCREEN_WIDTH,
                "tile": actual_tiles[index],
                "actual": actual_attributes[index],
                "expected": expected_attributes[actual_tiles[index]],
            }
            for index in ui_indexes
            if actual_attributes[index] != expected_attributes[actual_tiles[index]]
        ]
        stale_exposure_cells = [
            (index % SCREEN_WIDTH, index // SCREEN_WIDTH)
            for index in ui_indexes
            if before_attributes[index] & PALETTE_MASK == 0
            and expected_attributes[actual_tiles[index]] & PALETTE_MASK == TEXT_PALETTE
        ]

        expected_white = _rgb555(expected_palettes[56:58])
        lab_off_white = _rgb555(expected_palettes[0:2])
        reference_image = actual_image.copy()
        mask_image = Image.new("RGB", actual_image.size, (0, 0, 0))
        reference_pixels = reference_image.load()
        mask_pixels = mask_image.load()
        white_pixel_mismatches = []
        white_pixel_count = 0
        for index in ui_indexes:
            column, row = index % SCREEN_WIDTH, index // SCREEN_WIDTH
            expected_attribute = expected_attributes[actual_tiles[index]]
            for tile_x, tile_y in _tile_color_zero_pixels(
                emulator, actual_tiles[index], expected_attribute
            ):
                x, y = column * 8 + tile_x, row * 8 + tile_y
                white_pixel_count += 1
                if actual_image.getpixel((x, y)) != expected_white:
                    white_pixel_mismatches.append((x, y, actual_image.getpixel((x, y))))
                reference_pixels[x, y] = expected_white
                mask_pixels[x, y] = (255, 255, 255)

        difference = ImageChops.difference(actual_image, reference_image)
        actual_image.save(results / "actual-save-confirmation.png")
        reference_image.save(results / "reference-true-white-ui.png")
        difference.save(results / "diff-true-white-ui.png")
        mask_image.save(results / "true-white-ui-mask.png")
        (results / "actual-ui-attributes.bin").write_bytes(actual_ui_attributes)
        (results / "reference-ui-attributes.bin").write_bytes(expected_ui_attributes)
        diagnostics = {
            "route_endpoint": {
                "map": emulator.read("wCurMap"),
                "tileset": emulator.read("wCurMapTileset"),
                "y": emulator.read("wYCoord"),
                "x": emulator.read("wXCoord"),
                "oak_lab_script": emulator.read("wOaksLabCurScript"),
            },
            "confirmation_menu": {
                "text_box_id": emulator.read("wTextBoxID"),
                "top_y": emulator.read("wTopMenuItemY"),
                "top_x": emulator.read("wTopMenuItemX"),
                "max_item": emulator.read("wMaxMenuItem"),
                "watched_keys": emulator.read("wMenuWatchedKeys"),
                "current_item": emulator.read("wCurrentMenuItem"),
            },
            "expected_true_white_rgb": expected_white,
            "oak_lab_palette0_off_white_rgb": lab_off_white,
            "hardware_palette7_hex": hardware_palettes[56:64].hex(),
            "reference_palette7_hex": expected_palettes[56:64].hex(),
            "ui_cell_count": len(ui_indexes),
            "white_pixel_count": white_pixel_count,
            "stale_palette0_exposure_cells": stale_exposure_cells,
            "attribute_mismatches": attribute_mismatches,
            "white_pixel_mismatch_count": len(white_pixel_mismatches),
            "first_white_pixel_mismatches": white_pixel_mismatches[:32],
            "diff_bbox": difference.getbbox(),
        }
        (results / "diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        assert expected_white == (248, 248, 248)
        assert lab_off_white != expected_white
        assert hardware_palettes == expected_palettes
        assert stale_exposure_cells, "test did not cover Oak's Lab palette-0 cells"
        assert all(
            attribute & PALETTE_MASK == TEXT_PALETTE
            for attribute in expected_ui_attributes
        )
        assert not attribute_mismatches, diagnostics
        assert white_pixel_count > 1000
        assert not white_pixel_mismatches, diagnostics
        assert difference.getbbox() is None, diagnostics

        restored: dict[str, object] = {}
        restore_path = {
            "loaded_buffer2": False,
            "restore_entered": False,
            "update_sprites_calls": 0,
        }

        def observe_buffer2_restore(_: object) -> None:
            restore_path["loaded_buffer2"] = True

        def arm_completed_map_restore(_: object) -> None:
            assert restore_path["loaded_buffer2"]
            restore_path["restore_entered"] = True

        def capture_completed_map_restore(_: object) -> None:
            if not restore_path["restore_entered"] or restored:
                return
            restore_path["update_sprites_calls"] += 1
            if (
                restore_path["update_sprites_calls"]
                == PRESENTED_MAP_UPDATE_SPRITES_ENTRY
            ):
                restored.update(_map_presentation(emulator))

        boundary_symbols = (
            "LoadScreenTilesFromBuffer2",
            "PassiveFullColorRestoreAfterMenu",
            "UpdateSprites",
        )
        boundary_hooks = tuple(
            (emulator.symbol_banks[symbol], emulator.symbols[symbol])
            for symbol in boundary_symbols
        )
        boundary_callbacks = (
            observe_buffer2_restore,
            arm_completed_map_restore,
            capture_completed_map_restore,
        )
        with ExitStack() as boundary_hook_cleanup:
            for hook, callback, symbol in zip(
                boundary_hooks, boundary_callbacks, boundary_symbols, strict=True
            ):
                emulator.pyboy.hook_register(*hook, callback, symbol)
                boundary_hook_cleanup.callback(
                    emulator.pyboy.hook_deregister,
                    *hook,
                )
            emulator.pyboy.button("b", delay=2)
            for _ in range(120):
                if restored:
                    break
                emulator.tick()

        assert restore_path["loaded_buffer2"], "Save cancellation skipped buffer 2"
        assert restore_path["restore_entered"], "Save cancellation skipped map restore"
        assert restored, "completed Save cancellation boundary was not reached"
        observed_frame = restored["frame"]
        restored_render = restored["render"]
        restored_tiles = restored["tiles"]
        restored_attributes = restored["attributes"]
        restored_palettes = restored["palettes"]
        restored_graphics = restored["graphics"]
        restored_tilemap = restored["tilemap"]
        assert isinstance(observed_frame, Image.Image)
        assert isinstance(restored_render, Image.Image)
        assert isinstance(restored_tiles, bytes)
        assert isinstance(restored_attributes, bytes)
        assert isinstance(restored_palettes, bytes)
        assert isinstance(restored_graphics, tuple)
        assert isinstance(restored_tilemap, bytes)

        assert animator_trace["active"] is None, (
            "final capture interrupted UpdateMovingBgTiles"
        )
        final_authorized_water = animator_trace["authorized"]
        assert isinstance(final_authorized_water, bytes)
        _assert_authorized_moving_water_state(
            final_authorized_water,
            read_moving_water_tile(),
            boundary="completed restored-map capture",
        )
        animator_invocations = animator_trace["invocations"]
        assert isinstance(animator_invocations, list)
        assert animator_invocations, "UpdateMovingBgTiles was never observed"
        assert animator_trace["first_entry_continuous"] is True, (
            "first UpdateMovingBgTiles entry was not continuous with the "
            "captured baseline"
        )
        assert any(
            invocation["before_hex"] != invocation["after_hex"]
            for invocation in animator_invocations
        ), "test did not observe an authorized tile-$14 transition"

        expected_authorized_graphics_banks = [
            bytearray(bank) for bank in expected_underlying_graphics
        ]
        expected_authorized_graphics_banks[0][
            moving_water_offset : moving_water_offset + 16
        ] = final_authorized_water
        expected_authorized_graphics = tuple(
            bytes(bank) for bank in expected_authorized_graphics_banks
        )
        restored_difference = ImageChops.difference(
            restored_render, expected_underlying_render
        )
        tile_mismatches = _mismatches(restored_tiles, expected_underlying_tiles)
        attribute_mismatches = _mismatches(
            restored_attributes, expected_underlying_attributes
        )
        palette_mismatches = _mismatches(
            restored_palettes, expected_underlying_palettes
        )
        tilemap_mismatches = _mismatches(
            restored_tilemap, expected_underlying_tilemap
        )
        graphics_mismatches = [
            {
                "bank": bank,
                "offset": offset,
                "address": TILE_DATA + offset,
                "actual": actual,
                "expected": expected,
            }
            for bank, (actual_bank, expected_bank) in enumerate(
                zip(restored_graphics, expected_underlying_graphics, strict=True)
            )
            for offset, (actual, expected) in enumerate(
                zip(actual_bank, expected_bank, strict=True)
            )
            if actual != expected
        ]
        graphics_mismatch_identities = frozenset(
            (mismatch["bank"], mismatch["offset"])
            for mismatch in graphics_mismatches
        )
        unexpected_graphics_mismatches = [
            {
                "bank": bank,
                "offset": offset,
                "address": TILE_DATA + offset,
                "actual": actual,
                "expected": expected,
            }
            for bank, (actual_bank, expected_bank) in enumerate(
                zip(restored_graphics, expected_authorized_graphics, strict=True)
            )
            for offset, (actual, expected) in enumerate(
                zip(actual_bank, expected_bank, strict=True)
            )
            if actual != expected
        ]
        used_graphics_bytes = _used_graphics_bytes(
            expected_underlying_tiles,
            expected_underlying_attributes,
            underlying_lcdc,
        )
        used_graphics_mismatches = [
            mismatch
            for mismatch in graphics_mismatches
            if (mismatch["bank"], mismatch["offset"]) in used_graphics_bytes
        ]
        moving_water_graphics_bytes = frozenset(
            (0, offset)
            for offset in range(moving_water_offset, moving_water_offset + 16)
        )
        frame_difference = ImageChops.difference(
            observed_frame, expected_underlying_frame
        )
        frame_difference_bytes = frame_difference.tobytes()
        frame_mismatch_pixels = sum(
            any(frame_difference_bytes[offset : offset + 3])
            for offset in range(0, len(frame_difference_bytes), 3)
        )
        observed_frame.save(results / "observed-completed-map-restore-frame.png")
        frame_difference.save(results / "diff-completed-map-restore-frame.png")
        restored_render.save(results / "actual-restored-map-render.png")
        restored_difference.save(results / "diff-restored-map-render.png")
        (results / "expected-underlying-tiles.bin").write_bytes(
            expected_underlying_tiles
        )
        (results / "actual-restored-tiles.bin").write_bytes(restored_tiles)
        (results / "expected-underlying-attributes.bin").write_bytes(
            expected_underlying_attributes
        )
        (results / "actual-restored-attributes.bin").write_bytes(
            restored_attributes
        )
        (results / "expected-underlying-palettes.bin").write_bytes(
            expected_underlying_palettes
        )
        (results / "actual-restored-palettes.bin").write_bytes(restored_palettes)
        (results / "expected-underlying-tilemap.bin").write_bytes(
            expected_underlying_tilemap
        )
        (results / "actual-restored-tilemap.bin").write_bytes(restored_tilemap)
        diagnostics["dismissal"] = {
            "boundary": (
                "completed scanout at the fourth UpdateSprites entry after "
                "PassiveFullColorRestoreAfterMenu"
            ),
            "load_screen_tiles_from_buffer2_observed": restore_path[
                "loaded_buffer2"
            ],
            "update_sprites_entries_after_restore": restore_path[
                "update_sprites_calls"
            ],
            "expected_map_base": underlying_map,
            "actual_map_base": restored["map_base"],
            "expected_lcdc": underlying_lcdc,
            "actual_lcdc": restored["lcdc"],
            "window_y": restored["wy"],
            "window_x": restored["wx"],
            "tile_mismatches": tile_mismatches[:32],
            "attribute_mismatches": attribute_mismatches[:32],
            "palette_mismatches": palette_mismatches[:32],
            "tilemap_mismatches": tilemap_mismatches[:32],
            "graphics_mismatches": graphics_mismatches,
            "graphics_drift_authority": {
                "producer": "UpdateMovingBgTiles",
                "entry": animator_entry[1],
                "return": animator_return[1],
                "water_write_sites": water_write_sites,
                "bank": 0,
                "start_address": TILE_DATA + moving_water_offset,
                "end_address_exclusive": TILE_DATA + moving_water_offset + 16,
                "invocations": animator_invocations,
                "last_authorized_state_hex": final_authorized_water.hex(),
            },
            "unexpected_graphics_mismatches": unexpected_graphics_mismatches,
            "used_graphics_mismatches": used_graphics_mismatches,
            "frame_diff_bbox": frame_difference.getbbox(),
            "frame_mismatch_pixels": frame_mismatch_pixels,
            "oracle_mutation_diff_bboxes": mutation_diff_bboxes,
            "restored_render_diff_bbox": restored_difference.getbbox(),
            "final_map": emulator.read("wCurMap"),
            "final_passive_active": emulator.read("wPassiveFullColorActive"),
        }
        (results / "diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        assert restored["map_base"] == underlying_map
        assert restored["lcdc"] == underlying_lcdc
        assert restored_tiles == expected_underlying_tiles, diagnostics
        assert restored_attributes == expected_underlying_attributes, diagnostics
        assert restored_palettes == expected_underlying_palettes, diagnostics
        assert graphics_mismatch_identities <= moving_water_graphics_bytes, diagnostics
        assert not unexpected_graphics_mismatches, diagnostics
        assert restored_graphics == expected_authorized_graphics, diagnostics
        assert not used_graphics_mismatches, diagnostics
        assert restored_tilemap == expected_underlying_tilemap, diagnostics
        assert restored_difference.getbbox() is None, diagnostics
        assert observed_frame.tobytes() == expected_underlying_frame.tobytes(), (
            diagnostics
        )
        assert emulator.read("wCurMap") == OAKS_LAB
        assert emulator.read("wPassiveFullColorActive") == 1
    except BaseException:
        emulator.save_screenshot("failure.png")
        raise
    finally:
        try:
            animator_hook_cleanup.close()
        finally:
            emulator.close()

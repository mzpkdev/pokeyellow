"""Natural paired Color/Yellow routes for Phase 3 background review batches."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import tempfile
import uuid

from PIL import Image
import pytest

from tools.rom_tests.emulator import Emulator
from tools.rom_tests.scenarios.map_background_routes import (
    ARTIFACT_ONLY_PURPOSE,
    ARTIFACT_REVIEW_ROUTES,
    BATCH_ROUTES,
    MAP_IDENTITIES,
    MODES,
    NATURAL_DRIVERS,
    PRODUCTS,
    ROUTES_BY_BATCH,
    BatchRoute,
    RouteCheckpoint,
    validate_artifact_review_route,
)
from tools.rom_tests.scenarios.new_game import reach_bedroom_overworld
from tools.rom_tests.scenarios.oaks_lab import (
    finish_rival_battle_and_leave_lab,
    follow_oak_and_receive_pikachu,
    walk_from_bedroom_to_oak,
)
from tools.rom_tests.scenarios.parcel_delivery import collect_oaks_parcel
from tools.rom_tests.scenarios.renderer_mode import select_renderer_mode
from tools.rom_tests.scenarios.viridian_city import walk_from_oaks_lab_to_viridian
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT, result_directory


TILESET_IDS = {
    "OVERWORLD": 0,
    "REDS_HOUSE_2": 4,
    "DOJO": 5,
    "MART": 2,
}
RETAINED_MANIFEST_SCHEMA = "full-color-map-background-retained-artifacts-v1"


@dataclass(frozen=True, slots=True)
class Observation:
    logical: tuple[int, int, int, int]
    tilemap: bytes
    attributes: bytes
    palettes: bytes
    passive_active: int


def _canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _case_tree_entries(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise AssertionError(f"refusing unsafe Phase 3 result tree: {root}")
    entries = []
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in directory.iterdir():
            if entry.is_symlink():
                raise AssertionError(f"result tree contains a symlink: {entry}")
            if entry.is_dir():
                pending.append(entry)
            elif not entry.is_file():
                raise AssertionError(f"result tree contains a special file: {entry}")
            entries.append(entry)
    return entries


def _remove_case_tree(root: Path) -> None:
    entries = _case_tree_entries(root)
    for entry in sorted(entries, key=lambda path: len(path.parts), reverse=True):
        if entry.is_dir():
            entry.rmdir()
        else:
            entry.unlink()
    root.rmdir()


def _begin_case_results(stable: Path) -> Path:
    stable.parent.mkdir(parents=True, exist_ok=True)
    if stable.exists() or stable.is_symlink():
        _case_tree_entries(stable)
        stale = stable.parent / f".{stable.name}.stale-{uuid.uuid4().hex}"
        os.replace(stable, stale)
        _fsync_directory(stable.parent)
        _remove_case_tree(stale)
        _fsync_directory(stable.parent)
    return Path(tempfile.mkdtemp(prefix=f".{stable.name}.run-", dir=stable.parent))


def _publish_case_results(running: Path, stable: Path) -> None:
    if stable.exists() or stable.is_symlink():
        raise AssertionError("stable Phase 3 result tree was recreated during its run")
    directories = [path for path in running.rglob("*") if path.is_dir()]
    for directory in sorted(
        directories, key=lambda path: len(path.parts), reverse=True
    ):
        _fsync_directory(directory)
    _fsync_directory(running)
    os.replace(running, stable)
    _fsync_directory(stable.parent)


def _write_retained_manifest(
    results: Path, *, route: BatchRoute, product: str, mode: str
) -> dict[str, object]:
    declarations = [
        (checkpoint, kind, relative_name)
        for checkpoint in route.checkpoints
        for kind, relative_name in (
            ("screenshot", checkpoint.retained_screenshot),
            ("frame-strip", checkpoint.retained_frame_strip),
        )
    ]
    declared_paths = [relative_name for _, _, relative_name in declarations]
    for relative_name in declared_paths:
        candidate = PurePosixPath(relative_name)
        if (
            not relative_name
            or "\\" in relative_name
            or candidate.is_absolute()
            or any(part in {"", ".", ".."} for part in candidate.parts)
            or candidate.as_posix() != relative_name
        ):
            raise AssertionError(
                f"retained artifact path is not normalized: {relative_name!r}"
            )
    if len(declared_paths) != len(set(declared_paths)):
        raise AssertionError("retained artifact paths must be globally unique")

    artifacts = []
    for checkpoint, kind, relative_name in declarations:
        purposes = [sample.purpose for sample in checkpoint.tile_samples]
        path = results / relative_name
        if path.is_symlink() or not path.is_file():
            raise AssertionError(f"missing retained {kind}: {relative_name}")
        artifacts.append(
            {
                "path": relative_name,
                "sha256": _sha256(path),
                "route": route.route,
                "product": product,
                "checkpoint": checkpoint.name,
                "map_id": checkpoint.map_id,
                "map_name": checkpoint.map_name,
                "mode": mode,
                "kind": kind,
                "natural_driver": list(route.natural_driver),
                "replacements": list(checkpoint.replacements),
                "tile_sample_purposes": purposes,
                "tile_samples": [
                    {
                        "tile_id": sample.tile_id,
                        "attribute_authority": sample.attribute_authority,
                        "expected_attribute": sample.expected_attribute,
                        "purpose": sample.purpose,
                    }
                    for sample in checkpoint.tile_samples
                ],
            }
        )
    manifest: dict[str, object] = {
        "schema": RETAINED_MANIFEST_SCHEMA,
        "artifacts": sorted(artifacts, key=lambda row: str(row["path"])),
    }
    manifest["content_sha256"] = hashlib.sha256(
        _canonical_json(manifest).encode("utf-8")
    ).hexdigest()
    pngs = {
        path.relative_to(results).as_posix()
        for path in _case_tree_entries(results)
        if path.is_file() and path.suffix.lower() == ".png"
    }
    declared = {str(row["path"]) for row in artifacts}
    if pngs != declared:
        raise AssertionError(
            f"unlisted or missing retained PNGs: {sorted(pngs ^ declared)}"
        )
    manifest_path = results / "retained-artifacts.json"
    manifest_path.write_text(_canonical_json(manifest), encoding="utf-8")
    for row in artifacts:
        if _sha256(results / str(row["path"])) != row["sha256"]:
            raise AssertionError(f"retained artifact changed: {row['path']}")
    return manifest


def _linked_bytes(product: str, symbol: str, size: int) -> bytes:
    lines = (
        (REPOSITORY_ROOT / f"{product}.sym").read_text(encoding="utf-8").splitlines()
    )
    addresses = Emulator._parse_symbols(lines)
    banks = Emulator._parse_symbol_banks(lines)
    offset = banks[symbol] * 0x4000 + (addresses[symbol] & 0x3FFF)
    return (REPOSITORY_ROOT / f"{product}.gbc").read_bytes()[offset : offset + size]


def _checkpoint_palettes(product: str, checkpoint: RouteCheckpoint) -> bytes:
    palettes = bytearray(_linked_bytes(product, checkpoint.palette_authority, 64))
    if checkpoint.tileset == "OVERWORLD":
        assignments = _linked_bytes(product, "FullColorOverworldRoofAssignments", 37)
        roof_pairs = _linked_bytes(product, "FullColorOverworldRoofPalettes", 44)
        roof = assignments[checkpoint.map_id]
        palettes[50:54] = roof_pairs[roof * 4 : roof * 4 + 4]
    return bytes(palettes)


def _dmg_mapped_palette(base: bytes, bgp: int) -> bytes:
    assert len(base) == 8
    return b"".join(
        base[((bgp >> (index * 2)) & 3) * 2 : ((bgp >> (index * 2)) & 3) * 2 + 2]
        for index in range(4)
    )


def _yellow_palettes(
    emulator: Emulator, product: str, checkpoint: RouteCheckpoint
) -> bytes:
    base_address = emulator.symbols["CGBBasePalettes"]
    pointer_start = emulator.symbols["wCGBBasePalPointers"]
    pointers = tuple(
        emulator.pyboy.memory[pointer_start + index * 2]
        | (emulator.pyboy.memory[pointer_start + index * 2 + 1] << 8)
        for index in range(4)
    )
    assert pointers == tuple(
        base_address + palette_id * 8 for palette_id in checkpoint.yellow_pointer_ids
    )
    table = _linked_bytes(product, "CGBBasePalettes", 40 * 8)
    return b"".join(
        _dmg_mapped_palette(
            table[palette_id * 8 : palette_id * 8 + 8],
            emulator.pyboy.memory[0xFF47],
        )
        for palette_id in checkpoint.yellow_palette_ids
    )


def _rgb555(raw: bytes) -> tuple[int, int, int]:
    value = int.from_bytes(raw, "little")
    # PyBoy exposes the LCD's five-bit channels expanded by a three-bit shift.
    return tuple(((value >> shift) & 31) << 3 for shift in (0, 5, 10))


def _assert_yellow_background_pixels(emulator: Emulator, palettes: bytes) -> None:
    """Compare every non-sprite LCD pixel with Yellow's bank-0/BGP model."""
    lcdc = emulator.pyboy.memory[0xFF40]
    bg_tilemap_base = 0x9C00 if lcdc & (1 << 3) else 0x9800
    window_tilemap_base = 0x9C00 if lcdc & (1 << 6) else 0x9800
    bg_tilemap = emulator.read_vram_bank(0, bg_tilemap_base, 0x400)
    window_tilemap = emulator.read_vram_bank(0, window_tilemap_base, 0x400)
    graphics = emulator.read_vram_bank(0, 0x8000, 0x1800)
    colors = tuple(_rgb555(palettes[index : index + 2]) for index in range(0, 8, 2))
    scroll_x = emulator.pyboy.memory[0xFF43]
    scroll_y = emulator.pyboy.memory[0xFF42]
    window_x = emulator.pyboy.memory[0xFF4B] - 7
    window_y = emulator.pyboy.memory[0xFF4A]
    actual = emulator.capture_screen().convert("RGB")
    masked = set()
    sprite_height = 16 if lcdc & (1 << 2) else 8
    for index in range(40):
        y = emulator.pyboy.memory[0xFE00 + index * 4] - 16
        x = emulator.pyboy.memory[0xFE01 + index * 4] - 8
        if x <= -8 or x >= 160 or y <= -sprite_height or y >= 144:
            continue
        masked.update(
            (pixel_x, pixel_y)
            for pixel_y in range(max(y, 0), min(y + sprite_height, 144))
            for pixel_x in range(max(x, 0), min(x + 8, 160))
        )
    for screen_y in range(144):
        bg_y = (scroll_y + screen_y) & 0xFF
        for screen_x in range(160):
            if (screen_x, screen_y) in masked:
                continue
            if lcdc & (1 << 5) and screen_y >= window_y and screen_x >= window_x:
                pixel_x = screen_x - window_x
                pixel_y = screen_y - window_y
                tile_id = window_tilemap[(pixel_y // 8) * 32 + pixel_x // 8]
            else:
                pixel_x = (scroll_x + screen_x) & 0xFF
                pixel_y = bg_y
                tile_id = bg_tilemap[(pixel_y // 8) * 32 + pixel_x // 8]
            if lcdc & (1 << 4):
                tile_offset = tile_id * 16
            else:
                signed_id = tile_id if tile_id < 0x80 else tile_id - 0x100
                tile_offset = 0x1000 + signed_id * 16
            row = pixel_y & 7
            low, high = graphics[tile_offset + row * 2 : tile_offset + row * 2 + 2]
            bit = 7 - (pixel_x & 7)
            color_id = ((high >> bit) & 1) * 2 + ((low >> bit) & 1)
            assert actual.getpixel((screen_x, screen_y)) == colors[color_id]


def validate_yellow_payloads(
    attributes: bytes, palettes: bytes, expected_palettes: bytes
) -> None:
    """Fail closed on either Yellow attribute or palette corruption."""
    if attributes != bytes(len(attributes)):
        raise AssertionError("Yellow presentation contains nonzero attributes")
    if palettes != expected_palettes:
        raise AssertionError("Yellow presentation palette differs from its baseline")


def _planes(emulator: Emulator) -> tuple[bytes, bytes]:
    base = 0x9C00 if emulator.pyboy.memory[0xFF40] & (1 << 3) else 0x9800
    planes = (
        emulator.read_vram_bank(0, base, 0x400),
        emulator.read_vram_bank(1, base, 0x400),
    )
    left = emulator.pyboy.memory[0xFF43] // 8
    top = emulator.pyboy.memory[0xFF42] // 8
    return tuple(
        bytes(
            plane[((top + row) & 31) * 32 + ((left + column) & 31)]
            for row in range(18)
            for column in range(20)
        )
        for plane in planes
    )


def _retain_frames(
    emulator: Emulator, results: Path, checkpoint: RouteCheckpoint
) -> None:
    target = results / checkpoint.retained_screenshot
    target.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for _ in range(5):
        emulator.tick(20)
        frames.append(emulator.capture_screen().convert("RGB"))
    frames[2].save(target, format="PNG", optimize=False, compress_level=9)
    strip = Image.new("RGB", (frames[0].width * len(frames), frames[0].height))
    for index, frame in enumerate(frames):
        strip.paste(frame, (index * frame.width, 0))
    strip_path = results / checkpoint.retained_frame_strip
    strip_path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(strip_path, format="PNG", optimize=False, compress_level=9)


def _observe(
    emulator: Emulator,
    product: str,
    mode: str,
    results: Path,
    checkpoint: RouteCheckpoint,
) -> Observation:
    emulator.tick(60)
    logical = (
        emulator.read("wCurMap"),
        emulator.read("wYCoord"),
        emulator.read("wXCoord"),
        emulator.read("wCurMapTileset"),
    )
    assert logical == (
        checkpoint.map_id,
        checkpoint.coordinates[0],
        checkpoint.coordinates[1],
        TILESET_IDS[checkpoint.tileset],
    )
    assert MAP_IDENTITIES[logical[0]] == checkpoint.map_name
    tilemap, attributes = _planes(emulator)
    expected_attributes = _linked_bytes(
        product, checkpoint.tile_samples[0].attribute_authority, 256
    )
    assert all(
        sample.attribute_authority == checkpoint.tile_samples[0].attribute_authority
        for sample in checkpoint.tile_samples
    )
    for sample in checkpoint.tile_samples:
        assert sample.purpose
        assert expected_attributes[sample.tile_id] == sample.expected_attribute
        matches = [
            index for index, tile_id in enumerate(tilemap) if tile_id == sample.tile_id
        ]
        assert matches, f"{checkpoint.name}: tile ${sample.tile_id:02x} is absent"
        if mode == "color":
            assert all(
                attributes[index] == sample.expected_attribute for index in matches
            )
    palettes = emulator.read_palette_ram()
    active = emulator.read("wPassiveFullColorActive")
    mode_index = MODES.index(mode)
    expected_presentation = checkpoint.expected_presentation[mode_index]
    expected_effective_mode = checkpoint.expected_effective_mode[mode_index]
    if mode == "color":
        assert expected_presentation == "authored-full-color"
        assert expected_effective_mode == "color"
        assert active == 1
        assert palettes == _checkpoint_palettes(product, checkpoint)
        assert attributes == bytes(expected_attributes[tile] for tile in tilemap)
    else:
        assert expected_presentation == "yellow-baseline"
        assert expected_effective_mode == "yellow"
        assert active == 0
        expected_yellow = _yellow_palettes(emulator, product, checkpoint)
        validate_yellow_payloads(attributes, palettes, expected_yellow)
        _assert_yellow_background_pixels(emulator, expected_yellow)
    _retain_frames(emulator, results, checkpoint)
    return Observation(
        logical,
        tilemap,
        attributes,
        palettes,
        active,
    )


def _enter_selected_bedroom(emulator: Emulator, mode: str) -> None:
    reach_bedroom_overworld(emulator)
    select_renderer_mode(emulator, yellow_mode=mode == "yellow")


def _run_route(product: str, batch: str, mode: str) -> dict[str, Observation]:
    route = ROUTES_BY_BATCH[batch]
    assert route.natural_driver == NATURAL_DRIVERS[batch]
    stable_results = result_directory(route.id_for(product, mode))
    results = _begin_case_results(stable_results)
    emulator = Emulator(
        rom=REPOSITORY_ROOT / f"{product}.gbc",
        symbols=REPOSITORY_ROOT / f"{product}.sym",
        results=results,
        cgb=True,
    )
    expected = {checkpoint.name: checkpoint for checkpoint in route.checkpoints}
    observations: dict[str, Observation] = {}

    def record(name: str) -> None:
        observations[name] = _observe(emulator, product, mode, results, expected[name])

    try:
        _enter_selected_bedroom(emulator, mode)
        if batch == "residential-services":
            record("bedroom")
        walk_from_bedroom_to_oak(emulator)
        follow_oak_and_receive_pikachu(emulator)
        if batch == "challenge-special-interiors":
            record("oaks-lab-dojo")
        else:
            finish_rival_battle_and_leave_lab(emulator)
            if batch == "overworld":
                record("pallet-after-lab")

            def route_checkpoint(name: str, _emulator: Emulator) -> None:
                if name in expected:
                    record(name)

            walk_from_oaks_lab_to_viridian(
                emulator,
                route_checkpoint,
                use_debug_repel=False,
            )
            if batch == "residential-services":
                collect_oaks_parcel(emulator)
                record("viridian-mart")
        assert set(observations) == set(expected)
    except Exception:
        try:
            emulator.save_screenshot("map-background-route-failure.png")
        finally:
            emulator.close()
            _publish_case_results(results, stable_results)
        raise
    else:
        emulator.close()
        _write_retained_manifest(results, route=route, product=product, mode=mode)
        _publish_case_results(results, stable_results)
        return observations


@pytest.mark.parametrize("product", PRODUCTS)
@pytest.mark.parametrize("batch", tuple(route.batch for route in BATCH_ROUTES))
def test_natural_batch_route_preserves_yellow_gameplay_and_current_presentation(
    product: str, batch: str
) -> None:
    paired = {mode: _run_route(product, batch, mode) for mode in MODES}
    color, yellow = paired["color"], paired["yellow"]
    assert color.keys() == yellow.keys()
    for checkpoint in color:
        candidate, baseline = color[checkpoint], yellow[checkpoint]
        assert candidate.logical == baseline.logical
        assert candidate.tilemap == baseline.tilemap
        assert candidate.passive_active == 1
        assert baseline.passive_active == 0
        assert baseline.attributes == bytes(len(baseline.attributes))
        assert candidate.palettes != baseline.palettes


@pytest.mark.parametrize("route", ARTIFACT_REVIEW_ROUTES, ids=lambda row: row.batch)
def test_phase4_review_routes_are_explicitly_artifact_only(route: object) -> None:
    validate_artifact_review_route(route)
    assert route.purpose == ARTIFACT_ONLY_PURPOSE
    assert route.batch not in ROUTES_BY_BATCH
    assert route.products == (
        "pokeyellow",
        "pokeyellow_debug",
        "pokeyellow_vc",
        "pokeyellow_phase2_audit",
    )
    assert all(
        checkpoint.expected_presentation == "yellow"
        and checkpoint.fallback_authority
        == "engine/full_color/passive_overworld.asm#PassiveFullColorIsPresentedSliceMap"
        for checkpoint in route.checkpoints
    )

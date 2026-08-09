"""Deterministic Yellow map-background review atlases.

The producer deliberately keeps pictures as review evidence, not authority.  Tile
and block graphics come from the Yellow checkout while palettes and attributes are
read back from one linked product and checked against their linked symbols.  The
manifest binds both inputs, every emitted PNG, and the exact map/tileset order.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Sequence
import uuid

from PIL import Image, ImageDraw

from .map_background_content import (
    MapBackgroundAuthority,
    production_map_override_rules,
)
from .rom_discovery import SymbolTable, load_sym


SCHEMA = "full-color-map-background-atlas-v1"
MANIFEST_NAME = "manifest.json"
TILE_COUNT = 256
TILE_SIZE = 8
ATLAS_COLUMNS = 16
ATLAS_CELL = (52, 50)

# This is the exact closed partition approved by the Phase 3 plan.  The later
# missing-content batches are intentionally not silently admitted here.
BATCH_TILESETS = {
    "overworld": ("OVERWORLD",),
    "residential-services": (
        "REDS_HOUSE_1",
        "REDS_HOUSE_2",
        "MART",
        "POKECENTER",
        "HOUSE",
        "FOREST_GATE",
        "MUSEUM",
        "GATE",
        "LOBBY",
        "LAB",
        "CLUB",
    ),
    "challenge-special-interiors": (
        "DOJO",
        "GYM",
        "UNDERGROUND",
        "SHIP",
        "CEMETERY",
        "INTERIOR",
        "MANSION",
        "FACILITY",
    ),
}

_SOURCE_STEM = {
    "OVERWORLD": "overworld",
    "REDS_HOUSE_1": "reds_house",
    "REDS_HOUSE_2": "reds_house",
    "MART": "pokecenter",
    "POKECENTER": "pokecenter",
    "DOJO": "gym",
    "GYM": "gym",
    "HOUSE": "house",
    "FOREST_GATE": "gate",
    "MUSEUM": "gate",
    "GATE": "gate",
    "UNDERGROUND": "underground",
    "SHIP": "ship",
    "CEMETERY": "cemetery",
    "INTERIOR": "interior",
    "LOBBY": "lobby",
    "MANSION": "mansion",
    "LAB": "lab",
    "CLUB": "club",
    "FACILITY": "facility",
}

_LINKED_STEM = {
    "OVERWORLD": "Overworld",
    "REDS_HOUSE_1": "RedsHouse1",
    "REDS_HOUSE_2": "RedsHouse2",
    "MART": "Mart",
    "POKECENTER": "Pokecenter",
    "DOJO": "Dojo",
    "GYM": "Gym",
    "HOUSE": "House",
    "FOREST_GATE": "ForestGate",
    "MUSEUM": "Museum",
    "GATE": "Gate",
    "UNDERGROUND": "Underground",
    "SHIP": "Ship",
    "CEMETERY": "Cemetery",
    "INTERIOR": "Interior",
    "LOBBY": "Lobby",
    "MANSION": "Mansion",
    "LAB": "Lab",
    "CLUB": "Club",
    "FACILITY": "Facility",
}


class MapBackgroundAtlasError(ValueError):
    """Atlas inputs are incomplete or disagree with the linked product."""


@dataclass(frozen=True, slots=True)
class LinkedPayload:
    symbol: str
    bank: int
    address: int
    rom_offset: int
    data: bytes

    def manifest(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "bank": self.bank,
            "address": self.address,
            "rom_offset": self.rom_offset,
            "size": len(self.data),
            "sha256": _sha(self.data),
        }


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=9)


def _linked_payload(
    rom: bytes, symbols: SymbolTable, symbol_name: str, size: int
) -> LinkedPayload:
    try:
        symbol = symbols.by_name[symbol_name]
        end = symbols.by_name[f"{symbol_name}End"]
    except KeyError as exc:
        raise MapBackgroundAtlasError(f"missing linked symbol {exc.args[0]}") from exc
    if (end.bank, end.address) != (symbol.bank, symbol.address + size):
        raise MapBackgroundAtlasError(
            f"{symbol_name}: linked payload is not exactly {size} bytes"
        )
    data = rom[symbol.rom_offset : symbol.rom_offset + size]
    if len(data) != size:
        raise MapBackgroundAtlasError(f"{symbol_name}: linked payload exceeds ROM")
    return LinkedPayload(
        symbol_name, symbol.bank, symbol.address, symbol.rom_offset, data
    )


def _linked_source(
    rom: bytes, symbols: SymbolTable, symbol_name: str, source: bytes
) -> LinkedPayload:
    try:
        symbol = symbols.by_name[symbol_name]
    except KeyError as exc:
        raise MapBackgroundAtlasError(f"missing linked symbol {symbol_name}") from exc
    data = rom[symbol.rom_offset : symbol.rom_offset + len(source)]
    if data != source:
        raise MapBackgroundAtlasError(
            f"{symbol_name}: Yellow source bytes disagree with linked ROM"
        )
    return LinkedPayload(
        symbol_name, symbol.bank, symbol.address, symbol.rom_offset, data
    )


def _rgb555(raw: bytes) -> tuple[int, int, int]:
    value = int.from_bytes(raw, "little")
    return tuple(((value >> shift) & 31) * 255 // 31 for shift in (0, 5, 10))


def decode_palettes(raw: bytes) -> tuple[tuple[tuple[int, int, int], ...], ...]:
    """Decode eight CGB RGB555 palettes from the linked payload."""
    if len(raw) != 64:
        raise MapBackgroundAtlasError("palette payload must be exactly 64 bytes")
    return tuple(
        tuple(_rgb555(raw[offset : offset + 2]) for offset in range(base, base + 8, 2))
        for base in range(0, 64, 8)
    )


def decode_2bpp(raw: bytes) -> tuple[tuple[int, ...], ...]:
    if len(raw) % 16:
        raise MapBackgroundAtlasError("2bpp source is not tile aligned")
    tiles = []
    for base in range(0, len(raw), 16):
        pixels = []
        for row in range(8):
            low, high = raw[base + row * 2 : base + row * 2 + 2]
            pixels.extend(
                (((high >> bit) & 1) << 1) | ((low >> bit) & 1)
                for bit in range(7, -1, -1)
            )
        tiles.append(tuple(pixels))
    return tuple(tiles)


def render_tile(
    pixels: tuple[int, ...] | None,
    palette: tuple[tuple[int, int, int], ...],
    *,
    scale: int = 1,
) -> Image.Image:
    image = Image.new("RGB", (8, 8), palette[0])
    if pixels is None:
        # Missing source graphics and dynamically loaded text/UI identities use
        # a neutral hatch.  The semantic record distinguishes those cases.
        for y in range(8):
            for x in range(8):
                image.putpixel(
                    (x, y), (230, 230, 230) if (x + y) & 1 else (255, 255, 255)
                )
    else:
        image.putdata([palette[value] for value in pixels])
    if scale != 1:
        image = image.resize((8 * scale, 8 * scale), Image.Resampling.NEAREST)
    return image


def _tile_semantics(blockset: bytes, source_tile_count: int) -> list[str]:
    used = set(blockset)
    return [
        "text-reserved"
        if tile_id >= 0x60
        else "missing"
        if tile_id >= source_tile_count
        else "used"
        if tile_id in used
        else "unused"
        for tile_id in range(TILE_COUNT)
    ]


def render_tileset_atlas(
    graphics: bytes,
    palettes_raw: bytes,
    attributes: bytes,
    blockset: bytes,
) -> tuple[Image.Image, list[dict[str, object]]]:
    """Render all 256 identities, including unused and text-reserved slots."""
    if len(attributes) != TILE_COUNT:
        raise MapBackgroundAtlasError("attribute payload must cover all 256 tile IDs")
    if any(value & 0xF8 for value in attributes):
        raise MapBackgroundAtlasError("attribute payload uses unsupported CGB bits")
    tiles = decode_2bpp(graphics)
    palettes = decode_palettes(palettes_raw)
    semantics = _tile_semantics(blockset, len(tiles))
    cell_w, cell_h = ATLAS_CELL
    image = Image.new("RGB", (ATLAS_COLUMNS * cell_w, 16 * cell_h), "white")
    draw = ImageDraw.Draw(image)
    metadata = []
    for tile_id in range(TILE_COUNT):
        x = tile_id % ATLAS_COLUMNS * cell_w
        y = tile_id // ATLAS_COLUMNS * cell_h
        attribute = attributes[tile_id]
        pixels = tiles[tile_id] if tile_id < len(tiles) else None
        image.paste(
            render_tile(pixels, palettes[attribute & 7], scale=4), (x + 2, y + 14)
        )
        draw.text((x + 2, y + 2), f"{tile_id:02X} p{attribute & 7}", fill="black")
        draw.text((x + 2, y + 46), semantics[tile_id][:8], fill="black")
        metadata.append(
            {
                "tile_id": tile_id,
                "palette": attribute & 7,
                "attribute": attribute,
                "semantic": semantics[tile_id],
                "source_graphic": tile_id < len(tiles),
            }
        )
    return image, metadata


def _map_sources(
    root: Path, authority: MapBackgroundAuthority
) -> dict[str, tuple[str, str, Path]]:
    block_sources: dict[str, Path] = {}
    pending: list[str] = []
    for raw_line in (root / "maps.asm").read_text(encoding="utf-8").splitlines():
        line = raw_line.split(";", 1)[0].strip()
        label = re.fullmatch(r"([A-Za-z0-9_]+)_Blocks:", line)
        inline = re.fullmatch(
            r'([A-Za-z0-9_]+)_Blocks:\s+INCBIN\s+"([^"]+\.blk)"', line
        )
        incbin = re.fullmatch(r'INCBIN\s+"([^"]+\.blk)"', line)
        if inline is not None:
            path = root / inline.group(2)
            for name in (*pending, inline.group(1)):
                block_sources[name] = path
            pending.clear()
        elif label is not None:
            pending.append(label.group(1))
        elif incbin is not None:
            path = root / incbin.group(1)
            for name in pending:
                block_sources[name] = path
            pending.clear()
        elif line and not line.startswith(("SECTION", "INCLUDE")):
            pending.clear()

    pointer_source = (root / "data/maps/map_header_pointers.asm").read_text(
        encoding="utf-8"
    )
    pointer_names = []
    for raw_line in pointer_source.splitlines():
        match = re.fullmatch(
            r"dw\s+([A-Za-z0-9_]+)_h", raw_line.split(";", 1)[0].strip()
        )
        if match is not None:
            pointer_names.append(match.group(1))
    by_id = {row.id: row for row in authority.maps}
    source_constants = {}
    header_pattern = re.compile(
        r"^\s*map_header\s+([A-Za-z0-9_]+),\s*([A-Z0-9_]+),", re.MULTILINE
    )
    for header_path in (root / "data/maps/headers").glob("*.asm"):
        match = header_pattern.search(header_path.read_text(encoding="utf-8"))
        if match is not None:
            source_constants[match.group(1)] = match.group(2)
    result = {}
    for map_id, source_name in enumerate(pointer_names):
        row = by_id.get(map_id)
        if row is None:
            continue
        try:
            block_path = block_sources[source_name]
        except KeyError as exc:
            raise MapBackgroundAtlasError(
                f"{row.name}: block source {source_name}_Blocks is absent from maps.asm"
            ) from exc
        result[row.name] = (source_name, source_constants[source_name], block_path)
    return result


def _map_dimensions(root: Path) -> dict[str, tuple[int, int]]:
    pattern = re.compile(
        r"^\s*map_const\s+([A-Z0-9_]+),\s*(\d+),\s*(\d+)", re.MULTILINE
    )
    source = (root / "constants/map_constants.asm").read_text(encoding="utf-8")
    return {
        name: (int(width), int(height))
        for name, width, height in pattern.findall(source)
    }


def render_map_sheet(
    map_blocks: bytes,
    *,
    width: int,
    height: int,
    blockset: bytes,
    graphics: bytes,
    palettes_raw: bytes,
    attributes: bytes,
    title: str,
    attribute_overrides: dict[int, int] | None = None,
) -> Image.Image:
    if len(map_blocks) != width * height:
        raise MapBackgroundAtlasError(
            f"{title}: map block count {len(map_blocks)} != {width}x{height}"
        )
    if len(blockset) % 16:
        raise MapBackgroundAtlasError("blockset is not 4x4-tile aligned")
    tiles = decode_2bpp(graphics)
    palettes = decode_palettes(palettes_raw)
    header = 18
    image = Image.new("RGB", (max(width * 32, 240), height * 32 + header), "white")
    ImageDraw.Draw(image).text((3, 3), title, fill="black")
    for block_y in range(height):
        for block_x in range(width):
            block_id = map_blocks[block_y * width + block_x]
            start = block_id * 16
            if start + 16 > len(blockset):
                raise MapBackgroundAtlasError(
                    f"{title}: block ${block_id:02x} is absent"
                )
            for local_y in range(4):
                for local_x in range(4):
                    tile_id = blockset[start + local_y * 4 + local_x]
                    pixels = tiles[tile_id] if tile_id < len(tiles) else None
                    attribute = (attribute_overrides or {}).get(
                        tile_id, attributes[tile_id]
                    )
                    tile = render_tile(pixels, palettes[attribute & 7])
                    image.paste(
                        tile,
                        (
                            block_x * 32 + local_x * 8,
                            header + block_y * 32 + local_y * 8,
                        ),
                    )
    return image


def moving_water_frames(base: bytes) -> tuple[tuple[int, str, bytes], ...]:
    """Apply UpdateMovingBgTiles' exact counter/direction sequence."""
    if len(base) != 16:
        raise MapBackgroundAtlasError("water tile must be exactly 16 bytes")
    current = bytearray(base)
    frames = []
    for counter in (1, 2, 3, 4, 5, 6, 7, 0):
        direction = "left" if counter & 4 else "right"
        if direction == "right":
            current[:] = bytes(((value >> 1) | ((value & 1) << 7)) for value in current)
        else:
            current[:] = bytes(
                (((value << 1) & 0xFF) | (value >> 7)) for value in current
            )
        frames.append((counter, direction, bytes(current)))
    return tuple(frames)


def _animation_frames(
    root: Path, tileset: str, attributes: bytes, palettes: bytes
) -> list[dict[str, object]]:
    if tileset != "OVERWORLD":
        return []
    decoded_palettes = decode_palettes(palettes)
    records = []
    for index, path in enumerate(
        sorted((root / "gfx/tilesets/flower").glob("flower*.2bpp")), 1
    ):
        data = path.read_bytes()
        tile = decode_2bpp(data)[0]
        records.append(
            {
                "identity": "TILEANIM_WATER_FLOWER",
                "observation": "artifact-only-source-frame",
                "kind": "flower",
                "frame": index,
                "tile_id": 0x03,
                "source": path.relative_to(root).as_posix(),
                "source_sha256": _sha(data),
                "image": render_tile(
                    tile, decoded_palettes[attributes[0x03] & 7], scale=8
                ),
            }
        )
    # Water frames follow the routine's post-increment counter: counters 1-3
    # rotate right, 4-7 rotate left, and 0 rotates right.
    routine_path = root / "home/vcopy.asm"
    routine_sha256 = _sha(routine_path.read_bytes())
    base = (root / "gfx/tilesets/overworld.2bpp").read_bytes()[0x14 * 16 : 0x15 * 16]
    previous = base
    for frame, (counter, direction, data) in enumerate(moving_water_frames(base)):
        tile = decode_2bpp(data)[0]
        records.append(
            {
                "identity": "TILEANIM_WATER_FLOWER",
                "observation": "artifact-only-runtime-semantics",
                "kind": "water-rotation",
                "frame": frame,
                "counter": counter,
                "direction": direction,
                "tile_id": 0x14,
                "routine": "UpdateMovingBgTiles",
                "routine_source_path": routine_path.relative_to(root).as_posix(),
                "routine_source_file_sha256": routine_sha256,
                "input_frame_sha256": _sha(previous),
                "output_frame_sha256": _sha(data),
                "image": render_tile(
                    tile, decoded_palettes[attributes[0x14] & 7], scale=8
                ),
            }
        )
        previous = data
    return records


def _replacement_records(root: Path, blockset: bytes) -> list[dict[str, object]]:
    source = (root / "data/tilesets/cut_tree_blocks.asm").read_text(encoding="utf-8")
    pairs = [
        (int(a, 16), int(b, 16))
        for a, b in re.findall(r"db \$([0-9A-Fa-f]{2}), \$([0-9A-Fa-f]{2})", source)
    ]
    records = []
    for before, after in pairs:
        for identity in (before, after):
            if (identity + 1) * 16 > len(blockset):
                raise MapBackgroundAtlasError(
                    f"CUT_TREE block ${identity:02x} is absent"
                )
        records.append(
            {
                "identity": "CUT_TREE",
                "observation": "artifact-only-rendered-pair",
                "before_block": before,
                "after_block": after,
            }
        )
    return records


def _file_record(path: Path, *, root: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "size": len(data),
        "sha256": _sha(data),
    }


def _build_atlases_in_directory(
    root: Path | str,
    output: Path | str,
    *,
    product: str = "pokeyellow",
    batches: Sequence[str] = tuple(BATCH_TILESETS),
) -> dict[str, object]:
    """Build deterministic review artifacts and return their canonical manifest."""
    root, output = Path(root), Path(output)
    unknown = sorted(set(batches) - set(BATCH_TILESETS))
    if unknown:
        raise MapBackgroundAtlasError(f"unknown Phase 3 batch(es): {unknown}")
    authority = MapBackgroundAuthority.load(root)
    override_rules = production_map_override_rules(root)
    rom_path, sym_path = root / f"{product}.gbc", root / f"{product}.sym"
    rom, sym_bytes = rom_path.read_bytes(), sym_path.read_bytes()
    symbols = load_sym(sym_path)
    roof_assignments = _linked_payload(
        rom, symbols, "FullColorOverworldRoofAssignments", 37
    )
    roof_palettes = _linked_payload(rom, symbols, "FullColorOverworldRoofPalettes", 44)
    map_sources, dimensions = _map_sources(root, authority), _map_dimensions(root)
    tileset_rows = {row.name: row for row in authority.tilesets}
    maps_by_tileset: dict[str, list[object]] = {}
    for row in authority.maps:
        maps_by_tileset.setdefault(row.tileset, []).append(row)

    tileset_manifest = []
    all_artifacts: list[dict[str, object]] = []
    for batch in batches:
        for tileset in BATCH_TILESETS[batch]:
            row = tileset_rows[tileset]
            if row.palette_authority is None or row.attribute_authority is None:
                raise MapBackgroundAtlasError(f"{tileset}: review payload is absent")
            stem, linked_stem = _SOURCE_STEM[tileset], _LINKED_STEM[tileset]
            gfx_path, block_path = (
                root / f"gfx/tilesets/{stem}.2bpp",
                root / f"gfx/blocksets/{stem}.bst",
            )
            graphics, blockset = gfx_path.read_bytes(), block_path.read_bytes()
            gfx_link = _linked_source(rom, symbols, f"{linked_stem}_GFX", graphics)
            block_link = _linked_source(rom, symbols, f"{linked_stem}_Block", blockset)
            palette = _linked_payload(rom, symbols, row.palette_authority, 64)
            attributes = _linked_payload(rom, symbols, row.attribute_authority, 256)
            atlas, tile_records = render_tileset_atlas(
                graphics, palette.data, attributes.data, blockset
            )
            atlas_path = output / batch / "tilesets" / f"{tileset.lower()}.png"
            _save_png(atlas, atlas_path)
            all_artifacts.append(_file_record(atlas_path, root=output))

            animation_records = _animation_frames(
                root, tileset, attributes.data, palette.data
            )
            animations = []
            for record in animation_records:
                image = record.pop("image")
                path = (
                    output
                    / batch
                    / "animations"
                    / f"{tileset.lower()}-{record['kind']}-{record['frame']}.png"
                )
                _save_png(image, path)
                artifact = _file_record(path, root=output)
                all_artifacts.append(artifact)
                animations.append({**record, "artifact": artifact})
            replacements = (
                _replacement_records(root, blockset) if tileset == "OVERWORLD" else []
            )
            for index, replacement in enumerate(replacements):
                pair = Image.new("RGB", (64, 50), "white")
                pair_draw = ImageDraw.Draw(pair)
                pair_draw.text((2, 2), "before", fill="black")
                pair_draw.text((35, 2), "after", fill="black")
                for column, key in enumerate(("before_block", "after_block")):
                    block_image = render_map_sheet(
                        bytes((int(replacement[key]),)),
                        width=1,
                        height=1,
                        blockset=blockset,
                        graphics=graphics,
                        palettes_raw=palette.data,
                        attributes=attributes.data,
                        title="",
                    ).crop((0, 18, 32, 50))
                    pair.paste(block_image, (column * 32, 18))
                path = output / batch / "replacements" / f"cut-tree-{index:02d}.png"
                _save_png(pair, path)
                artifact = _file_record(path, root=output)
                all_artifacts.append(artifact)
                replacement["artifact"] = artifact

            map_records = []
            for map_row in sorted(
                maps_by_tileset.get(tileset, []), key=lambda item: (item.name, item.id)
            ):
                try:
                    source_name, source_constant, map_path = map_sources[map_row.name]
                    width, height = dimensions[map_row.name]
                except KeyError as exc:
                    raise MapBackgroundAtlasError(
                        f"{map_row.name}: source identity is absent"
                    ) from exc
                map_bytes = map_path.read_bytes()
                map_palettes = palette.data
                roof_identity = None
                if tileset == "OVERWORLD":
                    roof_identity = roof_assignments.data[map_row.id]
                    adjusted = bytearray(map_palettes)
                    adjusted[50:54] = roof_palettes.data[
                        roof_identity * 4 : roof_identity * 4 + 4
                    ]
                    map_palettes = bytes(adjusted)
                map_overrides = {
                    tile_id: int(rule["palette_value"])
                    for rule in override_rules
                    if rule["map"] == map_row.name
                    for tile_id in rule["tiles"]
                }
                source_width, source_height = width, height
                if len(map_bytes) != width * height:
                    source_width, source_height = dimensions[source_constant]
                    if len(map_bytes) != source_width * source_height:
                        if source_width == 0 or len(map_bytes) % source_width:
                            raise MapBackgroundAtlasError(
                                f"{map_row.name}: source block geometry is not rectangular"
                            )
                        source_height = len(map_bytes) // source_width
                    if source_width == 0:
                        raise MapBackgroundAtlasError(
                            f"{map_row.name}: source block geometry is not rectangular"
                        )
                sheet = render_map_sheet(
                    map_bytes,
                    width=source_width,
                    height=source_height,
                    blockset=blockset,
                    graphics=graphics,
                    palettes_raw=map_palettes,
                    attributes=attributes.data,
                    title=(
                        f"{map_row.name} | {tileset} | "
                        f"{source_width}x{source_height} source blocks"
                    ),
                    attribute_overrides=map_overrides,
                )
                sheet_path = output / batch / "maps" / f"{map_row.name.lower()}.png"
                _save_png(sheet, sheet_path)
                artifact = _file_record(sheet_path, root=output)
                all_artifacts.append(artifact)
                map_records.append(
                    {
                        "id": map_row.id,
                        "name": map_row.name,
                        "source_name": source_name,
                        "source_constant": source_constant,
                        "declared_dimensions_blocks": [width, height],
                        "source_dimensions_blocks": [source_width, source_height],
                        "roof_identity": roof_identity,
                        "attribute_overrides": [
                            {"tile_id": tile_id, "palette": palette_id}
                            for tile_id, palette_id in sorted(map_overrides.items())
                        ],
                        "source": _file_record(map_path, root=root),
                        "artifact": artifact,
                    }
                )
            tileset_manifest.append(
                {
                    "batch": batch,
                    "id": row.id,
                    "name": tileset,
                    "palette": palette.manifest(),
                    "attributes": attributes.manifest(),
                    "graphics_source": _file_record(gfx_path, root=root),
                    "graphics_linked": gfx_link.manifest(),
                    "blockset_source": _file_record(block_path, root=root),
                    "blockset_linked": block_link.manifest(),
                    "atlas": _file_record(atlas_path, root=output),
                    "atlas_dimensions": list(atlas.size),
                    "tile_order": list(range(TILE_COUNT)),
                    "tiles": tile_records,
                    "animations": animations,
                    "replacements": replacements,
                    "maps": map_records,
                }
            )

    manifest = {
        "schema": SCHEMA,
        "producer": "tools.rom_tests.full_color.map_background_atlas",
        "product": product,
        "rom": {"path": rom_path.name, "size": len(rom), "sha256": _sha(rom)},
        "symbols": {
            "path": sym_path.name,
            "size": len(sym_bytes),
            "sha256": _sha(sym_bytes),
        },
        "batches": [
            {"name": name, "tilesets": list(BATCH_TILESETS[name])} for name in batches
        ],
        "tilesets": tileset_manifest,
        "artifacts": sorted(all_artifacts, key=lambda item: str(item["path"])),
    }
    manifest["content_sha256"] = _sha(canonical_json(manifest).encode("utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    (output / MANIFEST_NAME).write_text(canonical_json(manifest), encoding="utf-8")
    return manifest


def _owned_output_entries(output: Path) -> tuple[set[str], list[Path]]:
    """Validate and enumerate one complete tree owned by this producer."""
    if output.is_symlink() or not output.is_dir():
        raise MapBackgroundAtlasError(f"refusing non-directory atlas output: {output}")
    manifest_path = output / MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        if not any(output.iterdir()):
            return set(), []
        raise MapBackgroundAtlasError("existing atlas output lacks a regular manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise MapBackgroundAtlasError("existing atlas manifest is unreadable") from exc
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("producer") != "tools.rom_tests.full_color.map_background_atlas"
    ):
        raise MapBackgroundAtlasError(
            "existing atlas output belongs to another producer"
        )
    owned = {MANIFEST_NAME}
    for record in manifest.get("artifacts", []):
        relative = Path(str(record.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise MapBackgroundAtlasError("existing atlas manifest has an unsafe path")
        owned.add(relative.as_posix())
    actual = set()
    directories = []
    for path in output.rglob("*"):
        if path.is_symlink():
            raise MapBackgroundAtlasError("existing atlas output contains a symlink")
        relative = path.relative_to(output).as_posix()
        if path.is_dir():
            directories.append(path)
        elif path.is_file():
            actual.add(relative)
        else:
            raise MapBackgroundAtlasError(
                "existing atlas output contains a special file"
            )
    if actual != owned:
        raise MapBackgroundAtlasError(
            "existing atlas output contains stale or unowned files"
        )
    return owned, directories


def _remove_owned_output(output: Path) -> None:
    """Remove only a complete output tree declared by this producer."""
    owned, directories = _owned_output_entries(output)
    for relative in sorted(owned):
        (output / relative).unlink()
    for directory in sorted(
        directories, key=lambda path: len(path.parts), reverse=True
    ):
        directory.rmdir()
    output.rmdir()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree_directories(root: Path) -> None:
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for directory in sorted(
        directories, key=lambda path: len(path.parts), reverse=True
    ):
        _fsync_directory(directory)
    _fsync_directory(root)


def _unique_backup_path(output: Path) -> Path:
    for _ in range(32):
        candidate = output.parent / f".{output.name}.backup-{uuid.uuid4().hex}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise MapBackgroundAtlasError("unable to reserve an atlas backup identity")


def _rollback_publication(output: Path, backup: Path) -> None:
    """Restore the validated prior tree, retaining no failed new publication."""
    failed: Path | None = None
    if output.exists() or output.is_symlink():
        failed = _unique_backup_path(output)
        os.replace(output, failed)
        _fsync_directory(output.parent)
    os.replace(backup, output)
    _fsync_directory(output.parent)
    if failed is not None:
        _remove_owned_output(failed)
        _fsync_directory(output.parent)


def build_atlases(
    root: Path | str,
    output: Path | str,
    *,
    product: str = "pokeyellow",
    batches: Sequence[str] = tuple(BATCH_TILESETS),
) -> dict[str, object]:
    """Build into a sibling temporary tree, then publish one stale-free result."""
    root, output = Path(root), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    published = False
    backup: Path | None = None
    try:
        manifest = _build_atlases_in_directory(
            root, temporary, product=product, batches=batches
        )
        _fsync_tree_directories(temporary)
        if output.exists() or output.is_symlink():
            # Validate the complete previous publication before moving it aside.
            # It remains recoverable until the new tree has been published and
            # the containing directory has reached stable storage.
            if output.is_symlink() or not output.is_dir():
                raise MapBackgroundAtlasError(
                    f"refusing non-directory atlas output: {output}"
                )
            _owned_output_entries(output)
            backup = _unique_backup_path(output)
            os.replace(output, backup)
            try:
                _fsync_directory(output.parent)
            except Exception:
                _rollback_publication(output, backup)
                backup = None
                raise
        try:
            os.replace(temporary, output)
            _fsync_directory(output.parent)
        except Exception:
            if backup is not None:
                _rollback_publication(output, backup)
                backup = None
            raise
        published = True
        if backup is not None:
            _remove_owned_output(backup)
            backup = None
            _fsync_directory(output.parent)
        return manifest
    finally:
        if not published and temporary.exists():
            # The temporary tree is producer-created in this call.  Enumerate it
            # without following links instead of applying broad recursive cleanup.
            paths = sorted(
                temporary.rglob("*"), key=lambda path: len(path.parts), reverse=True
            )
            for path in paths:
                if path.is_symlink() or path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            temporary.rmdir()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--product", default="pokeyellow")
    parser.add_argument("--batch", action="append", choices=tuple(BATCH_TILESETS))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    build_atlases(
        args.root,
        args.output,
        product=args.product,
        batches=tuple(args.batch or BATCH_TILESETS),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Canonical source-and-linked-product evidence for map-background content.

Schema ``full-color-map-background-snapshot-v1`` binds the reviewed content
ledger to its source authorities and to the exact bytes linked into all four
repository products.  Proposal generation is unprivileged and never changes
reviewed evidence; promotion requires the explicit ``--authority-reviewed``
acknowledgement.  Ordinary verification is read-only and donor-independent.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import tempfile
from typing import Sequence

from .map_background_content import (
    LEDGER_PATH,
    MapBackgroundAuthority,
    production_map_override_rules,
)
from .rom_discovery import RomDiscoveryError, SymbolTable, load_sym


SCHEMA = "full-color-map-background-snapshot-v1"
MANIFEST_PATH = Path("specs/full-colors/evidence/map-background-content.json")
PRODUCTS = (
    "pokeyellow",
    "pokeyellow_debug",
    "pokeyellow_vc",
    "pokeyellow_phase2_audit",
)
SOURCE_AUTHORITIES = (
    Path("data/tilesets/full_color_overworld.asm"),
    Path("data/tilesets/full_color_interiors.asm"),
    Path("data/tilesets/tileset_headers.asm"),
    Path("data/tilesets/spinner_tiles.asm"),
    Path("constants/map_data_constants.asm"),
    Path("data/tilesets/cut_tree_blocks.asm"),
    Path("data/predef_pointers.asm"),
    Path("engine/overworld/spinners.asm"),
    Path("engine/overworld/update_map.asm"),
    Path("engine/overworld/cut.asm"),
    Path("engine/events/hidden_events/cinnabar_gym_quiz.asm"),
    Path("home/hidden_events.asm"),
    Path("engine/full_color/passive_overworld.asm"),
    Path("engine/full_color/passive_palette_refresh.asm"),
)
POINTER_TABLES = (
    ("palettes", "FullColorBGPalettePointers", "FullColorBGPalettePointersEnd"),
    (
        "attributes",
        "FullColorTileAttributePointers",
        "FullColorTileAttributePointersEnd",
    ),
)
FIXED_PAYLOADS = (
    ("roof_assignments", "FullColorOverworldRoofAssignments", 37),
    ("roof_region_rules", "FullColorOverworldRoofRegionRules", 4),
    ("roof_palettes", "FullColorOverworldRoofPalettes", 44),
    ("map_overrides", "FullColorMapAttributeOverrides", 15),
)


class MapBackgroundSnapshotError(ValueError):
    """Source or linked-product content is incomplete, stale, or malformed."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> str:
    """Return the sole repository representation for reviewed snapshot JSON."""
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    data = (root / relative).read_bytes()
    return {"path": relative.as_posix(), "size": len(data), "sha256": _sha(data)}


def _symbol(table: SymbolTable, name: str):
    try:
        return table.by_name[name]
    except KeyError as exc:
        raise MapBackgroundSnapshotError(f"missing linked symbol {name}") from exc


def _read(
    rom: bytes,
    symbols: SymbolTable,
    name: str,
    size: int,
    *,
    end: str | None = None,
) -> tuple[bytes, dict[str, object]]:
    symbol = _symbol(symbols, name)
    if end is not None:
        end_symbol = _symbol(symbols, end)
        if (end_symbol.bank, end_symbol.address) != (
            symbol.bank,
            symbol.address + size,
        ):
            raise MapBackgroundSnapshotError(
                f"{name}: linked size is not the required {size} bytes"
            )
    offset = symbol.rom_offset
    payload = rom[offset : offset + size]
    if len(payload) != size:
        raise MapBackgroundSnapshotError(f"{name}: payload exceeds linked ROM")
    return payload, {
        "symbol": name,
        "bank": symbol.bank,
        "address": symbol.address,
        "rom_offset": offset,
        "size": size,
        "sha256": _sha(payload),
        "bytes": payload.hex(),
    }


def _pointer_target(symbols: SymbolTable, pointer: int, bank: int) -> tuple[str, ...]:
    if pointer == 0:
        return ()
    aliases = symbols.aliases(bank, pointer)
    return tuple(sorted(aliases))


def _routine_bytes(
    rom: bytes,
    symbols: SymbolTable,
    start_name: str,
    terminal_name: str,
    terminal_bytes: bytes,
) -> tuple[bytes, dict[str, object]]:
    """Read one linked routine through its reviewed terminal instruction bytes."""
    start = _symbol(symbols, start_name)
    terminal = _symbol(symbols, terminal_name)
    if start.bank != terminal.bank or terminal.address < start.address:
        raise MapBackgroundSnapshotError(
            f"{start_name}: terminal identity is outside the linked routine"
        )
    size = terminal.address - start.address + len(terminal_bytes)
    payload = rom[start.rom_offset : start.rom_offset + size]
    if len(payload) != size or not payload.endswith(terminal_bytes):
        raise MapBackgroundSnapshotError(
            f"{start_name}: linked terminal instruction contract drifted"
        )
    return payload, {
        "symbol": start_name,
        "bank": start.bank,
        "address": start.address,
        "rom_offset": start.rom_offset,
        "size": size,
        "sha256": _sha(payload),
    }


def _reference_bytes(symbols: SymbolTable, name: str, opcodes: Sequence[int]) -> tuple[bytes, ...]:
    target = _symbol(symbols, name)
    address = target.address.to_bytes(2, "little")
    return tuple(bytes((opcode,)) + address for opcode in opcodes)


def _require_reference(
    payload: bytes,
    symbols: SymbolTable,
    source: str,
    target: str,
    *,
    opcodes: Sequence[int],
    count: int = 1,
) -> None:
    found = sum(payload.count(pattern) for pattern in _reference_bytes(symbols, target, opcodes))
    if found != count:
        raise MapBackgroundSnapshotError(
            f"{source}: linked reference to {target} must occur exactly {count} time(s)"
        )


def _require_sequence(payload: bytes, source: str, identity: str, sequence: bytes) -> None:
    if payload.count(sequence) != 1:
        raise MapBackgroundSnapshotError(
            f"{source}: linked {identity} instruction contract drifted"
        )


def _consumer_contracts(
    rom: bytes, symbols: SymbolTable
) -> dict[str, dict[str, object]]:
    """Prove every reviewed map semantic has a linked production consumer."""
    override, override_record = _routine_bytes(
        rom,
        symbols,
        "PassiveFullColorResolveAttributeForIdentity",
        "PassiveFullColorResolveAttributeForIdentity.done",
        b"\xc1\xd1\xe1\xc9",
    )
    override_table = _symbol(symbols, "FullColorMapAttributeOverrides")
    attribute_table = _symbol(symbols, "FullColorTileAttributePointers")
    override_prefix = bytes(
        (
            0xE5,
            0x21,
            override_table.address & 0xFF,
            override_table.address >> 8,
            0x06,
            0x02,
        )
    )
    fallback = bytes(
        (
            0xE1,
            0x7C,
            0x87,
            0x5F,
            0x16,
            0x00,
            0x21,
            attribute_table.address & 0xFF,
            attribute_table.address >> 8,
        )
    )
    if not override.startswith(override_prefix) or override.count(fallback) != 1:
        raise MapBackgroundSnapshotError(
            "map attribute overrides are not bounded before tileset fallback"
        )
    if override.index(override_prefix) >= override.index(fallback):
        raise MapBackgroundSnapshotError(
            "map attribute overrides no longer precede tileset fallback"
        )
    _require_sequence(
        override,
        "PassiveFullColorResolveAttributeForIdentity",
        "full-byte override result",
        b"\x2a\x47\x2a\x5f",
    )
    _require_sequence(
        override,
        "PassiveFullColorResolveAttributeForIdentity",
        "bounded override tile loop",
        b"\x2a\xb9\x28\x05\x05\x20\xf9",
    )
    _require_sequence(
        override,
        "PassiveFullColorResolveAttributeForIdentity",
        "unmasked full-byte return",
        b"\x7b\xe1\x18",
    )

    roof_select, roof_select_record = _routine_bytes(
        rom,
        symbols,
        "PassiveFullColorRoofPaletteForMap",
        "PassiveFullColorRoofPaletteForMap.resolve",
        b"\x87\x87\x4f\x06\x00\x21"
        + _symbol(symbols, "FullColorOverworldRoofPalettes").address.to_bytes(2, "little")
        + b"\x09\xc9",
    )
    roof_invalidate, roof_invalidate_record = _routine_bytes(
        rom,
        symbols,
        "PassiveFullColorRoofRegionChanged",
        "PassiveFullColorRoofRegionChanged.unchanged",
        b"\xa7\xc9",
    )
    roof_rule, roof_rule_record = _routine_bytes(
        rom,
        symbols,
        "PassiveFullColorCurrentRoofRegion",
        "PassiveFullColorCurrentRoofRegion.resolved",
        b"\x4e\xe1\xc9",
    )
    _require_reference(
        roof_rule,
        symbols,
        "PassiveFullColorCurrentRoofRegion",
        "FullColorOverworldRoofRegionRules",
        opcodes=(0x21,),
    )
    for source, payload in (
        ("PassiveFullColorRoofPaletteForMap", roof_select),
        ("PassiveFullColorRoofRegionChanged", roof_invalidate),
    ):
        _require_reference(
            payload,
            symbols,
            source,
            "PassiveFullColorCurrentRoofRegion",
            opcodes=(0xCD,),
        )

    spinner, spinner_record = _routine_bytes(
        rom,
        symbols,
        "LoadSpinnerArrowTiles",
        "LoadSpinnerArrowTiles.loop",
        b"\xf5\xe5\xc5\x09\x2a\x5f\x2a\x57\x2a\x4f\x2a\x47\x2a\x66\x6f"
        + b"\xcd"
        + _symbol(symbols, "CopyVideoData").address.to_bytes(2, "little")
        + b"\xc1\x3e\x06\x81\x4f\xe1\xf1\x3d\x20\xe4\xc9",
    )
    for target in ("FacilitySpinnerArrows", "GymSpinnerArrows"):
        _require_reference(
            spinner, symbols, "LoadSpinnerArrowTiles", target, opcodes=(0x21,)
        )
    _require_reference(
        spinner,
        symbols,
        "LoadSpinnerArrowTiles",
        "CopyVideoData",
        opcodes=(0xCD,),
    )
    _require_sequence(spinner, "LoadSpinnerArrowTiles", "four-tile bound", b"\x3e\x04")

    replace, replace_record = _routine_bytes(
        rom,
        symbols,
        "ReplaceTileBlock",
        "RedrawMapView",
        b"",
    )
    _require_reference(
        replace,
        symbols,
        "ReplaceTileBlock",
        "GetPredefRegisters",
        opcodes=(0xCD,),
    )
    _require_reference(
        replace, symbols, "ReplaceTileBlock", "wOverworldMap", opcodes=(0x21,)
    )
    _require_sequence(
        replace,
        "ReplaceTileBlock",
        "map block writer",
        b"\xfa" + _symbol(symbols, "wNewTileBlockID").address.to_bytes(2, "little") + b"\x77",
    )
    predef, predef_record = _read(rom, symbols, "ReplaceTileBlockPredef", 3)
    expected_predef = bytes(
        (
            _symbol(symbols, "ReplaceTileBlock").bank,
            _symbol(symbols, "ReplaceTileBlock").address & 0xFF,
            _symbol(symbols, "ReplaceTileBlock").address >> 8,
        )
    )
    if predef != expected_predef:
        raise MapBackgroundSnapshotError(
            "ReplaceTileBlockPredef: linked caller identity does not bind ReplaceTileBlock"
        )

    cut, cut_record = _routine_bytes(
        rom, symbols, "UsedCut", "UsedCutText", b""
    )
    cut_writer, cut_writer_record = _routine_bytes(
        rom,
        symbols,
        "ReplaceTreeTileBlock",
        "ReplaceTreeTileBlock.loop",
        b"\x1a\x13\x13\xfe\xff\xc8\xb9\x20\xf7\x1b\x1a\x77\xc9",
    )
    _require_reference(
        cut, symbols, "UsedCut", "CutTreeBlockSwaps", opcodes=(0x11,)
    )
    _require_reference(
        cut, symbols, "UsedCut", "ReplaceTreeTileBlock", opcodes=(0xCD,)
    )
    _require_reference(
        cut_writer,
        symbols,
        "ReplaceTreeTileBlock",
        "wCurrentTileBlockMapViewPointer",
        opcodes=(0x21,),
    )
    _require_sequence(cut_writer, "ReplaceTreeTileBlock", "map block writer", b"\x1b\x1a\x77\xc9")

    cinnabar, cinnabar_record = _routine_bytes(
        rom,
        symbols,
        "UpdateCinnabarGymGateTileBlocks_",
        "UpdateCinnabarGymGateTileBlocks_.next",
        b"\xc1\xea"
        + _symbol(symbols, "wNewTileBlockID").address.to_bytes(2, "little")
        + b"\xcd"
        + _symbol(symbols, "CinnabarGym_ReplaceTileBlock").address.to_bytes(2, "little")
        + b"\x21\xdb\xff\x35\x20\xc9\x21"
        + _symbol(symbols, "RedrawMapView").address.to_bytes(2, "little")
        + b"\x06"
        + bytes((_symbol(symbols, "RedrawMapView").bank,))
        + b"\xcd"
        + _symbol(symbols, "Bankswitch").address.to_bytes(2, "little")
        + b"\xc9",
    )
    cinnabar_writer, cinnabar_writer_record = _routine_bytes(
        rom,
        symbols,
        "CinnabarGym_ReplaceTileBlock",
        "CinnabarGym_ReplaceTileBlock.addX",
        b"\x09\xfa"
        + _symbol(symbols, "wNewTileBlockID").address.to_bytes(2, "little")
        + b"\x77\xc9",
    )
    cinnabar_entry, cinnabar_entry_record = _routine_bytes(
        rom,
        symbols,
        "UpdateCinnabarGymGateTileBlocks",
        "UpdateCinnabarGymGateTileBlocks",
        b"\x06"
        + bytes((_symbol(symbols, "UpdateCinnabarGymGateTileBlocks_").bank,))
        + b"\x21"
        + _symbol(symbols, "UpdateCinnabarGymGateTileBlocks_").address.to_bytes(2, "little")
        + b"\xcd"
        + _symbol(symbols, "Bankswitch").address.to_bytes(2, "little")
        + b"\xc9",
    )
    _require_reference(
        cinnabar,
        symbols,
        "UpdateCinnabarGymGateTileBlocks_",
        "CinnabarGymGateCoords",
        opcodes=(0x21,),
    )
    _require_reference(
        cinnabar,
        symbols,
        "UpdateCinnabarGymGateTileBlocks_",
        "CinnabarGym_ReplaceTileBlock",
        opcodes=(0xCD,),
    )
    _require_sequence(
        cinnabar_writer,
        "CinnabarGym_ReplaceTileBlock",
        "map block writer",
        b"\xfa" + _symbol(symbols, "wNewTileBlockID").address.to_bytes(2, "little") + b"\x77\xc9",
    )
    _require_reference(
        cinnabar_writer,
        symbols,
        "CinnabarGym_ReplaceTileBlock",
        "wOverworldMap",
        opcodes=(0x21,),
    )

    return {
        "MAP_ATTRIBUTE_OVERRIDES": {
            "routines": [override_record],
            "edges": [
                "FullColorMapAttributeOverrides->PassiveFullColorResolveAttributeForIdentity",
                "PassiveFullColorResolveAttributeForIdentity->FullColorTileAttributePointers",
            ],
        },
        "ROOF_REGION_RULES": {
            "routines": [roof_rule_record, roof_select_record, roof_invalidate_record],
            "edges": [
                "FullColorOverworldRoofRegionRules->PassiveFullColorCurrentRoofRegion",
                "PassiveFullColorCurrentRoofRegion->PassiveFullColorRoofPaletteForMap",
                "PassiveFullColorCurrentRoofRegion->PassiveFullColorRoofRegionChanged",
            ],
        },
        "SPINNER_ARROW_TILES": {
            "routines": [spinner_record],
            "edges": [
                "FacilitySpinnerArrows->LoadSpinnerArrowTiles",
                "GymSpinnerArrows->LoadSpinnerArrowTiles",
                "LoadSpinnerArrowTiles->CopyVideoData",
            ],
        },
        "REPLACE_TILE_BLOCK": {
            "routines": [replace_record, predef_record],
            "edges": ["ReplaceTileBlockPredef->ReplaceTileBlock->wOverworldMap"],
        },
        "CUT_TREE": {
            "routines": [cut_record, cut_writer_record],
            "edges": ["CutTreeBlockSwaps->UsedCut->ReplaceTreeTileBlock->wOverworldMap"],
        },
        "CINNABAR_GYM_GATE_BLOCKS": {
            "routines": [cinnabar_entry_record, cinnabar_record, cinnabar_writer_record],
            "edges": [
                "UpdateCinnabarGymGateTileBlocks->UpdateCinnabarGymGateTileBlocks_",
                "CinnabarGymGateCoords->UpdateCinnabarGymGateTileBlocks_->CinnabarGym_ReplaceTileBlock->wOverworldMap",
            ],
        },
    }


def _validate_map_override_data(
    rom: bytes,
    symbols: SymbolTable,
    authority: MapBackgroundAuthority,
    rules: tuple[dict[str, object], ...],
) -> None:
    """Bind semantic override rules to the exact compact linked records."""
    if len(rules) != 2:
        raise MapBackgroundSnapshotError(
            "map override semantics must define exactly two production rules"
        )
    roof, first_floor = rules
    expected_rule_shapes = (
        (
            roof,
            "CELADON_MART_ROOF_TILES_4B_TO_4F_BLUE",
            "CELADON_MART_ROOF",
            "inclusive-range",
            [0x4B, 0x4C, 0x4D, 0x4E, 0x4F],
            "FULL_COLOR_INTERIOR_BLUE",
        ),
        (
            first_floor,
            "CELADON_MART_1F_TILES_07_08_17_18_YELLOW",
            "CELADON_MART_1F",
            "exact-set",
            [0x07, 0x08, 0x17, 0x18],
            "FULL_COLOR_INTERIOR_YELLOW",
        ),
    )
    for rule, identity, map_name, match, tiles, palette in expected_rule_shapes:
        if (
            rule.get("identity") != identity
            or rule.get("map") != map_name
            or rule.get("match") != match
            or rule.get("tiles") != tiles
            or rule.get("palette") != palette
        ):
            raise MapBackgroundSnapshotError(
                f"{map_name}: semantic map override shape is not production-exact"
            )
        palette_value = rule.get("palette_value")
        if (
            isinstance(palette_value, bool)
            or not isinstance(palette_value, int)
            or not 0 <= palette_value <= 7
        ):
            raise MapBackgroundSnapshotError(
                f"{map_name}: semantic palette immediate is outside palette bits"
            )

    map_ids = {row.name: row.id for row in authority.maps}
    expected = bytearray()
    for rule in rules:
        map_name = str(rule["map"])
        try:
            map_id = map_ids[map_name]
        except KeyError as exc:
            raise MapBackgroundSnapshotError(
                f"map override semantics name an unknown map: {map_name}"
            ) from exc
        tiles = rule["tiles"]
        palette_value = rule["palette_value"]
        assert isinstance(tiles, list) and isinstance(palette_value, int)
        if not 0 <= map_id <= 0xFF or not 1 <= len(tiles) <= 0xFF:
            raise MapBackgroundSnapshotError(
                f"{map_name}: override identity or tile count exceeds one byte"
            )
        expected.extend((map_id, len(tiles), palette_value, *tiles))

    actual, _ = _read(
        rom,
        symbols,
        "FullColorMapAttributeOverrides",
        len(expected),
        end="FullColorMapAttributeOverridesEnd",
    )
    if actual != expected:
        raise MapBackgroundSnapshotError(
            "linked map override data contradicts semantic rules or exact values"
        )


def _validate_roof_region_data(
    rom: bytes, symbols: SymbolTable, authority: MapBackgroundAuthority
) -> None:
    """Require Route 6 palette selection and invalidation to share one record."""
    map_ids = {row.name: row.id for row in authority.maps}
    try:
        route_6 = map_ids["ROUTE_6"]
        saffron_city = map_ids["SAFFRON_CITY"]
    except KeyError as exc:
        raise MapBackgroundSnapshotError(
            f"roof-region semantics name an unknown map: {exc.args[0]}"
        ) from exc
    assignments, _ = _read(
        rom,
        symbols,
        "FullColorOverworldRoofAssignments",
        37,
        end="FullColorOverworldRoofAssignmentsEnd",
    )
    expected = bytes(
        (route_6, 2, assignments[saffron_city], assignments[route_6])
    )
    actual, _ = _read(
        rom,
        symbols,
        "FullColorOverworldRoofRegionRules",
        len(expected),
        end="FullColorOverworldRoofRegionRulesEnd",
    )
    if actual != expected:
        raise MapBackgroundSnapshotError(
            "linked roof-region data contradicts Route 6 reviewed semantics"
        )


def _product_snapshot(
    root: Path,
    product: str,
    authority: MapBackgroundAuthority,
    override_rules: tuple[dict[str, object], ...],
) -> dict[str, object]:
    rom_path = root / f"{product}.gbc"
    sym_path = root / f"{product}.sym"
    map_path = root / f"{product}.map"
    try:
        rom = rom_path.read_bytes()
        symbols = load_sym(sym_path)
        map_bytes = map_path.read_bytes()
    except (OSError, UnicodeError, RomDiscoveryError) as exc:
        raise MapBackgroundSnapshotError(
            f"{product}: invalid linked artifacts: {exc}"
        ) from exc

    _validate_map_override_data(rom, symbols, authority, override_rules)
    _validate_roof_region_data(rom, symbols, authority)
    linked_consumers = _consumer_contracts(rom, symbols)

    payloads: dict[str, dict[str, object]] = {}
    unique_payloads = sorted(
        {
            (row.palette_authority, 64, "palette")
            for row in authority.tilesets
            if row.palette_authority is not None
        }
        | {
            (row.attribute_authority, 256, "attribute")
            for row in authority.tilesets
            if row.attribute_authority is not None
        }
    )
    for name, size, kind in unique_payloads:
        assert name is not None
        payload, record = _read(rom, symbols, name, size, end=f"{name}End")
        if kind == "attribute" and any(value & 0xF8 for value in payload):
            raise MapBackgroundSnapshotError(
                f"{name}: attributes must use palette bits only (0-7)"
            )
        payloads[name] = {"kind": kind, **record}

    pointer_tables: dict[str, object] = {}
    for kind, name, end in POINTER_TABLES:
        expected = [
            row.palette_authority if kind == "palettes" else row.attribute_authority
            for row in authority.tilesets
        ]
        raw, record = _read(rom, symbols, name, len(expected) * 2, end=end)
        source_bank = _symbol(symbols, name).bank
        rows: list[dict[str, object]] = []
        for index, (tileset, expected_name) in enumerate(
            zip(authority.tilesets, expected, strict=True)
        ):
            pointer = int.from_bytes(raw[index * 2 : index * 2 + 2], "little")
            aliases = _pointer_target(symbols, pointer, source_bank)
            if expected_name is None:
                if pointer != 0:
                    raise MapBackgroundSnapshotError(
                        f"{product}:{name}:{tileset.name}: expected null pointer"
                    )
            else:
                target = _symbol(symbols, expected_name)
                if target.bank != source_bank or pointer != target.address:
                    raise MapBackgroundSnapshotError(
                        f"{product}:{name}:{tileset.name}: pointer does not bind "
                        f"{expected_name}"
                    )
                if expected_name not in aliases:
                    raise MapBackgroundSnapshotError(
                        f"{product}:{name}:{tileset.name}: symbol alias identity missing"
                    )
            rows.append(
                {
                    "tileset_id": tileset.id,
                    "tileset": tileset.name,
                    "pointer": pointer,
                    "authority": expected_name,
                    "aliases": list(aliases),
                }
            )
        pointer_tables[kind] = {**record, "rows": rows}

    fixed: dict[str, object] = {}
    for key, name, size in FIXED_PAYLOADS:
        payload, record = _read(rom, symbols, name, size, end=f"{name}End")
        if key == "roof_assignments" and any(value >= 11 for value in payload):
            raise MapBackgroundSnapshotError(
                "roof assignment exceeds reviewed roof identity"
            )
        fixed[key] = record

    return {
        "product": product,
        "artifacts": {
            "rom": {"path": rom_path.name, "size": len(rom), "sha256": _sha(rom)},
            "sym": {"path": sym_path.name, "sha256": _sha(sym_path.read_bytes())},
            "map": {"path": map_path.name, "sha256": _sha(map_bytes)},
        },
        "pointer_tables": pointer_tables,
        "payloads": payloads,
        "linked_consumers": linked_consumers,
        **fixed,
    }


def _parity_view(product: dict[str, object]) -> dict[str, object]:
    payloads = product["payloads"]
    tables = product["pointer_tables"]
    assert isinstance(payloads, dict) and isinstance(tables, dict)
    return {
        "payloads": {
            name: {key: row[key] for key in ("kind", "size", "sha256", "bytes")}
            for name, row in payloads.items()
        },
        "pointer_identities": {
            kind: [
                {
                    "tileset_id": row["tileset_id"],
                    "tileset": row["tileset"],
                    "authority": row["authority"],
                }
                for row in table["rows"]
            ]
            for kind, table in tables.items()
        },
        "roof_assignments": {
            key: product["roof_assignments"][key] for key in ("size", "sha256", "bytes")
        },
        "roof_region_rules": {
            key: product["roof_region_rules"][key]
            for key in ("size", "sha256", "bytes")
        },
        "roof_palettes": {
            key: product["roof_palettes"][key] for key in ("size", "sha256", "bytes")
        },
        "map_overrides": {
            key: product["map_overrides"][key] for key in ("size", "sha256", "bytes")
        },
        "linked_consumers": product["linked_consumers"],
    }


def _cross_product_view(product: dict[str, object]) -> dict[str, object]:
    view = _parity_view(product)
    consumers = view["linked_consumers"]
    assert isinstance(consumers, dict)
    view["linked_consumers"] = {
        identity: {
            "routines": [row["symbol"] for row in contract["routines"]],
            "edges": contract["edges"],
        }
        for identity, contract in consumers.items()
    }
    return view


def _source_fingerprint(root: Path) -> tuple[tuple[str, str], ...]:
    paths = (*SOURCE_AUTHORITIES, Path("main.asm"), Path("includes.asm"))
    fingerprint = [
        (path.as_posix(), _sha((root / path).read_bytes())) for path in paths
    ]
    for path in (Path("layout.link"), Path("Makefile")):
        fingerprint.append((path.as_posix(), _sha((root / path).read_bytes())))
    return tuple(fingerprint)


def _build_products_from_source(root: Path, output: Path) -> Path:
    """Build all products in a private checkout copy and return its root."""
    output.mkdir(parents=True, exist_ok=True)
    build_root = output / "repository"
    shutil.copytree(
        root,
        build_root,
        symlinks=False,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".references",
            ".preemdeck",
            "test-results",
            "*.o",
            "*.gbc",
            "*.sym",
            "*.map",
            "*.patch",
            "*.2bpp",
            "*.1bpp",
            "*.pic",
            "*.pcm",
        ),
    )
    subprocess.run(
        [
            "make",
            "-j2",
            "yellow",
            "yellow_debug",
            "yellow_vc",
            "yellow_phase2_audit",
        ],
        cwd=build_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return build_root


@lru_cache(maxsize=8)
def _fresh_source_view_cached(
    root_text: str, fingerprint: tuple[tuple[str, str], ...]
) -> dict[str, object]:
    del fingerprint
    root = Path(root_text)
    try:
        with tempfile.TemporaryDirectory(prefix="map-background-source-") as temporary:
            output = Path(temporary)
            authority = MapBackgroundAuthority.load(root)
            override_rules = production_map_override_rules(root)
            build_root = _build_products_from_source(root, output)
            views: dict[str, object] = {}
            for product_name in PRODUCTS:
                views[product_name] = _parity_view(
                    _product_snapshot(
                        build_root, product_name, authority, override_rules
                    )
                )
            return views
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = (
            exc.stderr.strip()
            if isinstance(exc, subprocess.CalledProcessError)
            else str(exc)
        )
        raise MapBackgroundSnapshotError(
            f"cannot derive fresh map-background product from source: {detail}"
        ) from exc


def _fresh_source_view(root: Path) -> dict[str, object]:
    return _fresh_source_view_cached(str(root), _source_fingerprint(root))


def generate(root: Path | str) -> dict[str, object]:
    """Extract and validate the current source and four linked products."""
    root = Path(root).resolve()
    authority = MapBackgroundAuthority.load(root)
    override_rules = production_map_override_rules(root)
    ledger_bytes = (root / LEDGER_PATH).read_bytes()
    try:
        ledger_value = json.loads(ledger_bytes)
    except json.JSONDecodeError as exc:
        raise MapBackgroundSnapshotError(f"ledger is not JSON: {exc}") from exc
    ledger_canonical = canonical_json(ledger_value).encode()
    products = [
        _product_snapshot(root, product, authority, override_rules)
        for product in PRODUCTS
    ]
    reference = _cross_product_view(products[0])
    for product in products[1:]:
        if _cross_product_view(product) != reference:
            raise MapBackgroundSnapshotError(
                f"{product['product']}: map-background content differs from pokeyellow"
            )
    fresh_source = _fresh_source_view(root)
    for product in products:
        name = str(product["product"])
        if fresh_source[name] != _parity_view(product):
            raise MapBackgroundSnapshotError(
                f"{name}: authored map-background source differs from checked-in linked product"
            )

    tilesets = [row.to_dict() for row in authority.tilesets]
    maps = [row.to_dict() for row in authority.maps]
    semantic = {
        "tilesets": tilesets,
        "maps": maps,
        "tileset_identities_sha256": _sha(canonical_json(tilesets).encode()),
        "map_identities_sha256": _sha(canonical_json(maps).encode()),
        "roofs": [
            {"map_id": row.id, "map": row.name, "roof": row.roof}
            for row in authority.maps
            if row.roof is not None
        ],
        "overrides": [
            {"map_id": row.id, "map": row.name, "identities": list(row.overrides)}
            for row in authority.maps
            if row.overrides
        ],
        "override_rules": list(override_rules),
        "animations": sorted(
            {identity for row in authority.tilesets for identity in row.animations}
        ),
        "replacements": sorted(
            {identity for row in authority.tilesets for identity in row.replacements}
        ),
    }
    semantic["sha256"] = _sha(canonical_json(semantic).encode())
    return {
        "schema": SCHEMA,
        "ledger": {
            "path": LEDGER_PATH.as_posix(),
            "size": len(ledger_bytes),
            "sha256": _sha(ledger_bytes),
            "canonical_sha256": _sha(ledger_canonical),
        },
        "source": {
            "authorities": [_artifact(root, path) for path in SOURCE_AUTHORITIES],
            "assembled_parity_sha256": _sha(canonical_json(fresh_source).encode()),
            "semantic": semantic,
        },
        "products": products,
        "parity_sha256": _sha(canonical_json(reference).encode()),
    }


def verify(
    root: Path | str, manifest_path: Path | str = MANIFEST_PATH
) -> dict[str, object]:
    expected = canonical_json(generate(root))
    path = Path(manifest_path)
    if not path.is_absolute():
        path = Path(root) / path
    try:
        actual = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MapBackgroundSnapshotError(
            f"cannot read reviewed manifest {path}: {exc}"
        ) from exc
    if actual != expected:
        raise MapBackgroundSnapshotError(
            f"stale or edited map-background manifest: {path}"
        )
    return json.loads(expected)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    outputs = parser.add_mutually_exclusive_group(required=True)
    outputs.add_argument("--proposal-output", type=Path)
    outputs.add_argument("--output", type=Path)
    outputs.add_argument("--verify", type=Path, metavar="MANIFEST")
    parser.add_argument("--authority-reviewed", action="store_true")
    return parser


def _resolved_output(root: Path, output: Path) -> Path:
    candidate = output if output.is_absolute() else root / output
    return Path(os.path.abspath(candidate))


def _validate_output_authority(root: Path, output: Path, *, reviewed: bool) -> Path:
    candidate = _resolved_output(root, output)
    reviewed_manifest = (root / MANIFEST_PATH).resolve(strict=False)
    reviewed_directory = reviewed_manifest.parent
    resolved_candidate = candidate.resolve(strict=False)
    if reviewed:
        if candidate != reviewed_manifest or resolved_candidate != reviewed_manifest:
            raise MapBackgroundSnapshotError(
                "reviewed promotion output must be the canonical reviewed manifest"
            )
    else:
        same_file = False
        try:
            same_file = candidate.exists() and candidate.samefile(reviewed_manifest)
        except OSError as exc:
            raise MapBackgroundSnapshotError(
                f"cannot validate proposal output identity: {exc}"
            ) from exc
        if not (
            same_file
            or resolved_candidate == reviewed_directory
            or reviewed_directory in resolved_candidate.parents
        ):
            return candidate
        raise MapBackgroundSnapshotError(
            "proposal output cannot target checked-in reviewed evidence authority"
        )
    return candidate


def _validate_directory_identity(directory: Path, directory_fd: int) -> None:
    """Require the output pathname to still name the pinned destination directory."""
    try:
        path_stat = os.stat(directory, follow_symlinks=False)
        fd_stat = os.fstat(directory_fd)
    except OSError as exc:
        raise MapBackgroundSnapshotError(
            f"cannot revalidate proposal output directory: {exc}"
        ) from exc
    if not stat.S_ISDIR(path_stat.st_mode) or (
        path_stat.st_dev,
        path_stat.st_ino,
    ) != (fd_stat.st_dev, fd_stat.st_ino):
        raise MapBackgroundSnapshotError(
            "proposal output directory changed during generation"
        )


def _atomic_write(root: Path, output: Path, contents: str, *, reviewed: bool) -> None:
    """Publish bytes without following a concurrently replaced destination entry."""
    output = _validate_output_authority(root, output, reviewed=reviewed)
    output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(output.parent, flags)
    except OSError as exc:
        raise MapBackgroundSnapshotError(
            f"cannot open proposal output directory: {exc}"
        ) from exc

    temporary_name: str | None = None
    replaced = False
    try:
        _validate_directory_identity(output.parent, directory_fd)
        for _ in range(128):
            temporary_name = f".{output.name}.{secrets.token_hex(12)}.tmp"
            try:
                temporary_fd = os.open(
                    temporary_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory_fd,
                )
                break
            except FileExistsError:
                temporary_name = None
        else:
            raise MapBackgroundSnapshotError(
                "cannot allocate unique proposal output temporary file"
            )

        with os.fdopen(temporary_fd, "wb") as stream:
            stream.write(contents.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())

        # Generation can be arbitrarily expensive. Recheck every authority and
        # pathname identity at the last possible point, then use the pinned
        # directory descriptor so a subsequent symlink/hardlink swap is replaced.
        _validate_output_authority(root, output, reviewed=reviewed)
        _validate_directory_identity(output.parent, directory_fd)
        os.replace(
            temporary_name,
            output.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        replaced = True
        temporary_name = None
        _validate_directory_identity(output.parent, directory_fd)
        _validate_output_authority(root, output, reviewed=reviewed)
        os.fsync(directory_fd)
    except Exception:
        if replaced and not reviewed:
            try:
                os.unlink(output.name, dir_fd=directory_fd)
            except OSError:
                pass
        raise
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        if args.verify is not None:
            if args.authority_reviewed:
                raise MapBackgroundSnapshotError(
                    "--authority-reviewed is not used for read-only verification"
                )
            verify(root, args.verify)
        else:
            if args.output is not None and not args.authority_reviewed:
                raise MapBackgroundSnapshotError(
                    "promoting reviewed evidence requires --authority-reviewed"
                )
            if args.proposal_output is not None and args.authority_reviewed:
                raise MapBackgroundSnapshotError(
                    "--authority-reviewed is not used for proposal output"
                )
            output = args.output or args.proposal_output
            assert output is not None
            output = _validate_output_authority(
                root, output, reviewed=args.output is not None
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            contents = canonical_json(generate(root))
            _atomic_write(root, output, contents, reviewed=args.output is not None)
    except (OSError, MapBackgroundSnapshotError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

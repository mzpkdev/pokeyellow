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
    Path("constants/map_data_constants.asm"),
    Path("data/tilesets/cut_tree_blocks.asm"),
    Path("engine/full_color/passive_overworld.asm"),
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
    ("roof_palettes", "FullColorOverworldRoofPalettes", 44),
    ("map_overrides", "PassiveFullColorResolveAttributeForIdentity", 84),
)
_LINK_OBJECTS = (
    "audio.o",
    "home.o",
    "maps.o",
    "ram.o",
    "text.o",
    "gfx/pics.o",
    "gfx/pikachu.o",
    "gfx/sprites.o",
    "gfx/surfing_pikachu.o",
    "gfx/tilesets.o",
)
_PRODUCT_BUILD = {
    "pokeyellow": ((), "", "0x00"),
    "pokeyellow_debug": (("-D", "_DEBUG"), "_debug", "0xff"),
    "pokeyellow_vc": (("-D", "_YELLOW_VC"), "_vc", "0x00"),
    "pokeyellow_phase2_audit": (
        ("-D", "_DEBUG", "-D", "PHASE2_AUDIT"),
        "_phase2_audit",
        "0xff",
    ),
}


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


def _relative_jump(source_operand: int, target: int) -> int:
    displacement = target - (source_operand + 1)
    if not -128 <= displacement <= 127:
        raise MapBackgroundSnapshotError(
            "map override routine requires an out-of-range relative branch"
        )
    return displacement & 0xFF


def _validate_map_override_routine(
    rom: bytes,
    symbols: SymbolTable,
    authority: MapBackgroundAuthority,
    rules: tuple[dict[str, object], ...],
) -> None:
    """Bind semantic override rules to the exact linked instruction stream.

    The source contract deliberately does not try to emulate arbitrary RGBDS
    macro expansion.  This independent check instead synthesizes the one
    production routine that may implement the two reviewed rules and compares
    it byte-for-byte with the linked product.
    """
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
    try:
        roof_map = map_ids[str(roof["map"])]
        first_floor_map = map_ids[str(first_floor["map"])]
    except KeyError as exc:
        raise MapBackgroundSnapshotError(
            f"map override semantics name an unknown map: {exc.args[0]}"
        ) from exc
    if not 0 <= roof_map <= 0xFF or not 0 <= first_floor_map <= 0xFF:
        raise MapBackgroundSnapshotError(
            "map override identity exceeds an 8-bit map ID"
        )

    start = _symbol(symbols, "PassiveFullColorResolveAttributeForIdentity")
    pointer_table = _symbol(symbols, "FullColorTileAttributePointers")
    if start.bank != pointer_table.bank:
        raise MapBackgroundSnapshotError(
            "map override lookup and attribute pointer table are not in one ROM bank"
        )

    labels = {
        "not_roof": 18,
        "first_floor_match": 39,
        "lookup": 43,
        "done": 59,
    }
    symbol_names = {
        "not_roof": (
            "PassiveFullColorResolveAttributeForIdentity.not_celadon_mart_roof"
        ),
        "first_floor_match": (
            "PassiveFullColorResolveAttributeForIdentity.celadon_mart_1f"
        ),
        "lookup": "PassiveFullColorResolveAttributeForIdentity.lookup",
        "done": "PassiveFullColorResolveAttributeForIdentity.done",
    }
    for label, offset in labels.items():
        target = _symbol(symbols, symbol_names[label])
        if (target.bank, target.address) != (start.bank, start.address + offset):
            raise MapBackgroundSnapshotError(
                f"map override linked label {symbol_names[label]} has an invalid offset"
            )

    expected = bytearray(
        (
            0x7B,  # ld a, e
            0xFE,
            roof_map,
            0x20,
            0,  # jr nz, not_roof
            0x79,  # ld a, c
            0xFE,
            0x4B,
            0x38,
            0,  # jr c, lookup
            0xFE,
            0x50,
            0x30,
            0,  # jr nc, lookup
            0x3E,
            int(roof["palette_value"]),
            0x18,
            0,  # jr done
            0xFE,
            first_floor_map,
            0x20,
            0,  # jr nz, lookup
            0x79,
            0xFE,
            0x07,
            0x28,
            0,  # jr z, first_floor_match
            0xFE,
            0x08,
            0x28,
            0,
            0xFE,
            0x17,
            0x28,
            0,
            0xFE,
            0x18,
            0x20,
            0,  # jr nz, lookup
            0x3E,
            int(first_floor["palette_value"]),
            0x18,
            0,  # jr done
            0x7C,  # ld a, h
            0x87,  # add a
            0x5F,  # ld e, a
            0x16,
            0x00,
            0x21,
            pointer_table.address & 0xFF,
            pointer_table.address >> 8,
            0x19,  # add hl, de
            0x2A,  # ld a, [hli]
            0x66,  # ld h, [hl]
            0x6F,  # ld l, a
            0x06,
            0x00,
            0x09,  # add hl, bc
            0x7E,  # ld a, [hl]
            0xC1,  # pop bc
            0xD1,  # pop de
            0xE1,  # pop hl
            0xC9,  # ret
        )
    )
    for operand, target in (
        (4, labels["not_roof"]),
        (9, labels["lookup"]),
        (13, labels["lookup"]),
        (17, labels["done"]),
        (21, labels["lookup"]),
        (26, labels["first_floor_match"]),
        (30, labels["first_floor_match"]),
        (34, labels["first_floor_match"]),
        (38, labels["lookup"]),
        (42, labels["done"]),
    ):
        expected[operand] = _relative_jump(operand, target)

    actual = rom[start.rom_offset : start.rom_offset + len(expected)]
    if len(actual) != len(expected) or actual != expected:
        differences = [
            f"+0x{index:02x}: expected {wanted:02x}, linked {found:02x}"
            for index, (wanted, found) in enumerate(zip(expected, actual, strict=False))
            if wanted != found
        ]
        detail = differences[0] if differences else "routine is truncated"
        raise MapBackgroundSnapshotError(
            "linked map override routine contradicts semantic rules or exact "
            f"instruction contract ({detail})"
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

    _validate_map_override_routine(rom, symbols, authority, override_rules)

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
            for row in authority.tilesets[:23]
        ]
        raw, record = _read(rom, symbols, name, len(expected) * 2, end=end)
        source_bank = _symbol(symbols, name).bank
        rows: list[dict[str, object]] = []
        for index, (tileset, expected_name) in enumerate(
            zip(authority.tilesets[:23], expected, strict=True)
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
        end = None if key == "map_overrides" else f"{name}End"
        payload, record = _read(rom, symbols, name, size, end=end)
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
        "roof_palettes": {
            key: product["roof_palettes"][key] for key in ("size", "sha256", "bytes")
        },
        "map_overrides": {
            key: product["map_overrides"][key] for key in ("size", "sha256", "bytes")
        },
    }


def _cross_product_view(product: dict[str, object]) -> dict[str, object]:
    view = _parity_view(product)
    view.pop("map_overrides")
    return view


def _source_fingerprint(root: Path) -> tuple[tuple[str, str], ...]:
    paths = (*SOURCE_AUTHORITIES, Path("main.asm"), Path("includes.asm"))
    fingerprint = [
        (path.as_posix(), _sha((root / path).read_bytes())) for path in paths
    ]
    linked_inputs = {Path("layout.link")}
    for _, suffix, _ in _PRODUCT_BUILD.values():
        linked_inputs.update(
            Path(path.replace(".o", f"{suffix}.o")) for path in _LINK_OBJECTS
        )
    for path in sorted(linked_inputs):
        stat = (root / path).stat()
        fingerprint.append((path.as_posix(), f"{stat.st_size}:{stat.st_mtime_ns}"))
    return tuple(fingerprint)


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
            views: dict[str, object] = {}
            for product_name in PRODUCTS:
                defines, suffix, pad = _PRODUCT_BUILD[product_name]
                main_object = output / f"main{suffix}.o"
                subprocess.run(
                    [
                        "rgbasm",
                        "-Weverything",
                        "-Wtruncation=1",
                        "-Q8",
                        "-P",
                        "includes.asm",
                        *defines,
                        "-o",
                        str(main_object),
                        "main.asm",
                    ],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                other_objects = [
                    str(root / path.replace(".o", f"{suffix}.o"))
                    for path in _LINK_OBJECTS
                ]
                subprocess.run(
                    [
                        "rgblink",
                        "-Weverything",
                        "-Wtruncation=1",
                        "-p",
                        pad,
                        "-l",
                        "layout.link",
                        "-m",
                        str(output / f"{product_name}.map"),
                        "-n",
                        str(output / f"{product_name}.sym"),
                        "-o",
                        str(output / f"{product_name}.gbc"),
                        other_objects[0],
                        other_objects[1],
                        str(main_object),
                        *other_objects[2:],
                    ],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                views[product_name] = _parity_view(
                    _product_snapshot(output, product_name, authority, override_rules)
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

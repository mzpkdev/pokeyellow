"""Deterministic Yellow map-background review atlases.

The producer deliberately keeps pictures as review evidence, not authority.  Tile
and block graphics come from the Yellow checkout while palettes and attributes are
read back from one linked product and checked against their linked symbols.  The
manifest binds both inputs, every emitted PNG, and the exact map/tileset order.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

from .map_background_content import (
    MapBackgroundAuthority,
    production_map_override_rules,
)
from .rom_discovery import SymbolTable, load_sym

SCHEMA = "full-color-map-background-atlas-v1"
MANIFEST_NAME = "manifest.json"
ARTIFACT_STORE = ".artifacts"
TILE_COUNT = 256
TILE_SIZE = 8
ATLAS_COLUMNS = 16
ATLAS_CELL = (52, 50)

# This is the exact closed partition of reviewed map-background batches.  The
# Phase 4 additions remain content evidence only; membership here does not widen
# the production presentation predicate.
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
    "forest-cavern": ("FOREST", "CAVERN"),
    "transport-special": ("SHIP_PORT", "PLATEAU", "BEACH_HOUSE"),
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
    "FOREST": "forest",
    "CAVERN": "cavern",
    "SHIP_PORT": "ship_port",
    "PLATEAU": "plateau",
    "BEACH_HOUSE": "beach_house",
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
    "FOREST": "Forest",
    "CAVERN": "Cavern",
    "SHIP_PORT": "ShipPort",
    "PLATEAU": "Plateau",
    "BEACH_HOUSE": "BeachHouse",
}


class MapBackgroundAtlasError(ValueError):
    """Atlas inputs are incomplete or disagree with the linked product."""


class MapBackgroundAtlasCompositeError(MapBackgroundAtlasError):
    """Several publication or rollback failures preserved together."""

    def __init__(self, message: str, failures: Sequence[Exception]) -> None:
        self.failures = tuple(failures)
        details = "; ".join(f"{type(exc).__name__}: {exc}" for exc in self.failures)
        super().__init__(f"{message}: {details}")


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


def _rewrite_artifact_paths(value: object, replacements: dict[str, str]) -> None:
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, str) and path in replacements:
            value["path"] = replacements[path]
        for child in value.values():
            _rewrite_artifact_paths(child, replacements)
    elif isinstance(value, list):
        for child in value:
            _rewrite_artifact_paths(child, replacements)


def _address_artifacts(output: Path, manifest: dict[str, object]) -> dict[str, object]:
    """Move artifacts under immutable digest paths and rewrite every reference."""
    replacements: dict[str, str] = {}
    for record in manifest["artifacts"]:
        source_relative = str(record["path"])
        digest = str(record["sha256"])
        destination_relative = (
            Path(ARTIFACT_STORE) / digest / Path(source_relative)
        ).as_posix()
        source = output / source_relative
        destination = output / destination_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if _sha(destination.read_bytes()) != digest:
                raise MapBackgroundAtlasError(
                    f"content-addressed atlas artifact collision: {destination_relative}"
                )
            source.unlink()
        else:
            source.replace(destination)
        replacements[source_relative] = destination_relative
    # Empty legacy batch directories are not part of the publication contract.
    for directory in sorted(
        (path for path in output.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if directory.name != ARTIFACT_STORE:
            try:
                directory.rmdir()
            except OSError:
                pass
    _rewrite_artifact_paths(manifest, replacements)
    unhashed = dict(manifest)
    unhashed.pop("content_sha256", None)
    manifest["content_sha256"] = _sha(canonical_json(unhashed).encode("utf-8"))
    (output / MANIFEST_NAME).write_text(canonical_json(manifest), encoding="utf-8")
    return manifest


def _carry_forward_artifacts(previous: Path, temporary: Path) -> None:
    """Copy immutable prior blobs; cleanup is deliberately an external action."""
    source = previous / ARTIFACT_STORE
    if not source.exists():
        return
    shutil.copytree(source, temporary / ARTIFACT_STORE, dirs_exist_ok=True)


def _save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False, compress_level=9)


_CONVERTER_FLAGS = ("-O3", "-std=c11", "-Wall", "-Wextra", "-pedantic")


def _resolved_tool(command: str) -> Path:
    candidate = shutil.which(command)
    if candidate is None:
        raise MapBackgroundAtlasError(f"required graphics tool is absent: {command}")
    path = Path(candidate).resolve(strict=True)
    if not path.is_file():
        raise MapBackgroundAtlasError(
            f"required graphics tool is not a regular file: {command}"
        )
    return path


@dataclass(frozen=True, slots=True)
class _ExecutableSnapshot:
    descriptor: int


@contextmanager
def _executable_snapshot(
    directory: Path, name: str, data: bytes
) -> Iterator[_ExecutableSnapshot]:
    """Pin captured executable bytes after removing their only pathname."""
    path = directory / name
    path.write_bytes(data)
    path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    descriptor = os.open(path, os.O_RDONLY)
    os.unlink(path)
    try:
        yield _ExecutableSnapshot(descriptor)
    finally:
        os.close(descriptor)


def _run_executable_snapshot(
    executable: _ExecutableSnapshot,
    command: Sequence[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Execute the pinned inode while preserving the installed tool's argv[0]."""
    command_bytes = [os.fsencode(argument) for argument in command]
    argv = (ctypes.c_char_p * (len(command_bytes) + 1))(*command_bytes, None)
    environment_bytes = [
        os.fsencode(f"{name}={value}") for name, value in os.environ.items()
    ]
    environment = (ctypes.c_char_p * (len(environment_bytes) + 1))(
        *environment_bytes, None
    )
    libc = ctypes.CDLL(None, use_errno=True)

    def execute_pinned_inode() -> None:
        libc.fexecve(executable.descriptor, argv, environment)
        os._exit(ctypes.get_errno() or 127)

    return subprocess.run(
        list(command),
        executable="/bin/false",
        pass_fds=(executable.descriptor,),
        preexec_fn=execute_pinned_inode,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


@lru_cache(maxsize=16)
def _graphics_toolchain_cached(
    root_text: str,
    rgbds_version_bytes: bytes,
    gfx_source_bytes: bytes,
    common_source_bytes: bytes,
    rgbgfx_path_text: str,
    rgbgfx_binary_bytes: bytes,
    compiler_path_text: str,
    compiler_binary_bytes: bytes,
) -> dict[str, object]:
    """Bind the tracked converter implementation and exact executable tools."""
    root = Path(root_text)
    rgbds_version_sha256 = _sha(rgbds_version_bytes)
    gfx_source_sha256 = _sha(gfx_source_bytes)
    common_source_sha256 = _sha(common_source_bytes)
    rgbgfx_binary_sha256 = _sha(rgbgfx_binary_bytes)
    compiler_binary_sha256 = _sha(compiler_binary_bytes)
    expected_rgbds = rgbds_version_bytes.decode("utf-8").strip()
    rgbgfx_path = Path(rgbgfx_path_text)
    compiler_path = Path(compiler_path_text)
    with tempfile.TemporaryDirectory(prefix="map-background-converter-") as temporary:
        snapshot = Path(temporary)
        converter = snapshot / "gfx"
        gfx_source = snapshot / "gfx.c"
        common_source = snapshot / "common.h"
        gfx_source.write_bytes(gfx_source_bytes)
        common_source.write_bytes(common_source_bytes)
        try:
            with (
                _executable_snapshot(
                    snapshot, "rgbgfx", rgbgfx_binary_bytes
                ) as rgbgfx_executable,
                _executable_snapshot(
                    snapshot, "cc", compiler_binary_bytes
                ) as compiler_executable,
            ):
                rgbgfx_version = _run_executable_snapshot(
                    rgbgfx_executable,
                    [str(rgbgfx_path), "--version"],
                    cwd=root,
                ).stdout.strip()
                compiler_version = (
                    _run_executable_snapshot(
                        compiler_executable,
                        [str(compiler_path), "--version"],
                        cwd=root,
                    )
                    .stdout.splitlines()[0]
                    .strip()
                )
                if rgbgfx_version != f"rgbgfx v{expected_rgbds}":
                    raise MapBackgroundAtlasError(
                        "rgbgfx version disagrees with the checked-in .rgbds-version"
                    )
                _run_executable_snapshot(
                    compiler_executable,
                    [
                        str(compiler_path),
                        *_CONVERTER_FLAGS,
                        "-o",
                        str(converter),
                        str(gfx_source),
                    ],
                    cwd=root,
                )
        except MapBackgroundAtlasError:
            raise
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = (
                exc.stderr.strip()
                if isinstance(exc, subprocess.CalledProcessError)
                else str(exc)
            )
            raise MapBackgroundAtlasError(
                f"cannot compile checked-in graphics converter: {detail}"
            ) from exc
        converter_sha256 = _sha(converter.read_bytes())
    _revalidate_converter_inputs(
        root,
        rgbds_version_sha256=rgbds_version_sha256,
        gfx_source_sha256=gfx_source_sha256,
        common_source_sha256=common_source_sha256,
        rgbgfx_path=rgbgfx_path,
        rgbgfx_binary_sha256=rgbgfx_binary_sha256,
        compiler_path=compiler_path,
        compiler_binary_sha256=compiler_binary_sha256,
    )
    return {
        "rgbds_version": {
            "path": ".rgbds-version",
            "sha256": rgbds_version_sha256,
            "value": expected_rgbds,
        },
        "rgbgfx": {
            "command": "rgbgfx",
            "binary_sha256": rgbgfx_binary_sha256,
            "version": rgbgfx_version,
        },
        "postprocessor": {
            "binary_sha256": converter_sha256,
            "sources": [
                {
                    "path": "tools/common.h",
                    "sha256": common_source_sha256,
                },
                {"path": "tools/gfx.c", "sha256": gfx_source_sha256},
            ],
        },
        "compiler": {
            "command": "cc",
            "binary_sha256": compiler_binary_sha256,
            "version": compiler_version,
            "flags": list(_CONVERTER_FLAGS),
        },
    }


def _revalidate_converter_inputs(
    root: Path,
    *,
    rgbds_version_sha256: str,
    gfx_source_sha256: str,
    common_source_sha256: str,
    rgbgfx_path: Path,
    rgbgfx_binary_sha256: str,
    compiler_path: Path,
    compiler_binary_sha256: str,
) -> None:
    """Fail closed if any path used by conversion changed after identification."""
    expected = {
        root / ".rgbds-version": rgbds_version_sha256,
        root / "tools/gfx.c": gfx_source_sha256,
        root / "tools/common.h": common_source_sha256,
        rgbgfx_path: rgbgfx_binary_sha256,
        compiler_path: compiler_binary_sha256,
    }
    for path, digest in expected.items():
        try:
            current = _sha(path.read_bytes())
        except OSError as exc:
            raise MapBackgroundAtlasError(
                f"graphics conversion input disappeared after identification: {path}"
            ) from exc
        if current != digest:
            raise MapBackgroundAtlasError(
                f"graphics conversion input changed after identification: {path}"
            )


def graphics_toolchain(root: Path) -> dict[str, object]:
    rgbgfx = _resolved_tool("rgbgfx")
    compiler = _resolved_tool("cc")
    version_path = root / ".rgbds-version"
    gfx_source = root / "tools/gfx.c"
    common_source = root / "tools/common.h"
    return _graphics_toolchain_cached(
        str(root.resolve()),
        version_path.read_bytes(),
        gfx_source.read_bytes(),
        common_source.read_bytes(),
        str(rgbgfx),
        rgbgfx.read_bytes(),
        str(compiler),
        compiler.read_bytes(),
    )


@lru_cache(maxsize=64)
def _generated_2bpp_cached(
    root_text: str,
    relative_text: str,
    source_bytes: bytes,
    gfx_source_bytes: bytes,
    common_source_bytes: bytes,
    rgbgfx_path_text: str,
    rgbgfx_binary_bytes: bytes,
    compiler_path_text: str,
    compiler_binary_bytes: bytes,
    toolchain_sha256: str,
) -> bytes:
    """Derive a generated graphics include without writing into the checkout."""
    root = Path(root_text)
    relative = Path(relative_text)
    source = (root / relative).with_suffix(".png")
    source_sha256 = _sha(source_bytes)
    toolchain = _graphics_toolchain_cached(
        root_text,
        (root / ".rgbds-version").read_bytes(),
        gfx_source_bytes,
        common_source_bytes,
        rgbgfx_path_text,
        rgbgfx_binary_bytes,
        compiler_path_text,
        compiler_binary_bytes,
    )
    if _sha(canonical_json(toolchain).encode("utf-8")) != toolchain_sha256:
        raise MapBackgroundAtlasError(
            "graphics toolchain changed between provenance and conversion"
        )
    if _sha(source.read_bytes()) != source_sha256:
        raise MapBackgroundAtlasError(
            f"graphics source changed between provenance and conversion: {source}"
        )
    source_rows = {
        row["path"]: row["sha256"] for row in toolchain["postprocessor"]["sources"]
    }
    if (
        _sha(gfx_source_bytes) != source_rows["tools/gfx.c"]
        or _sha(common_source_bytes) != source_rows["tools/common.h"]
    ):
        raise MapBackgroundAtlasError(
            "converter source snapshot disagrees with graphics toolchain provenance"
        )
    with tempfile.TemporaryDirectory(prefix="map-background-gfx-") as temporary:
        snapshot = Path(temporary)
        compiler = Path(compiler_path_text)
        rgbgfx = Path(rgbgfx_path_text)
        converter = snapshot / "gfx"
        raw = snapshot / relative.name
        processed = snapshot / f"processed-{relative.name}"
        snapshot_source = snapshot / "source.png"
        snapshot_gfx_source = snapshot / "gfx.c"
        snapshot_common_source = snapshot / "common.h"
        snapshot_source.write_bytes(source_bytes)
        snapshot_gfx_source.write_bytes(gfx_source_bytes)
        snapshot_common_source.write_bytes(common_source_bytes)
        try:
            with (
                _executable_snapshot(
                    snapshot, "cc", compiler_binary_bytes
                ) as compiler_executable,
                _executable_snapshot(
                    snapshot, "rgbgfx", rgbgfx_binary_bytes
                ) as rgbgfx_executable,
            ):
                _run_executable_snapshot(
                    compiler_executable,
                    [
                        str(compiler),
                        *_CONVERTER_FLAGS,
                        "-o",
                        str(converter),
                        str(snapshot_gfx_source),
                    ],
                    cwd=root,
                )
                if (
                    _sha(converter.read_bytes())
                    != toolchain["postprocessor"]["binary_sha256"]
                ):
                    raise MapBackgroundAtlasError(
                        "compiled graphics converter disagrees with toolchain provenance"
                    )
                _run_executable_snapshot(
                    rgbgfx_executable,
                    [
                        str(rgbgfx),
                        "--colors",
                        "dmg",
                        "-Weverything",
                        "-o",
                        str(raw),
                        str(snapshot_source),
                    ],
                    cwd=root,
                )
            filters = ["--trim-whitespace"]
            if relative == Path("gfx/tilesets/reds_house.2bpp"):
                filters.append("--preserve=0x48")
            subprocess.run(
                [
                    str(converter),
                    *filters,
                    "-o",
                    str(processed),
                    str(raw),
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            current_toolchain = _graphics_toolchain_cached(
                root_text,
                (root / ".rgbds-version").read_bytes(),
                gfx_source_bytes,
                common_source_bytes,
                rgbgfx_path_text,
                rgbgfx_binary_bytes,
                compiler_path_text,
                compiler_binary_bytes,
            )
            if (
                _sha(canonical_json(current_toolchain).encode("utf-8"))
                != toolchain_sha256
            ):
                raise MapBackgroundAtlasError(
                    "graphics toolchain changed while conversion executed"
                )
            return processed.read_bytes()
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = (
                exc.stderr.strip()
                if isinstance(exc, subprocess.CalledProcessError)
                else str(exc)
            )
            raise MapBackgroundAtlasError(
                f"cannot derive {relative.as_posix()} from checked-in PNG: {detail}"
            ) from exc


def source_2bpp(root: Path, relative: Path) -> bytes:
    """Return Makefile-equivalent 2bpp bytes from the checked-in PNG source."""
    png = (root / relative).with_suffix(".png")
    return _source_2bpp_from_snapshot(root, relative, png.read_bytes())


def _source_2bpp_from_snapshot(
    root: Path, relative: Path, source_bytes: bytes
) -> bytes:
    """Convert one already-captured PNG snapshot with equally bound sources."""
    rgbgfx = _resolved_tool("rgbgfx")
    compiler = _resolved_tool("cc")
    rgbgfx_binary_bytes = rgbgfx.read_bytes()
    compiler_binary_bytes = compiler.read_bytes()
    gfx_source_bytes = (root / "tools/gfx.c").read_bytes()
    common_source_bytes = (root / "tools/common.h").read_bytes()
    toolchain = _graphics_toolchain_cached(
        str(root.resolve()),
        (root / ".rgbds-version").read_bytes(),
        gfx_source_bytes,
        common_source_bytes,
        str(rgbgfx),
        rgbgfx_binary_bytes,
        str(compiler),
        compiler_binary_bytes,
    )
    return _generated_2bpp_cached(
        str(root.resolve()),
        relative.as_posix(),
        source_bytes,
        gfx_source_bytes,
        common_source_bytes,
        str(rgbgfx),
        rgbgfx_binary_bytes,
        str(compiler),
        compiler_binary_bytes,
        _sha(canonical_json(toolchain).encode("utf-8")),
    )


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
    root: Path,
    tileset: str,
    animation_identity: str | None,
    attributes: bytes,
    palettes: bytes,
) -> list[dict[str, object]]:
    if animation_identity is None:
        return []
    if animation_identity not in {"TILEANIM_WATER", "TILEANIM_WATER_FLOWER"}:
        raise MapBackgroundAtlasError(
            f"{tileset}: unsupported animation identity {animation_identity}"
        )
    decoded_palettes = decode_palettes(palettes)
    records = []
    if animation_identity == "TILEANIM_WATER_FLOWER":
        for index, png_path in enumerate(
            sorted((root / "gfx/tilesets/flower").glob("flower*.png")), 1
        ):
            path = png_path.with_suffix(".2bpp")
            data = source_2bpp(root, path.relative_to(root))
            tile = decode_2bpp(data)[0]
            records.append(
                {
                    "identity": animation_identity,
                    "observation": "artifact-only-source-frame",
                    "kind": "flower",
                    "frame": index,
                    "tile_id": 0x03,
                    "source": path.relative_to(root).as_posix(),
                    "source_input": _file_record(png_path, root=root),
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
    source_path = Path(f"gfx/tilesets/{_SOURCE_STEM[tileset]}.2bpp")
    source_bytes = source_2bpp(root, source_path)
    base = source_bytes[0x14 * 16 : 0x15 * 16]
    if len(base) != 16:
        raise MapBackgroundAtlasError(
            f"{tileset}: TILEANIM_WATER source tile $14 is absent"
        )
    previous = base
    for frame, (counter, direction, data) in enumerate(moving_water_frames(base)):
        tile = decode_2bpp(data)[0]
        records.append(
            {
                "identity": animation_identity,
                "observation": "artifact-only-runtime-semantics",
                "kind": "water-rotation",
                "frame": frame,
                "counter": counter,
                "direction": direction,
                "tile_id": 0x14,
                "source": source_path.as_posix(),
                "source_input": _file_record(
                    (root / source_path).with_suffix(".png"), root=root
                ),
                "source_sha256": _sha(source_bytes),
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


def _bytes_record(relative: Path, data: bytes) -> dict[str, object]:
    return {
        "path": relative.as_posix(),
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
    toolchain = graphics_toolchain(root)
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
            gfx_relative = gfx_path.relative_to(root)
            gfx_input = gfx_path.with_suffix(".png")
            gfx_input_bytes = gfx_input.read_bytes()
            gfx_input_record = _bytes_record(
                gfx_input.relative_to(root), gfx_input_bytes
            )
            graphics = _source_2bpp_from_snapshot(root, gfx_relative, gfx_input_bytes)
            blockset = block_path.read_bytes()
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

            if len(row.animations) > 1:
                raise MapBackgroundAtlasError(
                    f"{tileset}: multiple tileset animation identities are unsupported"
                )
            animation_identity = row.animations[0] if row.animations else None
            animation_records = _animation_frames(
                root, tileset, animation_identity, attributes.data, palette.data
            )
            if animation_identity is not None:
                water_records = [
                    record
                    for record in animation_records
                    if record.get("kind") == "water-rotation"
                ]
                if len(water_records) != 8:
                    raise MapBackgroundAtlasError(
                        f"{tileset}: declared water animation lacks eight review frames"
                    )
                flower_records = [
                    record
                    for record in animation_records
                    if record.get("kind") == "flower"
                ]
                expected_flowers = (
                    3 if animation_identity == "TILEANIM_WATER_FLOWER" else 0
                )
                if len(flower_records) != expected_flowers:
                    raise MapBackgroundAtlasError(
                        f"{tileset}: declared flower animation lacks three review frames"
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
                    "graphics_input": gfx_input_record,
                    "graphics_source": _bytes_record(gfx_relative, graphics),
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
        "graphics_toolchain": toolchain,
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


_DIRECTORY_FLAGS = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
_RENAME_NOREPLACE = 1
_RENAME_EXCHANGE = 2


def _identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode)


@dataclass(frozen=True, slots=True)
class _ValidatedOutput:
    root_identity: tuple[int, int, int]
    entries: dict[str, _ValidatedEntry]
    manifest_sha256: str | None


@dataclass(frozen=True, slots=True)
class _ValidatedEntry:
    identity: tuple[int, int, int]
    nlink: int
    size: int
    sha256: str | None


@dataclass(slots=True)
class _QuarantinedOutput:
    path: Path
    name: str
    parent_descriptor: int
    tree_descriptor: int
    validated: _ValidatedOutput

    def close(self) -> None:
        errors: list[Exception] = []
        for attribute in ("tree_descriptor", "parent_descriptor"):
            descriptor = getattr(self, attribute)
            if descriptor < 0:
                continue
            setattr(self, attribute, -1)
            try:
                os.close(descriptor)
            except OSError as exc:
                errors.append(exc)
        if errors:
            raise MapBackgroundAtlasCompositeError(
                "failed to close atlas quarantine handles", errors
            )


def _regular_file_metadata(
    directory_descriptor: int, name: str, *, description: str
) -> tuple[os.stat_result, int]:
    try:
        metadata = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_descriptor)
    except OSError as exc:
        raise MapBackgroundAtlasError(f"{description} is not a regular file") from exc
    try:
        opened = os.fstat(descriptor)
        if metadata.st_nlink != 1 or opened.st_nlink != 1:
            raise MapBackgroundAtlasError(f"{description} is a hard-linked file")
        if not stat.S_ISREG(metadata.st_mode) or _identity(metadata) != _identity(
            opened
        ):
            raise MapBackgroundAtlasError(
                f"{description} is not a private regular file"
            )
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    return metadata, descriptor


def _read_regular_file(
    directory_descriptor: int,
    name: str,
    *,
    description: str,
    synchronize: bool = False,
) -> tuple[os.stat_result, bytes]:
    metadata, descriptor = _regular_file_metadata(
        directory_descriptor, name, description=description
    )
    try:
        chunks = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        data = b"".join(chunks)
        if synchronize:
            os.fsync(descriptor)
        final = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        _identity(final) != _identity(metadata)
        or final.st_nlink != 1
        or final.st_size != len(data)
    ):
        raise MapBackgroundAtlasError(f"{description} changed during validation")
    return final, data


def _walk_output(
    directory_descriptor: int,
    *,
    prefix: str = "",
    synchronize_files: bool = False,
) -> dict[str, _ValidatedEntry]:
    entries: dict[str, _ValidatedEntry] = {}
    with os.scandir(directory_descriptor) as iterator:
        names = sorted(entry.name for entry in iterator)
    for name in names:
        relative = f"{prefix}/{name}" if prefix else name
        metadata = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
        identity = _identity(metadata)
        if stat.S_ISREG(metadata.st_mode):
            final, data = _read_regular_file(
                directory_descriptor,
                name,
                description=f"atlas file {relative}",
                synchronize=synchronize_files,
            )
            metadata = final
            identity = _identity(final)
            entry = _ValidatedEntry(identity, final.st_nlink, len(data), _sha(data))
        elif stat.S_ISDIR(metadata.st_mode):
            try:
                child_descriptor = os.open(
                    name, _DIRECTORY_FLAGS, dir_fd=directory_descriptor
                )
            except OSError as exc:
                raise MapBackgroundAtlasError(
                    "existing atlas output directory changed during validation"
                ) from exc
            try:
                if _identity(os.fstat(child_descriptor)) != identity:
                    raise MapBackgroundAtlasError(
                        "existing atlas output directory changed during validation"
                    )
                entries.update(
                    _walk_output(
                        child_descriptor,
                        prefix=relative,
                        synchronize_files=synchronize_files,
                    )
                )
            finally:
                os.close(child_descriptor)
            entry = _ValidatedEntry(identity, metadata.st_nlink, metadata.st_size, None)
        elif stat.S_ISLNK(metadata.st_mode):
            raise MapBackgroundAtlasError("existing atlas output contains a symlink")
        else:
            raise MapBackgroundAtlasError(
                "existing atlas output contains a special file"
            )
        entries[relative] = entry
    return entries


def _validate_output_descriptor(
    tree_descriptor: int,
    output: Path,
    *,
    synchronize_files: bool = False,
) -> _ValidatedOutput:
    root_metadata = os.fstat(tree_descriptor)
    entries = _walk_output(tree_descriptor, synchronize_files=synchronize_files)
    if not entries:
        return _ValidatedOutput(_identity(root_metadata), entries, None)
    manifest_metadata, manifest_bytes = _read_regular_file(
        tree_descriptor, MANIFEST_NAME, description="atlas manifest"
    )
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MapBackgroundAtlasError("existing atlas manifest is unreadable") from exc
    manifest_entry = entries.get(MANIFEST_NAME)
    if (
        manifest_entry is None
        or manifest_entry.identity != _identity(manifest_metadata)
        or manifest_entry.size != len(manifest_bytes)
        or manifest_entry.sha256 != _sha(manifest_bytes)
    ):
        raise MapBackgroundAtlasError(
            "existing atlas manifest changed during validation"
        )
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("producer") != "tools.rom_tests.full_color.map_background_atlas"
    ):
        raise MapBackgroundAtlasError(
            "existing atlas output belongs to another producer"
        )
    canonical_manifest = canonical_json(manifest).encode("utf-8")
    if manifest_bytes != canonical_manifest:
        raise MapBackgroundAtlasError("atlas manifest is not canonical")
    unhashed = dict(manifest)
    content_sha256 = unhashed.pop("content_sha256", None)
    if content_sha256 != _sha(canonical_json(unhashed).encode("utf-8")):
        raise MapBackgroundAtlasError("atlas manifest content hash is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise MapBackgroundAtlasError("atlas manifest artifacts are invalid")
    owned = {MANIFEST_NAME}
    addressed = True
    for record in artifacts:
        if not isinstance(record, dict):
            raise MapBackgroundAtlasError("atlas manifest artifact is invalid")
        relative = Path(str(record.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise MapBackgroundAtlasError("existing atlas manifest has an unsafe path")
        normalized = relative.as_posix()
        parts = relative.parts
        if len(parts) < 3 or parts[0] != ARTIFACT_STORE:
            addressed = False
        elif not re.fullmatch(r"[0-9a-f]{64}", parts[1]) or parts[1] != record.get(
            "sha256"
        ):
            raise MapBackgroundAtlasError(
                "atlas manifest artifact content address is invalid"
            )
        if normalized in owned:
            raise MapBackgroundAtlasError(
                "existing atlas manifest repeats an owned path"
            )
        owned.add(normalized)
        entry = entries.get(normalized)
        if (
            entry is None
            or entry.identity[2] != stat.S_IFREG
            or entry.size != record.get("size")
            or entry.sha256 != record.get("sha256")
        ):
            raise MapBackgroundAtlasError(
                f"atlas artifact does not match manifest: {normalized}"
            )
    actual_files = {
        relative
        for relative, entry in entries.items()
        if entry.identity[2] == stat.S_IFREG
    }
    retained = actual_files - owned
    if addressed:
        for relative in retained:
            parts = Path(relative).parts
            entry = entries[relative]
            if (
                len(parts) < 3
                or parts[0] != ARTIFACT_STORE
                or not re.fullmatch(r"[0-9a-f]{64}", parts[1])
                or entry.sha256 != parts[1]
            ):
                raise MapBackgroundAtlasError(
                    f"existing atlas output contains an invalid retained artifact: {relative}"
                )
    elif retained:
        raise MapBackgroundAtlasError(
            "existing atlas output contains stale or unowned files"
        )
    return _ValidatedOutput(_identity(root_metadata), entries, _sha(manifest_bytes))


def _owned_output_entries(output: Path) -> tuple[set[str], list[Path]]:
    """Validate and enumerate one complete tree owned by this producer."""
    try:
        descriptor = os.open(output, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise MapBackgroundAtlasError(
            f"refusing non-directory atlas output: {output}"
        ) from exc
    try:
        validated = _validate_output_descriptor(descriptor, output)
    finally:
        os.close(descriptor)
    files = {
        relative
        for relative, entry in validated.entries.items()
        if entry.identity[2] == stat.S_IFREG
    }
    directories = [
        output / relative
        for relative, entry in validated.entries.items()
        if entry.identity[2] == stat.S_IFDIR
    ]
    return files, directories


def _retention_name(output: Path, slot: str) -> str:
    return f".{output.name}.{slot}"


def _require_absent(directory_descriptor: int, name: str, *, description: str) -> None:
    try:
        os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise MapBackgroundAtlasError(
        f"{description} is occupied; external operator cleanup is required"
    )


def _rename_noreplace(
    source: str,
    destination: str,
    *,
    source_directory_descriptor: int,
    destination_directory_descriptor: int,
) -> None:
    """Rename atomically without ever replacing a raced-in destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise MapBackgroundAtlasError(
            "atomic no-replace rename is unavailable on this host"
        ) from exc
    result = renameat2(
        source_directory_descriptor,
        os.fsencode(source),
        destination_directory_descriptor,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.ENOSYS, errno.EINVAL}:
            raise MapBackgroundAtlasError(
                "atomic no-replace rename is unavailable on this filesystem"
            )
        raise OSError(error, os.strerror(error), destination)


def _rename_exchange(
    first: str,
    second: str,
    *,
    directory_descriptor: int,
) -> None:
    """Atomically exchange two directory entries without an absent-name window."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise MapBackgroundAtlasError(
            "atomic exchange rename is unavailable on this host"
        ) from exc
    result = renameat2(
        directory_descriptor,
        os.fsencode(first),
        directory_descriptor,
        os.fsencode(second),
        _RENAME_EXCHANGE,
    )
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}:
            raise MapBackgroundAtlasError(
                "atomic exchange rename is unavailable on this filesystem"
            )
        raise OSError(error, os.strerror(error), f"{first}<->{second}")


def _pin_owned_output(output: Path) -> _QuarantinedOutput:
    """Open and validate the current publication without changing its name."""
    parent_descriptor = os.open(output.parent, _DIRECTORY_FLAGS)
    try:
        tree_descriptor = os.open(
            output.name, _DIRECTORY_FLAGS, dir_fd=parent_descriptor
        )
    except OSError as exc:
        os.close(parent_descriptor)
        raise MapBackgroundAtlasError(
            f"refusing non-directory atlas output: {output}"
        ) from exc
    try:
        validated = _validate_output_descriptor(tree_descriptor, output)
        current = os.stat(output.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if _identity(current) != validated.root_identity:
            raise MapBackgroundAtlasError(
                "atlas output changed while its publication was pinned"
            )
        return _QuarantinedOutput(
            output,
            output.name,
            parent_descriptor,
            tree_descriptor,
            validated,
        )
    except Exception:
        os.close(tree_descriptor)
        os.close(parent_descriptor)
        raise


def _quarantine_owned_output(
    output: Path, *, slot: str = "prior"
) -> _QuarantinedOutput:
    """Pin, validate, and atomically isolate the exact published directory."""
    parent_descriptor = os.open(output.parent, _DIRECTORY_FLAGS)
    try:
        tree_descriptor = os.open(
            output.name, _DIRECTORY_FLAGS, dir_fd=parent_descriptor
        )
    except OSError as exc:
        os.close(parent_descriptor)
        raise MapBackgroundAtlasError(
            f"refusing non-directory atlas output: {output}"
        ) from exc
    quarantine_moved = False
    try:
        validated = _validate_output_descriptor(tree_descriptor, output)
        quarantine_name = _retention_name(output, slot)
        _rename_noreplace(
            output.name,
            quarantine_name,
            source_directory_descriptor=parent_descriptor,
            destination_directory_descriptor=parent_descriptor,
        )
        quarantine_moved = True
        moved = os.stat(
            quarantine_name, dir_fd=parent_descriptor, follow_symlinks=False
        )
        if _identity(moved) != validated.root_identity:
            raise MapBackgroundAtlasError(
                "atlas output changed while it was moved to quarantine"
            )
        quarantined_validation = _validate_output_descriptor(tree_descriptor, output)
        if quarantined_validation != validated:
            raise MapBackgroundAtlasError(
                "atlas output tree changed while it was moved to quarantine"
            )
        return _QuarantinedOutput(
            output.parent / quarantine_name,
            quarantine_name,
            parent_descriptor,
            tree_descriptor,
            validated,
        )
    except Exception as quarantine_error:
        recovery_errors: list[Exception] = []
        if quarantine_moved:
            try:
                current_validation = _validate_output_descriptor(
                    tree_descriptor, output
                )
                if current_validation != validated:
                    raise MapBackgroundAtlasError(
                        "quarantined atlas publication changed before restoration"
                    )
                current = os.stat(
                    quarantine_name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if _identity(current) != validated.root_identity:
                    raise MapBackgroundAtlasError(
                        "quarantined atlas publication changed before restoration"
                    )
                _rename_noreplace(
                    quarantine_name,
                    output.name,
                    source_directory_descriptor=parent_descriptor,
                    destination_directory_descriptor=parent_descriptor,
                )
                os.fsync(parent_descriptor)
                restored = os.stat(
                    output.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                restored_validation = _validate_output_descriptor(
                    tree_descriptor, output
                )
                if (
                    _identity(restored) != validated.root_identity
                    or restored_validation != validated
                ):
                    raise MapBackgroundAtlasError(
                        "quarantined atlas publication changed during restoration"
                    )
            except Exception as exc:  # noqa: BLE001 - preserve recovery failures
                recovery_errors.append(exc)
        for descriptor in (tree_descriptor, parent_descriptor):
            try:
                os.close(descriptor)
            except OSError as exc:
                recovery_errors.append(exc)
        if recovery_errors:
            raise MapBackgroundAtlasCompositeError(
                "atlas quarantine failed and the prior publication could not be "
                "restored; the public atlas output may be unavailable",
                [quarantine_error, *recovery_errors],
            ) from None
        raise


def _retain_owned_output(output: Path) -> Path:
    """Atomically quarantine a validated tree for deferred external cleanup.

    In-process recursive deletion cannot bind an unlink or rmdir to the identity
    checked immediately beforehand.  Retention is deliberately fail-closed: the
    fixed quarantine name is never destructively accessed by this process.
    """
    quarantined = _quarantine_owned_output(output)
    try:
        return quarantined.path
    finally:
        quarantined.close()


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


def _rollback_publication(output: Path, backup: _QuarantinedOutput) -> None:
    """Restore the prior tree and retain any failed publication for recovery."""
    errors: list[Exception] = []
    failed: _QuarantinedOutput | None = None
    restore_allowed = not (output.exists() or output.is_symlink())
    try:
        if not restore_allowed:
            try:
                failed = _quarantine_owned_output(output, slot="failed")
            except Exception as exc:  # noqa: BLE001 - preserve recovery failures
                errors.append(exc)
            else:
                restore_allowed = True
                try:
                    _fsync_directory(output.parent)
                    failed_metadata = os.stat(
                        failed.name,
                        dir_fd=failed.parent_descriptor,
                        follow_symlinks=False,
                    )
                    failed_descriptor_metadata = os.fstat(failed.tree_descriptor)
                    failed_validation = _validate_output_descriptor(
                        failed.tree_descriptor, failed.path
                    )
                    if (
                        _identity(failed_metadata) != failed.validated.root_identity
                        or _identity(failed_descriptor_metadata)
                        != failed.validated.root_identity
                        or failed_validation != failed.validated
                    ):
                        raise MapBackgroundAtlasError(
                            "failed atlas publication changed while quarantine was "
                            "synchronized"
                        )
                except Exception as exc:  # noqa: BLE001 - preserve recovery failures
                    errors.append(exc)
        if restore_allowed:
            try:
                current_validation = _validate_output_descriptor(
                    backup.tree_descriptor, backup.path
                )
                if current_validation != backup.validated:
                    raise MapBackgroundAtlasError(
                        "prior atlas publication changed before rollback"
                    )
                current = os.stat(
                    backup.name,
                    dir_fd=backup.parent_descriptor,
                    follow_symlinks=False,
                )
                if _identity(current) != backup.validated.root_identity:
                    raise MapBackgroundAtlasError(
                        "prior atlas publication changed before rollback"
                    )
                _rename_noreplace(
                    backup.name,
                    output.name,
                    source_directory_descriptor=backup.parent_descriptor,
                    destination_directory_descriptor=backup.parent_descriptor,
                )
                _fsync_directory(output.parent)
                restored = os.stat(
                    output.name,
                    dir_fd=backup.parent_descriptor,
                    follow_symlinks=False,
                )
                if _identity(restored) != backup.validated.root_identity:
                    raise MapBackgroundAtlasError(
                        "prior atlas publication changed during rollback"
                    )
                restored_validation = _validate_output_descriptor(
                    backup.tree_descriptor, output
                )
                if restored_validation != backup.validated:
                    raise MapBackgroundAtlasError(
                        "prior atlas publication changed during rollback"
                    )
            except Exception as exc:  # noqa: BLE001 - preserve recovery failures
                errors.append(exc)
    finally:
        try:
            backup.close()
        except Exception as exc:  # noqa: BLE001 - preserve recovery failures
            errors.append(exc)
        if failed is not None:
            try:
                failed.close()
            except Exception as exc:  # noqa: BLE001 - preserve recovery failures
                errors.append(exc)
    if errors:
        raise MapBackgroundAtlasCompositeError(
            "atlas rollback encountered failures", errors
        )


def _quarantine_pinned_publication(
    output: Path,
    *,
    parent_descriptor: int,
    tree_descriptor: int,
    expected_root_identity: tuple[int, int, int],
) -> None:
    """Move the exact descriptor-pinned failed publication to its fixed slot."""
    failed_name = _retention_name(output, "failed")
    _require_absent(
        parent_descriptor,
        failed_name,
        description="atlas failed-publication slot",
    )
    if _identity(os.fstat(tree_descriptor)) != expected_root_identity:
        raise MapBackgroundAtlasError(
            "failed atlas publication no longer matches its pinned tree"
        )
    current = os.stat(output.name, dir_fd=parent_descriptor, follow_symlinks=False)
    if _identity(current) != expected_root_identity:
        raise MapBackgroundAtlasError(
            "failed atlas publication changed before quarantine"
        )
    _rename_noreplace(
        output.name,
        failed_name,
        source_directory_descriptor=parent_descriptor,
        destination_directory_descriptor=parent_descriptor,
    )
    moved = os.stat(failed_name, dir_fd=parent_descriptor, follow_symlinks=False)
    if _identity(moved) != expected_root_identity:
        recovery_errors: list[Exception] = [
            MapBackgroundAtlasError(
                "failed atlas publication changed during quarantine"
            )
        ]
        try:
            _rename_noreplace(
                failed_name,
                output.name,
                source_directory_descriptor=parent_descriptor,
                destination_directory_descriptor=parent_descriptor,
            )
            _fsync_directory(output.parent)
            restored = os.stat(
                output.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                _identity(restored) != expected_root_identity
                or _identity(os.fstat(tree_descriptor)) != expected_root_identity
            ):
                raise MapBackgroundAtlasError(
                    "failed atlas publication changed during quarantine recovery"
                )
        except Exception as exc:  # noqa: BLE001 - preserve recovery failures
            recovery_errors.append(exc)
        raise MapBackgroundAtlasCompositeError(
            "failed atlas quarantine encountered failures", recovery_errors
        )


def _recover_postpublication_failure(
    output: Path,
    backup: _QuarantinedOutput | None,
    *,
    parent_descriptor: int,
    tree_descriptor: int,
    expected_root_identity: tuple[int, int, int],
) -> None:
    """Retain a failed new tree, then restore the exact prior tree if present."""
    errors: list[Exception] = []
    failed_quarantined = False
    try:
        try:
            _quarantine_pinned_publication(
                output,
                parent_descriptor=parent_descriptor,
                tree_descriptor=tree_descriptor,
                expected_root_identity=expected_root_identity,
            )
        except Exception as exc:  # noqa: BLE001 - preserve recovery failures
            errors.append(exc)
        else:
            failed_quarantined = True
            try:
                _fsync_directory(output.parent)
                failed_metadata = os.stat(
                    _retention_name(output, "failed"),
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if (
                    _identity(failed_metadata) != expected_root_identity
                    or _identity(os.fstat(tree_descriptor)) != expected_root_identity
                ):
                    raise MapBackgroundAtlasError(
                        "failed atlas publication changed while quarantine was "
                        "synchronized"
                    )
            except Exception as exc:  # noqa: BLE001 - preserve recovery failures
                errors.append(exc)

        if failed_quarantined and backup is not None:
            try:
                current_validation = _validate_output_descriptor(
                    backup.tree_descriptor, backup.path
                )
                if current_validation != backup.validated:
                    raise MapBackgroundAtlasError(
                        "prior atlas publication changed before rollback"
                    )
                current = os.stat(
                    backup.name,
                    dir_fd=backup.parent_descriptor,
                    follow_symlinks=False,
                )
                if _identity(current) != backup.validated.root_identity:
                    raise MapBackgroundAtlasError(
                        "prior atlas publication changed before rollback"
                    )
                _rename_noreplace(
                    backup.name,
                    output.name,
                    source_directory_descriptor=backup.parent_descriptor,
                    destination_directory_descriptor=backup.parent_descriptor,
                )
                _fsync_directory(output.parent)
                restored = os.stat(
                    output.name,
                    dir_fd=backup.parent_descriptor,
                    follow_symlinks=False,
                )
                if _identity(restored) != backup.validated.root_identity:
                    raise MapBackgroundAtlasError(
                        "prior atlas publication changed during rollback"
                    )
                restored_validation = _validate_output_descriptor(
                    backup.tree_descriptor, output
                )
                if restored_validation != backup.validated:
                    raise MapBackgroundAtlasError(
                        "prior atlas publication changed during rollback"
                    )
            except Exception as exc:  # noqa: BLE001 - preserve recovery failures
                errors.append(exc)
    finally:
        if backup is not None:
            try:
                backup.close()
            except Exception as exc:  # noqa: BLE001 - preserve recovery failures
                errors.append(exc)
    if errors:
        raise MapBackgroundAtlasCompositeError(
            "atlas post-publication recovery encountered failures", errors
        )


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
    parent_descriptor = os.open(output.parent, _DIRECTORY_FLAGS)
    temporary_name = _retention_name(output, "tmp")
    prior_name = _retention_name(output, "prior")
    failed_name = _retention_name(output, "failed")
    try:
        _require_absent(
            parent_descriptor, temporary_name, description="atlas temporary slot"
        )
        _require_absent(
            parent_descriptor, prior_name, description="atlas prior-publication slot"
        )
        _require_absent(
            parent_descriptor, failed_name, description="atlas failed-publication slot"
        )
        os.mkdir(temporary_name, mode=0o700, dir_fd=parent_descriptor)
        temporary_descriptor = os.open(
            temporary_name, _DIRECTORY_FLAGS, dir_fd=parent_descriptor
        )
    except Exception:
        os.close(parent_descriptor)
        raise
    temporary = output.parent / temporary_name
    published = False
    backup: _QuarantinedOutput | None = None
    try:
        manifest = _build_atlases_in_directory(
            root, temporary, product=product, batches=batches
        )
        producer_validation = _validate_output_descriptor(
            temporary_descriptor, temporary
        )
        if producer_validation.manifest_sha256 != _sha(
            canonical_json(manifest).encode("utf-8")
        ):
            raise MapBackgroundAtlasError(
                "atlas producer result does not match its temporary manifest"
            )
        manifest = _address_artifacts(temporary, manifest)
        if output.exists() or output.is_symlink():
            if output.is_symlink() or not output.is_dir():
                raise MapBackgroundAtlasError(
                    f"refusing non-directory atlas output: {output}"
                )
            backup = _pin_owned_output(output)
            _carry_forward_artifacts(output, temporary)
            if _validate_output_descriptor(backup.tree_descriptor, output) != (
                backup.validated
            ):
                raise MapBackgroundAtlasError(
                    "prior atlas publication changed while artifacts were retained"
                )
        producer_validation = _validate_output_descriptor(
            temporary_descriptor, temporary
        )
        if producer_validation.manifest_sha256 != _sha(
            canonical_json(manifest).encode("utf-8")
        ):
            raise MapBackgroundAtlasError(
                "content-addressed atlas result does not match its manifest"
            )
        synchronized_files = _validate_output_descriptor(
            temporary_descriptor, temporary, synchronize_files=True
        )
        if synchronized_files != producer_validation:
            raise MapBackgroundAtlasError(
                "atlas temporary tree changed while its files were synchronized"
            )
        _fsync_tree_directories(temporary)
        validated_temporary = _validate_output_descriptor(
            temporary_descriptor, temporary
        )
        if validated_temporary != synchronized_files:
            raise MapBackgroundAtlasError(
                "atlas temporary tree changed while it was synchronized"
            )
        publication_moved = False
        try:
            # Validate the pinned producer tree again after every fsync and with
            # no intervening filesystem operation before its atomic publication.
            final_validation = _validate_output_descriptor(
                temporary_descriptor, temporary
            )
            if final_validation != validated_temporary:
                raise MapBackgroundAtlasError(
                    "atlas temporary tree changed after synchronization"
                )
            if backup is None:
                _rename_noreplace(
                    temporary_name,
                    output.name,
                    source_directory_descriptor=parent_descriptor,
                    destination_directory_descriptor=parent_descriptor,
                )
                publication_moved = True
            else:
                current_validation = _validate_output_descriptor(
                    backup.tree_descriptor, output
                )
                if current_validation != backup.validated:
                    raise MapBackgroundAtlasError(
                        "prior atlas publication changed before atomic replacement"
                    )
                current_root = os.stat(
                    output.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if _identity(current_root) != backup.validated.root_identity:
                    raise MapBackgroundAtlasError(
                        "prior atlas public root changed before atomic replacement"
                    )
                _rename_exchange(
                    temporary_name,
                    output.name,
                    directory_descriptor=parent_descriptor,
                )
                publication_moved = True
                backup.path = temporary
                backup.name = temporary_name
                retained_root = os.stat(
                    temporary_name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if _identity(retained_root) != backup.validated.root_identity:
                    raise MapBackgroundAtlasError(
                        "atomic replacement did not retain the exact prior atlas root"
                    )
            _fsync_directory(output.parent)
            published_metadata = os.stat(
                output.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            published_descriptor_metadata = os.fstat(temporary_descriptor)
            postpublication_validation = _validate_output_descriptor(
                temporary_descriptor, output
            )
            if (
                postpublication_validation != final_validation
                or _identity(published_metadata) != final_validation.root_identity
                or _identity(published_descriptor_metadata)
                != final_validation.root_identity
            ):
                raise MapBackgroundAtlasError(
                    "published atlas changed after its final validation"
                )
            if backup is not None:
                _rename_noreplace(
                    temporary_name,
                    prior_name,
                    source_directory_descriptor=parent_descriptor,
                    destination_directory_descriptor=parent_descriptor,
                )
                backup.path = output.parent / prior_name
                backup.name = prior_name
                _fsync_directory(output.parent)
                retained_validation = _validate_output_descriptor(
                    backup.tree_descriptor, backup.path
                )
                if retained_validation != backup.validated:
                    raise MapBackgroundAtlasError(
                        "prior atlas publication changed during retention"
                    )
        except Exception as publication_error:
            if publication_moved and backup is not None:
                recovery_errors: list[Exception] = []
                try:
                    # Put the old complete tree back at the public name in one
                    # exchange.  The rejected new tree moves back to the fixed
                    # temporary slot and is then retained for diagnosis.
                    rejected_name = backup.name
                    rollback_validation = _validate_output_descriptor(
                        backup.tree_descriptor, backup.path
                    )
                    if rollback_validation != backup.validated:
                        raise MapBackgroundAtlasError(
                            "prior atlas publication changed before atomic rollback"
                        )
                    retained_root = os.stat(
                        rejected_name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                    if _identity(retained_root) != backup.validated.root_identity:
                        raise MapBackgroundAtlasError(
                            "exact prior atlas root is disconnected from its retained name"
                        )
                    _rename_exchange(
                        output.name,
                        rejected_name,
                        directory_descriptor=parent_descriptor,
                    )
                    _fsync_directory(output.parent)
                    restored_root = os.stat(
                        output.name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                    rejected_root = os.stat(
                        rejected_name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                    restored = _validate_output_descriptor(
                        backup.tree_descriptor, output
                    )
                    if (
                        restored != backup.validated
                        or _identity(restored_root) != backup.validated.root_identity
                        or _identity(os.fstat(backup.tree_descriptor))
                        != backup.validated.root_identity
                        or _identity(rejected_root) != final_validation.root_identity
                        or _identity(os.fstat(temporary_descriptor))
                        != final_validation.root_identity
                    ):
                        raise MapBackgroundAtlasError(
                            "atomic rollback did not restore the exact prior atlas "
                            "root and retain the exact failed publication"
                        )
                    backup.path = output
                    backup.name = output.name
                    _rename_noreplace(
                        rejected_name,
                        failed_name,
                        source_directory_descriptor=parent_descriptor,
                        destination_directory_descriptor=parent_descriptor,
                    )
                    _fsync_directory(output.parent)
                except Exception as recovery_error:  # noqa: BLE001
                    recovery_errors.append(recovery_error)
                try:
                    backup.close()
                except Exception as close_error:  # noqa: BLE001
                    recovery_errors.append(close_error)
                backup = None
                if recovery_errors:
                    raise MapBackgroundAtlasCompositeError(
                        "atlas publication and recovery both failed",
                        [publication_error, *recovery_errors],
                    ) from None
            elif publication_moved:
                try:
                    _recover_postpublication_failure(
                        output,
                        None,
                        parent_descriptor=parent_descriptor,
                        tree_descriptor=temporary_descriptor,
                        expected_root_identity=final_validation.root_identity,
                    )
                except Exception as recovery_error:  # noqa: BLE001
                    raise MapBackgroundAtlasCompositeError(
                        "atlas publication and recovery both failed",
                        [publication_error, recovery_error],
                    ) from None
            elif backup is not None:
                backup.close()
                backup = None
            raise
        published = True
        if backup is not None:
            backup.close()
            backup = None
        return manifest
    finally:
        if backup is not None:
            backup.close()
        os.close(temporary_descriptor)
        os.close(parent_descriptor)
        if not published:
            # The fixed temporary slot is retained for diagnosis.  A later run
            # refuses while it is occupied, bounding retained producer trees.
            pass


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

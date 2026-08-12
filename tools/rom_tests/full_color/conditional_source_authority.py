"""Exact authority for source symbols emitted only by PHASE2_AUDIT."""

from __future__ import annotations

import hashlib
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Any, Collection

from .rom_discovery import RomDiscoveryError, load_sym


PRODUCTS = {
    "normal": ("pokeyellow.gbc", "pokeyellow.sym"),
    "debug": ("pokeyellow_debug.gbc", "pokeyellow_debug.sym"),
    "vc": ("pokeyellow_vc.gbc", "pokeyellow_vc.sym"),
    "audit": ("pokeyellow_phase2_audit.gbc", "pokeyellow_phase2_audit.sym"),
}
PRODUCTION_PRODUCTS = ("normal", "debug", "vc")

_IF = re.compile(r"^\s*IF\s+DEF\(PHASE2_AUDIT\)\s*(?:;.*)?$", re.IGNORECASE)
_OTHER_IF = re.compile(r"^\s*IF(?:DEF|NDEF)?\b", re.IGNORECASE)
_ELSE = re.compile(r"^\s*ELSE\s*(?:;.*)?$", re.IGNORECASE)
_ENDC = re.compile(r"^\s*ENDC\s*(?:;.*)?$", re.IGNORECASE)
_GLOBAL_LABEL = re.compile(r"^([A-Za-z_][\w#]*)(?:::|:)\s*(?:;.*)?$")
_LOCAL_LABEL = re.compile(r"^(\.[A-Za-z_][\w#]*)(?:::|:)?\s*(?:;.*)?$")


class ConditionalSourceAuthorityError(ValueError):
    """A conditional source-region claim is malformed or stale."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _body_sha256(lines: list[str], start: int, end: int) -> str:
    body = "\n".join(lines[start - 1 : end]) + "\n"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _conditional_lines(lines: list[str]) -> frozenset[int]:
    """Return lines in a direct, true PHASE2_AUDIT arm.

    Nested conditionals and ELSE arms are deliberately excluded. This keeps the
    reviewed exception structural and prevents a second flag from widening it.
    """
    stack: list[tuple[bool, bool]] = []
    result: set[int] = set()
    for number, raw in enumerate(lines, 1):
        line = raw.split(";", 1)[0].rstrip()
        if _IF.match(line):
            stack.append((True, False))
            continue
        if _OTHER_IF.match(line):
            stack.append((False, False))
            continue
        if _ELSE.match(line):
            if not stack:
                raise ConditionalSourceAuthorityError(
                    f"conditional source has unmatched ELSE at line {number}"
                )
            audit, _ = stack.pop()
            stack.append((audit, True))
            continue
        if _ENDC.match(line):
            if not stack:
                raise ConditionalSourceAuthorityError(
                    f"conditional source has unmatched ENDC at line {number}"
                )
            stack.pop()
            continue
        if len(stack) == 1 and stack[0] == (True, False):
            result.add(number)
    if stack:
        raise ConditionalSourceAuthorityError("conditional source has unclosed IF")
    return frozenset(result)


def _label_lines(lines: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    labels: dict[str, int] = {}
    global_labels: dict[str, int] = {}
    owner: str | None = None
    for number, raw in enumerate(lines, 1):
        line = raw.split(";", 1)[0].strip()
        if match := _GLOBAL_LABEL.fullmatch(line):
            owner = match.group(1)
            labels[owner] = number
            global_labels[owner] = number
        elif match := _LOCAL_LABEL.fullmatch(line):
            if owner is not None:
                labels[owner + match.group(1)] = number
    return labels, global_labels


def _region_for_symbol(path: Path, relative: str, symbol: str) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    conditional = _conditional_lines(lines)
    labels, globals_ = _label_lines(lines)
    line = labels.get(symbol)
    anchor = symbol
    if line not in conditional:
        owner = symbol.split(".", 1)[0]
        line = globals_.get(owner)
        anchor = owner
    if line not in conditional:
        raise ConditionalSourceAuthorityError(
            f"{relative}:{symbol}: label is not directly enclosed by IF DEF(PHASE2_AUDIT)"
        )
    assert line is not None
    end = line
    for candidate in range(line + 1, len(lines) + 1):
        text = lines[candidate - 1].split(";", 1)[0].strip()
        if (
            _GLOBAL_LABEL.fullmatch(text)
            or _LOCAL_LABEL.fullmatch(text)
            or _ELSE.match(text)
            or _ENDC.match(text)
            or _OTHER_IF.match(text)
        ):
            break
        end = candidate
    if any(number not in conditional for number in range(line, end + 1)):
        raise ConditionalSourceAuthorityError(
            f"{relative}:{symbol}: source body escapes IF DEF(PHASE2_AUDIT)"
        )
    return {
        "path": relative,
        "symbol": symbol,
        "conditional_anchor_symbol": anchor,
        "start_line": line,
        "end_line": end,
        "body_sha256": _body_sha256(lines, line, end),
    }


def product_identities(root: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for product, (rom_name, sym_name) in PRODUCTS.items():
        result[product] = {
            "rom_sha256": _sha256(root / rom_name),
            "sym_sha256": _sha256(root / sym_name),
        }
    return result


def build_regions(
    root: Path,
    symbols_by_path: Collection[tuple[str, str]],
    reviewed_delta_paths: dict[str, dict[str, str | None]],
) -> list[dict[str, Any]]:
    root = root.resolve()
    tables = {name: load_sym(root / PRODUCTS[name][1]) for name in PRODUCTS}
    rows: list[dict[str, Any]] = []
    for relative, symbol in sorted(symbols_by_path):
        normalized = PurePosixPath(relative)
        if (
            normalized.is_absolute()
            or relative != str(normalized)
            or "\\" in relative
            or ".." in normalized.parts
        ):
            raise ConditionalSourceAuthorityError(
                f"conditional source path is not normalized: {relative!r}"
            )
        source_path = root / relative
        try:
            source_path.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as exc:
            raise ConditionalSourceAuthorityError(
                f"conditional source path escapes the repository: {relative!r}"
            ) from exc
        binding = reviewed_delta_paths.get(relative)
        if (
            not isinstance(binding, dict)
            or set(binding) != {"reviewed_sha256", "current_sha256"}
            or not _digest(binding.get("reviewed_sha256"))
            or not _digest(binding.get("current_sha256"))
        ):
            raise ConditionalSourceAuthorityError(
                f"{relative}:{symbol}: conditional authority requires a reviewed predecessor file"
            )
        if _sha256(source_path) != binding["current_sha256"]:
            raise ConditionalSourceAuthorityError(
                f"{relative}:{symbol}: conditional authority has a stale current file identity"
            )
        if any(symbol in tables[name].by_name for name in PRODUCTION_PRODUCTS):
            raise ConditionalSourceAuthorityError(
                f"{relative}:{symbol}: audit-only symbol appears in a production product"
            )
        try:
            linked = tables["audit"].by_name[symbol]
        except KeyError as exc:
            raise ConditionalSourceAuthorityError(
                f"{relative}:{symbol}: audit-only symbol is absent from the audit product"
            ) from exc
        rom = root / PRODUCTS["audit"][0]
        if linked.rom_offset >= rom.stat().st_size:
            raise ConditionalSourceAuthorityError(
                f"{relative}:{symbol}: audit symbol does not resolve inside the audit ROM"
            )
        row = _region_for_symbol(source_path, relative, symbol)
        row.update(
            {
                "reviewed_file_sha256": binding["reviewed_sha256"],
                "current_file_sha256": binding["current_sha256"],
                "audit_bank": linked.bank,
                "audit_address": linked.address,
                "audit_rom_offset": linked.rom_offset,
            }
        )
        rows.append(row)
    return rows


def validate_regions(
    root: Path,
    raw_regions: object,
    raw_products: object,
    reviewed_delta_paths: dict[str, dict[str, str | None]],
) -> frozenset[tuple[str, str]]:
    if not isinstance(raw_products, dict) or raw_products != product_identities(root):
        raise ConditionalSourceAuthorityError(
            "conditional authority does not bind the exact current product artifacts"
        )
    if not isinstance(raw_regions, list):
        raise ConditionalSourceAuthorityError("conditional source regions must be an array")
    pairs: list[tuple[str, str]] = []
    expected_keys = {
        "path", "symbol", "conditional_anchor_symbol", "start_line", "end_line",
        "body_sha256", "reviewed_file_sha256", "current_file_sha256",
        "audit_bank", "audit_address", "audit_rom_offset",
    }
    for row in raw_regions:
        if not isinstance(row, dict) or set(row) != expected_keys:
            raise ConditionalSourceAuthorityError("malformed conditional source region")
        if not isinstance(row["path"], str) or not isinstance(row["symbol"], str):
            raise ConditionalSourceAuthorityError("malformed conditional source identity")
        pairs.append((row["path"], row["symbol"]))
    if pairs != sorted(set(pairs)):
        raise ConditionalSourceAuthorityError(
            "conditional source regions must be unique and sorted"
        )
    expected = build_regions(root, pairs, reviewed_delta_paths)
    if raw_regions != expected:
        raise ConditionalSourceAuthorityError(
            "conditional source region span, body, symbol, linkage, or file identity changed"
        )
    return frozenset(pairs)


def as_rom_discovery_error(exc: ConditionalSourceAuthorityError) -> RomDiscoveryError:
    return RomDiscoveryError(str(exc))

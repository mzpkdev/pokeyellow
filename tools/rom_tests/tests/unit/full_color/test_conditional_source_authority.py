"""Hostile checks for exact PHASE2_AUDIT conditional-region authority."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.rom_tests.full_color.conditional_source_authority import (
    ConditionalSourceAuthorityError,
    PRODUCTS,
    build_regions,
    product_identities,
    validate_regions,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fixture(tmp_path: Path, source: str = "IF DEF(PHASE2_AUDIT)\nWriter::\n\tld [hl], a\nENDC\n"):
    relative = "writer.asm"
    (tmp_path / relative).write_text(source, encoding="utf-8")
    for product, (rom_name, sym_name) in PRODUCTS.items():
        (tmp_path / rom_name).write_bytes(b"\x00" * 0x8000)
        symbols = "; symbols\n"
        if product == "audit":
            symbols += "01:4000 Writer\n"
        (tmp_path / sym_name).write_text(symbols, encoding="utf-8")
    current = _sha256(source.encode())
    bindings = {
        relative: {"reviewed_sha256": "1" * 64, "current_sha256": current}
    }
    rows = build_regions(tmp_path, {(relative, "Writer")}, bindings)
    products = product_identities(tmp_path)
    return relative, bindings, rows, products


@pytest.mark.parametrize(
    "source",
    (
        "Writer::\n\tld [hl], a\n",
        "IF DEF(RENAMED_AUDIT)\nWriter::\n\tld [hl], a\nENDC\n",
        "IF DEF(PHASE2_AUDIT)\nIF DEF(OTHER)\nWriter::\n\tld [hl], a\nENDC\nENDC\n",
        "IF DEF(PHASE2_AUDIT)\nELSE\nWriter::\n\tld [hl], a\nENDC\n",
    ),
)
def test_region_rejects_outside_renamed_nested_or_else_conditionals(
    tmp_path: Path, source: str
) -> None:
    relative, bindings, _, _ = _fixture(tmp_path)
    (tmp_path / relative).write_text(source, encoding="utf-8")
    bindings[relative]["current_sha256"] = _sha256(source.encode())
    with pytest.raises(ConditionalSourceAuthorityError, match="directly enclosed"):
        build_regions(tmp_path, {(relative, "Writer")}, bindings)


@pytest.mark.parametrize(
    "mutation",
    (
        "widen", "body", "wrong-symbol", "traversal", "stale-reviewed",
        "stale-current",
    ),
)
def test_region_rejects_span_body_symbol_and_file_identity_drift(
    tmp_path: Path, mutation: str
) -> None:
    _, bindings, rows, products = _fixture(tmp_path)
    changed = [dict(rows[0])]
    changed_bindings = {path: dict(binding) for path, binding in bindings.items()}
    if mutation == "widen":
        changed[0]["end_line"] += 1
    elif mutation == "body":
        changed[0]["body_sha256"] = "0" * 64
    elif mutation == "wrong-symbol":
        changed[0]["symbol"] = "WrongWriter"
    elif mutation == "traversal":
        changed[0]["path"] = "../writer.asm"
    elif mutation == "stale-reviewed":
        changed_bindings["writer.asm"]["reviewed_sha256"] = "2" * 64
    else:
        changed_bindings["writer.asm"]["current_sha256"] = "2" * 64
    with pytest.raises(ConditionalSourceAuthorityError):
        validate_regions(tmp_path, changed, products, changed_bindings)


def test_region_rejects_production_symbol_appearance(tmp_path: Path) -> None:
    relative, bindings, _, _ = _fixture(tmp_path)
    normal_sym = tmp_path / PRODUCTS["normal"][1]
    normal_sym.write_text("01:4000 Writer\n", encoding="utf-8")
    with pytest.raises(ConditionalSourceAuthorityError, match="production product"):
        build_regions(tmp_path, {(relative, "Writer")}, bindings)


def test_region_requires_exact_audit_symbol_and_rom_linkage(tmp_path: Path) -> None:
    relative, bindings, _, _ = _fixture(tmp_path)
    audit_sym = tmp_path / PRODUCTS["audit"][1]
    audit_sym.write_text("01:4000 DifferentWriter\n", encoding="utf-8")
    with pytest.raises(ConditionalSourceAuthorityError, match="absent from the audit"):
        build_regions(tmp_path, {(relative, "Writer")}, bindings)

    audit_sym.write_text("02:4000 Writer\n", encoding="utf-8")
    with pytest.raises(ConditionalSourceAuthorityError, match="inside the audit ROM"):
        build_regions(tmp_path, {(relative, "Writer")}, bindings)


def test_region_rejects_stale_product_hash_proof(tmp_path: Path) -> None:
    _, bindings, rows, products = _fixture(tmp_path)
    products["debug"]["sym_sha256"] = "0" * 64
    with pytest.raises(ConditionalSourceAuthorityError, match="exact current product"):
        validate_regions(tmp_path, rows, products, bindings)


def test_region_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-writer.asm"
    source = "IF DEF(PHASE2_AUDIT)\nWriter::\n\tld [hl], a\nENDC\n"
    outside.write_text(source, encoding="utf-8")
    linked = tmp_path / "linked"
    linked.symlink_to(tmp_path.parent, target_is_directory=True)
    relative = "linked/outside-writer.asm"
    bindings = {
        relative: {
            "reviewed_sha256": "1" * 64,
            "current_sha256": _sha256(source.encode()),
        }
    }
    for product, (rom_name, sym_name) in PRODUCTS.items():
        (tmp_path / rom_name).write_bytes(b"\x00" * 0x8000)
        symbols = "01:4000 Writer\n" if product == "audit" else "; symbols\n"
        (tmp_path / sym_name).write_text(symbols, encoding="utf-8")
    with pytest.raises(ConditionalSourceAuthorityError, match="escapes the repository"):
        build_regions(tmp_path, {(relative, "Writer")}, bindings)


def test_region_identity_keeps_same_symbol_in_different_paths_distinct(
    tmp_path: Path,
) -> None:
    _, bindings, rows, products = _fixture(tmp_path)
    identities = validate_regions(tmp_path, rows, products, bindings)
    assert identities == frozenset({("writer.asm", "Writer")})
    assert ("different.asm", "Writer") not in identities

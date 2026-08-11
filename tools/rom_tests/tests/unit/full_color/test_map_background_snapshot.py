"""Contracts for canonical map-background source/product evidence."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import tempfile

import pytest

from tools.rom_tests.full_color import map_background_snapshot as snapshot_module
from tools.rom_tests.full_color.map_background_content import MapBackgroundAuthority
from tools.rom_tests.full_color.map_background_content import (
    production_map_override_rules,
)
from tools.rom_tests.full_color.map_background_snapshot import (
    MANIFEST_PATH,
    PRODUCTS,
    SCHEMA,
    MapBackgroundSnapshotError,
    _product_snapshot,
    canonical_json,
    generate,
    main,
    verify,
)
from tools.rom_tests.full_color.rom_discovery import load_sym


ROOT = Path(__file__).parents[5]


def _copy_product(tmp_path: Path, product: str = "pokeyellow") -> None:
    for suffix in ("gbc", "sym", "map"):
        shutil.copy2(ROOT / f"{product}.{suffix}", tmp_path / f"{product}.{suffix}")


def _mutate_symbol_payload(
    tmp_path: Path,
    symbol: str,
    *,
    value: int,
    offset: int = 0,
    product: str = "pokeyellow",
) -> None:
    table = load_sym(tmp_path / f"{product}.sym")
    rom_offset = table.by_name[symbol].rom_offset + offset
    path = tmp_path / f"{product}.gbc"
    rom = bytearray(path.read_bytes())
    rom[rom_offset] = value
    path.write_bytes(rom)


def _mutate_routine_sequence(
    tmp_path: Path,
    product: str,
    routine: str,
    sequence: bytes,
    *,
    sequence_offset: int,
) -> None:
    symbols = load_sym(tmp_path / f"{product}.sym")
    path = tmp_path / f"{product}.gbc"
    rom = bytearray(path.read_bytes())
    start = symbols.by_name[routine].rom_offset
    relative = bytes(rom[start : start + 256]).find(sequence)
    assert relative >= 0, (product, routine, sequence.hex())
    location = start + relative + sequence_offset
    rom[location] ^= 1
    path.write_bytes(rom)


def _snapshot_product(
    root: Path, product: str, authority: MapBackgroundAuthority
) -> dict[str, object]:
    return _product_snapshot(
        root, product, authority, production_map_override_rules(ROOT)
    )


def _shadow_repository(tmp_path: Path, *, copied_directories: tuple[str, ...]) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    copied = {*copied_directories, "macros", "constants"}
    for child in ROOT.iterdir():
        destination = root / child.name
        if child.name in copied:
            shutil.copytree(child, destination, symlinks=True)
        elif child.name == "includes.asm":
            shutil.copy2(child, destination)
        else:
            destination.symlink_to(child, target_is_directory=child.is_dir())
    return root


def test_checked_manifest_is_canonical_stable_and_current() -> None:
    first = generate(ROOT)
    second = generate(ROOT)
    assert first == second
    assert first["schema"] == SCHEMA
    assert canonical_json(first) == (ROOT / MANIFEST_PATH).read_text(encoding="utf-8")
    assert verify(ROOT, MANIFEST_PATH) == first
    assert json.loads(canonical_json(first)) == first


def test_source_and_all_four_products_have_exact_payload_parity() -> None:
    snapshot = generate(ROOT)
    assert [row["product"] for row in snapshot["products"]] == list(PRODUCTS)
    assert len(snapshot["source"]["authorities"]) == 14
    views = []
    for product in snapshot["products"]:
        assert len(product["payloads"]) == 31
        assert len(product["pointer_tables"]["palettes"]["rows"]) == 25
        assert len(product["pointer_tables"]["attributes"]["rows"]) == 25
        assert set(product["linked_consumers"]) == {
            "MAP_ATTRIBUTE_OVERRIDES",
            "ROOF_REGION_RULES",
            "SPINNER_ARROW_TILES",
            "REPLACE_TILE_BLOCK",
            "CUT_TREE",
            "CINNABAR_GYM_GATE_BLOCKS",
        }
        views.append(
            {
                name: (row["size"], row["sha256"], row["bytes"])
                for name, row in product["payloads"].items()
            }
        )
    assert all(view == views[0] for view in views[1:])


def test_exact_sizes_roofs_semantics_and_legal_attribute_bits_are_retained() -> None:
    snapshot = generate(ROOT)
    product = snapshot["products"][0]
    assert product["roof_assignments"]["size"] == 37
    assert product["roof_region_rules"]["size"] == 4
    assert product["roof_palettes"]["size"] == 44
    assert product["map_overrides"]["size"] == 15
    assert bytes.fromhex(product["roof_region_rules"]["bytes"]) == bytes(
        (0x11, 2, 10, 5)
    )
    assert bytes.fromhex(product["map_overrides"]["bytes"]) == bytes(
        (
            0x7E,
            5,
            3,
            0x4B,
            0x4C,
            0x4D,
            0x4E,
            0x4F,
            0x7A,
            4,
            4,
            0x07,
            0x08,
            0x17,
            0x18,
        )
    )
    assert snapshot["source"]["semantic"]["animations"] == [
        "TILEANIM_WATER",
        "TILEANIM_WATER_FLOWER",
    ]
    assert snapshot["source"]["semantic"]["replacements"] == [
        "CINNABAR_GYM_GATE_BLOCKS",
        "CUT_TREE",
        "REPLACE_TILE_BLOCK",
        "SPINNER_ARROW_TILES",
    ]
    assert snapshot["source"]["semantic"]["overrides"] == [
        {
            "map_id": 122,
            "map": "CELADON_MART_1F",
            "identities": ["CELADON_MART_1F_TILES_07_08_17_18_YELLOW"],
        },
        {
            "map_id": 126,
            "map": "CELADON_MART_ROOF",
            "identities": ["CELADON_MART_ROOF_TILES_4B_TO_4F_BLUE"],
        },
    ]
    assert snapshot["source"]["semantic"]["override_rules"] == [
        {
            "identity": "CELADON_MART_ROOF_TILES_4B_TO_4F_BLUE",
            "map": "CELADON_MART_ROOF",
            "match": "inclusive-range",
            "tiles": [0x4B, 0x4C, 0x4D, 0x4E, 0x4F],
            "palette": "FULL_COLOR_INTERIOR_BLUE",
            "palette_value": 3,
        },
        {
            "identity": "CELADON_MART_1F_TILES_07_08_17_18_YELLOW",
            "map": "CELADON_MART_1F",
            "match": "exact-set",
            "tiles": [0x07, 0x08, 0x17, 0x18],
            "palette": "FULL_COLOR_INTERIOR_YELLOW",
            "palette_value": 4,
        },
    ]
    assert len(snapshot["source"]["semantic"]["roofs"]) == 34
    for row in product["payloads"].values():
        if row["kind"] == "palette":
            assert row["size"] == 64
        else:
            assert row["size"] == 256
            assert all(value < 8 for value in bytes.fromhex(row["bytes"]))


@pytest.mark.parametrize(
    "symbol",
    (
        "FullColorOverworldBGPalettes",
        "FullColorForestBGPalettes",
        "FullColorForestTileAttributes",
        "FullColorCavernBGPalettes",
        "FullColorCavernTileAttributes",
        "FullColorShipPortBGPalettes",
        "FullColorShipPortTileAttributes",
        "FullColorPlateauBGPalettes",
        "FullColorPlateauTileAttributes",
        "FullColorBeachHouseBGPalettes",
        "FullColorBeachHouseTileAttributes",
    ),
)
def test_linked_byte_mutation_is_observed(tmp_path: Path, symbol: str) -> None:
    _copy_product(tmp_path)
    authority = MapBackgroundAuthority.load(ROOT)
    before = _snapshot_product(tmp_path, "pokeyellow", authority)
    original = bytes.fromhex(before["payloads"][symbol]["bytes"])[0]
    _mutate_symbol_payload(tmp_path, symbol, value=original ^ 1)
    after = _snapshot_product(tmp_path, "pokeyellow", authority)
    assert after["payloads"][symbol]["sha256"] != before["payloads"][symbol]["sha256"]


@pytest.mark.parametrize(
    ("symbol", "offset", "value", "message"),
    [
        pytest.param(
            "FullColorMapAttributeOverrides",
            0,
            0x7D,
            "linked map override data contradicts semantic rules",
            id="roof-map-identity",
        ),
        pytest.param(
            "FullColorMapAttributeOverrides",
            1,
            4,
            "linked map override data contradicts semantic rules",
            id="roof-tile-count",
        ),
        pytest.param(
            "FullColorMapAttributeOverrides",
            2,
            5,
            "linked map override data contradicts semantic rules",
            id="blue-full-byte-result",
        ),
        pytest.param(
            "FullColorMapAttributeOverrides",
            3,
            0x4A,
            "linked map override data contradicts semantic rules",
            id="roof-tile-identity",
        ),
        pytest.param(
            "FullColorMapAttributeOverrides",
            8,
            0x79,
            "linked map override data contradicts semantic rules",
            id="first-floor-map-identity",
        ),
        pytest.param(
            "FullColorMapAttributeOverrides",
            10,
            5,
            "linked map override data contradicts semantic rules",
            id="yellow-full-byte-result",
        ),
        pytest.param(
            "FullColorOverworldRoofRegionRules",
            0,
            0x10,
            "linked roof-region data contradicts Route 6 reviewed semantics",
            id="roof-region-map",
        ),
        pytest.param(
            "FullColorOverworldRoofRegionRules",
            1,
            3,
            "linked roof-region data contradicts Route 6 reviewed semantics",
            id="roof-region-boundary",
        ),
        pytest.param(
            "FullColorOverworldRoofRegionRules",
            2,
            9,
            "linked roof-region data contradicts Route 6 reviewed semantics",
            id="roof-region-upper-identity",
        ),
    ],
)
def test_linked_compact_runtime_data_mutation_fails_closed(
    tmp_path: Path, symbol: str, offset: int, value: int, message: str
) -> None:
    _copy_product(tmp_path)
    _mutate_symbol_payload(tmp_path, symbol, offset=offset, value=value)

    authority = MapBackgroundAuthority.load(ROOT)
    with pytest.raises(MapBackgroundSnapshotError, match=message):
        _snapshot_product(tmp_path, "pokeyellow", authority)


@pytest.mark.parametrize("product", PRODUCTS)
def test_all_products_fail_closed_when_semantic_consumers_are_bypassed_or_split(
    tmp_path: Path, product: str
) -> None:
    authority = MapBackgroundAuthority.load(ROOT)
    symbols = load_sym(ROOT / f"{product}.sym")
    address = lambda name: symbols.by_name[name].address.to_bytes(2, "little")
    mutations = (
        (
            "remove-override-consumer",
            "PassiveFullColorResolveAttributeForIdentity",
            b"\x21" + address("FullColorMapAttributeOverrides"),
            0,
        ),
        (
            "alter-full-byte-result",
            "PassiveFullColorResolveAttributeForIdentity",
            b"\x2a\x47\x2a\x5f",
            3,
        ),
        (
            "split-roof-palette-consumer",
            "PassiveFullColorRoofPaletteForMap",
            b"\xcd" + address("PassiveFullColorCurrentRoofRegion"),
            1,
        ),
        (
            "retarget-roof-invalidation-consumer",
            "PassiveFullColorRoofRegionChanged",
            b"\xcd" + address("PassiveFullColorCurrentRoofRegion"),
            1,
        ),
        (
            "bypass-spinner-writer",
            "LoadSpinnerArrowTiles",
            b"\xcd" + address("CopyVideoData"),
            1,
        ),
        (
            "remove-generic-block-writer",
            "ReplaceTileBlock",
            b"\xfa" + address("wNewTileBlockID") + b"\x77",
            3,
        ),
        (
            "retarget-generic-block-destination",
            "ReplaceTileBlock",
            b"\x21" + address("wOverworldMap"),
            1,
        ),
        (
            "retarget-cut-authority",
            "UsedCut",
            b"\x11" + address("CutTreeBlockSwaps"),
            1,
        ),
        (
            "retarget-cut-block-destination",
            "ReplaceTreeTileBlock",
            b"\x21" + address("wCurrentTileBlockMapViewPointer"),
            1,
        ),
        (
            "split-cinnabar-writer",
            "UpdateCinnabarGymGateTileBlocks_",
            b"\xcd" + address("CinnabarGym_ReplaceTileBlock"),
            1,
        ),
        (
            "alter-cinnabar-block-store",
            "CinnabarGym_ReplaceTileBlock",
            b"\xfa" + address("wNewTileBlockID") + b"\x77\xc9",
            3,
        ),
        (
            "retarget-cinnabar-block-destination",
            "CinnabarGym_ReplaceTileBlock",
            b"\x21" + address("wOverworldMap"),
            1,
        ),
    )
    for identity, routine, sequence, sequence_offset in mutations:
        mutation_root = tmp_path / identity
        mutation_root.mkdir()
        _copy_product(mutation_root, product)
        _mutate_routine_sequence(
            mutation_root,
            product,
            routine,
            sequence,
            sequence_offset=sequence_offset,
        )
        with pytest.raises(MapBackgroundSnapshotError):
            _snapshot_product(mutation_root, product, authority)


def test_pointer_alias_cannot_replace_the_ledger_authority(tmp_path: Path) -> None:
    _copy_product(tmp_path)
    authority = MapBackgroundAuthority.load(ROOT)
    symbols = load_sym(tmp_path / "pokeyellow.sym")
    table = symbols.by_name["FullColorBGPalettePointers"]
    wrong = symbols.by_name["FullColorIndoorBGPalettes"]
    rom_path = tmp_path / "pokeyellow.gbc"
    rom = bytearray(rom_path.read_bytes())
    rom[table.rom_offset : table.rom_offset + 2] = wrong.address.to_bytes(2, "little")
    rom_path.write_bytes(rom)
    with pytest.raises(MapBackgroundSnapshotError, match="does not bind"):
        _snapshot_product(tmp_path, "pokeyellow", authority)


@pytest.mark.parametrize(
    ("table_name", "tileset_id"),
    (
        ("FullColorBGPalettePointers", 3),
        ("FullColorTileAttributePointers", 3),
        ("FullColorBGPalettePointers", 17),
        ("FullColorTileAttributePointers", 17),
        ("FullColorBGPalettePointers", 14),
        ("FullColorTileAttributePointers", 14),
        ("FullColorBGPalettePointers", 23),
        ("FullColorTileAttributePointers", 23),
        ("FullColorBGPalettePointers", 24),
        ("FullColorTileAttributePointers", 24),
    ),
)
def test_phase4_candidate_pointer_mutations_fail_closed(
    tmp_path: Path, table_name: str, tileset_id: int
) -> None:
    _copy_product(tmp_path)
    authority = MapBackgroundAuthority.load(ROOT)
    symbols = load_sym(tmp_path / "pokeyellow.sym")
    table = symbols.by_name[table_name]
    rom_path = tmp_path / "pokeyellow.gbc"
    rom = bytearray(rom_path.read_bytes())
    pointer_offset = table.rom_offset + tileset_id * 2
    rom[pointer_offset : pointer_offset + 2] = b"\x00\x00"
    rom_path.write_bytes(rom)

    with pytest.raises(MapBackgroundSnapshotError, match="does not bind"):
        _snapshot_product(tmp_path, "pokeyellow", authority)


def test_reordered_tileset_authority_cannot_reinterpret_pointer_slots(
    tmp_path: Path,
) -> None:
    _copy_product(tmp_path)
    authority = MapBackgroundAuthority.load(ROOT)
    reordered = replace(
        authority,
        tilesets=(
            authority.tilesets[1],
            authority.tilesets[0],
            *authority.tilesets[2:],
        ),
    )
    with pytest.raises(MapBackgroundSnapshotError, match="does not bind"):
        _snapshot_product(tmp_path, "pokeyellow", reordered)


def test_missing_payload_symbol_fails_closed(tmp_path: Path) -> None:
    _copy_product(tmp_path)
    sym = tmp_path / "pokeyellow.sym"
    sym.write_text(
        "\n".join(
            line
            for line in sym.read_text(encoding="utf-8").splitlines()
            if not line.endswith(" FullColorOverworldBGPalettes")
        )
        + "\n",
        encoding="utf-8",
    )
    authority = MapBackgroundAuthority.load(ROOT)
    with pytest.raises(MapBackgroundSnapshotError, match="missing linked symbol"):
        _snapshot_product(tmp_path, "pokeyellow", authority)


def test_wrong_end_symbol_size_fails_closed(tmp_path: Path) -> None:
    _copy_product(tmp_path)
    sym = tmp_path / "pokeyellow.sym"
    lines = sym.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.endswith(" FullColorOverworldBGPalettesEnd"):
            bank_address, name = line.split()
            bank, address = bank_address.split(":")
            lines[index] = f"{bank}:{int(address, 16) + 1:04x} {name}"
            break
    sym.write_text("\n".join(lines) + "\n", encoding="utf-8")
    authority = MapBackgroundAuthority.load(ROOT)
    with pytest.raises(MapBackgroundSnapshotError, match="required 64 bytes"):
        _snapshot_product(tmp_path, "pokeyellow", authority)


def test_illegal_attribute_bits_fail_closed(tmp_path: Path) -> None:
    _copy_product(tmp_path)
    _mutate_symbol_payload(tmp_path, "FullColorOverworldTileAttributes", value=0x10)
    authority = MapBackgroundAuthority.load(ROOT)
    with pytest.raises(MapBackgroundSnapshotError, match="palette bits only"):
        _snapshot_product(tmp_path, "pokeyellow", authority)


def test_semantic_source_drift_changes_the_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = MapBackgroundAuthority.load
    authority = original(ROOT)
    changed = replace(
        authority,
        maps=(replace(authority.maps[0], overrides=("DRIFT",)), *authority.maps[1:]),
    )
    monkeypatch.setattr(MapBackgroundAuthority, "load", lambda root: changed)
    candidate = generate(ROOT)
    assert candidate["source"]["semantic"]["overrides"] == [
        {
            "map_id": changed.maps[0].id,
            "map": changed.maps[0].name,
            "identities": ["DRIFT"],
        },
        {
            "map_id": 122,
            "map": "CELADON_MART_1F",
            "identities": ["CELADON_MART_1F_TILES_07_08_17_18_YELLOW"],
        },
        {
            "map_id": 126,
            "map": "CELADON_MART_ROOF",
            "identities": ["CELADON_MART_ROOF_TILES_4B_TO_4F_BLUE"],
        },
    ]


@pytest.mark.parametrize(
    ("directory", "relative", "original", "replacement"),
    [
        (
            "data",
            "data/tilesets/full_color_overworld.asm",
            "RGB 27, 31, 27 ; OUTDOOR_GRAY",
            "RGB 26, 31, 27 ; OUTDOOR_GRAY",
        ),
        (
            "data",
            "data/tilesets/full_color_interiors.asm",
            "db 3, 0, 0, 0, 1, 0, 3, 3",
            "db 2, 0, 0, 0, 1, 0, 3, 3",
        ),
        (
            "data",
            "data/tilesets/full_color_overworld.asm",
            "RGB 31, 31, 31 ; Pallet",
            "RGB 30, 31, 31 ; Pallet",
        ),
    ],
)
def test_generate_rejects_stale_products_after_exact_authored_payload_mutation(
    tmp_path: Path,
    directory: str,
    relative: str,
    original: str,
    replacement: str,
) -> None:
    root = _shadow_repository(tmp_path, copied_directories=(directory,))
    path = root / relative
    source = path.read_text(encoding="utf-8")
    assert original in source
    path.write_text(source.replace(original, replacement, 1), encoding="utf-8")
    with pytest.raises(MapBackgroundSnapshotError, match="differs from checked-in"):
        generate(root)


def test_override_boundary_mutation_fails_closed_before_snapshot(
    tmp_path: Path,
) -> None:
    root = _shadow_repository(tmp_path, copied_directories=("data",))
    path = root / "data/tilesets/full_color_interiors.asm"
    source = path.read_text(encoding="utf-8")
    original = "\tdb $4b, $4c, $4d, $4e, $4f"
    assert original in source
    path.write_text(
        source.replace(original, "\tdb $4c, $4d, $4e, $4f, $50", 1),
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError, match="override identities, data shape, or exact values drifted"
    ):
        generate(root)


@pytest.mark.parametrize(
    ("original", "replacement"),
    (
        ("CELADON_MART_ROOF, 5", "CELADON_MART_ROOF, 6"),
        ("$07, $08, $17, $18", "$06, $07, $08, $17, $18"),
    ),
)
def test_extra_data_override_anywhere_in_complete_table_fails_closed(
    tmp_path: Path, original: str, replacement: str
) -> None:
    root = _shadow_repository(tmp_path, copied_directories=("data",))
    path = root / "data/tilesets/full_color_interiors.asm"
    source = path.read_text(encoding="utf-8")
    assert original in source
    path.write_text(source.replace(original, replacement, 1), encoding="utf-8")
    with pytest.raises(
        ValueError, match="override identities, data shape, or exact values drifted"
    ):
        production_map_override_rules(root)


def test_override_palette_value_drift_fails_closed(
    tmp_path: Path,
) -> None:
    root = _shadow_repository(tmp_path, copied_directories=("data",))
    path = root / "data/tilesets/full_color_interiors.asm"
    source = path.read_text(encoding="utf-8")
    assert "DEF FULL_COLOR_INTERIOR_BLUE       EQU 3" in source
    path.write_text(
        source.replace(
            "DEF FULL_COLOR_INTERIOR_BLUE       EQU 3",
            "DEF FULL_COLOR_INTERIOR_BLUE       EQU 4",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError, match="override identities, data shape, or exact values drifted"
    ):
        production_map_override_rules(root)


def test_macro_redefinition_changes_all_fresh_products_but_semantics_fail_closed(
    tmp_path: Path,
) -> None:
    root = _shadow_repository(tmp_path, copied_directories=("data",))
    path = root / "data/tilesets/full_color_interiors.asm"
    source = path.read_text(encoding="utf-8")
    marker = "DEF FULL_COLOR_INTERIOR_BLUE       EQU 3"
    assert marker in source
    path.write_text(
        source.replace(
            marker,
            (
                f"{marker}\n"
                "MACRO redefine_override_palette\n"
                "REDEF \\1 EQU \\2\n"
                "ENDM\n"
                "redefine_override_palette FULL_COLOR_INTERIOR_BLUE, 5"
            ),
            1,
        ),
        encoding="utf-8",
    )
    rules = production_map_override_rules(root)
    assert rules[0]["palette_value"] == 3
    authority = MapBackgroundAuthority.load(root)
    with pytest.raises(
        MapBackgroundSnapshotError,
        match="linked map override data contradicts semantic rules or exact values",
    ):
        generate(root)

    isolated_root = snapshot_module._build_products_from_source(
        root, tmp_path / "isolated"
    )

    for product_name in PRODUCTS:
        baseline_symbols = load_sym(ROOT / f"{product_name}.sym")
        mutated_symbols = load_sym(isolated_root / f"{product_name}.sym")
        baseline_symbol = baseline_symbols.by_name["FullColorMapAttributeOverrides"]
        mutated_symbol = mutated_symbols.by_name["FullColorMapAttributeOverrides"]
        baseline = (ROOT / f"{product_name}.gbc").read_bytes()[
            baseline_symbol.rom_offset : baseline_symbol.rom_offset + 15
        ]
        mutated = (isolated_root / f"{product_name}.gbc").read_bytes()[
            mutated_symbol.rom_offset : mutated_symbol.rom_offset + 15
        ]
        differences = [
            (before, after)
            for before, after in zip(baseline, mutated, strict=True)
            if before != after
        ]
        assert differences == [(3, 5)]
        with pytest.raises(
            MapBackgroundSnapshotError,
            match="linked map override data contradicts semantic rules",
        ):
            _product_snapshot(isolated_root, product_name, authority, rules)


def test_promotion_refuses_without_explicit_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "reviewed.json"
    with pytest.raises(SystemExit) as raised:
        main(["--root", str(ROOT), "--output", str(output)])
    assert raised.value.code == 2
    assert "requires --authority-reviewed" in capsys.readouterr().err
    assert not output.exists()


def test_proposal_and_verify_reject_review_acknowledgement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proposal = tmp_path / "proposal.json"
    with pytest.raises(SystemExit):
        main(
            [
                "--root",
                str(ROOT),
                "--proposal-output",
                str(proposal),
                "--authority-reviewed",
            ]
        )
    assert "not used for proposal" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(
            [
                "--root",
                str(ROOT),
                "--verify",
                str(ROOT / MANIFEST_PATH),
                "--authority-reviewed",
            ]
        )
    assert "read-only verification" in capsys.readouterr().err


@pytest.mark.parametrize(
    "relative",
    [
        MANIFEST_PATH,
        Path("specs/full-colors/evidence/../evidence/proposal.json"),
        Path("specs/full-colors/evidence/nested/proposal.json"),
    ],
)
def test_proposal_cannot_write_reviewed_evidence_paths(
    relative: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = (ROOT / MANIFEST_PATH).read_bytes()
    with pytest.raises(SystemExit):
        main(["--root", str(ROOT), "--proposal-output", str(relative)])
    assert "cannot target checked-in reviewed evidence" in capsys.readouterr().err
    assert (ROOT / MANIFEST_PATH).read_bytes() == before


def test_proposal_cannot_reach_reviewed_evidence_through_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    alias = tmp_path / "evidence-alias"
    alias.symlink_to(ROOT / MANIFEST_PATH.parent, target_is_directory=True)
    with pytest.raises(SystemExit):
        main(["--root", str(ROOT), "--proposal-output", str(alias / "proposal.json")])
    assert "cannot target checked-in reviewed evidence" in capsys.readouterr().err


def test_proposal_cannot_reach_reviewed_manifest_through_hardlink(
    capsys: pytest.CaptureFixture[str],
) -> None:
    results = ROOT / "test-results"
    results.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=results) as temporary:
        alias = Path(temporary) / "manifest-alias.json"
        os.link(ROOT / MANIFEST_PATH, alias)
        with pytest.raises(SystemExit):
            main(["--root", str(ROOT), "--proposal-output", str(alias)])
        assert "cannot target checked-in reviewed evidence" in capsys.readouterr().err


@pytest.mark.parametrize("replacement", ["symlink", "hardlink"])
def test_atomic_proposal_replaces_target_raced_after_final_validation(
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
) -> None:
    results = ROOT / "test-results"
    results.mkdir(exist_ok=True)
    temporary = tempfile.TemporaryDirectory(dir=results)
    temporary_path = Path(temporary.name)
    output = temporary_path / "proposal.json"
    reviewed = ROOT / MANIFEST_PATH
    before = reviewed.read_bytes()
    real_replace = os.replace
    candidate = {"schema": "race-regression"}

    monkeypatch.setattr(snapshot_module, "generate", lambda root: candidate)

    def race_then_replace(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
    ) -> None:
        if replacement == "symlink":
            output.symlink_to(reviewed)
        else:
            os.link(reviewed, output)
        real_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(snapshot_module.os, "replace", race_then_replace)
    assert main(["--root", str(ROOT), "--proposal-output", str(output)]) == 0
    assert not output.is_symlink()
    assert output.read_text(encoding="utf-8") == canonical_json(candidate)
    assert reviewed.read_bytes() == before
    assert not list(temporary_path.glob(".*.tmp"))
    temporary.cleanup()


def test_atomic_proposal_fails_closed_if_destination_directory_is_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = tmp_path / "proposals"
    displaced = tmp_path / "displaced"
    directory.mkdir()
    output = directory / "proposal.json"
    reviewed_directory = ROOT / MANIFEST_PATH.parent
    before = (ROOT / MANIFEST_PATH).read_bytes()
    real_replace = os.replace

    monkeypatch.setattr(
        snapshot_module, "generate", lambda root: {"schema": "race-regression"}
    )

    def race_then_replace(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
    ) -> None:
        directory.rename(displaced)
        directory.symlink_to(reviewed_directory, target_is_directory=True)
        real_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(snapshot_module.os, "replace", race_then_replace)
    with pytest.raises(SystemExit):
        main(["--root", str(ROOT), "--proposal-output", str(output)])
    assert "output directory changed during generation" in capsys.readouterr().err
    assert not (displaced / "proposal.json").exists()
    assert not list(displaced.glob(".*.tmp"))
    assert (ROOT / MANIFEST_PATH).read_bytes() == before


def test_atomic_proposal_replaces_preexisting_safe_symlink_without_following_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "unrelated.json"
    target.write_text("unrelated\n", encoding="utf-8")
    output = tmp_path / "proposal.json"
    output.symlink_to(target)
    candidate = {"schema": "safe-symlink-regression"}
    monkeypatch.setattr(snapshot_module, "generate", lambda root: candidate)

    assert main(["--root", str(ROOT), "--proposal-output", str(output)]) == 0
    assert not output.is_symlink()
    assert output.read_text(encoding="utf-8") == canonical_json(candidate)
    assert target.read_text(encoding="utf-8") == "unrelated\n"


def test_reviewed_promotion_refuses_noncanonical_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "reviewed.json"
    with pytest.raises(SystemExit):
        main(
            [
                "--root",
                str(ROOT),
                "--output",
                str(output),
                "--authority-reviewed",
            ]
        )
    assert "must be the canonical reviewed manifest" in capsys.readouterr().err
    assert not output.exists()

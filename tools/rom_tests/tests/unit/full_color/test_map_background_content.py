from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil

import pytest

from tools.rom_tests.full_color import map_background_content
from tools.rom_tests.full_color.map_background_content import (
    ContentStatus,
    FallbackKind,
    MapBackgroundAuthority,
    MapBackgroundContentError,
    Presentation,
    _INCLUDE_DIRECTIVE_RE,
    production_map_override_rules,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
LEDGER = REPOSITORY_ROOT / "specs/full-colors/inventory/map-background-content.json"
REVIEW_DIRECTORY = REPOSITORY_ROOT / "specs/full-colors/evidence/map-background-reviews"
REVIEW_BATCHES = {
    "overworld": (
        "phase3-overworld-pallet-route1-viridian",
        "Codex independent visual review (overworld)",
        1,
        34,
        "69de585dd447e666c638947cdf9c73b0a49ae0ef",
        None,
    ),
    "residential-services": (
        "phase3-residential-bedroom-mart",
        "Codex independent visual review (residential-services)",
        11,
        98,
        "69de585dd447e666c638947cdf9c73b0a49ae0ef",
        None,
    ),
    "challenge-special-interiors": (
        "phase3-challenge-oaks-lab-dojo",
        "Codex independent visual review (challenge-special-interiors)",
        8,
        64,
        "69de585dd447e666c638947cdf9c73b0a49ae0ef",
        None,
    ),
    "forest-cavern": (
        "phase4-forest-cavern-artifact-review",
        "Codex independent visual review (forest-cavern)",
        2,
        24,
        "04c98f0a632d7e0a59ebb83dcd5ef1b6b3452cf5",
        "artifact-only-atlas-and-linked-product-parity",
    ),
    "transport-special": (
        "phase4-transport-special-artifact-review",
        "Codex independent visual review (transport-special)",
        3,
        4,
        "04c98f0a632d7e0a59ebb83dcd5ef1b6b3452cf5",
        "artifact-only-atlas-and-linked-product-parity",
    ),
}


def raw_ledger() -> dict[str, object]:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def parse(raw: dict[str, object]) -> MapBackgroundAuthority:
    return MapBackgroundAuthority.from_dict(raw)


def assert_parse_or_reconciliation_rejects(raw: dict[str, object]) -> None:
    try:
        authority = parse(raw)
    except MapBackgroundContentError:
        return
    assert authority.reconcile(REPOSITORY_ROOT)


def assert_source_reconciliation_rejects(
    authority: MapBackgroundAuthority, source_root: Path, expected: str
) -> None:
    try:
        findings = authority.reconcile(source_root)
    except MapBackgroundContentError:
        return
    assert any(expected in finding for finding in findings)


def copy_map_source_universe(target_root: Path) -> None:
    (target_root / "constants").mkdir()
    (target_root / "data/maps").mkdir(parents=True)
    (target_root / "data/tilesets").mkdir(parents=True)
    (target_root / "engine/full_color").mkdir(parents=True)
    (target_root / "macros").mkdir()
    for match in re.finditer(
        r'^\s*INCLUDE\s+"([^"]+)"',
        (REPOSITORY_ROOT / "includes.asm").read_text(encoding="utf-8"),
        re.MULTILINE,
    ):
        relative = match.group(1)
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative, target)
        if relative == "constants/tileset_constants.asm":
            break
    for relative in (
        "includes.asm",
        "macros/asserts.asm",
        "macros/const.asm",
        "constants/tileset_constants.asm",
        "constants/map_constants.asm",
        "constants/map_data_constants.asm",
        "data/maps/map_header_pointers.asm",
        "data/tilesets/full_color_interiors.asm",
        "data/tilesets/full_color_overworld.asm",
        "data/tilesets/tileset_headers.asm",
        "data/tilesets/cut_tree_blocks.asm",
        "engine/full_color/passive_overworld.asm",
    ):
        target = target_root / relative
        shutil.copy2(REPOSITORY_ROOT / relative, target)
    shutil.copytree(
        REPOSITORY_ROOT / "data/maps/headers",
        target_root / "data/maps/headers",
    )
    shutil.copytree(
        REPOSITORY_ROOT / "specs/full-colors/evidence/map-background-reviews",
        target_root / "specs/full-colors/evidence/map-background-reviews",
    )


def test_reviewed_authority_covers_exact_yellow_map_and_tileset_universe() -> None:
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    assert len(authority.maps) == 224
    assert len(authority.tilesets) == 25
    assert authority.reconcile(REPOSITORY_ROOT) == ()


def test_reviewed_batches_record_content_and_presentation_as_independent_axes() -> None:
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    assert [row.id for row in authority.tilesets] == list(range(25))
    assert {row.content_status for row in authority.tilesets} == {
        ContentStatus.COMPLETE
    }
    assert (
        sum(row.content_status is ContentStatus.MISSING for row in authority.tilesets)
        == 0
    )
    assert (
        sum(row.content_status is ContentStatus.MISSING for row in authority.maps) == 0
    )
    assert (
        sum(row.content_status is ContentStatus.FALLBACK for row in authority.tilesets)
        == 0
    )
    assert (
        sum(row.content_status is ContentStatus.FALLBACK for row in authority.maps) == 0
    )
    assert (
        sum(row.content_status is ContentStatus.COMPLETE for row in authority.tilesets)
        == 25
    )
    assert (
        sum(row.content_status is ContentStatus.COMPLETE for row in authority.maps)
        == 224
    )
    assert sum(row.presentation is Presentation.COLOR for row in authority.maps) == 196
    assert sum(row.presentation is Presentation.YELLOW for row in authority.maps) == 28
    assert all(
        (row.review is not None) == (row.content_status is ContentStatus.COMPLETE)
        for row in (*authority.tilesets, *authority.maps)
    )
    assert {
        row.name
        for row in authority.tilesets
        if row.content_status is ContentStatus.MISSING
    } == set()
    assert not {
        row.name
        for row in authority.tilesets
        if row.content_status is ContentStatus.FALLBACK
    }
    roofs = {row.name: row.roof for row in authority.maps if row.tileset == "OVERWORLD"}
    assert len(roofs) == 34
    assert roofs["PALLET_TOWN"] == "PALLET"
    assert roofs["ROUTE_6"] == "VERMILION"
    overrides = {row.name: row.overrides for row in authority.maps if row.overrides}
    assert overrides == {
        "CELADON_MART_1F": ("CELADON_MART_1F_TILES_07_08_17_18_YELLOW",),
        "CELADON_MART_ROOF": ("CELADON_MART_ROOF_TILES_4B_TO_4F_BLUE",),
    }


def test_exact_accepted_batch_membership_and_review_identity_are_durable() -> None:
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    for batch, (
        route,
        reviewer,
        tileset_count,
        map_count,
        revision,
        purpose,
    ) in REVIEW_BATCHES.items():
        record = json.loads((REVIEW_DIRECTORY / f"{batch}.json").read_text())
        tilesets = [
            {"id": row.id, "name": row.name}
            for row in authority.tilesets
            if row.batch == batch
        ]
        maps = [
            {"id": row.id, "name": row.name, "tileset": row.tileset}
            for row in authority.maps
            if row.batch == batch
        ]
        assert len(tilesets) == tileset_count
        assert len(maps) == map_count
        assert record["content"] == {"tilesets": tilesets, "maps": maps}
        expected_review = {
            "review_kind": "independent-ai-visual",
            "reviewer": reviewer,
            "result": "accepted",
            "revision": revision,
            "route": route,
            "products": [
                {"product": product, "mode": mode}
                for product in ("pokeyellow", "pokeyellow_debug")
                for mode in ("color", "yellow")
            ],
            "observations": record["review"]["observations"],
        }
        if purpose is not None:
            expected_review["purpose"] = purpose
            expected_review["products"] = [
                {"product": product, "claim": "linked-artifact-parity"}
                for product in (
                    "pokeyellow",
                    "pokeyellow_debug",
                    "pokeyellow_vc",
                    "pokeyellow_phase2_audit",
                )
            ]
        assert record["review"] == expected_review
        assert len(record["review"]["observations"]) >= 2
        assert set(record["reviews"]) == {
            *(f"tileset-{row['id']}" for row in tilesets),
            *(f"map-{row['id']}" for row in maps),
        }


def test_review_records_match_current_generated_manifests_and_frames_when_present() -> (
    None
):
    atlas_manifest = (
        REPOSITORY_ROOT / "test-results/full-color-map-background-atlases/manifest.json"
    )
    for batch in ("overworld", "residential-services", "challenge-special-interiors"):
        record = json.loads((REVIEW_DIRECTORY / f"{batch}.json").read_text())
        assert record["atlas"]["manifest_sha256"] == (
            "631a835a67ca568f320dddc25d7557bc6789a99990ce421ee118a9a70907f110"
        )
        assert record["atlas"]["content_sha256"] == (
            "95390973ab3b6bbb31800fcd577bc3791873b0a6501a32536fd75b1881291741"
        )
        if atlas_manifest.is_file():
            assert (
                hashlib.sha256(atlas_manifest.read_bytes()).hexdigest()
                == record["atlas"]["manifest_sha256"]
            )
            generated = json.loads(atlas_manifest.read_text())
            expected = [
                {"path": row["path"], "sha256": row["sha256"]}
                for row in generated["artifacts"]
                if row["path"].startswith(f"{batch}/")
            ]
            assert record["atlas"]["artifacts"] == expected
        for retained in record["retained_artifacts"]:
            manifest_path = REPOSITORY_ROOT / retained["manifest_path"]
            if not manifest_path.is_file():
                continue
            assert (
                hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                == retained["manifest_sha256"]
            )
            manifest = json.loads(manifest_path.read_text())
            expected_frames = [
                {
                    "path": (manifest_path.parent / row["path"])
                    .relative_to(REPOSITORY_ROOT)
                    .as_posix(),
                    "sha256": row["sha256"],
                }
                for row in manifest["artifacts"]
            ]
            assert retained["artifacts"] == expected_frames
            for frame in retained["artifacts"]:
                frame_path = REPOSITORY_ROOT / frame["path"]
                assert (
                    hashlib.sha256(frame_path.read_bytes()).hexdigest()
                    == frame["sha256"]
                )


def test_promoted_sources_make_no_donor_only_authority_claim() -> None:
    sources = "\n".join(
        (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "data/tilesets/full_color_overworld.asm",
            "data/tilesets/full_color_interiors.asm",
        )
    ).lower()
    assert "donor" not in sources
    assert "pokered-gbc" not in sources


def test_production_override_exact_values_are_closed_source_authority(
    tmp_path: Path,
) -> None:
    copy_map_source_universe(tmp_path)
    path = tmp_path / "engine/full_color/passive_overworld.asm"
    source = path.read_text(encoding="utf-8")
    assert "\tcp $4b" in source
    path.write_text(source.replace("\tcp $4b", "\tcp $4c", 1), encoding="utf-8")
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="exact values drifted"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    "statement",
    [
        "REDEF FULL_COLOR_INTERIOR_BLUE EQU 5",
        "rEdEf FULL_COLOR_INTERIOR_YELLOW eQu 5",
        "PURGE FULL_COLOR_INTERIOR_BLUE\nDEF FULL_COLOR_INTERIOR_BLUE EQU 5",
        "pUrGe FULL_COLOR_INTERIOR_YELLOW",
        'DEF FULL_COLOR_INTERIOR_BLUE EQUS "5"',
        "FULL_COLOR_INTERIOR_YELLOW SeT 5",
        "MACRO FULL_COLOR_INTERIOR_BLUE\nENDM",
    ],
)
def test_override_palette_authority_rejects_every_effective_symbol_mutation(
    tmp_path: Path, statement: str
) -> None:
    copy_map_source_universe(tmp_path)
    path = tmp_path / "data/tilesets/full_color_interiors.asm"
    source = path.read_text(encoding="utf-8")
    marker = "DEF FULL_COLOR_INTERIOR_YELLOW     EQU 4"
    assert marker in source
    path.write_text(
        source.replace(marker, f"{marker}\n{statement}", 1), encoding="utf-8"
    )

    with pytest.raises(MapBackgroundContentError, match="non-authoritative"):
        MapBackgroundAuthority.load(REPOSITORY_ROOT).reconcile(tmp_path)


def test_override_palette_authority_folds_directives_but_not_symbol_case(
    tmp_path: Path,
) -> None:
    copy_map_source_universe(tmp_path)
    path = tmp_path / "data/tilesets/full_color_interiors.asm"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "DEF FULL_COLOR_INTERIOR_BLUE       EQU 3",
        "dEf FULL_COLOR_INTERIOR_BLUE       eQu 3",
        1,
    )
    source += "\nREDEF full_color_interior_blue EQU 5\n"
    path.write_text(source, encoding="utf-8")

    rules = production_map_override_rules(tmp_path)
    assert rules[0]["palette_value"] == 3


@pytest.mark.parametrize(
    "wrapper",
    [
        "IF 1\n{definition}\nENDC",
        "MACRO define_override_blue\n{definition}\nENDM\ndefine_override_blue",
    ],
)
def test_override_palette_authority_must_be_an_unconditional_top_level_definition(
    tmp_path: Path, wrapper: str
) -> None:
    copy_map_source_universe(tmp_path)
    path = tmp_path / "data/tilesets/full_color_interiors.asm"
    source = path.read_text(encoding="utf-8")
    definition = "DEF FULL_COLOR_INTERIOR_BLUE       EQU 3"
    assert definition in source
    path.write_text(
        source.replace(definition, wrapper.format(definition=definition), 1),
        encoding="utf-8",
    )

    with pytest.raises(MapBackgroundContentError, match="non-authoritative"):
        production_map_override_rules(tmp_path)


def test_every_map_has_the_exact_recorded_tileset_status_and_fallback_contract() -> (
    None
):
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    statuses = {row.name: row.content_status for row in authority.tilesets}
    for row in authority.maps:
        assert row.content_status is statuses[row.tileset]
        if row.content_status is ContentStatus.MISSING:
            assert row.presentation is Presentation.YELLOW
            assert row.fallback_reason is not None
            assert row.fallback_reason.kind is FallbackKind.CONTENT_MISSING
        elif row.content_status is ContentStatus.FALLBACK:
            assert row.presentation is Presentation.YELLOW
            assert row.fallback_reason is not None
            assert row.fallback_reason.kind is FallbackKind.ARCHITECTURE_BOUNDARY
            assert row.review is None
        else:
            if row.presentation is Presentation.YELLOW:
                assert row.fallback_reason is not None
                assert row.fallback_reason.kind is FallbackKind.ARCHITECTURE_BOUNDARY
            else:
                assert row.presentation is Presentation.COLOR
                assert row.fallback_reason is None
            assert row.review is not None


def test_forest_cavern_candidates_cover_exact_maps_and_water_animation() -> None:
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    expected = {
        "FOREST": {
            "SAFARI_ZONE_CENTER",
            "SAFARI_ZONE_EAST",
            "SAFARI_ZONE_NORTH",
            "SAFARI_ZONE_WEST",
            "VIRIDIAN_FOREST",
        },
        "CAVERN": {
            "CERULEAN_CAVE_1F",
            "CERULEAN_CAVE_2F",
            "CERULEAN_CAVE_B1F",
            "DIGLETTS_CAVE",
            "DIGLETTS_CAVE_ROUTE_11",
            "DIGLETTS_CAVE_ROUTE_2",
            "MT_MOON_1F",
            "MT_MOON_B1F",
            "MT_MOON_B2F",
            "ROCK_TUNNEL_1F",
            "ROCK_TUNNEL_B1F",
            "SEAFOAM_ISLANDS_1F",
            "SEAFOAM_ISLANDS_B1F",
            "SEAFOAM_ISLANDS_B2F",
            "SEAFOAM_ISLANDS_B3F",
            "SEAFOAM_ISLANDS_B4F",
            "VICTORY_ROAD_1F",
            "VICTORY_ROAD_2F",
            "VICTORY_ROAD_3F",
        },
    }
    for tileset, map_names in expected.items():
        tileset_row = next(row for row in authority.tilesets if row.name == tileset)
        assert tileset_row.content_status is ContentStatus.COMPLETE
        assert tileset_row.review is not None
        assert tileset_row.animations == ("TILEANIM_WATER",)
        rows = {row.name: row for row in authority.maps if row.tileset == tileset}
        assert set(rows) == map_names
        assert all(
            row.content_status is ContentStatus.COMPLETE for row in rows.values()
        )
        assert all(row.animations == ("TILEANIM_WATER",) for row in rows.values())
        assert all(row.presentation is Presentation.YELLOW for row in rows.values())
        assert all(row.review is not None for row in rows.values())


def test_transport_special_candidates_cover_exact_maps_and_semantics() -> None:
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    expected = {
        "SHIP_PORT": ({"VERMILION_DOCK"}, ("TILEANIM_WATER",)),
        "PLATEAU": ({"INDIGO_PLATEAU", "ROUTE_23"}, ("TILEANIM_WATER",)),
        "BEACH_HOUSE": ({"SUMMER_BEACH_HOUSE"}, ()),
    }
    for tileset, (map_names, animations) in expected.items():
        tileset_row = next(row for row in authority.tilesets if row.name == tileset)
        assert tileset_row.content_status is ContentStatus.COMPLETE
        assert tileset_row.animations == animations
        assert tileset_row.review is not None
        rows = {row.name: row for row in authority.maps if row.tileset == tileset}
        assert set(rows) == map_names
        assert all(
            row.content_status is ContentStatus.COMPLETE for row in rows.values()
        )
        assert all(row.animations == animations for row in rows.values())
        assert all(row.presentation is Presentation.YELLOW for row in rows.values())
        assert all(row.review is not None for row in rows.values())


def test_all_source_declared_tileset_animations_are_closed_in_the_ledger() -> None:
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    expected = {
        "OVERWORLD": ("TILEANIM_WATER_FLOWER",),
        "FOREST": ("TILEANIM_WATER",),
        "DOJO": ("TILEANIM_WATER_FLOWER",),
        "GYM": ("TILEANIM_WATER_FLOWER",),
        "SHIP": ("TILEANIM_WATER",),
        "SHIP_PORT": ("TILEANIM_WATER",),
        "CAVERN": ("TILEANIM_WATER",),
        "FACILITY": ("TILEANIM_WATER",),
        "PLATEAU": ("TILEANIM_WATER",),
    }
    assert {
        row.name: row.animations for row in authority.tilesets if row.animations
    } == expected
    assert all(
        row.animations == expected.get(row.tileset, ()) for row in authority.maps
    )


@pytest.mark.parametrize("tileset", ["DOJO", "GYM", "SHIP", "FACILITY"])
def test_newly_closed_animation_ledger_rows_are_mutation_sensitive(
    tileset: str,
) -> None:
    raw = raw_ledger()
    tileset_row = next(row for row in raw["tilesets"] if row["name"] == tileset)
    tileset_row["animations"] = []
    map_row = next(row for row in raw["maps"] if row["tileset"] == tileset)
    map_row["animations"] = []
    assert_parse_or_reconciliation_rejects(raw)


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "duplicate", "reordered", "drifted"]
)
def test_tileset_identity_mutations_fail_closed(mutation: str) -> None:
    raw = raw_ledger()
    rows = raw["tilesets"]
    assert isinstance(rows, list)
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append(deepcopy(rows[-1]))
        rows[-1]["id"] = 25
        rows[-1]["name"] = "EXTRA_TILESET"
    elif mutation == "duplicate":
        rows[1] = deepcopy(rows[0])
    elif mutation == "reordered":
        rows[0], rows[1] = rows[1], rows[0]
    else:
        rows[0]["name"] = "DRIFTED_OVERWORLD"
    assert_parse_or_reconciliation_rejects(raw)


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "duplicate", "reordered", "drifted"]
)
def test_map_identity_mutations_fail_closed(mutation: str) -> None:
    raw = raw_ledger()
    rows = raw["maps"]
    assert isinstance(rows, list)
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append(deepcopy(rows[-1]))
        rows[-1]["id"] = 999
        rows[-1]["name"] = "ZZZ_EXTRA_MAP"
    elif mutation == "duplicate":
        rows[1] = deepcopy(rows[0])
    elif mutation == "reordered":
        rows[0], rows[1] = rows[1], rows[0]
    else:
        rows[0]["name"] = "AAA_DRIFTED_MAP"
    assert_parse_or_reconciliation_rejects(raw)


def test_map_to_tileset_and_status_mismatches_fail_reconciliation() -> None:
    for field, value in (("tileset", "GYM"), ("content_status", "missing")):
        raw = raw_ledger()
        rows = raw["maps"]
        assert isinstance(rows, list)
        rows[0][field] = value
        if field == "content_status":
            with pytest.raises(MapBackgroundContentError, match="reviewed authority"):
                parse(raw)
        else:
            assert parse(raw).reconcile(REPOSITORY_ROOT)


def test_source_identity_and_map_to_tileset_drift_fail_reconciliation(
    tmp_path: Path,
) -> None:
    copy_map_source_universe(tmp_path)
    header = tmp_path / "data/maps/headers/PalletTown.asm"
    header.write_text(
        header.read_text(encoding="utf-8").replace("OVERWORLD", "GYM", 1),
        encoding="utf-8",
    )
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    assert authority.reconcile(tmp_path) == (
        "map identities/order/tileset joins drift from the concrete source universe",
    )


def test_annotated_same_tileset_map_header_pointer_swap_fails_closed(
    tmp_path: Path,
) -> None:
    copy_map_source_universe(tmp_path)
    pointers = tmp_path / "data/maps/map_header_pointers.asm"
    source = pointers.read_text(encoding="utf-8")
    source = source.replace("dw PalletTown_h", "dw SWAPPED_PALLET_h", 1)
    source = source.replace("dw ViridianCity_h", "dw PalletTown_h ; VIRIDIAN_CITY", 1)
    source = source.replace("dw SWAPPED_PALLET_h", "dw ViridianCity_h ; PALLET_TOWN", 1)
    pointers.write_text(source, encoding="utf-8")

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="positional map constant"):
        authority.reconcile(tmp_path)


def test_map_header_declared_constant_drift_fails_closed(tmp_path: Path) -> None:
    copy_map_source_universe(tmp_path)
    header = tmp_path / "data/maps/headers/PalletTown.asm"
    header.write_text(
        header.read_text(encoding="utf-8").replace(
            "PalletTown, PALLET_TOWN,", "PalletTown, VIRIDIAN_CITY,", 1
        ),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="declaring VIRIDIAN_CITY"):
        authority.reconcile(tmp_path)


def test_only_exact_route_7_copy_header_compatibility_is_accepted(
    tmp_path: Path,
) -> None:
    copy_map_source_universe(tmp_path)
    header = tmp_path / "data/maps/headers/UndergroundPathRoute7Copy.asm"
    header.write_text(
        header.read_text(encoding="utf-8").replace(
            "UNDERGROUND_PATH_ROUTE_7,", "UNDERGROUND_PATH_ROUTE_6,", 1
        ),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="declaring"):
        authority.reconcile(tmp_path)


def test_pointer_annotations_are_exact_and_identity_bound(tmp_path: Path) -> None:
    cases = (
        (
            "dw UndergroundPathRoute7Copy_h",
            "dw UndergroundPathRoute7Copy_h ; UNDERGROUND_PATH_ROUTE_7_COPY",
            "positional map constant",
        ),
        (
            "dw UndergroundPathRoute7Copy_h",
            "dw UndergroundPathRoute7Copy_h ; lowercase_annotation",
            "malformed map header pointer",
        ),
        (
            "dw UndergroundPathRoute7Copy_h",
            "dw UndergroundPathRoute7Copy_h ; 78",
            "malformed map header pointer",
        ),
        (
            "dw UndergroundPathRoute7Copy_h",
            "dw UndergroundPathRoute7Copy_h ; UNDERGROUND_PATH_ROUTE_7_COPY trailing",
            "malformed map header pointer",
        ),
        (
            "dw LancesRoom_h ; UNUSED_MAP_69",
            "dw LancesRoom_h ; UNUSED_MAP_69 trailing",
            "malformed map header pointer",
        ),
        (
            "dw LancesRoom_h ; UNUSED_MAP_69",
            "dw LancesRoom_h ; UNUSED_MAP_69 ; forged",
            "malformed map header pointer",
        ),
    )
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    for index, (original, replacement, expected) in enumerate(cases):
        source_root = tmp_path / str(index)
        source_root.mkdir()
        copy_map_source_universe(source_root)
        pointers = source_root / "data/maps/map_header_pointers.asm"
        source = pointers.read_text(encoding="utf-8")
        assert original in source
        pointers.write_text(source.replace(original, replacement, 1), encoding="utf-8")

        with pytest.raises(MapBackgroundContentError, match=expected):
            authority.reconcile(source_root)


@pytest.mark.parametrize(
    "statement",
    [
        "db 0",
        "ForgedMapHeaderPointers:",
        'INCLUDE "data/maps/forged.asm"',
        "forged_pointer_macro PalletTown_h",
    ],
)
def test_map_header_pointer_table_rejects_non_pointer_content(
    tmp_path: Path, statement: str
) -> None:
    copy_map_source_universe(tmp_path)
    pointers = tmp_path / "data/maps/map_header_pointers.asm"
    source = pointers.read_text(encoding="utf-8")
    pointers.write_text(
        source.replace("\tdw PalletTown_h", f"\t{statement}\n\tdw PalletTown_h", 1),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="unauthorized"):
        authority.reconcile(tmp_path)


def test_map_header_pointer_table_rejects_trailing_pointer_tokens(
    tmp_path: Path,
) -> None:
    copy_map_source_universe(tmp_path)
    pointers = tmp_path / "data/maps/map_header_pointers.asm"
    source = pointers.read_text(encoding="utf-8")
    pointers.write_text(
        source.replace("dw PalletTown_h", "dw PalletTown_h trailing", 1),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="malformed map header pointer"):
        authority.reconcile(tmp_path)


def test_duplicate_alias_target_is_bound_to_exact_historical_slot(
    tmp_path: Path,
) -> None:
    copy_map_source_universe(tmp_path)
    pointers = tmp_path / "data/maps/map_header_pointers.asm"
    source = pointers.read_text(encoding="utf-8")
    pointers.write_text(
        source.replace(
            "dw LancesRoom_h ; UNUSED_MAP_6A",
            "dw PalletTown_h ; UNUSED_MAP_6A",
            1,
        ),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="exact historical"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("constants/tileset_constants.asm", "tileset identities/order drift"),
        ("constants/map_constants.asm", "map identities/order/tileset joins drift"),
    ],
)
def test_nonzero_const_def_bases_fail_closed(
    tmp_path: Path, relative: str, expected: str
) -> None:
    copy_map_source_universe(tmp_path)
    constants = tmp_path / relative
    constants.write_text(
        constants.read_text(encoding="utf-8").replace(
            "\tconst_def", "\tconst_def 1", 1
        ),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    assert_source_reconciliation_rejects(authority, tmp_path, expected)


@pytest.mark.parametrize(
    "relative",
    ["constants/tileset_constants.asm", "constants/map_constants.asm"],
)
def test_const_def_rejects_empty_base_with_increment(
    tmp_path: Path, relative: str
) -> None:
    copy_map_source_universe(tmp_path)
    constants = tmp_path / relative
    constants.write_text(
        constants.read_text(encoding="utf-8").replace(
            "\tconst_def\n", "\tconst_def , 1\n", 1
        ),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="exactly one const_def"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    "relative",
    ["constants/tileset_constants.asm", "constants/map_constants.asm"],
)
def test_const_def_accepts_explicit_base_and_increment(
    tmp_path: Path, relative: str
) -> None:
    copy_map_source_universe(tmp_path)
    includes = tmp_path / "includes.asm"
    includes.write_text(
        includes.read_text(encoding="utf-8").replace(
            'INCLUDE "macros/asserts.asm"', 'iNcLuDe "macros/asserts.asm"', 1
        ),
        encoding="utf-8",
    )
    macros = tmp_path / "macros/const.asm"
    macros.write_text(
        macros.read_text(encoding="utf-8").replace(
            "MACRO? const\n\tDEF \\1 EQU const_value\n"
            "\tDEF const_value += const_inc\nENDM",
            "mAcRo? const\n\tdEf \\1 eQu const_value\n"
            "\tdEf const_value += const_inc\neNdM",
            1,
        ),
        encoding="utf-8",
    )
    map_constants = tmp_path / "constants/map_constants.asm"
    map_constants.write_text(
        map_constants.read_text(encoding="utf-8")
        .replace("MACRO map_const", "mAcRo map_const", 1)
        .replace("\tDEF \\1_WIDTH EQU \\2", "\tdEf \\1_WIDTH eQu \\2", 1)
        .replace("\tDEF \\1_HEIGHT EQU \\3", "\tdEf \\1_HEIGHT eQu \\3", 1)
        .replace("ENDM", "eNdM", 1)
        .replace(
            "DEF NUM_INDOOR_MAP_GROUPS EQU 0", "dEf NUM_INDOOR_MAP_GROUPS eQu 0", 1
        )
        .replace(
            "\tREDEF NUM_INDOOR_MAP_GROUPS EQU NUM_INDOOR_MAP_GROUPS + 1",
            "\trEdEf NUM_INDOOR_MAP_GROUPS eQu NUM_INDOOR_MAP_GROUPS + 1",
            1,
        ),
        encoding="utf-8",
    )
    constants = tmp_path / relative
    constants.write_text(
        constants.read_text(encoding="utf-8").replace(
            "\tconst_def\n", "\tconst_def 0, 1\n", 1
        ),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    assert authority.reconcile(tmp_path) == ()


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        ("\tconst \\1", "\tDEF \\1 EQU const_value + 1\n\tconst_skip"),
        ("\tDEF \\1_WIDTH EQU \\2", "\tDEF \\1_WIDTH EQU \\2 + 1"),
        ("\tDEF \\1_HEIGHT EQU \\3", "\tDEF \\1_HEIGHT EQU \\3\n\tdb 0"),
        ("\tconst \\1\n", ""),
    ],
)
def test_map_const_macro_definition_drift_fails_closed(
    tmp_path: Path, original: str, replacement: str
) -> None:
    copy_map_source_universe(tmp_path)
    constants = tmp_path / "constants/map_constants.asm"
    source = constants.read_text(encoding="utf-8")
    assert original in source
    constants.write_text(source.replace(original, replacement, 1), encoding="utf-8")

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="map_const macro"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        (
            "\tDEF INDOORGROUP_\\1 EQU const_value",
            "\tconst_skip\n\tDEF INDOORGROUP_\\1 EQU const_value",
        ),
        (
            "\tDEF INDOORGROUP_\\1 EQU const_value",
            "\tconst_next 250\n\tDEF INDOORGROUP_\\1 EQU const_value",
        ),
        (
            "\tDEF INDOORGROUP_\\1 EQU const_value",
            "\tDEF FORGED_INDOOR_GROUP EQU const_value\n"
            "\tDEF INDOORGROUP_\\1 EQU const_value",
        ),
        (
            "\tREDEF NUM_INDOOR_MAP_GROUPS EQU NUM_INDOOR_MAP_GROUPS + 1",
            "\tDEF NUM_INDOOR_MAP_GROUPS EQU NUM_INDOOR_MAP_GROUPS + 1",
        ),
        (
            "\tREDEF NUM_INDOOR_MAP_GROUPS EQU NUM_INDOOR_MAP_GROUPS + 1",
            "\tdb 0\n\tREDEF NUM_INDOOR_MAP_GROUPS EQU NUM_INDOOR_MAP_GROUPS + 1",
        ),
        ("\tDEF INDOORGROUP_\\1 EQU const_value\n", ""),
        (
            "DEF NUM_INDOOR_MAP_GROUPS EQU 0",
            "REDEF NUM_INDOOR_MAP_GROUPS EQU 0",
        ),
        (
            "DEF NUM_INDOOR_MAP_GROUPS EQU 0",
            "DEF NUM_INDOOR_MAP_GROUPS EQU 1",
        ),
    ],
)
def test_end_indoor_group_macro_authority_drift_fails_closed(
    tmp_path: Path, original: str, replacement: str
) -> None:
    copy_map_source_universe(tmp_path)
    constants = tmp_path / "constants/map_constants.asm"
    source = constants.read_text(encoding="utf-8")
    assert original in source
    constants.write_text(source.replace(original, replacement, 1), encoding="utf-8")

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="end_indoor_group macro"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("constants/tileset_constants.asm", "tileset identities/order drift"),
        ("constants/map_constants.asm", "map identities/order/tileset joins drift"),
    ],
)
def test_const_skip_changes_positional_identity_in_both_authorities(
    tmp_path: Path, relative: str, expected: str
) -> None:
    copy_map_source_universe(tmp_path)
    constants = tmp_path / relative
    constants.write_text(
        constants.read_text(encoding="utf-8").replace(
            "\tconst_def\n", "\tconst_def\n\tconst_skip\n", 1
        ),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    assert_source_reconciliation_rejects(authority, tmp_path, expected)


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("constants/tileset_constants.asm", "tileset identities/order drift"),
        ("constants/map_constants.asm", "map identities/order/tileset joins drift"),
    ],
)
def test_const_next_changes_positional_identity_in_both_authorities(
    tmp_path: Path, relative: str, expected: str
) -> None:
    copy_map_source_universe(tmp_path)
    constants = tmp_path / relative
    constants.write_text(
        constants.read_text(encoding="utf-8").replace(
            "\tconst_def\n", "\tconst_def\n\tconst_next 1\n", 1
        ),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    assert_source_reconciliation_rejects(authority, tmp_path, expected)


@pytest.mark.parametrize(
    "relative",
    ["constants/tileset_constants.asm", "constants/map_constants.asm"],
)
@pytest.mark.parametrize(
    "statement",
    [
        "DEF const_value += 1",
        "REDEF const_value EQU const_value + 1",
        "db $00",
    ],
)
def test_unknown_executable_statements_in_positional_authorities_fail_closed(
    tmp_path: Path, relative: str, statement: str
) -> None:
    copy_map_source_universe(tmp_path)
    constants = tmp_path / relative
    constants.write_text(
        constants.read_text(encoding="utf-8").replace(
            "\tconst_def\n", f"\tconst_def\n\t{statement}\n", 1
        ),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(
        MapBackgroundContentError, match="unsupported positional constant statement"
    ):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        ("DEF const_value += const_inc", "DEF const_value += const_inc * 2"),
        ("DEF const_value += const_inc", "DEF const_value += 1"),
        (
            "DEF const_value += const_inc * (\\1)",
            "DEF const_value += (\\1)",
        ),
        ("DEF const_value = \\1", "DEF const_value = \\1 + const_inc"),
        ("MACRO? const_skip", "MACRO const_skip"),
        ("MACRO? const_next", "MACRO? const_next\n\tdb 0"),
    ],
)
def test_const_macro_semantic_drift_fails_closed(
    tmp_path: Path, original: str, replacement: str
) -> None:
    copy_map_source_universe(tmp_path)
    macros = tmp_path / "macros/const.asm"
    source = macros.read_text(encoding="utf-8")
    assert original in source
    macros.write_text(source.replace(original, replacement, 1), encoding="utf-8")

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="macro authority"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "remove",
        "move-after-map-constants",
        "duplicate",
    ],
)
def test_const_macro_preinclude_dependency_drift_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    copy_map_source_universe(tmp_path)
    includes = tmp_path / "includes.asm"
    source = includes.read_text(encoding="utf-8")
    macro_line = 'INCLUDE "macros/const.asm"\n'
    map_line = 'INCLUDE "constants/map_constants.asm"\n'
    assert macro_line in source and map_line in source
    if mutation == "remove":
        source = source.replace(macro_line, "", 1)
    elif mutation == "duplicate":
        source = source.replace(macro_line, macro_line * 2, 1)
    else:
        source = source.replace(macro_line, "", 1).replace(
            map_line, map_line + macro_line, 1
        )
    includes.write_text(source, encoding="utf-8")

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="dependency/order drifted"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    ("relative", "addition", "expected"),
    [
        ("macros/const.asm", "PURGE const\n", "top-level executable"),
        (
            "macros/asserts.asm",
            "mAcRo const\n\tdEf \\1 eQu 0\neNdM\n",
            "may not shadow",
        ),
        (
            "macros/asserts.asm",
            'iNcLuDe "macros/forged_const.asm"\n',
            "may not shadow",
        ),
    ],
)
def test_const_preinclude_shadowing_and_top_level_execution_fail_closed(
    tmp_path: Path, relative: str, addition: str, expected: str
) -> None:
    copy_map_source_universe(tmp_path)
    path = tmp_path / relative
    path.write_text(addition + path.read_text(encoding="utf-8"), encoding="utf-8")

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match=expected):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    ("relative", "addition", "case_distinct_addition"),
    [
        ("includes.asm", "pUrGe const\n", "pUrGe CONST\n"),
        ("macros/predef.asm", "purge const\n", "purge CONST\n"),
        (
            "macros/farcall.asm",
            "mAcRo? const_skip\neNdM\n",
            "mAcRo? CONST_SKIP\neNdM\n",
        ),
        (
            "constants/misc_constants.asm",
            "rEdEf const_inc eQu 2\n",
            "rEdEf CONST_INC eQu 2\n",
        ),
        (
            "constants/map_data_constants.asm",
            "dEf const_value eQu 0\n",
            "dEf CONST_VALUE eQu 0\n",
        ),
    ],
)
def test_intervening_effective_include_cannot_replace_const_authority(
    tmp_path: Path, relative: str, addition: str, case_distinct_addition: str
) -> None:
    copy_map_source_universe(tmp_path)
    path = tmp_path / relative
    original = path.read_text(encoding="utf-8")
    path.write_text(original + addition, encoding="utf-8")

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="positional authority"):
        authority.reconcile(tmp_path)

    path.write_text(original + case_distinct_addition, encoding="utf-8")
    assert authority.reconcile(tmp_path) == ()


def test_dynamic_effective_include_cannot_hide_const_redefinition(
    tmp_path: Path,
) -> None:
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    for index, label in enumerate((".local:", ".local::", ".0:", ".0::")):
        source_root = tmp_path / str(index)
        source_root.mkdir()
        copy_map_source_universe(source_root)
        hidden = source_root / "macros/hidden_const.asm"
        hidden.write_text(
            "PURGE const\n"
            "MACRO const\n"
            "\tDEF \\1 EQU const_value\n"
            "\tDEF const_value += const_inc + 1\n"
            "ENDM\n",
            encoding="utf-8",
        )
        dependency = source_root / "macros/predef.asm"
        dependency.write_text(
            dependency.read_text(encoding="utf-8")
            + 'DEF hidden_path EQUS "\\"macros/hidden_const.asm\\""\n'
            + f"{label} iNcLuDe hidden_path\n",
            encoding="utf-8",
        )

        with pytest.raises(
            MapBackgroundContentError, match="exactly one quoted literal"
        ):
            authority.reconcile(source_root)


def test_local_label_prefixed_literal_include_cannot_hide_const_redefinition(
    tmp_path: Path,
) -> None:
    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    for index, include in enumerate(
        (
            '.local: INCLUDE "macros/hidden_const.asm"',
            '.local:: include "macros/hidden_const.asm"',
            '.0: iNcLuDe "macros/hidden_const.asm"',
            '.0:: InClUdE "macros/hidden_const.asm"',
        )
    ):
        source_root = tmp_path / str(index)
        source_root.mkdir()
        copy_map_source_universe(source_root)
        hidden = source_root / "macros/hidden_const.asm"
        hidden.write_text(
            "PURGE const\n"
            "MACRO const\n"
            "\tDEF \\1 EQU const_value\n"
            "\tDEF const_value += const_inc + 1\n"
            "ENDM\n",
            encoding="utf-8",
        )
        dependency = source_root / "macros/predef.asm"
        dependency.write_text(
            dependency.read_text(encoding="utf-8") + include + "\n",
            encoding="utf-8",
        )

        with pytest.raises(
            MapBackgroundContentError, match="exactly one quoted literal"
        ):
            authority.reconcile(source_root)


@pytest.mark.parametrize(
    "include",
    [
        'HiddenLoader INCLUDE "macros/hidden_const.asm"',
        'HiddenLoader iNcLuDe "macros/hidden_const.asm"',
    ],
)
def test_unsupported_bare_symbol_prefixed_include_cannot_hide_const_redefinition(
    tmp_path: Path, include: str
) -> None:
    copy_map_source_universe(tmp_path)
    hidden = tmp_path / "macros/hidden_const.asm"
    hidden.write_text(
        "PURGE const\n"
        "MACRO const\n"
        "\tDEF \\1 EQU const_value\n"
        "\tDEF const_value += const_inc + 1\n"
        "ENDM\n",
        encoding="utf-8",
    )
    dependency = tmp_path / "macros/predef.asm"
    dependency.write_text(
        dependency.read_text(encoding="utf-8") + include + "\n",
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="exactly one quoted literal"):
        authority.reconcile(tmp_path)


def test_effective_include_prefix_detection_is_exact() -> None:
    detected_prefixes = (
        'HiddenLoader INCLUDE "dependency.asm"',
        'ExportedInclude:: INCLUDE "dependency.asm"',
        'Root.local INCLUDE "dependency.asm"',
        'Root.local: Include "dependency.asm"',
        'Root.local:: include "dependency.asm"',
        'Root.0 InClUdE "dependency.asm"',
        'Root.0: INCLUDE "dependency.asm"',
        'Root.0:: iNcLuDe "dependency.asm"',
        '.local INCLUDE "dependency.asm"',
        '.local: INCLUDE "dependency.asm"',
        '.local:: include "dependency.asm"',
        '.0 InClUdE "dependency.asm"',
        '.0: iNcLuDe "dependency.asm"',
        '.0:: InClUdE "dependency.asm"',
        ': INCLUDE "dependency.asm"',
    )
    for source in detected_prefixes:
        assert _INCLUDE_DIRECTIVE_RE.match(source) is not None

    ordinary_identifiers = (
        'HiddenLoaderINCLUDE "dependency.asm"',
        'INCLUDE_PATH EQU "dependency.asm"',
        '\tOrdinaryIdentifier INCLUDE "dependency.asm"',
    )
    for source in ordinary_identifiers:
        assert _INCLUDE_DIRECTIVE_RE.match(source) is None


def test_top_level_effective_dynamic_include_fails_closed(tmp_path: Path) -> None:
    copy_map_source_universe(tmp_path)
    includes = tmp_path / "includes.asm"
    source = includes.read_text(encoding="utf-8")
    map_include = 'INCLUDE "constants/map_constants.asm"\n'
    assert map_include in source
    includes.write_text(
        source.replace(
            map_include,
            'DEF hidden_path EQUS "\\"macros/hidden_const.asm\\""\n'
            "iNcLuDe hidden_path\n" + map_include,
            1,
        ),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="exactly one quoted literal"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    "include",
    [
        'iNcLuDe "macros/hidden_const.asm" + ""',
        'InClUdE "macros/hidden_const.asm" hidden_path',
        'include STRCAT("macros/", "hidden_const.asm")',
        'IncludeSite: iNcLuDe "macros/hidden_const.asm"',
        ':iNcLuDe "macros/hidden_const.asm"',
        'ExportedInclude:: Include "macros/hidden_const.asm"',
        'Root.local: INCLUDE "macros/hidden_const.asm"',
        '.local include "macros/hidden_const.asm"',
        'Root.local InClUdE "macros/hidden_const.asm"',
        '#INCLUDE: Include "macros/hidden_const.asm"',
    ],
)
def test_effective_include_rejects_expressions_and_extra_tokens(
    tmp_path: Path, include: str
) -> None:
    copy_map_source_universe(tmp_path)
    dependency = tmp_path / "macros/predef.asm"
    dependency.write_text(
        dependency.read_text(encoding="utf-8") + include + "\n",
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="exactly one quoted literal"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    "commented_include",
    [
        '; : INCLUDE "macros/hidden_const.asm"',
        ': ; INCLUDE "macros/hidden_const.asm"',
        'CommentOnly: ; iNcLuDe "macros/hidden_const.asm"',
    ],
)
def test_commented_label_prefixed_include_is_not_effective(
    tmp_path: Path, commented_include: str
) -> None:
    copy_map_source_universe(tmp_path)
    dependency = tmp_path / "macros/predef.asm"
    dependency.write_text(
        dependency.read_text(encoding="utf-8") + commented_include + "\n",
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    assert authority.reconcile(tmp_path) == ()


@pytest.mark.parametrize("include_path", ["/tmp/outside.asm", "../outside.asm"])
def test_effective_include_dependencies_reject_non_repo_relative_paths(
    tmp_path: Path, include_path: str
) -> None:
    copy_map_source_universe(tmp_path)
    dependency = tmp_path / "macros/predef.asm"
    dependency.write_text(
        dependency.read_text(encoding="utf-8") + f'iNcLuDe "{include_path}"\n',
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="repo-root-contained"):
        authority.reconcile(tmp_path)


def test_effective_include_dependencies_reject_symlink_escape(tmp_path: Path) -> None:
    copy_map_source_universe(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.asm"
    outside.write_text("", encoding="utf-8")
    escape = tmp_path / "macros/outside.asm"
    escape.symlink_to(outside)
    dependency = tmp_path / "macros/predef.asm"
    dependency.write_text(
        dependency.read_text(encoding="utf-8") + 'iNcLuDe "macros/outside.asm"\n',
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="outside repository root"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    ("compatibility_id", "marker"),
    [
        (78, "\tmap_const UNDERGROUND_PATH_ROUTE_7_COPY,"),
        (105, "\tmap_const UNUSED_MAP_69,"),
    ],
)
def test_compatibility_exceptions_are_bound_to_exact_numeric_ids(
    tmp_path: Path, compatibility_id: int, marker: str
) -> None:
    copy_map_source_universe(tmp_path)
    constants = tmp_path / "constants/map_constants.asm"
    source = constants.read_text(encoding="utf-8")
    assert marker in source
    constants.write_text(
        source.replace(marker, f"\tconst_skip\n{marker}", 1), encoding="utf-8"
    )
    raw = raw_ledger()
    rows = raw["maps"]
    assert isinstance(rows, list)
    for row in rows:
        if row["id"] >= compatibility_id:
            row["id"] += 1

    authority = parse(raw)
    with pytest.raises(MapBackgroundContentError, match="positional map constant"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize("depth", ["top-level", "nested"])
def test_json_loader_rejects_duplicate_object_keys_at_every_depth(
    tmp_path: Path, depth: str
) -> None:
    source = LEDGER.read_text(encoding="utf-8")
    if depth == "top-level":
        source = source.replace(
            '{\n  "schema":',
            '{\n  "schema": "full-color-map-background-content-v1",\n  "schema":',
            1,
        )
    else:
        source = source.replace('"id": 0,', '"id": 0,\n      "id": 0,', 1)
    path = tmp_path / "duplicate.json"
    path.write_text(source, encoding="utf-8")

    with pytest.raises(MapBackgroundContentError, match="duplicate JSON object key"):
        MapBackgroundAuthority.load(REPOSITORY_ROOT, path)


@pytest.mark.parametrize(
    ("relative", "terminal"),
    [
        ("constants/tileset_constants.asm", "NUM_TILESETS"),
        ("constants/map_constants.asm", "NUM_MAPS"),
    ],
)
def test_executable_statement_after_positional_terminal_fails_closed(
    tmp_path: Path, relative: str, terminal: str
) -> None:
    copy_map_source_universe(tmp_path)
    constants = tmp_path / relative
    source = constants.read_text(encoding="utf-8")
    marker = f"DEF {terminal} EQU const_value"
    assert marker in source
    constants.write_text(
        source.replace(marker, f"{marker}\nconst FORGED_AFTER_TERMINAL", 1),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match="after .* terminal|after NUM"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    ("relative", "terminal"),
    [
        ("constants/tileset_constants.asm", "NUM_TILESETS"),
        ("constants/map_constants.asm", "NUM_MAPS"),
    ],
)
def test_redef_positional_terminal_is_not_an_authorized_boundary(
    tmp_path: Path, relative: str, terminal: str
) -> None:
    copy_map_source_universe(tmp_path)
    constants = tmp_path / relative
    source = constants.read_text(encoding="utf-8")
    marker = f"DEF {terminal} EQU const_value"
    assert marker in source
    constants.write_text(
        source.replace(marker, f"REDEF {terminal} EQU const_value", 1),
        encoding="utf-8",
    )

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    with pytest.raises(MapBackgroundContentError, match=f"expected {terminal}"):
        authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    ("collection", "row_name", "field", "forged"),
    [
        ("tilesets", "OVERWORLD", "palette_authority", "ForgedPalette"),
        (
            "tilesets",
            "OVERWORLD",
            "attribute_authority",
            "ForgedAttributes",
        ),
        ("tilesets", "OVERWORLD", "animations", ["TILEANIM_WATER"]),
        ("tilesets", "OVERWORLD", "replacements", ["BOULDER"]),
        ("tilesets", "OVERWORLD", "batch", "residential-services"),
        ("tilesets", "GYM", "batch", "nonexistent-batch"),
        ("maps", "PALLET_TOWN", "roof", "VIRIDIAN"),
        ("maps", "PALLET_TOWN", "roof", "NONEXISTENT"),
        ("maps", "PALLET_TOWN", "overrides", ["FORGED_OVERRIDE"]),
        ("maps", "PALLET_TOWN", "animations", ["TILEANIM_WATER"]),
        ("maps", "PALLET_TOWN", "replacements", ["BOULDER"]),
        ("maps", "PALLET_TOWN", "batch", "residential-services"),
        ("maps", "PALLET_TOWN", "batch", "nonexistent-batch"),
    ],
)
def test_forged_ledger_semantic_fields_cannot_reconcile(
    collection: str, row_name: str, field: str, forged: object
) -> None:
    raw = raw_ledger()
    rows = raw[collection]
    row = next(candidate for candidate in rows if candidate["name"] == row_name)
    row[field] = forged
    assert_parse_or_reconciliation_rejects(raw)


def test_forged_fallback_authority_cannot_reconcile() -> None:
    raw = raw_ledger()
    row = next(
        candidate
        for candidate in raw["maps"]
        if candidate["fallback_reason"] is not None
    )
    row["fallback_reason"]["authority"] = "data/tilesets/forged.asm#Forged"
    assert_parse_or_reconciliation_rejects(raw)


@pytest.mark.parametrize(
    ("relative", "original", "replacement", "expected"),
    [
        (
            "data/tilesets/full_color_interiors.asm",
            "dw FullColorOverworldBGPalettes ; OVERWORLD",
            "dw ForgedPalette ; OVERWORLD",
            "pointer target ForgedPalette",
        ),
        (
            "data/tilesets/full_color_interiors.asm",
            "dw FullColorOverworldTileAttributes ; OVERWORLD",
            "dw ForgedAttributes ; OVERWORLD",
            "pointer target ForgedAttributes",
        ),
        (
            "data/tilesets/full_color_overworld.asm",
            "db FULL_COLOR_ROOF_PALLET    ; PALLET_TOWN",
            "db FULL_COLOR_ROOF_VIRIDIAN  ; PALLET_TOWN",
            "roof disagrees",
        ),
        (
            "constants/map_data_constants.asm",
            "const TILEANIM_WATER_FLOWER",
            "const TILEANIM_FORGED",
            "TILEANIM_WATER_FLOWER",
        ),
        (
            "data/tilesets/tileset_headers.asm",
            "tileset Forest,       -1, -1, -1, $20, TILEANIM_WATER",
            "tileset Forest,       -1, -1, -1, $20, TILEANIM_NONE",
            "animations disagree with Phase 1 metadata contract",
        ),
        (
            "data/tilesets/tileset_headers.asm",
            "tileset Dojo,        $3A, -1, -1,  -1, TILEANIM_WATER_FLOWER",
            "tileset Dojo,        $3A, -1, -1,  -1, TILEANIM_NONE",
            "animations disagree with Phase 1 metadata contract",
        ),
        (
            "data/tilesets/tileset_headers.asm",
            "tileset Gym,         $3A, -1, -1,  -1, TILEANIM_WATER_FLOWER",
            "tileset Gym,         $3A, -1, -1,  -1, TILEANIM_NONE",
            "animations disagree with Phase 1 metadata contract",
        ),
        (
            "data/tilesets/tileset_headers.asm",
            "tileset Ship,         -1, -1, -1,  -1, TILEANIM_WATER",
            "tileset Ship,         -1, -1, -1,  -1, TILEANIM_NONE",
            "animations disagree with Phase 1 metadata contract",
        ),
        (
            "data/tilesets/tileset_headers.asm",
            "tileset Facility,    $12, -1, -1,  -1, TILEANIM_WATER",
            "tileset Facility,    $12, -1, -1,  -1, TILEANIM_NONE",
            "animations disagree with Phase 1 metadata contract",
        ),
        (
            "data/tilesets/tileset_headers.asm",
            "tileset Cavern,       -1, -1, -1,  -1, TILEANIM_WATER",
            "tileset Cavern,       -1, -1, -1,  -1, TILEANIM_NONE",
            "animations disagree with Phase 1 metadata contract",
        ),
        (
            "data/tilesets/tileset_headers.asm",
            "tileset ShipPort,     -1, -1, -1,  -1, TILEANIM_WATER",
            "tileset ShipPort,     -1, -1, -1,  -1, TILEANIM_NONE",
            "animations disagree with Phase 1 metadata contract",
        ),
        (
            "data/tilesets/tileset_headers.asm",
            "tileset Plateau,      -1, -1, -1, $45, TILEANIM_WATER",
            "tileset Plateau,      -1, -1, -1, $45, TILEANIM_NONE",
            "animations disagree with Phase 1 metadata contract",
        ),
        (
            "data/tilesets/cut_tree_blocks.asm",
            "CutTreeBlockSwaps:",
            "ForgedCutTreeBlockSwaps:",
            "replacement authority",
        ),
        (
            "engine/full_color/passive_overworld.asm",
            "\tcp FACILITY + 1",
            "\tcp BEACH_HOUSE + 1",
            "production presentation predicate",
        ),
    ],
)
def test_repository_semantic_authority_drift_fails_closed(
    tmp_path: Path,
    relative: str,
    original: str,
    replacement: str,
    expected: str,
) -> None:
    copy_map_source_universe(tmp_path)
    path = tmp_path / relative
    source = path.read_text(encoding="utf-8")
    assert original in source
    path.write_text(source.replace(original, replacement, 1), encoding="utf-8")

    authority = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    if "disagree" in expected:
        assert any(expected in finding for finding in authority.reconcile(tmp_path))
    else:
        with pytest.raises(MapBackgroundContentError, match=expected):
            authority.reconcile(tmp_path)


@pytest.mark.parametrize(
    ("status", "presentation", "fallback", "review", "message"),
    [
        ("complete", "color", None, None, "reviewed authority"),
        ("fallback", "yellow", None, None, "requires fallback_reason"),
        (
            "complete",
            "yellow",
            {"kind": "content-missing", "authority": "contract#missing"},
            {
                "authority": "reviews/accepted.json",
                "atlas_sha256": "a" * 64,
                "route": "route-1",
                "revision": "b" * 40,
            },
            "content-missing fallback requires missing status",
        ),
        (
            "fallback",
            "color",
            None,
            {
                "authority": "reviews/accepted.json",
                "atlas_sha256": "a" * 64,
                "route": "route-1",
                "revision": "b" * 40,
            },
            "only complete content",
        ),
    ],
)
def test_invalid_status_presentation_fallback_and_review_combinations_fail(
    status: str,
    presentation: str,
    fallback: dict[str, str] | None,
    review: dict[str, str] | None,
    message: str,
) -> None:
    raw = raw_ledger()
    row = raw["maps"][0]
    row.update(
        content_status=status,
        presentation=presentation,
        fallback_reason=fallback,
        review=review,
    )
    with pytest.raises(MapBackgroundContentError, match=message):
        parse(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_status", "candidate"),
        ("presentation", "auto"),
        ("fallback_reason", {"kind": "unknown", "authority": "contract#x"}),
    ],
)
def test_unknown_contract_vocabulary_fails_closed(field: str, value: object) -> None:
    raw = raw_ledger()
    raw["maps"][0][field] = value
    with pytest.raises(MapBackgroundContentError):
        parse(raw)


def test_complete_rows_require_typed_review_metadata_not_a_coherent_rehash() -> None:
    raw = raw_ledger()
    row = raw["maps"][0]
    row["content_status"] = "complete"
    # Rehashing the altered canonical JSON is merely a self-consistent proposal;
    # it cannot stand in for a durable independent visual review record.
    raw["identity_sha256"] = "0" * 64
    with pytest.raises(MapBackgroundContentError):
        parse(raw)


def test_present_matching_forged_review_record_is_rejected_when_not_allowlisted(
    tmp_path: Path,
) -> None:
    copy_map_source_universe(tmp_path)
    raw = raw_ledger()
    row = raw["maps"][0]
    row["content_status"] = "complete"
    row["review"] = {
        "authority": "specs/full-colors/reviews/accepted.json#map-0",
        "atlas_sha256": "a" * 64,
        "route": "route-1",
        "revision": "b" * 40,
    }
    review_path = tmp_path / "specs/full-colors/reviews/accepted.json"
    review_path.parent.mkdir(parents=True)
    review_path.write_text(
        json.dumps(
            {
                "schema": "full-color-map-background-review-v1",
                "reviews": {
                    "map-0": {
                        "content_kind": "map",
                        "content_id": row["id"],
                        "content_name": row["name"],
                        "atlas_sha256": "a" * 64,
                        "route": "route-1",
                        "revision": "b" * 40,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    authority = parse(raw)
    assert any(
        "review authority path is not independently allowlisted" in finding
        for finding in authority.reconcile(tmp_path)
    )


@pytest.mark.parametrize(
    "mutation", ("batch", "purpose", "route", "candidate", "missing-artifact")
)
def test_phase4_review_semantic_mutations_fail_even_with_a_matching_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    copy_map_source_universe(tmp_path)
    relative = "specs/full-colors/evidence/map-background-reviews/forest-cavern.json"
    path = tmp_path / relative
    record = json.loads(path.read_text())
    if mutation == "batch":
        record["batch"] = "transport-special"
    elif mutation == "purpose":
        record["review"]["purpose"] = "runtime-admission"
    elif mutation == "route":
        record["review"]["route"] = "phase4-forged-route"
    elif mutation == "candidate":
        record["reviewed_candidate"]["sha256"] = "0" * 64
    else:
        record["atlas"]["artifacts"].pop()
    path.write_text(json.dumps(record), encoding="utf-8")
    canonical = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    allowlist = dict(map_background_content.REVIEW_RECORD_SHA256_ALLOWLIST)
    allowlist[relative] = hashlib.sha256(canonical).hexdigest()
    monkeypatch.setattr(
        map_background_content, "REVIEW_RECORD_SHA256_ALLOWLIST", allowlist
    )

    authority = parse(raw_ledger())
    assert any(
        "review authority is not durable" in finding
        for finding in authority.reconcile(tmp_path)
    )


def test_phase4_completion_cannot_overclaim_runtime_admission() -> None:
    raw = raw_ledger()
    row = next(row for row in raw["maps"] if row["name"] == "VIRIDIAN_FOREST")
    row["presentation"] = "color"
    with pytest.raises(MapBackgroundContentError):
        parse(raw)


def test_review_hashes_and_revision_are_exact_lowercase_encodings() -> None:
    raw = raw_ledger()
    row = raw["maps"][0]
    row["content_status"] = "complete"
    row["review"] = {
        "authority": "reviews/accepted.json",
        "atlas_sha256": "A" * 64,
        "route": "route-1",
        "revision": "b" * 40,
    }
    with pytest.raises(MapBackgroundContentError, match="atlas_sha256"):
        parse(raw)


def test_canonical_identity_is_deterministic_and_mutation_sensitive() -> None:
    first = MapBackgroundAuthority.load(REPOSITORY_ROOT)
    second = parse(json.loads(first.canonical_json()))
    assert first.canonical_json() == second.canonical_json()
    assert first.identity_sha256 == second.identity_sha256

    raw = raw_ledger()
    raw["maps"][0]["batch"] = "changed-batch"
    changed = parse(raw)
    assert changed.identity_sha256 != first.identity_sha256

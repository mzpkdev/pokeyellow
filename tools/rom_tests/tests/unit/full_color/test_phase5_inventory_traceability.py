"""Closed inventory and traceability contract for the audit-only Phase 5 slice."""

from __future__ import annotations

import json
from pathlib import Path
import re

from tools.rom_tests.full_color import phase5_stress
from tools.rom_tests.full_color.enums import Owner, Phase


ROOT = Path(__file__).resolve().parents[5]
MANIFEST_PATH = ROOT / "specs/full-colors/definitions/phase5-stress-cases.json"
INVENTORY_ROOT = ROOT / "specs/full-colors/inventory"
PRODUCTION_PRODUCTS = ("pokeyellow", "pokeyellow_debug", "pokeyellow_vc")
EXPECTED_WRITERS = {
    "WR-P5-AUDIT-ANIMATION-TILE-ATTRIBUTE",
    "WR-P5-AUDIT-BG-PALETTE",
    "WR-P5-AUDIT-CANONICAL-PAIRED-COLUMN2X18",
    "WR-P5-AUDIT-CANONICAL-PAIRED-DISPATCH",
    "WR-P5-AUDIT-CANONICAL-PAIRED-ROW20X2",
    "WR-P5-AUDIT-OAM-BUILD",
    "WR-P5-AUDIT-OAM-DMA",
    "WR-P5-AUDIT-PARTY-COLOR-ACTIVATION",
    "WR-P5-AUDIT-PARTY-COLOR-AUTHORITY-LOAD",
    "WR-P5-AUDIT-PARTY-COLOR-BARRIER",
    "WR-P5-AUDIT-PARTY-COLOR-LEGACY-PALETTE-ACK",
    "WR-P5-AUDIT-PARTY-COLOR-MAP-SPRITE-TILE-DATA",
    "WR-P5-AUDIT-PARTY-COLOR-OAM-BUILD",
    "WR-P5-AUDIT-PARTY-COLOR-PAIRED-BRIDGE",
    "WR-P5-AUDIT-PARTY-COLOR-PAIRED-FAST",
    "WR-P5-AUDIT-PARTY-COLOR-PAIRED-GENERAL",
    "WR-P5-AUDIT-PARTY-COLOR-PAIRED-MAP-PLANE",
    "WR-P5-AUDIT-PARTY-COLOR-PALETTE-DERIVATION",
    "WR-P5-AUDIT-PARTY-COLOR-PALETTE-PUBLISH",
    "WR-P5-AUDIT-PARTY-COLOR-PLAYER-TILE-DATA",
    "WR-P5-AUDIT-PARTY-COLOR-POISON",
    "WR-P5-AUDIT-PARTY-COLOR-RECONSTRUCTION",
    "WR-P5-AUDIT-PARTY-COLOR-TILESET-TILE-DATA",
    "WR-P5-AUDIT-PARTY-YELLOW-ACTIVATION",
    "WR-P5-AUDIT-PARTY-YELLOW-ATTRIBUTES",
    "WR-P5-AUDIT-PARTY-YELLOW-BARRIER",
    "WR-P5-AUDIT-PARTY-YELLOW-FONT-TILE-DATA",
    "WR-P5-AUDIT-PARTY-YELLOW-HP-STATUS-TILE-DATA",
    "WR-P5-AUDIT-PARTY-YELLOW-ICON-TILE-DATA",
    "WR-P5-AUDIT-PARTY-YELLOW-OAM-CLEAR",
    "WR-P5-AUDIT-PARTY-YELLOW-PALETTE-CONSTRUCTION",
    "WR-P5-AUDIT-PARTY-YELLOW-PALETTE-TRANSFORM",
    "WR-P5-AUDIT-PARTY-YELLOW-POISON",
    "WR-P5-AUDIT-PARTY-YELLOW-PRESENTATION",
    "WR-P5-AUDIT-PARTY-YELLOW-PRODUCER-LEDGER",
    "WR-P5-AUDIT-PARTY-YELLOW-SHADOW-OAM",
    "WR-P5-AUDIT-PARTY-YELLOW-TEXTBOX-TILE-DATA",
    "WR-P5-AUDIT-PARTY-YELLOW-TILEMAP",
    "WR-P5-AUDIT-VISIBLE-UNIT-DISPATCH",
}
REUSED_PRODUCTION_SYMBOLS = {
    "ClearSprites",
    "DrawPartyMenu_",
    "GBPalNormal",
    "InitCGBPalettes",
    "CopyVideoDataAlternate",
    "LoadBGMapAttributes",
    "LoadFontTilePatterns",
    "LoadHpBarAndStatusTilePatterns",
    "LoadMapSpriteTilePatterns",
    "LoadTextBoxTilePatterns",
    "WriteMonPartySpriteOAM",
}
EXPECTED_SCENES = {
    "SC-P5-AUDIT-PALLET-ROUTE1-NORTH",
    "SC-P5-AUDIT-PARTY-ENTRY",
    "SC-P5-AUDIT-PARTY-RETURN",
}
EXPECTED_MUTATIONS = {
    "MU-P5-AUDIT-COMBINED-ANIMATION",
    "MU-P5-AUDIT-COMBINED-OAM-BUILD",
    "MU-P5-AUDIT-COMBINED-OAM-DMA",
    "MU-P5-AUDIT-COMBINED-PALETTE",
    "MU-P5-AUDIT-COMBINED-VERTICAL",
    "MU-P5-AUDIT-CONNECTION-NORTH",
    "MU-P5-AUDIT-PARTY-RECONSTRUCTION",
}


def _manifest() -> dict[str, object]:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _inventory_rows(kind: str) -> dict[str, dict[str, object]]:
    raw = json.loads((INVENTORY_ROOT / f"{kind}.json").read_text(encoding="utf-8"))
    return {row["id"]: row for row in raw["rows"]}


def _linked_symbols(product: str) -> set[str]:
    return {
        line.split()[1]
        for line in (ROOT / f"{product}.sym").read_text(encoding="utf-8").splitlines()
        if len(line.split()) == 2 and ":" in line.split()[0]
    }


def _assert_source_symbol(path: str, symbol: str) -> None:
    source = (ROOT / path).read_text(encoding="utf-8")
    local = symbol.rsplit(".", 1)[-1]
    pattern = (
        rf"(?m)^\s*{'\\.' if '.' in symbol else ''}{re.escape(local)}"
        rf"(?:::|:)?(?:\s|$)"
    )
    assert re.search(pattern, source), f"{path} does not define {symbol}"


def _assert_ordered(source: str, *fragments: str) -> None:
    cursor = 0
    for fragment in fragments:
        cursor = source.find(fragment, cursor)
        assert cursor >= 0, f"missing ordered source fragment: {fragment}"
        cursor += len(fragment)


def test_phase5_manifest_binds_audit_scope_admission_and_review_workflow() -> None:
    raw = _manifest()

    assert set(raw) == {
        "schema", "phase", "activation", "production_activation",
        "runtime_admission", "reviewed_evidence", "capture_contract",
        "requirements", "acceptance", "inventory", "cases",
    }
    assert raw["schema"] == "full-color-phase5-stress-cases-v1"
    assert raw["phase"] == 5
    assert raw["activation"] == "PHASE2_AUDIT_ONLY"
    assert raw["production_activation"] is False
    assert raw["runtime_admission"] == {
        "color_presented_maps": 196,
        "yellow_presented_maps": 28,
        "changed": False,
    }
    assert raw["reviewed_evidence"] == {
        "path": "specs/full-colors/evidence/phase5-stress.json",
        "schema": phase5_stress.REVIEWED_SCHEMA,
        "promotion_forbidden_in_ci": True,
        "fresh_semantic_comparison": "EXACT",
        "capture_artifact_identities_are_separate": True,
    }
    assert raw["capture_contract"] == {
        "fresh_runs": 2,
        "minimum_natural_executions_per_path_per_run": phase5_stress.MINIMUM_EXECUTIONS,
        "stable_outputs_traces_and_frame_strips": True,
    }
    assert raw["requirements"] == [
        "R1.15", "R1.16", "R1.21", "R1.22", "R1.23", "R1.24", "R1.25",
        "R1.27", "R1.28", "R2.10", "R2.11", "R2.12", "R2.13", "R7.1",
        "R7.3", "R7.4", "R10.4", "R10.5", "R10.8", "R10.9", "R10.10",
    ]
    assert raw["acceptance"] == {
        "closes": [
            "AC-COMMIT-01", "AC-JOB-01", "AC-REQUEST-01", "AC-STRESS-01",
            "AC-STRESS-03", "AC-TIME-01",
        ],
        "progress_only": ["AC-RETURN-01", "AC-STRESS-02"],
    }

    def field_names(value: object) -> set[str]:
        if isinstance(value, dict):
            nested = (field_names(item) for item in value.values())
            return set(value) | set().union(*nested)
        if isinstance(value, list):
            return set().union(*(field_names(item) for item in value))
        return set()

    names = field_names(raw)
    assert not any(name.endswith("_sha256") for name in names)
    assert not names & {
        "worst_cycles", "margin_cycles", "margin_percent", "defer_threshold",
        "start_cycle", "deadline_cycle", "guard_cycles",
    }


def test_phase5_case_and_timing_rows_match_the_executable_producer() -> None:
    raw = _manifest()
    cases = raw["cases"]
    assert isinstance(cases, list)
    assert [case["id"] for case in cases] == list(
        phase5_stress.NATURAL_REQUEST_CLASSES
    )
    assert {
        case["id"]: case["natural_request_class"] for case in cases
    } == phase5_stress.NATURAL_REQUEST_CLASSES
    assert {
        case["id"]: case["boundary_request_class"] for case in cases
    } == phase5_stress.BOUNDARY_REQUEST_CLASSES
    assert [key for case in cases for key in case["timing_rows"]] == [
        row.key for row in phase5_stress.ROWS
    ]
    assert [case["check_ids"] for case in cases] == [
        ["CHK-STRESS-01"], ["CHK-STRESS-02"], ["CHK-STRESS-03"],
    ]


def test_phase5_inventory_relations_are_closed_and_audit_linked() -> None:
    raw = _manifest()
    inventory = raw["inventory"]
    writers = {row["id"]: row for row in inventory["writers"]}
    scenes = {row["id"]: row for row in inventory["scenes"]}
    mutations = {row["id"]: row for row in inventory["mutations"]}
    assert list(writers) == sorted(writers)
    assert list(scenes) == sorted(scenes)
    assert list(mutations) == sorted(mutations)
    assert set(writers) == EXPECTED_WRITERS
    assert set(scenes) == EXPECTED_SCENES
    assert set(mutations) == EXPECTED_MUTATIONS

    dependency_rows = {
        **_inventory_rows("writers"),
        **_inventory_rows("scenes"),
        **_inventory_rows("mutations"),
    }
    audit_symbols = _linked_symbols("pokeyellow_phase2_audit")
    production_symbols = set().union(
        *(_linked_symbols(name) for name in PRODUCTION_PRODUCTS)
    )
    for row in writers.values():
        assert row["owner"] in set(Owner)
        assert row["phase"] in set(Phase) | {"YELLOW_RECONSTRUCTING"}
        assert row["linked_symbol"] in audit_symbols
        if row["linked_symbol"] in REUSED_PRODUCTION_SYMBOLS:
            assert row["linked_symbol"] in production_symbols
        else:
            assert row["linked_symbol"] not in production_symbols
        _assert_source_symbol(row["source_path"], row["linked_symbol"])
        if "route_symbol" in row:
            assert row["route_symbol"] in audit_symbols
            _assert_source_symbol(row["route_path"], row["route_symbol"])
        if "selection_symbol" in row:
            assert row["selection_symbol"] in audit_symbols
            _assert_source_symbol(
                row.get("selection_path", row["route_path"]),
                row["selection_symbol"],
            )
        if "producer_symbol" in row:
            assert row["producer_symbol"] in audit_symbols
            _assert_source_symbol(row["source_path"], row["producer_symbol"])
        for field in ("write_start_symbol", "write_end_symbol"):
            if field in row:
                assert row[field] in audit_symbols
                _assert_source_symbol(row["source_path"], row[field])
        for downstream in row["downstream"]:
            assert downstream in writers or downstream in dependency_rows
    for row in scenes.values():
        assert row["source_symbol"] in audit_symbols
        assert row["destination_symbol"] in audit_symbols
        _assert_source_symbol(row["source_path"], row["source_symbol"])
        _assert_source_symbol(row["destination_path"], row["destination_symbol"])
        if "route_symbol" in row:
            assert row["route_symbol"] in audit_symbols
            _assert_source_symbol(row["route_path"], row["route_symbol"])
        assert set(row["first_writer_ids"]) <= set(writers)
    for row in mutations.values():
        assert set(row["writer_ids"]) <= set(writers)

    referenced = {kind: set() for kind in ("writers", "scenes", "mutations")}
    for case in raw["cases"]:
        referenced["writers"].update(case["writer_ids"])
        referenced["scenes"].update(case["scene_ids"])
        referenced["mutations"].update(case["mutation_ids"])
        for row_id in case["dependency_inventory_rows"]:
            assert row_id in dependency_rows
            assert dependency_rows[row_id]["planned"] is False
            assert dependency_rows[row_id]["evidence"]["reviewed"] is True
        roots = case["dependency_roots"]
        assert [root["row_id"] for root in roots] == case["dependency_inventory_rows"]
        assert all(root["scope"].endswith("_ONLY") for root in roots)
        assert all(root["executed_root"] for root in roots)
        assert all(
            symbol in audit_symbols
            for root in roots
            for symbol in root["executed_root"].split(" -> ")
        )
        assert all(
            root.get("linked_origin") is None
            or root["linked_origin"] in audit_symbols
            for root in roots
        )
    assert referenced == {
        "writers": set(writers), "scenes": set(scenes), "mutations": set(mutations),
    }


def test_party_reconstruction_inventory_names_all_hostile_variants() -> None:
    raw = _manifest()
    party = next(
        row for row in raw["inventory"]["mutations"]
        if row["id"] == "MU-P5-AUDIT-PARTY-RECONSTRUCTION"
    )
    assert party["hostile_variants"] == sorted({
        "FULL_COLOR_PHASE5_MUTATION_MISSING_POISON",
        "FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM",
        "FULL_COLOR_PHASE5_MUTATION_EARLY_BARRIER",
        "FULL_COLOR_PHASE5_MUTATION_DOUBLE_BARRIER",
        "FULL_COLOR_PHASE5_MUTATION_STALE_AUTHORITY",
        "FULL_COLOR_PHASE5_MUTATION_SAVED_AUTHORITY",
        "FULL_COLOR_PHASE5_MUTATION_PASSIVE_AUTHORITY",
        "FULL_COLOR_PHASE5_MUTATION_STALE_GENERATION",
        "FULL_COLOR_PHASE5_MUTATION_PREMATURE_MARKER_CLEAR",
        "FULL_COLOR_PHASE5_MUTATION_WRONG_BANK",
        "FULL_COLOR_PHASE5_MUTATION_STACK",
        "FULL_COLOR_PHASE5_MUTATION_INTERRUPT",
    })
    constants = (ROOT / "constants/full_color_constants.asm").read_text(encoding="utf-8")
    assert all(
        re.search(rf"(?m)^const\s+{name}$", constants)
        for name in party["hostile_variants"]
    )
    bindings = party["hostile_variant_bindings"]
    assert [binding["variant"] for binding in bindings] == party["hostile_variants"]
    assert {binding["fault_class"] for binding in bindings} == {
        "AUTHORITY_FRESHNESS",
        "BANK_PRESERVATION",
        "BARRIER_CARDINALITY",
        "BARRIER_ORDERING",
        "GENERATION_FRESHNESS",
        "INTERRUPT_PRESERVATION",
        "PASSIVE_AUTHORITY_REJECTION",
        "POISON_COMPLETENESS",
        "PRODUCER_LEDGER_COMPLETENESS",
        "RETURN_MARKER_LIFETIME",
        "SAVED_AUTHORITY_REJECTION",
        "STACK_PRESERVATION",
    }
    assert all(binding["affected_resources"] for binding in bindings)
    assert party["hostile_guard_writer_id"] == (
        "WR-P5-AUDIT-PARTY-YELLOW-PRESENTATION"
    )
    assert party["hostile_blocked_writer_ids"] == [
        "WR-P5-AUDIT-PARTY-YELLOW-ACTIVATION",
        "WR-P5-AUDIT-PARTY-YELLOW-BARRIER",
    ]
    special = {
        binding["variant"]: binding
        for binding in bindings
        if binding["injection"] != "HOSTILE_SELECTOR_FAILS_BEFORE_PRESENTATION"
    }
    assert set(special) == {
        "FULL_COLOR_PHASE5_MUTATION_MISSING_POISON",
        "FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM",
    }
    assert special["FULL_COLOR_PHASE5_MUTATION_MISSING_POISON"][
        "source_writer_ids"
    ] == ["WR-P5-AUDIT-PARTY-YELLOW-POISON"]
    assert special["FULL_COLOR_PHASE5_MUTATION_MISSING_POISON"][
        "observable_invariants"
    ] == [
        "POISON_LEDGER_IDENTITY_BIT_CLEAR",
        "YELLOW_DEADLINE_NOT_REACHED",
    ]
    assert special["FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM"][
        "source_writer_ids"
    ] == [
        "WR-P5-AUDIT-PARTY-YELLOW-FONT-TILE-DATA",
        "WR-P5-AUDIT-PARTY-YELLOW-PRODUCER-LEDGER",
    ]
    assert special["FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM"][
        "observable_invariants"
    ] == [
        "VFONT_0X800_BYTES_REMAIN_D3",
        "PRODUCER_LEDGER_BIT_0_CLEAR",
        "TILES_REPLACEMENTS_LEDGER_CLEAR",
        "YELLOW_DEADLINE_NOT_REACHED",
    ]


def test_party_inventory_binds_physical_writers_and_partial_dependencies() -> None:
    raw = _manifest()
    writers = {row["id"]: row for row in raw["inventory"]["writers"]}
    scenes = {row["id"]: row for row in raw["inventory"]["scenes"]}
    party_writers = {
        row_id: row for row_id, row in writers.items()
        if row_id.startswith("WR-P5-AUDIT-PARTY-")
    }

    assert all(row["generation_checked"] is False for row in party_writers.values())
    assert {
        row_id: (row["owner"], row["phase"])
        for row_id, row in party_writers.items()
        if row_id.endswith("-POISON")
    } == {
        "WR-P5-AUDIT-PARTY-COLOR-POISON": (
            "RENDERER_FULL_COLOR_OVERWORLD", "OVERWORLD_RECONSTRUCTING",
        ),
        "WR-P5-AUDIT-PARTY-YELLOW-POISON": (
            "RENDERER_YELLOW", "YELLOW_RECONSTRUCTING",
        ),
    }
    for row_id in (
        "WR-P5-AUDIT-PARTY-COLOR-POISON",
        "WR-P5-AUDIT-PARTY-YELLOW-POISON",
    ):
        row = writers[row_id]
        assert row["linked_symbol"] == "PoisonFullColorPhase5PartyState"
        assert {
            "TILEMAP_BACKUPS", "PALETTE_ATTRIBUTE_OAM_SCRATCH",
            "SCHEDULER_STATE", "RENDERER_JOB_STATE", "VIEWPORT_REGISTERS",
            "TRANSFER_STATE", "AUTHORITY_STATE",
        } <= set(row["resources"])
        assert row["preserved_machine_state"] == [
            "INTERRUPT_STATE", "ROM_BANK", "STACK_POINTER", "VRAM_BANK",
            "WRAM_BANK",
        ]

    assert scenes["SC-P5-AUDIT-PARTY-ENTRY"]["first_writer_ids"] == [
        "WR-P5-AUDIT-PARTY-YELLOW-POISON"
    ]
    assert scenes["SC-P5-AUDIT-PARTY-RETURN"]["first_writer_ids"] == [
        "WR-P5-AUDIT-PARTY-COLOR-POISON"
    ]
    assert writers["WR-P5-AUDIT-PARTY-COLOR-AUTHORITY-LOAD"][
        "linked_symbol"
    ] == "FullColorAuditLoadMapDataHomeAuthority"
    color = writers["WR-P5-AUDIT-PARTY-COLOR-RECONSTRUCTION"]
    assert color["linked_symbol"] == "ReconstructFullColorMapEntry"
    assert color["downstream"] == [
        "WR-P2-YELLOW-OAM-DMA",
        "WR-P5-AUDIT-PARTY-COLOR-BARRIER",
        "WR-P5-AUDIT-PARTY-COLOR-MAP-SPRITE-TILE-DATA",
        "WR-P5-AUDIT-PARTY-COLOR-OAM-BUILD",
        "WR-P5-AUDIT-PARTY-COLOR-PAIRED-BRIDGE",
        "WR-P5-AUDIT-PARTY-COLOR-PALETTE-DERIVATION",
        "WR-P5-AUDIT-PARTY-COLOR-PLAYER-TILE-DATA",
        "WR-P5-AUDIT-PARTY-COLOR-TILESET-TILE-DATA",
    ]
    assert writers["WR-P5-AUDIT-PARTY-COLOR-BARRIER"]["linked_symbol"] == (
        "FullColorPhase5PartyHandoffToColorDeadline"
    )
    activation = writers["WR-P5-AUDIT-PARTY-COLOR-ACTIVATION"]
    assert activation["kind"] == "ACTIVATION"
    assert activation["linked_symbol"] == (
        "CompleteFullColorPhase5PartyColorPresentation"
    )
    yellow_barrier = writers["WR-P5-AUDIT-PARTY-YELLOW-BARRIER"]
    assert yellow_barrier["resources"] == ["DISPLAY_REGISTER"]
    assert yellow_barrier["downstream"] == [
        "WR-P5-AUDIT-PARTY-YELLOW-ACTIVATION"
    ]
    yellow_activation = writers["WR-P5-AUDIT-PARTY-YELLOW-ACTIVATION"]
    assert yellow_activation["kind"] == "ACTIVATION"
    assert yellow_activation["resources"] == ["AUTHORITY_STATE"]
    assert {
        writers[row_id]["linked_symbol"]
        for row_id in party_writers
        if row_id.startswith("WR-P5-AUDIT-PARTY-YELLOW-")
    } >= {
        "CompleteFullColorPhase5PartyYellowReconstruction",
        "ClearSprites",
        "DrawPartyMenu_",
        "FullColorPhase5PartyHandoffToYellowDeadline",
        "GBPalNormal",
        "InitCGBPalettes",
        "LoadBGMapAttributes",
        "LoadFontTilePatterns",
        "LoadHpBarAndStatusTilePatterns",
        "LoadMonPartySpriteGfxLCDAlreadyDisabled",
        "LoadTextBoxTilePatterns",
        "PoisonFullColorPhase5PartyState",
        "RecordFullColorPhase5PartyYellowProducerStep",
        "WriteMonPartySpriteOAM",
    }

    party_case = next(
        case for case in raw["cases"]
        if case["id"] == "RC-P5-PARTY-RETURN-PALLET"
    )
    assert party_case["runtime_invariants"] == [
        "PRODUCER_ORDER_FONT_TEXT_HP_CLEAR_OAM_ICON_TILES_ICON_OAM_PALETTE_ATTRIBUTES_LOGICAL_TILEMAP",
        "PRODUCER_CALL_COUNTS_FONT_TEXT_HP_ICON_TILES_EQUAL_1",
        "PRODUCER_LEDGER_FF_BEFORE_YELLOW_BARRIER",
        "VFONT_TEXT_HP_MATCH_LINKED_ROM_AUTHORITY",
        "VISIBLE_TILEMAP_EQUALS_WTILEMAP",
        "ATTRIBUTES_NONPOISON",
        "SHADOW_OAM_EQUALS_HARDWARE_OAM",
        "UNUSED_OAM_ZERO",
        "ICON_TILES_NONPOISON",
        "SKIPPED_ITEM_LEAVES_VFONT_D3_FLAGS_FE_TILES_REPLACEMENTS_CLEAR_AND_NO_DEADLINE",
        "COLOR_TILESET_MATCHES_LINKED_BANK_POINTER_AUTHORITY",
        "COLOR_MAP_SPRITE_TILES_REBUILT_BEFORE_BASE_TILESET",
        "COLOR_MAP0_TILE_AND_ATTRIBUTE_PLANES_MATCH_LOGICAL_AUTHORITY",
        "COLOR_PALETTES_REPOPULATED_AFTER_PAIRED_ATTRIBUTE_SCRATCH",
        "COLOR_PLAYER_TILES_COPY_REDSPRITE_TO_8000_AND_8800_WHILE_HIDDEN",
        "COLOR_OAM_REBUILT_AND_DMA_PUBLISHED_WHILE_HIDDEN",
        "COLOR_GUARD_912_T_CYCLES_THEN_LEGACY_PALETTE_ACK_THEN_DEADLINE",
        "ALL_EIGHT_COLOR_TILESET_AND_PLAYER_HOSTILES_FAIL_BEFORE_DEADLINE",
    ]
    assert party_case["dependency_inventory_rows"] == [
        "MU-P2-MAP-RECONSTRUCTION",
        "MU-P2-OAM-FOLLOWER-NPC",
        "MU-P2-PALETTE-PAYLOADS",
        "MU-P2-START-MENU-OVERLAY",
        "SC-P2-PARTY-ENTRY",
        "WR-P2-YELLOW-OAM-BUILD",
        "WR-P2-YELLOW-OAM-DMA",
    ]
    assert {
        root["row_id"]: root["executed_root"]
        for root in party_case["dependency_roots"]
    } == {
        "MU-P2-MAP-RECONSTRUCTION": "LoadMapData",
        "MU-P2-OAM-FOLLOWER-NPC": "PrepareOAMData.build",
        "MU-P2-PALETTE-PAYLOADS": "TransferBGPPals",
        "MU-P2-START-MENU-OVERLAY": "DisplayStartMenu",
        "SC-P2-PARTY-ENTRY": "DisplayPartyMenu -> PartyMenuInit",
        "WR-P2-YELLOW-OAM-BUILD": "PrepareOAMData.build",
        "WR-P2-YELLOW-OAM-DMA": "hDMARoutine",
    }


def test_combined_oam_inventory_has_no_intermediate_shadow_copy() -> None:
    raw = _manifest()
    writers = {row["id"]: row for row in raw["inventory"]["writers"]}
    mutations = {row["id"]: row for row in raw["inventory"]["mutations"]}
    assert writers["WR-P5-AUDIT-OAM-BUILD"]["linked_symbol"] == (
        "PrepareFullColorOAMDataForOwnedVBlank"
    )
    assert writers["WR-P5-AUDIT-OAM-DMA"]["linked_symbol"] == (
        "CommitFullColorOAMBatchSelected"
    )
    assert "WR-P5-AUDIT-OAM-SHADOW" not in writers
    assert mutations["MU-P5-AUDIT-COMBINED-OAM-BUILD"]["writer_ids"] == [
        "WR-P5-AUDIT-OAM-BUILD"
    ]
    assert mutations["MU-P5-AUDIT-COMBINED-OAM-DMA"]["writer_ids"] == [
        "WR-P5-AUDIT-OAM-DMA"
    ]


def test_canonical_paired_writers_and_north_supersession_are_exact() -> None:
    raw = _manifest()
    writers = {row["id"]: row for row in raw["inventory"]["writers"]}
    scenes = {row["id"]: row for row in raw["inventory"]["scenes"]}
    mutations = {row["id"]: row for row in raw["inventory"]["mutations"]}

    dispatch = writers["WR-P5-AUDIT-CANONICAL-PAIRED-DISPATCH"]
    assert dispatch["linked_symbol"] == (
        "CommitFullColorPhase5PairedCanonicalTimedSelected"
    )
    assert dispatch["downstream"] == [
        "WR-P5-AUDIT-CANONICAL-PAIRED-COLUMN2X18",
        "WR-P5-AUDIT-CANONICAL-PAIRED-ROW20X2",
    ]
    column = writers["WR-P5-AUDIT-CANONICAL-PAIRED-COLUMN2X18"]
    assert column["linked_symbol"] == "CommitFullColorPhase5Paired2x18Selected"
    assert (column["write_start_symbol"], column["write_end_symbol"]) == (
        "FullColorPhase5Paired2x18WritesStart",
        "FullColorPhase5Paired2x18WritesEnd",
    )
    assert (
        column["width"], column["height"], column["extent"],
        column["public_target_writes"],
    ) == (2, 18, 36, 72)
    row = writers["WR-P5-AUDIT-CANONICAL-PAIRED-ROW20X2"]
    assert row["linked_symbol"] == "CommitFullColorPhase5Paired20x2Selected"
    assert (row["write_start_symbol"], row["write_end_symbol"]) == (
        "FullColorPhase5Paired20x2WritesStart",
        "FullColorPhase5Paired20x2WritesEnd",
    )
    assert (
        row["width"], row["height"], row["extent"],
        row["public_target_writes"],
    ) == (20, 2, 40, 80)
    assert mutations["MU-P5-AUDIT-COMBINED-VERTICAL"]["writer_ids"] == [
        "WR-P5-AUDIT-CANONICAL-PAIRED-COLUMN2X18",
        "WR-P5-AUDIT-CANONICAL-PAIRED-DISPATCH",
    ]
    north = mutations["MU-P5-AUDIT-CONNECTION-NORTH"]
    assert north["writer_ids"] == [
        "WR-P5-AUDIT-CANONICAL-PAIRED-DISPATCH",
        "WR-P5-AUDIT-CANONICAL-PAIRED-ROW20X2",
    ]
    supersession = north["supersession"]
    assert supersession["linked_symbol"] == (
        "RetireFullColorPhase5SupersededMovementSelected"
    )
    assert supersession["cancellation_symbol"] == (
        "CancelFullColorPhase5FastDescriptorSelected"
    )
    assert supersession["transition_sequence"] == [
        "CANCELLED", "ACCEPTED", "COMPLETE",
    ]
    assert supersession["predecessor"] == {
        "request_class": "FULL_COLOR_REQUEST_MAP_ROW_PAIRED",
        "state": "PREPARED",
        "flag": "FULL_COLOR_FLAG_MOVEMENT_STRIP",
        "required_cycles": "$ffff",
        "authority_map": "PALLET_TOWN",
        "live_map": "ROUTE_1",
        "destination_relation": "DISTINCT",
        "old_public_writes": 0,
    }
    assert supersession["successor"] == {
        "request_class": "FULL_COLOR_REQUEST_MAP_CONNECTION_PAIRED",
        "width": 20,
        "height": 2,
        "extent": 40,
        "destination": "$991c",
        "complete_count": 1,
        "presentation_count": 1,
    }
    audit_symbols = _linked_symbols("pokeyellow_phase2_audit")
    for symbol in (supersession["linked_symbol"], supersession["cancellation_symbol"]):
        assert symbol in audit_symbols
        _assert_source_symbol(supersession["source_path"], symbol)
    scene = scenes["SC-P5-AUDIT-PALLET-ROUTE1-NORTH"]
    assert scene["destination_symbol"] == "CommitFullColorPhase5Paired20x2Selected"
    assert scene["first_writer_ids"] == [
        "WR-P5-AUDIT-CANONICAL-PAIRED-ROW20X2"
    ]


def test_party_color_inventory_binds_every_hidden_producer_and_guard() -> None:
    raw = _manifest()
    writers = {row["id"]: row for row in raw["inventory"]["writers"]}
    mutation = next(
        row for row in raw["inventory"]["mutations"]
        if row["id"] == "MU-P5-AUDIT-PARTY-RECONSTRUCTION"
    )

    map_sprites = writers["WR-P5-AUDIT-PARTY-COLOR-MAP-SPRITE-TILE-DATA"]
    assert map_sprites["linked_symbol"] == "CopyVideoDataAlternate"
    assert map_sprites["route_symbol"] == "LoadMapSpriteTilePatterns"
    assert map_sprites["selection_symbol"] == "InitMapSprites"
    tileset = writers["WR-P5-AUDIT-PARTY-COLOR-TILESET-TILE-DATA"]
    assert tileset["linked_symbol"] == "FullColorPhase5PartyColorTilesetProducerStart"
    assert tileset["route_symbol"] == "FullColorPhase5PartyColorTilesetProducerReturn"
    assert tileset["producer_symbol"] == "LoadTilesetTilePatternData"
    assert (tileset["source_authority"], tileset["destination"], tileset["bytes"]) == (
        "wTilesetBank:wTilesetGfxPtr", "vTileset", 1536,
    )
    assert writers["WR-P5-AUDIT-PARTY-COLOR-PAIRED-BRIDGE"]["downstream"] == [
        "WR-P5-AUDIT-PARTY-COLOR-PAIRED-FAST"
    ]
    assert writers["WR-P5-AUDIT-PARTY-COLOR-PAIRED-BRIDGE"]["phase"] == (
        "OVERWORLD_RECONSTRUCTING"
    )
    assert writers["WR-P5-AUDIT-PARTY-COLOR-PAIRED-BRIDGE"][
        "generation_checked"
    ] is False
    assert writers["WR-P5-AUDIT-PARTY-COLOR-PAIRED-FAST"]["downstream"] == [
        "WR-P5-AUDIT-PARTY-COLOR-PAIRED-GENERAL"
    ]
    assert writers["WR-P5-AUDIT-PARTY-COLOR-PAIRED-GENERAL"]["downstream"] == [
        "WR-P5-AUDIT-PARTY-COLOR-PAIRED-MAP-PLANE"
    ]
    plane = writers["WR-P5-AUDIT-PARTY-COLOR-PAIRED-MAP-PLANE"]
    assert (plane["write_count"], plane["plane_order"], plane["destination"]) == (
        2, ["BG_TILE_IDS", "BG_ATTRIBUTES"], "vBGMap0",
    )
    derivation = writers["WR-P5-AUDIT-PARTY-COLOR-PALETTE-DERIVATION"]
    assert derivation["ordering"] == "AFTER_PAIRED_ATTRIBUTE_SCRATCH"
    assert derivation["downstream"] == [
        "WR-P5-AUDIT-PARTY-COLOR-PALETTE-PUBLISH"
    ]
    assert writers["WR-P5-AUDIT-PARTY-COLOR-PALETTE-PUBLISH"]["downstream"] == [
        "WR-P5-AUDIT-PARTY-COLOR-LEGACY-PALETTE-ACK"
    ]
    player = writers["WR-P5-AUDIT-PARTY-COLOR-PLAYER-TILE-DATA"]
    assert player["linked_symbol"] == "CopyVideoDataAlternate"
    assert player["route_symbol"] == "LoadPlayerSpriteGraphicsCommon"
    assert player["selection_symbol"] == "LoadPlayerSpriteGraphics"
    assert player["write_contract"] == [
        {"source": "RedSprite", "destination": "$8000", "tiles": 12},
        {"source": "RedSprite+$c0", "destination": "$8800", "tiles": 12},
    ]
    guard = mutation["color_presentation_guard"]
    assert guard == {
        "source_path": "engine/full_color/lifecycle.asm",
        "start_symbol": "FullColorPhase5PartyReconstructColorPresentationGuardStart",
        "end_symbol": "FullColorPhase5PartyReconstructColorPresentationGuardEnd",
        "exact_bytes": "c506370520fdc1",
        "t_cycles": 912,
        "minimum_reconstruct_end_to_deadline_t_cycles": 920,
        "preserves": ["BC", "STACK_POINTER", "DISPLAY_HIDDEN"],
        "temporal_relation": [
            "FullColorPhase5PartyReconstructColorEnd",
            "FullColorPhase5PartyReconstructColorPresentationGuardStart",
            "FullColorPhase5PartyReconstructColorPresentationGuardEnd",
            "FullColorPhase5AcknowledgeLegacyPaletteRegisters",
            "FullColorPhase5PartyReconstructColorDeadline",
        ],
    }
    audit_symbols = _linked_symbols("pokeyellow_phase2_audit")
    assert set(guard["temporal_relation"]) <= audit_symbols
    assert {item["injection"] for item in mutation["color_tileset_hostiles"]} == {
        "SKIP_PRODUCER", "WRONG_BANK", "WRONG_SOURCE",
    }
    assert {item["injection"] for item in mutation["color_player_hostiles"]} == {
        "SKIP_FIRST_HALF", "SKIP_SECOND_HALF", "WRONG_BANK", "WRONG_SOURCE",
        "WRONG_DESTINATION",
    }
    assert all(
        item["deadline_reached"] is False
        for group in ("color_tileset_hostiles", "color_player_hostiles")
        for item in mutation[group]
    )


def test_party_source_route_orders_poison_rebuild_barrier_and_activation() -> None:
    lifecycle = (ROOT / "engine/full_color/lifecycle.asm").read_text(encoding="utf-8")
    party_menu = (ROOT / "engine/menus/party_menu.asm").read_text(encoding="utf-8")
    start_menu = (ROOT / "engine/menus/start_sub_menus.asm").read_text(
        encoding="utf-8"
    )
    pokemon = (ROOT / "home/pokemon.asm").read_text(encoding="utf-8")
    overworld = (ROOT / "home/overworld.asm").read_text(encoding="utf-8")

    yellow_handoff = lifecycle.split(
        "BeginFullColorPhase5PartyHandoffToYellow::", 1
    )[1].split("FullColorPhase5PartyHandoffToYellowEnd::", 1)[0]
    _assert_ordered(
        yellow_handoff,
        "ld a, RENDERER_YELLOW",
        "ld a, YELLOW_RECONSTRUCTING",
        "call PoisonFullColorPhase5PartyState",
    )
    color_handoff = lifecycle.split(
        "BeginFullColorPhase5PartyHandoffToColor::", 1
    )[1].split("FullColorPhase5PartyHandoffToColorEnd::", 1)[0]
    _assert_ordered(
        color_handoff,
        "farcall SelectFullColorOwnerForDiagnostic",
        "call PoisonFullColorPhase5PartyState",
    )
    yellow_completion = lifecycle.split(
        "CompleteFullColorPhase5PartyYellowReconstruction::", 1
    )[1].split("FullColorPhase5PartyYellowMutationFailed:", 1)[0]
    _assert_ordered(
        yellow_completion,
        "call CopyFullColorPhase5TileMapToVRAM",
        "call hDMARoutine",
        "ld a, [wFullColorPhase5ScenarioFlags]",
        "cp FULL_COLOR_PHASE5_LEDGER_ALL",
        "ld [wFullColorPhase5BarrierState], a",
        "FullColorPhase5PartyHandoffToYellowDeadline::",
        "call EnableLCD",
        "ld [wRendererPhase], a",
        "ld [wRendererAdmissionOpen], a",
    )

    _assert_ordered(
        start_menu.split("StartMenu_Pokemon::", 1)[1].split(".loop", 1)[0],
        "farcall BeginFullColorPhase5PartyHandoffToYellow",
        "farcall ShouldSkipFullColorPhase5PartyFontProducer",
        "call LoadFontTilePatterns",
        "call LoadTextBoxTilePatterns",
        "call DisplayPartyMenu",
    )
    _assert_ordered(
        pokemon.split("PartyMenuInit::", 1)[1].split("HandlePartyMenuInput::", 1)[0],
        "call LoadHpBarAndStatusTilePatterns",
    )
    _assert_ordered(
        party_menu.split("DrawPartyMenu_::", 1)[1].split("\n.ordinary\n", 1)[0],
        "call ClearSprites",
        "farcall LoadMonPartySpriteGfxLCDAlreadyDisabled",
    )
    _assert_ordered(
        party_menu.split("RedrawPartyMenu_::", 1)[1].split(
            "PartyMenuItemUseMessagePointers:", 1
        )[0],
        "farcall WriteMonPartySpriteOAMByPartyIndex",
        "call RunPaletteCommand",
        "call GBPalNormal",
        "farcall CompleteFullColorPhase5PartyYellowReconstruction",
    )
    assert set(re.findall(
        r"DEF (FULL_COLOR_PHASE5_PARTY_STEP_[A-Z_]+) EQU 1 << [0-7]",
        party_menu,
    )) == {
        "FULL_COLOR_PHASE5_PARTY_STEP_CLEAR_OAM",
        "FULL_COLOR_PHASE5_PARTY_STEP_FONT",
        "FULL_COLOR_PHASE5_PARTY_STEP_HP_STATUS",
        "FULL_COLOR_PHASE5_PARTY_STEP_ICON_OAM",
        "FULL_COLOR_PHASE5_PARTY_STEP_ICON_TILES",
        "FULL_COLOR_PHASE5_PARTY_STEP_LOGICAL_TILEMAP",
        "FULL_COLOR_PHASE5_PARTY_STEP_PALETTE_ATTRIBUTES",
        "FULL_COLOR_PHASE5_PARTY_STEP_TEXTBOX",
    }

    authority = overworld.split(
        "FullColorAuditLoadMapDataHomeAuthority::", 1
    )[1].split("FullColorAuditLoadMapDataYellowPresentation:", 1)[0]
    _assert_ordered(
        authority,
        "call LoadTextBoxTilePatterns",
        "call LoadMapHeader",
        "call InitMapSprites",
        "call LoadScreenRelatedData",
        "call SnapshotFullColorMapAuthority",
        "call ReconstructFullColorMapEntry",
        "farcall FullColorPhase5PartyReconstructColorPresentationGuardStart",
        "farcall FullColorPhase5AcknowledgeLegacyPaletteRegisters",
        "FullColorPhase5PartyHandoffToColorDeadline::",
        "call EnableLCD",
        "farcall FullColorPhase5CompletePartyColorPresentationIfPending",
    )
    color_reconstruction = lifecycle.split(
        "ReconstructFullColorMapEntry::", 1
    )[1].split("\n.ordinaryBarrier\n", 1)[0]
    _assert_ordered(
        color_reconstruction,
        "call SnapshotFullColorVisibleMapSelected",
        "call CommitFullColorPairedTransferSelected",
        "call CopyAndTransformFullColorPaletteSelected",
        "farcall FullColorPhase5PublishPartyColorPalettesSelected",
        "farcall LoadPlayerSpriteGraphics",
        "farcall PrepareFullColorOAMDataForOwnedVBlank",
        "call hDMARoutine",
        "ld [wFullColorPhase5BarrierState], a",
    )


def test_phase5_docs_name_every_case_and_timing_row() -> None:
    raw = _manifest()
    migration = (ROOT / "specs/full-colors/docs/migration-plan.md").read_text(
        encoding="utf-8"
    )
    verification = (ROOT / "specs/full-colors/docs/verification-plan.md").read_text(
        encoding="utf-8"
    )
    assert MANIFEST_PATH.relative_to(ROOT).as_posix() in migration
    assert MANIFEST_PATH.relative_to(ROOT).as_posix() in verification
    for case in raw["cases"]:
        assert case["id"] in verification
        for key in case["timing_rows"]:
            assert key.rsplit("/", 1)[1] in verification

"""Mutation contracts for the Phase 5 host timing authority."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import stat

import pytest

from tools.rom_tests.full_color import phase5_stress as subject


ROOT = Path(__file__).resolve().parents[5]


def _row_evidence(descriptor: subject.RowDescriptor) -> dict[str, object]:
    digest = "1" * 64
    enqueued_mask = (
        7 if descriptor.row_id in {"VBlank", "palette", "animation", "OAM-build", "OAM-DMA"}
        else 0
    )
    drained_mask = 3 if descriptor.row_id == "VBlank" else 0
    if descriptor.row_id == "VBlank":
        public_sequence = [160, 160, 72, 160, 64, 160, 17] + [160] * 25
        enqueued_sequence = [4, 5] + [7] * 30
        drained_sequence = [4] * 4 + [5] * 2 + [7] * 26
    else:
        public_by_row = {
            "palette": 64, "vertical": 72, "animation": 17,
            "OAM-build": 0, "OAM-DMA": 160,
        }
        public_sequence = [public_by_row.get(descriptor.row_id, 0)] * 32
        enqueued_sequence = [enqueued_mask] * 32
        drained_sequence = [drained_mask] * 32
    enqueued_masks = sorted(set(enqueued_sequence))
    drained_masks = sorted(set(drained_sequence))
    evidence = {
        "case_id": descriptor.case_id,
        "row_id": descriptor.row_id,
        "operation": descriptor.operation,
        "scenario_constant": descriptor.scenario_constant,
        "natural_arm_constant": descriptor.arm_constant,
        "start_label": descriptor.start_label,
        "end_label": descriptor.end_label,
        "origin_label": descriptor.origin_label,
        "deadline_observation_label": descriptor.deadline_observation_label,
        "deadline_observation_role": (
            "HANDLER_END_DIAGNOSTIC_ONLY"
            if descriptor.deadline_kind == "FIXED_VBLANK"
            else "LINKED_PRESENTATION_DEADLINE"
        ),
        "deadline_kind": descriptor.deadline_kind,
        "natural_executions": 32,
        "sameboy": {
            "cycles": [321] * 32,
            "timing_observations": [
                {
                    "start_offset": (
                        0 if descriptor.start_label == descriptor.origin_label else 100
                    ),
                    "end_offset": 421,
                    "deadline_offset": 7000, "end_ly": 144, "end_stat": 1,
                    "deadline_ly": 145, "deadline_stat": 1,
                    "available_cycles_at_end": 6000,
                    "required_cycles_at_end": 1000,
                    "available_cycles_at_deadline": 6000,
                    "required_cycles_at_deadline": 1000,
                    "public_target_writes": public_sequence[index],
                    "post_end_public_target_writes": 0,
            "active_descriptor_state_at_end": (
                        0x32 if descriptor.row_id == "VBlank" and public_sequence[index] in (72, 80)
                        else 0xFF
                    ),
                    "active_descriptor_state_at_deadline": (
                        0x32 if descriptor.row_id == "VBlank" and public_sequence[index] in (72, 80)
                        else 0xFF
                    ),
                    "active_descriptor_address_at_end": (
                        0xD300 if descriptor.row_id == "VBlank" and public_sequence[index] in (72, 80)
                        else 0
                    ),
                    "active_descriptor_address_at_deadline": (
                        0xD300 if descriptor.row_id == "VBlank" and public_sequence[index] in (72, 80)
                        else 0
                    ),
                    "active_descriptor_destination_at_end": (
                        0x9800 if descriptor.row_id == "VBlank" and public_sequence[index] in (72, 80)
                        else 0
                    ),
                    "active_descriptor_destination_at_deadline": (
                        0x9800 if descriptor.row_id == "VBlank" and public_sequence[index] in (72, 80)
                        else 0
                    ),
                    "fast_cache_valid_at_end": (
                        0xA5 if descriptor.row_id == "VBlank" and public_sequence[index] in (72, 80)
                        else 0
                    ),
                    "fast_cache_valid_at_deadline": 0,
                    "request_count_at_end": (
                        1 if descriptor.row_id == "VBlank" and public_sequence[index] in (72, 80)
                        else 0
                    ),
                    "request_count_at_deadline": 0,
                }
                for index in range(32)
            ],
            "semantic_sha256": digest,
            "trace_sha256": digest,
            "frame_strip": [{"path": "strip.png", "sha256": digest}],
            "pressure_accounting": {
                "enqueued_masks_at_end": enqueued_masks,
                "drained_masks_at_end": drained_masks,
                "enqueued_masks_at_deadline": enqueued_masks,
                "drained_masks_at_deadline": drained_masks,
                "frame_sequence": [
                    {
                        "index": index,
                        "public_target_writes": public_sequence[index],
                        "enqueued_mask": enqueued_sequence[index],
                        "drained_mask": drained_sequence[index],
                        "remaining_cycles": 6000,
                        "required_cycles": 1000,
                    }
                    for index in range(32)
                ],
            },
        },
        "pyboy": {
            "semantic_sha256": digest,
            "trace_sha256": digest,
            "frame_strip": [{"path": "strip.png", "sha256": digest}],
        },
        "write_diagnostics": {
            "public_target_writes_within_interval": [0],
            "preparation_buffer_writes": [0],
            "descriptor_metadata_writes_included": False,
            "cycle_budget_role": "NONE",
        },
    }
    if descriptor.descriptor_class_constant is not None:
        extent = {
            "palette": 64,
            "vertical": 36,
            "animation": 17,
            "OAM-build": 160,
            "OAM-DMA": 160,
        }.get(descriptor.row_id, 40)
        semantic = extent * (2 if descriptor.semantic_write_kind == "PAIRED_PLANES" else 1)
        evidence["write_diagnostics"]["public_target_writes_within_interval"] = (
            [0] if descriptor.row_id == "connection" else [semantic]
        )
        evidence["descriptor_write_count_proposal"] = {
            "authority": "UNREVIEWED_PROPOSAL_ONLY",
            "unit": "DESCRIPTOR_SEMANTIC_PUBLIC_TARGET_WRITES",
            "request_class_constant": descriptor.descriptor_class_constant,
            "observed_descriptor": {
                "class": 3 if descriptor.row_id == "connection" else 1,
                "width": 2 if descriptor.row_id == "vertical" else (
                    20 if extent == 40 else 0
                ),
                "height": 18 if descriptor.row_id == "vertical" else (
                    2 if extent == 40 else 0
                ),
                "extent": extent,
            },
            "semantic_unit_target_writes": semantic,
            "semantic_unit_equation": f"fixture = {semantic} writes",
            "eventual_commit_corroboration": {
                "end_trace_sha256": [digest],
                "presentation_trace_sha256": [digest],
                "presentation_trace_differs_from_end": (
                    [True] if descriptor.row_id in {"OAM-build", "connection"} else [False]
                ),
                "eventual_public_target_writes": (
                    [semantic] if descriptor.row_id in {"OAM-build", "connection"}
                    else [0]
                ),
                "enqueued_masks_at_deadline": [7],
                "drained_masks_at_deadline": [0],
            },
            "proposed_target_write_count": semantic,
            "changes_admission": False,
            "cycle_budget_role": "NONE",
        }
    if descriptor.row_id == "connection":
        evidence["sameboy"]["producer_retry_evidence"] = {
            "schema": "full-color-phase5-producer-retry-v1",
            "samples": [
                {
                    "index": index,
                    "producer_class": 3,
                    "producer_destination": 0x991C,
                    "producer_width": 20,
                    "producer_height": 2,
                    "producer_extent": 40,
                    "producer_payload_sha256": digest,
                    "retry_admit_hits": 1,
                    "retry_finish_hits": 1,
                    "retry_publish_hits": 1,
                    "retry_publish_result": 0,
                    "completed_descriptor_address": 0xD300,
                    "completed_descriptor_destination": 0x991C,
                    "completed_descriptor_state": 0x33,
                    "completed_descriptor_result": "COMPLETE",
                }
                for index in range(32)
            ],
        }
    return evidence


def _proposal() -> dict[str, object]:
    first = [_row_evidence(row) for row in subject.ROWS]
    second = deepcopy(first)
    timing_rows = [
        subject._timing_row(row, first[index], second[index])
        for index, row in enumerate(subject.ROWS)
    ]
    threshold_contract = subject._boundary_threshold_contract_from_values(2600, 80)
    required = threshold_contract["accepted_required_cycles"]
    assert required == 2680
    boundary_rows = []
    for case_id, request_class in subject.BOUNDARY_REQUEST_CLASSES.items():
        for boundary in subject.MUTABLE_BOUNDARIES:
            for mode in ("EXACT_FIT", "THRESHOLD_PLUS_ONE"):
                boundary_rows.append({
                    "case_id": case_id,
                    "boundary": boundary,
                    "mode": mode,
                    "request_class": request_class,
                    "available_cycles": required,
                    "required_cycles": required + (mode == "THRESHOLD_PLUS_ONE"),
                    "retry_available_cycles": (
                        required + 1 if mode == "THRESHOLD_PLUS_ONE" else None
                    ),
                    "result": "COMPLETE" if mode == "EXACT_FIT" else "DEFER",
                    "entered_committing": mode == "EXACT_FIT",
                    "deferred_public_target_writes": 0 if mode == "THRESHOLD_PLUS_ONE" else None,
                    "first_attempt_public_target_writes": 0 if mode == "THRESHOLD_PLUS_ONE" else 2,
                    "retry_public_target_writes": 2 if mode == "THRESHOLD_PLUS_ONE" else 0,
                    "admitted_unit_identity_sha256": "6" * 64,
                    "retained_unit_identity_sha256": "4" * 64,
                    "retry_unit_identity_sha256": "4" * 64,
                    "completed_unit_identity_sha256": "6" * 64,
                    "retry_result": "COMPLETE",
                    "final_descriptor_state": "COMPLETE",
                    "final_request_count": 0,
                    "completed_units": 1,
                    "committing_transitions": 1,
                    "complete_transitions": 1,
                    "presented_target_writes": 2,
                    "presented_target_changes": 2,
                    "paired_publication": "4106",
                    "stress_state": (
                        bytes(3)
                        + required.to_bytes(2, "little")
                        + (required + (mode == "THRESHOLD_PLUS_ONE")).to_bytes(2, "little")
                        + bytes(4)
                    ).hex(),
                    "post_retry_stress_state": (
                        bytes(3)
                        + (required + (mode == "THRESHOLD_PLUS_ONE")).to_bytes(2, "little")
                        + (required + (mode == "THRESHOLD_PLUS_ONE")).to_bytes(2, "little")
                        + bytes(4)
                    ).hex(),
                    "trace_sha256": "3" * 64,
                })
    semantic_counts = {
        "OAM": 160,
        "palette": 64,
        "animation": 17,
        "vertical": 72,
    }
    return {
        "schema": subject.SCHEMA,
        "reviewed": False,
        "authority": {
            "timing": "PINNED_SAMEBOY_DEBUGGER_TICKS",
            "behavioral_cross_check": "PYBOY_2_7_ONLY",
            "product": "pokeyellow_phase2_audit.gbc",
            "production_activation": False,
        },
        "identities": {},
        "case_manifest": subject._case_manifest_binding(ROOT),
        "production_admission": {
            "color_presented_maps": 196,
            "yellow_presented_maps": 28,
            "changed": False,
            "phase5_production_activation": False,
        },
        "captures": [
            {"id": "run-1", "path": "attempt-0004/run-1/run.json", "sha256": "1" * 64},
            {"id": "run-2", "path": "attempt-0004/run-2/run.json", "sha256": "2" * 64},
        ],
        "timing_rows": timing_rows,
        "descriptor_write_counts": [
            {
                "key": row.key,
                "proposal": first[index]["descriptor_write_count_proposal"],
            }
            for index, row in enumerate(subject.ROWS)
            if row.descriptor_class_constant is not None
        ],
        "write_diagnostics": [
            {"key": row.key, **first[index]["write_diagnostics"]}
            for index, row in enumerate(subject.ROWS)
        ],
        "pressure_accounting": [
            {"key": row.key, **first[index]["sameboy"]["pressure_accounting"]}
            for index, row in enumerate(subject.ROWS)
        ],
        "north_retry_evidence": [
            {
                "key": row.key,
                "producer_class_constant": row.descriptor_class_constant,
                **first[index]["sameboy"]["producer_retry_evidence"],
            }
            for index, row in enumerate(subject.ROWS)
            if row.row_id == "connection"
        ],
        "combined_serialized_drain": subject._serialized_drain_evidence(
            first[0]["sameboy"]["pressure_accounting"], semantic_counts
        ),
        "combined_semantic_public_write_breakdown": [
            {
                "key": row.key,
                "semantic_unit_target_writes": first[index]["descriptor_write_count_proposal"]["semantic_unit_target_writes"],
                "semantic_unit_equation": first[index]["descriptor_write_count_proposal"]["semantic_unit_equation"],
                "eventual_commit_corroboration": first[index]["descriptor_write_count_proposal"]["eventual_commit_corroboration"],
            }
            for index, row in enumerate(subject.ROWS)
            if row.row_id in {"palette", "vertical", "animation", "OAM-build"}
        ],
        "comparison": {
            "fresh_captures": 2,
            "byte_stable_outputs_traces_frame_strips": True,
            "minimum_natural_executions_per_path_per_run": 32,
        },
        "boundary_matrix": {
            "schema": "full-color-phase5-boundary-matrix-v1",
            "cycle_unit": "CPU_T_CYCLES_AT_ACTIVE_SPEED",
            "threshold_contract": threshold_contract,
            "rows": boundary_rows,
        },
        "evidence_files": [
            {"path": path, "sha256": "5" * 64}
            for path in subject._expected_evidence_paths("attempt-0004")
        ],
    }


def test_stable_phase5_case_row_and_linked_symbol_surface() -> None:
    assert [(row.case_id, row.row_id) for row in subject.ROWS] == [
        ("RC-P5-COMBINED-PRESSURE-PALLET", "VBlank"),
        ("RC-P5-COMBINED-PRESSURE-PALLET", "palette"),
        ("RC-P5-COMBINED-PRESSURE-PALLET", "vertical"),
        ("RC-P5-COMBINED-PRESSURE-PALLET", "animation"),
        ("RC-P5-COMBINED-PRESSURE-PALLET", "OAM-build"),
        ("RC-P5-COMBINED-PRESSURE-PALLET", "OAM-DMA"),
        ("RC-P5-PARTY-RETURN-PALLET", "handoff-to-Yellow"),
        ("RC-P5-PARTY-RETURN-PALLET", "handoff-to-Color"),
        ("RC-P5-PARTY-RETURN-PALLET", "reconstruct-Color"),
        ("RC-P5-CONNECTION-PALLET-NORTH", "connection"),
    ]
    assert len(subject.TIMING_LABELS) >= 30
    assert all(
        label.endswith(("Start", "End", "Origin", "Deadline", "HandlerEnd"))
        for label in subject.TIMING_LABELS
    )
    vblank = subject.ROWS[0]
    assert vblank.start_label == vblank.origin_label == "FullColorPhase5VBlankOrigin"
    assert vblank.end_label == "FullColorPhase5CombinedVBlankEnd"
    assert vblank.deadline_observation_label == "FullColorPhase5VBlankHandlerEnd"
    assert vblank.deadline_kind == "FIXED_VBLANK"


def test_valid_proposal_uses_natural_double_speed_equation() -> None:
    parsed = subject.validate_proposal(_proposal())
    for descriptor, row in zip(subject.ROWS, parsed["timing_rows"], strict=True):
        assert row["deadline_cycle"] == (9120 if descriptor.deadline_kind == "FIXED_VBLANK" else 7000)
        assert row["guard_cycles"] == 912
        assert row["instrumentation_cycles"] == 0
        expected_start = 0 if descriptor.start_label == descriptor.origin_label else 100
        assert row["defer_threshold"] == row["deadline_cycle"] - expected_start - 912
        assert row["samples"] == 64
        assert row["breakpoint_overhead_t_cycles"] == 0
        assert row["deadline_observation_role"] == (
            "HANDLER_END_DIAGNOSTIC_ONLY"
            if descriptor.deadline_kind == "FIXED_VBLANK"
            else "LINKED_PRESENTATION_DEADLINE"
        )


@pytest.mark.parametrize("hostile_attempt", ("attempt-0003", "attempt-0005"))
def test_proposal_rejects_unreviewed_neighbor_attempts(hostile_attempt: str) -> None:
    proposal = _proposal()
    for capture in proposal["captures"]:
        capture["path"] = capture["path"].replace(
            subject.PINNED_REVIEW_ATTEMPT, hostile_attempt
        )
    for artifact in proposal["evidence_files"]:
        artifact["path"] = artifact["path"].replace(
            subject.PINNED_REVIEW_ATTEMPT, hostile_attempt
        )
    with pytest.raises(subject.Phase5StressError, match="capture identity"):
        subject.validate_proposal(proposal)


def test_fixed_vblank_handler_end_is_diagnostic_not_the_physical_deadline() -> None:
    descriptor = subject.ROWS[0]
    first = _row_evidence(descriptor)
    second = deepcopy(first)
    for observation in first["sameboy"]["timing_observations"]:
        observation["deadline_offset"] = 10_500
    for observation in second["sameboy"]["timing_observations"]:
        observation["deadline_offset"] = 14_000
    row = subject._timing_row(descriptor, first, second)
    assert row["deadline_cycle"] == 9120
    assert row["observed_breakpoint_offsets"] == [10_500] * 32 + [14_000] * 32
    assert row["measured_deadline_jitter_t_cycles"] == 0
    assert row["guard_cycles"] == 912
    assert row["deadline_observation_role"] == "HANDLER_END_DIAGNOSTIC_ONLY"
    assert row["result"] == "PASS"


def test_combined_subrows_use_one_natural_case_arm_without_synthetic_dispatch() -> None:
    combined = [
        row for row in subject.ROWS
        if row.case_id == "RC-P5-COMBINED-PRESSURE-PALLET"
    ]
    assert {row.arm_constant for row in combined} == {
        "FULL_COLOR_PHASE5_SCENARIO_COMBINED_VBLANK"
    }
    assert len({row.scenario_constant for row in combined}) == len(combined)
    assert {
        subject._observed_scenario_constant(row) for row in combined
    } == {"FULL_COLOR_PHASE5_SCENARIO_COMBINED_VBLANK"}


def test_party_subrows_arm_one_roundtrip_and_observe_distinct_lifecycle_ids() -> None:
    party = [
        row for row in subject.ROWS
        if row.case_id == "RC-P5-PARTY-RETURN-PALLET"
    ]
    assert {row.arm_constant for row in party} == {
        "FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_YELLOW"
    }
    assert len({row.scenario_constant for row in party}) == 3
    assert [subject._observed_scenario_constant(row) for row in party] == [
        row.scenario_constant for row in party
    ]


def test_combined_pressure_rejects_overlap_partial_or_reordered_drain() -> None:
    proposal = _proposal()
    sequence = proposal["pressure_accounting"][0]["frame_sequence"]
    sequence[0]["public_target_writes"] = 224  # OAM + palette in one frame
    with pytest.raises(subject.Phase5StressError, match="overlapped|partial"):
        subject.validate_proposal(proposal)

    proposal = _proposal()
    sequence = proposal["pressure_accounting"][0]["frame_sequence"]
    sequence[1]["drained_mask"] = 6
    proposal["pressure_accounting"][0]["drained_masks_at_end"] = [4, 5, 6, 7]
    with pytest.raises(subject.Phase5StressError, match="drain order"):
        subject.validate_proposal(proposal)


def test_combined_pressure_rejects_stale_three_unit_or_delayed_column_contracts() -> None:
    proposal = _proposal()
    sequence = proposal["pressure_accounting"][0]["frame_sequence"]
    sequence[6]["public_target_writes"] = 160
    sequence[6]["drained_mask"] = 5
    sequence[7]["public_target_writes"] = 17
    with pytest.raises(subject.Phase5StressError, match="latency"):
        subject.validate_proposal(proposal)

    proposal = _proposal()
    sequence = proposal["pressure_accounting"][0]["frame_sequence"]
    sequence[2]["public_target_writes"] = 160
    sequence[5]["public_target_writes"] = 72
    with pytest.raises(subject.Phase5StressError, match="column/order"):
        subject.validate_proposal(proposal)

    proposal = _proposal()
    sequence = proposal["pressure_accounting"][0]["frame_sequence"]
    sequence[2]["enqueued_mask"] = 0
    proposal["pressure_accounting"][0]["enqueued_masks_at_end"] = [0, 4, 5, 7]
    with pytest.raises(subject.Phase5StressError, match="simultaneous pressure interval"):
        subject.validate_proposal(proposal)

    proposal = _proposal()
    sequence = proposal["pressure_accounting"][0]["frame_sequence"]
    sequence[4]["public_target_writes"] = 17
    sequence[6]["public_target_writes"] = 64
    with pytest.raises(subject.Phase5StressError, match="column/order"):
        subject.validate_proposal(proposal)

    proposal = _proposal()
    proposal["combined_serialized_drain"]["semantic_public_target_writes"][
        "vertical"
    ] = 80
    with pytest.raises(subject.Phase5StressError, match="serialized drain evidence drifted"):
        subject.validate_proposal(proposal)


def test_combined_serialized_summary_cannot_self_authorize() -> None:
    proposal = _proposal()
    proposal["combined_serialized_drain"]["whole_unit_serialization"] = False
    with pytest.raises(subject.Phase5StressError, match="serialized drain evidence drifted"):
        subject.validate_proposal(proposal)


def test_party_navigation_matches_stock_missing_pokedex_index_adjustment() -> None:
    stock = (ROOT / "home/start_menu.asm").read_text(encoding="utf-8")
    driver = (ROOT / subject.DRIVER_SOURCE).read_text(encoding="utf-8")
    producer = (ROOT / "tools/rom_tests/full_color/phase5_stress.py").read_text(
        encoding="utf-8"
    )
    assert "inc a ; adjust position to account for missing pokedex menu item" in stock
    assert "driver.max_menu_item, 6) ? 0 : 1" in driver
    assert '0 if emulator.read("wMaxMenuItem") == 6 else 1' in producer


def test_sameboy_combined_capture_uses_pulsed_natural_movement() -> None:
    driver = (ROOT / subject.DRIVER_SOURCE).read_text(encoding="utf-8")
    pulse = driver.split("static void pulse_movement_key", 1)[1].split("static bool value_is", 1)[0]
    assert "GB_set_key_state(driver->gb, key, true);" in pulse
    assert "run_frames(driver, 2);" in pulse
    assert "GB_set_key_state(driver->gb, key, false);" in pulse
    assert "run_frames(driver, 121);" in pulse
    assert "pulse_movement_key(&driver, sustained_movement_key);" in driver
    assert "column_movement ? GB_KEY_RIGHT : GB_KEY_DOWN" in driver
    assert "prepare_natural_pallet(&driver, party_path || north_path)" in driver
    assert "if (coordinate <= 3) wanted = column_movement ? GB_KEY_RIGHT : GB_KEY_DOWN;" in driver
    assert "coordinate >= (column_movement ? 16 : 14)" in driver
    assert "(frame % 24)" not in driver
    assert "Shared enqueue and presentation seams may execute for unrelated" in driver
    assert "at_linked_symbol(driver, driver->operation_end)" in driver


def test_connection_capture_uses_stock_pallet_approach_and_specific_origin() -> None:
    driver = (ROOT / subject.DRIVER_SOURCE).read_text(encoding="utf-8")
    producer = (ROOT / "tools/rom_tests/full_color/phase5_stress.py").read_text(
        encoding="utf-8"
    )
    assert "driver.x_coord, 8" in driver
    assert "driver.y_coord, 2, GB_KEY_UP" in driver
    assert "driver.x_coord, 10, GB_KEY_RIGHT" in driver
    assert "GB_run(driver.gb);" in driver
    assert "driver->north_input_released = true" in driver
    assert "changed map before exact connection Start" in driver
    assert "driver.current_map, 0, GB_KEY_DOWN, 48" in driver
    assert "GB_set_key_state(driver.gb, GB_KEY_UP, true);" in driver
    assert "GB_set_key_state(driver->gb, GB_KEY_UP, false);" in driver
    assert '"EnqueueFullColorMapConnection"' in producer
    assert '"breakpoint $%04x"' not in driver
    assert '"breakpoint $%02x:$%04x"' in driver
    assert "North Start and producer linked symbols are not exact aliases" in driver
    assert "north_path ? GB_KEY_UP" in driver
    assert "driver.operation_start.bank" in driver
    assert "driver.operation_start.address" in driver
    assert "first observed origin" in driver
    assert "pre-breakpoint approach" in driver
    assert "captured_descriptor_is_complete(driver)" in driver
    assert "bind_retried_producer_descriptor(driver)" in driver
    assert '"AdmitPreparedFullColorSemanticSelected"' in driver
    assert '"RetryFullColorProducer.publish"' in driver
    assert "sample->producer_payload" in driver
    assert "producer_snapshot_destination" in driver
    assert "first observed origin" in driver
    assert 'emulator.read("wXCoord") == 8' in producer
    assert 'emulator.read("wYCoord") == 2' in producer
    assert 'emulator.read("wXCoord") == 10' in producer
    assert 'emulator.read("wYCoord") == 0' in producer
    assert 'if emulator.read("wYCoord") > 2:' in producer
    assert 'description="return to Pallet from Route 1"' in producer
    assert 'emulator.press("up", wait_frames=20)' in producer


def test_finite_case_rows_use_fresh_natural_windows_and_open_scroll_column() -> None:
    assert subject.FRESH_WINDOW_ROW_IDS == {
        "palette", "vertical", "animation",
        "handoff-to-Yellow", "handoff-to-Color", "reconstruct-Color",
        "connection",
    }
    assert subject.FRESH_WINDOW_TOTAL_TIMEOUT_SECONDS == 7200
    assert subject.FRESH_WINDOW_SINGLE_TIMEOUT_SECONDS == 600
    driver = (ROOT / subject.DRIVER_SOURCE).read_text(encoding="utf-8")
    producer = (ROOT / "tools/rom_tests/full_color/phase5_stress.py").read_text(
        encoding="utf-8"
    )
    assert "Pallet's open scrolling axis" in driver
    assert 'description="Pallet open scrolling column"' in producer
    assert 'windows_dir / f"window-{index:04d}"' in producer
    assert "time.monotonic() >= deadline" in producer


def test_combined_pressure_uses_natural_horizontal_strip_cadence() -> None:
    combined = subject.ROWS[0]
    vertical = next(row for row in subject.ROWS if row.row_id == "vertical")
    assert subject._natural_movement_axis(combined) == "column"
    assert subject._natural_movement_axis(vertical) == "column"
    assert vertical.descriptor_class_constant == "FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED"

    driver = (ROOT / subject.DRIVER_SOURCE).read_text(encoding="utf-8")
    producer = (ROOT / "tools/rom_tests/full_color/phase5_stress.py").read_text(
        encoding="utf-8"
    )
    assert "run_frames(driver, 2);" in driver
    assert "run_frames(driver, 121);" in driver
    assert "driver.x_coord, 9, GB_KEY_RIGHT, 2" in driver
    assert "clean_column_measurement_seam" in driver
    assert "driver->renderer_generation" in driver
    assert "driver->producer_pending" in driver
    assert "driver->options.oam_class_value" in driver
    assert 'description="Pallet open horizontal strip route"' in producer
    assert 'description="Pallet camera-column measurement seam"' in producer
    assert 'emulator.tick(121 if movement_axis == "column" else 12)' in producer


def test_fresh_window_metadata_rejects_skip_and_mixed_authorities() -> None:
    digest = "1" * 64
    windows = [
        {
            "index": index,
            "raw_capture_sha256": digest,
            "calibration_sha256": digest,
            "identities": {"rom": digest, "sameboy_driver": digest},
        }
        for index in range(2)
    ]
    subject._validate_fresh_window_metadata(
        windows, samples=2, require_calibration=True
    )

    skipped = deepcopy(windows)
    skipped[1]["index"] = 2
    with pytest.raises(subject.Phase5StressError, match="index"):
        subject._validate_fresh_window_metadata(
            skipped, samples=2, require_calibration=True
        )

    mixed_rom = deepcopy(windows)
    mixed_rom[1]["identities"]["rom"] = "2" * 64
    with pytest.raises(subject.Phase5StressError, match="mixed ROM or tool"):
        subject._validate_fresh_window_metadata(
            mixed_rom, samples=2, require_calibration=True
        )

    mixed_calibration = deepcopy(windows)
    mixed_calibration[1]["calibration_sha256"] = "2" * 64
    with pytest.raises(subject.Phase5StressError, match="mixed SameBoy"):
        subject._validate_fresh_window_metadata(
            mixed_calibration, samples=2, require_calibration=True
        )


def test_case_manifest_binds_exact_case_execution_rows_and_inventory_ids() -> None:
    parsed = subject.validate_proposal(_proposal())
    manifest = parsed["case_manifest"]
    assert [case["id"] for case in manifest["cases"]] == list(
        subject.NATURAL_REQUEST_CLASSES
    )
    combined = manifest["cases"][0]
    assert combined["natural_request_class"] == "FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED"
    assert combined["boundary_request_class"] == "FULL_COLOR_REQUEST_MAP_ROW_PAIRED"
    assert manifest == subject._case_manifest_binding(ROOT)
    party = next(
        case for case in manifest["cases"]
        if case["id"] == "RC-P5-PARTY-RETURN-PALLET"
    )
    assert [writer["id"] for writer in party["writer_bindings"]] == party["writer_ids"]
    assert [root["row_id"] for root in party["dependency_roots"]] == (
        party["dependency_inventory_rows"]
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("producer_payload_sha256", "not-a-hash"),
        ("producer_class", 2),
        ("completed_descriptor_address", 0xCFFF),
        ("completed_descriptor_destination", 0x991D),
        ("producer_extent", 39),
        ("retry_admit_hits", 0),
        ("retry_finish_hits", 0),
        ("retry_publish_hits", 0),
        ("completed_descriptor_state", 0x32),
        ("completed_descriptor_result", "DEFERRED"),
    ],
)
def test_north_retry_identity_and_completion_mutations_fail_closed(
    field: str, value: object
) -> None:
    proposal = _proposal()
    proposal["north_retry_evidence"][0]["samples"][0][field] = value
    with pytest.raises(
        subject.Phase5StressError,
        match="North producer/retry proof|north_retry_evidence|North producer identity",
    ):
        subject.validate_proposal(proposal)


def test_party_reconstruction_guard_is_linked_and_measured() -> None:
    proposal = _proposal()
    row = next(
        timing for timing in proposal["timing_rows"]
        if timing["key"].endswith("/reconstruct-Color")
    )
    guard = row["presentation_guard"]
    assert guard["cross_bank_farcall_roundtrip"] is True
    assert guard["guard_machine_code"] == "c506370520fdc1"
    assert guard["operation_end_to_guard_start_role"].startswith("SUCCESS_CHECK")
    assert guard["guard_end_to_deadline_role"].startswith("CROSS_BANK_RETURN")
    assert guard["minimum_observed_operation_end_to_deadline_t_cycles"] > 920
    assert {
        subject.PARTY_RECONSTRUCTION_GUARD_START,
        subject.PARTY_RECONSTRUCTION_GUARD_END,
    } <= subject.TIMING_LABELS
    guard["minimum_observed_operation_end_to_deadline_t_cycles"] = 920
    with pytest.raises(subject.Phase5StressError, match="presentation guard"):
        subject.validate_proposal(proposal)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("writer_ids", ["NOT-A-WRITER"]),
        ("scene_ids", ["NOT-A-SCENE"]),
        ("mutation_ids", ["NOT-A-MUTATION"]),
        ("dependency_inventory_rows", ["NOT-A-WRITER"]),
        ("writer_bindings", []),
        ("dependency_roots", []),
        ("timing_rows", ["RC-P5-COMBINED-PRESSURE-PALLET/not-a-row"]),
    ],
)
def test_case_manifest_execution_binding_mutations_fail_closed(
    field: str, replacement: list[str]
) -> None:
    proposal = _proposal()
    proposal["case_manifest"]["cases"][0][field] = replacement
    with pytest.raises(subject.Phase5StressError, match="manifest"):
        subject.validate_proposal(proposal)


def test_verify_rejects_validly_shaped_case_manifest_content_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal()
    proposal["case_manifest"]["cases"][0]["writer_ids"] = ["WR-P5-AUDIT-DRIFT"]
    proposal["case_manifest"]["cases"][0]["writer_bindings"] = [{
        **proposal["case_manifest"]["cases"][0]["writer_bindings"][0],
        "id": "WR-P5-AUDIT-DRIFT",
    }]
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    monkeypatch.setattr(subject, "capture_identities", lambda *_args: {})
    with pytest.raises(subject.Phase5StressError, match="execution manifest binding drifted"):
        subject.verify(ROOT, tmp_path, proposal_path)


def test_verify_rejects_linked_writer_inventory_record_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal()
    party = next(
        case for case in proposal["case_manifest"]["cases"]
        if case["id"] == "RC-P5-PARTY-RETURN-PALLET"
    )
    party["writer_bindings"][0]["linked_symbol"] = "DriftedColorAuxiliaryProducer"
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    monkeypatch.setattr(subject, "capture_identities", lambda *_args: {})
    with pytest.raises(subject.Phase5StressError, match="execution manifest binding drifted"):
        subject.verify(ROOT, tmp_path, proposal_path)


def test_verify_checks_fresh_capture_files_as_separate_regular_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _proposal()
    evidence_root = tmp_path / "captures"
    run_payload = subject._canonical({"schema": subject.RUN_SCHEMA, "rows": []}).encode()
    matrix_payload = subject._canonical(proposal["boundary_matrix"]).encode()
    capture_paths = {capture["path"] for capture in proposal["captures"]}
    matrix_paths = {
        "attempt-0004/boundary-run-1/matrix.json",
        "attempt-0004/boundary-run-2/matrix.json",
    }
    for item in proposal["evidence_files"]:
        path = evidence_root / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            run_payload if item["path"] in capture_paths
            else matrix_payload if item["path"] in matrix_paths
            else item["path"].encode()
        )
        item["sha256"] = subject._sha256(path)
    for capture in proposal["captures"]:
        capture["sha256"] = next(
            item["sha256"] for item in proposal["evidence_files"]
            if item["path"] == capture["path"]
        )
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    monkeypatch.setattr(subject, "capture_identities", lambda *_args: {})
    monkeypatch.setattr(
        subject, "_production_admission_binding",
        lambda *_args: proposal["production_admission"],
    )
    derived_names = {
        "timing_rows", "descriptor_write_counts", "write_diagnostics",
        "pressure_accounting", "north_retry_evidence",
        "combined_serialized_drain", "combined_semantic_public_write_breakdown",
        "comparison", "boundary_matrix",
    }
    monkeypatch.setattr(
        subject, "_derived_promoted_semantics",
        lambda *_args: {name: proposal[name] for name in derived_names},
    )
    monkeypatch.setattr(subject, "_validate_authenticated_run_artifacts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        subject, "PINNED_REVIEW_TREE_SHA256",
        subject._artifact_tree_sha256(proposal["evidence_files"]),
    )
    monkeypatch.setattr(
        subject, "PINNED_REVIEW_FILE_COUNT", len(proposal["evidence_files"])
    )
    subject.verify(ROOT, tmp_path, proposal_path, evidence_root=evidence_root)

    first = evidence_root / proposal["captures"][0]["path"]
    first.write_bytes(b"drift")
    with pytest.raises(subject.Phase5StressError, match="artifact.*drifted|tree digest"):
        subject.verify(ROOT, tmp_path, proposal_path, evidence_root=evidence_root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("deadline_cycle", 4560),
        ("guard_cycles", 911),
        ("instrumentation_cycles", 1),
        ("breakpoint_overhead_t_cycles", 1),
        ("defer_threshold", 8207),
        ("cycle_unit", "M_CYCLES"),
    ],
)
def test_timing_equation_mutations_fail_closed(field: str, value: object) -> None:
    proposal = _proposal()
    proposal["timing_rows"][0][field] = value
    with pytest.raises((subject.Phase5StressError, ValueError), match="timing|cycle|threshold|deadline|guard|instrumentation"):
        subject.validate_proposal(proposal)


def test_runtime_required_cycles_cannot_understate_measured_cost() -> None:
    proposal = _proposal()
    timing = proposal["timing_rows"][1]
    timing["observed_runtime_required_cycles"] = [320]
    timing["runtime_admission_equation"] = (
        "FrameAvailableCycles is remaining after accepted units; "
        "remaining=[6000], required=[320], min(required) >= measured 321 CPU T-cycles"
    )
    with pytest.raises(subject.Phase5StressError, match="understates observation"):
        subject.validate_proposal(proposal)


@pytest.mark.parametrize(
    ("cell_index", "field", "value"),
    [
        (0, "first_attempt_public_target_writes", 1),
        (0, "completed_units", 2),
        (0, "committing_transitions", 2),
        (0, "complete_transitions", 2),
        (0, "presented_target_writes", 1),
        (0, "presented_target_changes", 1),
        (0, "completed_unit_identity_sha256", "7" * 64),
        (1, "required_cycles", 321),
        (1, "available_cycles", 320),
        (1, "retry_available_cycles", 2680),
        (1, "retry_public_target_writes", 1),
        (1, "completed_units", 2),
        (1, "committing_transitions", 2),
        (1, "complete_transitions", 2),
        (1, "completed_unit_identity_sha256", "7" * 64),
    ],
)
def test_boundary_completed_unit_split_duplicate_or_substitution_fails_closed(
    cell_index: int, field: str, value: object
) -> None:
    proposal = _proposal()
    proposal["boundary_matrix"]["rows"][cell_index][field] = value
    with pytest.raises(subject.Phase5StressError, match="boundary|substituted"):
        subject.validate_proposal(proposal)


def test_boundary_matrix_uses_linked_1x1_paired_cost_not_lifecycle_maximum() -> None:
    proposal = _proposal()
    contract = proposal["boundary_matrix"]["threshold_contract"]
    assert contract["accepted_required_cycles"] == 2680
    for cell in proposal["boundary_matrix"]["rows"]:
        assert cell["available_cycles"] == 2680
        assert cell["required_cycles"] == (
            2681 if cell["mode"] == "THRESHOLD_PLUS_ONE" else 2680
        )
        assert cell["retry_available_cycles"] == (
            2681 if cell["mode"] == "THRESHOLD_PLUS_ONE" else None
        )

    lifecycle_max = max(row["worst_cycles"] for row in proposal["timing_rows"])
    assert lifecycle_max != 2680
    for cell in proposal["boundary_matrix"]["rows"]:
        cell["available_cycles"] = lifecycle_max
        cell["required_cycles"] = lifecycle_max + (
            cell["mode"] == "THRESHOLD_PLUS_ONE"
        )
    with pytest.raises(subject.Phase5StressError, match="boundary"):
        subject.validate_proposal(proposal)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("request_geometry", "width"), 2),
        (("request_geometry", "extent"), 2),
        (("request_geometry", "semantic_public_target_writes"), 1),
        (("equation",), "2600 + 80 = 2680 CPU T-cycles"),
        (("lifecycle_timing_source",), True),
        (("saturation_or_truncation",), True),
        (("accepted_required_cycles",), 42104),
    ],
)
def test_boundary_threshold_geometry_equation_or_truncation_fails_closed(
    path: tuple[str, ...], value: object
) -> None:
    proposal = _proposal()
    target = proposal["boundary_matrix"]["threshold_contract"]
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = value
    with pytest.raises(subject.Phase5StressError, match="boundary|paired|cycle"):
        subject.validate_proposal(proposal)


@pytest.mark.parametrize(("base", "cell"), [(0, 0), (0xFFFF, 0), (0xFFFE, 1)])
def test_boundary_threshold_never_saturates_or_truncates_u16(
    base: int, cell: int
) -> None:
    with pytest.raises(subject.Phase5StressError, match="u16"):
        subject._boundary_threshold_contract_from_values(base, cell)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unit", "CPU_T_CYCLES"),
        ("authority", "REVIEWED"),
        ("changes_admission", True),
        ("cycle_budget_role", "TIMING"),
        ("proposed_target_write_count", 5),
    ],
)
def test_descriptor_write_count_mutations_never_become_cycles(
    field: str, value: object
) -> None:
    proposal = _proposal()
    proposal["descriptor_write_counts"][0]["proposal"][field] = value
    with pytest.raises(subject.Phase5StressError, match="write-count|descriptor"):
        subject.validate_proposal(proposal)


def test_single_unit_public_count_and_eventual_commit_corroboration_fail_closed() -> None:
    proposal = _proposal()
    proposal["write_diagnostics"][1]["public_target_writes_within_interval"] = [0]
    with pytest.raises(subject.Phase5StressError, match="public commit count"):
        subject.validate_proposal(proposal)

    proposal = _proposal()
    proposal["descriptor_write_counts"][3]["proposal"][
        "eventual_commit_corroboration"
    ]["eventual_public_target_writes"] = [0]
    with pytest.raises(subject.Phase5StressError, match="eventual public commit"):
        subject.validate_proposal(proposal)


def test_compare_runs_rejects_trace_or_frame_strip_drift() -> None:
    first = {"rows": [_row_evidence(row) for row in subject.ROWS]}
    second = deepcopy(first)
    subject.compare_runs(first, second)
    second["rows"][3]["sameboy"]["trace_sha256"] = "2" * 64
    with pytest.raises(subject.Phase5StressError, match="differ"):
        subject.compare_runs(first, second)


def test_driver_capture_requires_double_speed_exact_state_and_pairing() -> None:
    row = subject.ROWS[0]
    constants = {
        row.scenario_constant: 1,
        subject.RESULT_PASSED_CONSTANT: 1,
        subject.STATE_COMPLETE_CONSTANT: 7,
        subject.FAST_CACHE_ACCOUNTING_PENDING_CONSTANT: 0xA5,
        "COMPLETE": 3,
        "RENDERER_FULL_COLOR_OVERWORLD": 1,
        "OVERWORLD_ACTIVE": 3,
    }
    sample = {
        "index": 0,
        "key1": 0x80,
        "scenario": bytes([0, 1, 0, 1, 7] + [0] * 6).hex(),
        "post_scenario": bytes([0, 1, 0, 1, 7] + [0] * 6).hex(),
        "post_owner": 1,
        "post_phase": 3,
        "stress": bytes(11).hex(),
        "trace": bytes(194).hex(),
        "frame": "frame-0000.ppm",
        "ticks": 10,
        "start_offset": 2,
        "end_offset": 12,
        "deadline_offset": 20,
        "public_target_writes": 3,
        "preparation_buffer_writes": 2,
        "post_end_public_target_writes": 0,
        "semantic_unit_public_target_writes": 0,
        "active_descriptor_state_at_end": 0xFF,
        "active_descriptor_state_at_deadline": 0xFF,
        "active_descriptor_address_at_end": 0,
        "active_descriptor_address_at_deadline": 0,
        "active_descriptor_destination_at_end": 0,
        "active_descriptor_destination_at_deadline": 0,
        "fast_cache_valid_at_end": 0,
        "fast_cache_valid_at_deadline": 0,
        "request_count_at_end": 0,
        "request_count_at_deadline": 0,
        "presentation_trace": bytes(194).hex(),
        "descriptor_found": False,
        "descriptor_class": 0, "descriptor_width": 0,
        "descriptor_height": 0, "descriptor_extent": 0,
        "descriptor_reservation": 0,
        "enqueued_mask_at_end": 0, "drained_mask_at_end": 0,
        "enqueued_mask_at_deadline": 0, "drained_mask_at_deadline": 0,
        "available_cycles_at_end": 0, "required_cycles_at_end": 0,
        "available_cycles_at_deadline": 0, "required_cycles_at_deadline": 0,
        "end_ly": 144,
        "end_stat": 1,
        "deadline_ly": 145,
        "deadline_stat": 1,
    }
    capture = {
        "calibration": {
            "frame_ticks": 140448,
            "known_nop_count": 16,
            "known_nop_ticks": 64,
            "scanline_ticks": 912,
            "ly144_to_ly145_register_ticks": 916,
            "ly144_to_ly0_register_ticks": 8220,
            "natural_vblank_ticks": 9120,
        },
        "schema": "sameboy-phase5-driver-v1",
        "model": "CGB-C",
        "start_count": 1,
        "samples": [sample],
    }
    subject._validate_driver_capture(row, capture, constants=constants, samples=1)
    capture["samples"][0]["deadline_offset"] = 12
    with pytest.raises(subject.Phase5StressError, match="end <= deadline"):
        subject._validate_driver_capture(row, capture, constants=constants, samples=1)
    capture["samples"][0]["deadline_offset"] = 11
    with pytest.raises(subject.Phase5StressError, match="end <= deadline"):
        subject._validate_driver_capture(row, capture, constants=constants, samples=1)
    capture["samples"][0]["deadline_offset"] = 20
    capture["samples"][0]["key1"] = 0
    with pytest.raises(subject.Phase5StressError, match="double-speed"):
        subject._validate_driver_capture(row, capture, constants=constants, samples=1)
    capture["samples"][0]["key1"] = 0x80
    capture["samples"][0].update({
        "producer_class": 3,
        "producer_bound_descriptor_address": 0xD300,
        "producer_bound_descriptor_destination": 0x991C,
        "producer_bound_descriptor_state": 0x33,
        "producer_destination": 0x991C,
        "producer_extent": 2,
        "producer_height": 1,
        "producer_payload": "01020304",
        "producer_snapshot_found": True,
        "producer_width": 2,
        "retry_admit_hits": 1,
        "retry_finish_hits": 1,
        "retry_publish_hits": 1,
        "retry_publish_result": 0,
    })
    subject._validate_driver_capture(row, capture, constants=constants, samples=1)
    capture["samples"][0]["producer_payload"] = "0102"
    with pytest.raises(subject.Phase5StressError, match="paired snapshot"):
        subject._validate_driver_capture(row, capture, constants=constants, samples=1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("known_nop_ticks", 63),
        ("scanline_ticks", 911),
        ("natural_vblank_ticks", 4560),
        ("frame_ticks", 140447),
        ("ly144_to_ly145_register_ticks", 1000),
        ("ly144_to_ly0_register_ticks", 9120),
    ],
)
def test_sameboy_tick_calibration_mutations_fail_closed(field: str, value: int) -> None:
    row = subject.ROWS[0]
    constants = {
        row.scenario_constant: 1,
        subject.FAST_CACHE_ACCOUNTING_PENDING_CONSTANT: 0xA5,
        "COMPLETE": 3,
        "RENDERER_FULL_COLOR_OVERWORLD": 1,
        "OVERWORLD_ACTIVE": 3,
    }
    sample = {
        "index": 0, "key1": 0x80,
        "scenario": bytes([0, 1] + [0] * 9).hex(),
        "post_scenario": bytes([0, 1] + [0] * 9).hex(),
        "post_owner": 1, "post_phase": 3,
        "stress": bytes(11).hex(), "trace": bytes(194).hex(),
        "frame": "frame-0000.ppm", "ticks": 10,
        "start_offset": 2, "end_offset": 12, "deadline_offset": 20,
        "public_target_writes": 3, "preparation_buffer_writes": 2,
        "post_end_public_target_writes": 0,
        "semantic_unit_public_target_writes": 0,
        "active_descriptor_state_at_end": 0xFF,
        "active_descriptor_state_at_deadline": 0xFF,
        "active_descriptor_address_at_end": 0,
        "active_descriptor_address_at_deadline": 0,
        "active_descriptor_destination_at_end": 0,
        "active_descriptor_destination_at_deadline": 0,
        "fast_cache_valid_at_end": 0,
        "fast_cache_valid_at_deadline": 0,
        "request_count_at_end": 0, "request_count_at_deadline": 0,
        "presentation_trace": bytes(194).hex(),
        "descriptor_found": False, "descriptor_class": 0,
        "descriptor_width": 0, "descriptor_height": 0,
        "descriptor_extent": 0, "descriptor_reservation": 0,
        "enqueued_mask_at_end": 0, "drained_mask_at_end": 0,
        "enqueued_mask_at_deadline": 0, "drained_mask_at_deadline": 0,
        "available_cycles_at_end": 0, "required_cycles_at_end": 0,
        "available_cycles_at_deadline": 0, "required_cycles_at_deadline": 0,
        "end_ly": 144, "end_stat": 1,
        "deadline_ly": 145, "deadline_stat": 1,
    }
    calibration = {
        "frame_ticks": 140448, "known_nop_count": 16,
        "known_nop_ticks": 64, "scanline_ticks": 912,
        "ly144_to_ly145_register_ticks": 916,
        "ly144_to_ly0_register_ticks": 8220, "natural_vblank_ticks": 9120,
    }
    calibration[field] = value
    capture = {
        "schema": "sameboy-phase5-driver-v1", "model": "CGB-C",
        "start_count": 1, "samples": [sample], "calibration": calibration,
    }
    with pytest.raises(subject.Phase5StressError, match="calibration"):
        subject._validate_driver_capture(row, capture, constants=constants, samples=1)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("post_end_public_target_writes", 1, "public/display writer"),
        ("fast_cache_valid_at_deadline", 0xA5, "left the fast cache armed"),
        ("active_descriptor_state_at_end", 0x22, "not COMPLETE"),
        ("fast_cache_valid_at_end", 0, "not COMPLETE"),
        ("request_count_at_deadline", 1, "retire exactly one"),
    ],
)
def test_vblank_owner_end_and_finalizer_mutations_fail_closed(
    field: str, value: int, message: str,
) -> None:
    sample = {
        "public_target_writes": 80,
        "post_end_public_target_writes": 0,
        "active_descriptor_state_at_end": 0x32,
        "active_descriptor_state_at_deadline": 0x32,
        "fast_cache_valid_at_end": 0xA5,
        "fast_cache_valid_at_deadline": 0,
        "request_count_at_end": 1,
        "request_count_at_deadline": 0,
    }
    sample[field] = value
    with pytest.raises(subject.Phase5StressError, match=message):
        subject._validate_vblank_finalizer_invariants(
            subject.ROWS[0],
            sample,
            {subject.FAST_CACHE_ACCOUNTING_PENDING_CONSTANT: 0xA5, "COMPLETE": 3},
            path="fixture",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("descriptor_found", False, "slot is missing"),
        ("descriptor_class", 1, "class or geometry"),
        ("descriptor_width", 20, "class or geometry"),
        ("active_descriptor_state_at_end", 0x12, "COMMITTING to COMPLETE"),
        ("active_descriptor_state_at_deadline", 0xF2, "COMMITTING to COMPLETE"),
        ("active_descriptor_address_at_deadline", 0, "reclaimed or substituted"),
    ],
)
def test_vertical_column_descriptor_lifecycle_fails_closed(
    field: str, value: object, message: str,
) -> None:
    vertical = next(row for row in subject.ROWS if row.row_id == "vertical")
    snapshot = bytearray(20)
    snapshot[0] = 0x22
    snapshot[1] = 1
    snapshot[6:8] = (0x9854).to_bytes(2, "little")
    snapshot[8:10] = (0xD6E4).to_bytes(2, "little")
    snapshot[10:12] = bytes((2, 18))
    snapshot[14:16] = (36).to_bytes(2, "little")
    snapshot[16:18] = (72).to_bytes(2, "little")
    sample = {
        "descriptor_found": True,
        "descriptor_class": 2,
        "descriptor_width": 2,
        "descriptor_height": 18,
        "descriptor_extent": 36,
        "descriptor_reservation": 72,
        "active_descriptor_state_at_end": 0x22,
        "active_descriptor_state_at_deadline": 0x32,
        "active_descriptor_address_at_end": 0xD049,
        "active_descriptor_address_at_deadline": 0xD049,
        "active_descriptor_destination_at_end": 0x9854,
        "active_descriptor_destination_at_deadline": 0x9854,
        "fast_cache_valid_at_end": 0x3C,
        "fast_cache_valid_at_deadline": 0,
        "request_count_at_end": 3,
        "request_count_at_deadline": 2,
        "post_end_public_target_writes": 0,
        "descriptor_snapshot": snapshot.hex(),
        "descriptor_home_seen": True,
        "descriptor_home_address": 0xD049,
        "descriptor_home_state": 0x32,
        "descriptor_home_cache": 0xA5,
        "descriptor_home_post_end_public_writes": 0,
        "descriptor_deferred_seen": True,
        "descriptor_deferred_address": 0xD049,
        "descriptor_deferred_state": 0x32,
        "descriptor_deferred_cache": 0xA5,
    }
    sample[field] = value
    constants = {
        "FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED": 2,
        "COMMITTING": 2,
        "COMPLETE": 3,
        subject.FAST_CACHE_ACCOUNTING_PENDING_CONSTANT: 0x3C,
    }
    with pytest.raises(subject.Phase5StressError, match=message):
        subject._validate_vertical_descriptor_lifecycle(
            vertical, sample, constants, path="fixture"
        )


def test_sameboy_descriptor_completion_uses_linked_constant_not_literal_state() -> None:
    driver = (ROOT / subject.DRIVER_SOURCE).read_text(encoding="utf-8")
    assert "--descriptor-complete-value" in driver
    assert "descriptor_complete_value << 4" in driver
    assert "(state_class & 0xF0) == 0x40" not in driver


def test_target_write_measurements_do_not_reuse_cycle_trace_slots(tmp_path) -> None:
    path = tmp_path / "capture.json"
    row = subject.ROWS[0]
    path.write_text(json.dumps({"samples": [{
        "public_target_writes": 37,
        "preparation_buffer_writes": 11,
    }]}), encoding="utf-8")
    diagnostics, proposal = subject._target_write_evidence(row, path, {})
    assert diagnostics["public_target_writes_within_interval"] == [37]
    assert diagnostics["preparation_buffer_writes"] == [11]
    assert diagnostics["descriptor_metadata_writes_included"] is False
    assert diagnostics["cycle_budget_role"] == "NONE"
    assert proposal is None


@pytest.mark.parametrize("samples", [31, 33])
def test_producer_rejects_nonexact_capture_before_identity_work(
    tmp_path, monkeypatch, samples: int
) -> None:
    monkeypatch.setattr(subject, "capture_identities", lambda *_: {})
    with pytest.raises(subject.Phase5StressError, match="exactly 32"):
        subject.produce(
            tmp_path, tmp_path, tmp_path / "results", tmp_path / "proposal",
            samples=samples,
        )


def test_reviewed_authority_comparison_pins_attempt_and_gates_semantics(
    tmp_path, monkeypatch,
) -> None:
    fresh = _proposal()
    reviewed = deepcopy(fresh)
    reviewed["schema"] = subject.REVIEWED_SCHEMA
    reviewed["reviewed"] = True
    reviewed["captures"] = [
        {"id": "run-1", "path": "attempt-9999/run-1/run.json", "sha256": "a" * 64},
        {"id": "run-2", "path": "attempt-9999/run-2/run.json", "sha256": "b" * 64},
    ]
    reviewed["evidence_files"] = [
        {"path": path, "sha256": "c" * 64}
        for path in subject._expected_evidence_paths("attempt-9999")
    ]
    reviewed_path = tmp_path / "reviewed.json"
    reviewed_path.write_text(subject._canonical(reviewed), encoding="utf-8")
    monkeypatch.setattr(subject, "verify", lambda *_args, **_kwargs: fresh)

    with pytest.raises(subject.Phase5StressError, match="capture identity"):
        subject.compare_reviewed_authority(
            tmp_path, tmp_path, tmp_path / "fresh", reviewed_path
        )

    reviewed["captures"] = deepcopy(fresh["captures"])
    reviewed["evidence_files"] = deepcopy(fresh["evidence_files"])
    reviewed_path.write_text(subject._canonical(reviewed), encoding="utf-8")
    subject.compare_reviewed_authority(tmp_path, tmp_path, tmp_path / "fresh", reviewed_path)

    reviewed["north_retry_evidence"][0]["samples"][0][
        "producer_payload_sha256"
    ] = "2" * 64
    reviewed_path.write_text(subject._canonical(reviewed), encoding="utf-8")
    with pytest.raises(subject.Phase5StressError, match="differs"):
        subject.compare_reviewed_authority(tmp_path, tmp_path, tmp_path / "fresh", reviewed_path)

    reviewed = deepcopy(fresh)
    reviewed["schema"] = subject.REVIEWED_SCHEMA
    reviewed["reviewed"] = True
    reviewed["comparison"]["minimum_natural_executions_per_path_per_run"] = 33
    reviewed_path.write_text(subject._canonical(reviewed), encoding="utf-8")
    with pytest.raises(subject.Phase5StressError, match="comparison contract"):
        subject.compare_reviewed_authority(tmp_path, tmp_path, tmp_path / "fresh", reviewed_path)


def _mock_pinned_regeneration(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], list[dict[str, str]], dict[str, bytes]]:
    template = _proposal()
    payloads = {
        "attempt-0004/run-1/run.json": b"authenticated-run-1",
        "attempt-0004/run-2/run.json": b"authenticated-run-2",
    }
    refs = deepcopy(template["evidence_files"])
    for item in refs:
        path = item["path"]
        if path in payloads:
            item["sha256"] = __import__("hashlib").sha256(payloads[path]).hexdigest()
    semantic_names = {
        "timing_rows", "descriptor_write_counts", "write_diagnostics",
        "pressure_accounting", "north_retry_evidence",
        "combined_serialized_drain", "combined_semantic_public_write_breakdown",
        "comparison", "boundary_matrix",
    }
    derived = {name: deepcopy(template[name]) for name in semantic_names}
    monkeypatch.setattr(
        subject, "_load_pinned_evidence",
        lambda *_args, **_kwargs: (deepcopy(refs), dict(payloads)),
    )
    monkeypatch.setattr(
        subject, "_derive_authenticated_evidence",
        lambda *_args, **_kwargs: deepcopy(derived),
    )
    monkeypatch.setattr(
        subject, "capture_identities",
        lambda *_args, **_kwargs: deepcopy(template["identities"]),
    )
    monkeypatch.setattr(
        subject, "_case_manifest_binding",
        lambda *_args, **_kwargs: deepcopy(template["case_manifest"]),
    )
    monkeypatch.setattr(
        subject, "_production_admission_binding",
        lambda *_args, **_kwargs: deepcopy(template["production_admission"]),
    )
    monkeypatch.setattr(
        subject, "_boundary_threshold_contract",
        lambda *_args, **_kwargs: deepcopy(
            template["boundary_matrix"]["threshold_contract"]
        ),
    )
    return template, refs, payloads


def test_pinned_evidence_loader_authenticates_exact_reviewed_tree() -> None:
    refs, payloads = subject._load_pinned_evidence(
        ROOT / "test-results/full-color-phase5"
    )
    assert len(refs) == subject.PINNED_REVIEW_FILE_COUNT == 3336
    assert len(payloads) == 3336
    assert subject._artifact_tree_sha256(refs) == subject.PINNED_REVIEW_TREE_SHA256


def test_evidence_only_regeneration_writes_one_verified_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _template, refs, _payloads = _mock_pinned_regeneration(monkeypatch)
    output = tmp_path / subject.PROPOSAL_OUTPUT_PATH
    output.parent.mkdir(parents=True)
    canonical = tmp_path / subject.REVIEWED_PATH
    load_calls = 0
    real_load = subject._load_pinned_evidence

    def count_loads(*args, **kwargs):
        nonlocal load_calls
        load_calls += 1
        return real_load(*args, **kwargs)

    monkeypatch.setattr(subject, "_load_pinned_evidence", count_loads)
    before_files = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*") if path.is_file()
    )
    regenerated = subject.regenerate_proposal_from_pinned_evidence(
        tmp_path, tmp_path, tmp_path / "evidence", output,
    )
    assert load_calls == 3
    assert regenerated["evidence_files"] == refs
    assert json.loads(output.read_text(encoding="utf-8")) == regenerated
    assert subject.verify(
        tmp_path, tmp_path, output, evidence_root=tmp_path / "evidence"
    ) == regenerated
    assert not canonical.exists()
    after_files = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*") if path.is_file()
    )
    assert after_files == [*before_files, subject.PROPOSAL_OUTPUT_PATH.as_posix()]


def _small_pinned_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, dict[str, bytes]]:
    evidence_root = tmp_path / "evidence"
    attempt = evidence_root / subject.PINNED_REVIEW_ATTEMPT
    attempt.mkdir(parents=True)
    payloads = {"a.bin": b"authenticated-a", "b.bin": b"authenticated-b"}
    for name, payload in payloads.items():
        (attempt / name).write_bytes(payload)
    refs = [
        {
            "path": f"{subject.PINNED_REVIEW_ATTEMPT}/{name}",
            "sha256": __import__("hashlib").sha256(payload).hexdigest(),
        }
        for name, payload in sorted(payloads.items())
    ]
    monkeypatch.setattr(subject, "PINNED_REVIEW_FILE_COUNT", len(refs))
    monkeypatch.setattr(
        subject, "PINNED_REVIEW_TREE_SHA256",
        subject._artifact_tree_sha256(refs),
    )
    return evidence_root, attempt, payloads


@pytest.mark.parametrize("mutation", ("omitted", "extra", "changed"))
def test_pinned_evidence_loader_rejects_static_nonexact_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    evidence_root, attempt, _payloads = _small_pinned_tree(tmp_path, monkeypatch)
    if mutation == "omitted":
        (attempt / "b.bin").unlink()
    elif mutation == "extra":
        (attempt / "extra.bin").write_bytes(b"extra")
    else:
        (attempt / "b.bin").write_bytes(b"changed")
    with pytest.raises(subject.Phase5StressError, match="count|digest"):
        subject._load_pinned_evidence(evidence_root)


@pytest.mark.parametrize(
    "mutation", ("extra-after-enumeration", "removal", "replacement", "attempt-swap")
)
def test_pinned_evidence_loader_rejects_tree_races_without_fd_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    evidence_root, attempt, payloads = _small_pinned_tree(tmp_path, monkeypatch)
    real_list = subject._list_regular_tree_from_fd
    real_read = subject._read_regular_at
    list_calls = 0
    mutation_done = False

    def enumerate_then_mutate(attempt_fd: int, attempt_name: str) -> list[str]:
        nonlocal list_calls, mutation_done
        paths = real_list(attempt_fd, attempt_name)
        list_calls += 1
        if list_calls == 1:
            if mutation == "extra-after-enumeration":
                (attempt / "extra.bin").write_bytes(b"late-extra")
                mutation_done = True
            elif mutation == "removal":
                (attempt / "b.bin").unlink()
                mutation_done = True
            elif mutation == "attempt-swap":
                moved = evidence_root / "attempt-moved"
                attempt.rename(moved)
                attempt.mkdir()
                for name, payload in payloads.items():
                    (attempt / name).write_bytes(payload)
                mutation_done = True
        return paths

    def read_then_replace(root_fd: int, relative: Path):
        nonlocal mutation_done
        result = real_read(root_fd, relative)
        if mutation == "replacement" and not mutation_done:
            replacement = attempt / "replacement.bin"
            replacement.write_bytes(payloads[relative.as_posix()])
            replacement.replace(attempt / relative)
            mutation_done = True
        return result

    monkeypatch.setattr(subject, "_list_regular_tree_from_fd", enumerate_then_mutate)
    monkeypatch.setattr(subject, "_read_regular_at", read_then_replace)
    fd_count_before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(
        subject.Phase5StressError,
        match="changed|hostile|binding|count|digest",
    ):
        subject._load_pinned_evidence(evidence_root)
    assert mutation_done
    assert len(os.listdir("/proc/self/fd")) == fd_count_before


@pytest.mark.parametrize("repository_input", (
    "engine/full_color/lifecycle.asm",
    "pokeyellow.gbc", "pokeyellow.map", "pokeyellow.sym",
    "pokeyellow_debug.gbc", "pokeyellow_debug.map", "pokeyellow_debug.sym",
    "pokeyellow_vc.gbc", "pokeyellow_vc.map", "pokeyellow_vc.sym",
    "pokeyellow_phase2_audit.gbc", "pokeyellow_phase2_audit.map",
    "pokeyellow_phase2_audit.sym",
    "specs/full-colors/definitions/phase5-stress-cases.json",
    "tools/rom_tests/full_color/phase5_stress.py",
    "tools/rom_tests/full_color/phase5_boundary.py",
    "tools/rom_tests/full_color/sameboy_phase5_driver.c",
    "tools/rom_tests/full_color/sameboy_phase5_setup.py",
    "tools/rom_tests/sameboy-phase5.lock.json",
    "test-results/full-color-tools/sameboy-v1.0.3/sameboy-phase5-driver",
    "test-results/full-color-phase5/attempt-0004/run-1/run.json",
    "specs/full-colors/evidence/phase5-stress.json",
))
def test_evidence_only_regeneration_rejects_every_repository_input_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repository_input: str,
) -> None:
    _mock_pinned_regeneration(monkeypatch)
    output = tmp_path / repository_input
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"authenticated-input-must-not-change")
    monkeypatch.setattr(
        subject, "_load_pinned_evidence",
        lambda *_args, **_kwargs: pytest.fail("evidence loaded before output rejection"),
    )
    with pytest.raises(subject.Phase5StressError, match="exact dedicated proposal path"):
        subject.regenerate_proposal_from_pinned_evidence(
            tmp_path, tmp_path, tmp_path / "evidence", output,
        )
    assert output.read_bytes() == b"authenticated-input-must-not-change"


@pytest.mark.parametrize("hostile", ("directory", "symlink", "hardlink", "parent-symlink", "alias"))
def test_evidence_only_regeneration_rejects_hostile_exact_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hostile: str,
) -> None:
    _mock_pinned_regeneration(monkeypatch)
    output = tmp_path / subject.PROPOSAL_OUTPUT_PATH
    backing = tmp_path / "backing.json"
    backing.write_text("unchanged", encoding="utf-8")
    if hostile == "parent-symlink":
        actual = tmp_path / "actual-test-results"
        (actual / "full-color-proposals").mkdir(parents=True)
        (tmp_path / "test-results").symlink_to(actual, target_is_directory=True)
    else:
        output.parent.mkdir(parents=True)
        if hostile == "directory":
            output.mkdir()
        elif hostile == "symlink":
            output.symlink_to(backing)
        elif hostile == "hardlink":
            output.hardlink_to(backing)
        elif hostile == "alias":
            output = output.parent / ".." / "full-color-proposals" / output.name
    with pytest.raises(
        subject.Phase5StressError,
        match="exact dedicated proposal path|regular|hostile",
    ):
        subject.regenerate_proposal_from_pinned_evidence(
            tmp_path, tmp_path, tmp_path / "evidence", output,
        )
    assert backing.read_text(encoding="utf-8") == "unchanged"


def test_evidence_only_regeneration_is_a_mutually_exclusive_cli_mode(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as failure:
        subject.main([
            "--root", str(tmp_path), "--tool-root", str(tmp_path),
            "--regenerate-proposal", "--verify", str(tmp_path / "proposal.json"),
            "--evidence-root", str(tmp_path / "evidence"),
            "--proposal-output", str(tmp_path / "output.json"),
        ])
    assert failure.value.code == 2


def test_reviewed_promotion_requires_explicit_authority_and_is_atomic(
    tmp_path, monkeypatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    target = tmp_path / subject.REVIEWED_PATH
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)

    with pytest.raises(subject.Phase5StressError, match="authority-reviewed"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, target,
            authority_reviewed=False,
        )

    promoted = subject.apply_reviewed_proposal(
        tmp_path, tmp_path, proposal_path, target,
        authority_reviewed=True, evidence_root=tmp_path,
    )
    assert json.loads(target.read_text(encoding="utf-8")) == promoted
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_reviewed_publication_preserves_existing_target_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    target = tmp_path / subject.REVIEWED_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"reviewed-old")
    target.chmod(0o664)
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)

    subject.apply_reviewed_proposal(
        tmp_path, tmp_path, proposal_path, target,
        authority_reviewed=True, evidence_root=tmp_path,
    )
    assert stat.S_IMODE(target.stat().st_mode) == 0o664
    assert not list(target.parent.glob(f".{target.name}.*"))


def test_reviewed_promotion_rejects_ci_noncanonical_and_hostile_target(
    tmp_path, monkeypatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    target = tmp_path / subject.REVIEWED_PATH
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    with pytest.raises(subject.Phase5StressError, match="canonical"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, target,
            authority_reviewed=True, evidence_root=tmp_path,
        )
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    with pytest.raises(subject.Phase5StressError, match="canonical evidence"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, tmp_path / "elsewhere.json",
            authority_reviewed=True, evidence_root=tmp_path,
        )
    second_link = tmp_path / "proposal-hardlink.json"
    second_link.hardlink_to(proposal_path)
    with pytest.raises(subject.Phase5StressError, match="single regular file"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, target,
            authority_reviewed=True, evidence_root=tmp_path,
        )
    second_link.unlink()
    monkeypatch.setenv("CI", "true")
    with pytest.raises(subject.Phase5StressError, match="forbidden"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, target,
            authority_reviewed=True, evidence_root=tmp_path,
        )
    monkeypatch.delenv("CI")
    target.parent.mkdir(parents=True)
    hostile = tmp_path / "hostile.json"
    hostile.write_text("do not replace", encoding="utf-8")
    target.symlink_to(hostile)
    with pytest.raises(subject.Phase5StressError, match="canonical|regular"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, target,
            authority_reviewed=True, evidence_root=tmp_path,
        )
    assert hostile.read_text(encoding="utf-8") == "do not replace"


@pytest.mark.parametrize("mutation", ("replace", "in-place", "parent-symlink"))
def test_reviewed_promotion_rejects_pinned_proposal_toctou(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    proposal = _proposal()
    proposal_dir = tmp_path / "incoming"
    proposal_dir.mkdir()
    proposal_path = proposal_dir / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    hostile_dir = tmp_path / "hostile-parent"
    hostile_dir.mkdir()
    (hostile_dir / "proposal.json").write_text(
        subject._canonical(proposal), encoding="utf-8"
    )

    def mutate(*_args: object, **_kwargs: object) -> dict[str, object]:
        if mutation == "replace":
            replacement = proposal_dir / "replacement.json"
            replacement.write_text(subject._canonical(proposal), encoding="utf-8")
            replacement.replace(proposal_path)
        elif mutation == "in-place":
            with proposal_path.open("r+b") as stream:
                stream.seek(0)
                stream.write(b" ")
                stream.flush()
                __import__("os").fsync(stream.fileno())
        else:
            moved = tmp_path / "moved-incoming"
            proposal_dir.rename(moved)
            proposal_dir.symlink_to(hostile_dir, target_is_directory=True)
        return proposal

    monkeypatch.setattr(subject, "_verify_raw", mutate)
    with pytest.raises(subject.Phase5StressError, match="proposal.*changed|parent changed"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, tmp_path / subject.REVIEWED_PATH,
            authority_reviewed=True, evidence_root=tmp_path,
        )


@pytest.mark.parametrize("mutation", ("omitted", "extra", "mixed-attempt"))
def test_evidence_reference_set_is_exact_and_attempt_local(mutation: str) -> None:
    proposal = _proposal()
    if mutation == "omitted":
        proposal["evidence_files"] = proposal["evidence_files"][1:]
    elif mutation == "extra":
        proposal["evidence_files"].append({
            "path": "attempt-0004/unexpected.bin", "sha256": "f" * 64,
        })
        proposal["evidence_files"].sort(key=lambda item: item["path"])
    else:
        proposal["evidence_files"][0]["path"] = "attempt-0003/foreign.bin"
    if mutation == "extra":
        # Shape validation permits arbitrary capture products; the pinned tree
        # comparison in verify is the authority that rejects undeclared/extra files.
        assert subject.validate_proposal(proposal) is proposal
    else:
        with pytest.raises(subject.Phase5StressError, match="omitted|escaped"):
            subject.validate_proposal(proposal)


def _retained_run_payloads(run_index: int = 1) -> tuple[dict, dict[str, bytes]]:
    attempt = ROOT / "test-results/full-color-phase5/attempt-0004"
    run_dir = attempt / f"run-{run_index}"
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    payloads = {
        f"attempt-0004/{path.relative_to(attempt).as_posix()}": path.read_bytes()
        for path in run_dir.rglob("*") if path.is_file()
    }
    return run, payloads


def test_authenticated_raw_and_frame_artifacts_are_derivation_authority() -> None:
    run, payloads = _retained_run_payloads()
    constants = subject._numeric_symbols(ROOT / f"{subject.AUDIT_PRODUCT}.sym")
    subject._validate_authenticated_run_artifacts(
        run, run_index=1, attempt_name="attempt-0004",
        payloads=payloads, constants=constants,
    )
    capture_path = "attempt-0004/run-1/row-00/sameboy/capture.json"
    hostile = dict(payloads)
    hostile[capture_path] = b"{}"
    hostile_run = deepcopy(run)
    hostile_run["rows"][0]["sameboy"]["raw_capture_sha256"] = (
        __import__("hashlib").sha256(b"{}").hexdigest()
    )
    hostile["attempt-0004/run-1/row-00/row.json"] = subject._canonical(
        hostile_run["rows"][0]
    ).encode("utf-8")
    with pytest.raises(subject.Phase5StressError, match="malformed SameBoy capture"):
        subject._validate_authenticated_run_artifacts(
            hostile_run, run_index=1, attempt_name="attempt-0004",
            payloads=hostile, constants=constants,
        )

    hostile = dict(payloads)
    frame_path = "attempt-0004/run-1/row-00/sameboy/frame-0031.ppm"
    hostile[frame_path] = b"P6\n1 1\n255\n\0\0\0"
    with pytest.raises(subject.Phase5StressError, match="noncanonical.*PPM"):
        subject._validate_authenticated_run_artifacts(
            run, run_index=1, attempt_name="attempt-0004",
            payloads=hostile, constants=constants,
        )


def test_reviewed_promotion_rejects_restored_same_inode_ctime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    original = proposal_path.stat()

    def restore_bytes(*_args: object, **_kwargs: object) -> dict[str, object]:
        payload = proposal_path.read_bytes()
        with proposal_path.open("r+b") as stream:
            stream.seek(0)
            stream.write(b" " if payload[:1] != b" " else b"{")
            stream.flush()
            os.fsync(stream.fileno())
            stream.seek(0)
            stream.write(payload)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        os.utime(proposal_path, ns=(original.st_atime_ns, original.st_mtime_ns))
        return proposal

    monkeypatch.setattr(subject, "_verify_raw", restore_bytes)
    with pytest.raises(subject.Phase5StressError, match="proposal changed"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, tmp_path / subject.REVIEWED_PATH,
            authority_reviewed=True, evidence_root=tmp_path,
        )


def test_publication_detached_parent_rolls_back_and_never_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)
    real_replace = subject.os.replace
    detached = tmp_path / "detached-specs"

    def detach_after_replace(src, dst, *args, **kwargs):
        result = real_replace(src, dst, *args, **kwargs)
        if str(src).endswith(".tmp") and dst == subject.REVIEWED_PATH.name:
            (tmp_path / "specs").rename(detached)
        return result

    monkeypatch.setattr(subject.os, "replace", detach_after_replace)
    with pytest.raises(subject.Phase5StressError, match="detached"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, tmp_path / subject.REVIEWED_PATH,
            authority_reviewed=True, evidence_root=tmp_path,
        )
    assert not (detached / "full-colors/evidence" / subject.REVIEWED_PATH.name).exists()
    assert not (tmp_path / subject.REVIEWED_PATH).exists()


def test_post_replace_fsync_failure_restores_old_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    target = tmp_path / subject.REVIEWED_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"reviewed-old")
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)
    real_fsync = subject.os.fsync
    calls = 0

    def fail_publication_fsync(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected parent fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(subject.os, "fsync", fail_publication_fsync)
    with pytest.raises(OSError, match="injected"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, target,
            authority_reviewed=True, evidence_root=tmp_path,
        )
    assert target.read_bytes() == b"reviewed-old"


def test_backup_cleanup_fsync_failure_restores_old_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    target = tmp_path / subject.REVIEWED_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"reviewed-old")
    target.chmod(0o664)
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)
    real_fsync = subject.os.fsync
    calls = 0

    def fail_backup_cleanup_fsync(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected backup cleanup fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(subject.os, "fsync", fail_backup_cleanup_fsync)
    previous_umask = os.umask(0o077)
    try:
        with pytest.raises(OSError, match="backup cleanup fsync"):
            subject.apply_reviewed_proposal(
                tmp_path, tmp_path, proposal_path, target,
                authority_reviewed=True, evidence_root=tmp_path,
            )
    finally:
        os.umask(previous_umask)
    assert target.read_bytes() == b"reviewed-old"
    assert stat.S_IMODE(target.stat().st_mode) == 0o664
    assert not list(target.parent.glob(f".{target.name}.*"))


def test_detach_during_backup_cleanup_is_caught_by_final_canonical_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    target = tmp_path / subject.REVIEWED_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"reviewed-old")
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)
    real_unlink = subject.os.unlink
    detached = tmp_path / "detached-specs"

    def detach_after_backup_cleanup(path, *args, **kwargs):
        result = real_unlink(path, *args, **kwargs)
        if str(path).endswith(".bak"):
            (tmp_path / "specs").rename(detached)
        return result

    monkeypatch.setattr(subject.os, "unlink", detach_after_backup_cleanup)
    with pytest.raises(subject.Phase5StressError, match="detached"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, target,
            authority_reviewed=True, evidence_root=tmp_path,
        )
    assert (detached / "full-colors/evidence" / target.name).read_bytes() == b"reviewed-old"
    assert not target.exists()
    assert not list((detached / "full-colors/evidence").glob(f".{target.name}.*"))


@pytest.mark.parametrize("fault", ("write", "fsync"))
def test_precommit_temp_io_failure_unlinks_temp_and_leaks_no_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    target = tmp_path / subject.REVIEWED_PATH
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)
    before_fds = len(list(Path("/proc/self/fd").iterdir()))
    if fault == "write":
        real_write = subject.os.write
        calls = 0

        def partial_then_fail(fd: int, data: bytes) -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(fd, data[:7])
            raise OSError("injected temporary write failure")

        monkeypatch.setattr(subject.os, "write", partial_then_fail)
        message = "write failure"
    else:
        def fail_temp_fsync(_fd: int) -> None:
            raise OSError("injected temporary fsync failure")

        monkeypatch.setattr(subject.os, "fsync", fail_temp_fsync)
        message = "fsync failure"

    with pytest.raises(OSError, match=message):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, target,
            authority_reviewed=True, evidence_root=tmp_path,
        )
    assert not target.exists()
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))
    assert len(list(Path("/proc/self/fd").iterdir())) == before_fds


def test_postcommit_close_failure_rolls_back_through_pinned_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    target = tmp_path / subject.REVIEWED_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"reviewed-old")
    parent_identity = (target.parent.stat().st_dev, target.parent.stat().st_ino)
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)
    real_close = subject.os.close
    injected = False

    def fail_closed_publication_parent(fd: int) -> None:
        nonlocal injected
        info = subject.os.fstat(fd)
        real_close(fd)
        if (
            not injected and target.exists() and stat.S_ISDIR(info.st_mode)
            and (info.st_dev, info.st_ino) == parent_identity
        ):
            injected = True
            raise OSError("injected committed close failure")

    monkeypatch.setattr(subject.os, "close", fail_closed_publication_parent)
    with pytest.raises(subject.Phase5StressError, match="cleanup failed after rollback"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, target,
            authority_reviewed=True, evidence_root=tmp_path,
        )
    assert injected
    assert target.read_bytes() == b"reviewed-old"


def test_rollback_failure_reports_uncertain_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    target = tmp_path / subject.REVIEWED_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"reviewed-old")
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)
    real_fsync = subject.os.fsync
    calls = 0

    def fail_publish_and_rollback_fsync(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise OSError("injected rollback durability failure")
        real_fsync(fd)

    monkeypatch.setattr(subject.os, "fsync", fail_publish_and_rollback_fsync)
    with pytest.raises(subject.Phase5StressError, match="UNCERTAIN PUBLICATION"):
        subject.apply_reviewed_proposal(
            tmp_path, tmp_path, proposal_path, target,
            authority_reviewed=True, evidence_root=tmp_path,
        )


def test_outer_apply_close_failure_cannot_override_committed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _proposal()
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(subject._canonical(proposal), encoding="utf-8")
    target = tmp_path / subject.REVIEWED_PATH
    monkeypatch.setattr(subject, "_verify_raw", lambda *_args, **_kwargs: proposal)
    proposal_identity = (proposal_path.stat().st_dev, proposal_path.stat().st_ino)
    real_close = subject.os.close
    injected = False

    def fail_outer_proposal_close(fd: int) -> None:
        nonlocal injected
        info = subject.os.fstat(fd)
        real_close(fd)
        if (
            not injected and target.exists()
            and (info.st_dev, info.st_ino) == proposal_identity
        ):
            injected = True
            raise OSError("injected outer close failure")

    monkeypatch.setattr(subject.os, "close", fail_outer_proposal_close)
    promoted = subject.apply_reviewed_proposal(
        tmp_path, tmp_path, proposal_path, target,
        authority_reviewed=True, evidence_root=tmp_path,
    )
    assert injected
    assert json.loads(target.read_text(encoding="utf-8")) == promoted


def test_unmarked_production_rom_or_sym_mutation_fails_exact_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_sha = subject._sha256

    def mutated(path: Path) -> str:
        if path.name == "pokeyellow.gbc":
            return "f" * 64
        return real_sha(path)

    monkeypatch.setattr(subject, "_sha256", mutated)
    with pytest.raises(
        subject.Phase5StressError,
        match="reviewed production baseline|product identity drifted",
    ):
        subject._production_admission_binding(ROOT)


@pytest.mark.parametrize("relative", (
    "specs/full-colors/evidence/map-background-content.json",
    "specs/full-colors/inventory/assignments.json",
    "specs/full-colors/inventory/mutations.json",
    "specs/full-colors/inventory/scenes.json",
    "specs/full-colors/inventory/writers.json",
    "specs/full-colors/definitions/phase1-audit-source-transition.json",
    "tools/rom_tests/full_color/conditional_source_authority.py",
))
def test_each_reviewed_production_dependency_mutation_fails_closed(
    monkeypatch: pytest.MonkeyPatch, relative: str,
) -> None:
    real_sha = subject._sha256

    def mutated(path: Path) -> str:
        if path.resolve() == (ROOT / relative).resolve():
            return "f" * 64
        return real_sha(path)

    monkeypatch.setattr(subject, "_sha256", mutated)
    with pytest.raises(subject.Phase5StressError, match="production admission source"):
        subject._production_admission_binding(ROOT)


@pytest.mark.parametrize("authority", (
    "map-snapshot", "assignments", "mutations", "scenes", "writers",
    "conditional-source",
))
def test_reviewed_production_dependency_semantics_are_revalidated(
    monkeypatch: pytest.MonkeyPatch, authority: str,
) -> None:
    if authority == "map-snapshot":
        real_read = subject._read_json

        def drifted_map_snapshot(path: Path):
            raw = real_read(path)
            if path.name == "map-background-content.json":
                raw["ledger"]["path"] = "wrong"
            return raw

        monkeypatch.setattr(subject, "_read_json", drifted_map_snapshot)
    elif authority == "conditional-source":
        def reject(*_args, **_kwargs):
            raise subject.ConditionalSourceAuthorityError("injected semantic drift")

        monkeypatch.setattr(subject, "validate_conditional_source_regions", reject)
    else:
        class DriftedAuthority:
            sha256 = "f" * 64

        loader = {
            "assignments": subject.DiscoveryAssignmentAuthority,
            "mutations": subject.MutationInventory,
            "scenes": subject.SceneInventory,
            "writers": subject.WriterInventory,
        }[authority]
        monkeypatch.setattr(loader, "load", lambda *_args: DriftedAuthority())
    with pytest.raises(subject.Phase5StressError, match="authority|semantics"):
        subject._production_admission_binding(ROOT)


def test_production_admission_is_derived_from_source_and_linked_products() -> None:
    binding = subject._production_admission_binding(ROOT)
    assert (binding["color_presented_maps"], binding["yellow_presented_maps"]) == (196, 28)
    assert binding["phase5_production_activation"] is False
    assert all(
        product["phase5_symbols"] == []
        and product["ownership_route_first_opcode"] == "c9"
        for product in binding["products"].values()
    )


def test_authenticated_semantics_reject_zeroed_timing_and_trace_hashes() -> None:
    first_rows = [_row_evidence(row) for row in subject.ROWS]
    second_rows = deepcopy(first_rows)
    for run_rows in (first_rows, second_rows):
        observation = run_rows[0]["sameboy"]["timing_observations"][0]
        observation["start_offset"] = 0
        observation["end_offset"] = 0
        observation["deadline_offset"] = 0
    with pytest.raises(subject.Phase5StressError, match="timing observation"):
        subject._derived_promoted_semantics(
            {"schema": subject.RUN_SCHEMA, "rows": first_rows},
            {"schema": subject.RUN_SCHEMA, "rows": second_rows},
            _proposal()["boundary_matrix"],
        )
    with pytest.raises(subject.Phase5StressError, match="SHA-256"):
        subject._require_hash("0" * 64, path="trace_sha256")

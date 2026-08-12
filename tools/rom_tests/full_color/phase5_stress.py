"""Produce and verify audit-only Phase 5 stress and timing evidence.

SameBoy is the numeric authority. PyBoy 2.7 independently checks natural
reachability and semantic/trace behavior, but its timing is never admitted as
cycle evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
from importlib import metadata
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import time
from typing import Any, Callable, Mapping, Sequence

from PIL import Image

from tools.rom_tests.emulator import Emulator
from tools.rom_tests.scenarios.new_game import reach_bedroom_overworld
from tools.rom_tests.scenarios.oaks_lab import (
    finish_rival_battle_and_leave_lab,
    follow_oak_and_receive_pikachu,
    walk_from_bedroom_to_pallet,
    walk_from_bedroom_to_oak,
)
from tools.rom_tests.scenarios.renderer_mode import move_cursor_to

from .phase2_audit_observability import (
    Phase2AuditError,
    Phase2AuditIdentity,
    _numeric_symbols,
)
from .sameboy_phase5_setup import (
    DRIVER_SOURCE,
    INSTALL_SCHEMA,
    LOCK_PATH,
    load_lock,
)
from .phase5_boundary import Phase5AuditRom
from .map_background_content import (
    LEDGER_PATH as MAP_BACKGROUND_LEDGER_PATH,
    MapBackgroundAuthority,
    MapBackgroundContentError,
    Presentation,
)
from .inventory import MutationInventory, SceneInventory, WriterInventory
from .discovery_assignment import DiscoveryAssignmentAuthority
from .conditional_source_authority import (
    ConditionalSourceAuthorityError,
    validate_regions as validate_conditional_source_regions,
)
from .snapshots import TimingRow


SCHEMA = "full-color-phase5-stress-proposal-v1"
RUN_SCHEMA = "full-color-phase5-stress-run-v1"
ROW_SCHEMA = "full-color-phase5-stress-row-v1"
REVIEWED_SCHEMA = "full-color-phase5-stress-reviewed-v1"
AUDIT_PRODUCT = "pokeyellow_phase2_audit"
REVIEWED_PATH = Path("specs/full-colors/evidence/phase5-stress.json")
PROPOSAL_OUTPUT_PATH = Path(
    "test-results/full-color-proposals/phase5-stress.proposal.json"
)
MINIMUM_EXECUTIONS = 32
NATURAL_VBLANK_DEADLINE_T_CYCLES = 9120
SCANLINE_GUARD_FLOOR_T_CYCLES = 912
INSTRUMENTATION_T_CYCLES = 0
USABLE_T_CYCLES = (
    NATURAL_VBLANK_DEADLINE_T_CYCLES - SCANLINE_GUARD_FLOOR_T_CYCLES
)
FRAME_STRIP_LENGTH = 5
PHASE5_STRESS_BYTES = 11
PHASE5_SCENARIO_BYTES = 11
PHASE2_TRACE_BYTES = 194
PYBOY_VERSION = "2.7.0"
PILLOW_VERSION = "12.3.0"
PRODUCTION_PRODUCTS = ("pokeyellow", "pokeyellow_debug", "pokeyellow_vc")
PINNED_REVIEW_ATTEMPT = "attempt-0004"
PINNED_REVIEW_FILE_COUNT = 3336
PINNED_REVIEW_TREE_SHA256 = (
    "8c37246cdd1865ef4e25f4c2d9cb2c0af12fa9397821cc195733772e8dae6a90"
)
PRODUCTION_BASELINE_IDENTITIES = {
    "pokeyellow": {
        "rom_sha256": "32649785eb15c48dd8150e3e1774b1a6cd3d07e5d4a1c31faa5ef77d921bef1b",
        "sym_sha256": "f8fd50c7fab32910d44a04644a39773e14d02428ff9a2a7514f6db2dfddd8929",
    },
    "pokeyellow_debug": {
        "rom_sha256": "c4efaee95d03a40f8d065f654bdf6c9275f644e3908dc46d99dc0d9dcf43f561",
        "sym_sha256": "b9b318fdca31f7d72e45d74168d05af6879bf41446420bb37730dbdf95616134",
    },
    "pokeyellow_vc": {
        "rom_sha256": "a0e3ba99a9206306554dfa28fba73a92d73455f3ff0949062d05b595c7eaef11",
        "sym_sha256": "a8aa2524b7f8a25dad45d670702fb9892481dd29c1a45d3b82f279a9a96d7100",
    },
}
PRODUCTION_GATE_SOURCE_IDENTITIES = {
    "main.asm": (
        "4b45d63771bdc30281cd8ac8f3497929f91c7e50af6c37c2f0eeb3609ccca162"
    ),
    "engine/full_color/passive_overworld.asm": (
        "4483216137e7e08c55fb3ae863ebf1a72dc17735bf92550ce115111f44ea1630"
    ),
    "engine/full_color/scheduler.asm": (
        "0b874fca62288b759e96b4b6b2b10715f3068438ea449de13dc9681819f50cbf"
    ),
    "engine/full_color/ownership.asm": (
        "b70b3bd9203defdad35c0f8294b3b943d5c223f40d4dbd2095bc9108ef885f22"
    ),
    "specs/full-colors/definitions/phase5-stress-cases.json": (
        "a949d3ba1d8cca961a0d19de55d699b242933bdd5e5dad08650f2f1ffde1c8c8"
    ),
    "specs/full-colors/evidence/map-background-content.json": (
        "635a07f56314c5001e4ff0283a02d2bad01f1c117f945da8803a5d4159b1f091"
    ),
    "specs/full-colors/inventory/assignments.json": (
        "7289e2c7fadc34169538e22993994d3f0f3f1bd4299b27732e6e2fc68f21b7e8"
    ),
    "specs/full-colors/inventory/mutations.json": (
        "5a824cfca268823bc964220ba15ae81aad418e765c04fcb46442736914ad1d8c"
    ),
    "specs/full-colors/inventory/scenes.json": (
        "49780a536a2c7e17edd41ddfe65178b11311c77b5d6581223631a02cea460a17"
    ),
    "specs/full-colors/inventory/writers.json": (
        "b954b343c38409018dd8df4874e99defa83864a8910afdd51aec9875092fc321"
    ),
    "specs/full-colors/definitions/phase1-audit-source-transition.json": (
        "7ed16d4fff5cc4bd6a74711a573224e74e640041d0d823472257e022dcf3a39d"
    ),
    "tools/rom_tests/full_color/conditional_source_authority.py": (
        "2042a20c67dfea61b784479f9e8ff6b851057e7251b72b309e0ef668010ba286"
    ),
}
PRODUCTION_PRESENTATION_SYMBOL = "PassiveFullColorIsPresentedSliceMap"
PRODUCTION_PRESENTATION_END_SYMBOL = "PassiveFullColorApplyMap"
PRODUCTION_PRESENTATION_MACHINE_CODE = bytes.fromhex(
    "fa66d3fe002816fe013821fe17301dfe032819fe0e2815fe112811afc9"
    "fa5dd3fe0b380cfe0c3804fe2538043e01a7c9afc9"
)
PRODUCTION_PHASE5_MARKERS = (
    "Phase5", "FULL_COLOR_PHASE5", "wFullColorPhase5",
)
MUTABLE_BOUNDARIES = (
    "FULL_COLOR_PHASE5_BOUNDARY_PREPARATION",
    "FULL_COLOR_PHASE5_BOUNDARY_OWNER_REVALIDATION",
    "FULL_COLOR_PHASE5_BOUNDARY_GENERATION_REVALIDATION",
    "FULL_COLOR_PHASE5_BOUNDARY_DESTINATION_REVALIDATION",
    "FULL_COLOR_PHASE5_BOUNDARY_BUDGET_REVALIDATION",
)
NATURAL_REQUEST_CLASSES = {
    "RC-P5-COMBINED-PRESSURE-PALLET": "FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED",
    "RC-P5-PARTY-RETURN-PALLET": "FULL_COLOR_REQUEST_MAP_RECTANGLE_PAIRED",
    "RC-P5-CONNECTION-PALLET-NORTH": "FULL_COLOR_REQUEST_MAP_CONNECTION_PAIRED",
}
BOUNDARY_REQUEST_CLASSES = {
    "RC-P5-COMBINED-PRESSURE-PALLET": "FULL_COLOR_REQUEST_MAP_ROW_PAIRED",
    "RC-P5-PARTY-RETURN-PALLET": "FULL_COLOR_REQUEST_MAP_ROW_PAIRED",
    "RC-P5-CONNECTION-PALLET-NORTH": "FULL_COLOR_REQUEST_MAP_ROW_PAIRED",
}
BOUNDARY_PAIRED_BASE_CONSTANT = "FULL_COLOR_PHASE5_CYCLES_PAIRED_BASE"
BOUNDARY_PAIRED_CELL_CONSTANT = "FULL_COLOR_PHASE5_CYCLES_PAIRED_CELL"

CONTROL_CONSTANT = "FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"
RESULT_PASSED_CONSTANT = "FULL_COLOR_PHASE5_SCENARIO_RESULT_PASSED"
STATE_COMPLETE_CONSTANT = "FULL_COLOR_PHASE5_SCENARIO_STATE_COMPLETE"
STATE_STABLE_CONSTANT = "FULL_COLOR_PHASE5_SCENARIO_STATE_STABLE"
LEDGER_ALL_CONSTANT = "FULL_COLOR_PHASE5_LEDGER_ALL"
BARRIER_STABLE_CONSTANT = "FULL_COLOR_PHASE5_BARRIER_STABLE"
FAST_CACHE_ACCOUNTING_PENDING_CONSTANT = (
    "FULL_COLOR_PHASE5_FAST_CACHE_ACCOUNTING_PENDING"
)
PARTY_DISPATCH_SCENARIO_CONSTANT = (
    "FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_YELLOW"
)
PARTY_RECONSTRUCTION_GUARD_START = (
    "FullColorPhase5PartyReconstructColorPresentationGuardStart"
)
PARTY_RECONSTRUCTION_GUARD_END = (
    "FullColorPhase5PartyReconstructColorPresentationGuardEnd"
)
FRESH_WINDOW_TOTAL_TIMEOUT_SECONDS = 7200
FRESH_WINDOW_SINGLE_TIMEOUT_SECONDS = 600
FRESH_WINDOW_ROW_IDS = frozenset({
    "palette", "vertical", "animation",
    "handoff-to-Yellow", "handoff-to-Color", "reconstruct-Color",
    "connection",
})

SOURCE_IDENTITY_PATHS = (
    "main.asm",
    "layout.link",
    "constants/full_color_constants.asm",
    "ram/wram.asm",
    "engine/full_color/phase5_audit.asm",
    "engine/full_color/scheduler.asm",
    "engine/full_color/lifecycle.asm",
    "engine/full_color/transfers.asm",
    "engine/full_color/palettes.asm",
    "engine/full_color/oam.asm",
    "engine/gfx/sprite_oam.asm",
    "engine/gfx/mon_icons.asm",
    "engine/menus/party_menu.asm",
    "engine/menus/start_sub_menus.asm",
    "home/vblank.asm",
    "home/overworld.asm",
    "home/pokemon.asm",
    "tools/rom_tests/full_color/phase5_boundary.py",
    "tools/rom_tests/full_color/phase5_stress.py",
    "tools/rom_tests/full_color/sameboy_phase5_driver.c",
    "tools/rom_tests/full_color/sameboy_phase5_setup.py",
    "tools/rom_tests/sameboy-phase5.lock.json",
    "specs/full-colors/definitions/phase5-stress-cases.json",
)


class Phase5StressError(AssertionError):
    """Phase 5 evidence is incomplete, stale, or semantically invalid."""


@dataclass(frozen=True, slots=True)
class RowDescriptor:
    case_id: str
    row_id: str
    operation: str
    scenario_constant: str
    start_label: str
    end_label: str
    origin_label: str
    deadline_observation_label: str
    deadline_kind: str
    descriptor_class_constant: str | None = None
    semantic_write_kind: str | None = None

    @property
    def key(self) -> str:
        return f"{self.case_id}/{self.row_id}"

    @property
    def arm_constant(self) -> str:
        if self.case_id == "RC-P5-PARTY-RETURN-PALLET":
            return "FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_YELLOW"
        if self.case_id == "RC-P5-COMBINED-PRESSURE-PALLET":
            # The audit-only natural mainline producer is intentionally armed
            # once for the combined case. Individual row scenario IDs describe
            # linked observation surfaces; they are not synthetic dispatchers.
            return "FULL_COLOR_PHASE5_SCENARIO_COMBINED_VBLANK"
        return self.scenario_constant


ROWS = (
    RowDescriptor(
        "RC-P5-COMBINED-PRESSURE-PALLET", "VBlank", "combined pressure VBlank",
        "FULL_COLOR_PHASE5_SCENARIO_COMBINED_VBLANK",
        "FullColorPhase5VBlankOrigin", "FullColorPhase5CombinedVBlankEnd",
        "FullColorPhase5VBlankOrigin", "FullColorPhase5VBlankHandlerEnd", "FIXED_VBLANK",
    ),
    RowDescriptor(
        "RC-P5-COMBINED-PRESSURE-PALLET", "palette", "palette publication",
        "FULL_COLOR_PHASE5_SCENARIO_PALETTE",
        "FullColorPhase5PaletteStart", "FullColorPhase5PaletteEnd",
        "FullColorPhase5VBlankOrigin", "FullColorPhase5VBlankHandlerEnd", "FIXED_VBLANK",
        "FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD", "EXTENT",
    ),
    RowDescriptor(
        "RC-P5-COMBINED-PRESSURE-PALLET", "vertical", "vertical paired transfer",
        "FULL_COLOR_PHASE5_SCENARIO_VERTICAL",
        "FullColorPhase5VerticalStart", "FullColorPhase5VerticalEnd",
        "FullColorPhase5VBlankOrigin", "FullColorPhase5VBlankHandlerEnd", "FIXED_VBLANK",
        "FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED", "PAIRED_PLANES",
    ),
    RowDescriptor(
        "RC-P5-COMBINED-PRESSURE-PALLET", "animation", "animated terrain replacement",
        "FULL_COLOR_PHASE5_SCENARIO_ANIMATION",
        "FullColorPhase5AnimationStart", "FullColorPhase5AnimationEnd",
        "FullColorPhase5VBlankOrigin", "FullColorPhase5VBlankHandlerEnd", "FIXED_VBLANK",
        "FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT", "EXTENT",
    ),
    RowDescriptor(
        "RC-P5-COMBINED-PRESSURE-PALLET", "OAM-build", "maximum representative OAM build",
        "FULL_COLOR_PHASE5_SCENARIO_OAM_BUILD",
        "FullColorPhase5OAMBuildStart", "FullColorPhase5OAMBuildEnd",
        "FullColorPhase5OAMBuildOrigin", "FullColorPhase5OAMBuildDeadline",
        "LINKED_PRESENTATION",
        "FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA", "EXTENT",
    ),
    RowDescriptor(
        "RC-P5-COMBINED-PRESSURE-PALLET", "OAM-DMA", "complete OAM DMA",
        "FULL_COLOR_PHASE5_SCENARIO_OAM_DMA",
        "FullColorPhase5OAMDMAStart", "FullColorPhase5OAMDMAEnd",
        "FullColorPhase5VBlankOrigin", "FullColorPhase5VBlankHandlerEnd", "FIXED_VBLANK",
        "FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA", "EXTENT",
    ),
    RowDescriptor(
        "RC-P5-PARTY-RETURN-PALLET", "handoff-to-Yellow", "Party handoff to Yellow",
        "FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_YELLOW",
        "FullColorPhase5PartyHandoffToYellowStart", "FullColorPhase5PartyHandoffToYellowEnd",
        "FullColorPhase5PartyHandoffToYellowOrigin",
        "FullColorPhase5PartyHandoffToYellowDeadline", "LINKED_PRESENTATION",
    ),
    RowDescriptor(
        "RC-P5-PARTY-RETURN-PALLET", "handoff-to-Color", "Party handoff to Color",
        "FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_COLOR",
        "FullColorPhase5PartyHandoffToColorStart", "FullColorPhase5PartyHandoffToColorEnd",
        "FullColorPhase5PartyHandoffToColorOrigin",
        "FullColorPhase5PartyHandoffToColorDeadline", "LINKED_PRESENTATION",
    ),
    RowDescriptor(
        "RC-P5-PARTY-RETURN-PALLET", "reconstruct-Color", "fresh Color reconstruction",
        "FULL_COLOR_PHASE5_SCENARIO_PARTY_RECONSTRUCT_COLOR",
        "FullColorPhase5PartyReconstructColorStart", "FullColorPhase5PartyReconstructColorEnd",
        "FullColorPhase5PartyReconstructColorOrigin",
        "FullColorPhase5PartyReconstructColorDeadline", "LINKED_PRESENTATION",
    ),
    RowDescriptor(
        "RC-P5-CONNECTION-PALLET-NORTH", "connection", "Pallet north connection",
        "FULL_COLOR_PHASE5_SCENARIO_NORTH_CONNECTION",
        "FullColorPhase5NorthConnectionStart", "FullColorPhase5NorthConnectionEnd",
        "FullColorPhase5NorthConnectionOrigin",
        "FullColorPhase5NorthConnectionDeadline", "LINKED_PRESENTATION",
        "FULL_COLOR_REQUEST_MAP_CONNECTION_PAIRED", "PAIRED_PLANES",
    ),
)
ROW_BY_KEY = {row.key: row for row in ROWS}


def _capture_scenario_constant(row: RowDescriptor) -> str:
    # The stock StartMenu_Pokemon hook consumes one natural round-trip arm.
    # Color handoff and reconstruction are later intervals in that journey,
    # not independently dispatchable synthetic scenarios.
    if row.case_id == "RC-P5-PARTY-RETURN-PALLET":
        return PARTY_DISPATCH_SCENARIO_CONSTANT
    return row.arm_constant


def _observed_scenario_constant(row: RowDescriptor) -> str:
    # Combined pressure keeps the one natural carrier arm while each linked
    # sub-operation is observed. Party advances the carrier scenario as its
    # natural Yellow/Color lifecycle progresses.
    if row.case_id == "RC-P5-COMBINED-PRESSURE-PALLET":
        return row.arm_constant
    return row.scenario_constant


def _natural_movement_axis(row: RowDescriptor) -> str:
    """Select the stock Pallet scrolling path exercised by a timing row."""
    # Combined pressure must cross a real camera-strip boundary during its
    # measured 32-frame window.  The column route prepositions at (8, 12) and
    # pulses Right/Left; it naturally produces the canonical 2x18 paired unit
    # while the audit pressure producer supplies OAM/palette/animation.
    return "column" if row.row_id in {"VBlank", "vertical"} else "row"


TIMING_LABELS = frozenset(
    label
    for row in ROWS
    for label in (
        row.start_label, row.end_label, row.origin_label, row.deadline_observation_label,
    )
) | {PARTY_RECONSTRUCTION_GUARD_START, PARTY_RECONSTRUCTION_GUARD_END}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(raw: object) -> str:
    return json.dumps(raw, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"


def _write_json(path: Path, raw: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical(raw), encoding="utf-8")


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase5StressError(f"invalid JSON evidence {path}: {exc}") from exc


def _decode_canonical_json(payload: bytes, *, path: str) -> object:
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase5StressError(f"invalid JSON evidence {path}: {exc}") from exc
    if payload != _canonical(raw).encode("utf-8"):
        raise Phase5StressError(f"{path}: JSON evidence is not canonical")
    return raw


def _decode_strict_json(payload: bytes, *, path: str) -> object:
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate object key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"), object_pairs_hook=unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite number {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise Phase5StressError(f"invalid JSON evidence {path}: {exc}") from exc


def _open_directory_at(parent_fd: int, name: str) -> int:
    if not name or name in {".", ".."} or "/" in name:
        raise Phase5StressError("evidence path contains a hostile component")
    try:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise Phase5StressError(f"evidence directory {name!r} is hostile: {exc}") from exc


def _file_identity(item: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns,
        item.st_ctime_ns,
    )


def _read_regular_at(root_fd: int, relative: Path) -> tuple[bytes, tuple[int, int, int, int, int]]:
    if relative.is_absolute() or not relative.parts:
        raise Phase5StressError("evidence path must be root-relative")
    current = os.dup(root_fd)
    try:
        for component in relative.parts[:-1]:
            following = _open_directory_at(current, component)
            os.close(current)
            current = following
        name = relative.parts[-1]
        if not name or name in {".", ".."} or "/" in name:
            raise Phase5StressError("evidence path contains a hostile component")
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current)
        except OSError as exc:
            raise Phase5StressError(f"evidence file {relative} is hostile: {exc}") from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise Phase5StressError(f"evidence file {relative} is not a single regular file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
            identity = _file_identity(before)
            if identity != _file_identity(after):
                raise Phase5StressError(f"evidence file {relative} changed while being read")
            return b"".join(chunks), identity
        finally:
            os.close(descriptor)
    finally:
        os.close(current)


def _regular_identity_at(
    root_fd: int, relative: Path,
) -> tuple[int, int, int, int, int]:
    """Return a hostile-path-safe identity without consuming the file again."""
    if relative.is_absolute() or not relative.parts:
        raise Phase5StressError("evidence path must be root-relative")
    current = os.dup(root_fd)
    try:
        for component in relative.parts[:-1]:
            following = _open_directory_at(current, component)
            os.close(current)
            current = following
        name = relative.parts[-1]
        if not name or name in {".", ".."} or "/" in name:
            raise Phase5StressError("evidence path contains a hostile component")
        try:
            item = os.stat(name, dir_fd=current, follow_symlinks=False)
        except OSError as exc:
            raise Phase5StressError(
                f"evidence file {relative} changed after being read: {exc}"
            ) from exc
        if not stat.S_ISREG(item.st_mode) or item.st_nlink != 1:
            raise Phase5StressError(
                f"evidence file {relative} is no longer a single regular file"
            )
        return _file_identity(item)
    finally:
        os.close(current)


def _artifact_refs(attempt: Path, results: Path) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for path in sorted(attempt.rglob("*")):
        relative = path.relative_to(results)
        item_stat = path.lstat()
        if stat.S_ISDIR(item_stat.st_mode):
            continue
        if not stat.S_ISREG(item_stat.st_mode) or item_stat.st_nlink != 1:
            raise Phase5StressError(f"capture artifact {relative} is not a single regular file")
        if path.name == "proposal.json" and path.parent == attempt:
            continue
        refs.append({"path": relative.as_posix(), "sha256": _sha256(path)})
    return refs


def _artifact_tree_sha256(refs: Sequence[Mapping[str, str]]) -> str:
    return hashlib.sha256(_canonical(list(refs)).encode("utf-8")).hexdigest()


def _expected_evidence_paths(attempt_name: str) -> list[str]:
    paths = [
        f"{attempt_name}/boundary-run-1/matrix.json",
        f"{attempt_name}/boundary-run-2/matrix.json",
    ]
    for run in ("run-1", "run-2"):
        paths.append(f"{attempt_name}/{run}/run.json")
        for row_index in range(len(ROWS)):
            base = f"{attempt_name}/{run}/row-{row_index:02d}"
            paths.append(f"{base}/row.json")
            for device in ("pyboy", "sameboy"):
                paths.append(f"{base}/{device}/capture.json")
                paths.extend(
                    f"{base}/{device}/frame-{sample:04d}.ppm"
                    for sample in range(MINIMUM_EXECUTIONS)
                )
                paths.extend(
                    f"{base}/{device}/strip-{strip_index:02d}.png"
                    for strip_index in range(FRAME_STRIP_LENGTH)
                )
    return sorted(paths)


def _list_regular_tree_from_fd(attempt_fd: int, attempt_name: str) -> list[str]:
    """Enumerate one already-pinned attempt directory without reopening its name."""
    paths: list[str] = []

    def visit(directory_fd: int, prefix: tuple[str, ...]) -> None:
        for name in sorted(os.listdir(directory_fd)):
            item = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            relative = (*prefix, name)
            if stat.S_ISDIR(item.st_mode):
                child = _open_directory_at(directory_fd, name)
                try:
                    visit(child, relative)
                finally:
                    os.close(child)
            elif stat.S_ISREG(item.st_mode) and item.st_nlink == 1:
                if relative != ("proposal.json",):
                    paths.append("/".join((attempt_name, *relative)))
            else:
                raise Phase5StressError(
                    f"Phase 5 evidence tree contains hostile entry {'/'.join(relative)}"
                )

    visit(attempt_fd, ())
    return sorted(paths)


def _list_regular_tree_at(root_fd: int, attempt_name: str) -> list[str]:
    attempt_fd = _open_directory_at(root_fd, attempt_name)
    try:
        return _list_regular_tree_from_fd(attempt_fd, attempt_name)
    finally:
        os.close(attempt_fd)


def _require_hash(value: object, *, path: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
        or value == "0" * 64
    ):
        raise Phase5StressError(f"{path}: expected exact SHA-256")
    return value


def _case_manifest_binding(root: Path) -> dict[str, object]:
    path = root / "specs/full-colors/definitions/phase5-stress-cases.json"
    raw = _read_json(path)
    if not isinstance(raw, dict) or raw.get("schema") != "full-color-phase5-stress-cases-v1":
        raise Phase5StressError("Phase 5 case manifest has the wrong schema")
    cases = raw.get("cases")
    if not isinstance(cases, list) or len(cases) != len(NATURAL_REQUEST_CLASSES):
        raise Phase5StressError("Phase 5 case manifest does not cover all stable cases")
    inventory = raw.get("inventory")
    writers = inventory.get("writers") if isinstance(inventory, dict) else None
    if not isinstance(writers, list):
        raise Phase5StressError("Phase 5 case manifest writer inventory is malformed")
    writer_inventory: dict[str, dict[str, object]] = {}
    for writer in writers:
        writer_id = writer.get("id") if isinstance(writer, dict) else None
        if not isinstance(writer_id, str) or not writer_id.startswith("WR-"):
            raise Phase5StressError("Phase 5 case manifest contains a malformed writer")
        if writer_id in writer_inventory:
            raise Phase5StressError(f"Phase 5 case manifest duplicates writer {writer_id}")
        writer_inventory[writer_id] = writer
    bindings: list[dict[str, object]] = []
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise Phase5StressError("Phase 5 case manifest contains a malformed case")
        case_id = case["id"]
        expected_rows = [row.key for row in ROWS if row.case_id == case_id]
        if (
            case_id not in NATURAL_REQUEST_CLASSES
            or case.get("natural_request_class") != NATURAL_REQUEST_CLASSES[case_id]
            or case.get("boundary_request_class") != BOUNDARY_REQUEST_CLASSES[case_id]
            or case.get("timing_rows") != expected_rows
        ):
            raise Phase5StressError(f"{case_id}: case manifest timing/request binding drifted")
        binding = {
            "id": case_id,
            "natural_request_class": NATURAL_REQUEST_CLASSES[case_id],
            "boundary_request_class": BOUNDARY_REQUEST_CLASSES[case_id],
            "timing_rows": expected_rows,
        }
        for name in ("writer_ids", "scene_ids", "mutation_ids", "dependency_inventory_rows"):
            values = case.get(name)
            if (
                not isinstance(values, list)
                or any(not isinstance(value, str) or not value for value in values)
                or values != list(dict.fromkeys(values))
            ):
                raise Phase5StressError(f"{case_id}: malformed {name} binding")
            binding[name] = values
        missing_writers = [
            writer_id for writer_id in binding["writer_ids"]
            if writer_id not in writer_inventory
        ]
        if missing_writers:
            raise Phase5StressError(
                f"{case_id}: case references missing writers {missing_writers}"
            )
        # Keep the exact inventory records in reviewed evidence, not merely their
        # identifiers.  New reconstruction auxiliaries and presentation-barrier
        # seams therefore bind their source and linked symbol as soon as the case
        # manifest assigns them to a stable case.
        binding["writer_bindings"] = [
            writer_inventory[writer_id] for writer_id in binding["writer_ids"]
        ]
        dependency_roots = case.get("dependency_roots")
        if not isinstance(dependency_roots, list):
            raise Phase5StressError(f"{case_id}: malformed dependency_roots binding")
        for dependency in dependency_roots:
            if (
                not isinstance(dependency, dict)
                or set(dependency) not in (
                    {"row_id", "executed_root", "scope"},
                    {"row_id", "executed_root", "linked_origin", "scope"},
                )
                or not isinstance(dependency.get("row_id"), str)
                or dependency["row_id"] not in binding["dependency_inventory_rows"]
                or not isinstance(dependency.get("executed_root"), str)
                or not dependency["executed_root"]
                or not isinstance(dependency.get("scope"), str)
                or not dependency["scope"]
                or (
                    "linked_origin" in dependency
                    and (
                        not isinstance(dependency["linked_origin"], str)
                        or not dependency["linked_origin"]
                    )
                )
            ):
                raise Phase5StressError(f"{case_id}: malformed dependency_roots binding")
        if [root["row_id"] for root in dependency_roots] != binding["dependency_inventory_rows"]:
            raise Phase5StressError(
                f"{case_id}: dependency roots do not exactly cover dependency inventory"
            )
        binding["dependency_roots"] = dependency_roots
        bindings.append(binding)
    if [binding["id"] for binding in bindings] != list(NATURAL_REQUEST_CLASSES):
        raise Phase5StressError("Phase 5 case manifest order drifted")
    return {
        "path": path.relative_to(root).as_posix(),
        "schema": raw["schema"],
        "sha256": _sha256(path),
        "cases": bindings,
    }


def _symbol_names(path: Path) -> set[str]:
    names: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if not fields or line.startswith(";"):
            continue
        if len(fields) != 2:
            raise Phase5StressError(f"{path.name}:{number}: malformed symbol row")
        names.add(fields[1])
    return names


def _symbol_locations(path: Path) -> dict[str, tuple[int, int]]:
    locations: dict[str, tuple[int, int]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if not fields or line.startswith(";"):
            continue
        if len(fields) != 2:
            raise Phase5StressError(f"{path.name}:{number}: malformed symbol row")
        if ":" not in fields[0]:
            # RGBDS exports numeric constants in the same .sym file without a
            # banked address. Only linked labels participate in order checks.
            continue
        bank, address = fields[0].split(":", 1)
        try:
            locations[fields[1]] = (int(bank, 16), int(address, 16))
        except ValueError as exc:
            raise Phase5StressError(
                f"{path.name}:{number}: malformed symbol location"
            ) from exc
    return locations


def _source_identities(root: Path) -> dict[str, str]:
    identities: dict[str, str] = {}
    for relative_name in SOURCE_IDENTITY_PATHS:
        relative = Path(relative_name)
        path = root / relative
        if not path.is_file():
            raise Phase5StressError(f"missing Phase 5 source identity: {relative_name}")
        identities[relative.as_posix()] = _sha256(path)
    return identities


def _load_tool_manifest(root: Path, tool_root: Path) -> dict[str, object]:
    manifest_path = tool_root / "install.json"
    raw = _read_json(manifest_path)
    if not isinstance(raw, dict) or raw.get("schema") != INSTALL_SCHEMA:
        raise Phase5StressError("SameBoy install manifest has the wrong schema")
    if raw.get("lock") != load_lock(root):
        raise Phase5StressError("SameBoy install does not match the repository pin")
    artifacts = raw.get("artifacts")
    if not isinstance(artifacts, dict):
        raise Phase5StressError("SameBoy install lacks exact artifacts")
    for name in ("driver", "library", "boot_rom"):
        item = artifacts.get(name)
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise Phase5StressError(f"SameBoy install artifact {name} is malformed")
        path = tool_root / str(item["path"])
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise Phase5StressError(f"SameBoy install artifact {name} drifted")
    if raw.get("driver_source_sha256") != _sha256(root / DRIVER_SOURCE):
        raise Phase5StressError("SameBoy driver source changed after setup")
    return raw


def _rom_interval(root: Path, product: str, start: str, end: str) -> bytes:
    locations = _symbol_locations(root / f"{product}.sym")
    try:
        start_bank, start_address = locations[start]
        end_bank, end_address = locations[end]
    except KeyError as exc:
        raise Phase5StressError(f"{product}: required linked symbol is absent: {exc}") from exc
    if start_bank != end_bank or end_address <= start_address:
        raise Phase5StressError(f"{product}: linked admission interval is malformed")
    offset = start_address if start_bank == 0 else start_bank * 0x4000 + start_address - 0x4000
    payload = (root / f"{product}.gbc").read_bytes()[offset:offset + end_address - start_address]
    if len(payload) != end_address - start_address:
        raise Phase5StressError(f"{product}: linked admission interval is truncated")
    return payload


def _production_admission_binding(root: Path) -> dict[str, object]:
    root = root.resolve()
    for relative, expected_hash in PRODUCTION_GATE_SOURCE_IDENTITIES.items():
        if _sha256(root / relative) != expected_hash:
            raise Phase5StressError(
                f"production admission source {relative} differs from reviewed baseline"
            )
    try:
        reviewed_map_snapshot = _read_json(
            root / "specs/full-colors/evidence/map-background-content.json"
        )
        authority = MapBackgroundAuthority.load(root)
        inventory_root = root / "specs/full-colors/inventory"
        assignments = DiscoveryAssignmentAuthority.load(
            inventory_root / "assignments.json"
        )
        mutations = MutationInventory.load(inventory_root / "mutations.json")
        scenes = SceneInventory.load(inventory_root / "scenes.json")
        writers = WriterInventory.load(inventory_root / "writers.json")
        transition = _read_json(
            root / "specs/full-colors/definitions/phase1-audit-source-transition.json"
        )
        transition_keys = {
            "schema", "reviewed_source_sha256", "current_source_sha256",
            "baseline_manifest_sha256", "reviewed_delta_paths",
            "subject_rebindings", "rom_subject_rebindings",
            "audit_only_source_regions", "product_identities",
        }
        if (
            not isinstance(transition, dict)
            or set(transition) != transition_keys
            or transition.get("schema") != "full-color-production-source-transition-v4"
        ):
            raise Phase5StressError("production source transition is malformed")
        validate_conditional_source_regions(
            root,
            transition["audit_only_source_regions"],
            transition["product_identities"],
            transition["reviewed_delta_paths"],
        )
    except (
        MapBackgroundContentError,
        ConditionalSourceAuthorityError, OSError, UnicodeError, ValueError,
    ) as exc:
        raise Phase5StressError(f"production map authority is invalid: {exc}") from exc
    reviewed_ledger = reviewed_map_snapshot.get("ledger")
    if (
        set(reviewed_map_snapshot) != {
            "schema", "ledger", "source", "products", "parity_sha256"
        }
        or reviewed_map_snapshot.get("schema")
        != "full-color-map-background-snapshot-v1"
        or not isinstance(reviewed_ledger, dict)
        or reviewed_ledger.get("path") != MAP_BACKGROUND_LEDGER_PATH.as_posix()
        or reviewed_ledger.get("sha256") != _sha256(root / MAP_BACKGROUND_LEDGER_PATH)
        or assignments.sha256 != PRODUCTION_GATE_SOURCE_IDENTITIES[
            "specs/full-colors/inventory/assignments.json"
        ]
        or mutations.sha256 != PRODUCTION_GATE_SOURCE_IDENTITIES[
            "specs/full-colors/inventory/mutations.json"
        ]
        or scenes.sha256 != PRODUCTION_GATE_SOURCE_IDENTITIES[
            "specs/full-colors/inventory/scenes.json"
        ]
        or writers.sha256 != PRODUCTION_GATE_SOURCE_IDENTITIES[
            "specs/full-colors/inventory/writers.json"
        ]
    ):
        raise Phase5StressError(
            "reviewed map-background dependency semantics differ from production authority"
        )
    reviewed_source = reviewed_map_snapshot.get("source")
    reviewed_products = reviewed_map_snapshot.get("products")
    if not isinstance(reviewed_source, dict) or not isinstance(reviewed_products, list):
        raise Phase5StressError("reviewed map-background evidence is malformed")
    source_authorities = reviewed_source.get("authorities")
    semantic = reviewed_source.get("semantic")
    if (
        not isinstance(source_authorities, list)
        or not isinstance(semantic, dict)
        or any(
            not isinstance(item, dict)
            or set(item) != {"path", "sha256", "size"}
            or _sha256(root / str(item["path"])) != item["sha256"]
            or (root / str(item["path"])).stat().st_size != item["size"]
            for item in source_authorities
        )
    ):
        raise Phase5StressError("reviewed map-background source authority drifted")
    semantic_maps = semantic.get("maps")
    if not isinstance(semantic_maps, list) or [
        (row.get("id"), row.get("name"), row.get("presentation"))
        for row in semantic_maps if isinstance(row, dict)
    ] != [
        (row.id, row.name, row.presentation.value) for row in authority.maps
    ]:
        raise Phase5StressError("reviewed map-background map semantics drifted")
    product_rows = {
        row.get("product"): row for row in reviewed_products if isinstance(row, dict)
    }
    for product in PRODUCTION_PRODUCTS:
        row = product_rows.get(product)
        artifacts = row.get("artifacts") if isinstance(row, dict) else None
        if not isinstance(artifacts, dict):
            raise Phase5StressError("reviewed map-background product evidence is malformed")
        for kind, suffix in (("rom", "gbc"), ("map", "map"), ("sym", "sym")):
            artifact = artifacts.get(kind)
            if (
                not isinstance(artifact, dict)
                or artifact.get("path") != f"{product}.{suffix}"
                or artifact.get("sha256") != _sha256(root / f"{product}.{suffix}")
            ):
                raise Phase5StressError(
                    f"{product}: reviewed map-background product identity drifted"
                )
    color = sum(row.presentation is Presentation.COLOR for row in authority.maps)
    yellow = sum(row.presentation is Presentation.YELLOW for row in authority.maps)
    manifest_path = root / "specs/full-colors/definitions/phase5-stress-cases.json"
    manifest = _read_json(manifest_path)
    runtime_admission = manifest.get("runtime_admission") if isinstance(manifest, dict) else None
    expected_admission = {
        "color_presented_maps": color,
        "yellow_presented_maps": yellow,
        "changed": False,
    }
    if runtime_admission != expected_admission or (color, yellow) != (196, 28):
        raise Phase5StressError("Phase 5 manifest or source authority changed production admission")
    products: dict[str, object] = {}
    for product in PRODUCTION_PRODUCTS:
        actual_baseline = {
            "rom_sha256": _sha256(root / f"{product}.gbc"),
            "sym_sha256": _sha256(root / f"{product}.sym"),
        }
        if actual_baseline != PRODUCTION_BASELINE_IDENTITIES[product]:
            raise Phase5StressError(
                f"{product}: shipped ROM/SYM differs from the reviewed production baseline"
            )
        symbols = _symbol_names(root / f"{product}.sym")
        leaked = sorted(
            name for name in symbols
            if any(marker in name for marker in PRODUCTION_PHASE5_MARKERS)
        )
        if leaked:
            raise Phase5StressError(
                f"{product} links Phase 5 activation surface: {', '.join(leaked)}"
            )
        predicate = _rom_interval(
            root, product, PRODUCTION_PRESENTATION_SYMBOL,
            PRODUCTION_PRESENTATION_END_SYMBOL,
        )
        if predicate != PRODUCTION_PRESENTATION_MACHINE_CODE:
            raise Phase5StressError(f"{product}: linked production admission opcode drifted")
        route_bank, route_address = _symbol_locations(
            root / f"{product}.sym"
        )["RouteRendererOwnershipVBlank"]
        route_offset = (
            route_address if route_bank == 0
            else route_bank * 0x4000 + route_address - 0x4000
        )
        with (root / f"{product}.gbc").open("rb") as rom:
            rom.seek(route_offset)
            route_opcode = rom.read(1)
        if route_opcode != b"\xc9":
            raise Phase5StressError(f"{product}: Phase 5 ownership route became active")
        products[product] = {
            **actual_baseline,
            "presentation_machine_code_sha256": hashlib.sha256(predicate).hexdigest(),
            "presentation_machine_code": predicate.hex(),
            "phase5_symbols": [],
            "ownership_route_first_opcode": "c9",
        }
    return {
        **expected_admission,
        "map_authority": {
            "path": MAP_BACKGROUND_LEDGER_PATH.as_posix(),
            "sha256": _sha256(root / MAP_BACKGROUND_LEDGER_PATH),
            "identity_sha256": authority.identity_sha256,
            "map_count": len(authority.maps),
        },
        "manifest": {
            "path": "specs/full-colors/definitions/phase5-stress-cases.json",
            "sha256": _sha256(manifest_path),
        },
        "presentation_source": {
            "path": "engine/full_color/passive_overworld.asm",
            "sha256": _sha256(root / "engine/full_color/passive_overworld.asm"),
            "symbol": PRODUCTION_PRESENTATION_SYMBOL,
        },
        "products": products,
        "phase5_production_activation": False,
    }


def capture_identities(root: Path, tool_root: Path) -> dict[str, object]:
    root = root.resolve()
    identity = Phase2AuditIdentity.from_root(root)
    audit_symbols = _symbol_names(root / f"{AUDIT_PRODUCT}.sym")
    missing = sorted(TIMING_LABELS - audit_symbols)
    if missing:
        raise Phase5StressError(
            "audit product lacks Phase 5 timing symbols: " + ", ".join(missing)
        )
    audit_locations = _symbol_locations(root / f"{AUDIT_PRODUCT}.sym")
    reconstruct = next(row for row in ROWS if row.row_id == "reconstruct-Color")
    reconstruct_end = audit_locations[reconstruct.end_label]
    guard_start = audit_locations[PARTY_RECONSTRUCTION_GUARD_START]
    guard_end = audit_locations[PARTY_RECONSTRUCTION_GUARD_END]
    deadline = audit_locations[reconstruct.deadline_observation_label]
    if not (
        reconstruct_end[0] == deadline[0]
        and reconstruct_end[1] < deadline[1]
        and guard_start[0] == guard_end[0]
        and guard_start[0] != reconstruct_end[0]
        and guard_start[1] + 7 == guard_end[1]
    ):
        raise Phase5StressError(
            "Party reconstruction guard must link as a seven-byte ROMX interval "
            "between ordered Home End/Deadline seams"
        )
    guard_file_offset = (
        guard_start[1]
        if guard_start[0] == 0
        else guard_start[0] * 0x4000 + guard_start[1] - 0x4000
    )
    with (root / f"{AUDIT_PRODUCT}.gbc").open("rb") as rom:
        rom.seek(guard_file_offset)
        guard_bytes = rom.read(7)
    if guard_bytes != bytes.fromhex("c506370520fdc1"):
        raise Phase5StressError(
            "Party reconstruction presentation guard machine code drifted"
        )
    for product in PRODUCTION_PRODUCTS:
        symbols = _symbol_names(root / f"{product}.sym")
        leaked = sorted(TIMING_LABELS & symbols)
        if leaked:
            raise Phase5StressError(
                f"{product} links audit-only Phase 5 timing symbols: {', '.join(leaked)}"
            )
    try:
        pyboy_version = metadata.version("pyboy")
    except metadata.PackageNotFoundError as exc:
        raise Phase5StressError("PyBoy is not installed") from exc
    if pyboy_version != PYBOY_VERSION:
        raise Phase5StressError(
            f"PyBoy behavioral cross-check must be exactly {PYBOY_VERSION}, got {pyboy_version}"
        )
    try:
        pillow_version = metadata.version("Pillow")
    except metadata.PackageNotFoundError as exc:
        raise Phase5StressError("Pillow frame-strip encoder is not installed") from exc
    if pillow_version != PILLOW_VERSION:
        raise Phase5StressError(
            f"Pillow frame-strip encoder must be exactly {PILLOW_VERSION}, "
            f"got {pillow_version}"
        )
    return {
        "audit_product": identity.to_dict(),
        "production_linkage": {
            product: {
                "rom_sha256": _sha256(root / f"{product}.gbc"),
                "sym_sha256": _sha256(root / f"{product}.sym"),
                "map_sha256": _sha256(root / f"{product}.map"),
                "phase5_timing_symbols": [],
            }
            for product in PRODUCTION_PRODUCTS
        },
        "source_files": _source_identities(root),
        "tools": {
            "sameboy": _load_tool_manifest(root, tool_root),
            "pyboy": {"role": "BEHAVIORAL_CROSS_CHECK_ONLY", "version": pyboy_version},
            "pillow": {"role": "FRAME_STRIP_ENCODER", "version": pillow_version},
            "phase5_producer_sha256": _sha256(Path(__file__)),
            "phase5_boundary_producer_sha256": _sha256(
                Path(__file__).with_name("phase5_boundary.py")
            ),
            "sameboy_setup_producer_sha256": _sha256(
                Path(__file__).with_name("sameboy_phase5_setup.py")
            ),
            "sameboy_lock_sha256": _sha256(root / LOCK_PATH),
        },
    }


def _driver_paths(tool_root: Path) -> tuple[Path, Path]:
    manifest = _read_json(tool_root / "install.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("artifacts"), dict):
        raise Phase5StressError("invalid SameBoy install manifest")
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)
    driver = artifacts.get("driver")
    boot = artifacts.get("boot_rom")
    if not isinstance(driver, dict) or not isinstance(boot, dict):
        raise Phase5StressError("SameBoy install manifest lacks driver or boot ROM")
    return tool_root / str(driver["path"]), tool_root / str(boot["path"])


def _convert_frame_strip(row_dir: Path, *, prefix: str, sample_count: int) -> list[dict[str, str]]:
    start = sample_count - FRAME_STRIP_LENGTH
    if start < 0:
        raise Phase5StressError("capture is too short for the required frame strip")
    result: list[dict[str, str]] = []
    for index in range(start, sample_count):
        source = row_dir / prefix / f"frame-{index:04d}.ppm"
        target = row_dir / prefix / f"strip-{index - start:02d}.png"
        if not source.is_file():
            raise Phase5StressError(f"missing frame evidence: {source}")
        with Image.open(source) as image:
            image.convert("RGB").save(target, format="PNG", optimize=False)
        result.append({"path": target.name, "sha256": _sha256(target)})
    return result


def _validate_sample_shape(
    raw: object,
    *,
    path: str,
    expect_ticks: bool,
    allow_end_at_deadline: bool = False,
) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise Phase5StressError(f"{path}: expected sample object")
    required = {
        "index", "key1", "scenario", "stress", "trace", "frame",
        "post_scenario", "post_owner", "post_phase",
    }
    if expect_ticks:
        required.update({
            "ticks", "start_offset", "end_offset", "deadline_offset",
            "public_target_writes", "preparation_buffer_writes",
            "end_ly", "end_stat", "deadline_ly", "deadline_stat",
            "presentation_trace", "descriptor_found", "descriptor_class",
            "descriptor_width", "descriptor_height", "descriptor_extent",
            "descriptor_reservation", "enqueued_mask_at_end",
            "drained_mask_at_end", "enqueued_mask_at_deadline",
            "drained_mask_at_deadline", "available_cycles_at_end",
            "required_cycles_at_end", "available_cycles_at_deadline",
            "required_cycles_at_deadline",
            "post_end_public_target_writes",
            "semantic_unit_public_target_writes",
            "active_descriptor_state_at_end",
            "active_descriptor_state_at_deadline",
            "active_descriptor_address_at_end",
            "active_descriptor_address_at_deadline",
            "active_descriptor_destination_at_end",
            "active_descriptor_destination_at_deadline",
            "fast_cache_valid_at_end", "fast_cache_valid_at_deadline",
            "request_count_at_end", "request_count_at_deadline",
        })
    producer_fields = {
        "producer_bound_descriptor_address",
        "producer_bound_descriptor_destination",
        "producer_bound_descriptor_state",
        "producer_class", "producer_destination", "producer_extent",
        "producer_height", "producer_payload", "producer_snapshot_found",
        "producer_width", "retry_admit_hits", "retry_finish_hits",
        "retry_publish_hits", "retry_publish_result",
    }
    vertical_fields = {
        "descriptor_snapshot",
        "descriptor_home_seen", "descriptor_home_address",
        "descriptor_home_state", "descriptor_home_cache",
        "descriptor_home_post_end_public_writes",
        "descriptor_deferred_seen", "descriptor_deferred_address",
        "descriptor_deferred_state", "descriptor_deferred_cache",
    }
    if set(raw) not in (
        required,
        required | producer_fields,
        required | vertical_fields,
        required | producer_fields | vertical_fields,
    ):
        raise Phase5StressError(f"{path}: unexpected sample fields")
    if not isinstance(raw["index"], int) or raw["index"] < 0:
        raise Phase5StressError(f"{path}.index: expected nonnegative integer")
    if not isinstance(raw["key1"], int) or raw["key1"] & 0x80 == 0:
        raise Phase5StressError(f"{path}.key1: production path is not CGB double-speed")
    byte_fields = [
        ("scenario", PHASE5_SCENARIO_BYTES),
        ("post_scenario", PHASE5_SCENARIO_BYTES),
        ("stress", PHASE5_STRESS_BYTES),
        ("trace", PHASE2_TRACE_BYTES),
    ]
    if expect_ticks:
        byte_fields.append(("presentation_trace", PHASE2_TRACE_BYTES))
    for name, size in byte_fields:
        value = raw[name]
        if not isinstance(value, str) or len(value) != size * 2:
            raise Phase5StressError(f"{path}.{name}: wrong byte length")
        try:
            bytes.fromhex(value)
        except ValueError as exc:
            raise Phase5StressError(f"{path}.{name}: expected lowercase hex") from exc
        if value != value.lower():
            raise Phase5StressError(f"{path}.{name}: expected canonical lowercase hex")
    if expect_ticks and (not isinstance(raw["ticks"], int) or raw["ticks"] <= 0):
        raise Phase5StressError(f"{path}.ticks: expected positive CPU T-cycles")
    if expect_ticks:
        for name in ("end_ly", "end_stat", "deadline_ly", "deadline_stat"):
            if not isinstance(raw[name], int) or not 0 <= raw[name] <= 0xFF:
                raise Phase5StressError(f"{path}.{name}: expected an observed IO byte")
        offsets = [raw[name] for name in ("start_offset", "end_offset", "deadline_offset")]
        ordered = (
            offsets[0] < offsets[1] <= offsets[2]
            if allow_end_at_deadline
            else offsets[0] < offsets[1] < offsets[2]
        )
        if (
            any(not isinstance(value, int) or value < 0 for value in offsets)
            or not ordered
            or raw["ticks"] != offsets[1] - offsets[0]
        ):
            raise Phase5StressError(
                f"{path}: expected origin <= start < end <= deadline observations"
            )
        for name in (
            "public_target_writes", "preparation_buffer_writes",
            "descriptor_class", "descriptor_width", "descriptor_height",
            "descriptor_extent", "descriptor_reservation",
            "enqueued_mask_at_end", "drained_mask_at_end",
            "enqueued_mask_at_deadline", "drained_mask_at_deadline",
            "available_cycles_at_end", "required_cycles_at_end",
            "available_cycles_at_deadline", "required_cycles_at_deadline",
            "post_end_public_target_writes",
            "active_descriptor_state_at_end",
            "active_descriptor_state_at_deadline",
            "active_descriptor_address_at_end",
            "active_descriptor_address_at_deadline",
            "active_descriptor_destination_at_end",
            "active_descriptor_destination_at_deadline",
            "fast_cache_valid_at_end", "fast_cache_valid_at_deadline",
            "request_count_at_end", "request_count_at_deadline",
        ):
            if not isinstance(raw[name], int) or not 0 <= raw[name] <= 0xFFFF:
                raise Phase5StressError(f"{path}.{name}: expected an observed counter")
        if not isinstance(raw["descriptor_found"], bool):
            raise Phase5StressError(f"{path}.descriptor_found: expected boolean")
        if not raw["descriptor_found"] and any(
            raw[name] != 0 for name in (
                "descriptor_class", "descriptor_width", "descriptor_height",
                "descriptor_extent", "descriptor_reservation",
            )
        ):
            raise Phase5StressError(f"{path}: absent descriptor has nonzero metadata")
        if vertical_fields <= set(raw):
            snapshot = raw["descriptor_snapshot"]
            if (
                not isinstance(snapshot, str)
                or len(snapshot) != 2 * 20
                or snapshot != snapshot.lower()
            ):
                raise Phase5StressError(f"{path}: malformed canonical descriptor snapshot")
            try:
                bytes.fromhex(snapshot)
            except ValueError as exc:
                raise Phase5StressError(
                    f"{path}: malformed canonical descriptor snapshot"
                ) from exc
            for name in ("descriptor_home_seen", "descriptor_deferred_seen"):
                if not isinstance(raw[name], bool):
                    raise Phase5StressError(f"{path}.{name}: expected boolean")
            for name in vertical_fields - {
                "descriptor_snapshot", "descriptor_home_seen",
                "descriptor_deferred_seen",
            }:
                if not isinstance(raw[name], int) or not 0 <= raw[name] <= 0xFFFF:
                    raise Phase5StressError(f"{path}.{name}: expected observed counter")
        if producer_fields <= set(raw):
            if raw["producer_snapshot_found"] is not True:
                raise Phase5StressError(f"{path}: retry evidence lacks producer snapshot")
            for name in producer_fields - {"producer_payload", "producer_snapshot_found"}:
                if not isinstance(raw[name], int) or not 0 <= raw[name] <= 0xFFFF:
                    raise Phase5StressError(f"{path}.{name}: expected producer/retry counter")
            payload = raw["producer_payload"]
            if (
                not isinstance(payload, str)
                or len(payload) != int(raw["producer_extent"]) * 4
                or payload != payload.lower()
            ):
                raise Phase5StressError(f"{path}.producer_payload: wrong paired snapshot")
            try:
                bytes.fromhex(payload)
            except ValueError as exc:
                raise Phase5StressError(
                    f"{path}.producer_payload: expected lowercase hex"
                ) from exc
    if not isinstance(raw["frame"], str) or Path(raw["frame"]).name != raw["frame"]:
        raise Phase5StressError(f"{path}.frame: expected local artifact name")
    for name in ("post_owner", "post_phase"):
        if not isinstance(raw[name], int) or not 0 <= raw[name] <= 0xFF:
            raise Phase5StressError(f"{path}.{name}: expected an observed state byte")
    return raw


def _validate_vblank_finalizer_invariants(
    row: RowDescriptor,
    sample: Mapping[str, object],
    constants: Mapping[str, int],
    *,
    path: str,
) -> None:
    """Prove that the measured owner seam precedes only non-public cleanup."""
    if row.deadline_kind != "FIXED_VBLANK":
        return
    if row.row_id != "VBlank":
        return
    if sample["post_end_public_target_writes"] != 0:
        raise Phase5StressError(f"{path}: public/display writer executed after owner End")
    # The retained canonical row/column path intentionally crosses the Home
    # owner-return seam after publication and before its non-public accounting
    # finalizer. Other serialized classes complete their accounting in-bank.
    if sample["public_target_writes"] not in (72, 80):
        return
    if sample["fast_cache_valid_at_deadline"] != 0:
        raise Phase5StressError(f"{path}: paired finalizer left the fast cache armed")
    pending = constants[FAST_CACHE_ACCOUNTING_PENDING_CONSTANT]
    if (
        int(sample["active_descriptor_state_at_end"]) >> 4 != constants["COMPLETE"]
        or sample["fast_cache_valid_at_end"] != pending
        or int(sample["active_descriptor_state_at_deadline"]) >> 4 != constants["COMPLETE"]
    ):
        raise Phase5StressError(
            f"{path}: paired publication was not COMPLETE with deferred accounting at End"
        )
    if sample["request_count_at_end"] != sample["request_count_at_deadline"] + 1:
        raise Phase5StressError(
            f"{path}: paired finalizer did not retire exactly one completed descriptor"
        )


def _validate_vertical_descriptor_lifecycle(
    row: RowDescriptor,
    sample: Mapping[str, object],
    constants: Mapping[str, int],
    *,
    path: str,
) -> None:
    """Bind the canonical column writer to one stable resident descriptor."""
    if row.row_id != "vertical":
        return
    vertical_fields = {
        "descriptor_snapshot", "descriptor_home_seen", "descriptor_home_address",
        "descriptor_home_state", "descriptor_home_cache",
        "descriptor_home_post_end_public_writes",
        "descriptor_deferred_seen", "descriptor_deferred_address",
        "descriptor_deferred_state", "descriptor_deferred_cache",
    }
    if sample["descriptor_found"] is not True or not vertical_fields <= set(sample):
        raise Phase5StressError(f"{path}: canonical column descriptor slot is missing")
    snapshot = bytes.fromhex(str(sample["descriptor_snapshot"]))
    if (
        sample["descriptor_class"] != constants["FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED"]
        or sample["descriptor_width"] != 2
        or sample["descriptor_height"] != 18
        or sample["descriptor_extent"] != 36
        or sample["descriptor_reservation"] != 72
        or snapshot[0] != (
            constants["COMMITTING"] << 4
            | constants["FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED"]
        )
        or snapshot[10:12] != bytes((2, 18))
        or int.from_bytes(snapshot[14:16], "little") != 36
        or int.from_bytes(snapshot[16:18], "little") != 72
    ):
        raise Phase5StressError(f"{path}: canonical column class or geometry drifted")
    address = int(sample["active_descriptor_address_at_end"])
    if (
        address == 0
        or sample["active_descriptor_address_at_deadline"] != address
        or sample["active_descriptor_destination_at_end"] == 0
        or sample["active_descriptor_destination_at_deadline"]
        != sample["active_descriptor_destination_at_end"]
    ):
        raise Phase5StressError(
            f"{path}: canonical column descriptor slot was reclaimed or substituted"
        )
    if (
        int(sample["active_descriptor_state_at_end"]) >> 4 != constants["COMMITTING"]
        or int(sample["active_descriptor_state_at_deadline"]) >> 4 != constants["COMPLETE"]
    ):
        raise Phase5StressError(
            f"{path}: canonical column descriptor did not transition COMMITTING to COMPLETE"
        )
    pending = constants[FAST_CACHE_ACCOUNTING_PENDING_CONSTANT]
    if (
        not sample["descriptor_home_seen"]
        or sample["descriptor_home_address"] != address
        or int(sample["descriptor_home_state"]) >> 4 != constants["COMPLETE"]
        or sample["descriptor_home_cache"] != pending
        or sample["descriptor_home_post_end_public_writes"] != 0
        or not sample["descriptor_deferred_seen"]
        or sample["descriptor_deferred_address"] != address
        or int(sample["descriptor_deferred_state"]) >> 4 != constants["COMPLETE"]
        or sample["descriptor_deferred_cache"] != pending
        or sample["fast_cache_valid_at_end"] in (0, pending)
        or sample["fast_cache_valid_at_deadline"] != 0
        or sample["request_count_at_end"] != sample["request_count_at_deadline"] + 1
        or sample["post_end_public_target_writes"] != 0
    ):
        raise Phase5StressError(
            f"{path}: canonical column completion/accounting finalizer drifted"
        )


def _validate_driver_capture(
    row: RowDescriptor,
    raw: object,
    *,
    constants: Mapping[str, int],
    samples: int,
) -> list[dict[str, object]]:
    if not isinstance(raw, dict) or set(raw) != {
        "schema", "model", "start_count", "samples", "calibration",
    }:
        raise Phase5StressError(f"{row.key}: malformed SameBoy capture")
    if raw["schema"] != "sameboy-phase5-driver-v1" or raw["model"] != "CGB-C":
        raise Phase5StressError(f"{row.key}: wrong SameBoy authority")
    if raw["start_count"] != samples or not isinstance(raw["samples"], list):
        raise Phase5StressError(f"{row.key}: unpaired or incomplete SameBoy executions")
    if len(raw["samples"]) != samples:
        raise Phase5StressError(f"{row.key}: SameBoy sample count is not exact")
    calibration = raw["calibration"]
    if not isinstance(calibration, dict) or set(calibration) != {
        "frame_ticks", "known_nop_count", "known_nop_ticks", "scanline_ticks",
        "ly144_to_ly145_register_ticks", "ly144_to_ly0_register_ticks",
        "natural_vblank_ticks",
    }:
        raise Phase5StressError(f"{row.key}: malformed SameBoy tick calibration")
    if (
        calibration["known_nop_count"] != 16
        or calibration["known_nop_ticks"] != 64
        or calibration["scanline_ticks"] != 912
        or calibration["natural_vblank_ticks"] != NATURAL_VBLANK_DEADLINE_T_CYCLES
        or calibration["frame_ticks"] != 140448
        or not 880 <= calibration["ly144_to_ly145_register_ticks"] <= 944
        or not 8160 <= calibration["ly144_to_ly0_register_ticks"] <= 8256
    ):
        raise Phase5StressError(f"{row.key}: SameBoy tick calibration is inconsistent")
    result: list[dict[str, object]] = []
    for index, sample_raw in enumerate(raw["samples"]):
        sample = _validate_sample_shape(
            sample_raw,
            path=f"{row.key}.sameboy.samples[{index}]",
            expect_ticks=True,
            allow_end_at_deadline=row.end_label == row.deadline_observation_label,
        )
        if sample["index"] != index:
            raise Phase5StressError(f"{row.key}: SameBoy sample indices are not stable")
        scenario = bytes.fromhex(str(sample["scenario"]))
        if scenario[1] != constants[_observed_scenario_constant(row)]:
            raise Phase5StressError(f"{row.key}: observed the wrong audit scenario")
        post = bytes.fromhex(str(sample["post_scenario"]))
        if row.case_id == "RC-P5-PARTY-RETURN-PALLET" and (
            post[3] != constants[RESULT_PASSED_CONSTANT]
            or post[4] != constants[STATE_COMPLETE_CONSTANT]
            or post[7] != constants[LEDGER_ALL_CONSTANT]
            or post[8] != constants[BARRIER_STABLE_CONSTANT]
            or post[9] != 5
            or sample["post_owner"] != constants["RENDERER_FULL_COLOR_OVERWORLD"]
            or sample["post_phase"] != constants["OVERWORLD_ACTIVE"]
        ):
            raise Phase5StressError(f"{row.key}: Party terminal postcondition drifted")
        if row.case_id != "RC-P5-PARTY-RETURN-PALLET" and (
            sample["post_owner"] != constants["RENDERER_FULL_COLOR_OVERWORLD"]
            or sample["post_phase"] != constants["OVERWORLD_ACTIVE"]
        ):
            raise Phase5StressError(f"{row.key}: natural Color owner/phase drifted")
        _validate_vblank_finalizer_invariants(
            row,
            sample,
            constants,
            path=f"{row.key}.sameboy.samples[{index}]",
        )
        _validate_vertical_descriptor_lifecycle(
            row,
            sample,
            constants,
            path=f"{row.key}.sameboy.samples[{index}]",
        )
        result.append(sample)
    return result


RunCommand = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _subprocess_run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command, text=True, capture_output=True, check=False,
            timeout=FRESH_WINDOW_SINGLE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(
            command, 124,
            error.stdout if isinstance(error.stdout, str) else "",
            error.stderr if isinstance(error.stderr, str) else "SameBoy window timeout",
        )


def _window_identity(root: Path, tool_root: Path | None = None) -> dict[str, str]:
    paths = {
        "rom": root / f"{AUDIT_PRODUCT}.gbc",
        "sym": root / f"{AUDIT_PRODUCT}.sym",
        "map": root / f"{AUDIT_PRODUCT}.map",
    }
    if tool_root is not None:
        driver, boot_rom = _driver_paths(tool_root)
        paths.update({
            "sameboy_driver": driver,
            "sameboy_boot_rom": boot_rom,
            "sameboy_install": tool_root / "install.json",
        })
    return {name: _sha256(path) for name, path in paths.items()}


def _validate_fresh_window_metadata(
    windows: object, *, samples: int, require_calibration: bool
) -> list[dict[str, object]]:
    if not isinstance(windows, list) or len(windows) != samples:
        raise Phase5StressError("fresh-window capture count is not exact")
    identities: set[str] = set()
    calibrations: set[str] = set()
    for index, window in enumerate(windows):
        required = {"index", "raw_capture_sha256", "identities"}
        if require_calibration:
            required.add("calibration_sha256")
        if (
            not isinstance(window, dict)
            or set(window) != required
            or window["index"] != index
            or not isinstance(window["identities"], dict)
            or not window["identities"]
        ):
            raise Phase5StressError("fresh-window identity or deterministic index drifted")
        _require_hash(window["raw_capture_sha256"], path=f"fresh_windows[{index}].raw")
        for name, digest in window["identities"].items():
            if not isinstance(name, str) or not name:
                raise Phase5StressError("fresh-window identity name is malformed")
            _require_hash(digest, path=f"fresh_windows[{index}].identities.{name}")
        identities.add(_canonical(window["identities"]))
        if require_calibration:
            calibrations.add(_require_hash(
                window["calibration_sha256"],
                path=f"fresh_windows[{index}].calibration",
            ))
    if len(identities) != 1:
        raise Phase5StressError("fresh windows mixed ROM or tool identities")
    if require_calibration and len(calibrations) != 1:
        raise Phase5StressError("fresh windows mixed SameBoy tick calibrations")
    return windows


def capture_sameboy_row(
    root: Path,
    tool_root: Path,
    row: RowDescriptor,
    row_dir: Path,
    constants: Mapping[str, int],
    *,
    samples: int = MINIMUM_EXECUTIONS,
    max_frames: int = 3600,
    movement_axis: str | None = None,
    diagnostic_labels: Sequence[str] = (),
    create_strip: bool = True,
    run_command: RunCommand = _subprocess_run,
) -> dict[str, object]:
    if movement_axis is None:
        movement_axis = _natural_movement_axis(row)
    if movement_axis not in {"row", "column"}:
        raise Phase5StressError(f"{row.key}: invalid natural movement axis")
    sameboy_dir = row_dir / "sameboy"
    sameboy_dir.mkdir(parents=True, exist_ok=False)
    driver, boot_rom = _driver_paths(tool_root)
    raw_path = sameboy_dir / "capture.json"
    fresh_window_metadata: list[dict[str, object]] | None = None

    def run_driver(capture_path: Path, frame_dir: Path, count: int) -> None:
        # SameBoy v1.0.3 resolves only one textual name for a zero-byte alias
        # set. The canonical scheduler export is address-identical to the
        # reviewed Phase 5 connection Start symbol; symbol identities are
        # checked above and the raw interval therefore remains exact.
        driver_start_label = (
            "EnqueueFullColorMapConnection"
            if row.row_id == "connection" else row.start_label
        )
        command = (
            str(driver),
            "--rom", str(root / f"{AUDIT_PRODUCT}.gbc"),
            "--sym", str(root / f"{AUDIT_PRODUCT}.sym"),
            "--boot-rom", str(boot_rom),
            "--json", str(capture_path),
            "--frame-dir", str(frame_dir),
            "--start", driver_start_label,
            "--end", row.end_label,
            "--origin", row.origin_label,
            # FIXED_VBLANK rows close the raw sample at HandlerEnd only so the
            # complete ISR remains available as a diagnostic. Their reviewed
            # physical deadline is synthesized as origin+9,120 CPU T-cycles.
            "--deadline", row.deadline_observation_label,
            "--deadline-kind", row.deadline_kind,
            "--movement-axis", movement_axis,
            "--scenario-value", str(constants[_capture_scenario_constant(row)]),
            "--control-value", str(constants[CONTROL_CONSTANT]),
            "--state-stable-value", str(constants[STATE_STABLE_CONSTANT]),
            "--state-complete-value", str(constants[STATE_COMPLETE_CONSTANT]),
            "--result-passed-value", str(constants[RESULT_PASSED_CONSTANT]),
            "--ledger-all-value", str(constants[LEDGER_ALL_CONSTANT]),
            "--barrier-stable-value", str(constants[BARRIER_STABLE_CONSTANT]),
            "--yellow-owner-value", str(constants["RENDERER_YELLOW"]),
            "--yellow-phase-value", str(constants["YELLOW_ACTIVE"]),
            "--color-owner-value", str(constants["RENDERER_FULL_COLOR_OVERWORLD"]),
            "--color-phase-value", str(constants["OVERWORLD_ACTIVE"]),
            "--descriptor-committing-value", str(constants["COMMITTING"]),
            "--descriptor-complete-value", str(constants["COMPLETE"]),
            "--oam-class-value", str(constants["FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA"]),
            "--samples", str(count),
            "--max-frames", str(max_frames),
        )
        if row.descriptor_class_constant is not None:
            command += (
                "--descriptor-class-value",
                str(constants[row.descriptor_class_constant]),
            )
        for label in diagnostic_labels:
            command += ("--diagnostic-breakpoint", label)
        completed = run_command(command)
        if completed.returncode:
            diagnostic = frame_dir / "failure.txt"
            diagnostic.write_text(
                f"command: {' '.join(command)}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
                encoding="utf-8",
            )
            raise Phase5StressError(
                f"{row.key}: SameBoy capture failed ({completed.returncode}); see {diagnostic}"
            )

    if row.row_id in FRESH_WINDOW_ROW_IDS and samples > 1:
        deadline = time.monotonic() + FRESH_WINDOW_TOTAL_TIMEOUT_SECONDS
        normalized_samples: list[dict[str, object]] = []
        fresh_window_metadata = []
        windows_dir = sameboy_dir / "windows"
        windows_dir.mkdir()
        for index in range(samples):
            if time.monotonic() >= deadline:
                raise Phase5StressError(f"{row.key}: fresh-window total timeout expired")
            window_dir = windows_dir / f"window-{index:04d}"
            window_dir.mkdir()
            window_raw_path = window_dir / "capture.json"
            identity_before = _window_identity(root, tool_root)
            run_driver(window_raw_path, window_dir, 1)
            identity_after = _window_identity(root, tool_root)
            if identity_before != identity_after:
                raise Phase5StressError(f"{row.key}: ROM or tool identity changed inside a window")
            window_raw = _read_json(window_raw_path)
            parsed_window = _validate_driver_capture(
                row, window_raw, constants=constants, samples=1
            )
            sample = dict(parsed_window[0])
            sample["index"] = index
            sample["frame"] = f"frame-{index:04d}.ppm"
            normalized_samples.append(sample)
            shutil.copy2(window_dir / "frame-0000.ppm", sameboy_dir / sample["frame"])
            fresh_window_metadata.append({
                "index": index,
                "raw_capture_sha256": _sha256(window_raw_path),
                "calibration_sha256": hashlib.sha256(
                    _canonical(window_raw["calibration"]).encode("utf-8")
                ).hexdigest(),
                "identities": identity_after,
            })
        _validate_fresh_window_metadata(
            fresh_window_metadata, samples=samples, require_calibration=True
        )
        raw = {
            "schema": "sameboy-phase5-driver-v1",
            "model": "CGB-C",
            "start_count": samples,
            "samples": normalized_samples,
            "calibration": _read_json(windows_dir / "window-0000/capture.json")["calibration"],
        }
        _write_json(raw_path, raw)
    else:
        run_driver(raw_path, sameboy_dir, samples)
    raw = _read_json(raw_path)
    parsed = _validate_driver_capture(row, raw, constants=constants, samples=samples)
    calibration = raw["calibration"]
    strips = (
        _convert_frame_strip(row_dir, prefix="sameboy", sample_count=samples)
        if create_strip else []
    )
    result = {
        "schema": "full-color-phase5-sameboy-row-v1",
        "authority": "SAMEBOY_DEBUGGER_TICKS",
        "samples": samples,
        "cycles": [sample["ticks"] for sample in parsed],
        "timing_observations": [
            {
                "start_offset": sample["start_offset"],
                "end_offset": sample["end_offset"],
                "deadline_offset": sample["deadline_offset"],
                "end_ly": sample["end_ly"],
                "end_stat": sample["end_stat"],
                "deadline_ly": sample["deadline_ly"],
                "deadline_stat": sample["deadline_stat"],
                "available_cycles_at_end": sample["available_cycles_at_end"],
                "required_cycles_at_end": sample["required_cycles_at_end"],
                "available_cycles_at_deadline": sample["available_cycles_at_deadline"],
                "required_cycles_at_deadline": sample["required_cycles_at_deadline"],
                "public_target_writes": sample["public_target_writes"],
                "post_end_public_target_writes": sample["post_end_public_target_writes"],
                "active_descriptor_state_at_end": sample["active_descriptor_state_at_end"],
                "active_descriptor_state_at_deadline": sample["active_descriptor_state_at_deadline"],
                "active_descriptor_address_at_end": sample["active_descriptor_address_at_end"],
                "active_descriptor_address_at_deadline": sample["active_descriptor_address_at_deadline"],
                "active_descriptor_destination_at_end": sample["active_descriptor_destination_at_end"],
                "active_descriptor_destination_at_deadline": sample["active_descriptor_destination_at_deadline"],
                "fast_cache_valid_at_end": sample["fast_cache_valid_at_end"],
                "fast_cache_valid_at_deadline": sample["fast_cache_valid_at_deadline"],
                "request_count_at_end": sample["request_count_at_end"],
                "request_count_at_deadline": sample["request_count_at_deadline"],
            }
            for sample in parsed
        ],
        "tick_calibration": calibration,
        "tick_calibration_equations": {
            "instruction_unit": "16 NOP * 4 CPU T-cycles = 64 SameBoy debugger ticks",
            "scanline": "140448 full-frame ticks / 154 PPU scanlines = 912 CPU T-cycles",
            "natural_vblank": "10 PPU scanlines * 912 CPU T-cycles = 9120 CPU T-cycles",
            "register_polling": (
                f"raw LY144->LY145 {calibration['ly144_to_ly145_register_ticks']} ticks; "
                f"raw LY144->LY0 {calibration['ly144_to_ly0_register_ticks']} ticks; "
                "instruction-boundary observations retained, not used as physical scaling"
            ),
        },
        "pressure_accounting": {
            "enqueued_masks_at_end": sorted({int(sample["enqueued_mask_at_end"]) for sample in parsed}),
            "drained_masks_at_end": sorted({int(sample["drained_mask_at_end"]) for sample in parsed}),
            "enqueued_masks_at_deadline": sorted({int(sample["enqueued_mask_at_deadline"]) for sample in parsed}),
            "drained_masks_at_deadline": sorted({int(sample["drained_mask_at_deadline"]) for sample in parsed}),
            "frame_sequence": [
                {
                    "index": int(sample["index"]),
                    "public_target_writes": int(sample["public_target_writes"]),
                    "enqueued_mask": int(sample["enqueued_mask_at_end"]),
                    "drained_mask": int(sample["drained_mask_at_end"]),
                    "remaining_cycles": int(sample["available_cycles_at_end"]),
                    "required_cycles": int(sample["required_cycles_at_end"]),
                }
                for sample in parsed
            ],
        },
        "semantic_sha256": hashlib.sha256(
            b"".join(
                bytes.fromhex(str(sample["scenario"]))
                + bytes.fromhex(str(sample["stress"]))
                + bytes.fromhex(str(sample["post_scenario"]))
                + bytes((int(sample["post_owner"]), int(sample["post_phase"])))
                for sample in parsed
            )
        ).hexdigest(),
        "trace_sha256": hashlib.sha256(
            b"".join(bytes.fromhex(str(sample["trace"])) for sample in parsed)
        ).hexdigest(),
        "frame_strip": strips,
        "raw_capture_sha256": _sha256(raw_path),
    }
    producer_samples = [
        sample for sample in parsed if "producer_payload" in sample
    ]
    if producer_samples:
        if len(producer_samples) != len(parsed):
            raise Phase5StressError(
                f"{row.key}: producer/retry evidence is missing from some natural windows"
            )
        result["producer_retry_evidence"] = {
            "schema": "full-color-phase5-producer-retry-v1",
            "samples": [
                {
                    "index": int(sample["index"]),
                    "producer_class": int(sample["producer_class"]),
                    "producer_destination": int(sample["producer_destination"]),
                    "producer_width": int(sample["producer_width"]),
                    "producer_height": int(sample["producer_height"]),
                    "producer_extent": int(sample["producer_extent"]),
                    "producer_payload_sha256": hashlib.sha256(
                        bytes.fromhex(str(sample["producer_payload"]))
                    ).hexdigest(),
                    "retry_admit_hits": int(sample["retry_admit_hits"]),
                    "retry_finish_hits": int(sample["retry_finish_hits"]),
                    "retry_publish_hits": int(sample["retry_publish_hits"]),
                    "retry_publish_result": int(sample["retry_publish_result"]),
                    "completed_descriptor_address": int(
                        sample["producer_bound_descriptor_address"]
                    ),
                    "completed_descriptor_destination": int(
                        sample["producer_bound_descriptor_destination"]
                    ),
                    "completed_descriptor_state": int(
                        sample["producer_bound_descriptor_state"]
                    ),
                    "completed_descriptor_result": "COMPLETE",
                }
                for sample in producer_samples
            ],
        }
    if fresh_window_metadata is not None:
        result["fresh_windows"] = {
            "mode": "INDEPENDENT_NATURAL_BOOT_TO_PALLET",
            "count": samples,
            "total_timeout_seconds": FRESH_WINDOW_TOTAL_TIMEOUT_SECONDS,
            "windows": fresh_window_metadata,
        }
    return result


def _finish_pyboy_capture(
    row: RowDescriptor,
    row_dir: Path,
    constants: Mapping[str, int],
    records: list[dict[str, object]],
    *,
    samples: int,
    start_count: int,
    open_execution: bool = False,
    fresh_window_metadata: list[dict[str, object]] | None = None,
    create_strip: bool = True,
) -> dict[str, object]:
    pyboy_dir = row_dir / "pyboy"
    if len(records) != samples or start_count != samples or open_execution:
        raise Phase5StressError(f"{row.key}: PyBoy did not complete exact natural executions")
    for index, record in enumerate(records):
        _validate_sample_shape(
            record, path=f"{row.key}.pyboy.samples[{index}]", expect_ticks=False
        )
        if record["index"] != index or record["frame"] != f"frame-{index:04d}.ppm":
            raise Phase5StressError(f"{row.key}: PyBoy fresh-window index drifted")
        scenario = bytes.fromhex(str(record["scenario"]))
        if scenario[1] != constants[_observed_scenario_constant(row)]:
            raise Phase5StressError(f"{row.key}: PyBoy observed the wrong scenario")
        post = bytes.fromhex(str(record["post_scenario"]))
        if row.case_id == "RC-P5-PARTY-RETURN-PALLET" and (
            post[3] != constants[RESULT_PASSED_CONSTANT]
            or post[4] != constants[STATE_COMPLETE_CONSTANT]
            or post[7] != constants[LEDGER_ALL_CONSTANT]
            or post[8] != constants[BARRIER_STABLE_CONSTANT]
            or post[9] != 5
            or record["post_owner"] != constants["RENDERER_FULL_COLOR_OVERWORLD"]
            or record["post_phase"] != constants["OVERWORLD_ACTIVE"]
        ):
            raise Phase5StressError(f"{row.key}: PyBoy Party terminal postcondition drifted")
        if row.case_id != "RC-P5-PARTY-RETURN-PALLET" and (
            record["post_owner"] != constants["RENDERER_FULL_COLOR_OVERWORLD"]
            or record["post_phase"] != constants["OVERWORLD_ACTIVE"]
        ):
            raise Phase5StressError(f"{row.key}: PyBoy natural Color owner/phase drifted")
    raw = {"schema": "pyboy-phase5-cross-check-v1", "samples": records, "start_count": start_count}
    raw_path = pyboy_dir / "capture.json"
    _write_json(raw_path, raw)
    strips = (
        _convert_frame_strip(row_dir, prefix="pyboy", sample_count=samples)
        if create_strip else []
    )
    result = {
        "schema": "full-color-phase5-pyboy-row-v1",
        "authority": "BEHAVIORAL_CROSS_CHECK_ONLY",
        "samples": samples,
        "semantic_sha256": hashlib.sha256(
            b"".join(
                bytes.fromhex(str(sample["scenario"]))
                + bytes.fromhex(str(sample["stress"]))
                + bytes.fromhex(str(sample["post_scenario"]))
                + bytes((int(sample["post_owner"]), int(sample["post_phase"])))
                for sample in records
            )
        ).hexdigest(),
        "trace_sha256": hashlib.sha256(
            b"".join(bytes.fromhex(str(sample["trace"])) for sample in records)
        ).hexdigest(),
        "frame_strip": strips,
        "raw_capture_sha256": _sha256(raw_path),
    }
    if fresh_window_metadata is not None:
        result["fresh_windows"] = {
            "mode": "INDEPENDENT_NATURAL_BOOT_TO_PALLET",
            "count": samples,
            "total_timeout_seconds": FRESH_WINDOW_TOTAL_TIMEOUT_SECONDS,
            "windows": fresh_window_metadata,
        }
    return result


def capture_pyboy_row(
    root: Path,
    row: RowDescriptor,
    row_dir: Path,
    constants: Mapping[str, int],
    *,
    samples: int = MINIMUM_EXECUTIONS,
    warmup_frames: int = 120,
    max_frames: int = 3600,
    _fresh_window: bool = True,
    _create_strip: bool = True,
) -> dict[str, object]:
    pyboy_dir = row_dir / "pyboy"
    pyboy_dir.mkdir(parents=True, exist_ok=False)
    if _fresh_window and row.row_id in FRESH_WINDOW_ROW_IDS and samples > 1:
        deadline = time.monotonic() + FRESH_WINDOW_TOTAL_TIMEOUT_SECONDS
        records: list[dict[str, object]] = []
        fresh_window_metadata: list[dict[str, object]] = []
        windows_dir = pyboy_dir / "windows"
        windows_dir.mkdir()
        pyboy_identity = hashlib.sha256(PYBOY_VERSION.encode("ascii")).hexdigest()
        for index in range(samples):
            if time.monotonic() >= deadline:
                raise Phase5StressError(f"{row.key}: PyBoy fresh-window total timeout expired")
            window_dir = windows_dir / f"window-{index:04d}"
            identity_before = {**_window_identity(root), "pyboy_version": pyboy_identity}
            capture_pyboy_row(
                root, row, window_dir, constants, samples=1,
                warmup_frames=warmup_frames, max_frames=max_frames,
                _fresh_window=False, _create_strip=False,
            )
            identity_after = {**_window_identity(root), "pyboy_version": pyboy_identity}
            if identity_before != identity_after:
                raise Phase5StressError(f"{row.key}: PyBoy ROM identity changed inside a window")
            child_pyboy = window_dir / "pyboy"
            window_raw_path = child_pyboy / "capture.json"
            window_raw = _read_json(window_raw_path)
            if (
                not isinstance(window_raw, dict)
                or window_raw.get("start_count") != 1
                or not isinstance(window_raw.get("samples"), list)
                or len(window_raw["samples"]) != 1
            ):
                raise Phase5StressError(f"{row.key}: malformed PyBoy fresh window")
            sample = dict(window_raw["samples"][0])
            sample["index"] = index
            sample["frame"] = f"frame-{index:04d}.ppm"
            records.append(sample)
            shutil.copy2(child_pyboy / "frame-0000.ppm", pyboy_dir / sample["frame"])
            fresh_window_metadata.append({
                "index": index,
                "raw_capture_sha256": _sha256(window_raw_path),
                "identities": identity_after,
            })
        _validate_fresh_window_metadata(
            fresh_window_metadata, samples=samples, require_calibration=False
        )
        return _finish_pyboy_capture(
            row, row_dir, constants, records, samples=samples,
            start_count=samples, fresh_window_metadata=fresh_window_metadata,
        )
    emulator = Emulator(
        root / f"{AUDIT_PRODUCT}.gbc",
        root / f"{AUDIT_PRODUCT}.sym",
        pyboy_dir,
        cgb=True,
    )
    records: list[dict[str, object]] = []
    start_count = 0
    open_execution = False

    def at_start(_: object) -> None:
        nonlocal start_count, open_execution
        if len(records) >= samples:
            return
        if open_execution:
            raise Phase5StressError(f"{row.key}: PyBoy observed nested start")
        if emulator.pyboy.memory[0xFF4D] & 0x80 == 0:
            raise Phase5StressError(f"{row.key}: PyBoy path is not CGB double-speed")
        open_execution = True
        start_count += 1

    def at_end(_: object) -> None:
        nonlocal open_execution
        if len(records) >= samples:
            return
        if not open_execution:
            if row.row_id == "connection":
                # The shared enqueue-result seam also closes ordinary approach
                # rows. Only the bank-qualified North Start opens this case.
                return
            raise Phase5StressError(f"{row.key}: PyBoy observed end before start")
        scenario = emulator.read_bytes("wFullColorPhase5ScenarioStateStart", PHASE5_SCENARIO_BYTES)
        stress = emulator.read_bytes("wFullColorPhase5StressStateStart", PHASE5_STRESS_BYTES)
        trace = emulator.read_bytes("wFullColorDebugTraceCountPhase2", PHASE2_TRACE_BYTES)
        records.append(
            {
                "index": len(records),
                "key1": emulator.pyboy.memory[0xFF4D],
                "scenario": scenario.hex(),
                "stress": stress.hex(),
                "trace": trace.hex(),
                "frame": f"frame-{len(records):04d}.ppm",
            }
        )
        open_execution = False

    start_hook = (emulator.symbol_banks[row.start_label], emulator.symbols[row.start_label])
    end_hook = (emulator.symbol_banks[row.end_label], emulator.symbols[row.end_label])
    reach_bedroom_overworld(emulator)
    emulator.tick(120)
    image = emulator.capture_screen()
    extrema = image.getextrema()
    stable_bedroom = (
        emulator.read("wCurMap") == 0x26
        and emulator.read("wXCoord") == 3
        and emulator.read("wYCoord") == 6
        and emulator.read("wCurMapTileset") == 4
        and emulator.read("wCurMapWidth") == 4
        and emulator.read("wCurMapHeight") == 4
        and emulator.pyboy.memory[0xFF40] & 0x80 != 0
        and emulator.pyboy.register_file.PC != 0x0038
        and any(low != high for low, high in extrema)
    )
    if not stable_bedroom:
        diagnostic = {
            "stage": "bedroom",
            "pc": emulator.pyboy.register_file.PC,
            "map": emulator.read("wCurMap"),
            "x": emulator.read("wXCoord"),
            "y": emulator.read("wYCoord"),
            "owner": emulator.read("wRendererOwner"),
            "phase": emulator.read("wRendererPhase"),
            "tileset": emulator.read("wCurMapTileset"),
            "width": emulator.read("wCurMapWidth"),
            "height": emulator.read("wCurMapHeight"),
            "lcdc": emulator.pyboy.memory[0xFF40],
            "screen_extrema": extrema,
        }
        _write_json(pyboy_dir / "natural-readiness-failure.json", diagnostic)
        emulator.save_screenshot("natural-readiness-failure.png")
        emulator.close()
        raise Phase5StressError(
            f"{row.key}: natural setup did not reach stable owned bedroom"
        )
    if row.case_id == "RC-P5-COMBINED-PRESSURE-PALLET":
        walk_from_bedroom_to_pallet(emulator)
        emulator.tick(60)
    else:
        walk_from_bedroom_to_oak(emulator)
        follow_oak_and_receive_pikachu(emulator)
        finish_rival_battle_and_leave_lab(emulator)
        emulator.tick(120)
    image = emulator.capture_screen()
    extrema = image.getextrema()
    stable_pallet = (
        emulator.read("wCurMap") == 0
        and emulator.read("wXCoord") < 20
        and emulator.read("wYCoord") < 18
        and emulator.read("wRendererOwner") == constants["RENDERER_FULL_COLOR_OVERWORLD"]
        and emulator.read("wRendererPhase") == constants["OVERWORLD_ACTIVE"]
        and emulator.pyboy.register_file.PC != 0x0038
        and any(low != high for low, high in extrema)
    )
    if not stable_pallet:
        diagnostic = {
            "pc": emulator.pyboy.register_file.PC,
            "map": emulator.read("wCurMap"),
            "x": emulator.read("wXCoord"),
            "y": emulator.read("wYCoord"),
            "owner": emulator.read("wRendererOwner"),
            "phase": emulator.read("wRendererPhase"),
            "screen_extrema": extrema,
        }
        _write_json(pyboy_dir / "natural-readiness-failure.json", diagnostic)
        emulator.save_screenshot("natural-readiness-failure.png")
        emulator.close()
        raise Phase5StressError(
            f"{row.key}: natural setup did not reach stable owned Pallet"
        )
    movement_axis = _natural_movement_axis(row)
    if row.case_id == "RC-P5-COMBINED-PRESSURE-PALLET":
        emulator.advance_until(
            lambda: emulator.read("wXCoord") == 8,
            button="right" if emulator.read("wXCoord") < 8 else "left",
            max_presses=20, description="Pallet open scrolling column",
        )
        if movement_axis == "column":
            emulator.advance_until(
                lambda: emulator.read("wYCoord") == 12,
                button="down" if emulator.read("wYCoord") < 12 else "up",
                max_presses=24, description="Pallet open horizontal strip route",
            )
            emulator.advance_until(
                lambda: emulator.read("wXCoord") == 9,
                button="right", max_presses=2,
                description="Pallet camera-column measurement seam",
            )
    emulator.pyboy.hook_register(*start_hook, at_start, None)
    emulator.pyboy.hook_register(*end_hook, at_end, None)
    try:
        captured = 0
        movement_presses = 0
        for _ in range(samples * max_frames):
            before = len(records)
            if row.case_id == "RC-P5-PARTY-RETURN-PALLET":
                emulator.press("start", wait_frames=30)
                for _ in range(240):
                    if (
                        emulator.read("wMaxMenuItem") == 6
                        and emulator.read("wMenuWatchedKeys") == 0xCB
                    ):
                        break
                    emulator.tick()
                else:
                    raise Phase5StressError(f"{row.key}: natural Start menu did not open")
                move_cursor_to(
                    emulator, "wCurrentMenuItem",
                    0 if emulator.read("wMaxMenuItem") == 6 else 1,
                    description="the natural Party menu item",
                )
                emulator.write(
                    "wFullColorPhase5Scenario",
                    constants[_capture_scenario_constant(row)],
                )
                emulator.write("wFullColorPhase5ScenarioMutation", 0)
                emulator.write("wFullColorPhase5ScenarioControl", constants[CONTROL_CONSTANT])
                emulator.press("a", wait_frames=20)
                for _ in range(900):
                    state = emulator.read("wFullColorPhase5ScenarioState")
                    stable = emulator.read("wFullColorPhase5StableFrames")
                    if (
                        state == constants[STATE_STABLE_CONSTANT]
                        and stable == 5
                        and emulator.read("wFullColorPhase5YellowLedgerMask")
                        == constants[LEDGER_ALL_CONSTANT]
                        and emulator.read("wFullColorPhase5BarrierState")
                        == constants[BARRIER_STABLE_CONSTANT]
                        and emulator.read("wRendererOwner") == constants["RENDERER_YELLOW"]
                        and emulator.read("wRendererPhase") == constants["YELLOW_ACTIVE"]
                    ):
                        break
                    emulator.tick()
                else:
                    _write_json(pyboy_dir / "party-yellow-failure.json", {
                        "scenario_state": emulator.read("wFullColorPhase5ScenarioState"),
                        "scenario_control": emulator.read("wFullColorPhase5ScenarioControl"),
                        "scenario": emulator.read("wFullColorPhase5Scenario"),
                        "scenario_result": emulator.read("wFullColorPhase5ScenarioResult"),
                        "stable_frames": emulator.read("wFullColorPhase5StableFrames"),
                        "party_count": emulator.read("wPartyCount"),
                        "current_menu_item": emulator.read("wCurrentMenuItem"),
                        "max_menu_item": emulator.read("wMaxMenuItem"),
                        "pc": emulator.pyboy.register_file.PC,
                        "captured_breakpoints": len(records),
                    })
                    emulator.save_screenshot("party-yellow-failure.png")
                    raise Phase5StressError(f"{row.key}: Party did not become stably Yellow-owned")
                emulator.press("b", wait_frames=20)
                for _ in range(900):
                    if (
                        emulator.read("wFullColorPhase5ScenarioState")
                        == constants[STATE_COMPLETE_CONSTANT]
                        and emulator.read("wFullColorPhase5ScenarioResult")
                        == constants[RESULT_PASSED_CONSTANT]
                        and emulator.read("wFullColorPhase5ColorLedgerMask")
                        == constants[LEDGER_ALL_CONSTANT]
                        and emulator.read("wFullColorPhase5BarrierState")
                        == constants[BARRIER_STABLE_CONSTANT]
                        and emulator.read("wFullColorPhase5StableFrames") == 5
                        and emulator.read("wRendererOwner")
                        == constants["RENDERER_FULL_COLOR_OVERWORLD"]
                        and emulator.read("wRendererPhase") == constants["OVERWORLD_ACTIVE"]
                    ):
                        break
                    emulator.tick()
                else:
                    raise Phase5StressError(f"{row.key}: Party did not reconstruct Color")
                emulator.tick(5)
            elif row.case_id == "RC-P5-CONNECTION-PALLET-NORTH":
                emulator.write(
                    "wFullColorPhase5Scenario",
                    constants[_capture_scenario_constant(row)],
                )
                emulator.write("wFullColorPhase5ScenarioControl", constants[CONTROL_CONSTANT])
                if emulator.read("wCurMap") != 0:
                    emulator.advance_until(
                        lambda: emulator.read("wCurMap") == 0,
                        button="down", max_presses=48,
                        description="return to Pallet from Route 1",
                    )
                if emulator.read("wYCoord") > 2:
                    emulator.advance_until(
                        lambda: emulator.read("wXCoord") == 8,
                        button="right" if emulator.read("wXCoord") < 8 else "left",
                        max_presses=20, description="west side of Oak's Lab",
                    )
                    emulator.advance_until(
                        lambda: emulator.read("wYCoord") == 2,
                        button="up", max_presses=24,
                        description="north Pallet Town",
                    )
                emulator.advance_until(
                    lambda: emulator.read("wXCoord") == 10,
                    button="right" if emulator.read("wXCoord") < 10 else "left",
                    max_presses=20, description="Pallet north connection column",
                )
                emulator.advance_until(
                    lambda: emulator.read("wYCoord") == 0,
                    button="up", max_presses=8,
                    description="Pallet north connection row",
                )
                emulator.press("up", wait_frames=20)
            else:
                emulator.write(
                    "wFullColorPhase5Scenario",
                    constants[_capture_scenario_constant(row)],
                )
                emulator.write("wFullColorPhase5ScenarioControl", constants[CONTROL_CONSTANT])
                if movement_axis == "column":
                    coordinate = emulator.read("wXCoord")
                    direction = "right" if coordinate <= 3 else (
                        "left" if coordinate >= 16 else
                        ("right" if (movement_presses // 8) % 2 == 0 else "left")
                    )
                else:
                    direction = "down" if (movement_presses // 8) % 2 == 0 else "up"
                emulator.pyboy.button(direction, delay=2)
                emulator.tick(121 if movement_axis == "column" else 12)
                movement_presses += 1
                emulator.tick(4)
            while captured < len(records):
                records[captured]["post_scenario"] = emulator.read_bytes(
                    "wFullColorPhase5ScenarioStateStart", PHASE5_SCENARIO_BYTES
                ).hex()
                records[captured]["post_owner"] = emulator.read("wRendererOwner")
                records[captured]["post_phase"] = emulator.read("wRendererPhase")
                emulator.capture_screen().save(
                    pyboy_dir / f"frame-{captured:04d}.ppm", format="PPM"
                )
                captured += 1
            if len(records) == before:
                emulator.tick(1)
            if len(records) >= samples:
                break
    finally:
        emulator.pyboy.hook_deregister(*end_hook)
        emulator.pyboy.hook_deregister(*start_hook)
        if len(records) != samples:
            _write_json(pyboy_dir / "natural-capture-failure.json", {
                "case_id": row.case_id,
                "row_id": row.row_id,
                "expected_samples": samples,
                "start_count": start_count,
                "completed_samples": len(records),
                "open_execution": open_execution,
                "pc": emulator.pyboy.register_file.PC,
                "rom_bank": emulator.read("hLoadedROMBank"),
                "map": emulator.read("wCurMap"),
                "x": emulator.read("wXCoord"),
                "y": emulator.read("wYCoord"),
                "owner": emulator.read("wRendererOwner"),
                "phase": emulator.read("wRendererPhase"),
                "scenario": emulator.read_bytes(
                    "wFullColorPhase5ScenarioStateStart", PHASE5_SCENARIO_BYTES
                ).hex(),
                "stress": emulator.read_bytes(
                    "wFullColorPhase5StressStateStart", PHASE5_STRESS_BYTES
                ).hex(),
            })
            emulator.save_screenshot("natural-capture-failure.png")
        emulator.close()
    return _finish_pyboy_capture(
        row, row_dir, constants, records, samples=samples,
        start_count=start_count, open_execution=open_execution,
        create_strip=_create_strip,
    )


def _target_write_evidence(
    row: RowDescriptor,
    trace_path: Path,
    constants: Mapping[str, int],
) -> tuple[dict[str, object], dict[str, object] | None]:
    raw = _read_json(trace_path)
    return _target_write_evidence_from_raw(row, raw, constants)


def _target_write_evidence_from_raw(
    row: RowDescriptor,
    raw: object,
    constants: Mapping[str, int],
) -> tuple[dict[str, object], dict[str, object] | None]:
    if not isinstance(raw, dict) or not isinstance(raw.get("samples"), list):
        raise Phase5StressError("SameBoy raw trace lacks samples")
    public_counts: set[int] = set()
    preparation_counts: set[int] = set()
    descriptor_snapshots: set[tuple[int, int, int, int]] = set()
    end_hashes: set[str] = set()
    presentation_hashes: set[str] = set()
    presentation_changes: set[bool] = set()
    eventual_public_counts: set[int] = set()
    enqueued_masks: set[int] = set()
    drained_masks: set[int] = set()
    for sample in raw["samples"]:
        if not isinstance(sample, dict):
            raise Phase5StressError("SameBoy capture lacks measured write diagnostics")
        public = sample.get("public_target_writes")
        preparation = sample.get("preparation_buffer_writes")
        if not isinstance(public, int) or public < 0 or not isinstance(preparation, int) or preparation < 0:
            raise Phase5StressError("SameBoy capture has malformed write diagnostics")
        public_counts.add(public)
        preparation_counts.add(preparation)
        if row.descriptor_class_constant is not None:
            if sample.get("descriptor_found") is not True:
                raise Phase5StressError(f"{row.key}: linked descriptor was not observed")
            snapshot = tuple(
                sample.get(name) for name in (
                    "descriptor_class", "descriptor_width", "descriptor_height",
                    "descriptor_extent",
                )
            )
            if any(not isinstance(value, int) for value in snapshot):
                raise Phase5StressError(f"{row.key}: descriptor geometry is malformed")
            descriptor_snapshots.add(snapshot)  # type: ignore[arg-type]
            presentation = sample.get("presentation_trace")
            end_trace = sample.get("trace")
            if not isinstance(presentation, str) or not isinstance(end_trace, str):
                raise Phase5StressError(f"{row.key}: eventual presentation trace is missing")
            end_hashes.add(hashlib.sha256(bytes.fromhex(end_trace)).hexdigest())
            presentation_hashes.add(hashlib.sha256(bytes.fromhex(presentation)).hexdigest())
            presentation_changes.add(presentation != end_trace)
            eventual_public = sample.get(
                "semantic_unit_public_target_writes"
                if row.row_id == "connection"
                else "post_end_public_target_writes"
            )
            if not isinstance(eventual_public, int) or eventual_public < 0:
                raise Phase5StressError(
                    f"{row.key}: eventual public-write count is malformed"
                )
            eventual_public_counts.add(eventual_public)
            enqueued_masks.add(int(sample["enqueued_mask_at_deadline"]))
            drained_masks.add(int(sample["drained_mask_at_deadline"]))
    diagnostics = {
        "public_target_writes_within_interval": sorted(public_counts),
        "preparation_buffer_writes": sorted(preparation_counts),
        "descriptor_metadata_writes_included": False,
        "cycle_budget_role": "NONE",
    }
    if row.descriptor_class_constant is None:
        return diagnostics, None
    if len(descriptor_snapshots) != 1:
        raise Phase5StressError(f"{row.key}: descriptor class or geometry was not stable")
    descriptor_class, width, height, extent = next(iter(descriptor_snapshots))
    expected_class = constants[row.descriptor_class_constant]
    if descriptor_class != expected_class or extent <= 0:
        raise Phase5StressError(f"{row.key}: descriptor class or extent drifted")
    if row.semantic_write_kind == "PAIRED_PLANES":
        if width * height != extent:
            raise Phase5StressError(f"{row.key}: linked paired geometry does not equal extent")
        semantic_writes = 2 * extent
        equation = f"2 public BG planes * ({width} width * {height} height) = {semantic_writes} writes"
    elif row.semantic_write_kind == "EXTENT":
        semantic_writes = extent
        equation = f"linked descriptor extent {extent} = {semantic_writes} public writes"
    else:
        raise Phase5StressError(f"{row.key}: semantic write equation is undefined")
    fixed_extents = {
        "FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD": constants["FULL_COLOR_PALETTE_EXTENT"],
        "FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT": constants["FULL_COLOR_ANIMATION_EXTENT"],
        "FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA": constants["FULL_COLOR_OAM_EXTENT"],
    }
    expected_extent = fixed_extents.get(row.descriptor_class_constant)
    if expected_extent is not None and extent != expected_extent:
        raise Phase5StressError(f"{row.key}: descriptor extent disagrees with linked class constant")
    # Commit rows bracket their final public writes. Producer rows bracket only
    # enqueue/preparation and are corroborated by the linked presentation trace.
    if row.row_id in {"palette", "vertical", "animation", "OAM-DMA"}:
        if public_counts != {semantic_writes}:
            raise Phase5StressError(f"{row.key}: eventual public commit does not match semantic unit")
    elif row.row_id == "connection" and public_counts != {0}:
        raise Phase5StressError(f"{row.key}: enqueue interval unexpectedly wrote a public destination")
    elif row.row_id == "OAM-build" and any(value > semantic_writes for value in public_counts):
        raise Phase5StressError(f"{row.key}: OAM preparation exceeded its semantic unit")
    if row.row_id in {"OAM-build", "connection"} and eventual_public_counts != {
        semantic_writes
    }:
        raise Phase5StressError(
            f"{row.key}: eventual public commit does not match semantic unit"
        )
    pressure_bit = {
        "palette": 1,
        "animation": 2,
        "OAM-build": 4,
        "OAM-DMA": 4,
    }.get(row.row_id)
    if pressure_bit is not None and not any(mask & pressure_bit for mask in enqueued_masks):
        raise Phase5StressError(f"{row.key}: pressure enqueue accounting was not observed")
    # OAM is published directly by hDMARoutine and is deliberately not part of
    # the non-OAM scheduler's drained mask. Its 160 public writes and linked
    # presentation trace are the completion authority.
    # The per-row captures retain the drained mask diagnostically. The stable
    # combined-pressure window is the authority that both non-OAM units drain;
    # an individual commit is instead proved by its exact public writes.
    proposal = {
        "authority": "UNREVIEWED_PROPOSAL_ONLY",
        "unit": "DESCRIPTOR_SEMANTIC_PUBLIC_TARGET_WRITES",
        "request_class_constant": row.descriptor_class_constant,
        "observed_descriptor": {
            "class": descriptor_class,
            "width": width,
            "height": height,
            "extent": extent,
        },
        "semantic_unit_target_writes": semantic_writes,
        "semantic_unit_equation": equation,
        "eventual_commit_corroboration": {
            "end_trace_sha256": sorted(end_hashes),
            "presentation_trace_sha256": sorted(presentation_hashes),
            "presentation_trace_differs_from_end": sorted(presentation_changes),
            "eventual_public_target_writes": sorted(eventual_public_counts),
            "enqueued_masks_at_deadline": sorted(enqueued_masks),
            "drained_masks_at_deadline": sorted(drained_masks),
        },
        "proposed_target_write_count": semantic_writes,
        "changes_admission": False,
        "cycle_budget_role": "NONE",
    }
    return diagnostics, proposal


def capture_row(
    root: Path,
    tool_root: Path,
    row: RowDescriptor,
    row_dir: Path,
    constants: Mapping[str, int],
    *,
    samples: int = MINIMUM_EXECUTIONS,
    sameboy_capture: Callable[..., dict[str, object]] = capture_sameboy_row,
    pyboy_capture: Callable[..., dict[str, object]] = capture_pyboy_row,
) -> dict[str, object]:
    sameboy = sameboy_capture(root, tool_root, row, row_dir, constants, samples=samples)
    pyboy = pyboy_capture(root, row, row_dir, constants, samples=samples)
    for name in ("semantic_sha256", "trace_sha256"):
        if sameboy[name] != pyboy[name]:
            raise Phase5StressError(
                f"{row.key}: SameBoy and PyBoy disagree on {name.removesuffix('_sha256')}"
            )
    write_diagnostics, reservation = _target_write_evidence(
        row, row_dir / "sameboy/capture.json", constants
    )
    evidence = {
        "schema": ROW_SCHEMA,
        "case_id": row.case_id,
        "row_id": row.row_id,
        "operation": row.operation,
        "scenario_constant": row.scenario_constant,
        "natural_arm_constant": row.arm_constant,
        "start_label": row.start_label,
        "end_label": row.end_label,
        "origin_label": row.origin_label,
        "deadline_observation_label": row.deadline_observation_label,
        "deadline_observation_role": (
            "HANDLER_END_DIAGNOSTIC_ONLY"
            if row.deadline_kind == "FIXED_VBLANK"
            else "LINKED_PRESENTATION_DEADLINE"
        ),
        "deadline_kind": row.deadline_kind,
        "natural_executions": samples,
        "sameboy": sameboy,
        "pyboy": pyboy,
        "write_diagnostics": write_diagnostics,
    }
    if reservation is not None:
        evidence["descriptor_write_count_proposal"] = reservation
    _write_json(row_dir / "row.json", evidence)
    return evidence


def _stable_view(row: Mapping[str, object]) -> dict[str, object]:
    stable = {
        "case_id": row["case_id"],
        "row_id": row["row_id"],
        "operation": row["operation"],
        "scenario_constant": row["scenario_constant"],
        "natural_arm_constant": row["natural_arm_constant"],
        "start_label": row["start_label"],
        "end_label": row["end_label"],
        "origin_label": row["origin_label"],
        "deadline_observation_label": row["deadline_observation_label"],
        "deadline_observation_role": row["deadline_observation_role"],
        "deadline_kind": row["deadline_kind"],
        "natural_executions": row["natural_executions"],
        "sameboy": row["sameboy"],
        "pyboy": row["pyboy"],
        "write_diagnostics": row["write_diagnostics"],
    }
    if "descriptor_write_count_proposal" in row:
        stable["descriptor_write_count_proposal"] = row["descriptor_write_count_proposal"]
    return stable


def compare_runs(first: Mapping[str, object], second: Mapping[str, object]) -> None:
    first_rows = first.get("rows")
    second_rows = second.get("rows")
    if not isinstance(first_rows, list) or not isinstance(second_rows, list):
        raise Phase5StressError("Phase 5 run lacks row evidence")
    if len(first_rows) != len(ROWS) or len(second_rows) != len(ROWS):
        raise Phase5StressError("Phase 5 run does not cover every stable row")
    for index, descriptor in enumerate(ROWS):
        left = first_rows[index]
        right = second_rows[index]
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise Phase5StressError("Phase 5 run row is malformed")
        if (left.get("case_id"), left.get("row_id")) != (
            descriptor.case_id, descriptor.row_id
        ):
            raise Phase5StressError("Phase 5 run row order or identity drifted")
        if _canonical(_stable_view(left)) != _canonical(_stable_view(right)):
            raise Phase5StressError(
                f"independent Phase 5 captures differ at {descriptor.key}"
            )


def capture_run(
    root: Path,
    tool_root: Path,
    run_dir: Path,
    *,
    samples: int = MINIMUM_EXECUTIONS,
    capture: Callable[..., dict[str, object]] = capture_row,
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=False)
    constants = _numeric_symbols(root / f"{AUDIT_PRODUCT}.sym")
    required_constants = {
        CONTROL_CONSTANT, RESULT_PASSED_CONSTANT, STATE_COMPLETE_CONSTANT,
        STATE_STABLE_CONSTANT, LEDGER_ALL_CONSTANT, BARRIER_STABLE_CONSTANT,
        "RENDERER_YELLOW", "YELLOW_ACTIVE",
        "RENDERER_FULL_COLOR_OVERWORLD", "OVERWORLD_ACTIVE",
        "FULL_COLOR_PHASE5_SCENARIO_STATE_YELLOW_ACTIVE",
        *(row.scenario_constant for row in ROWS),
        *(row.descriptor_class_constant for row in ROWS if row.descriptor_class_constant),
        "FULL_COLOR_PALETTE_EXTENT", "FULL_COLOR_ANIMATION_EXTENT",
        "FULL_COLOR_OAM_EXTENT",
        FAST_CACHE_ACCOUNTING_PENDING_CONSTANT,
        "COMMITTING", "COMPLETE",
    }
    missing = sorted(required_constants - constants.keys())
    if missing:
        raise Phase5StressError("audit symbols lack constants: " + ", ".join(missing))
    rows: list[dict[str, object]] = []
    for index, row in enumerate(ROWS):
        row_dir = run_dir / f"row-{index:02d}"
        rows.append(capture(root, tool_root, row, row_dir, constants, samples=samples))
    result = {"schema": RUN_SCHEMA, "rows": rows}
    _write_json(run_dir / "run.json", result)
    return result


def _round_up_four(value: int) -> int:
    return (value + 3) // 4 * 4


def _timing_row(row: RowDescriptor, first: Mapping[str, object], second: Mapping[str, object]) -> dict[str, object]:
    observations: list[dict[str, int]] = []
    for raw in (first, second):
        sameboy = raw.get("sameboy")
        measured = sameboy.get("timing_observations") if isinstance(sameboy, dict) else None
        if not isinstance(measured, list):
            raise Phase5StressError(f"{row.key}: missing SameBoy origin/deadline observations")
        for sample in measured:
            if (
                not isinstance(sample, dict)
                or set(sample) != {
                    "start_offset", "end_offset", "deadline_offset",
                    "end_ly", "end_stat", "deadline_ly", "deadline_stat",
                    "available_cycles_at_end", "required_cycles_at_end",
                    "available_cycles_at_deadline", "required_cycles_at_deadline",
                    "public_target_writes",
                    "post_end_public_target_writes",
                    "active_descriptor_state_at_end",
                    "active_descriptor_state_at_deadline",
                    "active_descriptor_address_at_end",
                    "active_descriptor_address_at_deadline",
                    "active_descriptor_destination_at_end",
                    "active_descriptor_destination_at_deadline",
                    "fast_cache_valid_at_end", "fast_cache_valid_at_deadline",
                    "request_count_at_end", "request_count_at_deadline",
                }
                or any(not isinstance(sample[name], int) for name in sample)
                or not (
                    0 <= sample["start_offset"] < sample["end_offset"]
                    <= sample["deadline_offset"]
                    if row.end_label == row.deadline_observation_label
                    else 0 <= sample["start_offset"] < sample["end_offset"]
                    < sample["deadline_offset"]
                )
            ):
                raise Phase5StressError(f"{row.key}: invalid SameBoy timing observation")
            observations.append(sample)
    start_cycle = max(sample["start_offset"] for sample in observations)
    if row.start_label == row.origin_label and start_cycle != 0:
        raise Phase5StressError(f"{row.key}: aliased origin/start did not capture at cycle zero")
    observed_deadlines = [sample["deadline_offset"] for sample in observations]
    deadline_cycle = (
        NATURAL_VBLANK_DEADLINE_T_CYCLES
        if row.deadline_kind == "FIXED_VBLANK"
        else min(observed_deadlines)
    )
    # HandlerEnd is deliberately retained for FIXED_VBLANK rows as a
    # diagnostic observation only.  The renderer deadline applies to the
    # owner-return seam, after all executed public/display writers and after
    # bank restoration, not unrelated ISR housekeeping after that seam.
    worst = max(sample["end_offset"] - sample["start_offset"] for sample in observations)
    is_descriptor_commit = row.row_id in {
        "palette", "vertical", "animation", "OAM-DMA"
    }
    runtime_required = (
        sorted({
            sample["required_cycles_at_end"] for sample in observations
            if sample["required_cycles_at_end"] > 0
        }) if is_descriptor_commit else []
    )
    runtime_available = (
        sorted({sample["available_cycles_at_end"] for sample in observations})
        if is_descriptor_commit else []
    )
    if is_descriptor_commit and (
        not runtime_required or min(runtime_required) < worst + INSTRUMENTATION_T_CYCLES
    ):
        raise Phase5StressError(
            f"{row.key}: runtime required-cycle table understates measured operation"
        )
    # A fixed physical VBlank boundary has no linked-breakpoint jitter: it is
    # exactly origin+9,120.  HandlerEnd may vary or occur after that boundary,
    # but is retained only as an ISR diagnostic and must not inflate the
    # renderer guard.  Linked presentation deadlines use their measured jitter.
    jitter = (
        0
        if row.deadline_kind == "FIXED_VBLANK"
        else max(observed_deadlines) - min(observed_deadlines)
    )
    guard = max(SCANLINE_GUARD_FLOOR_T_CYCLES, _round_up_four(jitter))
    end_to_deadline = [
        sample["deadline_offset"] - sample["end_offset"] for sample in observations
    ]
    if row.row_id == "reconstruct-Color" and min(end_to_deadline) <= 920:
        raise Phase5StressError(
            f"{row.key}: operation End to linked deadline is shorter than "
            "the cross-bank 912-cycle presentation guard seam"
        )
    usable = deadline_cycle - start_cycle - guard
    margin = usable - INSTRUMENTATION_T_CYCLES - worst
    raw = {
        "key": row.key,
        "operation": row.operation,
        "mode": "CGB_DOUBLE_SPEED",
        "rom": f"{AUDIT_PRODUCT}.gbc",
        "tool_device": "SameBoy v1.0.3 CGB-C debugger ticks",
        "samples": len(observations),
        "worst_cycles": worst,
        "instrumentation_cycles": INSTRUMENTATION_T_CYCLES,
        "start_cycle": start_cycle,
        "deadline_cycle": deadline_cycle,
        "guard_cycles": guard,
        "margin_cycles": margin,
        "margin_percent": margin * 100 / usable,
        "defer_threshold": usable - INSTRUMENTATION_T_CYCLES,
        "threshold_plus_one_result": "DEFER",
        "threshold_plus_one_entered_committing": False,
        "result": "PASS" if margin >= 0 else "DEFER",
        "evidence_kind": "RENDERER_RUNTIME",
        "activation_phase": 5,
    }
    timing = TimingRow.from_dict(raw)
    if timing.result != "PASS" or timing.margin_cycles <= 0:
        raise Phase5StressError(f"{row.key}: timing margin is not positive")
    return {
        **timing.to_dict(),
        "authority_product": "PHASE2_AUDIT_ONLY",
        "cycle_unit": "CPU_T_CYCLES_AT_ACTIVE_SPEED",
        "origin": row.origin_label,
        "deadline": (
            "ORIGIN_PLUS_9120_CPU_T_CYCLES"
            if row.deadline_kind == "FIXED_VBLANK"
            else row.deadline_observation_label
        ),
        "deadline_equation": (
            "0 + 9120 = 9120 CPU T-cycles from natural VBlank origin"
            if row.deadline_kind == "FIXED_VBLANK"
            else f"min({observed_deadlines}) = {deadline_cycle} CPU T-cycles from linked origin"
        ),
        "guard_floor_equation": "1 double-speed scanline * 912 CPU T-cycles = 912 CPU T-cycles",
        "usable_equation": (
            f"{deadline_cycle} - {start_cycle} - {guard} = {usable} CPU T-cycles"
        ),
        "pass_equation": (
            f"{worst} + 0 <= {deadline_cycle} - {start_cycle} - {guard}"
        ),
        "observed_breakpoint_offsets": observed_deadlines,
        "deadline_observation_role": (
            "HANDLER_END_DIAGNOSTIC_ONLY"
            if row.deadline_kind == "FIXED_VBLANK"
            else "LINKED_PRESENTATION_DEADLINE"
        ),
        "measured_deadline_jitter_t_cycles": jitter,
        "threshold_evidence_ref": f"boundary_matrix/{row.case_id}",
        "breakpoint_overhead_t_cycles": 0,
        "descriptor_reservation_role": "SEPARATE_WRITE_COUNT_ADMISSION_EVIDENCE",
        "observed_runtime_required_cycles": runtime_required,
        "observed_runtime_available_cycles": runtime_available,
        "runtime_admission_equation": (
            "FrameAvailableCycles is remaining after accepted units; "
            f"remaining={runtime_available}, required={runtime_required}, "
            f"min(required) >= measured {worst} CPU T-cycles"
            if runtime_available and runtime_required
            else "NOT_A_SINGLE_VBLANK_DESCRIPTOR_COMMIT"
        ),
        "runtime_required_equation": (
            f"min({runtime_required}) >= {worst} + 0 CPU T-cycles"
            if runtime_required else "NOT_A_SINGLE_VBLANK_DESCRIPTOR_COMMIT"
        ),
        "presentation_guard": (
            {
                "start_label": PARTY_RECONSTRUCTION_GUARD_START,
                "end_label": PARTY_RECONSTRUCTION_GUARD_END,
                "cross_bank_farcall_roundtrip": True,
                "guard_machine_code": "c506370520fdc1",
                "equation": "16 + 8 + 54 * (4 + 12) + 4 + 8 + 12 = 912 CPU T-cycles",
                "operation_end_to_guard_start_role": (
                    "SUCCESS_CHECK_AND_CROSS_BANK_FARCALL_INCLUDED_IN_MEASURED_END_TO_DEADLINE"
                ),
                "guard_end_to_deadline_role": (
                    "CROSS_BANK_RETURN_INCLUDED_IN_MEASURED_END_TO_DEADLINE"
                ),
                "minimum_observed_operation_end_to_deadline_t_cycles": min(
                    end_to_deadline
                ),
                "result": "PASS",
            }
            if row.row_id == "reconstruct-Color"
            else "NOT_PARTY_RECONSTRUCTION"
        ),
        "owner_end_finalizer_invariants": (
            {
                "post_end_public_target_writes": sorted({
                    sample["post_end_public_target_writes"] for sample in observations
                }),
                "paired_fast_cache_valid_at_handler_end": sorted({
                    sample["fast_cache_valid_at_deadline"] for sample in observations
                    if sample["public_target_writes"] in (72, 80)
                }),
                "paired_complete_at_owner_end": all(
                    sample["request_count_at_end"]
                    == sample["request_count_at_deadline"] + 1
                    for sample in observations
                    if sample["public_target_writes"] in (72, 80)
                ),
                "paired_fast_cache_pending_at_owner_end": all(
                    sample["fast_cache_valid_at_end"] != 0
                    for sample in observations
                    if sample["public_target_writes"] in (72, 80)
                ),
                "fast_cache_pending_constant": FAST_CACHE_ACCOUNTING_PENDING_CONSTANT,
                "descriptor_complete_constant": "COMPLETE",
            }
            if row.row_id == "VBlank"
            else "NOT_OWNER_ROUTE_END"
        ),
    }


def _serialized_drain_evidence(
    pressure: Mapping[str, object],
    semantic_counts: Mapping[str, int],
) -> dict[str, object]:
    """Bind Combined pressure to serialized, whole-unit frame publication."""
    sequence = pressure.get("frame_sequence")
    units = ("OAM", "palette", "animation", "vertical")
    expected_counts = {
        "OAM": 160,
        "palette": 64,
        "animation": 17,
        "vertical": 72,
    }
    if dict(semantic_counts) != expected_counts:
        raise Phase5StressError(
            "Combined pressure semantic unit counts are not the exact linked units"
        )
    if set(semantic_counts) != set(units) or len(set(semantic_counts.values())) != len(units):
        raise Phase5StressError("Combined pressure semantic unit counts are incomplete or ambiguous")
    if not isinstance(sequence, list) or len(sequence) < MINIMUM_EXECUTIONS:
        raise Phase5StressError("Combined pressure lacks its natural per-frame drain sequence")
    expected_indices = list(range(len(sequence)))
    if [frame.get("index") if isinstance(frame, dict) else None for frame in sequence] != expected_indices:
        raise Phase5StressError("Combined pressure frame order is not exact")
    count_to_unit = {count: unit for unit, count in semantic_counts.items()}
    events: list[dict[str, object]] = []
    enqueued_union = 0
    drained_union = 0
    first_queue: int | None = None
    first_drain: dict[str, int] = {}
    for frame in sequence:
        if not isinstance(frame, dict) or set(frame) != {
            "index", "public_target_writes", "enqueued_mask", "drained_mask",
            "remaining_cycles", "required_cycles",
        }:
            raise Phase5StressError("Combined pressure frame sequence is malformed")
        if any(
            not isinstance(frame[name], int) or frame[name] < 0
            for name in frame
        ):
            raise Phase5StressError("Combined pressure frame sequence has an invalid counter")
        index = int(frame["index"])
        enqueued = int(frame["enqueued_mask"])
        drained = int(frame["drained_mask"])
        enqueued_union |= enqueued
        drained_union |= drained
        if first_queue is None and enqueued & 0x07 == 0x07:
            first_queue = index
        if drained & 0x01 and "palette" not in first_drain:
            first_drain["palette"] = index
        if drained & 0x02 and "animation" not in first_drain:
            first_drain["animation"] = index
        public = int(frame["public_target_writes"])
        if public == 0:
            continue
        unit = count_to_unit.get(public)
        if unit is None:
            raise Phase5StressError(
                "Combined pressure overlapped units or published a partial/unknown unit"
            )
        events.append({"index": index, "unit": unit, "public_target_writes": public})
    if first_queue is None or enqueued_union & 0x07 != 0x07 or drained_union & 0x03 != 0x03:
        raise Phase5StressError("Combined pressure queue did not enqueue and drain every unit")
    if set(first_drain) != {"palette", "animation"}:
        raise Phase5StressError("Combined pressure lacks exact pressure drain observations")
    if not first_queue < first_drain["palette"] < first_drain["animation"]:
        raise Phase5StressError("Combined pressure drain order or latency exceeded its bound")
    first_publication: dict[str, int] = {}
    for event in events:
        first_publication.setdefault(str(event["unit"]), int(event["index"]))
    if set(first_publication) != set(units):
        raise Phase5StressError("Combined pressure did not naturally publish every semantic unit")
    vertical_frame = first_publication["vertical"]
    vertical_observation = sequence[vertical_frame]
    if not (
        first_publication["OAM"] < vertical_frame <= first_queue
        and first_queue < first_publication["palette"]
        < first_publication["animation"]
        and int(vertical_observation["enqueued_mask"]) & 0x07
    ):
        raise Phase5StressError(
            "Combined pressure column/order lacks the simultaneous pressure interval"
        )
    if not (
        first_drain["palette"] - first_queue <= 2
        and first_drain["animation"] - first_queue <= 4
    ):
        raise Phase5StressError("Combined pressure four-unit drain latency exceeded its bound")
    return {
        "schema": "full-color-phase5-serialized-drain-v1",
        "semantic_public_target_writes": dict(semantic_counts),
        "publication_events": events,
        "queue_first_seen_frame": first_queue,
        "drain_first_seen_frames": first_drain,
        "drain_order": ["palette", "animation"],
        "column_publication_frame": vertical_frame,
        "column_at_or_before_full_pressure_queue": True,
        "simultaneous_scroll_pressure_interval": True,
        "maximum_non_oam_drain_latency_frames": (
            first_drain["animation"] - first_queue
        ),
        "whole_unit_serialization": True,
        "oam_and_non_oam_same_frame": False,
        "deferred_unit_retry_identity_ref": (
            "boundary_matrix/RC-P5-COMBINED-PRESSURE-PALLET"
        ),
    }


def _boundary_threshold_contract_from_values(
    paired_base_cycles: int,
    paired_cell_cycles: int,
) -> dict[str, object]:
    if (
        type(paired_base_cycles) is not int
        or type(paired_cell_cycles) is not int
        or paired_base_cycles < 0
        or paired_cell_cycles < 0
    ):
        raise Phase5StressError("Phase 5 boundary linked cycle constants are invalid")
    extent = 1
    accepted = paired_base_cycles + extent * paired_cell_cycles
    # The threshold+1 mutation must also fit the exact u16 stress carrier.
    # Lifecycle timing never enters this arithmetic and is intentionally not
    # saturated or truncated into it.
    if not 1 <= accepted <= 0xFFFE:
        raise Phase5StressError(
            "Phase 5 boundary paired threshold is outside the exact u16 mutation range"
        )
    return {
        "role": "INDEPENDENT_SCHEDULER_ADMISSION_PROOF",
        "unit": "CPU_T_CYCLES_AT_ACTIVE_SPEED",
        "request_geometry": {
            "width": 1,
            "height": 1,
            "extent": extent,
            "semantic_public_target_writes": 2,
        },
        "linked_cycle_constants": {
            "base": {
                "symbol": BOUNDARY_PAIRED_BASE_CONSTANT,
                "value": paired_base_cycles,
            },
            "per_cell": {
                "symbol": BOUNDARY_PAIRED_CELL_CONSTANT,
                "value": paired_cell_cycles,
            },
        },
        "accepted_required_cycles": accepted,
        "equation": (
            f"{paired_base_cycles} + (1 * {paired_cell_cycles}) = {accepted} "
            "CPU T-cycles"
        ),
        "lifecycle_timing_source": False,
        "saturation_or_truncation": False,
    }


def _boundary_threshold_contract(root: Path) -> dict[str, object]:
    constants = _numeric_symbols(root / f"{AUDIT_PRODUCT}.sym")
    try:
        paired_base = constants[BOUNDARY_PAIRED_BASE_CONSTANT]
        paired_cell = constants[BOUNDARY_PAIRED_CELL_CONSTANT]
    except KeyError as exc:
        raise Phase5StressError(
            f"Phase 5 boundary cycle constant is not linked: {exc.args[0]}"
        ) from exc
    return _boundary_threshold_contract_from_values(paired_base, paired_cell)


def _validate_boundary_threshold_contract(raw: object) -> int:
    if not isinstance(raw, dict) or set(raw) != {
        "role", "unit", "request_geometry", "linked_cycle_constants",
        "accepted_required_cycles", "equation", "lifecycle_timing_source",
        "saturation_or_truncation",
    }:
        raise Phase5StressError("Phase 5 boundary threshold contract is malformed")
    geometry = raw["request_geometry"]
    linked = raw["linked_cycle_constants"]
    if (
        raw["role"] != "INDEPENDENT_SCHEDULER_ADMISSION_PROOF"
        or raw["unit"] != "CPU_T_CYCLES_AT_ACTIVE_SPEED"
        or raw["lifecycle_timing_source"] is not False
        or raw["saturation_or_truncation"] is not False
        or geometry != {
            "width": 1,
            "height": 1,
            "extent": 1,
            "semantic_public_target_writes": 2,
        }
        or not isinstance(linked, dict)
        or set(linked) != {"base", "per_cell"}
    ):
        raise Phase5StressError(
            "Phase 5 boundary threshold must be the independent exact 1x1 paired unit"
        )
    base = linked["base"]
    per_cell = linked["per_cell"]
    if (
        not isinstance(base, dict)
        or not isinstance(per_cell, dict)
        or base.get("symbol") != BOUNDARY_PAIRED_BASE_CONSTANT
        or per_cell.get("symbol") != BOUNDARY_PAIRED_CELL_CONSTANT
        or set(base) != {"symbol", "value"}
        or set(per_cell) != {"symbol", "value"}
        or type(base["value"]) is not int
        or type(per_cell["value"]) is not int
    ):
        raise Phase5StressError("Phase 5 boundary linked cycle equation is malformed")
    expected = _boundary_threshold_contract_from_values(
        base["value"], per_cell["value"]
    )
    if raw != expected:
        raise Phase5StressError("Phase 5 boundary linked cycle equation drifted")
    accepted = raw["accepted_required_cycles"]
    assert isinstance(accepted, int)
    return accepted


def capture_boundary_matrix(
    root: Path,
    output: Path,
) -> dict[str, object]:
    constants = _numeric_symbols(root / f"{AUDIT_PRODUCT}.sym")
    threshold_contract = _boundary_threshold_contract(root)
    accepted_threshold = int(threshold_contract["accepted_required_cycles"])
    rows: list[dict[str, object]] = []
    output.mkdir(parents=True, exist_ok=False)

    def paired_write_site(audit: Phase5AuditRom) -> tuple[int, int]:
        # The exact 1x1 admission probe takes the final general paired writer,
        # not either canonical 20x2/2x18 fast path. Count the public store at
        # the linked instruction seam and fail closed if its opcode pair moves.
        label = "FullColorPhase5PairedMapWrite"
        bank = audit.emulator.symbol_banks[label]
        address = audit.emulator.symbols[label]
        if bank == 0:
            raise Phase5StressError("paired public-write linkage moved to ROM0")
        rom = (root / f"{AUDIT_PRODUCT}.gbc").read_bytes()
        base = bank * 0x4000
        offset = base + address - 0x4000
        if rom[offset:offset + 2] != b"\x1a\x77":  # ld a,[de]; ld [hl],a
            raise Phase5StressError("linked paired public-write instruction drifted")
        return bank, address + 1

    def call_counting_public_writes(
        audit: Phase5AuditRom, site: tuple[int, int]
    ) -> tuple[int, int, int]:
        count = 0

        def mark(_: object) -> None:
            nonlocal count
            destination = audit.emulator.pyboy.register_file.HL
            if not 0x8000 <= destination <= 0x9FFF:
                raise Phase5StressError("paired commit write escaped public VRAM")
            count += 1

        audit.emulator.pyboy.hook_register(*site, mark, None)
        try:
            result, flags = audit.call("FullColorPhase5StressCheckpointSelected")
        finally:
            audit.emulator.pyboy.hook_deregister(*site)
        return result, flags, count

    for case_id, request_constant in BOUNDARY_REQUEST_CLASSES.items():
        for boundary in MUTABLE_BOUNDARIES:
            for mode, available, required, terminal_name in (
                (
                    "EXACT_FIT", accepted_threshold, accepted_threshold,
                    "FULL_COLOR_PHASE5_TERMINAL_COMPLETE",
                ),
                (
                    "THRESHOLD_PLUS_ONE", accepted_threshold,
                    accepted_threshold + 1,
                    "FULL_COLOR_PHASE5_TERMINAL_DEFERRED",
                ),
            ):
                cell_dir = output / f"cell-{len(rows):02d}"
                emulator = Emulator(
                    root / f"{AUDIT_PRODUCT}.gbc",
                    root / f"{AUDIT_PRODUCT}.sym",
                    cell_dir,
                    cgb=True,
                )
                audit = Phase5AuditRom(emulator, constants)
                try:
                    audit.activate()
                    write_site = paired_write_site(audit)
                    audit.admit_unit(request_constant)
                    target_before = (
                        emulator.read_vram_bank(0, 0x9800, 1)
                        + emulator.read_vram_bank(1, 0x9800, 1)
                    )
                    audit.call("FullColorPhase5StressReset")
                    admitted_descriptor = audit.read_wram2(
                        "wFullColorRequestDescriptors", 20
                    )
                    admitted_frozen = audit.read_wram2(
                        "wFullColorAttributeRectangle", 2
                    )
                    # The PREPARATION checkpoint may populate the internal
                    # frozen buffers, so those buffers are not part of the
                    # pre-admission/completed job identity. The normalized
                    # descriptor is: class, owner/generation, destination,
                    # original source, geometry, extent, and reservation.
                    admitted_job_identity = hashlib.sha256(
                        bytes((admitted_descriptor[0] & 0x0F,))
                        + admitted_descriptor[1:]
                    ).hexdigest()
                    control = b"".join((
                        bytes((
                            constants["FULL_COLOR_PHASE5_STRESS_MODE_ARMED"],
                            constants[request_constant],
                            constants[boundary],
                        )),
                        available.to_bytes(2, "little"),
                        required.to_bytes(2, "little"),
                        bytes(4),
                    ))
                    audit.write_wram2("wFullColorPhase5StressStateStart", control)
                    result, flags, first_public_writes = call_counting_public_writes(
                        audit, write_site
                    )
                    state = audit.read_wram2("wFullColorPhase5StressStateStart", 11)
                    trace = audit.read_wram2("wFullColorDebugTraceCountPhase2", PHASE2_TRACE_BYTES)
                    descriptor = audit.read_wram2("wFullColorRequestDescriptors", 20)
                    frozen = audit.read_wram2("wFullColorAttributeRectangle", 2)
                    request_count = audit.read_wram2("wFullColorRequestCount")[0]
                    retry_counter = audit.read_wram2("wFullColorRetryCounter")[0]
                    target_after_first = (
                        emulator.read_vram_bank(0, 0x9800, 1)
                        + emulator.read_vram_bank(1, 0x9800, 1)
                    )
                    first_public_changes = sum(
                        before != after
                        for before, after in zip(target_before, target_after_first, strict=True)
                    )
                    retained_identity = hashlib.sha256(
                        descriptor + frozen + bytes((request_count, retry_counter))
                    ).hexdigest()
                    if mode == "THRESHOLD_PLUS_ONE":
                        if first_public_writes != 0 or first_public_changes != 0 or request_count != 1:
                            raise Phase5StressError(
                                f"{case_id}/{boundary}: defer changed a public target or accounting"
                            )
                        # Poison caller storage, restore the exact independent
                        # cycle budget, and require the frozen paired unit to
                        # complete once without descriptor/accounting drift.
                        audit.write_fixed(0xC900, b"\xee\xff")
                        audit.write_wram2(
                            "wFullColorPhase5StressAvailableCycles",
                            required.to_bytes(2, "little"),
                        )
                        retry_identity = hashlib.sha256(
                            audit.read_wram2("wFullColorRequestDescriptors", 20)
                            + audit.read_wram2("wFullColorAttributeRectangle", 2)
                            + audit.read_wram2("wFullColorRequestCount")
                            + audit.read_wram2("wFullColorRetryCounter")
                        ).hexdigest()
                        retry_result, retry_flags, retry_public_writes = call_counting_public_writes(
                            audit, write_site
                        )
                    else:
                        retry_identity = retained_identity
                        retry_result, retry_flags = result, flags
                        retry_public_writes = 0
                    target_final = (
                        emulator.read_vram_bank(0, 0x9800, 1)
                        + emulator.read_vram_bank(1, 0x9800, 1)
                    )
                    final_descriptor = audit.read_wram2("wFullColorRequestDescriptors", 20)
                    final_frozen = audit.read_wram2("wFullColorAttributeRectangle", 2)
                    completed_job_identity = hashlib.sha256(
                        bytes((final_descriptor[0] & 0x0F,))
                        + final_descriptor[1:]
                    ).hexdigest()
                    final_request_count = audit.read_wram2("wFullColorRequestCount")[0]
                    transition_log = audit.read_wram2("wFullColorTransitionLog", 8)
                    post_retry_state = audit.read_wram2(
                        "wFullColorPhase5StressStateStart", 11
                    )
                finally:
                    emulator.close()
                terminal = constants[terminal_name]
                if result != terminal or state[10] != terminal:
                    raise Phase5StressError(
                        f"{case_id}/{boundary}/{mode}: unexpected terminal result"
                    )
                count = trace[0]
                if count > 8:
                    raise Phase5StressError("Phase 5 boundary trace exceeded capacity")
                entered_committing = any(
                    trace[2 + index * 24 + 1] == constants["COMMITTING"]
                    for index in range(count)
                )
                if mode == "THRESHOLD_PLUS_ONE" and (flags & 0x10 == 0 or entered_committing):
                    raise Phase5StressError(
                        f"{case_id}/{boundary}: threshold+1 did not defer pre-commit"
                    )
                completed_public_writes = sum(
                    before != after
                    for before, after in zip(target_before, target_final, strict=True)
                )
                commit_count = transition_log.count(constants["COMMITTING"])
                complete_count = transition_log.count(constants["COMPLETE"])
                completion_diagnostics = {
                    "retry_result": retry_result,
                    "complete_terminal": constants["FULL_COLOR_PHASE5_TERMINAL_COMPLETE"],
                    "retry_carry": bool(retry_flags & 0x10),
                    "final_request_count": final_request_count,
                    "final_descriptor_state": final_descriptor[0] >> 4,
                    "complete_state": constants["COMPLETE"],
                    "paired_publication": target_final.hex(),
                    "first_public_writes": first_public_writes,
                    "retry_public_writes": retry_public_writes,
                    "completed_public_changes": completed_public_writes,
                    "admitted_job_identity_sha256": admitted_job_identity,
                    "completed_job_identity_sha256": completed_job_identity,
                    "admitted_descriptor": admitted_descriptor.hex(),
                    "completed_descriptor": final_descriptor.hex(),
                    "admitted_frozen": admitted_frozen.hex(),
                    "completed_frozen": final_frozen.hex(),
                    "committing_transitions": commit_count,
                    "complete_transitions": complete_count,
                }
                if (
                    retry_result != constants["FULL_COLOR_PHASE5_TERMINAL_COMPLETE"]
                    or retry_flags & 0x10
                    or final_request_count != 0
                    or final_descriptor[0] >> 4 != constants["COMPLETE"]
                    or target_final != b"\x41\x06"
                    or first_public_writes + retry_public_writes != 2
                    or completed_public_writes != 2
                    or admitted_job_identity != completed_job_identity
                    or commit_count != 1
                    or complete_count != 1
                ):
                    _write_json(cell_dir / "completion-failure.json", completion_diagnostics)
                    raise Phase5StressError(
                        f"{case_id}/{boundary}/{mode}: paired unit was split or duplicated: "
                        f"{json.dumps(completion_diagnostics, sort_keys=True)}"
                    )
                if mode == "THRESHOLD_PLUS_ONE" and retry_identity != retained_identity:
                    raise Phase5StressError(
                        f"{case_id}/{boundary}: deferred descriptor or accounting drifted before retry"
                    )
                rows.append({
                    "case_id": case_id,
                    "boundary": boundary,
                    "mode": mode,
                    "request_class": request_constant,
                    "available_cycles": available,
                    "required_cycles": required,
                    "retry_available_cycles": (
                        required if mode == "THRESHOLD_PLUS_ONE" else None
                    ),
                    "result": "COMPLETE" if mode == "EXACT_FIT" else "DEFER",
                    "entered_committing": entered_committing,
                    "deferred_public_target_writes": first_public_writes if mode == "THRESHOLD_PLUS_ONE" else None,
                    "first_attempt_public_target_writes": first_public_writes,
                    "retry_public_target_writes": retry_public_writes,
                    "admitted_unit_identity_sha256": admitted_job_identity,
                    "retained_unit_identity_sha256": retained_identity,
                    "retry_unit_identity_sha256": retry_identity,
                    "completed_unit_identity_sha256": completed_job_identity,
                    "retry_result": "COMPLETE",
                    "final_descriptor_state": "COMPLETE",
                    "final_request_count": final_request_count,
                    "completed_units": 1,
                    "committing_transitions": commit_count,
                    "complete_transitions": complete_count,
                    "presented_target_writes": first_public_writes + retry_public_writes,
                    "presented_target_changes": completed_public_writes,
                    "paired_publication": target_final.hex(),
                    "stress_state": state.hex(),
                    "post_retry_stress_state": post_retry_state.hex(),
                    "trace_sha256": hashlib.sha256(trace).hexdigest(),
                })
    matrix = {
        "schema": "full-color-phase5-boundary-matrix-v1",
        "cycle_unit": "CPU_T_CYCLES_AT_ACTIVE_SPEED",
        "threshold_contract": threshold_contract,
        "rows": rows,
    }
    _write_json(output / "matrix.json", matrix)
    return matrix


def _derived_promoted_semantics(
    first: Mapping[str, object],
    second: Mapping[str, object],
    matrix: Mapping[str, object],
) -> dict[str, object]:
    compare_runs(first, second)
    first_rows = first.get("rows")
    second_rows = second.get("rows")
    if not isinstance(first_rows, list) or not isinstance(second_rows, list):
        raise Phase5StressError("Phase 5 authenticated runs lack row evidence")
    timing_rows = [
        _timing_row(row, first_rows[index], second_rows[index])
        for index, row in enumerate(ROWS)
    ]
    unit_row_ids = {
        "OAM": "OAM-build", "palette": "palette",
        "animation": "animation", "vertical": "vertical",
    }
    semantic_counts = {
        unit: int(next(
            row["descriptor_write_count_proposal"]["semantic_unit_target_writes"]
            for row in first_rows if row["row_id"] == row_id
        ))
        for unit, row_id in unit_row_ids.items()
    }
    combined_pressure = first_rows[0]["sameboy"]["pressure_accounting"]
    if not isinstance(combined_pressure, dict):
        raise Phase5StressError("Combined pressure accounting is malformed")
    return {
        "timing_rows": timing_rows,
        "descriptor_write_counts": [
            {"key": row.key, "proposal": first_rows[index]["descriptor_write_count_proposal"]}
            for index, row in enumerate(ROWS)
            if row.descriptor_class_constant is not None
        ],
        "write_diagnostics": [
            {"key": row.key, **first_rows[index]["write_diagnostics"]}
            for index, row in enumerate(ROWS)
        ],
        "pressure_accounting": [
            {"key": row.key, **first_rows[index]["sameboy"]["pressure_accounting"]}
            for index, row in enumerate(ROWS)
        ],
        "north_retry_evidence": [
            {
                "key": row.key,
                "producer_class_constant": row.descriptor_class_constant,
                **first_rows[index]["sameboy"]["producer_retry_evidence"],
            }
            for index, row in enumerate(ROWS) if row.row_id == "connection"
        ],
        "combined_serialized_drain": _serialized_drain_evidence(
            combined_pressure, semantic_counts
        ),
        "combined_semantic_public_write_breakdown": [
            {
                "key": row.key,
                "semantic_unit_target_writes": first_rows[index]["descriptor_write_count_proposal"]["semantic_unit_target_writes"],
                "semantic_unit_equation": first_rows[index]["descriptor_write_count_proposal"]["semantic_unit_equation"],
                "eventual_commit_corroboration": first_rows[index]["descriptor_write_count_proposal"]["eventual_commit_corroboration"],
            }
            for index, row in enumerate(ROWS)
            if row.row_id in {"palette", "vertical", "animation", "OAM-build"}
        ],
        "comparison": {
            "fresh_captures": 2,
            "byte_stable_outputs_traces_frame_strips": True,
            "minimum_natural_executions_per_path_per_run": MINIMUM_EXECUTIONS,
        },
        "boundary_matrix": dict(matrix),
    }


def produce(
    root: Path,
    tool_root: Path,
    results: Path,
    proposal_output: Path,
    *,
    samples: int = MINIMUM_EXECUTIONS,
    capture: Callable[..., dict[str, object]] = capture_run,
) -> dict[str, object]:
    if samples != MINIMUM_EXECUTIONS:
        raise Phase5StressError(
            f"each distinct path requires exactly {MINIMUM_EXECUTIONS} natural executions"
        )
    root = root.resolve()
    tool_root = tool_root.resolve()
    results = results.resolve()
    proposal_output = proposal_output.resolve()
    if proposal_output == (root / REVIEWED_PATH).resolve():
        raise Phase5StressError("proposal output cannot overwrite reviewed evidence")
    identities_before = capture_identities(root, tool_root)
    attempt = results / "attempt-0001"
    suffix = 1
    while attempt.exists():
        suffix += 1
        attempt = results / f"attempt-{suffix:04d}"
    attempt.mkdir(parents=True)
    first = capture(root, tool_root, attempt / "run-1", samples=samples)
    second = capture(root, tool_root, attempt / "run-2", samples=samples)
    compare_runs(first, second)
    identities_after = capture_identities(root, tool_root)
    if identities_before != identities_after:
        raise Phase5StressError("ROM/sym/map/source/tool identities changed during capture")
    first_rows = first["rows"]
    second_rows = second["rows"]
    assert isinstance(first_rows, list) and isinstance(second_rows, list)
    timing_rows = [
        _timing_row(row, first_rows[index], second_rows[index])
        for index, row in enumerate(ROWS)
    ]
    first_matrix = capture_boundary_matrix(root, attempt / "boundary-run-1")
    second_matrix = capture_boundary_matrix(root, attempt / "boundary-run-2")
    if _canonical(first_matrix) != _canonical(second_matrix):
        raise Phase5StressError("independent Phase 5 boundary matrices differ")
    unit_row_ids = {
        "OAM": "OAM-build",
        "palette": "palette",
        "animation": "animation",
        "vertical": "vertical",
    }
    semantic_counts = {
        unit: int(next(
            row["descriptor_write_count_proposal"]["semantic_unit_target_writes"]
            for row in first_rows
            if row["row_id"] == row_id
        ))
        for unit, row_id in unit_row_ids.items()
    }
    combined_pressure = first_rows[0]["sameboy"]["pressure_accounting"]
    if not isinstance(combined_pressure, dict):
        raise Phase5StressError("Combined pressure accounting is malformed")
    proposal = {
        "schema": SCHEMA,
        "reviewed": False,
        "authority": {
            "timing": "PINNED_SAMEBOY_DEBUGGER_TICKS",
            "behavioral_cross_check": "PYBOY_2_7_ONLY",
            "product": f"{AUDIT_PRODUCT}.gbc",
            "production_activation": False,
        },
        "identities": identities_after,
        "case_manifest": _case_manifest_binding(root),
        "production_admission": _production_admission_binding(root),
        "captures": [
            {"id": "run-1", "path": f"{attempt.name}/run-1/run.json", "sha256": _sha256(attempt / "run-1/run.json")},
            {"id": "run-2", "path": f"{attempt.name}/run-2/run.json", "sha256": _sha256(attempt / "run-2/run.json")},
        ],
        "timing_rows": timing_rows,
        "descriptor_write_counts": [
            {
                "key": row.key,
                "proposal": first_rows[index]["descriptor_write_count_proposal"],
            }
            for index, row in enumerate(ROWS)
            if row.descriptor_class_constant is not None
        ],
        "write_diagnostics": [
            {"key": row.key, **first_rows[index]["write_diagnostics"]}
            for index, row in enumerate(ROWS)
        ],
        "pressure_accounting": [
            {"key": row.key, **first_rows[index]["sameboy"]["pressure_accounting"]}
            for index, row in enumerate(ROWS)
        ],
        "north_retry_evidence": [
            {
                "key": row.key,
                "producer_class_constant": row.descriptor_class_constant,
                **first_rows[index]["sameboy"]["producer_retry_evidence"],
            }
            for index, row in enumerate(ROWS)
            if row.row_id == "connection"
        ],
        "combined_serialized_drain": _serialized_drain_evidence(
            combined_pressure, semantic_counts
        ),
        "combined_semantic_public_write_breakdown": [
            {
                "key": row.key,
                "semantic_unit_target_writes": first_rows[index]["descriptor_write_count_proposal"]["semantic_unit_target_writes"],
                "semantic_unit_equation": first_rows[index]["descriptor_write_count_proposal"]["semantic_unit_equation"],
                "eventual_commit_corroboration": first_rows[index]["descriptor_write_count_proposal"]["eventual_commit_corroboration"],
            }
            for index, row in enumerate(ROWS)
            if row.row_id in {"palette", "vertical", "animation", "OAM-build"}
        ],
        "comparison": {
            "fresh_captures": 2,
            "byte_stable_outputs_traces_frame_strips": True,
            "minimum_natural_executions_per_path_per_run": samples,
        },
        "boundary_matrix": first_matrix,
        "evidence_files": _artifact_refs(attempt, results),
    }
    _write_json(attempt / "proposal.json", proposal)
    proposal_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(attempt / "proposal.json", proposal_output)
    return proposal


def validate_proposal(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise Phase5StressError("Phase 5 proposal must be an object")
    required = {
        "schema", "reviewed", "authority", "identities", "case_manifest", "captures",
        "production_admission", "evidence_files",
        "timing_rows", "write_diagnostics", "pressure_accounting", "descriptor_write_counts",
        "combined_semantic_public_write_breakdown", "combined_serialized_drain",
        "north_retry_evidence", "comparison",
        "boundary_matrix",
    }
    schema = raw.get("schema")
    if set(raw) != required or schema not in {SCHEMA, REVIEWED_SCHEMA}:
        raise Phase5StressError("Phase 5 proposal has an unexpected schema or field set")
    if not isinstance(raw["reviewed"], bool):
        raise Phase5StressError("Phase 5 reviewed flag must be boolean")
    if schema == SCHEMA and raw["reviewed"]:
        raise Phase5StressError("an unreviewed proposal cannot claim review")
    if schema == REVIEWED_SCHEMA and raw["reviewed"] is not True:
        raise Phase5StressError("reviewed Phase 5 evidence must claim review")
    if raw["authority"] != {
        "timing": "PINNED_SAMEBOY_DEBUGGER_TICKS",
        "behavioral_cross_check": "PYBOY_2_7_ONLY",
        "product": f"{AUDIT_PRODUCT}.gbc",
        "production_activation": False,
    }:
        raise Phase5StressError("Phase 5 timing authority or product changed")
    manifest = raw["case_manifest"]
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"path", "schema", "sha256", "cases"}
        or manifest["path"] != "specs/full-colors/definitions/phase5-stress-cases.json"
        or manifest["schema"] != "full-color-phase5-stress-cases-v1"
        or not isinstance(manifest["cases"], list)
        or len(manifest["cases"]) != len(NATURAL_REQUEST_CLASSES)
    ):
        raise Phase5StressError("Phase 5 case manifest binding is malformed")
    manifest_hash = _require_hash(manifest["sha256"], path="case_manifest.sha256")
    identities = raw.get("identities")
    if isinstance(identities, dict) and isinstance(identities.get("source_files"), dict):
        if identities["source_files"].get(manifest["path"]) != manifest_hash:
            raise Phase5StressError("Phase 5 case manifest identity drifted")
    for case_id, binding in zip(NATURAL_REQUEST_CLASSES, manifest["cases"], strict=True):
        expected_rows = [row.key for row in ROWS if row.case_id == case_id]
        if (
            not isinstance(binding, dict)
            or set(binding) != {
                "id", "natural_request_class", "boundary_request_class",
                "timing_rows", "writer_ids", "scene_ids", "mutation_ids",
                "dependency_inventory_rows", "writer_bindings", "dependency_roots",
            }
            or binding["id"] != case_id
            or binding["natural_request_class"] != NATURAL_REQUEST_CLASSES[case_id]
            or binding["boundary_request_class"] != BOUNDARY_REQUEST_CLASSES[case_id]
            or binding["timing_rows"] != expected_rows
        ):
            raise Phase5StressError(f"{case_id}: case manifest execution binding drifted")
        for name, prefixes in (
            ("writer_ids", ("WR-",)),
            ("scene_ids", ("SC-",)),
            ("mutation_ids", ("MU-",)),
            ("dependency_inventory_rows", ("WR-", "SC-", "MU-")),
        ):
            values = binding.get(name)
            if (
                not isinstance(values, list)
                or values != list(dict.fromkeys(values))
                or any(
                    not isinstance(value, str) or not value.startswith(prefixes)
                    for value in values
                )
            ):
                raise Phase5StressError(f"{case_id}: malformed case manifest {name}")
        writer_bindings = binding.get("writer_bindings")
        if (
            not isinstance(writer_bindings, list)
            or len(writer_bindings) != len(binding["writer_ids"])
            or any(
                not isinstance(writer, dict)
                or writer.get("id") != writer_id
                or not isinstance(writer.get("source_path"), str)
                or not writer["source_path"]
                or not isinstance(writer.get("linked_symbol"), str)
                or not writer["linked_symbol"]
                for writer_id, writer in zip(
                    binding["writer_ids"], writer_bindings, strict=True
                )
            )
        ):
            raise Phase5StressError(f"{case_id}: malformed case manifest writer_bindings")
        dependency_roots = binding.get("dependency_roots")
        if (
            not isinstance(dependency_roots, list)
            or [
                dependency.get("row_id") if isinstance(dependency, dict) else None
                for dependency in dependency_roots
            ] != binding["dependency_inventory_rows"]
            or any(
                not isinstance(dependency, dict)
                or set(dependency) not in (
                    {"row_id", "executed_root", "scope"},
                    {"row_id", "executed_root", "linked_origin", "scope"},
                )
                or not isinstance(dependency.get("executed_root"), str)
                or not dependency["executed_root"]
                or not isinstance(dependency.get("scope"), str)
                or not dependency["scope"]
                or (
                    "linked_origin" in dependency
                    and (
                        not isinstance(dependency["linked_origin"], str)
                        or not dependency["linked_origin"]
                    )
                )
                for dependency in dependency_roots
            )
        ):
            raise Phase5StressError(f"{case_id}: malformed case manifest dependency_roots")
    if not isinstance(raw["captures"], list) or len(raw["captures"]) != 2:
        raise Phase5StressError("Phase 5 requires exactly two fresh captures")
    for index, capture in enumerate(raw["captures"], 1):
        capture_path = Path(str(capture.get("path"))) if isinstance(capture, dict) else Path()
        capture_parts = capture_path.parts
        if (
            not isinstance(capture, dict)
            or set(capture) != {"id", "path", "sha256"}
            or capture["id"] != f"run-{index}"
            or len(capture_parts) != 3
            or capture_parts[0] != PINNED_REVIEW_ATTEMPT
            or capture_parts[1:] != (f"run-{index}", "run.json")
        ):
            raise Phase5StressError("Phase 5 capture identity or order drifted")
        _require_hash(capture["sha256"], path=f"captures.run-{index}.sha256")
    if raw["captures"][0]["path"].split("/", 1)[0] != raw["captures"][1]["path"].split("/", 1)[0]:
        raise Phase5StressError("Phase 5 captures do not belong to one fresh attempt")
    attempt_name = raw["captures"][0]["path"].split("/", 1)[0]
    if attempt_name != PINNED_REVIEW_ATTEMPT:
        raise Phase5StressError(
            f"Phase 5 authority is pinned to {PINNED_REVIEW_ATTEMPT}"
        )
    evidence_files = raw["evidence_files"]
    if not isinstance(evidence_files, list) or not evidence_files:
        raise Phase5StressError("Phase 5 evidence file manifest is absent")
    evidence_paths: list[str] = []
    for index, item in enumerate(evidence_files):
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise Phase5StressError("Phase 5 evidence file reference is malformed")
        path = item["path"]
        if (
            not isinstance(path, str)
            or Path(path).is_absolute()
            or Path(path).parts[:1] != (attempt_name,)
            or any(component in {"", ".", ".."} for component in Path(path).parts)
            or path.endswith("/proposal.json")
        ):
            raise Phase5StressError("Phase 5 evidence file reference escaped its attempt")
        _require_hash(item["sha256"], path=f"evidence_files[{index}].sha256")
        evidence_paths.append(path)
    if evidence_paths != sorted(set(evidence_paths)):
        raise Phase5StressError("Phase 5 evidence file references must be exact and sorted")
    required_refs = {
        *(str(capture["path"]) for capture in raw["captures"]),
        f"{attempt_name}/boundary-run-1/matrix.json",
        f"{attempt_name}/boundary-run-2/matrix.json",
    }
    if not required_refs <= set(evidence_paths):
        raise Phase5StressError("Phase 5 capture or boundary matrix reference is omitted")
    admission = raw["production_admission"]
    if (
        not isinstance(admission, dict)
        or admission.get("color_presented_maps") != 196
        or admission.get("yellow_presented_maps") != 28
        or admission.get("changed") is not False
        or admission.get("phase5_production_activation") is not False
    ):
        raise Phase5StressError("Phase 5 production admission binding is malformed")
    if not isinstance(raw["timing_rows"], list) or len(raw["timing_rows"]) != len(ROWS):
        raise Phase5StressError("Phase 5 timing rows do not cover every stable row")
    for index, descriptor in enumerate(ROWS):
        timing = raw["timing_rows"][index]
        if not isinstance(timing, dict):
            raise Phase5StressError("Phase 5 timing row must be an object")
        observed_breakpoints = timing.get("observed_breakpoint_offsets")
        if (
            not isinstance(observed_breakpoints, list)
            or not observed_breakpoints
            or any(
                not isinstance(offset, int) or offset < 0
                for offset in observed_breakpoints
            )
        ):
            raise Phase5StressError(f"{descriptor.key}: malformed timing breakpoint observations")
        extension = {
            "authority_product": "PHASE2_AUDIT_ONLY",
            "cycle_unit": "CPU_T_CYCLES_AT_ACTIVE_SPEED",
            "origin": descriptor.origin_label,
            "deadline": (
                "ORIGIN_PLUS_9120_CPU_T_CYCLES"
                if descriptor.deadline_kind == "FIXED_VBLANK"
                else descriptor.deadline_observation_label
            ),
            "deadline_equation": (
                "0 + 9120 = 9120 CPU T-cycles from natural VBlank origin"
                if descriptor.deadline_kind == "FIXED_VBLANK"
                else (
                    f"min({observed_breakpoints}) = {min(observed_breakpoints)} "
                    "CPU T-cycles from linked origin"
                )
            ),
            "guard_floor_equation": "1 double-speed scanline * 912 CPU T-cycles = 912 CPU T-cycles",
            "deadline_observation_role": (
                "HANDLER_END_DIAGNOSTIC_ONLY"
                if descriptor.deadline_kind == "FIXED_VBLANK"
                else "LINKED_PRESENTATION_DEADLINE"
            ),
            "breakpoint_overhead_t_cycles": 0,
            "descriptor_reservation_role": "SEPARATE_WRITE_COUNT_ADMISSION_EVIDENCE",
            "threshold_evidence_ref": f"boundary_matrix/{descriptor.case_id}",
        }
        if any(timing.get(name) != value for name, value in extension.items()):
            raise Phase5StressError(f"{descriptor.key}: timing authority equation drifted")
        if not isinstance(timing.get("pass_equation"), str):
            raise Phase5StressError(f"{descriptor.key}: missing explicit pass equation")
        finalizer = timing.get("owner_end_finalizer_invariants")
        if descriptor.row_id == "VBlank":
            if finalizer != {
                "post_end_public_target_writes": [0],
                "paired_fast_cache_valid_at_handler_end": [0],
                "paired_complete_at_owner_end": True,
                "paired_fast_cache_pending_at_owner_end": True,
                "fast_cache_pending_constant": FAST_CACHE_ACCOUNTING_PENDING_CONSTANT,
                "descriptor_complete_constant": "COMPLETE",
            }:
                raise Phase5StressError(
                    f"{descriptor.key}: owner End/finalizer invariant drifted"
                )
        elif finalizer != "NOT_OWNER_ROUTE_END":
            raise Phase5StressError(f"{descriptor.key}: unexpected owner End invariant")
        presentation_guard = timing.get("presentation_guard")
        if descriptor.row_id == "reconstruct-Color":
            if (
                not isinstance(presentation_guard, dict)
                or set(presentation_guard) != {
                    "start_label", "end_label", "cross_bank_farcall_roundtrip",
                    "guard_machine_code", "equation",
                    "operation_end_to_guard_start_role", "guard_end_to_deadline_role",
                    "minimum_observed_operation_end_to_deadline_t_cycles", "result",
                }
                or presentation_guard["start_label"]
                != PARTY_RECONSTRUCTION_GUARD_START
                or presentation_guard["end_label"]
                != PARTY_RECONSTRUCTION_GUARD_END
                or presentation_guard["cross_bank_farcall_roundtrip"] is not True
                or presentation_guard["guard_machine_code"] != "c506370520fdc1"
                or presentation_guard["equation"]
                != "16 + 8 + 54 * (4 + 12) + 4 + 8 + 12 = 912 CPU T-cycles"
                or presentation_guard["operation_end_to_guard_start_role"]
                != "SUCCESS_CHECK_AND_CROSS_BANK_FARCALL_INCLUDED_IN_MEASURED_END_TO_DEADLINE"
                or presentation_guard["guard_end_to_deadline_role"]
                != "CROSS_BANK_RETURN_INCLUDED_IN_MEASURED_END_TO_DEADLINE"
                or not isinstance(
                    presentation_guard[
                        "minimum_observed_operation_end_to_deadline_t_cycles"
                    ],
                    int,
                )
                or presentation_guard[
                    "minimum_observed_operation_end_to_deadline_t_cycles"
                ] <= 920
                or presentation_guard["result"] != "PASS"
            ):
                raise Phase5StressError(
                    f"{descriptor.key}: Party presentation guard proof drifted"
                )
        elif presentation_guard != "NOT_PARTY_RECONSTRUCTION":
            raise Phase5StressError(f"{descriptor.key}: unexpected presentation guard")
        extended = dict(timing)
        for name in (
            "authority_product", "cycle_unit", "origin", "deadline",
            "deadline_equation",
            "guard_floor_equation", "usable_equation", "pass_equation",
            "breakpoint_overhead_t_cycles", "descriptor_reservation_role",
            "observed_breakpoint_offsets", "measured_deadline_jitter_t_cycles",
            "deadline_observation_role",
            "threshold_evidence_ref", "observed_runtime_required_cycles",
            "observed_runtime_available_cycles", "runtime_required_equation",
            "runtime_admission_equation",
            "owner_end_finalizer_invariants", "presentation_guard",
        ):
            extended.pop(name, None)
        parsed = TimingRow.from_dict(extended)
        if parsed.key != descriptor.key or parsed.samples != 2 * MINIMUM_EXECUTIONS:
            raise Phase5StressError(f"{descriptor.key}: unstable timing identity or sample count")
        if (
            parsed.mode != "CGB_DOUBLE_SPEED"
            or (descriptor.deadline_kind == "FIXED_VBLANK" and parsed.deadline_cycle != NATURAL_VBLANK_DEADLINE_T_CYCLES)
            or parsed.guard_cycles < SCANLINE_GUARD_FLOOR_T_CYCLES
            or parsed.guard_cycles % 4 != 0
            or parsed.instrumentation_cycles != 0
            or parsed.margin_cycles <= 0
            or parsed.result != "PASS"
        ):
            raise Phase5StressError(f"{descriptor.key}: invalid natural timing equation")
        expected_pass = (
            f"{parsed.worst_cycles} + 0 <= {parsed.deadline_cycle} - "
            f"{parsed.start_cycle} - {parsed.guard_cycles}"
        )
        if timing["pass_equation"] != expected_pass:
            raise Phase5StressError(f"{descriptor.key}: pass equation changed")
        expected_usable = (
            f"{parsed.deadline_cycle} - {parsed.start_cycle} - "
            f"{parsed.guard_cycles} = {parsed.defer_threshold} CPU T-cycles"
        )
        if timing.get("usable_equation") != expected_usable:
            raise Phase5StressError(f"{descriptor.key}: usable equation changed")
        runtime_required = timing.get("observed_runtime_required_cycles")
        runtime_available = timing.get("observed_runtime_available_cycles")
        if not isinstance(runtime_available, list) or any(
            not isinstance(value, int) or value < 0 for value in runtime_available
        ):
            if descriptor.row_id in {"palette", "vertical", "animation", "OAM-DMA"}:
                raise Phase5StressError(f"{descriptor.key}: missing runtime available-cycle evidence")
        if not isinstance(runtime_required, list) or any(
            not isinstance(value, int) or value <= 0 for value in runtime_required
        ):
            if descriptor.row_id in {"palette", "vertical", "animation", "OAM-DMA"}:
                raise Phase5StressError(f"{descriptor.key}: missing runtime cycle reservation evidence")
        elif descriptor.row_id in {"palette", "vertical", "animation", "OAM-DMA"} and min(runtime_required) < parsed.worst_cycles:
            raise Phase5StressError(f"{descriptor.key}: runtime cycle table understates observation")
        expected_admission = (
            "FrameAvailableCycles is remaining after accepted units; "
            f"remaining={runtime_available}, required={runtime_required}, "
            f"min(required) >= measured {parsed.worst_cycles} CPU T-cycles"
            if runtime_available and runtime_required
            else "NOT_A_SINGLE_VBLANK_DESCRIPTOR_COMMIT"
        )
        if timing.get("runtime_admission_equation") != expected_admission:
            raise Phase5StressError(f"{descriptor.key}: runtime admission equation drifted")
    pressure = raw["pressure_accounting"]
    if not isinstance(pressure, list) or len(pressure) != len(ROWS):
        raise Phase5StressError("Phase 5 pressure accounting is incomplete")
    for item, descriptor in zip(pressure, ROWS, strict=True):
        names = (
            "enqueued_masks_at_end", "drained_masks_at_end",
            "enqueued_masks_at_deadline", "drained_masks_at_deadline",
        )
        if (
            not isinstance(item, dict)
            or set(item) != {"key", *names, "frame_sequence"}
            or item["key"] != descriptor.key
        ):
            raise Phase5StressError(f"{descriptor.key}: pressure accounting is malformed")
        for name in names:
            values = item[name]
            if (
                not isinstance(values, list) or not values
                or any(not isinstance(value, int) or not 0 <= value <= 0xFF for value in values)
                or values != sorted(set(values))
            ):
                raise Phase5StressError(f"{descriptor.key}: {name} is malformed")
        frame_sequence = item["frame_sequence"]
        if (
            not isinstance(frame_sequence, list)
            or len(frame_sequence) != MINIMUM_EXECUTIONS
            or [
                frame.get("index") if isinstance(frame, dict) else None
                for frame in frame_sequence
            ] != list(range(len(frame_sequence)))
        ):
            raise Phase5StressError(f"{descriptor.key}: pressure frame sequence is malformed")
        for frame in frame_sequence:
            if (
                not isinstance(frame, dict)
                or set(frame) != {
                    "index", "public_target_writes", "enqueued_mask", "drained_mask",
                    "remaining_cycles", "required_cycles",
                }
                or any(not isinstance(value, int) or value < 0 for value in frame.values())
            ):
                raise Phase5StressError(f"{descriptor.key}: pressure frame is malformed")
        if (
            sorted({int(frame["enqueued_mask"]) for frame in frame_sequence})
            != item["enqueued_masks_at_end"]
            or sorted({int(frame["drained_mask"]) for frame in frame_sequence})
            != item["drained_masks_at_end"]
        ):
            raise Phase5StressError(f"{descriptor.key}: pressure frame summary drifted")
        enqueued_union = 0
        drained_union = 0
        for value in item["enqueued_masks_at_deadline"]:
            enqueued_union |= value
        for value in item["drained_masks_at_deadline"]:
            drained_union |= value
        if drained_union & ~enqueued_union:
            raise Phase5StressError(f"{descriptor.key}: drained pressure was never enqueued")
        expected_bit = {"palette": 1, "animation": 2, "OAM-build": 4, "OAM-DMA": 4}.get(
            descriptor.row_id
        )
        if expected_bit is not None and enqueued_union & expected_bit == 0:
            raise Phase5StressError(f"{descriptor.key}: expected pressure unit was not enqueued")
        if descriptor.row_id == "VBlank" and (enqueued_union & 7 != 7 or drained_union & 3 != 3):
            raise Phase5StressError(f"{descriptor.key}: combined pressure did not fully drain")
    north_retry = raw["north_retry_evidence"]
    connection = next(row for row in ROWS if row.row_id == "connection")
    if (
        not isinstance(north_retry, list)
        or len(north_retry) != 1
        or not isinstance(north_retry[0], dict)
        or set(north_retry[0]) != {
            "key", "producer_class_constant", "schema", "samples"
        }
        or north_retry[0]["key"] != connection.key
        or north_retry[0]["producer_class_constant"]
        != connection.descriptor_class_constant
        or north_retry[0]["schema"] != "full-color-phase5-producer-retry-v1"
        or not isinstance(north_retry[0]["samples"], list)
        or len(north_retry[0]["samples"]) != MINIMUM_EXECUTIONS
    ):
        raise Phase5StressError("Phase 5 North producer/retry evidence is malformed")
    retry_fields = {
        "index", "producer_class", "producer_destination", "producer_width",
        "producer_height", "producer_extent", "producer_payload_sha256",
        "retry_admit_hits", "retry_finish_hits", "retry_publish_hits",
        "retry_publish_result", "completed_descriptor_destination",
        "completed_descriptor_address", "completed_descriptor_state",
        "completed_descriptor_result",
    }
    for index, sample in enumerate(north_retry[0]["samples"]):
        if (
            not isinstance(sample, dict)
            or set(sample) != retry_fields
            or sample["index"] != index
            or sample["producer_destination"] != sample["completed_descriptor_destination"]
            or not 0xD000 <= sample["completed_descriptor_address"] <= 0xDFFF
            or sample["producer_width"] * sample["producer_height"]
            != sample["producer_extent"]
            or sample["retry_admit_hits"] <= 0
            or sample["retry_finish_hits"] <= 0
            or sample["retry_publish_hits"] <= 0
            or sample["completed_descriptor_result"] != "COMPLETE"
            or sample["completed_descriptor_state"] & 0x0F
            != sample["producer_class"]
            or sample["completed_descriptor_state"] & 0xF0 == 0
            or any(
                not isinstance(sample[name], int) or not 0 <= sample[name] <= 0xFFFF
                for name in retry_fields - {
                    "producer_payload_sha256", "completed_descriptor_result"
                }
            )
        ):
            raise Phase5StressError("Phase 5 North producer/retry proof drifted")
        _require_hash(
            sample["producer_payload_sha256"],
            path=f"north_retry_evidence.samples[{index}].producer_payload_sha256",
        )
    matrix = raw["boundary_matrix"]
    if (
        not isinstance(matrix, dict)
        or set(matrix) != {"schema", "cycle_unit", "threshold_contract", "rows"}
        or matrix["schema"] != "full-color-phase5-boundary-matrix-v1"
        or matrix["cycle_unit"] != "CPU_T_CYCLES_AT_ACTIVE_SPEED"
        or not isinstance(matrix["rows"], list)
        or len(matrix["rows"]) != len(BOUNDARY_REQUEST_CLASSES) * len(MUTABLE_BOUNDARIES) * 2
    ):
        raise Phase5StressError("Phase 5 boundary matrix is incomplete")
    threshold = _validate_boundary_threshold_contract(matrix["threshold_contract"])
    expected_matrix_keys = [
        (case_id, boundary, mode)
        for case_id in BOUNDARY_REQUEST_CLASSES
        for boundary in MUTABLE_BOUNDARIES
        for mode in ("EXACT_FIT", "THRESHOLD_PLUS_ONE")
    ]
    for expected, cell in zip(expected_matrix_keys, matrix["rows"], strict=True):
        if not isinstance(cell, dict) or set(cell) != {
            "case_id", "boundary", "mode", "request_class",
            "available_cycles", "required_cycles", "retry_available_cycles", "result",
            "entered_committing", "deferred_public_target_writes",
            "first_attempt_public_target_writes", "retry_public_target_writes",
            "admitted_unit_identity_sha256",
            "retained_unit_identity_sha256", "retry_unit_identity_sha256",
            "completed_unit_identity_sha256",
            "retry_result", "final_descriptor_state", "final_request_count",
            "completed_units", "committing_transitions", "complete_transitions",
            "presented_target_writes", "presented_target_changes", "paired_publication",
            "stress_state", "post_retry_stress_state", "trace_sha256",
        }:
            raise Phase5StressError("Phase 5 boundary matrix cell is malformed")
        case_id, boundary, mode = expected
        required = threshold + (mode == "THRESHOLD_PLUS_ONE")
        if (
            (cell["case_id"], cell["boundary"], cell["mode"]) != expected
            or cell["request_class"] != BOUNDARY_REQUEST_CLASSES[case_id]
            or cell["required_cycles"] != required
            or cell["available_cycles"] != threshold
            or cell["retry_available_cycles"] != (
                required if mode == "THRESHOLD_PLUS_ONE" else None
            )
            or cell["result"] != ("COMPLETE" if mode == "EXACT_FIT" else "DEFER")
            or cell["entered_committing"] is not (mode == "EXACT_FIT")
            or cell["deferred_public_target_writes"] != (
                0 if mode == "THRESHOLD_PLUS_ONE" else None
            )
            or cell["first_attempt_public_target_writes"] != (
                0 if mode == "THRESHOLD_PLUS_ONE" else 2
            )
            or cell["retry_public_target_writes"] != (
                2 if mode == "THRESHOLD_PLUS_ONE" else 0
            )
            or cell["retry_result"] != "COMPLETE"
            or cell["final_descriptor_state"] != "COMPLETE"
            or cell["final_request_count"] != 0
            or cell["completed_units"] != 1
            or cell["committing_transitions"] != 1
            or cell["complete_transitions"] != 1
            or cell["presented_target_writes"] != 2
            or cell["presented_target_changes"] != 2
            or cell["paired_publication"] != "4106"
            or not isinstance(cell["stress_state"], str)
            or len(cell["stress_state"]) != 22
            or not isinstance(cell["post_retry_stress_state"], str)
            or len(cell["post_retry_stress_state"]) != 22
        ):
            raise Phase5StressError("Phase 5 boundary matrix result drifted")
        state = bytes.fromhex(cell["stress_state"])
        post_retry_state = bytes.fromhex(cell["post_retry_stress_state"])
        if (
            int.from_bytes(state[3:5], "little") != threshold
            or int.from_bytes(state[5:7], "little") != required
            or int.from_bytes(post_retry_state[3:5], "little") != (
                required if mode == "THRESHOLD_PLUS_ONE" else threshold
            )
            or int.from_bytes(post_retry_state[5:7], "little") != required
        ):
            raise Phase5StressError("Phase 5 boundary retry cycle carrier drifted")
        retained = _require_hash(
            cell["retained_unit_identity_sha256"],
            path="boundary_matrix.retained_unit_identity_sha256",
        )
        retried = _require_hash(
            cell["retry_unit_identity_sha256"],
            path="boundary_matrix.retry_unit_identity_sha256",
        )
        admitted = _require_hash(
            cell["admitted_unit_identity_sha256"],
            path="boundary_matrix.admitted_unit_identity_sha256",
        )
        completed = _require_hash(
            cell["completed_unit_identity_sha256"],
            path="boundary_matrix.completed_unit_identity_sha256",
        )
        if admitted != completed:
            raise Phase5StressError("Phase 5 completed a substituted unit")
        if mode == "THRESHOLD_PLUS_ONE" and retained != retried:
            raise Phase5StressError("Phase 5 deferred unit identity drifted before retry")
        _require_hash(cell["trace_sha256"], path="boundary_matrix.trace_sha256")
    descriptor_rows = [row for row in ROWS if row.descriptor_class_constant is not None]
    diagnostics = raw["write_diagnostics"]
    if not isinstance(diagnostics, list) or len(diagnostics) != len(ROWS):
        raise Phase5StressError("Phase 5 public/preparation write diagnostics are incomplete")
    for item, descriptor in zip(diagnostics, ROWS, strict=True):
        if (
            not isinstance(item, dict)
            or set(item) != {
                "key", "public_target_writes_within_interval",
                "preparation_buffer_writes", "descriptor_metadata_writes_included",
                "cycle_budget_role",
            }
            or item["key"] != descriptor.key
            or item["descriptor_metadata_writes_included"] is not False
            or item["cycle_budget_role"] != "NONE"
        ):
            raise Phase5StressError(f"{descriptor.key}: write diagnostics are malformed")
        for name in ("public_target_writes_within_interval", "preparation_buffer_writes"):
            counts = item[name]
            if (
                not isinstance(counts, list) or not counts
                or any(not isinstance(value, int) or value < 0 for value in counts)
                or counts != sorted(set(counts))
            ):
                raise Phase5StressError(f"{descriptor.key}: {name} is malformed")
    if (
        not isinstance(raw["descriptor_write_counts"], list)
        or len(raw["descriptor_write_counts"]) != len(descriptor_rows)
    ):
        raise Phase5StressError("Phase 5 descriptor write-count proposals are incomplete")
    for index, descriptor in enumerate(descriptor_rows):
        item = raw["descriptor_write_counts"][index]
        if not isinstance(item, dict) or item.get("key") != descriptor.key:
            raise Phase5StressError("Phase 5 descriptor write-count row identity drifted")
        proposal = item.get("proposal")
        if (
            not isinstance(proposal, dict)
            or set(proposal) != {
                "authority", "unit", "request_class_constant",
                "observed_descriptor", "semantic_unit_target_writes",
                "semantic_unit_equation", "eventual_commit_corroboration",
                "proposed_target_write_count", "changes_admission",
                "cycle_budget_role",
            }
            or proposal.get("authority") != "UNREVIEWED_PROPOSAL_ONLY"
            or proposal.get("unit") != "DESCRIPTOR_SEMANTIC_PUBLIC_TARGET_WRITES"
            or proposal.get("request_class_constant") != descriptor.descriptor_class_constant
            or proposal.get("changes_admission") is not False
            or proposal.get("cycle_budget_role") != "NONE"
        ):
            raise Phase5StressError(f"{descriptor.key}: invalid descriptor write-count proposal")
        observed = proposal["observed_descriptor"]
        semantic = proposal["semantic_unit_target_writes"]
        corroboration = proposal["eventual_commit_corroboration"]
        if (
            not isinstance(observed, dict)
            or set(observed) != {"class", "width", "height", "extent"}
            or any(not isinstance(value, int) or value < 0 for value in observed.values())
            or not isinstance(semantic, int) or semantic <= 0
            or proposal["proposed_target_write_count"] != semantic
            or not isinstance(proposal["semantic_unit_equation"], str)
            or not isinstance(corroboration, dict)
            or set(corroboration) != {
                "end_trace_sha256", "presentation_trace_sha256",
                "presentation_trace_differs_from_end",
                "eventual_public_target_writes",
                "enqueued_masks_at_deadline", "drained_masks_at_deadline",
            }
        ):
            raise Phase5StressError(f"{descriptor.key}: write-count proposal is malformed")
        for name in ("end_trace_sha256", "presentation_trace_sha256"):
            hashes = corroboration[name]
            if not isinstance(hashes, list) or not hashes:
                raise Phase5StressError(f"{descriptor.key}: eventual commit trace is missing")
            for trace_hash in hashes:
                _require_hash(trace_hash, path=f"{descriptor.key}.{name}")
        for name in (
            "presentation_trace_differs_from_end",
            "eventual_public_target_writes",
            "enqueued_masks_at_deadline", "drained_masks_at_deadline",
        ):
            values = corroboration[name]
            if not isinstance(values, list) or not values or values != sorted(set(values)):
                raise Phase5StressError(f"{descriptor.key}: eventual commit accounting is malformed")
        expected_semantic = observed["extent"] * (
            2 if descriptor.semantic_write_kind == "PAIRED_PLANES" else 1
        )
        if semantic != expected_semantic:
            raise Phase5StressError(f"{descriptor.key}: semantic target count is not class/geometry derived")
        diagnostic = next(item for item in diagnostics if item["key"] == descriptor.key)
        public_counts = diagnostic["public_target_writes_within_interval"]
        if descriptor.row_id in {"palette", "vertical", "animation", "OAM-DMA"}:
            if public_counts != [semantic]:
                raise Phase5StressError(f"{descriptor.key}: public commit count drifted")
        elif descriptor.row_id == "connection" and public_counts != [0]:
            raise Phase5StressError(f"{descriptor.key}: enqueue wrote a public target")
        elif descriptor.row_id == "OAM-build" and any(
            value > semantic for value in public_counts
        ):
            raise Phase5StressError(f"{descriptor.key}: preparation exceeded semantic unit")
        if descriptor.row_id in {"OAM-build", "connection"} and corroboration[
            "eventual_public_target_writes"
        ] != [semantic]:
            raise Phase5StressError(f"{descriptor.key}: eventual public commit count drifted")
    breakdown = raw["combined_semantic_public_write_breakdown"]
    breakdown_rows = [
        row for row in ROWS
        if row.row_id in {"palette", "vertical", "animation", "OAM-build"}
    ]
    if not isinstance(breakdown, list) or len(breakdown) != len(breakdown_rows):
        raise Phase5StressError("combined pressure lacks its per-unit semantic write breakdown")
    by_key = {
        item["key"]: item["proposal"]
        for item in raw["descriptor_write_counts"]
    }
    connection = next(row for row in ROWS if row.row_id == "connection")
    connection_observed = by_key[connection.key]["observed_descriptor"]
    for sample in north_retry[0]["samples"]:
        if {
            "class": sample["producer_class"],
            "width": sample["producer_width"],
            "height": sample["producer_height"],
            "extent": sample["producer_extent"],
        } != connection_observed:
            raise Phase5StressError(
                "Phase 5 North producer identity differs from eventual linked descriptor"
            )
    for item, descriptor in zip(breakdown, breakdown_rows, strict=True):
        proposal = by_key[descriptor.key]
        expected = {
            "key": descriptor.key,
            "semantic_unit_target_writes": proposal["semantic_unit_target_writes"],
            "semantic_unit_equation": proposal["semantic_unit_equation"],
            "eventual_commit_corroboration": proposal["eventual_commit_corroboration"],
        }
        if item != expected:
            raise Phase5StressError("combined pressure semantic breakdown drifted or was summed")
    combined_counts = {
        "OAM": int(by_key[ROW_BY_KEY[
            "RC-P5-COMBINED-PRESSURE-PALLET/OAM-build"
        ].key]["semantic_unit_target_writes"]),
        "palette": int(by_key[ROW_BY_KEY[
            "RC-P5-COMBINED-PRESSURE-PALLET/palette"
        ].key]["semantic_unit_target_writes"]),
        "animation": int(by_key[ROW_BY_KEY[
            "RC-P5-COMBINED-PRESSURE-PALLET/animation"
        ].key]["semantic_unit_target_writes"]),
        "vertical": int(by_key[ROW_BY_KEY[
            "RC-P5-COMBINED-PRESSURE-PALLET/vertical"
        ].key]["semantic_unit_target_writes"]),
    }
    expected_serialized = _serialized_drain_evidence(pressure[0], combined_counts)
    if raw["combined_serialized_drain"] != expected_serialized:
        raise Phase5StressError("Combined pressure serialized drain evidence drifted")
    comparison = raw["comparison"]
    if (
        not isinstance(comparison, dict)
        or comparison.get("fresh_captures") != 2
        or comparison.get("byte_stable_outputs_traces_frame_strips") is not True
        or comparison.get("minimum_natural_executions_per_path_per_run")
        != MINIMUM_EXECUTIONS
    ):
        raise Phase5StressError("Phase 5 comparison contract is incomplete")
    return raw


def _validate_authenticated_run_artifacts(
    run: Mapping[str, object],
    *,
    run_index: int,
    attempt_name: str,
    payloads: Mapping[str, bytes],
    constants: Mapping[str, int],
) -> None:
    rows = run.get("rows")
    if not isinstance(rows, list) or len(rows) != len(ROWS):
        raise Phase5StressError("authenticated Phase 5 run has incomplete rows")
    for row_index, (descriptor, row) in enumerate(zip(ROWS, rows, strict=True)):
        if (
            not isinstance(row, dict)
            or row.get("schema") != ROW_SCHEMA
            or (row.get("case_id"), row.get("row_id"))
            != (descriptor.case_id, descriptor.row_id)
            or row.get("natural_executions") != MINIMUM_EXECUTIONS
        ):
            raise Phase5StressError(f"authenticated row {descriptor.key} is malformed")
        expected_row_fields = {
            "schema", "case_id", "row_id", "operation", "scenario_constant",
            "natural_arm_constant", "start_label", "end_label", "origin_label",
            "deadline_observation_label", "deadline_observation_role",
            "deadline_kind", "natural_executions", "sameboy", "pyboy",
            "write_diagnostics",
        }
        if descriptor.descriptor_class_constant is not None:
            expected_row_fields.add("descriptor_write_count_proposal")
        if set(row) != expected_row_fields:
            raise Phase5StressError(f"authenticated row {descriptor.key} has extra fields")
        row_base = f"{attempt_name}/run-{run_index}/row-{row_index:02d}"
        row_path = f"{row_base}/row.json"
        if payloads[row_path] != _canonical(row).encode("utf-8"):
            raise Phase5StressError(f"authenticated row artifact {row_path} drifted")
        for device in ("sameboy", "pyboy"):
            capture = row.get(device)
            if not isinstance(capture, dict):
                raise Phase5StressError(f"{descriptor.key}: missing {device} capture")
            for field in ("raw_capture_sha256", "semantic_sha256", "trace_sha256"):
                _require_hash(capture.get(field), path=f"{descriptor.key}.{device}.{field}")
            capture_path = f"{row_base}/{device}/capture.json"
            capture_raw = _decode_strict_json(payloads[capture_path], path=capture_path)
            if hashlib.sha256(payloads[capture_path]).hexdigest() != capture["raw_capture_sha256"]:
                raise Phase5StressError(f"{descriptor.key}: {device} raw capture drifted")
            if device == "sameboy":
                parsed = _validate_driver_capture(
                    descriptor, capture_raw, constants=constants,
                    samples=MINIMUM_EXECUTIONS,
                )
                calibration = capture_raw["calibration"]
                expected_fields: dict[str, object] = {
                    "cycles": [sample["ticks"] for sample in parsed],
                    "timing_observations": [
                        {name: sample[name] for name in (
                            "start_offset", "end_offset", "deadline_offset",
                            "end_ly", "end_stat", "deadline_ly", "deadline_stat",
                            "available_cycles_at_end", "required_cycles_at_end",
                            "available_cycles_at_deadline", "required_cycles_at_deadline",
                            "public_target_writes", "post_end_public_target_writes",
                            "active_descriptor_state_at_end",
                            "active_descriptor_state_at_deadline",
                            "active_descriptor_address_at_end",
                            "active_descriptor_address_at_deadline",
                            "active_descriptor_destination_at_end",
                            "active_descriptor_destination_at_deadline",
                            "fast_cache_valid_at_end", "fast_cache_valid_at_deadline",
                            "request_count_at_end", "request_count_at_deadline",
                        )}
                        for sample in parsed
                    ],
                    "tick_calibration": calibration,
                    "semantic_sha256": hashlib.sha256(b"".join(
                        bytes.fromhex(str(sample["scenario"]))
                        + bytes.fromhex(str(sample["stress"]))
                        + bytes.fromhex(str(sample["post_scenario"]))
                        + bytes((int(sample["post_owner"]), int(sample["post_phase"])))
                        for sample in parsed
                    )).hexdigest(),
                    "trace_sha256": hashlib.sha256(b"".join(
                        bytes.fromhex(str(sample["trace"])) for sample in parsed
                    )).hexdigest(),
                    "pressure_accounting": {
                        "enqueued_masks_at_end": sorted({int(s["enqueued_mask_at_end"]) for s in parsed}),
                        "drained_masks_at_end": sorted({int(s["drained_mask_at_end"]) for s in parsed}),
                        "enqueued_masks_at_deadline": sorted({int(s["enqueued_mask_at_deadline"]) for s in parsed}),
                        "drained_masks_at_deadline": sorted({int(s["drained_mask_at_deadline"]) for s in parsed}),
                        "frame_sequence": [{
                            "index": int(s["index"]),
                            "public_target_writes": int(s["public_target_writes"]),
                            "enqueued_mask": int(s["enqueued_mask_at_end"]),
                            "drained_mask": int(s["drained_mask_at_end"]),
                            "remaining_cycles": int(s["available_cycles_at_end"]),
                            "required_cycles": int(s["required_cycles_at_end"]),
                        } for s in parsed],
                    },
                }
                equations = {
                    "instruction_unit": "16 NOP * 4 CPU T-cycles = 64 SameBoy debugger ticks",
                    "scanline": "140448 full-frame ticks / 154 PPU scanlines = 912 CPU T-cycles",
                    "natural_vblank": "10 PPU scanlines * 912 CPU T-cycles = 9120 CPU T-cycles",
                    "register_polling": (
                        f"raw LY144->LY145 {calibration['ly144_to_ly145_register_ticks']} ticks; "
                        f"raw LY144->LY0 {calibration['ly144_to_ly0_register_ticks']} ticks; "
                        "instruction-boundary observations retained, not used as physical scaling"
                    ),
                }
                expected_fields["tick_calibration_equations"] = equations
                producer = [s for s in parsed if "producer_payload" in s]
                if producer:
                    expected_fields["producer_retry_evidence"] = {
                        "schema": "full-color-phase5-producer-retry-v1",
                        "samples": [{
                            "index": int(s["index"]),
                            "producer_class": int(s["producer_class"]),
                            "producer_destination": int(s["producer_destination"]),
                            "producer_width": int(s["producer_width"]),
                            "producer_height": int(s["producer_height"]),
                            "producer_extent": int(s["producer_extent"]),
                            "producer_payload_sha256": hashlib.sha256(
                                bytes.fromhex(str(s["producer_payload"]))
                            ).hexdigest(),
                            "retry_admit_hits": int(s["retry_admit_hits"]),
                            "retry_finish_hits": int(s["retry_finish_hits"]),
                            "retry_publish_hits": int(s["retry_publish_hits"]),
                            "retry_publish_result": int(s["retry_publish_result"]),
                            "completed_descriptor_address": int(s["producer_bound_descriptor_address"]),
                            "completed_descriptor_destination": int(s["producer_bound_descriptor_destination"]),
                            "completed_descriptor_state": int(s["producer_bound_descriptor_state"]),
                            "completed_descriptor_result": "COMPLETE",
                        } for s in producer],
                    }
            else:
                if (
                    not isinstance(capture_raw, dict)
                    or set(capture_raw) != {"schema", "samples", "start_count"}
                    or capture_raw["schema"] != "pyboy-phase5-cross-check-v1"
                    or capture_raw["start_count"] != MINIMUM_EXECUTIONS
                    or not isinstance(capture_raw["samples"], list)
                    or len(capture_raw["samples"]) != MINIMUM_EXECUTIONS
                ):
                    raise Phase5StressError(f"{descriptor.key}: malformed PyBoy capture")
                parsed = []
                for sample_index, sample_raw in enumerate(capture_raw["samples"]):
                    sample = _validate_sample_shape(
                        sample_raw,
                        path=f"{descriptor.key}.pyboy.samples[{sample_index}]",
                        expect_ticks=False,
                    )
                    if sample["index"] != sample_index:
                        raise Phase5StressError(f"{descriptor.key}: PyBoy sample order drifted")
                    scenario = bytes.fromhex(str(sample["scenario"]))
                    if scenario[1] != constants[_observed_scenario_constant(descriptor)]:
                        raise Phase5StressError(f"{descriptor.key}: PyBoy observed wrong scenario")
                    post = bytes.fromhex(str(sample["post_scenario"]))
                    if descriptor.case_id == "RC-P5-PARTY-RETURN-PALLET" and (
                        post[3] != constants[RESULT_PASSED_CONSTANT]
                        or post[4] != constants[STATE_COMPLETE_CONSTANT]
                        or post[7] != constants[LEDGER_ALL_CONSTANT]
                        or post[8] != constants[BARRIER_STABLE_CONSTANT]
                        or post[9] != 5
                    ):
                        raise Phase5StressError(f"{descriptor.key}: PyBoy postcondition drifted")
                    if (
                        sample["post_owner"] != constants["RENDERER_FULL_COLOR_OVERWORLD"]
                        or sample["post_phase"] != constants["OVERWORLD_ACTIVE"]
                    ):
                        raise Phase5StressError(f"{descriptor.key}: PyBoy owner/phase drifted")
                    parsed.append(sample)
                expected_fields = {
                    "semantic_sha256": hashlib.sha256(b"".join(
                        bytes.fromhex(str(sample["scenario"]))
                        + bytes.fromhex(str(sample["stress"]))
                        + bytes.fromhex(str(sample["post_scenario"]))
                        + bytes((int(sample["post_owner"]), int(sample["post_phase"])))
                        for sample in parsed
                    )).hexdigest(),
                    "trace_sha256": hashlib.sha256(b"".join(
                        bytes.fromhex(str(sample["trace"])) for sample in parsed
                    )).hexdigest(),
                }
            fixed = (
                {
                    "schema": "full-color-phase5-sameboy-row-v1",
                    "authority": "SAMEBOY_DEBUGGER_TICKS",
                    "samples": MINIMUM_EXECUTIONS,
                }
                if device == "sameboy" else {
                    "schema": "full-color-phase5-pyboy-row-v1",
                    "authority": "BEHAVIORAL_CROSS_CHECK_ONLY",
                    "samples": MINIMUM_EXECUTIONS,
                }
            )
            for field, expected_value in fixed.items():
                if capture.get(field) != expected_value:
                    raise Phase5StressError(f"{descriptor.key}: malformed {device} row")
            expected_capture_fields = {
                *fixed, *expected_fields, "frame_strip", "raw_capture_sha256",
            }
            if descriptor.row_id in FRESH_WINDOW_ROW_IDS:
                expected_capture_fields.add("fresh_windows")
                fresh = capture.get("fresh_windows")
                if (
                    not isinstance(fresh, dict)
                    or set(fresh) != {"mode", "count", "total_timeout_seconds", "windows"}
                    or fresh["mode"] != "INDEPENDENT_NATURAL_BOOT_TO_PALLET"
                    or fresh["count"] != MINIMUM_EXECUTIONS
                    or fresh["total_timeout_seconds"] != FRESH_WINDOW_TOTAL_TIMEOUT_SECONDS
                ):
                    raise Phase5StressError(f"{descriptor.key}: malformed fresh-window authority")
                _validate_fresh_window_metadata(
                    fresh["windows"], samples=MINIMUM_EXECUTIONS,
                    require_calibration=device == "sameboy",
                )
            if set(capture) != expected_capture_fields:
                raise Phase5StressError(f"{descriptor.key}: {device} row has extra fields")
            for field, expected_value in expected_fields.items():
                if capture.get(field) != expected_value:
                    raise Phase5StressError(
                        f"{descriptor.key}: {device} {field} differs from raw capture"
                    )
            strips = capture.get("frame_strip")
            if not isinstance(strips, list) or len(strips) != FRAME_STRIP_LENGTH:
                raise Phase5StressError(f"{descriptor.key}: {device} frame strip is incomplete")
            for strip_index, strip in enumerate(strips):
                expected_name = f"strip-{strip_index:02d}.png"
                if (
                    not isinstance(strip, dict)
                    or set(strip) != {"path", "sha256"}
                    or strip.get("path") != expected_name
                ):
                    raise Phase5StressError(f"{descriptor.key}: {device} frame strip ref drifted")
                expected_hash = _require_hash(
                    strip["sha256"], path=f"{descriptor.key}.{device}.frame_strip"
                )
                strip_path = f"{row_base}/{device}/{expected_name}"
                if hashlib.sha256(payloads[strip_path]).hexdigest() != expected_hash:
                    raise Phase5StressError(f"{descriptor.key}: {device} frame strip drifted")
                frame_index = MINIMUM_EXECUTIONS - FRAME_STRIP_LENGTH + strip_index
                frame_name = f"frame-{frame_index:04d}.ppm"
                frame_path = f"{row_base}/{device}/{frame_name}"
                if parsed[frame_index]["frame"] != frame_name:
                    raise Phase5StressError(f"{descriptor.key}: {device} frame reference drifted")
                frame_rgb = _decode_canonical_ppm(payloads[frame_path], path=frame_path)
                strip_rgb = _decode_png_rgb(payloads[strip_path], path=strip_path)
                if strip_rgb != frame_rgb:
                    raise Phase5StressError(f"{descriptor.key}: {device} strip content drifted")
            for sample_index, sample in enumerate(parsed):
                expected_frame = f"frame-{sample_index:04d}.ppm"
                if sample["frame"] != expected_frame:
                    raise Phase5StressError(f"{descriptor.key}: {device} frame order drifted")
                frame_path = f"{row_base}/{device}/{expected_frame}"
                _decode_canonical_ppm(payloads[frame_path], path=frame_path)
        diagnostics, proposal = _target_write_evidence_from_raw(
            descriptor,
            _decode_strict_json(
                payloads[f"{row_base}/sameboy/capture.json"],
                path=f"{row_base}/sameboy/capture.json",
            ),
            constants,
        )
        if row.get("write_diagnostics") != diagnostics:
            raise Phase5StressError(f"{descriptor.key}: write diagnostics differ from raw capture")
        if proposal is None:
            if "descriptor_write_count_proposal" in row:
                raise Phase5StressError(f"{descriptor.key}: unexpected descriptor write proposal")
        elif row.get("descriptor_write_count_proposal") != proposal:
            raise Phase5StressError(f"{descriptor.key}: descriptor writes differ from raw capture")
        if row["sameboy"]["semantic_sha256"] != row["pyboy"]["semantic_sha256"]:
            raise Phase5StressError(f"{descriptor.key}: semantic cross-check drifted")
        if row["sameboy"]["trace_sha256"] != row["pyboy"]["trace_sha256"]:
            raise Phase5StressError(f"{descriptor.key}: trace cross-check drifted")


def _decode_canonical_ppm(payload: bytes, *, path: str) -> bytes:
    header = b"P6\n160 144\n255\n"
    if not payload.startswith(header) or len(payload) != len(header) + 160 * 144 * 3:
        raise Phase5StressError(f"{path}: noncanonical 160x144 RGB PPM")
    return payload[len(header):]


def _decode_png_rgb(payload: bytes, *, path: str) -> bytes:
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            if image.format != "PNG" or image.mode != "RGB" or image.size != (160, 144):
                raise Phase5StressError(f"{path}: expected a 160x144 RGB PNG")
            return image.tobytes()
    except (OSError, ValueError) as exc:
        raise Phase5StressError(f"{path}: invalid PNG frame strip: {exc}") from exc


def _load_pinned_evidence(
    evidence_root: Path,
) -> tuple[list[dict[str, str]], dict[str, bytes]]:
    """Authenticate and load the complete frozen attempt through directory fds."""
    try:
        evidence_fd = os.open(
            evidence_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError as exc:
        raise Phase5StressError(f"Phase 5 evidence root is hostile: {exc}") from exc
    attempt_fd = -1
    try:
        attempt_fd = _open_directory_at(evidence_fd, PINNED_REVIEW_ATTEMPT)
        attempt_before = os.fstat(attempt_fd)
        if not stat.S_ISDIR(attempt_before.st_mode):
            raise Phase5StressError("Phase 5 pinned attempt is not a directory")
        paths = _list_regular_tree_from_fd(attempt_fd, PINNED_REVIEW_ATTEMPT)
        if len(paths) != PINNED_REVIEW_FILE_COUNT:
            raise Phase5StressError(
                f"Phase 5 {PINNED_REVIEW_ATTEMPT} regular file count differs "
                "from reviewed authority"
            )
        refs: list[dict[str, str]] = []
        payloads: dict[str, bytes] = {}
        identities: dict[str, tuple[int, int, int, int, int]] = {}
        for path in paths:
            relative = Path(*Path(path).parts[1:])
            payload, identity = _read_regular_at(attempt_fd, relative)
            digest = hashlib.sha256(payload).hexdigest()
            refs.append({"path": path, "sha256": digest})
            payloads[path] = payload
            identities[path] = identity

        paths_after = _list_regular_tree_from_fd(
            attempt_fd, PINNED_REVIEW_ATTEMPT
        )
        if paths_after != paths:
            raise Phase5StressError(
                f"Phase 5 {PINNED_REVIEW_ATTEMPT} exact tree changed while loading"
            )
        for path in paths:
            relative = Path(*Path(path).parts[1:])
            if _regular_identity_at(attempt_fd, relative) != identities[path]:
                raise Phase5StressError(
                    f"Phase 5 evidence file {path} changed after being read"
                )
        attempt_after = os.fstat(attempt_fd)
        if _file_identity(attempt_before) != _file_identity(attempt_after):
            raise Phase5StressError(
                f"Phase 5 {PINNED_REVIEW_ATTEMPT} directory changed while loading"
            )
        try:
            current_attempt = os.stat(
                PINNED_REVIEW_ATTEMPT,
                dir_fd=evidence_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise Phase5StressError(
                f"Phase 5 {PINNED_REVIEW_ATTEMPT} directory binding changed: {exc}"
            ) from exc
        if (
            not stat.S_ISDIR(current_attempt.st_mode)
            or _file_identity(current_attempt) != _file_identity(attempt_after)
        ):
            raise Phase5StressError(
                f"Phase 5 {PINNED_REVIEW_ATTEMPT} directory binding changed while loading"
            )
        if _artifact_tree_sha256(refs) != PINNED_REVIEW_TREE_SHA256:
            raise Phase5StressError(
                f"Phase 5 {PINNED_REVIEW_ATTEMPT} tree digest differs from reviewed authority"
            )
        # Keep this as the final filesystem observation before accepting the
        # immutable in-memory payloads. It closes changes racing the per-file
        # identity and root-binding checks above.
        if _file_identity(os.fstat(attempt_fd)) != _file_identity(attempt_after):
            raise Phase5StressError(
                f"Phase 5 {PINNED_REVIEW_ATTEMPT} directory changed before acceptance"
            )
        return refs, payloads
    finally:
        if attempt_fd >= 0:
            os.close(attempt_fd)
        os.close(evidence_fd)


def _derive_authenticated_evidence(
    root: Path,
    payloads: Mapping[str, bytes],
    captures: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Parse and derive every promoted field from authenticated raw artifacts."""
    runs: list[Mapping[str, object]] = []
    for capture in captures:
        path = str(capture["path"])
        try:
            payload = payloads[path]
        except KeyError as exc:
            raise Phase5StressError(f"Phase 5 capture {capture['id']} is omitted") from exc
        if hashlib.sha256(payload).hexdigest() != capture["sha256"]:
            raise Phase5StressError(f"Phase 5 capture {capture['id']} drifted")
        decoded = _decode_canonical_json(payload, path=path)
        if (
            not isinstance(decoded, dict)
            or set(decoded) != {"schema", "rows"}
            or decoded["schema"] != RUN_SCHEMA
        ):
            raise Phase5StressError(f"Phase 5 capture {capture['id']} has the wrong schema")
        runs.append(decoded)
    matrices: list[Mapping[str, object]] = []
    for index in (1, 2):
        path = f"{PINNED_REVIEW_ATTEMPT}/boundary-run-{index}/matrix.json"
        try:
            matrix_payload = payloads[path]
        except KeyError as exc:
            raise Phase5StressError("Phase 5 boundary matrix is omitted") from exc
        decoded = _decode_canonical_json(matrix_payload, path=path)
        if not isinstance(decoded, dict):
            raise Phase5StressError("Phase 5 boundary matrix is malformed")
        matrices.append(decoded)
    if _canonical(matrices[0]) != _canonical(matrices[1]):
        raise Phase5StressError("independent Phase 5 boundary matrices differ")
    constants = _numeric_symbols(root / f"{AUDIT_PRODUCT}.sym")
    for run_index, run in enumerate(runs, 1):
        _validate_authenticated_run_artifacts(
            run, run_index=run_index, attempt_name=PINNED_REVIEW_ATTEMPT,
            payloads=payloads, constants=constants,
        )
    return _derived_promoted_semantics(runs[0], runs[1], matrices[0])


def _verify_raw(
    root: Path,
    tool_root: Path,
    raw_object: object,
    *,
    evidence_root: Path | None = None,
) -> dict[str, object]:
    raw = validate_proposal(raw_object)
    if raw["identities"] != capture_identities(root.resolve(), tool_root.resolve()):
        raise Phase5StressError("Phase 5 ROM/sym/map/source/tool identities drifted")
    if raw["case_manifest"] != _case_manifest_binding(root.resolve()):
        raise Phase5StressError("Phase 5 case execution manifest binding drifted")
    if raw["production_admission"] != _production_admission_binding(root.resolve()):
        raise Phase5StressError("Phase 5 production admission authority drifted")
    matrix = raw["boundary_matrix"]
    assert isinstance(matrix, dict)
    if matrix["threshold_contract"] != _boundary_threshold_contract(root.resolve()):
        raise Phase5StressError("Phase 5 linked boundary threshold identity drifted")
    if evidence_root is None:
        return raw
    refs, payloads = _load_pinned_evidence(evidence_root)
    if raw["evidence_files"] != refs:
        raise Phase5StressError(
            "Phase 5 evidence file references are omitted, extra, mixed, or tampered"
        )
    captures = raw["captures"]
    assert isinstance(captures, list)
    derived = _derive_authenticated_evidence(root.resolve(), payloads, captures)
    for name, expected in derived.items():
        if raw[name] != expected:
            raise Phase5StressError(
                f"Phase 5 proposal field {name} differs from authenticated captures"
            )
    return raw


def verify(
    root: Path,
    tool_root: Path,
    proposal_path: Path,
    *,
    evidence_root: Path | None = None,
) -> dict[str, object]:
    try:
        descriptor = os.open(proposal_path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise Phase5StressError(f"Phase 5 proposal is hostile: {exc}") from exc
    try:
        proposal_stat = os.fstat(descriptor)
        if not stat.S_ISREG(proposal_stat.st_mode) or proposal_stat.st_nlink != 1:
            raise Phase5StressError("Phase 5 proposal must be a single regular file")
        payload = b""
        while chunk := os.read(descriptor, 1024 * 1024):
            payload += chunk
    finally:
        os.close(descriptor)
    raw = _decode_canonical_json(payload, path=str(proposal_path))
    return _verify_raw(root, tool_root, raw, evidence_root=evidence_root)


def compare_reviewed_authority(
    root: Path,
    tool_root: Path,
    fresh_proposal: Path,
    reviewed_path: Path,
) -> None:
    fresh = verify(root, tool_root, fresh_proposal)
    reviewed = validate_proposal(_read_json(reviewed_path))
    if reviewed.get("schema") != REVIEWED_SCHEMA or reviewed.get("reviewed") is not True:
        raise Phase5StressError("canonical Phase 5 authority is not reviewed evidence")
    if reviewed["identities"] != fresh["identities"]:
        raise Phase5StressError("canonical Phase 5 ROM/source/tool identities are stale")

    def semantic_view(raw: Mapping[str, object]) -> dict[str, object]:
        result = dict(raw)
        result.pop("schema", None)
        result.pop("reviewed", None)
        # Capture paths and container hashes identify archived external files;
        # every stable semantic/trace/frame hash inside the rows remains gated.
        result.pop("captures", None)
        result.pop("evidence_files", None)
        return result

    if _canonical(semantic_view(fresh)) != _canonical(semantic_view(reviewed)):
        raise Phase5StressError(
            "fresh Phase 5 semantic/timing evidence differs from reviewed authority"
        )


def regenerate_proposal_from_pinned_evidence(
    root: Path,
    tool_root: Path,
    evidence_root: Path,
    proposal_output: Path,
) -> dict[str, object]:
    """Regenerate an unreviewed proposal from the frozen pinned attempt only."""
    root = Path(os.path.abspath(root))
    tool_root = Path(os.path.abspath(tool_root))
    evidence_root = Path(os.path.abspath(evidence_root))
    requested_output = Path(proposal_output)
    expected_requested_output = (
        root / PROPOSAL_OUTPUT_PATH
        if requested_output.is_absolute()
        else PROPOSAL_OUTPUT_PATH
    )
    if requested_output != expected_requested_output:
        raise Phase5StressError(
            "regenerated proposal output must be the exact dedicated proposal path"
        )
    proposal_output = root / PROPOSAL_OUTPUT_PATH
    output_relative = PROPOSAL_OUTPUT_PATH

    identities_before = capture_identities(root, tool_root)
    refs, payloads = _load_pinned_evidence(evidence_root)
    captures = [
        {
            "id": f"run-{index}",
            "path": f"{PINNED_REVIEW_ATTEMPT}/run-{index}/run.json",
            "sha256": hashlib.sha256(
                payloads[f"{PINNED_REVIEW_ATTEMPT}/run-{index}/run.json"]
            ).hexdigest(),
        }
        for index in (1, 2)
    ]
    derived = _derive_authenticated_evidence(root, payloads, captures)
    proposal: dict[str, object] = {
        "schema": SCHEMA,
        "reviewed": False,
        "authority": {
            "timing": "PINNED_SAMEBOY_DEBUGGER_TICKS",
            "behavioral_cross_check": "PYBOY_2_7_ONLY",
            "product": f"{AUDIT_PRODUCT}.gbc",
            "production_activation": False,
        },
        "identities": identities_before,
        "case_manifest": _case_manifest_binding(root),
        "production_admission": _production_admission_binding(root),
        "captures": captures,
        "evidence_files": refs,
        **derived,
    }
    validate_proposal(proposal)
    identities_after_derivation = capture_identities(root, tool_root)
    if identities_before != identities_after_derivation:
        raise Phase5StressError(
            "ROM/sym/map/source/tool identities changed during proposal regeneration"
        )
    refs_before_publication, _ = _load_pinned_evidence(evidence_root)
    if refs_before_publication != refs:
        raise Phase5StressError(
            f"Phase 5 {PINNED_REVIEW_ATTEMPT} changed during proposal regeneration"
        )

    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise Phase5StressError(f"repository root is hostile: {exc}") from exc
    parent_fd = os.dup(root_fd)
    try:
        # Refuse absent or hostile parent components so the sole mutation is
        # the requested proposal file itself.
        for component in output_relative.parts[:-1]:
            following = _open_directory_at(parent_fd, component)
            os.close(parent_fd)
            parent_fd = following
        _atomic_publish_reviewed_at(
            root, root_fd, output_relative, _canonical(proposal).encode("utf-8")
        )
    finally:
        os.close(parent_fd)
        os.close(root_fd)

    refs_after_publication, _ = _load_pinned_evidence(evidence_root)
    if refs_after_publication != refs:
        raise Phase5StressError(
            "UNCERTAIN PUBLICATION: pinned attempt changed during output publication"
        )
    return proposal


def _validate_parent_chain(
    root: Path,
    root_fd: int,
    root_identity: tuple[int, int],
    bindings: Sequence[tuple[int, str, tuple[int, int]]],
) -> None:
    try:
        canonical_root = os.stat(root, follow_symlinks=False)
    except OSError as exc:
        raise Phase5StressError(f"canonical repository root detached: {exc}") from exc
    held_root = os.fstat(root_fd)
    if (
        not stat.S_ISDIR(canonical_root.st_mode)
        or (canonical_root.st_dev, canonical_root.st_ino) != root_identity
        or (held_root.st_dev, held_root.st_ino) != root_identity
    ):
        raise Phase5StressError("canonical repository root detached during publication")
    for parent_fd, component, expected in bindings:
        try:
            current = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise Phase5StressError("canonical publication parent detached") from exc
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != expected:
            raise Phase5StressError("canonical publication parent detached")


def _atomic_publish_reviewed_at(
    root: Path, root_fd: int, relative: Path, payload: bytes
) -> None:
    parent_fd = os.dup(root_fd)
    root_stat = os.fstat(root_fd)
    root_identity = (root_stat.st_dev, root_stat.st_ino)
    bindings: list[tuple[int, str, tuple[int, int]]] = []
    held_directories: list[int] = []
    temporary: str | None = None
    backup: str | None = None
    descriptor = -1
    rollback_parent_fd = -1
    publication_started = False
    committed = False
    published_identity: tuple[int, int, int, int, int] | None = None
    before: os.stat_result | None = None
    old_payload: bytes | None = None
    expected_rollback: tuple[int, int, int, int] | None = None
    operation_error: BaseException | None = None
    cleanup_errors: list[BaseException] = []

    def close_best_effort(fd: int) -> None:
        if fd < 0:
            return
        try:
            os.close(fd)
        except BaseException as exc:
            cleanup_errors.append(exc)

    def unlink_best_effort(entry: str | None, directory_fd: int) -> None:
        if entry is None:
            return
        try:
            os.unlink(entry, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        except BaseException as exc:
            cleanup_errors.append(exc)

    def rollback_publication(directory_fd: int) -> None:
        """Restore the pre-publication bytes through the pinned parent."""
        nonlocal backup
        try:
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None:
            if (
                published_identity is not None
                and _file_identity(current) != published_identity
            ):
                raise Phase5StressError(
                    "publication target changed before rollback"
                )
            os.unlink(name, dir_fd=directory_fd)
        if before is not None:
            restored_from_backup = False
            if backup is not None:
                try:
                    os.replace(
                        backup, name,
                        src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                    )
                    backup = None
                    restored_from_backup = True
                except FileNotFoundError:
                    pass
            if not restored_from_backup:
                if old_payload is None:
                    raise Phase5StressError("rollback bytes are unavailable")
                rollback_temp = f".{name}.{secrets.token_hex(12)}.rollback"
                rollback_fd = -1
                try:
                    rollback_fd = os.open(
                        rollback_temp,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        before.st_mode & 0o7777, dir_fd=directory_fd,
                    )
                    os.fchmod(rollback_fd, stat.S_IMODE(before.st_mode))
                    offset = 0
                    while offset < len(old_payload):
                        written = os.write(rollback_fd, old_payload[offset:])
                        if written <= 0:
                            raise OSError("rollback write made no progress")
                        offset += written
                    os.fsync(rollback_fd)
                    closing = rollback_fd
                    rollback_fd = -1
                    os.close(closing)
                    os.replace(
                        rollback_temp, name,
                        src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                    )
                    rollback_temp = ""
                    os.utime(
                        name, ns=(before.st_atime_ns, before.st_mtime_ns),
                        dir_fd=directory_fd, follow_symlinks=False,
                    )
                finally:
                    if rollback_fd >= 0:
                        os.close(rollback_fd)
                    if rollback_temp:
                        try:
                            os.unlink(rollback_temp, dir_fd=directory_fd)
                        except FileNotFoundError:
                            pass
            restored = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if restored_from_backup and (
                restored.st_dev, restored.st_ino,
                restored.st_size, restored.st_mtime_ns,
            ) != expected_rollback:
                raise Phase5StressError("restored authority identity drifted")
            restored_fd = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd
            )
            try:
                if os.pread(restored_fd, restored.st_size + 1, 0) != old_payload:
                    raise Phase5StressError("restored authority bytes drifted")
            finally:
                os.close(restored_fd)
        else:
            try:
                os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise Phase5StressError("new authority remained after rollback")
        os.fsync(directory_fd)

    try:
        for component in relative.parts[:-1]:
            try:
                following = _open_directory_at(parent_fd, component)
            except Phase5StressError:
                try:
                    os.mkdir(component, 0o755, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                following = _open_directory_at(parent_fd, component)
            child_stat = os.fstat(following)
            bindings.append(
                (parent_fd, component, (child_stat.st_dev, child_stat.st_ino))
            )
            held_directories.append(parent_fd)
            parent_fd = following
        name = relative.parts[-1]
        try:
            before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            before = None
        if before is not None and (
            not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
        ):
            raise Phase5StressError("reviewed authority target is not a single regular file")
        expected = None if before is None else _file_identity(before)
        expected_rollback = None if before is None else (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
        )
        if before is not None:
            old_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
            try:
                if _file_identity(os.fstat(old_fd)) != expected:
                    raise Phase5StressError("reviewed authority changed before backup")
                old_payload = os.pread(old_fd, before.st_size + 1, 0)
                if len(old_payload) != before.st_size:
                    raise Phase5StressError("reviewed authority changed before backup")
            finally:
                os.close(old_fd)
        temporary = f".{name}.{secrets.token_hex(12)}.tmp"
        backup = f".{name}.{secrets.token_hex(12)}.bak"
        # Everything from creation onward is inside this transaction.  Any
        # pre-commit failure therefore reaches the common unlink path below.
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=parent_fd,
        )
        try:
            if before is not None:
                os.fchmod(descriptor, stat.S_IMODE(before.st_mode))
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("temporary publication write made no progress")
                offset += written
            os.fsync(descriptor)
        finally:
            closing = descriptor
            descriptor = -1
            os.close(closing)
        _validate_parent_chain(root, root_fd, root_identity, bindings)
        try:
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        identity = None if current is None else _file_identity(current)
        if identity != expected:
            raise Phase5StressError("reviewed authority changed before atomic publication")
        rollback_parent_fd = os.dup(parent_fd)
        if before is not None:
            os.replace(name, backup, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            publication_started = True
        os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary = None
        publication_started = True
        committed = True
        published_identity = _file_identity(
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        )
        _validate_parent_chain(root, root_fd, root_identity, bindings)
        os.fsync(parent_fd)
        _validate_parent_chain(root, root_fd, root_identity, bindings)
        if before is not None:
            os.unlink(backup, dir_fd=parent_fd)
            backup = None
            # Make removal of the successful transaction's backup name as
            # durable as publication of the replacement itself.
            os.fsync(parent_fd)
        # This check intentionally follows both directory durability and backup
        # cleanup.  A canonical root/parent swap in the last publication window
        # is rolled back through rollback_parent_fd, never through the path.
        _validate_parent_chain(root, root_fd, root_identity, bindings)
    except BaseException as exc:
        operation_error = exc

    unlink_best_effort(temporary, parent_fd)
    close_best_effort(descriptor)
    descriptor = -1
    close_best_effort(parent_fd)
    parent_fd = -1
    for directory_fd in reversed(held_directories):
        close_best_effort(directory_fd)
    held_directories.clear()

    must_rollback = publication_started and (
        operation_error is not None or bool(cleanup_errors)
    )
    if must_rollback:
        try:
            rollback_publication(rollback_parent_fd)
            committed = False
        except BaseException as rollback_error:
            close_best_effort(rollback_parent_fd)
            raise Phase5StressError(
                "UNCERTAIN PUBLICATION: rollback could not be proven"
            ) from rollback_error

    close_best_effort(rollback_parent_fd)
    rollback_parent_fd = -1
    if committed and cleanup_errors:
        # A failure closing the final pinned descriptor is intrinsically
        # ambiguous: it is too late to prove another rollback safely.
        raise Phase5StressError(
            "UNCERTAIN PUBLICATION: committed cleanup could not be proven"
        ) from cleanup_errors[0]
    if cleanup_errors:
        phase = "after rollback" if publication_started else "before commit"
        raise Phase5StressError(
            f"publication cleanup failed {phase} ({len(cleanup_errors)} errors)"
        ) from cleanup_errors[0]
    if operation_error is not None:
        raise operation_error


def apply_reviewed_proposal(
    root: Path,
    tool_root: Path,
    proposal_path: Path,
    output: Path,
    *,
    authority_reviewed: bool,
    evidence_root: Path | None = None,
) -> dict[str, object]:
    root = Path(os.path.abspath(root))
    proposal_path = Path(os.path.abspath(proposal_path))
    output = Path(os.path.abspath(output if output.is_absolute() else root / output))
    if not authority_reviewed:
        raise Phase5StressError("reviewed proposal application requires --authority-reviewed")
    if "CI" in os.environ:
        raise Phase5StressError("reviewed Phase 5 promotion is forbidden in CI")
    if evidence_root is None:
        raise Phase5StressError("reviewed promotion requires the fresh capture artifact root")
    try:
        proposal_relative = proposal_path.relative_to(root)
    except ValueError as exc:
        raise Phase5StressError("reviewed proposal must be contained by the repository") from exc
    if output != root / REVIEWED_PATH:
        raise Phase5StressError("reviewed promotion may only target canonical evidence")
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise Phase5StressError(f"repository root is hostile: {exc}") from exc
    proposal_fd = -1
    proposal_directories: list[int] = []
    directory_bindings: list[tuple[int, str, tuple[int, int]]] = []
    publication_committed = False
    try:
        proposal_directories.append(os.dup(root_fd))
        for component in proposal_relative.parts[:-1]:
            parent_fd = proposal_directories[-1]
            child_fd = _open_directory_at(parent_fd, component)
            child_stat = os.fstat(child_fd)
            directory_bindings.append(
                (parent_fd, component, (child_stat.st_dev, child_stat.st_ino))
            )
            proposal_directories.append(child_fd)
        proposal_fd = os.open(
            proposal_relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=proposal_directories[-1],
        )
        before = os.fstat(proposal_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise Phase5StressError("Phase 5 proposal must be a single regular file")
        identity = _file_identity(before)
        proposal_bytes = os.pread(proposal_fd, before.st_size + 1, 0)
        if len(proposal_bytes) != before.st_size:
            raise Phase5StressError("Phase 5 proposal changed while being read")
        parsed_proposal = _decode_canonical_json(
            proposal_bytes, path=proposal_relative.as_posix()
        )
        raw = dict(_verify_raw(
            root, tool_root, parsed_proposal, evidence_root=evidence_root
        ))
        after = os.fstat(proposal_fd)
        if identity != _file_identity(after):
            raise Phase5StressError("Phase 5 proposal changed before publication")
        if os.pread(proposal_fd, before.st_size + 1, 0) != proposal_bytes:
            raise Phase5StressError("Phase 5 proposal changed before publication")
        for parent_fd, component, expected_directory in directory_bindings:
            current = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(current.st_mode)
                or (current.st_dev, current.st_ino) != expected_directory
            ):
                raise Phase5StressError("Phase 5 proposal parent changed before publication")
        current_proposal = os.stat(
            proposal_relative.parts[-1],
            dir_fd=proposal_directories[-1], follow_symlinks=False,
        )
        if identity != _file_identity(current_proposal):
            raise Phase5StressError("Phase 5 proposal changed before publication")
        raw["schema"] = REVIEWED_SCHEMA
        raw["reviewed"] = True
        _atomic_publish_reviewed_at(
            root, root_fd, REVIEWED_PATH, _canonical(raw).encode("utf-8")
        )
        publication_committed = True
        return raw
    finally:
        cleanup_errors: list[BaseException] = []
        if proposal_fd >= 0:
            try:
                os.close(proposal_fd)
            except BaseException as exc:
                cleanup_errors.append(exc)
        for directory_fd in reversed(proposal_directories):
            try:
                os.close(directory_fd)
            except BaseException as exc:
                cleanup_errors.append(exc)
        try:
            os.close(root_fd)
        except BaseException as exc:
            cleanup_errors.append(exc)
        if cleanup_errors and not publication_committed:
            # A primary verification/publication error, if one is already
            # unwinding, remains the useful diagnosis.  Raising here would
            # replace it with a generic close failure.  Once publication has
            # committed, these unrelated proposal/root closes likewise cannot
            # rewrite the transaction's certified outcome.
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Produce/verify Phase 5 stress timing")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--tool-root", type=Path, required=True)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--proposal-output", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", type=Path)
    mode.add_argument("--apply-proposal", type=Path)
    mode.add_argument("--regenerate-proposal", action="store_true")
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--compare-reviewed", type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--authority-reviewed", action="store_true")
    parser.add_argument("--samples", type=int, default=MINIMUM_EXECUTIONS)
    args = parser.parse_args(argv)
    try:
        if args.regenerate_proposal:
            if (
                args.evidence_root is None
                or args.proposal_output is None
                or args.results is not None
                or args.target is not None
                or args.authority_reviewed
                or args.compare_reviewed is not None
                or args.samples != MINIMUM_EXECUTIONS
            ):
                raise Phase5StressError(
                    "proposal regeneration requires only --evidence-root and "
                    "--proposal-output"
                )
            regenerate_proposal_from_pinned_evidence(
                args.root, args.tool_root, args.evidence_root,
                args.proposal_output,
            )
        elif args.apply_proposal is not None:
            if (
                args.target is None
                or args.results is not None
                or args.proposal_output is not None
                or args.compare_reviewed is not None
            ):
                raise Phase5StressError(
                    "proposal application requires only --apply-proposal, --target, "
                    "--evidence-root, and --authority-reviewed"
                )
            apply_reviewed_proposal(
                args.root, args.tool_root, args.apply_proposal, args.target,
                authority_reviewed=args.authority_reviewed,
                evidence_root=args.evidence_root,
            )
        elif args.verify is not None:
            if (
                args.target is not None
                or args.authority_reviewed
                or args.results is not None
                or args.proposal_output is not None
            ):
                raise Phase5StressError(
                    "--target/--authority-reviewed are proposal-application options"
                )
            verify(
                args.root, args.tool_root, args.verify,
                evidence_root=args.evidence_root,
            )
            if args.compare_reviewed is not None:
                compare_reviewed_authority(
                    args.root, args.tool_root, args.verify, args.compare_reviewed
                )
        else:
            if (
                args.target is not None
                or args.authority_reviewed
                or args.compare_reviewed is not None
                or args.evidence_root is not None
            ):
                raise Phase5StressError(
                    "--target/--authority-reviewed are proposal-application options"
                )
            if args.results is None or args.proposal_output is None:
                raise Phase5StressError("capture requires --results and --proposal-output")
            produce(
                args.root, args.tool_root, args.results, args.proposal_output,
                samples=args.samples,
            )
    except (Phase5StressError, Phase2AuditError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

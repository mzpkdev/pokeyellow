"""Measure and select the bounded Phase 2 hostile-slice representation.

The decision is derived from both release and debug linker products.  The
descriptor layout and the bounded hostile scenario are source authorities;
addresses and capacities are measurements.  Nothing in this module activates
the Phase 2 runtime.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from dataclasses import replace
from functools import lru_cache
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
from typing import Mapping, Sequence

from .baseline_discovery import (
    COPIED_REGIONS,
    DMA_CONTROL_LABELS,
    FARCALL_LABELS,
    SHADOW_OAM_RANGES,
    SOURCE_ROOTS,
    load_predef_targets,
    discover_baseline_rom,
    discover_baseline_sources,
)
from .baseline_inventory import (
    _PLANNED_ONLY_ROW_CONTRACTS,
    _phase2_transition_state,
    _reviewed_rom_view,
    _reviewed_source_view,
    _validate_planned_rows,
)
from .discovery_review import (
    rom_finding_subject,
    source_error_subject,
    source_finding_subject,
)
from .discovery_assignment import (
    BASELINE_PRODUCT,
    DEBUG_PRODUCT,
    DiscoveryAssignmentAuthority,
    NORMAL_PRODUCT,
    PHASE2_AUDIT_PRODUCT,
    PRODUCTION_PRODUCTS,
    StaleDiscoveryAssignmentError,
    VC_PRODUCT,
)
from .inventory import MutationInventory, SceneInventory, WriterInventory
from .phase1_measurements import (
    FORBIDDEN_ROM_BANKS,
    MINIMUM_STACK_MARGIN,
    PHASE1_STATE_BYTES,
)
from .rom_discovery import (
    discover_rom_batched,
    load_map,
    load_sym,
    normalize_rom_offset,
)
from .source_discovery import (
    PHASE2_HOSTILE_LIFECYCLE_ROOTS,
    PHASE2_HOSTILE_MUTATION_ROOTS,
    PHASE2_HOSTILE_SCENE_ROOTS,
    SourceDiscoveryReport,
    discover_sources,
)


SCHEMA = "full-color-phase2-hostile-slice-representation-v1"
MEASUREMENT_IDENTITY = "full-color-phase2-link-measurement-v1"
AUDIT_GUARD = "PHASE2_AUDIT"
AUDIT_MARKER = b"P2AUDIT1"
PRODUCT_ARTIFACTS = {
    NORMAL_PRODUCT: "pokeyellow",
    DEBUG_PRODUCT: "pokeyellow_debug",
    VC_PRODUCT: "pokeyellow_vc",
    PHASE2_AUDIT_PRODUCT: "pokeyellow_phase2_audit",
}
DEFINITION_PATH = (
    "specs/full-colors/definitions/phase2-hostile-slice-representation.json"
)
SOURCE_TRANSITION_PATH = (
    "specs/full-colors/definitions/phase1-audit-source-transition.json"
)
PLANNED_SUBJECTS_PATH = "specs/full-colors/definitions/phase2-planned-subjects.json"
REVIEWED_TRANSITION_PATH = (
    "specs/full-colors/definitions/phase2-reviewed-transition.json"
)
REVIEWED_TRANSITION_PROPOSAL_SCHEMA = (
    "full-color-phase2-reviewed-transition-rebind-proposal-v1"
)
REVIEWED_TRANSITION_SHA256 = (
    "e7c92959999b01625bf70aef4db01c7fdf61a89690a74b02b47cf3ace9e21e4a"
)
VERIFIER_PATH = "tools/rom_tests/full_color/phase2_measurements.py"
_TRANSITION_DIGEST_CARRIER = re.compile(
    rb'REVIEWED_TRANSITION_SHA256 = \(\n    "[0-9a-f]{64}"\n\)'
)

PLANNED_ONLY_DISPOSITION_ROWS = frozenset()

PHASE2_SCENE_EDGE_CLASSIFICATIONS = {
    ("DisplayPartyMenu", "PartyMenuInit"): ("DIRECTED_EDGE", "MAP_TO_YELLOW"),
    (
        "StartMenu_Pokemon.exitMenu",
        "RestoreScreenTilesAndReloadTilePatterns",
    ): ("DIRECTED_EDGE", "YELLOW_TO_YELLOW"),
}

_CLOSED_SCENE_DIRECTIONS = {
    ("DisplayPartyMenu", "PartyMenuInit"): "YELLOW_TO_YELLOW",
    (
        "StartMenu_Pokemon.exitMenu",
        "RestoreScreenTilesAndReloadTilePatterns",
    ): "YELLOW_TO_YELLOW",
}

_CLOSED_PALETTE_ROW_CONTRACT = {
    "commit_unit": "PALETTE",
    "resources": (
        {
            "aliases": [],
            "end": 0xFF69,
            "resource": "CGB_PALETTE",
            "start": 0xFF68,
            "vram_bank": None,
        },
    ),
    "roots": (
        "PassiveFullColorCommitPalettes",
        "PassiveFullColorHomogenizeBGPalettes",
    ),
}

_PASSIVE_REQUIRED_EDGES = (
    ("LoadMapData", "RunPaletteCommand"),
    ("LoadMapData", "PassiveFullColorApplyMap"),
    ("CheckMapConnections.loadNewMap", "RunPaletteCommand"),
    ("CheckMapConnections.loadNewMap", "PassiveFullColorApplyMap"),
    ("PassiveFullColorApplyMap.apply", "PassiveFullColorCommitPalettes"),
    (
        "PassiveFullColorApplyMap.apply",
        "PassiveFullColorCommitVisibleAttributes",
    ),
    ("PassiveFullColorVBlank.slice", "PassiveFullColorCommitRedrawRow"),
    ("PassiveFullColorVBlank.slice", "PassiveFullColorCommitRedrawColumn"),
    ("PassiveFullColorVBlank.inactive", "PassiveFullColorHomogenizeBGPalettes"),
    ("PassiveFullColorVBlank.bounded_clear", "PassiveFullColorClearBGMapChunk"),
    ("DisplayPartyMenu", "PartyMenuInit"),
    (
        "StartMenu_Pokemon.exitMenu",
        "RestoreScreenTilesAndReloadTilePatterns",
    ),
    ("StartMenu_Pokemon.exitMenu", "LoadGBPal"),
    ("DisplayTextID.skipSpriteHandling", "PrintText_NoCreatingTextBox"),
    ("DisplayStartMenu", "FullColorDisplayStartMenu"),
    ("FullColorStartMenuReveal", "PrintSafariZoneSteps"),
    ("FullColorHandleStartMenuInput", "HandleMenuInput"),
    ("FullColorPlaceUnfilledStartMenuCursor", "PlaceUnfilledArrowMenuCursor"),
    ("PrepareOAMData.spriteusesOBP0", "MapFullColorOAMAttributeFar"),
)

_PASSIVE_REQUIRED_WRITERS = {
    "PassiveFullColorCommitPalettes": frozenset({"CGB_PALETTE"}),
    "PassiveFullColorCommitVisibleAttributes": frozenset(
        {"VRAM_BANK", "COMPUTED_POINTER"}
    ),
    "PassiveFullColorCommitRedrawColumn": frozenset({"VRAM_BANK", "COMPUTED_POINTER"}),
    "PassiveFullColorCommitRedrawRow": frozenset({"VRAM_BANK", "COMPUTED_POINTER"}),
    "PassiveFullColorHomogenizeBGPalettes": frozenset({"CGB_PALETTE"}),
    "PassiveFullColorClearBGMapChunk": frozenset({"VRAM_BANK", "COMPUTED_POINTER"}),
}

_FORBIDDEN_PRODUCTION_DESTINATIONS = frozenset(
    {
        "BeginFullColorMapEntry",
        "EnqueueFullColorStartMenuOverlay",
        "EnqueueFullColorWindowTileMapOverlayFar",
        "EnsureFullColorPartyHandoff",
        "EnsureFullColorPartyMenuYellow",
        "EnterFullColorOverlay",
        "FullColorAuditBeginBoundedMapEntry",
        "FullColorAuditLoadMapData",
        "FullColorVBlankOwnerConsumed",
        "PrepareFullColorOAMDataForOwnedVBlank",
        "ReturnFullColorFromParty",
        "RunFullColorOwnershipVBlank",
    }
)

_PRODUCTION_INTEGRATION_SYMBOLS = frozenset(
    {
        "CheckMapConnections.loadNewMap",
        "FullColorDisplayStartMenu",
        "FullColorHandleStartMenuInput",
        "FullColorPlaceUnfilledStartMenuCursor",
        "FullColorStartMenuReveal",
    }
)

# Each root maps its control/entry evidence first and its concrete writer
# evidence second.  This keeps duplicate inventory rows distinct without ever
# listing one canonical subject under more than one planned row.
PHASE2_ROOT_ROWS = {
    "AutoBgMapTransfer": ("MU-P2-START-MENU-OVERLAY", "WR-P2-YELLOW-OVERLAY-TRANSFER"),
    "DMARoutine": ("WR-P2-YELLOW-OAM-DMA", "WR-P2-YELLOW-OAM-DMA"),
    "DisplayPartyMenu": ("SC-P2-PARTY-ENTRY", "SC-P2-PARTY-ENTRY"),
    "DisplayStartMenu": ("MU-P2-START-MENU-OVERLAY", "MU-P2-START-MENU-OVERLAY"),
    "DisplayTextID": ("MU-P2-DIALOGUE-OVERLAY", "MU-P2-DIALOGUE-OVERLAY"),
    "EnterMap": ("MU-P2-MAP-RECONSTRUCTION", "MU-P2-MAP-RECONSTRUCTION"),
    "LoadGBPal": ("MU-P2-PALETTE-PAYLOADS", "MU-P2-PALETTE-PAYLOADS"),
    "LoadMapData": ("MU-P2-MAP-RECONSTRUCTION", "MU-P2-MAP-RECONSTRUCTION"),
    "LoadNorthSouthConnectionsTileMap": (
        "MU-P2-MAP-CONNECTION-NORTH",
        "MU-P2-MAP-CONNECTION-NORTH",
    ),
    "PassiveFullColorApplyMap": (
        "MU-P2-MAP-RECONSTRUCTION",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    ),
    "PassiveFullColorClearBGMapAttributes": (
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    ),
    "PassiveFullColorClearBGMapChunk": (
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    ),
    "PassiveFullColorCommitPalettes": (
        "MU-P2-PALETTE-PAYLOADS",
        "WR-P2-YELLOW-BG-PALETTE",
    ),
    "PassiveFullColorCommitRedrawColumn": (
        "MU-P2-MOVEMENT-HORIZONTAL",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    ),
    "PassiveFullColorCommitRedrawRow": (
        "MU-P2-MOVEMENT-VERTICAL",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    ),
    "PassiveFullColorCommitVisibleAttributes": (
        "MU-P2-MAP-RECONSTRUCTION",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    ),
    "PassiveFullColorHandleConnection": (
        "MU-P2-MAP-CONNECTION-NORTH",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    ),
    "PassiveFullColorHomogenizeBGPalettes": (
        "MU-P2-PALETTE-PAYLOADS",
        "WR-P2-YELLOW-BG-PALETTE",
    ),
    "PassiveFullColorVBlank": (
        "WR-P2-YELLOW-MAP-STREAM",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    ),
    "PalletTown_h": ("SC-P2-PALLET-ROUTE1-NORTH", "SC-P2-PALLET-ROUTE1-NORTH"),
    "PartyMenuInit": ("SC-P2-PARTY-ENTRY", "SC-P2-PARTY-ENTRY"),
    "PrepareOAMData": ("MU-P2-OAM-FOLLOWER-NPC", "WR-P2-YELLOW-OAM-BUILD"),
    "RedrawRowOrColumn": ("WR-P2-YELLOW-MAP-STREAM", "WR-P2-YELLOW-MAP-STREAM"),
    "RestoreScreenTilesAndReloadTilePatterns": (
        "SC-P2-PARTY-RETURN",
        "SC-P2-PARTY-RETURN",
    ),
    "Route1_h": ("SC-P2-PALLET-ROUTE1-NORTH", "SC-P2-PALLET-ROUTE1-NORTH"),
    "ScheduleEastColumnRedraw": (
        "MU-P2-MOVEMENT-HORIZONTAL",
        "MU-P2-MOVEMENT-HORIZONTAL",
    ),
    "ScheduleNorthRowRedraw": ("MU-P2-MOVEMENT-VERTICAL", "MU-P2-MOVEMENT-VERTICAL"),
    "ScheduleSouthRowRedraw": ("MU-P2-MOVEMENT-VERTICAL", "MU-P2-MOVEMENT-VERTICAL"),
    "ScheduleWestColumnRedraw": (
        "MU-P2-MOVEMENT-HORIZONTAL",
        "MU-P2-MOVEMENT-HORIZONTAL",
    ),
    "StartMenu_Pokemon.exitMenu": ("SC-P2-PARTY-RETURN", "SC-P2-PARTY-RETURN"),
    "TransferBGPPals": ("MU-P2-PALETTE-PAYLOADS", "WR-P2-YELLOW-BG-PALETTE"),
    "UpdateMovingBgTiles": ("MU-P2-ANIMATED-TERRAIN", "WR-P2-YELLOW-ANIMATION-TILES"),
}

MINIMUM_ROM_BYTES = 0x1000
PHASE2_PIPELINE_SECTION = "Full Color Phase 2 Pipelines"
WRAMX_START, WRAMX_END = 0xD000, 0xDFFF
SRAM_START, SRAM_END = 0xA000, 0xBFFF
ROMX_START, ROMX_END = 0x4000, 0x7FFF

_BANK = re.compile(r"^([A-Z0-9]+) bank #(\d+):$")
_SECTION = re.compile(
    r"^\s*SECTION: \$([0-9a-fA-F]{4})(?:-\$([0-9a-fA-F]{4}))? "
    r'\(\$([0-9a-fA-F]{4}) bytes?\) \["([^"]+)"\]$'
)
_SYMBOL = re.compile(r"^([0-9a-fA-F]+):([0-9a-fA-F]{4}) (\S+)$")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

PHASE2_PLANNED_ROW_IDS = frozenset(
    {
        "MU-P2-ANIMATED-TERRAIN",
        "MU-P2-DIALOGUE-OVERLAY",
        "MU-P2-MAP-CONNECTION-NORTH",
        "MU-P2-MAP-RECONSTRUCTION",
        "MU-P2-MOVEMENT-HORIZONTAL",
        "MU-P2-MOVEMENT-VERTICAL",
        "MU-P2-OAM-FOLLOWER-NPC",
        "MU-P2-PALETTE-PAYLOADS",
        "MU-P2-START-MENU-OVERLAY",
        "SC-P2-PALLET-ROUTE1-NORTH",
        "SC-P2-PARTY-ENTRY",
        "SC-P2-PARTY-RETURN",
        "WR-P2-YELLOW-ANIMATION-TILES",
        "WR-P2-YELLOW-BG-PALETTE",
        "WR-P2-YELLOW-MAP-STREAM",
        "WR-P2-YELLOW-OAM-BUILD",
        "WR-P2-YELLOW-OAM-DMA",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    }
)

RESOURCE_VOCABULARY = frozenset(
    {"ATTRIBUTES", "BG_MAP", "BG_TILES", "HARDWARE_OAM", "PALETTES", "SHADOW_OAM"}
)
REQUEST_CLASS_REQUIRED_RESOURCES = {
    "ANIMATION_REPLACEMENT": frozenset({"BG_TILES"}),
    "BG_PALETTE_PAYLOAD": frozenset({"PALETTES"}),
    "MAP_COLUMN_PAIRED": frozenset({"ATTRIBUTES", "BG_MAP"}),
    "MAP_CONNECTION_PAIRED": frozenset({"ATTRIBUTES", "BG_MAP"}),
    "MAP_OVERLAY_PAIRED": frozenset({"ATTRIBUTES", "BG_MAP"}),
    "MAP_RECTANGLE_PAIRED": frozenset({"ATTRIBUTES", "BG_MAP"}),
    "MAP_ROW_PAIRED": frozenset({"ATTRIBUTES", "BG_MAP"}),
    "OAM_BATCH_AND_DMA": frozenset({"HARDWARE_OAM", "SHADOW_OAM"}),
    "OBJ_PALETTE_PAYLOAD": frozenset({"PALETTES"}),
}


class Phase2MeasurementError(ValueError):
    """The measured products cannot safely host the Phase 2 representation."""


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise Phase2MeasurementError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise Phase2MeasurementError(f"{path}: expected non-empty string")
    return value


def _positive_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise Phase2MeasurementError(f"{path}: expected positive integer")
    return value


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise Phase2MeasurementError(f"{path}: expected boolean")
    return value


def _array(value: object, path: str, *, nonempty: bool = False) -> list[object]:
    if not isinstance(value, list) or (nonempty and not value):
        raise Phase2MeasurementError(
            f"{path}: expected {'non-empty ' if nonempty else ''}array"
        )
    return value


@dataclass(frozen=True, slots=True)
class Phase2Definition:
    descriptor_layout: tuple[tuple[str, int], ...]
    scratch_layout: tuple[tuple[str, int], ...]
    debug_header_bytes: int
    debug_record_bytes: int
    classes: tuple["RequestClassMeasurement", ...]
    scenario: tuple[tuple[str, tuple["PressureRequest", ...], bool], ...]
    aggregate_high_water: int
    class_high_water: Mapping[str, int]

    @property
    def descriptor_bytes(self) -> int:
        return sum(size for _, size in self.descriptor_layout)

    @property
    def scratch_bytes(self) -> int:
        return sum(size for _, size in self.scratch_layout)


@dataclass(frozen=True, slots=True)
class RequestClassMeasurement:
    name: str
    required_work: bool
    equivalent_at_capacity: bool
    high_water_mark: int
    retry_observable: bool = True
    fallback_observable: bool = False


@dataclass(frozen=True, slots=True)
class PressureRequest:
    request_class: str
    owner: str
    generation: str
    resources: tuple[str, ...]
    destination: str
    desired_state: str
    visible_boundary: str

    @property
    def equivalence_identity(self) -> tuple[object, ...]:
        return (
            self.request_class,
            self.owner,
            self.generation,
            self.resources,
            self.destination,
            self.desired_state,
            self.visible_boundary,
        )


@dataclass(frozen=True, slots=True)
class RequestClassDecision:
    name: str
    high_water_mark: int
    required_work_policy: str
    capacity_equivalence_policy: str
    retry_observable: bool
    fallback_observable: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "high_water_mark": self.high_water_mark,
            "required_work_policy": self.required_work_policy,
            "capacity_equivalence_policy": self.capacity_equivalence_policy,
            "retry_observable": self.retry_observable,
            "fallback_observable": self.fallback_observable,
        }


@dataclass(frozen=True, order=True, slots=True)
class Phase2Candidate:
    wram_bank: int
    wram_start: int
    wram_end: int
    sram_bank: int
    sram_start: int
    sram_end: int
    rom_bank: int
    rom_start: int
    rom_end: int
    stack_margin_bytes: int
    ownership_adjacent: bool = False
    overlaps: tuple[str, ...] = ()
    forbidden_reason: str | None = None

    @property
    def wram_bytes(self) -> int:
        return self.wram_end - self.wram_start + 1

    @property
    def sram_bytes(self) -> int:
        return self.sram_end - self.sram_start + 1

    @property
    def rom_bytes(self) -> int:
        return self.rom_end - self.rom_start + 1

    @property
    def selection_key(self) -> tuple[int, int, int, int, int, int]:
        return (
            0 if self.ownership_adjacent else 1,
            -self.rom_bytes,
            self.rom_bank,
            self.wram_bank,
            self.wram_start,
            self.sram_start,
        )


@dataclass(frozen=True, slots=True)
class Phase2Measurement:
    input_sha256: Mapping[str, str]
    definition: Phase2Definition
    classes: tuple[RequestClassMeasurement, ...]
    descriptor_bytes: int
    scratch_bytes: int
    valid_candidates: tuple[Phase2Candidate, ...]
    rejected_candidates: tuple[tuple[str, str], ...] = ()
    ownership_state_bytes: int = PHASE1_STATE_BYTES
    inventory_audit: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Phase2Decision:
    schema: str
    input_sha256: Mapping[str, str]
    request_classes: tuple[RequestClassDecision, ...]
    descriptor_bytes: int
    capacity: int
    scratch_bytes: int
    wram_bank: int
    wram_start: int
    sram_bank: int
    sram_start: int
    rom_bank: int
    wram_end: int
    sram_end: int
    rom_start: int
    rom_end: int
    debug_carrier_capacity: int
    ownership_state_bytes: int
    audit_guard: str
    normal_rom_reachable: bool
    rejected_candidates: tuple[tuple[str, str], ...]
    inventory_audit: Mapping[str, object]
    descriptor_layout: tuple[tuple[str, int], ...]
    scratch_layout: tuple[tuple[str, int], ...]
    debug_header_bytes: int
    debug_record_bytes: int
    pressure_scenario: tuple[tuple[str, tuple[PressureRequest, ...], bool], ...]

    @classmethod
    def from_measurement(
        cls,
        measurement: Phase2Measurement,
        decisions: tuple[RequestClassDecision, ...],
        candidate: Phase2Candidate,
    ) -> "Phase2Decision":
        capacity = measurement.definition.aggregate_high_water
        needed_wram = (
            measurement.scratch_bytes + capacity * measurement.descriptor_bytes
        )
        debug_capacity = (
            candidate.sram_bytes - measurement.definition.debug_header_bytes
        ) // measurement.definition.debug_record_bytes
        if candidate.wram_bytes < needed_wram:
            raise Phase2MeasurementError(
                "selected WRAM candidate does not fit representation"
            )
        if debug_capacity < capacity:
            raise Phase2MeasurementError(
                "selected SRAM candidate lacks debug-carrier capacity"
            )
        return cls(
            SCHEMA,
            dict(sorted(measurement.input_sha256.items())),
            decisions,
            measurement.descriptor_bytes,
            capacity,
            measurement.scratch_bytes,
            candidate.wram_bank,
            candidate.wram_start,
            candidate.sram_bank,
            candidate.sram_start,
            candidate.rom_bank,
            candidate.wram_start + needed_wram - 1,
            candidate.sram_start
            + measurement.definition.debug_header_bytes
            + capacity * measurement.definition.debug_record_bytes
            - 1,
            candidate.rom_start,
            candidate.rom_start + MINIMUM_ROM_BYTES - 1,
            debug_capacity,
            measurement.ownership_state_bytes,
            AUDIT_GUARD,
            True,
            measurement.rejected_candidates,
            dict(measurement.inventory_audit),
            measurement.definition.descriptor_layout,
            measurement.definition.scratch_layout,
            measurement.definition.debug_header_bytes,
            measurement.definition.debug_record_bytes,
            measurement.definition.scenario,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "inputs": {
                key: {"path": key, "sha256": value}
                for key, value in sorted(self.input_sha256.items())
            },
            "activation": {
                "normal_rom_reachable": self.normal_rom_reachable,
                "production_products": list(PRODUCTION_PRODUCTS),
                "audit_diagnostics": {
                    "guard": self.audit_guard,
                    "product": PHASE2_AUDIT_PRODUCT,
                },
            },
            "inventory_audit": dict(self.inventory_audit),
            "ownership_abi": {"preserved_prefix_bytes": self.ownership_state_bytes},
            "requests": {
                "descriptor_bytes": self.descriptor_bytes,
                "descriptor_layout": [
                    {"name": name, "bytes": size}
                    for name, size in self.descriptor_layout
                ],
                "capacity": self.capacity,
                "classes": [item.to_dict() for item in self.request_classes],
                "pressure_measurement": {
                    "bounded": True,
                    "aggregate_high_water": self.capacity,
                    "steps": [
                        {
                            "name": name,
                            "drain_before": drain,
                            "enqueue": [
                                {
                                    "class": request.request_class,
                                    "owner": request.owner,
                                    "generation": request.generation,
                                    "resources": list(request.resources),
                                    "destination": request.destination,
                                    "desired_state": request.desired_state,
                                    "visible_boundary": request.visible_boundary,
                                }
                                for request in enqueue
                            ],
                        }
                        for name, enqueue, drain in self.pressure_scenario
                    ],
                },
            },
            "scratch": {
                "bytes": self.scratch_bytes,
                "layout": [
                    {"name": name, "bytes": size} for name, size in self.scratch_layout
                ],
            },
            "wram": {
                "bank": self.wram_bank,
                "start": self.wram_start,
                "end": self.wram_end,
            },
            "sram_debug_carrier": {
                "bank": self.sram_bank,
                "start": self.sram_start,
                "end": self.sram_end,
                "record_bytes": self.debug_record_bytes,
                "record_capacity": self.debug_carrier_capacity,
                "selected_records": self.capacity,
            },
            "rom": {
                "bank": self.rom_bank,
                "start": self.rom_start,
                "end": self.rom_end,
                "reserved_bytes": MINIMUM_ROM_BYTES,
            },
            "rejected_candidates": [
                {"candidate": name, "reason": reason}
                for name, reason in self.rejected_candidates
            ],
            "selection_rule": (
                "common release/debug WRAM/SRAM free space; use the exact common linked "
                "Full Color Phase 2 Pipelines ROM section across normal, debug, VC, and "
                "audit products; preserve the 13-byte ownership ABI; select the lowest "
                "fitting WRAM/SRAM address; required work defers with observable caller retry"
            ),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


def load_definition(path: Path) -> Phase2Definition:
    """Parse concrete layouts and replay the bounded hostile pressure trace."""
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object
        )
        if not isinstance(raw, dict):
            raise Phase2MeasurementError("Phase 2 definition must be an object")
        if set(raw) != {
            "schema",
            "descriptor",
            "scratch",
            "debug_carrier",
            "request_classes",
            "scenario",
        }:
            raise Phase2MeasurementError("unknown or omitted Phase 2 definition fields")
        if raw["schema"] != "full-color-phase2-hostile-slice-definition-v1":
            raise Phase2MeasurementError("unexpected Phase 2 definition schema")
        if (
            any(set(item) != {"name", "bytes"} for item in raw["descriptor"])
            or any(set(item) != {"name", "bytes"} for item in raw["scratch"])
            or set(raw["debug_carrier"]) != {"header_bytes", "record_bytes"}
            or any(
                set(item)
                != {
                    "name",
                    "required_work",
                    "equivalent_at_capacity",
                    "retry_observable",
                    "fallback_observable",
                }
                for item in raw["request_classes"]
            )
        ):
            raise Phase2MeasurementError("unknown or omitted Phase 2 definition fields")
        descriptor_rows = _array(raw["descriptor"], "descriptor", nonempty=True)
        scratch_rows = _array(raw["scratch"], "scratch", nonempty=True)
        class_rows = _array(raw["request_classes"], "request_classes", nonempty=True)
        scenario_rows = _array(raw["scenario"], "scenario", nonempty=True)
        descriptor = tuple(
            (
                _string(item["name"], f"descriptor[{index}].name"),
                _positive_int(item["bytes"], f"descriptor[{index}].bytes"),
            )
            for index, item in enumerate(descriptor_rows)
        )
        scratch = tuple(
            (
                _string(item["name"], f"scratch[{index}].name"),
                _positive_int(item["bytes"], f"scratch[{index}].bytes"),
            )
            for index, item in enumerate(scratch_rows)
        )
        debug_header = _positive_int(
            raw["debug_carrier"]["header_bytes"], "debug_carrier.header_bytes"
        )
        debug_record = _positive_int(
            raw["debug_carrier"]["record_bytes"], "debug_carrier.record_bytes"
        )
        names = tuple(
            _string(item["name"], f"request_classes[{index}].name")
            for index, item in enumerate(class_rows)
        )
        if (
            names != tuple(sorted(set(names)))
            or set(names) != set(REQUEST_CLASS_REQUIRED_RESOURCES)
            or len({name for name, _ in descriptor}) != len(descriptor)
            or len({name for name, _ in scratch}) != len(scratch)
        ):
            raise Phase2MeasurementError("malformed Phase 2 layout or request classes")
        typed_class_rows = []
        for index, item in enumerate(class_rows):
            typed_class_rows.append(
                {
                    "name": names[index],
                    "required_work": _boolean(
                        item["required_work"], f"request_classes[{index}].required_work"
                    ),
                    "equivalent_at_capacity": _boolean(
                        item["equivalent_at_capacity"],
                        f"request_classes[{index}].equivalent_at_capacity",
                    ),
                    "retry_observable": _boolean(
                        item["retry_observable"],
                        f"request_classes[{index}].retry_observable",
                    ),
                    "fallback_observable": _boolean(
                        item["fallback_observable"],
                        f"request_classes[{index}].fallback_observable",
                    ),
                }
            )
        class_rows = typed_class_rows
        # Resident descriptors are keyed by destination for request classes
        # whose final desired state may replace an older request.  Other work
        # remains independently resident even when its class matches.
        queue: list[PressureRequest] = []
        aggregate = 0
        per_class = {name: 0 for name in names}
        scenario = []
        for step_index, step in enumerate(scenario_rows):
            required_step_keys = {"name", "enqueue", "identity"}
            if set(step) not in (required_step_keys, required_step_keys | {"drain"}):
                raise Phase2MeasurementError(
                    "scenario step has unknown or omitted identity fields"
                )
            identity = step["identity"]
            if set(identity) != {
                "owner",
                "generation",
                "resources",
                "visible_boundary",
            }:
                raise Phase2MeasurementError(
                    "scenario identity requires owner, generation, resources, and visible_boundary"
                )
            step_name = _string(step["name"], f"scenario[{step_index}].name")
            owner = _string(identity["owner"], f"scenario[{step_index}].identity.owner")
            generation = _string(
                identity["generation"], f"scenario[{step_index}].identity.generation"
            )
            resource_values = _array(
                identity["resources"],
                f"scenario[{step_index}].identity.resources",
                nonempty=True,
            )
            resources = tuple(
                _string(resource, f"scenario[{step_index}].identity.resources[{index}]")
                for index, resource in enumerate(resource_values)
            )
            if resources != tuple(sorted(set(resources))):
                raise Phase2MeasurementError(
                    "scenario identity resources must be unique and sorted"
                )
            unknown_resources = sorted(set(resources) - RESOURCE_VOCABULARY)
            if unknown_resources:
                raise Phase2MeasurementError(
                    f"scenario identity uses unknown resources: {unknown_resources}"
                )
            visible_boundary = _string(
                identity["visible_boundary"],
                f"scenario[{step_index}].identity.visible_boundary",
            )
            drain = _boolean(step.get("drain", False), f"scenario[{step_index}].drain")
            if drain:
                queue.clear()
            enqueued_list = []
            for item_index, item in enumerate(
                _array(
                    step["enqueue"], f"scenario[{step_index}].enqueue", nonempty=True
                )
            ):
                if set(item) != {"class", "destination", "desired_state"}:
                    raise Phase2MeasurementError(
                        "scenario request has unknown or omitted definition fields"
                    )
                enqueued_list.append(
                    PressureRequest(
                        _string(
                            item["class"],
                            f"scenario[{step_index}].enqueue[{item_index}].class",
                        ),
                        owner,
                        generation,
                        resources,
                        _string(
                            item["destination"],
                            f"scenario[{step_index}].enqueue[{item_index}].destination",
                        ),
                        _string(
                            item["desired_state"],
                            f"scenario[{step_index}].enqueue[{item_index}].desired_state",
                        ),
                        visible_boundary,
                    )
                )
            enqueued = tuple(enqueued_list)
            unknown = sorted({item.request_class for item in enqueued} - set(names))
            if unknown:
                raise Phase2MeasurementError(
                    f"scenario names unknown request classes: {unknown}"
                )
            expected_resources = frozenset().union(
                *(
                    REQUEST_CLASS_REQUIRED_RESOURCES[item.request_class]
                    for item in enqueued
                )
            )
            if set(resources) != expected_resources:
                raise Phase2MeasurementError(
                    "scenario identity resources are incompatible with its request classes; "
                    f"expected {sorted(expected_resources)}, got {sorted(resources)}"
                )
            class_rows_by_name = {item["name"]: item for item in class_rows}
            for request in enqueued:
                request_class = request.request_class
                required_resources = REQUEST_CLASS_REQUIRED_RESOURCES[request_class]
                if not required_resources <= set(request.resources):
                    raise Phase2MeasurementError(
                        f"{request_class}: incompatible identity resources; requires "
                        f"{sorted(required_resources)}"
                    )
                if class_rows_by_name[request_class]["equivalent_at_capacity"]:
                    queue = [
                        resident
                        for resident in queue
                        if resident.equivalence_identity != request.equivalence_identity
                    ]
                queue.append(request)
            aggregate = max(aggregate, len(queue))
            for name in names:
                per_class[name] = max(
                    per_class[name], sum(item.request_class == name for item in queue)
                )
            scenario.append((step_name, enqueued, drain))
        if aggregate <= 0 or any(value <= 0 for value in per_class.values()):
            raise Phase2MeasurementError(
                "bounded hostile scenario does not exercise every class"
            )
        classes = tuple(
            RequestClassMeasurement(
                item["name"],
                item["required_work"],
                item["equivalent_at_capacity"],
                per_class[item["name"]],
                item["retry_observable"],
                item["fallback_observable"],
            )
            for item in class_rows
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise Phase2MeasurementError(
            "malformed Phase 2 representation definition"
        ) from exc
    return Phase2Definition(
        descriptor,
        scratch,
        debug_header,
        debug_record,
        classes,
        tuple(scenario),
        aggregate,
        dict(sorted(per_class.items())),
    )


def select_required_defer_policy(item: RequestClassMeasurement) -> RequestClassDecision:
    if not item.name or item.high_water_mark <= 0:
        raise Phase2MeasurementError(
            "request class requires a name and positive high-water mark"
        )
    if item.required_work and not item.retry_observable:
        raise Phase2MeasurementError(
            f"{item.name}: required DEFERRED work lacks runtime-observable retry"
        )
    if not item.required_work and not item.fallback_observable:
        raise Phase2MeasurementError(
            f"{item.name}: optional work lacks runtime-observable fallback"
        )
    return RequestClassDecision(
        item.name,
        item.high_water_mark,
        "DEFERRED_CALLER_RETRY" if item.required_work else "REJECTED_OBSERVED_FALLBACK",
        "COALESCED_FINAL_STATE"
        if item.equivalent_at_capacity
        else "DEFERRED_CALLER_RETRY",
        item.retry_observable,
        item.fallback_observable,
    )


def select_phase2_representation(measurement: Phase2Measurement) -> Phase2Decision:
    if measurement.descriptor_bytes != measurement.definition.descriptor_bytes:
        raise Phase2MeasurementError(
            "descriptor byte cost does not match the hashed concrete definition"
        )
    if measurement.scratch_bytes != measurement.definition.scratch_bytes:
        raise Phase2MeasurementError(
            "scratch byte cost does not match the hashed concrete definition"
        )
    if measurement.classes != measurement.definition.classes:
        raise Phase2MeasurementError(
            "request classes/policies do not match hostile trace definition"
        )
    if measurement.ownership_state_bytes != PHASE1_STATE_BYTES:
        raise Phase2MeasurementError("Phase 1 ownership ABI prefix changed")
    decisions = tuple(
        select_required_defer_policy(item) for item in measurement.classes
    )
    if tuple(sorted(item.name for item in decisions)) != tuple(
        item.name for item in decisions
    ):
        raise Phase2MeasurementError("request classes must be sorted by stable name")
    capacity = measurement.definition.aggregate_high_water
    needed_wram = measurement.scratch_bytes + capacity * measurement.descriptor_bytes
    needed_sram = (
        measurement.definition.debug_header_bytes
        + capacity * measurement.definition.debug_record_bytes
    )
    valid = []
    for candidate in measurement.valid_candidates:
        if candidate.overlaps or candidate.forbidden_reason:
            continue
        if candidate.stack_margin_bytes < MINIMUM_STACK_MARGIN:
            continue
        if candidate.rom_bank in FORBIDDEN_ROM_BANKS:
            continue
        if candidate.wram_bytes < needed_wram:
            continue
        if candidate.sram_bytes < needed_sram:
            continue
        if candidate.rom_bytes < MINIMUM_ROM_BYTES:
            continue
        valid.append(candidate)
    if not valid:
        raise Phase2MeasurementError(
            "no non-overlapping Phase 2 candidate fits measured WRAM/SRAM/ROM limits"
        )
    candidate = min(valid, key=lambda item: item.selection_key)
    return Phase2Decision.from_measurement(measurement, decisions, candidate)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_sections(path: Path) -> dict[tuple[str, int], list[tuple[int, int, str]]]:
    result: dict[tuple[str, int], list[tuple[int, int, str]]] = {}
    kind: str | None = None
    bank: int | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if match := _BANK.match(line):
            kind, bank = match.group(1), int(match.group(2))
            result.setdefault((kind, bank), [])
            continue
        if kind is None or bank is None or not (match := _SECTION.match(line)):
            continue
        start = int(match.group(1), 16)
        end = int(match.group(2) or match.group(1), 16)
        result[(kind, bank)].append((start, end, match.group(4)))
    return result


def _common_linked_pipeline_section(
    product_sections: Mapping[
        str, Mapping[tuple[str, int], Sequence[tuple[int, int, str]]]
    ],
) -> tuple[int, int, int]:
    products = (*PRODUCTION_PRODUCTS, PHASE2_AUDIT_PRODUCT)
    missing_products = tuple(
        product for product in products if product not in product_sections
    )
    if missing_products:
        raise Phase2MeasurementError(
            "missing linked section data for product(s): " + ", ".join(missing_products)
        )

    placements: dict[str, tuple[int, int, int]] = {}
    for product in products:
        matches = tuple(
            (bank, low, high)
            for (kind, bank), values in product_sections[product].items()
            if kind == "ROMX"
            for low, high, name in values
            if name == PHASE2_PIPELINE_SECTION
        )
        if not matches:
            raise Phase2MeasurementError(
                f'{product}: missing linked ROMX section "{PHASE2_PIPELINE_SECTION}"'
            )
        if len(matches) != 1:
            raise Phase2MeasurementError(
                f'{product}: multiple linked ROMX sections named "{PHASE2_PIPELINE_SECTION}"'
            )
        placements[product] = matches[0]

    unique = set(placements.values())
    if len(unique) != 1:
        rendered = ", ".join(
            f"{product}=${bank:02x}:${low:04x}-${high:04x}"
            for product, (bank, low, high) in placements.items()
        )
        raise Phase2MeasurementError(
            f'linked "{PHASE2_PIPELINE_SECTION}" placement differs across products: '
            f"{rendered}"
        )

    bank, low, high = next(iter(unique))
    if not ROMX_START <= low <= high <= ROMX_END:
        raise Phase2MeasurementError(
            f'linked "{PHASE2_PIPELINE_SECTION}" is outside the ROMX window'
        )
    size = high - low + 1
    if size < MINIMUM_ROM_BYTES:
        raise Phase2MeasurementError(
            f'linked "{PHASE2_PIPELINE_SECTION}" is undersized: '
            f"{size} bytes < {MINIMUM_ROM_BYTES} bytes"
        )
    if bank in FORBIDDEN_ROM_BANKS:
        raise Phase2MeasurementError(
            f'linked "{PHASE2_PIPELINE_SECTION}" uses forbidden ROM bank '
            f"${bank:02x}: {FORBIDDEN_ROM_BANKS[bank]}"
        )
    return bank, low, high


def _free(
    start: int, end: int, occupied: Sequence[tuple[int, int, str]]
) -> list[tuple[int, int]]:
    ranges = []
    cursor = start
    for low, high, _ in sorted(occupied):
        if high < start or low > end:
            continue
        low, high = max(low, start), min(high, end)
        if cursor < low:
            ranges.append((cursor, low - 1))
        cursor = max(cursor, high + 1)
    if cursor <= end:
        ranges.append((cursor, end))
    return ranges


def _intersection(
    left: Sequence[tuple[int, int]], right: Sequence[tuple[int, int]]
) -> list[tuple[int, int]]:
    return [
        (max(a, c), min(b, d))
        for a, b in left
        for c, d in right
        if max(a, c) <= min(b, d)
    ]


def _stack_margin(
    sym_path: Path, sections: Mapping[tuple[str, int], list[tuple[int, int, str]]]
) -> int:
    address = None
    for line in sym_path.read_text(encoding="utf-8").splitlines():
        match = _SYMBOL.match(line)
        if match and match.group(3) == "wStack":
            address = int(match.group(2), 16)
            break
    stacks = [
        item for values in sections.values() for item in values if item[2] == "Stack"
    ]
    if (
        address is None
        or len(stacks) != 1
        or not stacks[0][0] <= address <= stacks[0][1]
    ):
        raise Phase2MeasurementError("linker products do not define one valid wStack")
    return address - stacks[0][0] + 1


def _phase2_roots() -> tuple[str, ...]:
    return tuple(
        sorted(
            set(PHASE2_HOSTILE_LIFECYCLE_ROOTS)
            | set(PHASE2_HOSTILE_SCENE_ROOTS)
            | set(PHASE2_HOSTILE_MUTATION_ROOTS)
        )
    )


@lru_cache(maxsize=4)
def discover_phase2_sources(
    root: Path, *, guarded: bool = True
) -> SourceDiscoveryReport:
    """Run the real source discoverer over every declared hostile-slice root."""
    if guarded:
        _verify_audit_product(root)
    return discover_sources(
        root,
        SOURCE_ROOTS,
        lifecycle_roots=PHASE2_HOSTILE_LIFECYCLE_ROOTS,
        scene_roots=PHASE2_HOSTILE_SCENE_ROOTS,
        mutation_roots=PHASE2_HOSTILE_MUTATION_ROOTS,
        scene_edge_classifications=PHASE2_SCENE_EDGE_CLASSIFICATIONS,
    )


def _verify_audit_product(root: Path) -> tuple[Path, Path, Path]:
    rom_path = root / "pokeyellow_phase2_audit.gbc"
    sym_path = root / "pokeyellow_phase2_audit.sym"
    map_path = root / "pokeyellow_phase2_audit.map"
    if not all(path.is_file() for path in (rom_path, sym_path, map_path)):
        raise Phase2MeasurementError("missing compile-time PHASE2_AUDIT link product")
    symbols = load_sym(sym_path)
    try:
        marker = symbols.by_name["Phase2AuditProvenance"]
        roots_start = symbols.by_name["Phase2AuditRoots"]
        roots_end = symbols.by_name["Phase2AuditRootsEnd"]
    except KeyError as exc:
        raise Phase2MeasurementError(
            "audit product lacks PHASE2_AUDIT provenance symbols"
        ) from exc
    rom = rom_path.read_bytes()
    offset = normalize_rom_offset(marker.bank, marker.address)
    if rom[offset : offset + len(AUDIT_MARKER)] != AUDIT_MARKER:
        raise Phase2MeasurementError(
            "audit product has invalid compile-time provenance marker"
        )
    if roots_end.address - roots_start.address != 2 * len(_phase2_roots()):
        raise Phase2MeasurementError(
            "audit product root table does not cover configured roots"
        )
    table_offset = normalize_rom_offset(roots_start.bank, roots_start.address)
    table = rom[table_offset : table_offset + 2 * len(_phase2_roots())]
    if len(table) != 2 * len(_phase2_roots()):
        raise Phase2MeasurementError("audit product root table is truncated")
    decoded = tuple(
        int.from_bytes(table[index : index + 2], "little")
        for index in range(0, len(table), 2)
    )
    try:
        expected = tuple(symbols.by_name[name].address for name in _phase2_roots())
    except KeyError as exc:
        raise Phase2MeasurementError(
            f"audit product lacks configured root symbol {exc.args[0]!r}"
        ) from exc
    if len(set(decoded)) != len(decoded):
        raise Phase2MeasurementError(
            "audit product root table contains duplicate pointers"
        )
    if decoded != expected:
        mismatch = next(
            (
                (name, actual, wanted)
                for name, actual, wanted in zip(_phase2_roots(), decoded, expected)
                if actual != wanted
            ),
            None,
        )
        raise Phase2MeasurementError(
            f"audit product root pointer does not match configured symbol: {mismatch}"
        )
    sections = load_map(map_path)
    if not any(
        section.name == "Phase 2 Audit Provenance"
        and section.bank == marker.bank
        and section.start <= marker.address <= section.end
        for section in sections
    ):
        raise Phase2MeasurementError(
            "audit marker is not linked in its provenance section"
        )
    forbidden = (b"Phase2Audit", b"FullColorPhase2", b"Phase2Hostile", AUDIT_MARKER)
    for stem in ("pokeyellow", "pokeyellow_debug", "pokeyellow_vc"):
        for suffix in (".sym", ".map", ".gbc"):
            product = root / f"{stem}{suffix}"
            blob = product.read_bytes()
            if any(marker in blob for marker in forbidden):
                raise Phase2MeasurementError(
                    f"normal product {product.name} exposes a forbidden Phase 2 entry, "
                    "section, marker, or call-path"
                )
    return rom_path, sym_path, map_path


@lru_cache(maxsize=8)
def discover_phase2_rom_product(root: Path, product: str):
    """Run exact hostile-slice discovery against one explicit link product."""
    stem = PRODUCT_ARTIFACTS.get(product)
    if stem is None:
        raise Phase2MeasurementError(f"unknown Phase 2 link product: {product}")
    if product == PHASE2_AUDIT_PRODUCT:
        rom_path, sym_path, map_path = _verify_audit_product(root)
    else:
        rom_path = root / f"{stem}.gbc"
        sym_path = root / f"{stem}.sym"
        map_path = root / f"{stem}.map"
        if not all(path.is_file() for path in (rom_path, sym_path, map_path)):
            raise Phase2MeasurementError(
                f"missing production link artifacts for {product}"
            )
    symbols = load_sym(sym_path)
    roots = _phase2_roots()
    return discover_rom_batched(
        rom_path.read_bytes(),
        symbols,
        roots,
        batch_size=16,
        sections=load_map(map_path),
        farcall_labels=FARCALL_LABELS,
        predef_targets=load_predef_targets(root, symbols),
        copied_regions=COPIED_REGIONS,
        shadow_oam_ranges=SHADOW_OAM_RANGES,
        scene_roots=tuple(
            sorted(
                set(PHASE2_HOSTILE_LIFECYCLE_ROOTS) | set(PHASE2_HOSTILE_SCENE_ROOTS)
            )
        ),
        mutation_roots=PHASE2_HOSTILE_MUTATION_ROOTS,
        dma_control_labels=DMA_CONTROL_LABELS,
        follow_calls=False,
    )


def _load_planned_subjects(
    root: Path,
    *,
    closed: bool = False,
) -> tuple[
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
    dict[str, dict[str, object]],
    dict[str, str],
    tuple[str, ...],
    dict[str, dict[str, str]],
]:
    try:
        raw = json.loads(
            (root / PLANNED_SUBJECTS_PATH).read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase2MeasurementError(
            "invalid planned semantic subject authority"
        ) from exc
    if (
        not isinstance(raw, dict)
        or set(raw)
        != {
            "schema",
            "source_subjects",
            "rom_subjects",
            "rom_candidate_subjects",
            "rom_unresolved_dispositions",
            "source_error_subjects",
            "source_error_disposition",
            "planned_only_dispositions",
            "shared_candidate_dispositions",
            "authority_counts",
        }
        or raw["schema"] != "full-color-phase2-planned-subjects-v5"
    ):
        raise Phase2MeasurementError("invalid planned semantic subject authority")
    result = []
    for kind in ("source_subjects", "rom_subjects", "rom_candidate_subjects"):
        mapping = raw[kind]
        if not isinstance(mapping, dict) or set(mapping) != PHASE2_PLANNED_ROW_IDS:
            raise Phase2MeasurementError(
                f"{kind}: must bind the exact planned Phase 2 row set"
            )
        checked: dict[str, tuple[str, ...]] = {}
        for row_id, values in mapping.items():
            items = tuple(
                _string(value, f"{kind}.{row_id}[{index}]")
                for index, value in enumerate(_array(values, f"{kind}.{row_id}"))
            )
            if items != tuple(sorted(set(items))) or any(
                not _SHA256.fullmatch(item) for item in items
            ):
                raise Phase2MeasurementError(
                    f"{kind}.{row_id}: subjects must be unique sorted canonical SHA-256 digests"
                )
            checked[row_id] = items
        result.append(checked)
        flattened = [item for values in checked.values() for item in values]
        if len(flattened) != len(set(flattened)):
            raise Phase2MeasurementError(
                f"{kind}: one canonical subject may bind exactly one planned row"
            )

    shared = raw["shared_candidate_dispositions"]
    if not isinstance(shared, dict) or tuple(shared) != tuple(sorted(shared)):
        raise Phase2MeasurementError(
            "shared_candidate_dispositions: must be an object sorted by candidate digest"
        )
    checked_shared: dict[str, dict[str, object]] = {}
    assignment_products = tuple(sorted((*PRODUCTION_PRODUCTS, PHASE2_AUDIT_PRODUCT)))
    for digest, disposition in shared.items():
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise Phase2MeasurementError(
                "shared_candidate_dispositions: keys must be canonical SHA-256 digests"
            )
        if not isinstance(disposition, dict) or set(disposition) != {
            "disposition",
            "eligible_rows",
            "products",
            "representative_row",
            "reviewed",
            "reviewer",
        }:
            raise Phase2MeasurementError(
                f"shared_candidate_dispositions.{digest}: malformed disposition"
            )
        eligible_rows = tuple(
            _string(
                value, f"shared_candidate_dispositions.{digest}.eligible_rows[{index}]"
            )
            for index, value in enumerate(
                _array(
                    disposition["eligible_rows"],
                    f"shared_candidate_dispositions.{digest}.eligible_rows",
                )
            )
        )
        products = tuple(
            _string(value, f"shared_candidate_dispositions.{digest}.products[{index}]")
            for index, value in enumerate(
                _array(
                    disposition["products"],
                    f"shared_candidate_dispositions.{digest}.products",
                )
            )
        )
        representative = _string(
            disposition["representative_row"],
            f"shared_candidate_dispositions.{digest}.representative_row",
        )
        reviewer = disposition["reviewer"]
        if (
            len(eligible_rows) < 2
            or eligible_rows != tuple(sorted(set(eligible_rows)))
            or not set(eligible_rows) <= PHASE2_PLANNED_ROW_IDS
            or products != assignment_products
            or representative not in eligible_rows
            or disposition["disposition"] != "REVIEWED_SHARED_SITE_REPRESENTATIVE"
            or disposition["reviewed"] is not True
            or not isinstance(reviewer, str)
            or not reviewer
            or reviewer != reviewer.strip()
            or "\n" in reviewer
            or "\r" in reviewer
        ):
            raise Phase2MeasurementError(
                f"shared_candidate_dispositions.{digest}: malformed disposition"
            )
        audit_candidate_rows = tuple(
            row_id for row_id, digests in result[2].items() if digest in digests
        )
        if audit_candidate_rows != (representative,):
            raise Phase2MeasurementError(
                f"shared_candidate_dispositions.{digest}: audit candidate must have "
                "one canonical representative row"
            )
        checked_shared[digest] = {
            "disposition": disposition["disposition"],
            "eligible_rows": eligible_rows,
            "products": products,
            "representative_row": representative,
            "reviewed": True,
            "reviewer": reviewer,
        }
    unresolved = raw["rom_unresolved_dispositions"]
    if not isinstance(unresolved, dict):
        raise Phase2MeasurementError("rom_unresolved_dispositions: expected object")
    checked_unresolved = {
        _string(message, "rom_unresolved_dispositions key"): _string(
            row_id, f"rom_unresolved_dispositions.{message}"
        )
        for message, row_id in unresolved.items()
    }
    if not set(checked_unresolved.values()) <= PHASE2_PLANNED_ROW_IDS:
        raise Phase2MeasurementError(
            "rom_unresolved_dispositions: disposition names an unknown planned row"
        )
    checked_source_errors = tuple(
        _string(value, f"source_error_subjects[{index}]")
        for index, value in enumerate(
            _array(raw["source_error_subjects"], "source_error_subjects")
        )
    )
    if (
        checked_source_errors != tuple(sorted(set(checked_source_errors)))
        or any(not _SHA256.fullmatch(item) for item in checked_source_errors)
        or raw["source_error_disposition"] != "KNOWN_DYNAMIC_JUMP_DISCOVERY_LIMITATION"
    ):
        raise Phase2MeasurementError(
            "source_error_subjects: dispositions must be unique sorted canonical SHA-256 digests"
        )

    planned_only = raw["planned_only_dispositions"]
    expected_planned_only = frozenset() if closed else PLANNED_ONLY_DISPOSITION_ROWS
    if not isinstance(planned_only, dict) or set(planned_only) != expected_planned_only:
        raise Phase2MeasurementError(
            "planned_only_dispositions: must be empty after audit closure"
            if closed
            else "planned_only_dispositions: must be the exact narrow planned-only row set"
        )
    checked_planned_only: dict[str, dict[str, object]] = {}
    for row_id, disposition in planned_only.items():
        contract = _PLANNED_ONLY_ROW_CONTRACTS[row_id]
        expected = {
            "commit_unit": contract["commit_unit"],
            "disposition": "PALETTE_GENERATION_DEFERRED_BY_PHASE2_PLAN",
            "machine_sites": list(contract["machine_sites"]),
            "resources": list(contract["resources"]),
            "role": "writer",
            "root": contract["root"],
        }
        if disposition != expected:
            raise Phase2MeasurementError(
                f"planned_only_dispositions.{row_id}: malformed disposition"
            )
        checked = dict(disposition)
        root = checked["root"]
        if (
            checked["role"] != "writer"
            or checked["disposition"] != "PALETTE_GENERATION_DEFERRED_BY_PHASE2_PLAN"
            or root not in PHASE2_ROOT_ROWS
            or PHASE2_ROOT_ROWS[root][1] != row_id
        ):
            raise Phase2MeasurementError(
                f"planned_only_dispositions.{row_id}: disposition is not role-bound"
            )
        checked_planned_only[row_id] = checked

    counts = raw["authority_counts"]
    expected_counts = {
        "source_subjects": {
            "by_row": {row_id: len(values) for row_id, values in result[0].items()},
            "total": sum(map(len, result[0].values())),
        },
        "rom_subjects": {
            "by_row": {row_id: len(values) for row_id, values in result[1].items()},
            "total": sum(map(len, result[1].values())),
        },
        "rom_candidate_subjects": {
            "by_row": {row_id: len(values) for row_id, values in result[2].items()},
            "total": sum(map(len, result[2].values())),
        },
        "shared_candidate_dispositions": {
            "by_representative_row": {
                row_id: sum(
                    disposition["representative_row"] == row_id
                    for disposition in checked_shared.values()
                )
                for row_id in sorted(PHASE2_PLANNED_ROW_IDS)
            },
            "product_bindings": sum(
                len(disposition["products"]) for disposition in checked_shared.values()
            ),
            "total": len(checked_shared),
        },
        "rom_unresolved_dispositions": {
            "by_row": {
                row_id: tuple(checked_unresolved.values()).count(row_id)
                for row_id in sorted(PHASE2_PLANNED_ROW_IDS)
            },
            "total": len(checked_unresolved),
        },
        "source_error_subjects": {"total": len(checked_source_errors)},
        "planned_only_dispositions": {"total": len(checked_planned_only)},
    }
    if counts != expected_counts:
        raise Phase2MeasurementError(
            "authority_counts: exact cardinalities or per-bucket counts changed"
        )
    return (
        result[0],
        result[1],
        result[2],
        checked_shared,
        checked_unresolved,
        checked_source_errors,
        checked_planned_only,
    )


def _reject_duplicate_projection(values: Sequence[str], label: str) -> None:
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise Phase2MeasurementError(
            f"duplicate {label} before projection: {duplicates}"
        )


def _reject_duplicate_rom_report(report: object, product: str = "") -> None:
    prefix = f"{product} " if product else ""
    _reject_duplicate_projection(
        tuple(rom_finding_subject(finding).sha256 for finding in report.findings),
        f"{prefix}ROM subjects",
    )
    _reject_duplicate_projection(
        tuple(
            rom_finding_subject(finding).sha256 for finding in report.candidate_findings
        ),
        f"{prefix}ROM candidate subjects",
    )
    _reject_duplicate_projection(
        (*report.unresolved_destinations, *report.unresolved_control_flow),
        f"{prefix}ROM unresolved messages",
    )


def _source_finding_root(finding: object) -> str | None:
    symbol = finding.symbol
    return next(
        (
            root
            for root in sorted(_phase2_roots(), key=len, reverse=True)
            if symbol == root or symbol.startswith(root + ".")
        ),
        None,
    )


_PASSIVE_PALETTE_RESOURCES = frozenset({"CGB_PALETTE", "PALETTES"})
_PASSIVE_ATTRIBUTE_RESOURCES = frozenset(
    {
        "ATTRIBUTES",
        "BG_WINDOW_MAP",
        "COMPUTED_POINTER",
        "SYMBOLIC_SINK",
        "VRAM_BANK",
        "WRAM_BANK",
    }
)


def _planned_row_for(
    root: str,
    category: str,
    *,
    resource: str | None = None,
) -> str:
    if category == "writer" and root.startswith("PassiveFullColor"):
        if resource in _PASSIVE_PALETTE_RESOURCES:
            return "WR-P2-YELLOW-BG-PALETTE"
        if resource in _PASSIVE_ATTRIBUTE_RESOURCES:
            return "WR-P2-YELLOW-OVERLAY-TRANSFER"
        raise Phase2MeasurementError(
            f"{root}: passive writer has unclassified resource {resource!r}"
        )
    control_row, writer_row = PHASE2_ROOT_ROWS[root]
    return writer_row if category == "writer" else control_row


_PASSIVE_VISIBLE_POINTER_ROOTS = {
    "PassiveFullColorApplyMap": (
        (
            "PassiveFullColorApplyMap",
            "3b:5378",
            "3b:54bd",
        ),
    ),
    "PassiveFullColorCommitVisibleAttributes": (
        ("PassiveFullColorCommitVisibleAttributes",),
    ),
}
_PASSIVE_CLEAR_POINTER_ROOTS = {
    "PassiveFullColorClearBGMapChunk": (
        ("PassiveFullColorClearBGMapChunk",),
        ("PassiveFullColorClearBGMapChunk", "3b:5513"),
        ("PassiveFullColorClearBGMapChunk", "3b:5513", "3b:5513"),
    ),
    "PassiveFullColorVBlank": (
        (
            "PassiveFullColorVBlank",
            "3b:545a",
            "3b:549a",
            "3b:54ad",
            "3b:54ba",
            "3b:54ec",
        ),
        (
            "PassiveFullColorVBlank",
            "3b:545a",
            "3b:549a",
            "3b:54ad",
            "3b:54ba",
            "3b:54ec",
            "3b:5513",
        ),
        (
            "PassiveFullColorVBlank",
            "3b:545a",
            "3b:549a",
            "3b:54ad",
            "3b:54ba",
            "3b:54ec",
            "3b:5513",
            "3b:5513",
        ),
    ),
}
_PASSIVE_COLUMN_POINTER_ROOTS = {
    "PassiveFullColorCommitRedrawColumn": (("PassiveFullColorCommitRedrawColumn",),),
    "PassiveFullColorVBlank": (("PassiveFullColorVBlank", "3b:545a", "3b:7341"),),
}
_PASSIVE_ROW_POINTER_ROOTS = {
    "PassiveFullColorCommitRedrawRow": (("PassiveFullColorCommitRedrawRow",),),
    "PassiveFullColorVBlank": (("PassiveFullColorVBlank", "3b:545a", "3b:73fa"),),
}

# Diagnostic ROM pointer sites remain a reviewed literal authority. Production
# products are independently bound by their product-specific assignments.
# Keep every reviewed pointer store literal: address drift, opcode drift, a new
# store, a new root, or different call ancestry must block projection.
_PREVIOUS_PASSIVE_ROM_POINTER_WRITES = {
    (0x3B, 0x54CF, "72"): _PASSIVE_VISIBLE_POINTER_ROOTS,
    (0x3B, 0x5513, "22"): _PASSIVE_CLEAR_POINTER_ROOTS,
    (0x3B, 0x6BD5, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6BD8, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6BDE, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6BE1, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6BE7, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6BEA, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6BF0, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6BF3, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6BF9, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6BFC, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C02, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C05, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C0B, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C0E, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C14, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C17, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C1D, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C20, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C26, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C29, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C2F, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C32, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C38, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C3B, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C41, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C44, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C4A, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C4D, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C53, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C56, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C5C, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C5F, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C65, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C68, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C6E, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C71, "12"): _PASSIVE_COLUMN_POINTER_ROOTS,
    (0x3B, 0x6C8E, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6C91, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6C97, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6C9A, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CA0, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CA3, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CA9, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CAC, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CB2, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CB5, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CBB, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CBE, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CC4, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CC7, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CCD, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CD0, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CD6, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CD9, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CDF, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CE2, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CE8, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CEB, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CF1, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CF4, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CFA, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6CFD, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D03, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D06, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D0C, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D0F, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D15, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D18, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D1E, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D21, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D27, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D2A, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D30, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D33, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D39, "12"): _PASSIVE_ROW_POINTER_ROOTS,
    (0x3B, 0x6D3C, "12"): _PASSIVE_ROW_POINTER_ROOTS,
}

# The newly linked tileset payload region sits between the fixed visible /
# clear stores and the redraw-column / redraw-row routines.  Preserve the
# prior reviewed authority so the rebase remains mechanically auditable: the
# 76 redraw stores move by one uniform cumulative delta, while the two stores
# before the inserted region remain fixed.
# The reviewed FOREST/CAVERN predecessor already established a uniform $3c0
# relocation from the original sites. SHIP_PORT/PLATEAU/BEACH_HOUSE add exactly
# three more 64-byte palette plus 256-byte attribute pairs before the passive
# code: another 3 * (64 + 256) = $3c0, for the cumulative exact $780 rebase.
_PASSIVE_ROM_POINTER_REBASE_BYTES = 0x780
_TRANSPORT_SPECIAL_PAYLOAD_BYTES = 3 * (64 + 256)
_ALL_TILESET_POINTER_EXPANSION_BYTES = 2 * 2 * 2
_PHASE4_BANK3B_CODE_REBASE_BYTES = 0x640
_PHASE4_BASELINE_EVIDENCE_ROWS = frozenset(
    {
        "MU-YELLOW-MAP-VIEW-INITIAL",
        "SC-YELLOW-MAP-ENTRY",
        "WR-YELLOW-LCDC-DISABLE",
        "WR-YELLOW-MAP-VIEW-TILE-COPY",
    }
)
_PASSIVE_ROM_POINTER_WRITES = {
    (
        bank,
        address + (_PASSIVE_ROM_POINTER_REBASE_BYTES if opcode == "12" else 0),
        opcode,
    ): roots
    for (bank, address, opcode), roots in _PREVIOUS_PASSIVE_ROM_POINTER_WRITES.items()
}


def _validate_passive_rom_pointer_authority(findings: Sequence[object]) -> None:
    passive_pointer_findings = tuple(
        finding
        for finding in findings
        if finding.category == "writer"
        and finding.resource == "UNKNOWN_DESTINATION"
        and finding.root.startswith("PassiveFullColor")
    )
    actual_sites = {
        (finding.bank, finding.address, finding.bytes)
        for finding in passive_pointer_findings
    }
    expected_sites = set(_PASSIVE_ROM_POINTER_WRITES)
    if actual_sites != expected_sites:
        raise Phase2MeasurementError(
            "passive ROM pointer sites changed: "
            f"missing={sorted(expected_sites - actual_sites)} "
            f"added={sorted(actual_sites - expected_sites)}"
        )
    for site in sorted(expected_sites):
        actual_roots = {
            finding.root
            for finding in passive_pointer_findings
            if (finding.bank, finding.address, finding.bytes) == site
        }
        expected_roots = set(_PASSIVE_ROM_POINTER_WRITES[site])
        if actual_roots != expected_roots:
            raise Phase2MeasurementError(
                "passive ROM pointer roots changed at "
                f"{site[0]:02x}:{site[1]:04x}: "
                f"missing={sorted(expected_roots - actual_roots)} "
                f"added={sorted(actual_roots - expected_roots)}"
            )
        for root in sorted(expected_roots):
            actual_paths = {
                finding.call_path
                for finding in passive_pointer_findings
                if (finding.bank, finding.address, finding.bytes) == site
                and finding.root == root
            }
            expected_paths = set(_PASSIVE_ROM_POINTER_WRITES[site][root])
            if actual_paths != expected_paths:
                raise Phase2MeasurementError(
                    "passive ROM pointer ancestry changed at "
                    f"{site[0]:02x}:{site[1]:04x} for {root}: "
                    f"missing={sorted(expected_paths - actual_paths)} "
                    f"added={sorted(actual_paths - expected_paths)}"
                )


def _planned_rom_row_for(
    finding: object,
    *,
    reviewed_pointer_rows: Mapping[str, str] | None = None,
) -> str:
    """Project only reviewed passive pointer stores hidden by ROM dataflow."""
    if finding.category != "writer" or finding.resource != "UNKNOWN_DESTINATION":
        return _planned_row_for(
            finding.root,
            finding.category,
            resource=finding.resource,
        )
    if not finding.root.startswith("PassiveFullColor"):
        return _planned_row_for(
            finding.root,
            finding.category,
            resource=finding.resource,
        )
    if reviewed_pointer_rows is not None:
        digest = rom_finding_subject(finding).sha256
        row_id = reviewed_pointer_rows.get(digest)
        if finding.mechanism != "pointer" or row_id != "WR-P2-YELLOW-OVERLAY-TRANSFER":
            raise Phase2MeasurementError(
                "unreviewed passive ROM pointer write: "
                f"{finding.root} {finding.bank:02x}:{finding.address:04x} "
                f"{finding.bytes} {finding.resource} {finding.mechanism} "
                f"{finding.call_path}"
            )
        return row_id
    expected_roots = _PASSIVE_ROM_POINTER_WRITES.get(
        (finding.bank, finding.address, finding.bytes)
    )
    allowed_paths = None if expected_roots is None else expected_roots.get(finding.root)
    root_allowed = expected_roots is not None and finding.root in expected_roots
    path_allowed = root_allowed and finding.call_path in allowed_paths
    if finding.mechanism != "pointer" or not path_allowed:
        raise Phase2MeasurementError(
            "unreviewed passive ROM pointer write: "
            f"{finding.root} {finding.bank:02x}:{finding.address:04x} "
            f"{finding.bytes} {finding.resource} {finding.mechanism} "
            f"{finding.call_path}"
        )
    return "WR-P2-YELLOW-OVERLAY-TRANSFER"


def _normalize_closed_scene_directions(
    report: SourceDiscoveryReport,
) -> SourceDiscoveryReport:
    """Translate hostile party edges into the inventory's stable vocabulary."""
    return replace(
        report,
        findings=tuple(
            replace(
                finding,
                direction=_CLOSED_SCENE_DIRECTIONS.get(
                    (finding.symbol, finding.destination), finding.direction
                ),
            )
            for finding in report.findings
        ),
    )


def _passive_production_contract_errors(
    report: SourceDiscoveryReport,
) -> tuple[str, ...]:
    """Prove that the audit product adds only passive palette/attribute work.

    The old scheduler and ownership helpers deliberately remain buildable as
    direct test seams.  They are rejected only when a configured production
    root (or one of its banked integration helpers) reaches them.
    """
    errors: list[str] = []
    edges = {(finding.symbol, finding.destination) for finding in report.findings}
    for edge in _PASSIVE_REQUIRED_EDGES:
        if edge not in edges:
            errors.append(f"passive production edge omitted: {edge[0]} -> {edge[1]}")

    for symbol, resources in _PASSIVE_REQUIRED_WRITERS.items():
        discovered = {
            finding.resource
            for finding in report.findings
            if finding.category == "writer"
            and (finding.symbol == symbol or finding.symbol.startswith(symbol + "."))
        }
        missing = sorted(resources - discovered)
        if missing:
            errors.append(
                f"{symbol}: passive donor writer resources omitted: {missing}"
            )

    for finding in report.findings:
        production_source = (
            _source_finding_root(finding) is not None
            or finding.symbol in _PRODUCTION_INTEGRATION_SYMBOLS
            or any(
                finding.symbol.startswith(symbol + ".")
                for symbol in _PRODUCTION_INTEGRATION_SYMBOLS
            )
        )
        if (
            production_source
            and finding.destination in _FORBIDDEN_PRODUCTION_DESTINATIONS
        ):
            errors.append(
                "hostile ownership/scheduler edge resurrected in production: "
                f"{finding.symbol} -> {finding.destination}"
            )
        if production_source and finding.destination.startswith(
            ("wRendererOwner", "wRendererGeneration")
        ):
            errors.append(
                "passive production mutates Yellow ownership/generation: "
                f"{finding.symbol} -> {finding.destination}"
            )
    return tuple(errors)


def _closed_concrete_subject_errors(
    source_subjects: Mapping[str, set[str]],
) -> tuple[str, ...]:
    required = (
        "WR-P2-YELLOW-BG-PALETTE",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    )
    return tuple(
        f"{row_id}: closed audit requires a discoverable concrete source subject"
        for row_id in required
        if not source_subjects.get(row_id)
    )


def _closed_inventory_row_errors(
    rows: Sequence[Mapping[str, object]],
    hashes: Mapping[str, str],
    rom: bytes,
) -> tuple[str, ...]:
    """Keep reviewed hostile rows bound to their audit product and ROM."""
    errors: list[str] = []
    for row in rows:
        row_id = str(row["id"])
        if row_id not in PHASE2_PLANNED_ROW_IDS:
            continue
        evidence = row["evidence"]
        assert isinstance(evidence, Mapping)
        if evidence["reviewed"] is not True:
            errors.append(f"{row_id}: closed audit row became unreviewed")
        for name, expected in hashes.items():
            if evidence[name] != expected:
                errors.append(
                    f"{row_id}: stale audit {name.removesuffix('_sha256')} hash"
                )
        source_sites = (
            (row["source"],) if "source" in row else row.get("source_sites", ())
        )
        if not source_sites:
            errors.append(f"{row_id}: closed audit row lacks source evidence")
        machine_sites = row.get("machine_sites", ())
        if not machine_sites:
            errors.append(f"{row_id}: closed audit row lacks machine evidence")
        for site in machine_sites:
            expected_bytes = bytes.fromhex(site["bytes"])
            start = site["rom_offset"]
            if rom[start : start + len(expected_bytes)] != expected_bytes:
                errors.append(
                    f"{row_id}: audit machine bytes do not match "
                    f"{site['bank']:02x}:{site['address']:04x}"
                )

    palette = next(row for row in rows if row["id"] == "WR-P2-YELLOW-BG-PALETTE")
    contract = _CLOSED_PALETTE_ROW_CONTRACT
    reachability = palette["reachability"]
    assert isinstance(reachability, Mapping)
    comparisons = {
        "resource": tuple(palette["resources"]) == contract["resources"],
        "commit": palette["commit_unit"] == contract["commit_unit"],
        "root": tuple(sorted(reachability["roots"])) == contract["roots"],
        "source-site": {
            site["symbol"].split(".", 1)[0] for site in palette["source_sites"]
        }
        == set(contract["roots"]),
    }
    errors.extend(
        f"WR-P2-YELLOW-BG-PALETTE: closed audit {name} contract changed"
        for name, matches in comparisons.items()
        if not matches
    )
    return tuple(errors)


def _validate_audit_assignment_enrichments(
    assignments: DiscoveryAssignmentAuthority,
    writers: WriterInventory,
    scenes: SceneInventory,
    mutations: MutationInventory,
) -> None:
    """Validate row semantics without duplicating every descendant site.

    Exact subject ownership is checked separately against the discovered
    subject-to-row projection.  Inventory source and machine sites remain the
    semantic roots of each row instead of becoming an instruction manifest.
    """
    targets = {
        row["id"]: row
        for document in (writers, scenes, mutations)
        for row in document.rows
    }
    errors: list[str] = []
    for assignment in assignments.rows:
        target = targets.get(assignment.row_id)
        if target is None:
            errors.append(f"{assignment.id}: target row does not exist")
            continue
        if assignment.subject.kind.value != "SOURCE_FINDING":
            continue
        if assignment.category.value == "mutation":
            destination = (
                assignment.subject.metadata["destination"]
                if assignment.mutation is None
                else assignment.mutation.destination
            )
            if destination != target["destination"]:
                errors.append(
                    f"{assignment.id}: mutation destination does not match "
                    f"{assignment.row_id}"
                )
        elif assignment.category.value == "scene":
            enrichment = assignment.scene
            destination = target["destination"]
            expected_shape = (
                target["row_kind"],
                target["direction"],
                None if destination is None else destination["path"],
                None if destination is None else destination["line"],
                None if destination is None else destination["symbol"],
            )
            actual_shape = (
                enrichment.row_kind.value,
                enrichment.direction,
                enrichment.destination_path,
                enrichment.destination_line,
                enrichment.destination_symbol,
            )
            if actual_shape != expected_shape:
                errors.append(
                    f"{assignment.id}: scene shape does not match {assignment.row_id}"
                )
    if errors:
        raise ValueError("\n".join(errors))


def _validate_product_assignment_coverage(
    assignments: DiscoveryAssignmentAuthority,
    expected_subject_rows: Mapping[str, str],
    hashes: Mapping[str, str],
    *,
    product: str,
) -> DiscoveryAssignmentAuthority:
    """Require one current assignment for every exact product subject."""
    selected = assignments.for_product(product)
    assigned: dict[str, str] = {}
    errors: list[str] = []
    for row in selected.rows:
        digest = row.subject.sha256
        if digest in assigned:
            errors.append(f"duplicate {product} subject assignment: {digest}")
        assigned[digest] = row.row_id
        for name, expected in hashes.items():
            if getattr(row.evidence, name) != expected:
                errors.append(
                    f"{row.id}: stale {product} {name.removesuffix('_sha256')} identity"
                )
    missing = sorted(set(expected_subject_rows) - set(assigned))
    extra = sorted(set(assigned) - set(expected_subject_rows))
    wrong = sorted(
        digest
        for digest in set(assigned) & set(expected_subject_rows)
        if assigned[digest] != expected_subject_rows[digest]
    )
    if missing:
        errors.append(f"missing {product} subject assignment(s): {missing}")
    if extra:
        errors.append(f"extra {product} subject assignment(s): {extra}")
    if wrong:
        errors.append(f"{product} subject assigned to wrong row: {wrong}")
    if errors:
        raise ValueError("\n".join(errors))
    return selected


def _product_hashes(
    source_report: SourceDiscoveryReport, rom_report: object
) -> dict[str, str]:
    return {
        "source_sha256": source_report.source_sha256,
        "rom_sha256": rom_report.rom_sha256,
        "sym_sha256": rom_report.sym_sha256,
        "map_sha256": rom_report.map_sha256,
    }


def _scoped_product_subjects(
    source_report: SourceDiscoveryReport,
    rom_report: object,
    *,
    product: str,
    shared_candidate_dispositions: Mapping[str, Mapping[str, object]],
    reviewed_pointer_rows: Mapping[str, str] | None = None,
) -> tuple[tuple[object, ...], tuple[tuple[object, str], ...]]:
    roots = set(_phase2_roots())
    source = tuple(
        finding
        for finding in source_report.findings
        if _source_finding_root(finding) is not None
    )
    rom = tuple(finding for finding in rom_report.findings if finding.root in roots)
    sites: dict[tuple[int, int], set[str]] = {}
    projected: list[tuple[object, str]] = []
    for finding in rom:
        row_id = _planned_rom_row_for(
            finding, reviewed_pointer_rows=reviewed_pointer_rows
        )
        projected.append((finding, row_id))
        sites.setdefault((finding.bank, finding.address), set()).add(row_id)

    candidates = tuple(
        finding
        for finding in rom_report.candidate_findings
        if (finding.bank, finding.address) in sites
    )
    actual_shared: dict[str, tuple[str, ...]] = {}
    for finding in candidates:
        eligible_rows = tuple(sorted(sites[(finding.bank, finding.address)]))
        if len(eligible_rows) < 2:
            continue
        digest = rom_finding_subject(finding).sha256
        if digest in actual_shared:
            raise Phase2MeasurementError(
                f"duplicate {product} shared candidate before disposition: {digest}"
            )
        actual_shared[digest] = eligible_rows
    reviewed_shared = {
        digest: disposition
        for digest, disposition in shared_candidate_dispositions.items()
        if product in disposition["products"]
    }
    errors: list[str] = []
    missing = sorted(set(actual_shared) - set(reviewed_shared))
    extra = sorted(set(reviewed_shared) - set(actual_shared))
    if missing:
        errors.append(f"missing {product} shared-candidate disposition(s): {missing}")
    if extra:
        errors.append(
            f"stale or extra {product} shared-candidate disposition(s): {extra}"
        )
    for digest in sorted(set(actual_shared) & set(reviewed_shared)):
        disposition = reviewed_shared[digest]
        if disposition.get("reviewed") is not True:
            errors.append(f"{product} shared candidate {digest} is unreviewed")
        if tuple(disposition.get("eligible_rows", ())) != actual_shared[digest]:
            errors.append(
                f"{product} shared candidate {digest} eligible row set changed: "
                f"{actual_shared[digest]}"
            )
        if disposition.get("representative_row") not in actual_shared[digest]:
            errors.append(
                f"{product} shared candidate {digest} has conflicting representative row"
            )
    if errors:
        raise Phase2MeasurementError("; ".join(errors))

    for finding in candidates:
        eligible_rows = tuple(sorted(sites[(finding.bank, finding.address)]))
        row_id = (
            eligible_rows[0]
            if len(eligible_rows) == 1
            else reviewed_shared[rom_finding_subject(finding).sha256][
                "representative_row"
            ]
        )
        assert isinstance(row_id, str)
        projected.append((finding, row_id))
    return source, tuple(projected)


def propose_phase2_subjects(root: Path) -> dict[str, object]:
    """Discover an explicitly unreviewed proposal without editing authority.

    The proposal deliberately contains raw canonical subjects and product
    identities, not assignments or inventory edits.  A reviewer can compare it
    with the checked-in authorities; the official evidence producer only
    verifies those authorities and cannot promote this output.
    """
    source_report = _normalize_closed_scene_directions(discover_phase2_sources(root))
    scoped_source = tuple(
        finding
        for finding in source_report.findings
        if _source_finding_root(finding) is not None
    )
    products: dict[str, object] = {}
    for product in (*PRODUCTION_PRODUCTS, PHASE2_AUDIT_PRODUCT):
        report = discover_phase2_rom_product(root, product)
        roots = set(_phase2_roots())
        products[product] = {
            "hashes": _product_hashes(source_report, report),
            "rom_subjects": [
                rom_finding_subject(finding).to_dict()
                for finding in report.findings
                if finding.root in roots
            ],
            "rom_candidate_subjects": [
                rom_finding_subject(finding).to_dict()
                for finding in report.candidate_findings
                if (finding.bank, finding.address)
                in {
                    (item.bank, item.address)
                    for item in report.findings
                    if item.root in roots
                }
            ],
        }
    return {
        "schema": "full-color-phase2-subject-proposal-v1",
        "reviewed": False,
        "source_sha256": source_report.source_sha256,
        "source_subjects": [
            source_finding_subject(finding).to_dict() for finding in scoped_source
        ],
        "products": products,
    }


def audit_phase2_inventory(root: Path) -> dict[str, object]:
    """Reconcile real guarded source/ROM subjects to declared inventory rows."""
    inventory_root = root / "specs/full-colors/inventory"
    writers = WriterInventory.load(inventory_root / "writers.json")
    scenes = SceneInventory.load(inventory_root / "scenes.json")
    mutations = MutationInventory.load(inventory_root / "mutations.json")
    assignments = DiscoveryAssignmentAuthority.load(inventory_root / "assignments.json")
    authority_rows = [
        row for document in (writers, scenes, mutations) for row in document.rows
    ]
    try:
        closure_state = _phase2_transition_state(
            writers=writers,
            scenes=scenes,
            mutations=mutations,
            assignments=assignments,
        )
    except ValueError as exc:
        raise Phase2MeasurementError(
            f"standalone hostile authority validation failed: {exc}"
        ) from exc
    planned = [row for row in authority_rows if row["planned"]]
    normal_assignments = assignments.for_product(BASELINE_PRODUCT)

    configured_roots = set(_phase2_roots())
    rows = [
        row
        for row in authority_rows
        if configured_roots
        & {
            site["symbol"]
            for site in (
                list(row.get("source_sites", ()))
                + ([row["source"]] if "source" in row else [])
                + (
                    [row["destination"]]
                    if "source" in row and row["destination"] is not None
                    else []
                )
            )
        }
    ]

    source_sites: dict[tuple[str, int, str], set[str]] = {}
    machine_sites: dict[tuple[int, int], set[str]] = {}
    row_roots: dict[str, set[str]] = {}
    for row in rows:
        allowed = row_roots.setdefault(row["id"], set())
        if "source" in row:
            site = row["source"]
            allowed.add(site["symbol"])
            source_sites.setdefault(
                (site["path"], site["line"], site["symbol"]), set()
            ).add(row["id"])
            if (
                row["destination"] is not None
                and row["destination"]["symbol"] in configured_roots
            ):
                site = row["destination"]
                allowed.add(site["symbol"])
                source_sites.setdefault(
                    (site["path"], site["line"], site["symbol"]), set()
                ).add(row["id"])
        for site in row.get("source_sites", ()):
            allowed.add(site["symbol"])
            source_sites.setdefault(
                (site["path"], site["line"], site["symbol"]), set()
            ).add(row["id"])
        for site in row.get("machine_sites", ()):
            machine_sites.setdefault((site["bank"], site["address"]), set()).add(
                row["id"]
            )

    roots = set(_phase2_roots())

    # Reuse the strict v2 verification-contract transition parser and
    # hash/delta validation on its native reviewed discovery surface. The
    # hostile report is a distinct scoped projection and must not weaken that
    # contract.
    try:
        baseline_source = discover_baseline_sources(root)
        _, transition = _reviewed_source_view(normal_assignments, baseline_source, root)
        baseline_rom = discover_baseline_rom(root, source_report=baseline_source)
        _reviewed_rom_view(normal_assignments, baseline_rom, transition)
        if closure_state == "planned":
            _validate_planned_rows(
                writers=writers,
                scenes=scenes,
                mutations=mutations,
                assignments=normal_assignments,
                source_report=baseline_source,
                rom_report=baseline_rom,
                rom=(root / "pokeyellow_debug.gbc").read_bytes(),
                repository=root,
            )
        del baseline_source, baseline_rom
        gc.collect()
        source_report = discover_phase2_sources(root)
        rom_report = discover_phase2_rom_product(root, PHASE2_AUDIT_PRODUCT)
    except (OSError, ValueError) as exc:
        raise Phase2MeasurementError(
            f"standalone hostile authority validation failed: {exc}"
        ) from exc

    assignment_counts: dict[str, int] = {}
    if closure_state == "production-closed":
        source_report = _normalize_closed_scene_directions(source_report)

    _reject_duplicate_projection(
        tuple(
            source_finding_subject(finding).sha256 for finding in source_report.findings
        ),
        "source subjects",
    )
    _reject_duplicate_rom_report(rom_report)
    _reject_duplicate_projection(
        tuple(source_report.errors), "source diagnostic messages"
    )

    (
        planned_source_authority,
        planned_rom_authority,
        planned_candidate_authority,
        shared_candidate_dispositions,
        planned_unresolved_authority,
        planned_source_error_authority,
        planned_only_authority,
    ) = _load_planned_subjects(root, closed=closure_state == "production-closed")

    actual_source_errors = tuple(
        sorted(source_error_subject(message).sha256 for message in source_report.errors)
    )
    if closure_state == "production-closed":
        diagnostic_shapes = tuple(
            re.sub(r":\d+:", ":<line>:", message) for message in source_report.errors
        )
        if (
            len(diagnostic_shapes) != len(planned_source_error_authority)
            or len(set(diagnostic_shapes)) != len(diagnostic_shapes)
            or any(
                not message.endswith(": unresolved jp destination hl")
                for message in diagnostic_shapes
            )
        ):
            raise Phase2MeasurementError(
                "source diagnostic dispositions changed: expected one unique "
                "known dynamic-jump limitation per reviewed semantic site"
            )
    elif actual_source_errors != planned_source_error_authority:
        raise Phase2MeasurementError(
            "source diagnostic dispositions changed: every diagnostic must appear "
            "exactly once in the hash-bound authority"
        )

    scoped_source = tuple(
        finding
        for finding in source_report.findings
        if _source_finding_root(finding) is not None
    )
    scoped_rom = tuple(
        finding for finding in rom_report.findings if finding.root in roots
    )
    scoped_sites = {(finding.bank, finding.address) for finding in scoped_rom}
    scoped_candidates = tuple(
        finding
        for finding in rom_report.candidate_findings
        if (finding.bank, finding.address) in scoped_sites
    )
    scoped_unresolved = tuple(
        message
        for message in (
            *rom_report.unresolved_destinations,
            *rom_report.unresolved_control_flow,
        )
        if message.split(":", 1)[0] in roots
    )
    _validate_passive_rom_pointer_authority(scoped_rom)
    actual_source_subjects: dict[str, set[str]] = {
        row_id: set() for row_id in PHASE2_PLANNED_ROW_IDS
    }
    actual_rom_subjects: dict[str, set[str]] = {
        row_id: set() for row_id in PHASE2_PLANNED_ROW_IDS
    }
    actual_candidate_subjects: dict[str, set[str]] = {
        row_id: set() for row_id in PHASE2_PLANNED_ROW_IDS
    }
    semantic_subject_errors: list[str] = []
    for finding in scoped_source:
        finding_root = _source_finding_root(finding)
        assert finding_root is not None
        actual_source_subjects[
            _planned_row_for(
                finding_root,
                finding.category,
                resource=finding.resource,
            )
        ].add(source_finding_subject(finding).sha256)
    site_rows: dict[tuple[int, int], set[str]] = {}
    for finding in scoped_rom:
        row_id = _planned_rom_row_for(finding)
        actual_rom_subjects[row_id].add(rom_finding_subject(finding).sha256)
        site_rows.setdefault((finding.bank, finding.address), set()).add(row_id)
    audit_shared = {
        digest: disposition
        for digest, disposition in shared_candidate_dispositions.items()
        if PHASE2_AUDIT_PRODUCT in disposition["products"]
    }
    actual_audit_shared: dict[str, tuple[str, ...]] = {}
    for finding in scoped_candidates:
        eligible_rows = tuple(sorted(site_rows[(finding.bank, finding.address)]))
        digest = rom_finding_subject(finding).sha256
        if len(eligible_rows) > 1:
            actual_audit_shared[digest] = eligible_rows
            disposition = audit_shared.get(digest)
            if disposition is None:
                continue
            row_id = disposition["representative_row"]
            assert isinstance(row_id, str)
        else:
            row_id = eligible_rows[0]
        actual_candidate_subjects[row_id].add(rom_finding_subject(finding).sha256)
    missing_shared = sorted(set(actual_audit_shared) - set(audit_shared))
    extra_shared = sorted(set(audit_shared) - set(actual_audit_shared))
    if missing_shared:
        semantic_subject_errors.append(
            f"missing {PHASE2_AUDIT_PRODUCT} shared-candidate disposition(s): "
            f"{missing_shared}"
        )
    if extra_shared:
        semantic_subject_errors.append(
            f"stale or extra {PHASE2_AUDIT_PRODUCT} shared-candidate disposition(s): "
            f"{extra_shared}"
        )
    for digest in sorted(set(actual_audit_shared) & set(audit_shared)):
        if tuple(audit_shared[digest]["eligible_rows"]) != actual_audit_shared[digest]:
            semantic_subject_errors.append(
                f"{PHASE2_AUDIT_PRODUCT} shared candidate {digest} eligible row set changed"
            )
    for row_id in sorted(PHASE2_PLANNED_ROW_IDS):
        actual_source = tuple(sorted(actual_source_subjects[row_id]))
        actual_rom = tuple(sorted(actual_rom_subjects[row_id]))
        actual_candidates = tuple(sorted(actual_candidate_subjects[row_id]))
        if (
            closure_state != "production-closed"
            and actual_source != planned_source_authority[row_id]
        ):
            semantic_subject_errors.append(
                f"{row_id}: source subjects {actual_source} != {planned_source_authority[row_id]}"
            )
        if (
            closure_state != "production-closed"
            and actual_rom != planned_rom_authority[row_id]
        ):
            semantic_subject_errors.append(
                f"{row_id}: ROM subjects {actual_rom} != {planned_rom_authority[row_id]}"
            )
        if (
            closure_state != "production-closed"
            and actual_candidates != planned_candidate_authority[row_id]
        ):
            semantic_subject_errors.append(
                f"{row_id}: ROM candidate subjects {actual_candidates} != "
                f"{planned_candidate_authority[row_id]}"
            )
        if closure_state == "production-closed":
            if actual_source and not planned_source_authority[row_id]:
                semantic_subject_errors.append(
                    f"{row_id}: source subjects authority is empty for a non-empty "
                    "closed row"
                )
            if actual_rom and not planned_rom_authority[row_id]:
                semantic_subject_errors.append(
                    f"{row_id}: ROM subjects authority is empty for a non-empty "
                    "closed row"
                )
            if actual_candidates and not planned_candidate_authority[row_id]:
                semantic_subject_errors.append(
                    f"{row_id}: ROM candidate subjects authority is empty for a "
                    "non-empty closed row"
                )
        unresolved_count = tuple(planned_unresolved_authority.values()).count(row_id)
        has_role_evidence = bool(
            actual_source_subjects[row_id]
            or actual_rom_subjects[row_id]
            or actual_candidate_subjects[row_id]
            or unresolved_count
        )
        if not has_role_evidence and row_id not in planned_only_authority:
            semantic_subject_errors.append(
                f"{row_id}: exact planned row has no row-bound semantic evidence"
            )
    if (
        closure_state != "production-closed"
        and dict(
            sorted(
                (item, _planned_row_for(item.split(":", 1)[0], "control_flow"))
                for item in scoped_unresolved
            )
        )
        != planned_unresolved_authority
    ):
        semantic_subject_errors.append("scoped ROM unresolved dispositions changed")

    if closure_state == "production-closed":
        product_reports = {
            product: discover_phase2_rom_product(root, product)
            for product in (*PRODUCTION_PRODUCTS, PHASE2_AUDIT_PRODUCT)
        }
        for product, product_report in product_reports.items():
            _reject_duplicate_rom_report(product_report, product)
            reviewed_pointer_rows = {
                row.subject.sha256: row.row_id
                for row in assignments.for_product(product).rows
                if row.subject.kind.value == "ROM_FINDING"
            }
            product_source, product_rom = _scoped_product_subjects(
                source_report,
                product_report,
                product=product,
                shared_candidate_dispositions=shared_candidate_dispositions,
                reviewed_pointer_rows=reviewed_pointer_rows,
            )
            expected_subject_rows: dict[str, str] = {}
            for finding in product_source:
                source_root = _source_finding_root(finding)
                assert source_root is not None
                expected_subject_rows[source_finding_subject(finding).sha256] = (
                    _planned_row_for(
                        source_root, finding.category, resource=finding.resource
                    )
                )
            for finding, row_id in product_rom:
                digest = rom_finding_subject(finding).sha256
                previous = expected_subject_rows.setdefault(digest, row_id)
                if previous != row_id:
                    semantic_subject_errors.append(
                        f"{product}: subject {digest} is ambiguously owned by "
                        f"{previous} and {row_id}"
                    )
            hashes = _product_hashes(source_report, product_report)
            try:
                product_assignments = _validate_product_assignment_coverage(
                    assignments,
                    expected_subject_rows,
                    hashes,
                    product=product,
                )
                _validate_audit_assignment_enrichments(
                    product_assignments, writers, scenes, mutations
                )
                matcher = product_assignments.matcher(**hashes, product=product)
                for finding in product_source:
                    matcher.project_source_finding(finding)
                for finding, _ in product_rom:
                    matcher.project_rom_finding(finding)
                matcher.assert_all_consumed()
                assignment_counts[product] = len(product_assignments.rows)
            except (ValueError, StaleDiscoveryAssignmentError) as exc:
                semantic_subject_errors.append(
                    f"{product} assignment closure failed: {exc}"
                )

        debug_report = product_reports[DEBUG_PRODUCT]
        debug_hashes = _product_hashes(source_report, debug_report)
        phase2_rows = {
            row["id"]: row
            for row in authority_rows
            if row["id"] in PHASE2_PLANNED_ROW_IDS
        }
        stale_rows = sorted(
            row_id
            for row_id, row in phase2_rows.items()
            if any(
                row["evidence"][name] != digest for name, digest in debug_hashes.items()
            )
        )
        if stale_rows:
            semantic_subject_errors.append(
                f"production inventory rows have stale debug identities: {stale_rows}"
            )
        semantic_subject_errors.extend(
            _closed_inventory_row_errors(
                authority_rows,
                debug_hashes,
                (root / "pokeyellow_debug.gbc").read_bytes(),
            )
        )
        semantic_subject_errors.extend(
            _closed_concrete_subject_errors(actual_source_subjects)
        )
        semantic_subject_errors.extend(
            _passive_production_contract_errors(source_report)
        )
    inventory_report = (
        discover_phase2_rom_product(root, DEBUG_PRODUCT)
        if closure_state == "production-closed"
        else rom_report
    )
    inventory_rom = tuple(
        finding for finding in inventory_report.findings if finding.root in roots
    )
    discovered_source_sites = {finding.site_key for finding in scoped_source}
    discovered_rom_sites = {finding.site_key for finding in inventory_rom}
    missing_source = sorted(set(source_sites) - discovered_source_sites)
    missing_rom = sorted(set(machine_sites) - discovered_rom_sites)
    # Every configured root must have both a source subject and ROM root-entry subject.
    source_root_names = {
        item.symbol for item in scoped_source if item.mechanism == "configured-root"
    }
    rom_root_names = {
        item.root for item in inventory_rom if item.mechanism == "root-entry"
    }
    missing_roots = sorted(roots - source_root_names | roots - rom_root_names)
    pallet_header = (root / "data/maps/headers/PalletTown.asm").read_text(
        encoding="utf-8"
    )
    route_header = (root / "data/maps/headers/Route1.asm").read_text(encoding="utf-8")
    concrete_slice_ok = (
        "map_header PalletTown, PALLET_TOWN, OVERWORLD" in pallet_header
        and "connection north, Route1, ROUTE_1" in pallet_header
        and "map_header Route1, ROUTE_1, OVERWORLD" in route_header
        and {"PalletTown_h", "Route1_h"} <= source_root_names
        and {"PalletTown_h", "Route1_h"} <= rom_root_names
    )
    yellow_restoration_ok = any(
        item.symbol == "DisplayPartyMenu"
        and item.destination == "PartyMenuInit"
        and item.row_kind == "DIRECTED_EDGE"
        and item.direction
        == (
            "YELLOW_TO_YELLOW"
            if closure_state == "production-closed"
            else "MAP_TO_YELLOW"
        )
        for item in scoped_source
    ) and any(
        item.symbol == "StartMenu_Pokemon.exitMenu"
        and item.destination == "RestoreScreenTilesAndReloadTilePatterns"
        and item.row_kind == "DIRECTED_EDGE"
        and item.direction == "YELLOW_TO_YELLOW"
        for item in scoped_source
    )
    if missing_source or missing_rom or missing_roots or semantic_subject_errors:
        raise Phase2MeasurementError(
            "hostile inventory audit lacks exact evidence: source="
            f"{missing_source}, ROM={missing_rom}, roots={missing_roots}, "
            f"subjects={semantic_subject_errors}"
        )
    if not concrete_slice_ok or not yellow_restoration_ok:
        raise Phase2MeasurementError(
            "passive slice directed source/ROM identity is not exact"
        )
    return {
        "concrete_slice": ["PalletTown_h", "Route1_h", "OVERWORLD", "NORTH"],
        "guard": AUDIT_GUARD,
        "guarded_root_count": len(roots),
        "normal_rom_reachable": True,
        "production_products": list(PRODUCTION_PRODUCTS),
        "diagnostic_product": PHASE2_AUDIT_PRODUCT,
        "product_assignment_counts": assignment_counts,
        "planned_assignment_count": sum(assignment_counts.values()),
        "planned_row_count": len(planned),
        "inventory_state": closure_state,
        "coverage": "SCOPED_DESCENDANT_CLOSURE",
        "rom_candidate_subject_count": len(scoped_candidates),
        "rom_subject_count": len(scoped_rom),
        "rom_unlisted_subject_count": 0,
        "rom_unresolved_disposition_count": len(scoped_unresolved),
        "source_subject_count": len(scoped_source),
        "source_unlisted_subject_count": 0,
    }


def measure(root: Path) -> Phase2Measurement:
    root = root.resolve()
    paths = {
        name: root / name
        for name in (
            "pokeyellow.gbc",
            "pokeyellow.map",
            "pokeyellow.sym",
            "pokeyellow_debug.gbc",
            "pokeyellow_debug.map",
            "pokeyellow_debug.sym",
            "pokeyellow_vc.gbc",
            "pokeyellow_vc.map",
            "pokeyellow_vc.sym",
            "pokeyellow_phase2_audit.gbc",
            "pokeyellow_phase2_audit.map",
            "pokeyellow_phase2_audit.sym",
            DEFINITION_PATH,
            SOURCE_TRANSITION_PATH,
            PLANNED_SUBJECTS_PATH,
            "specs/full-colors/inventory/assignments.json",
            "specs/full-colors/inventory/mutations.json",
            "specs/full-colors/inventory/scenes.json",
            "specs/full-colors/inventory/writers.json",
        )
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise Phase2MeasurementError(
            "missing measurement input(s): " + ", ".join(missing)
        )
    product_sections = {
        product: _parse_sections(paths[f"{artifact}.map"])
        for product, artifact in PRODUCT_ARTIFACTS.items()
    }
    release = product_sections[NORMAL_PRODUCT]
    debug = product_sections[DEBUG_PRODUCT]
    margin = min(
        _stack_margin(paths["pokeyellow.sym"], release),
        _stack_margin(paths["pokeyellow_debug.sym"], debug),
    )
    if margin < MINIMUM_STACK_MARGIN:
        raise Phase2MeasurementError("measured stack margin regressed below minimum")

    ownership = [
        (bank, low, high)
        for (kind, bank), values in debug.items()
        if kind == "WRAMX"
        for low, high, name in values
        if name == "Full Color Ownership State"
    ]
    if (
        len(ownership) != 1
        or ownership[0][2] - ownership[0][1] + 1 != PHASE1_STATE_BYTES
    ):
        raise Phase2MeasurementError(
            "debug link does not preserve the Phase 1 ownership state"
        )
    wbank, _, ownership_end = ownership[0]
    common_wram = _intersection(
        _free(WRAMX_START, WRAMX_END, release.get(("WRAMX", wbank), ())),
        _free(WRAMX_START, WRAMX_END, debug.get(("WRAMX", wbank), ())),
    )
    common_wram = [
        (max(low, ownership_end + 1), high)
        for low, high in common_wram
        if high > ownership_end
    ]

    common_sram = _intersection(
        _free(SRAM_START, SRAM_END, release.get(("SRAM", 3), ())),
        _free(SRAM_START, SRAM_END, debug.get(("SRAM", 3), ())),
    )
    core = [
        (bank, low, high)
        for (kind, bank), values in debug.items()
        if kind == "ROMX"
        for low, high, name in values
        if name == "Full Color Ownership Core"
    ]
    if len(core) != 1:
        raise Phase2MeasurementError("debug link does not define one ownership core")
    _, _, core_end = core[0]
    rom_bank, rom_start, rom_end = _common_linked_pipeline_section(product_sections)
    if not common_wram or not common_sram:
        raise Phase2MeasurementError(
            "release/debug products have no common Phase 2 placement"
        )

    candidates = tuple(
        Phase2Candidate(
            wbank,
            wl,
            wh,
            3,
            sl,
            sh,
            rom_bank,
            rom_start,
            rom_end,
            margin,
            ownership_adjacent=(wl == ownership_end + 1 and rom_start == core_end + 1),
        )
        for wl, wh in common_wram
        for sl, sh in common_sram
    )
    rejected = tuple(
        (f"ROM bank ${bank:02x}", reason)
        for bank, reason in sorted(FORBIDDEN_ROM_BANKS.items())
    )
    definition = load_definition(paths[DEFINITION_PATH])
    return Phase2Measurement(
        {name: _sha(path) for name, path in paths.items()},
        definition,
        definition.classes,
        definition.descriptor_bytes,
        definition.scratch_bytes,
        candidates,
        rejected,
        inventory_audit=audit_phase2_inventory(root),
    )


def generate(root: Path) -> Phase2Decision:
    return select_phase2_representation(measure(root))


def verify_evidence(root: Path, evidence_path: Path) -> Phase2Decision:
    decision = generate(root)
    if evidence_path.read_text(encoding="utf-8") != decision.to_json():
        raise Phase2MeasurementError(
            f"stale or edited Phase 2 representation: regenerate {evidence_path}"
        )
    return decision


def _canonical_pretty(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


@dataclass(frozen=True)
class _AuthorityIdentity:
    device: int
    inode: int
    mode: int
    links: int


@dataclass
class _PublishedAuthority:
    path: Path
    directory_fd: int
    backup_name: str
    backup_fd: int
    backup_identity: _AuthorityIdentity
    backup_sha256: str
    identity: _AuthorityIdentity


def _identity(value: os.stat_result) -> _AuthorityIdentity:
    return _AuthorityIdentity(value.st_dev, value.st_ino, value.st_mode, value.st_nlink)


def _open_directory_without_symlinks(directory: Path) -> int:
    """Open an absolute directory without following any path component."""
    directory = Path(os.path.abspath(directory))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(directory.anchor, flags)
        for component in directory.parts[1:]:
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            finally:
                os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError as exc:
        raise Phase2MeasurementError(
            f"reviewed authority ancestor is unavailable or unsafe: {directory}"
        ) from exc


def _canonical_apply_path(root: Path, path: Path, expected: str, label: str) -> Path:
    root = Path(os.path.abspath(root))
    candidate = path if path.is_absolute() else root / path
    lexical = Path(os.path.abspath(candidate))
    canonical = root / expected
    if lexical != canonical or root not in lexical.parents:
        raise Phase2MeasurementError(f"{label} must be canonical target {expected}")
    root_fd = _open_directory_without_symlinks(root)
    os.close(root_fd)
    parent_fd = _open_directory_without_symlinks(lexical.parent)
    os.close(parent_fd)
    _authority_identity(lexical, label=label)
    return lexical


def _directory_identity(directory: Path, directory_fd: int) -> None:
    reopened_fd: int | None = None
    try:
        reopened_fd = _open_directory_without_symlinks(directory)
        path_stat = os.fstat(reopened_fd)
        fd_stat = os.fstat(directory_fd)
    except (OSError, Phase2MeasurementError) as exc:
        raise Phase2MeasurementError(
            f"cannot validate reviewed authority parent: {directory}"
        ) from exc
    finally:
        if reopened_fd is not None:
            os.close(reopened_fd)
    if not stat.S_ISDIR(path_stat.st_mode) or _identity(path_stat) != _identity(
        fd_stat
    ):
        raise Phase2MeasurementError(
            f"reviewed authority parent changed during apply: {directory}"
        )


def _authority_identity(path: Path, *, label: str) -> _AuthorityIdentity:
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise Phase2MeasurementError(f"{label} is unavailable: {path}") from exc
    if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
        raise Phase2MeasurementError(
            f"{label} must be a regular non-symlink file with one link: {path}"
        )
    return _identity(current)


def _authority_identity_at(
    path: Path, directory_fd: int, expected: _AuthorityIdentity
) -> None:
    try:
        current = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        raise Phase2MeasurementError(
            f"reviewed authority changed during apply: {path}"
        ) from exc
    if _identity(current) != expected or not stat.S_ISREG(current.st_mode):
        raise Phase2MeasurementError(f"reviewed authority changed during apply: {path}")


def _read_authority_at(
    name: str,
    directory_fd: int,
    expected: _AuthorityIdentity,
    *,
    expected_sha256: str | None = None,
    label: str,
) -> tuple[int, bytes]:
    """Open and read one exact regular file relative to a pinned directory."""
    descriptor: int | None = None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
        current = os.fstat(descriptor)
        if _identity(current) != expected or not stat.S_ISREG(current.st_mode):
            raise Phase2MeasurementError(f"{label} changed during apply")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read()
        current = os.fstat(descriptor)
        _authority_identity_at(Path(name), directory_fd, expected)
        digest = hashlib.sha256(payload).hexdigest()
        if (
            _identity(current) != expected
            or not stat.S_ISREG(current.st_mode)
            or (expected_sha256 is not None and digest != expected_sha256)
        ):
            raise Phase2MeasurementError(f"{label} changed during apply")
        return descriptor, payload
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise Phase2MeasurementError(f"{label} changed during apply") from exc
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        raise


def _read_pinned_backup(publication: _PublishedAuthority) -> bytes:
    """Validate and read the exact backup object retained by the transaction."""
    _validate_backup_name(publication)
    try:
        os.lseek(publication.backup_fd, 0, os.SEEK_SET)
        with os.fdopen(publication.backup_fd, "rb", closefd=False) as stream:
            payload = stream.read()
        current = os.fstat(publication.backup_fd)
    except OSError as exc:
        raise Phase2MeasurementError(
            f"reviewed authority backup changed during apply: {publication.path}"
        ) from exc
    _validate_backup_name(publication)
    if (
        _identity(current) != publication.backup_identity
        or not stat.S_ISREG(current.st_mode)
        or hashlib.sha256(payload).hexdigest() != publication.backup_sha256
    ):
        raise Phase2MeasurementError(
            f"reviewed authority backup changed during apply: {publication.path}"
        )
    return payload


def _validate_backup_name(publication: _PublishedAuthority) -> None:
    try:
        _authority_identity_at(
            Path(publication.backup_name),
            publication.directory_fd,
            publication.backup_identity,
        )
    except Phase2MeasurementError as exc:
        raise Phase2MeasurementError(
            f"reviewed authority backup changed during apply: {publication.path}"
        ) from exc


def _unlink_pinned_backup(publication: _PublishedAuthority) -> None:
    """Remove only the name still referring to the pinned backup object."""
    _validate_backup_name(publication)
    os.unlink(publication.backup_name, dir_fd=publication.directory_fd)
    current = os.fstat(publication.backup_fd)
    os.lseek(publication.backup_fd, 0, os.SEEK_SET)
    with os.fdopen(publication.backup_fd, "rb", closefd=False) as stream:
        digest = hashlib.sha256(stream.read()).hexdigest()
    if (
        not stat.S_ISREG(current.st_mode)
        or replace(_identity(current), links=publication.backup_identity.links)
        != publication.backup_identity
        or current.st_nlink != 0
        or digest != publication.backup_sha256
    ):
        raise Phase2MeasurementError(
            f"reviewed authority backup changed during apply: {publication.path}"
        )


def _allocate_temporary(directory_fd: int, path: Path, suffix: str) -> tuple[int, str]:
    for _ in range(128):
        name = f".{path.name}.{secrets.token_hex(12)}.{suffix}"
        try:
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
            return descriptor, name
        except FileExistsError:
            pass
    raise Phase2MeasurementError(
        f"cannot allocate reviewed authority temporary file: {path}"
    )


def _read_pinned_regular_file(root: Path, path: Path, *, label: str) -> bytes:
    root = Path(os.path.abspath(root))
    lexical = Path(os.path.abspath(path))
    if lexical == root or root not in lexical.parents:
        raise Phase2MeasurementError(
            f"{label} must be a regular file inside the repository"
        )
    expected = _authority_identity(lexical, label=label)
    directory_fd = _open_directory_without_symlinks(lexical.parent)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        _directory_identity(lexical.parent, directory_fd)
        descriptor = os.open(lexical.name, flags, dir_fd=directory_fd)
        with os.fdopen(descriptor, "rb") as stream:
            current = os.fstat(stream.fileno())
            if _identity(current) != expected or not stat.S_ISREG(current.st_mode):
                raise Phase2MeasurementError(
                    f"{label} changed while being read: {lexical}"
                )
            return stream.read()
    except OSError as exc:
        raise Phase2MeasurementError(f"{label} is unavailable: {lexical}") from exc
    finally:
        os.close(directory_fd)


def _atomic_replace(
    path: Path,
    payload: bytes,
    expected: _AuthorityIdentity,
    rollback_ledger: list[_PublishedAuthority] | None = None,
) -> _AuthorityIdentity:
    directory_fd = _open_directory_without_symlinks(path.parent)

    temporary_name: str | None = None
    backup_name: str | None = None
    backup_fd: int | None = None
    publication: _PublishedAuthority | None = None
    try:
        _directory_identity(path.parent, directory_fd)
        _authority_identity_at(path, directory_fd, expected)
        original_fd, original_payload = _read_authority_at(
            path.name,
            directory_fd,
            expected,
            label=f"reviewed authority {path}",
        )
        os.close(original_fd)
        original_sha256 = hashlib.sha256(original_payload).hexdigest()
        descriptor, temporary_name = _allocate_temporary(directory_fd, path, "tmp")
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

        # Revalidate both names at the last possible point. Using the pinned
        # directory descriptor means a later parent-path swap cannot redirect
        # the rename, and replacing a symlink or hardlink never follows it.
        _directory_identity(path.parent, directory_fd)
        _authority_identity_at(path, directory_fd, expected)
        backup_descriptor, backup_name = _allocate_temporary(
            directory_fd, path, "rollback"
        )
        os.close(backup_descriptor)
        os.unlink(backup_name, dir_fd=directory_fd)
        os.link(
            path.name,
            backup_name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        linked_expected = replace(expected, links=2)
        _authority_identity_at(path, directory_fd, linked_expected)
        _authority_identity_at(Path(backup_name), directory_fd, linked_expected)
        staged = os.stat(temporary_name, dir_fd=directory_fd, follow_symlinks=False)
        staged_identity = _identity(staged)
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temporary_name = None
        backup_identity = replace(expected, links=1)
        backup_fd, backup_payload = _read_authority_at(
            backup_name,
            directory_fd,
            backup_identity,
            expected_sha256=original_sha256,
            label=f"reviewed authority backup {path}",
        )
        publication = _PublishedAuthority(
            path=path,
            directory_fd=directory_fd,
            backup_name=backup_name,
            backup_fd=backup_fd,
            backup_identity=backup_identity,
            backup_sha256=hashlib.sha256(backup_payload).hexdigest(),
            identity=staged_identity,
        )
        if rollback_ledger is not None:
            rollback_ledger.append(publication)
        current = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        if _identity(current) != staged_identity:
            raise Phase2MeasurementError(
                f"reviewed authority publication was redirected: {path}"
            )
        _directory_identity(path.parent, directory_fd)
        if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
            raise Phase2MeasurementError(
                f"reviewed authority publication was redirected: {path}"
            )
        os.fsync(directory_fd)
        if rollback_ledger is None:
            _finalize_publication(publication)
            backup_name = None
            publication = None
            backup_fd = None
        return _identity(current)
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        if backup_name is not None and publication is None:
            try:
                os.unlink(backup_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        if publication is None:
            if backup_fd is not None:
                try:
                    os.close(backup_fd)
                except OSError:
                    pass
            try:
                os.close(directory_fd)
            except OSError:
                pass


def _restore_publication(publication: _PublishedAuthority) -> _AuthorityIdentity:
    temporary_name: str | None = None
    try:
        backup_payload = _read_pinned_backup(publication)
        _authority_identity_at(
            publication.path, publication.directory_fd, publication.identity
        )
        descriptor, temporary_name = _allocate_temporary(
            publication.directory_fd, publication.path, "restore"
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(backup_payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(
            temporary_name,
            publication.path.name,
            src_dir_fd=publication.directory_fd,
            dst_dir_fd=publication.directory_fd,
        )
        temporary_name = None
        os.fsync(publication.directory_fd)
        restored = os.stat(
            publication.path.name,
            dir_fd=publication.directory_fd,
            follow_symlinks=False,
        )
        restored_identity = _identity(restored)
        restored_fd, restored_payload = _read_authority_at(
            publication.path.name,
            publication.directory_fd,
            restored_identity,
            expected_sha256=publication.backup_sha256,
            label=f"restored reviewed authority {publication.path}",
        )
        os.close(restored_fd)
        if restored_payload != backup_payload:
            raise Phase2MeasurementError(
                f"restored reviewed authority changed during apply: {publication.path}"
            )
        _read_pinned_backup(publication)
        _unlink_pinned_backup(publication)
        return _identity(restored)
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=publication.directory_fd)
            except FileNotFoundError:
                pass
        os.close(publication.backup_fd)
        os.close(publication.directory_fd)


def _validate_publication(publication: _PublishedAuthority) -> None:
    """Prove the published inode remains connected to its public path."""
    _directory_identity(publication.path.parent, publication.directory_fd)
    _authority_identity_at(
        publication.path, publication.directory_fd, publication.identity
    )


def _finalize_publication(publication: _PublishedAuthority) -> None:
    try:
        _validate_publication(publication)
        _read_pinned_backup(publication)
        _validate_publication(publication)
        _unlink_pinned_backup(publication)
        os.fsync(publication.directory_fd)
    finally:
        os.close(publication.backup_fd)
        os.close(publication.directory_fd)


def _git_read(root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", os.fspath(root), *arguments],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition requires its exact Git worktree"
        ) from exc
    return completed.stdout


def _tracked_worktree_paths(root: Path) -> tuple[str, ...]:
    """Return tracked worktree edits while rejecting every staged change."""
    status = _git_read(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=no",
        "--ignore-submodules=none",
    )
    entries = status.split(b"\0")
    index = 0
    dirty_paths: list[str] = []
    while index < len(entries) and entries[index]:
        entry = entries[index]
        index += 1
        if len(entry) < 4 or entry[2:3] != b" ":
            raise Phase2MeasurementError(
                "reviewed Phase 4 transition received invalid Git status"
            )
        state = entry[:2]
        if state[:1] != b" ":
            raise Phase2MeasurementError(
                "reviewed Phase 4 transition requires a clean Git index"
            )
        if b"R" in state or b"C" in state:
            raise Phase2MeasurementError(
                "reviewed Phase 4 transition forbids tracked renames or copies"
            )
        try:
            dirty_paths.append(entry[3:].decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise Phase2MeasurementError(
                "reviewed Phase 4 transition requires UTF-8 tracked paths"
            ) from exc
    return tuple(dirty_paths)


def _normalized_verifier_source(raw_source: bytes) -> bytes:
    """Remove only the transition-digest carrier from the verifier identity."""
    normalized, replacements = _TRANSITION_DIGEST_CARRIER.subn(
        b'REVIEWED_TRANSITION_SHA256 = (\n    "<reviewed-transition-sha256>"\n)',
        raw_source,
    )
    if replacements != 1:
        raise Phase2MeasurementError(
            "reviewed Phase 4 verifier transition-digest carrier changed"
        )
    return normalized


def propose_reviewed_transition_rebind(root: Path) -> dict[str, object]:
    """Propose identity-only rebinding of the existing reviewed transition."""
    root = Path(os.path.abspath(root))
    transition_path = _canonical_apply_path(
        root,
        root / REVIEWED_TRANSITION_PATH,
        REVIEWED_TRANSITION_PATH,
        "reviewed transition authority",
    )
    raw_transition = _read_pinned_regular_file(
        root, transition_path, label="reviewed transition authority"
    )
    try:
        transition = json.loads(raw_transition, object_pairs_hook=_strict_object)
    except json.JSONDecodeError as exc:
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition authority is malformed"
        ) from exc
    if raw_transition != _canonical_pretty(transition):
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition authority is not canonical JSON"
        )
    expected_keys = {
        "allowed_tracked_path_sha256",
        "base_commit",
        "base_tree",
        "reason",
        "schema",
        "subject_transitions",
        "verifier_normalized_sha256",
    }
    if set(transition) != expected_keys or (
        transition.get("schema") != "full-color-phase2-reviewed-transition-v1"
    ):
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition authority is malformed"
        )
    actual_commit = os.fsdecode(
        _git_read(root, "rev-parse", "--verify", "HEAD")
    ).strip()
    actual_tree = os.fsdecode(
        _git_read(root, "rev-parse", "--verify", "HEAD^{tree}")
    ).strip()
    if (
        transition["base_commit"] != actual_commit
        or transition["base_tree"] != actual_tree
    ):
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition base identity changed"
        )

    raw_allowlist = transition["allowed_tracked_path_sha256"]
    if not isinstance(raw_allowlist, dict) or not raw_allowlist:
        raise Phase2MeasurementError(
            "transition.allowed_tracked_path_sha256: expected non-empty object"
        )
    dirty_paths = _tracked_worktree_paths(root)
    unexpected = sorted(set(dirty_paths) - set(raw_allowlist))
    if unexpected:
        raise Phase2MeasurementError(
            "reviewed transition rebind forbids newly modified tracked paths: "
            + ", ".join(unexpected)
        )

    rebound = dict(transition)
    rebound_allowlist: dict[str, list[str]] = {}
    for relative, raw_digests in raw_allowlist.items():
        if not isinstance(relative, str) or not isinstance(raw_digests, list):
            raise Phase2MeasurementError(
                "reviewed Phase 4 transition authority is malformed"
            )
        path = _canonical_apply_path(
            root, root / relative, relative, "allowed tracked path"
        )
        raw_content = _read_pinned_regular_file(
            root, path, label="allowed tracked path"
        )
        digest_content = (
            _normalized_verifier_source(raw_content)
            if relative == VERIFIER_PATH
            else raw_content
        )
        current_digest = hashlib.sha256(digest_content).hexdigest()
        digests = list(raw_digests)
        if current_digest not in digests:
            digests.append(current_digest)
        rebound_allowlist[relative] = digests
        if relative == VERIFIER_PATH:
            rebound["verifier_normalized_sha256"] = current_digest
    rebound["allowed_tracked_path_sha256"] = rebound_allowlist
    return {
        "authority_path": REVIEWED_TRANSITION_PATH,
        "reviewed": False,
        "schema": REVIEWED_TRANSITION_PROPOSAL_SCHEMA,
        "transition": rebound,
    }


def apply_reviewed_transition_rebind(root: Path, proposal_path: Path) -> None:
    """Apply one canonically recomputed, explicitly reviewed identity rebind."""
    root = Path(os.path.abspath(root))
    proposal = Path(os.path.abspath(proposal_path))
    raw_proposal = _read_pinned_regular_file(root, proposal, label="proposal")
    try:
        parsed = json.loads(raw_proposal, object_pairs_hook=_strict_object)
    except json.JSONDecodeError as exc:
        raise Phase2MeasurementError(
            "invalid reviewed-transition rebind proposal"
        ) from exc
    if raw_proposal != _canonical_pretty(parsed):
        raise Phase2MeasurementError(
            "reviewed-transition rebind proposal is not canonical JSON"
        )
    measured = propose_reviewed_transition_rebind(root)
    if parsed != measured:
        raise Phase2MeasurementError(
            "stale or semantically changed reviewed-transition rebind proposal"
        )

    transition_path = _canonical_apply_path(
        root,
        root / REVIEWED_TRANSITION_PATH,
        REVIEWED_TRANSITION_PATH,
        "reviewed transition authority",
    )
    verifier_path = _canonical_apply_path(
        root, root / VERIFIER_PATH, VERIFIER_PATH, "reviewed transition verifier"
    )
    transition_payload = _canonical_pretty(parsed["transition"])
    transition_digest = hashlib.sha256(transition_payload).hexdigest()
    verifier_payload = _read_pinned_regular_file(
        root, verifier_path, label="reviewed transition verifier"
    )
    rebound_verifier, replacements = _TRANSITION_DIGEST_CARRIER.subn(
        f'REVIEWED_TRANSITION_SHA256 = (\n    "{transition_digest}"\n)'.encode(),
        verifier_payload,
    )
    if replacements != 1:
        raise Phase2MeasurementError(
            "reviewed Phase 4 verifier transition-digest carrier changed"
        )

    updates = {
        transition_path: transition_payload,
        verifier_path: rebound_verifier,
    }
    identities = {
        path: _authority_identity(path, label="reviewed authority") for path in updates
    }
    publications: list[_PublishedAuthority] = []
    try:
        for path, payload in updates.items():
            identities[path] = _atomic_replace(
                path, payload, identities[path], publications
            )
        if (
            hashlib.sha256(transition_path.read_bytes()).hexdigest()
            != transition_digest
        ):
            raise Phase2MeasurementError(
                "reviewed transition rebind produced the wrong authority identity"
            )
        if _TRANSITION_DIGEST_CARRIER.search(verifier_path.read_bytes()) is None:
            raise Phase2MeasurementError(
                "reviewed transition rebind produced an invalid digest carrier"
            )
        for publication in publications:
            _validate_publication(publication)
    except Exception:
        for publication in reversed(publications):
            _restore_publication(publication)
        raise
    else:
        for publication in publications:
            _finalize_publication(publication)


def _validate_reviewed_phase4_worktree(
    root: Path, transition: Mapping[str, object]
) -> None:
    expected_keys = {
        "allowed_tracked_path_sha256",
        "base_commit",
        "base_tree",
        "reason",
        "schema",
        "subject_transitions",
        "verifier_normalized_sha256",
    }
    if set(transition) != expected_keys:
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition has unexpected authority fields"
        )
    if transition["schema"] != "full-color-phase2-reviewed-transition-v1":
        raise Phase2MeasurementError("reviewed Phase 4 transition schema changed")
    base_commit = _string(transition["base_commit"], "transition.base_commit")
    base_tree = _string(transition["base_tree"], "transition.base_tree")
    if re.fullmatch(r"[0-9a-f]{40}", base_commit) is None:
        raise Phase2MeasurementError(
            "transition.base_commit: expected full Git object identity"
        )
    if re.fullmatch(r"[0-9a-f]{40}", base_tree) is None:
        raise Phase2MeasurementError(
            "transition.base_tree: expected full Git object identity"
        )

    lexical_root = Path(os.path.abspath(root))
    try:
        real_root = lexical_root.resolve(strict=True)
    except OSError as exc:
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition repository root is unavailable"
        ) from exc
    if real_root != lexical_root:
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition repository root must not use symlinks"
        )
    git_root = Path(
        os.fsdecode(_git_read(lexical_root, "rev-parse", "--show-toplevel")).strip()
    )
    if git_root != lexical_root:
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition requires the canonical repository root"
        )
    actual_commit = os.fsdecode(
        _git_read(lexical_root, "rev-parse", "--verify", "HEAD")
    ).strip()
    actual_tree = os.fsdecode(
        _git_read(lexical_root, "rev-parse", "--verify", "HEAD^{tree}")
    ).strip()
    if actual_commit != base_commit:
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition base commit does not match HEAD"
        )
    if actual_tree != base_tree:
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition base tree does not match HEAD"
        )

    expected_verifier_digest = _string(
        transition["verifier_normalized_sha256"],
        "transition.verifier_normalized_sha256",
    )
    if _SHA256.fullmatch(expected_verifier_digest) is None:
        raise Phase2MeasurementError(
            "transition.verifier_normalized_sha256: expected SHA-256 identity"
        )
    verifier_path = _canonical_apply_path(
        lexical_root,
        lexical_root / VERIFIER_PATH,
        VERIFIER_PATH,
        "reviewed transition verifier",
    )
    verifier_source = _read_pinned_regular_file(
        lexical_root, verifier_path, label="reviewed transition verifier"
    )
    actual_verifier_digest = hashlib.sha256(
        _normalized_verifier_source(verifier_source)
    ).hexdigest()
    if actual_verifier_digest != expected_verifier_digest:
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition verifier source changed"
        )

    raw_allowlist = transition["allowed_tracked_path_sha256"]
    if not isinstance(raw_allowlist, dict) or not raw_allowlist:
        raise Phase2MeasurementError(
            "transition.allowed_tracked_path_sha256: expected non-empty object"
        )
    allowlist: dict[str, frozenset[str]] = {}
    for relative, raw_digests in raw_allowlist.items():
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or "\\" in relative
            or Path(relative).as_posix() != relative
            or any(part in {"", ".", ".."} for part in Path(relative).parts)
        ):
            raise Phase2MeasurementError(
                "reviewed Phase 4 transition contains a non-canonical tracked path"
            )
        if not isinstance(raw_digests, list) or not raw_digests:
            raise Phase2MeasurementError(
                f"transition.allowed_tracked_path_sha256.{relative}: "
                "expected non-empty digest array"
            )
        digests = frozenset(raw_digests)
        if len(digests) != len(raw_digests) or any(
            not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
            for digest in raw_digests
        ):
            raise Phase2MeasurementError(
                f"transition.allowed_tracked_path_sha256.{relative}: "
                "expected unique SHA-256 identities"
            )
        allowlist[relative] = digests

    dirty_paths = _tracked_worktree_paths(lexical_root)

    for relative in dirty_paths:
        expected_digests = allowlist.get(relative)
        if expected_digests is None:
            raise Phase2MeasurementError(
                f"reviewed Phase 4 transition forbids modified tracked path {relative}"
            )
        path = _canonical_apply_path(
            lexical_root, lexical_root / relative, relative, "allowed tracked path"
        )
        raw_content = _read_pinned_regular_file(
            lexical_root, path, label="allowed tracked path"
        )
        digest_content = (
            _normalized_verifier_source(raw_content)
            if relative == VERIFIER_PATH
            else raw_content
        )
        actual_digest = hashlib.sha256(digest_content).hexdigest()
        if actual_digest not in expected_digests:
            raise Phase2MeasurementError(
                f"reviewed Phase 4 transition tracked path content changed: {relative}"
            )


def apply_reviewed_subject_proposal(
    root: Path, proposal_path: Path, target: Path
) -> None:
    """Install only exact measured subject rebindings into the planned authority."""
    root = Path(os.path.abspath(root))
    target = _canonical_apply_path(root, target, PLANNED_SUBJECTS_PATH, "target")
    proposal = Path(os.path.abspath(proposal_path))
    try:
        raw_proposal = _read_pinned_regular_file(root, proposal, label="proposal")
        parsed = json.loads(raw_proposal, object_pairs_hook=_strict_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase2MeasurementError("invalid Phase 2 subject proposal") from exc
    if raw_proposal != _canonical_pretty(parsed):
        raise Phase2MeasurementError("Phase 2 subject proposal is not canonical JSON")
    measured = propose_phase2_subjects(root)
    if parsed != measured:
        raise Phase2MeasurementError(
            "stale or semantically changed Phase 2 subject proposal"
        )

    old = json.loads(
        target.read_text(encoding="utf-8"), object_pairs_hook=_strict_object
    )
    _load_planned_subjects(root, closed=True)
    assignment_path = _canonical_apply_path(
        root,
        root / "specs/full-colors/inventory/assignments.json",
        "specs/full-colors/inventory/assignments.json",
        "assignment authority",
    )
    DiscoveryAssignmentAuthority.load(assignment_path)
    assignment_document = json.loads(assignment_path.read_text(encoding="utf-8"))
    assignment_rows = assignment_document["rows"]
    row_ids = tuple(old["source_subjects"])
    reviewed_phase4_transition = (
        hashlib.sha256(assignment_path.read_bytes()).hexdigest()
        == "2305a913d02621b869279e5188dc1ee826638c94db3ad7665e75030e2f5a094b"
        and hashlib.sha256(target.read_bytes()).hexdigest()
        == "7555a490ca771a2717eeef2930dfc09f1109a6d7764ddb2544a89b9bb126cf94"
    )
    reviewed_subject_transitions: Mapping[str, str] = {}
    if reviewed_phase4_transition:
        transition_path = _canonical_apply_path(
            root,
            root / REVIEWED_TRANSITION_PATH,
            REVIEWED_TRANSITION_PATH,
            "reviewed transition authority",
        )
        raw_transition = _read_pinned_regular_file(
            root, transition_path, label="reviewed transition authority"
        )
        if hashlib.sha256(raw_transition).hexdigest() != REVIEWED_TRANSITION_SHA256:
            raise Phase2MeasurementError(
                "reviewed Phase 4 transition authority changed"
            )
        transition = json.loads(raw_transition, object_pairs_hook=_strict_object)
        if raw_transition != _canonical_pretty(transition):
            raise Phase2MeasurementError(
                "reviewed Phase 4 transition authority is not canonical JSON"
            )
        _validate_reviewed_phase4_worktree(root, transition)
        reviewed_subject_transitions = transition["subject_transitions"]

    def direct_rom_row(subject: Mapping[str, object]) -> str:
        metadata = subject["metadata"]
        assert isinstance(metadata, Mapping)
        root_name = metadata["root"]
        if (
            isinstance(root_name, str)
            and root_name.startswith("PassiveFullColor")
            and metadata["resource"] == "UNKNOWN_DESTINATION"
            and metadata["mechanism"] == "pointer"
        ):
            return "WR-P2-YELLOW-OVERLAY-TRANSFER"
        assert isinstance(root_name, str)
        return _planned_row_for(
            root_name, metadata["category"], resource=metadata.get("resource")
        )

    proposed_rom_rows: dict[tuple[str, str], str] = {}
    for product_name, product in parsed["products"].items():
        site_rows: dict[tuple[int, int], set[str]] = {}
        for subject in product["rom_subjects"]:
            metadata = subject["metadata"]
            row_id = direct_rom_row(subject)
            proposed_rom_rows[(product_name, subject["sha256"])] = row_id
            site_rows.setdefault((metadata["bank"], metadata["address"]), set()).add(
                row_id
            )
        reviewed_shared_rows = {
            tuple(item["eligible_rows"]): item["representative_row"]
            for item in old["shared_candidate_dispositions"].values()
        }
        for subject in product["rom_candidate_subjects"]:
            metadata = subject["metadata"]
            eligible = tuple(sorted(site_rows[(metadata["bank"], metadata["address"])]))
            row_id = (
                eligible[0]
                if len(eligible) == 1
                else reviewed_shared_rows.get(eligible)
            )
            if row_id is None:
                raise Phase2MeasurementError("proposal changed candidate row semantics")
            proposed_rom_rows[(product_name, subject["sha256"])] = row_id

    def fixed_rom_signature(subject: Mapping[str, object]) -> bytes:
        metadata = dict(subject["metadata"])
        for field_name in ("address", "call_path", "rom_offset"):
            metadata.pop(field_name, None)
        if reviewed_phase4_transition:
            # Phase 4 inserts reviewed bank-$3b data before existing code. Calls
            # and jumps therefore re-encode their operands while preserving
            # opcode, root, mechanism, category, and resource semantics. The
            # complete five-file before/after digests below make this relaxation
            # usable for exactly that one reviewed promotion.
            for field_name in ("bytes", "destination_high", "destination_low"):
                metadata.pop(field_name, None)
        return json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()

    def known_relocation(
        old_subject: Mapping[str, object], new_subject: Mapping[str, object]
    ) -> bool:
        old_metadata = old_subject["metadata"]
        new_metadata = new_subject["metadata"]
        assert isinstance(old_metadata, Mapping)
        assert isinstance(new_metadata, Mapping)
        if fixed_rom_signature(old_subject) != fixed_rom_signature(new_subject):
            return False

        old_site = (
            old_metadata["bank"],
            old_metadata["address"],
            old_metadata["bytes"],
        )
        old_address = old_metadata["address"]
        new_address = new_metadata["address"]
        assert isinstance(old_address, int)
        assert isinstance(new_address, int)
        site_delta = new_address - old_address
        if reviewed_phase4_transition:
            if old_metadata["bank"] != new_metadata["bank"]:
                return False
            if site_delta not in {0, 0x640, 0x642, 0x648, 0x780}:
                return False
            old_bytes = old_metadata["bytes"]
            new_bytes = new_metadata["bytes"]
            if not isinstance(old_bytes, str) or not isinstance(new_bytes, str):
                return False
            if old_bytes != new_bytes and old_bytes[:2] != new_bytes[:2]:
                return False
            for bound in ("destination_low", "destination_high"):
                old_bound = old_metadata[bound]
                new_bound = new_metadata[bound]
                if (old_bound is None) != (new_bound is None):
                    return False
            old_offset = old_metadata["rom_offset"]
            new_offset = new_metadata["rom_offset"]
            if not isinstance(old_offset, int) or not isinstance(new_offset, int):
                return False
            return new_offset - old_offset == site_delta
        if old_site in _PREVIOUS_PASSIVE_ROM_POINTER_WRITES:
            expected_address = old_address + (
                _PASSIVE_ROM_POINTER_REBASE_BYTES
                if old_metadata["bytes"] == "12"
                else 0
            )
            if new_address != expected_address:
                return False
            allowed_ancestor_deltas = {0, site_delta}
        elif site_delta == 0:
            allowed_ancestor_deltas = {0}
        else:
            return False

        old_offset = old_metadata["rom_offset"]
        new_offset = new_metadata["rom_offset"]
        if not isinstance(old_offset, int) or not isinstance(new_offset, int):
            return old_offset == new_offset
        if new_offset - old_offset != site_delta:
            return False

        old_path = old_metadata["call_path"]
        new_path = new_metadata["call_path"]
        if not isinstance(old_path, list) or not isinstance(new_path, list):
            return old_path == new_path
        # The previous discovery authority retained the terminal $2987 node
        # twice while walking the unresolved pointer at $2989.  Collapsing that
        # immediately repeated traversal node changes neither the site nor its
        # ancestry.  Bind this reviewed correction to the exact old/new
        # canonical subjects; every other call-path change remains forbidden.
        reviewed_call_path_transition = {
            "da2e53db737f57469c85f1ce9bb64f643107438368e53e7d265a903b6a24df5d": "e52103989f15f43acb345d412ad4291290b8479d3e9137f6fb3d982c823f46d9"
        }
        if (
            reviewed_call_path_transition.get(old_subject["sha256"])
            == new_subject["sha256"]
        ):
            return True
        if len(old_path) != len(new_path):
            return False
        for old_step, new_step in zip(old_path, new_path, strict=True):
            if old_step == new_step:
                continue
            if not isinstance(old_step, str) or not isinstance(new_step, str):
                return False
            old_match = re.fullmatch(r"([0-9a-f]{2}):([0-9a-f]{4})", old_step)
            new_match = re.fullmatch(r"([0-9a-f]{2}):([0-9a-f]{4})", new_step)
            if old_match is None or new_match is None or old_match[1] != new_match[1]:
                return False
            ancestor_delta = int(new_match[2], 16) - int(old_match[2], 16)
            if ancestor_delta not in allowed_ancestor_deltas:
                return False
        return True

    old_groups: dict[tuple[str, str, bytes], list[dict[str, object]]] = {}
    for assignment in assignment_rows:
        if (
            assignment["row_id"] not in row_ids
            or assignment["subject"]["kind"] != "ROM_FINDING"
        ):
            continue
        key = (
            assignment["product"],
            assignment["row_id"],
            fixed_rom_signature(assignment["subject"]),
        )
        old_groups.setdefault(key, []).append(assignment)
    new_groups: dict[tuple[str, str, bytes], list[dict[str, object]]] = {}
    for product_name, product in parsed["products"].items():
        for subject in (*product["rom_subjects"], *product["rom_candidate_subjects"]):
            key = (
                product_name,
                proposed_rom_rows[(product_name, subject["sha256"])],
                fixed_rom_signature(subject),
            )
            new_groups.setdefault(key, []).append(subject)
    if set(old_groups) != set(new_groups) or any(
        len(old_groups[key]) != len(new_groups[key]) for key in old_groups
    ):
        raise Phase2MeasurementError("proposal changed reviewed ROM subject semantics")
    for key, old_group in old_groups.items():
        remaining = list(new_groups[key])
        for assignment in old_group:
            if reviewed_phase4_transition:
                expected_digest = reviewed_subject_transitions.get(
                    assignment["id"], assignment["subject"]["sha256"]
                )
                matches = [
                    subject
                    for subject in remaining
                    if subject["sha256"] == expected_digest
                    and known_relocation(assignment["subject"], subject)
                ]
            else:
                matches = [
                    subject
                    for subject in remaining
                    if known_relocation(assignment["subject"], subject)
                ]
            if len(matches) != 1:
                raise Phase2MeasurementError(
                    "proposal changed reviewed ROM subject semantics"
                )
            subject = matches[0]
            remaining.remove(subject)
            assignment["subject"] = subject
    if reviewed_phase4_transition:
        proposed_source_by_digest = {
            subject["sha256"]: subject for subject in parsed["source_subjects"]
        }
        for assignment in assignment_rows:
            if (
                assignment["row_id"] not in row_ids
                or assignment["subject"]["kind"] != "SOURCE_FINDING"
            ):
                continue
            expected_digest = reviewed_subject_transitions.get(
                assignment["id"], assignment["subject"]["sha256"]
            )
            try:
                assignment["subject"] = proposed_source_by_digest[expected_digest]
            except KeyError as exc:
                raise Phase2MeasurementError(
                    "reviewed Phase 4 source transition is absent from the proposal"
                ) from exc
    for assignment in assignment_rows:
        product_name = assignment["product"]
        if product_name in parsed["products"]:
            assignment["evidence"].update(parsed["products"][product_name]["hashes"])
        elif (
            reviewed_phase4_transition
            and product_name == BASELINE_PRODUCT
            and assignment["row_id"] in _PHASE4_BASELINE_EVIDENCE_ROWS
        ):
            assignment["evidence"].update(parsed["products"][DEBUG_PRODUCT]["hashes"])
    assignment_authority = DiscoveryAssignmentAuthority.from_dict(assignment_document)

    inventory_documents: dict[Path, dict[str, object]] = {}
    debug_subjects_by_row: dict[str, list[dict[str, object]]] = {
        row_id: [] for row_id in row_ids
    }
    for subject in parsed["products"][DEBUG_PRODUCT]["rom_subjects"]:
        debug_subjects_by_row[
            proposed_rom_rows[(DEBUG_PRODUCT, subject["sha256"])]
        ].append(subject)
    debug_hashes = parsed["products"][DEBUG_PRODUCT]["hashes"]
    for filename in ("writers.json", "scenes.json", "mutations.json"):
        relative_inventory = f"specs/full-colors/inventory/{filename}"
        inventory_path = _canonical_apply_path(
            root,
            root / relative_inventory,
            relative_inventory,
            "inventory authority",
        )
        document = json.loads(inventory_path.read_text(encoding="utf-8"))
        for row in document["rows"]:
            row_id = row["id"]
            if row_id not in row_ids:
                if (
                    reviewed_phase4_transition
                    and row_id in _PHASE4_BASELINE_EVIDENCE_ROWS
                ):
                    row["evidence"].update(debug_hashes)
                continue
            row["evidence"].update(debug_hashes)
            for site in row.get("machine_sites", ()):
                candidates = [
                    subject
                    for subject in debug_subjects_by_row[row_id]
                    if subject["metadata"]["bank"] == site["bank"]
                    and subject["metadata"]["address"]
                    in (
                        site["address"],
                        site["address"] + _TRANSPORT_SPECIAL_PAYLOAD_BYTES,
                        site["address"]
                        + _TRANSPORT_SPECIAL_PAYLOAD_BYTES
                        + _ALL_TILESET_POINTER_EXPANSION_BYTES,
                        site["address"] + _PHASE4_BANK3B_CODE_REBASE_BYTES,
                        site["address"] + _PHASE4_BANK3B_CODE_REBASE_BYTES + 2,
                        site["address"] + _PHASE4_BANK3B_CODE_REBASE_BYTES + 8,
                        site["address"] + _PASSIVE_ROM_POINTER_REBASE_BYTES,
                    )
                ]
                if len(candidates) != 1:
                    exact_bytes = [
                        subject
                        for subject in candidates
                        if subject["metadata"]["bytes"] == site["bytes"]
                    ]
                    candidates = exact_bytes
                site_values = {
                    tuple(
                        subject["metadata"][field_name]
                        for field_name in (
                            "address",
                            "bank",
                            "bytes",
                            "rom_offset",
                            "runtime_copy",
                        )
                    )
                    for subject in candidates
                }
                if len(site_values) == 1:
                    candidates = candidates[:1]
                if len(candidates) != 1:
                    raise Phase2MeasurementError(
                        f"proposal cannot uniquely rebind machine site {row_id} "
                        f"{site['bank']:02x}:{site['address']:04x}"
                    )
                metadata = candidates[0]["metadata"]
                for field_name in (
                    "address",
                    "bank",
                    "bytes",
                    "rom_offset",
                    "runtime_copy",
                ):
                    site[field_name] = metadata[field_name]
        inventory_documents[inventory_path] = document

    row_for_digest: dict[str, str] = {}
    for assignment in assignment_rows:
        digest = assignment["subject"]["sha256"]
        row_id = assignment["row_id"]
        if row_id not in row_ids:
            continue
        prior = row_for_digest.setdefault(digest, row_id)
        if prior != row_id:
            raise Phase2MeasurementError("reviewed assignments disagree on subject row")

    def reviewed_row(subject: Mapping[str, object], kind: str) -> str:
        digest = subject["sha256"]
        assert isinstance(digest, str)
        if digest in row_for_digest:
            return row_for_digest[digest]
        metadata = subject["metadata"]
        assert isinstance(metadata, Mapping)
        if (
            kind.startswith("rom_")
            and metadata["root"].startswith("PassiveFullColor")
            and metadata["resource"] == "UNKNOWN_DESTINATION"
            and metadata["mechanism"] == "pointer"
        ):
            return "WR-P2-YELLOW-OVERLAY-TRANSFER"
        try:
            return _planned_row_for(
                metadata["root"],
                metadata["category"],
                resource=metadata.get("resource"),
            )
        except Phase2MeasurementError as exc:
            raise Phase2MeasurementError(
                f"proposal contains an unreviewed {kind} subject: {digest}"
            ) from exc

    rebound = {key: [] for key in row_ids}
    for subject in parsed["source_subjects"]:
        digest = subject["sha256"]
        rebound[reviewed_row(subject, "source")].append(digest)
    new = dict(old)
    new["source_subjects"] = {row: sorted(set(rebound[row])) for row in row_ids}

    rebound = {key: [] for key in row_ids}
    audit_product = parsed["products"][PHASE2_AUDIT_PRODUCT]
    for subject in audit_product["rom_subjects"]:
        digest = subject["sha256"]
        rebound[reviewed_row(subject, "rom_subjects")].append(digest)
    new["rom_subjects"] = {row: sorted(set(rebound[row])) for row in row_ids}

    reviewed_shared_rows: dict[tuple[str, ...], str] = {}
    for disposition in old["shared_candidate_dispositions"].values():
        eligible = tuple(disposition["eligible_rows"])
        representative = disposition["representative_row"]
        prior = reviewed_shared_rows.setdefault(eligible, representative)
        if prior != representative:
            raise Phase2MeasurementError(
                "existing shared candidate review is ambiguous"
            )

    candidate_rows: dict[tuple[str, str], tuple[tuple[str, ...], str]] = {}
    rebound = {key: [] for key in row_ids}
    for product_name, product in parsed["products"].items():
        site_rows: dict[tuple[int, int], set[str]] = {}
        for subject in product["rom_subjects"]:
            metadata = subject["metadata"]
            site = (metadata["bank"], metadata["address"])
            site_rows.setdefault(site, set()).add(reviewed_row(subject, "rom_subjects"))
        for subject in product["rom_candidate_subjects"]:
            metadata = subject["metadata"]
            eligible = tuple(
                sorted(site_rows.get((metadata["bank"], metadata["address"]), ()))
            )
            if not eligible:
                raise Phase2MeasurementError(
                    "candidate has no reviewed finding at its site"
                )
            representative = (
                eligible[0]
                if len(eligible) == 1
                else reviewed_shared_rows.get(eligible)
            )
            if representative is None:
                raise Phase2MeasurementError("candidate changed shared row semantics")
            digest = subject["sha256"]
            candidate_rows[(product_name, digest)] = (eligible, representative)
            if product_name == PHASE2_AUDIT_PRODUCT:
                rebound[representative].append(digest)
    new["rom_candidate_subjects"] = {row: sorted(set(rebound[row])) for row in row_ids}

    # Shared candidate review decisions keep their exact row/product meaning;
    # only the canonical subject digest may follow the measured relocation.
    shared: dict[str, dict[str, object]] = {}
    for product_name, product in parsed["products"].items():
        site_rows: dict[tuple[int, int], set[str]] = {}
        for subject in product["rom_subjects"]:
            metadata = subject["metadata"]
            site = (metadata["bank"], metadata["address"])
            site_rows.setdefault(site, set()).add(reviewed_row(subject, "rom_subjects"))
        for subject in product["rom_candidate_subjects"]:
            metadata = subject["metadata"]
            eligible = tuple(
                sorted(site_rows.get((metadata["bank"], metadata["address"]), ()))
            )
            if len(eligible) < 2:
                continue
            digest = subject["sha256"]
            representative = candidate_rows[(product_name, digest)][1]
            disposition = shared.setdefault(
                digest,
                {
                    "disposition": "REVIEWED_SHARED_SITE_REPRESENTATIVE",
                    "eligible_rows": list(eligible),
                    "products": [],
                    "representative_row": representative,
                    "reviewed": True,
                    "reviewer": "pr-15-inventory-review",
                },
            )
            if (
                disposition["eligible_rows"] != list(eligible)
                or disposition["representative_row"] != representative
            ):
                raise Phase2MeasurementError(
                    "shared candidate semantics changed across products"
                )
            disposition["products"].append(product_name)
    new["shared_candidate_dispositions"] = dict(sorted(shared.items()))

    counts = dict(old["authority_counts"])
    for key in ("source_subjects", "rom_subjects", "rom_candidate_subjects"):
        by_row = {row: len(new[key][row]) for row in row_ids}
        counts[key] = {"by_row": by_row, "total": sum(by_row.values())}
    shared_by_row = {row: 0 for row in row_ids}
    for disposition in shared.values():
        shared_by_row[disposition["representative_row"]] += 1
    counts["shared_candidate_dispositions"] = {
        "by_representative_row": shared_by_row,
        "product_bindings": sum(len(item["products"]) for item in shared.values()),
        "total": len(shared),
    }
    new["authority_counts"] = counts

    for key in (
        "schema",
        "source_error_subjects",
        "source_error_disposition",
        "rom_unresolved_dispositions",
        "planned_only_dispositions",
    ):
        if new[key] != old[key]:
            raise Phase2MeasurementError(f"proposal changed structural authority {key}")
    for key, value in counts.items():
        if value != old["authority_counts"][key]:
            raise Phase2MeasurementError(
                f"proposal changed authority counts for {key}: "
                f"expected={old['authority_counts'][key]} actual={value}"
            )
    if {
        (
            tuple(item["eligible_rows"]),
            tuple(item["products"]),
            item["representative_row"],
        )
        for item in shared.values()
    } != {
        (
            tuple(item["eligible_rows"]),
            tuple(item["products"]),
            item["representative_row"],
        )
        for item in old["shared_candidate_dispositions"].values()
    }:
        raise Phase2MeasurementError("proposal changed shared candidate semantics")

    updates = {
        assignment_path: assignment_authority.to_json().encode("utf-8"),
        **{
            path: {
                "writers.json": WriterInventory,
                "scenes.json": SceneInventory,
                "mutations.json": MutationInventory,
            }[path.name]
            .from_dict(document)
            .to_json()
            .encode("utf-8")
            for path, document in inventory_documents.items()
        },
        target: _canonical_pretty(new),
    }
    if reviewed_phase4_transition:
        expected_phase4_outputs = {
            "assignments.json": "529b544025c941b79a5bc41bcb874396b6c0c19559ed97c3a4ee44791786a0a4",
            "writers.json": "f6092ce3ef057526ce977468e2ddf2f52df88bdd79a4534365cf0313a226eba2",
            "scenes.json": "55da69839eaad9877cc6a2a8a459c753cb5ad68ebe599c7c7081c7b9627a6b10",
            "mutations.json": "e078124cafc8023ba65e0a06fdee5c05a3518cdb2f0a399848baf8c5394e2c67",
            "phase2-planned-subjects.json": "5d9f4e80713fbb38346e13d617d906febf352e60312f83e4a7a30d3515d26df5",
        }
        actual_digests = {
            path.name: hashlib.sha256(payload).hexdigest()
            for path, payload in updates.items()
        }
        if actual_digests != expected_phase4_outputs:
            raise Phase2MeasurementError(
                "proposal does not match the exact reviewed Phase 4 authority "
                f"transition: {actual_digests}"
            )
    identities = {
        path: _authority_identity(path, label="reviewed authority") for path in updates
    }
    publications: list[_PublishedAuthority] = []
    try:
        for path, payload in updates.items():
            identities[path] = _atomic_replace(
                path, payload, identities[path], publications
            )
        DiscoveryAssignmentAuthority.load(assignment_path)
        WriterInventory.load(root / "specs/full-colors/inventory/writers.json")
        SceneInventory.load(root / "specs/full-colors/inventory/scenes.json")
        MutationInventory.load(root / "specs/full-colors/inventory/mutations.json")
        _load_planned_subjects(root, closed=True)
        for publication in publications:
            _validate_publication(publication)
    except Exception as exc:
        rollback_errors: list[str] = []
        for publication in reversed(publications):
            try:
                identities[publication.path] = _restore_publication(publication)
            except (OSError, Phase2MeasurementError) as rollback_exc:
                rollback_errors.append(
                    f"{publication.path}: {rollback_exc}; recoverable backup "
                    f"retained as {publication.backup_name} in its pinned parent"
                )
        if rollback_errors:
            raise Phase2MeasurementError(
                "Phase 2 authority transaction failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise Phase2MeasurementError(
            f"Phase 2 authority transaction failed: {exc}; original authorities "
            "restored in their pinned parents; the public namespace remains refused"
        ) from exc
    else:
        finalize_errors: list[str] = []
        for publication in publications:
            try:
                _finalize_publication(publication)
            except (OSError, Phase2MeasurementError) as finalize_exc:
                finalize_errors.append(f"{publication.path}: {finalize_exc}")
        if finalize_errors:
            raise Phase2MeasurementError(
                "Phase 2 authority transaction committed but backup cleanup failed: "
                + "; ".join(finalize_errors)
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    outputs = parser.add_mutually_exclusive_group(required=True)
    outputs.add_argument("--output", type=Path)
    outputs.add_argument("--proposal-output", type=Path)
    outputs.add_argument("--apply-proposal", type=Path)
    outputs.add_argument("--transition-proposal-output", type=Path)
    outputs.add_argument("--apply-transition-proposal", type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--authority-reviewed",
        action="store_true",
        help="confirm human-reviewed authorities before writing accepted evidence",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.apply_transition_proposal is not None:
            if args.verify or not args.authority_reviewed or args.target is not None:
                raise Phase2MeasurementError(
                    "applying a transition proposal requires --authority-reviewed"
                )
            apply_reviewed_transition_rebind(
                root=args.root, proposal_path=args.apply_transition_proposal
            )
        elif args.transition_proposal_output is not None:
            if args.verify or args.authority_reviewed or args.target is not None:
                raise Phase2MeasurementError(
                    "review/verify/target flags do not apply to transition proposals"
                )
            proposal = propose_reviewed_transition_rebind(args.root)
            args.transition_proposal_output.parent.mkdir(parents=True, exist_ok=True)
            args.transition_proposal_output.write_bytes(_canonical_pretty(proposal))
        elif args.apply_proposal is not None:
            if args.verify or not args.authority_reviewed or args.target is None:
                raise Phase2MeasurementError(
                    "applying a proposal requires --authority-reviewed and --target"
                )
            apply_reviewed_subject_proposal(args.root, args.apply_proposal, args.target)
        elif args.proposal_output is not None:
            if args.verify or args.authority_reviewed:
                raise Phase2MeasurementError(
                    "review/verify flags apply only to reviewed evidence, not proposals"
                )
            proposal = propose_phase2_subjects(args.root.resolve())
            args.proposal_output.parent.mkdir(parents=True, exist_ok=True)
            args.proposal_output.write_text(
                json.dumps(proposal, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        elif args.verify:
            if args.authority_reviewed:
                raise Phase2MeasurementError(
                    "--authority-reviewed is not needed for read-only verification"
                )
            assert args.output is not None
            verify_evidence(args.root, args.output)
        else:
            assert args.output is not None
            if not args.authority_reviewed:
                raise Phase2MeasurementError(
                    "writing accepted Phase 2 evidence requires --authority-reviewed "
                    "after human review"
                )
            decision = generate(args.root)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(decision.to_json(), encoding="utf-8")
    except (OSError, Phase2MeasurementError) as exc:
        _parser().error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from types import SimpleNamespace
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
    RejectionSubject,
    SubjectKind,
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
    PlacementError,
    generate as generate_phase1_placement,
    verify_evidence as verify_phase1_placement_evidence,
)
from .rom_discovery import (
    discover_rom_batched,
    load_map,
    load_sym,
    normalize_rom_offset,
)
from . import source_transition as phase1_source_transition
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
    "674229ceef9af05de64c8aad1ff25e0d24330cad5fc8173a09879205cec2b22b"
)
VERIFIER_PATH = "tools/rom_tests/full_color/phase2_measurements.py"
REVIEWED_TRANSITION_EXTENSION_PATH = (
    "specs/full-colors/evidence/phase1-ownership-placement.json"
)
REVIEWED_TRANSITION_EXTENSION_SCHEMA = (
    "full-color-phase2-consumed-transition-extension-v1"
)
PHASE5_RELOCATION_EXTENSION_KEY = "phase5_audit_relocation_extension"
PHASE5_RELOCATION_EXTENSION_SCHEMA = (
    "full-color-phase2-phase5-audit-relocation-extension-v1"
)
PHASE5_RELOCATION_PROPOSAL_SCHEMA = (
    "full-color-phase2-phase5-audit-relocation-proposal-v1"
)
PHASE5_CLOSURE_EXTENSION_KEY = "phase5_audit_closure_extension"
PHASE5_CLOSURE_EXTENSION_SCHEMA = "full-color-phase2-phase5-audit-closure-extension-v1"
PHASE5_CLOSURE_PROPOSAL_SCHEMA = "full-color-phase2-phase5-audit-closure-proposal-v1"
PHASE5_PRODUCT_SPLIT_EXTENSION_KEY = "phase5_audit_product_split_extension"
PHASE5_PRODUCT_SPLIT_EXTENSION_SCHEMA = (
    "full-color-phase2-phase5-audit-product-split-extension-v1"
)
PHASE5_PRODUCT_SPLIT_PROPOSAL_SCHEMA = (
    "full-color-phase2-phase5-audit-product-split-proposal-v1"
)
_TRANSITION_DIGEST_CARRIER = re.compile(
    rb'REVIEWED_TRANSITION_SHA256 = \(\n    "[0-9a-f]{64}"\n\)'
)

_PHASE2_AUDIT_IF = re.compile(
    r"^\s*IF\s+DEF\(PHASE2_AUDIT\)\s*(?:;.*)?$", re.IGNORECASE
)
_PHASE2_AUDIT_IF_NOT = re.compile(
    r"^\s*IF\s+NDEF\(PHASE2_AUDIT\)\s*(?:;.*)?$", re.IGNORECASE
)
_ANY_IF = re.compile(r"^\s*IF(?:DEF|NDEF)?\b", re.IGNORECASE)
_ANY_ELSE = re.compile(r"^\s*ELSE\s*(?:;.*)?$", re.IGNORECASE)
_ANY_ENDC = re.compile(r"^\s*ENDC\s*(?:;.*)?$", re.IGNORECASE)

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
            or not products
            or products != tuple(sorted(set(products)))
            or not set(products) <= set(assignment_products)
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
        expected_audit_rows = (
            (representative,) if PHASE2_AUDIT_PRODUCT in products else ()
        )
        if audit_candidate_rows != expected_audit_rows:
            raise Phase2MeasurementError(
                f"shared_candidate_dispositions.{digest}: audit candidate binding "
                "does not match its declared products"
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
    try:
        control_row, writer_row = PHASE2_ROOT_ROWS[root]
    except KeyError as exc:
        raise Phase2MeasurementError(f"unreviewed Phase 2 root {root}") from exc
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
    "PassiveFullColorVBlank": (("PassiveFullColorVBlank", "3b:545a", "3b:7353"),),
}
_PASSIVE_ROW_POINTER_ROOTS = {
    "PassiveFullColorCommitRedrawRow": (("PassiveFullColorCommitRedrawRow",),),
    "PassiveFullColorVBlank": (("PassiveFullColorVBlank", "3b:545a", "3b:740c"),),
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

# The linked tileset payload region sits between the fixed visible / clear
# stores and the redraw-column / redraw-row routines.  Preserve the prior
# reviewed authority so every relocation remains mechanically auditable.
# The reviewed FOREST/CAVERN predecessor already established a uniform $3c0
# relocation from the original sites. SHIP_PORT/PLATEAU/BEACH_HOUSE add exactly
# three more 64-byte palette plus 256-byte attribute pairs before the passive
# code: another 3 * (64 + 256) = $3c0, for the cumulative exact $780 rebase.
_PASSIVE_ROM_POINTER_REBASE_BYTES = 0x780
_TRANSPORT_SPECIAL_PAYLOAD_BYTES = 3 * (64 + 256)
_ALL_TILESET_POINTER_EXPANSION_BYTES = 2 * 2 * 2
_PHASE4_BANK3B_CODE_REBASE_BYTES = 0x640
# The reviewed roof-region lookup and grouped full-byte override lookup add
# different exact instruction spans before the first column and row stores.
# Keep the affected predecessor sites literal: applying either delta to any
# other pointer write must fail the complete-site comparison below.
_MAP_SEMANTIC_COLUMN_POINTER_REBASE_BYTES = 0xA2
_MAP_SEMANTIC_ROW_POINTER_REBASE_BYTES = 0xB4
_MAP_SEMANTIC_COLUMN_POINTER_SITES = frozenset(
    {
        0x6BD5,
        0x6BD8,
        0x6BDE,
        0x6BE1,
    }
)
_MAP_SEMANTIC_ROW_POINTER_SITES = frozenset(
    {
        0x6C8E,
        0x6C91,
        0x6C97,
        0x6C9A,
    }
)
# Normal/VC, debug, and audit products place the reviewed semantic lookup code
# at different bank-$3b offsets.  These are the only whole-site relocations an
# ordinary subject promotion may accept for PassiveFullColor roots.  The
# subject's bank, semantic signature, opcode, artifact offset, and complete
# call ancestry remain independently checked.
_PHASE4_BASELINE_EVIDENCE_ROWS = frozenset(
    {
        "MU-YELLOW-MAP-VIEW-INITIAL",
        "SC-YELLOW-MAP-ENTRY",
        "WR-YELLOW-LCDC-DISABLE",
        "WR-YELLOW-MAP-VIEW-TILE-COPY",
    }
)
def _passive_pointer_rebase(address: int, opcode: str) -> int:
    if opcode != "12":
        return 0
    if address in _MAP_SEMANTIC_COLUMN_POINTER_SITES:
        return (
            _PASSIVE_ROM_POINTER_REBASE_BYTES
            + _MAP_SEMANTIC_COLUMN_POINTER_REBASE_BYTES
        )
    if address in _MAP_SEMANTIC_ROW_POINTER_SITES:
        return (
            _PASSIVE_ROM_POINTER_REBASE_BYTES
            + _MAP_SEMANTIC_ROW_POINTER_REBASE_BYTES
        )
    return _PASSIVE_ROM_POINTER_REBASE_BYTES


_PHASE4_PASSIVE_ROM_POINTER_WRITES = {
    (bank, address + _passive_pointer_rebase(address, opcode), opcode): roots
    for (bank, address, opcode), roots in _PREVIOUS_PASSIVE_ROM_POINTER_WRITES.items()
}

# Phase 5 remains audit-only, but its linked audit routines move the two clear
# stores earlier and the redraw routines later in bank $3b.  Keep this as a
# second exact predecessor-to-successor layer instead of folding it into the
# reviewed Phase 4 deltas: that preserves both independently reviewable
# relocations and refuses any insertion, deletion, opcode change, or root
# change across the complete 78-site authority.
_PHASE5_CLEAR_POINTER_REBASE_BYTES = -0xAA
_PHASE5_REDRAW_POINTER_REBASE_BYTES = 0x419
_PHASE5_SHARED_CANDIDATE_REBASE_BYTES = -0x18


def _phase5_passive_pointer_rebase(opcode: str) -> int:
    if opcode == "12":
        return _PHASE5_REDRAW_POINTER_REBASE_BYTES
    if opcode in {"22", "72"}:
        return _PHASE5_CLEAR_POINTER_REBASE_BYTES
    raise Phase2MeasurementError(
        f"unreviewed Phase 5 passive pointer opcode: {opcode}"
    )


_PHASE5_CLEAR_ANCESTRY_SITES = frozenset(
    {0x5378, 0x545A, 0x549A, 0x54AD, 0x54BA, 0x54BD, 0x54EC, 0x5513}
)
_PHASE5_REDRAW_ANCESTRY_SITES = frozenset({0x7353, 0x740C})


def _phase5_passive_ancestry_rebase(step: str) -> str:
    match = re.fullmatch(r"3b:([0-9a-f]{4})", step)
    if match is None:
        return step
    address = int(match.group(1), 16)
    if address in _PHASE5_CLEAR_ANCESTRY_SITES:
        delta = _PHASE5_CLEAR_POINTER_REBASE_BYTES
    elif address in _PHASE5_REDRAW_ANCESTRY_SITES:
        delta = _PHASE5_REDRAW_POINTER_REBASE_BYTES
    else:
        raise Phase2MeasurementError(
            f"unreviewed Phase 5 passive pointer ancestry site: {step}"
        )
    return f"3b:{address + delta:04x}"


def _phase5_passive_pointer_roots(
    roots: Mapping[str, Sequence[Sequence[str]]],
) -> dict[str, tuple[tuple[str, ...], ...]]:
    return {
        root: tuple(
            tuple(_phase5_passive_ancestry_rebase(step) for step in call_path)
            for call_path in call_paths
        )
        for root, call_paths in roots.items()
    }


_PASSIVE_ROM_POINTER_WRITES = {
    (
        bank,
        address + _phase5_passive_pointer_rebase(opcode),
        opcode,
    ): _phase5_passive_pointer_roots(roots)
    for (bank, address, opcode), roots in _PHASE4_PASSIVE_ROM_POINTER_WRITES.items()
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
        if row_id == "WR-P2-YELLOW-OVERLAY-TRANSFER":
            if finding.mechanism != "pointer":
                raise Phase2MeasurementError(
                    "unreviewed passive ROM pointer write: "
                    f"{finding.root} {finding.bank:02x}:{finding.address:04x} "
                    f"{finding.bytes} {finding.resource} {finding.mechanism} "
                    f"{finding.call_path}"
                )
            return row_id
        # An audit-only linked relocation changes the subject digest before
        # the retained planned authority is promoted.  Admit that intermediate
        # state only through the complete exact site/root/ancestry authority
        # below; no semantic or row inference is permitted.
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


@lru_cache(maxsize=None)
def _phase2_source_line_products(
    source_path: str, source_sha256: str
) -> tuple[frozenset[str], ...]:
    """Return the exact link-product partition active at every source line.

    Source discovery intentionally parses the authored file once and therefore
    sees both arms of ``IF DEF(PHASE2_AUDIT)``.  Linked ROM discovery is already
    product-specific.  This structural projection gives source evidence the
    same product boundary without pretending that raw-source presence means a
    branch is compiled.
    """
    path = Path(source_path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source_sha256:
        raise Phase2MeasurementError(
            f"conditional source changed while classifying products: {path}"
        )
    production = frozenset(PRODUCTION_PRODUCTS)
    audit = frozenset({PHASE2_AUDIT_PRODUCT})
    all_products = production | audit
    active = all_products
    stack: list[tuple[frozenset[str], str]] = []
    result: list[frozenset[str]] = []
    for number, raw_line in enumerate(raw.decode("utf-8").splitlines(), 1):
        line = raw_line.split(";", 1)[0].rstrip()
        if _PHASE2_AUDIT_IF.match(line):
            stack.append((active, "audit"))
            active &= audit
        elif _PHASE2_AUDIT_IF_NOT.match(line):
            stack.append((active, "production"))
            active &= production
        elif _ANY_IF.match(line):
            stack.append((active, "other"))
        elif _ANY_ELSE.match(line):
            if not stack:
                raise Phase2MeasurementError(
                    f"conditional source has unmatched ELSE: {path}:{number}"
                )
            parent, kind = stack[-1]
            if kind == "audit":
                active = parent & production
                stack[-1] = (parent, "audit-else")
            elif kind == "production":
                active = parent & audit
                stack[-1] = (parent, "production-else")
            elif kind in {"audit-else", "production-else"}:
                raise Phase2MeasurementError(
                    f"conditional source has duplicate ELSE: {path}:{number}"
                )
        elif _ANY_ENDC.match(line):
            if not stack:
                raise Phase2MeasurementError(
                    f"conditional source has unmatched ENDC: {path}:{number}"
                )
            active, _ = stack.pop()
        result.append(active)
    if stack:
        raise Phase2MeasurementError(f"conditional source has unclosed IF: {path}")
    return tuple(result)


def _source_finding_active_for_product(
    root: Path, finding: object, product: str
) -> bool:
    path = root / finding.path
    raw_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    products = _phase2_source_line_products(str(path.resolve()), raw_sha256)
    if finding.line < 1 or finding.line > len(products):
        raise Phase2MeasurementError(
            f"source finding line is outside its file: {finding.path}:{finding.line}"
        )
    return product in products[finding.line - 1]


def _product_source_report(
    root: Path, report: SourceDiscoveryReport, product: str
) -> SourceDiscoveryReport:
    return replace(
        report,
        findings=tuple(
            finding
            for finding in report.findings
            if _source_finding_active_for_product(root, finding, product)
        ),
    )


def _scoped_product_subjects(
    source_report: SourceDiscoveryReport,
    rom_report: object,
    *,
    root: Path | None = None,
    product: str,
    shared_candidate_dispositions: Mapping[str, Mapping[str, object]],
    reviewed_pointer_rows: Mapping[str, str] | None = None,
) -> tuple[tuple[object, ...], tuple[tuple[object, str], ...]]:
    roots = set(_phase2_roots())
    source = tuple(
        finding
        for finding in _product_source_report(
            Path.cwd() if root is None else root, source_report, product
        ).findings
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
                root=root,
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
            _passive_production_contract_errors(
                _product_source_report(root, source_report, DEBUG_PRODUCT)
            )
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
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass
class _PublishedAuthority:
    path: Path
    directory_fd: int
    backup_name: str
    backup_fd: int
    backup_identity: _AuthorityIdentity
    backup_sha256: str
    identity: _AuthorityIdentity
    published_sha256: str


def _identity(value: os.stat_result) -> _AuthorityIdentity:
    return _AuthorityIdentity(
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _same_authority_object(
    current: _AuthorityIdentity,
    previous: _AuthorityIdentity,
    *,
    links: int,
) -> bool:
    """Compare identity across an intentional link-count/ctime mutation."""
    return (
        current.device == previous.device
        and current.inode == previous.inode
        and current.mode == previous.mode
        and current.links == links
        and current.size == previous.size
        and current.mtime_ns == previous.mtime_ns
    )


def _same_authority_inode(
    current: _AuthorityIdentity,
    previous: _AuthorityIdentity,
    *,
    links: int,
) -> bool:
    """Identify the published inode even when hostile content changed."""
    return (
        current.device == previous.device
        and current.inode == previous.inode
        and current.mode == previous.mode
        and current.links == links
    )


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


def _read_pinned_backup(
    publication: _PublishedAuthority, *, allow_unlinked: bool = False
) -> bytes:
    """Validate and read the exact backup object retained by the transaction."""
    try:
        before = os.fstat(publication.backup_fd)
        unlinked = allow_unlinked and before.st_nlink == 0
        if unlinked:
            try:
                os.stat(
                    publication.backup_name,
                    dir_fd=publication.directory_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                raise Phase2MeasurementError(
                    f"reviewed authority backup changed during apply: {publication.path}"
                )
        else:
            _validate_backup_name(publication)
        os.lseek(publication.backup_fd, 0, os.SEEK_SET)
        with os.fdopen(publication.backup_fd, "rb", closefd=False) as stream:
            payload = stream.read()
        current = os.fstat(publication.backup_fd)
    except OSError as exc:
        raise Phase2MeasurementError(
            f"reviewed authority backup changed during apply: {publication.path}"
        ) from exc
    if not unlinked:
        _validate_backup_name(publication)
    if (
        (
            not _same_authority_object(
                _identity(current), publication.backup_identity, links=0
            )
            if unlinked
            else _identity(current) != publication.backup_identity
        )
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
        or not _same_authority_object(
            _identity(current), publication.backup_identity, links=0
        )
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
    *,
    expected_sha256: str | None = None,
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
        if expected_sha256 is not None and original_sha256 != expected_sha256:
            raise Phase2MeasurementError(
                f"reviewed authority predecessor hash changed: {path}"
            )
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
        linked_expected = _identity(
            os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        )
        if not _same_authority_object(linked_expected, expected, links=2):
            raise Phase2MeasurementError(
                f"reviewed authority changed during apply: {path}"
            )
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
        backup_identity = _identity(
            os.stat(backup_name, dir_fd=directory_fd, follow_symlinks=False)
        )
        if not _same_authority_object(backup_identity, linked_expected, links=1):
            raise Phase2MeasurementError(
                f"reviewed authority backup changed during apply: {path}"
            )
        backup_fd, backup_payload = _read_authority_at(
            backup_name,
            directory_fd,
            backup_identity,
            expected_sha256=original_sha256,
            label=f"reviewed authority backup {path}",
        )
        current = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        current_identity = _identity(current)
        if not _same_authority_object(current_identity, staged_identity, links=1):
            raise Phase2MeasurementError(
                f"reviewed authority publication was redirected: {path}"
            )
        publication = _PublishedAuthority(
            path=path,
            directory_fd=directory_fd,
            backup_name=backup_name,
            backup_fd=backup_fd,
            backup_identity=backup_identity,
            backup_sha256=hashlib.sha256(backup_payload).hexdigest(),
            identity=current_identity,
            published_sha256=hashlib.sha256(payload).hexdigest(),
        )
        if rollback_ledger is not None:
            rollback_ledger.append(publication)
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
        backup_payload = _read_pinned_backup(publication, allow_unlinked=True)
        current = _identity(
            os.stat(
                publication.path.name,
                dir_fd=publication.directory_fd,
                follow_symlinks=False,
            )
        )
        if not _same_authority_inode(current, publication.identity, links=1):
            raise Phase2MeasurementError(
                f"reviewed authority changed during apply: {publication.path}"
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
        _read_pinned_backup(publication, allow_unlinked=True)
        if os.fstat(publication.backup_fd).st_nlink != 0:
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
    """Prove the published inode and reviewed bytes remain at the public path."""
    _directory_identity(publication.path.parent, publication.directory_fd)
    _authority_identity_at(
        publication.path, publication.directory_fd, publication.identity
    )
    descriptor, _ = _read_authority_at(
        publication.path.name,
        publication.directory_fd,
        publication.identity,
        expected_sha256=publication.published_sha256,
        label=f"published reviewed authority {publication.path}",
    )
    os.close(descriptor)


def _restore_failed_publication_transaction(
    publications: Sequence[_PublishedAuthority], failure: Exception
) -> None:
    rollback_errors: list[str] = []
    for publication in reversed(publications):
        try:
            _restore_publication(publication)
        except Exception as restore_failure:
            rollback_errors.append(f"{publication.path}: {restore_failure}")
    if rollback_errors:
        raise Phase2MeasurementError(
            "reviewed authority transaction changed before finalize and rollback "
            "failed: " + "; ".join(rollback_errors)
        ) from failure
    raise Phase2MeasurementError(
        "reviewed authority transaction changed before finalize; original authorities "
        "restored"
    ) from failure


def _close_publication_descriptors(
    publications: Sequence[_PublishedAuthority],
) -> None:
    close_errors: list[str] = []
    for publication in publications:
        for label, descriptor in (
            ("backup", publication.backup_fd),
            ("directory", publication.directory_fd),
        ):
            try:
                os.close(descriptor)
            except OSError as exc:
                close_errors.append(f"{publication.path} {label}: {exc}")
                try:
                    os.fstat(descriptor)
                except OSError:
                    continue
                try:
                    os.close(descriptor)
                except OSError as retry_exc:
                    close_errors.append(
                        f"{publication.path} {label} retry: {retry_exc}"
                    )
    if close_errors:
        raise Phase2MeasurementError(
            "reviewed authority transaction committed but descriptor cleanup failed: "
            + "; ".join(close_errors)
        )


def _finalize_publications(publications: Sequence[_PublishedAuthority]) -> None:
    publications = tuple(publications)
    try:
        for publication in publications:
            _validate_publication(publication)
        for publication in publications:
            _read_pinned_backup(publication)
        for publication in publications:
            _validate_publication(publication)
    except Exception as exc:
        _restore_failed_publication_transaction(publications, exc)
    try:
        for publication in publications:
            _unlink_pinned_backup(publication)
        for publication in publications:
            _validate_publication(publication)
        for publication in publications:
            os.fsync(publication.directory_fd)
    except Exception as exc:
        _restore_failed_publication_transaction(publications, exc)
    _close_publication_descriptors(publications)


def _finalize_publication(publication: _PublishedAuthority) -> None:
    _finalize_publications((publication,))


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


def _reviewed_phase1_extension_digest(root: Path) -> str:
    """Return the current canonical Phase 1 evidence identity, or refuse it."""
    relative = REVIEWED_TRANSITION_EXTENSION_PATH
    path = _canonical_apply_path(
        root, root / relative, relative, "reviewed Phase 1 evidence extension"
    )
    raw_evidence = _read_pinned_regular_file(
        root, path, label="reviewed Phase 1 evidence extension"
    )
    try:
        generated = generate_phase1_placement(root)
        expected = generated.to_json().encode("utf-8")
        if raw_evidence != expected:
            raise Phase2MeasurementError(
                "reviewed Phase 1 evidence extension is stale or edited"
            )
        verified = verify_phase1_placement_evidence(root, path)
        if verified != generated:
            raise Phase2MeasurementError(
                "reviewed Phase 1 evidence extension verification changed"
            )
    except (OSError, PlacementError) as exc:
        raise Phase2MeasurementError(
            "reviewed Phase 1 evidence extension is not current for this build"
        ) from exc
    return hashlib.sha256(raw_evidence).hexdigest()


def _reviewed_consumed_extension(
    transition: Mapping[str, object],
) -> tuple[str, str, str]:
    """Load the one path and exact verifier identity reviewed after consumption."""
    extension = transition.get("consumed_extension")
    if not isinstance(extension, Mapping) or set(extension) != {
        "path",
        "predecessor_sha256",
        "schema",
        "successor_sha256",
        "verifier_normalized_sha256",
    }:
        raise Phase2MeasurementError(
            "reviewed transition consumed-extension authority is malformed"
        )
    if extension.get("schema") != REVIEWED_TRANSITION_EXTENSION_SCHEMA:
        raise Phase2MeasurementError(
            "reviewed transition consumed-extension schema changed"
        )
    if extension.get("path") != REVIEWED_TRANSITION_EXTENSION_PATH:
        raise Phase2MeasurementError(
            "reviewed transition consumed-extension path changed"
        )
    verifier_digest = extension.get("verifier_normalized_sha256")
    predecessor_digest = extension.get("predecessor_sha256")
    successor_digest = extension.get("successor_sha256")
    if any(
        not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
        for digest in (predecessor_digest, successor_digest, verifier_digest)
    ) or predecessor_digest == successor_digest:
        raise Phase2MeasurementError(
            "reviewed transition consumed-extension identities changed"
        )
    return predecessor_digest, successor_digest, verifier_digest


def propose_reviewed_transition_rebind(root: Path) -> dict[str, object]:
    """Propose one exact, hash-bound authority promotion transition."""
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
    if hashlib.sha256(raw_transition).hexdigest() != REVIEWED_TRANSITION_SHA256:
        raise Phase2MeasurementError("reviewed transition authority changed")
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
    if not isinstance(transition.get("allowed_tracked_path_sha256"), dict):
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition authority is malformed"
        )
    (
        reviewed_extension_predecessor,
        reviewed_extension_successor,
        reviewed_extension_verifier,
    ) = _reviewed_consumed_extension(transition)
    actual_commit = os.fsdecode(
        _git_read(root, "rev-parse", "--verify", "HEAD")
    ).strip()
    actual_tree = os.fsdecode(
        _git_read(root, "rev-parse", "--verify", "HEAD^{tree}")
    ).strip()
    transition_consumed = actual_commit != transition.get("base_commit")
    raw_allowlist = transition["allowed_tracked_path_sha256"]
    if not isinstance(raw_allowlist, dict) or not raw_allowlist:
        raise Phase2MeasurementError(
            "transition.allowed_tracked_path_sha256: expected non-empty object"
        )
    dirty_paths = _tracked_worktree_paths(root)
    rebound_allowlist: dict[str, list[str]] = {}
    reviewed_paths = set(raw_allowlist)
    if not transition_consumed:
        reviewed_paths.update(dirty_paths)
        reviewed_paths.discard(REVIEWED_TRANSITION_PATH)
    for relative in sorted(reviewed_paths):
        raw_digests = raw_allowlist.get(relative, [])
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
        if (
            not transition_consumed
            and relative not in {REVIEWED_TRANSITION_EXTENSION_PATH, VERIFIER_PATH}
            and current_digest not in digests
        ):
            digests.append(current_digest)
        rebound_allowlist[relative] = digests
    authority_paths = (
        "specs/full-colors/inventory/assignments.json",
        PLANNED_SUBJECTS_PATH,
        "specs/full-colors/inventory/writers.json",
        "specs/full-colors/inventory/scenes.json",
        "specs/full-colors/inventory/mutations.json",
    )
    predecessor_payloads = {
        relative: _git_read(root, "show", f"HEAD:{relative}")
        for relative in authority_paths
    }
    successor_payloads = {
        relative: _read_pinned_regular_file(
            root, root / relative, label=f"successor authority {relative}"
        )
        for relative in authority_paths
    }
    existing_successor_hashes = transition.get("successor_authority_sha256")
    current_authority_hashes = {
        relative: hashlib.sha256(payload).hexdigest()
        for relative, payload in successor_payloads.items()
    }
    if transition_consumed and current_authority_hashes != existing_successor_hashes:
        raise Phase2MeasurementError(
            "reviewed transition successor authority set is partial or changed"
        )

    verifier_digest = hashlib.sha256(
        _normalized_verifier_source(
            _read_pinned_regular_file(
                root, root / VERIFIER_PATH, label="reviewed transition verifier"
            )
        )
    ).hexdigest()
    if verifier_digest != reviewed_extension_verifier:
        raise Phase2MeasurementError(
            "reviewed transition extension forbids verifier source rotation"
        )
    phase1_digests = rebound_allowlist.get(REVIEWED_TRANSITION_EXTENSION_PATH)
    if not isinstance(phase1_digests, list) or not phase1_digests:
        raise Phase2MeasurementError(
            "reviewed transition lacks its Phase 1 evidence extension authority"
        )
    if phase1_digests not in (
        [reviewed_extension_predecessor],
        [reviewed_extension_predecessor, reviewed_extension_successor],
    ):
        raise Phase2MeasurementError(
            "reviewed transition Phase 1 extension is partial or replayed"
        )
    phase1_digest = _reviewed_phase1_extension_digest(root)
    if phase1_digest not in {
        reviewed_extension_predecessor,
        reviewed_extension_successor,
    }:
        raise Phase2MeasurementError(
            "reviewed transition forbids an unreviewed Phase 1 successor"
        )
    if transition_consumed and phase1_digest != reviewed_extension_successor:
        raise Phase2MeasurementError(
            "reviewed transition consumed extension requires its exact successor"
        )
    if (
        phase1_digest == reviewed_extension_successor
        and phase1_digests == [reviewed_extension_predecessor]
    ):
        phase1_digests.append(reviewed_extension_successor)
    verifier_digests = rebound_allowlist.get(VERIFIER_PATH)
    if not isinstance(verifier_digests, list) or not verifier_digests:
        raise Phase2MeasurementError(
            "reviewed transition lacks its verifier authority"
        )
    if verifier_digest not in verifier_digests:
        verifier_digests.append(verifier_digest)
    if transition_consumed:
        allowed_dirty = {
            REVIEWED_TRANSITION_PATH,
            REVIEWED_TRANSITION_EXTENSION_PATH,
            VERIFIER_PATH,
        }
        for relative in dirty_paths:
            if relative in allowed_dirty:
                continue
            raise Phase2MeasurementError(
                "reviewed transition extension forbids modified tracked path "
                f"{relative}"
            )
        rebound = dict(transition)
        rebound["allowed_tracked_path_sha256"] = rebound_allowlist
        rebound["verifier_normalized_sha256"] = verifier_digest
        return {
            "authority_path": REVIEWED_TRANSITION_PATH,
            "reviewed": False,
            "schema": REVIEWED_TRANSITION_PROPOSAL_SCHEMA,
            "transition": rebound,
        }

    predecessor_assignments = json.loads(
        predecessor_payloads[authority_paths[0]], object_pairs_hook=_strict_object
    )
    successor_assignments = json.loads(
        successor_payloads[authority_paths[0]], object_pairs_hook=_strict_object
    )
    old_rows = {row["id"]: row for row in predecessor_assignments["rows"]}
    new_rows = {row["id"]: row for row in successor_assignments["rows"]}
    if set(old_rows) != set(new_rows):
        raise Phase2MeasurementError(
            "reviewed transition forbids assignment namespace changes"
        )
    subject_transitions: dict[str, dict[str, str]] = {}
    for assignment_id in sorted(old_rows):
        old_subject = old_rows[assignment_id]["subject"]
        new_subject = new_rows[assignment_id]["subject"]
        if old_subject == new_subject:
            continue
        if old_subject["kind"] != new_subject["kind"] or old_subject["kind"] not in {
            "ROM_FINDING",
            "SOURCE_FINDING",
        }:
            raise Phase2MeasurementError(
                f"reviewed transition forbids subject kind change: {assignment_id}"
            )
        subject_transitions[assignment_id] = {
            "from_sha256": old_subject["sha256"],
            "to_sha256": new_subject["sha256"],
        }

    inventory_site_transitions: list[dict[str, object]] = []
    for relative in authority_paths[2:]:
        old_document = json.loads(
            predecessor_payloads[relative], object_pairs_hook=_strict_object
        )
        new_document = json.loads(
            successor_payloads[relative], object_pairs_hook=_strict_object
        )
        old_inventory_rows = {row["id"]: row for row in old_document["rows"]}
        new_inventory_rows = {row["id"]: row for row in new_document["rows"]}
        if set(old_inventory_rows) != set(new_inventory_rows):
            raise Phase2MeasurementError(
                "reviewed transition forbids inventory namespace changes"
            )
        for row_id in sorted(old_inventory_rows):
            for site_kind in ("machine_sites", "source_sites"):
                old_sites = old_inventory_rows[row_id].get(site_kind, [])
                new_sites = new_inventory_rows[row_id].get(site_kind, [])
                if len(old_sites) != len(new_sites):
                    raise Phase2MeasurementError(
                        "reviewed transition forbids inventory site count changes"
                    )
                for index, (old_site, new_site) in enumerate(
                    zip(old_sites, new_sites, strict=True)
                ):
                    if old_site != new_site:
                        inventory_site_transitions.append(
                            {
                                "from": old_site,
                                "index": index,
                                "inventory": relative,
                                "row_id": row_id,
                                "site_kind": site_kind,
                                "to": new_site,
                            }
                        )

    rebound = {
        "allowed_tracked_path_sha256": rebound_allowlist,
        "base_commit": actual_commit,
        "base_tree": actual_tree,
        "consumed_extension": transition["consumed_extension"],
        "inventory_site_transitions": inventory_site_transitions,
        "predecessor_authority_sha256": {
            relative: hashlib.sha256(payload).hexdigest()
            for relative, payload in predecessor_payloads.items()
        },
        "reason": (
            "One-time reviewed foundation promotion for exact map-semantic ROM, "
            "source, and inventory-site identity rebinding"
        ),
        "schema": "full-color-phase2-reviewed-transition-v2",
        "subject_transitions": subject_transitions,
        "successor_authority_sha256": {
            relative: hashlib.sha256(payload).hexdigest()
            for relative, payload in successor_payloads.items()
        },
        "verifier_normalized_sha256": verifier_digest,
    }
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
        _finalize_publications(publications)


def _validate_reviewed_phase4_worktree(
    root: Path, transition: Mapping[str, object]
) -> None:
    expected_keys = {
        "allowed_tracked_path_sha256",
        "base_commit",
        "base_tree",
        "consumed_extension",
        "inventory_site_transitions",
        "predecessor_authority_sha256",
        "reason",
        "schema",
        "subject_transitions",
        "successor_authority_sha256",
        "verifier_normalized_sha256",
    }
    if set(transition) != expected_keys:
        raise Phase2MeasurementError(
            "reviewed Phase 4 transition has unexpected authority fields"
        )
    if transition["schema"] != "full-color-phase2-reviewed-transition-v2":
        raise Phase2MeasurementError("reviewed Phase 4 transition schema changed")
    _reviewed_consumed_extension(transition)
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

    dirty_paths = tuple(
        relative
        for relative in _tracked_worktree_paths(lexical_root)
        if relative != REVIEWED_TRANSITION_PATH
    )

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


def _apply_reviewed_inventory_site_transitions(
    inventory_documents: Mapping[Path, dict[str, object]],
    transitions: Sequence[Mapping[str, object]],
) -> None:
    """Apply only authority-listed exact old-to-new inventory sites."""
    documents_by_relative = {
        path.relative_to(path.parents[3]).as_posix(): document
        for path, document in inventory_documents.items()
    }
    seen: set[tuple[str, str, str, int]] = set()
    for transition in transitions:
        if set(transition) != {
            "from",
            "index",
            "inventory",
            "row_id",
            "site_kind",
            "to",
        }:
            raise Phase2MeasurementError("reviewed inventory site transition is malformed")
        inventory = transition["inventory"]
        row_id = transition["row_id"]
        site_kind = transition["site_kind"]
        index = transition["index"]
        if (
            not isinstance(inventory, str)
            or not isinstance(row_id, str)
            or site_kind not in {"machine_sites", "source_sites"}
            or not isinstance(index, int)
            or index < 0
        ):
            raise Phase2MeasurementError("reviewed inventory site transition is malformed")
        identity = (inventory, row_id, site_kind, index)
        if identity in seen:
            raise Phase2MeasurementError("reviewed inventory site transition is duplicated")
        seen.add(identity)
        document = documents_by_relative.get(inventory)
        if document is None:
            raise Phase2MeasurementError(
                f"reviewed inventory site transition lacks {inventory}"
            )
        rows = [row for row in document["rows"] if row["id"] == row_id]
        if len(rows) != 1:
            raise Phase2MeasurementError(
                f"reviewed inventory site transition row changed: {row_id}"
            )
        sites = rows[0].get(site_kind, [])
        if index >= len(sites) or sites[index] != transition["from"]:
            raise Phase2MeasurementError(
                "reviewed inventory site predecessor identity changed: "
                f"{inventory}:{row_id}:{site_kind}:{index}"
            )
        sites[index] = transition["to"]


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
        raise Phase2MeasurementError("reviewed transition authority changed")
    transition = json.loads(raw_transition, object_pairs_hook=_strict_object)
    if raw_transition != _canonical_pretty(transition):
        raise Phase2MeasurementError(
            "reviewed transition authority is not canonical JSON"
        )
    predecessor_hashes = transition.get("predecessor_authority_sha256")
    successor_hashes = transition.get("successor_authority_sha256")
    if not isinstance(predecessor_hashes, dict) or not isinstance(
        successor_hashes, dict
    ) or set(predecessor_hashes) != set(successor_hashes):
        raise Phase2MeasurementError("reviewed transition authority is malformed")
    current_authority_hashes = {
        relative: hashlib.sha256(
            _read_pinned_regular_file(
                root, root / relative, label=f"transition authority {relative}"
            )
        ).hexdigest()
        for relative in predecessor_hashes
    }
    predecessor_matches = {
        relative
        for relative, digest in current_authority_hashes.items()
        if digest == predecessor_hashes[relative]
    }
    if predecessor_matches and predecessor_matches != set(predecessor_hashes):
        raise Phase2MeasurementError(
            "reviewed transition predecessor authority set is partial or changed"
        )
    reviewed_transition_active = predecessor_matches == set(predecessor_hashes)
    if reviewed_transition_active:
        _validate_reviewed_phase4_worktree(root, transition)
    reviewed_subject_transitions = transition.get("subject_transitions")
    if not isinstance(reviewed_subject_transitions, dict):
        raise Phase2MeasurementError("reviewed transition subject authority changed")

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

    proposed_rom_by_product_digest: dict[tuple[str, str], Mapping[str, object]] = {}
    for product_name, product in parsed["products"].items():
        for subject in (*product["rom_subjects"], *product["rom_candidate_subjects"]):
            key = (product_name, subject["sha256"])
            if key in proposed_rom_by_product_digest:
                raise Phase2MeasurementError("proposal contains duplicate ROM identity")
            proposed_rom_by_product_digest[key] = subject
    proposed_source_by_digest = {
        subject["sha256"]: subject for subject in parsed["source_subjects"]
    }
    consumed_transitions: set[str] = set()
    for assignment in assignment_rows:
        old_subject = assignment["subject"]
        if assignment["row_id"] not in row_ids or old_subject["kind"] not in {
            "ROM_FINDING",
            "SOURCE_FINDING",
        }:
            continue
        expected_digest = old_subject["sha256"]
        binding = reviewed_subject_transitions.get(assignment["id"])
        if reviewed_transition_active and binding is not None:
            if (
                not isinstance(binding, dict)
                or set(binding) != {"from_sha256", "to_sha256"}
                or binding["from_sha256"] != old_subject["sha256"]
                or any(
                    not isinstance(value, str) or _SHA256.fullmatch(value) is None
                    for value in binding.values()
                )
            ):
                raise Phase2MeasurementError(
                    f"reviewed transition predecessor changed: {assignment['id']}"
                )
            expected_digest = binding["to_sha256"]
            consumed_transitions.add(assignment["id"])
        if old_subject["kind"] == "ROM_FINDING":
            subject = proposed_rom_by_product_digest.get(
                (assignment["product"], expected_digest)
            )
            if subject is not None and proposed_rom_rows.get(
                (assignment["product"], expected_digest)
            ) != assignment["row_id"]:
                raise Phase2MeasurementError(
                    f"reviewed ROM transition crossed rows: {assignment['id']}"
                )
        else:
            subject = proposed_source_by_digest.get(expected_digest)
        if subject is None:
            raise Phase2MeasurementError(
                f"proposal lacks exact reviewed subject identity: {assignment['id']}"
            )
        assignment["subject"] = subject
    if reviewed_transition_active and consumed_transitions != set(
        reviewed_subject_transitions
    ):
        raise Phase2MeasurementError(
            "reviewed transition contains stale or cross-subject bindings"
        )
    for assignment in assignment_rows:
        product_name = assignment["product"]
        if product_name in parsed["products"]:
            assignment["evidence"].update(parsed["products"][product_name]["hashes"])
        elif (
            reviewed_transition_active
            and product_name == BASELINE_PRODUCT
            and assignment["row_id"] in _PHASE4_BASELINE_EVIDENCE_ROWS
        ):
            assignment["evidence"].update(parsed["products"][DEBUG_PRODUCT]["hashes"])
    assignment_authority = DiscoveryAssignmentAuthority.from_dict(assignment_document)

    inventory_documents: dict[Path, dict[str, object]] = {}
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
                    reviewed_transition_active
                    and row_id in _PHASE4_BASELINE_EVIDENCE_ROWS
                ):
                    row["evidence"].update(debug_hashes)
                continue
            row["evidence"].update(debug_hashes)
        inventory_documents[inventory_path] = document

    if reviewed_transition_active:
        inventory_transitions = transition.get("inventory_site_transitions")
        if not isinstance(inventory_transitions, list):
            raise Phase2MeasurementError(
                "reviewed inventory transition authority changed"
            )
        _apply_reviewed_inventory_site_transitions(
            inventory_documents, inventory_transitions
        )

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
    if reviewed_transition_active:
        actual_digests = {
            path.relative_to(root).as_posix(): hashlib.sha256(payload).hexdigest()
            for path, payload in updates.items()
        }
        if actual_digests != successor_hashes:
            raise Phase2MeasurementError(
                "proposal does not match the exact reviewed authority "
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
        _finalize_publications(publications)


_PHASE2_AUTHORITY_PATHS = (
    "specs/full-colors/inventory/assignments.json",
    PLANNED_SUBJECTS_PATH,
    "specs/full-colors/inventory/writers.json",
    "specs/full-colors/inventory/scenes.json",
    "specs/full-colors/inventory/mutations.json",
)


def _phase5_relocated_subject_metadata(
    subject: Mapping[str, object],
) -> dict[str, object] | None:
    """Return the one exact Phase 5 linked relocation, or no transition."""
    if subject.get("kind") != "ROM_FINDING":
        return None
    metadata = subject.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    try:
        site = (
            int(metadata["bank"]),
            int(metadata["address"]),
            _string(metadata["bytes"], "subject.metadata.bytes"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    roots = _PHASE4_PASSIVE_ROM_POINTER_WRITES.get(site)
    if roots is None or metadata.get("mechanism") != "pointer":
        return None
    root_name = metadata.get("root")
    call_path = metadata.get("call_path")
    if not isinstance(root_name, str) or not isinstance(call_path, list):
        return None
    if root_name.startswith("PassiveFullColor"):
        if root_name not in roots or tuple(call_path) not in roots[root_name]:
            return None
    elif root_name != "<candidate-scan>":
        return None

    delta = _phase5_passive_pointer_rebase(site[2])
    successor = dict(metadata)
    successor["address"] = site[1] + delta
    successor["rom_offset"] = int(metadata["rom_offset"]) + delta
    successor["call_path"] = [
        _phase5_passive_ancestry_rebase(step) for step in call_path
    ]
    return successor


def _phase5_relocation_successor_payloads(
    root: Path, measured: Mapping[str, object]
) -> tuple[dict[str, bytes], dict[str, object]]:
    """Build the bounded authority successor without publishing it."""
    authority_payloads = {
        relative: _read_pinned_regular_file(
            root, root / relative, label=f"Phase 5 predecessor authority {relative}"
        )
        for relative in _PHASE2_AUTHORITY_PATHS
    }
    assignment_document = json.loads(
        authority_payloads[_PHASE2_AUTHORITY_PATHS[0]],
        object_pairs_hook=_strict_object,
    )
    planned_document = json.loads(
        authority_payloads[PLANNED_SUBJECTS_PATH], object_pairs_hook=_strict_object
    )
    row_ids = set(planned_document["source_subjects"])
    audit = measured["products"][PHASE2_AUDIT_PRODUCT]
    measured_subjects = (*audit["rom_subjects"], *audit["rom_candidate_subjects"])
    by_metadata: dict[str, Mapping[str, object]] = {}
    measured_by_digest: dict[str, Mapping[str, object]] = {}
    for subject in measured_subjects:
        measured_by_digest[subject["sha256"]] = subject
        metadata_key = json.dumps(
            subject["metadata"], sort_keys=True, separators=(",", ":")
        )
        previous = by_metadata.setdefault(metadata_key, subject)
        if previous["sha256"] != subject["sha256"]:
            raise Phase2MeasurementError(
                "Phase 5 proposal contains ambiguous relocated subject metadata"
            )

    shared_digest_transitions: dict[str, str] = {}
    audit_assignments_by_digest = {
        assignment["subject"]["sha256"]: assignment["subject"]
        for assignment in assignment_document["rows"]
        if assignment["product"] == PHASE2_AUDIT_PRODUCT
    }
    for old_digest in planned_document["shared_candidate_dispositions"]:
        old_subject = audit_assignments_by_digest.get(old_digest)
        if old_subject is None:
            raise Phase2MeasurementError(
                "Phase 5 shared candidate lacks its audit predecessor subject"
            )
        successor_metadata = dict(old_subject["metadata"])
        successor_metadata["address"] += _PHASE5_SHARED_CANDIDATE_REBASE_BYTES
        successor_metadata["rom_offset"] += _PHASE5_SHARED_CANDIDATE_REBASE_BYTES
        key = json.dumps(successor_metadata, sort_keys=True, separators=(",", ":"))
        successor = by_metadata.get(key)
        if successor is None:
            raise Phase2MeasurementError(
                "Phase 5 proposal lacks exact relocated shared candidate "
                f"{old_digest}"
            )
        shared_digest_transitions[old_digest] = successor["sha256"]
    if len(shared_digest_transitions) != 15:
        raise Phase2MeasurementError(
            "Phase 5 relocation must split exactly 15 audit shared candidates: "
            f"actual={len(shared_digest_transitions)}"
        )

    transitions: dict[str, dict[str, str]] = {}
    digest_transitions: dict[str, str] = {}
    covered_sites: set[tuple[int, int, str]] = set()
    for assignment in assignment_document["rows"]:
        if assignment["product"] != PHASE2_AUDIT_PRODUCT:
            continue
        old_subject = assignment["subject"]
        old_digest = old_subject["sha256"]
        if old_digest in shared_digest_transitions:
            successor = measured_by_digest[shared_digest_transitions[old_digest]]
        elif assignment["row_id"] == "WR-P2-YELLOW-OVERLAY-TRANSFER":
            successor_metadata = _phase5_relocated_subject_metadata(old_subject)
            if successor_metadata is None:
                continue
            key = json.dumps(
                successor_metadata, sort_keys=True, separators=(",", ":")
            )
            successor = by_metadata.get(key)
            if successor is None:
                raise Phase2MeasurementError(
                    f"Phase 5 proposal lacks bounded relocated subject "
                    f"{assignment['id']}"
                )
        else:
            continue
        new_digest = successor["sha256"]
        prior = digest_transitions.setdefault(old_digest, new_digest)
        if prior != new_digest:
            raise Phase2MeasurementError(
                "Phase 5 relocation maps one predecessor digest ambiguously"
            )
        transitions[assignment["id"]] = {
            "from_sha256": old_digest,
            "to_sha256": new_digest,
        }
        assignment["subject"] = successor
        if old_digest not in shared_digest_transitions:
            metadata = old_subject["metadata"]
            covered_sites.add(
                (metadata["bank"], metadata["address"], metadata["bytes"])
            )

    expected_sites = set(_PHASE4_PASSIVE_ROM_POINTER_WRITES)
    if covered_sites != expected_sites:
        raise Phase2MeasurementError(
            "Phase 5 authority transition does not cover every predecessor site: "
            f"missing={sorted(expected_sites - covered_sites)} "
            f"extra={sorted(covered_sites - expected_sites)}"
        )

    for assignment in assignment_document["rows"]:
        if assignment["row_id"] not in row_ids:
            continue
        product = assignment["product"]
        if product in measured["products"]:
            assignment["evidence"].update(measured["products"][product]["hashes"])

    for key in ("rom_subjects", "rom_candidate_subjects"):
        for row_id, digests in planned_document[key].items():
            rebound = [digest_transitions.get(digest, digest) for digest in digests]
            if len(rebound) != len(set(rebound)):
                raise Phase2MeasurementError(
                    f"Phase 5 relocation collapses planned authority {key}.{row_id}"
                )
            planned_document[key][row_id] = sorted(rebound)

    shared = planned_document["shared_candidate_dispositions"]
    rebound_shared: dict[str, object] = {}
    for old_digest, disposition in shared.items():
        new_digest = shared_digest_transitions.get(old_digest)
        if new_digest is None:
            rebound_shared[old_digest] = disposition
            continue
        predecessor = dict(disposition)
        predecessor["products"] = [
            product
            for product in predecessor["products"]
            if product != PHASE2_AUDIT_PRODUCT
        ]
        successor = dict(disposition)
        successor["products"] = [PHASE2_AUDIT_PRODUCT]
        if not predecessor["products"]:
            raise Phase2MeasurementError(
                "Phase 5 shared-candidate split lost production authority"
            )
        rebound_shared[old_digest] = predecessor
        rebound_shared[new_digest] = successor
    planned_document["shared_candidate_dispositions"] = dict(
        sorted(rebound_shared.items())
    )
    planned_document["authority_counts"]["shared_candidate_dispositions"] = {
        "by_representative_row": {
            row_id: sum(
                disposition["representative_row"] == row_id
                for disposition in rebound_shared.values()
            )
            for row_id in planned_document["source_subjects"]
        },
        "product_bindings": sum(
            len(disposition["products"])
            for disposition in rebound_shared.values()
        ),
        "total": len(rebound_shared),
    }

    debug_hashes = measured["products"][DEBUG_PRODUCT]["hashes"]
    inventory_documents: dict[str, dict[str, object]] = {}
    for relative in _PHASE2_AUTHORITY_PATHS[2:]:
        document = json.loads(
            authority_payloads[relative], object_pairs_hook=_strict_object
        )
        for row in document["rows"]:
            if row["id"] in row_ids:
                row["evidence"].update(debug_hashes)
        inventory_documents[relative] = document

    successor_payloads = {
        _PHASE2_AUTHORITY_PATHS[0]: DiscoveryAssignmentAuthority.from_dict(
            assignment_document
        )
        .to_json()
        .encode("utf-8"),
        PLANNED_SUBJECTS_PATH: _canonical_pretty(planned_document),
        **{
            relative: {
                "writers.json": WriterInventory,
                "scenes.json": SceneInventory,
                "mutations.json": MutationInventory,
            }[Path(relative).name]
            .from_dict(document)
            .to_json()
            .encode("utf-8")
            for relative, document in inventory_documents.items()
        },
    }
    details = {
        "shared_candidate_transitions": dict(
            sorted(shared_digest_transitions.items())
        ),
        "subject_transitions": dict(sorted(transitions.items())),
    }
    return successor_payloads, details


def propose_phase5_relocation_extension(root: Path) -> dict[str, object]:
    """Propose the one bounded Phase 5 audit-only authority transition."""
    root = Path(os.path.abspath(root))
    transition_path = root / REVIEWED_TRANSITION_PATH
    raw_transition = _read_pinned_regular_file(
        root, transition_path, label="reviewed transition authority"
    )
    if hashlib.sha256(raw_transition).hexdigest() != REVIEWED_TRANSITION_SHA256:
        raise Phase2MeasurementError("reviewed transition authority changed")
    transition = json.loads(raw_transition, object_pairs_hook=_strict_object)
    if PHASE5_RELOCATION_EXTENSION_KEY in transition:
        raise Phase2MeasurementError("Phase 5 relocation extension is already consumed")

    measured = propose_phase2_subjects(root)
    successor_payloads, details = _phase5_relocation_successor_payloads(root, measured)
    predecessor_hashes = {
        relative: hashlib.sha256(
            _read_pinned_regular_file(
                root, root / relative, label=f"Phase 5 predecessor authority {relative}"
            )
        ).hexdigest()
        for relative in _PHASE2_AUTHORITY_PATHS
    }
    successor_hashes = {
        relative: hashlib.sha256(payload).hexdigest()
        for relative, payload in successor_payloads.items()
    }
    evidence = json.loads(
        (root / "specs/full-colors/evidence/phase2-hostile-slice-representation.json").read_text()
    )
    production_artifacts: dict[str, str] = {}
    for product in PRODUCTION_PRODUCTS:
        artifact = PRODUCT_ARTIFACTS[product]
        for suffix in (".gbc", ".map", ".sym"):
            name = f"{artifact}{suffix}"
            digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
            if evidence["inputs"][name]["sha256"] != digest:
                raise Phase2MeasurementError(
                    f"Phase 5 relocation changed production artifact {name}"
                )
            production_artifacts[name] = digest

    relocation_sites = []
    for (bank, address, opcode), roots in _PHASE4_PASSIVE_ROM_POINTER_WRITES.items():
        delta = _phase5_passive_pointer_rebase(opcode)
        relocation_sites.append(
            {
                "from": {"address": address, "bank": bank, "bytes": opcode},
                "roots": {
                    root_name: [list(path) for path in paths]
                    for root_name, paths in roots.items()
                },
                "successor_roots": {
                    root_name: [list(path) for path in paths]
                    for root_name, paths in _phase5_passive_pointer_roots(roots).items()
                },
                "to": {
                    "address": address + delta,
                    "bank": bank,
                    "bytes": opcode,
                },
            }
        )
    extension = {
        "predecessor_authority_sha256": predecessor_hashes,
        "previous_transition_sha256": REVIEWED_TRANSITION_SHA256,
        "production_artifact_sha256": dict(sorted(production_artifacts.items())),
        "proposal_sha256": hashlib.sha256(_canonical_pretty(measured)).hexdigest(),
        "relocation_sites": relocation_sites,
        "schema": PHASE5_RELOCATION_EXTENSION_SCHEMA,
        "shared_candidate_transitions": details["shared_candidate_transitions"],
        "subject_transitions": details["subject_transitions"],
        "successor_authority_sha256": successor_hashes,
        "verifier_normalized_sha256": hashlib.sha256(
            _normalized_verifier_source((root / VERIFIER_PATH).read_bytes())
        ).hexdigest(),
    }
    return {
        "authority_path": REVIEWED_TRANSITION_PATH,
        "extension": extension,
        "reviewed": False,
        "schema": PHASE5_RELOCATION_PROPOSAL_SCHEMA,
    }


def apply_phase5_relocation_extension(root: Path, proposal_path: Path) -> None:
    _apply_phase5_extension(root, proposal_path, closure=False)


def apply_phase5_closure_extension(root: Path, proposal_path: Path) -> None:
    _apply_phase5_extension(root, proposal_path, closure=True)


def _apply_phase5_extension(
    root: Path, proposal_path: Path, *, closure: bool
) -> None:
    """Atomically publish one freshly recomputed reviewed Phase 5 extension."""
    root = Path(os.path.abspath(root))
    raw_proposal = _read_pinned_regular_file(
        root, Path(os.path.abspath(proposal_path)), label="proposal"
    )
    parsed = json.loads(raw_proposal, object_pairs_hook=_strict_object)
    if raw_proposal != _canonical_pretty(parsed):
        raise Phase2MeasurementError("Phase 5 relocation proposal is not canonical JSON")
    extension = parsed.get("extension")
    if not isinstance(extension, Mapping):
        raise Phase2MeasurementError("Phase 5 relocation proposal is malformed")
    predecessor_hashes = extension.get("predecessor_authority_sha256")
    successor_hashes = extension.get("successor_authority_sha256")
    if (
        not isinstance(predecessor_hashes, Mapping)
        or not isinstance(successor_hashes, Mapping)
        or set(predecessor_hashes) != set(_PHASE2_AUTHORITY_PATHS)
        or set(successor_hashes) != set(_PHASE2_AUTHORITY_PATHS)
    ):
        raise Phase2MeasurementError("Phase 5 authority hash sets are malformed")

    transition_path = root / REVIEWED_TRANSITION_PATH
    verifier_path = root / VERIFIER_PATH
    predecessor_paths = {
        **{root / relative: predecessor_hashes[relative] for relative in _PHASE2_AUTHORITY_PATHS},
        **{
            root / relative: digest
            for relative, digest in extension.get(
                "production_artifact_sha256", {}
            ).items()
        },
        transition_path: extension.get("previous_transition_sha256"),
    }
    pinned_identities: dict[Path, _AuthorityIdentity] = {}
    pinned_payloads: dict[Path, bytes] = {}
    for path, expected_digest in predecessor_paths.items():
        if not isinstance(expected_digest, str) or _SHA256.fullmatch(expected_digest) is None:
            raise Phase2MeasurementError("Phase 5 predecessor hash set is malformed")
        pinned_identities[path] = _authority_identity(
            path, label="Phase 5 predecessor authority"
        )
        payload = _read_pinned_regular_file(
            root, path, label="Phase 5 predecessor authority"
        )
        if hashlib.sha256(payload).hexdigest() != expected_digest:
            raise Phase2MeasurementError(
                f"Phase 5 predecessor authority hash changed: {path}"
            )
        if _authority_identity(path, label="Phase 5 predecessor authority") != (
            pinned_identities[path]
        ):
            raise Phase2MeasurementError(
                f"Phase 5 predecessor authority changed while pinning: {path}"
            )
        pinned_payloads[path] = payload
    pinned_identities[verifier_path] = _authority_identity(
        verifier_path, label="Phase 5 verifier authority"
    )
    raw_verifier = _read_pinned_regular_file(
        root, verifier_path, label="Phase 5 verifier authority"
    )
    if hashlib.sha256(_normalized_verifier_source(raw_verifier)).hexdigest() != (
        extension.get("verifier_normalized_sha256")
    ):
        raise Phase2MeasurementError("Phase 5 verifier normalized hash changed")
    if _authority_identity(verifier_path, label="Phase 5 verifier authority") != (
        pinned_identities[verifier_path]
    ):
        raise Phase2MeasurementError("Phase 5 verifier changed while pinning")
    pinned_payloads[verifier_path] = raw_verifier

    measured_proposal = (
        propose_phase5_closure_extension(root)
        if closure
        else propose_phase5_relocation_extension(root)
    )
    if parsed != measured_proposal:
        raise Phase2MeasurementError("stale or changed Phase 5 relocation proposal")

    measured = propose_phase2_subjects(root)
    successor_payloads, _ = (
        _phase5_closure_successor_payloads(root, measured)
        if closure
        else _phase5_relocation_successor_payloads(root, measured)
    )
    actual_successor_hashes = {
        relative: hashlib.sha256(payload).hexdigest()
        for relative, payload in successor_payloads.items()
    }
    if actual_successor_hashes != dict(successor_hashes):
        raise Phase2MeasurementError("Phase 5 recomputed successor hashes changed")
    for path, identity in pinned_identities.items():
        if _authority_identity(path, label="Phase 5 pinned authority") != identity:
            raise Phase2MeasurementError(
                f"Phase 5 pinned authority changed during recomputation: {path}"
            )

    transition = json.loads(
        pinned_payloads[transition_path], object_pairs_hook=_strict_object
    )
    transition[
        PHASE5_CLOSURE_EXTENSION_KEY if closure else PHASE5_RELOCATION_EXTENSION_KEY
    ] = parsed["extension"]
    transition_payload = _canonical_pretty(transition)
    transition_digest = hashlib.sha256(transition_payload).hexdigest()
    verifier_payload, replacements = _TRANSITION_DIGEST_CARRIER.subn(
        f'REVIEWED_TRANSITION_SHA256 = (\n    "{transition_digest}"\n)'.encode(),
        pinned_payloads[verifier_path],
    )
    if replacements != 1:
        raise Phase2MeasurementError("reviewed transition digest carrier changed")

    updates = {
        **{root / relative: payload for relative, payload in successor_payloads.items()},
        transition_path: transition_payload,
        verifier_path: verifier_payload,
    }
    identities = dict(pinned_identities)
    publications: list[_PublishedAuthority] = []
    try:
        for path, payload in updates.items():
            identities[path] = _atomic_replace(
                path,
                payload,
                identities[path],
                publications,
                expected_sha256=hashlib.sha256(pinned_payloads[path]).hexdigest(),
            )
        DiscoveryAssignmentAuthority.load(root / _PHASE2_AUTHORITY_PATHS[0])
        WriterInventory.load(root / _PHASE2_AUTHORITY_PATHS[2])
        SceneInventory.load(root / _PHASE2_AUTHORITY_PATHS[3])
        MutationInventory.load(root / _PHASE2_AUTHORITY_PATHS[4])
        _load_planned_subjects(root, closed=True)
        for relative, expected_digest in extension.get(
            "production_artifact_sha256", {}
        ).items():
            artifact_path = root / relative
            artifact_payload = _read_pinned_regular_file(
                root, artifact_path, label="Phase 5 production artifact"
            )
            if hashlib.sha256(artifact_payload).hexdigest() != expected_digest or (
                _authority_identity(artifact_path, label="Phase 5 production artifact")
                != pinned_identities[artifact_path]
            ):
                raise Phase2MeasurementError(
                    f"Phase 5 production artifact changed during apply: {relative}"
                )
        for publication in publications:
            _validate_publication(publication)
    except Exception as exc:
        rollback_errors = []
        for publication in reversed(publications):
            try:
                identities[publication.path] = _restore_publication(publication)
            except (OSError, Phase2MeasurementError) as rollback_exc:
                rollback_errors.append(f"{publication.path}: {rollback_exc}")
        if rollback_errors:
            raise Phase2MeasurementError(
                "Phase 5 relocation apply failed with incomplete rollback: "
                + "; ".join(rollback_errors)
            ) from exc
        raise Phase2MeasurementError(
            "Phase 5 relocation apply failed; predecessor authorities restored"
        ) from exc
    else:
        _finalize_publications(publications)


def _closure_subject_signature(subject: Mapping[str, object]) -> str:
    metadata = dict(subject["metadata"])
    metadata.pop("evidence_sha256", None)
    if subject["kind"] == "SOURCE_FINDING":
        metadata.pop("line", None)
        metadata.pop("destination_line", None)
    else:
        for key in (
            "address",
            "rom_offset",
            "destination_high",
            "destination_low",
            "bytes",
            "vbk_high",
            "vbk_low",
        ):
            metadata.pop(key, None)
        metadata.pop("call_path", None)
    return json.dumps(metadata, sort_keys=True, separators=(",", ":"))


def _closure_subject_order(subject: Mapping[str, object]) -> tuple[object, ...]:
    metadata = subject["metadata"]
    if subject["kind"] == "SOURCE_FINDING":
        return (
            metadata.get("path") or "",
            metadata.get("line") if metadata.get("line") is not None else -1,
            metadata.get("destination_path") or "",
            metadata.get("destination_line")
            if metadata.get("destination_line") is not None
            else -1,
            subject["sha256"],
        )
    return (
        metadata.get("bank") if metadata.get("bank") is not None else -1,
        metadata.get("address") if metadata.get("address") is not None else -1,
        metadata.get("rom_offset") if metadata.get("rom_offset") is not None else -1,
        subject["sha256"],
    )


def _phase5_closure_successor_payloads(
    root: Path, measured: Mapping[str, object]
) -> tuple[dict[str, bytes], dict[str, object]]:
    authority_payloads = {
        relative: _read_pinned_regular_file(
            root, root / relative, label=f"Phase 5 closure predecessor {relative}"
        )
        for relative in _PHASE2_AUTHORITY_PATHS
    }
    assignment_document = json.loads(
        authority_payloads[_PHASE2_AUTHORITY_PATHS[0]], object_pairs_hook=_strict_object
    )
    planned_document = json.loads(
        authority_payloads[PLANNED_SUBJECTS_PATH], object_pairs_hook=_strict_object
    )
    row_ids = set(planned_document["source_subjects"])
    desired: dict[tuple[str, str, str], list[Mapping[str, object]]] = {}
    for product_name, product in measured["products"].items():
        for subject in measured["source_subjects"]:
            metadata = subject["metadata"]
            root_name = _source_finding_root(SimpleNamespace(**metadata))
            if root_name is None:
                continue
            row_id = _planned_row_for(
                root_name, metadata["category"], resource=metadata.get("resource")
            )
            desired.setdefault((product_name, row_id, "SOURCE_FINDING"), []).append(subject)
        site_rows: dict[tuple[int, int], set[str]] = {}
        direct_rows: dict[str, str] = {}
        for subject in product["rom_subjects"]:
            metadata = subject["metadata"]
            if (
                metadata["root"].startswith("PassiveFullColor")
                and metadata["resource"] == "UNKNOWN_DESTINATION"
                and metadata["mechanism"] == "pointer"
            ):
                row_id = "WR-P2-YELLOW-OVERLAY-TRANSFER"
            else:
                row_id = _planned_row_for(
                    metadata["root"], metadata["category"], resource=metadata.get("resource")
                )
            direct_rows[subject["sha256"]] = row_id
            site_rows.setdefault((metadata["bank"], metadata["address"]), set()).add(row_id)
            desired.setdefault((product_name, row_id, "ROM_FINDING"), []).append(subject)
        reviewed_shared = {
            tuple(disposition["eligible_rows"]): disposition["representative_row"]
            for disposition in planned_document["shared_candidate_dispositions"].values()
            if product_name in disposition["products"]
        }
        for subject in product["rom_candidate_subjects"]:
            metadata = subject["metadata"]
            eligible = tuple(sorted(site_rows[(metadata["bank"], metadata["address"])]))
            row_id = eligible[0] if len(eligible) == 1 else reviewed_shared.get(eligible)
            if row_id is None:
                raise Phase2MeasurementError("Phase 5 closure candidate semantics changed")
            desired.setdefault((product_name, row_id, "ROM_FINDING"), []).append(subject)

    assignment_groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    assignment_templates: dict[tuple[str, str, str], dict[str, object]] = {}
    for assignment in assignment_document["rows"]:
        if assignment["row_id"] in row_ids and assignment["subject"]["kind"] in {
            "SOURCE_FINDING", "ROM_FINDING"
        }:
            assignment_groups.setdefault(
                (assignment["product"], assignment["subject"]["kind"]), []
            ).append(assignment)
            assignment_templates.setdefault(
                (assignment["product"], assignment["row_id"], assignment["subject"]["kind"]),
                {
                    "category": assignment["category"],
                    "scene": assignment["scene"],
                    "mutation": assignment["mutation"],
                },
            )

    def reclassify(assignment: dict[str, object], row_id: str, kind: str) -> None:
        template = assignment_templates.get((assignment["product"], row_id, kind))
        if template is None:
            raise Phase2MeasurementError(f"Phase 5 closure lacks row template {row_id}")
        assignment["row_id"] = row_id
        for key in ("category", "scene", "mutation"):
            assignment[key] = template[key]

    transitions: dict[str, dict[str, str]] = {}
    audit_splits: dict[str, dict[str, str]] = {}
    additions: dict[str, dict[str, str]] = {}
    retirements: dict[str, dict[str, str]] = {}
    retired_ids: set[str] = set()
    added_assignments: list[dict[str, object]] = []
    for group_key, assignments in assignment_groups.items():
        product_name, kind = group_key
        successor_entries = [
            (row_id, subject)
            for (candidate_product, row_id, candidate_kind), subjects in desired.items()
            if (candidate_product, candidate_kind) == group_key
            for subject in subjects
        ]
        allow_audit_split = (
            product_name == PHASE2_AUDIT_PRODUCT
            and kind == "ROM_FINDING"
            and len(successor_entries) >= len(assignments)
        )
        allow_source_retirement = kind == "SOURCE_FINDING" and len(
            successor_entries
        ) <= len(assignments)
        if (
            len(assignments) != len(successor_entries)
            and not allow_audit_split
            and not allow_source_retirement
        ):
            raise Phase2MeasurementError(
                f"Phase 5 closure count changed for {group_key}: "
                f"{len(assignments)} != {len(successor_entries)}"
            )
        successor_by_digest = {
            subject["sha256"]: (row_id, subject)
            for row_id, subject in successor_entries
        }
        unmatched_old = []
        used: set[str] = set()
        for assignment in assignments:
            digest = assignment["subject"]["sha256"]
            successor_entry = successor_by_digest.get(digest)
            if successor_entry is not None:
                row_id, successor = successor_entry
                reclassify(assignment, row_id, kind)
                assignment["subject"] = successor
                used.add(digest)
            else:
                unmatched_old.append(assignment)
        unmatched_new = [
            entry for entry in successor_entries if entry[1]["sha256"] not in used
        ]
        old_by_signature: dict[str, list[dict[str, object]]] = {}
        new_by_signature: dict[
            str, list[tuple[str, Mapping[str, object]]]
        ] = {}
        for assignment in unmatched_old:
            old_by_signature.setdefault(
                _closure_subject_signature(assignment["subject"]), []
            ).append(assignment)
        for row_id, subject in unmatched_new:
            new_by_signature.setdefault(_closure_subject_signature(subject), []).append(
                (row_id, subject)
            )
        if not allow_source_retirement and not set(old_by_signature).issubset(
            new_by_signature
        ):
            raise Phase2MeasurementError(f"Phase 5 closure semantics changed for {group_key}")
        for signature in sorted(old_by_signature):
            old_items = sorted(
                old_by_signature[signature], key=lambda item: _closure_subject_order(item["subject"])
            )
            new_items = sorted(
                new_by_signature.get(signature, []),
                key=lambda item: _closure_subject_order(item[1]),
            )
            if len(old_items) > len(new_items) and not (
                allow_source_retirement or allow_audit_split
            ):
                raise Phase2MeasurementError(
                    f"Phase 5 closure semantic multiplicity changed for {group_key}"
                )
            pairs: list[tuple[dict[str, object], tuple[str, Mapping[str, object]]]] = []
            remaining_old = list(old_items)
            remaining_new = list(new_items)
            for assignment in list(remaining_old):
                match = next(
                    (entry for entry in remaining_new if entry[0] == assignment["row_id"]),
                    None,
                )
                if match is not None:
                    pairs.append((assignment, match))
                    remaining_old.remove(assignment)
                    remaining_new.remove(match)
            if remaining_old and remaining_new:
                # Different roots/rows are distinct Phase 5 semantics, never a
                # relocation merely because their normalized shapes collide.
                pass
            for assignment, (row_id, successor) in pairs:
                old_digest = assignment["subject"]["sha256"]
                new_digest = successor["sha256"]
                transitions[assignment["id"]] = {
                    "from_sha256": old_digest,
                    "from_row_id": assignment["row_id"],
                    "from_subject": assignment["subject"],
                    "to_sha256": new_digest,
                    "to_row_id": row_id,
                    "to_subject": successor,
                }
                reclassify(assignment, row_id, kind)
                assignment["subject"] = successor
            for assignment in remaining_old:
                retired_ids.add(assignment["id"])
                retirements[assignment["id"]] = {
                    "disposition": "retired_for_product",
                    "product": product_name,
                    "retired_sha256": assignment["subject"]["sha256"],
                    "retired_row_id": assignment["row_id"],
                    "retired_subject": assignment["subject"],
                }
            new_by_signature[signature] = remaining_new

        leftovers = [
            entry
            for signature in sorted(new_by_signature)
            for entry in sorted(
                new_by_signature[signature], key=lambda item: _closure_subject_order(item[1])
            )
        ]
        if leftovers and not (allow_audit_split or allow_source_retirement):
            raise Phase2MeasurementError(f"Phase 5 closure added semantics for {group_key}")
        production = [
            assignment
            for assignment in assignment_document["rows"]
            if assignment["product"] == PRODUCTION_PRODUCTS[0]
            and assignment["subject"]["kind"] == kind
        ]
        production_by_signature: dict[str, list[dict[str, object]]] = {}
        for assignment in production:
            production_by_signature.setdefault(
                _closure_subject_signature(assignment["subject"]), []
            ).append(assignment)
        for row_id, successor in leftovers:
            signature = _closure_subject_signature(successor)
            predecessors = production_by_signature.get(signature, [])
            if kind == "SOURCE_FINDING":
                predecessors = [
                    row
                    for row in assignments
                    if row["row_id"] == row_id
                ]
            if not predecessors:
                raise Phase2MeasurementError(
                    "Phase 5 audit split lacks production-retained semantic peer for "
                    f"{row_id}: {successor['metadata']}"
                )
            predecessor = sorted(
                predecessors, key=lambda item: _closure_subject_order(item["subject"])
            )[0]
            template = assignment_templates[(product_name, row_id, kind)]
            prefix = {
                "pokeyellow": "NORMAL",
                "pokeyellow_debug": "DEBUG",
                "pokeyellow_vc": "VC",
                PHASE2_AUDIT_PRODUCT: "AUDIT",
            }[product_name]
            assignment_id = (
                f"AS-{prefix}-PHASE5-CLOSURE-{kind[:3]}-"
                + successor["sha256"][:16].upper()
            )
            if any(row["id"] == assignment_id for row in assignment_document["rows"]):
                raise Phase2MeasurementError("Phase 5 closure split ID collision")
            added = {
                "category": template["category"],
                "evidence": dict(predecessor["evidence"]),
                "id": assignment_id,
                "mutation": template["mutation"],
                "product": product_name,
                "row_id": row_id,
                "scene": template["scene"],
                "subject": successor,
            }
            added_assignments.append(added)
            if kind == "SOURCE_FINDING":
                additions[assignment_id] = {
                    "added_sha256": successor["sha256"],
                    "added_row_id": row_id,
                    "added_subject": successor,
                    "disposition": "added_for_product",
                    "product": product_name,
                    "reason": "phase5_source_control_flow_addition",
                }
            else:
                audit_splits[assignment_id] = {
                    "audit_successor_subject": successor,
                    "production_retained_sha256": predecessor["subject"]["sha256"],
                    "production_retained_subject": predecessor["subject"],
                    "audit_successor_sha256": successor["sha256"],
                }

    assignment_document["rows"] = [
        row for row in assignment_document["rows"] if row["id"] not in retired_ids
    ]
    assignment_document["rows"].extend(added_assignments)
    assignment_document["rows"].sort(key=lambda row: row["id"])

    for assignment in assignment_document["rows"]:
        product_name = assignment["product"]
        if assignment["row_id"] in row_ids and product_name in measured["products"]:
            assignment["evidence"].update(measured["products"][product_name]["hashes"])

    for transition in transitions.values():
        transition.setdefault("reason", "phase5_linked_layout_relocation")
        transition["type"] = (
            "source_replacement"
            if transition["reason"] == "phase5_source_control_flow_replacement"
            else
            "cross_row_reroot"
            if transition.get("from_row_id") != transition.get("to_row_id")
            else "one_to_one_relocation"
        )
    for retirement in retirements.values():
        retirement["reason"] = "phase5_source_control_flow_retirement"
        retirement["type"] = "retirement"
    for split in audit_splits.values():
        split["reason"] = "phase5_audit_only_control_flow_addition"
        split["type"] = "production_retained_audit_split"

    audit_name = PHASE2_AUDIT_PRODUCT
    for kind, key in (("SOURCE_FINDING", "source_subjects"),):
        planned_document[key] = {
            row_id: sorted(
                subject["sha256"]
                for subject in desired.get((audit_name, row_id, kind), [])
            )
            for row_id in row_ids
        }
    audit = measured["products"][audit_name]
    direct_digests = {subject["sha256"] for subject in audit["rom_subjects"]}
    candidate_digests = {subject["sha256"] for subject in audit["rom_candidate_subjects"]}
    planned_document["rom_subjects"] = {row_id: [] for row_id in row_ids}
    planned_document["rom_candidate_subjects"] = {row_id: [] for row_id in row_ids}
    for assignment in assignment_document["rows"]:
        if assignment["product"] != audit_name or assignment["row_id"] not in row_ids:
            continue
        digest = assignment["subject"]["sha256"]
        if digest in direct_digests:
            planned_document["rom_subjects"][assignment["row_id"]].append(digest)
        elif digest in candidate_digests:
            planned_document["rom_candidate_subjects"][assignment["row_id"]].append(digest)
    for key in ("rom_subjects", "rom_candidate_subjects"):
        for row_id in row_ids:
            planned_document[key][row_id] = sorted(set(planned_document[key][row_id]))
    for key in ("source_subjects", "rom_subjects", "rom_candidate_subjects"):
        by_row = {row_id: len(planned_document[key][row_id]) for row_id in row_ids}
        planned_document["authority_counts"][key] = {
            "by_row": by_row, "total": sum(by_row.values())
        }

    for assignment in assignment_document["rows"]:
        expected_prefix = {"mutation": "MU-", "scene": "SC-", "writer": "WR-"}[
            assignment["category"]
        ]
        if not assignment["row_id"].startswith(expected_prefix):
            raise Phase2MeasurementError(
                f"Phase 5 closure classification mismatch: {assignment['id']} "
                f"{assignment['category']} {assignment['row_id']}"
            )
    payloads = {
        _PHASE2_AUTHORITY_PATHS[0]: DiscoveryAssignmentAuthority.from_dict(
            assignment_document
        ).to_json().encode(),
        PLANNED_SUBJECTS_PATH: _canonical_pretty(planned_document),
        **{relative: authority_payloads[relative] for relative in _PHASE2_AUTHORITY_PATHS[2:]},
    }
    return payloads, {
        "audit_splits": dict(sorted(audit_splits.items())),
        "additions": dict(sorted(additions.items())),
        "retirements": dict(sorted(retirements.items())),
        "subject_transitions": dict(sorted(transitions.items())),
    }


def propose_phase5_closure_extension(root: Path) -> dict[str, object]:
    """Propose the exact remaining Phase 5 source and audit-ROM closure."""
    root = Path(os.path.abspath(root))
    raw_transition = _read_pinned_regular_file(
        root, root / REVIEWED_TRANSITION_PATH, label="reviewed transition authority"
    )
    if hashlib.sha256(raw_transition).hexdigest() != REVIEWED_TRANSITION_SHA256:
        raise Phase2MeasurementError("reviewed transition authority changed")
    transition = json.loads(raw_transition, object_pairs_hook=_strict_object)
    if PHASE5_RELOCATION_EXTENSION_KEY not in transition:
        raise Phase2MeasurementError("Phase 5 relocation predecessor is absent")
    if PHASE5_CLOSURE_EXTENSION_KEY in transition:
        raise Phase2MeasurementError("Phase 5 closure extension is already consumed")
    measured = propose_phase2_subjects(root)
    successors, details = _phase5_closure_successor_payloads(root, measured)
    predecessor = {
        relative: hashlib.sha256(
            _read_pinned_regular_file(root, root / relative, label="closure predecessor")
        ).hexdigest()
        for relative in _PHASE2_AUTHORITY_PATHS
    }
    production = {}
    evidence = json.loads(
        (root / "specs/full-colors/evidence/phase2-hostile-slice-representation.json").read_text()
    )
    for product in PRODUCTION_PRODUCTS:
        artifact = PRODUCT_ARTIFACTS[product]
        for suffix in (".gbc", ".map", ".sym"):
            name = artifact + suffix
            digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
            if evidence["inputs"][name]["sha256"] != digest:
                raise Phase2MeasurementError(f"Phase 5 closure changed production artifact {name}")
            production[name] = digest
    extension = {
        **details,
        "cardinality": {
            "audit_rom_additions": len(details["audit_splits"]),
            "audit_rom_equation": "1215 - 5 + 21 = 1231",
            "audit_rom_retirements": sum(
                item["retired_subject"]["kind"] == "ROM_FINDING"
                for item in details["retirements"].values()
            ),
            "by_product": {
                product: {
                    "source_additions": sum(
                        item["product"] == product for item in details["additions"].values()
                    ),
                    "source_equation": "263 - 25 + 14 = 252",
                    "source_predecessor": 263,
                    "source_retirements": sum(
                        item["product"] == product
                        and item["retired_subject"]["kind"] == "SOURCE_FINDING"
                        for item in details["retirements"].values()
                    ),
                    "source_successor": 252,
                }
                for product in (*PRODUCTION_PRODUCTS, PHASE2_AUDIT_PRODUCT)
            },
            "source_additions": len(details["additions"]),
            "source_retirements": sum(
                item["retired_subject"]["kind"] == "SOURCE_FINDING"
                for item in details["retirements"].values()
            ),
        },
        "predecessor_authority_sha256": predecessor,
        "previous_transition_sha256": REVIEWED_TRANSITION_SHA256,
        "production_artifact_sha256": dict(sorted(production.items())),
        "proposal_sha256": hashlib.sha256(_canonical_pretty(measured)).hexdigest(),
        "schema": PHASE5_CLOSURE_EXTENSION_SCHEMA,
        "successor_authority_sha256": {
            relative: hashlib.sha256(payload).hexdigest()
            for relative, payload in successors.items()
        },
        "verifier_normalized_sha256": hashlib.sha256(
            _normalized_verifier_source((root / VERIFIER_PATH).read_bytes())
        ).hexdigest(),
    }
    return {
        "authority_path": REVIEWED_TRANSITION_PATH,
        "extension": extension,
        "reviewed": False,
        "schema": PHASE5_CLOSURE_PROPOSAL_SCHEMA,
    }


_PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS = (
    "specs/full-colors/inventory/assignments.json",
    "specs/full-colors/inventory/writers.json",
    "specs/full-colors/inventory/scenes.json",
    "specs/full-colors/inventory/mutations.json",
    SOURCE_TRANSITION_PATH,
)

_PHASE5_INVENTORY_LINE_RELOCATIONS = (
    ("engine/menus/start_sub_menus.asm", "StartMenu_Pokemon.exitMenu", 44, 70),
    ("home/pokemon.asm", "PartyMenuInit", 207, 222),
    ("home/overworld.asm", "LoadNorthSouthConnectionsTileMap", 1008, 1019),
    ("home/overworld.asm", "ScheduleNorthRowRedraw", 1456, 1467),
    ("home/overworld.asm", "ScheduleSouthRowRedraw", 1477, 1493),
    ("home/overworld.asm", "ScheduleEastColumnRedraw", 1496, 1516),
    ("home/overworld.asm", "ScheduleWestColumnRedraw", 1533, 1557),
    ("home/overworld.asm", "LoadMapData", 1941, 1977),
)

_PHASE5_REQUIRED_PRODUCTION_EDGES = frozenset(
    {
        ("LoadMapData", "RunPaletteCommand"),
        ("LoadMapData", "PassiveFullColorApplyMap"),
        ("DisplayPartyMenu", "PartyMenuInit"),
        (
            "StartMenu_Pokemon.exitMenu",
            "RestoreScreenTilesAndReloadTilePatterns",
        ),
        ("StartMenu_Pokemon.exitMenu", "LoadGBPal"),
    }
)
_PHASE5_AUDIT_ONLY_EDGE = ("LoadMapData", "FullColorAuditLoadMapData")


def _relocate_inventory_lines(value: object) -> dict[tuple[str, str, int, int], int]:
    """Apply the eight reviewed source-coordinate relocations in memory."""
    counts = {item: 0 for item in _PHASE5_INVENTORY_LINE_RELOCATIONS}

    def visit(item: object, matched: set[tuple[str, str, int, int]]) -> None:
        if isinstance(item, dict):
            path = item.get("path")
            symbol = item.get("symbol")
            line = item.get("line")
            for relocation in _PHASE5_INVENTORY_LINE_RELOCATIONS:
                expected_path, expected_symbol, old_line, new_line = relocation
                if (path, symbol, line) == (expected_path, expected_symbol, old_line):
                    item["line"] = new_line
                    matched.add(relocation)
                    line = new_line
            for child in item.values():
                visit(child, matched)
        elif isinstance(item, list):
            for child in item:
                visit(child, matched)

    units = value.get("rows", []) if isinstance(value, dict) else []
    if not isinstance(units, list) or not units:
        units = [value]
    for unit in units:
        matched: set[tuple[str, str, int, int]] = set()
        visit(unit, matched)
        for relocation in matched:
            counts[relocation] += 1
    return counts


def _assignment_source_edge(row: Mapping[str, object]) -> tuple[str, str | None]:
    metadata = row["subject"]["metadata"]
    symbol = metadata["symbol"]
    if symbol.startswith("LoadMapData."):
        symbol = "LoadMapData"
    elif symbol.startswith("StartMenu_Pokemon.exitMenu"):
        symbol = "StartMenu_Pokemon.exitMenu"
    return symbol, metadata.get("destination")


def _validate_product_source_partition(
    root: Path, assignments: Mapping[str, object]
) -> None:
    by_product = {
        product: [
            row
            for row in assignments["rows"]
            if row.get("product") == product
            and row.get("subject", {}).get("kind") == "SOURCE_FINDING"
        ]
        for product in (*PRODUCTION_PRODUCTS, PHASE2_AUDIT_PRODUCT)
    }
    for product in PRODUCTION_PRODUCTS:
        inactive = [
            row["id"]
            for row in by_product[product]
            if not _source_finding_active_for_product(
                root,
                SimpleNamespace(
                    path=row["subject"]["metadata"]["path"],
                    line=row["subject"]["metadata"]["line"],
                ),
                product,
            )
        ]
        if inactive:
            raise Phase2MeasurementError(
                f"{product}: audit-only source assignment appears in production: "
                + ", ".join(sorted(inactive))
            )
        edges = {_assignment_source_edge(row) for row in by_product[product]}
        missing_edges = _PHASE5_REQUIRED_PRODUCTION_EDGES - edges
        if missing_edges:
            raise Phase2MeasurementError(
                f"{product}: production source edge omitted: {sorted(missing_edges)}"
            )
        if _PHASE5_AUDIT_ONLY_EDGE in edges:
            raise Phase2MeasurementError(
                f"{product}: audit-only LoadMapData edge remains in production"
            )
    audit_edges = {
        _assignment_source_edge(row) for row in by_product[PHASE2_AUDIT_PRODUCT]
    }
    if _PHASE5_AUDIT_ONLY_EDGE not in audit_edges:
        raise Phase2MeasurementError("audit LoadMapData successor edge is absent")


def _phase5_product_split_successor_payloads(
    root: Path,
) -> tuple[dict[str, bytes], dict[str, object]]:
    """Return the exact product-partitioned authority successor."""
    raw_payloads = {
        relative: _read_pinned_regular_file(
            root, root / relative, label=f"product-split predecessor {relative}"
        )
        for relative in _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS
    }
    documents = {
        relative: json.loads(payload, object_pairs_hook=_strict_object)
        for relative, payload in raw_payloads.items()
    }
    transition = documents[SOURCE_TRANSITION_PATH]
    if transition.get("schema") != phase1_source_transition.SCHEMA:
        raise Phase2MeasurementError("Phase 1 source transition schema changed")
    if len(transition.get("audit_only_source_regions", ())) != 17:
        raise Phase2MeasurementError(
            "Phase 1 source transition must retain exactly 17 conditional regions"
        )
    try:
        canonical_transition = phase1_source_transition.generate_from_authority(
            root, transition
        )
    except phase1_source_transition.SourceTransitionError as exc:
        raise Phase2MeasurementError(
            "Phase 1 source transition failed canonical recomputation"
        ) from exc
    if transition != canonical_transition:
        raise Phase2MeasurementError(
            "Phase 1 source transition is not its canonical current authority"
        )

    assignments = documents[_PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[0]]
    reviewed_transition = json.loads(
        _read_pinned_regular_file(
            root,
            root / REVIEWED_TRANSITION_PATH,
            label="product-split consumed transition history",
        ),
        object_pairs_hook=_strict_object,
    )
    closure_history = reviewed_transition.get(PHASE5_CLOSURE_EXTENSION_KEY)
    if not isinstance(closure_history, Mapping):
        raise Phase2MeasurementError("Phase 5 closure history is absent")
    closure_successors = closure_history.get("successor_authority_sha256")
    if not isinstance(closure_successors, Mapping) or set(closure_successors) != set(
        _PHASE2_AUTHORITY_PATHS
    ):
        raise Phase2MeasurementError("Phase 5 closure successor history is malformed")
    for relative in _PHASE2_AUTHORITY_PATHS:
        actual = hashlib.sha256(
            _read_pinned_regular_file(
                root, root / relative, label="product-split closure successor"
            )
        ).hexdigest()
        if actual != closure_successors[relative]:
            raise Phase2MeasurementError(
                f"Phase 5 product split lost exact closure predecessor: {relative}"
            )

    contaminated_owners = {
        "DisplayPartyMenu": "DisplayPartyMenu.phase5Hidden",
        "LoadMapData": "FullColorAuditLoadMapData",
        "StartMenu_Pokemon": "StartMenu_Pokemon.ordinaryExit",
        "ScheduleNorthRowRedraw": "FullColorPhase5NorthConnectionOrigin",
    }

    def predecessor_group(item: Mapping[str, object]) -> tuple[str, str, str, str]:
        metadata = item["retired_subject"]["metadata"]
        owner = metadata["symbol"].split(".", 1)[0]
        return (
            metadata["path"],
            owner,
            metadata["mechanism"],
            metadata["destination"],
        )

    def finding_group(finding: object) -> tuple[str, str, str, str] | None:
        for owner, contaminated in contaminated_owners.items():
            if finding.symbol == contaminated or finding.symbol.startswith(contaminated):
                return (finding.path, owner, finding.mechanism, finding.destination)
        return None

    source_report = _normalize_closed_scene_directions(discover_phase2_sources(root))
    product_rebindings: dict[
        str, dict[str, tuple[dict[str, object], str, dict[str, object]]]
    ] = {}
    for product in PRODUCTION_PRODUCTS:
        historical = [
            {**item, "historical_assignment_id": assignment_id}
            for assignment_id, item in closure_history.get("retirements", {}).items()
            if item.get("product") == product
            and item.get("retired_subject", {}).get("kind") == "SOURCE_FINDING"
        ]
        old_groups: dict[tuple[str, str, str, str], list[dict[str, object]]] = {}
        for item in historical:
            old_groups.setdefault(predecessor_group(item), []).append(item)
        current_groups: dict[tuple[str, str, str, str], list[object]] = {}
        for finding in _product_source_report(root, source_report, product).findings:
            group = finding_group(finding)
            if group is not None:
                current_groups.setdefault(group, []).append(finding)
        rebound: dict[str, tuple[dict[str, object], str, dict[str, object]]] = {}
        for key, old_items in old_groups.items():
            current_items = current_groups.get(key, [])
            if len(old_items) != len(current_items):
                raise Phase2MeasurementError(
                    f"{product}: consumed production predecessor cannot be restored "
                    f"uniquely ({len(old_items)} != {len(current_items)})"
                )
            for old_item, finding in zip(
                sorted(
                    old_items,
                    key=lambda item: item["retired_subject"]["metadata"]["line"],
                ),
                sorted(current_items, key=lambda item: item.line),
                strict=True,
            ):
                current_subject = source_finding_subject(finding).to_dict()
                predecessor = old_item["retired_subject"]
                corrected_metadata = dict(predecessor["metadata"])
                current_metadata = current_subject["metadata"]
                for field in (
                    "line",
                    "evidence_sha256",
                    "destination_line",
                    "destination_path",
                ):
                    corrected_metadata[field] = current_metadata[field]
                corrected = RejectionSubject.create(
                    SubjectKind.SOURCE_FINDING, corrected_metadata
                ).to_dict()
                rebound[current_subject["sha256"]] = (
                    corrected,
                    old_item["retired_row_id"],
                    old_item,
                )
        if len(rebound) != 25:
            raise Phase2MeasurementError(
                f"{product}: expected 25 consumed production predecessors, got {len(rebound)}"
            )
        product_rebindings[product] = rebound

    retained_rows: list[dict[str, object]] = []
    removed: dict[str, list[dict[str, object]]] = {
        product: [] for product in (*PRODUCTION_PRODUCTS, PHASE2_AUDIT_PRODUCT)
    }
    for row in assignments["rows"]:
        product = row.get("product")
        subject = row.get("subject", {})
        if (
            product in removed
            and subject.get("kind") == "SOURCE_FINDING"
        ):
            metadata = subject.get("metadata", {})
            finding = SimpleNamespace(
                path=metadata.get("path"), line=metadata.get("line")
            )
            if (
                not isinstance(finding.path, str)
                or not isinstance(finding.line, int)
                or not _source_finding_active_for_product(root, finding, product)
            ):
                removed[product].append(
                    {
                        "id": row["id"],
                        "row_id": row["row_id"],
                        "subject_sha256": subject.get("sha256"),
                    }
                )
                continue
        retained_rows.append(row)
    templates: dict[tuple[str, str], dict[str, object]] = {}
    scene_authority = {
        row["id"]: row
        for row in documents[_PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[2]]["rows"]
    }
    for row in assignments["rows"]:
        key = (row["product"], row["row_id"])
        if (
            key not in templates
            or (
                templates[key]["subject"]["kind"] != "SOURCE_FINDING"
                and row["subject"]["kind"] == "SOURCE_FINDING"
            )
        ):
            templates[key] = row
    restored_assignment_ids: set[str] = set()
    for product, rebindings in product_rebindings.items():
        for corrected, row_id, historical in rebindings.values():
            template = templates.get((product, row_id))
            if template is None:
                raise Phase2MeasurementError(
                    f"{product}: restored predecessor lacks row template {row_id}"
                )
            assignment_id = historical["historical_assignment_id"]
            if assignment_id in restored_assignment_ids or any(
                row["id"] == assignment_id for row in retained_rows
            ):
                raise Phase2MeasurementError(
                    f"{product}: restored predecessor ID collision {assignment_id}"
                )
            restored_assignment_ids.add(assignment_id)
            metadata = corrected["metadata"]
            scene = template["scene"]
            mutation = template["mutation"]
            if template["category"] == "scene":
                scene_row = scene_authority[row_id]
                scene = {
                    "destination_line": metadata["destination_line"],
                    "destination_path": metadata["destination_path"],
                    "destination_symbol": metadata["destination"],
                    "direction": scene_row["direction"],
                    "row_kind": scene_row["row_kind"],
                }
            retained_rows.append(
                {
                    "category": template["category"],
                    "evidence": dict(template["evidence"]),
                    "id": assignment_id,
                    "mutation": mutation,
                    "product": product,
                    "row_id": row_id,
                    "scene": scene,
                    "subject": corrected,
                }
            )
    retained_rows.sort(key=lambda row: row["id"])
    assignments["rows"] = retained_rows

    # The scene snapshot embedded in every assignment follows the inventory's
    # stable destination coordinate; it is metadata, not a new subject.
    assignment_scene_updates = 0
    for row in assignments["rows"]:
        scene = row.get("scene")
        if (
            isinstance(scene, dict)
            and scene.get("destination_path") == "home/pokemon.asm"
            and scene.get("destination_symbol") == "PartyMenuInit"
            and scene.get("destination_line") == 207
        ):
            scene["destination_line"] = 222
            assignment_scene_updates += 1
    if assignment_scene_updates == 0:
        raise Phase2MeasurementError(
            "Phase 5 PartyMenuInit assignment metadata predecessor is absent"
        )

    restored_rows_by_product = {
        product: [
            corrected
            for corrected, _, _ in product_rebindings[product].values()
        ]
        for product in PRODUCTION_PRODUCTS
    }
    by_product = {
        product: [
            row
            for row in assignments["rows"]
            if row.get("product") == product
            and row.get("subject", {}).get("kind") == "SOURCE_FINDING"
        ]
        for product in (*PRODUCTION_PRODUCTS, PHASE2_AUDIT_PRODUCT)
    }
    for product in PRODUCTION_PRODUCTS:
        edges = {_assignment_source_edge(row) for row in by_product[product]}
        edges.update(
            (
                "LoadMapData"
                if subject["metadata"]["symbol"].startswith("LoadMapData")
                else "StartMenu_Pokemon.exitMenu"
                if subject["metadata"]["symbol"].startswith(
                    "StartMenu_Pokemon.exitMenu"
                )
                else subject["metadata"]["symbol"],
                subject["metadata"].get("destination"),
            )
            for subject in restored_rows_by_product[product]
        )
        # The restored subjects are already installed in the retained rows; the
        # explicit set proves the complete expected predecessor mapping before
        # strict serialized validation below.
        if _PHASE5_REQUIRED_PRODUCTION_EDGES - edges:
            raise Phase2MeasurementError(
                f"{product}: consumed production predecessor restoration is incomplete"
            )
    _validate_product_source_partition(root, assignments)

    inventory_counts: dict[str, dict[str, int]] = {}
    total_relocation_counts = {
        relocation: 0 for relocation in _PHASE5_INVENTORY_LINE_RELOCATIONS
    }
    for relative in _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[1:4]:
        counts = _relocate_inventory_lines(documents[relative])
        for relocation, count in counts.items():
            total_relocation_counts[relocation] += count
        inventory_counts[relative] = {
            f"{path}:{symbol}:{old}->{new}": count
            for (path, symbol, old, new), count in counts.items()
            if count
        }
    exact_relocation_counts = dict.fromkeys(_PHASE5_INVENTORY_LINE_RELOCATIONS, 1)
    wrong_relocations = [
        relocation
        for relocation, count in total_relocation_counts.items()
        if count != exact_relocation_counts[relocation]
    ]
    if wrong_relocations:
        raise Phase2MeasurementError(
            "Phase 5 inventory line predecessor multiplicity changed: "
            f"{[(item, total_relocation_counts[item], exact_relocation_counts[item]) for item in wrong_relocations]}"
        )

    payloads = {
        _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[0]: DiscoveryAssignmentAuthority.from_dict(
            assignments
        ).to_json().encode("utf-8"),
        _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[1]: WriterInventory.from_dict(
            documents[_PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[1]]
        ).to_json().encode("utf-8"),
        _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[2]: SceneInventory.from_dict(
            documents[_PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[2]]
        ).to_json().encode("utf-8"),
        _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[3]: MutationInventory.from_dict(
            documents[_PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[3]]
        ).to_json().encode("utf-8"),
        SOURCE_TRANSITION_PATH: phase1_source_transition._canonical(transition).encode(
            "utf-8"
        ),
    }
    return payloads, {
        "assignment_scene_updates": assignment_scene_updates,
        "conditional_region_count": 17,
        "inventory_relocations": inventory_counts,
        "removed_assignments_by_product": {
            product: sorted(rows, key=lambda row: row["id"])
            for product, rows in removed.items()
        },
        "restored_production_predecessors": {
            product: {
                current_sha256: {
                    "historical_predecessor_sha256": historical["retired_sha256"],
                    "row_id": row_id,
                    "successor_sha256": corrected["sha256"],
                }
                for current_sha256, (corrected, row_id, historical) in sorted(
                    rebindings.items()
                )
            }
            for product, rebindings in product_rebindings.items()
        },
        "source_assignment_counts": {
            product: len(rows) for product, rows in by_product.items()
        },
    }


def propose_phase5_product_split_extension(root: Path) -> dict[str, object]:
    """Propose the one final audit/production source-authority split."""
    root = Path(os.path.abspath(root))
    raw_transition = _read_pinned_regular_file(
        root, root / REVIEWED_TRANSITION_PATH, label="reviewed transition authority"
    )
    if hashlib.sha256(raw_transition).hexdigest() != REVIEWED_TRANSITION_SHA256:
        raise Phase2MeasurementError("reviewed transition authority changed")
    transition = json.loads(raw_transition, object_pairs_hook=_strict_object)
    if PHASE5_RELOCATION_EXTENSION_KEY not in transition:
        raise Phase2MeasurementError("Phase 5 relocation predecessor is absent")
    if PHASE5_CLOSURE_EXTENSION_KEY not in transition:
        raise Phase2MeasurementError("Phase 5 closure predecessor is absent")
    if PHASE5_PRODUCT_SPLIT_EXTENSION_KEY in transition:
        raise Phase2MeasurementError("Phase 5 product split extension is already consumed")

    successors, details = _phase5_product_split_successor_payloads(root)
    predecessor_hashes = {
        relative: hashlib.sha256(
            _read_pinned_regular_file(root, root / relative, label="split predecessor")
        ).hexdigest()
        for relative in _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS
    }
    production_artifacts = {
        f"{PRODUCT_ARTIFACTS[product]}{suffix}": hashlib.sha256(
            (root / f"{PRODUCT_ARTIFACTS[product]}{suffix}").read_bytes()
        ).hexdigest()
        for product in PRODUCTION_PRODUCTS
        for suffix in (".gbc", ".map", ".sym")
    }
    extension = {
        **details,
        "predecessor_authority_sha256": predecessor_hashes,
        "previous_transition_sha256": REVIEWED_TRANSITION_SHA256,
        "production_artifact_sha256": dict(sorted(production_artifacts.items())),
        "schema": PHASE5_PRODUCT_SPLIT_EXTENSION_SCHEMA,
        "successor_authority_sha256": {
            relative: hashlib.sha256(payload).hexdigest()
            for relative, payload in successors.items()
        },
        "verifier_normalized_sha256": hashlib.sha256(
            _normalized_verifier_source((root / VERIFIER_PATH).read_bytes())
        ).hexdigest(),
    }
    return {
        "authority_path": REVIEWED_TRANSITION_PATH,
        "extension": extension,
        "reviewed": False,
        "schema": PHASE5_PRODUCT_SPLIT_PROPOSAL_SCHEMA,
    }


def apply_phase5_product_split_extension(root: Path, proposal_path: Path) -> None:
    """Atomically consume one freshly recomputed product-split proposal."""
    root = Path(os.path.abspath(root))
    proposal_path = Path(os.path.abspath(proposal_path))
    proposal_identity = _authority_identity(proposal_path, label="product-split proposal")
    raw_proposal = _read_pinned_regular_file(root, proposal_path, label="product-split proposal")
    parsed = json.loads(raw_proposal, object_pairs_hook=_strict_object)
    if raw_proposal != _canonical_pretty(parsed):
        raise Phase2MeasurementError("Phase 5 product-split proposal is not canonical JSON")
    expected = propose_phase5_product_split_extension(root)
    if parsed != expected:
        raise Phase2MeasurementError("stale or changed Phase 5 product-split proposal")
    extension = parsed["extension"]
    predecessor_hashes = extension.get("predecessor_authority_sha256")
    successor_hashes = extension.get("successor_authority_sha256")
    if (
        not isinstance(predecessor_hashes, Mapping)
        or not isinstance(successor_hashes, Mapping)
        or set(predecessor_hashes) != set(_PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS)
        or set(successor_hashes) != set(_PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS)
    ):
        raise Phase2MeasurementError("Phase 5 product-split authority hashes are malformed")

    transition_path = root / REVIEWED_TRANSITION_PATH
    verifier_path = root / VERIFIER_PATH
    predecessor_paths = {
        **{
            root / relative: predecessor_hashes[relative]
            for relative in _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS
        },
        **{
            root / relative: digest
            for relative, digest in extension["production_artifact_sha256"].items()
        },
        transition_path: extension["previous_transition_sha256"],
    }
    identities: dict[Path, _AuthorityIdentity] = {}
    originals: dict[Path, bytes] = {}
    for path, digest in predecessor_paths.items():
        identities[path] = _authority_identity(path, label="product-split predecessor")
        payload = _read_pinned_regular_file(root, path, label="product-split predecessor")
        if hashlib.sha256(payload).hexdigest() != digest:
            raise Phase2MeasurementError(f"Phase 5 product-split predecessor changed: {path}")
        originals[path] = payload
    identities[verifier_path] = _authority_identity(verifier_path, label="split verifier")
    originals[verifier_path] = _read_pinned_regular_file(
        root, verifier_path, label="split verifier"
    )
    if hashlib.sha256(_normalized_verifier_source(originals[verifier_path])).hexdigest() != (
        extension["verifier_normalized_sha256"]
    ):
        raise Phase2MeasurementError("Phase 5 product-split verifier changed")

    successors, _ = _phase5_product_split_successor_payloads(root)
    if {
        relative: hashlib.sha256(payload).hexdigest()
        for relative, payload in successors.items()
    } != dict(successor_hashes):
        raise Phase2MeasurementError("Phase 5 product-split successor hashes changed")
    if _authority_identity(proposal_path, label="product-split proposal") != proposal_identity:
        raise Phase2MeasurementError("Phase 5 product-split proposal changed during recomputation")
    for path, identity in identities.items():
        if _authority_identity(path, label="product-split pinned authority") != identity:
            raise Phase2MeasurementError(
                f"Phase 5 product-split authority changed during recomputation: {path}"
            )

    reviewed = json.loads(originals[transition_path], object_pairs_hook=_strict_object)
    reviewed[PHASE5_PRODUCT_SPLIT_EXTENSION_KEY] = extension
    reviewed_payload = _canonical_pretty(reviewed)
    reviewed_digest = hashlib.sha256(reviewed_payload).hexdigest()
    verifier_payload, replacements = _TRANSITION_DIGEST_CARRIER.subn(
        f'REVIEWED_TRANSITION_SHA256 = (\n    "{reviewed_digest}"\n)'.encode(),
        originals[verifier_path],
    )
    if replacements != 1:
        raise Phase2MeasurementError("reviewed transition digest carrier changed")
    updates = {
        **{root / relative: payload for relative, payload in successors.items()},
        transition_path: reviewed_payload,
        verifier_path: verifier_payload,
    }
    publications: list[_PublishedAuthority] = []
    try:
        for path, payload in updates.items():
            identities[path] = _atomic_replace(
                path,
                payload,
                identities[path],
                publications,
                expected_sha256=hashlib.sha256(originals[path]).hexdigest(),
            )
        DiscoveryAssignmentAuthority.load(root / _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[0])
        WriterInventory.load(root / _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[1])
        SceneInventory.load(root / _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[2])
        MutationInventory.load(root / _PHASE5_PRODUCT_SPLIT_AUTHORITY_PATHS[3])
        if phase1_source_transition.generate(root) != json.loads(
            (root / SOURCE_TRANSITION_PATH).read_text(), object_pairs_hook=_strict_object
        ):
            raise Phase2MeasurementError("published Phase 1 source transition is not canonical")
        for relative, expected_digest in extension[
            "production_artifact_sha256"
        ].items():
            artifact = root / relative
            payload = _read_pinned_regular_file(
                root, artifact, label="Phase 5 product-split production artifact"
            )
            if hashlib.sha256(payload).hexdigest() != expected_digest or (
                _authority_identity(
                    artifact, label="Phase 5 product-split production artifact"
                )
                != identities[artifact]
            ):
                raise Phase2MeasurementError(
                    f"Phase 5 product-split production artifact changed during apply: {relative}"
                )
        for publication in publications:
            _validate_publication(publication)
    except Exception as exc:
        rollback_errors = []
        for publication in reversed(publications):
            try:
                identities[publication.path] = _restore_publication(publication)
            except (OSError, Phase2MeasurementError) as rollback_exc:
                rollback_errors.append(f"{publication.path}: {rollback_exc}")
        if rollback_errors:
            raise Phase2MeasurementError(
                "Phase 5 product-split transaction failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise Phase2MeasurementError(
            f"Phase 5 product-split transaction failed: {exc}; original authorities "
            "restored in their pinned parents; the public namespace remains refused"
        ) from exc
    else:
        _finalize_publications(publications)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    outputs = parser.add_mutually_exclusive_group(required=True)
    outputs.add_argument("--output", type=Path)
    outputs.add_argument("--proposal-output", type=Path)
    outputs.add_argument("--apply-proposal", type=Path)
    outputs.add_argument("--transition-proposal-output", type=Path)
    outputs.add_argument("--apply-transition-proposal", type=Path)
    outputs.add_argument("--phase5-relocation-proposal-output", type=Path)
    outputs.add_argument("--apply-phase5-relocation-proposal", type=Path)
    outputs.add_argument("--phase5-closure-proposal-output", type=Path)
    outputs.add_argument("--apply-phase5-closure-proposal", type=Path)
    outputs.add_argument("--phase5-product-split-proposal-output", type=Path)
    outputs.add_argument("--apply-phase5-product-split-proposal", type=Path)
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
        if args.apply_phase5_product_split_proposal is not None:
            if args.verify or not args.authority_reviewed or args.target is not None:
                raise Phase2MeasurementError(
                    "applying a Phase 5 product-split proposal requires --authority-reviewed"
                )
            apply_phase5_product_split_extension(
                args.root, args.apply_phase5_product_split_proposal
            )
        elif args.phase5_product_split_proposal_output is not None:
            if args.verify or args.authority_reviewed or args.target is not None:
                raise Phase2MeasurementError(
                    "review/verify/target flags do not apply to Phase 5 proposals"
                )
            proposal = propose_phase5_product_split_extension(args.root)
            args.phase5_product_split_proposal_output.parent.mkdir(
                parents=True, exist_ok=True
            )
            args.phase5_product_split_proposal_output.write_bytes(
                _canonical_pretty(proposal)
            )
        elif args.apply_phase5_closure_proposal is not None:
            if args.verify or not args.authority_reviewed or args.target is not None:
                raise Phase2MeasurementError(
                    "applying a Phase 5 closure proposal requires --authority-reviewed"
                )
            apply_phase5_closure_extension(args.root, args.apply_phase5_closure_proposal)
        elif args.phase5_closure_proposal_output is not None:
            if args.verify or args.authority_reviewed or args.target is not None:
                raise Phase2MeasurementError(
                    "review/verify/target flags do not apply to Phase 5 proposals"
                )
            proposal = propose_phase5_closure_extension(args.root)
            args.phase5_closure_proposal_output.parent.mkdir(parents=True, exist_ok=True)
            args.phase5_closure_proposal_output.write_bytes(_canonical_pretty(proposal))
        elif args.apply_phase5_relocation_proposal is not None:
            if args.verify or not args.authority_reviewed or args.target is not None:
                raise Phase2MeasurementError(
                    "applying a Phase 5 relocation proposal requires "
                    "--authority-reviewed"
                )
            apply_phase5_relocation_extension(
                root=args.root,
                proposal_path=args.apply_phase5_relocation_proposal,
            )
        elif args.phase5_relocation_proposal_output is not None:
            if args.verify or args.authority_reviewed or args.target is not None:
                raise Phase2MeasurementError(
                    "review/verify/target flags do not apply to Phase 5 proposals"
                )
            proposal = propose_phase5_relocation_extension(args.root)
            args.phase5_relocation_proposal_output.parent.mkdir(
                parents=True, exist_ok=True
            )
            args.phase5_relocation_proposal_output.write_bytes(
                _canonical_pretty(proposal)
            )
        elif args.apply_transition_proposal is not None:
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

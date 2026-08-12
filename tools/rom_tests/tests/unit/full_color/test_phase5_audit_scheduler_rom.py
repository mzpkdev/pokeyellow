"""Real-ROM proofs for the audit-only Phase 5 pressure checkpoints."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from tools.rom_tests.emulator import Emulator
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT, result_directory
from tools.rom_tests.tests.unit.full_color.test_phase2_scheduler_rom import (
    Phase2Rom,
    numeric_symbols,
    phase2_rom,
)


PRODUCTION_PRODUCTS = ("pokeyellow", "pokeyellow_debug", "pokeyellow_vc")
MUTABLE_BOUNDARIES = (
    "FULL_COLOR_PHASE5_BOUNDARY_PREPARATION",
    "FULL_COLOR_PHASE5_BOUNDARY_OWNER_REVALIDATION",
    "FULL_COLOR_PHASE5_BOUNDARY_GENERATION_REVALIDATION",
    "FULL_COLOR_PHASE5_BOUNDARY_DESTINATION_REVALIDATION",
    "FULL_COLOR_PHASE5_BOUNDARY_BUDGET_REVALIDATION",
)
FAST_CACHE_ROW20X2 = 0x2D
FAST_CACHE_COLUMN2X18 = 0x3C
FAST_CACHE_GENERIC = 0x1E
PALLET_TOWN = 0x00
ROUTE_1 = 0x0C


def _call_selected_with_wram2(
    rom: Phase2Rom, symbol: str, **registers: int,
) -> tuple[int, int]:
    emu = rom.emulator.pyboy
    old_bank = emu.memory[0xFF70]
    emu.memory[0xFF70] = 2
    try:
        return rom.call(symbol, **registers)
    finally:
        emu.memory[0xFF70] = old_bank


def test_retry_extent_ignores_fast_writer_staging_clobber(
    phase2_rom: Phase2Rom,
) -> None:
    sentinel = bytes([0xA5]) * 20
    phase2_rom.write_wram2("wFullColorSchedulerEnqueueDescriptor", sentinel)
    phase2_rom.write_wram2("wFullColorProducerWidth", b"\x14")
    phase2_rom.write_wram2("wFullColorProducerHeight", b"\x02")
    phase2_rom.write_wram2(
        "wFullColorRequestStaging", b"\x14\x12\0\x28\x24"
    )

    _, flags = _call_selected_with_wram2(
        phase2_rom, "FullColorPhase5WriteProducerExtentSelected"
    )

    descriptor = phase2_rom.read_wram2(
        "wFullColorSchedulerEnqueueDescriptor", 20
    )
    assert flags & 0x10 == 0
    assert descriptor[:14] == sentinel[:14]
    assert descriptor[14:18] == b"\x28\0\x50\0"
    assert descriptor[18:] == sentinel[18:]


@pytest.mark.parametrize(("width", "height"), ((0, 2), (21, 2), (20, 0), (20, 19)))
def test_retry_extent_rejects_corrupt_producer_geometry_without_partial_write(
    phase2_rom: Phase2Rom, width: int, height: int,
) -> None:
    sentinel = bytes(range(20))
    phase2_rom.write_wram2("wFullColorSchedulerEnqueueDescriptor", sentinel)
    phase2_rom.write_wram2("wFullColorProducerWidth", bytes((width,)))
    phase2_rom.write_wram2("wFullColorProducerHeight", bytes((height,)))

    _, flags = _call_selected_with_wram2(
        phase2_rom, "FullColorPhase5WriteProducerExtentSelected"
    )

    assert flags & 0x10
    assert phase2_rom.read_wram2(
        "wFullColorSchedulerEnqueueDescriptor", 20
    ) == sentinel


@pytest.mark.parametrize(
    ("source_delta", "expected"),
    (
        (-1, b"\xa1\xd4\xd5"),
        (0, b"\xd4\xd5\xd6"),
        (1, b"\xc3\xc4\xc5"),
    ),
)
def test_generic_plane_writer_switches_source_only_at_exact_scratch_boundary(
    phase2_rom: Phase2Rom, source_delta: int, expected: bytes,
) -> None:
    boundary = phase2_rom.emulator.symbols["wFullColorAttributeRectangle"]
    shadow = phase2_rom.emulator.symbols["wFullColorShadowOAMBatch"]
    phase2_rom.write_wram2(
        "wFullColorRequestStaging", bytes((len(expected), 1, 1, 0, 0))
    )
    phase2_rom.write_wram2("wFullColorTimingState", b"\x98\0\0\0")
    phase2_rom.write_wram2(
        "wFullColorAttributeRectangle", b"\xb2\xc3\xc4\xc5"
    )
    phase2_rom.write_wram2("wFullColorShadowOAMBatch", b"\xd4\xd5\xd6")
    phase2_rom.write_wram2(
        "wFullColorAttributeRectangle", b"\xb2\xc3\xc4\xc5"
    )
    phase2_rom.write_wram2(
        "wFullColorBGPaletteBase", b"\0" * 255 + b"\xa1"
    )
    phase2_rom.emulator.pyboy.memory[0xFF4F] = 0

    _call_selected_with_wram2(
        phase2_rom,
        "CommitFullColorPhase5MapPlaneSelected",
        de=boundary + source_delta,
        hl=0x9800,
    )

    assert phase2_rom.emulator.read_vram_bank(0, 0x9800, len(expected)) == expected
    assert shadow == boundary + 360


def _cached_superseded_row(rom: Phase2Rom) -> bytes:
    generation = rom.read_wram2("wRendererGeneration", 4)
    return bytes((
        rom.constants["PREPARED"] << 4
        | rom.constants["FULL_COLOR_REQUEST_MAP_ROW_PAIRED"],
        rom.constants["RENDERER_FULL_COLOR_OVERWORLD"],
    )) + generation + bytes.fromhex("d89bf9d314020600280050000800")


@pytest.mark.parametrize(
    "mutation",
    (
        "none",
        "wrong_class",
        "owner",
        "generation",
        "destination",
        "same_map",
        "authority_map",
        "unrelated_row",
        "producer_width",
        "same_destination",
    ),
)
def test_connection_retry_retires_only_exact_superseded_movement(
    phase2_rom: Phase2Rom, mutation: str,
) -> None:
    descriptor = bytearray(_cached_superseded_row(phase2_rom))
    if mutation == "unrelated_row":
        descriptor[18] = 0
    snapshot = bytes(descriptor)
    if mutation == "owner":
        descriptor[1] ^= 1
    elif mutation == "generation":
        descriptor[2] ^= 1
    elif mutation == "destination":
        descriptor[6] ^= 1
    phase2_rom.write_wram2("wFullColorRequestDescriptors", bytes(descriptor))
    phase2_rom.write_wram2("wFullColorRequestCount", b"\x01")
    phase2_rom.write_wram2("wFullColorPhase5FastCacheValid", bytes((FAST_CACHE_GENERIC,)))
    phase2_rom.write_wram2(
        "wFullColorPhase5FastCacheDescriptor",
        phase2_rom.emulator.symbols["wFullColorRequestDescriptors"].to_bytes(2, "little"),
    )
    phase2_rom.write_wram2("wFullColorPhase5FastCacheSnapshot", snapshot)
    phase2_rom.write_wram2("wFullColorPhase5FastCacheRequiredCycles", b"\xff\xff")
    producer_class = (
        phase2_rom.constants["FULL_COLOR_REQUEST_MAP_ROW_PAIRED"]
        if mutation == "wrong_class"
        else phase2_rom.constants["FULL_COLOR_REQUEST_MAP_CONNECTION_PAIRED"]
    )
    phase2_rom.write_wram2("wFullColorProducerClass", bytes((producer_class,)))
    phase2_rom.write_wram2("wFullColorProducerPending", 1)
    phase2_rom.write_wram2(
        "wFullColorProducerDestination",
        (0x9BD8 if mutation == "same_destination" else 0x991C).to_bytes(
            2, "little"
        ),
    )
    phase2_rom.write_wram2(
        "wFullColorProducerWidth", 19 if mutation == "producer_width" else 20
    )
    phase2_rom.write_wram2("wFullColorProducerHeight", 2)
    phase2_rom.write_wram2("wFullColorProducerFlags", 0)
    phase2_rom.write_wram2(
        "wFullColorAuthorityMap",
        ROUTE_1 if mutation == "authority_map" else PALLET_TOWN,
    )
    old_bank = phase2_rom.emulator.pyboy.memory[0xFF70]
    phase2_rom.emulator.pyboy.memory[0xFF70] = 1
    try:
        phase2_rom.emulator.pyboy.memory[
            phase2_rom.emulator.symbols["wCurMap"]
        ] = PALLET_TOWN if mutation == "same_map" else ROUTE_1
    finally:
        phase2_rom.emulator.pyboy.memory[0xFF70] = old_bank
    phase2_rom.write_wram2("wFullColorTransitionCount", 0)
    before_vram = (
        phase2_rom.emulator.read_vram_bank(0, 0x9BD8, 40),
        phase2_rom.emulator.read_vram_bank(1, 0x9BD8, 40),
    )

    _call_selected_with_wram2(
        phase2_rom, "RetireFullColorPhase5SupersededMovementSelected"
    )

    live = phase2_rom.read_wram2("wFullColorRequestDescriptors", 20)
    if mutation == "none":
        assert live[0] >> 4 == phase2_rom.constants["CANCELLED"]
        assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\0"
        assert phase2_rom.read_wram2("wFullColorPhase5FastCacheValid") == b"\0"
        assert phase2_rom.read_wram2("wFullColorTransitionCount") == b"\x01"
        assert phase2_rom.read_wram2("wFullColorTransitionLog") == bytes((
            phase2_rom.constants["CANCELLED"],
        ))
    else:
        assert live == bytes(descriptor)
        assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x01"
        assert phase2_rom.read_wram2(
            "wFullColorPhase5FastCacheValid"
        ) == bytes((FAST_CACHE_GENERIC,))
    assert phase2_rom.emulator.read_vram_bank(0, 0x9BD8, 40) == before_vram[0]
    assert phase2_rom.emulator.read_vram_bank(1, 0x9BD8, 40) == before_vram[1]


def test_connection_supersession_is_reachable_only_from_exact_north_scene() -> None:
    callsites: list[tuple[Path, int]] = []
    for path in REPOSITORY_ROOT.rglob("*.asm"):
        count = path.read_text(encoding="utf-8").count(
            "call EnqueueFullColorMapConnection"
        )
        if count:
            callsites.append((path.relative_to(REPOSITORY_ROOT), count))
    assert callsites == [(Path("home/overworld.asm"), 1)]

    source = (REPOSITORY_ROOT / "home/overworld.asm").read_text(
        encoding="utf-8"
    )
    north = source.split("FullColorAuditScheduleNorthRow:", 1)[1].split(
        "FullColorAuditScheduleMovementRow:", 1
    )[0]
    exact_scene = (
        "ld a, [wCurMap]\n"
        "\tcp PALLET_TOWN\n"
        "\tjr nz, .movement\n"
        "\tld a, [wYCoord]\n"
        "\tand a\n"
        "\tjr nz, .movement"
    )
    assert exact_scene in north
    assert north.index(exact_scene) < north.index(
        "call EnqueueFullColorMapConnection"
    )


def _arm_pressure(
    rom: Phase2Rom, boundary: str, *, available_cycles: int, required_cycles: int,
) -> None:
    rom.call("FullColorPhase5StressReset")
    rom.write_wram2(
        "wFullColorPhase5StressStateStart",
        bytes((
            rom.constants["FULL_COLOR_PHASE5_STRESS_MODE_ARMED"],
            rom.constants["FULL_COLOR_REQUEST_MAP_ROW_PAIRED"],
            rom.constants[boundary],
        ))
        + available_cycles.to_bytes(2, "little")
        + required_cycles.to_bytes(2, "little")
        + bytes(4),
    )


def _admit_one_cell_pair(rom: Phase2Rom) -> None:
    rom.write_fixed(0xC900, b"\x41\x06")
    result, flags = rom.admit(rom.descriptor(
        "FULL_COLOR_REQUEST_MAP_ROW_PAIRED",
        destination=0x9800,
        source=0xC900,
        desired=0x0101,
        extent=1,
        reservation=2,
    ))
    assert result == rom.constants["ACCEPTED"]
    assert flags & 0x10 == 0


@pytest.mark.parametrize("boundary", MUTABLE_BOUNDARIES)
def test_exact_fit_completes_one_paired_unit_at_every_mutable_boundary(
    phase2_rom: Phase2Rom, boundary: str,
) -> None:
    _admit_one_cell_pair(phase2_rom)
    _arm_pressure(
        phase2_rom, boundary, available_cycles=100, required_cycles=100,
    )
    phase2_rom.write_wram2("wFullColorCommitBudget", b"\0\0")

    result, flags = phase2_rom.call("FullColorPhase5StressCheckpointSelected")

    assert result == phase2_rom.constants["FULL_COLOR_PHASE5_TERMINAL_COMPLETE"]
    assert flags & 0x10 == 0
    assert phase2_rom.read_wram2("wFullColorPhase5StressReachedMask") == bytes((
        phase2_rom.constants["FULL_COLOR_PHASE5_REACHED_BOUNDARY_MASK"],
    ))
    assert phase2_rom.read_wram2("wFullColorPhase5StressDeferredMask", 3) == b"\0\0\x01"
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\0"
    assert phase2_rom.emulator.read_vram_bank(0, 0x9800, 1) == b"\x41"
    assert phase2_rom.emulator.read_vram_bank(1, 0x9800, 1) == b"\x06"
    assert phase2_rom.read_wram2("wFullColorTransitionLog", 4) == bytes(
        phase2_rom.constants[name]
        for name in ("PENDING", "PREPARED", "COMMITTING", "COMPLETE")
    )
    assert phase2_rom.read_wram2("wFullColorDebugTraceCountPhase2") == b"\x06"
    assert phase2_rom.read_wram2("wFullColorCommitBudget", 2) == b"\0\0"
    trace = phase2_rom.read_wram2("wFullColorDebugTracePhase2", 24)
    assert trace[17:21] == b"\x64\0\x64\0"


@pytest.mark.parametrize("boundary", MUTABLE_BOUNDARIES)
def test_threshold_plus_one_defers_unchanged_then_exact_budget_completes(
    phase2_rom: Phase2Rom, boundary: str,
) -> None:
    _admit_one_cell_pair(phase2_rom)
    _arm_pressure(
        phase2_rom, boundary, available_cycles=99, required_cycles=100,
    )
    phase2_rom.write_wram2("wFullColorCommitBudget", b"\x34\x12")
    before_tiles = phase2_rom.emulator.read_vram_bank(0, 0x9800, 1)
    before_attributes = phase2_rom.emulator.read_vram_bank(1, 0x9800, 1)

    result, flags = phase2_rom.call("FullColorPhase5StressCheckpointSelected")

    assert result == phase2_rom.constants["FULL_COLOR_PHASE5_TERMINAL_DEFERRED"]
    assert flags & 0x10
    descriptor = phase2_rom.read_wram2("wFullColorRequestDescriptors", 20)
    assert descriptor[0] >> 4 == phase2_rom.constants["PREPARED"]
    frozen = phase2_rom.read_wram2("wFullColorAttributeRectangle", 2)
    retry = phase2_rom.read_wram2("wFullColorRetryCounter")
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x01"
    assert phase2_rom.emulator.read_vram_bank(0, 0x9800, 1) == before_tiles
    assert phase2_rom.emulator.read_vram_bank(1, 0x9800, 1) == before_attributes
    assert phase2_rom.read_wram2("wFullColorPhase5StressReachedMask") == bytes((
        (1 << (phase2_rom.constants[boundary] + 1)) - 1,
    ))
    assert phase2_rom.read_wram2("wFullColorPhase5StressDeferredMask") == bytes((
        1 << phase2_rom.constants[boundary],
    ))
    assert phase2_rom.read_wram2("wFullColorTransitionLog", 2) == bytes((
        phase2_rom.constants["PENDING"], phase2_rom.constants["PREPARED"],
    ))
    assert phase2_rom.read_wram2("wFullColorCommitBudget", 2) == b"\x34\x12"

    # The retry must consume the frozen preparation, not changed producer bytes.
    phase2_rom.write_fixed(0xC900, b"\xee\xff")
    phase2_rom.write_wram2("wFullColorPhase5StressAvailableCycles", b"\x64\0")
    result, flags = phase2_rom.call("FullColorPhase5StressCheckpointSelected")
    assert result == phase2_rom.constants["FULL_COLOR_PHASE5_TERMINAL_COMPLETE"]
    assert flags & 0x10 == 0
    assert phase2_rom.read_wram2("wFullColorRetryCounter") == retry
    assert phase2_rom.read_wram2("wFullColorAttributeRectangle", 2) == frozen
    assert phase2_rom.read_wram2("wFullColorCommitBudget", 2) == b"\x34\x12"
    assert phase2_rom.emulator.read_vram_bank(0, 0x9800, 1) == b"\x41"
    assert phase2_rom.emulator.read_vram_bank(1, 0x9800, 1) == b"\x06"


@pytest.mark.parametrize(
    ("available", "required", "deferred"),
    ((100, 100, False), (99, 100, True)),
)
def test_passive_selected_checkpoint_uses_only_independent_cycle_authority(
    phase2_rom: Phase2Rom, available: int, required: int, deferred: bool,
) -> None:
    boundary_name = "FULL_COLOR_PHASE5_BOUNDARY_OWNER_REVALIDATION"
    _arm_pressure(
        phase2_rom,
        boundary_name,
        available_cycles=available,
        required_cycles=required,
    )
    phase2_rom.write_wram2("wFullColorCommitBudget", b"\x34\x12")
    phase2_rom.emulator.pyboy.memory[0xFF70] = 2
    registers = phase2_rom.emulator.pyboy.register_file

    _, flags = phase2_rom.call(
        "FullColorPhase5AuditCycleCheckpointSelected",
        a=phase2_rom.constants[boundary_name],
        b=0x12,
        c=0x34,
        de=0x5678,
        hl=0x9ABC,
    )

    assert bool(flags & 0x10) is deferred
    assert (
        registers.B,
        registers.C,
        registers.D << 8 | registers.E,
        registers.HL,
    ) == (
        0x12, 0x34, 0x5678, 0x9ABC,
    )
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\0"
    assert phase2_rom.read_wram2("wFullColorCommitBudget", 2) == b"\x34\x12"
    assert phase2_rom.read_wram2("wFullColorPhase5StressReachedMask") == b"\x02"
    expected_mask = b"\x02" if deferred else b"\0"
    assert phase2_rom.read_wram2("wFullColorPhase5StressDeferredMask") == expected_mask
    expected_terminal = (
        phase2_rom.constants["FULL_COLOR_PHASE5_TERMINAL_DEFERRED"]
        if deferred else phase2_rom.constants["FULL_COLOR_PHASE5_TERMINAL_NONE"]
    )
    assert phase2_rom.read_wram2("wFullColorPhase5StressTerminalResult") == bytes((
        expected_terminal,
    ))


def _linked_symbol(sym: Path, name: str) -> tuple[int, int]:
    pattern = re.compile(rf"^([0-9a-fA-F]+):([0-9a-fA-F]+) {re.escape(name)}$")
    for line in sym.read_text(encoding="utf-8").splitlines():
        match = pattern.fullmatch(line)
        if match:
            return int(match.group(1), 16), int(match.group(2), 16)
    raise AssertionError(f"missing linked symbol {name}")


def test_destination_boundary_revalidates_resources_exactly_once() -> None:
    source = (
        REPOSITORY_ROOT / "engine/full_color/phase5_audit.asm"
    ).read_text(encoding="utf-8")
    body = source.split(
        "FullColorPhase5BoundaryDestinationRevalidation::", 1
    )[1].split("FullColorPhase5BoundaryBudgetRevalidation::", 1)[0]
    assert body.count("call ValidateFullColorRequestResourcesSelected") == 1


def test_paired_class_bridge_uses_audit_only_interrupt_stable_fixed_scratch() -> None:
    asm_sources = list(REPOSITORY_ROOT.rglob("*.asm"))
    references = {
        path.relative_to(REPOSITORY_ROOT): path.read_text(encoding="utf-8").count(
            "wFullColorPhase5PairedClassScratch"
        )
        for path in asm_sources
    }
    assert {path: count for path, count in references.items() if count} == {
        Path("engine/full_color/scheduler.asm"): 2,
        Path("ram/wram.asm"): 1,
    }
    scheduler = (
        REPOSITORY_ROOT / "engine/full_color/scheduler.asm"
    ).read_text(encoding="utf-8")
    bridge = scheduler.split("EnqueueFullColorPairedSemantic:", 1)[1].split(
        ".flags_ready", 1
    )[0]
    assert "push af" not in bridge
    assert bridge.index("ld [wFullColorPhase5PairedClassScratch], a") < bridge.index(
        "select_renderer_state_e"
    ) < bridge.index("ld a, [wFullColorPhase5PairedClassScratch]")

    audit_sym = REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym"
    assert _linked_symbol(
        audit_sym, "wFullColorPhase5PairedClassScratch"
    ) == _linked_symbol(audit_sym, "wUnusedCreditsByte")
    for product in PRODUCTION_PRODUCTS:
        symbols = (REPOSITORY_ROOT / f"{product}.sym").read_text(encoding="utf-8")
        assert "wFullColorPhase5PairedClassScratch" not in symbols


def test_hostile_shadow_epoch_mutation_blocks_retained_oam_publication(
    phase2_rom: Phase2Rom,
) -> None:
    epoch = 7
    descriptor = bytearray(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA",
        source=phase2_rom.emulator.symbols["wShadowOAM"],
        flags=phase2_rom.constants["FULL_COLOR_FLAG_OAM_FINISHED"],
    ))
    descriptor[0] |= phase2_rom.constants["COMPLETE"] << 4
    descriptor[19] = epoch
    phase2_rom.write_wram2("wFullColorRequestDescriptors", descriptor)
    phase2_rom.write_wram2("wFullColorRequestCursor", 0)
    phase2_rom.write_wram2("wFullColorPhase5OAMAuthorityEpoch", epoch)
    phase2_rom.write_wram2(
        "wFullColorPhase5ScenarioControl",
        phase2_rom.constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
    )
    shadow = phase2_rom.emulator.symbols["wShadowOAM"]
    phase2_rom.write_fixed(shadow, b"\x11" * 160)
    for offset in range(160):
        phase2_rom.emulator.pyboy.memory[0xFE00 + offset] = 0x5A

    # A matching COMPLETE certificate permits a writer-free retained frame.
    phase2_rom.call("RunFullColorPhase5CachedVBlank")
    assert bytes(
        phase2_rom.emulator.pyboy.memory[0xFE00 + offset]
        for offset in range(160)
    ) == b"\x5a" * 160
    assert phase2_rom.read_wram2("wFullColorPhase5ScenarioState") != bytes((
        phase2_rom.constants["FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED"],
    ))

    # A hostile writer changes both the batch and its explicit authority epoch.
    # The stale certificate must fail closed without a DMA or any other public
    # write, rather than silently retaining authority for the changed shadow.
    phase2_rom.write_fixed(shadow, b"\xee" + b"\x11" * 159)
    phase2_rom.write_wram2("wFullColorPhase5OAMAuthorityEpoch", epoch + 1)
    phase2_rom.call("RunFullColorPhase5CachedVBlank")

    assert bytes(
        phase2_rom.emulator.pyboy.memory[0xFE00 + offset]
        for offset in range(160)
    ) == b"\x5a" * 160
    assert phase2_rom.read_wram2("wFullColorPhase5ScenarioResult") == bytes((
        phase2_rom.constants["FULL_COLOR_PHASE5_SCENARIO_RESULT_FAILED"],
    ))
    assert phase2_rom.read_wram2("wFullColorPhase5ScenarioState") == bytes((
        phase2_rom.constants["FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED"],
    ))


def test_fresh_owned_oam_revalidates_exact_shadow_source_once_before_dma(
    phase2_rom: Phase2Rom,
) -> None:
    """A hostile source mutation cannot DMA or replay a fresh declaration."""
    epoch = 13
    shadow = phase2_rom.emulator.symbols["wShadowOAM"]
    descriptor = bytearray(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA",
        source=shadow,
        flags=phase2_rom.constants["FULL_COLOR_FLAG_OAM_FINISHED"],
    ))
    descriptor[0] |= phase2_rom.constants["PREPARED"] << 4
    descriptor[19] = epoch
    phase2_rom.write_wram2("wFullColorRequestDescriptors", descriptor)
    phase2_rom.write_wram2("wFullColorRequestCursor", 0)
    phase2_rom.write_wram2("wFullColorRequestCount", 1)
    phase2_rom.write_wram2("wFullColorPhase5OAMAuthorityEpoch", epoch)
    phase2_rom.write_wram2(
        "wFullColorPhase5ScenarioControl",
        phase2_rom.constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
    )
    phase2_rom.write_fixed(shadow, bytes(range(160)))
    for offset in range(160):
        phase2_rom.emulator.pyboy.memory[0xFE00 + offset] = 0x5A

    # Mutate only the resident declaration after the producer-finished shadow
    # exists. The final source-identity check must reject it before hDMA.
    descriptor[8] ^= 1
    phase2_rom.write_wram2("wFullColorRequestDescriptors", descriptor)
    dma_calls = [0]

    def record_dma(_: object) -> None:
        dma_calls[0] += 1

    key = (
        phase2_rom.emulator.symbol_banks["FullColorPhase5OAMDMAStart"],
        phase2_rom.emulator.symbols["FullColorPhase5OAMDMAStart"],
    )
    phase2_rom.emulator.pyboy.hook_register(*key, record_dma, None)
    try:
        phase2_rom.emulator.pyboy.memory[0xFF70] = 2
        phase2_rom.call("RunFullColorPhase5CachedVBlankSelected")
        phase2_rom.call("RunFullColorPhase5CachedVBlankSelected")
    finally:
        phase2_rom.emulator.pyboy.hook_deregister(*key)
        phase2_rom.emulator.pyboy.memory[0xFF70] = 1

    assert dma_calls == [0]
    assert bytes(
        phase2_rom.emulator.pyboy.memory[0xFE00 + offset]
        for offset in range(160)
    ) == b"\x5a" * 160
    assert phase2_rom.read_wram2("wFullColorRequestDescriptors")[0] >> 4 == (
        phase2_rom.constants["CANCELLED"]
    )
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\0"
    assert phase2_rom.read_wram2("wFullColorPhase5ScenarioState") == bytes((
        phase2_rom.constants["FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED"],
    ))


@pytest.mark.parametrize("mutation", ("kind", "geometry", "destination"))
def test_hostile_canonical_kind_certificate_mutation_cancels_before_visibility(
    phase2_rom: Phase2Rom, mutation: str,
) -> None:
    """The mutable fast kind never grants partial canonical-writer authority."""
    epoch = 5
    oam = bytearray(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA",
        source=phase2_rom.emulator.symbols["wShadowOAM"],
        flags=phase2_rom.constants["FULL_COLOR_FLAG_OAM_FINISHED"],
    ))
    oam[0] |= phase2_rom.constants["COMPLETE"] << 4
    oam[19] = epoch
    paired = bytearray(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_MAP_ROW_PAIRED",
        destination=0x9800,
        source=0xC900,
        desired=0x0214,
        extent=40,
        reservation=80,
    ))
    paired[0] |= phase2_rom.constants["PREPARED"] << 4
    phase2_rom.write_wram2("wFullColorRequestDescriptors", oam + paired)
    phase2_rom.write_wram2("wFullColorRequestCursor", 0)
    phase2_rom.write_wram2("wFullColorRequestCount", 1)
    phase2_rom.write_wram2("wFullColorPhase5OAMAuthorityEpoch", epoch)
    phase2_rom.write_wram2("wFullColorAvailableResources", b"\xff\xff")
    phase2_rom.emulator.pyboy.memory[0xFF70] = 2
    phase2_rom.call("CacheFullColorPhase5PreparedNonOAMSelected")
    assert phase2_rom.read_wram2("wFullColorPhase5FastCacheValid") == bytes((
        FAST_CACHE_ROW20X2,
    ))

    if mutation == "kind":
        phase2_rom.write_wram2(
            "wFullColorPhase5FastCacheValid",
            FAST_CACHE_COLUMN2X18,
        )
    elif mutation == "geometry":
        # Keep the exact extent and derived cycle certificate unchanged. A
        # 20x3 geometry must still lose its 20x2 canonical-writer authority.
        phase2_rom.write_wram2(
            "wFullColorPhase5FastCacheSnapshot", bytes(paired[:11] + b"\x03" + paired[12:])
        )
        phase2_rom.write_wram2(
            "wFullColorRequestDescriptors",
            oam + paired[:11] + b"\x03" + paired[12:],
        )
    else:
        # $9bcd would cross the 1 KiB map-plane boundary for the certified row.
        paired[6:8] = b"\xcd\x9b"
        phase2_rom.write_wram2("wFullColorPhase5FastCacheSnapshot", paired)
        phase2_rom.write_wram2("wFullColorRequestDescriptors", oam + paired)

    before_tiles = phase2_rom.emulator.read_vram_bank(0, 0x9800, 40)
    before_attributes = phase2_rom.emulator.read_vram_bank(1, 0x9800, 40)
    phase2_rom.emulator.pyboy.memory[0xFF70] = 2
    phase2_rom.call("RunFullColorPhase5CachedVBlankSelected")

    cancelled = phase2_rom.read_wram2(
        "wFullColorRequestDescriptors", 40
    )[20]
    assert cancelled >> 4 == phase2_rom.constants["CANCELLED"]
    assert phase2_rom.read_wram2("wFullColorPhase5FastCacheValid") == b"\0"
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\0"
    assert phase2_rom.emulator.read_vram_bank(0, 0x9800, 40) == before_tiles
    assert phase2_rom.emulator.read_vram_bank(1, 0x9800, 40) == before_attributes


@pytest.mark.parametrize("destination", (0x9C00, 0x9BFF, 0x9BD0))
def test_uncertified_column_destination_defers_before_committing(
    phase2_rom: Phase2Rom, destination: int,
) -> None:
    """A safe generic fallback must not inherit the canonical cycle budget."""
    epoch = 9
    oam = bytearray(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA",
        source=phase2_rom.emulator.symbols["wShadowOAM"],
        flags=phase2_rom.constants["FULL_COLOR_FLAG_OAM_FINISHED"],
    ))
    oam[0] |= phase2_rom.constants["COMPLETE"] << 4
    oam[19] = epoch
    column = bytearray(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED",
        destination=destination,
        source=0xC900,
        desired=0x1202,
        extent=36,
        reservation=72,
    ))
    column[0] |= phase2_rom.constants["PREPARED"] << 4
    phase2_rom.write_wram2("wFullColorRequestDescriptors", oam + column)
    phase2_rom.write_wram2("wFullColorRequestCursor", 0)
    phase2_rom.write_wram2("wFullColorRequestCount", 1)
    phase2_rom.write_wram2("wFullColorPhase5OAMAuthorityEpoch", epoch)
    phase2_rom.write_wram2("wFullColorAvailableResources", b"\xff\xff")
    phase2_rom.emulator.pyboy.memory[0xFF70] = 2
    phase2_rom.call("CacheFullColorPhase5PreparedNonOAMSelected")
    assert phase2_rom.read_wram2("wFullColorPhase5FastCacheValid") == bytes((
        FAST_CACHE_GENERIC,
    ))
    assert phase2_rom.read_wram2(
        "wFullColorPhase5FastCacheRequiredCycles", 2
    ) == b"\xff\xff"
    before_tiles = phase2_rom.emulator.read_vram_bank(0, 0x9800, 0x800)
    before_attributes = phase2_rom.emulator.read_vram_bank(1, 0x9800, 0x800)

    phase2_rom.emulator.pyboy.memory[0xFF70] = 2
    phase2_rom.call("RunFullColorPhase5CachedVBlankSelected")

    resident = phase2_rom.read_wram2("wFullColorRequestDescriptors", 40)[20:]
    assert resident[0] >> 4 == phase2_rom.constants["PREPARED"]
    assert phase2_rom.read_wram2("wFullColorPhase5FastCacheValid") == bytes((
        FAST_CACHE_GENERIC,
    ))
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x01"
    assert phase2_rom.emulator.read_vram_bank(0, 0x9800, 0x800) == before_tiles
    assert phase2_rom.emulator.read_vram_bank(1, 0x9800, 0x800) == before_attributes


def test_certified_column_writer_publishes_exact_2x18_no_wrap_batch(
    phase2_rom: Phase2Rom,
) -> None:
    epoch = 11
    destination = 0x9856
    oam = bytearray(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA",
        source=phase2_rom.emulator.symbols["wShadowOAM"],
        flags=phase2_rom.constants["FULL_COLOR_FLAG_OAM_FINISHED"],
    ))
    oam[0] |= phase2_rom.constants["COMPLETE"] << 4
    oam[19] = epoch
    column = bytearray(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED",
        destination=destination,
        source=0xC900,
        desired=0x1202,
        extent=36,
        reservation=72,
    ))
    column[0] |= phase2_rom.constants["PREPARED"] << 4
    tiles = bytes(range(0x20, 0x20 + 36))
    attributes = bytes(range(0x80, 0x80 + 36))
    phase2_rom.write_wram2("wFullColorAttributeRectangle", tiles)
    phase2_rom.write_wram2("wFullColorBGPaletteBase", attributes)
    phase2_rom.write_wram2("wFullColorRequestDescriptors", oam + column)
    phase2_rom.write_wram2("wFullColorRequestCursor", 0)
    phase2_rom.write_wram2("wFullColorRequestCount", 1)
    phase2_rom.write_wram2("wFullColorPhase5OAMAuthorityEpoch", epoch)
    phase2_rom.write_wram2("wFullColorAvailableResources", b"\xff\xff")
    before_tiles = phase2_rom.emulator.read_vram_bank(0, 0x9800, 0x400)
    before_attributes = phase2_rom.emulator.read_vram_bank(1, 0x9800, 0x400)
    phase2_rom.emulator.pyboy.memory[0xFF70] = 2
    phase2_rom.call("CacheFullColorPhase5PreparedNonOAMSelected")
    assert phase2_rom.read_wram2("wFullColorPhase5FastCacheValid") == bytes((
        FAST_CACHE_COLUMN2X18,
    ))

    phase2_rom.call("RunFullColorPhase5CachedVBlankSelected")

    expected_addresses = [
        0x9800 | ((destination - 0x9800 + row * 32 + column_offset) & 0x3FF)
        for row in range(18)
        for column_offset in range(2)
    ]
    presented_tiles = phase2_rom.emulator.read_vram_bank(0, 0x9800, 0x400)
    presented_attributes = phase2_rom.emulator.read_vram_bank(1, 0x9800, 0x400)
    assert bytes(presented_tiles[address - 0x9800] for address in expected_addresses) == tiles
    assert bytes(
        presented_attributes[address - 0x9800] for address in expected_addresses
    ) == attributes
    assert {
        index for index, (before, after) in enumerate(zip(before_tiles, presented_tiles))
        if before != after
    } == {address - 0x9800 for address in expected_addresses}
    assert {
        index
        for index, (before, after) in enumerate(zip(before_attributes, presented_attributes))
        if before != after
    } == {address - 0x9800 for address in expected_addresses}
    resident = phase2_rom.read_wram2("wFullColorRequestDescriptors", 40)[20]
    assert resident >> 4 == phase2_rom.constants["COMPLETE"]
    assert phase2_rom.read_wram2("wFullColorPhase5FastCacheValid") == bytes((
        phase2_rom.constants["FULL_COLOR_PHASE5_FAST_CACHE_ACCOUNTING_PENDING"],
    ))


def test_hostile_deferred_finalizer_state_cannot_replay_public_unit(
    phase2_rom: Phase2Rom,
) -> None:
    descriptor = bytearray(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_MAP_ROW_PAIRED",
        destination=0x9800,
        source=0xC900,
        desired=0x0214,
        extent=40,
        reservation=80,
    ))
    descriptor[0] |= phase2_rom.constants["COMMITTING"] << 4
    address = phase2_rom.emulator.symbols["wFullColorRequestDescriptors"]
    phase2_rom.write_wram2("wFullColorRequestDescriptors", descriptor)
    phase2_rom.write_wram2("wFullColorRequestCount", 1)
    phase2_rom.write_wram2(
        "wFullColorPhase5FastCacheDescriptor", address.to_bytes(2, "little")
    )
    phase2_rom.write_wram2(
        "wFullColorActiveDescriptor", address.to_bytes(2, "little")
    )
    phase2_rom.write_wram2(
        "wFullColorPhase5FastCacheValid",
        phase2_rom.constants["FULL_COLOR_PHASE5_FAST_CACHE_ACCOUNTING_PENDING"],
    )
    phase2_rom.write_wram2(
        "wFullColorPhase5ScenarioControl",
        phase2_rom.constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
    )
    phase2_rom.emulator.pyboy.memory[0xFF70] = 2
    before_tiles = phase2_rom.emulator.read_vram_bank(0, 0x9800, 40)
    before_attributes = phase2_rom.emulator.read_vram_bank(1, 0x9800, 40)

    phase2_rom.call("FinishFullColorPhase5DeferredAccountingSelected")
    # The one-shot marker is consumed on failure. A second invocation is a
    # no-op, so neither an interrupted nor a hostile observer can replay writes.
    phase2_rom.call("FinishFullColorPhase5DeferredAccountingSelected")

    assert phase2_rom.read_wram2("wFullColorPhase5FastCacheValid") == b"\0"
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x01"
    assert phase2_rom.read_wram2("wFullColorRequestDescriptors")[0] >> 4 == (
        phase2_rom.constants["COMMITTING"]
    )
    assert phase2_rom.read_wram2("wFullColorPhase5ScenarioResult") == bytes((
        phase2_rom.constants["FULL_COLOR_PHASE5_SCENARIO_RESULT_FAILED"],
    ))
    assert phase2_rom.read_wram2("wFullColorPhase5ScenarioState") == bytes((
        phase2_rom.constants["FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED"],
    ))
    assert phase2_rom.emulator.read_vram_bank(0, 0x9800, 40) == before_tiles
    assert phase2_rom.emulator.read_vram_bank(1, 0x9800, 40) == before_attributes


def test_yellow_vblank_stable_observer_uses_linked_cross_bank_farcall() -> None:
    sym = REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym"
    rom = (REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc").read_bytes()
    owner_bank, owner_address = _linked_symbol(
        sym, "FullColorPhase5CombinedVBlankYellow"
    )
    observer_bank, observer_address = _linked_symbol(
        sym, "UpdateFullColorPhase5PartyStableFrames"
    )
    _, bankswitch_address = _linked_symbol(sym, "Bankswitch")
    assert owner_bank != observer_bank
    offset = owner_bank * 0x4000 + owner_address - 0x4000
    assert rom[offset:offset + 8] == bytes((
        0x06,
        observer_bank,
        0x21,
        observer_address & 0xFF,
        observer_address >> 8,
        0xCD,
        bankswitch_address & 0xFF,
        bankswitch_address >> 8,
    ))


def test_owned_vblank_end_is_after_bank_restore_and_before_writer_free_tail() -> None:
    sym = REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym"
    rom = (REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc").read_bytes()
    end_bank, end_address = _linked_symbol(sym, "FullColorPhase5CombinedVBlankEnd")
    owner_bank, owner_address = _linked_symbol(sym, "FullColorVBlankOwnerConsumed")
    finalizer_bank, finalizer_address = _linked_symbol(
        sym, "FinishFullColorPhase5DeferredAccounting"
    )
    _, bankswitch_address = _linked_symbol(sym, "Bankswitch")
    assert end_bank == 0
    assert owner_bank != end_bank
    # The owner farcall must have restored Home's ROM bank before the carry
    # split reaches the Color-only timing seam.
    assert rom[end_address - 10:end_address - 2] == bytes((
        0x06,
        owner_bank,
        0x21,
        owner_address & 0xFF,
        owner_address >> 8,
        0xCD,
        bankswitch_address & 0xFF,
        bankswitch_address >> 8,
    ))
    assert rom[end_address - 2] == 0x38  # jr c, Yellow owner
    assert rom[end_address:end_address + 8] == bytes((
        0x06,
        finalizer_bank,
        0x21,
        finalizer_address & 0xFF,
        finalizer_address >> 8,
        0xCD,
        bankswitch_address & 0xFF,
        bankswitch_address >> 8,
    ))

    source = (REPOSITORY_ROOT / "home/vblank.asm").read_text(encoding="utf-8")
    assert (
        "farcall FullColorVBlankOwnerConsumed\n"
        "\t\tjr c, FullColorPhase5YellowOwner\n"
        "FullColorPhase5CombinedVBlankEnd::\n"
        "\t\tfarcall FinishFullColorPhase5DeferredAccounting\n"
        "\t\tjr FullColorPhase5YellowOwner.vblankSensitiveOperationsDone"
    ) in source
    tail = source.split("\n.vblankSensitiveOperationsDone\n", 1)[1].split(
        "FullColorPhase5VBlankHandlerEnd::", 1
    )[0]
    for visible_writer in (
        "rSCX", "rSCY", "rWY", "rWX", "rDMA", "hDMARoutine",
        "AutoBgMapTransfer", "VBlankCopy", "RedrawRowOrColumn",
        "UpdateMovingBgTiles", "PrepareOAMData", "rHDMA5",
    ):
        assert visible_writer not in tail

    audit_source = (
        REPOSITORY_ROOT / "engine/full_color/phase5_audit.asm"
    ).read_text(encoding="utf-8")
    finalizer = audit_source.split(
        "FinishFullColorPhase5DeferredAccountingSelected:", 1
    )[1].split("CancelFullColorPhase5FastDescriptorSelected:", 1)[0]
    for visible_writer in (
        "rSCX", "rSCY", "rWY", "rWX", "rVBK", "rDMA", "hDMARoutine",
        "AutoBgMapTransfer", "VBlankCopy", "RedrawRowOrColumn",
        "UpdateMovingBgTiles", "PrepareOAMData", "rHDMA5", "rBCPD", "rOCPD",
    ):
        assert visible_writer not in finalizer
    assert re.findall(r"\b(?:farcall|call)\s+(\S+)", finalizer) == [
        "LoadFullColorPhase5FastCacheDescriptorSelected",
        "RecordFullColorPhase5FastTransitionSelected",
    ]


def test_paired_fast_writer_is_added_only_and_called_from_fixed_bridge() -> None:
    sym = REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym"
    rom = (REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc").read_bytes()
    bridge_bank, bridge_address = _linked_symbol(
        sym, "CommitFullColorPairedTransferSelected"
    )
    fast_bank, fast_address = _linked_symbol(
        sym, "CommitFullColorPhase5PairedTransferFastSelected"
    )
    _, bankswitch_address = _linked_symbol(sym, "Bankswitch")
    assert bridge_bank == 0x3B
    assert bridge_address < 0x552B
    assert fast_bank != bridge_bank
    offset = bridge_bank * 0x4000 + bridge_address - 0x4000
    bridge = rom[offset:offset + 32]
    farcall = bytes((
        0x06,
        fast_bank,
        0x21,
        fast_address & 0xFF,
        fast_address >> 8,
        0xCD,
        bankswitch_address & 0xFF,
        bankswitch_address >> 8,
    ))
    assert bridge.count(farcall) == 1
    assert "CommitFullColorPhase5PairedTransferFastSelected::" not in (
        REPOSITORY_ROOT / "engine/full_color/transfers.asm"
    ).read_text(encoding="utf-8")
    assert "CommitFullColorPhase5PairedTransferFastSelected::" in (
        REPOSITORY_ROOT / "engine/full_color/phase5_audit.asm"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize("carry_set", (False, True))
def test_audit_map_restore_tail_preserves_result_carry_bank_and_stack(
    phase2_rom: Phase2Rom, carry_set: bool,
) -> None:
    """The compressed Home tail must return either lifecycle result verbatim."""
    emu = phase2_rom.emulator
    pyboy = emu.pyboy
    registers = pyboy.register_file
    tail = emu.symbols["FullColorAuditLoadMapDataRestoreRomBank"]
    trampoline = 0xC700
    stack = 0xCFFE
    return_probe = 0x0100
    saved_bank = 9
    selected_bank = 4
    set_result = 0x37 if carry_set else 0xA7  # scf / and a
    phase2_rom.write_fixed(trampoline, bytes((
        0x3E, saved_bank,                         # ld a, saved_bank
        0xF5,                                     # push af
        set_result,
        0xC3, tail & 0xFF, tail >> 8,             # jp restore tail
    )))
    stack_canary = b"P5TAIL"
    phase2_rom.write_fixed(stack - 8, stack_canary)
    pyboy.memory[stack] = return_probe & 0xFF
    pyboy.memory[stack + 1] = return_probe >> 8
    pyboy.memory[emu.symbols["hLoadedROMBank"]] = selected_bank
    pyboy.memory[0x2000] = selected_bank
    pyboy.memory[0xFFFF] = 0
    registers.A = 0
    registers.F = 0
    registers.SP = stack
    registers.PC = trampoline
    returned = [False]

    def stop(_: object) -> None:
        returned[0] = True
        phase2_rom.write_fixed(0xC780, b"\x18\xfe")
        registers.PC = 0xC780

    pyboy.hook_register(0, return_probe, stop, None)
    try:
        for _ in range(8):
            pyboy.tick(1, render=False, sound=False)
            if returned[0]:
                break
    finally:
        pyboy.hook_deregister(0, return_probe)

    assert returned[0]
    assert bool(registers.F & 0x10) is carry_set
    assert pyboy.memory[emu.symbols["hLoadedROMBank"]] == saved_bank
    assert registers.SP == 0xD000
    assert bytes(pyboy.memory[stack - 8:stack - 2]) == stack_canary


@pytest.mark.parametrize(
    ("mutation", "boundary", "terminal"),
    (
        ("FullColorPhase5MutationPreparation", MUTABLE_BOUNDARIES[0], "CANCELLED"),
        ("FullColorPhase5MutationOwner", MUTABLE_BOUNDARIES[1], "CANCELLED"),
        ("FullColorPhase5MutationGeneration", MUTABLE_BOUNDARIES[2], "CANCELLED"),
        ("FullColorPhase5MutationDestination", MUTABLE_BOUNDARIES[3], "CANCELLED"),
        ("FullColorPhase5MutationResources", MUTABLE_BOUNDARIES[4], "DEFERRED"),
        ("FullColorPhase5MutationBudget", MUTABLE_BOUNDARIES[4], "DEFERRED"),
    ),
)
def test_patchable_boundary_mutations_fail_closed_before_visibility(
    tmp_path: Path, mutation: str, boundary: str, terminal: str,
) -> None:
    source_rom = REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc"
    source_sym = REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym"
    bank, address = _linked_symbol(source_sym, mutation)
    blob = bytearray(source_rom.read_bytes())
    offset = bank * 0x4000 + address - 0x4000
    blob[offset] = 1
    mutant_rom = tmp_path / f"{mutation}.gbc"
    mutant_rom.write_bytes(blob)
    emulator = Emulator(
        rom=mutant_rom,
        symbols=source_sym,
        results=tmp_path / mutation,
        cgb=True,
    )
    mutant = Phase2Rom(emulator, numeric_symbols(source_sym))
    try:
        mutant.activate()
        _admit_one_cell_pair(mutant)
        _arm_pressure(
            mutant, boundary, available_cycles=100, required_cycles=100,
        )
        before = (
            mutant.emulator.read_vram_bank(0, 0x9800, 1),
            mutant.emulator.read_vram_bank(1, 0x9800, 1),
        )
        result, flags = mutant.call("FullColorPhase5StressCheckpointSelected")
        assert result == mutant.constants[f"FULL_COLOR_PHASE5_TERMINAL_{terminal}"]
        assert flags & 0x10
        assert (
            mutant.emulator.read_vram_bank(0, 0x9800, 1),
            mutant.emulator.read_vram_bank(1, 0x9800, 1),
        ) == before
        expected_count = 1 if terminal == "DEFERRED" else 0
        assert mutant.read_wram2("wFullColorRequestCount") == bytes((expected_count,))
    finally:
        emulator.close()


def test_phase5_abi_and_marker_link_only_in_audit_product() -> None:
    forbidden = ("FullColorPhase5", "wFullColorPhase5")
    for product in PRODUCTION_PRODUCTS:
        symbols = (REPOSITORY_ROOT / f"{product}.sym").read_text(encoding="utf-8")
        assert all(marker not in symbols for marker in forbidden)
        assert b"P5STRESS1" not in (REPOSITORY_ROOT / f"{product}.gbc").read_bytes()

    audit_symbols = (
        REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym"
    ).read_text(encoding="utf-8")
    assert all(marker in audit_symbols for marker in forbidden)
    assert b"P5STRESS1" in (
        REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc"
    ).read_bytes()

"""Focused real-ROM checks for the audit-only poisoned Party round trip."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.rom_tests.tests.conftest import REPOSITORY_ROOT
from tools.rom_tests.tests.unit.full_color.test_phase2_scheduler_rom import (
    Phase2Rom,
    _farcall_from_wram,
    phase2_rom as _phase2_rom,  # noqa: F401 - registered by pytest
)


@pytest.fixture(name="phase2_rom")
def phase2_rom_fixture(request: pytest.FixtureRequest) -> Phase2Rom:
    return request.getfixturevalue("_phase2_rom")


def _arm(rom: Phase2Rom, mutation: str = "FULL_COLOR_PHASE5_MUTATION_NONE") -> None:
    rom.write_wram2(
        "wFullColorPhase5Scenario",
        rom.constants["FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_YELLOW"],
    )
    rom.write_wram2("wFullColorPhase5ScenarioMutation", rom.constants[mutation])
    rom.write_wram2(
        "wFullColorPhase5ScenarioControl",
        rom.constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
    )


def _phase5_state(rom: Phase2Rom) -> bytes:
    return rom.read_wram2("wFullColorPhase5ScenarioStateStart", 11)


def _linked_rom_slice(start: str, end: str) -> bytes:
    locations: dict[str, tuple[int, int]] = {}
    for line in (REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line or line.startswith(";"):
            continue
        location, name = line.split(maxsplit=1)
        if name not in (start, end):
            continue
        bank_text, address_text = location.split(":", maxsplit=1)
        locations[name] = (int(bank_text, 16), int(address_text, 16))
    bank, address = locations[start]
    end_bank, end_address = locations[end]
    assert end_bank == bank
    offset = address if bank == 0 else bank * 0x4000 + address - 0x4000
    return (REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc").read_bytes()[
        offset:offset + end_address - address
    ]


def _party_presentation_guard_cycles(blob: bytes) -> int:
    # push bc; ld b,n; dec b; jr nz,-3; pop bc
    assert len(blob) == 7
    assert blob[:2] == b"\xc5\x06"
    assert blob[3:] == b"\x05\x20\xfd\xc1"
    iterations = blob[2]
    assert iterations > 0
    return 16 + 8 + (iterations - 1) * (4 + 12) + 4 + 8 + 12


def _arm_cycles(rom: Phase2Rom, boundary: int, available: int, required: int) -> None:
    rom.write_wram2(
        "wFullColorPhase5StressMode",
        rom.constants["FULL_COLOR_PHASE5_STRESS_MODE_ARMED"],
    )
    rom.write_wram2("wFullColorPhase5StressTargetBoundary", boundary)
    rom.write_wram2("wFullColorPhase5StressAvailableCycles", available.to_bytes(2, "little"))
    rom.write_wram2("wFullColorPhase5StressRequiredCycles", required.to_bytes(2, "little"))


def _begin_yellow(rom: Phase2Rom, *, entry_bank: int) -> tuple[int, int]:
    # Direct fixture calls begin inside the already-hidden variant; a poison
    # breakpoint briefly resumes LCD timing only after all destinations changed.
    rom.emulator.pyboy.memory[0xFF40] &= 0x7F
    result = _farcall_hidden(
        rom,
        "BeginFullColorPhase5PartyHandoffToYellow",
        "FullColorPhase5PartyHandoffToYellowEnd",
        entry_bank=entry_bank,
    )
    return result


def _farcall_hidden(
    rom: Phase2Rom, name: str, end_label: str, *, entry_bank: int,
) -> tuple[int, int]:
    """Let PyBoy finish its frame after a routine deliberately disables LCD."""
    pyboy = rom.emulator.pyboy
    reveal_label = "PoisonFullColorPhase5PartyState.poisonRecorded"
    bank = rom.emulator.symbol_banks[reveal_label]
    address = rom.emulator.symbols[reveal_label]

    def reveal_for_tick(_: object) -> None:
        pyboy.memory[0xFF40] |= 0x80

    pyboy.hook_register(bank, address, reveal_for_tick, None)
    try:
        result = _farcall_from_wram(rom, name, entry_bank=entry_bank)
    finally:
        pyboy.hook_deregister(bank, address)
        pyboy.memory[0xFF40] &= 0x7F
    return result


def _complete_yellow(rom: Phase2Rom) -> None:
    # Direct probes supply a fresh logical Party result.  The natural-input E2E
    # separately proves every linked-ROM/logical producer. Mark that independent
    # precondition complete before exercising the physical presentation gate.
    tiles = bytes((index * 17 + 9) & 0xFF for index in range(20 * 18))
    rom.write_fixed(rom.emulator.symbols["wTileMap"], tiles)
    shadow = bytes((index * 11 + 3) & 0xFF for index in range(160))
    rom.write_fixed(rom.emulator.symbols["wShadowOAM"], shadow)
    rom.write_wram2("wFullColorPhase5ScenarioFlags", b"\xff")
    assert _farcall_from_wram(
        rom, "CompleteFullColorPhase5PartyYellowReconstruction", entry_bank=4,
    )[1] & 0x10 == 0


def test_phase5_party_symbols_and_scene_identities_are_audit_only() -> None:
    linked_markers = (
        "FullColorPhase5PartyHandoffToYellowStart",
        "FullColorPhase5PartyHandoffToYellowEnd",
        "FullColorPhase5PartyHandoffToColorStart",
        "FullColorPhase5PartyHandoffToColorEnd",
        "FullColorPhase5PartyReconstructColorStart",
        "FullColorPhase5PartyReconstructColorEnd",
        "FullColorPhase5PartyReconstructColorPresentationGuardStart",
        "FullColorPhase5PartyReconstructColorPresentationGuardEnd",
        "FullColorPhase5PartyColorTilesetProducerStart",
        "FullColorPhase5PartyColorTilesetProducerReturn",
        "RecordFullColorPhase5PartyYellowProducerStep",
        "ShouldSkipFullColorPhase5PartyFontProducer",
    )
    rom_markers = (
        "SC-P5-AUDIT-PARTY-ENTRY",
        "SC-P5-AUDIT-PARTY-RETURN",
    )
    audit_symbols = (REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym").read_text(
        encoding="utf-8"
    )
    audit_rom = (REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc").read_bytes()
    for marker in linked_markers:
        assert marker in audit_symbols
    for marker in rom_markers:
        assert marker.encode() in audit_rom

    for product in ("pokeyellow", "pokeyellow_debug", "pokeyellow_vc"):
        symbols = (REPOSITORY_ROOT / f"{product}.sym").read_text(encoding="utf-8")
        rom = (REPOSITORY_ROOT / f"{product}.gbc").read_bytes()
        for marker in linked_markers:
            assert marker not in symbols
        for marker in rom_markers:
            assert marker.encode() not in rom


def test_phase5_party_color_presentation_guard_is_one_exact_scanline() -> None:
    guard = _linked_rom_slice(
        "FullColorPhase5PartyReconstructColorPresentationGuardStart",
        "FullColorPhase5PartyReconstructColorPresentationGuardEnd",
    )
    assert guard == b"\xc5\x06\x37\x05\x20\xfd\xc1"
    assert _party_presentation_guard_cycles(guard) == 912


@pytest.mark.parametrize("hostile", ("bypass", "shorten"))
def test_phase5_party_color_presentation_guard_rejects_hostile_mutants(
    hostile: str,
) -> None:
    guard = bytearray(_linked_rom_slice(
        "FullColorPhase5PartyReconstructColorPresentationGuardStart",
        "FullColorPhase5PartyReconstructColorPresentationGuardEnd",
    ))
    if hostile == "bypass":
        # An unconditional jump skips the bounded loop completely.
        guard[:2] = b"\x18\x05"
        with pytest.raises(AssertionError):
            _party_presentation_guard_cycles(bytes(guard))
        return

    # One fewer iteration removes 16 CPU T-cycles and violates the scanline
    # floor even though the surrounding instruction identities are unchanged.
    guard[2] -= 1
    assert _party_presentation_guard_cycles(bytes(guard)) == 896
    assert _party_presentation_guard_cycles(bytes(guard)) < 912


@pytest.mark.parametrize("boundary", range(5))
def test_phase5_party_cycle_boundaries_exact_fit_and_retry_threshold_plus_one(
    phase2_rom: Phase2Rom, boundary: int,
) -> None:
    rom = phase2_rom
    _arm(rom)
    _arm_cycles(rom, boundary, available=127, required=128)
    generation = rom.generation
    owner = rom.read_wram2("wRendererOwner")
    phase = rom.read_wram2("wRendererPhase")
    rom.emulator.pyboy.memory[0xFF40] |= 0x80

    _, flags = _farcall_from_wram(
        rom, "BeginFullColorPhase5PartyHandoffToYellow", entry_bank=4,
    )
    assert flags & 0x10
    assert rom.generation == generation
    assert rom.read_wram2("wRendererOwner") == owner
    assert rom.read_wram2("wRendererPhase") == phase
    assert rom.read_wram2("wFullColorPhase5ScenarioControl") == bytes((
        rom.constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
    ))
    assert rom.read_wram2("wFullColorPhase5StressReachedMask") == bytes((
        (1 << (boundary + 1)) - 1,
    ))
    assert rom.read_wram2("wFullColorPhase5StressDeferredMask") == bytes((
        1 << boundary,
    ))

    rom.write_wram2("wFullColorPhase5StressAvailableCycles", (128).to_bytes(2, "little"))
    assert _begin_yellow(rom, entry_bank=4)[1] & 0x10 == 0
    assert rom.generation == generation + 1
    assert rom.read_wram2("wRendererPhase") == bytes((
        rom.constants["YELLOW_RECONSTRUCTING"],
    ))


def test_phase5_party_entry_poison_ledger_barrier_and_five_stable_frames(
    phase2_rom: Phase2Rom,
) -> None:
    rom = phase2_rom
    emu = rom.emulator.pyboy
    _arm(rom)
    generation = rom.generation
    stack_canary_address = 0xCF40
    stack_canary = bytes(range(16))
    rom.write_fixed(stack_canary_address, stack_canary)
    ie = emu.memory[0xFFFF]
    svbk = emu.memory[0xFF70]
    vbk = emu.memory[0xFF4F]

    assert _begin_yellow(rom, entry_bank=4)[1] & 0x10 == 0

    state = _phase5_state(rom)
    assert rom.generation == generation + 1
    assert rom.read_wram2("wRendererOwner") == bytes((rom.constants["RENDERER_YELLOW"],))
    assert rom.read_wram2("wRendererPhase") == bytes((rom.constants["YELLOW_RECONSTRUCTING"],))
    assert rom.read_wram2("wRendererAdmissionOpen") == b"\0"
    assert state[5] == rom.constants["FULL_COLOR_PHASE5_LEDGER_ALL"]
    assert state[6:8] == b"\0\0"
    assert rom.read_wram2("wFullColorPartyReturnPending") == b"\x01"
    assert emu.memory[0xFF40] & 0x80 == 0
    assert bytes(emu.memory[stack_canary_address + i] for i in range(16)) == stack_canary
    assert emu.memory[0xFFFF] == ie
    assert emu.memory[0xFF70] == svbk
    assert emu.memory[0xFF4F] == vbk
    assert emu.memory[0xFF4B] == 0xD3
    assert rom.emulator.read_vram_bank(0, 0x8000, 32) == b"\xd3" * 32
    assert rom.emulator.read_vram_bank(1, 0x9800, 32) == b"\x6d" * 32
    assert bytes(emu.memory[0xFE00 + i] for i in range(32)) == b"\xb7" * 32
    assert rom.emulator.read_bytes("wMonPartySpritesSavedOAM", 96) == b"\xb7" * 96
    assert rom.read_wram2("wFullColorBGPaletteBase", 64 * 4) == b"\xd3" * (64 * 4)
    assert rom.read_wram2("wFullColorAttributeRectangle", 32) == b"\xd3" * 32
    assert rom.read_wram2("wFullColorShadowOAMBatch", 32) == b"\xd3" * 32
    assert rom.read_wram2("wFullColorAuthoritySnapshot", 16) == b"\xd3" * 16
    assert rom.read_wram2("wFullColorProducerTiles", 32) == b"\xd3" * 32

    _complete_yellow(rom)
    assert emu.memory[0xFF4B] == 7
    expected_tiles = bytes((index * 17 + 9) & 0xFF for index in range(20 * 18))
    for row in range(18):
        start = row * 20
        assert rom.emulator.read_vram_bank(0, 0x9C00 + row * 32, 20) == (
            expected_tiles[start:start + 20]
        )
    assert rom.emulator.read_vram_bank(0, 0x9800, 20) == b"\xd3" * 20
    assert rom.read_wram2("wFullColorPhase5YellowLedgerMask") == b"\xff"
    assert rom.read_wram2("wFullColorPhase5BarrierState") == bytes((
        rom.constants["FULL_COLOR_PHASE5_BARRIER_PRESENTED"],
    ))
    assert rom.read_wram2("wRendererPhase") == bytes((rom.constants["YELLOW_ACTIVE"],))
    assert rom.read_wram2("wRendererAdmissionOpen") == b"\x01"

    for expected in range(1, 6):
        _farcall_from_wram(
            rom, "UpdateFullColorPhase5PartyStableFrames", entry_bank=7,
        )
        assert rom.read_wram2("wFullColorPhase5StableFrames") == bytes((expected,))
    assert rom.read_wram2("wFullColorPhase5ScenarioState") == bytes((
        rom.constants["FULL_COLOR_PHASE5_SCENARIO_STATE_STABLE"],
    ))
    assert rom.read_wram2("wFullColorPhase5BarrierState") == bytes((
        rom.constants["FULL_COLOR_PHASE5_BARRIER_STABLE"],
    ))
    assert rom.read_wram2("wFullColorPartyReturnPending") == b"\x01"


@pytest.mark.parametrize(
    "mutation",
    (
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
    ),
)
def test_phase5_party_mutations_fail_before_first_presentation(
    phase2_rom: Phase2Rom, mutation: str,
) -> None:
    rom = phase2_rom
    _arm(rom, mutation)
    generation = rom.generation
    assert _begin_yellow(rom, entry_bank=7)[1] & 0x10 == 0

    _, flags = _farcall_from_wram(
        rom, "CompleteFullColorPhase5PartyYellowReconstruction", entry_bank=4,
    )
    assert flags & 0x10
    assert rom.generation == generation + 1
    assert rom.read_wram2("wFullColorPhase5ScenarioResult") == bytes((
        rom.constants["FULL_COLOR_PHASE5_SCENARIO_RESULT_FAILED"],
    ))
    assert rom.read_wram2("wFullColorPhase5ScenarioState") == bytes((
        rom.constants["FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED"],
    ))
    assert rom.read_wram2("wRendererAdmissionOpen") == b"\0"
    assert rom.read_wram2("wFullColorPhase5BarrierState") == b"\0"
    assert rom.read_wram2("wFullColorPartyReturnPending") == b"\x01"
    assert rom.emulator.pyboy.memory[0xFF40] & 0x80 == 0


def test_phase5_party_color_handoff_advances_once_and_preserves_marker(
    phase2_rom: Phase2Rom,
) -> None:
    rom = phase2_rom
    _arm(rom)
    assert _begin_yellow(rom, entry_bank=4)[1] & 0x10 == 0
    _complete_yellow(rom)
    for _ in range(5):
        _farcall_from_wram(
            rom, "UpdateFullColorPhase5PartyStableFrames", entry_bank=7,
        )

    generation = rom.generation
    rom.emulator.pyboy.memory[0xFF40] &= 0x7F
    assert _farcall_hidden(
        rom,
        "BeginFullColorPhase5PartyHandoffToColor",
        "FullColorPhase5PartyHandoffToColorEnd",
        entry_bank=4,
    )[1] & 0x10 == 0
    assert rom.generation == generation + 1
    assert rom.read_wram2("wRendererOwner") == bytes((
        rom.constants["RENDERER_FULL_COLOR_OVERWORLD"],
    ))
    assert rom.read_wram2("wRendererPhase") == bytes((
        rom.constants["OVERWORLD_RECONSTRUCTING"],
    ))
    assert rom.read_wram2("wRendererAdmissionOpen") == b"\0"
    assert rom.read_wram2("wFullColorPartyReturnPending") == b"\x01"
    assert rom.read_wram2("wFullColorPhase5ColorLedgerMask") == b"\0"

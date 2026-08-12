"""Direct real-ROM tests for the guarded Phase 2 scheduler seams."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re

import pytest

from tools.rom_tests.emulator import Emulator
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT, result_directory


def numeric_symbols(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]+)\s+(\S+)", line)
        if match:
            result[match.group(2)] = int(match.group(1), 16)
    return result


@dataclass
class Phase2Rom:
    emulator: Emulator
    constants: dict[str, int]

    def call(
        self, name: str, *, a: int = 0, b: int = 0, c: int = 0,
        de: int = 0, hl: int = 0,
    ) -> tuple[int, int]:
        emu = self.emulator
        regs = emu.pyboy.register_file
        address = emu.symbols[name]
        bank = emu.symbol_banks[name]
        stack = 0xCFFE
        regs.A, regs.B, regs.C = a, b, c
        regs.D, regs.E = (de >> 8) & 0xFF, de & 0xFF
        regs.HL, regs.SP = hl, stack
        emu.pyboy.memory[stack] = 0
        emu.pyboy.memory[stack + 1] = 1
        emu.pyboy.memory[0xFFFF] = 0
        if bank:
            emu.pyboy.memory[0x2000] = bank
        # Mirror Bankswitch's software-visible ROM-bank state, including Home.
        # Direct ROM entry used to update only MBC5, so a routine containing a
        # nested farcall restored a stale bank and continued through unrelated
        # code.
        emu.pyboy.memory[emu.symbols["hLoadedROMBank"]] = bank
        regs.PC = address
        returned = False

        def stop(_: object) -> None:
            nonlocal returned
            returned = True
            # Never use $ff80: that is the production OAM DMA routine.
            emu.pyboy.memory[0xC6F0] = 0x18
            emu.pyboy.memory[0xC6F1] = 0xFE
            regs.PC = 0xC6F0

        emu.pyboy.hook_register(0, 0x0100, stop, None)
        try:
            # A maximum 360-cell paired PREPARE/COMMIT is intentionally larger
            # than one emulated frame. Keep stepping until the return hook has
            # fired, with a small hard ceiling so a real ROM loop still fails.
            for _ in range(64):
                emu.pyboy.tick(1, render=False, sound=False)
                if returned:
                    break
        finally:
            emu.pyboy.hook_deregister(0, 0x0100)
        assert returned, f"{name} did not return (PC={regs.PC:#06x}, SP={regs.SP:#06x})"
        return regs.A, regs.F

    def write_fixed(self, address: int, data: bytes) -> None:
        for offset, value in enumerate(data):
            self.emulator.pyboy.memory[address + offset] = value

    def write_wram2(self, symbol: str, data: bytes | int) -> None:
        blob = bytes([data]) if isinstance(data, int) else data
        old = self.emulator.pyboy.memory[0xFF70]
        self.emulator.pyboy.memory[0xFF70] = 2
        try:
            address = self.emulator.symbols[symbol]
            for offset, value in enumerate(blob):
                self.emulator.pyboy.memory[address + offset] = value
        finally:
            self.emulator.pyboy.memory[0xFF70] = old

    def read_wram2(self, symbol: str, size: int = 1) -> bytes:
        old = self.emulator.pyboy.memory[0xFF70]
        self.emulator.pyboy.memory[0xFF70] = 2
        try:
            address = self.emulator.symbols[symbol]
            return bytes(self.emulator.pyboy.memory[address + i] for i in range(size))
        finally:
            self.emulator.pyboy.memory[0xFF70] = old

    @property
    def generation(self) -> int:
        return int.from_bytes(self.read_wram2("wRendererGeneration", 4), "little")

    def activate(self) -> None:
        self.call("InitRendererOwnership")
        # Direct-call ROM tests bypass the game's boot copier. Install the exact
        # production DMA stub in its HRAM execution address before OAM tests.
        dma_stub = bytes((0x3E, 0xC3, 0xE0, 0x46, 0x3E, 0x28, 0x3D, 0x20, 0xFD, 0xC9))
        for offset, value in enumerate(dma_stub):
            self.emulator.pyboy.memory[0xFF80 + offset] = value
        self.write_wram2("wRendererOwner", self.constants["RENDERER_FULL_COLOR_OVERWORLD"])
        self.write_wram2("wRendererPhase", self.constants["OVERWORLD_ACTIVE"])
        self.write_wram2("wRendererAdmissionOpen", 1)
        self.call("InitFullColorScheduler")

    def descriptor(
        self,
        request_class: str,
        *,
        destination: int | None = None,
        source: int = 0xC900,
        desired: int | None = None,
        resources: int | None = None,
        extent: int | None = None,
        reservation: int | None = None,
        flags: int = 0,
        owner: str = "RENDERER_FULL_COLOR_OVERWORLD",
        generation: int | None = None,
    ) -> bytes:
        cls = self.constants[request_class]
        if request_class == "FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD":
            defaults = (self.constants["FULL_COLOR_BG_PALETTE_DESTINATION"], 0, 1, 64, 64)
        elif request_class == "FULL_COLOR_REQUEST_OBJ_PALETTE_PAYLOAD":
            defaults = (self.constants["FULL_COLOR_OBJ_PALETTE_DESTINATION"], 0, 1, 64, 64)
        elif request_class == "FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA":
            defaults = (self.constants["FULL_COLOR_OAM_DESTINATION"], 0, 24, 160, 200)
        elif request_class == "FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT":
            defaults = (0x8000, 0x9800, 36, 17, 17)
        else:
            defaults = (0x9800, 0x0101, 6, 1, 2)
        destination, desired, resources, extent, reservation = (
            default if value is None else value
            for value, default in zip(
                (destination, desired, resources, extent, reservation), defaults, strict=True
            )
        )
        return b"".join((
            bytes([cls, self.constants[owner]]),
            (self.generation if generation is None else generation).to_bytes(4, "little"),
            destination.to_bytes(2, "little"), source.to_bytes(2, "little"),
            desired.to_bytes(2, "little"), resources.to_bytes(2, "little"),
            extent.to_bytes(2, "little"), reservation.to_bytes(2, "little"),
            bytes([flags, 0]),
        ))

    def admit(self, descriptor: bytes) -> tuple[int, int]:
        assert len(descriptor) == 20
        self.write_fixed(0xC700, descriptor)
        return self.call("AdmitFullColorRequest", hl=0xC700)


def _farcall_from_wram(
    phase2_rom: Phase2Rom, name: str, *, entry_bank: int,
) -> tuple[int, int]:
    """Execute a no-argument routine through the production Bankswitch path."""
    emu = phase2_rom.emulator
    regs = emu.pyboy.register_file
    target = emu.symbols[name]
    target_bank = emu.symbol_banks[name]
    bankswitch = emu.symbols["Bankswitch"]
    trampoline = 0xC6F0
    stack = 0xCFFE
    phase2_rom.write_fixed(trampoline, bytes((
        0x06, target_bank,                    # ld b, BANK(target)
        0x21, target & 0xFF, target >> 8,    # ld hl, target
        0xCD, bankswitch & 0xFF, bankswitch >> 8,
        0xC9,
    )))
    emu.pyboy.memory[emu.symbols["hLoadedROMBank"]] = entry_bank
    emu.pyboy.memory[0x2000] = entry_bank
    regs.SP = stack
    emu.pyboy.memory[stack] = 0
    emu.pyboy.memory[stack + 1] = 1
    emu.pyboy.memory[0xFFFF] = 0
    regs.PC = trampoline
    returned = False

    def stop(_: object) -> None:
        nonlocal returned
        returned = True
        emu.pyboy.memory[0xC780] = 0x18
        emu.pyboy.memory[0xC781] = 0xFE
        regs.PC = 0xC780

    emu.pyboy.hook_register(0, 0x0100, stop, None)
    try:
        for _ in range(64):
            emu.pyboy.tick(1, render=False, sound=False)
            if returned:
                break
    finally:
        emu.pyboy.hook_deregister(0, 0x0100)
    assert returned, (
        f"{name} did not return through Bankswitch "
        f"(PC={regs.PC:#06x}, SP={regs.SP:#06x}, "
        f"ROM={emu.pyboy.memory[emu.symbols['hLoadedROMBank']]:#04x})"
    )
    assert emu.pyboy.memory[emu.symbols["hLoadedROMBank"]] == entry_bank
    return regs.A, regs.F


def _linked_rom_bytes(
    phase2_rom: Phase2Rom, start_name: str, end_name: str,
) -> bytes:
    """Read one symbol-bounded byte range from the exact ROM under test."""
    emu = phase2_rom.emulator
    bank = emu.symbol_banks[start_name]
    address = emu.symbols[start_name]
    assert emu.symbol_banks[end_name] == bank
    size = emu.symbols[end_name] - address
    assert size >= 0
    offset = address if bank == 0 else bank * 0x4000 + address - 0x4000
    linked = emu.rom.read_bytes()[offset:offset + size]
    assert len(linked) == size
    return linked


def _linked_overworld_tile_attributes(phase2_rom: Phase2Rom) -> bytes:
    """Read the independently linked 256-byte semantic attribute table."""
    linked = _linked_rom_bytes(
        phase2_rom,
        "FullColorOverworldTileAttributes",
        "FullColorOverworldTileAttributesEnd",
    )
    assert len(linked) == 0x100
    return linked


@pytest.fixture
def phase2_rom(request: pytest.FixtureRequest):
    rom = Path(os.environ.get("ROM_TEST_ROM", REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc"))
    sym = Path(os.environ.get("ROM_TEST_SYMBOLS", REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym"))
    emulator = Emulator(rom=rom, symbols=sym, results=result_directory(request.node.nodeid), cgb=True)
    instance = Phase2Rom(emulator, numeric_symbols(sym))
    try:
        instance.activate()
        yield instance
    finally:
        emulator.close()


@pytest.mark.parametrize("entry_bank", (1, 4))
@pytest.mark.parametrize(
    ("owner", "owned"),
    (
        ("RENDERER_YELLOW", False),
        ("RENDERER_FULL_COLOR_OVERWORLD", True),
    ),
)
def test_farcall_owner_predicate_preserves_carry_and_state(
    phase2_rom: Phase2Rom, entry_bank: int, owner: str, owned: bool,
) -> None:
    phase2_rom.write_wram2("wRendererOwner", phase2_rom.constants[owner])
    generation = phase2_rom.generation

    _, flags = _farcall_from_wram(
        phase2_rom, "IsFullColorOverworldOwnerFar", entry_bank=entry_bank,
    )

    assert bool(flags & 0x10) is not owned
    assert phase2_rom.read_wram2("wRendererOwner") == bytes((phase2_rom.constants[owner],))
    assert phase2_rom.generation == generation


def test_owned_vblank_commits_window_bg1_before_presentation_and_close_hides_it(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator
    tile_map = phase2_rom.emulator.symbols["wTileMap"]
    payload = bytes((index * 11 + 3) & 0xFF for index in range(20 * 18))
    attribute_table = _linked_overworld_tile_attributes(phase2_rom)
    expected_attributes = bytes(attribute_table[tile] for tile in payload)
    phase2_rom.write_fixed(tile_map, payload)
    phase2_rom.write_wram2("wFullColorAuthorityVRAMView", b"\x00\x98")
    bg0_before = bytes((0xA0 + index) & 0xFF for index in range(20))
    for offset, value in enumerate(bg0_before):
        phase2_rom.emulator.pyboy.memory[0x9800 + offset] = value

    _, flags = _farcall_from_wram(
        phase2_rom, "EnqueueFullColorWindowTileMapOverlayFar", entry_bank=4,
    )
    assert flags & 0x10 == 0
    phase2_rom.write_fixed(tile_map, b"\xee" * len(payload))
    emu.pyboy.memory[emu.symbols["wUpdateSpritesEnabled"]] = 0xFF
    shadow = emu.symbols["wShadowOAM"]
    oam_batch = bytes((index * 13 + 7) & 0xFF for index in range(160))
    phase2_rom.write_fixed(shadow, oam_batch)
    for offset in range(160):
        emu.pyboy.memory[0xFE00 + offset] = 0x5A
    # Serialized audit publication may retain hardware OAM only with an exact
    # COMPLETE declaration for the current shadow-authority epoch.
    epoch = 7
    retained_oam = bytearray(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA",
        source=shadow,
        flags=phase2_rom.constants["FULL_COLOR_FLAG_OAM_FINISHED"],
    ))
    retained_oam[0] |= phase2_rom.constants["COMPLETE"] << 4
    retained_oam[19] = epoch
    descriptors = bytearray(phase2_rom.read_wram2(
        "wFullColorRequestDescriptors", 8 * 20
    ))
    descriptors[20:40] = retained_oam
    phase2_rom.write_wram2("wFullColorRequestDescriptors", descriptors)
    phase2_rom.write_wram2("wFullColorPhase5OAMAuthorityEpoch", epoch)
    emu.pyboy.memory[emu.symbols["hSCX"]] = 7
    emu.pyboy.memory[emu.symbols["hSCY"]] = 9
    emu.pyboy.memory[emu.symbols["hWY"]] = 0
    emu.pyboy.memory[0xFF43] = 0x55
    emu.pyboy.memory[0xFF42] = 0x66
    emu.pyboy.memory[0xFF4A] = 0x90
    barrier_samples: list[tuple[int, bytes, bytes]] = []
    barrier_name = "FullColorPhase5OwnerRevalidationEnd.publishWindowY"
    barrier = emu.symbols[barrier_name]
    barrier_bank = emu.symbol_banks[barrier_name]

    def observe_barrier(_: object) -> None:
        barrier_samples.append((
            emu.pyboy.memory[0xFF4A],
            emu.read_vram_bank(0, 0x9C00, 20),
            emu.read_vram_bank(0, 0x9800, 20),
        ))

    # Commit the immutable overlay through the retained scheduler before the
    # owner route publishes WY/scroll state. The barrier hook proves the public
    # plane is complete at its first presentation seam.
    phase2_rom.call("RunFullColorOwnershipVBlank")
    emu.pyboy.hook_register(barrier_bank, barrier, observe_barrier, None)
    try:
        _, flags = _farcall_from_wram(
            phase2_rom, "FullColorVBlankOwnerConsumed", entry_bank=4,
        )
    finally:
        emu.pyboy.hook_deregister(barrier_bank, barrier)
    assert flags & 0x10 == 0
    assert barrier_samples == [(0x90, payload[:20], bg0_before)]
    assert emu.pyboy.memory[0xFF43] == 7
    assert emu.pyboy.memory[0xFF42] == 9
    assert emu.pyboy.memory[0xFF4A] == 0
    assert emu.read_vram_bank(0, 0x9800, 20) == bg0_before
    for row in range(18):
        start = row * 20
        assert emu.read_vram_bank(0, 0x9C00 + row * 32, 20) == (
            payload[start:start + 20]
        )
        assert emu.read_vram_bank(1, 0x9C00 + row * 32, 20) == (
            expected_attributes[start:start + 20]
        )
    hardware_oam = bytes(emu.pyboy.memory[0xFE00 + offset] for offset in range(160))
    assert hardware_oam == b"\x5a" * 160
    # The overlay was already completed through the retained scheduler. Owner
    # presentation must not manufacture a retry merely because the declared
    # OAM epoch is retained rather than copied again.
    assert phase2_rom.read_wram2("wFullColorRetryCounter") == b"\x00"

    emu.pyboy.memory[emu.symbols["hWY"]] = 0x90
    _, flags = _farcall_from_wram(
        phase2_rom, "FullColorVBlankOwnerConsumed", entry_bank=1,
    )
    assert flags & 0x10 == 0
    assert emu.pyboy.memory[0xFF4A] == 0x90
    hardware_oam = bytes(emu.pyboy.memory[0xFE00 + offset] for offset in range(160))
    assert hardware_oam == b"\x5a" * 160
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x00"


def test_admission_coalescing_and_exact_oam_declaration_identity(
    phase2_rom: Phase2Rom,
) -> None:
    bg = phase2_rom.descriptor("FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD")
    assert phase2_rom.admit(bg)[0] == phase2_rom.constants["ACCEPTED"]
    assert phase2_rom.admit(bg)[0] == phase2_rom.constants["COALESCED"]
    shadow = phase2_rom.emulator.symbols["wShadowOAM"]
    # The natural audit ABI declares only the producer-finished fixed shadow;
    # an arbitrary descriptor source is rejected without residency.
    assert phase2_rom.call("EnqueueFullColorOAMBatch", hl=0xC900)[0] == (
        phase2_rom.constants["DEFERRED"]
    )
    assert phase2_rom.call("EnqueueFullColorOAMBatch", hl=shadow)[0] == (
        phase2_rom.constants["ACCEPTED"]
    )
    # A second declaration in the same epoch is a retry, never coalesced or
    # admitted as a duplicate OAM authority.
    assert phase2_rom.call("EnqueueFullColorOAMBatch", hl=shadow)[0] == (
        phase2_rom.constants["DEFERRED"]
    )
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x02"


@pytest.mark.parametrize("mutated_offset", (13, 17))
def test_invalid_resident_cannot_absorb_and_strand_valid_retry(
    phase2_rom: Phase2Rom, mutated_offset: int
) -> None:
    payload = bytes((index * 3) & 0x7F for index in range(64))
    phase2_rom.write_fixed(0xC900, payload)
    request = phase2_rom.descriptor("FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD")
    assert phase2_rom.admit(request)[0] == phase2_rom.constants["ACCEPTED"]

    resident = bytearray(phase2_rom.read_wram2("wFullColorRequestDescriptors", 20))
    resident[mutated_offset] = 1  # high resource byte or reservation high byte
    phase2_rom.write_wram2("wFullColorRequestDescriptors", resident)

    assert phase2_rom.admit(request)[0] == phase2_rom.constants["ACCEPTED"]
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x01"
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.emulator.read_palette_ram() == payload
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x00"


def test_capacity_plus_one_defers_and_retry_is_observable(phase2_rom: Phase2Rom) -> None:
    for index in range(8):
        request = phase2_rom.descriptor(
            "FULL_COLOR_REQUEST_MAP_ROW_PAIRED", destination=0x9800 + index,
            desired=0x0101,
        )
        assert phase2_rom.admit(request)[0] == phase2_rom.constants["ACCEPTED"]
    ninth = phase2_rom.descriptor("FULL_COLOR_REQUEST_MAP_ROW_PAIRED", destination=0x9900)
    assert phase2_rom.admit(ninth)[0] == phase2_rom.constants["DEFERRED"]
    assert phase2_rom.read_wram2("wFullColorRetryCounter") == b"\x01"
    assert phase2_rom.read_wram2("wFullColorTimingState", 4) == bytes((
        8, 1, phase2_rom.constants["DEFERRED"], 8,
    ))
    phase2_rom.write_fixed(0xC900, b"\x55\x06")
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.admit(ninth)[0] == phase2_rom.constants["ACCEPTED"]


def test_movement_row_strip_is_one_atomic_20_by_2_visible_unit(
    phase2_rom: Phase2Rom,
) -> None:
    tiles = bytes(range(40))
    attribute_table = _linked_overworld_tile_attributes(phase2_rom)
    expected_attributes = bytes(attribute_table[tile] for tile in tiles)
    assert expected_attributes != bytes(tile & 7 for tile in tiles)
    phase2_rom.write_fixed(0xC900, tiles)
    result, flags = phase2_rom.call(
        "EnqueueFullColorMovementRowStrip", hl=0xC900, de=0x9800,
    )
    assert result == phase2_rom.constants["ACCEPTED"]
    assert flags & 0x10 == 0
    descriptor = phase2_rom.read_wram2("wFullColorRequestDescriptors", 20)
    assert descriptor[10:12] == bytes((20, 2))
    assert int.from_bytes(descriptor[14:16], "little") == 40
    assert int.from_bytes(descriptor[16:18], "little") == 80
    assert descriptor[18] == phase2_rom.constants["FULL_COLOR_FLAG_MOVEMENT_STRIP"]

    phase2_rom.write_fixed(0xC900, b"\xee" * 40)
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.emulator.read_vram_bank(0, 0x9800, 20) == tiles[:20]
    assert phase2_rom.emulator.read_vram_bank(0, 0x9820, 20) == tiles[20:]
    assert phase2_rom.emulator.read_vram_bank(1, 0x9800, 20) == expected_attributes[:20]
    assert phase2_rom.emulator.read_vram_bank(1, 0x9820, 20) == expected_attributes[20:]


def test_deferred_movement_strip_is_retained_and_retried_without_partial_commit(
    phase2_rom: Phase2Rom,
) -> None:
    first = bytes(range(40))
    second = bytes((0x80 + index) & 0xFF for index in range(36))
    phase2_rom.write_fixed(0xC900, first)
    assert phase2_rom.call(
        "EnqueueFullColorMovementRowStrip", hl=0xC900, de=0x9800,
    )[0] == phase2_rom.constants["ACCEPTED"]

    phase2_rom.write_fixed(0xC940, second)
    assert phase2_rom.call(
        "EnqueueFullColorMovementColumnStrip", hl=0xC940, de=0x9840,
    )[0] == phase2_rom.constants["DEFERRED"]
    assert phase2_rom.read_wram2("wFullColorProducerPending") == b"\x01"
    assert phase2_rom.emulator.read_vram_bank(0, 0x9840, 2) != second[:2]
    phase2_rom.write_fixed(0xC940, b"\xff" * 36)
    phase2_rom.emulator.pyboy.memory[
        phase2_rom.emulator.symbols["wUpdateSpritesEnabled"]
    ] = 0xFF

    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.read_wram2("wFullColorProducerPending") == b"\x01"
    # Retry is a natural mainline responsibility in the serialized audit
    # route. It rebuilds only from the frozen private producer authority.
    _farcall_from_wram(phase2_rom, "RetryFullColorProducer", entry_bank=1)
    assert phase2_rom.read_wram2("wFullColorProducerPending") == b"\x00"
    phase2_rom.call("RunFullColorOwnershipVBlank")
    for row in range(18):
        assert phase2_rom.emulator.read_vram_bank(0, 0x9840 + row * 32, 2) == second[row * 2:row * 2 + 2]


def test_reconstruction_commits_complete_palette_and_20_by_18_pair_before_activation(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    tiles = bytes(index & 0xFF for index in range(360))
    attribute_table = _linked_overworld_tile_attributes(phase2_rom)
    expected_attributes = bytes(attribute_table[tile] for tile in tiles)
    phase2_rom.write_fixed(phase2_rom.emulator.symbols["wTileMap"], tiles)
    prior_svbk = emu.memory[0xFF70]
    emu.memory[0xFF70] = 1
    try:
        address = phase2_rom.emulator.symbols["wMapViewVRAMPointer"]
        emu.memory[address] = 0x00
        emu.memory[address + 1] = 0x98
    finally:
        emu.memory[0xFF70] = prior_svbk
    phase2_rom.write_wram2(
        "wRendererOwner", phase2_rom.constants["RENDERER_YELLOW"],
    )
    phase2_rom.write_wram2("wRendererPhase", phase2_rom.constants["YELLOW_ACTIVE"])
    phase2_rom.write_wram2("wRendererAdmissionOpen", 1)
    assert phase2_rom.call("BeginFullColorMapEntry")[1] & 0x10 == 0
    emu.memory[0xFF40] &= 0x7F
    assert _farcall_from_wram(
        phase2_rom, "ReconstructFullColorMapEntry", entry_bank=4,
    )[1] & 0x10 == 0
    assert phase2_rom.read_wram2("wFullColorProducerTiles", 360) == tiles
    assert phase2_rom.read_wram2("wRendererPhase") == bytes((phase2_rom.constants["OVERWORLD_ACTIVE"],))
    assert phase2_rom.read_wram2("wRendererAdmissionOpen") == b"\x01"
    for row in range(18):
        start = row * 20
        assert phase2_rom.emulator.read_vram_bank(0, 0x9800 + row * 32, 20) == tiles[start:start + 20]
        assert phase2_rom.emulator.read_vram_bank(1, 0x9800 + row * 32, 20) == (
            expected_attributes[start:start + 20]
        )


def test_reconstruction_expands_complete_font_before_activation_and_preserves_banks(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator
    linked_font = _linked_rom_bytes(
        phase2_rom, "FontGraphics", "FontGraphicsEnd",
    )
    assert len(linked_font) == 0x80 * 8
    expected_font = b"".join(bytes((value, value)) for value in linked_font)
    vfont = phase2_rom.emulator.symbols["vFont"]
    bank1_sentinel = bytes((index * 13 + 7) & 0xFF for index in range(len(expected_font)))
    for offset in range(len(expected_font)):
        emu.pyboy.memory[0, vfont + offset] = 0xA5
        emu.pyboy.memory[1, vfont + offset] = bank1_sentinel[offset]

    phase2_rom.write_wram2(
        "wRendererOwner", phase2_rom.constants["RENDERER_YELLOW"],
    )
    phase2_rom.write_wram2("wRendererPhase", phase2_rom.constants["YELLOW_ACTIVE"])
    phase2_rom.write_wram2("wRendererAdmissionOpen", 1)
    prior_svbk = emu.pyboy.memory[0xFF70]
    emu.pyboy.memory[0xFF70] = 1
    try:
        map_view = emu.symbols["wMapViewVRAMPointer"]
        emu.pyboy.memory[map_view] = 0x00
        emu.pyboy.memory[map_view + 1] = 0x98
    finally:
        emu.pyboy.memory[0xFF70] = prior_svbk
    assert phase2_rom.call("BeginFullColorMapEntry")[1] & 0x10 == 0
    emu.pyboy.memory[0xFF40] &= 0x7F
    emu.pyboy.memory[0xFF70] = 3
    emu.pyboy.memory[0xFF4F] = 1

    observed: dict[str, bytes | int] = {}
    activation = emu.symbols["ActivateFullColorOwnerForDiagnostic"]
    activation_bank = emu.symbol_banks["ActivateFullColorOwnerForDiagnostic"]

    def capture_before_activation(_: object) -> None:
        observed["font"] = emu.read_vram_bank(0, vfont, len(expected_font))
        observed["bank1"] = emu.read_vram_bank(1, vfont, len(expected_font))
        observed["svbk"] = emu.pyboy.memory[0xFF70]
        observed["vbk"] = emu.pyboy.memory[0xFF4F] & 1

    emu.pyboy.hook_register(activation_bank, activation, capture_before_activation, None)
    try:
        _, flags = _farcall_from_wram(
            phase2_rom, "ReconstructFullColorMapEntry", entry_bank=4,
        )
    finally:
        emu.pyboy.hook_deregister(activation_bank, activation)

    assert flags & 0x10 == 0
    assert observed == {
        "font": expected_font,
        "bank1": bank1_sentinel,
        "svbk": 3,
        "vbk": 1,
    }
    assert emu.pyboy.memory[0xFF70] == 3
    assert emu.pyboy.memory[0xFF4F] & 1 == 1


def test_reconstruction_with_visible_lcd_fails_before_font_write(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator
    vfont = phase2_rom.emulator.symbols["vFont"]
    sentinel = bytes((index * 5 + 0x31) & 0xFF for index in range(0x800))
    for offset, value in enumerate(sentinel):
        emu.pyboy.memory[0, vfont + offset] = value
    phase2_rom.write_wram2(
        "wRendererOwner", phase2_rom.constants["RENDERER_YELLOW"],
    )
    phase2_rom.write_wram2("wRendererPhase", phase2_rom.constants["YELLOW_ACTIVE"])
    phase2_rom.write_wram2("wRendererAdmissionOpen", 1)
    assert phase2_rom.call("BeginFullColorMapEntry")[1] & 0x10 == 0
    emu.pyboy.memory[0xFF40] |= 0x80

    _, flags = phase2_rom.call("ReconstructFullColorMapEntry")

    assert flags & 0x10
    assert emu.read_vram_bank(0, vfont, len(sentinel)) == sentinel
    assert phase2_rom.read_wram2("wRendererPhase") == bytes((
        phase2_rom.constants["OVERWORLD_RECONSTRUCTING"],
    ))
    assert phase2_rom.read_wram2("wRendererAdmissionOpen") == b"\x00"


def test_retry_and_transition_counters_saturate_in_real_rom(phase2_rom: Phase2Rom) -> None:
    phase2_rom.write_wram2("wFullColorRetryCounter", 0xFF)
    phase2_rom.write_wram2("wRendererAdmissionOpen", 0)
    request = phase2_rom.descriptor("FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD")
    assert phase2_rom.admit(request)[0] == phase2_rom.constants["DEFERRED"]
    assert phase2_rom.read_wram2("wFullColorRetryCounter") == b"\xff"
    assert phase2_rom.read_wram2("wFullColorTimingState", 2)[1] == 0xFF

    phase2_rom.write_wram2("wRendererAdmissionOpen", 1)
    phase2_rom.write_wram2("wFullColorTransitionCount", 0xFF)
    phase2_rom.write_wram2("wFullColorTransitionLog", b"sentinel")
    assert phase2_rom.admit(request)[0] == phase2_rom.constants["ACCEPTED"]
    assert phase2_rom.read_wram2("wFullColorTransitionCount") == b"\xff"
    assert phase2_rom.read_wram2("wFullColorTransitionLog", 8) == b"sentinel"


def test_ring_reuse_preserves_fifo_after_wrap(phase2_rom: Phase2Rom) -> None:
    for index in range(8):
        phase2_rom.write_fixed(0xC900 + index * 2, bytes((0x40 + index, index)))
        assert phase2_rom.admit(phase2_rom.descriptor(
            "FULL_COLOR_REQUEST_MAP_ROW_PAIRED", destination=0x9800 + index,
            source=0xC900 + index * 2, desired=0x100 + index + 1,
            extent=index + 1, reservation=(index + 1) * 2,
        ))[0] == phase2_rom.constants["ACCEPTED"]
    phase2_rom.call("RunFullColorOwnershipVBlank")
    phase2_rom.write_fixed(0xC920, b"\x99\x07")
    assert phase2_rom.admit(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_MAP_ROW_PAIRED", destination=0x9900, source=0xC920,
    ))[0] == phase2_rom.constants["ACCEPTED"]
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.emulator.read_vram_bank(0, 0x9801, 1) == b"\x41"
    assert phase2_rom.emulator.read_vram_bank(0, 0x9900, 1) != b"\x99"


def test_wrong_owner_and_stale_generation_reject_without_residency(phase2_rom: Phase2Rom) -> None:
    wrong = phase2_rom.descriptor("FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD", owner="RENDERER_YELLOW")
    assert phase2_rom.admit(wrong)[0] == phase2_rom.constants["REJECTED_WRONG_OWNER"]
    stale = phase2_rom.descriptor("FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD", generation=phase2_rom.generation + 1)
    assert phase2_rom.admit(stale)[0] == phase2_rom.constants["REJECTED_STALE_GENERATION"]
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x00"


def test_transition_order_and_generation_cancellation(phase2_rom: Phase2Rom) -> None:
    phase2_rom.write_fixed(0xC900, bytes(range(64)))
    request = phase2_rom.descriptor("FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD", resources=1, extent=64)
    assert phase2_rom.admit(request)[0] == phase2_rom.constants["ACCEPTED"]
    phase2_rom.call("PrepareNextFullColorRequest")
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.read_wram2("wFullColorTransitionLog", 4) == bytes(
        phase2_rom.constants[name] for name in ("PENDING", "PREPARED", "COMMITTING", "COMPLETE")
    )
    second = phase2_rom.descriptor("FULL_COLOR_REQUEST_MAP_ROW_PAIRED")
    assert phase2_rom.admit(second)[0] == phase2_rom.constants["ACCEPTED"]
    phase2_rom.call("AdvanceRendererGeneration")
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x00"


def test_resource_and_budget_revalidation_defer_before_committing(phase2_rom: Phase2Rom) -> None:
    phase2_rom.write_fixed(0xC900, bytes(range(64)))
    request = phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD",
    )
    phase2_rom.admit(request)
    phase2_rom.call("PrepareNextFullColorRequest")
    phase2_rom.write_wram2("wFullColorAvailableResources", b"\x00\x00")
    phase2_rom.write_wram2("wFullColorCommitBudget", b"\xff\xff")
    before = phase2_rom.emulator.read_palette_ram()
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.emulator.read_palette_ram() == before
    assert phase2_rom.read_wram2("wFullColorTransitionLog", 2) == bytes(
        [phase2_rom.constants["PENDING"], phase2_rom.constants["PREPARED"]]
    )


def test_complete_bg_and_obj_palette_payloads_commit(phase2_rom: Phase2Rom) -> None:
    bg = bytes((index * 3) & 0x7F for index in range(64))
    phase2_rom.write_fixed(0xC900, bg)
    phase2_rom.admit(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD", source=0xC900,
    ))
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.emulator.read_palette_ram() == bg

    obj = bytes((index * 5) & 0x7F for index in range(64))
    phase2_rom.write_fixed(0xC940, obj)
    phase2_rom.admit(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_OBJ_PALETTE_PAYLOAD", source=0xC940, desired=2,
        resources=1,
    ))
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.emulator.read_palette_ram(object_palettes=True) == obj


def test_paired_transfer_commits_whole_tiles_and_attributes(phase2_rom: Phase2Rom) -> None:
    tiles = bytes([0x11, 0x22, 0x33, 0x44])
    attributes = bytes([0x1F, 0x92, 0xE7, 0x10])
    phase2_rom.write_fixed(0xC900, tiles + attributes)
    phase2_rom.admit(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_MAP_ROW_PAIRED", source=0xC900, desired=0x0104, extent=4, reservation=8,
    ))
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.emulator.read_vram_bank(0, 0x9800, 4) == tiles
    assert phase2_rom.emulator.read_vram_bank(1, 0x9800, 4) == bytes(value & 0xEF for value in attributes)


def test_two_row_paired_transfer_writes_every_tile_and_attribute_once(
    phase2_rom: Phase2Rom,
) -> None:
    width, height = 20, 2
    extent = width * height
    tiles = bytes((index * 5 + 3) & 0x7F for index in range(extent))
    attributes = bytes((index * 3 + 1) & 0xFF for index in range(extent))
    phase2_rom.write_fixed(0xC900, tiles + attributes)
    result, flags = phase2_rom.admit(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_MAP_ROW_PAIRED",
        source=0xC900,
        desired=width | height << 8,
        extent=extent,
        reservation=2 * extent,
        flags=phase2_rom.constants["FULL_COLOR_FLAG_MOVEMENT_STRIP"],
    ))
    assert result == phase2_rom.constants["ACCEPTED"]
    assert flags & 0x10 == 0

    writes: list[tuple[int, int]] = []
    emu = phase2_rom.emulator
    start_name = "FullColorPhase5PairedRow20WritesStart"
    end_name = "FullColorPhase5PairedRow20WritesEnd"
    bank = emu.symbol_banks[start_name]
    start = emu.symbols[start_name]
    end = emu.symbols[end_name]
    assert emu.symbol_banks[end_name] == bank
    rom = (REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc").read_bytes()
    offset = bank * 0x4000 + start - 0x4000
    write_sites = [
        start + index
        for index, opcode in enumerate(rom[offset:offset + end - start])
        if opcode == 0x22  # ld [hli], a
    ]
    assert len(write_sites) == 2 * width * height

    def record_write(_: object) -> None:
        writes.append((emu.pyboy.memory[0xFF4F] & 1, emu.pyboy.register_file.HL))

    for address in write_sites:
        emu.pyboy.hook_register(bank, address, record_write, None)
    try:
        phase2_rom.call("RunFullColorOwnershipVBlank")
    finally:
        for address in write_sites:
            emu.pyboy.hook_deregister(bank, address)

    destinations = [
        0x9800 + row * 32 + column
        for row in range(height)
        for column in range(width)
    ]
    assert writes == (
        [(0, address) for address in destinations]
        + [(1, address) for address in destinations]
    )
    assert len(writes) == 2 * width * height
    for row in range(height):
        start = row * width
        destination = 0x9800 + row * 32
        assert emu.read_vram_bank(0, destination, width) == tiles[start:start + width]
        assert emu.read_vram_bank(1, destination, width) == bytes(
            value & 0xEF for value in attributes[start:start + width]
        )


def test_overlay_is_independent_of_vram_or_ambient_map_oracle(phase2_rom: Phase2Rom) -> None:
    tiles = bytes([0x08, 0x19, 0x2A, 0x3B])
    attribute_table = _linked_overworld_tile_attributes(phase2_rom)
    attributes = bytes(attribute_table[tile] for tile in tiles)
    assert attributes != bytes(value & 7 for value in tiles)
    phase2_rom.write_fixed(0xC900, tiles + attributes + b"ambient-not-consumed")
    for bank, fill in ((0, 0xA5), (1, 0x5A)):
        old = phase2_rom.emulator.pyboy.memory[0xFF4F]
        phase2_rom.emulator.pyboy.memory[0xFF4F] = bank
        for offset in range(4):
            phase2_rom.emulator.pyboy.memory[0x9800 + offset] = fill
        phase2_rom.emulator.pyboy.memory[0xFF4F] = old
    phase2_rom.admit(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_MAP_OVERLAY_PAIRED", source=0xC900, desired=0x0104, extent=4, reservation=8,
    ))
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.emulator.read_vram_bank(0, 0x9800, 4) == tiles
    assert phase2_rom.emulator.read_vram_bank(1, 0x9800, 4) == attributes


def test_audit_oam_declaration_uses_finished_shadow_without_legacy_remap(
    phase2_rom: Phase2Rom,
) -> None:
    batch = bytearray(160)
    for index in range(40):
        batch[index * 4 + 3] = 0xF8 | (index & 7)
    shadow = phase2_rom.emulator.symbols["wShadowOAM"]
    phase2_rom.write_fixed(shadow, bytes(batch))
    phase2_rom.write_fixed(0xC900, b"\xee" * 160)
    phase2_rom.write_wram2("wFullColorShadowOAMBatch", b"\xa5" * 160)
    before_hardware = bytes(
        phase2_rom.emulator.pyboy.memory[0xFE00 + index] for index in range(160)
    )

    assert phase2_rom.call("EnqueueFullColorOAMBatch", hl=0xC900)[0] == (
        phase2_rom.constants["DEFERRED"]
    )
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x00"
    assert bytes(
        phase2_rom.emulator.pyboy.memory[0xFE00 + index] for index in range(160)
    ) == before_hardware

    assert phase2_rom.call("EnqueueFullColorOAMBatch", hl=shadow)[0] == (
        phase2_rom.constants["ACCEPTED"]
    )
    descriptor = phase2_rom.read_wram2("wFullColorRequestDescriptors", 20)
    assert int.from_bytes(descriptor[8:10], "little") == shadow
    assert descriptor[18] == phase2_rom.constants["FULL_COLOR_FLAG_OAM_FINISHED"]
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert bytes(
        phase2_rom.emulator.pyboy.memory[0xFE00 + index] for index in range(160)
    ) == bytes(batch)
    assert phase2_rom.read_wram2("wFullColorShadowOAMBatch", 160) == b"\xa5" * 160


def test_prepared_scratch_cannot_be_overwritten_by_a_second_request(phase2_rom: Phase2Rom) -> None:
    first, second = bytes(range(64)), bytes(reversed(range(64)))
    phase2_rom.write_fixed(0xC900, first)
    phase2_rom.write_fixed(0xC940, second)
    assert phase2_rom.admit(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD", source=0xC900, desired=1,
    ))[0] == phase2_rom.constants["ACCEPTED"]
    phase2_rom.call("PrepareNextFullColorRequest")
    assert phase2_rom.admit(phase2_rom.descriptor(
        "FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD", source=0xC940, desired=2,
    ))[0] == phase2_rom.constants["ACCEPTED"]
    before = phase2_rom.read_wram2("wFullColorBGPaletteBase", 64)
    phase2_rom.call("PrepareNextFullColorRequest")
    assert phase2_rom.read_wram2("wFullColorBGPaletteBase", 64) == before == first
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.emulator.read_palette_ram() == first
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.emulator.read_palette_ram() == second


@pytest.mark.parametrize(
    ("request_class", "changes"),
    (
        ("FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD", {"extent": 1}),
        ("FULL_COLOR_REQUEST_OBJ_PALETTE_PAYLOAD", {"reservation": 1}),
        ("FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA", {"extent": 1}),
        ("FULL_COLOR_REQUEST_MAP_ROW_PAIRED", {"reservation": 1}),
        ("FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED", {"desired": 0x0201, "extent": 1}),
        ("FULL_COLOR_REQUEST_MAP_RECTANGLE_PAIRED", {"desired": 0x0202, "extent": 1}),
        ("FULL_COLOR_REQUEST_MAP_CONNECTION_PAIRED", {"reservation": 1}),
        ("FULL_COLOR_REQUEST_MAP_OVERLAY_PAIRED", {"extent": 2}),
        ("FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT", {"reservation": 1}),
    ),
)
def test_each_class_rejects_false_extent_or_reservation(
    phase2_rom: Phase2Rom, request_class: str, changes: dict[str, int]
) -> None:
    result, _ = phase2_rom.admit(phase2_rom.descriptor(request_class, **changes))
    assert result == phase2_rom.constants["DEFERRED"]
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\0"


@pytest.mark.parametrize(
    ("request_class", "resources", "reservation"),
    (
        ("FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD", 1, 64),
        ("FULL_COLOR_REQUEST_OBJ_PALETTE_PAYLOAD", 1, 64),
        ("FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA", 24, 200),
        ("FULL_COLOR_REQUEST_MAP_ROW_PAIRED", 6, 2),
        ("FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED", 6, 2),
        ("FULL_COLOR_REQUEST_MAP_RECTANGLE_PAIRED", 6, 2),
        ("FULL_COLOR_REQUEST_MAP_CONNECTION_PAIRED", 6, 2),
        ("FULL_COLOR_REQUEST_MAP_OVERLAY_PAIRED", 6, 2),
        ("FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT", 36, 17),
    ),
)
def test_every_class_rejects_high_resource_bits_and_reservation_plus_one(
    phase2_rom: Phase2Rom, request_class: str, resources: int, reservation: int
) -> None:
    high_mask = phase2_rom.descriptor(request_class, resources=resources | 0x100)
    assert phase2_rom.admit(high_mask)[0] == phase2_rom.constants["DEFERRED"]
    plus_one = phase2_rom.descriptor(request_class, reservation=reservation + 1)
    assert phase2_rom.admit(plus_one)[0] == phase2_rom.constants["DEFERRED"]
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\0"


def test_destination_is_validated_at_admission_and_again_before_commit(phase2_rom: Phase2Rom) -> None:
    phase2_rom.write_fixed(0xC900, b"\x41\x06")
    bad = phase2_rom.descriptor("FULL_COLOR_REQUEST_MAP_ROW_PAIRED", destination=0xD000)
    assert phase2_rom.admit(bad)[0] == phase2_rom.constants["DEFERRED"]
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\0"

    good = phase2_rom.descriptor("FULL_COLOR_REQUEST_MAP_ROW_PAIRED")
    assert phase2_rom.admit(good)[0] == phase2_rom.constants["ACCEPTED"]
    phase2_rom.call("PrepareNextFullColorRequest")
    descriptors = bytearray(phase2_rom.read_wram2("wFullColorRequestDescriptors", 20))
    descriptors[6:8] = (0xD000).to_bytes(2, "little")
    phase2_rom.write_wram2("wFullColorRequestDescriptors", descriptors)
    sentinel = phase2_rom.read_wram2("wRendererOwner")
    phase2_rom.call("RunFullColorOwnershipVBlank")
    assert phase2_rom.read_wram2("wRendererOwner") == sentinel
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\0"


def test_rom_byte_mutation_of_validator_trips_a_useful_contract(tmp_path: Path) -> None:
    source_rom = REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc"
    source_sym = REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym"
    symbols = numeric_symbols(source_sym)
    probe = Emulator(rom=source_rom, symbols=source_sym, results=tmp_path / "probe", cgb=True)
    try:
        address = probe.symbols["ValidateFullColorRequestResourcesSelected"]
        bank = probe.symbol_banks["ValidateFullColorRequestResourcesSelected"]
    finally:
        probe.close()
    blob = bytearray(source_rom.read_bytes())
    offset = bank * 0x4000 + address - 0x4000
    blob[offset:offset + 2] = b"\xa7\xc9"  # and a; ret -- bypass validation
    mutant_rom = tmp_path / "mutant.gbc"
    mutant_rom.write_bytes(blob)
    emulator = Emulator(rom=mutant_rom, symbols=source_sym, results=tmp_path / "mutant", cgb=True)
    mutant = Phase2Rom(emulator, symbols)
    try:
        mutant.activate()
        with pytest.raises(AssertionError, match="exact palette extent"):
            result = mutant.admit(mutant.descriptor(
                "FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD", extent=1,
            ))[0]
            assert result != mutant.constants["ACCEPTED"], "exact palette extent mutation escaped"
    finally:
        emulator.close()

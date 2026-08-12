"""Real audit-ROM OAM full-batch, DMA and fallback checks."""

import pytest

from tools.rom_tests.tests.unit.full_color.test_phase2_scheduler_rom import Phase2Rom, phase2_rom


def _farcall_from_wram(
    phase2_rom: Phase2Rom,
    name: str,
    *,
    c: int = 0,
    de: int = 0,
    entry_bank: int = 7,
) -> tuple[int, int]:
    """Execute the production Bankswitch path from a deliberately foreign bank."""
    emu = phase2_rom.emulator
    regs = emu.pyboy.register_file
    target = emu.symbols[name]
    target_bank = emu.symbol_banks[name]
    bankswitch = emu.symbols["Bankswitch"]
    trampoline = 0xC6F0
    stack = 0xCFFE
    code = bytes((
        0x0E, c,                         # ld c, identity
        0x11, de & 0xFF, de >> 8,       # ld de, attribute pointer
        0x06, target_bank,               # ld b, BANK(target)
        0x21, target & 0xFF, target >> 8,  # ld hl, target
        0xCD, bankswitch & 0xFF, bankswitch >> 8,
        0xC9,
    ))
    phase2_rom.write_fixed(trampoline, code)
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


@pytest.mark.parametrize(
    ("identity", "object_index", "palette", "fallback_kind"),
    (
        (1, 0, 1, None),
        (3, 7, 3, None),
        (13, 19, 4, None),
        (47, 31, 5, None),
        (61, 39, 2, None),
        (0, 4, 0, "FULL_COLOR_FALLBACK_UNMAPPED"),
        (2, 5, 0, "FULL_COLOR_FALLBACK_UNMAPPED"),
        (4, 6, 0, "FULL_COLOR_FALLBACK_UNMAPPED"),
        (5, 7, 0, "FULL_COLOR_FALLBACK_UNMAPPED"),
        (6, 8, 0, "FULL_COLOR_FALLBACK_UNMAPPED"),
        (7, 9, 0, "FULL_COLOR_FALLBACK_UNMAPPED"),
    ),
)
def test_farcall_mapper_uses_only_preserved_identity_and_attribute_pointer(
    phase2_rom: Phase2Rom,
    identity: int,
    object_index: int,
    palette: int,
    fallback_kind: str | None,
) -> None:
    attribute = phase2_rom.emulator.symbols["wShadowOAM"] + object_index * 4 + 3
    phase2_rom.emulator.pyboy.memory[attribute] = 0xF8 | 7
    _, flags = _farcall_from_wram(
        phase2_rom, "MapFullColorOAMAttributeFar", c=identity, de=attribute,
    )
    # Bankswitch restores the caller bank through A. The stable public result
    # is the attribute byte plus carry/fallback observability, not A.
    assert phase2_rom.emulator.pyboy.memory[attribute] == 0xF8 | palette
    if fallback_kind is None:
        assert flags & 0x10 == 0
        assert phase2_rom.read_wram2("wFullColorReconstructionItems", 4) == bytes(4)
    else:
        assert flags & 0x10
        assert phase2_rom.read_wram2("wFullColorReconstructionItems", 4) == bytes((
            1,
            phase2_rom.constants[fallback_kind],
            identity,
            object_index,
        ))


def test_owned_mainline_producer_reaches_one_scheduler_dma_through_real_bankswitch(
    phase2_rom: Phase2Rom,
) -> None:
    emu = phase2_rom.emulator.pyboy
    shadow = phase2_rom.emulator.symbols["wShadowOAM"]
    for offset in range(160):
        emu.memory[shadow + offset] = offset ^ 0xA5
        emu.memory[0xFE00 + offset] = 0x5A
    # -1 takes the ordinary "no rebuild requested" return from .build. The
    # owned producer must still enqueue the already-finished full batch.
    emu.memory[phase2_rom.emulator.symbols["wUpdateSpritesEnabled"]] = 0xFF

    _, producer_flags = _farcall_from_wram(
        phase2_rom, "FullColorPhase5PrepareOwnedMainlineFrame"
    )
    assert producer_flags & 0x10 == 0
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x01"

    dma_calls = [0]

    def record_dma(_: object) -> None:
        dma_calls[0] += 1

    key = (
        phase2_rom.emulator.symbol_banks["FullColorPhase5OAMDMAStart"],
        phase2_rom.emulator.symbols["FullColorPhase5OAMDMAStart"],
    )
    emu.hook_register(*key, record_dma, None)
    try:
        _, flags = _farcall_from_wram(
            phase2_rom, "FullColorVBlankOwnerConsumed"
        )
        # Re-entering without another producer build must retain the exact
        # hardware batch and must not replay DMA.
        _farcall_from_wram(phase2_rom, "FullColorVBlankOwnerConsumed")
    finally:
        emu.hook_deregister(*key)

    assert flags & 0x10 == 0
    assert dma_calls == [1]
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x00"
    assert bytes(emu.memory[0xFE00 + i] for i in range(160)) == bytes(
        emu.memory[shadow + i] for i in range(160)
    )


def test_no_arg_overlay_farcall_rebuilds_semantic_abi_after_bankswitch(
    phase2_rom: Phase2Rom,
) -> None:
    tile_map = phase2_rom.emulator.symbols["wTileMap"]
    payload = bytes((index * 5) & 0xFF for index in range(20 * 18))
    phase2_rom.write_fixed(tile_map, payload)
    phase2_rom.write_wram2("wFullColorAuthorityVRAMView", b"\x20\x98")

    _, flags = _farcall_from_wram(
        phase2_rom, "EnqueueFullColorCurrentTileMapOverlayFar",
    )

    assert flags & 0x10 == 0
    assert phase2_rom.read_wram2("wFullColorRequestCount") == b"\x01"
    descriptor = phase2_rom.read_wram2("wFullColorRequestDescriptors", 20)
    assert descriptor[0] & 0x0F == (
        phase2_rom.constants["FULL_COLOR_REQUEST_MAP_OVERLAY_PAIRED"]
    )
    assert descriptor[6:8] == b"\x20\x98"
    assert descriptor[10:12] == bytes((20, 18))
    phase2_rom.write_fixed(tile_map, b"\xee" * len(payload))
    phase2_rom.call("RunFullColorOwnershipVBlank")
    for row in range(18):
        start = row * 20
        assert phase2_rom.emulator.read_vram_bank(0, 0x9820 + row * 32, 20) == (
            payload[start:start + 20]
        )


def test_route1_youngster_identity_falls_back_without_losing_oam_control_bits(
    phase2_rom: Phase2Rom,
) -> None:
    """Route 1's authored SPRITE_YOUNGSTER ($04) is not a palette number."""
    shadow = phase2_rom.emulator.symbols["wShadowOAM"]
    identities = (4, 1, 3, 13, 47, 61)
    for index, identity in enumerate(identities):
        attribute = shadow + index * 4 + 3
        phase2_rom.emulator.pyboy.memory[attribute] = 0xD8 | 7
        _farcall_from_wram(
            phase2_rom,
            "MapFullColorOAMAttributeFar",
            c=identity,
            de=attribute,
        )

    attributes = bytes(
        phase2_rom.emulator.pyboy.memory[shadow + index * 4 + 3]
        for index in range(6)
    )
    assert attributes == bytes((0xD8, 0xD9, 0xDB, 0xDC, 0xDD, 0xDA))
    assert all(attribute & 0xF8 == 0xD8 for attribute in attributes)


def test_oam_fallback_ledger_is_bounded_exact_and_marks_overflow(phase2_rom: Phase2Rom) -> None:
    shadow = phase2_rom.emulator.symbols["wShadowOAM"]
    for _ in range(7):
        for index in range(40):
            attribute = shadow + index * 4 + 3
            _farcall_from_wram(
                phase2_rom,
                "MapFullColorOAMAttributeFar",
                c=0xFF,
                de=attribute,
            )
    assert phase2_rom.read_wram2("wFullColorReconstructionItems", 4) == bytes((
        0xFF,
        phase2_rom.constants["FULL_COLOR_FALLBACK_MISSING_IDENTITY"],
        0xFF,
        39,
    ))


def test_phase2_oam_never_touches_write_only_sram_controls(phase2_rom: Phase2Rom) -> None:
    # This is execution-sensitive: SRAM holds sentinel bytes in two banks and
    # the fallback path runs. No Phase 2 code may guess/restore bank zero.
    for bank, value in ((1, 0x51), (3, 0x73)):
        phase2_rom.emulator.pyboy.memory[0x0000] = 0x0A
        phase2_rom.emulator.pyboy.memory[0x4000] = bank
        phase2_rom.emulator.pyboy.memory[0xA000] = value
    phase2_rom.emulator.pyboy.memory[0x4000] = 1
    attribute = phase2_rom.emulator.symbols["wShadowOAM"] + 3
    _farcall_from_wram(
        phase2_rom,
        "MapFullColorOAMAttributeFar",
        c=0xFF,
        de=attribute,
    )
    assert phase2_rom.emulator.pyboy.memory[0xA000] == 0x51

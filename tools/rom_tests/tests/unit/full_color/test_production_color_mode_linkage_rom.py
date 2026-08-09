"""Product-matrix linkage and reachability proofs for bounded Color mode."""

from __future__ import annotations

import re

import pytest

from tools.rom_tests.emulator import Emulator
from tools.rom_tests.full_color.map_background_snapshot import MANIFEST_PATH, verify
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT, result_directory
from tools.rom_tests.tests.unit.full_color.test_phase2_scheduler_rom import (
    Phase2Rom,
    numeric_symbols,
)


PRODUCTS = ("pokeyellow", "pokeyellow_debug", "pokeyellow_vc")
PRODUCTION_RENDERER_SURFACE = frozenset(
    {
        "RouteRendererOwnershipVBlank",
        "OptionsMenu_ColorMode",
        "FullColorOverworldBGPalettes",
        "FullColorOverworldBGPalettesEnd",
        "FullColorOverworldTileAttributes",
        "FullColorOverworldTileAttributesEnd",
        "PassiveFullColorApplyMap",
        "PassiveFullColorHandleConnection",
        "PassiveFullColorPrepareRedrawAttributes",
        "PassiveFullColorPrepareColumnAttributes",
        "PassiveFullColorInvalidateOverlayAttributes",
        "PassiveFullColorPrepareMenuOverlay",
        "PassiveFullColorPrepareTextOverlay",
        "PassiveFullColorRestoreAfterMenu",
        "PassiveFullColorPrepareBattleHandoff",
        "PassiveFullColorVBlank",
        "wPassiveFullColorStateStart",
        "wPassiveFullColorStateEnd",
    }
)
FORBIDDEN_PRODUCTION_MARKERS = (
    "Phase2Audit",
    "Phase2Hostile",
    "PollFullColorPhase2DebugCommand",
    "SnapshotFullColorPhase2DebugSelected",
    "wFullColorPhase2Debug",
    "wFullColorDebugCarrier",
    "FullColorCanary",
    "InitFullColorScheduler",
    "BeginFullColorMapEntry",
    "FullColorProductionLifecycle",
    "FullColorProductionScheduler",
)
REQUIRED_REACHABLE_RENDERER = frozenset(
    {
        "PassiveFullColorApplyMap",
        "PassiveFullColorPrepareRedrawAttributes",
        "PassiveFullColorPrepareColumnAttributes",
        "PassiveFullColorPrepareMenuHandoff",
        "PassiveFullColorRestoreAfterMenu",
        "PassiveFullColorPrepareBattleHandoff",
        "PassiveFullColorShouldColorOverlay",
        "PassiveFullColorInvalidateOverlayAttributes",
        "PassiveFullColorPrepareMenuOverlay",
        "PassiveFullColorPrepareTextOverlay",
        "PassiveFullColorOverlayAttributeGDMA",
        "PassiveFullColorVBlank",
    }
)
PRODUCTION_ROOTS = (
    "Start",
    "VBlank",
    "InitRendererOwnership",
    "ResetRendererOwnership",
    "SoftResetRendererOwnership",
    "OverworldLoop",
    "LoadMapData",
    "ScheduleSouthRowRedraw",
    "DisplayStartMenu",
    # DisplayStartMenu pins bank 4 before its ROM0 trampoline jumps here; the
    # static walker cannot infer that bank state from BankswitchCommon.
    "FullColorDisplayStartMenu",
    "DisplayPartyMenu",
    "InitBattle",
    "DisplayBattleMenu",
)
YELLOW_VBLANK_CALLS = (
    "AutoBgMapTransfer",
    "VBlankCopyBgMap",
    "RedrawRowOrColumn",
    "VBlankCopy",
    "VBlankCopyDouble",
    "UpdateMovingBgTiles",
    "PrepareOAMData",
)
RSVBK = 0xFF70
RVBK = 0xFF4F
INTERRUPT_FLAGS = 0xFF0F
INTERRUPT_ENABLE = 0xFFFF
BOOTROM_DISABLE = 0xFF50
VBLANK_INTERRUPT = 1
WRAM_PROGRAM = 0xD100
RETURN_PROBE = 0x0100
HARNESS_LOOP = 0xFF80


def _symbols(
    product: str,
) -> tuple[dict[str, tuple[int, int]], dict[tuple[int, int], set[str]]]:
    by_name: dict[str, tuple[int, int]] = {}
    by_address: dict[tuple[int, int], set[str]] = {}
    for line in (
        (REPOSITORY_ROOT / f"{product}.sym").read_text(encoding="utf-8").splitlines()
    ):
        match = re.fullmatch(r"([0-9a-fA-F]+):([0-9a-fA-F]+) (\S+)", line)
        if match is None:
            continue
        location = (int(match.group(1), 16), int(match.group(2), 16))
        by_name[match.group(3)] = location
        if "." not in match.group(3):
            by_address.setdefault(location, set()).add(match.group(3))
    return by_name, by_address


@pytest.mark.parametrize("product", PRODUCTS)
def test_shipped_products_link_renderer_and_exclude_audit_machinery(
    product: str,
) -> None:
    symbols, _ = _symbols(product)
    assert PRODUCTION_RENDERER_SURFACE <= symbols.keys()
    assert not {
        name
        for name in symbols
        if any(marker in name for marker in FORBIDDEN_PRODUCTION_MARKERS)
    }

    assert symbols["wRendererStateStart"] == (2, 0xD000)
    assert symbols["wRendererStateEnd"] == (2, 0xD00D)
    assert symbols["wPassiveFullColorStateStart"] == (2, 0xD800)
    assert symbols["wPassiveFullColorAttributeRectangle"] == (2, 0xD810)
    assert symbols["wPassiveFullColorStateEnd"] == (2, 0xDA50)
    assert (
        symbols["FullColorOverworldBGPalettesEnd"][1]
        - symbols["FullColorOverworldBGPalettes"][1]
        == 64
    )
    assert (
        symbols["FullColorOverworldTileAttributesEnd"][1]
        - symbols["FullColorOverworldTileAttributes"][1]
        == 256
    )


def _read_wram2(emulator: Emulator, start: int, end: int) -> bytes:
    prior = emulator.pyboy.memory[0xFF70]
    emulator.pyboy.memory[0xFF70] = 2
    try:
        return bytes(emulator.pyboy.memory[address] for address in range(start, end))
    finally:
        emulator.pyboy.memory[0xFF70] = prior


def _run_complete_vblank(
    emulator: Emulator, observed_symbols: frozenset[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    memory = emulator.pyboy.memory
    registers = emulator.pyboy.register_file
    memory[BOOTROM_DISABLE] = 1
    prior_bank = memory[RSVBK]
    memory[RSVBK] = 6
    memory[WRAM_PROGRAM : WRAM_PROGRAM + 3] = b"\xf3\x18\xfe"
    memory[INTERRUPT_ENABLE] = 0
    memory[INTERRUPT_FLAGS] = 0
    registers.PC = WRAM_PROGRAM
    registers.SP = 0xFFFC
    emulator.pyboy.tick(1, render=False, sound=False)
    memory[WRAM_PROGRAM : WRAM_PROGRAM + 4] = bytes(
        (0xFB, 0xC3, RETURN_PROBE & 0xFF, RETURN_PROBE >> 8)
    )
    registers.PC = WRAM_PROGRAM
    registers.SP = 0xFFFC
    memory[RSVBK] = 6
    memory[RVBK] = 1
    memory[INTERRUPT_ENABLE] = VBLANK_INTERRUPT
    memory[INTERRUPT_FLAGS] = VBLANK_INTERRUPT
    yellow_calls: list[str] = []
    color_calls: list[str] = []
    returned = False

    def record_yellow(context: str) -> None:
        yellow_calls.append(context)

    def record_color(context: str) -> None:
        color_calls.append(context)

    def returned_to_probe(_: object) -> None:
        nonlocal returned
        returned = True
        memory[INTERRUPT_ENABLE] = 0
        memory[HARNESS_LOOP] = 0x18
        memory[HARNESS_LOOP + 1] = 0xFE
        registers.PC = HARNESS_LOOP

    hooks: list[tuple[int, int]] = []
    locations: dict[tuple[int, int], list[str]] = {}
    for name in observed_symbols:
        locations.setdefault(
            (emulator.symbol_banks[name], emulator.symbols[name]), []
        ).append(name)
    for (bank, address), names in locations.items():
        label = "/".join(sorted(names))
        emulator.pyboy.hook_register(bank, address, record_color, label)
        hooks.append((bank, address))
    for name in YELLOW_VBLANK_CALLS:
        bank = emulator.symbol_banks[name]
        address = emulator.symbols[name]
        emulator.pyboy.hook_register(bank, address, record_yellow, name)
        hooks.append((bank, address))
    emulator.pyboy.hook_register(0, RETURN_PROBE, returned_to_probe, None)
    try:
        emulator.pyboy.tick(1, render=False, sound=False)
    finally:
        emulator.pyboy.hook_deregister(0, RETURN_PROBE)
        for bank, address in reversed(hooks):
            emulator.pyboy.hook_deregister(bank, address)
        memory[RSVBK] = prior_bank
    assert returned, "production VBlank did not return through RETI"
    return tuple(yellow_calls), tuple(color_calls)


@pytest.mark.parametrize("product", PRODUCTS)
@pytest.mark.parametrize("yellow_mode", (False, True), ids=("color", "yellow"))
def test_complete_product_vblank_reaches_passive_renderer_and_preserves_yellow(
    request: pytest.FixtureRequest, product: str, yellow_mode: bool
) -> None:
    emulator = Emulator(
        rom=REPOSITORY_ROOT / f"{product}.gbc",
        symbols=REPOSITORY_ROOT / f"{product}.sym",
        results=result_directory(request.node.nodeid),
        cgb=True,
    )
    try:
        rom = Phase2Rom(emulator, numeric_symbols(REPOSITORY_ROOT / f"{product}.sym"))
        dma_stub = bytes((0x3E, 0xC3, 0xE0, 0x46, 0x3E, 0x28, 0x3D, 0x20, 0xFD, 0xC9))
        for offset, value in enumerate(dma_stub):
            emulator.pyboy.memory[0xFF80 + offset] = value
        rom.call("InitRendererOwnership")
        emulator.pyboy.memory[RSVBK] = 1
        emulator.pyboy.memory[emulator.symbols["wCurMap"]] = 0
        emulator.pyboy.memory[emulator.symbols["wUnusedObtainedBadges"]] = int(
            yellow_mode
        )
        emulator.pyboy.memory[0xFF40] &= 0x7F
        rom.call("PassiveFullColorApplyMap")
        if not yellow_mode:
            rom.write_wram2("wPassiveFullColorPalettePending", 1)
        owner_state = _read_wram2(
            emulator,
            emulator.symbols["wRendererStateStart"],
            emulator.symbols["wRendererStateEnd"],
        )
        yellow_calls, color_calls = _run_complete_vblank(
            emulator, frozenset({"PassiveFullColorVBlank"})
        )
        assert color_calls == ("PassiveFullColorVBlank",)
        assert set(YELLOW_VBLANK_CALLS) <= set(yellow_calls)
        assert (
            _read_wram2(
                emulator,
                emulator.symbols["wRendererStateStart"],
                emulator.symbols["wRendererStateEnd"],
            )
            == owner_state
        )
        assert rom.read_wram2("wPassiveFullColorActive") == bytes((not yellow_mode,))
        assert rom.read_wram2("wPassiveFullColorPalettePending") == b"\x00"
    finally:
        emulator.close()


def _instruction_length(mnemonic: str, opcode: int) -> int:
    if opcode == 0xCB:
        return 2
    if "d16" in mnemonic or "a16" in mnemonic:
        return 3
    if "d8" in mnemonic or "a8" in mnemonic or "r8" in mnemonic:
        return 2
    return 1


def _reachable_symbols(
    product: str,
    roots: tuple[str, ...],
) -> set[str]:
    from pyboy.core.opcodes import CPU_COMMANDS

    symbols, by_address = _symbols(product)
    rom = (REPOSITORY_ROOT / f"{product}.gbc").read_bytes()
    work = [symbols[root] for root in roots]
    visited_instructions: set[tuple[int, int]] = set()
    reached: set[str] = set()
    while work:
        bank, address = work.pop()
        location = (bank, address)
        if location in visited_instructions:
            continue
        visited_instructions.add(location)
        if location in by_address:
            reached.update(by_address[location])
        offset = address if bank == 0 else bank * 0x4000 + address - 0x4000
        opcode = rom[offset]
        mnemonic = CPU_COMMANDS[opcode]
        length = _instruction_length(mnemonic, opcode)
        fallthrough = (bank, address + length)
        if opcode in {0xC9, 0xD9, 0xE9, 0x10, 0x76}:
            continue
        if opcode in {0x18, 0x20, 0x28, 0x30, 0x38}:
            displacement = int.from_bytes(
                rom[offset + 1 : offset + 2], "little", signed=True
            )
            work.append((bank, (address + 2 + displacement) & 0xFFFF))
            if opcode != 0x18:
                work.append(fallthrough)
            continue
        if opcode in {0xC2, 0xC3, 0xCA, 0xD2, 0xDA, 0xC4, 0xCC, 0xCD, 0xD4, 0xDC}:
            target_address = int.from_bytes(rom[offset + 1 : offset + 3], "little")
            target_bank = 0 if target_address < 0x4000 else bank
            target = (target_bank, target_address)
            bankswitch = symbols.get("Bankswitch")
            if (
                target == bankswitch
                and offset >= 5
                and rom[offset - 5] == 0x06
                and rom[offset - 3] == 0x21
            ):
                target = (
                    rom[offset - 4],
                    int.from_bytes(rom[offset - 2 : offset], "little"),
                )
            work.append(target)
            if opcode != 0xC3:
                work.append(fallthrough)
            continue
        if opcode in {0xC0, 0xC8, 0xD0, 0xD8}:
            work.append(fallthrough)
            continue
        if opcode in {0xC7, 0xCF, 0xD7, 0xDF, 0xE7, 0xEF, 0xF7, 0xFF}:
            work.append((0, opcode & 0x38))
        work.append(fallthrough)
    return reached


@pytest.mark.parametrize("product", PRODUCTS)
def test_static_production_roots_reach_bounded_renderer_not_audit_pipeline(
    product: str,
) -> None:
    symbols, _ = _symbols(product)
    bank, address = symbols["RouteRendererOwnershipVBlank"]
    offset = bank * 0x4000 + address - 0x4000
    route = (REPOSITORY_ROOT / f"{product}.gbc").read_bytes()[offset : offset + 4]
    assert route[0] == 0xC9
    assert "PollFullColorDebugCommand" not in symbols
    assert set(PRODUCTION_ROOTS) <= symbols.keys()
    reached = _reachable_symbols(product, PRODUCTION_ROOTS)
    assert REQUIRED_REACHABLE_RENDERER <= reached
    assert not {
        name
        for name in reached
        if any(marker in name for marker in FORBIDDEN_PRODUCTION_MARKERS)
    }


def test_audit_adds_diagnostics_without_changing_renderer_payload() -> None:
    audit, _ = _symbols("pokeyellow_phase2_audit")
    assert {
        "PollFullColorPhase2DebugCommand",
        "wFullColorDebugCarrierStart",
        "wPassiveFullColorActive",
        "PassiveFullColorVBlank",
        "FullColorCanaryBGPalettes",
        "FullColorCanaryOBJPalettes",
        "FullColorCanaryOverworldTileClasses",
        "OptionsMenu_ColorMode",
        "FullColorOverworldBGPalettes",
        "FullColorOverworldTileAttributes",
    } <= audit.keys()
    audit_rom = (REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc").read_bytes()
    for product in PRODUCTS:
        symbols, _ = _symbols(product)
        rom = (REPOSITORY_ROOT / f"{product}.gbc").read_bytes()
        for start, end in (
            ("FullColorOverworldBGPalettes", "FullColorOverworldBGPalettesEnd"),
            ("FullColorOverworldTileAttributes", "FullColorOverworldTileAttributesEnd"),
        ):
            audit_offset = audit[start][0] * 0x4000 + audit[start][1] - 0x4000
            product_offset = symbols[start][0] * 0x4000 + symbols[start][1] - 0x4000
            size = audit[end][1] - audit[start][1]
            assert (
                audit_rom[audit_offset : audit_offset + size]
                == rom[product_offset : product_offset + size]
            )


def test_reviewed_map_background_evidence_covers_production_and_audit_products() -> (
    None
):
    manifest = verify(REPOSITORY_ROOT, MANIFEST_PATH)
    assert [row["product"] for row in manifest["products"]] == [
        "pokeyellow",
        "pokeyellow_debug",
        "pokeyellow_vc",
        "pokeyellow_phase2_audit",
    ]
    for product in manifest["products"]:
        assert product["payloads"]["FullColorOverworldBGPalettes"]["size"] == 64
        assert product["payloads"]["FullColorOverworldTileAttributes"]["size"] == 256

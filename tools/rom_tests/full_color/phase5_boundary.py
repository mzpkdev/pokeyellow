"""Direct audit-ROM carrier for Phase 5 selected-boundary observations."""

from __future__ import annotations

from dataclasses import dataclass

from tools.rom_tests.emulator import Emulator


@dataclass(slots=True)
class Phase5AuditRom:
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
        regs.D, regs.E = de >> 8, de & 0xFF
        regs.HL, regs.SP = hl, stack
        emu.pyboy.memory[stack], emu.pyboy.memory[stack + 1] = 0, 1
        emu.pyboy.memory[0xFFFF] = 0
        if bank:
            emu.pyboy.memory[0x2000] = bank
        emu.pyboy.memory[emu.symbols["hLoadedROMBank"]] = bank
        regs.PC = address
        returned = False

        def stop(_: object) -> None:
            nonlocal returned
            returned = True
            emu.pyboy.memory[0xC6F0] = 0x18
            emu.pyboy.memory[0xC6F1] = 0xFE
            regs.PC = 0xC6F0

        emu.pyboy.hook_register(0, 0x0100, stop, None)
        try:
            for _ in range(64):
                emu.pyboy.tick(1, render=False, sound=False)
                if returned:
                    break
        finally:
            emu.pyboy.hook_deregister(0, 0x0100)
        if not returned:
            raise AssertionError(f"{name} did not return (PC={regs.PC:#06x})")
        return regs.A, regs.F

    def write_fixed(self, address: int, data: bytes) -> None:
        for offset, value in enumerate(data):
            self.emulator.pyboy.memory[address + offset] = value

    def write_wram2(self, symbol: str, data: bytes) -> None:
        old = self.emulator.pyboy.memory[0xFF70]
        self.emulator.pyboy.memory[0xFF70] = 2
        try:
            address = self.emulator.symbols[symbol]
            for offset, value in enumerate(data):
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

    def activate(self) -> None:
        self.call("InitRendererOwnership")
        dma = bytes((0x3E, 0xC3, 0xE0, 0x46, 0x3E, 0x28, 0x3D, 0x20, 0xFD, 0xC9))
        for offset, value in enumerate(dma):
            self.emulator.pyboy.memory[0xFF80 + offset] = value
        self.write_wram2(
            "wRendererOwner",
            bytes((self.constants["RENDERER_FULL_COLOR_OVERWORLD"],)),
        )
        self.write_wram2("wRendererPhase", bytes((self.constants["OVERWORLD_ACTIVE"],)))
        self.write_wram2("wRendererAdmissionOpen", b"\1")
        self.call("InitFullColorScheduler")

    @property
    def generation(self) -> int:
        return int.from_bytes(self.read_wram2("wRendererGeneration", 4), "little")

    def admit_unit(self, request_constant: str) -> None:
        request_class = self.constants[request_constant]
        self.write_fixed(0xC900, b"\x41\x06")
        descriptor = b"".join((
            bytes((request_class, self.constants["RENDERER_FULL_COLOR_OVERWORLD"])),
            self.generation.to_bytes(4, "little"),
            (0x9800).to_bytes(2, "little"),
            (0xC900).to_bytes(2, "little"),
            (0x0101).to_bytes(2, "little"),
            (6).to_bytes(2, "little"),
            (1).to_bytes(2, "little"),
            (2).to_bytes(2, "little"),
            b"\0\0",
        ))
        self.write_fixed(0xC700, descriptor)
        result, flags = self.call("AdmitFullColorRequest", hl=0xC700)
        if result != self.constants["ACCEPTED"] or flags & 0x10:
            raise AssertionError("Phase 5 boundary descriptor was not admitted")

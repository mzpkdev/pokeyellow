"""Cold-boot regression for the audit-only natural map-entry route."""

from __future__ import annotations

import pytest

from tools.rom_tests.emulator import Emulator
from tools.rom_tests.scenarios.new_game import reach_bedroom_overworld
from tools.rom_tests.scenarios.oaks_lab import (
    PALLET_TOWN,
    finish_rival_battle_and_leave_lab,
    follow_oak_and_receive_pikachu,
    walk_from_bedroom_to_oak,
    walk_from_bedroom_to_pallet,
)
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT, result_directory
from tools.rom_tests.tests.unit.full_color.test_phase2_scheduler_rom import (
    Phase2Rom,
    numeric_symbols,
)


ROUTE_1 = 0x0C


@pytest.fixture
def audit_emulator(request: pytest.FixtureRequest) -> Emulator:
    emulator = Emulator(
        rom=REPOSITORY_ROOT / "pokeyellow_phase2_audit.gbc",
        symbols=REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym",
        results=result_directory(request.node.nodeid),
        cgb=True,
    )
    try:
        yield emulator
    finally:
        emulator.close()


def _read_u16(emulator: Emulator, symbol: str) -> int:
    address = emulator.symbols[symbol]
    return emulator.pyboy.memory[address] | emulator.pyboy.memory[address + 1] << 8


def _read_wram2(emulator: Emulator, symbol: str) -> int:
    old_bank = emulator.pyboy.memory[0xFF70]
    emulator.pyboy.memory[0xFF70] = 2
    try:
        return emulator.pyboy.memory[emulator.symbols[symbol]]
    finally:
        emulator.pyboy.memory[0xFF70] = old_bank


def _write_wram2(emulator: Emulator, symbol: str, value: int) -> None:
    old_bank = emulator.pyboy.memory[0xFF70]
    emulator.pyboy.memory[0xFF70] = 2
    try:
        emulator.pyboy.memory[emulator.symbols[symbol]] = value
    finally:
        emulator.pyboy.memory[0xFF70] = old_bank


def _read_wram2_bytes(emulator: Emulator, symbol: str, size: int) -> bytes:
    old_bank = emulator.pyboy.memory[0xFF70]
    emulator.pyboy.memory[0xFF70] = 2
    try:
        address = emulator.symbols[symbol]
        return bytes(emulator.pyboy.memory[address:address + size])
    finally:
        emulator.pyboy.memory[0xFF70] = old_bank


def _write_wram2_bytes(emulator: Emulator, symbol: str, payload: bytes) -> None:
    old_bank = emulator.pyboy.memory[0xFF70]
    emulator.pyboy.memory[0xFF70] = 2
    try:
        address = emulator.symbols[symbol]
        emulator.pyboy.memory[address:address + len(payload)] = payload
    finally:
        emulator.pyboy.memory[0xFF70] = old_bank


def _read_wram2_at(emulator: Emulator, address: int, size: int) -> bytes:
    old_bank = emulator.pyboy.memory[0xFF70]
    emulator.pyboy.memory[0xFF70] = 2
    try:
        return bytes(emulator.pyboy.memory[address:address + size])
    finally:
        emulator.pyboy.memory[0xFF70] = old_bank


def _map_cell_addresses(destination: int, width: int, height: int) -> list[int]:
    """Mirror the scheduler's 32-byte-stride, 1 KiB-wrapping map traversal."""
    base = destination & 0xFC00
    result: list[int] = []
    row = destination
    for _ in range(height):
        cell = row
        for _ in range(width):
            result.append(cell)
            cell = base | ((cell + 1) & 0x03FF)
        row = base | ((row + 32) & 0x03FF)
    return result


def _assert_stable_bedroom_semantics(emulator: Emulator) -> None:
    registers = emulator.pyboy.register_file
    assert emulator.is_in_bedroom_overworld()
    assert _read_u16(emulator, "wCurMapDataPtr") == emulator.symbols[
        "RedsHouse2F_Blocks"
    ]
    assert registers.PC != 0x0038
    assert 0xD000 <= registers.SP <= 0xDFFF


def test_audit_cold_boot_reaches_stable_semantic_bedroom_state(
    audit_emulator: Emulator,
) -> None:
    reach_bedroom_overworld(audit_emulator)

    # A transient map/status predicate previously returned before a corrupt
    # banked map-header return fell into RST $38. Recheck the complete header,
    # spawn, LCD, stack, and map-authority state across subsequent frames.
    for _ in range(8):
        audit_emulator.tick(15)
        _assert_stable_bedroom_semantics(audit_emulator)


@pytest.mark.parametrize(("lcd_enabled", "disable_calls"), ((False, 0), (True, 1)))
def test_audit_home_map_authority_preserves_success_bank_stack_and_lcd_branch(
    audit_emulator: Emulator,
    lcd_enabled: bool,
    disable_calls: int,
) -> None:
    reach_bedroom_overworld(audit_emulator)
    rom = Phase2Rom(
        audit_emulator,
        numeric_symbols(REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym"),
    )
    pyboy = audit_emulator.pyboy
    calls = [0]

    def record_disable(_: object) -> None:
        calls[0] += 1

    def finish_direct_delay(_: object) -> None:
        pyboy.memory[audit_emulator.symbols["hVBlankOccurred"]] = 0
        pyboy.register_file.PC = audit_emulator.symbols["DelayFrame.halt"] + 1

    key = (
        audit_emulator.symbol_banks["DisableLCD"],
        audit_emulator.symbols["DisableLCD"],
    )
    pyboy.hook_register(*key, record_disable, None)
    delay_key = (
        audit_emulator.symbol_banks["DelayFrame.halt"],
        audit_emulator.symbols["DelayFrame.halt"],
    )
    pyboy.hook_register(*delay_key, finish_direct_delay, None)
    try:
        pyboy.memory[audit_emulator.symbols["wStatusFlags7"]] |= 1 << 1
        if lcd_enabled:
            pyboy.memory[0xFF40] |= 0x80
        else:
            pyboy.memory[0xFF40] &= 0x7F
        _, flags = rom.call("FullColorAuditLoadMapDataHomeAuthority")
    finally:
        pyboy.hook_deregister(*key)
        pyboy.hook_deregister(*delay_key)

    assert flags & 0x10 == 0
    assert calls[0] == disable_calls
    assert pyboy.memory[audit_emulator.symbols["hLoadedROMBank"]] == 0
    assert pyboy.register_file.SP == 0xD000
    _assert_stable_bedroom_semantics(audit_emulator)


def test_natural_owned_pallet_vblank_runs_full_color_pipeline_and_restores_frame(
    audit_emulator: Emulator,
) -> None:
    reach_bedroom_overworld(audit_emulator)
    walk_from_bedroom_to_pallet(audit_emulator)
    pyboy = audit_emulator.pyboy

    constants = numeric_symbols(REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym")
    descriptor_capacity = 8
    descriptor_bytes = 20
    observed_names = (
        "FullColorVBlankOwnerConsumed",
        "FullColorPhase5CombinedVBlankEnd",
        "FullColorPhase5OAMDMAStart",
        "FullColorPhase5SchedulerPass1Start",
        "FullColorPhase5SchedulerPass2Start",
    )
    frames: list[dict[str, object]] = []
    current_frame: list[dict[str, object] | None] = [None]
    pending_builds = [0]
    presented_oam: list[bytes] = []
    declared_oam_sources: list[int] = []
    frame_aligned = [False]
    paired: dict[str, object] = {}
    producer_rebuilds: list[tuple[int, int]] = []
    admitted_semantic_classes: list[int] = []
    producer_stages: list[tuple[str, int, int, int, int, int]] = []
    loaded_bank = audit_emulator.symbols["hLoadedROMBank"]
    initial_position = (
        audit_emulator.read("wXCoord"),
        audit_emulator.read("wYCoord"),
    )

    def count_build(_: object) -> None:
        if frame_aligned[0]:
            pending_builds[0] += 1

    def count_site(name: str):
        def count(_: object) -> None:
            frame = current_frame[0]
            if frame is not None:
                frame[name] = int(frame[name]) + 1
                if name == "FullColorPhase5CombinedVBlankEnd":
                    active_descriptor = int.from_bytes(
                        _read_wram2_bytes(
                            audit_emulator, "wFullColorActiveDescriptor", 2
                        ),
                        "little",
                    )
                    frame["owner_end_state"] = (
                        pyboy.memory[loaded_bank],
                        pyboy.memory[0xFF70],
                        pyboy.memory[0xFFFF],
                    )
                    frame["owner_end_active_descriptor"] = active_descriptor
                    frame["owner_end_descriptor_state"] = (
                        _read_wram2_at(audit_emulator, active_descriptor, 1)[0] >> 4
                    )
                    frame["owner_end_cache_valid"] = _read_wram2(
                        audit_emulator, "wFullColorPhase5FastCacheValid"
                    )
                    frame["owner_end_request_count"] = _read_wram2(
                        audit_emulator, "wFullColorRequestCount"
                    )
                if name == "FullColorPhase5OAMDMAStart":
                    descriptor = pyboy.register_file.HL
                    declared_oam_sources.append(
                        pyboy.memory[descriptor + 8]
                        | pyboy.memory[descriptor + 9] << 8
                    )

        return count

    def record_origin(_: object) -> None:
        if not frame_aligned[0]:
            return
        assert current_frame[0] is None
        cache_valid = _read_wram2(
            audit_emulator, "wFullColorPhase5FastCacheValid"
        )
        cache_snapshot = _read_wram2_bytes(
            audit_emulator, "wFullColorPhase5FastCacheSnapshot", descriptor_bytes
        )
        cache_pointer = int.from_bytes(
            _read_wram2_bytes(
                audit_emulator, "wFullColorPhase5FastCacheDescriptor", 2
            ),
            "little",
        )
        current_frame[0] = {
            **{name: 0 for name in observed_names},
            "builds": pending_builds[0],
            "origin_state": (
                pyboy.memory[loaded_bank],
                pyboy.register_file.SP,
                pyboy.memory[0xFF70],
                pyboy.memory[0xFFFF],
            ),
                "origin_requests": _read_wram2(
                    audit_emulator, "wFullColorRequestCount"
                ),
                "origin_cursor": _read_wram2(
                    audit_emulator, "wFullColorRequestCursor"
                ),
            "cache_valid": cache_valid,
            "cache_snapshot": cache_snapshot,
            "cache_pointer": cache_pointer,
            "producer_pending": _read_wram2(
                audit_emulator, "wFullColorProducerPending"
            ),
            "origin_shadow_oam": bytes(pyboy.memory[0xC300:0xC3A0]),
            "origin_hardware_oam": bytes(pyboy.memory[0xFE00:0xFEA0]),
            "origin_oam_epoch": _read_wram2(
                audit_emulator, "wFullColorPhase5OAMAuthorityEpoch"
            ),
            "origin_descriptors": _read_wram2_bytes(
                audit_emulator,
                "wFullColorRequestDescriptors",
                descriptor_capacity * descriptor_bytes,
            ),
        }
        pending_builds[0] = 0

        # Mutate the first naturally prepared row/column producer only after
        # preparation has frozen both planes. The commit must consume the
        # frozen scheduler batch, never these changed producer bytes.
        if paired and "committed_frame" not in paired:
            descriptor = _read_wram2_at(
                audit_emulator, int(paired["descriptor_address"]), descriptor_bytes
            )
            if descriptor[0] >> 4 == constants["CANCELLED"]:
                source = int(paired["source"])
                payload = paired["source_payload"]
                pyboy.memory[source:source + len(payload)] = payload
                paired.clear()
        if paired:
            return
        paired_classes = {
            constants["FULL_COLOR_REQUEST_MAP_ROW_PAIRED"],
            constants["FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED"],
        }
        candidates: list[tuple[int, bytes]] = []
        if cache_valid:
            candidates.append((cache_pointer, cache_snapshot))
        for address, descriptor in candidates:
            state = descriptor[0] >> 4
            request_class = descriptor[0] & 0x0F
            if state != constants["PREPARED"] or request_class not in paired_classes:
                continue
            extent = int.from_bytes(descriptor[14:16], "little")
            source = int.from_bytes(descriptor[8:10], "little")
            destination = int.from_bytes(descriptor[6:8], "little")
            width, height = descriptor[10], descriptor[11]
            assert extent == width * height
            assert 0xC000 <= source < 0xE000
            source_payload = bytes(pyboy.memory[source:source + 2 * extent])
            paired.update({
                "descriptor_address": address,
                "prepared_descriptor": descriptor,
                "request_class": request_class,
                "source": source,
                "source_payload": source_payload,
                "frozen_tiles": _read_wram2_bytes(
                    audit_emulator, "wFullColorAttributeRectangle", extent
                ),
                "frozen_attributes": _read_wram2_bytes(
                    audit_emulator, "wFullColorBGPaletteBase", extent
                ),
                "addresses": _map_cell_addresses(destination, width, height),
                "prepared_frame": len(frames),
            })
            pyboy.memory[source:source + 2 * extent] = b"\xee" * (2 * extent)
            break

    def record_paired_start(_: object) -> None:
        if not paired or "committing_descriptor" in paired:
            return
        descriptor_address = pyboy.register_file.HL
        descriptor = _read_wram2_at(
            audit_emulator,
            descriptor_address,
            descriptor_bytes,
        )
        if descriptor_address != paired["descriptor_address"]:
            return
        paired["committing_descriptor"] = descriptor

    def record_paired_end(_: object) -> None:
        if not paired or "committed_frame" in paired:
            return
        descriptor_address = pyboy.register_file.HL
        if descriptor_address != paired["descriptor_address"]:
            return
        addresses = paired["addresses"]
        paired["presented_tiles"] = bytes(
            audit_emulator.read_vram_bank(0, address, 1)[0]
            for address in addresses
        )
        paired["presented_attributes"] = bytes(
            audit_emulator.read_vram_bank(1, address, 1)[0]
            for address in addresses
        )
        paired["committed_frame"] = len(frames)
        source = int(paired["source"])
        source_payload = paired["source_payload"]
        pyboy.memory[source:source + len(source_payload)] = source_payload

    def record_producer_rebuild(_: object) -> None:
        producer_rebuilds.append((
            _read_wram2(audit_emulator, "wFullColorProducerClass"),
            _read_wram2(audit_emulator, "wFullColorProducerFlags"),
        ))

    def record_semantic_admission(_: object) -> None:
        admitted_semantic_classes.append(
            _read_wram2_bytes(
                audit_emulator, "wFullColorSchedulerEnqueueDescriptor", 1
            )[0]
        )

    def record_producer_stage(stage: str):
        def record(_: object) -> None:
            producer_stages.append((
                stage,
                _read_wram2(audit_emulator, "wFullColorProducerClass"),
                _read_wram2(audit_emulator, "wFullColorProducerFlags"),
                pyboy.register_file.B,
                pyboy.register_file.C,
                pyboy.memory[0xFF70],
            ))

        return record

    def record_handler_end(_: object) -> None:
        if not frame_aligned[0]:
            frame_aligned[0] = True
            return
        frame = current_frame[0]
        if frame is None:
            return
        frame["end_state"] = (
            pyboy.memory[loaded_bank],
            pyboy.register_file.SP,
            pyboy.memory[0xFF70],
            pyboy.memory[0xFFFF],
        )
        frame["request_count"] = _read_wram2(
            audit_emulator, "wFullColorRequestCount"
        )
        active_descriptor = int.from_bytes(
            _read_wram2_bytes(audit_emulator, "wFullColorActiveDescriptor", 2),
            "little",
        )
        frame["handler_end_active_descriptor"] = active_descriptor
        frame["handler_end_descriptor_state"] = (
            _read_wram2_at(audit_emulator, active_descriptor, 1)[0] >> 4
        )
        frame["handler_end_cache_valid"] = _read_wram2(
            audit_emulator, "wFullColorPhase5FastCacheValid"
        )
        frame["end_shadow_oam"] = bytes(pyboy.memory[0xC300:0xC3A0])
        frame["end_hardware_oam"] = bytes(pyboy.memory[0xFE00:0xFEA0])
        frame["end_oam_epoch"] = _read_wram2(
            audit_emulator, "wFullColorPhase5OAMAuthorityEpoch"
        )
        frames.append(frame)
        current_frame[0] = None
        presented_oam.append(bytes(pyboy.memory[0xFE00:0xFEA0]))

    hooks: list[tuple[int, int]] = []
    key = (
        audit_emulator.symbol_banks["FullColorPhase5OAMBuildStart"],
        audit_emulator.symbols["FullColorPhase5OAMBuildStart"],
    )
    pyboy.hook_register(*key, count_build, None)
    hooks.append(key)
    for name in observed_names:
        key = (
            audit_emulator.symbol_banks[name],
            audit_emulator.symbols[name],
        )
        pyboy.hook_register(*key, count_site(name), None)
        hooks.append(key)
    for name, callback in (
        ("FullColorPhase5VBlankOrigin", record_origin),
        ("FullColorPhase5VBlankHandlerEnd", record_handler_end),
        ("FullColorPhase5VerticalStart", record_paired_start),
        ("FullColorPhase5VerticalEnd", record_paired_end),
        ("BuildAndPrepareFullColorPairedDescriptorSelected", record_producer_rebuild),
        ("AdmitPreparedFullColorSemanticSelected", record_semantic_admission),
    ):
        key = (
            audit_emulator.symbol_banks[name],
            audit_emulator.symbols[name],
        )
        pyboy.hook_register(*key, callback, None)
        hooks.append(key)
    for name in (
        "EnqueueFullColorPairedSemantic.flags_ready",
        "EnqueueFullColorPairedSemantic.geometry_ok",
        "EnqueueFullColorPairedSemantic.source_extent_ok",
        "EnqueueFullColorPairedSemantic.derived",
    ):
        key = (audit_emulator.symbol_banks[name], audit_emulator.symbols[name])
        pyboy.hook_register(*key, record_producer_stage(name), None)
        hooks.append(key)

    try:
        audit_emulator.advance_until(
            lambda: audit_emulator.read("wXCoord") >= 14,
            button="right",
            max_presses=12,
            description="sustained Pallet horizontal scroll",
        )
        assert audit_emulator.read("wCurMap") == 0
        assert _read_wram2(audit_emulator, "wRendererOwner") == 1
        assert _read_wram2(audit_emulator, "wRendererPhase") == 3
        # Finish at a handler boundary and give a just-prepared paired unit a
        # bounded opportunity to drain without manufacturing another request.
        for _ in range(32):
            if paired.get("committed_frame") is not None and frames[-1]["request_count"] == 0:
                break
            audit_emulator.tick(1)
    finally:
        if paired and "committed_frame" not in paired:
            source = int(paired["source"])
            payload = paired["source_payload"]
            pyboy.memory[source:source + len(payload)] = payload
        for bank, address in hooks:
            pyboy.hook_deregister(bank, address)

    assert len(frames) >= 8
    retained_frames: list[int] = []
    for index, frame in enumerate(frames):
        diagnostic = {"frame": index, **frame}
        assert frame["builds"] in {0, 1}, diagnostic
        assert frame["FullColorVBlankOwnerConsumed"] == 1, diagnostic
        assert frame["FullColorPhase5CombinedVBlankEnd"] == 1, diagnostic
        assert frame["FullColorPhase5SchedulerPass1Start"] == 1, diagnostic
        if frame["FullColorPhase5SchedulerPass2Start"] != 1:
            raise AssertionError({
                "frame": index,
                "builds": frame["builds"],
                "origin_requests": frame["origin_requests"],
                "cursor": frame["origin_cursor"],
                "cache_valid": frame["cache_valid"],
                "producer_pending": frame["producer_pending"],
                "origin_oam_epoch": frame["origin_oam_epoch"],
                "end_oam_epoch": frame["end_oam_epoch"],
                "states": tuple(
                    frame["origin_descriptors"][offset] for offset in range(
                        0, len(frame["origin_descriptors"]), descriptor_bytes
                    )
                ),
                "slot0": frame["origin_descriptors"][:descriptor_bytes].hex(),
                "slot7": frame["origin_descriptors"][-descriptor_bytes:].hex(),
                "owner_end_cache": frame["owner_end_cache_valid"],
                "owner_end_count": frame["owner_end_request_count"],
            })
        assert frame["owner_end_state"] == (
            frame["origin_state"][0],
            frame["origin_state"][2],
            frame["origin_state"][3],
        ), diagnostic
        assert frame["origin_state"] == frame["end_state"], diagnostic
        if frame["builds"]:
            # A changed shadow authority must publish its exact fresh batch.
            assert frame["FullColorPhase5OAMDMAStart"] == 1, diagnostic
            continue
        # The pre-shift interrupt may spend the frame on the frozen paired unit
        # only when the shadow writer epoch is unchanged. Hardware OAM must be
        # exactly the already-presented batch; a redundant DMA is forbidden.
        retained_frames.append(index)
        assert frame["FullColorPhase5OAMDMAStart"] == 0, diagnostic
        assert frame["origin_oam_epoch"] == frame["end_oam_epoch"], diagnostic
        descriptor_image = frame["origin_descriptors"]
        assert isinstance(descriptor_image, bytes)
        retained_certificates = [
            descriptor_image[offset:offset + descriptor_bytes]
            for offset in range(0, len(descriptor_image), descriptor_bytes)
            if descriptor_image[offset]
            == (
                constants["COMPLETE"] << 4
                | constants["FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA"]
            )
        ]
        assert any(
            descriptor[19] == frame["origin_oam_epoch"]
            for descriptor in retained_certificates
        ), diagnostic
        assert frame["origin_shadow_oam"] == frame["end_shadow_oam"], diagnostic
        assert (
            frame["origin_hardware_oam"] == frame["end_hardware_oam"]
        ), diagnostic
        assert frame["origin_shadow_oam"] == frame["origin_hardware_oam"], diagnostic
    assert (
        audit_emulator.read("wXCoord"),
        audit_emulator.read("wYCoord"),
    ) != initial_position
    assert len(set(presented_oam)) >= 2
    assert declared_oam_sources
    assert set(declared_oam_sources) == {audit_emulator.symbols["wShadowOAM"]}
    assert retained_frames, "natural scrolling never exercised certified OAM retention"
    assert _read_wram2(
        audit_emulator, "wFullColorPhase5ScenarioState"
    ) != constants["FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED"]
    assert (
        _read_wram2(audit_emulator, "wFullColorPhase5PressureEnqueuedMask")
        & (1 << 2)  # FULL_COLOR_PHASE5_PRESSURE_OAM
    )
    assert paired, (
        "sustained movement never prepared a paired row/column",
        producer_stages,
        producer_rebuilds,
        admitted_semantic_classes,
    )
    assert paired["request_class"] in {
        constants["FULL_COLOR_REQUEST_MAP_ROW_PAIRED"],
        constants["FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED"],
    }
    prepared_descriptor = paired["prepared_descriptor"]
    assert "committing_descriptor" in paired, paired
    committing_descriptor = paired["committing_descriptor"]
    assert (
        committing_descriptor[0] & 0x0F
    ) == (
        prepared_descriptor[0] & 0x0F
    )
    assert committing_descriptor[1:] == prepared_descriptor[1:]
    assert paired["presented_tiles"] == paired["frozen_tiles"]
    assert paired["presented_attributes"] == paired["frozen_attributes"]
    assert int(paired["committed_frame"]) - int(paired["prepared_frame"]) <= 2, [
        (
            index,
            frame["builds"],
            frame["FullColorPhase5OAMDMAStart"],
            frame["cache_valid"],
            frame["cache_snapshot"][0],
            frame["request_count"],
            frame["producer_pending"],
        )
        for index, frame in enumerate(frames[:8])
    ]
    assert int(paired["committed_frame"]) in retained_frames
    committed_frame = frames[int(paired["committed_frame"])]
    assert committed_frame["owner_end_active_descriptor"] == paired[
        "descriptor_address"
    ]
    assert committed_frame["owner_end_descriptor_state"] == constants["COMPLETE"]
    assert committed_frame["owner_end_cache_valid"] == constants[
        "FULL_COLOR_PHASE5_FAST_CACHE_ACCOUNTING_PENDING"
    ]
    assert committed_frame["handler_end_active_descriptor"] == paired[
        "descriptor_address"
    ]
    assert committed_frame["handler_end_descriptor_state"] == constants["COMPLETE"]
    assert committed_frame["handler_end_cache_valid"] == 0
    assert committed_frame["request_count"] + 1 == committed_frame[
        "owner_end_request_count"
    ]
    assert frames[-1]["request_count"] == 0


def test_natural_owned_oam_source_mutation_fails_before_dma(
    audit_emulator: Emulator,
) -> None:
    """Hostile descriptor drift cannot publish the producer-finished batch."""
    reach_bedroom_overworld(audit_emulator)
    walk_from_bedroom_to_pallet(audit_emulator)
    constants = numeric_symbols(REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym")
    descriptor_bytes = 20
    _write_wram2(
        audit_emulator,
        "wFullColorPhase5ScenarioControl",
        constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
    )
    mutation = {"done": False, "hardware": b""}
    failed = {"seen": False, "hardware": b""}
    dma_calls = [0]
    dma_descriptors: list[tuple[int, bytes]] = []

    def mutate_natural_declaration(_: object) -> None:
        if mutation["done"]:
            return
        descriptors = bytearray(_read_wram2_bytes(
            audit_emulator, "wFullColorRequestDescriptors", 8 * descriptor_bytes
        ))
        for offset in range(0, len(descriptors), descriptor_bytes):
            descriptor = descriptors[offset:offset + descriptor_bytes]
            if descriptor[0] != (
                constants["PREPARED"] << 4
                | constants["FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA"]
            ):
                continue
            assert int.from_bytes(descriptor[8:10], "little") == (
                audit_emulator.symbols["wShadowOAM"]
            )
            mutation["hardware"] = bytes(
                audit_emulator.pyboy.memory[0xFE00:0xFE00 + 160]
            )
            descriptors[offset + 8] ^= 1
            _write_wram2_bytes(
                audit_emulator, "wFullColorRequestDescriptors", bytes(descriptors)
            )
            mutation["done"] = True
            return
        raise AssertionError("finished natural OAM build has no declaration")

    def record_dma(_: object) -> None:
        if mutation["done"] and not failed["seen"]:
            dma_calls[0] += 1
            pointer = audit_emulator.pyboy.register_file.HL
            dma_descriptors.append((
                pointer,
                _read_wram2_at(audit_emulator, pointer, descriptor_bytes),
            ))

    def record_failed_revalidation(_: object) -> None:
        failed["seen"] = True
        failed["hardware"] = bytes(
            audit_emulator.pyboy.memory[0xFE00:0xFE00 + 160]
        )

    hooks = (
        (
            audit_emulator.symbol_banks["FullColorPhase5OAMBuildEnd"],
            audit_emulator.symbols["FullColorPhase5OAMBuildEnd"],
            mutate_natural_declaration,
        ),
        (
            audit_emulator.symbol_banks["FullColorPhase5OAMDMAStart"],
            audit_emulator.symbols["FullColorPhase5OAMDMAStart"],
            record_dma,
        ),
        (
            audit_emulator.symbol_banks["FullColorPhase5FastFreshOAMFailed"],
            audit_emulator.symbols["FullColorPhase5FastFreshOAMFailed"],
            record_failed_revalidation,
        ),
    )
    for bank, address, callback in hooks:
        audit_emulator.pyboy.hook_register(bank, address, callback, None)
    try:
        for frame in range(120):
            if frame % 4 == 0:
                audit_emulator.pyboy.button("right", delay=2)
            audit_emulator.tick(1)
            if failed["seen"]:
                break
        assert mutation["done"], "natural movement never built owned OAM"
        assert failed["seen"], "poisoned natural OAM was not revalidated"
    finally:
        for bank, address, _ in hooks:
            audit_emulator.pyboy.hook_deregister(bank, address)

    assert dma_calls == [0], dma_descriptors
    assert failed["hardware"] == mutation["hardware"]
    assert _read_wram2(
        audit_emulator, "wFullColorPhase5ScenarioState"
    ) == constants["FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED"]


def test_natural_combined_pressure_keeps_fresh_oam_and_drains_other_units(
    audit_emulator: Emulator,
) -> None:
    reach_bedroom_overworld(audit_emulator)
    walk_from_bedroom_to_pallet(audit_emulator)
    constants = numeric_symbols(REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym")
    pyboy = audit_emulator.pyboy

    # The walk into Pallet may leave its last natural paired strip queued. Drain
    # that pre-scenario authority before measuring the bounded Combined corpus.
    for _ in range(8):
        if (
            _read_wram2(audit_emulator, "wFullColorRequestCount") == 0
            and _read_wram2(audit_emulator, "wFullColorPhase5FastCacheValid") == 0
        ):
            break
        audit_emulator.tick(1)
    assert _read_wram2(audit_emulator, "wFullColorRequestCount") == 0
    assert _read_wram2(audit_emulator, "wFullColorPhase5FastCacheValid") == 0

    _write_wram2(audit_emulator, "wFullColorPhase5PressureEnqueuedMask", 0)
    _write_wram2(audit_emulator, "wFullColorPhase5PressureDrainedMask", 0)
    _write_wram2(
        audit_emulator,
        "wFullColorPhase5Scenario",
        constants["FULL_COLOR_PHASE5_SCENARIO_COMBINED_VBLANK"],
    )
    _write_wram2(
        audit_emulator,
        "wFullColorPhase5ScenarioControl",
        constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
    )

    owned_frame = [0]
    builds: list[int] = []
    dmas: list[int] = []
    palette_commits: list[int] = []
    animation_commits: list[int] = []
    frozen_palette: list[bytes] = []
    frozen_animation: list[tuple[bytes, int]] = []

    def count_owned(_: object) -> None:
        owned_frame[0] += 1

    def record_into(target: list[int]):
        def record(_: object) -> None:
            target.append(owned_frame[0])

        return record

    def mutate_declared_sources_after_preparation(_: object) -> None:
        if not _read_wram2(
            audit_emulator, "wFullColorPhase5FastCacheValid"
        ):
            return
        request_class = _read_wram2(
            audit_emulator, "wFullColorPhase5FastCacheSnapshot"
        ) & 0x0F
        if (
            request_class == constants["FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD"]
            and not frozen_palette
        ):
            frozen_palette.append(
                _read_wram2_bytes(
                    audit_emulator, "wFullColorBGPaletteBase", 64
                )
            )
            _write_wram2_bytes(
                audit_emulator, "wFullColorOBJPaletteBase", b"\xee" * 64
            )
        elif (
            request_class == constants["FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT"]
            and not frozen_animation
        ):
            frozen_animation.append((
                _read_wram2_bytes(
                    audit_emulator, "wFullColorBGPaletteBase", 16
                ),
                _read_wram2(
                    audit_emulator, "wFullColorAttributeRectangle"
                ),
            ))
            _write_wram2_bytes(
                audit_emulator, "wFullColorProducerTiles", b"\xdd" * 17
            )

    callbacks = {
        "FullColorVBlankOwnerConsumed": count_owned,
        "FullColorPhase5OAMBuildStart": record_into(builds),
        "FullColorPhase5OAMDMAStart": record_into(dmas),
        "FullColorPhase5PaletteStart": record_into(palette_commits),
        "FullColorPhase5AnimationStart": record_into(animation_commits),
        "FullColorPhase5VBlankOrigin": mutate_declared_sources_after_preparation,
    }
    hooks: list[tuple[int, int]] = []
    for name, callback in callbacks.items():
        key = (audit_emulator.symbol_banks[name], audit_emulator.symbols[name])
        pyboy.hook_register(*key, callback, None)
        hooks.append(key)
    try:
        for _ in range(6):
            audit_emulator.tick(1)
    finally:
        for bank, address in hooks:
            pyboy.hook_deregister(bank, address)

    assert owned_frame[0] >= 3
    assert dmas == [frame + 1 for frame in builds]
    assert len(builds) < owned_frame[0]
    diagnostics = {
        "owned": owned_frame[0],
        "builds": builds,
        "dmas": dmas,
        "palette": palette_commits,
        "animation": animation_commits,
        "enqueued": _read_wram2(
            audit_emulator, "wFullColorPhase5PressureEnqueuedMask"
        ),
        "drained": _read_wram2(
            audit_emulator, "wFullColorPhase5PressureDrainedMask"
        ),
        "requests": _read_wram2(audit_emulator, "wFullColorRequestCount"),
        "last_admission": _read_wram2(
            audit_emulator, "wFullColorLastAdmissionResult"
        ),
        "scenario_control": _read_wram2(
            audit_emulator, "wFullColorPhase5ScenarioControl"
        ),
        "scenario": _read_wram2(audit_emulator, "wFullColorPhase5Scenario"),
    }
    assert palette_commits and palette_commits[0] <= 2, diagnostics
    assert animation_commits and animation_commits[0] <= 4
    assert not set(palette_commits + animation_commits) & set(dmas), diagnostics
    assert _read_wram2(
        audit_emulator, "wFullColorPhase5PressureEnqueuedMask"
    ) == constants["FULL_COLOR_PHASE5_PRESSURE_ALL"]
    assert _read_wram2(
        audit_emulator, "wFullColorPhase5PressureDrainedMask"
    ) == constants["FULL_COLOR_PHASE5_PRESSURE_ALL"]
    assert _read_wram2(audit_emulator, "wFullColorRequestCount") == 0
    assert frozen_palette and audit_emulator.read_palette_ram() == frozen_palette[0]
    assert frozen_animation
    frozen_tiles, frozen_attribute = frozen_animation[0]
    assert audit_emulator.read_vram_bank(0, 0x8000, 16) == frozen_tiles
    assert audit_emulator.read_vram_bank(1, 0x9800, 1) == bytes((frozen_attribute,))


def test_fast_cache_rejects_downward_required_cycle_mutation_before_palette(
    audit_emulator: Emulator,
) -> None:
    reach_bedroom_overworld(audit_emulator)
    walk_from_bedroom_to_pallet(audit_emulator)
    constants = numeric_symbols(REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym")
    pyboy = audit_emulator.pyboy
    _write_wram2(
        audit_emulator,
        "wFullColorPhase5Scenario",
        constants["FULL_COLOR_PHASE5_SCENARIO_PALETTE"],
    )
    _write_wram2(
        audit_emulator,
        "wFullColorPhase5ScenarioControl",
        constants["FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED"],
    )
    mutated = [False]
    handler_complete = [False]
    palette_commits = [0]
    palette_before: list[bytes] = []
    palette_states_at_handler: list[int] = []

    def mutate_cache(_: object) -> None:
        if mutated[0] or not _read_wram2(
            audit_emulator, "wFullColorPhase5FastCacheValid"
        ):
            return
        snapshot = _read_wram2_bytes(
            audit_emulator, "wFullColorPhase5FastCacheSnapshot", 20
        )
        if snapshot[0] & 0x0F != constants["FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD"]:
            return
        palette_before.append(audit_emulator.read_palette_ram())
        _write_wram2_bytes(
            audit_emulator, "wFullColorPhase5FastCacheRequiredCycles", b"\0\0"
        )
        mutated[0] = True

    def record_palette(_: object) -> None:
        if mutated[0] and not handler_complete[0]:
            palette_commits[0] += 1

    def record_handler(_: object) -> None:
        if mutated[0]:
            descriptors = _read_wram2_bytes(
                audit_emulator, "wFullColorRequestDescriptors", 8 * 20
            )
            palette_states_at_handler.extend(
                descriptor[0] >> 4
                for offset in range(0, len(descriptors), 20)
                if (
                    descriptor := descriptors[offset:offset + 20]
                )[0] & 0x0F
                == constants["FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD"]
            )
            handler_complete[0] = True

    callbacks = {
        "FullColorPhase5VBlankOrigin": mutate_cache,
        "FullColorPhase5PaletteStart": record_palette,
        "FullColorPhase5VBlankHandlerEnd": record_handler,
    }
    hooks: list[tuple[int, int]] = []
    for name, callback in callbacks.items():
        key = (audit_emulator.symbol_banks[name], audit_emulator.symbols[name])
        pyboy.hook_register(*key, callback, None)
        hooks.append(key)
    try:
        for _ in range(8):
            audit_emulator.tick(1)
            if handler_complete[0]:
                break
    finally:
        for bank, address in hooks:
            pyboy.hook_deregister(bank, address)

    assert mutated[0] and handler_complete[0]
    assert palette_commits[0] == 0
    assert palette_before and audit_emulator.read_palette_ram() == palette_before[0]
    assert _read_wram2(audit_emulator, "wFullColorPhase5FastCacheValid") == 0
    assert _read_wram2(audit_emulator, "wFullColorRequestCount") == 0
    assert constants["CANCELLED"] in palette_states_at_handler


def test_natural_north_connection_binds_pending_identity_through_retry(
    audit_emulator: Emulator,
) -> None:
    """The OAM-contended connection survives in private authority until retry."""
    reach_bedroom_overworld(audit_emulator)
    walk_from_bedroom_to_oak(audit_emulator)
    follow_oak_and_receive_pikachu(audit_emulator)
    finish_rival_battle_and_leave_lab(audit_emulator)
    constants = numeric_symbols(REPOSITORY_ROOT / "pokeyellow_phase2_audit.sym")
    pyboy = audit_emulator.pyboy
    descriptor_bytes = 20
    capacity = 8
    connection_class = constants["FULL_COLOR_REQUEST_MAP_CONNECTION_PAIRED"]
    accepted = constants["ACCEPTED"]
    trace: dict[str, object] = {
        "origins": 0,
        "ends": 0,
        "retry_results": [],
        "connection_commits": 0,
        "outgoing_commits": 0,
        "deadlines": 0,
        "supersession_events": [],
    }

    def at_origin(_: object) -> None:
        if (
            audit_emulator.read("wCurMap") == PALLET_TOWN
            and audit_emulator.read("wYCoord") == 0
        ):
            trace["origins"] = int(trace["origins"]) + 1

    def at_enqueue_end(_: object) -> None:
        if _read_wram2(audit_emulator, "wFullColorProducerClass") != connection_class:
            return
        trace["ends"] = int(trace["ends"]) + 1
        producer_extent = (
            _read_wram2(audit_emulator, "wFullColorProducerWidth")
            * _read_wram2(audit_emulator, "wFullColorProducerHeight")
        )
        trace["pending_identity"] = (
            _read_wram2(audit_emulator, "wFullColorProducerPending"),
            _read_wram2(audit_emulator, "wFullColorProducerClass"),
            int.from_bytes(
                _read_wram2_bytes(
                    audit_emulator, "wFullColorProducerDestination", 2
                ),
                "little",
            ),
            _read_wram2(audit_emulator, "wFullColorProducerWidth"),
            _read_wram2(audit_emulator, "wFullColorProducerHeight"),
            producer_extent,
            _read_wram2(audit_emulator, "wFullColorProducerFlags"),
        )
        trace["producer_payload"] = _read_wram2_bytes(
            audit_emulator, "wFullColorProducerTiles", 2 * producer_extent
        )
        trace["outgoing_authority_map"] = _read_wram2(
            audit_emulator, "wFullColorAuthorityMap"
        )
        cached_address = int.from_bytes(
            _read_wram2_bytes(
                audit_emulator, "wFullColorPhase5FastCacheDescriptor", 2
            ),
            "little",
        )
        assert cached_address
        outgoing = _read_wram2_at(
            audit_emulator, cached_address, descriptor_bytes
        )
        trace["outgoing_descriptor"] = outgoing
        trace["outgoing_address"] = cached_address
        outgoing_destination = int.from_bytes(outgoing[6:8], "little")
        assert _map_cell_addresses(
            outgoing_destination, outgoing[10], outgoing[11]
        )
        # Reproduce the exact fast-writer scratch clobber that originally made
        # retry advertise extent $1214/reservation $2428 instead of 40/80.
        _write_wram2_bytes(
            audit_emulator, "wFullColorRequestStaging", b"\x14\x12\0\x28\x24"
        )

    def at_retry_result(_: object) -> None:
        if (
            "pending_identity" not in trace
            or _read_wram2(audit_emulator, "wFullColorProducerClass")
            != connection_class
        ):
            return
        result = pyboy.register_file.A
        results = trace["retry_results"]
        assert isinstance(results, list)
        results.append(result)
        descriptors = _read_wram2_bytes(
            audit_emulator,
            "wFullColorRequestDescriptors",
            capacity * descriptor_bytes,
        )
        if result != accepted or "resident_address" in trace:
            return
        trace["accepted_candidate"] = _read_wram2_bytes(
            audit_emulator,
            "wFullColorSchedulerEnqueueDescriptor",
            descriptor_bytes,
        )
        trace["successor_map"] = audit_emulator.read("wCurMap")
        trace["accepted_deadline"] = trace["deadlines"]
        events = trace["supersession_events"]
        assert isinstance(events, list)
        events.append("accepted")
        base = audit_emulator.symbols["wFullColorRequestDescriptors"]
        for index in range(capacity):
            descriptor = descriptors[
                index * descriptor_bytes:(index + 1) * descriptor_bytes
            ]
            if (
                descriptor[0] >> 4 == constants["PREPARED"]
                and descriptor[0] & 0x0F == connection_class
            ):
                trace["resident_address"] = base + index * descriptor_bytes
                trace["prepared_descriptor"] = descriptor
                extent = int.from_bytes(descriptor[14:16], "little")
                trace["frozen_tiles"] = _read_wram2_bytes(
                    audit_emulator, "wFullColorAttributeRectangle", extent
                )
                trace["frozen_attributes"] = _read_wram2_bytes(
                    audit_emulator, "wFullColorBGPaletteBase", extent
                )
                assert trace["producer_payload"] == (
                    trace["frozen_tiles"] + trace["frozen_attributes"]
                )
                return

    def at_cancel_outgoing(_: object) -> None:
        if (
            "pending_identity" not in trace
            or _read_wram2(audit_emulator, "wFullColorProducerClass")
            != connection_class
        ):
            return
        events = trace["supersession_events"]
        assert isinstance(events, list)
        events.append("cancelled")

    def at_vertical_start(_: object) -> None:
        address = int.from_bytes(
            _read_wram2_bytes(audit_emulator, "wFullColorActiveDescriptor", 2),
            "little",
        )
        if not address:
            return
        if address == trace.get("outgoing_address"):
            trace["outgoing_commits"] = int(trace["outgoing_commits"]) + 1
        descriptor = _read_wram2_at(audit_emulator, address, descriptor_bytes)
        if descriptor[0] & 0x0F == connection_class:
            trace["connection_commits"] = int(trace["connection_commits"]) + 1

    def at_deadline(_: object) -> None:
        if "pending_identity" not in trace:
            return
        trace["deadlines"] = int(trace["deadlines"]) + 1
        if "resident_address" not in trace or "completed_descriptor" in trace:
            return
        address = int(trace["resident_address"])
        descriptor = _read_wram2_at(audit_emulator, address, descriptor_bytes)
        if descriptor[0] >> 4 != constants["COMPLETE"]:
            return
        trace["completed_descriptor"] = descriptor
        trace["completed_deadline"] = trace["deadlines"]
        destination = int.from_bytes(descriptor[6:8], "little")
        width, height = descriptor[10], descriptor[11]
        addresses = _map_cell_addresses(destination, width, height)
        trace["presented_tiles"] = bytes(
            audit_emulator.read_vram_bank(0, cell, 1)[0] for cell in addresses
        )
        trace["presented_attributes"] = bytes(
            audit_emulator.read_vram_bank(1, cell, 1)[0] for cell in addresses
        )

    callbacks = {
        "FullColorPhase5NorthConnectionOrigin": at_origin,
        "FullColorPhase5NorthConnectionEnd": at_enqueue_end,
        "RetryFullColorProducer.publish": at_retry_result,
        "CancelFullColorPhase5FastDescriptorSelected": at_cancel_outgoing,
        "FullColorPhase5VerticalStart": at_vertical_start,
        "FullColorPhase5NorthConnectionDeadline": at_deadline,
    }
    hooks: list[tuple[int, int]] = []
    for name, callback in callbacks.items():
        key = (audit_emulator.symbol_banks[name], audit_emulator.symbols[name])
        pyboy.hook_register(*key, callback, None)
        hooks.append(key)
    try:
        audit_emulator.advance_until(
            lambda: audit_emulator.read("wXCoord") == 8,
            button="right" if audit_emulator.read("wXCoord") < 8 else "left",
            max_presses=20,
            description="west side of Oak's Lab",
        )
        audit_emulator.advance_until(
            lambda: audit_emulator.read("wYCoord") == 2,
            button="up",
            max_presses=24,
            description="north Pallet Town",
        )
        audit_emulator.advance_until(
            lambda: audit_emulator.read("wXCoord") == 10,
            button="right",
            max_presses=20,
            description="Pallet north connection column",
        )
        audit_emulator.advance_until(
            lambda: audit_emulator.read("wYCoord") == 0,
            button="up",
            max_presses=8,
            description="Pallet north connection row",
        )
        audit_emulator.press("up", wait_frames=20)
        for _ in range(12):
            if "completed_descriptor" in trace:
                break
            audit_emulator.tick(1)
        if "completed_descriptor" in trace:
            audit_emulator.tick(2)
    finally:
        for bank, address in hooks:
            pyboy.hook_deregister(bank, address)

    assert audit_emulator.read("wCurMap") == ROUTE_1, trace
    assert int(trace["origins"]) >= 1, trace
    assert int(trace["ends"]) >= 1, trace
    pending = trace["pending_identity"]
    assert isinstance(pending, tuple)
    assert pending[0] == 1
    assert pending[1:] == (connection_class, pending[2], 20, 2, 40, 0)
    assert trace["retry_results"].count(accepted) == 1, trace
    assert "prepared_descriptor" in trace, trace
    prepared = trace["prepared_descriptor"]
    completed = trace["completed_descriptor"]
    candidate = trace["accepted_candidate"]
    assert isinstance(prepared, bytes) and isinstance(completed, bytes)
    assert isinstance(candidate, bytes)
    assert candidate[10:12] == b"\x14\x02"
    assert candidate[14:18] == b"\x28\0\x50\0"
    assert trace["outgoing_authority_map"] == PALLET_TOWN
    assert trace["successor_map"] == ROUTE_1
    outgoing = trace["outgoing_descriptor"]
    assert isinstance(outgoing, bytes)
    assert outgoing[0] & 0x0F == constants["FULL_COLOR_REQUEST_MAP_ROW_PAIRED"]
    assert outgoing[1] == constants["RENDERER_FULL_COLOR_OVERWORLD"]
    assert outgoing[2:6] == prepared[2:6]
    assert outgoing[6:8] != prepared[6:8]
    assert outgoing[10:12] == b"\x14\x02"
    assert outgoing[14:18] == b"\x28\0\x50\0"
    assert outgoing[18] == constants["FULL_COLOR_FLAG_MOVEMENT_STRIP"]
    assert trace["supersession_events"] == ["cancelled", "accepted"]
    assert trace["outgoing_commits"] == 0
    assert prepared[0] >> 4 == constants["PREPARED"]
    assert completed[0] >> 4 == constants["COMPLETE"]
    assert completed[0] & 0x0F == connection_class
    assert completed[1:] == prepared[1:]
    assert trace["presented_tiles"] == trace["frozen_tiles"]
    assert trace["presented_attributes"] == trace["frozen_attributes"]
    assert trace["connection_commits"] == 1
    assert _read_wram2(audit_emulator, "wFullColorProducerPending") == 0
    assert (
        int(trace["completed_deadline"]) - int(trace["accepted_deadline"])
    ) <= 3, trace

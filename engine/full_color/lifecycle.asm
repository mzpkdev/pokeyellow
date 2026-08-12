; Guarded hostile-slice lifecycle ABI. These routines are deliberately banked;
; Home integration reaches them with farcall and pays no permanent Home cost.

FullColorLifecycleROMStart::

; Audit products use an owned WRAM2 protocol. They never open or poll the
; Phase 1 SRAM mailbox, whose write-only MBC state cannot be restored safely.
IF DEF(PHASE2_AUDIT)
PollFullColorPhase2DebugCommand::
	select_renderer_state_e
	ldh a, [hRendererStateSavedSVBK]
	ld [wFullColorDebugEntrySVBK], a
	ldh a, [hRendererStateSavedIE]
	ld [wFullColorDebugEntryIE], a
	ld hl, sp+0
	ld a, l
	ld [wFullColorDebugEntrySP], a
	ld a, h
	ld [wFullColorDebugEntrySP + 1], a
	ld a, [wFullColorDebugCommandPhase2]
	and a
	jp z, .finish
	ld b, a
	xor a
	ld [wFullColorDebugCommandPhase2], a
	ld a, b
	cp FULL_COLOR_DEBUG_COMMAND_CLEAR
	jr z, .clear
	cp FULL_COLOR_DEBUG_COMMAND_ARM
	jr z, .arm
	cp FULL_COLOR_DEBUG_COMMAND_SNAPSHOT
	jr z, .snapshot
	cp FULL_COLOR_DEBUG_COMMAND_ACK
	jr z, .ack
	ld a, FULL_COLOR_ASSERT_DEBUG_COMMAND
	ld [wFullColorDebugWriterState], a
	jr .finish
.clear
	ld hl, wFullColorDebugCarrierStart
	ld bc, FULL_COLOR_DEBUG_CARRIER_BYTES
	xor a
	call FillMemory
	ldh a, [hRendererStateSavedSVBK]
	ld [wFullColorDebugEntrySVBK], a
	ldh a, [hRendererStateSavedIE]
	ld [wFullColorDebugEntryIE], a
	ld hl, sp+0
	ld a, l
	ld [wFullColorDebugEntrySP], a
	ld a, h
	ld [wFullColorDebugEntrySP + 1], a
	ld a, FULL_COLOR_DEBUG_CHECKPOINT_CLEAR
	ld [wFullColorDebugCheckpointPhase2], a
	jr .finish
.arm
	ld a, [wFullColorDebugProtocolState]
	and a
	jr z, .arm_valid
	cp FULL_COLOR_DEBUG_PROTOCOL_ACKNOWLEDGED
	jr nz, .protocol_error
.arm_valid
	ld a, FULL_COLOR_DEBUG_PROTOCOL_ARMED
	ld [wFullColorDebugProtocolState], a
	ld a, FULL_COLOR_DEBUG_CHECKPOINT_ARMED
	ld [wFullColorDebugCheckpointPhase2], a
	jr .finish
.snapshot
	ld a, [wFullColorDebugProtocolState]
	cp FULL_COLOR_DEBUG_PROTOCOL_ARMED
	jr nz, .protocol_error
	call SnapshotFullColorPhase2DebugSelected
	ld a, FULL_COLOR_DEBUG_PROTOCOL_SNAPSHOTTED
	ld [wFullColorDebugProtocolState], a
	ld a, FULL_COLOR_DEBUG_CHECKPOINT_SNAPSHOT
	ld [wFullColorDebugCheckpointPhase2], a
	jr .finish
.ack
	ld a, [wFullColorDebugProtocolState]
	cp FULL_COLOR_DEBUG_PROTOCOL_SNAPSHOTTED
	jr nz, .protocol_error
	ld a, FULL_COLOR_DEBUG_PROTOCOL_ACKNOWLEDGED
	ld [wFullColorDebugProtocolState], a
	ld a, FULL_COLOR_DEBUG_CHECKPOINT_ACKNOWLEDGED
	ld [wFullColorDebugCheckpointPhase2], a
	jr .finish
.protocol_error
	ld a, FULL_COLOR_ASSERT_DEBUG_COMMAND
	ld [wFullColorDebugWriterState], a
.finish
	ld hl, sp+0
	ld a, l
	ld [wFullColorDebugExitSP], a
	ld a, h
	ld [wFullColorDebugExitSP + 1], a
	ldh a, [hRendererStateSavedSVBK]
	ld [wFullColorDebugExitSVBK], a
	ldh a, [hRendererStateSavedIE]
	ld [wFullColorDebugExitIE], a
	restore_renderer_state_e
	ret

SnapshotFullColorPhase2DebugSelected::
	ld hl, wFullColorDebugSequence
	inc [hl]
	jr nz, .sequence_ready
	inc hl
	inc [hl]
.sequence_ready
	ld a, [wRendererOwner]
	ld [wFullColorDebugOwnerPhase], a
	ld a, [wRendererPhase]
	ld [wFullColorDebugOwnerPhase + 1], a
	ld hl, wRendererGeneration
	ld de, wFullColorDebugGenerationPhase2
	ld b, 4
.generation
	ld a, [hli]
	ld [de], a
	inc de
	dec b
	jr nz, .generation
	ld a, [wFullColorRequestCount]
	ld [wFullColorDebugRequestState], a
	ld a, [wFullColorRequestCursor]
	ld [wFullColorDebugRequestState + 1], a
	ld a, [wFullColorLastAdmissionResult]
	ld [wFullColorDebugRequestState + 2], a
	ld a, [wFullColorTransitionCount]
	ld [wFullColorDebugRequestState + 3], a
	ld [wFullColorDebugWriterState + 1], a
	ld a, [wFullColorTransitionLog]
	ld [wFullColorDebugWriterState + 2], a
	ldh a, [hAutoBGTransferEnabled]
	ld [wFullColorDebugCommonState], a
	ldh a, [hVBlankCopyBGNumRows]
	ld [wFullColorDebugCommonState + 1], a
	ldh a, [hVBlankCopySize]
	ld [wFullColorDebugCommonState + 2], a
	ldh a, [hRedrawRowOrColumnMode]
	ld [wFullColorDebugCommonState + 3], a
	ld hl, wFullColorReconstructionItems
	ld de, wFullColorDebugFallbackState
	ld b, 4
.fallback
	ld a, [hli]
	ld [de], a
	inc de
	dec b
	jr nz, .fallback
	ld a, [wFullColorAuthorityMap]
	ld [wFullColorDebugReconstructionState + 1], a
	ld a, [wFullColorAuthorityTileset]
	ld [wFullColorDebugReconstructionState + 2], a
	ld a, [wFullColorAuthorityY]
	ld [wFullColorDebugReconstructionState + 3], a
	ld a, [wFullColorAuthorityX]
	ld [wFullColorDebugReconstructionState + 4], a
	ret
ENDC

; Called with WRAM bank 2 selected during ownership initialization.
IF DEF(PHASE2_AUDIT)
InitFullColorPhase2LifecycleSelected::
	ld hl, wFullColorPhase2LifecycleStateStart
	ld bc, wFullColorPhase2LifecycleStateEnd - wFullColorPhase2LifecycleStateStart
	xor a
	jp FillMemory
ELSE
InitFullColorProductionLifecycleSelected::
	ld hl, wFullColorProductionLifecycleStateStart
	ld bc, wFullColorProductionLifecycleStateEnd - wFullColorProductionLifecycleStateStart
	xor a
	jp FillMemory
ENDC

; Copy the evolving 20x18 fixed-WRAM tile authority into producer-owned WRAM2
; and derive a separate attribute plane from independent tile-class authority.
; Bank 2 must be selected. Clobbers AF, BC, DE, HL.
SnapshotFullColorVisibleMapSelected::
	ld de, wTileMap
	ld hl, wFullColorProducerTiles
	ld bc, SCREEN_AREA
.tiles
	ld a, [de]
	ld [hli], a
	inc de
	dec bc
	ld a, b
	or c
	jr nz, .tiles
	ld de, wFullColorProducerTiles
	ld hl, wFullColorProducerAttributes
	ld bc, SCREEN_AREA
.attributes
	push bc
	push hl
	ld a, [de]
	ld c, a
	ld b, 0
	ld hl, FullColorOverworldTileAttributes
	add hl, bc
	ld a, [hl]
	pop hl
	ld [hli], a
	pop bc
	inc de
	dec bc
	ld a, b
	or c
	jr nz, .attributes
	ret

; Copy one byte from WRAM bank 1 into the guarded WRAM bank 2 snapshot. IE must
; already be masked. The value crosses banks in C, never through an aliased
; pointer, so bank-1 authority is never dereferenced while bank 2 is selected.
MACRO snapshot_wram1_byte
	ld a, 1
	ldh [rSVBK], a
	ld a, [\1]
	ld c, a
	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	ld a, c
	ld [\2], a
ENDM

; No inputs. Returns carry clear. Clobbers AF, BC, HL. Preserves the caller's
; raw IE and SVBK. The snapshot is a closed 16-byte authority record.
SnapshotFullColorMapAuthority::
	select_renderer_state_e
	snapshot_wram1_byte wCurMap, wFullColorAuthorityMap
	snapshot_wram1_byte wCurMapTileset, wFullColorAuthorityTileset
	snapshot_wram1_byte wYCoord, wFullColorAuthorityY
	snapshot_wram1_byte wXCoord, wFullColorAuthorityX
	snapshot_wram1_byte wCurrentTileBlockMapViewPointer, wFullColorAuthorityBlockView
	snapshot_wram1_byte wCurrentTileBlockMapViewPointer + 1, wFullColorAuthorityBlockView + 1
	snapshot_wram1_byte wMapViewVRAMPointer, wFullColorAuthorityVRAMView
	snapshot_wram1_byte wMapViewVRAMPointer + 1, wFullColorAuthorityVRAMView + 1
	snapshot_wram1_byte wCurMapHeight, wFullColorAuthorityMapHeight
	snapshot_wram1_byte wCurMapWidth, wFullColorAuthorityMapWidth
	snapshot_wram1_byte wNumSprites, wFullColorAuthoritySpriteCount
	; Sprite authority lives in fixed WRAM0 and is safe with bank 2 selected.
	ld a, [wSpritePlayerStateData1]
	ld [wFullColorAuthorityPlayerPicture], a
	ld a, [wSpritePikachuStateData1]
	ld [wFullColorAuthorityPikachuPicture], a
	xor a
	ld [wFullColorAuthorityReserved], a
	ld [wFullColorAuthorityReserved + 1], a
	ld [wFullColorAuthorityReserved + 2], a
	restore_renderer_state_e
	and a
	ret

; No inputs. Clobbers AF. Clears every legacy pending visible-video enable.
; Call at both sides of a Yellow/full-color ownership boundary.
PoisonLegacyVideoRequests::
	xor a
	ldh [hAutoBGTransferEnabled], a
	ldh [hVBlankCopyBGSource], a
	ldh [hVBlankCopyBGSource + 1], a
	ldh [hVBlankCopyBGNumRows], a
	ldh [hVBlankCopySize], a
	ldh [hVBlankCopyDoubleSize], a
	ldh [hRedrawRowOrColumnMode], a
	ld [wUpdateSpritesEnabled], a
	ret

; No inputs. Returns carry set on an ownership transition failure. Clobbers
; AF, BC, HL. Snapshots WRAM1 authority before ownership selects bank 2.
BeginFullColorMapEntry::
	call SnapshotFullColorMapAuthority
	call PoisonLegacyVideoRequests
	ld a, HANDOFF_TO_OVERWORLD
	call BeginRendererHandoff
	ret c
	jp SelectFullColorOwnerForDiagnostic

; No inputs. Returns carry clear only after reconstruction crosses the single
; presentation barrier and admissions reopen. Clobbers AF, BC, HL.
CompleteFullColorMapReconstruction::
	jp ReconstructFullColorMapEntry

; Expand the complete 1bpp font authority into VRAM bank 0 while presentation
; is hidden. FarCopyDataDouble uses one byte of Yellow WRAM1 as its private ROM
; bank save, so select that bank explicitly without reopening interrupts, then
; return to the Phase 2 state bank. The caller's raw VRAM bank is preserved.
; Bank 2 must be selected. Clobbers AF, BC, DE, HL.
LoadFullColorFontGraphicsSelected:
	ldh a, [rVBK]
	push af
	xor a
	ldh [rVBK], a
	ld a, 1
	ldh [rSVBK], a
	ld hl, FontGraphics
	ld de, vFont
	ld bc, FontGraphicsEnd - FontGraphics
	ld a, BANK(FontGraphics)
	call FarCopyDataDouble
	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	pop af
	ldh [rVBK], a
	ret

; No inputs. The caller must have begun map entry and kept LCD presentation
; hidden. Returns carry clear only after one complete BG palette plus the
; complete font graphics and 20x18 tile/attribute map have committed and
; admissions have reopened.
; Clobbers AF, BC, DE, HL.
ReconstructFullColorMapEntry::
	ldh a, [rLCDC]
	bit 7, a
	jp nz, .failed
	select_renderer_state_e
	ld a, [wRendererOwner]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jp nz, .restore_failed
	ld a, [wRendererPhase]
	cp OVERWORLD_RECONSTRUCTING
	jp nz, .restore_failed
	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN
	jr nz, .loadDiagnosticFont
	ld a, [wFullColorPhase5Scenario]
	cp FULL_COLOR_PHASE5_SCENARIO_PARTY_RECONSTRUCT_COLOR
	jr z, .fontReady
.loadDiagnosticFont
	call LoadFullColorFontGraphicsSelected
.fontReady
	call SnapshotFullColorVisibleMapSelected
	; Build the exact reconstruction descriptor and use the ordinary paired
	; preparation/commit machinery. Its source has already been snapshotted.
	ld hl, wFullColorSchedulerEnqueueDescriptor
	ld bc, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	xor a
	call FillMemory
	ld hl, wFullColorSchedulerEnqueueDescriptor
	ld a, FULL_COLOR_REQUEST_MAP_RECTANGLE_PAIRED
	ld [hli], a
	ld a, RENDERER_FULL_COLOR_OVERWORLD
	ld [hli], a
	ld de, wRendererGeneration
	REPT 4
		ld a, [de]
		ld [hli], a
		inc de
	ENDR
	ld a, [wFullColorAuthorityVRAMView]
	ld [hli], a
	ld a, [wFullColorAuthorityVRAMView + 1]
	ld [hli], a
	ld a, LOW(wFullColorProducerTiles)
	ld [hli], a
	ld a, HIGH(wFullColorProducerTiles)
	ld [hli], a
	ld a, FULL_COLOR_RECONSTRUCTION_WIDTH
	ld [hli], a
	ld a, FULL_COLOR_RECONSTRUCTION_HEIGHT
	ld [hli], a
	ld a, FULL_COLOR_RESOURCE_BG_MAP | FULL_COLOR_RESOURCE_ATTRIBUTES
	ld [hli], a
	xor a
	ld [hli], a
	ld a, LOW(SCREEN_AREA)
	ld [hli], a
	ld a, HIGH(SCREEN_AREA)
	ld [hli], a
	ld a, LOW(SCREEN_AREA * 2)
	ld [hli], a
	ld a, HIGH(SCREEN_AREA * 2)
	ld [hli], a
	xor a
	ld [hli], a
	ld [hl], a
	ld hl, wFullColorSchedulerEnqueueDescriptor
	ld d, h
	ld e, l
	call ValidateFullColorRequestResourcesSelected
	jp c, .restore_failed
	ld hl, wFullColorSchedulerEnqueueDescriptor
	call PrepareFullColorPairedTransferSelected
	jp c, .restore_failed
	call CommitFullColorPairedTransferSelected
	; Paired preparation deliberately uses the palette-buffer union as its
	; immutable attribute scratch.  Rebuild distinct base and transformed
	; palettes from linked ROM authority only after that final scratch consumer,
	; then publish both complete hardware destinations while still hidden.
	ld de, FullColorOverworldBGPalettes
	ld hl, wFullColorBGPaletteBase
	call CopyAndTransformFullColorPaletteSelected
	ld de, FullColorCanaryOBJPalettes
	ld hl, wFullColorOBJPaletteBase
	call CopyAndTransformFullColorPaletteSelected
	farcall FullColorPhase5PublishPartyColorPalettesSelected
	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN
	jp nz, .ordinaryBarrier
	ld a, [wFullColorPhase5Scenario]
	cp FULL_COLOR_PHASE5_SCENARIO_PARTY_RECONSTRUCT_COLOR
	jp nz, .ordinaryBarrier
	; Rebuild current-map shadow OAM from sprite logical state and authored final
	; picture identities.  Admission is deliberately still closed, so the
	; producer's scheduler submission is rejected after its finished shadow
	; batch is built; reconstruction performs the sole hidden DMA directly.
	restore_renderer_state_e
	; Party poison covers the player slots too. Rebuild from the real movement
	; producer after restoring ordinary WRAM; farcall restores its ROM bank.
	farcall LoadPlayerSpriteGraphics
	ld a, 1
	ld [wUpdateSpritesEnabled], a
	farcall PrepareFullColorOAMDataForOwnedVBlank
	call hDMARoutine
	; LoadScreenRelatedData rebuilt the logical viewport. Publish those fresh
	; coordinates while still hidden instead of retaining the poisoned overlay.
	ldh a, [hSCX]
	ldh [rSCX], a
	ldh a, [hSCY]
	ldh [rSCY], a
	ldh a, [hWY]
	ldh [rWY], a
	ld a, 7
	ldh [rWX], a
	select_renderer_state_e
	ld a, FULL_COLOR_PHASE5_LEDGER_ALL
	ld b, a
	ld a, [wFullColorPhase5ScenarioMutation]
	cp FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM
	jr nz, .colorLedgerReady
	res 2, b
.colorLedgerReady
	ld a, b
	ld [wFullColorPhase5ColorLedgerMask], a
	ld a, [wFullColorPhase5ScenarioMutation]
	and a
	jr nz, .phase5FailedSelected
	ld a, [wFullColorPhase5PoisonMask]
	cp FULL_COLOR_PHASE5_LEDGER_ALL
	jr nz, .phase5FailedSelected
	ld a, b
	cp FULL_COLOR_PHASE5_LEDGER_ALL
	jr nz, .phase5FailedSelected
	ld a, [wFullColorPartyReturnPending]
	and a
	jr z, .phase5FailedSelected
	ld a, FULL_COLOR_PHASE5_BARRIER_ARMED
	ld [wFullColorPhase5BarrierState], a
	restore_renderer_state_e
	and a
	ret
.phase5FailedSelected
	farcall RecordFullColorPhase5PartyFailureSelected
	jr .restore_failed
.ordinaryBarrier
	; Exactly one reconstruction barrier is observable before activation.
IF DEF(PHASE2_AUDIT)
	ld hl, wFullColorDebugReconstructionState
ELSE
	ld hl, wFullColorProductionReconstructionBarrier
ENDC
	inc [hl]
	restore_renderer_state_e
	call ActivateFullColorOwnerForDiagnostic
	ret c
	; BeginFullColorMapEntry poisoned sprite production before reconstruction.
	; Reopen it only after the hidden authoritative commit and successful owner
	; activation. The caller still owns the LCD-off boundary, so no active frame
	; can observe the old hidden batch between these two lifecycle points.
	ld a, 1
	ld [wUpdateSpritesEnabled], a
	and a
	ret
.restore_failed
	restore_renderer_state_e
.failed
	scf
	ret

; No inputs. Returns carry clear when Yellow owns before PartyMenuInit.
; Clobbers AF, BC, HL.
BeginFullColorPartyHandoff::
	call PoisonLegacyVideoRequests
	ld a, HANDOFF_TO_YELLOW
	call BeginRendererHandoff
	ret c
	call SelectYellowRenderer
	ret c
	select_renderer_state_e
	ld a, TRUE
	ld [wFullColorPartyReturnPending], a
	restore_renderer_state_e
	and a
	ret

; Farcall-safe party entry. Already-Yellow callers succeed idempotently without
; setting the Phase 2 return marker or advancing ownership generation.
EnsureFullColorPartyHandoff::
	call GetRendererOwner
	cp RENDERER_YELLOW
	jr z, .yellow
	jp BeginFullColorPartyHandoff
.yellow
	and a
	ret

; No inputs. Returns carry clear in OVERWORLD_RECONSTRUCTING. This poisons all
; prior presentation state and takes a fresh authority snapshot; it never
; restores captured VRAM. Clobbers AF, BC, HL.
ReturnFullColorFromParty::
	select_renderer_state_e
	ld a, [wFullColorPartyReturnPending]
	and a
	jr z, .not_party
	xor a
	ld [wFullColorPartyReturnPending], a
	restore_renderer_state_e
	call PoisonLegacyVideoRequests
	call SnapshotFullColorMapAuthority
	ld a, HANDOFF_TO_OVERWORLD
	call BeginRendererHandoff
	ret c
	jp SelectFullColorOwnerForDiagnostic
.not_party
	restore_renderer_state_e
	scf
	ret

; Returns A=1 and carry clear only for a Yellow owner reached through the
; successful Phase 2 party handoff. A=0/carry set is ordinary Yellow flow.
IsFullColorPartyReturnPending::
	select_renderer_state_e
	ld a, [wFullColorPartyReturnPending]
	ld b, a
	restore_renderer_state_e
	ld a, b
	and a
	ret nz
	scf
	ret

IF DEF(PHASE2_AUDIT)
; Phase 5 Party is a one-shot audit state machine.  The ordinary retained
; scaffold above remains available to its older direct probes, but natural
; Start/Party input reaches only these stricter entry points.
PUSHS
SECTION "Full Color Phase 5 Party Audit", ROMX

RecordFullColorPhase5PartyFailureSelected:
	ld a, FULL_COLOR_PHASE5_SCENARIO_RESULT_FAILED
	ld [wFullColorPhase5ScenarioResult], a
	ld a, FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED
	ld [wFullColorPhase5ScenarioState], a
	xor a
	ld [wRendererAdmissionOpen], a
	ret

; Run the independent audit cycle budget through every mutable boundary before
; the operation changes renderer state. A selected shortfall therefore leaves
; the operation byte-for-byte retryable; the observation carrier is the only
; state written. Ordinary Party flow has no armed stress mode and pays no
; cross-bank call cost.
CheckFullColorPhase5PartyCyclesSelected:
	ld a, [wFullColorPhase5StressMode]
	cp FULL_COLOR_PHASE5_STRESS_MODE_ARMED
	jr z, .armed
	and a
	ret
.armed
	ld c, FULL_COLOR_PHASE5_BOUNDARY_PREPARATION
	farcall FullColorPhase5AuditCycleCheckpointFromCSelected
	ret c
	ld c, FULL_COLOR_PHASE5_BOUNDARY_OWNER_REVALIDATION
	farcall FullColorPhase5AuditCycleCheckpointFromCSelected
	ret c
	ld c, FULL_COLOR_PHASE5_BOUNDARY_GENERATION_REVALIDATION
	farcall FullColorPhase5AuditCycleCheckpointFromCSelected
	ret c
	ld c, FULL_COLOR_PHASE5_BOUNDARY_DESTINATION_REVALIDATION
	farcall FullColorPhase5AuditCycleCheckpointFromCSelected
	ret c
	ld c, FULL_COLOR_PHASE5_BOUNDARY_BUDGET_REVALIDATION
	farcall FullColorPhase5AuditCycleCheckpointFromCSelected
	ret

IsFullColorPhase5PartyYellowReconstructing::
	select_renderer_state_e
	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN
	jr nz, .no
	ld a, [wRendererOwner]
	cp RENDERER_YELLOW
	jr nz, .no
	ld a, [wRendererPhase]
	cp YELLOW_RECONSTRUCTING
	jr nz, .no
	restore_renderer_state_e
	and a
	ret
.no
	restore_renderer_state_e
	scf
	ret

; The Party renderer records each fresh linked-ROM/logical producer only after
; that producer returns. C is one producer bit. This secondary ledger makes a
; real omitted write observable without changing the shared architectural
; eight-item ledger ABI.
RecordFullColorPhase5PartyYellowProducerStep::
	select_renderer_state_e
	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN
	jr nz, .done
	ld a, [wRendererOwner]
	cp RENDERER_YELLOW
	jr nz, .done
	ld a, [wRendererPhase]
	cp YELLOW_RECONSTRUCTING
	jr nz, .done
	ld a, [wFullColorPhase5ScenarioFlags]
	or c
	ld [wFullColorPhase5ScenarioFlags], a
.done
	restore_renderer_state_e
	ret

; Carry clear selects the hostile skipped-ledger-item case. It suppresses the
; actual font authority producer, leaving vFont poisoned and the producer bit
; absent; every ordinary reconstruction returns carry set and performs it.
ShouldSkipFullColorPhase5PartyFontProducer::
	select_renderer_state_e
	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN
	jr nz, .produce
	ld a, [wFullColorPhase5ScenarioMutation]
	cp FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM
	jr nz, .produce
	restore_renderer_state_e
	and a
	ret
.produce
	restore_renderer_state_e
	scf
	ret

; Bank 2 is already selected by reconstruction. Publish the two complete
; freshly-derived palette bases without disturbing that selection.
FullColorPhase5PublishPartyColorPalettesSelected:
	ld a, $80
	ldh [rBGPI], a
	ld hl, wFullColorBGPaletteBase
	ld b, FULL_COLOR_PALETTE_EXTENT
.bgPalette
	ld a, [hli]
	ldh [rBGPD], a
	dec b
	jr nz, .bgPalette
	ld a, $80
	ldh [rOBPI], a
	ld hl, wFullColorOBJPaletteBase
	ld b, FULL_COLOR_PALETTE_EXTENT
.objPalette
	ld a, [hli]
	ldh [rOBPD], a
	dec b
	jr nz, .objPalette
	ret

FullColorPhase5AcknowledgeLegacyPaletteRegisters::
	ldh a, [rBGP]
	ld [wLastBGP], a
	ldh a, [rOBP0]
	ld [wLastOBP0], a
	ldh a, [rOBP1]
	ld [wLastOBP1], a
	ret

; Keep one complete double-speed scanline between the finished, validated
; reconstruction and its first physical presentation instruction. BC is the
; only scratch and is restored exactly; LCD remains disabled throughout.
; CPU T-cycle equation for B=55:
;   push bc 16 + ld b,n 8 + 54 * (dec b 4 + jr nz,taken 12)
;   + dec b 4 + jr nz,not-taken 8 + pop bc 12 = 912.
FullColorPhase5PartyReconstructColorPresentationGuardStart::
	push bc
	ld b, 55
.presentationGuard
	dec b
	jr nz, .presentationGuard
	pop bc
FullColorPhase5PartyReconstructColorPresentationGuardEnd::
	ret

IsFullColorPhase5PartyDeferred::
	select_renderer_state_e
	ld a, [wFullColorPhase5StressTerminalResult]
	cp FULL_COLOR_PHASE5_TERMINAL_DEFERRED
	jr nz, .no
	restore_renderer_state_e
	and a
	ret
.no
	restore_renderer_state_e
	scf
	ret

; Fill one complete 20x18 logical screen into the selected BG map while the
; LCD is off.  This is fresh wTileMap authority, never either backup buffer.
CopyFullColorPhase5TileMapToVRAM:
	ld hl, wTileMap
	; Start/Party uses the LCD window plane at WY=0, WX=7. Publish the fresh
	; logical Party screen to that selected destination, not the hidden BG plane.
	ld de, vBGMap1
	ld b, SCREEN_HEIGHT
.row
	ld c, SCREEN_WIDTH
.column
	ld a, [hli]
	ld [de], a
	inc e
	dec c
	jr nz, .column
	ld a, TILEMAP_WIDTH - SCREEN_WIDTH
	add e
	ld e, a
	jr nc, .noCarry
	inc d
.noCarry
	dec b
	jr nz, .row
	ret

; The poison is intentionally broader than the reconstructed visible unit.
; It covers the complete Party-relevant banks, maps, palette/OAM carriers,
; saved buffers, viewport and legacy transfer state while presentation is
; hidden.  The live stack is never used as a poison destination.
PoisonFullColorPhase5PartyState:
	ldh a, [rLCDC]
	bit B_LCDC_ENABLE, a
	jp nz, .failed
	ldh a, [rVBK]
	push af
	xor a
	ldh [rVBK], a
	ld hl, vChars0
	ld bc, vBGMap1 + TILEMAP_AREA - vChars0
	ld a, $d3
	call FillMemory
	ld a, 1
	ldh [rVBK], a
	ld hl, vBGMap0
	ld bc, TILEMAP_AREA * 2
	ld a, $6d
	call FillMemory
	pop af
	ldh [rVBK], a

	ld hl, wTileMap
	ld bc, SCREEN_AREA
	ld a, $d3
	call FillMemory
	ld hl, wTileMapBackup
	ld bc, SCREEN_AREA
	ld a, $6d
	call FillMemory
	ld hl, wTileMapBackup2
	ld bc, SCREEN_AREA
	ld a, $b7
	call FillMemory
	ld hl, wShadowOAM
	ld bc, wShadowOAMEnd - wShadowOAM
	ld a, $d3
	call FillMemory
	ld hl, wShadowOAMBackup
	ld bc, wShadowOAMBackupEnd - wShadowOAMBackup
	ld a, $6d
	call FillMemory
	ld hl, wMonPartySpritesSavedOAM
	ld bc, OBJ_SIZE * 4 * PARTY_LENGTH
	ld a, $b7
	call FillMemory
	ld hl, $fe00
	ld bc, OAM_COUNT * 4
	ld a, $b7
	call FillMemory
	ld hl, wCGBBasePalPointers
	ld bc, wBGPPalsBuffer + NUM_ACTIVE_PALS * PAL_SIZE - wCGBBasePalPointers
	ld a, $d3
	call FillMemory

	ld a, $80
	ldh [rBGPI], a
	ldh [rOBPI], a
	ld b, FULL_COLOR_PALETTE_EXTENT
.palettes
	ld a, $6d
	ldh [rBGPD], a
	ld a, $b7
	ldh [rOBPD], a
	dec b
	jr nz, .palettes

	ld a, $d3
	ldh [hSCX], a
	ldh [hSCY], a
	ldh [hWY], a
	ldh [rSCX], a
	ldh [rSCY], a
	ldh [rWY], a
	ldh [rWX], a
	ld [wUpdateSpritesEnabled], a
	ldh [hTileAnimations], a
	farcall PoisonLegacyVideoRequests
	; Force the later fresh map-sprite producer through its source-table load;
	; the cached set identity cannot certify VRAM after full tile poison.
	ld a, $ff
	ld [wSpriteSetID], a

	select_renderer_state_e
	; Poison the complete retained renderer preparation authority as well as the
	; Yellow-facing carriers above.  The scenario control and return marker are
	; deliberately outside these ranges, so the route remains live while stale
	; palettes, paired buffers, OAM, descriptors and producer metadata cannot.
	ld hl, wFullColorBGPaletteBase
	ld bc, wFullColorPhase2StateEnd - wFullColorBGPaletteBase
	ld a, $d3
	call FillMemory
	ld hl, wFullColorAuthoritySnapshot
	ld bc, wFullColorPartyReturnPending - wFullColorAuthoritySnapshot
	ld a, $d3
	call FillMemory
	ld hl, wFullColorPartyReturnPending + 1
	ld bc, wFullColorDebugCarrierStart - (wFullColorPartyReturnPending + 1)
	ld a, $d3
	call FillMemory
	farcall InitFullColorSchedulerSelected
	ld a, FULL_COLOR_PHASE5_LEDGER_ALL
	ld b, a
	ld a, [wFullColorPhase5ScenarioMutation]
	cp FULL_COLOR_PHASE5_MUTATION_MISSING_POISON
	jr nz, .poisonRecorded
	res 0, b
.poisonRecorded
	ld a, b
	ld [wFullColorPhase5PoisonMask], a
	restore_renderer_state_e
	and a
	ret
.failed
	scf
	ret

FullColorPhase5PartyHandoffToYellowOrigin::
FullColorPhase5PartyHandoffToYellowStart::
BeginFullColorPhase5PartyHandoffToYellow::
	select_renderer_state_e
	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED
	jp nz, FullColorPhase5PartyHandoffToYellowNotArmed
	ld a, [wFullColorPhase5Scenario]
	cp FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_YELLOW
	jp nz, FullColorPhase5PartyHandoffToYellowNotArmed
	call CheckFullColorPhase5PartyCyclesSelected
	jp c, FullColorPhase5PartyHandoffToYellowDeferredSelected
	restore_renderer_state_e
	ld c, HANDOFF_TO_YELLOW
	farcall FullColorPhase5BeginRendererHandoffFromCSelected
	jp c, FullColorPhase5PartyHandoffToYellowFailedOutside
	select_renderer_state_e
	ld a, [wRendererOwner]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jr nz, FullColorPhase5PartyHandoffToYellowFailedSelected
	ld a, [wRendererPhase]
	cp HANDOFF_TO_YELLOW
	jr nz, FullColorPhase5PartyHandoffToYellowFailedSelected
	ld a, RENDERER_YELLOW
	ld [wRendererOwner], a
	ld a, YELLOW_RECONSTRUCTING
	ld [wRendererPhase], a
	clear_renderer_job
	ld a, TRUE
	ld [wFullColorPartyReturnPending], a
	ld a, FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN
	ld [wFullColorPhase5ScenarioControl], a
	ld a, FULL_COLOR_PHASE5_SCENARIO_STATE_RUNNING
	ld [wFullColorPhase5ScenarioState], a
	xor a
	ld [wFullColorPhase5ScenarioResult], a
	ld [wFullColorPhase5PoisonMask], a
	ld [wFullColorPhase5YellowLedgerMask], a
	ld [wFullColorPhase5ColorLedgerMask], a
	ld [wFullColorPhase5BarrierState], a
	ld [wFullColorPhase5StableFrames], a
	ld [wFullColorPhase5ScenarioFlags], a
	restore_renderer_state_e
	ldh a, [rIF]
	push af
	ldh a, [rLCDC]
	bit B_LCDC_ENABLE, a
	call nz, DisableLCD
	pop af
	ldh [rIF], a
	call PoisonFullColorPhase5PartyState
	jr c, FullColorPhase5PartyHandoffToYellowFailedOutside
FullColorPhase5PartyHandoffToYellowEnd::
	and a
	ret
FullColorPhase5PartyHandoffToYellowFailedSelected:
	call RecordFullColorPhase5PartyFailureSelected
	restore_renderer_state_e
FullColorPhase5PartyHandoffToYellowFailedOutside:
	scf
	ret
FullColorPhase5PartyHandoffToYellowDeferredSelected:
	restore_renderer_state_e
	ld a, FULL_COLOR_PHASE5_TERMINAL_DEFERRED
	scf
	ret
FullColorPhase5PartyHandoffToYellowNotArmed:
	restore_renderer_state_e
	scf
	ret

; Called by the audit DrawPartyMenu_ only after PartyMenuInit, ROM icon/HP
; producers, logical tile construction, Yellow attributes, and palette
; generation have all completed with the LCD still disabled.
CompleteFullColorPhase5PartyYellowReconstruction::
	ldh a, [rLCDC]
	bit B_LCDC_ENABLE, a
	jp nz, FullColorPhase5PartyYellowPresentationFailed
	xor a
	ldh [rVBK], a
	call CopyFullColorPhase5TileMapToVRAM
	call hDMARoutine
	xor a
	ldh [hAutoBGTransferEnabled], a
	ldh [hSCX], a
	ldh [hSCY], a
	ldh [hWY], a
	ldh [rSCX], a
	ldh [rSCY], a
	ldh [rWY], a
	ld a, 7
	ldh [rWX], a
	select_renderer_state_e
	ld a, FULL_COLOR_PHASE5_LEDGER_ALL
	ld b, a
	ld a, [wFullColorPhase5ScenarioMutation]
	cp FULL_COLOR_PHASE5_MUTATION_SKIPPED_ITEM
	jr nz, .ledgerReady
	res 2, b
.ledgerReady
	ld a, b
	ld [wFullColorPhase5YellowLedgerMask], a
	ld a, [wFullColorPhase5ScenarioMutation]
	and a
	jr nz, FullColorPhase5PartyYellowMutationFailed
	ld a, [wFullColorPhase5PoisonMask]
	cp FULL_COLOR_PHASE5_LEDGER_ALL
	jr nz, FullColorPhase5PartyYellowMutationFailed
	ld a, b
	cp FULL_COLOR_PHASE5_LEDGER_ALL
	jr nz, FullColorPhase5PartyYellowMutationFailed
	ld a, [wFullColorPhase5ScenarioFlags]
	cp FULL_COLOR_PHASE5_LEDGER_ALL
	jr nz, FullColorPhase5PartyYellowMutationFailed
	ld a, [wFullColorPartyReturnPending]
	and a
	jr z, FullColorPhase5PartyYellowMutationFailed
	ld a, FULL_COLOR_PHASE5_BARRIER_ARMED
	ld [wFullColorPhase5BarrierState], a
	restore_renderer_state_e
FullColorPhase5PartyHandoffToYellowDeadline::
	call EnableLCD
	select_renderer_state_e
	ld a, FULL_COLOR_PHASE5_BARRIER_PRESENTED
	ld [wFullColorPhase5BarrierState], a
	ld a, YELLOW_ACTIVE
	ld [wRendererPhase], a
	ld a, TRUE
	ld [wRendererAdmissionOpen], a
	ld a, FULL_COLOR_PHASE5_SCENARIO_STATE_YELLOW_ACTIVE
	ld [wFullColorPhase5ScenarioState], a
	xor a
	ld [wFullColorPhase5StableFrames], a
	restore_renderer_state_e
	and a
	ret
FullColorPhase5PartyYellowMutationFailed:
	call RecordFullColorPhase5PartyFailureSelected
	restore_renderer_state_e
FullColorPhase5PartyYellowPresentationFailed:
	scf
	ret

FullColorPhase5PartyHandoffToColorOrigin::
FullColorPhase5PartyReconstructColorOrigin::
FullColorPhase5PartyHandoffToColorStart::
BeginFullColorPhase5PartyHandoffToColor::
	select_renderer_state_e
	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN
	jp nz, FullColorPhase5PartyHandoffToColorNotRunning
	ld a, [wFullColorPhase5ScenarioState]
	cp FULL_COLOR_PHASE5_SCENARIO_STATE_STABLE
	jr nz, FullColorPhase5PartyHandoffToColorFailedSelected
	ld a, [wFullColorPhase5YellowLedgerMask]
	cp FULL_COLOR_PHASE5_LEDGER_ALL
	jr nz, FullColorPhase5PartyHandoffToColorFailedSelected
	ld a, [wFullColorPartyReturnPending]
	and a
	jr z, FullColorPhase5PartyHandoffToColorFailedSelected
	call CheckFullColorPhase5PartyCyclesSelected
	jr c, FullColorPhase5PartyHandoffToColorDeferredSelected
	ld a, FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_COLOR
	ld [wFullColorPhase5Scenario], a
	; Publish reconstruction intent before the owner/phase transition so an
	; interrupting stable-frame observer cannot misclassify the closed handoff
	; as a broken Yellow-active frame.
	ld a, FULL_COLOR_PHASE5_SCENARIO_STATE_COLOR_RECONSTRUCTING
	ld [wFullColorPhase5ScenarioState], a
	restore_renderer_state_e
	ld c, HANDOFF_TO_OVERWORLD
	farcall FullColorPhase5BeginRendererHandoffFromCSelected
	jr c, FullColorPhase5PartyHandoffToColorFailedOutside
	farcall SelectFullColorOwnerForDiagnostic
	jr c, FullColorPhase5PartyHandoffToColorFailedOutside
	ldh a, [rIF]
	push af
	ldh a, [rLCDC]
	bit B_LCDC_ENABLE, a
	call nz, DisableLCD
	pop af
	ldh [rIF], a
	call PoisonFullColorPhase5PartyState
	jr c, FullColorPhase5PartyHandoffToColorFailedOutside
	select_renderer_state_e
	xor a
	ld [wFullColorPhase5ColorLedgerMask], a
	ld [wFullColorPhase5BarrierState], a
	ld [wFullColorPhase5StableFrames], a
	restore_renderer_state_e
FullColorPhase5PartyHandoffToColorEnd::
	and a
	ret
FullColorPhase5PartyHandoffToColorFailedSelected:
	call RecordFullColorPhase5PartyFailureSelected
	restore_renderer_state_e
FullColorPhase5PartyHandoffToColorFailedOutside:
	scf
	ret
FullColorPhase5PartyHandoffToColorDeferredSelected:
	restore_renderer_state_e
	ld a, FULL_COLOR_PHASE5_TERMINAL_DEFERRED
	scf
	ret
FullColorPhase5PartyHandoffToColorNotRunning:
	restore_renderer_state_e
	scf
	ret

FullColorPhase5PartyReconstructColorStart::
BeginFullColorPhase5PartyColorReconstruction::
	select_renderer_state_e
	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN
	jr nz, .invalid
	ld a, [wRendererOwner]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jr nz, .invalid
	ld a, [wRendererPhase]
	cp OVERWORLD_RECONSTRUCTING
	jr nz, .invalid
	ld a, [wRendererAdmissionOpen]
	and a
	jr nz, .invalid
	call CheckFullColorPhase5PartyCyclesSelected
	jr c, .deferred
	ld a, FULL_COLOR_PHASE5_SCENARIO_PARTY_RECONSTRUCT_COLOR
	ld [wFullColorPhase5Scenario], a
	ld a, FULL_COLOR_PHASE5_SCENARIO_STATE_COLOR_RECONSTRUCTING
	ld [wFullColorPhase5ScenarioState], a
	restore_renderer_state_e
	and a
	ret
.deferred
	restore_renderer_state_e
	ld a, FULL_COLOR_PHASE5_TERMINAL_DEFERRED
	scf
	ret
.invalid
	call RecordFullColorPhase5PartyFailureSelected
	restore_renderer_state_e
	scf
	ret

; The caller has just executed the one physical EnableLCD barrier after fresh
; map/header/block/tile/replacement/palette/OAM construction.  Only now may the
; Color owner become active and reopen admission.
IsFullColorPhase5PartyColorPresentationPending::
	select_renderer_state_e
	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN
	jr nz, .no
	ld a, [wFullColorPhase5Scenario]
	cp FULL_COLOR_PHASE5_SCENARIO_PARTY_RECONSTRUCT_COLOR
	jr nz, .no
	ld a, [wRendererPhase]
	cp OVERWORLD_RECONSTRUCTING
	jr nz, .no
	restore_renderer_state_e
	and a
	ret
.no
	restore_renderer_state_e
	scf
	ret

; One farcall-sized bridge for the fixed-bank map loader. Non-Phase5 map loads
; succeed without activation; a pending Phase5 reconstruction completes in
; this bank so the caller can distinguish a real validation failure by carry.
FullColorPhase5CompletePartyColorPresentationIfPending::
	call IsFullColorPhase5PartyColorPresentationPending
	jr nc, .pending
	and a
	ret
.pending
	jp CompleteFullColorPhase5PartyColorPresentation

CompleteFullColorPhase5PartyColorPresentation::
	select_renderer_state_e
	ld a, [wFullColorPhase5BarrierState]
	cp FULL_COLOR_PHASE5_BARRIER_ARMED
	jr nz, FullColorPhase5PartyColorPresentationInvalid
	ld a, [wFullColorPhase5ColorLedgerMask]
	cp FULL_COLOR_PHASE5_LEDGER_ALL
	jr nz, FullColorPhase5PartyColorPresentationInvalid
	ld a, [wFullColorPartyReturnPending]
	and a
	jr z, FullColorPhase5PartyColorPresentationInvalid
	ld a, [wRendererOwner]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jr nz, FullColorPhase5PartyColorPresentationInvalid
	ld a, [wRendererPhase]
	cp OVERWORLD_RECONSTRUCTING
	jr nz, FullColorPhase5PartyColorPresentationInvalid
	ld a, FULL_COLOR_PHASE5_BARRIER_PRESENTED
	ld [wFullColorPhase5BarrierState], a
	ld a, OVERWORLD_ACTIVE
	ld [wRendererPhase], a
	ld a, TRUE
	ld [wRendererAdmissionOpen], a
	ld a, FULL_COLOR_PHASE5_SCENARIO_STATE_COLOR_PRESENTED
	ld [wFullColorPhase5ScenarioState], a
	xor a
	ld [wFullColorPhase5StableFrames], a
	restore_renderer_state_e
	and a
	ret
FullColorPhase5PartyColorPresentationInvalid:
	call RecordFullColorPhase5PartyFailureSelected
	restore_renderer_state_e
	scf
	ret

; Called once from the ordinary VBlank ownership decision.  Five consecutive
; frames must retain the expected owner, phase, open admission, complete
; ledger, and presented barrier.  Any discontinuity fails closed.
UpdateFullColorPhase5PartyStableFrames::
	select_renderer_state_e
	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_RUN
	jp nz, .done
	ld a, [wFullColorPhase5ScenarioState]
	cp FULL_COLOR_PHASE5_SCENARIO_STATE_YELLOW_ACTIVE
	jr z, .yellow
	cp FULL_COLOR_PHASE5_SCENARIO_STATE_COLOR_PRESENTED
	jr z, .color
	jr .done
.yellow
	; BeginRendererHandoff closes admission before changing owner/phase. A VBlank
	; inside that intentionally hidden interval must not reinterpret the already
	; proven five-frame Yellow presentation as a new active-frame failure.
	ld a, [wRendererAdmissionOpen]
	and a
	jr z, .done
	ld a, [wRendererOwner]
	cp RENDERER_YELLOW
	jr nz, .failed
	ld a, [wRendererPhase]
	cp YELLOW_ACTIVE
	jr nz, .failed
	ld a, [wFullColorPhase5YellowLedgerMask]
	cp FULL_COLOR_PHASE5_LEDGER_ALL
	jr nz, .failed
	ld a, [wFullColorPhase5ScenarioFlags]
	cp FULL_COLOR_PHASE5_LEDGER_ALL
	jr nz, .failed
	ld b, FULL_COLOR_PHASE5_SCENARIO_PARTY_HANDOFF_TO_COLOR
	jr .count
.color
	ld a, [wRendererOwner]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jr nz, .failed
	ld a, [wRendererPhase]
	cp OVERWORLD_ACTIVE
	jr nz, .failed
	ld a, [wFullColorPhase5ColorLedgerMask]
	cp FULL_COLOR_PHASE5_LEDGER_ALL
	jr nz, .failed
	ld b, FULL_COLOR_PHASE5_SCENARIO_NONE
.count
	ld a, [wRendererAdmissionOpen]
	cp TRUE
	jr nz, .failed
	ld a, [wFullColorPhase5BarrierState]
	cp FULL_COLOR_PHASE5_BARRIER_PRESENTED
	jr nz, .failed
	ld hl, wFullColorPhase5StableFrames
	inc [hl]
	ld a, [hl]
	cp 5
	jr c, .done
	ld [hl], 5
	ld a, FULL_COLOR_PHASE5_BARRIER_STABLE
	ld [wFullColorPhase5BarrierState], a
	ld a, b
	and a
	jr z, .complete
	ld [wFullColorPhase5Scenario], a
	ld a, FULL_COLOR_PHASE5_SCENARIO_STATE_STABLE
	ld [wFullColorPhase5ScenarioState], a
	jr .done
.complete
	ld a, FULL_COLOR_PHASE5_SCENARIO_STATE_COMPLETE
	ld [wFullColorPhase5ScenarioState], a
	ld a, FULL_COLOR_PHASE5_SCENARIO_RESULT_PASSED
	ld [wFullColorPhase5ScenarioResult], a
	xor a
	ld [wFullColorPartyReturnPending], a
	ld [wFullColorPhase5ScenarioControl], a
	jr .done
.failed
	call RecordFullColorPhase5PartyFailureSelected
.done
	restore_renderer_state_e
	ret
POPS
ENDC

; Generic bounded-slice exit. Idempotent when Yellow already owns. This never
; sets the party-return marker.
LeaveFullColorOverworldSlice::
	call GetRendererOwner
	cp RENDERER_YELLOW
	jr z, .done
	call PoisonLegacyVideoRequests
	ld a, HANDOFF_TO_YELLOW
	call BeginRendererHandoff
	ret c
	jp SelectYellowRenderer
.done
	and a
	ret

; Conventional farcall-safe ownership predicate. Carry clear means the current
; owner is the full-color overworld; carry set means every other owner. A is
; deliberately unspecified because Bankswitch restores the caller ROM bank
; through A after this routine returns.
IsFullColorOverworldOwnerFar::
	call GetRendererOwner
	cp RENDERER_FULL_COLOR_OVERWORLD
	ret z
	scf
	ret

; Overlay boundaries change only the exact ownership phase. They snapshot the
; evolving fixed-WRAM tile authority before returning, so later producers do
; not reconstruct from stale entry data.
EnterFullColorOverlay::
	ld c, OVERWORLD_ACTIVE
	ld b, OVERWORLD_OVERLAY
	jr ChangeFullColorOverlayPhase
ExitFullColorOverlay::
	ld c, OVERWORLD_OVERLAY
	ld b, OVERWORLD_ACTIVE
ChangeFullColorOverlayPhase:
	select_renderer_state_e
	ld a, [wRendererOwner]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jr nz, .invalid
	ld a, [wRendererPhase]
	cp c
	jr nz, .invalid
	ld a, b
	ld [wRendererPhase], a
	call SnapshotFullColorVisibleMapSelected
	restore_renderer_state_e
	and a
	ret
.invalid
	restore_renderer_state_e
	scf
	ret

; Full-color close restores gameplay authority in WRAM, never from the legacy
; saved VRAM image. Presentation remains owned until the immutable replacement
; is queued; ExitFullColorOverlay then returns the lifecycle to ACTIVE.
PrepareCloseFullColorTextDisplay::
	xor a
	ldh [hAutoBGTransferEnabled], a
	ld hl, wSprite01StateData2OrigFacingDirection
	ld c, NUM_SPRITESTATEDATA_STRUCTS - 1
	ld de, SPRITESTATEDATA1_LENGTH
.restoreSpriteFacingDirectionLoop
	ld a, [hl]
	dec h
	ld [hl], a
	inc h
	add hl, de
	dec c
	jr nz, .restoreSpriteFacingDirectionLoop
	ld hl, wFontLoaded
	res BIT_FONT_LOADED, [hl]
	call LoadCurrentMapView
	call ExitFullColorOverlay
	jr c, .failed
.enqueueRestoredMap
	call EnqueueFullColorCurrentTileMapOverlayFar
	jr c, .enqueueRestoredMap
	ld a, $90
	ldh [hWY], a
	ret
.failed
	jr .failed

; HL points to a fixed-WRAM 20-byte descriptor. These class-exact wrappers
; return the scheduler result in A; carry is clear only for ACCEPTED/COALESCED.
MACRO exact_paired_submit
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp \1
	jr z, .valid\@
	ld a, DEFERRED
	scf
	ret
.valid\@
	jp AdmitFullColorRequest
ENDM

SubmitFullColorMapRow::
	exact_paired_submit FULL_COLOR_REQUEST_MAP_ROW_PAIRED
SubmitFullColorMapColumn::
	exact_paired_submit FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED
SubmitFullColorMapConnection::
	exact_paired_submit FULL_COLOR_REQUEST_MAP_CONNECTION_PAIRED
SubmitFullColorMapOverlay::
	exact_paired_submit FULL_COLOR_REQUEST_MAP_OVERLAY_PAIRED
SubmitFullColorMapRectangle::
	exact_paired_submit FULL_COLOR_REQUEST_MAP_RECTANGLE_PAIRED
SubmitFullColorAnimationReplacement::
	exact_paired_submit FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT

; No-input adapter for Home producers. Conventional farcall consumes A, B and
; HL, so rebuild the complete semantic overlay ABI after entering this bank.
; The destination comes from the closed map-authority snapshot in WRAM2.
EnqueueFullColorCurrentTileMapOverlayFar::
	select_renderer_state_e
	ld a, [wFullColorAuthorityVRAMView]
	ld e, a
	ld a, [wFullColorAuthorityVRAMView + 1]
	ld d, a
	restore_renderer_state_e
	ld hl, wTileMap
	ld b, SCREEN_WIDTH
	ld c, SCREEN_HEIGHT
	jp EnqueueFullColorMapOverlay

; No-input adapter for window-backed dialogue and start-menu producers. Window
; presentation is always the BG1 map at $9c00; it must not inherit the BG0
; destination captured by overworld map authority.
EnqueueFullColorWindowTileMapOverlayFar::
	ld de, vBGMap1
	ld hl, wTileMap
	ld b, SCREEN_WIDTH
	ld c, SCREEN_HEIGHT
	jp EnqueueFullColorMapOverlay

; Farcall-safe adapters for bank-1 producers. These contracts avoid relying on
; the conventional farcall register scratch used by the internal APIs.
; Map: C=identity, DE=attribute pointer within wShadowOAM. The farcall itself
; consumes A, B and HL, so derive the reverse object cursor from the surviving
; pointer only after entering this bank.
MapFullColorOAMAttributeFar::
	ld h, d
	ld l, e
	ld a, e
	sub LOW(wShadowOAM + 3)
	srl a
	srl a
	ld b, a
	ld a, OAM_COUNT
	sub b
	ld b, a
	ld a, c
	jp MapFullColorOAMAttribute

; Enqueue: DE=fixed-WRAM finished 160-byte OAM batch. Returns the ordinary
; EnqueueFullColorOAMBatch A/carry result.
EnqueueFullColorOAMBatchFar::
	ld h, d
	ld l, e
	jp EnqueueFullColorOAMBatch

IF DEF(PHASE2_AUDIT)
; Fixed-carrier adapter for the audit-only Pallet pressure producer.  The
; bank-switch ABI consumes HL, so reconstruct the real admission pointer here.
AdmitFullColorPhase5PressureDescriptorFar::
	ld hl, wFullColorSchedulerEnqueueDescriptor
	jp AdmitFullColorRequest

; The cross-bank audit cache stores the already-selected resident pointer
; because Bankswitch consumes HL. Reconstruct it only after all five live
; revalidations have passed and the descriptor has entered COMMITTING.
CommitFullColorPhase5ActiveDescriptorFar::
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	jp CommitFullColorVisibleUnitSelected
ENDC

; Carry clear means the owner consumed the VBlank. Yellow-visible writers must
; be skipped. Carry set means Yellow remains the VBlank owner.
IF DEF(PHASE2_AUDIT)
FullColorPhase5CombinedVBlankStart::
ENDC
FullColorVBlankOwnerConsumed::
IF DEF(PHASE2_AUDIT)
	call GetRendererOwner
	cp RENDERER_FULL_COLOR_OVERWORLD
	jr nz, FullColorPhase5CombinedVBlankYellow
FullColorPhase5OwnerRevalidationEnd::
	; Mainline declared the finished batch directly in fixed wShadowOAM; no
	; WRAM2 shadow recopy or mutable producer reread remains in this VBlank.
	; The audit fast cache removes generic scans but remains fail-closed: VBlank
	; revalidates the complete OAM identity and every commit-relevant cached
	; field immediately before the same atomic commit functions.
	farcall RunFullColorPhase5CachedVBlank
	; Presentation follows the scheduler commit barrier in this same VBlank.
	; Yellow's route publishes these registers in Home and never reaches here.
	ldh a, [hSCX]
	ldh [rSCX], a
	ldh a, [hSCY]
	ldh [rSCY], a
.publishWindowY
	ldh a, [hWY]
	ldh [rWY], a
	and a
FullColorPhase5OAMBuildDeadline::
FullColorPhase5NorthConnectionDeadline::
	ret
FullColorPhase5CombinedVBlankYellow:
	; Party/menu DelayFrame loops never reach the overworld mainline observer.
	; Count only this already-selected Yellow branch; owned Color timing remains
	; outside VBlank in FullColorPhase5PrepareOwnedMainlineFrame.
	farcall UpdateFullColorPhase5PartyStableFrames
	scf
	ret
ELSE
	; This audit integration route is deliberately inert in production Phase 1.
	scf
	ret
ENDC

EXPORT SnapshotFullColorMapAuthority, PoisonLegacyVideoRequests
EXPORT BeginFullColorMapEntry, CompleteFullColorMapReconstruction
EXPORT ReconstructFullColorMapEntry
EXPORT BeginFullColorPartyHandoff, ReturnFullColorFromParty
EXPORT EnsureFullColorPartyHandoff
EXPORT IsFullColorPartyReturnPending, LeaveFullColorOverworldSlice
EXPORT IsFullColorOverworldOwnerFar
EXPORT EnterFullColorOverlay, ExitFullColorOverlay
EXPORT SubmitFullColorMapRow, SubmitFullColorMapColumn
EXPORT SubmitFullColorMapConnection, SubmitFullColorMapOverlay
EXPORT SubmitFullColorMapRectangle, SubmitFullColorAnimationReplacement
EXPORT EnqueueFullColorCurrentTileMapOverlayFar
EXPORT EnqueueFullColorWindowTileMapOverlayFar
EXPORT MapFullColorOAMAttributeFar, EnqueueFullColorOAMBatchFar
EXPORT FullColorVBlankOwnerConsumed
IF DEF(PHASE2_AUDIT)
EXPORT InitFullColorPhase2LifecycleSelected
EXPORT AdmitFullColorPhase5PressureDescriptorFar
EXPORT BeginFullColorPhase5PartyHandoffToYellow
EXPORT IsFullColorPhase5PartyYellowReconstructing
EXPORT RecordFullColorPhase5PartyYellowProducerStep
EXPORT ShouldSkipFullColorPhase5PartyFontProducer
EXPORT CompleteFullColorPhase5PartyYellowReconstruction
EXPORT BeginFullColorPhase5PartyHandoffToColor
EXPORT BeginFullColorPhase5PartyColorReconstruction
EXPORT IsFullColorPhase5PartyColorPresentationPending
EXPORT CompleteFullColorPhase5PartyColorPresentation
EXPORT FullColorPhase5PartyHandoffToYellowStart
EXPORT FullColorPhase5PartyHandoffToYellowEnd
EXPORT FullColorPhase5PartyHandoffToYellowOrigin
EXPORT FullColorPhase5PartyHandoffToYellowDeadline
EXPORT FullColorPhase5PartyHandoffToColorStart
EXPORT FullColorPhase5PartyHandoffToColorEnd
EXPORT FullColorPhase5PartyHandoffToColorOrigin
EXPORT FullColorPhase5PartyReconstructColorStart
EXPORT FullColorPhase5PartyReconstructColorOrigin
ELSE
EXPORT InitFullColorProductionLifecycleSelected
ENDC

; Phase 5 audit-only scheduler checkpoint and pressure protocol.
;
; The callable root lives after FULL_COLOR_PHASE2_ROM_END and has no production
; call site. It drives one already-admitted visible unit through the retained
; scheduler's exact PREPARED-to-COMPLETE boundary. The host supplies separate
; audit-only available/required cycle values at one mutable checkpoint. These
; values never alias descriptor write reservations or production scheduler
; budget state. Identity failures cancel;
; current resource or budget pressure defers with the descriptor and frozen
; preparation scratch unchanged. COMMITTING is observation-only.

FullColorPhase5StressReset::
	select_renderer_state_e
	ld hl, wFullColorDebugTraceCountPhase2
	ld bc, wFullColorPhase5StressStateEnd - wFullColorDebugTraceCountPhase2
	xor a
	call FillMemory
	restore_renderer_state_e
	ret

; Banked callers put the boundary in C because farcall consumes A. The bridge
; is one byte and falls through to the ordinary selected-call ABI.
FullColorPhase5AuditCycleCheckpointFromCSelected::
	ld a, c

; A=mutable boundary. Called only with renderer WRAM bank 2 already selected.
; Carry clear means the independent audit cycle budget fits; carry set means
; defer (or invalid control). BC, DE and HL are preserved. This routine never
; selects a bank, touches IE, writes scheduler budget, or requires a descriptor,
; so lifecycle code may call it safely inside an existing selected critical
; section. The host/direct descriptor proof uses the richer root below.
FullColorPhase5AuditCycleCheckpointSelected::
	push bc
	push de
	push hl
	ld c, a
	ld a, [wFullColorPhase5StressMode]
	cp FULL_COLOR_PHASE5_STRESS_MODE_ARMED
	jp nz, .invalid
	ld a, c
	cp FULL_COLOR_PHASE5_BOUNDARY_COMMITTING
	jr nc, .invalid
	call ReachFullColorPhase5BoundarySelected
	jr c, .deferred
	pop hl
	pop de
	pop bc
	and a
	ret
.deferred
	ld a, FULL_COLOR_PHASE5_TERMINAL_DEFERRED
	ld [wFullColorPhase5TraceResult], a
	call MarkFullColorPhase5TerminalBoundarySelected
	ld a, FULL_COLOR_PHASE5_TERMINAL_DEFERRED
	ld [wFullColorPhase5StressTerminalResult], a
	jr .failed
.invalid
	ld a, FULL_COLOR_PHASE5_TERMINAL_INVALID_CONTROL
	ld [wFullColorPhase5StressTerminalResult], a
.failed
	pop hl
	pop de
	pop bc
	scf
	ret

; Banked callers pass one-byte arguments in C because the farcall trampoline
; consumes A. These tail bridges restore the selected-call ABIs without adding
; another bank transition or changing the preserved caller register frame.
FullColorPhase5BeginRendererHandoffFromCSelected::
	ld a, c
	jp BeginRendererHandoff

FullColorPhase5StressCheckpointSelected::
	select_renderer_state_e
	call RunFullColorPhase5StressCheckpointSelected
	ld b, a
	restore_renderer_state_e
	ld a, b
	cp FULL_COLOR_PHASE5_TERMINAL_COMPLETE
	ret z
	scf
	ret

RunFullColorPhase5StressCheckpointSelected:
	ld a, [wFullColorPhase5StressMode]
	cp FULL_COLOR_PHASE5_STRESS_MODE_ARMED
	jp nz, FullColorPhase5InvalidControlSelected
	ld a, [wFullColorPhase5StressTargetBoundary]
	cp FULL_COLOR_PHASE5_BOUNDARY_COMMITTING
	jp nc, FullColorPhase5InvalidControlSelected
	xor a
	ld [wFullColorPhase5StressTerminalResult], a

	call FindFullColorPhase5PreparedDescriptorSelected
	jr nc, .have_prepared
	call PrepareNextFullColorRequestSelected
	jp c, FullColorPhase5InvalidControlSelected
	call FindFullColorPhase5PreparedDescriptorSelected
	jp c, FullColorPhase5InvalidControlSelected
.have_prepared
	ld a, l
	ld [wFullColorActiveDescriptor], a
	ld a, h
	ld [wFullColorActiveDescriptor + 1], a

	ld a, [wFullColorPhase5StressRequestClass]
	cp FULL_COLOR_PHASE5_REQUEST_CLASS_ANY
	jr z, .class_selected
	ld b, a
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp b
	jp nz, FullColorPhase5FilteredSelected
.class_selected

	call FullColorPhase5BoundaryPreparation
	jp c, FullColorPhase5BoundaryFailureSelected
	call FullColorPhase5BoundaryOwnerRevalidation
	jp c, FullColorPhase5BoundaryFailureSelected
	call FullColorPhase5BoundaryGenerationRevalidation
	jp c, FullColorPhase5BoundaryFailureSelected
	call FullColorPhase5BoundaryDestinationRevalidation
	jp c, FullColorPhase5BoundaryFailureSelected
	call FullColorPhase5BoundaryBudgetRevalidation
	jp c, FullColorPhase5BoundaryFailureSelected

	; Reservation succeeded. No mutation or pressure hook is permitted after this
	; transition; the complete visible unit must retire in this invocation.
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	ld b, a
	ld a, COMMITTING << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	or b
	ld [hl], a
	ld a, COMMITTING
	push hl
	call RecordFullColorTransitionSelected
	pop hl
	call FullColorPhase5BoundaryCommitting
	call CommitFullColorVisibleUnitSelected
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	ld b, a
	ld a, COMPLETE << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	or b
	ld [hl], a
	ld a, COMPLETE
	call RecordFullColorTransitionSelected
	ld hl, wFullColorRequestCount
	dec [hl]
	call AdvanceFullColorRequestCursorSelected
	call PublishFullColorSchedulerDebugSelected
	ld a, FULL_COLOR_PHASE5_TERMINAL_COMPLETE
	ld [wFullColorPhase5StressTerminalResult], a
	ret

; Output HL=the singleton PREPARED descriptor, carry clear. Carry set means
; none exists. The scan begins at the scheduler cursor to preserve FIFO.
FindFullColorPhase5PreparedDescriptorSelected:
	call LoadFullColorCursorDescriptorSelected
	ld b, FULL_COLOR_REQUEST_CAPACITY
.next
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_STATE_MASK
	cp PREPARED << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr z, .found
	call AdvanceFullColorDescriptorPointerSelected
	dec b
	jr nz, .next
	scf
	ret
.found
	and a
	ret

FullColorPhase5BoundaryPreparation::
	ld a, FULL_COLOR_PHASE5_BOUNDARY_PREPARATION
	call ReachFullColorPhase5BoundarySelected
	jp c, FullColorPhase5TraceDeferredSelected
	ld a, [FullColorPhase5MutationPreparation]
	and a
	jp nz, FullColorPhase5TraceCancelledSelected
	jp TraceFullColorPhase5PassedSelected

FullColorPhase5BoundaryOwnerRevalidation::
	ld a, FULL_COLOR_PHASE5_BOUNDARY_OWNER_REVALIDATION
	call ReachFullColorPhase5BoundarySelected
	jp c, FullColorPhase5TraceDeferredSelected
	ld a, [FullColorPhase5MutationOwner]
	and a
	jp nz, FullColorPhase5TraceCancelledSelected
	ld a, [wRendererOwner]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jp nz, FullColorPhase5TraceCancelledSelected
	push hl
	inc hl
	ld a, [hl]
	pop hl
	cp RENDERER_FULL_COLOR_OVERWORLD
	jp nz, FullColorPhase5TraceCancelledSelected
	jp TraceFullColorPhase5PassedSelected

FullColorPhase5BoundaryGenerationRevalidation::
	ld a, FULL_COLOR_PHASE5_BOUNDARY_GENERATION_REVALIDATION
	call ReachFullColorPhase5BoundarySelected
	jp c, FullColorPhase5TraceDeferredSelected
	ld a, [FullColorPhase5MutationGeneration]
	and a
	jp nz, FullColorPhase5TraceCancelledSelected
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_GENERATION
	add hl, de
	ld de, wRendererGeneration
	ld b, 4
.generation
	ld a, [de]
	cp [hl]
	jr nz, .stale
	inc de
	inc hl
	dec b
	jr nz, .generation
	pop hl
	jp TraceFullColorPhase5PassedSelected
.stale
	pop hl
	jr FullColorPhase5TraceCancelledSelected

FullColorPhase5BoundaryDestinationRevalidation::
	ld a, FULL_COLOR_PHASE5_BOUNDARY_DESTINATION_REVALIDATION
	call ReachFullColorPhase5BoundarySelected
	jp c, FullColorPhase5TraceDeferredSelected
	ld a, [FullColorPhase5MutationDestination]
	and a
	jr nz, FullColorPhase5TraceCancelledSelected
	push hl
	ld d, h
	ld e, l
	call ValidateFullColorRequestResourcesSelected
	pop hl
	jr c, FullColorPhase5TraceCancelledSelected
	jp TraceFullColorPhase5PassedSelected

FullColorPhase5BoundaryBudgetRevalidation::
	ld a, FULL_COLOR_PHASE5_BOUNDARY_BUDGET_REVALIDATION
	call ReachFullColorPhase5BoundarySelected
	jp c, FullColorPhase5TraceDeferredSelected
	ld a, [FullColorPhase5MutationResources]
	and a
	jr nz, FullColorPhase5TraceDeferredSelected
	; Required resources must remain a subset of current availability.
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_RESOURCE_MASK
	add hl, de
	ld a, [hli]
	ld c, a
	ld a, [wFullColorAvailableResources]
	and c
	cp c
	jr nz, .defer_pop
	ld a, [hl]
	ld c, a
	ld a, [wFullColorAvailableResources + 1]
	and c
	cp c
	jr nz, .defer_pop
	pop hl
	ld a, [FullColorPhase5MutationBudget]
	and a
	jr nz, FullColorPhase5TraceDeferredSelected
	jp TraceFullColorPhase5PassedSelected
.defer_pop
	pop hl
	jr FullColorPhase5TraceDeferredSelected

FullColorPhase5BoundaryCommitting::
	ld a, FULL_COLOR_PHASE5_BOUNDARY_COMMITTING
	call ReachFullColorPhase5BoundarySelected
	ld c, FULL_COLOR_PHASE5_VALIDATION_OBSERVED
	ld d, FULL_COLOR_PHASE5_TERMINAL_NONE
	ld a, FULL_COLOR_PHASE5_BOUNDARY_COMMITTING
	jp AppendFullColorPhase5TraceSelected

TraceFullColorPhase5PassedSelected:
	ld c, FULL_COLOR_PHASE5_VALIDATION_PASSED
	ld d, FULL_COLOR_PHASE5_TERMINAL_NONE
	call LoadLastFullColorPhase5BoundarySelected
	call AppendFullColorPhase5TraceSelected
	and a
	ret

FullColorPhase5TraceCancelledSelected:
	ld c, FULL_COLOR_PHASE5_VALIDATION_CANCELLED
	ld d, FULL_COLOR_PHASE5_TERMINAL_CANCELLED
	call LoadLastFullColorPhase5BoundarySelected
	call AppendFullColorPhase5TraceSelected
	scf
	ret

FullColorPhase5TraceDeferredSelected:
	ld c, FULL_COLOR_PHASE5_VALIDATION_DEFERRED
	ld d, FULL_COLOR_PHASE5_TERMINAL_DEFERRED
	call LoadLastFullColorPhase5BoundarySelected
	call AppendFullColorPhase5TraceSelected
	scf
	ret

; A=boundary, HL=descriptor. Mark it reached and compare the independent
; audit-cycle authority only at the selected mutable boundary. Descriptor
; reservation and wFullColorCommitBudget are write-count scheduler contracts,
; never cycle budgets. Carry means required cycles exceed available cycles.
ReachFullColorPhase5BoundarySelected:
	ld [wFullColorPhase5TraceBoundary], a
	push hl
	push bc
	ld c, a
	ld b, 0
	ld hl, FullColorPhase5BoundaryBits
	add hl, bc
	ld a, [wFullColorPhase5StressReachedMask]
	or [hl]
	ld [wFullColorPhase5StressReachedMask], a
	ld a, [wFullColorPhase5StressTargetBoundary]
	cp c
	jr nz, .done
	ld a, [wFullColorPhase5StressAvailableCycles + 1]
	ld c, a
	ld a, [wFullColorPhase5StressRequiredCycles + 1]
	cp c
	jr c, .done
	jr nz, .insufficient
	ld a, [wFullColorPhase5StressAvailableCycles]
	ld c, a
	ld a, [wFullColorPhase5StressRequiredCycles]
	cp c
	jr z, .done
	jr c, .done
.insufficient
	pop bc
	pop hl
	scf
	ret
.done
	pop bc
	pop hl
	and a
	ret

LoadLastFullColorPhase5BoundarySelected:
	ld a, [wFullColorPhase5TraceBoundary]
	ret

FullColorPhase5CancelSelected:
	call MarkFullColorPhase5TerminalBoundarySelected
	ld a, FULL_COLOR_PHASE5_TERMINAL_CANCELLED
	ld [wFullColorPhase5StressTerminalResult], a
	call CancelFullColorDescriptorStaleSelected
	ld a, FULL_COLOR_PHASE5_TERMINAL_CANCELLED
	scf
	ret

; Each mutable boundary records whether its failure is an identity cancellation
; or resource/cycle deferral before returning carry. Route by that bounded trace
; result so audit cycle pressure defers at whichever boundary the host selected.
FullColorPhase5BoundaryFailureSelected:
	ld a, [wFullColorPhase5TraceResult]
	cp FULL_COLOR_PHASE5_TERMINAL_DEFERRED
	jp z, FullColorPhase5DeferSelected
	jp FullColorPhase5CancelSelected

FullColorPhase5DeferSelected:
	call MarkFullColorPhase5TerminalBoundarySelected
	ld a, FULL_COLOR_PHASE5_TERMINAL_DEFERRED
	ld [wFullColorPhase5StressTerminalResult], a
	scf
	ret

; OR the selected mutation checkpoint into the appropriate terminal mask.
; The caller's A is irrelevant; the terminal result chooses the destination.
MarkFullColorPhase5TerminalBoundarySelected:
	push hl
	push bc
	ld a, [wFullColorPhase5StressTargetBoundary]
	ld c, a
	ld b, 0
	ld hl, FullColorPhase5BoundaryBits
	add hl, bc
	ld a, [wFullColorPhase5TraceResult]
	cp FULL_COLOR_PHASE5_TERMINAL_CANCELLED
	jr z, .cancelled
	ld a, [wFullColorPhase5StressDeferredMask]
	or [hl]
	ld [wFullColorPhase5StressDeferredMask], a
	jr .done
.cancelled
	ld a, [wFullColorPhase5StressCancelledMask]
	or [hl]
	ld [wFullColorPhase5StressCancelledMask], a
.done
	pop bc
	pop hl
	ret

FullColorPhase5FilteredSelected:
	ld a, FULL_COLOR_PHASE5_TERMINAL_FILTERED
	ld [wFullColorPhase5StressTerminalResult], a
	scf
	ret

FullColorPhase5InvalidControlSelected:
	ld a, FULL_COLOR_PHASE5_TERMINAL_INVALID_CONTROL
	ld [wFullColorPhase5StressTerminalResult], a
	scf
	ret

; A=boundary, C=validation, D=result, HL=active descriptor. Layout (24 bytes):
; boundary/state/class/validation/result, active+declared owner, active+declared
; generation, destination, audit available+required cycles, required resources,
; request count, transition count.
AppendFullColorPhase5TraceSelected:
	ld [wFullColorPhase5TraceBoundary], a
	ld a, c
	ld [wFullColorPhase5TraceValidation], a
	ld a, d
	ld [wFullColorPhase5TraceResult], a
	push hl

	ld a, [wFullColorDebugTraceWritePhase2]
	cp FULL_COLOR_DEBUG_TRACE_CAPACITY_PHASE2
	jr c, .write_index_ok
	xor a
.write_index_ok
	ld c, a
	ld b, 0
	ld hl, wFullColorDebugTracePhase2
	ld de, FULL_COLOR_DEBUG_TRACE_RECORD_BYTES
.seek
	ld a, c
	and a
	jr z, .record
	add hl, de
	dec c
	jr .seek
.record
	ld d, h
	ld e, l
	pop hl

	ld a, [wFullColorPhase5TraceBoundary]
	ld [de], a
	inc de
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_STATE_MASK
	swap a
	ld [de], a
	inc de
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	ld [de], a
	inc de
	ld a, [wFullColorPhase5TraceValidation]
	ld [de], a
	inc de
	ld a, [wFullColorPhase5TraceResult]
	ld [de], a
	inc de
	ld a, [wRendererOwner]
	ld [de], a
	inc de
	inc hl
	ld a, [hli]
	ld [de], a
	inc de

	ld a, [wRendererGeneration]
	ld [de], a
	inc de
	ld a, [wRendererGeneration + 1]
	ld [de], a
	inc de
	ld a, [wRendererGeneration + 2]
	ld [de], a
	inc de
	ld a, [wRendererGeneration + 3]
	ld [de], a
	inc de
	REPT 4
		ld a, [hli]
		ld [de], a
		inc de
	ENDR
	REPT 2
		ld a, [hli]
		ld [de], a
		inc de
	ENDR
	ld a, [wFullColorPhase5StressAvailableCycles]
	ld [de], a
	inc de
	ld a, [wFullColorPhase5StressAvailableCycles + 1]
	ld [de], a
	inc de
	ld a, [wFullColorPhase5StressRequiredCycles]
	ld [de], a
	inc de
	ld a, [wFullColorPhase5StressRequiredCycles + 1]
	ld [de], a
	inc de
	; Resource low byte is enough: every current resource lies in bits 0..5.
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	ld bc, FULL_COLOR_DESCRIPTOR_RESOURCE_MASK
	add hl, bc
	ld a, [hl]
	ld [de], a
	inc de
	ld a, [wFullColorRequestCount]
	ld [de], a
	inc de
	ld a, [wFullColorTransitionCount]
	ld [de], a

	ld hl, wFullColorDebugTraceWritePhase2
	inc [hl]
	ld a, [hl]
	cp FULL_COLOR_DEBUG_TRACE_CAPACITY_PHASE2
	jr c, .count
	xor a
	ld [hl], a
.count
	ld hl, wFullColorDebugTraceCountPhase2
	ld a, [hl]
	cp FULL_COLOR_DEBUG_TRACE_CAPACITY_PHASE2
	jr nc, .restore_descriptor
	inc [hl]

.restore_descriptor
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	ret

FullColorPhase5BoundaryBits:
	db 1 << FULL_COLOR_PHASE5_BOUNDARY_PREPARATION
	db 1 << FULL_COLOR_PHASE5_BOUNDARY_OWNER_REVALIDATION
	db 1 << FULL_COLOR_PHASE5_BOUNDARY_GENERATION_REVALIDATION
	db 1 << FULL_COLOR_PHASE5_BOUNDARY_DESTINATION_REVALIDATION
	db 1 << FULL_COLOR_PHASE5_BOUNDARY_BUDGET_REVALIDATION
	db 1 << FULL_COLOR_PHASE5_BOUNDARY_COMMITTING

; Patchable audit-ROM negatives. Clean builds contain zero; each nonzero byte
; forces its named checkpoint to reject before any presented write.
FullColorPhase5MutationPreparation:: db 0
FullColorPhase5MutationOwner:: db 0
FullColorPhase5MutationGeneration:: db 0
FullColorPhase5MutationDestination:: db 0
FullColorPhase5MutationResources:: db 0
FullColorPhase5MutationBudget:: db 0

; Raw ASCII bypasses the game's active text charmap so host linkage checks can
; reject the same literal marker in every production binary.
FullColorPhase5StressMagic::
	db $50, $35, $53, $54, $52, $45, $53, $53, $31 ; P5STRESS1

EXPORT FullColorPhase5StressCheckpointSelected
EXPORT FullColorPhase5StressReset
EXPORT FullColorPhase5AuditCycleCheckpointSelected
EXPORT FullColorPhase5BeginRendererHandoffFromCSelected
EXPORT FullColorPhase5AuditCycleCheckpointFromCSelected
EXPORT FullColorPhase5BoundaryPreparation
EXPORT FullColorPhase5BoundaryOwnerRevalidation
EXPORT FullColorPhase5BoundaryGenerationRevalidation
EXPORT FullColorPhase5BoundaryDestinationRevalidation
EXPORT FullColorPhase5BoundaryBudgetRevalidation
EXPORT FullColorPhase5BoundaryCommitting
EXPORT FullColorPhase5MutationPreparation, FullColorPhase5MutationOwner
EXPORT FullColorPhase5MutationGeneration, FullColorPhase5MutationDestination
EXPORT FullColorPhase5MutationResources, FullColorPhase5MutationBudget
EXPORT FullColorPhase5StressMagic

IF DEF(PHASE2_AUDIT)
	PUSHS
	SECTION "Full Color Phase 5 Fast Cache", ROMX
; Recompute the complete paired-unit extent and its two-plane reservation only
; from private producer width/height. The farcall ABI consumes HL, so rebuild
; the fixed descriptor destination here. Scheduler staging is deliberately
; excluded: fast commit writers reuse it after a unit
; has been retained for retry. Invalid geometry returns carry before writing any
; descriptor field, so a corrupted producer cannot become a partial request.
FullColorPhase5WriteProducerExtentSelected::
	ld a, [wFullColorProducerWidth]
	and a
	jr z, .invalid
	cp SCREEN_WIDTH + 1
	jr nc, .invalid
	ld e, a
	ld a, [wFullColorProducerHeight]
	and a
	jr z, .invalid
	cp SCREEN_HEIGHT + 1
	jr nc, .invalid
	ld d, a
	ld bc, 0
.multiply
	ld a, c
	add e
	ld c, a
	jr nc, .noCarry
	inc b
.noCarry
	dec d
	jr nz, .multiply
	ld d, b
	ld e, c
	sla c
	rl b
	jr c, .invalid
	ld hl, wFullColorSchedulerEnqueueDescriptor + FULL_COLOR_DESCRIPTOR_EXTENT
	ld a, e
	ld [hli], a
	ld a, d
	ld [hli], a
	ld a, c
	ld [hli], a
	ld a, b
	ld [hli], a
	and a
	ret
.invalid
	scf
	ret

; Retry may retire the certified outgoing movement row only after the actual
; map authority has advanced from the snapshotted Pallet frame to Route 1.
; This is semantic supersession, never generic capacity reclamation: every
; owner/generation/resource/snapshot byte, old destination, new geometry, and
; new destination is revalidated before recording CANCELLED.
RetireFullColorPhase5SupersededMovementSelected::
	ld a, [wFullColorProducerPending]
	and a
	ret z
	ld a, [wFullColorProducerClass]
	cp FULL_COLOR_REQUEST_MAP_CONNECTION_PAIRED
	ret nz
	ld a, [wFullColorProducerWidth]
	cp SCREEN_WIDTH
	ret nz
	ld a, [wFullColorProducerHeight]
	cp 2
	ret nz
	ld a, [wFullColorProducerFlags]
	and a
	ret nz
	; Stackless bank-1 peek: Retry has IE masked and WRAM2 selected.  Restore
	; WRAM2 before the first stack access or call.
	ld a, 1
	ldh [rSVBK], a
	ld a, [wCurMap]
	ld e, a
	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	ld a, e
	cp ROUTE_1
	ret nz
	ld a, [wFullColorAuthorityMap]
	cp PALLET_TOWN
	ret nz
	ld a, [wFullColorProducerDestination + 1]
	and $fc
	cp $98
	ret nz
	ld a, [wFullColorPhase5FastCacheValid]
	cp FULL_COLOR_PHASE5_FAST_CACHE_GENERIC
	ret nz
	ld a, [wFullColorPhase5FastCacheRequiredCycles]
	inc a
	ret nz
	ld a, [wFullColorPhase5FastCacheRequiredCycles + 1]
	inc a
	ret nz
	call LoadFullColorPhase5FastCacheDescriptorSelected
	ret c
	ld a, [hl]
	cp PREPARED << FULL_COLOR_DESCRIPTOR_STATE_SHIFT | FULL_COLOR_REQUEST_MAP_ROW_PAIRED
	ret nz
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_FLAGS
	add hl, de
	ld a, [hl]
	cp FULL_COLOR_FLAG_MOVEMENT_STRIP
	jr nz, .identityPop
	pop hl
	call ValidateFullColorPhase5FastCacheSelected
	ret c
	; Both descriptors are generation-bound to the live owner.  Their distinct
	; destinations prove that the Route 1 connection replaces, rather than
	; retries, the outgoing Pallet movement row.
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_DESTINATION
	add hl, de
	ld a, [hli]
	ld c, a
	ld a, [hl]
	ld b, a
	pop hl
	ld a, [wFullColorProducerDestination]
	cp c
	jr nz, .destinationDistinct
	ld a, [wFullColorProducerDestination + 1]
	cp b
	ret z
.destinationDistinct
	call CancelFullColorPhase5FastDescriptorSelected
	xor a
	ld [wFullColorPhase5FastCacheValid], a
	ret
.identityPop
	pop hl
	ret

; Mainline performs the generic preparation scan and freezes one exact non-OAM
; descriptor identity. The cache is an accelerator, never admission authority.
PrepareAndCacheNextFullColorPhase5Request::
	farcall PrepareNextFullColorRequest
	select_renderer_state_e
	call CacheFullColorPhase5PreparedNonOAMSelected
	restore_renderer_state_e
	and a
	ret

; Mark the fixed shadow authority changed before any writer starts.  All old
; OAM descriptor certificates are first poisoned with the complement of the
; current epoch, so an interrupt between invalidation and increment also fails
; closed and an 8-bit epoch wrap cannot revive an older terminal descriptor.
InvalidateFullColorPhase5OAMAuthority::
	select_renderer_state_e
	ld a, [wFullColorPhase5OAMAuthorityEpoch]
	cpl
	ld c, a
	ld hl, wFullColorRequestDescriptors
	ld b, FULL_COLOR_REQUEST_CAPACITY
.descriptor
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr nz, .next
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_RETRY_TOKEN
	add hl, de
	ld [hl], c
	pop hl
.next
	ld de, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	add hl, de
	dec b
	jr nz, .descriptor
	ld hl, wFullColorPhase5OAMAuthorityEpoch
	inc [hl]
	restore_renderer_state_e
	ret

CacheFullColorPhase5PreparedNonOAMSelected:
	ld a, [wFullColorPhase5FastCacheValid]
	and a
	ret nz
	ld hl, wFullColorRequestDescriptors
	ld b, FULL_COLOR_REQUEST_CAPACITY
.scan
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_STATE_MASK
	cp PREPARED << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr nz, .next
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr nz, .found
.next
	ld de, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	add hl, de
	dec b
	jr nz, .scan
	ret
.found
	ld a, l
	ld [wFullColorPhase5FastCacheDescriptor], a
	ld a, h
	ld [wFullColorPhase5FastCacheDescriptor + 1], a
	ld de, wFullColorPhase5FastCacheSnapshot
	ld b, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
.copy
	ld a, [hli]
	ld [de], a
	inc de
	dec b
	jr nz, .copy
	call DeriveFullColorPhase5FastCacheCyclesSelected
	jr FullColorPhase5CacheRequired

DeriveFullColorPhase5FastCacheCyclesSelected:
	ld a, [wFullColorPhase5FastCacheSnapshot]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD
	jr z, .palette
	cp FULL_COLOR_REQUEST_OBJ_PALETTE_PAYLOAD
	jr z, .palette
	cp FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT
	jr z, .animation
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_EXTENT + 1]
	and a
	jr nz, .too_large
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_EXTENT]
	ld l, a
	ld h, 0
	REPT 4
		add hl, hl
	ENDR
	ld b, h
	ld c, l
	REPT 2
		add hl, hl
	ENDR
	add hl, bc
	ld bc, FULL_COLOR_PHASE5_CYCLES_PAIRED_BASE
	add hl, bc
	ret
.palette
	ld hl, FULL_COLOR_PHASE5_CYCLES_PALETTE
	ret
.animation
	ld hl, FULL_COLOR_PHASE5_CYCLES_ANIMATION
	ret
.too_large
	ld hl, $ffff
	ret
FullColorPhase5CacheRequired:
	ld a, l
	ld [wFullColorPhase5FastCacheRequiredCycles], a
	ld a, h
	ld [wFullColorPhase5FastCacheRequiredCycles + 1], a
	ld a, FULL_COLOR_PHASE5_FAST_CACHE_GENERIC
	ld [wFullColorPhase5FastCacheValid], a
	ld a, [wFullColorPhase5FastCacheSnapshot]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED
	ret c
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	ret nc
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESIRED_STATE]
	cp SCREEN_WIDTH
	jr z, .row
	cp 2
	jr nz, .uncertified_paired
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESIRED_STATE + 1]
	cp SCREEN_HEIGHT
	jr nz, .uncertified_paired
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_EXTENT]
	cp 2 * SCREEN_HEIGHT
	jr nz, .uncertified_paired
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_EXTENT + 1]
	and a
	jr nz, .uncertified_paired
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION + 1]
	and $fc
	cp $98
	jr nz, .uncertified_paired
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION + 1]
	and 3
	jr z, .column_span_safe
	cp 1
	jr nz, .uncertified_paired
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION]
	cp $df
	jr nc, .uncertified_paired
.column_span_safe
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION]
	cp $ff
	jr z, .uncertified_paired
	ld a, FULL_COLOR_PHASE5_FAST_CACHE_COLUMN2X18
	ld [wFullColorPhase5FastCacheValid], a
	ret
.row
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESIRED_STATE + 1]
	cp 2
	jr nz, .uncertified_paired
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_EXTENT]
	cp SCREEN_WIDTH * 2
	jr nz, .uncertified_paired
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_EXTENT + 1]
	and a
	jr nz, .uncertified_paired
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION + 1]
	ld c, a
	and $fc
	add 3
	cp c
	jr nz, .row_certified
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION]
	cp $cd
	jr c, .row_certified
	cp $e0
	jr c, .uncertified_paired
	cp $ed
	jr nc, .uncertified_paired
.row_certified
	ld a, FULL_COLOR_PHASE5_FAST_CACHE_ROW20X2
	ld [wFullColorPhase5FastCacheValid], a
	ret
.uncertified_paired
	ld a, $ff
	ld [wFullColorPhase5FastCacheRequiredCycles], a
	ld [wFullColorPhase5FastCacheRequiredCycles + 1], a
	ret

; Audit VBlank fast path. Mainline has already selected the mandatory OAM slot
; as the cursor and cached at most one independently PREPARED non-OAM unit.
; Every live identity is revalidated immediately before COMMITTING.
RunFullColorPhase5CachedVBlank::
	select_renderer_state_e
	call RunFullColorPhase5CachedVBlankSelected
	restore_renderer_state_e
	ret

RunFullColorPhase5CachedVBlankSelected:
	ld a, LOW(FULL_COLOR_PHASE5_VBLANK_SCHEDULER_BUDGET - FULL_COLOR_PHASE5_CYCLES_FRAME_BASE)
	ld [wFullColorPhase5FrameAvailableCycles], a
	ld a, HIGH(FULL_COLOR_PHASE5_VBLANK_SCHEDULER_BUDGET - FULL_COLOR_PHASE5_CYCLES_FRAME_BASE)
	ld [wFullColorPhase5FrameAvailableCycles + 1], a
	xor a
	ld [wFullColorPhase5FrameRequiredCycles], a
	ld [wFullColorPhase5FrameRequiredCycles + 1], a
FullColorPhase5BeginBudgetEnd::
FullColorPhase5SchedulerPass1Start::
	call LoadFullColorPhase5CursorDescriptorSelected
	ld a, [hl]
	cp PREPARED << FULL_COLOR_DESCRIPTOR_STATE_SHIFT | FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr nz, .retainPriorOAM
	call ValidateFullColorPhase5FastOAMSelected
	jp c, FullColorPhase5FastFreshOAMFailed
	ld a, LOW(FULL_COLOR_PHASE5_CYCLES_OAM)
	ld [wFullColorPhase5FrameRequiredCycles], a
	ld a, HIGH(FULL_COLOR_PHASE5_CYCLES_OAM)
	ld [wFullColorPhase5FrameRequiredCycles + 1], a
	ld a, [wFullColorPhase5FrameAvailableCycles]
	sub LOW(FULL_COLOR_PHASE5_CYCLES_OAM)
	ld [wFullColorPhase5FrameAvailableCycles], a
	ld a, [wFullColorPhase5FrameAvailableCycles + 1]
	sbc HIGH(FULL_COLOR_PHASE5_CYCLES_OAM)
	jr c, FullColorPhase5FastOAMDeferred
	ld [wFullColorPhase5FrameAvailableCycles + 1], a
	call CommitFullColorPhase5FastDescriptorSelected
	jr FullColorPhase5SchedulerPass1End
.retainPriorOAM
	call ValidateFullColorPhase5RetainedOAMSelected
	jp c, FullColorPhase5FastRetainedOAMFailed
FullColorPhase5SchedulerPass1End::
FullColorPhase5SchedulerPass2Start::
	ld a, [wFullColorPhase5FastCacheValid]
	and a
	jr z, FullColorPhase5FastVBlankDone
	call LoadFullColorPhase5FastCacheDescriptorSelected
	jr c, FullColorPhase5FastCacheInvalid
	call ValidateFullColorPhase5FastCacheSelected
	jr c, FullColorPhase5FastCacheCancel
	ld a, [wFullColorPhase5FastCacheRequiredCycles + 1]
	ld b, a
	ld a, [wFullColorPhase5FrameAvailableCycles + 1]
	cp b
	jr c, FullColorPhase5FastVBlankDone
	jr nz, FullColorPhase5FastCacheBudgetOK
	ld a, [wFullColorPhase5FastCacheRequiredCycles]
	ld b, a
	ld a, [wFullColorPhase5FrameAvailableCycles]
	cp b
	jr c, FullColorPhase5FastVBlankDone
FullColorPhase5FastCacheBudgetOK:
	ld a, [wFullColorPhase5FastCacheRequiredCycles]
	ld [wFullColorPhase5FrameRequiredCycles], a
	ld b, a
	ld a, [wFullColorPhase5FrameAvailableCycles]
	sub b
	ld [wFullColorPhase5FrameAvailableCycles], a
	ld a, [wFullColorPhase5FastCacheRequiredCycles + 1]
	ld [wFullColorPhase5FrameRequiredCycles + 1], a
	ld b, a
	ld a, [wFullColorPhase5FrameAvailableCycles + 1]
	sbc b
	ld [wFullColorPhase5FrameAvailableCycles + 1], a
	call CommitFullColorPhase5FastDescriptorSelected
	jr c, FullColorPhase5FastVBlankDone
	xor a
	ld [wFullColorPhase5FastCacheValid], a
	jr FullColorPhase5FastVBlankDone
FullColorPhase5FastCacheCancel:
	call CancelFullColorPhase5FastDescriptorSelected
FullColorPhase5FastCacheInvalid:
	xor a
	ld [wFullColorPhase5FastCacheValid], a
	jr FullColorPhase5FastVBlankDone
FullColorPhase5FastFreshOAMFailed:
	call CancelFullColorPhase5FastDescriptorSelected
	call FailClosedFullColorPhase5RetainedOAMSelected
	jr FullColorPhase5FastVBlankDone
FullColorPhase5FastRetainedOAMFailed:
	call FailClosedFullColorPhase5RetainedOAMSelected
	jr FullColorPhase5FastVBlankDone
FullColorPhase5FastOAMDeferred:
	; Restore the subtraction on the impossible normal-path budget miss.
	ld a, LOW(FULL_COLOR_PHASE5_VBLANK_SCHEDULER_BUDGET - FULL_COLOR_PHASE5_CYCLES_FRAME_BASE)
	ld [wFullColorPhase5FrameAvailableCycles], a
	ld a, HIGH(FULL_COLOR_PHASE5_VBLANK_SCHEDULER_BUDGET - FULL_COLOR_PHASE5_CYCLES_FRAME_BASE)
	ld [wFullColorPhase5FrameAvailableCycles + 1], a
FullColorPhase5FastVBlankDone:
FullColorPhase5SchedulerPass2End::
	ret

LoadFullColorPhase5CursorDescriptorSelected:
	ld hl, wFullColorRequestDescriptors
	ld a, [wFullColorRequestCursor]
	and a
	ret z
	ld c, a
.offset
	ld de, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	add hl, de
	dec c
	jr nz, .offset
	ret

; HL must be the cursor's complete direct-wShadowOAM declaration.
ValidateFullColorPhase5FastOAMSelected:
	ld a, [hl]
	cp PREPARED << FULL_COLOR_DESCRIPTOR_STATE_SHIFT | FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr z, :+
	scf
	ret
:
	jp ValidateFullColorPhase5OAMIdentitySelected

; When no sprite authority changed since the previous presentation, hardware
; OAM may remain untouched while a frozen non-OAM unit drains.  The certificate
; is a COMPLETE exact OAM declaration whose retry byte equals the live epoch.
; Every other identity is revalidated by the same routine as a fresh batch.
ValidateFullColorPhase5RetainedOAMSelected:
	ld hl, wFullColorRequestDescriptors
	ld b, FULL_COLOR_REQUEST_CAPACITY
.scan
	ld a, [hl]
	cp COMPLETE << FULL_COLOR_DESCRIPTOR_STATE_SHIFT | FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr nz, .next
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_RETRY_TOKEN
	add hl, de
	ld a, [wFullColorPhase5OAMAuthorityEpoch]
	cp [hl]
	pop hl
	jr z, .found
.next
	ld de, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	add hl, de
	dec b
	jr nz, .scan
	scf
	ret
.found
	; fallthrough
ValidateFullColorPhase5OAMIdentitySelected:
	push hl
	inc hl
	ld a, [hli]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jr nz, .invalid_pop
	ld de, wRendererGeneration
	ld b, 4
.generation
	ld a, [de]
	cp [hl]
	jr nz, .invalid_pop
	inc de
	inc hl
	dec b
	jr nz, .generation
	ld a, [hli]
	and a
	jr nz, .invalid_pop
	ld a, [hli]
	cp HIGH(FULL_COLOR_OAM_DESTINATION)
	jr nz, .invalid_pop
	ld a, [hli]
	cp LOW(wShadowOAM)
	jr nz, .invalid_pop
	ld a, [hli]
	cp HIGH(wShadowOAM)
	jr nz, .invalid_pop
	ld a, [hli]
	or [hl]
	jr nz, .invalid_pop
	inc hl
	ld a, [hli]
	cp FULL_COLOR_RESOURCE_SHADOW_OAM | FULL_COLOR_RESOURCE_HARDWARE_OAM
	jr nz, .invalid_pop
	ld a, [hli]
	and a
	jr nz, .invalid_pop
	ld a, [hli]
	cp LOW(FULL_COLOR_OAM_EXTENT)
	jr nz, .invalid_pop
	ld a, [hli]
	cp HIGH(FULL_COLOR_OAM_EXTENT)
	jr nz, .invalid_pop
	ld a, [hli]
	cp LOW(FULL_COLOR_OAM_RESERVATION)
	jr nz, .invalid_pop
	ld a, [hli]
	cp HIGH(FULL_COLOR_OAM_RESERVATION)
	jr nz, .invalid_pop
	ld a, [hl]
	cp FULL_COLOR_FLAG_OAM_FINISHED
	jr nz, .invalid_pop
	ld a, [wRendererOwner]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jr nz, .invalid_pop
	ld a, [wFullColorAvailableResources]
	and FULL_COLOR_RESOURCE_SHADOW_OAM | FULL_COLOR_RESOURCE_HARDWARE_OAM
	cp FULL_COLOR_RESOURCE_SHADOW_OAM | FULL_COLOR_RESOURCE_HARDWARE_OAM
	jp nz, .resource_pop
	pop hl
	and a
	ret
.resource_pop
	pop hl
	scf
	ret
.invalid_pop
	pop hl
.invalid
	scf
	ret

; A changed or missing OAM authority certificate blocks every public write in
; this VBlank.  Cancel only the privately cached non-OAM unit after validating
; its pointer; never reinterpret the cursor's arbitrary descriptor as OAM.
FailClosedFullColorPhase5RetainedOAMSelected:
	ld a, [wFullColorPhase5ScenarioControl]
	and a
	jr z, .cache
	ld a, FULL_COLOR_PHASE5_SCENARIO_RESULT_FAILED
	ld [wFullColorPhase5ScenarioResult], a
	ld a, FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED
	ld [wFullColorPhase5ScenarioState], a
.cache
	ld a, [wFullColorPhase5FastCacheValid]
	and a
	jr z, .clear
	call LoadFullColorPhase5FastCacheDescriptorSelected
	jr c, .clear
	call CancelFullColorPhase5FastDescriptorSelected
.clear
	xor a
	ld [wFullColorPhase5FastCacheValid], a
	ret

; Validate the private pointer before dereferencing it. All eight descriptors
; occupy one WRAM2 page and are exactly 20 bytes apart.
LoadFullColorPhase5FastCacheDescriptorSelected:
	ld a, [wFullColorPhase5FastCacheDescriptor]
	ld l, a
	ld a, [wFullColorPhase5FastCacheDescriptor + 1]
	ld h, a
	cp HIGH(wFullColorRequestDescriptors)
	jp nz, .invalid
	ld a, l
	sub LOW(wFullColorRequestDescriptors)
	cp FULL_COLOR_REQUEST_CAPACITY * FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	jr nc, .invalid
.multiple
	and a
	ret z
	sub FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	jr nc, .multiple
.invalid
	scf
	ret

; Exact snapshot match excludes only the retry token, which is scheduler
; accounting rather than visible-unit identity. Live owner/generation and the
; currently available resources are then revalidated separately.
ValidateFullColorPhase5FastCacheSelected:
	push hl
	ld de, wFullColorPhase5FastCacheSnapshot
.bytes
	REPT FULL_COLOR_DESCRIPTOR_RETRY_TOKEN
		ld a, [de]
		cp [hl]
		jp nz, .invalid_pop
		inc de
		inc hl
	ENDR
	pop hl
	ld a, [wRendererOwner]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jp nz, .invalid
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_GENERATION
	add hl, de
	ld de, wRendererGeneration
	REPT 4
		ld a, [de]
		cp [hl]
		jp nz, .invalid_pop
		inc de
		inc hl
	ENDR
	pop hl
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_RESOURCE_MASK
	add hl, de
	ld a, [hli]
	ld c, a
	ld a, [wFullColorAvailableResources]
	and c
	cp c
	jp nz, .resource_pop
	ld a, [hl]
	ld c, a
	ld a, [wFullColorAvailableResources + 1]
	and c
	cp c
	jp nz, .resource_pop
	pop hl
	; Noncanonical paired work carries an exact impossible cycle certificate.
	; It remains PREPARED/deferred and can never enter the generic writer under
	; the canonical 5800-cycle authority.
	ld a, [wFullColorPhase5FastCacheValid]
	cp FULL_COLOR_PHASE5_FAST_CACHE_GENERIC
	jr z, .generic_kind
	cp FULL_COLOR_PHASE5_FAST_CACHE_ROW20X2
	jr z, .required_row
	cp FULL_COLOR_PHASE5_FAST_CACHE_COLUMN2X18
	jr z, .required_column
	jr .derive
.generic_kind
	ld a, [wFullColorPhase5FastCacheSnapshot]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED
	jr c, .derive
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr nc, .derive
	ld a, [wFullColorPhase5FastCacheRequiredCycles]
	inc a
	jp nz, .invalid
	ld a, [wFullColorPhase5FastCacheRequiredCycles + 1]
	inc a
	jp nz, .invalid
	jr .kind
.required_row
	ld bc, FULL_COLOR_PHASE5_CYCLES_PAIRED_BASE + SCREEN_WIDTH * 2 * FULL_COLOR_PHASE5_CYCLES_PAIRED_CELL
	jr .required_canonical
.required_column
	ld bc, FULL_COLOR_PHASE5_CYCLES_PAIRED_BASE + 2 * SCREEN_HEIGHT * FULL_COLOR_PHASE5_CYCLES_PAIRED_CELL
.required_canonical
	ld a, [wFullColorPhase5FastCacheRequiredCycles]
	cp c
	jp nz, .invalid
	ld a, [wFullColorPhase5FastCacheRequiredCycles + 1]
	cp b
	jp nz, .invalid
	jr .kind
.derive
	push hl
	call DeriveFullColorPhase5FastCacheCyclesSelected
	ld a, [wFullColorPhase5FastCacheRequiredCycles]
	cp l
	jp nz, .derived_invalid_pop
	ld a, [wFullColorPhase5FastCacheRequiredCycles + 1]
	cp h
	jp nz, .derived_invalid_pop
	pop hl
.kind
	ld a, [wFullColorPhase5FastCacheValid]
	cp FULL_COLOR_PHASE5_FAST_CACHE_GENERIC
	jp z, .valid
	; A mutable kind byte is never authority by itself. Rebind it to the exact
	; paired class, geometry, extent, and destination/wrap predicate that selected
	; the canonical writer in mainline.
	ld a, [wFullColorPhase5FastCacheSnapshot]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED
	jp c, .invalid
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jp nc, .invalid
	ld a, [wFullColorPhase5FastCacheValid]
	cp FULL_COLOR_PHASE5_FAST_CACHE_ROW20X2
	jr z, .validate_row_kind
	cp FULL_COLOR_PHASE5_FAST_CACHE_COLUMN2X18
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESIRED_STATE]
	cp 2
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESIRED_STATE + 1]
	cp SCREEN_HEIGHT
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_EXTENT]
	cp 2 * SCREEN_HEIGHT
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_EXTENT + 1]
	and a
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION + 1]
	and $fc
	cp $98
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION + 1]
	and 3
	jr z, .column_span_safe
	cp 1
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION]
	cp $df
	jr nc, .invalid
.column_span_safe
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION]
	cp $ff
	jr z, .invalid
	jr .valid
.validate_row_kind
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESIRED_STATE]
	cp SCREEN_WIDTH
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESIRED_STATE + 1]
	cp 2
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_EXTENT]
	cp SCREEN_WIDTH * 2
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_EXTENT + 1]
	and a
	jr nz, .invalid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION + 1]
	ld c, a
	and $fc
	add 3
	cp c
	jr nz, .valid
	ld a, [wFullColorPhase5FastCacheSnapshot + FULL_COLOR_DESCRIPTOR_DESTINATION]
	cp $cd
	jr c, .valid
	cp $e0
	jr c, .invalid
	cp $ed
	jr nc, .valid
	jr .invalid
.valid
	and a
	ret
.derived_invalid_pop
	pop hl
	scf
	ret
.resource_pop
	pop hl
	scf
	ret
.invalid_pop
	pop hl
.invalid
	scf
	ret

CommitFullColorPhase5FastDescriptorSelected:
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	ld b, a
	ld a, COMMITTING << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	or b
	ld [hl], a
	ld a, l
	ld [wFullColorActiveDescriptor], a
	ld a, h
	ld [wFullColorActiveDescriptor + 1], a
	; Preserve the live class and already revalidated canonical-kind certificate
	; across the transition recorder. The direct writer consumes it without repeating
	; the geometry/destination eligibility tree inside the physical window.
	ld a, [wFullColorPhase5FastCacheValid]
	ld c, a
	push bc
	ld a, COMMITTING
	call RecordFullColorPhase5FastTransitionSelected
	pop bc
	; Pass 1 shares this helper for mandatory OAM.  A non-OAM cache may coexist,
	; so its kind certificate is meaningful only for the paired live class.
	ld a, b
	cp FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED
	jr c, .generic_commit
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr nc, .generic_commit
	ld a, c
	cp FULL_COLOR_PHASE5_FAST_CACHE_ROW20X2
	jr z, .direct_paired
	cp FULL_COLOR_PHASE5_FAST_CACHE_COLUMN2X18
	jr nz, .generic_commit
.direct_paired
	call CommitFullColorPhase5PairedCanonicalTimedSelected
	jr FullColorPhase5PairedPublicComplete
.generic_commit
	farcall CommitFullColorPhase5ActiveDescriptorFar
.committed
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
.committed_hl
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	ld b, a
	ld a, COMPLETE << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	or b
	ld [hl], a
	ld a, COMPLETE
	call RecordFullColorPhase5FastTransitionSelected
	; Pressure accounting becomes terminal at the exact scheduler transition,
	; not at a later mainline scan that could already have admitted a new OAM
	; declaration for the next frame.
	ld a, b
	cp FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD
	jr z, .drained_palette
	cp FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT
	jr z, .drained_animation
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr nz, .drained_done
	ld c, FULL_COLOR_PHASE5_PRESSURE_OAM
	jr .record_drained
.drained_palette
	ld c, FULL_COLOR_PHASE5_PRESSURE_PALETTE
	jr .record_drained
.drained_animation
	ld c, FULL_COLOR_PHASE5_PRESSURE_ANIMATION
.record_drained
	ld hl, wFullColorPhase5PressureDrainedMask
	ld a, [hl]
	or c
	ld [hl], a
.drained_done
	ld de, wFullColorRequestCount
	ld a, [de]
	and a
	jr z, .count_done
	dec a
	ld [de], a
.count_done
	ld hl, wFullColorRequestCursor
	inc [hl]
	ld a, [hl]
	cp FULL_COLOR_REQUEST_CAPACITY
	jr c, .cursor_done
	xor a
	ld [hl], a
.cursor_done
	and a
	ret

FullColorPhase5PairedPublicComplete::
	; Public tile+attribute visibility is complete and cannot replay. Only the
	; non-public transition/accounting tail is deferred until after Home has
	; restored the caller ROM bank and crossed the measured owner-end seam.
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	ld b, a
	ld a, COMPLETE << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	or b
	ld [hl], a
	ld a, FULL_COLOR_PHASE5_FAST_CACHE_ACCOUNTING_PENDING
	ld [wFullColorPhase5FastCacheValid], a
	scf
	ret

; Called only by the Color branch after FullColorPhase5CombinedVBlankEnd. It
; performs no display/public write. A hostile pointer/state mutation clears the
; one-shot marker and fails the scenario closed, so a completed unit is never
; dispatched twice.
FinishFullColorPhase5DeferredAccounting::
	select_renderer_state_e
	call FinishFullColorPhase5DeferredAccountingSelected
	restore_renderer_state_e
	ret

FinishFullColorPhase5DeferredAccountingSelected:
FullColorPhase5DeferredAccountingStart::
	ld a, [wFullColorPhase5FastCacheValid]
	cp FULL_COLOR_PHASE5_FAST_CACHE_ACCOUNTING_PENDING
	ret nz
	call LoadFullColorPhase5FastCacheDescriptorSelected
	jr c, .invalid
	ld a, [wFullColorActiveDescriptor]
	cp l
	jr nz, .invalid
	ld a, [wFullColorActiveDescriptor + 1]
	cp h
	jr nz, .invalid
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_STATE_MASK
	cp COMPLETE << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr nz, .invalid
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_MAP_COLUMN_PAIRED
	jr c, .invalid
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr nc, .invalid
	ld a, COMPLETE
	call RecordFullColorPhase5FastTransitionSelected
	ld hl, wFullColorRequestCount
	ld a, [hl]
	and a
	jr z, .cursor
	dec [hl]
.cursor
	; The private pointer is exact; derive its resident slot and advance once.
	ld a, [wFullColorPhase5FastCacheDescriptor]
	sub LOW(wFullColorRequestDescriptors)
	ld b, 0
.index
	cp FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	jr c, .index_done
	sub FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	inc b
	jr .index
.index_done
	inc b
	ld a, b
	cp FULL_COLOR_REQUEST_CAPACITY
	jr c, .store_cursor
	xor a
.store_cursor
	ld [wFullColorRequestCursor], a
	xor a
	ld [wFullColorPhase5FastCacheValid], a
	ret
.invalid
	xor a
	ld [wFullColorPhase5FastCacheValid], a
	ld a, [wFullColorPhase5ScenarioControl]
	and a
	ret z
	ld a, FULL_COLOR_PHASE5_SCENARIO_RESULT_FAILED
	ld [wFullColorPhase5ScenarioResult], a
	ld a, FULL_COLOR_PHASE5_SCENARIO_STATE_FAILED
	ld [wFullColorPhase5ScenarioState], a
	ret

CancelFullColorPhase5FastDescriptorSelected:
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	ld b, a
	ld a, CANCELLED << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	or b
	ld [hl], a
	ld a, CANCELLED
	push hl
	call RecordFullColorPhase5FastTransitionSelected
	pop hl
	ld de, wFullColorRequestCount
	ld a, [de]
	and a
	ret z
	dec a
	ld [de], a
	ret

RecordFullColorPhase5FastTransitionSelected:
	ld c, a
	ld a, [wFullColorTransitionCount]
	cp 8
	jr nc, .count_only
	ld e, a
	ld d, 0
	ld hl, wFullColorTransitionLog
	add hl, de
	ld [hl], c
.count_only
	ld hl, wFullColorTransitionCount
	ld a, [hl]
	cp $ff
	ret z
	inc [hl]
	ret

PublishFullColorPhase5FastDebugSelected:
	ld a, [wFullColorRequestCount]
	ld [wFullColorTimingState], a
	ld a, [wFullColorRetryCounter]
	ld [wFullColorTimingState + 1], a
	ld a, [wFullColorLastAdmissionResult]
	ld [wFullColorTimingState + 2], a
	ld a, [wFullColorTransitionCount]
	ld [wFullColorTimingState + 3], a
	ret

; The first mainline observer publishes the completed interrupt state before
; retry or producer code can mutate it.  VBlank pays no diagnostic copy cost.
PublishFullColorPhase5FastDebug::
	select_renderer_state_e
	call PublishFullColorPhase5FastDebugSelected
	restore_renderer_state_e
	ret

; Exact BG palette publication fully unrolled. Every byte is still written
; through the hardware auto-increment port in declaration order; only the
; per-byte branch/count overhead is removed.
CommitFullColorPhase5BGPaletteFastSelected::
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	ld de, FULL_COLOR_DESCRIPTOR_FLAGS
	add hl, de
	bit 1, [hl]
	ld hl, wFullColorBGPaletteBase
	jr z, .source
	ld hl, wFullColorBGPaletteTransformed
.source
	ld a, $80
	ldh [rBGPI], a
	ld c, LOW(rBGPD)
	REPT 64
		ld a, [hli]
		ldh [c], a
	ENDR
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	ret

; Exact local publishers for validated Phase 5 movement/connection strips.
; They avoid the audit->lifecycle->generic->audit bank carousel and load only
; the live destination plus the two immutable frozen plane sources.
CommitFullColorPhase5PairedCanonicalTimedSelected:
	ld b, a
	; The COMMITTING transition recorder clobbers HL. Reload the exact resident
	; descriptor selected immediately above; never reinterpret trace storage as
	; a destination-bearing descriptor.
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	push hl
FullColorPhase5VerticalStart::
	ld a, b
	cp FULL_COLOR_PHASE5_FAST_CACHE_ROW20X2
	jr z, .row
	call CommitFullColorPhase5Paired2x18Selected
	jr .done
.row
	call CommitFullColorPhase5Paired20x2Selected
.done
	pop hl
FullColorPhase5VerticalEnd::
	ret

CommitFullColorPhase5Paired20x2Selected:
	ld de, FULL_COLOR_DESCRIPTOR_DESTINATION
	add hl, de
	ld a, [hli]
	ld h, [hl]
	ld l, a
	push hl
	ld a, h
	and $fc
	ld b, a
	ldh a, [rVBK]
	ld c, a
	ld de, wFullColorAttributeRectangle
	xor a
	ldh [rVBK], a
FullColorPhase5Paired20x2WritesStart::
	REPT SCREEN_WIDTH
		ld a, [de]
		inc de
		ld [hli], a
	ENDR
	ld a, l
	add TILEMAP_WIDTH - SCREEN_WIDTH
	ld l, a
	jr nc, :+
	inc h
:
	ld a, b
	add 4
	cp h
	jr nz, :+
	ld h, b
:
	REPT SCREEN_WIDTH
		ld a, [de]
		inc de
		ld [hli], a
	ENDR
	ld a, 1
	ldh [rVBK], a
	ld de, wFullColorBGPaletteBase
	pop hl
	REPT SCREEN_WIDTH
		ld a, [de]
		inc de
		ld [hli], a
	ENDR
	ld a, l
	add TILEMAP_WIDTH - SCREEN_WIDTH
	ld l, a
	jr nc, :+
	inc h
:
	ld a, b
	add 4
	cp h
	jr nz, :+
	ld h, b
:
	REPT SCREEN_WIDTH
		ld a, [de]
		inc de
		ld [hli], a
	ENDR
FullColorPhase5Paired20x2WritesEnd::
	ld a, c
	ldh [rVBK], a
	ret

CommitFullColorPhase5Paired2x18Selected:
	ld de, FULL_COLOR_DESCRIPTOR_DESTINATION
	add hl, de
	ld a, [hli]
	ld h, [hl]
	ld l, a
	push hl
	ldh a, [rVBK]
	ld [wFullColorTimingState + 3], a
	ld de, wFullColorAttributeRectangle
	ld bc, TILEMAP_WIDTH - 2
	xor a
	ldh [rVBK], a
FullColorPhase5Paired2x18WritesStart::
	REPT SCREEN_HEIGHT - 1
		REPT 2
			ld a, [de]
			inc de
			ld [hli], a
		ENDR
		add hl, bc
	ENDR
	REPT 2
		ld a, [de]
		inc de
		ld [hli], a
	ENDR
	ld a, 1
	ldh [rVBK], a
	ld de, wFullColorBGPaletteBase
	pop hl
	REPT SCREEN_HEIGHT - 1
		REPT 2
			ld a, [de]
			inc de
			ld [hli], a
		ENDR
		add hl, bc
	ENDR
	REPT 2
		ld a, [de]
		inc de
		ld [hli], a
	ENDR
FullColorPhase5Paired2x18WritesEnd::
	ld a, [wFullColorTimingState + 3]
	ldh [rVBK], a
	ret

; Added-only paired publication fast path. The fixed-window bridge stores the
; exact descriptor pointer before Bankswitch consumes HL; this routine rebuilds
; every operand from that selected WRAM2 authority. Tile and attribute planes
; are still complete and ordered before return, with no partial-unit exit.
CommitFullColorPhase5PairedTransferFastSelected::
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_DESIRED_STATE
	add hl, de
	ld a, [hli]
	ld [wFullColorRequestStaging], a ; width
	ld a, [hl]
	ld [wFullColorRequestStaging + 1], a ; height
	pop hl
	ld de, FULL_COLOR_DESCRIPTOR_DESTINATION
	add hl, de
	ld a, [hli]
	ld h, [hl]
	ld l, a
	ld a, l
	ld [wFullColorRequestStaging + 3], a
	ld a, h
	ld [wFullColorRequestStaging + 4], a
	ld a, h
	and $fc
	ld [wFullColorTimingState], a ; selected map base high
	ldh a, [rVBK]
	ld [wFullColorTimingState + 1], a
	; Phase 5 movement and connection rows are exactly 20x2.  Their frozen
	; tile and attribute planes are contiguous, so select each source once and
	; resolve the 32-byte map stride only at row boundaries.  The general path
	; retains per-cell 1 KiB wrapping for every other or boundary-crossing
	; geometry.
	ld a, [wFullColorRequestStaging]
	cp SCREEN_WIDTH
	jp nz, FullColorPhase5PairedGeneralSelected
	ld a, [wFullColorRequestStaging + 1]
	cp 2
	jp nz, FullColorPhase5PairedGeneralSelected
	ld a, [wFullColorTimingState]
	add 3
	cp h
	jp z, FullColorPhase5PairedGeneralSelected
	ld de, wFullColorAttributeRectangle
	xor a
	ldh [rVBK], a

FullColorPhase5PairedRow20WritesStart::
	REPT SCREEN_WIDTH
		ld a, [de]
		inc de
		ld [hli], a
	ENDR
	ld a, l
	add TILEMAP_WIDTH - SCREEN_WIDTH
	ld l, a
	jr nc, :+
	inc h
:
	REPT SCREEN_WIDTH
		ld a, [de]
		inc de
		ld [hli], a
	ENDR
	ld a, 1
	ldh [rVBK], a
	ld de, wFullColorBGPaletteBase
	ld a, [wFullColorRequestStaging + 3]
	ld l, a
	ld a, [wFullColorRequestStaging + 4]
	ld h, a
	REPT SCREEN_WIDTH
		ld a, [de]
		inc de
		ld [hli], a
	ENDR
	ld a, l
	add TILEMAP_WIDTH - SCREEN_WIDTH
	ld l, a
	jr nc, :+
	inc h
:
	REPT SCREEN_WIDTH
		ld a, [de]
		inc de
		ld [hli], a
	ENDR
FullColorPhase5PairedRow20WritesEnd::
	ld a, [wFullColorTimingState + 1]
	ldh [rVBK], a
	ret

FullColorPhase5PairedGeneralSelected:
	ld de, wFullColorAttributeRectangle
	xor a
	ld [wFullColorRequestStaging + 2], a
	xor a
	ldh [rVBK], a
	call CommitFullColorPhase5MapPlaneSelected
	ld a, 1
	ldh [rVBK], a
	ld de, wFullColorBGPaletteBase
	ld [wFullColorRequestStaging + 2], a
	call LoadFullColorPhase5ActiveMapDestinationSelected
	call CommitFullColorPhase5MapPlaneSelected
	ld a, [wFullColorTimingState + 1]
	ldh [rVBK], a
	ret

LoadFullColorPhase5ActiveMapDestinationSelected:
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	ld bc, FULL_COLOR_DESCRIPTOR_DESTINATION
	add hl, bc
	ld a, [hli]
	ld h, [hl]
	ld l, a
	ret

; DE packed source, HL first destination. Width/height are in staging. The
; exact 20x2 Phase 5 path above never enters this general wrap-safe writer.
CommitFullColorPhase5MapPlaneSelected:
	ld a, l
	ld [wFullColorRequestStaging + 3], a
	ld a, h
	ld [wFullColorRequestStaging + 4], a
	ld a, [wFullColorRequestStaging + 1]
	ld c, a
.row
	ld a, [wFullColorRequestStaging + 3]
	ld l, a
	ld a, [wFullColorRequestStaging + 4]
	ld h, a
	ld a, [wFullColorRequestStaging]
	ld b, a
.cell
	ld a, [wFullColorRequestStaging + 2]
	and a
	jr z, .load
	ld a, d
	cp HIGH(wFullColorAttributeRectangle)
	jr nz, .load
	ld a, e
	cp LOW(wFullColorAttributeRectangle)
	jr nz, .load
	ld de, wFullColorShadowOAMBatch
.load
FullColorPhase5PairedMapWrite::
	ld a, [de]
	ld [hl], a
	inc de
	; Preserve the exact 1 KiB BG-map wrap without a per-cell call/return.
	inc hl
	ld a, [wFullColorTimingState]
	add 4
	cp h
	jr nz, .cellAdvanced
	ld a, [wFullColorTimingState]
	ld h, a
.cellAdvanced
	dec b
	jr nz, CommitFullColorPhase5MapPlaneSelected.cell
	ld a, [wFullColorRequestStaging + 3]
	ld l, a
	ld a, [wFullColorRequestStaging + 4]
	ld h, a
	ld a, l
	add 32
	ld l, a
	jr nc, .rowRange
	inc h
.rowRange
	ld a, [wFullColorTimingState]
	add 4
	cp h
	jr nz, .rowAdvanced
	ld a, [wFullColorTimingState]
	ld h, a
.rowAdvanced
	ld a, l
	ld [wFullColorRequestStaging + 3], a
	ld a, h
	ld [wFullColorRequestStaging + 4], a
	dec c
	jr nz, CommitFullColorPhase5MapPlaneSelected.row
	ret
	POPS
ENDC

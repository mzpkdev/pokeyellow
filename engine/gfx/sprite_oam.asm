PrepareOAMData::
; Determine OAM data for currently visible
; sprites and write it to wShadowOAM.
; Yellow code has been changed to use registers more efficiently
; as well as tweaking the code to show cgb palettes

IF DEF(PHASE2_AUDIT)
.build
ENDC
	ld a, [wUpdateSpritesEnabled]
	dec a
	jr z, .updateEnabled

	cp -1
	ret nz
	ld [wUpdateSpritesEnabled], a
	jp HideSprites

.updateEnabled
	xor a
	ldh [hOAMBufferOffset], a

.spriteLoop
	ldh [hSpriteOffset2], a

	ld e, a
	ld d, HIGH(wSpriteStateData1)

	ld a, [de] ; [x#SPRITESTATEDATA1_PICTUREID]
	and a
	jp z, .nextSprite

	inc e
	inc e
	ld a, [de] ; [x#SPRITESTATEDATA1_IMAGEINDEX]
	ld [wSavedSpriteImageIndex], a
	cp $ff ; off-screen (don't draw)
	jr nz, .visible

	call GetSpriteScreenXY
IF DEF(PHASE2_AUDIT)
	jp .nextSprite
ELSE
	jr .nextSprite
ENDC

.visible
	cp $a0 ; is the sprite unchanging like an item ball or boulder?
	jr c, .usefacing

; unchanging
	ld a, $0
	jr .next

.usefacing
	and $f

.next
; read the entry from the table
	ld c, a
	ld b, 0
	ld hl, SpriteFacingAndAnimationTable
	add hl, bc
	add hl, bc
	ld a, [hli]
	ld h, [hl]
	ld l, a
; get sprite priority
	push de
	inc d
	ld a, e
	add $5
	ld e, a
	ld a, [de] ; [x#SPRITESTATEDATA2_GRASSPRIORITY]
	and $80
IF DEF(PHASE2_AUDIT)
	push af
	ldh a, [hSpritePriority]
	and 1
	ld b, a
	pop af
	or b
ENDC
	ldh [hSpritePriority], a ; temp store sprite priority
	pop de


	call GetSpriteScreenXY

	ldh a, [hOAMBufferOffset]
	add [hl]
	cp $a0
	jr z, .hidden
	jr nc, .asm_4a41
.hidden
	call Func_4a7b
	ld [wSavedSpriteImageIndex], a
	ldh a, [hOAMBufferOffset]

	ld e, a
	ld d, HIGH(wShadowOAM)

.tileLoop
	ld a, [hli]
	ld c, a
.loop
	ldh a, [hSpriteScreenY]   ; temp for sprite Y position
	add $10                  ; Y=16 is top of screen (Y=0 is invisible)
	add [hl]                 ; add Y offset from table
	ld [de], a               ; write new sprite OAM Y position
	inc hl
	inc e
	ldh a, [hSpriteScreenX]   ; temp for sprite X position
	add $8                   ; X=8 is left of screen (X=0 is invisible)
	add [hl]                 ; add X offset from table
	ld [de], a
	inc hl
	inc e
	ld a, [wSavedSpriteImageIndex]
	add [hl]
	cp $80
	jr c, .asm_4a1c
	ld b, a
	ldh a, [hPikachuSpriteVRAMOffset]
	add b
.asm_4a1c
	ld [de], a ; tile id
	inc hl
	inc e
	ld a, [hl]
	bit BIT_SPRITE_UNDER_GRASS, a
	jr z, .skipPriority
	ldh a, [hSpritePriority]
IF DEF(PHASE2_AUDIT)
	and $80
ENDC
	or [hl]
.skipPriority
	and $f0
	bit B_OAM_PAL1, a
	jr z, .spriteusesOBP0
	or OAM_HIGH_PALS
.spriteusesOBP0
	ld [de], a
IF DEF(PHASE2_AUDIT)
	; Identity is retained beside the sprite state by LoadMapSpritesImageBaseOffset.
	; Map only after the final tile and Pikachu offset have been selected, while
	; preserving the producer's control bits and every live loop register.
	ldh a, [hSpritePriority]
	bit 0, a
	jr z, :+
	push bc
	push de
	push hl
	ldh a, [hSpriteOffset2]
	add LOW(wSpritePlayerStateData2PictureID)
	ld l, a
	ld h, HIGH(wSpritePlayerStateData2PictureID)
	ld c, [hl]
	farcall MapFullColorOAMAttributeFar
	pop hl
	pop de
	pop bc
:
ENDC
	inc hl
	inc e
	dec c
	jr nz, .loop

	ld a, e
	ldh [hOAMBufferOffset], a
.nextSprite
	ldh a, [hSpriteOffset2]
	add $10
	cp LOW($100)
	jp nz, .spriteLoop

	; Clear unused OAM.
.asm_4a41
	ld a, [wMovementFlags]
	bit BIT_LEDGE_OR_FISHING, a
	ld c, LOW(wShadowOAMEnd)
	jr z, .clear

; Don't clear the last 4 entries because they are used for the shadow in the
; jumping down ledge animation and the rod in the fishing animation.
	ld c, LOW(wShadowOAMSprite36)

.clear
	ldh a, [hOAMBufferOffset]
	cp c
	ret nc
	ld l, a
	ld h, HIGH(wShadowOAM)
	ld a, c
	ld de, $4 ; entry size
	ld b, $a0
.clearLoop
	ld [hl], b
	add hl, de
	cp l
	jr nz, .clearLoop
	ret

IF DEF(PHASE2_AUDIT)
; Called after lifecycle has made the single full-color ownership decision for
; this VBlank. Build and enqueue once; the scheduler remains the sole DMA owner.
FullColorPhase5OAMBuildOrigin::
FullColorPhase5OAMBuildStart::
PrepareFullColorOAMDataForOwnedVBlank::
	; Invalidate the prior hardware-OAM certificate before the first possible
	; shadow write.  If VBlank interrupts this build, the epoch mismatch makes
	; the retained path fail closed instead of presenting an older batch as if
	; the newly-mutated shadow authority were unchanged.
	farcall InvalidateFullColorPhase5OAMAuthority
	ld a, 1
	ldh [hSpritePriority], a
	call PrepareOAMData.build
	ld de, wShadowOAM
	farcall EnqueueFullColorOAMBatchFar
FullColorPhase5OAMBuildEnd::
	ret

	PUSHS
	SECTION "Full Color Phase 5 Natural Audit", ROMX

; Natural audit-only producer route.  Overworld mainline invokes this before
; each retained DelayFrame, so construction and the immutable scheduler
; snapshot finish before the following VBlank.  A resident unit owns its
; frozen source and suppresses another build until it has been consumed.
FullColorPhase5PrepareOwnedMainlineFrame::
	; Publish the just-completed scheduler state before polling, retrying, or
	; admitting any next-frame producer mutation.
	farcall PublishFullColorPhase5FastDebug
	farcall PollFullColorPhase2DebugCommand
	farcall RetryFullColorProducer
	farcall UpdateFullColorPhase5PartyStableFrames
	ldh a, [rIE]
	ldh [hRendererStateSavedIE], a
	xor a
	ldh [rIE], a
	ldh a, [rSVBK]
	ldh [hRendererStateSavedSVBK], a
	ld a, PHASE1_SELECTED_WRAM_BANK
	ldh [rSVBK], a
	ld a, [wRendererOwner]
	cp RENDERER_FULL_COLOR_OVERWORLD
	jp nz, .skip
	ld a, [wRendererPhase]
	cp OVERWORLD_ACTIVE
	jp nz, .skip
	ld a, [wRendererAdmissionOpen]
	and a
	jp z, .skip
	; A frozen non-OAM cache owns the next retained frame.  Do not run any
	; shadow-OAM writer or advance its authority epoch until that whole unit has
	; drained; hardware OAM remains the exact prior committed shadow batch.
	ld a, [wFullColorPhase5FastCacheValid]
	and a
	jp nz, .skip
	; Never overwrite a declared batch that has not reached its atomic DMA.
	; Other pending/prepared classes use independent scratch and may coexist.
	ld hl, wFullColorRequestDescriptors
	ld b, FULL_COLOR_REQUEST_CAPACITY
	ld c, 0
.residentOAM
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_STATE_MASK
	cp FULL_COLOR_DESCRIPTOR_FREE
	jr z, .nextResident
	cp COMPLETE << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr z, .nextResident
	cp CANCELLED << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr z, .nextResident
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr z, .residentOAMFound
.nextResident
	ld de, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	add hl, de
	inc c
	dec b
	jr nz, .residentOAM
	; Admission cannot fail after the shadow writer has started.  Reclaim one
	; terminal slot first; if all eight descriptors are genuinely active, retain
	; the prior hardware certificate and leave shadow/epoch untouched.
	call EnsureFreeFullColorPhase5DescriptorSelected
	jp c, .skip
	; Keep interrupts masked from the first shadow-authority mutation through
	; publishing the new OAM descriptor's cursor.  Nested farcalls see IE=0 and
	; therefore cannot reopen the exact window that previously let VBlank use
	; the old non-OAM cursor against a newly PREPARED OAM declaration.  This
	; natural overworld seam has the Yellow stack in WRAM1 by contract.
	ldh a, [hRendererStateSavedSVBK]
	ldh [rSVBK], a
	ldh a, [hRendererStateSavedIE]
	push af
	farcall PrepareFullColorOAMDataForOwnedVBlank
	jr c, .newOAMFailed

	; OAM is mandatory under simultaneous pressure.  Point the round-robin
	; cursor at its newly frozen descriptor before other natural producers run.
	ld a, PHASE1_SELECTED_WRAM_BANK
	ldh [rSVBK], a
	ld hl, wFullColorRequestDescriptors
	push hl
	ld hl, wFullColorPhase5PressureEnqueuedMask
	set 2, [hl]
	pop hl
	ld c, 0
	ld b, FULL_COLOR_REQUEST_CAPACITY
.findOAM
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_STATE_MASK
	cp FULL_COLOR_DESCRIPTOR_FREE
	jr z, .next
	cp COMPLETE << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr z, .next
	cp CANCELLED << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr z, .next
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr z, .foundOAM
.next
	ld de, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	add hl, de
	inc c
	dec b
	jr nz, .findOAM
	jr .done
.foundOAM
	ld a, c
	ld [wFullColorRequestCursor], a
.done
	ld a, 1
	ldh [rSVBK], a
	pop af
	ldh [rIE], a
	call FullColorPhase5PressureMainline
	farcall PrepareAndCacheNextFullColorPhase5Request
	and a
	ret
.newOAMFailed
	pop af
	ldh [rIE], a
	scf
	ret
.residentOAMFound
	ld a, c
	ld [wFullColorRequestCursor], a
.pressureSelected
	ldh a, [hRendererStateSavedSVBK]
	ldh [rSVBK], a
	ldh a, [hRendererStateSavedIE]
	ldh [rIE], a
	call FullColorPhase5PressureMainline
	farcall PrepareAndCacheNextFullColorPhase5Request
	and a
	ret
.skip
	ldh a, [hRendererStateSavedSVBK]
	ldh [rSVBK], a
	ldh a, [hRendererStateSavedIE]
	ldh [rIE], a
	and a
	ret

EnsureFreeFullColorPhase5DescriptorSelected:
	ld hl, wFullColorRequestDescriptors
	ld b, FULL_COLOR_REQUEST_CAPACITY
.scan
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_STATE_MASK
	cp FULL_COLOR_DESCRIPTOR_FREE
	ret z
	cp COMPLETE << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr z, .reclaim
	cp CANCELLED << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr z, .reclaim
	ld de, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	add hl, de
	dec b
	jr nz, .scan
	scf
	ret
.reclaim
	ld a, FULL_COLOR_DESCRIPTOR_FREE
	ld [hl], a
	and a
	ret

; Observe and inject only the Pallet operations absent from the natural
; navigation corpus.  Every unit enters through ordinary admission, and the
; masks distinguish successful enqueue from eventual scheduler drain.
FullColorPhase5PressureMainline::
	ldh a, [rIE]
	ldh [hRendererStateSavedIE], a
	xor a
	ldh [rIE], a
	ldh a, [rSVBK]
	ldh [hRendererStateSavedSVBK], a
	ld a, PHASE1_SELECTED_WRAM_BANK
	ldh [rSVBK], a

	; Build a compact active-class mask in E while ignoring terminal slots.
	ld hl, wFullColorRequestDescriptors
	ld b, FULL_COLOR_REQUEST_CAPACITY
	ld c, 0
.active
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_STATE_MASK
	cp FULL_COLOR_DESCRIPTOR_FREE
	jr z, .activeNext
	cp COMPLETE << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr z, .activeNext
	cp CANCELLED << FULL_COLOR_DESCRIPTOR_STATE_SHIFT
	jr z, .activeNext
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD
	jr nz, :+
	set 0, c
:
	cp FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT
	jr nz, :+
	set 1, c
:
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr nz, .activeNext
	set 2, c
.activeNext
	ld a, l
	add FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	ld l, a
	jr nc, :+
	inc h
:
	dec b
	jr nz, .active
	ld a, c
	cpl
	ld e, a
	ld a, [wFullColorPhase5PressureEnqueuedMask]
	and e
	ld e, a
	ld hl, wFullColorPhase5PressureDrainedMask
	ld a, [hl]
	or e
	ld [hl], a

	ld a, [wFullColorPhase5ScenarioControl]
	cp FULL_COLOR_PHASE5_SCENARIO_CONTROL_ARMED
	jp nz, .restore
	ld a, [wFullColorPhase5Scenario]
	cp FULL_COLOR_PHASE5_SCENARIO_COMBINED_VBLANK
	jr z, .paletteOrAnimation
	cp FULL_COLOR_PHASE5_SCENARIO_PALETTE
	jr z, .paletteOnly
	cp FULL_COLOR_PHASE5_SCENARIO_ANIMATION
	jr z, .animationOnly
	jp .restore
.paletteOrAnimation
	ld a, [wFullColorPhase5PressureEnqueuedMask]
	bit 0, a
	jr z, .preparePalette
	; fallthrough
.animationOnly
	ld a, [wFullColorPhase5PressureEnqueuedMask]
	bit 1, a
	jr z, .prepareAnimation
	jr .restore
.paletteOnly
	ld a, [wFullColorPhase5PressureEnqueuedMask]
	bit 0, a
	jr nz, .restore
	; fallthrough
.preparePalette
	ld hl, FullColorPhase5PressurePaletteDescriptor
	ld de, wFullColorSchedulerEnqueueDescriptor
	ld b, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	ld c, FULL_COLOR_PHASE5_PRESSURE_PALETTE
	jr .copyDescriptor
.prepareAnimation
	ld hl, FullColorPhase5PressureAnimationDescriptor
	ld de, wFullColorSchedulerEnqueueDescriptor
	ld b, FULL_COLOR_REQUEST_DESCRIPTOR_BYTES
	ld c, FULL_COLOR_PHASE5_PRESSURE_ANIMATION
.copyDescriptor
	ld a, [hli]
	ld [de], a
	inc de
	dec b
	jr nz, .copyDescriptor
	; Bind the resident request to the current ownership generation.
	ld hl, wRendererGeneration
	ld de, wFullColorSchedulerEnqueueDescriptor + FULL_COLOR_DESCRIPTOR_GENERATION
	ld b, 4
.generation
	ld a, [hli]
	ld [de], a
	inc de
	dec b
	jr nz, .generation
	ldh a, [hRendererStateSavedSVBK]
	ldh [rSVBK], a
	ldh a, [hRendererStateSavedIE]
	ldh [rIE], a
	push bc
	farcall AdmitFullColorPhase5PressureDescriptorFar
	pop bc
	; Bankswitch restores the caller ROM bank through A.  Read the admission
	; authority from its selected-WRAM result byte before publishing accounting.
	ldh a, [rIE]
	ldh [hRendererStateSavedIE], a
	xor a
	ldh [rIE], a
	ldh a, [rSVBK]
	ldh [hRendererStateSavedSVBK], a
	ld a, PHASE1_SELECTED_WRAM_BANK
	ldh [rSVBK], a
	ld a, [wFullColorLastAdmissionResult]
	cp ACCEPTED
	jr z, .admittedSelected
	cp COALESCED
	jr nz, .admissionFailedSelected
.admittedSelected
	ld a, c
	ld hl, wFullColorPhase5PressureEnqueuedMask
	or [hl]
	ld [hl], a
	ldh a, [hRendererStateSavedSVBK]
	ldh [rSVBK], a
	ldh a, [hRendererStateSavedIE]
	ldh [rIE], a
	jp FullColorPhase5PressureMainline
.admissionFailedSelected
	ldh a, [hRendererStateSavedSVBK]
	ldh [rSVBK], a
	ldh a, [hRendererStateSavedIE]
	ldh [rIE], a
	ret
.restore
	ldh a, [hRendererStateSavedSVBK]
	ldh [rSVBK], a
	ldh a, [hRendererStateSavedIE]
	ldh [rIE], a
	ret

; Fixed-WRAM sources remain immutable until the scheduler prepares each unit.
; Palette bytes use the existing authored base buffer; animation uses the
; producer tile buffer already reserved by the Phase 2 ABI.
FullColorPhase5PressurePaletteDescriptor:
	db FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD, RENDERER_FULL_COLOR_OVERWORLD
	ds 4
	dw FULL_COLOR_BG_PALETTE_DESTINATION, wFullColorOBJPaletteBase
	dw 0
	dw FULL_COLOR_RESOURCE_PALETTES
	dw FULL_COLOR_PALETTE_EXTENT, FULL_COLOR_PALETTE_RESERVATION
	db 0, 0
FullColorPhase5PressureAnimationDescriptor:
	db FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT, RENDERER_FULL_COLOR_OVERWORLD
	ds 4
	dw FULL_COLOR_TILE_DATA_FIRST, wFullColorProducerTiles
	dw FULL_COLOR_BG_MAP_FIRST
	dw FULL_COLOR_RESOURCE_TILE_DATA | FULL_COLOR_RESOURCE_ATTRIBUTES
	dw FULL_COLOR_ANIMATION_EXTENT, FULL_COLOR_ANIMATION_RESERVATION
	db 0, 0

; Both retained overworld DelayFrame seams pass through this natural mainline
; producer.  The far-call trampoline remains live until DelayFrame returns, so
; the caller's ROM bank is restored only after the owned VBlank completes.
FullColorPhase5PrepareOwnedMainlineFrameAndDelayFrame::
	call FullColorPhase5PrepareOwnedMainlineFrame
	jp DelayFrame

; DE is the resident descriptor and WRAM2 is already selected.  Carry rejects
; any mutation of the exact fixed-WRAM declaration immediately before commit.
FullColorPhase5ValidateOAMDeclarationSelectedFar::
	ld hl, FULL_COLOR_DESCRIPTOR_SOURCE
	add hl, de
	ld a, [hli]
	and a ; LOW(wShadowOAM) == 0
	jr nz, .invalid
	ld a, [hl]
	cp HIGH(wShadowOAM)
	jr nz, .invalid
	ld hl, FULL_COLOR_DESCRIPTOR_FLAGS
	add hl, de
	ld a, [hl]
	cp FULL_COLOR_FLAG_OAM_FINISHED
	jr nz, .invalid
	and a
	ret
.invalid
	scf
	ret

; Establish the measured scheduler budget once, after the VBlank owner has been
; revalidated and before any prepared unit can enter COMMITTING.
FullColorPhase5BeginVBlankBudgetFar::
	ldh a, [rIE]
	ldh [hRendererStateSavedIE], a
	xor a
	ldh [rIE], a
	ldh a, [rSVBK]
	ldh [hRendererStateSavedSVBK], a
	ld a, PHASE1_SELECTED_WRAM_BANK
	ldh [rSVBK], a
	ld a, LOW(FULL_COLOR_PHASE5_VBLANK_SCHEDULER_BUDGET)
	ld [wFullColorPhase5FrameAvailableCycles], a
	ld a, HIGH(FULL_COLOR_PHASE5_VBLANK_SCHEDULER_BUDGET)
	ld [wFullColorPhase5FrameAvailableCycles + 1], a
	xor a
	ld [wFullColorPhase5FrameRequiredCycles], a
	ld [wFullColorPhase5FrameRequiredCycles + 1], a
	ldh a, [hRendererStateSavedSVBK]
	ldh [rSVBK], a
	ldh a, [hRendererStateSavedIE]
	ldh [rIE], a
	ret

; DE is a resident descriptor and WRAM2 is already selected.  Required cycles
; come from the measured operation table; paired geometry scales by visible
; cells.  Carry defers the whole PREPARED unit without any presented write.
FullColorPhase5ReserveDescriptorCyclesSelectedFar::
	ldh a, [rLCDC]
	bit B_LCDC_ENABLE, a
	jr z, .hidden
	ld h, d
	ld l, e
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD
	jr z, .palette
	cp FULL_COLOR_REQUEST_OBJ_PALETTE_PAYLOAD
	jr z, .palette
	cp FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT
	jr z, .animation
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jr z, .oam
	ld hl, FULL_COLOR_DESCRIPTOR_EXTENT
	add hl, de
	inc hl
	ld a, [hld]
	and a
	jr nz, .tooLarge
	ld a, [hl]
	ld l, a
	ld h, 0
	REPT 5
		add hl, hl
	ENDR
	ld b, h
	ld c, l
	add hl, hl
	add hl, bc
	ld bc, FULL_COLOR_PHASE5_CYCLES_PAIRED_BASE
	add hl, bc
	jr .required
.palette
	ld hl, FULL_COLOR_PHASE5_CYCLES_PALETTE
	jr .required
.animation
	ld hl, FULL_COLOR_PHASE5_CYCLES_ANIMATION
	jr .required
.oam
	ld hl, FULL_COLOR_PHASE5_CYCLES_OAM
	jr .required
.tooLarge
	ld hl, $ffff
	jr .required
.hidden
	ld hl, 0
.required
	ld a, l
	ld [wFullColorPhase5FrameRequiredCycles], a
	ld a, h
	ld [wFullColorPhase5FrameRequiredCycles + 1], a
	ld a, [wFullColorPhase5FrameAvailableCycles + 1]
	cp h
	jr c, .defer
	jr nz, .subtract
	ld a, [wFullColorPhase5FrameAvailableCycles]
	cp l
	jr c, .defer
.subtract
	ld a, [wFullColorPhase5FrameAvailableCycles]
	sub l
	ld [wFullColorPhase5FrameAvailableCycles], a
	ld a, [wFullColorPhase5FrameAvailableCycles + 1]
	sbc h
	ld [wFullColorPhase5FrameAvailableCycles + 1], a
	and a
	ret
.defer
	scf
	ret

	POPS
ENDC

GetSpriteScreenXY:
	inc e
	inc e
	ld a, [de] ; [x#SPRITESTATEDATA1_YPIXELS]
	ldh [hSpriteScreenY], a
	inc e
	inc e
	ld a, [de] ; [x#SPRITESTATEDATA1_XPIXELS]
	ldh [hSpriteScreenX], a
	ld a, 4
	add e
	ld e, a
	ldh a, [hSpriteScreenY]
	add 4
	and $f0
	ld [de], a ; [x#SPRITESTATEDATA1_YADJUSTED]
	inc e
	ldh a, [hSpriteScreenX]
	and $f0
	ld [de], a  ; [x#SPRITESTATEDATA1_XADJUSTED]
	ret

Func_4a7b:
	push bc
	ld a, [wSavedSpriteImageIndex]
	swap a                   ; high nybble determines sprite used (0 is always player sprite, next are some npcs)
	and $f

	; Sprites $a and $b have one face (and therefore 4 tiles instead of 12).
	; As a result, sprite $b's tile offset is less than normal.
	cp $b
	jr nz, .notFourTileSprite
	ld a, $a * 12 + 4 ; $7c
	jr .done

.notFourTileSprite
	; a *= 12
	add a
	add a
	ld c, a
	add a
	add c
.done
	pop bc
	ret

INCLUDE "engine/gfx/oam_dma.asm"

_IsTilePassable::
	ld hl, wTilesetCollisionPtr ; pointer to list of passable tiles
	ld a, [hli]
	ld h, [hl]
	ld l, a ; hl now points to passable tiles
.loop
	ld a, [hli]
	cp $ff
	jr z, .tileNotPassable
	cp c
	jr nz, .loop
	xor a
	ret
.tileNotPassable
	scf
	ret

INCLUDE "data/tilesets/collision_tile_ids.asm"

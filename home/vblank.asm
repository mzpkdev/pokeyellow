IF DEF(PHASE2_AUDIT)
; Zero-byte timing origin for the natural interrupt path. The accepted CGB
; double-speed deadline remains this origin plus 9120 CPU T-cycles.
FullColorPhase5VBlankOrigin::
ENDC
VBlank::

	push af
	push bc
	push de
	push hl

	ldh a, [rSVBK]
	; The outer register frame is already on the interrupted WRAM bank. Save
	; SVBK in HRAM so restoring it never tries to read through another bank.
	ldh [hPassiveFullColorVBlankSavedSVBK], a
	ld a, 1
	ldh [rSVBK], a

	ldh a, [rVBK] ; vram bank
	push af
	xor a
	ldh [rVBK], a ; reset vram bank to 0

	ldh a, [hLoadedROMBank]
	ld [wVBlankSavedROMBank], a
	IF DEF(PHASE2_AUDIT)
		; Decide the retained VBlank owner before any Yellow-visible register,
		; VRAM, or OAM writer. Carry clear means the full-color owner completed
		; its bounded work; resume only the shared non-visible interrupt tail.
		farcall FullColorVBlankOwnerConsumed
		jr c, FullColorPhase5YellowOwner
FullColorPhase5CombinedVBlankEnd::
		farcall FinishFullColorPhase5DeferredAccounting
		jr FullColorPhase5YellowOwner.vblankSensitiveOperationsDone
FullColorPhase5YellowOwner:
	ENDC
	ldh a, [hSCX]
	ldh [rSCX], a
	ldh a, [hSCY]
	ldh [rSCY], a

	ld a, [wDisableVBlankWYUpdate]
	and a
	jr nz, .ok
	ldh a, [hWY]
	ldh [rWY], a
.ok

	; A fresh Color overlay publishes its hidden bank-1 attribute plane with one
	; aligned GDMA. Yellow's stock transfer owns the next three bank-0 frames.
	; Keep Yellow's separate OAM pipeline alive throughout that VRAM barrier.
	ldh a, [hAutoBGTransferEnabled]
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_ATTRIBUTE_GDMA, a
	jr z, .ordinaryAutoBgMapTransfer
	farcall PassiveFullColorOverlayAttributeGDMA
	; The GDMA owns VRAM this frame. Leave other VRAM work armed, but preserve
	; Yellow's OAM DMA/preparation cadence so a full-screen menu cannot reveal
	; stale overworld sprites.
	jr .yellowOAMOperations
.ordinaryAutoBgMapTransfer
	ldh a, [hAutoBGTransferEnabled]
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_COMPLETE, a
	jr nz, .completedOverlayTransfer
	call AutoBgMapTransfer
	call VBlankCopyBgMap
	jr .ordinaryVisibleOperations
.completedOverlayTransfer
	farcall PassiveFullColorCompletedOverlayVBlank
	jr nc, .yellowOAMDMAOnly

.ordinaryVisibleOperations
	; RedrawRowOrColumn consumes its mode. Freeze that one byte so the passive
	; bank-1 mirror can follow the completed Yellow bank-0 write geometrically.
	ldh a, [hRedrawRowOrColumnMode]
	push af
	call RedrawRowOrColumn
	; D carries the consumed mode through Bankswitch; E is the discarded flags.
	pop de
	farcall PassiveFullColorVBlank
.passiveFullColorVBlankDone
	call VBlankCopy
	call VBlankCopyDouble
	call UpdateMovingBgTiles

.yellowOAMOperations
	ld c, 1
	jr .yellowOAMDMA

	; The attribute frame already prepared the frozen menu/dialogue OAM image.
	; Stock tile chunks only need to commit it; rebuilding sprites here would run
	; beyond VBlank beside AutoBgMapTransfer.
.yellowOAMDMAOnly
	ld c, 0
.yellowOAMDMA
	call hDMARoutine
	bit 0, c
	jr z, .vblankSensitiveOperationsDone
	ld a, BANK(PrepareOAMData)
	call BankswitchCommon
	call PrepareOAMData

	; VBlank-sensitive operations end.
.vblankSensitiveOperationsDone
	call TrackPlayTime ; keep track of time played

	call Random
	call ReadJoypad

	; The postcondition was always zero; write it directly and leave more of
	; the fixed Home section for the bank-preserving interrupt prologue.
	xor a
	ldh [hVBlankOccurred], a

	ldh a, [hFrameCounter]
	and a
	jr z, .skipDec
	dec a
	ldh [hFrameCounter], a

.skipDec
	call FadeOutAudio

	ld a, BANK(Music_DoLowHealthAlarm)
	call BankswitchCommon
	call Music_DoLowHealthAlarm
	ld a, BANK(Audio1_UpdateMusic)
	call BankswitchCommon
	call Audio1_UpdateMusic

	call SerialFunction

	ld a, [wVBlankSavedROMBank]
	call BankswitchCommon

	pop af
	ldh [rVBK], a

	ldh a, [hPassiveFullColorVBlankSavedSVBK]
	ldh [rSVBK], a

	pop hl
	pop de
	pop bc
	pop af
	IF DEF(PHASE2_AUDIT)
FullColorPhase5VBlankHandlerEnd::
	ENDC
	reti


DelayFrame::
; Wait for the next vblank interrupt.
; As a bonus, this saves battery.

DEF NOT_VBLANKED EQU 1

	ld a, NOT_VBLANKED
	ldh [hVBlankOccurred], a
.halt
	halt
	ldh a, [hVBlankOccurred]
	and a
	jr nz, .halt
	ret

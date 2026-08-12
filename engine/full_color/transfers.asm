; Class-specific complete visible units. Map requests encode width/height in
; desired-state and commit with the hardware 32-byte BG-map stride. The source
; owns both planes: extent tile bytes followed by extent attribute bytes.

PrepareFullColorPairedTransferSelected::
	ld a, l
	ld [wFullColorActiveDescriptor], a
	ld a, h
	ld [wFullColorActiveDescriptor + 1], a
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_EXTENT
	add hl, de
	ld a, [hli]
	ld c, a
	ld b, [hl]
	pop hl
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_SOURCE
	add hl, de
	ld a, [hli]
	ld d, [hl]
	ld e, a
	pop hl
	; Freeze the complete tile plane in the 360-byte rectangle buffer.
	push hl
	push bc
	ld hl, wFullColorAttributeRectangle
.tile
	ld a, b
	or c
	jr z, .tile_done
	ld a, [de]
	ld [hli], a
	inc de
	dec bc
	jr .tile
.tile_done
	pop bc
	pop hl
	; The second frozen plane uses the four palette buffers followed by the
	; first 104 bytes of the OAM buffer. Singleton preparation makes that union
	; safe and keeps the measured scratch allocation unchanged.
	ld hl, wFullColorBGPaletteBase
.attribute
	ld a, b
	or c
	jr z, .done
	ld a, h
	cp HIGH(wFullColorAttributeRectangle)
	jr nz, .attribute_source
	ld a, l
	cp LOW(wFullColorAttributeRectangle)
	jr nz, .attribute_source
	ld hl, wFullColorShadowOAMBatch
.attribute_source
	ld a, [de]
	and $ef
	ld [hli], a
	inc de
	dec bc
	jr .attribute
.done
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	and a
	ret

PrepareFullColorAnimationReplacementSelected::
	ld a, l
	ld [wFullColorActiveDescriptor], a
	ld a, h
	ld [wFullColorActiveDescriptor + 1], a
	ld de, FULL_COLOR_DESCRIPTOR_SOURCE
	add hl, de
	ld a, [hli]
	ld d, [hl]
	ld e, a
	ld hl, FULL_COLOR_ANIMATION_TILE_BYTES
	add hl, de
	ld a, [hl]
	and $ef
	ld [wFullColorAttributeRectangle], a
	; Freeze all tile bytes too; COMMITTING must never reread caller storage.
	ld hl, wFullColorBGPaletteBase
	ld b, FULL_COLOR_ANIMATION_TILE_BYTES
.tile
	ld a, [de]
	ld [hli], a
	inc de
	dec b
	jr nz, .tile
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	and a
	ret

CommitFullColorPairedTransferSelected::
	ld a, l
	ld [wFullColorActiveDescriptor], a
	ld a, h
	ld [wFullColorActiveDescriptor + 1], a
	; The measured cell writer lives in the added-only auto-ROMX Phase 5 region;
	; this paid fixed-window seam only preserves the descriptor ABI.
	farcall CommitFullColorPhase5PairedTransferFastSelected
	call LoadFullColorActiveDescriptorSelected
	ret

LoadFullColorActiveDescriptorSelected:
	ld a, [wFullColorActiveDescriptor]
	ld l, a
	ld a, [wFullColorActiveDescriptor + 1]
	ld h, a
	ret

LoadFullColorActiveMapDestinationSelected:
	call LoadFullColorActiveDescriptorSelected
	ld bc, FULL_COLOR_DESCRIPTOR_DESTINATION
	add hl, bc
	ld a, [hli]
	ld h, [hl]
	ld l, a
	ret

FullColorPhase5AnimationStart::
CommitFullColorAnimationReplacementSelected::
	ld a, l
	ld [wFullColorActiveDescriptor], a
	ld a, h
	ld [wFullColorActiveDescriptor + 1], a
	ld de, FULL_COLOR_DESCRIPTOR_DESTINATION
	add hl, de
	ld a, [hli]
	ld h, [hl]
	ld l, a
	ld de, wFullColorBGPaletteBase
	ldh a, [rVBK]
	ld [wFullColorTimingState + 1], a
	xor a
	ldh [rVBK], a
	ld b, FULL_COLOR_ANIMATION_TILE_BYTES
.tile
	ld a, [de]
	ld [hli], a
	inc de
	dec b
	jr nz, .tile
	ld a, 1
	ldh [rVBK], a
	call LoadFullColorActiveDescriptorSelected
	ld bc, FULL_COLOR_DESCRIPTOR_DESIRED_STATE
	add hl, bc
	ld a, [hli]
	ld h, [hl]
	ld l, a
	ld a, [wFullColorAttributeRectangle]
	ld [hl], a
	ld a, [wFullColorTimingState + 1]
	ldh [rVBK], a
	call LoadFullColorActiveDescriptorSelected
FullColorPhase5AnimationEnd::
	ret

ASSERT wFullColorBGPaletteBase + 256 == wFullColorAttributeRectangle
ASSERT wFullColorAttributeRectangle + SCREEN_AREA == wFullColorShadowOAMBatch
ASSERT 256 + 104 == SCREEN_AREA

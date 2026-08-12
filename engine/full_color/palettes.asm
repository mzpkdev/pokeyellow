; Complete 64-byte palette preparation and commit. Base buffers are immutable
; inputs for a request; transformations are derived into distinct buffers.

PrepareFullColorVisibleUnitSelected::
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT
	jp z, PrepareFullColorAnimationReplacementSelected
	cp FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD
	jr z, PrepareFullColorBGPaletteSelected
	cp FULL_COLOR_REQUEST_OBJ_PALETTE_PAYLOAD
	jr z, PrepareFullColorOBJPaletteSelected
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jp z, PrepareFullColorOAMBatchSelected
	jp PrepareFullColorPairedTransferSelected

PrepareFullColorBGPaletteSelected:
	; The audit fast writer reconstructs the resident descriptor after its
	; cross-bank call. Bind that pointer while preparation owns the singleton
	; palette scratch so a separately cached commit cannot inherit an older
	; descriptor's transform flag.
	ld a, l
	ld [wFullColorActiveDescriptor], a
	ld a, h
	ld [wFullColorActiveDescriptor + 1], a
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_SOURCE
	add hl, de
	ld a, [hli]
	ld d, [hl]
	ld e, a
	ld hl, wFullColorBGPaletteBase
	call CopyAndTransformFullColorPaletteSelected
	pop hl
	and a
	ret

PrepareFullColorOBJPaletteSelected:
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_SOURCE
	add hl, de
	ld a, [hli]
	ld d, [hl]
	ld e, a
	ld hl, wFullColorOBJPaletteBase
	call CopyAndTransformFullColorPaletteSelected
	pop hl
	and a
	ret

; DE source, HL 64-byte base. The transformed buffer immediately follows base.
CopyAndTransformFullColorPaletteSelected:
	push hl
	ld b, 64
.base
	ld a, [de]
	ld [hli], a
	inc de
	dec b
	jr nz, .base
	pop de
	ld hl, 64
	add hl, de
	ld b, 32
.color
	ld a, [de]
	and $1f
	ld c, a
	ld a, $1f
	sub c
	ld [hli], a
	inc de
	ld a, [de]
	and $7c
	xor $7c
	ld [hli], a
	inc de
	dec b
	jr nz, .color
	ret

CommitFullColorVisibleUnitSelected::
	ld a, [hl]
	and FULL_COLOR_DESCRIPTOR_CLASS_MASK
	cp FULL_COLOR_REQUEST_ANIMATION_REPLACEMENT
	jp z, CommitFullColorAnimationReplacementSelected
	cp FULL_COLOR_REQUEST_BG_PALETTE_PAYLOAD
	jr z, CommitFullColorBGPaletteSelected
	cp FULL_COLOR_REQUEST_OBJ_PALETTE_PAYLOAD
	jr z, CommitFullColorOBJPaletteSelected
	cp FULL_COLOR_REQUEST_OAM_BATCH_AND_DMA
	jp z, CommitFullColorOAMBatchSelected
	jp CommitFullColorPairedTransferSelected

FullColorPhase5PaletteStart::
CommitFullColorBGPaletteSelected:
	; The added-only writer unrolls all 64 bytes while reconstructing
	; the descriptor pointer from scheduler authority after the farcall.
	farcall CommitFullColorPhase5BGPaletteFastSelected
FullColorPhase5PaletteEnd::
	ret

CommitFullColorOBJPaletteSelected:
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_FLAGS
	add hl, de
	bit 1, [hl]
	ld hl, wFullColorOBJPaletteBase
	jr z, .source
	ld hl, wFullColorOBJPaletteTransformed
.source
	ld a, $80
	ldh [rOBPI], a
	ld c, LOW(rOBPD)
	ld b, 64
.copy
	ld a, [hli]
	ldh [c], a
	dec b
	jr nz, .copy
	pop hl
	ret

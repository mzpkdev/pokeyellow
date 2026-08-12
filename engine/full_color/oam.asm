; Snapshot a producer-finished full-color OAM batch. Identity lookup and
; fallback happen while the producer constructs the final batch; deferred
; scheduler preparation never rereads mutable sprite authority.

PrepareFullColorOAMBatchSelected::
	push hl
	ld de, FULL_COLOR_DESCRIPTOR_SOURCE
	add hl, de
	ld a, [hli]
	ld d, [hl]
	ld e, a
	ld hl, wFullColorShadowOAMBatch
	ld b, 160
.copy
	ld a, [de]
	ld [hli], a
	inc de
	dec b
	jr nz, .copy
	pop hl
	push hl
	ld bc, FULL_COLOR_DESCRIPTOR_FLAGS
	add hl, bc
	ld a, [hl]
	pop hl
	and FULL_COLOR_FLAG_OAM_FINISHED
	jr nz, .finished
	; Legacy audit probes may still supply forty identities after the batch.
	; Map them through the same authored-identity contract as the real producer;
	; the exact producer helper above marks its batch finished and never enters
	; this compatibility path.
	push hl
	ld hl, wFullColorShadowOAMBatch + 3
	ld b, 40
.map
	ld a, [de]
	inc de
	push de
	call MapFullColorOAMAttributeSelected
	pop de
	inc hl
	inc hl
	inc hl
	inc hl
	dec b
	jr nz, .map
	pop hl
.finished
	and a
	ret

; Map one final-picture identity into a finished fixed-WRAM batch before it is
; enqueued. Input A=identity, B=reverse object cursor (40..1), HL=attribute
; byte. Output A=palette (0..7), carry set only when palette-0 fallback was
; used. Bits 3-7 at [HL] are always preserved. Clobbers CDE.
MapFullColorOAMAttribute::
	ld c, a
	select_renderer_state_e
	ld a, c
	call MapFullColorOAMAttributeSelected
	ld d, a
	ld e, 0
	jr nc, .mapped
	inc e
.mapped
	restore_renderer_state_e
	ld a, d
	ld d, a
	ld a, e
	and a
	ld a, d
	ret z
	scf
	ret

MapFullColorOAMAttributeSelected:
	ld d, a
	cp SPRITE_RED
	jr z, .red
	cp SPRITE_PIKACHU
	jr z, .pikachu
	cp SPRITE_OAK
	jr z, .oak
	cp SPRITE_GIRL
	jr z, .girl
	cp SPRITE_FISHER
	jr z, .fisher
	cp $ff
	jr z, .missing
	cp 8
	jr c, .unmapped
	bit 7, a
	jr nz, .unmapped
	ld c, FULL_COLOR_FALLBACK_OUT_OF_RANGE
	jr .fallback
.missing
	ld c, FULL_COLOR_FALLBACK_MISSING_IDENTITY
	jr .fallback
.unmapped
	ld c, FULL_COLOR_FALLBACK_UNMAPPED
.fallback
	xor a
	call RecordFullColorOAMFallbackSelected
	ld c, 1
	jr .write
.red
	ld a, 1
	jr .apply
.pikachu
	ld a, 2
	jr .apply
.oak
	ld a, 3
	jr .apply
.girl
	ld a, 4
	jr .apply
.fisher
	ld a, 5
.apply
	ld c, 0
.write
	ld e, a
	ld a, [hl]
	and $f8
	or e
	ld [hl], a
	ld a, c
	and a
	ld a, e
	ret z
	scf
	ret

; A palette (zero for fallback), B reverse object cursor, C fallback kind,
; D rejected identity. The fixed four-byte bounded record is a seven-bit
; saturating count with an explicit high-bit overflow marker, then last kind,
; rejected identity, and object index. Together the total and final event
; distinguish an expected late fallback from hidden earlier fallbacks without
; touching write-only SRAM controls.
RecordFullColorOAMFallbackSelected:
	push hl
	ld hl, wFullColorReconstructionItems
	ld a, [hl]
	bit 7, a
	jr nz, .record
	cp $7f
	jr z, .overflow
	inc [hl]
	jr .record
.overflow
	ld a, $ff
	ld [hl], a
.record
	ld a, c
	ld [wFullColorReconstructionItems + 1], a
	ld a, d
	ld [wFullColorReconstructionItems + 2], a
	ld a, 40
	sub b
	ld [wFullColorReconstructionItems + 3], a
	pop hl
	xor a
	ret

CommitFullColorOAMBatchSelected:
	push hl
	IF DEF(PHASE2_AUDIT)
		; The complete declared wShadowOAM batch was built immediately before
		; this owned VBlank.  The resident descriptor prevents any second build;
		; final revalidation precedes this sole hardware-visible operation.
	ELSE
	ld hl, wFullColorShadowOAMBatch
	ld de, wShadowOAM
	ld b, 160
.copy
	ld a, [hli]
	ld [de], a
	inc de
	dec b
	jr nz, .copy
	ENDC
FullColorPhase5OAMDMAStart::
	call hDMARoutine
FullColorPhase5OAMDMAEnd::
	pop hl
	ret

EXPORT MapFullColorOAMAttribute

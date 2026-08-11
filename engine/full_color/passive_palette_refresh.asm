; Scope the steady overworld LoadGBPal call. An active authored presentation
; keeps BG palette hardware ownership while Yellow updates its BGP cache and
; object palettes. Other contexts retain Yellow's ordinary palette publication.
;
; This audit-only writer lives beyond the frozen Phase 2 pipeline range so
; adding it cannot move the reviewed source-to-ROM subjects in that range.

PassiveFullColorLoadGBPal:
	call PassiveFullColorIsSliceMap
	jr nz, .yellow
	call PassiveFullColorReadActive
	cp 1
	jr nz, .yellow
	select_renderer_state_e
	ld a, 1
	ld [wPassiveFullColorBGPaletteProtected], a
	restore_renderer_state_e
	call LoadGBPal
	select_renderer_state_e
	xor a
	ld [wPassiveFullColorBGPaletteProtected], a
	ld a, [wPassiveFullColorPaletteInvalidated]
	ld d, a
	restore_renderer_state_e
	call PassiveFullColorRoofRegionChanged
	jr c, .refresh
	ld a, d
	and a
	ret z
.refresh
	jp PassiveFullColorHandleConnection
.yellow
	call LoadGBPal
	ret

; Fade timing and shade selection remain Yellow-owned. For an active authored
; map, apply Yellow's current BGP permutation to all eight donor palettes so
; palettes 4-7 cannot remain bright while the first four fade.
PassiveFullColorUpdateCGBPal_BGPFade:
	ldh a, [hOnCGB]
	and a
	jr z, .handled
	ldh a, [rBGP]
	ld b, a
	ld a, [wLastBGP]
	cp b
	jr z, .handled
	call PassiveFullColorIsSliceMap
	jr nz, .yellow
	call PassiveFullColorReadActive
	cp 1
	jr nz, .yellow
	call PassiveFullColorReadOverlaySuspended
	jr nz, .yellow
	; Preserve Yellow's cache contract without letting its four-palette writer
	; expose half of an eight-palette fade unit.
	ldh a, [rBGP]
	ld [wLastBGP], a
	call PassiveFullColorReadBGPaletteProtected
	jr nz, .handled
	call PassiveFullColorTransferFadedPalettes
	call PassiveFullColorRecordPalettePublished
.handled
	scf
	ret
.yellow
	farcall _UpdateCGBPal_BGP
	ret

; LoadGBPal uses the same Yellow fade helper during ordinary overworld frames,
; but its protected call must only detect invalidation and queue a VBlank
; refresh. Actual fades stage all eight authored palettes in the serialized
; passive transfer slot, then publish one complete 64-byte visible unit.
PassiveFullColorReadBGPaletteProtected:
	select_renderer_state_e
	ld a, [wPassiveFullColorBGPaletteProtected]
	ld b, a
	restore_renderer_state_e
	ld a, b
	and a
	ret

PassiveFullColorReadOverlaySuspended:
	select_renderer_state_e
	ld a, [wPassiveFullColorOverlaySuspended]
	ld b, a
	restore_renderer_state_e
	ld a, b
	and a
	ret

; A forced-Yellow submenu may leave the active presentation's BG palettes
; invalid when Start resumes its paired overlay. Once admission is restored,
; republish the complete authored current-BGP unit before overlay construction.
PassiveFullColorRestoreInvalidatedPalettes:
	call PassiveFullColorShouldColorOverlay
	ret nc
	select_renderer_state_e
	ld a, [wPassiveFullColorPaletteInvalidated]
	ld b, a
	restore_renderer_state_e
	ld a, b
	and a
	ret z
	call PassiveFullColorTransferFadedPalettes
	jp PassiveFullColorRecordPalettePublished

PassiveFullColorTransferFadedPalettes:
	call PassiveFullColorWaitForRedrawSlot
	ld de, wPassiveFullColorPaletteStaging
	ld c, 0
.stage_color
	; Resolve the BGP-selected authored source shade for destination color C.
	ld a, c
	and %11
	ld b, a
	ldh a, [rBGP]
	jr z, .mapped
.shift
	rrca
	rrca
	dec b
	jr nz, .shift
.mapped
	and %11
	ld b, a
	ld a, c
	and %11111100
	add b
	push bc
	call PassiveFullColorSelectBGPaletteColor
	ld a, [hli]
	ld b, a
	ld a, [hl]
	ld c, a
	select_renderer_state_e
	ld a, b
	ld [de], a
	inc de
	ld a, c
	ld [de], a
	inc de
	restore_renderer_state_e
	pop bc
	inc c
	ld a, c
	cp 8 * PAL_COLORS
	jr nz, .stage_color

	; Match Yellow's palette-transfer seam: mask admission before the LCD-safe
	; wait, switch WRAM only after the stack is quiescent, publish the complete
	; payload, then restore SVBK, BGPI, and the exact raw IE value last.
	ldh a, [rBGPI]
	push af
	ldh a, [rIE]
	ldh [hRendererStateSavedIE], a
	xor a
	ldh [rIE], a
	ldh a, [rSVBK]
	ldh [hRendererStateSavedSVBK], a
	ldh a, [rLCDC]
	and LCDC_ON
	jr z, .publish
.wait_for_vblank
	ldh a, [rLY]
	cp SCREEN_HEIGHT_PX
	jr c, .wait_for_vblank
.publish
	ld a, PASSIVE_FULL_COLOR_WRAM_BANK
	ldh [rSVBK], a
	ld hl, wPassiveFullColorPaletteStaging
	ld c, 8 * PAL_SIZE
	ld a, $80
	ldh [rBGPI], a
.publish_byte
	ld a, [hli]
	ldh [rBGPD], a
	dec c
	jr nz, .publish_byte
	ldh a, [hRendererStateSavedSVBK]
	ldh [rSVBK], a
	pop af
	ldh [rBGPI], a
	ldh a, [hRendererStateSavedIE]
	ldh [rIE], a
	ret

; Return HL at one authored color. Overworld palette 6 colors 1-2 are the
; only non-linear entries because their roof identity is map/coordinate based.
PassiveFullColorSelectBGPaletteColor:
	push de
	ld d, a
	ld a, [wCurMapTileset]
	and a
	jr nz, .linear
	ld a, d
	cp 6 * PAL_COLORS + 1
	jr c, .linear
	cp 6 * PAL_COLORS + 3
	jr nc, .linear
	call PassiveFullColorRoofPaletteForMap
	ld a, d
	sub 6 * PAL_COLORS + 1
	add a
	ld c, a
	ld b, 0
	add hl, bc
	pop de
	ret
.linear
	call PassiveFullColorSelectBGPalettePayload
	ld a, d
	add a
	ld c, a
	ld b, 0
	add hl, bc
	pop de
	ret

; RedrawMapView is Yellow's structural producer. Preserve the active donor BG
; palette and bank-1 plane while its ordinary command updates Yellow's caches
; and object palettes; paired row mirrors publish only the structural changes.
PassiveFullColorRunDefaultPaletteCommand:
	call PassiveFullColorIsSliceMap
	jr nz, .yellow
	call PassiveFullColorReadActive
	cp 1
	jr nz, .yellow
	select_renderer_state_e
	ld a, 1
	ld [wPassiveFullColorBGPaletteProtected], a
	ld [wPassiveFullColorBGAttributesProtected], a
	restore_renderer_state_e
	call RunDefaultPaletteCommand
	select_renderer_state_e
	xor a
	ld [wPassiveFullColorBGPaletteProtected], a
	ld [wPassiveFullColorBGAttributesProtected], a
	restore_renderer_state_e
	ret
.yellow
	call RunDefaultPaletteCommand
	ret

PassiveFullColorShouldSuppressBGAttributesWrite:
	select_renderer_state_e
	ld a, [wPassiveFullColorBGAttributesProtected]
	ld b, a
	restore_renderer_state_e
	ld a, b
	and a
	ret z
	scf
	ret

; Central observation seam for Yellow-authored bank-1 packets. Forced menus
; suspend passive overlay projection until an explicit Start/Options resume;
; the base-map certificate remains dirty until final reconstruction.
PassiveFullColorObserveBGAttributesWrite:
	call PassiveFullColorReadActive
	cp 1
	ret nz
	jp PassiveFullColorInvalidateAttributes

; LoadCurrentMapView redisplays in the Pokecenter healing flow replace the
; complete 20x18 bank-0 picture. Publish matching attributes first, keep the
; window hidden through Yellow's stock three-frame sweep, then reveal once.
PassiveFullColorRedisplayMapView:
	call PassiveFullColorShouldColorOverlay
	jr nc, .yellow
	ld a, SCREEN_HEIGHT_PX
	ldh [hWY], a
	call PassiveFullColorInvalidateOverlayAttributes
	call PassiveFullColorPrepareMenuOverlay
	call Delay3
	xor a
	ldh [hWY], a
	ret
.yellow
	jp Delay3

; Attribute validity and overlay admission are distinct. A forced-Yellow
; full-screen presentation may overwrite bank 1 while the saved Color map
; remains active underneath; returned Start/Options overlays can resume before
; the base map is reconstructed on final close.
PassiveFullColorInvalidateAttributes:
	select_renderer_state_e
	ld a, 1
	ld [wPassiveFullColorAttributesInvalidated], a
	ld [wPassiveFullColorOverlaySuspended], a
	restore_renderer_state_e
	ret

; B=pending palette commit, C=remaining cleanup chunks. State lives in the
; passive renderer's private WRAM2 allocation; raw SVBK is always restored.
PassiveFullColorWriteState:
	select_renderer_state_e
	ld a, b
	ld [wPassiveFullColorPalettePending], a
	ld a, c
	ld [wPassiveFullColorClearChunks], a
	restore_renderer_state_e
	ret

; Overlay translation already runs with Yellow's WRAM1 selected. Avoid a
; redundant bank switch for every tile, then share the authored dispatch and
; override logic with redraw preparation.
PassiveFullColorAttributeForTileWRAM1:
	push hl
	push de
	push bc
	ld c, a
	ld a, [wCurMap]
	ld e, a
	ld a, [wCurMapTileset]
	ld h, a
	jp PassiveFullColorResolveAttributeForIdentity

; Party entry hook. Mark only an active slice; the close path performs the
; bounded restore after Yellow has rebuilt wTileMap.
PassiveFullColorScheduleAttributeRestore:
	call PassiveFullColorIsSliceMap
	ret nz
	call PassiveFullColorReadActive
	cp 1
	ret nz
	jp PassiveFullColorInvalidateAttributes

PassiveFullColorReadAttributesInvalidated:
	select_renderer_state_e
	ld a, [wPassiveFullColorAttributesInvalidated]
	ld b, a
	restore_renderer_state_e
	ld a, b
	ret

PassiveFullColorResumeOverlays:
	select_renderer_state_e
	xor a
	ld [wPassiveFullColorOverlaySuspended], a
	restore_renderer_state_e
	ret

PassiveFullColorCompleteAttributeRestore:
	call PassiveFullColorIsSliceMap
	ret nz
	call PassiveFullColorReadActive
	cp 1
	ret nz
	call PassiveFullColorWaitForRedrawSlot
	select_renderer_state_e
	xor a
	ld [wPassiveFullColorAttributesInvalidated], a
	ld [wPassiveFullColorOverlaySuspended], a
	restore_renderer_state_e
	ret

; Return the selected coordinate-region token in A and its roof identity in C.
; Maps without a coordinate rule return $ff. The fixed record count bounds the
; scan, and palette selection shares this exact authority with invalidation.
PassiveFullColorCurrentRoofRegion:
	push hl
	ld a, [wCurMap]
	ld c, a
	ld hl, FullColorOverworldRoofRegionRules
	ld b, NUM_FULL_COLOR_ROOF_REGION_RULES
.find
	ld a, [hli]
	cp c
	jr z, .matched
	inc hl
	inc hl
	inc hl
	dec b
	jr nz, .find
	ld a, $ff
	pop hl
	ret
.matched
	ld a, [wYCoord]
	cp [hl]
	inc hl
	ld a, 0
	jr c, .resolved
	inc hl
	inc a
.resolved
	ld c, [hl]
	pop hl
	ret

; Carry means the currently visible Route 6 region no longer matches the last
; authored palette commit and one bounded refresh must be queued.
PassiveFullColorRoofRegionChanged:
	call PassiveFullColorCurrentRoofRegion
	cp $ff
	jr z, .unchanged
	ld b, a
	select_renderer_state_e
	ld a, [wPassiveFullColorRoofRegion]
	ld c, a
	restore_renderer_state_e
	ld a, b
	cp c
	jr z, .unchanged
	scf
	ret
.unchanged
	and a
	ret

EXPORT PassiveFullColorLoadGBPal, PassiveFullColorUpdateCGBPal_BGPFade
EXPORT PassiveFullColorRunDefaultPaletteCommand
EXPORT PassiveFullColorShouldSuppressBGAttributesWrite
EXPORT PassiveFullColorObserveBGAttributesWrite, PassiveFullColorRedisplayMapView
EXPORT PassiveFullColorInvalidateAttributes, PassiveFullColorResumeOverlays
EXPORT PassiveFullColorRestoreInvalidatedPalettes
EXPORT PassiveFullColorCompleteAttributeRestore, PassiveFullColorRoofRegionChanged
EXPORT PassiveFullColorScheduleAttributeRestore

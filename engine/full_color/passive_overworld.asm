; Shipped passive CGB coloring for the authored overworld/interior slice.
;
; Yellow remains authoritative for tiles, OAM, timing, overlays, fades, and
; mechanics. This code writes only BG palette RAM and VRAM bank 1 attributes.

; Called during ownership boot with WRAM2 already selected. Explicitly clear
; every persistent passive field so random power-on WRAM cannot impersonate a
; loaded Pallet Town before Yellow has completed a real map publication.
InitPassiveFullColorStateSelected:
	xor a
	ld hl, wPassiveFullColorStateStart
	ld b, wPassiveFullColorAttributeRectangle - wPassiveFullColorStateStart
.clear
	ld [hli], a
	dec b
	jr nz, .clear
	ld [wPassiveFullColorDeferredRedrawState], a
	ret

PassiveFullColorIsSliceMap:
	ld a, [wUnusedObtainedBadges]
	bit BIT_FULL_COLOR_YELLOW_MODE, a
	ret nz

; Presentation stays latched while a Start/Options overlay is open. The saved
; preference is reconciled only when the outer overlay closes or a map loads.
PassiveFullColorIsPresentedSliceMap:
	ld a, [wCurMapTileset]
	cp OVERWORLD
	jr z, .overworld
	cp REDS_HOUSE_1
	jr c, .ineligible
	cp FACILITY + 1
	jr nc, .ineligible
	cp FOREST
	jr z, .ineligible
	cp SHIP_PORT
	jr z, .ineligible
	cp CAVERN
	jr z, .ineligible
	xor a
	ret
.overworld
	ld a, [wCurMap]
	cp NUM_CITY_MAPS
	jr c, .eligible
	cp FIRST_ROUTE_MAP
	jr c, .ineligible
	cp FIRST_INDOOR_MAP
	jr c, .eligible
.ineligible
	ld a, 1
	and a
	ret
.eligible
	xor a
	ret

; Called with the LCD disabled after Yellow's complete ordinary map setup.
PassiveFullColorApplyMap:
	call PassiveFullColorIsSliceMap
	jr z, .apply
	call PassiveFullColorClearState
	xor a
	call PassiveFullColorWriteActive
	call PassiveFullColorClearBGMapAttributes
	ret
.apply
	call PassiveFullColorClearState
	ld a, 1
	call PassiveFullColorWriteActive
	call PassiveFullColorCommitPalettes
	jp PassiveFullColorCommitVisibleAttributes

; Seamless connections happen with the LCD active. Palette installation and
; any bank-1 cleanup are therefore deferred to bounded VBlank work.
PassiveFullColorHandleConnection:
	call PassiveFullColorIsSliceMap
	jr z, .enter
	ld bc, $320 ; homogenize first, then clear thirty-two 32-byte chunks
	call PassiveFullColorWriteState
	xor a
	call PassiveFullColorWriteActive
	ret
.enter
	ld bc, $100
	call PassiveFullColorWriteState
	ld a, 1
	call PassiveFullColorWriteActive
	ret

PUSHS
SECTION "Passive Full Color Bounded Helpers", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

; Yellow's tile source remains authoritative; translation happens outside
; VBlank. The fixed extent is loaded here because farcall consumes B.
PassiveFullColorPrepareRedrawAttributes:
	call PassiveFullColorIsSliceMap
	ret nz
	call PassiveFullColorReadActive
	cp 1
	ret nz
	call PassiveFullColorWaitForRedrawSlot
	select_renderer_state_e
	ld hl, wRedrawRowOrColumnSrcTiles
	ld de, wPassiveFullColorRedrawStaging
	ldh a, [hRedrawRowOrColumnDest]
	ld c, a
	ldh a, [hRedrawRowOrColumnDest + 1]
	ld b, a
	push bc
	call .prepare_row
	pop bc
	ld a, TILEMAP_WIDTH
	add c
	ld c, a
	call .prepare_row
	ld a, $80 | REDRAW_ROW
	ld [wPassiveFullColorDeferredRedrawState], a
	restore_renderer_state_e
	ret
.prepare_row
	ld a, SCREEN_WIDTH / 2
.pair
	push af
	ld a, c
	ld [de], a
	inc de
	ld a, b
	ld [de], a
	inc de
	ld a, [hli]
	call PassiveFullColorAttributeForTile
	ld [de], a
	inc de
	ld a, [hli]
	call PassiveFullColorAttributeForTile
	ld [de], a
	inc de
	ld a, c
	add 2
	and %11111
	push af
	ld a, c
	and %11100000
	ld c, a
	pop af
	or c
	ld c, a
	pop af
	dec a
	jr nz, .pair
	ret

; Column geometry is frozen outside VBlank as 18 records containing destination
; low/high followed by two translated attributes. The bounded consumer then has
; no per-row address arithmetic in the visible critical section.
PassiveFullColorPrepareColumnAttributes:
	call PassiveFullColorIsSliceMap
	ret nz
	call PassiveFullColorReadActive
	cp 1
	ret nz
	call PassiveFullColorWaitForRedrawSlot
	select_renderer_state_e
	ld hl, wRedrawRowOrColumnSrcTiles
	ld de, wPassiveFullColorRedrawStaging
	ldh a, [hRedrawRowOrColumnDest]
	ld c, a
	ldh a, [hRedrawRowOrColumnDest + 1]
	ld b, a
	ld a, SCREEN_HEIGHT
.row
	push af
	ld a, c
	ld [de], a
	inc de
	ld a, b
	ld [de], a
	inc de
	ld a, [hli]
	call PassiveFullColorAttributeForTile
	ld [de], a
	inc de
	ld a, [hli]
	call PassiveFullColorAttributeForTile
	ld [de], a
	inc de
	ld a, TILEMAP_WIDTH
	add c
	ld c, a
	jr nc, .normalize
	inc b
.normalize
	ld a, b
	and HIGH(TILEMAP_AREA - 1)
	or HIGH(vBGMap0)
	ld b, a
	pop af
	dec a
	jr nz, .row
	ld a, $80 | REDRAW_COL
	ld [wPassiveFullColorDeferredRedrawState], a
	restore_renderer_state_e
	ret

; Color-to-Yellow menu close must retire donor attributes before LoadGBPal can
; install Yellow palettes. Yellow's whole-screen GDMA packet clears both bank-1
; maps during safe video periods, matching the established battle handoff.
PassiveFullColorPrepareMenuHandoff:
	call PassiveFullColorIsSliceMap
	ret z
	call PassiveFullColorShouldColorOverlay
	ret nc
	call PassiveFullColorClearState
	xor a
	call PassiveFullColorWriteActive
	ld c, 12 ; BGMapAttributes_WholeScreen
	jpfar LoadBGMapAttributes

; Menu/dialogue close hook, called after Yellow's LoadCurrentMapView and
; LoadGBPal. Never blank the live LCD. An already-active Color presentation
; needs only a palette refresh. Activating Color from Yellow first translates
; Yellow's finalized wTileMap outside VBlank, then holds this close path until
; a bounded live-LCD transaction has published all 20x18 attributes.
PassiveFullColorRestoreAfterMenu:
	call PassiveFullColorIsSliceMap
	jr nz, .yellow
	ld a, [wIsInBattle]
	and a
	jr nz, .battle_owned
	call PassiveFullColorReadActive
	cp 1
	jr nz, .activate_color
	; Any Yellow attribute packet invalidates the base-map certificate. Keep
	; Color latched through a returned Start overlay, then rebuild the complete
	; visible plane when the outer menu finally closes.
	call PassiveFullColorReadAttributesInvalidated
	and a
	jr nz, .activate_color
	call PassiveFullColorClearState
	ldh a, [rLCDC]
	bit B_LCDC_ENABLE, a
	jr nz, .schedule_color
	call PassiveFullColorCommitPalettes
	jp PassiveFullColorCommitVisibleAttributes
.schedule_color
	ld bc, $100
	jp PassiveFullColorWriteState
.activate_color
	call PassiveFullColorClearState
	xor a
	call PassiveFullColorWriteActive
	ldh a, [rLCDC]
	bit B_LCDC_ENABLE, a
	jr nz, .prepare_activation
	call PassiveFullColorCommitPalettes
	call PassiveFullColorCommitVisibleAttributes
	ld a, 1
	jp PassiveFullColorWriteActive
.prepare_activation
	call PassiveFullColorTranslateTileMap
	ld bc, $412 ; neutralize, then publish eighteen rows
	call PassiveFullColorWriteState
	ld b, 12 ; one bounded spare frame beyond the eleven-step transaction
.wait
	push bc
	call DelayFrame
	call PassiveFullColorReadActive
	cp 1
	pop bc
	ret z
	dec b
	jr nz, .wait
	ret
.battle_owned
	call PassiveFullColorClearState
	xor a
	jp PassiveFullColorWriteActive
.yellow
	ld b, SET_PAL_OVERWORLD
	call RunPaletteCommand
	call PassiveFullColorClearState
	xor a
	call PassiveFullColorWriteActive
	ldh a, [rLCDC]
	bit B_LCDC_ENABLE, a
	jp z, PassiveFullColorClearBGMapAttributes
	ld bc, $320
	jp PassiveFullColorWriteState

POPS

; A=active. An explicit bit prevents the power-on wCurMap value (Pallet's ID
; is zero) from coloring the intro before a real Yellow map load completes.
PassiveFullColorWriteActive:
	ld b, a
	select_renderer_state_e
	ld a, b
	ld [wPassiveFullColorActive], a
	ld a, [wRendererGeneration]
	ld [wPassiveFullColorGeneration], a
	restore_renderer_state_e
	ret

PassiveFullColorReadActive:
	select_renderer_state_e
	ld a, [wPassiveFullColorActive]
	ld b, a
	ld a, [wPassiveFullColorGeneration]
	ld c, a
	ld a, [wRendererGeneration]
	cp c
	jr z, .generation_ok
	xor a
	ld b, a
	ld [wPassiveFullColorActive], a
	ld [wPassiveFullColorPalettePending], a
	ld [wPassiveFullColorClearChunks], a
	ld [wPassiveFullColorBGPaletteProtected], a
	ld [wPassiveFullColorBGAttributesProtected], a
	ld [wPassiveFullColorAttributesInvalidated], a
	ld [wPassiveFullColorOverlaySuspended], a
.generation_ok
	ld a, [wPassiveFullColorPalettePending]
	ld c, a
	ld a, [wPassiveFullColorClearChunks]
	ld e, a
	restore_renderer_state_e
	ld a, b
	ret

PUSHS
SECTION "Passive Full Color Redraw Admission", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

; One bounded redraw record set owns this slot from preparation through its
; bank-1 commit. The hold normally lasts two VBlanks: Yellow publishes bank 0
; first, then the passive mirror consumes the following redraw-free frame.
; Admission backpressure prevents a second scroll producer from replacing the
; frozen records in between.
PassiveFullColorWaitForRedrawSlot:
.wait
	select_renderer_state_e
	ld a, [wPassiveFullColorDeferredRedrawState]
	ld b, a
	restore_renderer_state_e
	ld a, b
	and a
	ret z
	call DelayFrame
	jr .wait

POPS

PUSHS
SECTION "Passive Full Color State Reset", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

PassiveFullColorClearState:
	xor a
	ld b, a
	ld c, a
	call PassiveFullColorWriteState
	select_renderer_state_e
	xor a
	ld [wPassiveFullColorDeferredRedrawState], a
	ld [wPassiveFullColorBGPaletteProtected], a
	ld [wPassiveFullColorBGAttributesProtected], a
	ld [wPassiveFullColorAttributesInvalidated], a
	ld [wPassiveFullColorOverlaySuspended], a
	restore_renderer_state_e
	ldh a, [hAutoBGTransferEnabled]
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_FINITE_SWEEP, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_STOCK_SWEEP, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_ATTRIBUTE_GDMA, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_COMPLETE, a
	ldh [hAutoBGTransferEnabled], a
	xor a
	ldh [hAutoBGTransferPortion], a
	ret

POPS

; Battles remain wholly Yellow-owned. Relinquish the passive overlay before
; the stock palette command waits for safe video access and replaces both
; bank-1 BG maps, so no transition frame can combine the two authorities.
PassiveFullColorPrepareBattleHandoff:
	call PassiveFullColorShouldColorOverlay
	ret nc
	call PassiveFullColorClearState
	xor a
	call PassiveFullColorWriteActive
	; RunPaletteCommand installs palettes before its attribute packet. Clear the
	; two maps first while the complete donor palette is still coherent, so its
	; LCD-safe waits cannot expose stock colors through stale donor attributes.
	ld c, 12 ; BGMapAttributes_WholeScreen
	farcall LoadBGMapAttributes
	ld b, SET_PAL_OVERWORLD
	jp RunPaletteCommand

PUSHS
SECTION "Passive Full Color Window Transfer", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

; hAutoBGTransferEnabled bit 7 owns one aligned attribute GDMA, bit 5 latches
; the coherent plane, bit 4 owns a stock three-frame bank-0 sweep, and bit 3
; makes that sweep finite for menus.

; Carry means the active supported Color slice owns bank-1 attributes for this
; overlay. Yellow mode and every other scene remain on the stock path.
PassiveFullColorShouldColorOverlay:
	call PassiveFullColorIsPresentedSliceMap
	jr nz, .inactive
	call PassiveFullColorReadActive
	cp 1
	jr nz, .inactive
	select_renderer_state_e
	ld a, [wPassiveFullColorOverlaySuspended]
	ld b, a
	restore_renderer_state_e
	ld a, b
	and a
	jr nz, .inactive
	scf
	ret
.inactive
	and a
	ret

; The completion latch certifies only the current structural window contents.
; Call this after Yellow replaces a dialogue/menu window and before preparing its
; overlay. Cursor-only updates keep the latch and use the completed fast path.
PassiveFullColorInvalidateOverlayAttributes:
	ldh a, [hAutoBGTransferEnabled]
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_COMPLETE, a
	ldh [hAutoBGTransferEnabled], a
	ret

; Translate Yellow's finalized 20x18 window tilemap once outside VBlank. A fresh
; hidden plane uses one dedicated attribute-GDMA frame, then callers' established
; Delay3 runs Yellow's unchanged stock six-row sweep before reveal. A coherent
; plane returns immediately, so cursor movement retains only the stock sweep.
PassiveFullColorPrepareMenuOverlay:
	call PassiveFullColorShouldColorOverlay
	jr nc, PassiveFullColorPrepareOverlayInactive
	ldh a, [hAutoBGTransferEnabled]
	set BIT_PASSIVE_FULL_COLOR_OVERLAY_FINITE_SWEEP, a
	ldh [hAutoBGTransferEnabled], a
	jr PassiveFullColorPrepareOverlay

; Dialogue needs Yellow's continuous tile publication while letters print. It
; yields every fourth VBlank so OAM and queued video writers cannot starve.
PassiveFullColorPrepareTextOverlay:
	call PassiveFullColorShouldColorOverlay
	jr nc, PassiveFullColorPrepareOverlayInactive
	call PassiveFullColorInvalidateOverlayAttributes
	ldh a, [hAutoBGTransferEnabled]
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_FINITE_SWEEP, a
	ldh [hAutoBGTransferEnabled], a
PassiveFullColorPrepareOverlay:
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_COMPLETE, a
	jr nz, .armStockSweep
	call PassiveFullColorTranslateTileMap
	xor a
	ldh [hAutoBGTransferPortion], a
	ldh a, [hAutoBGTransferEnabled]
	set BIT_PASSIVE_FULL_COLOR_OVERLAY_ATTRIBUTE_GDMA, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_STOCK_SWEEP, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_COMPLETE, a
	ldh [hAutoBGTransferEnabled], a
	call DelayFrame
	scf
	ret
.armStockSweep
	xor a
	ldh [hAutoBGTransferPortion], a
	ldh a, [hAutoBGTransferEnabled]
	set BIT_PASSIVE_FULL_COLOR_OVERLAY_STOCK_SWEEP, a
	set 0, a
	ldh [hAutoBGTransferEnabled], a
	scf
	ret
PassiveFullColorPrepareOverlayInactive:
	ldh a, [hAutoBGTransferEnabled]
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_FINITE_SWEEP, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_STOCK_SWEEP, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_ATTRIBUTE_GDMA, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_COMPLETE, a
	ldh [hAutoBGTransferEnabled], a
	xor a
	ldh [hAutoBGTransferPortion], a
	ret

PassiveFullColorTranslateTileMap:
	; The Yellow stack is in switchable WRAM1, so interrupts cannot remain
	; admitted while WRAM2 is selected. Resolve each attribute with WRAM1
	; present, then mask only its bounded store into the WRAM2 plane.
	ld hl, wTileMap
	ld de, wPassiveFullColorAttributeRectangle
	ld b, SCREEN_HEIGHT
.row
	ld c, SCREEN_WIDTH
.translate_tile
	ld a, [hli]
	call PassiveFullColorAttributeForTileWRAM1
	push bc
	ld b, a
	select_renderer_state_e
	ld a, b
	ld [de], a
	restore_renderer_state_e
	pop bc
	inc de
	dec c
	jr nz, .translate_tile
	push bc
	select_renderer_state_e
	ld b, TILEMAP_WIDTH - SCREEN_WIDTH
	xor a
.pad_row
	ld [de], a
	inc de
	dec b
	jr nz, .pad_row
	restore_renderer_state_e
	pop bc
	dec b
	jr nz, .row
	ret

; VBlank entry for initial overlay attributes. The padded and aligned WRAM2
; plane maps directly onto one 32x18 VRAM region, so one dedicated GDMA can
; publish it without mixing an attribute writer with Yellow's tile sweep.
PassiveFullColorOverlayAttributeGDMA:
	ldh a, [hAutoBGTransferEnabled]
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_ATTRIBUTE_GDMA, a
	ret z
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_COMPLETE, a
	jr nz, .abort
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_STOCK_SWEEP, a
	jr nz, .abort
	ldh a, [hAutoBGTransferPortion]
	and a
	jr nz, .abort
	ldh a, [hAutoBGTransferDest]
	and a
	jr nz, .abort
	ldh a, [hAutoBGTransferDest + 1]
	cp HIGH(vBGMap0)
	jr z, .commit
	cp HIGH(vBGMap1)
	jr nz, .abort
.commit
	ld a, PASSIVE_FULL_COLOR_WRAM_BANK
	ldh [rSVBK], a
	ld a, 1
	ldh [rVBK], a
	ld a, HIGH(wPassiveFullColorAttributeRectangle)
	ldh [rVDMA_SRC_HIGH], a
	ld a, LOW(wPassiveFullColorAttributeRectangle)
	ldh [rVDMA_SRC_LOW], a
	ldh a, [hAutoBGTransferDest + 1]
	ldh [rVDMA_DEST_HIGH], a
	ldh a, [hAutoBGTransferDest]
	ldh [rVDMA_DEST_LOW], a
	ld a, PASSIVE_FULL_COLOR_ATTRIBUTE_GDMA_BLOCKS - 1
	ldh [rVDMA_LEN], a
	ld a, 1
	ldh [rSVBK], a
	xor a
	ldh [rVBK], a
	ldh [hAutoBGTransferPortion], a
	ldh a, [hAutoBGTransferEnabled]
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_ATTRIBUTE_GDMA, a
	set BIT_PASSIVE_FULL_COLOR_OVERLAY_COMPLETE, a
	set BIT_PASSIVE_FULL_COLOR_OVERLAY_STOCK_SWEEP, a
	set 0, a
	ldh [hAutoBGTransferEnabled], a
	scf
	ret
.abort
	xor a
	ldh [hAutoBGTransferPortion], a
	ldh a, [hAutoBGTransferEnabled]
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_FINITE_SWEEP, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_STOCK_SWEEP, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_ATTRIBUTE_GDMA, a
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_COMPLETE, a
	res 0, a
	ldh [hAutoBGTransferEnabled], a
	scf
	ret

; Carry returns VBlank to its ordinary visible writers. A completed dialogue
; runs three stock chunks followed by one such recovery frame; a menu runs one
; finite three-chunk sweep, disables bit 0, then stays on ordinary frames.
PassiveFullColorCompletedOverlayVBlank:
	ldh a, [hAutoBGTransferEnabled]
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_STOCK_SWEEP, a
	jr nz, .stock
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_FINITE_SWEEP, a
	jr nz, .stock
	bit 0, a
	jr z, .ordinary
	; Continuous dialogue reached its recovery frame. Arm the next sweep, but
	; leave this frame to queued video work and OAM preparation.
	set BIT_PASSIVE_FULL_COLOR_OVERLAY_STOCK_SWEEP, a
	ldh [hAutoBGTransferEnabled], a
	call VBlankCopyBgMap
	scf
	ret
.stock
	call AutoBgMapTransfer
	ldh a, [hAutoBGTransferPortion]
	and a
	jr nz, .consumed
	ldh a, [hAutoBGTransferEnabled]
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_STOCK_SWEEP, a
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_FINITE_SWEEP, a
	jr z, .store
	res BIT_PASSIVE_FULL_COLOR_OVERLAY_FINITE_SWEEP, a
	res 0, a
.store
	ldh [hAutoBGTransferEnabled], a
.consumed
	and a
	ret
.ordinary
	call VBlankCopyBgMap
	scf
	ret

POPS

; Runs after Yellow's RedrawRowOrColumn. It never replaces or suppresses the
; bank-0 write. A consumed redraw becomes a bank-1 commit for the next idle
; VBlank so each frame retains the complete Yellow interrupt tail.
PassiveFullColorVBlank:
	; Initial overlay publication already consumed this frame's one visible
	; operation. Once complete, Yellow's stock bank-0 transfer owns presentation;
	; keep ordinary passive palette/redraw work out until the overlay closes.
	ldh a, [hAutoBGTransferEnabled]
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_ATTRIBUTE_GDMA, a
	ret nz
	bit BIT_PASSIVE_FULL_COLOR_OVERLAY_COMPLETE, a
	ret nz
	ld h, d ; freeze Yellow's consumed redraw mode without touching the stack
	; VBlank has IME clear and its prologue selected Yellow's WRAM1 stack.
	; Read WRAM2 stacklessly, then restore bank 1 before any pop or return.
	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	ld a, [wPassiveFullColorActive]
	ld b, a
	ld a, [wPassiveFullColorGeneration]
	ld c, a
	ld a, [wRendererGeneration]
	cp c
	jr z, .generation_ok
	xor a
	ld b, a
	ld [wPassiveFullColorActive], a
	ld [wPassiveFullColorPalettePending], a
	ld [wPassiveFullColorClearChunks], a
	ld [wPassiveFullColorDeferredRedrawState], a
	ld [wPassiveFullColorBGPaletteProtected], a
	ld [wPassiveFullColorBGAttributesProtected], a
	ld [wPassiveFullColorAttributesInvalidated], a
	ld [wPassiveFullColorOverlaySuspended], a
.generation_ok
	ld a, [wPassiveFullColorPalettePending]
	ld c, a
	ld a, [wPassiveFullColorClearChunks]
	ld e, a
	ld a, [wPassiveFullColorDeferredRedrawState]
	ld l, a
	ld a, 1
	ldh [rSVBK], a
	ld a, b
	dec a
	jr nz, .inactive
	call PassiveFullColorIsPresentedSliceMap
	jr nz, .inactive
.slice
	ld d, h
	ld a, d
	cp REDRAW_ROW
	jp z, PassiveFullColorScheduleRedrawMirror
	cp REDRAW_COL
	jp z, PassiveFullColorScheduleRedrawMirror
	ld a, l
	cp REDRAW_ROW
	jp z, PassiveFullColorCommitRedrawRow
	cp REDRAW_COL
	jp z, PassiveFullColorCommitRedrawColumn
	; A redraw owns this frame. A pending palette remains queued for the next
	; redraw-free VBlank instead of combining two bounded operations.
	ld a, c
	cp 2
	ret z
	and a
	ret z
	ld b, 0
	ld c, 0
	call PassiveFullColorWriteState
	jp PassiveFullColorCommitPalettes
.inactive
	ld a, c
	cp 4
	jp nc, PassiveFullColorActivationVBlank
	cp 3
	jr nz, .clear
	ld c, e
	ld b, 0
	call PassiveFullColorWriteState
	jp PassiveFullColorHomogenizeBGPalettes
.clear
	ld a, e
	ld c, a
	ld a, c
	and a
	ret z
	cp 33
	jr c, .bounded_clear
	; Timing scratch is aliased but may contain pre-activation scheduler bytes.
	; Reject anything outside the only authored exit range before SP targets VRAM.
	call PassiveFullColorClearState
	ret
.bounded_clear
	jp PassiveFullColorClearBGMapChunk

; LCD must be off or the caller must be in VBlank.
PUSHS
SECTION "Passive Full Color Map Palettes", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

; Select the complete authored palette payload for the current admitted tileset.
; Callers have already passed PassiveFullColorIsSliceMap. Returns HL at byte 0;
; clobbers A and BC. All callers are in this bank and use a direct call.
PassiveFullColorSelectBGPalettePayload:
	ld a, [wCurMapTileset]
	add a
	ld c, a
	ld b, 0
	ld hl, FullColorBGPalettePointers
	add hl, bc
	ld a, [hli]
	ld h, [hl]
	ld l, a
	ret

PassiveFullColorCommitPalettes:
	ld a, $80
	ldh [rBGPI], a
	call PassiveFullColorSelectBGPalettePayload
	ld a, [wCurMapTileset]
	and a
	jr z, .overworld
	ld b, 8 * 4 * 2
.interior
	ld a, [hli]
	ldh [rBGPD], a
	dec b
	jr nz, .interior
	jr PassiveFullColorRecordPalettePublished
.overworld
	ld b, 6 * 4 * 2 + 2 ; palettes 0-5 and roof color 0
.prefix
	ld a, [hli]
	ldh [rBGPD], a
	dec b
	jr nz, .prefix
	call PassiveFullColorRoofPaletteForMap
	ld b, 2 * 2
.roof
	ld a, [hli]
	ldh [rBGPD], a
	dec b
	jr nz, .roof
	ld hl, FullColorOverworldBGPalettes + 6 * 4 * 2 + 3 * 2
	ld b, 2 + 4 * 2 ; roof color 3 and palette 7
.suffix
	ld a, [hli]
	ldh [rBGPD], a
	dec b
	jr nz, .suffix

PassiveFullColorRecordPalettePublished:
	; This authored payload supersedes every Yellow publication observed so far.
	call PassiveFullColorCurrentRoofRegion
	ld b, a
	select_renderer_state_e
	xor a
	ld [wPassiveFullColorPaletteInvalidated], a
	ld a, b
	ld [wPassiveFullColorRoofRegion], a
	restore_renderer_state_e
	ret

; Select the donor's two authored roof colors for the current town or route.
; The caller has already admitted an OVERWORLD map, so its ID is below the
; indoor boundary. A coordinate-dependent rule supplies its exact roof byte;
; every other map uses the reviewed positional assignment.
PassiveFullColorRoofPaletteForMap:
	call PassiveFullColorCurrentRoofRegion
	cp $ff
	ld a, c
	jr nz, .resolve
	ld a, [wCurMap]
	cp FIRST_INDOOR_MAP
	jr nc, .pallet
.assigned
	ld c, a
	ld b, 0
	ld hl, FullColorOverworldRoofAssignments
	add hl, bc
	ld a, [hl]
	jr .resolve
.pallet
	xor a
.resolve
	add a
	add a
	ld c, a
	ld b, 0
	ld hl, FullColorOverworldRoofPalettes
	add hl, bc
	ret

POPS

; Translate tile A through the current tileset's donor-authored 256-byte table.
; Preserves DE, returns the attribute in A.
PUSHS
SECTION "Passive Full Color Tile Dispatch", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

PassiveFullColorAttributeForTile:
	push hl
	push de
	push bc
	ld c, a
	; Redraw preparation keeps WRAM2 selected, while Yellow's map identity is
	; in WRAM1. Read both identities under a bounded, interrupt-closed bank
	; switch, restoring the raw caller state before touching the stack again.
	ldh a, [rIE]
	ld b, a
	xor a
	ldh [rIE], a
	ldh a, [rSVBK]
	ld d, a
	ld a, 1
	ldh [rSVBK], a
	ld a, [wCurMap]
	ld e, a
	ld a, [wCurMapTileset]
	ld h, a
	ld a, d
	ldh [rSVBK], a
	ld a, b
	ldh [rIE], a
PassiveFullColorResolveAttributeForIdentity:
	push hl ; Preserve the tileset identity in H while HL scans override data.
	ld hl, FullColorMapAttributeOverrides
	ld b, NUM_FULL_COLOR_MAP_ATTRIBUTE_OVERRIDE_GROUPS
.override_group
	ld a, [hli]
	cp e
	jr z, .matching_map
	ld a, [hli]
	inc hl ; Skip the exact override byte before the tile identity sequence.
	add l
	ld l, a
	jr nc, .next_override_group
	inc h
.next_override_group
	dec b
	jr nz, .override_group
	jr .lookup
.matching_map
	ld a, [hli]
	ld b, a
	ld a, [hli]
	ld e, a
.override_tile
	ld a, [hli]
	cp c
	jr z, .override
	dec b
	jr nz, .override_tile
	jr .lookup
.override
	ld a, e
	pop hl
	jr .done
.lookup
	pop hl
	ld a, h
	add a
	ld e, a
	ld d, 0
	ld hl, FullColorTileAttributePointers
	add hl, de
	ld a, [hli]
	ld h, [hl]
	ld l, a
	ld b, 0 ; B previously held the saved interrupt mask; BC is now a tile offset.
	add hl, bc
	ld a, [hl]
.done
	pop bc
	pop de
	pop hl
	ret

POPS

; LCD-off map path: mirror the complete bank-0 tilemap address-for-address.
; This covers both ordinary entries and scrolled seamless connections without
; guessing where wTileMap's visible window currently lands in VRAM.
PassiveFullColorCommitVisibleAttributes:
	ld hl, vBGMap0
	ld bc, TILEMAP_AREA
.loop
	xor a
	ldh [rVBK], a
	ld a, [hl]
	call PassiveFullColorAttributeForTile
	ld d, a
	ld a, 1
	ldh [rVBK], a
	ld [hl], d
	inc hl
	dec bc
	ld a, b
	or c
	jr nz, .loop
	; LoadMapData immediately streams player graphics after this hook. Its
	; established postcondition is VRAM bank 0, regardless of whatever a
	; palette command happened to leave selected on entry.
	xor a
	ldh [rVBK], a
	ret

PUSHS
SECTION "Passive Full Color Redraw Commits", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

; The producer marks a prepared record with bit 7. Yellow's bank-0 redraw
; consumes this frame; convert that marker to a low-valued bank-1 pending mode
; for the next VBlank. A redraw without a matching passive record remains
; wholly Yellow-owned.
PassiveFullColorScheduleRedrawMirror:
	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	ld a, [wPassiveFullColorDeferredRedrawState]
	ld b, a
	and $7f
	cp d
	jr nz, .restore
	bit 7, b
	jr z, .restore
	ld a, d
	ld [wPassiveFullColorDeferredRedrawState], a
.restore
	ld a, 1
	ldh [rSVBK], a
	ret

PassiveFullColorCommitRedrawColumn:
	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	xor a
	ld [wPassiveFullColorDeferredRedrawState], a
	ld a, 1
	ldh [rVBK], a
	ld hl, wPassiveFullColorRedrawStaging
	REPT SCREEN_HEIGHT
		ld a, [hli]
		ld e, a
		ld a, [hli]
		ld d, a
		ld a, [hli]
		ld [de], a
		inc e
		ld a, [hli]
		ld [de], a
	ENDR
	ld a, 1
	ldh [rSVBK], a
	xor a
	ldh [rVBK], a
	ret

PassiveFullColorCommitRedrawRow:
	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	xor a
	ld [wPassiveFullColorDeferredRedrawState], a
	ld a, 1
	ldh [rVBK], a
	ld hl, wPassiveFullColorRedrawStaging
	REPT SCREEN_WIDTH
		ld a, [hli]
		ld e, a
		ld a, [hli]
		ld d, a
		ld a, [hli]
		ld [de], a
		inc e
		ld a, [hli]
		ld [de], a
	ENDR
	ld a, 1
	ldh [rSVBK], a
	xor a
	ldh [rVBK], a
	ret

POPS

PUSHS
SECTION "Passive Full Color Activation Barrier", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

PassiveFullColorActivationVBlank:
	cp 4
	jr z, .neutralize
	cp 5
	jr z, .rows
	cp 6
	jr nz, .abort
	call PassiveFullColorValidateActivation
	jr nc, .abort
	jp PassiveFullColorCommitActivation
.neutralize
	call PassiveFullColorValidateActivation
	jr nc, .abort
	ld b, 5
	ld c, e
	call PassiveFullColorWriteState
	jp PassiveFullColorHomogenizeBGPalettes
.rows
	call PassiveFullColorValidateActivation
	jr nc, .abort
	jp PassiveFullColorCommitActivationRows
.abort
	call PassiveFullColorClearState
	ret

; Carry means an inactive live-LCD activation may continue. The saved option
; cannot change while RestoreAfterMenu is blocking, so admission is bound to
; generation-validated transaction state, map identity, and battle ownership.
PassiveFullColorValidateActivation:
	ld a, [wIsInBattle]
	and a
	jr nz, .invalid
	call PassiveFullColorIsPresentedSliceMap
	jr nz, .invalid
	scf
	ret
.invalid
	and a
	ret

; Publish two translated visible rows per VBlank. wPassiveFullColorClearChunks
; carries the remaining row count (18, 16, ... 2) during this transaction.
PassiveFullColorCommitActivationRows:
	ld a, SCREEN_HEIGHT
	sub e
	push af
	call PassiveFullColorCommitActivationRow
	pop af
	inc a
	call PassiveFullColorCommitActivationRow

	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	ld a, [wPassiveFullColorClearChunks]
	sub 2
	ld [wPassiveFullColorClearChunks], a
	jr nz, .restore
	ld a, 6
	ld [wPassiveFullColorPalettePending], a
.restore
	ld a, 1
	ldh [rSVBK], a
	ret

; A=row (0..17). Resolve both axes independently on Yellow's 32x32 torus:
; vertical addition wraps at $9bff and horizontal increments wrap within the
; same row instead of spilling into the next one.
PassiveFullColorCommitActivationRow:
	push af
	ld a, [wMapViewVRAMPointer]
	ld e, a
	ld a, [wMapViewVRAMPointer + 1]
	ld d, a
	pop af
	push af
	ld c, a
.advance_row
	ld a, c
	and a
	jr z, .destination_ready
	ld a, TILEMAP_WIDTH
	add e
	ld e, a
	jr nc, .no_carry
	inc d
.no_carry
	dec c
	jr .advance_row
.destination_ready
	ld a, d
	and HIGH(TILEMAP_AREA - 1)
	or HIGH(vBGMap0)
	ld d, a

	; Convert the row to the hardware-shaped 32-byte scratch offset.
	pop af
	ld l, a
	ld h, 0
	REPT 5
		add hl, hl
	ENDR
	ld bc, wPassiveFullColorAttributeRectangle
	add hl, bc
	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	ld a, 1
	ldh [rVBK], a
	ld a, e
	and %11111
	ld c, a
	add SCREEN_WIDTH
	cp TILEMAP_WIDTH + 1
	jr nc, .split_copy
	ld b, SCREEN_WIDTH
.copy_one_segment
	ld a, [hli]
	ld [de], a
	inc e
	dec b
	jr nz, .copy_one_segment
	jr .copy_done
.split_copy
	ld a, TILEMAP_WIDTH
	sub c
	ld b, a
.copy_before_wrap
	ld a, [hli]
	ld [de], a
	inc e
	dec b
	jr nz, .copy_before_wrap
	ld a, e
	sub TILEMAP_WIDTH
	ld e, a
	ld a, c
	sub TILEMAP_WIDTH - SCREEN_WIDTH
	ld b, a
.copy_after_wrap
	ld a, [hli]
	ld [de], a
	inc e
	dec b
	jr nz, .copy_after_wrap
.copy_done
	ld a, 1
	ldh [rSVBK], a
	xor a
	ldh [rVBK], a
	ret

; Palettes are committed only after every visible attribute row is complete.
; Set active in the same later bounded VBlank so no mixed presentation exists.
PassiveFullColorCommitActivation:
	call PassiveFullColorCommitPalettes
	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	ld a, 1
	ld [wPassiveFullColorActive], a
	xor a
	ld [wPassiveFullColorPalettePending], a
	ld [wPassiveFullColorClearChunks], a
	ld a, 1
	ldh [rSVBK], a
	ret

POPS

PUSHS
SECTION "Passive Full Color Exit Barrier", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

; VBlank-only exit barrier. Read each color from palette 0 and duplicate it
; across palettes 1-7, so any uncleared attribute selects identical colors.
PassiveFullColorHomogenizeBGPalettes:
	ldh a, [rBGPI]
	push af
	ld b, 0 ; palette-0 byte index, advanced two bytes per color
.color
	ld a, b
	ldh [rBGPI], a
	ldh a, [rBGPD]
	ld d, a
	ld a, b
	inc a
	ldh [rBGPI], a
	ldh a, [rBGPD]
	ld e, a
	ld c, 1
.palette
	ld a, c
	add a
	add a
	add a
	add b
	or $80
	ldh [rBGPI], a
	ld a, d
	ldh [rBGPD], a
	ld a, e
	ldh [rBGPD], a
	inc c
	bit 3, c
	jr z, .palette
	inc b
	inc b
	ld a, b
	cp 8
	jr nz, .color
	pop af
	ldh [rBGPI], a
	ret

POPS

; LCD-off cleanup for door/warp exits. Clear the complete BG map bank so no
; stale attribute survives into an unrelated Yellow scene.
PassiveFullColorClearBGMapAttributes:
	ld a, 1
	ldh [rVBK], a
	ld hl, vBGMap0
	ld bc, TILEMAP_AREA
	xor a
	call FillMemory
	xor a
	ldh [rVBK], a
	ret

; Seamless exits amortize the same complete clear over 32 VBlanks. The plain
; bounded loop is deliberately stack-independent: pre-activation scratch can
; never redirect SP or turn malformed state into a control-flow failure.
PassiveFullColorClearBGMapChunk:
	ld a, FULL_COLOR_PHASE2_WRAM_BANK
	ldh [rSVBK], a
	ld a, [wPassiveFullColorClearChunks]
	dec a
	ld [wPassiveFullColorClearChunks], a
	ld c, a
	ld a, 31
	sub c ; completed-chunk index, 0 through 31
	ld b, a
	and 7
	swap a
	add a
	ld l, a
	ld a, b
	srl a
	srl a
	srl a
	add HIGH(vBGMap0)
	ld h, a
	ld a, 1
	ldh [rVBK], a
	ld b, 32
	xor a
.loop
	ld [hli], a
	dec b
	jr nz, .loop
	ld a, 1
	ldh [rSVBK], a
	xor a
	ldh [rVBK], a
	ret

EXPORT PassiveFullColorApplyMap, PassiveFullColorHandleConnection
EXPORT PassiveFullColorPrepareRedrawAttributes
EXPORT PassiveFullColorPrepareColumnAttributes
EXPORT PassiveFullColorRestoreAfterMenu
EXPORT PassiveFullColorPrepareMenuHandoff
EXPORT PassiveFullColorShouldColorOverlay
EXPORT PassiveFullColorInvalidateOverlayAttributes, PassiveFullColorPrepareMenuOverlay
EXPORT PassiveFullColorPrepareTextOverlay
EXPORT PassiveFullColorPrepareBattleHandoff
EXPORT PassiveFullColorOverlayAttributeGDMA
EXPORT PassiveFullColorCompletedOverlayVBlank
EXPORT PassiveFullColorVBlank

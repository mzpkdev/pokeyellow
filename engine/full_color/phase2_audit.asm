; Compile-time-only provenance for the Phase 2 hostile-slice inventory audit.
; This section contains data references, never an executable entry point.
IF DEF(PHASE2_AUDIT)
SECTION "Phase 2 Audit Provenance", ROMX

Phase2AuditProvenance::
	db $50, $32, $41, $55, $44, $49, $54, $31 ; ASCII "P2AUDIT1"

; Phase 5 directed identities are audit-ROM evidence, not production scene
; markers.  Each identity binds the natural input route to exact handoff and
; reconstruction breakpoint pairs without widening the closed Phase 2 root
; table below.
FullColorPhase5AuditPartyEntryIdentity::
	db $53, $43, $2d, $50, $35, $2d, $41, $55, $44, $49, $54, $2d
	db $50, $41, $52, $54, $59, $2d, $45, $4e, $54, $52, $59, 0
FullColorPhase5AuditPartyReturnIdentity::
	db $53, $43, $2d, $50, $35, $2d, $41, $55, $44, $49, $54, $2d
	db $50, $41, $52, $54, $59, $2d, $52, $45, $54, $55, $52, $4e, 0
FullColorPhase5AuditPartyRouteRoots::
	dw FullColorPhase5PartyHandoffToYellowStart
	dw FullColorPhase5PartyHandoffToYellowEnd
	dw FullColorPhase5PartyHandoffToColorStart
	dw FullColorPhase5PartyHandoffToColorEnd
	dw FullColorPhase5PartyReconstructColorStart
	dw FullColorPhase5PartyReconstructColorEnd
FullColorPhase5AuditPartyRouteRootsEnd::
ASSERT FullColorPhase5AuditPartyRouteRootsEnd - FullColorPhase5AuditPartyRouteRoots == 6 * 2

Phase2AuditRoots::
	; Stable lexical order; the verifier decodes and binds every entry.
	dw AutoBgMapTransfer
	dw DMARoutine
	dw DisplayPartyMenu
	dw DisplayStartMenu
	dw DisplayTextID
	dw EnterMap
	dw LoadGBPal
	dw LoadMapData
	dw LoadNorthSouthConnectionsTileMap
	dw PalletTown_h
	dw PartyMenuInit
	dw PassiveFullColorApplyMap
	dw PassiveFullColorClearBGMapAttributes
	dw PassiveFullColorClearBGMapChunk
	dw PassiveFullColorCommitPalettes
	dw PassiveFullColorCommitRedrawColumn
	dw PassiveFullColorCommitRedrawRow
	dw PassiveFullColorCommitVisibleAttributes
	dw PassiveFullColorHandleConnection
	dw PassiveFullColorHomogenizeBGPalettes
	dw PassiveFullColorVBlank
	dw PrepareOAMData
	dw RedrawRowOrColumn
	dw RestoreScreenTilesAndReloadTilePatterns
	dw Route1_h
	dw ScheduleEastColumnRedraw
	dw ScheduleNorthRowRedraw
	dw ScheduleSouthRowRedraw
	dw ScheduleWestColumnRedraw
	dw StartMenu_Pokemon.exitMenu
	dw TransferBGPPals
	dw UpdateMovingBgTiles
Phase2AuditRootsEnd::

ASSERT Phase2AuditRootsEnd - Phase2AuditRoots == 32 * 2
ENDC

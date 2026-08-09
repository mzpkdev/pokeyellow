; Yellow-owned conventional-interior color authority retained after independent
; visual review of every map and tileset sheet plus normal/debug Color and
; Yellow route artifacts. Yellow remains authoritative for tile graphics.
; These tables supply only the complete passive BG palette payload and base
; bank-1 attribute lookup; runtime applies the two reviewed Celadon Mart
; map-specific overrides afterward.
;
; Each table below materializes the reviewed 96 assignment bytes, then assigns
; tile IDs $60-$ff to palette 7. All payload bytes and size assertions are
; retained unchanged.

DEF FULL_COLOR_INTERIOR_GRAY       EQU 0
DEF FULL_COLOR_INTERIOR_RED        EQU 1
DEF FULL_COLOR_INTERIOR_GREEN      EQU 2
DEF FULL_COLOR_INTERIOR_BLUE       EQU 3
DEF FULL_COLOR_INTERIOR_YELLOW     EQU 4
DEF FULL_COLOR_INTERIOR_BROWN      EQU 5
DEF FULL_COLOR_INTERIOR_LIGHT_BLUE EQU 6
DEF FULL_COLOR_INTERIOR_TEXT       EQU 7
DEF NUM_PASSIVE_FULL_COLOR_INTERIOR_TILESETS EQU FACILITY - REDS_HOUSE_1 + 1 - 3
ASSERT NUM_PASSIVE_FULL_COLOR_INTERIOR_TILESETS == 19

PUSHS
SECTION "Passive Full Color Interior Pointers", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

FullColorBGPalettePointers::
	dw FullColorOverworldBGPalettes ; OVERWORLD
	dw FullColorIndoorBGPalettes ; REDS_HOUSE_1
	dw FullColorIndoorPCBGPalettes ; MART
	dw 0 ; FOREST
	dw FullColorIndoorBGPalettes ; REDS_HOUSE_2
	dw FullColorIndoorBGPalettes ; DOJO
	dw FullColorPokecenterBGPalettes ; POKECENTER
	dw FullColorIndoorBGPalettes ; GYM
	dw FullColorIndoorBGPalettes ; HOUSE
	dw FullColorIndoorBGPalettes ; FOREST_GATE
	dw FullColorIndoorAltTextBGPalettes ; MUSEUM
	dw FullColorIndoorBGPalettes ; UNDERGROUND
	dw FullColorIndoorAltTextBGPalettes ; GATE
	dw FullColorIndoorBGPalettes ; SHIP
	dw 0 ; SHIP_PORT
	dw FullColorCemeteryBGPalettes ; CEMETERY
	dw FullColorIndoorPCBGPalettes ; INTERIOR
	dw 0 ; CAVERN
	dw FullColorIndoorPCBGPalettes ; LOBBY
	dw FullColorIndoorPCBGPalettes ; MANSION
	dw FullColorIndoorPCBGPalettes ; LAB
	dw FullColorIndoorBGPalettes ; CLUB
	dw FullColorIndoorBGPalettes ; FACILITY
FullColorBGPalettePointersEnd::

FullColorTileAttributePointers::
	dw FullColorOverworldTileAttributes ; OVERWORLD
	dw FullColorRedsHouseTileAttributes ; REDS_HOUSE_1
	dw FullColorPokecenterTileAttributes ; MART
	dw 0 ; FOREST
	dw FullColorRedsHouseTileAttributes ; REDS_HOUSE_2
	dw FullColorGymTileAttributes ; DOJO
	dw FullColorPokecenterTileAttributes ; POKECENTER
	dw FullColorGymTileAttributes ; GYM
	dw FullColorHouseTileAttributes ; HOUSE
	dw FullColorGateTileAttributes ; FOREST_GATE
	dw FullColorGateTileAttributes ; MUSEUM
	dw FullColorUndergroundTileAttributes ; UNDERGROUND
	dw FullColorGateTileAttributes ; GATE
	dw FullColorShipTileAttributes ; SHIP
	dw 0 ; SHIP_PORT
	dw FullColorCemeteryTileAttributes ; CEMETERY
	dw FullColorInteriorTileAttributes ; INTERIOR
	dw 0 ; CAVERN
	dw FullColorLobbyTileAttributes ; LOBBY
	dw FullColorMansionTileAttributes ; MANSION
	dw FullColorLabTileAttributes ; LAB
	dw FullColorClubTileAttributes ; CLUB
	dw FullColorFacilityTileAttributes ; FACILITY
FullColorTileAttributePointersEnd::

ASSERT FullColorBGPalettePointersEnd - FullColorBGPalettePointers == (FACILITY + 1) * 2
ASSERT FullColorTileAttributePointersEnd - FullColorTileAttributePointers == (FACILITY + 1) * 2

POPS

PUSHS
SECTION "Passive Full Color Interior Palettes", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

MACRO full_color_indoor_common
	RGB 30, 28, 26 ; INDOOR_GRAY
	RGB 19, 19, 19
	RGB 13, 13, 13
	RGB 7, 7, 7
	RGB 30, 28, 26 ; INDOOR_RED
	RGB 31, 19, 24
	RGB 30, 10, 6
	RGB 7, 7, 7
	RGB 30, 28, 26 ; INDOOR_GREEN
	RGB 15, 20, 1
	RGB 9, 13, 0
	RGB 7, 7, 7
	RGB 30, 28, 26 ; INDOOR_BLUE
	RGB 15, 16, 31
	RGB 9, 9, 31
	RGB 7, 7, 7
ENDM

MACRO full_color_indoor_tail
	RGB 30, 28, 26 ; INDOOR_BROWN
	RGB 21, 17, 7
	RGB 16, 13, 3
	RGB 7, 7, 7
ENDM

MACRO full_color_indoor_light_blue
	RGB 30, 28, 26 ; INDOOR_LIGHT_BLUE
	RGB 17, 19, 31
	RGB 14, 16, 31
	RGB 7, 7, 7
ENDM

MACRO full_color_textbox
	RGB 31, 31, 31 ; CRYS_TEXTBOX
	RGB 31, 31, 31
	RGB 31, 31, 31
	RGB 0, 0, 0
ENDM

FullColorIndoorBGPalettes::
	full_color_indoor_common
	RGB 30, 28, 26 ; INDOOR_YELLOW
	RGB 31, 31, 7
	RGB 31, 16, 1
	RGB 7, 7, 7
	full_color_indoor_tail
	full_color_indoor_light_blue
	full_color_textbox
FullColorIndoorBGPalettesEnd::

FullColorIndoorPCBGPalettes::
	full_color_indoor_common
	RGB 30, 28, 26 ; INDOOR_YELLOW
	RGB 31, 31, 7
	RGB 31, 16, 1
	RGB 7, 7, 7
	full_color_indoor_tail
	full_color_indoor_light_blue
	RGB 31, 31, 31 ; PC_POKEBALL_PAL
	RGB 31, 19, 10
	RGB 30, 10, 6
	RGB 0, 0, 0
FullColorIndoorPCBGPalettesEnd::

FullColorPokecenterBGPalettes::
	full_color_indoor_common
	RGB 31, 19, 10 ; BENCH_GUY_PAL
	RGB 31, 19, 24
	RGB 30, 10, 6
	RGB 7, 7, 7
	full_color_indoor_tail
	full_color_indoor_light_blue
	RGB 31, 31, 31 ; PC_POKEBALL_PAL
	RGB 31, 19, 10
	RGB 30, 10, 6
	RGB 0, 0, 0
FullColorPokecenterBGPalettesEnd::

FullColorIndoorAltTextBGPalettes::
	full_color_indoor_common
	RGB 30, 28, 26 ; INDOOR_YELLOW
	RGB 31, 31, 7
	RGB 31, 16, 1
	RGB 7, 7, 7
	full_color_indoor_tail
	full_color_indoor_light_blue
	RGB 31, 31, 31 ; ALT_TEXTBOX_PAL
	RGB 21, 21, 21
	RGB 13, 13, 13
	RGB 0, 0, 0
FullColorIndoorAltTextBGPalettesEnd::

FullColorCemeteryBGPalettes::
	full_color_indoor_common
	RGB 30, 28, 26 ; INDOOR_YELLOW
	RGB 31, 31, 7
	RGB 31, 16, 1
	RGB 7, 7, 7
	full_color_indoor_tail
	RGB 30, 28, 26 ; INDOOR_PURPLE
	RGB 25, 22, 31
	RGB 18, 12, 31
	RGB 7, 7, 7
	full_color_textbox
FullColorCemeteryBGPalettesEnd::

ASSERT FullColorIndoorBGPalettesEnd - FullColorIndoorBGPalettes == 8 * 4 * 2
ASSERT FullColorIndoorPCBGPalettesEnd - FullColorIndoorPCBGPalettes == 8 * 4 * 2
ASSERT FullColorPokecenterBGPalettesEnd - FullColorPokecenterBGPalettes == 8 * 4 * 2
ASSERT FullColorIndoorAltTextBGPalettesEnd - FullColorIndoorAltTextBGPalettes == 8 * 4 * 2
ASSERT FullColorCemeteryBGPalettesEnd - FullColorCemeteryBGPalettes == 8 * 4 * 2

PURGE full_color_indoor_common
PURGE full_color_indoor_tail
PURGE full_color_indoor_light_blue
PURGE full_color_textbox

POPS

PUSHS
SECTION "Passive Full Color Interior Attributes", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

FullColorRedsHouseTileAttributes::
	db 3, 0, 0, 0, 1, 0, 3, 3
	db 2, 2, 5, 5, 5, 5, 0, 0
	db 0, 0, 0, 0, 1, 0, 3, 3
	db 5, 5, 5, 5, 5, 5, 0, 0
	db 0, 0, 5, 5, 3, 3, 5, 5
	db 5, 5, 5, 5, 5, 0, 0, 0
	db 5, 5, 5, 5, 3, 3, 5, 5
	db 5, 5, 5, 5, 5, 0, 0, 0
	db 0, 0, 0, 0, 2, 2, 5, 5
	db 0, 0, 1, 1, 3, 3, 0, 0
	db 0, 0, 0, 0, 1, 0, 0, 0
	db 0, 0, 1, 1, 3, 3, 0, 1
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorRedsHouseTileAttributesEnd::
ASSERT FullColorRedsHouseTileAttributesEnd - FullColorRedsHouseTileAttributes == $100

FullColorPokecenterTileAttributes::
	db 0, 0, 1, 1, 3, 3, 0, 0
	db 0, 0, 0, 0, 1, 0, 0, 0
	db 0, 0, 1, 1, 3, 3, 0, 1
	db 3, 3, 0, 0, 1, 1, 0, 0
	db 2, 2, 5, 5, 1, 4, 1, 1
	db 3, 0, 1, 1, 6, 6, 6, 6
	db 2, 2, 5, 5, 1, 4, 0, 1
	db 0, 0, 0, 0, 0, 0, 6, 6
	db 0, 0, 0, 0, 0, 0, 0, 0
	db 0, 0, 0, 0, 6, 6, 4, 4
	db 0, 0, 0, 0, 0, 0, 0, 0
	db 0, 3, 0, 0, 0, 0, 0, 0
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorPokecenterTileAttributesEnd::
ASSERT FullColorPokecenterTileAttributesEnd - FullColorPokecenterTileAttributes == $100

FullColorGymTileAttributes::
	db 3, 0, 5, 1, 0, 0, 1, 5
	db 5, 0, 0, 0, 0, 5, 5, 0
	db 3, 0, 5, 5, 3, 0, 1, 5
	db 5, 0, 0, 0, 0, 5, 5, 0
	db 0, 0, 0, 0, 6, 6, 6, 6
	db 0, 5, 5, 2, 2, 2, 2, 2
	db 0, 0, 0, 0, 3, 6, 0, 0
	db 5, 5, 5, 5, 1, 1, 3, 1
	db 2, 2, 3, 3, 0, 0, 0, 0
	db 0, 0, 0, 0, 1, 1, 5, 5
	db 2, 2, 3, 3, 0, 0, 0, 0
	db 5, 5, 5, 0, 0, 0, 0, 0
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorGymTileAttributesEnd::
ASSERT FullColorGymTileAttributesEnd - FullColorGymTileAttributes == $100

FullColorHouseTileAttributes::
	db 3, 0, 0, 0, 1, 0, 3, 3
	db 2, 2, 2, 2, 2, 2, 5, 5
	db 0, 0, 0, 0, 1, 0, 3, 3
	db 5, 5, 5, 5, 0, 0, 5, 5
	db 0, 0, 3, 3, 3, 5, 5, 5
	db 5, 5, 2, 2, 5, 3, 3, 5
	db 5, 5, 5, 5, 3, 5, 5, 5
	db 5, 5, 5, 5, 5, 3, 3, 3
	db 0, 0, 0, 0, 0, 0, 5, 5
	db 3, 3, 3, 3, 5, 5, 5, 5
	db 5, 5, 5, 5, 3, 3, 5, 5
	db 3, 0, 3, 3, 5, 5, 3, 1
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorHouseTileAttributesEnd::
ASSERT FullColorHouseTileAttributesEnd - FullColorHouseTileAttributes == $100

FullColorGateTileAttributes::
	db 3, 1, 0, 0, 1, 2, 2, 5
	db 5, 5, 0, 0, 0, 0, 0, 0
	db 0, 0, 0, 0, 1, 2, 2, 5
	db 5, 6, 0, 0, 0, 0, 0, 0
	db 5, 5, 5, 5, 0, 5, 5, 6
	db 6, 5, 5, 5, 6, 6, 6, 6
	db 6, 6, 5, 5, 0, 5, 5, 1
	db 1, 0, 6, 5, 6, 6, 0, 0
	db 0, 0, 0, 0, 0, 0, 6, 6
	db 5, 0, 5, 0, 0, 0, 1, 1
	db 0, 0, 0, 0, 0, 0, 0, 0
	db 0, 0, 0, 0, 0, 0, 1, 0
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorGateTileAttributesEnd::
ASSERT FullColorGateTileAttributesEnd - FullColorGateTileAttributes == $100

FullColorUndergroundTileAttributes::
	db 0, 1, 0, 5, 5, 5, 5, 5
	db 5, 5, 5, 1, 1, 0, 0, 0
	db 0, 0, 0, 5, 5, 1, 0, 0
	db 1, 0, 0, 0, 6, 6, 5, 0
	db 0, 1, 1, 3, 3, 5, 3, 0
	db 1, 1, 0, 0, 3, 3, 3, 0
	db 0, 1, 1, 3, 0, 0, 3, 1
	db 1, 1, 6, 6, 0, 5, 1, 0
	db 0, 5, 5, 0, 0, 5, 3, 0
	db 0, 0, 3, 3, 0, 0, 1, 1
	db 5, 5, 5, 0, 0, 5, 5, 0
	db 0, 0, 4, 4, 1, 1, 5, 5
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorUndergroundTileAttributesEnd::
ASSERT FullColorUndergroundTileAttributesEnd - FullColorUndergroundTileAttributes == $100

FullColorShipTileAttributes::
	db 0, 0, 6, 6, 5, 0, 0, 1
	db 1, 3, 3, 5, 3, 0, 1, 1
	db 0, 0, 3, 3, 3, 0, 0, 1
	db 1, 3, 0, 0, 3, 1, 1, 1
	db 6, 6, 0, 5, 1, 0, 0, 5
	db 5, 0, 0, 5, 3, 0, 0, 0
	db 3, 3, 0, 0, 1, 1, 5, 5
	db 5, 0, 0, 5, 5, 0, 0, 0
	db 4, 4, 1, 1, 5, 5, 0, 0
	db 1, 1, 5, 0, 0, 0, 0, 0
	db 4, 4, 0, 0, 1, 1, 0, 0
	db 1, 1, 0, 4, 3, 3, 3, 0
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorShipTileAttributesEnd::
ASSERT FullColorShipTileAttributesEnd - FullColorShipTileAttributes == $100

FullColorCemeteryTileAttributes::
	db 0, 6, 5, 0, 0, 0, 0, 5
	db 5, 6, 6, 0, 0, 5, 5, 5
	db 6, 0, 5, 0, 0, 0, 0, 5
	db 5, 6, 6, 0, 0, 5, 5, 5
	db 5, 5, 6, 5, 5, 5, 5, 5
	db 5, 5, 0, 0, 0, 0, 0, 5
	db 5, 5, 1, 5, 5, 5, 5, 5
	db 0, 0, 5, 5, 5, 5, 5, 5
	db 0, 0, 1, 0, 5, 5, 5, 0
	db 5, 5, 0, 0, 0, 0, 3, 5
	db 0, 0, 1, 0, 0, 0, 0, 5
	db 0, 5, 5, 5, 0, 1, 1, 0
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorCemeteryTileAttributesEnd::
ASSERT FullColorCemeteryTileAttributesEnd - FullColorCemeteryTileAttributes == $100

FullColorInteriorTileAttributes::
	db 0, 1, 1, 0, 0, 5, 5, 5
	db 5, 5, 5, 5, 5, 5, 5, 0
	db 5, 5, 5, 1, 1, 5, 5, 0
	db 0, 0, 0, 5, 5, 5, 5, 0
	db 0, 5, 5, 1, 1, 0, 2, 0
	db 0, 0, 0, 5, 5, 0, 0, 0
	db 0, 1, 1, 1, 0, 0, 2, 0
	db 1, 1, 0, 5, 5, 5, 5, 5
	db 5, 1, 1, 1, 1, 0, 1, 1
	db 5, 5, 5, 5, 5, 5, 5, 5
	db 0, 5, 5, 1, 1, 1, 1, 0
	db 5, 0, 0, 5, 5, 5, 5, 0
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorInteriorTileAttributesEnd::
ASSERT FullColorInteriorTileAttributesEnd - FullColorInteriorTileAttributes == $100

FullColorLobbyTileAttributes::
	db 0, 1, 1, 1, 1, 5, 1, 0
	db 0, 0, 0, 0, 0, 0, 3, 3
	db 0, 5, 1, 1, 1, 5, 1, 0
	db 0, 0, 0, 0, 0, 0, 3, 3
	db 4, 1, 5, 5, 0, 0, 0, 0
	db 5, 0, 0, 0, 0, 0, 0, 0
	db 5, 5, 5, 5, 0, 0, 0, 0
	db 5, 0, 0, 0, 0, 0, 0, 0
	db 0, 0, 0, 0, 0, 0, 0, 0
	db 6, 6, 1, 5, 5, 5, 5, 5
	db 0, 0, 0, 0, 0, 0, 0, 0
	db 6, 6, 0, 1, 5, 5, 0, 5
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorLobbyTileAttributesEnd::
ASSERT FullColorLobbyTileAttributesEnd - FullColorLobbyTileAttributes == $100

FullColorMansionTileAttributes::
	db 0, 5, 5, 5, 1, 1, 3, 3
	db 2, 2, 0, 0, 0, 0, 3, 0
	db 0, 1, 5, 5, 1, 4, 3, 3
	db 5, 5, 0, 0, 0, 0, 3, 0
	db 6, 0, 5, 5, 5, 5, 5, 5
	db 4, 5, 0, 0, 0, 5, 5, 5
	db 3, 0, 5, 5, 5, 5, 5, 5
	db 5, 5, 5, 5, 5, 0, 0, 5
	db 5, 5, 5, 5, 2, 2, 5, 5
	db 3, 3, 3, 3, 3, 3, 3, 3
	db 3, 0, 0, 0, 0, 5, 5, 5
	db 3, 3, 3, 3, 3, 3, 0, 3
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorMansionTileAttributesEnd::
ASSERT FullColorMansionTileAttributesEnd - FullColorMansionTileAttributes == $100

FullColorLabTileAttributes::
	db 0, 3, 5, 5, 5, 5, 5, 5
	db 5, 5, 0, 0, 1, 1, 5, 5
	db 5, 5, 5, 5, 5, 5, 5, 5
	db 0, 0, 0, 0, 6, 6, 5, 5
	db 5, 5, 5, 5, 6, 6, 0, 1
	db 5, 5, 5, 5, 2, 2, 5, 5
	db 5, 5, 2, 2, 1, 1, 0, 1
	db 0, 0, 5, 5, 2, 2, 5, 5
	db 5, 5, 5, 2, 2, 0, 5, 6
	db 5, 5, 0, 5, 1, 1, 6, 0
	db 5, 5, 5, 5, 5, 0, 5, 6
	db 6, 6, 0, 5, 0, 2, 2, 2
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorLabTileAttributesEnd::
ASSERT FullColorLabTileAttributesEnd - FullColorLabTileAttributes == $100

FullColorClubTileAttributes::
	db 0, 2, 2, 2, 0, 5, 2, 5
	db 5, 1, 1, 1, 1, 1, 1, 0
	db 5, 2, 2, 2, 0, 1, 1, 5
	db 5, 0, 1, 1, 1, 1, 6, 6
	db 0, 0, 0, 0, 0, 0, 0, 0
	db 1, 1, 0, 0, 1, 1, 1, 1
	db 1, 1, 1, 1, 1, 1, 5, 0
	db 0, 0, 0, 0, 0, 0, 0, 6
	db 0, 0, 6, 6, 6, 6, 6, 5
	db 5, 5, 5, 0, 0, 1, 5, 5
	db 5, 2, 2, 5, 0, 5, 5, 5
	db 5, 5, 5, 5, 0, 0, 5, 5
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorClubTileAttributesEnd::
ASSERT FullColorClubTileAttributesEnd - FullColorClubTileAttributes == $100

FullColorFacilityTileAttributes::
	db 0, 1, 5, 5, 5, 2, 2, 5
	db 0, 5, 5, 5, 5, 5, 5, 5
	db 0, 0, 5, 5, 3, 2, 2, 5
	db 0, 5, 5, 5, 5, 5, 5, 5
	db 1, 1, 1, 5, 0, 0, 5, 5
	db 5, 5, 0, 0, 0, 0, 0, 5
	db 1, 1, 1, 0, 5, 5, 5, 5
	db 0, 0, 5, 5, 5, 0, 0, 5
	db 5, 5, 1, 5, 5, 5, 5, 5
	db 5, 5, 0, 0, 0, 0, 5, 5
	db 5, 5, 1, 5, 5, 1, 0, 5
	db 0, 5, 0, 0, 5, 5, 0, 0
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT
FullColorFacilityTileAttributesEnd::
ASSERT FullColorFacilityTileAttributesEnd - FullColorFacilityTileAttributes == $100

POPS

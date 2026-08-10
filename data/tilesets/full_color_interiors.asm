; Yellow-owned map-background color data. Reviewed conventional-interior data
; remains unchanged. FOREST, CAVERN, SHIP_PORT, PLATEAU, and BEACH_HOUSE are
; independently authored candidates: their complete payloads are linked and
; integrity-covered, but the production admission predicate still deliberately
; presents those maps in Yellow mode.
; Yellow remains authoritative for tile graphics, animation, and mechanics.
;
; Every assignment table covers all 256 tile identities. Tile IDs $60-$ff are
; explicitly reserved for Yellow's text tiles and always select palette 7.

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
	dw FullColorForestBGPalettes ; FOREST
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
	dw FullColorShipPortBGPalettes ; SHIP_PORT
	dw FullColorCemeteryBGPalettes ; CEMETERY
	dw FullColorIndoorPCBGPalettes ; INTERIOR
	dw FullColorCavernBGPalettes ; CAVERN
	dw FullColorIndoorPCBGPalettes ; LOBBY
	dw FullColorIndoorPCBGPalettes ; MANSION
	dw FullColorIndoorPCBGPalettes ; LAB
	dw FullColorIndoorBGPalettes ; CLUB
	dw FullColorIndoorBGPalettes ; FACILITY
	dw FullColorPlateauBGPalettes ; PLATEAU
	dw FullColorBeachHouseBGPalettes ; BEACH_HOUSE
FullColorBGPalettePointersEnd::

FullColorTileAttributePointers::
	dw FullColorOverworldTileAttributes ; OVERWORLD
	dw FullColorRedsHouseTileAttributes ; REDS_HOUSE_1
	dw FullColorPokecenterTileAttributes ; MART
	dw FullColorForestTileAttributes ; FOREST
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
	dw FullColorShipPortTileAttributes ; SHIP_PORT
	dw FullColorCemeteryTileAttributes ; CEMETERY
	dw FullColorInteriorTileAttributes ; INTERIOR
	dw FullColorCavernTileAttributes ; CAVERN
	dw FullColorLobbyTileAttributes ; LOBBY
	dw FullColorMansionTileAttributes ; MANSION
	dw FullColorLabTileAttributes ; LAB
	dw FullColorClubTileAttributes ; CLUB
	dw FullColorFacilityTileAttributes ; FACILITY
	dw FullColorPlateauTileAttributes ; PLATEAU
	dw FullColorBeachHouseTileAttributes ; BEACH_HOUSE
FullColorTileAttributePointersEnd::

ASSERT FullColorBGPalettePointersEnd - FullColorBGPalettePointers == NUM_TILESETS * 2
ASSERT FullColorTileAttributePointersEnd - FullColorTileAttributePointers == NUM_TILESETS * 2

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

; Forest roles keep the shared outdoor sheet readable across Viridian Forest
; and all four Safari Zone areas: meadow, foliage, animated water, earth,
; timber, stone, and sign/accent colors, followed by the text palette.
FullColorForestBGPalettes::
	RGB 31, 31, 27 ; FOREST_MEADOW
	RGB 20, 28, 13
	RGB 9, 18, 6
	RGB 2, 7, 3
	RGB 31, 31, 27 ; FOREST_FOLIAGE
	RGB 13, 24, 10
	RGB 5, 14, 4
	RGB 2, 7, 3
	RGB 28, 31, 31 ; FOREST_WATER
	RGB 15, 25, 31
	RGB 5, 15, 27
	RGB 1, 6, 14
	RGB 31, 30, 24 ; FOREST_EARTH
	RGB 25, 19, 10
	RGB 15, 10, 5
	RGB 5, 5, 3
	RGB 31, 29, 24 ; FOREST_TIMBER
	RGB 27, 16, 8
	RGB 18, 8, 5
	RGB 6, 4, 3
	RGB 30, 31, 28 ; FOREST_STONE
	RGB 20, 22, 18
	RGB 11, 13, 11
	RGB 4, 5, 4
	RGB 31, 31, 24 ; FOREST_ACCENT
	RGB 31, 25, 8
	RGB 23, 15, 3
	RGB 6, 5, 2
	RGB 31, 31, 31 ; FOREST_TEXT
	RGB 31, 31, 31
	RGB 31, 31, 31
	RGB 0, 0, 0
FullColorForestBGPalettesEnd::

; Cavern roles are based on the one Yellow sheet shared by Mt. Moon, Rock
; Tunnel, Diglett's Cave, Seafoam, Victory Road, and Cerulean Cave: limestone,
; deep floor, animated water, cool highlights, ladders, boulders, and voids.
FullColorCavernBGPalettes::
	RGB 29, 30, 28 ; CAVERN_LIMESTONE
	RGB 20, 22, 20
	RGB 11, 13, 12
	RGB 3, 4, 4
	RGB 29, 27, 24 ; CAVERN_FLOOR
	RGB 20, 15, 11
	RGB 11, 8, 7
	RGB 3, 3, 4
	RGB 28, 31, 31 ; CAVERN_WATER
	RGB 14, 25, 31
	RGB 5, 14, 27
	RGB 1, 5, 13
	RGB 29, 31, 31 ; CAVERN_COOL_HIGHLIGHT
	RGB 18, 27, 29
	RGB 9, 17, 20
	RGB 3, 6, 8
	RGB 31, 29, 23 ; CAVERN_LADDER
	RGB 27, 18, 8
	RGB 16, 9, 4
	RGB 5, 4, 3
	RGB 30, 30, 27 ; CAVERN_BOULDER
	RGB 19, 20, 18
	RGB 9, 10, 10
	RGB 3, 4, 4
	RGB 27, 25, 31 ; CAVERN_VOID
	RGB 16, 13, 22
	RGB 8, 6, 14
	RGB 2, 2, 5
	RGB 31, 31, 31 ; CAVERN_TEXT
	RGB 31, 31, 31
	RGB 31, 31, 31
	RGB 0, 0, 0
FullColorCavernBGPalettesEnd::

; Vermilion Dock roles follow Yellow's one-map sheet: harbor water, concrete
; pier, S.S. Anne hull, navy windows/shadows, timber deck, cargo, and funnels.
FullColorShipPortBGPalettes::
	RGB 28, 31, 31 ; SHIP_PORT_WATER
	RGB 14, 25, 31
	RGB 4, 14, 27
	RGB 1, 5, 13
	RGB 31, 30, 25 ; SHIP_PORT_PIER
	RGB 21, 22, 21
	RGB 12, 13, 14
	RGB 4, 5, 7
	RGB 31, 31, 28 ; SHIP_PORT_HULL
	RGB 25, 27, 27
	RGB 15, 18, 20
	RGB 4, 6, 9
	RGB 28, 31, 31 ; SHIP_PORT_NAVY
	RGB 13, 21, 29
	RGB 5, 11, 22
	RGB 2, 4, 10
	RGB 31, 29, 23 ; SHIP_PORT_DECK
	RGB 25, 18, 9
	RGB 15, 9, 4
	RGB 5, 4, 3
	RGB 31, 30, 24 ; SHIP_PORT_CARGO
	RGB 24, 20, 12
	RGB 14, 12, 8
	RGB 4, 5, 5
	RGB 31, 29, 24 ; SHIP_PORT_FUNNEL
	RGB 31, 18, 8
	RGB 22, 7, 4
	RGB 6, 4, 4
	full_color_textbox
FullColorShipPortBGPalettesEnd::

; Plateau roles cover both Route 23 and Indigo Plateau: snowfield, alpine
; grass, animated water, cliffs, League masonry, evergreens, and statues/signs.
FullColorPlateauBGPalettes::
	RGB 31, 31, 29 ; PLATEAU_SNOWFIELD
	RGB 24, 27, 25
	RGB 15, 18, 18
	RGB 5, 7, 8
	RGB 31, 31, 25 ; PLATEAU_GRASS
	RGB 19, 27, 11
	RGB 8, 17, 6
	RGB 2, 7, 4
	RGB 28, 31, 31 ; PLATEAU_WATER
	RGB 14, 25, 31
	RGB 5, 14, 27
	RGB 1, 5, 13
	RGB 30, 30, 28 ; PLATEAU_CLIFF
	RGB 21, 21, 20
	RGB 12, 13, 14
	RGB 4, 5, 7
	RGB 31, 29, 24 ; PLATEAU_LEAGUE
	RGB 29, 18, 10
	RGB 18, 8, 6
	RGB 6, 4, 5
	RGB 29, 31, 28 ; PLATEAU_EVERGREEN
	RGB 13, 23, 13
	RGB 5, 13, 7
	RGB 2, 6, 4
	RGB 31, 31, 24 ; PLATEAU_MONUMENT
	RGB 29, 23, 8
	RGB 17, 13, 5
	RGB 5, 5, 4
	full_color_textbox
FullColorPlateauBGPalettesEnd::

; Summer Beach House uses its native Yellow sheet: sand, timber, seaside-blue
; furnishings, tropical plants, warm posters/chairs, printer metal, and accents.
FullColorBeachHouseBGPalettes::
	RGB 31, 31, 25 ; BEACH_HOUSE_SAND
	RGB 28, 24, 15
	RGB 18, 13, 8
	RGB 6, 5, 4
	RGB 31, 29, 24 ; BEACH_HOUSE_TIMBER
	RGB 25, 18, 10
	RGB 15, 9, 5
	RGB 5, 4, 3
	RGB 29, 31, 31 ; BEACH_HOUSE_SEASIDE
	RGB 14, 24, 29
	RGB 5, 13, 23
	RGB 2, 5, 10
	RGB 30, 31, 25 ; BEACH_HOUSE_PLANT
	RGB 15, 25, 9
	RGB 6, 15, 5
	RGB 2, 6, 3
	RGB 31, 29, 24 ; BEACH_HOUSE_WARM_ACCENT
	RGB 31, 19, 9
	RGB 22, 8, 5
	RGB 6, 4, 4
	RGB 31, 31, 29 ; BEACH_HOUSE_PRINTER
	RGB 22, 24, 25
	RGB 12, 14, 17
	RGB 3, 5, 8
	RGB 31, 31, 23 ; BEACH_HOUSE_GOLD
	RGB 31, 25, 7
	RGB 21, 14, 3
	RGB 6, 5, 2
	full_color_textbox
FullColorBeachHouseBGPalettesEnd::

ASSERT FullColorIndoorBGPalettesEnd - FullColorIndoorBGPalettes == 8 * 4 * 2
ASSERT FullColorIndoorPCBGPalettesEnd - FullColorIndoorPCBGPalettes == 8 * 4 * 2
ASSERT FullColorPokecenterBGPalettesEnd - FullColorPokecenterBGPalettes == 8 * 4 * 2
ASSERT FullColorIndoorAltTextBGPalettesEnd - FullColorIndoorAltTextBGPalettes == 8 * 4 * 2
ASSERT FullColorCemeteryBGPalettesEnd - FullColorCemeteryBGPalettes == 8 * 4 * 2
ASSERT FullColorForestBGPalettesEnd - FullColorForestBGPalettes == 8 * 4 * 2
ASSERT FullColorCavernBGPalettesEnd - FullColorCavernBGPalettes == 8 * 4 * 2
ASSERT FullColorShipPortBGPalettesEnd - FullColorShipPortBGPalettes == 8 * 4 * 2
ASSERT FullColorPlateauBGPalettesEnd - FullColorPlateauBGPalettes == 8 * 4 * 2
ASSERT FullColorBeachHouseBGPalettesEnd - FullColorBeachHouseBGPalettes == 8 * 4 * 2

PURGE full_color_indoor_common
PURGE full_color_indoor_tail
PURGE full_color_indoor_light_blue
PURGE full_color_textbox

POPS

PUSHS
SECTION "Passive Full Color Interior Attributes", ROMX, BANK[FULL_COLOR_PHASE2_ROM_BANK]

; FOREST $00-$5f: meadow/ground, tree canopy and trunks, water $14/$41,
; paths and banks, timber gates/buildings, stone, and signs/accents.
FullColorForestTileAttributes::
	db 0, 0, 0, 0, 1, 1, 1, 1
	db 3, 1, 1, 3, 3, 3, 0, 1
	db 1, 1, 1, 1, 2, 0, 0, 0
	db 3, 1, 1, 1, 3, 3, 0, 1
	db 0, 6, 4, 0, 5, 3, 3, 3
	db 4, 4, 1, 1, 6, 1, 0, 1
	db 0, 3, 4, 1, 6, 3, 0, 5
	db 3, 3, 3, 3, 4, 4, 4, 4
	db 0, 2, 0, 0, 4, 1, 1, 3
	db 4, 4, 4, 4, 3, 3, 3, 3
	db 5, 0, 3, 3, 4, 4, 5, 5
	db 0, 0, 4, 4, 4, 5, 5, 5
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT ; $60-$ff: Yellow text
FullColorForestTileAttributesEnd::
ASSERT FullColorForestTileAttributesEnd - FullColorForestTileAttributes == $100

; CAVERN $00-$3c: limestone edges, deep floor, animated water $14,
; ladders/warps $0a/$0b/$18/$1a, hole $22, boulders, cracks, and dark void $3c.
; Unused or absent sheet identities $3d-$5f stay on neutral limestone.
FullColorCavernTileAttributes::
	db 0, 6, 0, 0, 5, 1, 5, 0
	db 0, 0, 4, 4, 6, 5, 4, 4
	db 5, 5, 0, 0, 2, 0, 0, 0
	db 4, 4, 4, 4, 6, 5, 4, 4
	db 1, 6, 6, 1, 5, 0, 0, 0
	db 0, 0, 4, 4, 6, 5, 4, 4
	db 0, 5, 0, 0, 0, 0, 0, 0
	db 0, 0, 0, 0, 6, 0, 0, 0
	ds $60 - $40, 0 ; $40-$5f: unused/absent source identities
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT ; $60-$ff: Yellow text
FullColorCavernTileAttributesEnd::
ASSERT FullColorCavernTileAttributesEnd - FullColorCavernTileAttributes == $100

; SHIP_PORT $00-$5d: ship hull and deck details, animated water $0a/$14,
; pier tiles $31/$3a/$45, cargo $50-$59, and funnel/accent tiles $42/$43.
FullColorShipPortTileAttributes::
	db 2, 2, 2, 2, 2, 2, 3, 3
	db 2, 2, 0, 2, 2, 2, 2, 2
	db 2, 2, 2, 2, 0, 2, 2, 2
	db 2, 2, 2, 2, 2, 2, 2, 2
	db 4, 4, 4, 4, 4, 4, 4, 4
	db 4, 4, 2, 2, 4, 4, 4, 4
	db 2, 1, 1, 2, 2, 2, 2, 2
	db 1, 1, 1, 1, 1, 1, 1, 1
	db 2, 2, 6, 6, 2, 1, 1, 1
	db 2, 2, 2, 2, 3, 3, 3, 3
	db 5, 5, 5, 5, 5, 5, 5, 5
	db 5, 5, 5, 5, 5, 5, 1, 1
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT ; $60-$ff: Yellow text
FullColorShipPortTileAttributesEnd::
ASSERT FullColorShipPortTileAttributesEnd - FullColorShipPortTileAttributes == $100

; PLATEAU $00-$45: snowfield, cliffs, water $14, League walls/doors,
; evergreen tiles, monuments, and the source-owned grass identity $45.
FullColorPlateauTileAttributes::
	db 0, 3, 3, 0, 0, 3, 3, 5
	db 5, 3, 3, 3, 3, 4, 4, 4
	db 5, 3, 5, 3, 2, 4, 4, 5
	db 5, 6, 6, 4, 4, 4, 4, 4
	db 4, 4, 5, 0, 5, 5, 5, 5
	db 5, 5, 3, 3, 0, 6, 4, 4
	db 4, 4, 3, 3, 1, 1, 1, 1
	db 0, 5, 5, 5, 5, 4, 4, 4
	db 4, 4, 4, 4, 0, 1, 0, 0
	db 0, 0, 0, 0, 0, 0, 0, 0
	db 0, 0, 0, 0, 0, 0, 0, 0
	db 0, 0, 0, 0, 0, 0, 0, 0
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT ; $60-$ff: Yellow text
FullColorPlateauTileAttributesEnd::
ASSERT FullColorPlateauTileAttributesEnd - FullColorPlateauTileAttributes == $100

; BEACH_HOUSE $00-$47: sandy and timber floors, chairs/tables, seaside
; furniture, native plant quadrants $08/$09/$18/$19/$44-$47, and printer.
FullColorBeachHouseTileAttributes::
	db 1, 0, 1, 1, 4, 0, 4, 4
	db 3, 3, 0, 0, 0, 0, 0, 0
	db 1, 1, 1, 1, 4, 0, 4, 4
	db 3, 3, 0, 0, 0, 0, 0, 0
	db 1, 1, 0, 0, 1, 1, 1, 1
	db 1, 1, 1, 1, 1, 1, 0, 0
	db 1, 1, 1, 1, 1, 1, 1, 1
	db 1, 1, 1, 1, 1, 1, 1, 1
	db 5, 5, 2, 2, 3, 3, 3, 3
	db 0, 0, 0, 0, 0, 0, 0, 0
	db 0, 0, 0, 0, 0, 0, 0, 0
	db 0, 0, 0, 0, 0, 0, 0, 0
	ds $100 - $60, FULL_COLOR_INTERIOR_TEXT ; $60-$ff: Yellow text
FullColorBeachHouseTileAttributesEnd::
ASSERT FullColorBeachHouseTileAttributesEnd - FullColorBeachHouseTileAttributes == $100

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

# Full-color renderer

This manual is the normative contract for the renderer that actually runs
today and describes the proposed migration beyond it. It supplements the
ROM-wide [ARCHITECTURE.md](ARCHITECTURE.md).
Procedures live in [ADDING_CONTENT.md](ADDING_CONTENT.md), and proof boundaries
live in [TESTING.md](TESTING.md).

## Current scope

The shipped renderer is a bounded passive CGB color layer for the 34 city and
route maps that use `OVERWORLD` and the conventional interior maps using
tileset IDs `REDS_HOUSE_1` through `FACILITY`, excluding `FOREST`, `SHIP_PORT`,
and `CAVERN`. Those 19 tilesets cover 162 maps. `PLATEAU` and `BEACH_HOUSE`
also remain Yellow. The normal, debug, and VC products
expose a saved `COLOR MODE`
preference between `COLOR` and `YELLOW`; fresh saves default to Color, Continue
retains the saved choice, and New Game may reset it to Color. It is a release
feature, but it is not the retained full-color scheduler taking ownership of
the game.

`passive_overworld` is the only active color presentation path. No plan,
compiled module, callable symbol, retained test, or migration proposal changes
that fact without a separately approved architecture change.

| Target | Product | Active passive slice |
| --- | --- | --- |
| `make yellow` | `pokeyellow.gbc` | Yes |
| `make yellow_debug` | `pokeyellow_debug.gbc` | Yes |
| `make yellow_vc` | VC ROM/patch | Yes |
| `make yellow_phase2_audit` | `pokeyellow_phase2_audit.gbc` | Yes |

The audit target defines both `_DEBUG` and `PHASE2_AUDIT`, but that flag adds
only extra diagnostics and certification surfaces. The toggle, passive code,
data, state, and hooks are unconditional product functionality; runtime mode
selection, never `PHASE2_AUDIT`, decides whether Color is presented.

## Ownership contract

Yellow MUST retain authority for every bank-0 background tile and tile pattern;
sprite graphics, OAM, movement, and gameplay; map and overlay construction,
scrolling, menus, dialogue, battle, and cutscenes; and animations, fade
progression, scheduling, and lifecycle behavior. Explicitly integrated overlays
may receive a passive bank-1 attribute projection after Yellow finishes their
bank-0 structure. Active-map fades may transform all eight authored passive BG
palettes using Yellow's current `BGP` mapping. Neither operation activates the
retained Color owner or its scheduler pipeline.

The passive Color path MAY publish only:

- a complete set of eight CGB background palettes; and
- corresponding per-tile attributes in VRAM bank 1.

It translates the tile picture Yellow already finished. It never suppresses,
replaces, or races Yellow's bank-0 write. Object palettes are present in the
audit data ABI, but the passive path does not publish them; sprites stay under
Yellow control.

Earlier incomplete ownership attempts produced mismatched tilemaps and broken
cutscenes. Do not widen this boundary as a shortcut for another colored map.

## Active path and retained scaffolding

[engine/full_color/passive_overworld.asm](../engine/full_color/passive_overworld.asm)
is the live presentation path. Hooks in Yellow's normal map, redraw, menu,
palette, and VBlank flows call its `PassiveFullColor*` routines in every
shipped product. The activation gate requires the saved Color preference and
accepts either a city/route map whose loaded tileset is `OVERWORLD` or an
authored conventional-interior tileset from the bounded range above.
While Start or Options is open, the active presentation remains
latched; the saved preference is reconciled only when the outer menu closes.

[engine/full_color/passive_palette_refresh.asm](../engine/full_color/passive_palette_refresh.asm)
scopes the steady overworld `LoadGBPal`: an active authored map keeps BG palette
hardware authority while Yellow still updates its BGP cache and object palettes.
During a real fade, Yellow chooses the step and timing while the passive layer
streams the same mapping across all eight authored BG palettes. Yellow-mode and
forced-menu contexts retain their ordinary palette publications.

The following modules preserve measured contracts, debug observability, and
future migration seams but do not drive the current passive display:

- `ownership.asm` and `scheduler.asm`;
- `palettes.asm`, `transfers.asm`, and `oam.asm`; and
- most of `lifecycle.asm`.

The active production VBlank calls `PassiveFullColorVBlank`; it does not route
the frame through `RouteRendererOwnershipVBlank`. The passive path reuses
reviewed WRAM2 storage and the renderer generation, but it does not acquire
`RENDERER_FULL_COLOR_OVERWORLD` ownership or enqueue ordinary scheduler jobs.
Compiled or callable scaffolding is not evidence of active presentation.
Retained ownership, scheduler, and lifecycle machinery MUST NOT be activated,
used as current presentation authority, or treated as the foundation of a
broader renderer without a separately approved architecture change.

## Data authority

[data/tilesets/full_color_overworld.asm](../data/tilesets/full_color_overworld.asm)
contains the live outdoor decisions, while
[data/tilesets/full_color_interiors.asm](../data/tilesets/full_color_interiors.asm)
contains the interior palette/attribute pointer tables and independently
reviewed repository-owned payloads:

- `FullColorOverworldBGPalettes`: 64 bytes, eight complete four-color CGB BG
  palettes;
- `FullColorOverworldTileAttributes`: 256 bytes mapping each tile ID directly
  to an attribute;
- tile IDs `$00`–`$5f`: reviewed `OVERWORLD` assignments against Yellow graphics;
- tile IDs `$60`–`$ff`: text palette 7;
- bank 0 and no authored priority for all current attributes; and
- `FullColorOverworldRoofAssignments`: one reviewed roof identity for each city
  and route map ID;
- `FullColorOverworldRoofPalettes`: the eleven repository-owned roof color
  pairs; and
- palette 6: common outdoor edge colors with map-aware roof middle colors;
- every admitted tileset selects a complete 64-byte BG palette payload and a
  complete 256-byte tile attribute lookup;
- identical palette sets and assignment maps are shared by pointer;
- all interior tile IDs `$60`–`$ff` explicitly use palette 7; and
- two reviewed map overrides apply after tileset lookup: `CELADON_MART_ROOF`
  tiles `$4b`–`$4f` use palette 3, and `CELADON_MART_1F` tiles `$07`, `$08`,
  `$17`, and `$18` use palette 4.

The tables are the checked repository authority, retain provenance evidence,
and have size assertions. Runtime uses
a direct lookup; there is no `tile_id & 7` or other legal-looking fallback.

Each admitted map keeps the Yellow graphics selected by its own map header.
Runtime selects the corresponding repository-owned tileset palette payload and
tile-to-attribute table. Outdoor maps additionally select authored roof colors;
Route 6 uses Saffron roof colors in its top rows and Vermilion colors elsewhere.

## Map load and publication

`LoadMapData` in [home/overworld.asm](../home/overworld.asm) disables the LCD and
lets Yellow complete normal map setup, tilemap copy, and `SET_PAL_OVERWORLD`.
It then calls `PassiveFullColorApplyMap`.

For an allowed map while Color is selected, the passive routine:

1. clears pending passive state;
2. records active state for the current renderer generation;
3. commits all eight BG palettes; and
4. mirrors the complete 32×32 bank-0 BG map into bank 1, translating every tile
   through the authored attribute table.

The LCD-off publication is atomic to the player. The routine restores `rVBK`
to bank 0 before Yellow resumes.

For Yellow mode or every other map, it clears passive state and the active bit,
then clears the complete bank-1 BG map. Yellow continues normally.

## Scrolling and VBlank

Yellow produces the next bank-0 row or column. Immediately before arming a
redraw, `PassiveFullColorPrepareRedrawAttributes` or
`PassiveFullColorPrepareColumnAttributes` translates those completed tile IDs
outside VBlank into fixed records in `wPassiveFullColorRedrawStaging`.

During an ordinary scrolling VBlank, Yellow's `RedrawRowOrColumn` executes
first and publishes the offscreen bank-0 strip. The consumed mode changes the
frozen redraw record from prepared to mirror-pending. The next redraw-free
VBlank commits the matching bank-1 row or column, before another producer may
reuse the single slot. Column records carry destination addresses so the
critical section does not reconstruct them per row.

The hidden overlay activation barrier is the exception. A fresh dialogue
window, initial or redisplayed Start menu, or initial Options screen explicitly
invalidates the completed-plane latch after Yellow finalizes its structure. It
then translates the finalized 20x18 tilemap once into an aligned WRAM2 plane
with Yellow's 32-byte BG-map row stride. One dedicated VBlank publishes that
complete 32x18 plane to VRAM bank 1 with GDMA. The caller's unchanged `Delay3`
then gives Yellow's stock six-row `AutoBgMapTransfer` exactly three bank-0
frames before reveal. Fresh presentation therefore takes four frames. The
completion latch certifies only that structural tilemap. Later Start or Options
cursor movement does not invalidate it and rearms only the stock three-frame
sweep. Yellow's OAM DMA and shadow-OAM preparation continue on
the attribute frame because sprites are a separate Yellow-owned resource. Each
stock tile frame commits that frozen shadow OAM without rebuilding it, which
keeps the combined tile-and-OAM work inside VBlank. The sweep then disables
stock publication so queued VRAM work resumes on the next VBlank.
The Start redisplay seam invalidates the latch explicitly, so correctness does
not depend on whether an intervening submenu happened to clear
`hAutoBGTransferEnabled`. Two-option menus likewise treat both drawing their
border and restoring the covered tiles on dismissal as structural changes.
The dismissal rebuild is gated to the active Color slice; Yellow presentation
keeps its original return path and timing.

Overlay construction remains Yellow-owned. The passive work above is only the
paired bank-1 half of that already-finalized structure; it never enters the
retained `OVERWORLD_OVERLAY` phase. A Yellow full-screen attribute packet marks
the base attribute certificate dirty and suspends overlay projection. Explicit
Start/Options redisplay may resume paired overlays, while final close rebuilds
the base map before clearing that dirty state. Pokecenter map redisplays use the
same hidden four-frame barrier so bank 0 and bank 1 cannot diverge on reveal.
Translation keeps WRAM1 selected and interrupts admitted between cells, masking
only each bounded WRAM2 store.

The attribute GDMA is the only VRAM writer in its frame, and any pending Yellow
redraw or queued VRAM work remains armed until the barrier finishes.
While the completed plane is latched, ordinary passive palette and redraw work
stays excluded. Each stock six-row bank-0 publication likewise owns its frame's
VRAM-write budget, then performs only Yellow's OAM DMA before the common tail.
Dialogue retains continuous Yellow tile publication while letters print, but
inserts one full visible-work recovery VBlank after every three stock chunks;
menus use one finite sweep and then remain on ordinary VBlanks until another
update.

The scrolling invariant is strict: prepare outside VBlank, Yellow tile write
first, matching passive attribute write second, and apply producer backpressure
until both halves finish. The hidden overlay instead completes its translated
attribute plane before Yellow's three-frame bank-0 sweep. Overlay attributes and
redraw records use separate WRAM2 storage, so either may be staged first without
corrupting the other.

Yellow's complete and single background-palette writers mark the authored
payload invalidated at their hardware publication seam. During steady Color
gameplay, `PassiveFullColorLoadGBPal` suppresses only Yellow's buffered BG
hardware transfer while retaining its BGP cache and object-palette work. This
prevents a Yellow-colored frame after map entry. Any earlier unscoped writer
still queues bounded VBlank republication, and the authored commit clears the
signal without probing palette RAM.

Yellow owns fade progression and delay timing. On active authored maps the
fade seam resolves each output shade from immutable authored data, stages all
eight BG palettes, and publishes one complete 64-byte LCD-safe unit. The protected
steady `LoadGBPal` call never performs that live transfer. Route 6 records its
last committed roof region, so crossing y=1/2 queues the normal bounded VBlank
palette refresh instead of publishing a coordinate-dependent roof mid-frame.

`RedrawMapView` scopes both sides of its default palette command: Yellow still
updates its palette cache and object palettes, but the command's whole-screen
bank-1 packet is suppressed while the active authored plane is authoritative.
Each subsequent bank-0 row is paired with its passive row mirror, and the base
attribute dirty state clears only after the final mirror completes.

At most one passive visible operation runs per frame:

1. an armed overlay-transfer step wins and defers any Yellow redraw;
2. otherwise a Yellow row/column redraw wins and arms its passive mirror;
3. otherwise a pending passive redraw mirror wins;
4. otherwise one remaining activation-barrier step may run;
5. otherwise a pending palette commit may run;
6. otherwise one exit-cleanup chunk may run.

A palette request remains pending when a redraw wins. Combining them violates
the measured timing contract.

## Leaving the slice

Integrated doors, warps, and connected-map routes reach
`PassiveFullColorApplyMap` while the LCD is off, so all 1024 bank-1 attributes
are cleared immediately.

The module also exposes `PassiveFullColorHandleConnection` for a bounded LCD-on
barrier. `PassiveFullColorHomogenizeBGPalettes` first copies palette 0 across
palettes 1–7, making uncleared attributes visually equivalent to Yellow palette
0. It then clears the 1024-byte bank-1 map in thirty-two 32-byte VBlank chunks.
The entry side supports deferred palette republication; the complete handler is
also a diagnostic-callable seam. Never assume a new natural transition reaches the
right branch without verifying its Yellow call site.

## Menus, maps, dialogue, and battles

The passive renderer is a bounded map layer, not global display ownership.

- Conventional interiors in the admitted tileset range use their selected
  authored payload. `FOREST`, `SHIP_PORT`, `CAVERN`, `PLATEAU`, `BEACH_HOUSE`,
  and any other unsupported map use Yellow palettes with cleared bank-1 attributes.
- Selected dialogue, Start/Options, and two-option overlays keep Yellow's
  bank-0 construction and timing, then receive a paired passive bank-1
  projection behind the hidden four-frame barrier. Full-screen Yellow menus
  that publish their own attribute packet suspend projection and mark the base
  attributes dirty. On close, Yellow rebuilds `wTileMap`, and
  `PassiveFullColorRestoreAfterMenu` reconciles the selected presentation. An
  already-active presentation with dirty base attributes performs a complete
  passive rebuild; a palette-only invalidation remains a bounded refresh.
  Yellow-to-Color
  activation keeps Color inactive and authored palettes unpublished while two
  wrapped visible rows are published per VBlank, then commits all authored
  palettes and activates Color in one later VBlank. Yellow mode reruns Yellow's
  authoritative overworld palette command and leaves passive state inactive.
- Battles and transitions remain Yellow behavior. Normal map restoration
  reapplies the passive attributes when returning to an allowed map.
- Sprites, battle effects, moving tiles, and cutscene objects are never inferred
  from background tile IDs.

Donor attributes appearing in an unsupported overlay, unsupported map, or
battle are an ownership leak, not evidence of broader renderer support.

## State and fail-closed behavior

Passive state is declared in [ram/wram.asm](../ram/wram.asm) and lives in WRAM2:

- `wPassiveFullColorActive` prevents power-on map ID zero from impersonating a
  loaded Pallet Town;
- `wPassiveFullColorPalettePending` records deferred palette work;
- `wPassiveFullColorClearChunks` records bounded cleanup;
- `wPassiveFullColorGeneration` binds state to `wRendererGeneration`;
- `wPassiveFullColorPaletteInvalidated` records a Yellow background-palette
  publication that has not yet been superseded by an authored commit;
- `wPassiveFullColorBGPaletteProtected` scopes the steady overworld call whose
  Yellow BG hardware transfer is suppressed;
- `wPassiveFullColorBGAttributesProtected` scopes `RedrawMapView` while its
  default palette command must not replace the authored bank-1 plane;
- `wPassiveFullColorAttributesInvalidated` records that Yellow replaced the
  base bank-1 authority and a complete passive rebuild is required;
- `wPassiveFullColorOverlaySuspended` prevents passive projection while a
  forced-Yellow full-screen attribute packet is authoritative;
- `wPassiveFullColorRoofRegion` records the coordinate-dependent Route 6 roof
  identity from the last authored palette commit;
- `wPassiveFullColorAttributeRectangle` is an aligned, padded 32x18 overlay
  plane whose first 20 bytes per row hold translated visible attributes; and
- `wPassiveFullColorDeferredRedrawState` owns one prepared or mirror-pending
  redraw transaction; `wPassiveFullColorRedrawStaging` holds its immutable
  destination and attribute records outside the overlay translation plane.
  The same serialized slot is named `wPassiveFullColorPaletteStaging` while an
  eight-palette fade is prepared, after redraw backpressure proves it idle.

`InitRendererOwnership` clears the complete private passive allocation before
any map can be treated as active. The allocation is unconditional and does not
alias the audit scheduler or its timing scratch.

Every active-state read validates the generation. A mismatch clears active and
pending work. VBlank repeats the map allowlist check before publishing. Cleanup
rejects unauthored chunk counts before deriving a VRAM address. Stale, reset,
pre-activation, or aliased state therefore produces no color write.

Helpers use the ownership core's `select_renderer_state_e` /
`restore_renderer_state_e` protocol outside VBlank. The interrupt path switches
WRAM stacklessly, restores WRAM bank 1 before popping, restores the interrupted
raw `SVBK`, and leaves `rVBK` as Yellow expects.

## Load-bearing invariants

1. Every normal, debug, and VC build exposes the same bounded passive slice;
   `PHASE2_AUDIT` may add diagnostics but MUST NOT gate its behavior.
2. Only the saved Color preference on admitted `OVERWORLD` or conventional
   interior maps is active.
3. Yellow owns bank-0 tiles, sprites, mechanics, overlay construction, fade
   progression, and timing; passive work is limited to paired bank-1 projection
   and authored eight-palette transformation.
4. Passive code writes only complete BG palettes and bank-1 BG attributes.
5. Every attribute comes from the selected authored 256-byte table or one of
   the two authored Celadon Mart map overrides.
6. Initial publication is LCD-off; every live transition is a bounded sequence
   of one-operation passive VBlanks with palettes committed only after the
   corresponding visible attribute plane is coherent.
7. Yellow's bank-0 redraw precedes the corresponding bank-1 attribute commit.
8. Every exit removes or neutralizes stale attributes.
9. Map identity, active state, and renderer generation agree before a visible
   write.
10. `rVBK`, `rSVBK`, interrupt state, stack state, and Yellow postconditions are
    restored exactly.

A prettier screenshot does not justify breaking one of these contracts.

## Evidence boundary

The active-runtime claim must be supported in each shipped product, not merely
by source inspection, the audit ROM, or synthetic machinery. Runtime journeys
select Color and Yellow within the same production binary. Verification spans
model tests, built-ROM probes, retained deterministic gates, and natural
gameplay journeys. Each catches different failures; none makes the others
redundant.

The synthetic renderer conformance checker proves its own modeled contract. It
does not prove that gameplay routes through the passive path. Phase 1 runtime
evidence proves ownership supersession mechanics, not global coloring. A single
screenshot can show palette quality but cannot prove scrolling, timing,
handoffs, flicker, or cutscene correctness. The exact commands and limitations
are in [TESTING.md](TESTING.md).

## Code map

- [Makefile](../Makefile): products and audit flags.
- [main.asm](../main.asm): production placement and audit-only diagnostic
  placement.
- [constants/full_color_constants.asm](../constants/full_color_constants.asm):
  ROM/WRAM banks, windows, and renderer constants.
- [ram/wram.asm](../ram/wram.asm): ownership, scheduler, passive, and staging
  state.
- [engine/full_color/passive_overworld.asm](../engine/full_color/passive_overworld.asm):
  live activation, translation, redraw, VBlank, and cleanup.
- [engine/full_color/passive_palette_refresh.asm](../engine/full_color/passive_palette_refresh.asm):
  steady overworld palette-publication scope and stale-authority reconciliation.
- [data/tilesets/full_color_overworld.asm](../data/tilesets/full_color_overworld.asm):
  current palette and attribute authority.
- [home/overworld.asm](../home/overworld.asm) and
  [home/vblank.asm](../home/vblank.asm): map and interrupt integration.
- `home/text_script.asm` and `home/start_menu.asm`: overlay restoration seams.

## Roadmap: Phases 3–9

The authoritative
[migration plan](../specs/full-colors/docs/migration-plan.md) separates the
remaining work and exit gates:

- **Phase 3 — palette and transfers:** map-aware palette selection; effects,
  reloads, connections, overlays, animations, replacements, and paired
  transfer destinations under retained renderer ownership. The shipped passive
  layer already covers its explicitly documented subset.
- **Phase 4 — overworld OAM:** authored picture-ID OBJ palettes after Yellow's
  final tile calculation, preserving follower offsets and DMA behavior.
- **Phase 5 — architecture stress:** combined pressure, poisoned handoff
  reconstruction, interrupted connections, timing margins, and deferral.
- **Phase 6 — bounded content runtime:** prove accepted data, overrides, and
  animation/field-replacement behavior reached by Pallet Town and Route 1.
- **Phase 7 — handoffs:** every concrete map-to-Yellow and Yellow-to-overworld
  edge, including resets, nesting, errors, and soak paths.
- **Phase 8 — ownership deletion:** remove superseded Yellow overworld tint,
  attribute, adapter, and restoration paths while preserving excluded scenes.
- **Phase 9 — release hardening:** numeric budgets, multi-frame behavior, soak
  coverage, and release/debug/VC reproducibility.

All 25 tilesets and all maps now have independently reviewed repository-owned
background content. That content completion is non-gating and does not imply
that the shipped toggle admits excluded maps.

Until the relevant phases are proved, maps outside the current outdoor and
conventional-interior passive set remain Yellow-owned. The migration plan may
widen retained ownership only after its phase gates; it does not narrow or
silently redefine the shipped passive set documented above.
Follow
[ADDING_CONTENT.md](ADDING_CONTENT.md) instead of editing the allowlist in
isolation.

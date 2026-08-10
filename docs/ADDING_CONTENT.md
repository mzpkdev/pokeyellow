# Adding content

This is the ROMhack-wide extension manual. It covers ordinary Yellow content
first—maps, events, text, encounters, graphics, and playable tests—then the
extra obligations imposed by the full-color migration. Read
[ARCHITECTURE.md](ARCHITECTURE.md) before changing shared runtime ownership and
[TESTING.md](TESTING.md) before interpreting a green
gate.

## The map ID is a positional ABI

[constants/map_constants.asm](../constants/map_constants.asm) assigns every map
an 8-bit ID and its block dimensions. That order indexes parallel tables,
including:

- [map header pointers](../data/maps/map_header_pointers.asm) and
  [header banks](../data/maps/map_header_banks.asm);
- [map music](../data/maps/songs.asm),
  [sprite sets](../data/maps/sprite_sets.asm), and
  [toggleable-object pointers](../data/maps/toggleable_objects.asm);
- [town-map entries](../data/maps/town_map_entries.asm); and
- [wild-data pointers](../data/wild/grass_water.asm).

Treat this ordering as an ABI, not a convenient list. Inserting or reordering a
constant changes every later numeric ID, including IDs saved in data, events,
warps, scripts, and external tools. Prefer an existing reserved `UNUSED_MAP_*`
slot when practical. If a new ID really is required, update every positional
table in the same change, preserve indoor grouping semantics, and audit every
numeric consumer. Table assertions catch length drift; they cannot prove that
row 42 still describes map 42.

## A map is a multi-file feature

Use a nearby map of the same kind as the template. A complete map normally
spans these owners:

- `constants/map_constants.asm`: ID, width, and height.
- `data/maps/headers/<Map>.asm`: tileset, block source, connection directions,
  and connection geometry.
- `data/maps/objects/<Map>.asm`: border block, warps, background events, object
  events, and return-warp data.
- `maps/<Map>.blk`: the block layout. Its dimensions must agree with the map
  constant.
- `scripts/<Map>.asm`: per-frame map script, script-pointer table, local event
  state, text-pointer table, and text wrappers.
- `text/<Map>.asm`: far text payloads, included in a suitable section of
  [text.asm](../text.asm).
- `data/wild/maps/<Map>.asm`: grass/water encounter rates and slots when the map
  has encounters; its positional pointer belongs in
  [data/wild/grass_water.asm](../data/wild/grass_water.asm).
- [maps.asm](../maps.asm): banked aggregation of the header, script, objects,
  and block binary. ROM-bank capacity and every `BANK(...)` consumer must remain
  correct.

Some maps intentionally share blocks, headers, scripts, or encounter data.
Reuse must be explicit in the pointer tables and aggregator; a copied map ID
does not acquire those relationships automatically.

### Recommended implementation order

1. Pick the map ID and dimensions. Decide whether this is a new identity or an
   intentional alias of existing data.
2. Create the `.blk` layout and select an existing tileset. Do not add graphics
   just because one block is missing; first check whether the tileset already
   contains an equivalent block.
3. Define the header and all connections. Check both sides of every seamless
   connection: direction, offset, strip geometry, destination ID, and the
   reciprocal connection where one is expected.
4. Define warps, signs/background events, objects, and `def_warps_to`. Keep text
   IDs aligned with the script's text-pointer table and object constants aligned
   with code that refers to them.
5. Add the script and text. Use event flags for persistent progression and the
   map script index for bounded local sequencing. Exercise repeat interaction,
   re-entry, save/continue, and already-completed states—not only the first run.
6. Add encounter data or an explicit no-encounter pointer. Verify rates, all ten
   slots, version-appropriate species, and water behavior where applicable.
7. Include the pieces in `maps.asm` and `text.asm`, then add the exact row to
   every map-ID-indexed table. Check music, sprite set, indoor/town-map grouping,
   toggles, special warps, and other feature tables that apply to the map.
8. Build immediately. Inspect the map in the `.sym`/`.map` products if bank
   placement changed, then play every entry, exit, connection, warp, object,
   script branch, and encounter surface.

### Graphics and tileset ownership

A map header selects a tileset; the `.blk` file selects blocks from that
tileset. The tileset owns block composition, collision, tile graphics, and any
animation assumptions. A new map does not own a private copy of those assets.
Changing a shared tileset can alter every map that uses it, so inventory its
consumers before editing blocks, collision, or graphics.

Keep identities explicit across the chain: map block → tileset block → tile ID
→ graphics/animation owner. Visual similarity is not proof of compatibility.
This rule matters in stock Yellow and becomes load-bearing under CGB attributes,
where the same tile ID also selects palette metadata.

## Add gameplay and E2E coverage

Reusable journeys live under
[tools/rom_tests/scenarios](../tools/rom_tests/scenarios); assertions live under
[tools/rom_tests/tests/e2e](../tools/rom_tests/tests/e2e). Current journeys are
layered: `new_game.py` reaches the bedroom, `oaks_lab.py` builds on it,
`viridian_city.py` continues north, and `parcel_delivery.py` continues the
quest.

For a new path:

1. Start a fresh emulator and reach the state through controller input and
   natural transitions. Memory reads may observe progress; they must not
   teleport the player, force scripts, or manufacture expected VRAM.
2. Put reusable navigation in a scenario module and assertions in the test.
   Bound every loop and name the expected map, coordinate, script, or battle
   condition in failure messages.
3. Assert gameplay state first—map, position, events, party, inventory, or
   battle—then renderer state and pixels where relevant.
4. Cover entry, interaction, completion, departure, re-entry, and save/continue.
   Capture named failure images and observe multiple frames around flicker-prone
   transitions.

Committed snapshots under `tools/rom_tests/snapshots` are optional golden
evidence, not a substitute for semantic assertions. Update only the intended
snapshot with the intended ROM, rerun without update mode, inspect the PNG and
diff, and obtain fresh review. Never bulk-bless failures.

## Full-color extension recipes

The current playable color renderer is deliberately narrower than the ROMhack:
normal, debug, and VC products offer Color for the 34 city and route maps using
`OVERWORLD` and conventional interiors using tileset IDs `REDS_HOUSE_1`
through `FACILITY`, except `FOREST`, `SHIP_PORT`, and `CAVERN`; the 19
admitted interior tilesets cover 162 maps.
Yellow mode and unsupported maps use Yellow presentation. Yellow still owns
bank-0 tile graphics, sprites, animations, overlay/menu construction, battles,
mechanics, fade progression, and scheduling. The passive layer may install
complete BG palettes, transform those palettes at Yellow's fade seam, and
publish paired VRAM-bank-1 attributes only. `PHASE2_AUDIT` adds diagnostics and certification
surfaces; it never gates this player-visible behavior.

### Add a map compatible with the Phase 2 slice

A shared `OVERWORLD` tileset plus a city/route map ID, or one of the authored
conventional-interior tileset IDs, defines the current playable set. All maps
that meet either condition are admitted through one runtime predicate.

Closure comes before adding another map or tileset. Before widening this set:

1. Add the source scene root to `PHASE2_HOSTILE_SCENE_ROOTS` in
   [source_discovery.py](../tools/rom_tests/full_color/source_discovery.py).
2. Update the concrete-slice authorities in
   [phase2_measurements.py](../tools/rom_tests/full_color/phase2_measurements.py):
   root rows and planned IDs, edge classifications, closed directions, required
   edges/writers, reviewed ROM pointer writes and pinned audit identity, hard-
   coded header predicates, and the returned concrete-slice identity.
3. Add the root pointer, in stable lexical order, to
   [phase2_audit.asm](../engine/full_color/phase2_audit.asm) and update its exact
   size assertion.
4. Reconcile discoveries against
   [phase2-planned-subjects.json](../specs/full-colors/definitions/phase2-planned-subjects.json)
   and the four reviewed inventories:
   [assignments.json](../specs/full-colors/inventory/assignments.json),
   [mutations.json](../specs/full-colors/inventory/mutations.json),
   [scenes.json](../specs/full-colors/inventory/scenes.json), and
   [writers.json](../specs/full-colors/inventory/writers.json). Update the
   authoritative
   [phase2-hostile-slice-representation.json definition](../specs/full-colors/definitions/phase2-hostile-slice-representation.json)
   when the boundary changes. That definition is a reviewed input and is
   distinct from the generated evidence file with the same basename under
   `specs/full-colors/evidence/`.
5. Build all four products and generate the unreviewed proposal chain. Review
   every new subject and hash delta, then deliberately incorporate the accepted
   changes into the source transition and four inventories, including reviewer
   metadata supplied by the human review. No Make target performs that
   acceptance. Production runtime coverage must select Color and Yellow within
   the same shipped binary; the audit product supplies only its additional
   diagnostic evidence. Never hand-edit derived evidence.

```sh
make yellow_debug yellow_phase2_audit pokeyellow.gbc pokeyellow_vc.gbc
make measure-full-color-phase2-audit
# Human review and deliberate authority updates happen here.
.venv/bin/python -m tools.rom_tests.full_color.phase2_measurements \
  --root . \
  --authority-reviewed \
  --output specs/full-colors/evidence/phase2-hostile-slice-representation.json
make test-full-color-audit
```

The runtime predicate in
[passive_overworld.asm](../engine/full_color/passive_overworld.asm) checks map
range and tileset for both ordinary and VBlank paths. Do not reintroduce a
second map allowlist. Extend `FullColorOverworldRoofAssignments` in lockstep
with the city/route map-ID boundary; extend the interior pointer tables in
lockstep with the tileset-ID ABI.

Then extend linked-ROM coverage in
[test_passive_overworld_rom.py](../tools/rom_tests/tests/unit/full_color/test_passive_overworld_rom.py)
and timing coverage in
[test_passive_overworld_timing.py](../tools/rom_tests/tests/unit/full_color/test_passive_overworld_timing.py)
for LCD-off entry, all 1,024 attributes, row/column redraw, palette deferral,
seamless crossings, cleanup, generation mismatch, and bank/register
restoration. Rebuild, regenerate evidence again because source and ROM
identities changed, run the full verification contracts, add a natural
cold-boot checkpoint,
and manually inspect both directions of every boundary.

### Map-aware roofs

Palette 6 keeps the common outdoor edge colors and replaces its middle pair
from `FullColorOverworldRoofAssignments`. The assignments are reviewed,
repository-owned city and route content. Route 6 selects Saffron colors in its
top rows and Vermilion colors elsewhere.

### Change palettes or tile attributes

[full_color_overworld.asm](../data/tilesets/full_color_overworld.asm) and
[full_color_interiors.asm](../data/tilesets/full_color_interiors.asm) are the
current authorities:

- `FullColorOverworldBGPalettes` is exactly 64 bytes: eight complete CGB BG
  palettes of four RGB555 colors;
- `FullColorOverworldRoofAssignments` has one row per city/route map ID and
  selects one of eleven two-color roof pairs;
- `FullColorOverworldTileAttributes` is exactly 256 bytes, indexed by the full
  bank-0 tile ID; and
- every attribute must use legal CGB bits. The present table selects bank 0 and
  authors no priority.
- every interior palette payload is exactly 64 bytes and every interior
  assignment table is exactly 256 bytes; `$00`–`$5f` are independently
  reviewed against Yellow graphics and `$60`–`$ff` are palette 7.

Never derive a palette with `tile_id & 7`. Tile IDs are identities, not palette
classes. Preserve repository-owned source, provenance evidence, complete tables,
and size assertions. Independently verify any new authority before updating the
permitted digests and semantic checks in
[test_overworld_color_data.py](../tools/rom_tests/tests/unit/full_color/test_overworld_color_data.py).
Make linked-ROM tests read actual ROM bytes, regenerate Phase 2 evidence, run
the affected verification contracts, and review natural gameplay captures.

### Know the roadmap boundary

Do not hide later ownership work in a palette edit. The playable passive slice
already has map-aware roof selection, paired scroll/redraw and selected overlay
transfers, and eight-palette fade transforms. The roadmap phases describe
migration into retained renderer ownership, not missing passive behavior.
Phase 4 owns overworld OAM; Phase 5 stress-tests the architecture;
Phase 6 closes runtime use of map-specific overrides, animation, and
field-replacement behavior in its bounded proof slice;
Phase 7 closes every handoff; Phase 8 removes old overworld ownership; and Phase
9 hardens release timing and products. The repository-owned all-25-tileset and all-map
background corpus is already authored and reviewed; excluded maps remain
non-gating Yellow presentation until a separately approved runtime-admission
change. The authoritative exit gates live in the
[migration plan](../specs/full-colors/docs/migration-plan.md).

## Verification before handoff

For ordinary content, build the affected products and run focused unit/E2E
checks plus natural playthroughs. For a full-color extension, also run:

```sh
make test-full-color-fast
make test-unit
make test-full-color-harness-contracts
make test-full-color-evidence
make test-full-color-audit
make test-full-color-smoke
make test-full-color-renderer-contracts
make test-full-color-renderer-runtime
make test-full-color-e2e-core
make test-full-color-e2e-renderer
make test-full-color-e2e-journey
make test-full-color-certify
```

Preserve independent stable-evidence captures, runtime evidence, synthetic
checker mutation sensitivity, time bounds, separation of audit-only
diagnostics from production behavior, and byte-identical stable artifacts.
Core, Renderer, and Journey are separate gameplay authorities; certification
runs all three. Screenshots add evidence; they do not replace it.

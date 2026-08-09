# Technical debt register

## Purpose and rules

This register explains intentional compromises that a cold operator could
otherwise mistake for finished architecture, dead code, or permission to widen
the renderer. It covers the current full-color initiative and the ROMhack-wide
contracts exposed by that work.

Three categories must stay distinct:

- **Intentional constraint:** a boundary that protects current correctness. It
  is not debt until an approved change needs behavior outside the boundary.
- **Technical debt:** a retained compromise whose trigger has been reached or
  whose risk must be paid down before a named capability can ship.
- **Planned work:** an accepted future capability with its own phase and gate.
  Planned work is not evidence that the implementation exists today.

An entry records a decision; it does not authorize its own scope. Work still
needs an approved plan or task, fresh source and ROM evidence, review, and the
gates required by [AGENTS.md](AGENTS.md) and the
[development workflow](docs/DEVELOPMENT_WORKFLOW.md). Update an entry's status,
links, and proof when the underlying code changes. Do not close an entry from a
source diff, build, screenshot, or synthetic test alone when its acceptance
proof requires linked-ROM or natural-gameplay evidence.

Current product truth: normal, debug, and VC products all ship the saved
`COLOR/YELLOW` option and bounded passive map-background renderer for the 34
`OVERWORLD` maps plus 162 maps using the 19 admitted interior tilesets.
`PHASE2_AUDIT` adds diagnostics and certification surfaces only; it never gates
player-visible behavior. Broader scheduler ownership, OAM color, animation
ownership, and all-map color remain proposed in the
[migration plan](specs/full-colors/docs/migration-plan.md).

## Status and priority

Statuses:

- **CONSTRAINT:** safe boundary; revisit only when its trigger is reached.
- **TRIGGERED:** an approved change now depends on resolving the entry.
- **PLANNED:** assigned to a future migration phase, not yet active.
- **ACTIVE:** debt exists in a live product and should be reduced now.
- **BLOCKED:** trigger is reached, but a named dependency is not complete.
- **CLOSED:** retirement or activation proof is linked in the entry.

Priorities:

- **P0:** blocks safe production promotion or can corrupt visible/game state.
- **P1:** blocks a promised capability or can create false release confidence.
- **P2:** raises maintenance cost but does not presently threaten correctness.

## Index

| ID | Status | Priority | Subject |
| --- | --- | --- | --- |
| [FC-001](#fc-001-production-passive-runtime) | CLOSED | P0 | Production passive runtime |
| [FC-002](#fc-002-map-and-roof-dispatch-acceptance) | ACTIVE | P1 | Map and roof dispatch acceptance |
| [FC-003](#fc-003-yellow-owned-scene-fallbacks) | PLANNED | P1 | Yellow-owned scene fallbacks |
| [FC-004](#fc-004-palette-ownership-flashes) | CLOSED | P0 | Palette ownership flashes |
| [FC-005](#fc-005-atomic-mode-handoff) | CLOSED | P0 | Atomic mode handoff |
| [FC-006](#fc-006-passive-state-aliases-dormant-scheduler-storage) | CLOSED | P1 | WRAM alias with dormant scheduler |
| [FC-007](#fc-007-dormant-renderer-architecture) | PLANNED | P1 | Dormant scheduler and lifecycle |
| [FC-008](#fc-008-remove-phase2_audit-after-diagnostic-migration) | ACTIVE | P1 | Remove `PHASE2_AUDIT` after diagnostic migration |
| [FC-009](#fc-009-product-link-and-reachability-partition) | CLOSED | P0 | Product link partition |
| [FC-010](#fc-010-object-color-path-is-only-scaffolding) | PLANNED | P1 | OAM color scaffolding |
| [FC-011](#fc-011-audit-evidence-still-needs-a-diagnostic-product) | ACTIVE | P1 | Diagnostic-product evidence dependency |
| [FC-012](#fc-012-generated-inventory-transition-cost) | ACTIVE | P1 | Generated inventory transitions |
| [FC-013](#fc-013-hosted-gameplay-coverage) | CLOSED | P1 | Hosted gameplay coverage |
| [FC-014](#fc-014-donor-content-is-incomplete-for-yellow) | BLOCKED | P1 | Incomplete Yellow color content |
| [WF-001](#wf-001-branch-and-release-evidence-hygiene) | TRIGGERED | P1 | Branch and release evidence hygiene |

## Production quarantine

The rule is to remove unproved machinery from **production reachability**, not
from the repository. Delete retained code only after its replacement or
obsolescence is proved.

| Surface | Production disposition | Audit/repository disposition | Activation or removal trigger |
| --- | --- | --- | --- |
| Passive palettes, tile attributes, redraw preparation, bounded VBlank commit, cleanup | Shipped unconditionally in normal, debug, and VC; runtime preference and map eligibility gate presentation | Same behavior in the audit product | Keep bounded until broader ownership and content phases close |
| Phase 2 provenance, audit-only SRAM/WRAM mailboxes and trace carriers, callable audit roots | Unreachable and absent from release/debug/VC symbol maps | Temporarily keep under `PHASE2_AUDIT` for diagnostics and proof; preserve the separate Phase 1 `_DEBUG` SRAM protocol | Remove `PHASE2_AUDIT` after every diagnostic consumer and retained evidence contract has migrated |
| Ownership scheduler, lifecycle planes, palette scheduler, paired transfers, OAM mapper | Unreachable in production until its owning migration phase | Keep buildable and tested as dormant seams | Activate one bounded subsystem only after its phase inventory and exit gate close; remove if the chosen production design supersedes it |

The passive runtime no longer belongs behind an audit guard. A blanket removal
of the remaining flag is still forbidden until its consumers migrate: it could
ship Phase 2 command channels or provenance markers, or invalidate retained
evidence. This quarantine does not remove or weaken the Phase 1 `_DEBUG`
mailbox or runtime evidence.

## Debt entries

### FC-001: Production passive runtime

- **Status / priority:** CLOSED / P0.
- **What exists:** normal, debug, and VC products all link the saved
  Color/Yellow option and bounded map-background passive renderer. The
  audit product runs the same player-visible behavior.
- **Why it changed:** audit isolation proved the initial slice, then the
  operator approved it as ordinary product behavior without approving the
  diagnostic surface or dormant architecture for promotion.
- **Resolved risk:** production no longer needs `PHASE2_AUDIT` to reach Color,
  so enabling the feature cannot implicitly enable audit commands or markers.
- **Dependencies closed:** FC-004, FC-005, and FC-009. FC-008 and FC-011 remain
  follow-up debt for deleting the now-diagnostic-only flag and migrating its
  evidence consumers.
- **Closure proof:** the product matrix checks all three shipped ROMs for the
  same toggle and bounded runtime while excluding audit-only symbols; natural
  play selects Color and Yellow inside one shipped binary and proves
  unsupported-map fallback.
- **Sources:** [Makefile](Makefile), [main.asm](main.asm),
  [passive_overworld.asm](engine/full_color/passive_overworld.asm), and the
  [renderer product matrix](docs/FULL_COLOR_RENDERER.md#current-scope).

### FC-002: Map and roof dispatch acceptance

- **Status / priority:** ACTIVE / P1.
- **What exists:** one predicate admits the 34 city/route maps using
  `OVERWORLD` plus conventional interiors from `REDS_HOUSE_1` through
  `FACILITY`, excluding `FOREST`, `SHIP_PORT`, and `CAVERN`; those 19 tilesets
  cover 162 maps, and donor-derived pointer tables
  select complete palettes and attributes, while the outdoor roof table keeps
  the Route 6 Saffron/Vermilion split.
- **Why retained:** implementation is playable, but manual traversal and visual
  acceptance have not closed the wider map set.
- **Current risk:** an incorrect roof row or transition can show the wrong
  palette despite valid tile attributes.
- **Dependencies:** manual play review across representative cities, routes,
  connections, menus, battles, and returns.
- **Right-time trigger:** reached by the playable `OVERWORLD` expansion.
- **Recommendation:** keep the single predicate and explicit roof identities;
  correct rejected visual cases in data rather than adding map-shaped code paths.
- **Acceptance proof:** source and built-ROM inventory show one authority;
  supported and unsupported maps agree at load and VBlank; each admitted map
  has reviewed content and natural transition coverage.
- **Sources:** [passive_overworld.asm](engine/full_color/passive_overworld.asm),
  [full_color_overworld.asm](data/tilesets/full_color_overworld.asm), and the
  [extension recipe](docs/ADDING_CONTENT.md#full-color-extension-recipes).

### FC-003: Yellow-owned scene fallbacks

- **Status / priority:** PLANNED / P1.
- **What exists:** conventional interior map backgrounds are admitted, but
  menus, dialogue, battles, cutscenes, sprites, effects, and animations remain
  Yellow-owned; the passive layer restores a colored map after some overlays.
- **Why retained:** Yellow remains the only proved owner for those scenes, and
  coloring them by inferring from background tile IDs previously corrupted
  geometry and progression.
- **Current risk:** fallback edges can expose stale attributes or one-frame
  palette changes; future contributors may mistake stock-looking scenes for a
  completed full-color product.
- **Dependencies:** Phase 3 effects/transfers, Phase 4 OAM, Phase 7 handoffs,
  and Phase 8 ownership deletion.
- **Right-time trigger:** reached separately for each scene class when product
  scope promises color there or a transition cannot be made visually atomic.
- **Recommendation:** inventory concrete handoff edges and migrate one resource
  owner at a time; do not add scene-shaped exceptions to the passive map layer.
- **Acceptance proof:** each migrated scene has an exclusive writer, explicit
  entry/exit reconstruction, frame-strip review, built-ROM probes, and natural
  gameplay in both player modes.
- **Sources:** [renderer scene boundaries](docs/FULL_COLOR_RENDERER.md#menus-maps-dialogue-and-battles),
  [migration phases](specs/full-colors/docs/migration-plan.md), and
  [acceptance criteria](specs/full-colors/docs/acceptance-criteria.md).

### FC-004: Palette ownership flashes

- **Status / priority:** CLOSED / P0.
- **What exists:** Yellow's `LoadGBPal`, fades, menus, dialogue, and battle
  transitions may replace global CGB BG palettes; the passive layer detects
  replacement and queues republication in a later VBlank.
- **Why retained:** deferred publication respects visible-time and VBlank
  budgets better than an immediate palette write.
- **Resolution:** passive republication is suspended while Yellow owns an
  overlay, fade, or battle transition, and the saved preference is reconciled
  once at the bounded restoration boundary.
- **Closure proof:** frame strips and natural input tests show no mixed-owner
  frame across Start, Options, dialogue, party, battle, return, save, reset, and
  Continue; timing evidence still permits only bounded VBlank work.
- **Sources:** [passive_palette_refresh.asm](engine/full_color/passive_palette_refresh.asm),
  [palette publication contract](docs/FULL_COLOR_RENDERER.md#scrolling-and-vblank),
  and [testing limitations](docs/TESTING.md#false-confidence-traps).

### FC-005: Atomic mode handoff

- **Status / priority:** CLOSED / P0.
- **What exists:** Options changes the saved preference while the active
  presentation remains latched. The outer menu close performs the bounded
  Color-to-Yellow or Yellow-to-Color reconciliation; unsupported maps resolve
  to Yellow without erasing Color preference.
- **Resolved risk:** live preference writes cannot expose a mixed palette and
  bank-1 attribute plane or leave stale pending work active.
- **Closure proof:** repeated/no-op changes, supported/unsupported maps,
  maps in both directions, save/reset/Continue, and every overlay edge prove
  one coherent reconciliation and no stale write.
- **Sources:** [passive lifecycle](docs/FULL_COLOR_RENDERER.md#map-load-and-publication),
  [save declarations](ram/wram.asm), [Options engine](engine/menus/options.asm),
  and [handoff requirements](specs/full-colors/docs/requirements.md).

### FC-006: Passive state aliases dormant scheduler storage

- **Status / priority:** CLOSED / P1.
- **What exists:** every product uses the same dedicated passive allocation;
  the audit scheduler and diagnostic layouts remain separate from it.
- **Resolution:** promotion allocated standalone passive state instead of
  depending on the former audit-only lifetime alias.
- **Closure proof:** linker symbols and hostile overlap tests prove unique,
  bounded storage in every product that can reach both owners.
- **Sources:** [WRAM declarations](ram/wram.asm),
  [scheduler.asm](engine/full_color/scheduler.asm), and
  [bank and memory ownership](docs/ARCHITECTURE.md#banks-and-memory-ownership).

### FC-007: Dormant renderer architecture

- **Status / priority:** PLANNED / P1.
- **What exists:** ownership, scheduler, lifecycle, palette, transfer, and OAM
  modules preserve measured contracts and synthetic/callable test seams, but
  they do not drive the playable slice.
- **Why retained:** later phases need explicit ownership, generation,
  reconstruction, transfer, and identity concepts; deleting them now discards
  reviewed experiments.
- **Current risk:** compiled or callable code can be mistaken for an active
  renderer, and its design may diverge from the minimal passive production
  path before activation.
- **Dependencies:** each module's owning migration phase and a fresh inventory
  of actual Yellow writers.
- **Right-time trigger:** activate a module only when a bounded production
  capability needs it and its phase prerequisites, inventory, and gates close;
  retire it when the selected production design proves it redundant.
- **Recommendation:** keep it quarantined, buildable, and testable. Activate or
  delete one subsystem per reviewed change, never the directory as a unit.
- **Acceptance proof:** activation requires natural reachability and exclusive
  writer evidence; retirement requires symbol/source absence plus preserved
  acceptance coverage for the behavior it modeled.
- **Sources:** [active path and scaffolding](docs/FULL_COLOR_RENDERER.md#active-path-and-retained-scaffolding),
  [engine/full_color](engine/full_color), and the
  [migration plan](specs/full-colors/docs/migration-plan.md).

### FC-008: Remove `PHASE2_AUDIT` after diagnostic migration

- **Status / priority:** ACTIVE / P1.
- **What exists:** `PHASE2_AUDIT` now adds only Phase 2 SRAM/WRAM mailboxes,
  trace records, audit commands, provenance, callable roots, and the separate
  audit product used by diagnostic and certification consumers. The toggle and
  passive renderer are unconditional in normal, debug, and VC products.
- **Why retained:** current Phase 2 probes and retained evidence still consume
  these carriers to make bank, rejection, inventory, and provenance claims
  observable. The separate Phase 1 `_DEBUG` mailbox remains an independent
  runtime evidence protocol.
- **Current risk:** the obsolete product flag duplicates layouts and product
  identities, encourages tests to confuse diagnostics with behavior, and keeps
  a permanent-looking build surface after behavior ceased to depend on it.
- **Dependencies:** migrate every Phase 2 diagnostic consumer and retained
  evidence identity to a product-neutral debug protocol or another reviewed
  authority; close FC-011 without weakening runtime evidence.
- **Right-time trigger:** reached now that every shipped product has the same
  player-visible renderer behavior.
- **Recommendation:** keep the remaining flag narrowly diagnostic while those
  consumers exist. Then delete the `PHASE2_AUDIT` define, audit-only target,
  conditional mailboxes/carriers/roots, and obsolete product identities in one
  reviewed migration. Never expose them in production as an intermediate step.
- **Acceptance proof:** source and symbol scans contain no `PHASE2_AUDIT` or
  Phase 2-only carrier; all former diagnostic claims have named replacement
  producers and migrated retained evidence; production mode-selection,
  product-linkage, evidence determinism, and runtime checks remain green.
- **Sources:** [debug_runtime.asm](engine/full_color/debug_runtime.asm),
  [phase2_audit.asm](engine/full_color/phase2_audit.asm),
  [HRAM declarations](ram/hram.asm), and
  [audit observability](tools/rom_tests/full_color/phase2_audit_observability.py).

### FC-009: Product link and reachability partition

- **Status / priority:** CLOSED / P0.
- **What exists:** passive code, data, state, hooks, and the saved toggle are
  linked in normal, debug, and VC products. Audit-only diagnostics remain in a
  separate partition, and broader scheduler/OAM machinery remains inactive.
- **Resolved risk:** shipping the passive slice no longer requires promoting
  the audit command surface or treating linked future seams as active owners.
- **Closure proof:** the four-product matrix proves expected production
  symbols, forbidden diagnostic-symbol absence, runtime mode reachability,
  bank/layout bounds, and retained audit identity semantics.
- **Sources:** [main.asm](main.asm), [layout.link](layout.link),
  [product variants](docs/ARCHITECTURE.md#product-variants-and-experimental-isolation),
  and [ROM discovery](tools/rom_tests/full_color/rom_discovery.py).

### FC-010: Object color path is only scaffolding

- **Status / priority:** PLANNED / P1.
- **What exists:** OBJ palette payloads, OAM mapping, fallback records, and
  scheduler requests exist in audit scaffolding; the passive slice does not
  publish object palettes or alter Yellow's OAM.
- **Why retained:** the code records the intended final-picture-identity rule
  and deterministic palette-0 fallback for Phase 4.
- **Current risk:** activating it before Yellow's final tile calculation can
  recolor the wrong sprite, break follower Pikachu offsets, or race DMA.
- **Dependencies:** Phase 4 writer inventory, complete picture-ID assignments,
  and shadow-to-hardware OAM timing proof.
- **Right-time trigger:** player scope promises colored overworld objects, or
  background-only color is no longer an accepted slice boundary.
- **Recommendation:** map palette bits from final authored picture identity
  after Yellow completes tile calculation; preserve bits 3-7; commit one
  complete shadow-OAM batch through the existing DMA contract.
- **Acceptance proof:** player, Pikachu, NPC, fallback, mutation, bank, timing,
  and complete-DMA tests plus natural movement/cutscene frame review close
  Phase 4.
- **Sources:** [oam.asm](engine/full_color/oam.asm),
  [Phase 4 plan](specs/full-colors/docs/migration-plan.md#phase-4-overworld-oam),
  and [AC-OW-05](specs/full-colors/docs/acceptance-criteria.md).

### FC-011: Audit evidence still needs a diagnostic product

- **Status / priority:** ACTIVE / P1.
- **What exists:** production evidence proves Color and Yellow reachability in
  the same shipped binaries and diagnostic-symbol exclusion. Separate Phase 2
  verification still binds provenance, inventory rows, and observability to an
  exact audit product.
- **Why retained:** the remaining diagnostic evidence prevents source-only,
  hand-edited, or stale-ROM claims from passing while its replacement is
  designed.
- **Current risk:** retaining a distinct audit product can be misread as proof
  that player-visible Color is audit-only, and it blocks deletion of
  `PHASE2_AUDIT` even though behavior no longer uses that flag.
- **Dependencies:** replacement producers for every Phase 2 diagnostic claim,
  preserved schema/provenance integrity, and FC-008.
- **Right-time trigger:** reached when the production evidence contract began
  selecting both modes in the same shipped product.
- **Recommendation:** migrate audit consumers and retained evidence to named,
  product-neutral diagnostic authorities without overwriting historical
  semantics. Then remove the audit-product identity and close FC-008.
- **Acceptance proof:** migrated generators reject wrong ROMs, stale hashes,
  forbidden symbols, false mode reachability, and hand-edited payloads without
  requiring an audit-behavior variant.
- **Sources:** [phase2_measurements.py](tools/rom_tests/full_color/phase2_measurements.py),
  [phase2_audit_observability.py](tools/rom_tests/full_color/phase2_audit_observability.py),
  [Phase 2 definition](specs/full-colors/definitions/phase2-hostile-slice-representation.json),
  and [evidence rules](docs/TESTING.md#full-color-evidence-stack).

### FC-012: Generated inventory transition cost

- **Status / priority:** ACTIVE / P1.
- **What exists:** reviewed source discovery, ROM discovery, assignments,
  rejections, inventories, and evidence bind exact hashes and semantic subjects.
- **Why retained:** the friction is deliberate: it makes a new hook, writer,
  root, or product identity visible instead of silently escaping the audit.
- **Current risk:** duplicated roots and hand-maintained transition metadata can
  become stale; operators may bypass the producer or edit JSON until it passes.
- **Dependencies:** official generators in `tools/rom_tests/full_color` and
  reviewed authority under `specs/full-colors`.
- **Right-time trigger:** any source, linked-ROM root, writer set, product
  identity, or accepted scene changes.
- **Recommendation:** keep closure before activation. Improve generators and
  error messages when the transition is hard, but never relax exact hashes,
  typed provenance, stale-row rejection, or mutation sensitivity.
- **Acceptance proof:** the official generator produces a reviewed semantic
  diff; stale, phantom, omitted, and hand-mutated rows fail; two independent
  evidence captures remain byte-identical.
- **Sources:** [baseline_inventory.py](tools/rom_tests/full_color/baseline_inventory.py),
  [source_discovery.py](tools/rom_tests/full_color/source_discovery.py),
  [phase2_measurements.py](tools/rom_tests/full_color/phase2_measurements.py),
  and the [evidence stack](docs/TESTING.md#full-color-evidence-stack).

### FC-013: Hosted gameplay coverage

- **Status / priority:** CLOSED / P1.
- **What exists:** hosted CI runs Core, Renderer, and Journey independently
  against same-revision normal and debug products. The journeys cover new game,
  Pallet/Route 1, Oak's capture, menus/dialogue, battles, fallback,
  save/reset/Continue, and parcel delivery through natural inputs.
- **Resolved risk:** a pull request can no longer receive a green
  `Merge Gate` result when any hosted gameplay suite fails, skips, or is
  cancelled.
- **Remaining boundary:** manual visual review still catches flicker, aesthetic
  failures, hardware differences, and unencoded scene coverage. Hosted E2E does
  not turn those human claims into automated facts.
- **Closure proof:** `E2E (Core)`, `E2E (Renderer)`, and `E2E (Journey)` consume
  one build artifact, retain failure diagnostics, and feed the blocking
  `Merge Gate` job.
- **Sources:** [journey tests](tools/rom_tests/tests/e2e/journey/),
  [scenario helpers](tools/rom_tests/scenarios), and
  [hosted coverage](docs/TESTING.md#what-hosted-ci-covers).

### FC-014: Donor content is incomplete for Yellow

- **Status / priority:** BLOCKED / P1.
- **What exists:** donor-derived `OVERWORLD` and conventional-interior
  tile-to-attribute tables, shared complete BG palette sets, and map-aware roof
  colors cover the admitted map slice. The donor offers useful Gen 1
  organization and artistic evidence, not
  a drop-in Yellow renderer.
- **Why retained:** the accepted data is a strong canary and avoids inventing
  colors already authored for a related engine.
- **Current risk:** treating donor mappings as authoritative can miscolor
  Yellow-exclusive graphics, roofs, maps, follower Pikachu, animations, and
  tilesets while all attribute bytes remain technically legal.
- **Dependencies:** future independent authoring/validation for the remaining
  Yellow tilesets and overrides.
- **Right-time trigger:** adding any map whose exact tileset, roof, override,
  or animation identity differs from the accepted slice.
- **Recommendation:** keep the accepted bounded map payload pinned to its
  exact authorities. Treat every other donor value as candidate provenance
  and validate it against Yellow graphics and behavior. Keep mechanisms separate
  from authored data.
- **Acceptance proof:** every Yellow tileset, roof, override, animation, and
  special case has inventory closure, atlas/table review, semantic full-byte
  attribute tests, and natural visual acceptance.
- **Sources:** [full_color_overworld.asm](data/tilesets/full_color_overworld.asm),
  [full_color_interiors.asm](data/tilesets/full_color_interiors.asm),
  [future all-25 plan](specs/full-colors/docs/migration-plan.md#future-non-gating-work-all-25-tileset-authoring),
  [R8.2](specs/full-colors/docs/requirements.md), and
  [full-color extension recipes](docs/ADDING_CONTENT.md#full-color-extension-recipes).

### WF-001: Branch and release evidence hygiene

- **Status / priority:** TRIGGERED / P1.
- **What exists:** merged work can leave local `main`, product hashes,
  retained artifacts, and operator plans behind the remote truth. The workflow
  requires exact-path staging, reviewed commits, feature branches, early draft
  PRs, and hosted checks, but those are human discipline rather than a single
  machine-enforced transaction.
- **Why retained:** operator state and generated evidence cannot safely be
  swept into every commit; direct local iteration needs flexibility.
- **Current risk:** branching from stale local `main`, pushing unrelated
  `.preemdeck/` or `test-results/`, hand-editing evidence, or updating product
  hashes before final verified ROMs can make review and reproduction false.
- **Dependencies:** repository instructions, protected remote branch policy,
  official evidence producers, and product identity gates.
- **Right-time trigger:** reached for the production toggle because it changes
  release/debug/VC identities and must begin from merged `origin/main`.
- **Recommendation:** fetch `origin main`, branch from `origin/main`, open
  a draft PR after the first reviewed green commit, stage exact owned paths,
  regenerate evidence only through its producer, and update release hashes only
  from final verified products. Never commit `.preemdeck/` plans.
- **Acceptance proof:** PR history shows the correct base and scoped commits;
  worktree inspection shows no unrelated files; product `.gbc`/`.map`/`.sym`
  identities agree with evidence; required local checks, manual play, and
  hosted CI are recorded before merge.
- **Sources:** [AGENTS.md](AGENTS.md),
  [development workflow](docs/DEVELOPMENT_WORKFLOW.md#handoff-commit-and-pull-request-discipline),
  [Makefile](Makefile), and [roms.sha1](roms.sha1).

## Intentional constraints and non-goals

These are not shortcuts to remove. A constraint becomes debt only when its
trigger is reached and the replacement has a proved boundary.

### IC-001: Color is not audit-gated

**Status:** the former audit-only constraint is retired. Normal, debug, and VC
products all ship the bounded renderer. The remaining `PHASE2_AUDIT` flag is
diagnostic debt tracked by FC-008 and FC-011, not a behavior boundary.

### IC-002: Bounded authored map tilesets

The slice stays limited to city/route maps using `OVERWORLD` and conventional
interiors using IDs `REDS_HOUSE_1` through `FACILITY`, except `FOREST`,
`SHIP_PORT`, and `CAVERN`. `PLATEAU`, `BEACH_HOUSE`, and other unsupported tilesets remain
Yellow-owned until independently authored content exists.

### IC-003: Yellow owns bank-0 tiles and gameplay

Passive color may translate only completed Yellow background tiles into BG
palettes and bank-1 attributes. It must not change scripts, mechanics, tile
geometry, movement, or cutscene progression.

### IC-004: Yellow owns excluded scenes

Menus, dialogue, battles, effects, sprites, and cutscenes stay Yellow until
their concrete migration phases close. Admitting an interior map background
does not color those scene classes by itself.

### IC-005: One bounded passive VBlank operation

Yellow row/column redraw wins; palette publication defers; cleanup is chunked.
Performance pressure must improve preparation or measured budgets, not combine
unbounded work in one interrupt.

### IC-006: Complete authored attributes and palettes

Every tile uses the reviewed 256-byte table, and palette publication writes a
complete set. Arithmetic fallbacks such as `tile_id & 7`, partial palettes, or
sampling VRAM as an oracle are non-goals.

### IC-007: Phase 2 audit diagnostics stay out of production

Phase 2 audit mailboxes, provenance carriers, synthetic roots, and dormant
subsystems remain audit-only even when the minimal passive runtime ships. The
separate Phase 1 `_DEBUG` mailbox and trace protocol remain available to
runtime evidence until deliberately replaced with equivalent proof.

### IC-008: Synthetic and callable evidence stays narrow

The conformance checker proves its modeled contract; callable ROM tests prove
controlled entry points. Neither may claim natural reachability, playability,
visual stability, or artistic quality.

### IC-009: Donor content outside the accepted map payload is candidate evidence

The pinned authorities accepted for the outdoor and conventional-interior
palette and 96-byte attribute payloads remain authoritative for that payload
only. All other material from `git@github.com:dannye/pokered-gbc.git` can supply only
organization and artistic candidates. Yellow-specific values outside that
accepted payload still require independent authoring and validation; no donor
import can waive Yellow's inventories or acceptance gates.

## ROMhack-wide recommendations

- Treat map, tileset, species, move, item, sprite, WRAM, HRAM, and SRAM order as
  positional ABI. Update parallel tables and assertions together, then prove
  the linked addresses and sizes.
- Treat ROM banks and `layout.link` placement as evidence-bearing contracts.
  Verify `.map` and `.sym` output, far-call boundaries, and restored ROM/WRAM/
  VRAM bank state for every new shared hook.
- Reserve “natural gameplay” for cold-boot input-driven scenarios. State
  injection, direct routine calls, screenshots, and save states are different
  evidence classes and must be named honestly.
- Never hand-edit generated evidence. Run the official producer, preserve
  schema versions and provenance, review the semantic diff, and keep failed
  attempts separate from accepted artifacts.
- Branch from fetched `origin/main`, keep operator state untracked, stage
  exact paths, use a draft PR for visible review, and bind release claims to the
  pushed revision whose hosted checks completed.

## Maintenance workflow

Create a new debt entry only when all of these are known:

1. a concrete retained compromise or live risk exists in source, products, or
   evidence;
2. keeping it has a defensible reason;
3. a specific event defines when it must change; and
4. executable or inspectable proof can define closure.

Use the next stable ID in the owning family. Link source and tracked authority,
name dependencies, and separate player impact from maintenance discomfort. Do
not add vague wishes, duplicate the migration roadmap, or use this file to
authorize a feature.

To close an entry:

1. land the replacement, activation, or deletion through a reviewed PR;
2. run the entry's acceptance proof and the gates required by its blast radius;
3. link the PR, committed evidence, or stable test authority in the entry;
4. set status to CLOSED and record what remains intentionally constrained; and
5. update or remove dependent entries whose triggers or recommendations changed.

Evidence JSON and retained generated reports must be regenerated by their
official tools, never edited by hand. Local `.preemdeck` plans can help the
operator resume work, but they remain optional context: tracked docs, specs,
source, linked products, and verified evidence must stand without them.

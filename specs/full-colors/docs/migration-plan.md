# Migration plan

## Status and authority

This document is a future proposal and execution framework. It does not
supersede the current renderer architecture or product truth in
`FULL_COLOR_RENDERER.md` and `ARCHITECTURE.md`. The normal, debug, and VC
products already ship the Color/Yellow toggle and bounded passive renderer for
the 34 `OVERWORLD` maps plus 162 maps using the 19 admitted interior tilesets.
Where this plan describes broader ownership transfer, scheduling, lifecycle
control, OAM color, animation ownership, or map content beyond that passive
renderer, the behavior remains proposed.

Implementation MUST stop if this plan conflicts with the current approved
manuals. An explicit operator decision and separately approved architecture
change are required before proceeding. This plan MUST NOT activate retained or
quarantined ownership, scheduler, lifecycle, palette, transfer, or OAM
machinery by itself.

## Execution evidence rule

This plan defines the execution record required at every migration gate.
Phase 0 and Phase 1 now have retained evidence where explicitly described
below; later phases remain plans and gain no acceptance credit from the Phase 1
diagnostic. Every phase retains the evidence block below in its execution
record:

- **Requirements:** concrete `R…` sub-IDs changed or established by the phase.
- **Inventory:** concrete `WR-…`, `SC-…`, and `MU-…` rows touched by the phase.
  Phase 0 closes the initial map-entry slice. Phases 1–9 declare the paths they
  touch, cite concrete IDs for that slice, and review source plus built-ROM
  evidence before the changed path becomes reachable or the phase proceeds.
  `none`, category names, wildcards, and placeholder IDs are not permitted
  where a row is touched.
- **Acceptance:** concrete `AC-…` IDs the phase must close.
- **Evidence:** named future checks and artifacts, including concrete
  `CHK-…` IDs and timing-row keys when the phase changes timed work.
- **Exit gate:** an observable evidence condition. Later phases may not begin
  while it is red.

Each implementation PR names its affected requirement and inventory IDs,
commit units, owner transitions, timing-row keys, and concrete `CHK-…` checks.

## Current bounded production release scope

The shipped products expose a persistent `COLOR/YELLOW` policy preference.
Color is eligible for ordinary presentation of the admitted outdoor and
conventional-interior map slice. Boot/reset, overlays, dialogue, menus, battles,
standalone scenes, unsupported maps, and every map under Yellow preference use
the retained Yellow renderer. The current passive implementation reconciles
the saved preference at its bounded menu, map-load, and VBlank publication
boundaries; it does not activate the proposed scheduler or broader ownership
resolver described by later phases.

`PHASE2_AUDIT` adds diagnostics and certification surfaces only. It does not
gate the toggle, passive renderer, or mode selection in any product.

The diagnostic overlay oracle remains a valuable future foundation. The
repository-owned all-25-tileset background corpus is now authored and reviewed,
but production Color-overlay rollout and runtime admission of excluded maps are
not gates for this bounded release. Prior phase descriptions of broader runtime
behavior remain quarantined diagnostic/future work and MUST NOT be activated
without the separately approved architecture change described above.

## Historical Phase 0: mandatory iteration foundation

The completed foundation established the
[baseline verification contracts](verification-contracts.md) using the
[PyBoy/Python harness](ai-iteration-harness.md). This section is retained as an
architectural execution record, not a description of the current production
state.

Its historical scope was:

- tests and fixtures;
- debug-only observability;
- source and built-ROM writer, scene, and mutation discovery;
- assignment of concrete `WR-…`, `SC-…`, and `MU-…` IDs;
- complete population and review of the initial map-entry inventory slice;
- semantic snapshot and diff support;
- model-based ownership sequences;
- bank-torture controls;
- lossless screenshot, bounded frame-strip, annotated contact-sheet, localized
  image-diff, and contract-versioned manifest artifacts linked to semantic
  snapshots and writer traces;
- mutation tests for currently implemented harness contracts.

This foundation did not modify production renderer code. The current tree has
since activated production renderer paths under their own contracts.

The retained Phase 0 record proves source and built-ROM discovery on the
initial map-entry slice.
It produces harness, schema, self-mutation, initial-inventory, semantic,
bank-torture, visual-pipeline, and CI artifacts twice with identical semantic
and contract-versioned artifact-manifest outputs. Writer traces remain linked
evidence rather than an independent byte-identity contract. It does not select
renderer representation or timing values and does not accept renderer request,
commit, return, overlay, OAM, or operation-timing behavior.

**Requirements:** The execution record cites `R1.7`, `R11.3`, `R11.4`,
`R11.5`, `R11.6`, `R12.6`, and `R12.8`.

**Inventory:** Before Phase 0 exits, this execution record contains every
concrete `WR-…`, `SC-…`, and `MU-…` ID in the initial map-entry slice; every
required field is populated and every row is reviewed against source and
built-ROM evidence.

**Acceptance:** The execution record closes `AC-EVIDENCE-01`, `AC-INV-01`,
`AC-TRACE-01`, `AC-TECH-03`, and `AC-TECH-09`.

**Evidence:** Named initial-inventory-closure, contract-schema, bank-torture,
self-mutation, semantic-snapshot, visual-manifest, stable-command, and CI
checks; renderer oracles remain model/schema self-tests, and the executed
record supplies their concrete `CHK-…` IDs.

**Exit gate:** The initial map-entry inventory slice was populated, reviewed,
and closed by source and built-ROM evidence; the harness, schema, bank-torture,
visual pipeline, implemented-contract mutations, stable commands, and CI
artifacts passed twice with identical semantic and contract-versioned
artifact-manifest outputs. This historical result made no renderer acceptance
claim.

## Phase 1: ownership foundation

Baseline verification contracts are green. This phase declares and closes every inventory row it
touches before the changed path becomes reachable.

- Make the ROM CGB-only.
- Select renderer WRAM placement from current Phase 1 measurements, then add it.
- Add both renderer owners and ownership generation.
- Preserve banks in renderer-capable interrupts.
- Add job cancellation behavior.
- Keep visuals unchanged.

**Requirements:** The execution record cites `R1.1`, `R1.2`, `R1.3`, `R1.4`,
`R1.5`, `R1.6`, `R1.19`, `R1.20`, `R1.24`, `R1.25`, `R2.1`, `R2.2`, `R2.3`,
`R2.4`, `R2.8`, `R2.9`, `R3.1`, `R3.2`, `R3.3`, `R3.4`, `R3.5`, `R3.6`,
`R4.1`, `R4.2`, `R4.3`, `R4.4`, and `R4.5`.

**Inventory:** The executed Phase 1 visible-resource slice closes
`WR-YELLOW-LCDC-DISABLE`, `WR-YELLOW-MAP-VIEW-TILE-COPY`,
`SC-YELLOW-MAP-ENTRY`, and `MU-YELLOW-MAP-VIEW-INITIAL` against current source
and built-ROM evidence. Startup rejection and ownership-core control flow do
not touch the visible-resource schema and require no artificial rows.

**Acceptance:** The execution record closes `AC-OWN-01`, `AC-JOB-01`,
`AC-TECH-02`, `AC-TECH-04`, `AC-TECH-06`, and `AC-TECH-07`.

**Evidence:** Named ownership-model, hostile-writer, handoff/reset,
bank-torture, cancellation, baseline-semantic, and mutation checks; execution
records their concrete `CHK-…` IDs. The cited handoff/reset cases are progress
toward `AC-HO-01` and `AC-HO-04`, not closure of their universally quantified
directed-edge coverage.

**Exit gate:** Ownership-model sequences agree with debug-ROM traces, and
bank-torture, cancellation, mutation, handoff, and baseline semantic evidence
is green for every cited closed-inventory row.

### Executed Phase 1 record

The stable command is `make test-full-color-renderer-runtime`. It creates a
new numbered attempt under `test-results/full-color-renderer-runtime` (or
`FULL_COLOR_RUNTIME_RESULTS`), runs two fresh CGB emulator captures, validates
both closed manifests, and requires their stable files to be byte-identical.
Read `summary.json` first; for each run read `run-summary.json`,
`manifest.json`, `baseline-semantic-report.json`, `baseline-before.json`, and
`baseline-after.json`; then read the activated case's `compact-summary.txt`,
`structured-diff.json`, `expected-patches.json`,
`actual-semantic-snapshot.json`, and `actual-writer-trace.json`.

Only `RC-OWNERSHIP-REPLACEMENT` is activated. Its snapshots declare
`RENDERER_RUNTIME` at activation phase 1, and its exact check set is
`CHK-OWN-01`, `CHK-JOB-01`, and `CHK-COMMIT-01`. The case proves that the old
generation is cancelled with `SUPERSEDED`, cannot write afterward, and is
replaced by a job that completes under the fresh generation. This is real-ROM
evidence for that ownership-job operation only, not colored-resource commit
coverage and not closure of Phase 2 color acceptance.

The measured 13-byte ownership state is linked in WRAM bank 2 at
`$d000`–`$d00c`, with its exclusive end at `$d00d`, 235 bytes of stack margin,
and banked interrupt/runtime access that preserves `rSVBK`. The ownership core
is linked in ROM bank `$3b` at `$4000`–`$4753` (`$754` bytes). The authoritative
decision and build identities are retained in
`../evidence/phase1-ownership-placement.json`.

Phase 1 revalidates the closed initial-map-entry visible-resource inventory:
`WR-YELLOW-LCDC-DISABLE`, `WR-YELLOW-MAP-VIEW-TILE-COPY`,
`SC-YELLOW-MAP-ENTRY`, and `MU-YELLOW-MAP-VIEW-INITIAL`. Each row has one exact
source and one exact ROM assignment, for eight reviewed assignments total,
and discovery reports zero unlisted findings within that slice. CGB-only
startup and ownership-core control flow do not touch the visible-resource
schema and therefore do not add artificial inventory rows.

The baseline semantic comparison preserves BG tile IDs, attributes, BG and OBJ
palettes, shadow and hardware OAM, map and tileset identity, dirty state, and
banks; it restores `RENDERER_YELLOW`/`YELLOW_ACTIVE` with empty jobs and a fresh
generation. Yellow's baseline visuals are therefore unchanged. The release,
debug, and VC products are CGB-only: a normal CGB hard boot switches speed
exactly once, an already-double-speed entry does not switch again, and DMG and
SGB boot remain in the rejection path. No palette, attribute, transfer,
overlay, OAM-coloring, or colored-renderer acceptance is claimed before
Phase 2.

## Phase 2: diagnostic vertical slice

Baseline verification contracts are green. This phase declares and closes every inventory row it
touches before the changed path becomes reachable.

- Add the unmistakable eight-palette canary mode.
- Add transformed buffers and shade remapping.
- Pair initial, horizontal, vertical, connection, animation, and field-
  replacement units for the diagnostic Pallet Town/Route 1 slice. Keep the
  overlay oracle quarantined from production.
- Route wrappers by owner.
- Exercise follower Pikachu, several NPCs, and animated terrain.
- Implement one real standalone-screen handoff and return.
- Measure and select the pressure policy of each implemented request class,
  then run its runtime pressure tests; required visible-state work defers and
  retries, and any final capacity rejection proves its optional/supersedable
  caller fallback.
- Run with non-default banks and representative interrupt pressure.
- Run the complete visual pipeline for the hostile slice: semantic-linked
  screenshots, bounded frame strips, annotated contact sheets, localized image
  diffs, and its versioned manifest.
- Measure LCD, VBlank, transfer, palette, and OAM work.
- Exercise missing, out-of-range, and unmapped overworld picture identities;
  prove OBJ palette 0, preserved attribute bits 3–7, and required diagnostic
  fallback evidence.

**Requirements:** The execution record cites `R1.8`, `R1.9`, `R1.10`,
`R1.11`, `R1.12`, `R1.13`, `R1.14`, `R1.15`, `R1.16`, `R1.17`, `R1.18`,
`R1.21`, `R1.22`, `R1.23`, `R1.27`, `R1.28`, `R2.5`, `R2.6`, `R2.7`,
`R2.10`, `R2.11`, `R2.12`, `R2.13`, `R5.1`, `R5.2`, `R5.3`, `R5.4`,
`R5.6`, `R5.7`, `R5.8`, `R6.4`, `R6.5`, `R6.6`, `R6.7`, `R6.8`, `R6.9`,
`R6.10`, `R6.11`, `R9.1`, `R9.2`, `R9.3`, `R9.4`, `R10.3`, `R10.4`,
`R11.1`, `R11.2`, `R11.3`, `R11.4`, and `R11.5`.

**Inventory:** When executed, declare and close every concrete
`WR-…`, `SC-…`, and `MU-…` row exercised by the hostile diagnostic slice,
including its one proven map-to-Yellow edge, proven Yellow-to-map edge, and
OAM fallback writers/mutations; rerun source plus built-ROM closure before
either new path becomes reachable.

**Acceptance:** The execution record closes `AC-REQUEST-01`,
`AC-COMMIT-01`, `AC-OVERLAY-01`, `AC-OAM-01`, `AC-TECH-05`,
`AC-TECH-06`, `AC-TECH-08`, and `AC-TECH-10`. This is the first phase that
closes `AC-TECH-05`, using actual completed-resource and reconstruction
states after renderer activation.

**Evidence:** Named hostile-slice request-pressure, canary, overlay-oracle,
reconstruction-poison, presentation-barrier, five-active-frame, OAM-fallback,
semantic, visual, owner, bank, and numeric timing checks; execution records
their concrete `CHK-…` IDs and timing-row keys. Its one proven pair of
directed boundaries is slice evidence toward `AC-HO-01`, `AC-HO-03`,
`AC-HO-04`, `AC-RETURN-01`, and `AC-STRESS-02`; it does not close any of
those global criteria.

**Exit gate:** The hostile scenario passes exact request, semantic, model,
visual, bank, ownership, reconstruction, atomicity, OAM fallback, and numeric
timing evidence without restoration hooks.

Do not expand the architecture until this gate is green.

## Phase 3: complete palette and transfer architecture

Baseline verification contracts are green. This phase declares and closes every inventory row it
touches before the changed path becomes reachable.

- Generalize the tile attribute lookup.
- Complete the overworld palette/shade pipeline for fades, flashes, white,
  black, and poison effects.
- Cover Pallet Town and Route 1 load/reload paths for bounded production.
- Cover all connections and transfer destinations.
- Prove dialogue and transient overlays remain Yellow baseline, with complete
  Color-to-Yellow departure and Yellow-to-Color eligible-map return.
- Cover animated and replaced tiles.
- In the quarantined diagnostic oracle, keep every overlay request authoritative for destination BG/window selector,
  map identity, tileset identity, world-coordinate transform, override set,
  and preserved source/destination/world mapping.

**Requirements:** The execution record cites `R5.5`, `R6.1`, `R6.3`, `R6.4`,
`R6.5`, `R6.6`, `R6.7`, `R6.8`, `R6.9`, `R6.10`, `R6.11`, `R6.12`,
`R7.1`, `R7.2`, `R7.3`, `R7.4`, `R10.4`, `R10.5`, and `R10.6`.

**Inventory:** When executed, list and close every concrete paired-transfer
and palette-effect `MU-…` row and each `WR-…` row it reaches for fades,
flashes, white, black, poison, load/reload, both scroll axes, four connections,
row/column/rectangle/third-screen transfers, overlays, alternate destinations,
animation, and field replacement.

**Acceptance:** The execution record closes `AC-COMMIT-01`,
`AC-OVERLAY-01`, `AC-OW-02`, `AC-OW-03`, `AC-OW-06`, `AC-STRESS-03`,
`AC-TECH-05`, and `AC-TECH-08`.

**Evidence:** Named fade/flash/white/black/poison semantic palette snapshots
and frame strips, paired-transfer matrix, overlay-oracle, forced-boundary,
bank, ownership-trace, focused-soak, and numeric worst-case timing checks;
execution records their concrete `CHK-…` IDs and timing-row keys. Transfer
and override-precedence coverage in this phase is evidence toward
`AC-OW-04`, but that criterion does not close until Phase 6 supplies bounded
Pallet Town/Route 1 animation and field-replacement content. Transfer coverage in this
phase does not close any globally quantified handoff or return criterion.

**Exit gate:** Every cited paired-transfer and palette-effect `MU-…` and
reached `WR-…` row is closed, and the effect semantics and frame strips plus
transfer matrix, atomicity, bank, ownership, soak, and numeric timing evidence
pass.

## Phase 4: overworld OAM

Baseline verification contracts are green. This phase declares and closes every inventory row it
touches before the changed path becomes reachable.

- Add picture-ID palette assignments.
- Insert palette bits after Yellow's final tile calculation.
- Preserve follower Pikachu VRAM offsets.
- Cover field objects and transient effects.

**Requirements:** The execution record cites `R9.1`, `R9.2`, `R9.3`, `R9.4`,
`R9.5`, `R9.6`, `R9.7`, `R9.8`, `R9.9`, `R10.2`, `R10.4`, and `R10.6`.

**Inventory:** When executed, list and close every concrete shadow-OAM
lifecycle, hardware-OAM, `rDMA` source/launch/wait `WR-…` row and every
overworld OAM build, palette-map, sort/copy, invalidate, DMA, and
LCD-off/reset/handoff `MU-…` row touched.

**Acceptance:** The execution record closes `AC-OAM-01`, `AC-OW-05`,
`AC-OW-06`, `AC-TECH-04`, `AC-TECH-05`, `AC-TECH-07`, and `AC-TECH-08`.

**Evidence:** Named maximum-NPC, player, follower, final-picture, priority,
field-object, shadow-to-hardware DMA, fallback, bank, wobble, and numeric
timing checks; execution records their concrete `CHK-…` IDs and timing-row
keys.

**Exit gate:** Every cited shadow-OAM, hardware-OAM, and `rDMA` `WR-…`/`MU-…`
row is closed, and OAM identity, fallback, complete-DMA, bank, visual-stability,
and numeric timing evidence passes.

## Phase 5: architecture stress gate

Baseline verification contracts are green. This phase declares and closes every inventory row it
touches before the changed path becomes reachable.

Prove these cases before scaling real color content:

1. **Combined pressure:** simultaneous scrolling, animated terrain, palette
   work, maximum representative overworld OAM, and interrupt pressure.
2. **Handoff reconstruction:** a standalone screen entered immediately after
   map activity, followed by a complete map return with no stale generation or
   restoration hook.
3. **Interrupted connection:** force insufficient budget at every pre-visible
   preparation and revalidation boundary; the transfer defers before
   `COMMITTING`, while a visible commit that reserved its measured worst-case
   budget completes without arbitrary interruption. Interrupt a mid-operation
   write only when its destination is inactive or the LCD is off.

For each case, require semantic state, ownership-model agreement, writer trace,
bank restoration, timing measurements, and LLM-reviewed screenshots/frame
strips.

Each case records complete numeric timing rows, proves `defer threshold + 1`
whole-unit deferral at every pre-visible boundary, and proves reserved-budget
completion after visible `COMMITTING` begins.

**Requirements:** The execution record cites `R1.15`, `R1.16`, `R1.21`,
`R1.22`, `R1.23`, `R1.24`, `R1.25`, `R1.27`, `R1.28`, `R2.10`, `R2.11`,
`R2.12`, `R2.13`, `R7.1`, `R7.3`, `R7.4`, `R10.4`, `R10.5`, `R10.8`,
`R10.9`, and `R10.10`.

**Inventory:** When executed, list every concrete closed-inventory `WR-…`,
`SC-…`, and `MU-…` row reached by combined pressure, standalone handoff
reconstruction, and interrupted connection transfer.

**Acceptance:** The execution record closes `AC-STRESS-01`, `AC-STRESS-03`,
`AC-REQUEST-01`, `AC-JOB-01`, `AC-COMMIT-01`, and `AC-TIME-01`.

**Evidence:** Named combined-pressure, poisoned-return reconstruction,
interrupted-connection, request-accounting, owner-model, writer-trace, bank,
atomicity, semantic, visual, and complete numeric timing checks; execution
records their concrete `CHK-…` IDs and timing-row keys. The named
poisoned-return case is stress progress toward `AC-STRESS-02` and
`AC-RETURN-01`, not exhaustive closure.

**Exit gate:** All three named architecture stress cases pass repeatedly with
deterministic artifacts, positive numeric margins, and threshold-plus-one
whole-unit deferral for every timed path.

Do not begin scheduler-owned production content activation until this gate is
green. This gate does not retract the already shipped passive slice.

## Phase 6: bounded Pallet Town and Route 1 content

Baseline verification contracts are green. This phase declares and closes every inventory row it
touches before the changed path becomes reachable.

- Independently author and validate only palette/attribute data reached by
  ordinary Pallet Town and Route 1; donor content remains candidate evidence.
- Close their connection, map-specific overrides, every animated tile, and
  every field replacement reached in those two maps.
- Revalidate fades, flashes, white, black, and poison effects for the bounded
  Pallet Town/Route 1 Color scene.

**Requirements:** The execution record cites `R5.5`, `R6.1`, `R6.3`, `R6.7`,
`R6.9`, `R7.1`, `R7.3`, `R8.2`, `R8.4`, `R8.5`, and `R8.6` only for data
and operations reachable in ordinary Pallet Town and Route 1.

**Inventory:** When executed, list and close every concrete closed-inventory
bounded tileset/content and palette-effect `MU-…` row and every `WR-…` row
used to load or transform its palette or to apply its lookup, override,
animation, or field replacement.

**Acceptance:** The execution record closes bounded `AC-OW-04`, `AC-OW-06`,
`AC-TECH-05`, and `AC-TECH-10` obligations. Completed, non-gating `AC-OW-01`
content does not close these bounded runtime obligations or widen their scope.

**Evidence:** Named Pallet Town/Route 1 table-length, Yellow-graphics,
override, animation, field-replacement, semantic full-byte attribute,
fade/flash/white/black/poison frame-strip, and visual-review checks; execution
records their concrete `CHK-…` IDs and per-operation timing rows.

**Exit gate:** Every cited Pallet Town/Route 1 content row is closed, and its
table, semantic attribute, animation, field-replacement, palette-effect, and
visual-review evidence passes. Unsupported-map authoring is not part of this
gate.

## Phase 7: complete handoff coverage

Baseline verification contracts are green. This phase declares and closes every inventory row it
touches before the changed path becomes reachable.

- Handoff before destination initialization on every concrete map-to-Yellow
  edge.
- Reconstruct from fresh logical state on every concrete Yellow-to-Color
  Pallet Town/Route 1 edge and reconstruct Yellow completely on every reverse
  edge, including reset and soft reset from Color,
  and do not invent map returns for standalone lifecycles without that edge.
- Stress rapid, repeated, interrupted, boot/reset, Yellow-to-Yellow nested and
  error, and actual ownership-boundary transitions.
- Reject stale-generation jobs.

**Requirements:** The execution record cites `R1.6`, `R1.9`, `R1.10`,
`R1.19`, `R1.20`, `R1.24`, `R2.1`, `R2.2`, `R2.3`, `R2.4`, `R2.5`, `R2.6`,
`R2.7`, `R2.8`, `R2.9`, `R2.10`, `R2.11`, `R2.12`, `R2.13`, `R12.1`,
`R12.2`, `R12.5`, and `R12.8`.

**Inventory:** When executed, list and close every concrete `MAP_BACKED`,
`STANDALONE`, and directed `SCENE_BOUNDARY` `SC-…` row from the baseline and
atomically extended inventories, including hard boot and Yellow-to-Yellow
nested/error edges, plus every reached handoff/reconstruction `WR-…` and
`MU-…` row. These scene labels classify scene rows only and do not classify
resources or responsibilities.

**Acceptance:** The execution record closes `AC-JOB-01`, `AC-RETURN-01`,
`AC-HO-01`, `AC-HO-02`, `AC-HO-03`, `AC-HO-04`, `AC-STRESS-02`, and
`AC-TECH-06`. `AC-RETURN-01`, `AC-HO-01`, `AC-HO-03`, and `AC-HO-04`
close here, and not in an earlier representative slice, only after every
concrete directed inventory edge has exhaustive evidence.

**Evidence:** Named directed scene-graph and boundary handoff matrix,
Yellow-before-destination-initialization, complete destination-resource poison
and fresh reconstruction on every real owner change in either direction,
exactly one barrier, admission reopening only afterward, five-active-frame,
stale-generation, boot/reset/nested/error-exit, and 100-cycle soak checks;
execution records their concrete `CHK-…` IDs, including the `R2.6` and
`R12.2` first-writer and initialization-entry evidence required by
`AC-HO-01`.

**Exit gate:** Every cited lifecycle and boundary `SC-…` row is closed, and
the full handoff matrix plus rapid, repeated, interrupted, nested, reset,
return-reconstruction, and 100-cycle soak evidence passes.

## Phase 8: remove only obsolete competing ownership

Baseline verification contracts are green. This phase declares and closes every inventory row it
touches before the changed path becomes reachable.

- Remove only obsolete competing or repair paths; retain every Yellow path
  required by preference and forced-Yellow contexts.
- Remove transitional overworld adapters.
- Remove restoration behavior.
- Enforce owner-gated hardware writers in CI.
- Retain Yellow code required by excluded scenes.

**Requirements:** The execution record cites `R1.3`, `R1.4`, `R1.7`, `R7.2`,
`R12.3`, `R12.4`, `R12.5`, `R12.6`, and `R12.7`.

**Inventory:** When executed, list every concrete closed-inventory `WR-…`,
`SC-…`, and `MU-…` row removed, retained, or proven unreachable; this includes
obsolete overworld ownership and every captured-screen/restoration path.

**Acceptance:** The execution record closes `AC-INV-01`, `AC-REMOVE-01`,
`AC-REMOVE-02`, `AC-REMOVE-03`, `AC-REMOVE-04`, `AC-TECH-03`, and
`AC-HO-02`.

**Evidence:** Named source plus built-ROM reachability, restoration-hook
absence, owner-gated writer, adapter justification/removal, and excluded-scene
regression checks; execution records their concrete `CHK-…` IDs.

**Exit gate:** Source and built-ROM evidence proves obsolete Yellow overworld
ownership, tint/attribute, and captured-screen restoration paths unreachable
and removed, while every retained excluded-scene row remains green.

## Phase 9: timing and release hardening

Baseline verification contracts are green. This phase declares and closes every inventory row it
touches before the changed path becomes reachable.

- Reconfirm LCD, VBlank, map streaming, palette upload, and OAM budgets.
- Verify safe missed-deadline behavior.
- Run the complete multi-frame suite.
- Verify release, debug, and VC builds.

**Requirements:** The execution record cites `R3.1`, `R3.4`, `R3.5`, `R3.6`,
`R5.5`, `R9.7`, `R10.1`, `R10.2`, `R10.3`, `R10.4`, `R10.5`, `R10.6`,
`R10.7`, `R10.8`, `R10.9`, `R10.10`, `R11.3`, `R11.4`, `R11.5`, `R12.1`,
`R12.5`, and `R12.6`.

**Inventory:** When executed, list every remaining concrete closed-inventory
`WR-…`, `SC-…`, and `MU-…` row reached by timing comparison, soak, release
builds, and excluded-scene regressions.

**Acceptance:** The execution record closes every bounded-release acceptance
criterion still open after Phases 0–8, including `AC-TIME-01`, `AC-TRACE-01`,
`AC-TECH-01`, `AC-TECH-08`, `AC-TECH-10`, `AC-HO-02`, `AC-REMOVE-04`, and
`AC-DONE-01`.
Completed, non-gating `AC-OW-01` is explicitly outside this runtime release
gate.

**Evidence:** Named timing-budget and baseline-comparison tables, exact
threshold-plus-one deferrals, complete traceability report,
fade/flash/white/black/poison multi-frame regressions, multi-frame and soak
suites, reproducible release/debug/VC builds, and excluded-scene regression
checks; execution records their concrete `CHK-…` IDs and every timing-row key.

**Exit gate:** All remaining bounded-release rows in the
[acceptance criteria](acceptance-criteria.md), traceability, numeric timing
comparison, threshold deferral, soak, build, and excluded-scene regression
evidence pass. The completed all-25 content corpus remains non-gating and does
not widen runtime admission.

## Completed non-gating work: all-25-tileset authoring

A separate content effort independently authored and validated all Yellow
palette sets and `$60` assignment tables, native Beach House data, roofs and
map overrides, all-map animations, and all-map palette-effect evidence. That
completed corpus closes the content scope of `AC-OW-01` outside this
migration's ordered runtime phases and release gate. Its evidence cannot weaken
or substitute for the exact Pallet Town/Route 1 production matrix, and it does
not authorize runtime presentation of excluded maps.

## Iteration rule

Run the fastest relevant contract after each change. A red verification,
ownership, bank, or semantic-state contract stops renderer expansion until
fixed.

Each implementation PR must:

- address one phase or bounded transfer path;
- name concrete affected `R…`, `AC-…`, `CHK-…`, `WR-…`, `SC-…`, and `MU-…`
  IDs from the closed authorities and inventory;
- state owner transitions and visible commit units;
- name applicable timing-row keys;
- include a machine-checkable test;
- avoid unrelated non-overworld work; and
- remain bootable and diagnosable.

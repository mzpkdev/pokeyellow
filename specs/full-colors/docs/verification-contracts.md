# Verification contracts

The harness is split by evidence authority:

- `test-unit` runs the complete unit and built-ROM contract tree once.
- `test-full-color-harness-contracts` validates current repository discovery,
  reviewed inventory closure, and synthetic bank behavior once.
- `test-full-color-evidence` captures runtime observability, traceability, and
  visual evidence twice and requires byte-identical stable outputs.
- `test-full-color-audit` verifies the reviewed audit evidence against all four
  same-revision ROM products.
- renderer contract/runtime commands and the three E2E suites prove their
  named boundaries independently.

These contracts are ongoing release requirements. They are not a numbered
implementation stage, and none alone proves the whole renderer correct. A red
activated contract blocks the affected release or renderer expansion.

## Required evidence artifacts

The outputs below form the baseline evidence contract. They do not claim
whole-game inventory closure or substitute diagnostic fixtures for renderer
runtime, representation, timing, or hostile-slice evidence.

| Evidence artifact | Required baseline content |
|---|---|
| deterministic harness | pinned dependencies, bounded scenarios, stable commands, and identical double-run outputs |
| observability and snapshots | decodable debug symbols, bounded traces, semantic capture, and exact resource/offset diffs |
| model and bank torture | deterministic valid/adversarial ownership sequences plus ROM/WRAM/VRAM, stack, and interrupt restoration fixtures |
| initial writer/scene/mutation slice | concrete reviewed `WR-…`/`SC-…`/`MU-…` rows for map entry, with matching source and built-ROM evidence and unlisted-item self-mutations |
| semantic schema | decodable owner, phase, generation, request result, job state/cancellation, commit unit, reconstruction items, overlay request fields, OAM fallback, and timing-row fields |
| visual artifact pipeline | deterministic lossless screenshots, bounded frame strips, annotated contact sheets, localized image diffs, and a contract-versioned manifest linking semantic snapshots and writer traces |
| execution surface | stable local commands, blocking CI, deterministic double execution, and diagnostic failure artifacts |

The baseline inventory contract closes the reviewed initial map-entry slice.
Every implementation slice closes each writer, scene, boundary, and mutation
row it touches before the changed path becomes reachable. Untouched baseline
findings remain visible backlog evidence and do not block unrelated renderer
work.

Schema and reference-model evidence exercises every request result
branch without selecting a runtime pressure policy. The phase implementing a
request class measures it, selects exactly one policy, and proves runtime
conformance. Required visible-state classes select `DEFERRED` plus caller retry
when they cannot coalesce. `REJECTED_CAPACITY` remains limited to optional or
supersedable work with a documented caller fallback.

Evidence determinism alone does not establish request, commit,
Yellow-to-overworld reconstruction, overlay, overworld OAM, representation, or
renderer timing acceptance. Each renderer contract or runtime command supplies
the authority for its named boundary, and the three E2E suites supply gameplay
evidence independently.

## Renderer-conformance checker readiness

Renderer contract fixtures execute against `SCHEMA_FIXTURE` evidence. Their
oracle derives expected values only from versioned authoritative inputs, and
their positive observations are authored independently. Passing proves checker
sensitivity and deterministic evidence; it closes no renderer runtime
acceptance criterion.

A behavior contributes runtime acceptance only by providing `RENDERER_RUNTIME`
snapshots and writer traces with a nonzero activation phase. The activated
path then blocks on its existing `CHK-…` IDs. Screenshots remain linked review
evidence and never replace semantic or trace assertions.

Oracle fixture inputs are causal request configuration, initial state, and
actions only. Job state sequences and cancellation reasons, reconstruction
ledgers/provenance/poison/barrier results, fallback classifications, and
machine-restoration results are derived expectations and are forbidden as
fixture inputs. Every derived field uses an exact dotted path exposed by
`SemanticSnapshot.to_dict()`, `OverlayRequestState`, `OAMFallbackState`, or
`BankTortureResult`; job and writer assertions use decoded `WriterTrace`
predicates instead of invented snapshot fields. Each operation also admits
only its documented `CHK-…` identity set.

Trace predicates declare complete commits only for paired tile/attribute
transfers, palette uploads, reconstruction presentation, overlays with at
least one surviving cell, and the completing replacement in an ownership/job
supersession. The independent oracle names the required phase and canonical
written-resource identities for each predicate. Trace-local numeric resource
IDs are debug encodings only: the observation carrier maps them to canonical
identities, including distinct `bg_palettes` and `obj_palettes` identities,
before comparison. Each such predicate requires a concrete commit-unit ID. A
fully clipped overlay, OAM fallback attribute rewrite, and machine-restoration
boundary are not commit units and explicitly set `require_complete_commit` to
false; their fixture commit-unit ID is null. The fully clipped overlay alone
sets `require_no_writes` true, forbidding every `wrote=true` trace entry even
when its writer is the canonical `WR-NONE`; its positive evidence is an empty
trace with that non-writing permitted-writer allowlist. OAM fallback and
machine-restoration predicates keep `require_no_writes` false because their
empty job sets do not preclude observational trace evidence.

Case IDs and every observation carrier path, including optional boundary
paths, have case-insensitive uniqueness and exact canonical case ownership.
This prevents distinct fixture aliases from resolving to the same evidence on
case-insensitive filesystems.

The overlay schema carries destination BG/window selector, map identity,
tileset identity, rectangle, world-coordinate origin/transform, override set,
per-cell classification, tile IDs, and attributes. Its independent model
preserves source-to-destination tilemap and world-coordinate mappings through
clipping, rejects singular affine transforms, and never reads VRAM or ambient
map state. Each matrix label is validated from destination, clipping geometry,
map and the declared canonical tileset identity, alternating classification,
all four explicit/default/lookup/override precedence branches, and meaningful
attribute bits. Across those four attribute sources, the corpus must set palette bits
0–2, bank bit 3, flip bits 5–6, and priority bit 7 while canonicalizing bit 4
to zero; the label is not itself oracle authority. The checker schema fixes the
complete synthetic mapped-picture authority to `[1, 2, 3, 7]`, shared by every
OAM case, and validates all three fallback classifications against it. Per-case
mapping authority is rejected so a mapped identity cannot be relabelled as
fallback. Runtime ordinary, clipped,
edge, connection, alternate-BG, and alternate-map coverage activates in
Phases 2–3. Runtime OAM fallback coverage activates in Phases 2 and 4.

| Operation | Mode | ROM | Tool/device | Samples | Worst cycles | Instrumentation | Start | Deadline | Guard | Margin cycles | Margin % | Defer threshold | Result |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

Every numeric cell is required when a renderer timing row activates. A row
passes only when `worst + instrumentation <= deadline - start - guard`.
Activation checks force insufficient budget at every pre-visible preparation
or revalidation boundary. A visible-destination operation must defer before
`COMMITTING`; after reserving its worst-case budget it must complete. Arbitrary
mid-operation interruption is tested only for an inactive destination or with
the LCD off.

## Reproducible test environment

- Extend the existing `tools/rom_tests` pytest/PyBoy framework.
- Keep PyBoy and related packages pinned in
  `tools/rom_tests/requirements.txt`.
- Build and consume `pokeyellow_debug.gbc` and `pokeyellow_debug.sym`.
- Give every test a deterministic initial state, bounded frame count, and
  explicit timeout.
- Preserve per-test failure artifacts under `test-results`.

Pass condition: a clean checkout runs the smoke command twice with identical
semantic outputs.

## Inventory discovery and initial-slice closure

Build the inventory machinery defined by
[replacement-inventory.md](replacement-inventory.md) and prove it on the
initial map-entry slice. Discovery covers source search and built-ROM
symbol/disassembly reachability. Grep only seeds rows and cannot prove closure.

Within each declared slice, the writer audit covers direct, indirect-high-memory, wrapper, DMA, and
interrupt writes to every owner-gated resource, including LCD/STAT/LYC,
scroll/window/palette registers, `rVBK`, `rSVBK`, HDMA/GDMA, shadow OAM,
hardware OAM, and every `rDMA` source, launch, and wait path. Scene discovery
covers every in-slice lifecycle and boundary plus reachable reset, failure,
nested-exit, load, and return paths. Mutation discovery covers
every visible-map load, transfer, overlay, animation, replacement, alternate
destination, and reconstruction path.

Every discovered item inside the declared slice receives a concrete `WR-…`,
`SC-…`, or `MU-…` ID and a fully populated reviewed row. Later phases expand
the declared slice around the paths they touch, review those rows, and close
source plus built-ROM evidence before the changed path becomes reachable.
Unexpected in-slice additions fail CI.

Pass condition: the initial map-entry writer, scene, and mutation rows are
populated, reviewed, and closed in source and built-ROM evidence; independent
source and ROM fixtures containing an unlisted in-slice item make the audit
fail; the progress report keeps out-of-slice findings visible without treating
them as failures of the baseline evidence contract.

## Debug observability

The debug ROM exposes symbols for:

- active owner;
- active phase;
- ownership generation;
- last request result;
- job state, cancellation reason, and dirty flags;
- current commit-unit and writer IDs;
- current ROM/WRAM/VRAM banks;
- last writer ID and resource;
- reconstruction-item and presentation-barrier status;
- OAM fallback evidence;
- current timing-row key;
- assertion failure code; and
- a bounded writer trace ring.

Release builds need not include the trace.

Pass condition: PyBoy can resolve every symbol and decode a synthetic trace.

## Semantic snapshots

Extend the Python emulator helper to capture JSON containing:

- schema/contract version, ROM identity, scenario, seed, checkpoint, and frame;
- owner, phase, and generation;
- exact request result, job state, cancellation reason, and commit-unit IDs;
- current and traced writer IDs;
- ROM/WRAM/VRAM banks;
- BG tile IDs and attributes;
- BG and OBJ palette RAM;
- shadow and hardware OAM;
- dirty and queued job state; and
- current map/tileset, transfer state, reconstruction-item status, OAM
  fallback, and timing-row key.

Diffs identify exact offsets and expected/actual values. Screenshots are
secondary artifacts. Cancelled work remains in a bounded trace long enough to
prove that it performs no later write.

Pass condition: identical checkpoints compare cleanly and an intentional
one-byte mutation reports the resource and offset.

## Ownership assertions

Debug assertions fail when:

- a writer runs under the wrong owner;
- two owners appear active;
- a stale-generation job executes;
- ownership changes during a partially committed job; or
- a renderer returns with unexpected bank state.

Verification-contract schema/reference-model fixtures submit wrong-owner,
equivalent-at-capacity, and every pressure-result branch without selecting a
runtime class policy. Atomicity
self-mutations model insufficient time at every pre-visible preparation and
revalidation boundary, failure to reserve worst-case completion budget, and
illegal interruption after visible `COMMITTING`.

Pass condition: mutation fixtures trigger every harness assertion,
schema/reference-model request and atomicity oracles match exactly, and normal
Yellow baseline scenarios trigger no assertion. Runtime request accounting and
visible atomicity become Phase 2 acceptance.

## Bank-torture harness

Provide debug entry points, synthetic fixtures, or controlled baseline
scenarios that exercise bank capture and restoration with:

- non-default ROM bank;
- every valid WRAM entry bank, without assuming the later renderer placement;
- VRAM bank 1;
- an interrupt during a far call; and
- pending work during soft reset or ownership switch.

Pass condition: every baseline or synthetic fixture restores banks,
stack, and interrupts and proves the owner/generation/dirty-state schema
is decodable. Renderer-path conformance activates in Phases 1–2.

## Model-based ownership testing

Implement a small Python reference model using the stable owner, phase,
request-result, job-state, and cancellation symbols from the requirements
contract. Its observable phases are:

```text
YELLOW_ACTIVE
HANDOFF_TO_OVERWORLD
OVERWORLD_RECONSTRUCTING
OVERWORLD_ACTIVE
OVERWORLD_OVERLAY
HANDOFF_TO_YELLOW
```

Generate seeded valid and adversarial action sequences covering movement,
overlays, connections, handoffs, returns, reset, pending work, and interrupt
boundaries. After every action, compare the ROM trace and semantic snapshot to
the model's expected owner, phase, generation, exact request result, job
state/cancellation, permitted writer and commit-unit IDs, queued work, and bank
state.

Failures preserve the seed and reduce to the shortest reproducible action
sequence where practical.

Pass condition: model unit tests and seeded synthetic traces are
deterministic, valid sequences satisfy the model, and deliberately corrupted
transitions fail at the first divergent action.

Activation condition after Phase 1: generated sequences agree with debug-ROM
traces at every action.

## Phase 2 activation: hostile diagnostic vertical slice

Script one bounded PyBoy scenario:

```text
map entry
-> horizontal and vertical movement
-> animated terrain
-> map connection near a tilemap boundary
-> dialogue near a map edge
-> start-menu overlay
-> follower Pikachu and several NPCs
-> standalone screen
-> map return
```

Run it with forced non-default ROM/WRAM/VRAM entry state and representative
interrupt pressure.

This scenario activates with the first colored renderer slice. Before expanding
beyond that slice, all semantic, multi-frame visual, ownership, bank, and
initial timing checkpoints pass without
restoration hooks. An actual Yellow-to-overworld return records the last map
generation, Yellow ownership before destination initialization entry, poison
installation, every reconstruction item, the presentation barrier, and at
least five active overworld frames. Overlay checkpoints apply the
authoritative destination/map/tileset/world-transform request oracle from the
artifact contract.

## LLM visual artifact pipeline

At named checkpoints, emit lossless screenshots, bounded frame strips,
annotated contact sheets, and metadata linking each image to its semantic
snapshot and writer trace. The filenames and checkpoint labels are stable
enough for an LLM-driven test play to locate and view them directly. A small
contract-versioned artifact manifest lists relative paths, checkpoint names,
frame numbers, scenario, seed, ROM identity, semantic schema version, and
linked trace and timing-row keys.

Pass condition: a deterministic baseline fixture produces viewable
artifacts, and an intentional visual mutation produces a localized image diff.

Activation condition during Phase 2: the hostile slice's canary assignments
produce the expected semantic and visual artifacts.

## Contract mutation suite

The mutation suite targets only implemented harness behavior: schema validation, snapshot
diffs, trace decoding, ownership-model transitions, bank restoration, initial
inventory-slice closure, visual artifact integrity, and CI failure reporting.
Each later phase adds the runtime mutations for the behavior it activates,
including:

- wrong-owner write;
- invalid ownership-model transition;
- stale job generation;
- wrong-owner and stale-generation request admission;
- selected per-class capacity-plus-one pressure plus model-only unselected
  enum branches;
- silent loss of accepted or coalesced work;
- missing streamed attribute;
- insufficient time at each pre-visible boundary, missing worst-case
  reservation, or visible mid-commit interruption;
- VRAM-derived, ambient-map-derived, or mapping-losing overlay classification;
- incomplete or saved-byte reconstruction after poisoned prior state;
- missing OAM fallback diagnostic or changed bits 3–7;
- a defer-threshold-plus-one boundary that enters `COMMITTING`;
- leaked WRAM bank;
- unexpected hardware writer; and
- snapshot corruption.

Pass condition: every mutation for currently implemented behavior makes its
intended contract fail with a specific message and useful artifacts. A renderer
mutation blocks only after runtime evidence activates its target behavior.

## Phase activation: timing instrumentation

Add debug counters and checkpoints when the first timed renderer path exists.
Each affected phase records scanline or cycle consumption for its LCD, VBlank,
transfer, palette, and OAM work and populates one numeric table row per timed
operation. Budgets and exact safe-defer thresholds are derived from the running
implementation rather than assumed beforehand.

PyBoy may drive and record these checks, but a timing-focused emulator or
physical CGB remains the final authority.

Activation condition before architecture expansion: the hostile slice has
complete numeric results for every timed operation, every row passes the
required equation, insufficient budget at every pre-visible boundary safely
defers the whole job, and a visible `COMMITTING` unit always completes from its
reserved worst-case budget.

## Hosted CI enforcement

- Build normal, debug, VC, and audit ROM products once from the same revision.
- Run unit and harness contracts once.
- Run two independent evidence captures and byte-compare their stable outputs.
- Run audit, renderer contract, and renderer runtime verification separately.
- Run Core, Renderer, and Journey E2E suites as independent jobs.
- Archive semantic diffs, traces, screenshots, frame strips, and retained
  diagnostics on failure.
- Emit a machine-readable traceability report mapping every concrete `R…` and
  `AC-…` to named `CHK-…` checks and artifacts, and fail on unknown or
  uncovered IDs.
- Publish one blocking `Merge Gate` result.

Pass condition: every CI job reports its named boundary, mutations fail their
intended contract, and `Merge Gate` stays fail-closed.

## Required commands

The stable local command surface is:

```text
test-unit
test-full-color-harness-contracts
test-full-color-evidence
test-full-color-audit
test-full-color-renderer-contracts
test-full-color-renderer-runtime
test-full-color-smoke
test-full-color-e2e-core
test-full-color-e2e-renderer
test-full-color-e2e-journey
test-full-color-fast
test-full-color-certify
test-full-color-handoffs
test-full-color-soak
```

Use `test-full-color-fast` for the short local loop and
`test-full-color-certify` before handoff. Run the affected renderer or E2E
boundary directly while iterating.

## Stop rule

If an activated contract becomes red, fix the harness or violated invariant
before changing the affected color content or adding another transfer path.

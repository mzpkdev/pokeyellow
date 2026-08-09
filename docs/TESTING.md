# Testing the ROM hack

This project tests a running Game Boy ROM, not only assembly source. Every
check must name the claim it proves: a pure rule, a linked-ROM property, a
callable routine, a naturally reached gameplay state, or a visual result. No
single green command proves that the game is playable and visually correct.

The harness lives under [`tools/rom_tests`](../tools/rom_tests/), its public
commands are in the repository [`Makefile`](../Makefile), and hosted automation
starts at [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). Read
[`ARCHITECTURE.md`](ARCHITECTURE.md) for runtime ownership and
[`ADDING_CONTENT.md`](ADDING_CONTENT.md) before adding maps or content.

## Test layout

```text
tools/rom_tests/
├── emulator.py          # PyBoy wrapper and runtime inspection helpers
├── scenarios/           # reusable player-input journeys
├── snapshots/           # reviewed visual expectations
├── fixtures/            # read-only inputs for specialized checkers
├── full_color/          # evidence runners and verification contracts
└── tests/
    ├── unit/            # rules, models, linked-ROM and callable checks
    └── e2e/
        ├── core/        # short product-health journeys
        ├── renderer/    # visual and renderer-boundary journeys
        └── journey/     # longer progression and lifecycle journeys
```

Keep navigation in `scenarios/` and assertions in `tests/e2e/`. Generated
diagnostics belong under `test-results/`, which is ignored. Reviewed snapshots
live in `tools/rom_tests/snapshots/` and are committed deliberately. ROMs,
symbols, fixtures, scenarios, and committed snapshots are read-only test
inputs.

`ROM_TEST_RESULTS` changes the base directory for per-test diagnostics. Hosted
and local certification set it to an attempt-scoped component directory. Any
cleanup helper must refuse paths that are not direct children of the resolved
root and must never traverse a symlink or recursively delete a directory.

## Setup and public commands

Create the ignored Python environment once per checkout:

```console
make test-full-color-setup
```

The historical target name is retained because it is the established harness
bootstrap command. Make prefers `.venv/bin/python` locally and falls back to
`python3` in managed environments.

The public verification surface is:

| Claim | Command |
| --- | --- |
| complete non-donor unit and linked-ROM contracts | `make test-unit` |
| exact pinned donor contract | `make test-full-color-donor-contract` |
| repository discovery, reviewed inventory, and bank contracts | `make test-full-color-harness-contracts` |
| two independent stable evidence captures compare byte-for-byte | `make test-full-color-evidence` |
| reviewed audit evidence matches all four products | `make test-full-color-audit` |
| synthetic renderer fixtures reject contract mutations | `make test-full-color-renderer-contracts` |
| built-ROM renderer ownership is bounded and observable | `make test-full-color-renderer-runtime` |
| short runtime observability probe | `make test-full-color-smoke` |
| short product-health gameplay | `make test-full-color-e2e-core` |
| renderer and visual gameplay | `make test-full-color-e2e-renderer` |
| longer progression and lifecycle gameplay | `make test-full-color-e2e-journey` |
| focused production feedback | `make test-full-color-fast` |
| complete local certification | `make test-full-color-certify` |
| focused handoff and reset model checks | `make test-full-color-handoffs` |
| seeded model soak | `make test-full-color-soak` |

There is no gameplay aggregate command. Run the affected suite while
iterating, and run Core, Renderer, and Journey independently when the change
crosses their boundaries.

Every ROM-consuming command builds its required products by default. Hosted CI
downloads products built from the same revision and passes
`ROM_TEST_PREBUILT_PRODUCTS=1`; the private prerequisites then fail closed if
any required `.gbc`, `.map`, or `.sym` file is missing. Contributors should not
set prebuilt mode unless those exact products already exist.

## Writing a gameplay test

Every gameplay test follows these rules:

- Use the shared `emulator` fixture for an ordinary single-product test. It
  creates a fresh PyBoy instance and isolated result directory for each test.
- A paired or multi-product comparison creates one fresh `Emulator` per
  product, gives each one a separate result directory, and closes each instance
  in a `finally` block.
- Reach player-facing states through normal inputs. Direct memory setup belongs
  in a callable-ROM contract, not evidence that a player can reach the scene.
- Wait for named semantic conditions with a hard bound. A timeout retains a
  descriptive screenshot or diagnostic and never spins forever.
- Observe runtime state without repairing it. A test cannot write the value it
  then claims the ROM produced.
- Never depend on test order, shared mutable emulator state, or another
  product's mutable state.
- Assert meaning as well as pixels: map, coordinates, script phase, menu or
  battle state, tile/OAM state, and relevant renderer state.
- Update a committed snapshot only after inspecting and approving the new
  actual image. Do not weaken tolerances or ignored regions to bless a change.

A plausible screenshot can conceal corrupt tile IDs, stale attributes, broken
OAM, or incomplete progression. One frame cannot rule out flicker or late
VBlank writes. Exercise movement, animation, and transitions over time.

PyBoy is deterministic and practical, but it is not a cycle-accurate hardware
oracle. Keep timing margins conservative and recheck suspicious timing
failures in another emulator or on hardware before changing a runtime contract.

## Fast feedback and certification

`make test-full-color-fast` runs these ordered components:

1. `build-products`
2. `production-linkage`
3. `audit-evidence`
4. `smoke`
5. `renderer-contracts`
6. `renderer-runtime`

Fast feedback is not certification. It is the narrow production-foundation
loop and intentionally omits the donor, complete unit tree, evidence
determinism, repository contracts, and gameplay suites.

`make test-full-color-certify` runs these ordered components exactly once:

1. `build-products`
2. `donor-contract`
3. `unit-tests`
4. `harness-contracts`
5. `evidence-determinism`
6. `audit-evidence`
7. `renderer-contracts`
8. `renderer-runtime`
9. `e2e-core`
10. `e2e-renderer`
11. `e2e-journey`

Only the three stable evidence producers inside `evidence-determinism` run
twice: runtime observability, traceability, and the visual pipeline. Unit,
discovery, inventory, bank, renderer, audit, and gameplay checks do not run a
second time to imitate determinism.

Both profiles retain component stdout, stderr, JUnit where applicable, and
evidence below `test-results/full-color-harness/attempt-NNNN/`. The aggregate
`summary.json` links those outputs without copying or promoting another
authority's result. Set `FULL_COLOR_OUTPUT=json` for one canonical JSON summary.

## Fast-to-slow development loop

Climb only as far as the claim and blast radius require:

1. Run `.venv/bin/python -m pytest <focused-path> -q`.
2. Build every affected ROM product.
3. Run `make test-full-color-fast` for production-foundation changes.
4. Run `make test-unit` when shared source, layouts, harness code, or product
   identities changed.
5. Run `make test-full-color-e2e-core` for product-health changes.
6. Run `make test-full-color-e2e-renderer` for rendering, menus, palettes,
   attributes, transfers, or visual transitions.
7. Run `make test-full-color-e2e-journey` for progression, scripts, battles,
   save/reset, or longer lifecycle changes.
8. Inspect changed screenshots and retained diagnostics manually.
9. Run `make test-full-color-certify` before handing off full-color work.
10. Push and wait for every hosted check on that revision.

Manual play remains separate evidence. Record the ROM, revision, route, and
observed result instead of translating a green automated suite into a human
playtest claim.

## What hosted CI covers

The top-level `CI` workflow exposes purpose-grouped jobs and one stable
`Merge Gate` result:

- `Build` builds normal, debug, VC, and audit products once, publishes the
  unchanged release artifact, and publishes exact same-revision test products.
- `Full-color Verification / Donor Contract` verifies the pinned external
  authority until repository-owned palette coverage replaces it under issue
  #17.
- `Unit Tests` runs the complete non-donor unit tree once.
- `Repository Inventory & Bank Safety` runs discovery, reviewed inventory, and
  bank contracts once.
- `Evidence / Capture A` and `Evidence / Capture B` capture stable evidence
  independently; `Evidence / Determinism` compares
  their stable files byte-for-byte.
- `Renderer / Contract Fixtures`, `Renderer / Runtime Ownership`, and
  `Evidence / Audit` run their named independent contracts.
- `E2E (Core)`, `E2E (Renderer)`, and `E2E (Journey)` download the same-revision
  products and run independently.
- `Merge Gate` fails if any verification job fails, is skipped, or is
  cancelled.

The workflow runs when a pull request is opened or synchronized and on pushes
to `main`. A newer commit cancels obsolete work for the same pull request.
`Metadata / Lint` combines workflow and title validation. The non-required
`Metadata / Labels` check remains isolated in the trusted
`pull_request_target` workflow.

Hosted gameplay reduces the chance of merging a visibly broken ROM, but it does
not replace manual frame review, full-game play, hardware checks, or claims not
encoded by the current journeys.

## Full-color evidence stack

Read evidence from narrowest to broadest:

1. Pure contracts and mutation tests prove rules and checker sensitivity.
2. Source and linked-ROM discovery prove exact identities, symbols, placement,
   reachability, and forbidden partitions.
3. Callable-ROM tests prove controlled entry points and bounded state changes.
4. Runtime observability proves named behavior in a built debug ROM.
5. Natural E2E proves player-input reachability, progression, and selected
   visual/lifecycle claims.
6. Manual review establishes aesthetics, flicker, and behavior outside encoded
   assertions.

`make test-full-color-evidence` captures runtime observability, traceability,
and visual pipeline outputs twice. Only stable semantic files are compared;
diagnostic logs remain available for explaining a failure but are not promoted
as deterministic evidence.

`make test-full-color-renderer-contracts` is a synthetic fixture checker. It
must reject mutated inputs, but it cannot prove natural reachability or visual
quality. `make test-full-color-renderer-runtime` uses fresh emulator state to
prove built-ROM ownership behavior. `make test-full-color-audit` recomputes the
reviewed audit evidence against all same-revision products and fails on stale
identities or authority drift.

Measurement commands such as `measure-full-color-phase2-audit` write
unreviewed proposals under `test-results/full-color-proposals/`. They never
overwrite checked-in authority. A human reviews and incorporates an accepted
semantic change before official evidence is regenerated through its producer.

Common evidence roots are:

- deterministic evidence: `test-results/full-color-evidence/`;
- hosted harness-contract log artifact: `test-results/full-color-contracts/`
  (the local command writes to stdout only);
- smoke: `test-results/full-color-smoke/`;
- renderer fixtures: `test-results/full-color-renderer-contracts/`;
- renderer runtime: `test-results/full-color-renderer-runtime/`;
- local certification: `test-results/full-color-harness/attempt-NNNN/`;
- per-test E2E diagnostics: the configured `ROM_TEST_RESULTS` root;
- reviewed evidence: `specs/full-colors/evidence/`.

An ignored artifact is not authority by itself. Bind conclusions to its source
revision, ROM hashes, producer, manifest, and attempt directory.

## False-confidence traps

- A successful build does not prove boot, progression, ownership, or visuals.
- A linked symbol does not prove natural reachability.
- A callable routine does not prove the normal game invokes it.
- A synthetic checker proves its modeled contract, not the renderer.
- One screenshot does not prove timing or absence of flicker.
- A debug-only path does not prove release or VC behavior.
- The audit product is diagnostic, not a player-visible behavior variant.
- Color and Yellow comparison must select both modes inside the same shipped
  product, not compare two different binaries as behavioral baselines.
- A green hosted run does not prove manual play or unencoded scene coverage.

## Gates that must not be weakened

Do not make a failure disappear by widening timing bounds without evidence,
dropping a product, accepting missing symbols, replacing natural inputs with
state injection, editing reviewed JSON by hand, loosening mutation tests,
raising visual tolerance, reusing emulator state, or treating a skipped job as
success. Fix the implementation, authority, or test premise that is wrong.

## Failure map

- Build/link/layout: `Makefile`, `layout.link`, and product `.map`/`.sym` files.
- Product identity or discovery: `tools/rom_tests/full_color/rom_discovery.py`
  and source/inventory producers.
- Evidence determinism: `tools/rom_tests/full_color/evidence_runner.py`.
- Audit evidence: `tools/rom_tests/full_color/phase2_measurements.py`.
- Renderer fixtures: `tools/rom_tests/full_color/renderer_conformance_runner.py`.
- Runtime ownership: `tools/rom_tests/full_color/renderer_runtime_runner.py`.
- Gameplay/navigation: `tools/rom_tests/scenarios/` and the owning E2E suite.
- Snapshot mismatch: inspect actual/diff images before changing the reviewed
  snapshot or comparison boundary.

Fix the first failing authority. Later failures often describe fallout.

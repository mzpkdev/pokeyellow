# ROMhack development workflow

This is the next-day continuation and handoff manual for the ROMhack as a
whole. Start with [Documentation index](INDEX.md), then read
[Architecture](ARCHITECTURE.md) before changing shared runtime behavior and
[Testing](TESTING.md) before treating a green check
as proof. Feature-specific guides, including the current full-color extension
recipe, are linked from [Adding content](ADDING_CONTENT.md). Historical
failures are recorded in [Bugs and glitches](BUGS_AND_GLITCHES.md).

## Start every session from facts

Read the repository instructions and inspect the checkout before assuming that
yesterday's state still applies:

```console
cat AGENTS.md
git status --short --branch
git log -5 --oneline --decorate
git diff --stat
git diff
```

Check the active pull request and hosted checks when the branch has one. Local
files do not reveal whether the last push is green, whether review changed, or
whether the target branch moved.

Treat the worktree as shared. Existing modifications and untracked files belong
to their author unless the current task explicitly owns them. Do not clean,
rewrite, stage, or reformat unrelated paths. In particular, `.preemdeck/` is
operator state, not ROMhack source. Preserve it.

Before editing, establish:

- the requested player-visible outcome and its deliberate exclusions;
- the files, products, and tests the change is allowed to affect;
- whether generated data or retained evidence has an authoritative producer;
- which stock or debug ROM supplies the comparison baseline;
- which checks actually exercise the changed runtime path.

Then perform the architecture conflict gate: compare the task or pull-request
plan with [Architecture](ARCHITECTURE.md), the current product truth in
[the index](INDEX.md), and any applicable normative subsystem manual. Plans
govern execution scope, but they MUST NOT override current approved
architecture or product truth. If the plan contradicts an approved owner,
activation path, product boundary, data flow, scheduler, or lifecycle,
implementation MUST stop and the operator must decide explicitly.

Do not write code for the contradictory plan and revise the manuals afterward
to make that unapproved architecture look intentional. Update architecture
documentation only when a separately approved architecture change authorizes
both the new contract and its dependent implementation.

## General build and review loop

Use the cheapest check capable of disproving the current change, then widen the
circle:

1. Run focused tests or validators for the edited subsystem.
2. Build every product whose assembly path, data, or packaging may have changed.
3. Run the subsystem's broader suite and product-identity checks.
4. Compare relevant output against an appropriate stock or previous baseline.
5. Exercise the feature through natural gameplay from a cold boot.
6. Run the retained project gates required by the feature's documentation and
   pull request.
7. Inspect the complete diff and every generated or untracked artifact before
   handoff.

The repository's ordinary products are:

```console
make yellow
make yellow_debug
make yellow_vc
```

Use `make compare` when the task is expected to preserve the pinned stock ROM
identities. A successful build proves that RGBDS accepted the source. It does
not prove that the game boots, progresses, renders correctly, or preserves
unrelated products.

Manual review must match the change. Start from a cold boot rather than a save
state produced by another revision. Test transitions into and out of the
changed behavior, repeated use, menus and interruption points, save/reset when
state persists, and both directions of movement when maps or scrolling are
involved. Watch several frames: a single screenshot misses flicker, transient
corruption, deadlocks, and delayed writes.

## Failure triage

Capture the failure before changing code. Record the exact ROM, source revision,
command or input sequence, last known-good scene, and artifact directory. Keep
the `.gbc`, `.sym`, and `.map` files from one source revision together.

Classify first; debug second:

- **Build or link failure:** reduce to the first assembler/linker error and
  confirm the expected RGBDS/tool environment. Later diagnostics are commonly
  fallout.
- **Boot or progression stop:** compare the same path in `pokeyellow_debug.gbc`.
  If both fail, suspect the scenario, toolchain, or shared ROM change before a
  feature-only runtime.
- **Visual geometry corruption:** wrong shapes, positions, repeated fragments,
  or overlays in the wrong scene indicate tile data, indices, banks, coordinates,
  ownership, or cleanup—not aesthetic tuning.
- **Correct geometry, wrong presentation:** inspect feature data and dispatch
  only after proving the underlying stock-owned scene still matches.
- **Intermittent failure:** record frame timing, transition direction, and
  concurrent redraw/animation work. Inspect sequences or frame strips instead
  of only the final frame.
- **Stale evidence:** bind every conclusion to its manifest, ROM identity,
  revision, and attempt directory. Never copy an old green summary over a new
  failure or regenerate evidence until it happens to pass.

Diagnostic output is evidence, not source. Preserve failed and successful
attempts separately. Regenerate checked-in evidence only through its documented
producer and review the semantic diff, not merely the exit code.
Ordinary `measure-full-color-*` commands stop before that acceptance boundary:
they write unreviewed proposals under `test-results/full-color-proposals/` and
never update checked-in authority or evidence. A human review must explicitly
incorporate accepted authority changes before generating reviewed evidence.

## Current playable full-color loop

The normal, debug, and VC products all ship the same saved Color/Yellow toggle
and bounded passive renderer. Color passively colors city and route maps using
`OVERWORLD` plus the authored conventional-interior tileset range. Yellow mode,
unsupported maps, menus, battles, cutscenes, sprites, and animation retain Pokemon Yellow's
existing visual behavior.

`pokeyellow_phase2_audit.gbc` adds diagnostic and certification surfaces to the
same behavior. `PHASE2_AUDIT` does not gate the toggle or renderer. Read
[Architecture](ARCHITECTURE.md) for the ownership contract and
[Adding content](ADDING_CONTENT.md) before adding a map or palette.

Set up the pinned Python environment once per checkout, then build the shipped
normal and debug ROMs used by the natural journeys. Build the audit ROM as well
when running its diagnostic verifier:

```console
make test-full-color-setup
make yellow yellow_debug yellow_phase2_audit
```

Use `pokeyellow.gbc` for ordinary Color and Yellow review, changing the saved
option inside the game. The debug ROM is for journeys that need debug controls;
it is not a separate Yellow baseline.
Run checks from fast to slow:

```console
.venv/bin/python -m pytest tools/rom_tests/tests/unit/full_color -q
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

Use the narrow commands while iterating. Certification runs the complete unit,
harness, evidence, audit, renderer, and gameplay graph once; only stable
evidence capture runs twice. The renderer fixture checker remains synthetic,
and neither certification nor hosted gameplay replaces human visual review.

At minimum, play through the Game Freak logo, Oak's introduction, bedroom,
Pallet Town, Oak's interception and capture, Route 1, Viridian entry, and the
return trip. Exercise a house transition, dialogue, Start and party menus, a
wild battle, save/reset/Continue, scrolling in both directions, and ledges.
Verify stable slice color, stock-like geometry and sprites, clean fallback, clean
return, and no seams or one-frame palette swaps.

### Full-color-specific triage

- A white screen or progression stop is a control-flow failure, not a palette
  problem. Narrow the first renderer entry reached before the stall; inspect
  audit-only entries only when the failing product is the audit ROM.
- Corrupt tiles or cutscene graphics drawn over an overworld mean tile bytes,
  indices, attribute coordinates, VRAM banks, wrapping, or cleanup are wrong.
  Stop palette tuning until geometry matches the debug ROM.
- If geometry matches but a roof, ground, or object color is wrong, inspect the
  palette payload, map roof assignment, and tile-to-attribute authority.
- For flicker or seams, assume scheduling until disproved. Yellow's redraw and
  animation work retains priority; passive work must defer or clear in bounded
  chunks.
- Audit-only diagnostics in a shipped product are a release-boundary
  regression. The toggle and passive renderer themselves are required there.
  Stop feature work and run the product-linkage and Phase 2 audit checks; do not
  weaken reachability, identity, or provenance assertions.

Full-color artifacts currently land in:

- deterministic evidence: `test-results/full-color-evidence/`;
- hosted harness-contract log artifact: `test-results/full-color-contracts/`
  (the local command writes to stdout only);
- smoke: `test-results/full-color-smoke/`;
- renderer fixtures: `test-results/full-color-renderer-contracts/`;
- renderer runtime: `test-results/full-color-renderer-runtime/`;
- local certification: `test-results/full-color-harness/attempt-NNNN/`;
- E2E diagnostics: the configured `ROM_TEST_RESULTS` root;
- reviewed evidence: `specs/full-colors/evidence/`.

The future renderer direction is governed by the
[full-color migration plan](../specs/full-colors/docs/migration-plan.md). Do not
collapse Phases 3–9 into a vague next phase, widen an allowlist as a substitute
for map-aware content, or claim retained architecture is already active.

## Hosted pull-request checks

Full `CI` is commit-bearing: it runs when a pull request is opened, when a new
commit synchronizes the pull request, and for pushes to `main`. A newer commit
on the same pull request cancels obsolete in-flight verification, so the
latest revision is the one consuming hosted capacity.

Title/body edits, reopening, and draft-state changes run `Metadata` only;
metadata edits cannot repeat full verification. `Metadata / Lint` validates workflow
syntax and the Conventional Commit title without rebuilding ROM products.
On reopen, the same check queries the exact current head SHA and fails closed
unless that revision already has a successful `Merge Gate` check.
Concurrency is scoped by pull request and event action, so a later edit or
draft-state change cannot cancel the reopen check or replace its result with a
same-named job. Repeated runs of the same action may cancel their obsolete
predecessors. The existing merge gate is reused until a new commit is
pushed; that commit starts a fresh full `CI` run.

`Merge Gate` is the stable final status. `Build` creates all products once.
The remaining `CI` jobs expose the donor contract, unit contracts, repository
inventory and bank safety, independent evidence captures and comparison,
renderer contracts, audit evidence, and three E2E suites directly. `Merge Gate`
fails when any dependency fails, is skipped, or is cancelled.

The active `main` ruleset requires pull requests, `Metadata / Lint`, and
`CI / Merge Gate`; it blocks branch deletion and force pushes. The trusted
`Metadata / Labels` check remains non-required.

## Handoff, commit, and pull-request discipline

Before committing or handing work to another session:

1. Review `git status`, the full diff, every new file, and every generated file.
2. Separate task-owned paths from concurrent or unrelated work.
3. Run the focused checks, product builds, identity checks, gameplay journeys,
   manual review, and retained gates appropriate to the blast radius.
4. Record exact commands and outcomes; explicitly name checks not run.
5. Record the ROM and revision manually played, route taken, observed result,
   and useful artifact directories.
6. Obtain fresh read-only review of the task diff and verify every finding
   against source or runtime evidence.
7. Stage exact paths only. Do not use blanket staging in a dirty worktree.
8. Recheck the staged diff, commit only reviewed paths, push the feature branch,
   update the pull request with verified facts, and watch hosted CI to completion.

Pull-request descriptions start from `.github/pull_request_template.md` and
follow `AGENTS.md`: lead with the player-visible premise, explain mechanics and
limits plainly, show affected content, document meaningful tradeoffs, and end
with verified checks. Never claim a release behavior, supported map, test, or
CI result that the branch has not earned.

Implementation workers do not commit, push, or rewrite pull requests. The root
operator owns exact-path staging and external state. If the worktree is dirty,
that discipline is not bureaucracy—it is what keeps somebody else's work out
of your commit.

## A useful next-day handoff note

A continuation note should answer, without relying on chat history:

- Which branch and pull request are active, and what is their current state?
- What player-visible behavior exists now, in which ROM product?
- What changed in the last session, using exact paths?
- Which commands passed, failed, or were skipped?
- What was manually played, from which revision, and what was observed?
- Where are the useful success and failure artifacts?
- What unresolved issue or next bounded task should be taken first?
- Which invariants, exclusions, and concurrent files must remain untouched?

If those answers are missing, tomorrow starts with archaeology. Write them down.

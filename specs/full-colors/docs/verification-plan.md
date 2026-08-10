# Overworld verification plan

This file is the sole requirement-to-check index. It defines live and planned
checks plus the evidence each implementation boundary must produce. The
[verification contracts](verification-contracts.md) define the current local
and hosted split, and the [AI harness](ai-iteration-harness.md) runs the checks
in the tiers below. Checks marked future remain non-gating until their runtime
authority is activated.

## Check definitions

- **CHK-OWN-01:** Method: seeded owner/phase/generation model sequences plus owner-gated writer traces; tier: fast/full; evidence: semantic snapshots, decoded trace, mutation result, seed, and reduced action sequence.
- **CHK-SELECT-01:** Method: enumerate the explicit Cartesian product `{COLOR, YELLOW}` × `{ordinary map presentation, overlay, dialogue, menu, battle, standalone, boot/reset}` × `{each of 34 supported OVERWORLD maps, each of 162 supported interior maps, unsupported map}` without pruning inapplicable-looking cells; tier: fast/full; evidence: all 2,758 pure-resolver rows, including every forced context across the supported 19-interior-tileset slice and unsupported cases, with exactly one owner per cell and a mutation proving preference cannot authorize a write. The expanded harness execution and its evidence are deferred and are not claimed by the current implementation slice.
- **CHK-SELECT-02:** Method: recompute policy before each destination's first owner-gated writer and exercise same-owner and changed-owner cases in both directions; tier: focused/full; evidence: preference/write trace, owner/generation trace, cancellation reason, reconstruction ledger, and exactly one barrier per real handoff.
- **CHK-PROD-01:** Method: inspect normal, debug, and VC source/symbol/callgraph reachability and run the bounded scene matrix across the 34 supported `OVERWORLD` maps and 162 maps using the 19 admitted interior tilesets; tier: fast/focused/full; evidence: exact supported-map gate, forced-Yellow traces, unreachable `OVERWORLD_OVERLAY`, and no production audit carrier. Expanded harness execution is deferred, so the current slice claims build/source/symbol reachability only, not scene-matrix evidence.
- **CHK-REQUEST-01:** Method: runtime pressure for exactly the selected policy of each request class plus schema/reference-model coverage of unselected enum branches; tier: fast/full; evidence: selected capacity/policy table, required-work defer/retry trace, optional-or-supersedable final-rejection fallback where selected, work accounting, and reduced seed.
- **CHK-JOB-01:** Method: handoff, reset, supersession, stale-generation, and adversarial cancellation sequences; tier: fast/full; evidence: job-state and cancellation trace proving no post-cancellation write.
- **CHK-COMMIT-01:** Method: force insufficient budget at every pre-visible preparation/revalidation boundary, verify deferral before `COMMITTING`, and verify uninterrupted completion after worst-case budget reservation; tier: focused/full; evidence: old/new semantic snapshots, frame strip, commit-unit/writer IDs, boundary defer traces, reservation record, and inactive-or-LCD-off interruption cases.
- **CHK-RETURN-01:** Method: for every concrete Yellow-to-Color eligible-map boundary, poison every destination resource and reconstruct from fresh logical authority; tier: focused/full; evidence: concrete directed scene IDs, poison record, reconstruction-item ledger, exactly one presentation barrier, and five active-frame snapshots.
- **CHK-OVERLAY-01:** Method: independent request-data oracle across authoritative BG/window destination, map/tileset identity, nonsingular world transform, override set, clipping mappings, classification, and full-byte precedence; tier: fast/focused/full; evidence: complete causal request fixture, canonical clipped source-index/destination/world mapping records, independently derived tile and attribute bytes, structural proof for each matrix case, and trace proving no VRAM or ambient-map oracle read.
- **CHK-OAM-01:** Method: derive missing, out-of-range, and unmapped fallback classification from final-picture identity plus one corpus-level authoritative mapped-identity set shared by every OAM case under diagnostic and release builds; tier: fast/focused; evidence: corpus-authority consistency/completeness validation, occurred/kind/identity/generation/writer, final tile, before/after attributes, palette-0 result, diagnostic fallback record, and release-symbol audit.
- **CHK-TIME-01:** Method: named instruction-path cycle equations for every selector-activated operation, each with natural budget/deadline, exact-fit case, and exact threshold-plus-one case; tier: focused/full; evidence: completed timing row, equation result, exact-fit commit, whole-unit defer trace, and timing artifact key.
- **CHK-INV-01:** Method: reconcile source search with symbol-guided built-ROM disassembly for the initial map-entry slice and every later declared implementation slice; tier: fast/full; evidence: reviewed `WR-…`, `SC-…`, and `MU-…` rows, before-reachability review, slice closure report, visible out-of-slice backlog, and unlisted-writer/scene/mutation fixtures.
- **CHK-TRACE-01:** Method: validate authority definitions, references, and bidirectional primary mappings; tier: fast; evidence: machine-readable mapping report and zero unknown, uncovered, duplicate, or orphan IDs.
- **CHK-EVIDENCE-01:** Method: execute independent full-color evidence captures against the same debug ROM and compare every stable artifact byte-for-byte; tier: fast/full; evidence: comparison summary, semantic snapshot, traceability report, visual manifest, images, and retained diagnostics.
- **CHK-BUILD-01:** Method: reproducibly build release, debug, and VC variants with warnings fatal; tier: fast/full; evidence: commands, tool versions, ROM content IDs, headers, symbols, link maps, and warning logs.
- **CHK-CGB-01:** Method: exercise CGB hard boot, DMG/SGB rejection, soft reset, and double-speed initialization; tier: fast/full; evidence: header bytes, startup traces, reset snapshots, and rejection-path checkpoints.
- **CHK-BANK-01:** Method: invoke renderer paths from non-default ROM/VRAM banks, every selected renderer WRAM bank, every other valid WRAM entry bank, and interrupt boundaries; tier: fast/focused/full; evidence: before/after bank, stack, interrupt, owner, generation, and dirty-state snapshots.
- **CHK-ROM-01:** Method: inspect source, link maps, and donor adaptations for prohibited banks and MBC1 assumptions; tier: fast/full; evidence: placement decision record, link-map ranges, far-call audit, and negative source/disassembly findings.
- **CHK-PALETTE-01:** Method: compare base, transformed, and hardware BG/OBJ palettes through every remap/effect and owner-dispatched wrapper; tier: focused/full; evidence: palette snapshots, wrapper trace, complete-payload commit record, and visual checkpoints.
- **CHK-TRANSFER-01:** Method: exercise every concrete paired-transfer mutation and destination from the closed baseline and atomically extended inventories; tier: focused/full; evidence: concrete mutation/writer IDs, renewed source/ROM closure, tile/attribute byte pairs, serialization trace, and five-frame boundary captures.
- **CHK-TILESET-01:** Completed, non-gating content method: audit all 25 tilesets, table assertions, graphics, roofs, overrides, animations, and native Beach House data; tier: full; evidence: table lengths, assignment audit, semantic atlas, animation captures, and reviewed visual atlas. The all-25 corpus is authored and reviewed. Runtime exercise and admission remain limited to the bounded outdoor/conventional-interior presentation predicate and do not follow from content closure.
- **CHK-HANDOFF-01:** Method: execute every concrete changed-owner edge in both directions plus reset and soft reset from Color, and every same-owner edge; tier: focused/full; evidence: close/cancel/generation/select/reconstruct/barrier/reopen ordering, destination-resource unknown/poison ledger, complete fresh destination reconstruction ledger, exactly one generation and barrier per changed owner, admission reopening only afterward, zero generation for same owner, bank/interrupt restoration, hidden-display proof where used, normal-boot re-entry after soft reset, and first-writer trace.
- **CHK-OAM-02:** Method: exercise player, follower, every mapped object class, maximum population, shadow construction, sort/copy, invalidation, and one hardware DMA; tier: focused/full; evidence: concrete writer/mutation IDs, final-picture mapping, shadow/hardware OAM snapshots, DMA trace, and frame strip.
- **CHK-VISUAL-01:** Method: inspect named screenshots, bounded frame strips, annotated contact sheets, and localized image diffs beside semantic state; tier: fast/focused/full; evidence: versioned manifest, reviewer result, image diffs, snapshots, and linked traces.
- **CHK-STRESS-01:** Method: repeat simultaneous scrolling, animation, palette, maximum representative OAM, and interrupt pressure; tier: focused/full; evidence: request accounting, semantic snapshots, writer trace, bank snapshots, numeric timing rows, and reviewed frame strips.
- **CHK-STRESS-02:** Method: poison the complete R2.10 destination-resource set around both handoff directions and reset/soft reset from Color; tier: focused/full; evidence: concrete scene IDs, admission closure, cancellation, complete fresh R2.11 reconstruction ledger, exactly one barrier, admission reopening only afterward, hidden-display proof for any reset path using it, normal-boot re-entry after soft reset, five active frames after each return, model trace, and timing rows.
- **CHK-STRESS-03:** Method: force insufficient budget at every pre-visible connection-transfer boundary and interrupt mid-operation only for inactive or LCD-off destinations; tier: focused/full; evidence: concrete mutation/writer IDs, old/new snapshots, pre-commit defer traces, reserved-budget completion, bank state, timing row, and frame strip.
- **CHK-REMOVE-01:** Method: source plus built-ROM reachability audit for obsolete competing ownership, restoration, and transitional paths while proving required Yellow paths remain; tier: full; evidence: deleted/unreachable concrete inventory rows, retained forced-Yellow reachability, negative disassembly findings, and adapter disposition report.
- **CHK-REGRESS-01:** Method: run baseline-equivalence scenarios for Yellow preference and every forced-Yellow lifecycle/resource path in normal, debug, and VC products; tier: focused/full; evidence: concrete scene IDs, semantic and visual comparisons, build variants, and regression logs.
- **CHK-CANARY-01:** Method: exercise all eight diagnostic canary palette slots and selected tile classes and audit release exclusion; tier: fast/focused; evidence: semantic palette/tile snapshots, screenshots, debug trace, and release source/symbol findings.

### Checker execution modes

| Mode | Input evidence | What a pass proves | Acceptance effect |
|---|---|---|---|
| `synthetic_checker_self_test` | independently authored `SCHEMA_FIXTURE` snapshots and traces | the named checker accepts its positive contract case and rejects its named corruptions | none |
| `rom_runtime` | `RENDERER_RUNTIME` snapshots and traces from a declared nonzero activation phase | the activated renderer path matches the independent oracle | contributes evidence only to the named activated `CHK-…` and mapped acceptance rows |

The mode is recorded in every conformance report and manifest. A synthetic
result cannot be promoted, relabelled, or aggregated as runtime evidence.
Synthetic inputs may contain only causal initial state, actions, and request
configuration. Exact results—including job completion/cancellation,
reconstruction ledgers and barriers, and fallback kind—must be derived. The
case parser rejects missing primary check IDs and check IDs unrelated to the
selected operation before a report can be produced.

## Requirement-to-evidence traceability

Each row has one primary requirement. Cross-reference cells contain only
defined concrete IDs.

| Map kind | Requirement | Acceptance | Check | Tier | Mutation | Evidence |
|---|---|---|---|---|---|---|
| R-MAP | R1.1 | AC-DONE-01, AC-OWN-01 | CHK-OWN-01 | fast/full | zero or dual active owner | owner snapshot and writer trace |
| R-MAP | R1.2 | AC-OWN-01, AC-TECH-06 | CHK-OWN-01 | fast/full | invalid owner/phase pair | model and ROM transition trace |
| R-MAP | R1.3 | AC-OWN-01, AC-TECH-04 | CHK-OWN-01 | fast/full | Yellow write during full-color ownership | assertion and writer trace |
| R-MAP | R1.4 | AC-OWN-01, AC-TECH-04 | CHK-OWN-01 | fast/full | full-color write during Yellow ownership | assertion and writer trace |
| R-MAP | R1.5 | AC-OWN-01, AC-TECH-06 | CHK-OWN-01 | fast/full | absent owner or generation | job snapshot and trace |
| R-MAP | R1.6 | AC-HO-04, AC-JOB-01 | CHK-JOB-01 | fast/full | departing-generation execution | cancellation and no-later-write trace |
| R-MAP | R1.7 | AC-EVIDENCE-01, AC-INV-01, AC-TECH-03 | CHK-EVIDENCE-01, CHK-INV-01 | fast/full | reachable unlisted in-slice writer | source/ROM slice closure report |
| R-MAP | R1.8 | AC-REQUEST-01 | CHK-REQUEST-01 | fast/full | missing admission declaration | request record and assertion |
| R-MAP | R1.9 | AC-REQUEST-01 | CHK-REQUEST-01 | fast/full | wrong owner | result and no-work trace |
| R-MAP | R1.10 | AC-REQUEST-01 | CHK-REQUEST-01 | fast/full | stale generation | result and no-work trace |
| R-MAP | R1.11 | AC-REQUEST-01 | CHK-REQUEST-01 | fast/full | accepted request untracked | request/job accounting |
| R-MAP | R1.12 | AC-REQUEST-01 | CHK-REQUEST-01 | fast/full | equivalent request at capacity | coalescing attachment trace |
| R-MAP | R1.13 | AC-REQUEST-01 | CHK-REQUEST-01 | fast/full | retryable pressure | deferred no-work and retry trace |
| R-MAP | R1.14 | AC-REQUEST-01 | CHK-REQUEST-01 | fast/full | final pressure rejection | rejected no-work/finality trace |
| R-MAP | R1.15 | AC-REQUEST-01, AC-STRESS-01 | CHK-REQUEST-01, CHK-STRESS-01 | fast/full | capacity plus one | selected-policy result record |
| R-MAP | R1.16 | AC-REQUEST-01, AC-STRESS-01 | CHK-REQUEST-01, CHK-STRESS-01 | fast/full | admitted-work pressure | eventual-completion accounting |
| R-MAP | R1.17 | AC-COMMIT-01 | CHK-COMMIT-01 | focused/full | pending/prepared presented write | resource snapshots |
| R-MAP | R1.18 | AC-REQUEST-01 | CHK-REQUEST-01 | fast/full | non-equivalent coalescing | ordered final-state comparison |
| R-MAP | R1.19 | AC-JOB-01, AC-TECH-06 | CHK-JOB-01 | fast/full | illegal job transition | state trace and model diff |
| R-MAP | R1.20 | AC-JOB-01, AC-TECH-06 | CHK-JOB-01 | fast/full | absent/invalid cancellation reason | cancellation trace |
| R-MAP | R1.21 | AC-COMMIT-01, AC-STRESS-01 | CHK-COMMIT-01, CHK-TIME-01 | focused/full | state/budget change before commit | revalidation trace and timing row |
| R-MAP | R1.22 | AC-COMMIT-01, AC-STRESS-01 | CHK-COMMIT-01, CHK-TIME-01 | focused/full | insufficient time | whole-unit defer evidence |
| R-MAP | R1.23 | AC-COMMIT-01, AC-TECH-05 | CHK-COMMIT-01 | focused/full | early completion record | declared-resource diff |
| R-MAP | R1.24 | AC-JOB-01 | CHK-JOB-01 | fast/full | write after cancellation | bounded trace |
| R-MAP | R1.25 | AC-COMMIT-01, AC-HO-04 | CHK-COMMIT-01, CHK-JOB-01 | focused/full | missing reservation or illegal visible mid-commit interruption | reservation, presentation, and ownership trace |
| R-MAP | R1.26 | AC-REQUEST-01, AC-STRESS-01 | CHK-REQUEST-01, CHK-STRESS-01 | focused/full | preselected representation | phase-local numeric decision record |
| R-MAP | R1.27 | AC-JOB-01 | CHK-JOB-01, CHK-COMMIT-01 | fast/full | failed commit revalidation | cancellation/no-write trace |
| R-MAP | R1.28 | AC-COMMIT-01, AC-REQUEST-01 | CHK-REQUEST-01, CHK-COMMIT-01 | focused/full | numeric budget failure | prepared-job retry trace |
| R-MAP | R1.29 | AC-SELECT-01, AC-SELECT-02 | CHK-SELECT-01, CHK-SELECT-02 | fast/full | preference directly grants a write | policy/write trace |
| R-MAP | R1.30 | AC-DONE-01, AC-HO-02, AC-PROD-01, AC-SELECT-01 | CHK-SELECT-01, CHK-PROD-01 | fast/full | Color outside exact eligible cells | exhaustive matrix and reachability audit |
| R-MAP | R1.31 | AC-DONE-01, AC-PROD-01, AC-SELECT-01 | CHK-SELECT-01, CHK-PROD-01 | fast/full | zero or dual effective owner | exhaustive matrix |
| R-MAP | R1.32 | AC-DONE-01, AC-HO-01, AC-HO-03, AC-RETURN-01, AC-SELECT-02 | CHK-SELECT-02, CHK-HANDOFF-01, CHK-RETURN-01 | focused/full | wrong generation count | transition trace and ledger |
| R-MAP | R1.33 | AC-OWN-01 | CHK-OWN-01, CHK-PROD-01 | focused/full | multiple VBlank owner routes | per-frame writer trace |
| R-MAP | R2.1 | AC-HO-01, AC-HO-04, AC-JOB-01, AC-SELECT-02 | CHK-JOB-01, CHK-HANDOFF-01 | focused/full | admission during handoff | admission and transition trace |
| R-MAP | R2.2 | AC-HO-01, AC-HO-04, AC-JOB-01, AC-SELECT-02, AC-STRESS-03 | CHK-JOB-01, CHK-COMMIT-01 | focused/full | handoff at commit step | old/new unit and cancellation trace |
| R-MAP | R2.3 | AC-HO-01, AC-HO-04, AC-JOB-01, AC-SELECT-02 | CHK-JOB-01, CHK-HANDOFF-01 | focused/full | aliasing generation | generation and writer trace |
| R-MAP | R2.4 | AC-HO-01, AC-SELECT-02 | CHK-HANDOFF-01 | focused/full | early admission reopening | owner/init/admission trace |
| R-MAP | R2.5 | AC-OW-02 | CHK-RETURN-01, CHK-TRANSFER-01 | focused/full | present before reconstruction | reconstruction ledger |
| R-MAP | R2.6 | AC-DONE-01, AC-HO-01, AC-OW-03, AC-STRESS-02 | CHK-HANDOFF-01 | focused/full | Yellow display before selection | first-writer trace |
| R-MAP | R2.7 | AC-DONE-01, AC-HO-03, AC-RETURN-01, AC-STRESS-02 | CHK-HANDOFF-01, CHK-RETURN-01 | focused/full | actual Yellow-to-overworld boundary shortcut or invented return | directed boundary and reconstruction evidence |
| R-MAP | R2.8 | AC-DONE-01, AC-HO-04, AC-JOB-01, AC-STRESS-02 | CHK-JOB-01, CHK-CGB-01, CHK-HANDOFF-01, CHK-STRESS-02, CHK-TIME-01 | focused/full | reset or soft reset exposes display, reopens admission, omits ledger/barrier, or skips normal boot | hidden-display/admission trace, full Yellow ledger, exactly-one-barrier trace, timing row, and normal-boot checkpoint |
| R-MAP | R2.9 | AC-HO-04, AC-JOB-01, AC-TECH-06 | CHK-JOB-01, CHK-OWN-01 | fast/full | live-generation reuse | generation trace |
| R-MAP | R2.10 | AC-HO-03, AC-RETURN-01, AC-STRESS-02 | CHK-RETURN-01, CHK-STRESS-02 | focused/full | poisoned prior resources | unknown-state and rebuild ledger |
| R-MAP | R2.11 | AC-HO-03, AC-RETURN-01, AC-STRESS-02, AC-TECH-05 | CHK-RETURN-01, CHK-STRESS-02 | focused/full | omitted reconstruction item | per-item ledger and snapshot |
| R-MAP | R2.12 | AC-HO-03, AC-RETURN-01, AC-STRESS-02 | CHK-RETURN-01, CHK-STRESS-02 | focused/full | missing/early barrier | barrier and five-frame trace |
| R-MAP | R2.13 | AC-HO-03, AC-REMOVE-02, AC-RETURN-01, AC-STRESS-02 | CHK-RETURN-01, CHK-REMOVE-01 | focused/full | saved-byte restoration | poison result and reachability audit |
| R-MAP | R3.1 | AC-TECH-02 | CHK-CGB-01 | fast/full | DMG/SGB startup | header and rejection checkpoints |
| R-MAP | R3.2 | AC-TECH-02 | CHK-CGB-01 | fast/full | repeated/missing speed switch | hard-boot trace |
| R-MAP | R3.3 | AC-TECH-07 | CHK-BANK-01 | focused/full | unmeasured WRAM placement | Phase 1 decision record and link map |
| R-MAP | R3.4 | AC-EVIDENCE-01, AC-TECH-02 | CHK-CGB-01, CHK-EVIDENCE-01, CHK-JOB-01 | fast/full | observable uncleared state | boot/reset snapshots |
| R-MAP | R3.5 | AC-EVIDENCE-01, AC-TECH-07 | CHK-BANK-01, CHK-EVIDENCE-01 | fast/full | leaked bank/stack/interrupt | boundary snapshots |
| R-MAP | R3.6 | AC-EVIDENCE-01, AC-TECH-07 | CHK-BANK-01, CHK-EVIDENCE-01 | fast/full | accidental return bank | Yellow-return snapshots |
| R-MAP | R4.1 | AC-TECH-01 | CHK-ROM-01, CHK-BUILD-01 | fast/full | use donor bank 2c | link-map and source audit |
| R-MAP | R4.2 | AC-TECH-01 | CHK-ROM-01, CHK-BUILD-01 | fast/full | import donor bank 31 | link-map and source audit |
| R-MAP | R4.3 | AC-TECH-01 | CHK-ROM-01, CHK-BUILD-01 | fast/full | assume extension bank 1c | link-map and source audit |
| R-MAP | R4.4 | AC-TECH-01 | CHK-BUILD-01, CHK-ROM-01 | fast/full | fixed unmeasured bank 3b | Phase 1 ROM/build audit |
| R-MAP | R4.5 | AC-TECH-07 | CHK-ROM-01, CHK-BANK-01 | fast/full | retained MBC1 assumption | far-call and bank audit |
| R-MAP | R5.1 | AC-OW-01, AC-TECH-05 | CHK-PALETTE-01 | focused/full | incomplete BG base palettes | palette snapshot |
| R-MAP | R5.2 | AC-OW-05, AC-TECH-05 | CHK-PALETTE-01 | focused/full | incomplete OBJ base palettes | palette snapshot |
| R-MAP | R5.3 | AC-OW-06, AC-TECH-05 | CHK-PALETTE-01 | focused/full | aliased base/transformed data | before/after buffers |
| R-MAP | R5.4 | AC-OW-06, AC-TECH-05 | CHK-PALETTE-01 | focused/full | destructive shade remap | base/transformed diff |
| R-MAP | R5.5 | AC-OW-06 | CHK-PALETTE-01, CHK-VISUAL-01 | focused/full | overworld visual effect | semantic palettes and frame strips |
| R-MAP | R5.6 | AC-TECH-04 | CHK-PALETTE-01, CHK-OWN-01 | focused/full | gameplay hardware palette write | wrapper/writer trace |
| R-MAP | R5.7 | AC-OWN-01, AC-TECH-06 | CHK-PALETTE-01, CHK-OWN-01 | focused/full | wrong-owner wrapper dispatch | dispatch trace |
| R-MAP | R5.8 | AC-TECH-08 | CHK-PALETTE-01, CHK-COMMIT-01 | focused/full | partial palette payload | payload snapshot and boundary frames |
| R-MAP | R6.1 | AC-OW-01 | CHK-TILESET-01 | full | lookup length/coverage | semantic atlas |
| R-MAP | R6.2 | AC-OW-01 | CHK-TILESET-01 | full | missing deliberate base assignment | assignment audit |
| R-MAP | R6.3 | AC-OW-01 | CHK-TILESET-01, CHK-OVERLAY-01 | focused/full | missing text/window default | expected attribute bytes |
| R-MAP | R6.4 | AC-OVERLAY-01 | CHK-OVERLAY-01 | fast/focused/full | incomplete request data | fixture schema and assertion |
| R-MAP | R6.5 | AC-OVERLAY-01 | CHK-OVERLAY-01 | fast/focused/full | classify before clipping | clipped coordinate map |
| R-MAP | R6.6 | AC-OVERLAY-01 | CHK-OVERLAY-01 | fast/focused/full | non-request classification | independent oracle diff |
| R-MAP | R6.7 | AC-OVERLAY-01 | CHK-OVERLAY-01 | fast/focused/full | meaningful attribute bits | full-byte expected/actual |
| R-MAP | R6.8 | AC-OVERLAY-01 | CHK-OVERLAY-01 | fast/focused/full | opaque precedence | explicit/default byte diff |
| R-MAP | R6.9 | AC-OVERLAY-01, AC-OW-04 | CHK-OVERLAY-01 | fast/focused/full | revealed precedence | override/lookup byte diff |
| R-MAP | R6.10 | AC-OVERLAY-01 | CHK-OVERLAY-01 | fast/focused/full | VRAM-derived oracle | observational-access trace |
| R-MAP | R6.11 | AC-OVERLAY-01 | CHK-OVERLAY-01 | focused/full | destination/clipping variant | destination matrix |
| R-MAP | R6.12 | AC-REMOVE-02 | CHK-REMOVE-01, CHK-OVERLAY-01 | fast/full | imported static palette-map mode | source/ROM negative evidence |
| R-MAP | R6.13 | AC-HO-02, AC-OW-03, AC-PROD-01 | CHK-PROD-01, CHK-REGRESS-01 | focused/full | production Color overlay route | source/ROM reachability and baseline trace |
| R-MAP | R7.1 | AC-DONE-01, AC-OW-02, AC-OW-03, AC-OW-04, AC-STRESS-03 | CHK-TRANSFER-01, CHK-COMMIT-01 | focused/full | unpaired tile write | paired byte and writer trace |
| R-MAP | R7.2 | AC-REMOVE-02 | CHK-REMOVE-01 | fast/full | gameplay repair hook | reachability audit |
| R-MAP | R7.3 | AC-COMMIT-01, AC-OW-02, AC-OW-06, AC-STRESS-01, AC-STRESS-03 | CHK-COMMIT-01 | focused/full | visible mixed unit | old/new frames and snapshots |
| R-MAP | R7.4 | AC-COMMIT-01, AC-STRESS-03 | CHK-COMMIT-01, CHK-TIME-01 | focused/full | over-budget indivisible unit | whole-unit defer trace |
| R-MAP | R8.1 | AC-OW-01 | CHK-TILESET-01 | full | absent tileset content | 25-tileset atlas |
| R-MAP | R8.2 | AC-OW-01 | CHK-TILESET-01 | full | donor content treated as authoritative | independent Yellow authorship and validation audit |
| R-MAP | R8.3 | AC-OW-01 | CHK-TILESET-01 | full | reused Safari data | Beach House evidence |
| R-MAP | R8.4 | AC-OW-01, AC-TECH-01 | CHK-TILESET-01, CHK-BUILD-01 | fast/full | wrong table length | build assertion |
| R-MAP | R8.5 | AC-OW-04 | CHK-TILESET-01 | full | roof/override mismatch | documented semantic cases |
| R-MAP | R8.6 | AC-OW-04 | CHK-TILESET-01, CHK-VISUAL-01 | full | incompatible animation indices | animation snapshots/frame strips |
| R-MAP | R9.1 | AC-OAM-01, AC-OW-05 | CHK-OAM-01, CHK-OAM-02 | fast/focused | map before final identity | final-identity trace |
| R-MAP | R9.2 | AC-OAM-01, AC-OW-05 | CHK-OAM-01, CHK-OAM-02 | fast/focused | control-bit clobber | before/after attributes |
| R-MAP | R9.3 | AC-OAM-01 | CHK-OAM-01 | fast/focused | unknown identity | palette-0 result |
| R-MAP | R9.4 | AC-OAM-01, AC-TECH-10 | CHK-OAM-01 | fast/focused | missing diagnostic fallback record | debug artifact |
| R-MAP | R9.5 | AC-OW-05 | CHK-OAM-02 | focused/full | Pikachu offset loss | final tile/OAM snapshot |
| R-MAP | R9.6 | AC-OW-05 | CHK-OAM-02 | focused/full | omitted object class | object coverage report |
| R-MAP | R9.7 | AC-OW-06, AC-STRESS-01, AC-TECH-08, AC-TIME-01 | CHK-TIME-01, CHK-OAM-02 | focused/full | maximum OAM budget/wobble | timing row and frame strip |
| R-MAP | R9.8 | AC-OW-05 | CHK-OAM-02, CHK-COMMIT-01 | focused/full | partial shadow/DMA image | shadow/hardware snapshots and DMA trace |
| R-MAP | R9.9 | AC-OW-05 | CHK-OAM-02 | focused/full | non-final palette identity | mapping trace |
| R-MAP | R10.1 | AC-TECH-07 | CHK-BANK-01, CHK-TIME-01 | focused/full | override-handler interference | interrupt trace and timing row |
| R-MAP | R10.2 | AC-OWN-01, AC-TECH-06 | CHK-OWN-01 | fast/full | wrong-owner VBlank route | owner/generation writer trace |
| R-MAP | R10.3 | AC-TIME-01 | CHK-TIME-01 | focused/full | late instrumentation | diagnostic-slice timing artifacts |
| R-MAP | R10.4 | AC-COMMIT-01, AC-STRESS-03, AC-TECH-08, AC-TIME-01 | CHK-TIME-01, CHK-COMMIT-01 | focused/full | unchecked upload threshold | timing and defer trace |
| R-MAP | R10.5 | AC-OW-02, AC-TECH-08 | CHK-TIME-01, CHK-TRANSFER-01 | focused/full | transfer/palette overlap | serialization trace and timing rows |
| R-MAP | R10.6 | AC-TECH-07 | CHK-BANK-01 | fast/full | scheduled-work bank leak | boundary snapshots |
| R-MAP | R10.7 | AC-TIME-01 | CHK-TIME-01 | focused/full | accepted donor constant | Yellow measurement record |
| R-MAP | R10.8 | AC-STRESS-01, AC-TECH-08, AC-TIME-01 | CHK-TIME-01 | focused/full | incomplete timing row | complete numeric row |
| R-MAP | R10.9 | AC-STRESS-01, AC-TECH-08, AC-TIME-01 | CHK-TIME-01 | focused/full | nonpositive timing margin | equation result |
| R-MAP | R10.10 | AC-COMMIT-01, AC-STRESS-01, AC-STRESS-03, AC-TECH-08, AC-TIME-01 | CHK-TIME-01, CHK-COMMIT-01 | focused/full | threshold plus one | whole-unit defer evidence |
| R-MAP | R10.11 | AC-DONE-01, AC-TECH-08, AC-TIME-01 | CHK-TIME-01 | focused/full | activated operation lacks numeric closure | equation, exact-fit, threshold-plus-one evidence |
| R-MAP | R11.1 | AC-TECH-10 | CHK-CANARY-01 | fast/focused | indistinct canary assignments | semantic and visual artifacts |
| R-MAP | R11.2 | AC-TECH-01 | CHK-CANARY-01, CHK-BUILD-01 | fast/full | canary in release | source/symbol audit |
| R-MAP | R11.3 | AC-EVIDENCE-01, AC-TECH-10 | CHK-EVIDENCE-01, CHK-VISUAL-01 | fast/focused/full | missing named visual | manifest and image artifacts |
| R-MAP | R11.4 | AC-EVIDENCE-01, AC-TECH-10, AC-TRACE-01 | CHK-EVIDENCE-01, CHK-VISUAL-01 | fast/focused/full | unpaired visual | linked snapshot and trace |
| R-MAP | R11.5 | AC-EVIDENCE-01, AC-TECH-10 | CHK-EVIDENCE-01, CHK-VISUAL-01 | fast/focused/full | visual-only verdict | machine assertion and review |
| R-MAP | R11.6 | AC-DONE-01, AC-EVIDENCE-01, AC-TECH-09 | CHK-EVIDENCE-01 | fast/full | non-identical evidence captures or renderer expands while a contract is red | evidence comparison and phase/build audit |
| R-MAP | R12.1 | AC-DONE-01, AC-HO-02, AC-OW-03, AC-PROD-01, AC-REMOVE-04, AC-SELECT-01 | CHK-REGRESS-01 | focused/full | changed Yellow lifecycle | baseline comparisons |
| R-MAP | R12.2 | AC-HO-01 | CHK-HANDOFF-01 | focused/full | standalone display before Yellow | first-writer trace |
| R-MAP | R12.3 | AC-REMOVE-02, AC-REMOVE-04 | CHK-REMOVE-01, CHK-REGRESS-01 | fast/full | imported excluded runtime | source/ROM audit |
| R-MAP | R12.4 | AC-DONE-01, AC-REMOVE-01, AC-REMOVE-03 | CHK-REMOVE-01 | full | reachable old overworld owner | reachability report |
| R-MAP | R12.5 | AC-HO-02, AC-PROD-01, AC-REMOVE-01, AC-REMOVE-03, AC-REMOVE-04 | CHK-REGRESS-01 | focused/full | removed required Yellow code | excluded-scene regressions |
| R-MAP | R12.6 | AC-DONE-01, AC-EVIDENCE-01, AC-INV-01, AC-TECH-03, AC-TECH-04, AC-TECH-09, AC-TRACE-01 | CHK-EVIDENCE-01, CHK-INV-01 | fast/full | unreviewed in-slice writer in CI | audit log and mutation |
| R-MAP | R12.7 | AC-REMOVE-01, AC-SELECT-01 | CHK-REMOVE-01 | full | dual selectable overworld modes | source/ROM negative evidence |
| R-MAP | R12.8 | AC-EVIDENCE-01, AC-INV-01 | CHK-EVIDENCE-01, CHK-INV-01, CHK-HANDOFF-01 | fast/full | scene touched without row | closed scene slice |

## Acceptance-to-evidence traceability

Each row has one primary acceptance outcome. Representative fast-tier samples
never satisfy a full-tier completion row.

| Map kind | Acceptance | Requirement | Check | Tier | Mutation | Evidence |
|---|---|---|---|---|---|---|
| AC-MAP | AC-OWN-01 | R1.1, R1.2, R1.3, R1.4, R1.5, R1.33, R5.7, R10.2 | CHK-OWN-01 | fast/full | hostile owner/phase/generation writer | snapshots, trace, reduced seed |
| AC-MAP | AC-SELECT-01 | R1.29, R1.30, R1.31, R12.1, R12.7 | CHK-SELECT-01 | fast/full | preference/lifecycle/map cell | exhaustive exactly-one-owner matrix |
| AC-MAP | AC-SELECT-02 | R1.29, R1.32, R2.1, R2.2, R2.3, R2.4 | CHK-SELECT-02, CHK-HANDOFF-01 | focused/full | preference write or incorrect handoff count | write-free preference and transition traces |
| AC-MAP | AC-PROD-01 | R1.30, R1.31, R6.13, R12.1, R12.5 | CHK-PROD-01, CHK-REGRESS-01 | fast/focused/full | Color outside bounded production scope | reachability and baseline evidence |
| AC-MAP | AC-REQUEST-01 | R1.8, R1.9, R1.10, R1.11, R1.12, R1.13, R1.14, R1.15, R1.16, R1.18, R1.26, R1.28 | CHK-REQUEST-01 | fast/full | selected per-class pressure plus model-only unselected branches | result/work-accounting and fallback trace |
| AC-MAP | AC-JOB-01 | R1.6, R1.19, R1.20, R1.24, R1.27, R2.1, R2.2, R2.3, R2.8, R2.9 | CHK-JOB-01 | fast/full | handoff/reset/adversarial cancellation | cancellation/no-later-write trace |
| AC-MAP | AC-COMMIT-01 | R1.17, R1.21, R1.22, R1.23, R1.25, R1.28, R7.3, R7.4, R10.4, R10.10 | CHK-COMMIT-01 | focused/full | every pre-visible budget boundary and reserved commit | old/new frames, defer traces, and reservation record |
| AC-MAP | AC-RETURN-01 | R1.32, R2.7, R2.10, R2.11, R2.12, R2.13 | CHK-RETURN-01 | focused/full | poisoned actual Yellow-to-Color edge | inventory IDs, ledger, barrier, five frames |
| AC-MAP | AC-OVERLAY-01 | R6.4, R6.5, R6.6, R6.7, R6.8, R6.9, R6.10, R6.11 | CHK-OVERLAY-01 | fast/focused/full | clipping and precedence matrix | independent oracle byte diffs |
| AC-MAP | AC-OAM-01 | R9.1, R9.2, R9.3, R9.4 | CHK-OAM-01 | fast/focused | invalid picture identities | palette-0/debug/control-bit evidence |
| AC-MAP | AC-TIME-01 | R9.7, R10.3, R10.4, R10.7, R10.8, R10.9, R10.10, R10.11 | CHK-TIME-01 | focused/full | numeric margin and threshold plus one | completed rows, exact fit, and defer trace |
| AC-MAP | AC-INV-01 | R1.7, R12.6, R12.8 | CHK-INV-01 | fast/full | unlisted reachable item | source/ROM reconciliation |
| AC-MAP | AC-TRACE-01 | R11.4, R12.6 | CHK-TRACE-01 | fast | unknown/uncovered/duplicate ID | validator and mapping report |
| AC-MAP | AC-EVIDENCE-01 | R1.7, R3.4, R3.5, R3.6, R11.3, R11.4, R11.5, R11.6, R12.6, R12.8 | CHK-EVIDENCE-01, CHK-INV-01, CHK-BANK-01, CHK-VISUAL-01 | fast/full | named evidence-contract mutations | comparison summary, semantic snapshots, traceability, and manifests |
| AC-MAP | AC-OW-01 | R5.1, R6.1, R6.2, R6.3, R8.1, R8.2, R8.3, R8.4 | CHK-TILESET-01, CHK-PALETTE-01 | full | all tileset content | semantic/visual atlas and audits |
| AC-MAP | AC-OW-02 | R2.5, R7.1, R7.3, R10.5 | CHK-TRANSFER-01, CHK-COMMIT-01 | focused/full | load/scroll/connection paths | paired bytes, traces, frame strips |
| AC-MAP | AC-OW-03 | R2.6, R6.13, R7.1, R12.1 | CHK-PROD-01, CHK-HANDOFF-01, CHK-REGRESS-01 | focused/full | dialogue and transient overlays | Yellow baseline and complete return evidence |
| AC-MAP | AC-OW-04 | R6.9, R7.1, R8.5, R8.6 | CHK-TILESET-01, CHK-TRANSFER-01 | full | overrides/animation/replacement | semantic atlas and frame strips |
| AC-MAP | AC-OW-05 | R5.2, R9.1, R9.2, R9.5, R9.6, R9.8, R9.9 | CHK-OAM-02 | focused/full | every object class and DMA | OAM snapshots and mapping/DMA trace |
| AC-MAP | AC-OW-06 | R5.3, R5.4, R5.5, R7.3, R9.7 | CHK-VISUAL-01, CHK-COMMIT-01, CHK-TIME-01 | focused/full | stale/mixed/flickering frame | frame strips, snapshots, timing rows |
| AC-MAP | AC-HO-01 | R1.32, R2.1, R2.2, R2.3, R2.4, R2.6, R12.2 | CHK-HANDOFF-01 | focused/full | incomplete Color-to-Yellow handoff | ordered transition and destination-first-writer trace |
| AC-MAP | AC-HO-02 | R1.30, R6.13, R12.1, R12.5 | CHK-REGRESS-01, CHK-PROD-01 | focused/full | forced-Yellow lifecycle regression | baseline comparisons |
| AC-MAP | AC-HO-03 | R1.32, R2.7, R2.10, R2.11, R2.12, R2.13 | CHK-HANDOFF-01, CHK-RETURN-01 | focused/full | each actual Yellow-to-Color edge | concrete directed boundaries and reconstruction evidence |
| AC-MAP | AC-HO-04 | R1.6, R1.25, R2.1, R2.2, R2.3, R2.8, R2.9 | CHK-HANDOFF-01, CHK-JOB-01 | focused/full | repeated/nested/reset/interrupted | transition and cancellation traces |
| AC-MAP | AC-TECH-01 | R4.1, R4.2, R4.3, R4.4, R8.4, R11.2 | CHK-BUILD-01, CHK-ROM-01 | fast/full | variant build and warning failure | ROM IDs, headers, maps, logs |
| AC-MAP | AC-TECH-02 | R3.1, R3.2, R3.4 | CHK-CGB-01 | fast/full | platform/startup/reset | header and startup checkpoints |
| AC-MAP | AC-TECH-03 | R1.7, R12.6 | CHK-INV-01 | fast/full | reachable unreviewed writer | inventory closure report |
| AC-MAP | AC-TECH-04 | R1.3, R1.4, R5.6, R12.6 | CHK-OWN-01, CHK-INV-01 | fast/full | targeted writer mutations | assertion and audit results |
| AC-MAP | AC-TECH-05 | R1.23, R2.11, R5.1, R5.2, R5.3, R5.4 | CHK-COMMIT-01, CHK-PALETTE-01 | fast/full | semantic checkpoint mutation | exact state diff |
| AC-MAP | AC-TECH-06 | R1.2, R1.5, R1.19, R1.20, R2.9, R5.7, R10.2 | CHK-OWN-01, CHK-JOB-01, CHK-REQUEST-01 | fast/full | seeded ownership actions | model/ROM state comparison |
| AC-MAP | AC-TECH-07 | R3.3, R3.5, R3.6, R4.5, R10.1, R10.6 | CHK-BANK-01, CHK-ROM-01 | fast/focused/full | bank and interrupt torture | boundary snapshots |
| AC-MAP | AC-TECH-08 | R5.8, R9.7, R10.4, R10.5, R10.8, R10.9, R10.10, R10.11 | CHK-TIME-01 | focused/full | all timed operations | numeric equations, exact-fit, and defer evidence |
| AC-MAP | AC-TECH-09 | R11.6, R12.6 | CHK-EVIDENCE-01 | fast/full | each implemented or phase-activated critical contract mutation | targeted failure artifacts |
| AC-MAP | AC-TECH-10 | R9.4, R11.1, R11.3, R11.4, R11.5 | CHK-VISUAL-01, CHK-CANARY-01, CHK-OAM-01 | focused/full | checkpoint artifact omissions | complete versioned manifests |
| AC-MAP | AC-STRESS-01 | R1.15, R1.16, R1.21, R1.22, R1.26, R7.3, R9.7, R10.8, R10.9, R10.10 | CHK-STRESS-01 | focused/full | combined renderer pressure | accounting, traces, timing, visuals |
| AC-MAP | AC-STRESS-02 | R2.6, R2.7, R2.8, R2.10, R2.11, R2.12, R2.13 | CHK-STRESS-02 | focused/full | bidirectional/reset handoff | poison/rebuild/barrier/five-frame evidence |
| AC-MAP | AC-STRESS-03 | R2.2, R7.1, R7.3, R7.4, R10.4, R10.10 | CHK-STRESS-03 | focused/full | interrupted connection | atomic snapshots, defer, timing |
| AC-MAP | AC-REMOVE-01 | R12.4, R12.5, R12.7 | CHK-REMOVE-01, CHK-REGRESS-01 | full | obsolete ownership or missing required Yellow path | reachability and regression evidence |
| AC-MAP | AC-REMOVE-02 | R2.13, R6.12, R7.2, R12.3 | CHK-REMOVE-01 | full | captured-screen/restoration path | negative source/ROM reachability |
| AC-MAP | AC-REMOVE-03 | R12.4, R12.5 | CHK-REMOVE-01, CHK-REGRESS-01 | full | unjustified transitional adapter | disposition and regression report |
| AC-MAP | AC-REMOVE-04 | R12.1, R12.3, R12.5 | CHK-REGRESS-01 | focused/full | removed required Yellow path | excluded-scene regressions |
| AC-MAP | AC-DONE-01 | R1.1, R1.30, R1.31, R1.32, R2.6, R2.7, R2.8, R7.1, R10.11, R11.6, R12.1, R12.4, R12.6 | CHK-TRACE-01, CHK-SELECT-01, CHK-PROD-01, CHK-HANDOFF-01, CHK-TRANSFER-01, CHK-TIME-01, CHK-REMOVE-01, CHK-REGRESS-01 | full | incomplete bounded aggregate completion | all mapped reports and artifacts green |

## Numeric timing operation matrix

Future execution creates one complete numeric row for every row below before
that operation becomes production-reachable. Each row records every exact
instruction path and its expanded cycle equation, operation, mode, ROM,
tool/device, samples, worst cycles, instrumentation cycles, numeric budget or
deadline, start, guard, margin cycles, margin percent, exact defer threshold,
equation result, insufficient-budget injection at every
pre-visible preparation/revalidation boundary, and the threshold-plus-one
whole-unit defer artifact. For a visible destination it also records
worst-case reservation and uninterrupted completion after `COMMITTING`.
Arbitrary mid-operation interruption appears only for inactive destinations or
LCD-off cases. Repeated measurements retain phase and ROM identity. A row with
a placeholder equation, budget, or deadline grants no activation credit.

| Timing row key | Independently timed operation | Required equation and numeric limit | Contract | Required boundary evidence |
|---|---|---|---|---|
| TIME-LCD-OVERRIDE-OFF | LCD interrupt with scanline overrides disabled | exact instruction-path sum ≤ measured numeric interrupt deadline | R10.1, R10.8–R10.10 | exact-fit; threshold+1 whole-operation defer |
| TIME-LCD-OVERRIDE-ON | LCD interrupt with scanline overrides enabled | exact instruction-path sum ≤ measured numeric interrupt deadline | R10.1, R10.8–R10.10 | exact-fit; threshold+1 whole-operation defer |
| TIME-VBLANK-YELLOW | complete Yellow VBlank owner route | dispatch + every executed writer path ≤ numeric VBlank deadline | R10.2, R10.8–R10.11 | one-route trace; exact-fit; threshold+1 defer |
| TIME-VBLANK-OVERWORLD | complete Color VBlank owner route | dispatch + every executed writer path ≤ numeric VBlank deadline | R10.2, R10.8–R10.11 | one-route trace; exact-fit; threshold+1 defer |
| TIME-SELECTOR | policy recomputation before destination writer | exact resolver path ≤ numeric pre-first-writer budget | R1.32, R10.11 | exact-fit; threshold+1 defer |
| TIME-HANDOFF-TO-YELLOW | Color departure, cancellation, generation, Yellow selection | exact transition-control paths ≤ numeric hidden/display deadline | R2.1–R2.6, R10.11 | ordered trace; exact-fit; threshold+1 defer |
| TIME-HANDOFF-TO-COLOR | Yellow departure, cancellation, generation, Color selection | exact transition-control paths ≤ numeric hidden/display deadline | R2.1–R2.4, R2.7, R10.11 | ordered trace; exact-fit; threshold+1 defer |
| TIME-RESET-TO-YELLOW | hard reset from Color through Yellow selection | exact reset path ≤ numeric hidden/display deadline | R2.8, R10.11 | hidden/ordinary proof; exact-fit; threshold+1 defer |
| TIME-SOFT-RESET-TO-YELLOW | soft reset from Color through normal-boot re-entry | exact soft-reset path ≤ numeric hidden/display deadline | R2.8, R10.11 | normal-boot trace; exact-fit; threshold+1 defer |
| TIME-RECONSTRUCT-YELLOW | fresh complete Yellow reconstruction and barrier | sum of every R2.11 Yellow item path ≤ numeric hidden/display deadline | R2.6, R2.10–R2.12, R10.11 | poison/full ledger/one barrier; exact-fit; threshold+1 defer |
| TIME-RECONSTRUCT-COLOR | fresh complete Color reconstruction and barrier | sum of every R2.11 Color item path ≤ numeric hidden/display deadline | R2.7, R2.10–R2.12, R10.11 | poison/full ledger/one barrier; exact-fit; threshold+1 defer |
| TIME-PALETTE-BG | complete 64-byte BG palette upload | setup + 64-byte exact upload path ≤ numeric VBlank budget | R5.8, R10.4, R10.8–R10.11 | old/new payload; exact-fit; threshold+1 defer |
| TIME-PALETTE-OBJ | complete 64-byte OBJ palette upload | setup + 64-byte exact upload path ≤ numeric VBlank budget | R5.8, R10.4, R10.8–R10.11 | old/new payload; exact-fit; threshold+1 defer |
| TIME-PALETTE-COMBINED | serialized complete BG then OBJ uploads | exact BG + serialization + exact OBJ paths ≤ numeric VBlank budget | R5.8, R10.4–R10.5, R10.8–R10.11 | payload ordering; exact-fit; threshold+1 defer |
| TIME-TRANSFER-LOAD | eligible-map paired initial load | exact bank-0 + switch + bank-1 path ≤ numeric hidden/display deadline | R7.1, R7.3–R7.4, R10.11 | complete pairs; exact-fit; threshold+1 defer |
| TIME-TRANSFER-RELOAD | eligible-map paired reload | exact bank-0 + switch + bank-1 path ≤ numeric hidden/display deadline | R7.1, R7.3–R7.4, R10.11 | complete pairs; exact-fit; threshold+1 defer |
| TIME-STREAM-HORIZONTAL | paired horizontal streaming transfer | exact bank-0 + switch + bank-1 path ≤ numeric VBlank budget | R7.1, R7.3–R7.4, R10.4–R10.5, R10.8–R10.11 | old/new pairs; exact-fit; threshold+1 defer |
| TIME-STREAM-VERTICAL | paired vertical streaming transfer | exact bank-0 + switch + bank-1 path ≤ numeric VBlank budget | R7.1, R7.3–R7.4, R10.4–R10.5, R10.8–R10.11 | old/new pairs; exact-fit; threshold+1 defer |
| TIME-STREAM-CONNECTION | paired Pallet/Route 1 connection transfer per direction | exact direction-specific bank-0 + switch + bank-1 path ≤ numeric deadline | R7.1, R7.3–R7.4, R10.4–R10.5, R10.8–R10.11 | each direction; exact-fit; threshold+1 defer |
| TIME-TRANSFER-ROW | explicit paired row transfer | exact bank-0 + switch + bank-1 path ≤ numeric VBlank budget | R7.1, R7.3–R7.4, R10.11 | exact-fit; threshold+1 defer |
| TIME-TRANSFER-COLUMN | explicit paired column transfer | exact bank-0 + switch + bank-1 path ≤ numeric VBlank budget | R7.1, R7.3–R7.4, R10.11 | exact-fit; threshold+1 defer |
| TIME-TRANSFER-RECTANGLE | paired rectangle transfer | exact bank-0 + switch + bank-1 path ≤ numeric natural deadline | R7.1, R7.3–R7.4, R10.11 | exact-fit; threshold+1 defer |
| TIME-TRANSFER-THIRD-SCREEN | paired third-screen transfer | exact bank-0 + switch + bank-1 path ≤ numeric natural deadline | R7.1, R7.3–R7.4, R10.4, R10.8–R10.11 | exact-fit; threshold+1 defer |
| TIME-TRANSFER-ALTERNATE-BG | paired alternate-BG destination transfer | exact bank-0 + switch + bank-1 path ≤ numeric natural deadline | R7.1, R7.3–R7.4, R10.11 | destination trace; exact-fit; threshold+1 defer |
| TIME-ANIMATED-TILE | one Color animated-tile dependency and paired commit | dependency preparation + exact bank-0/bank-1 commit path ≤ numeric budget | R7.1, R7.3–R7.4, R10.11 | dependency ledger; exact-fit; threshold+1 defer |
| TIME-FIELD-REPLACEMENT | one Color field-replacement dependency and paired commit | dependency preparation + exact bank-0/bank-1 commit path ≤ numeric budget | R7.1, R7.3–R7.4, R10.11 | dependency ledger; exact-fit; threshold+1 defer |
| TIME-OAM-SHADOW-BUILD | maximum visible-object shadow-OAM construction | exact maximum-object instruction paths ≤ numeric frame budget | R9.7–R9.9, R10.11 | complete shadow image; exact-fit; threshold+1 defer |
| TIME-OAM-DMA | one complete shadow-to-hardware OAM DMA | setup + launch + wait exact path ≤ numeric DMA/VBlank deadline | R9.7–R9.8, R10.11 | complete hardware image; exact-fit; threshold+1 defer |

## Directed scene and reconstruction matrix

Each implementation phase expands this matrix for the lifecycles and directed
transitions it touches, then reruns source plus built-ROM slice closure before
the changed path becomes reachable. A lifecycle row is never expanded into assumed map entry and
return edges. Grouping aliases is forbidden unless the reviewed inventory
proves identical control flow and names every alias. A representative
fast-tier sample cannot close a full-tier row.

| Directed coverage | Required concrete inventory join | Destination evidence | Reconstruction evidence | Check |
|---|---|---|---|---|
| hard boot, reset, soft reset, new-game, and continue into Yellow lifecycles | one `STANDALONE` row plus each concrete Yellow-owned edge | Yellow selected and completely reconstructed before presentation | reset/soft reset from Color includes hidden-display/admission proof, complete fresh Yellow ledger, exactly one barrier, timing evidence, and soft-reset normal-boot re-entry | CHK-HANDOFF-01, CHK-STRESS-02, CHK-TIME-01, CHK-REGRESS-01 |
| overlay, dialogue, menus, battle, status, Pokédex, town map, trainer card, naming, PC, evolution, Hall of Fame, trade, slots, printer, link, Pikachu pictures, Beach, and Surfing Pikachu lifecycles | one row per reachable lifecycle | Yellow owns initialization and display; `OVERWORLD_OVERLAY` unreachable | Color departure completes Yellow reconstruction and barrier | CHK-HANDOFF-01, CHK-PROD-01, CHK-REGRESS-01 |
| Yellow-to-Yellow nesting, return, failure, disconnect, and error recovery | one concrete directed Yellow-owned `SC-…` row per edge | Yellow remains selected; no generation handoff | none | CHK-HANDOFF-01, CHK-REGRESS-01 |
| each effective Color-to-Yellow edge | one concrete directional `SCENE_BOUNDARY` row | Yellow selected before destination initialization entry | poison, complete fresh Yellow reconstruction, one barrier | CHK-HANDOFF-01, CHK-STRESS-02 |
| each effective Yellow-to-Color eligible-map edge | one concrete directional `SCENE_BOUNDARY` row joined to its actual source lifecycle | Color selected before reconstruction | poison, every reconstruction item, one barrier, five active frames | CHK-HANDOFF-01, CHK-RETURN-01 |
| Pallet↔Route 1 while preference is Color, and all Yellow-to-Yellow edges | one reviewed concrete row | owner and generation unchanged | no synthetic handoff, generation, reconstruction, or barrier | CHK-SELECT-02, CHK-HANDOFF-01 |
| every lifecycle or directed edge activated by an implementation phase | one reviewed concrete row plus renewed source/ROM slice closure | evidence follows the effective owner transition | reconstruction for every real owner change in either direction | CHK-INV-01, CHK-HANDOFF-01, CHK-RETURN-01 |

Every actual Yellow-to-Color row records its actual Yellow-owned source
lifecycle and poisons prior bank-0 tilemaps, bank-1 attributes, BG and OBJ
palette RAM, shadow and hardware OAM, buffers, flags, and jobs while Yellow
owns that lifecycle. Evidence records a preceding map-to-Yellow edge and its
last map generation only when source plus built-ROM evidence proves that
predecessor; initial new-game, continue, reset, and other Yellow-owned entry
lifecycles never invent a departure. Evidence then records
map/tileset/override identity; viewport, scroll, window, and destination;
required tiles, animation, and replacements; every presentable bank-0 tilemap
and freshly generated bank-1 attribute; base, transformed, and hardware
palettes; player, follower, and object shadow OAM; current-generation
scheduler state; restored banks, stack, and interrupts; the single
presentation barrier; and five consecutive `OVERWORLD_ACTIVE` frames.

## Exhaustive production policy matrix

`CHK-SELECT-01` expands the complete Cartesian product `{COLOR, YELLOW}` ×
`{ordinary map presentation, overlay, dialogue, menu, battle, standalone,
boot/reset}` × `{each of 34 supported OVERWORLD maps, each of 162 supported
interior maps, unsupported map}`. Only cells combining `COLOR` with ordinary presentation of
one of those 196 supported maps select `RENDERER_FULL_COLOR_OVERWORLD`; every
other cell selects `RENDERER_YELLOW`. Each row asserts one and only one owner.
Executing and retaining this expanded harness matrix is deferred and is not
claimed by the current slice. `CHK-SELECT-02` additionally proves
that preference writes touch no video, renderer, generation, queue, palette,
VRAM, OAM, or hardware state and that policy is recomputed before the first
destination owner-gated writer.

## Overlay precedence matrix

This matrix remains conformance evidence for the quarantined/audit oracle; it
does not make a production Color overlay reachable. Production overlay,
dialogue, and menu scenes are instead covered as Yellow baseline plus complete
Color-to-Yellow and optional Yellow-to-Color return evidence by
`CHK-PROD-01`, `CHK-HANDOFF-01`, and `CHK-REGRESS-01`.

Expected values are derived only from the request's authoritative destination
BG/window selector, map identity, tileset identity, rectangle,
world-coordinate origin/transform, complete override set, classification,
desired tile ID, and explicit attribute or text/window default. The harness
clips the selected destination while retaining source-to-destination tilemap
and source-to-world mappings. Revealed terrain uses the supplied
world-coordinate override or supplied tileset lookup. Reading either VRAM bank
or ambient active-map state to derive classification, coordinate, tile
identity, or an expected attribute fails `CHK-OVERLAY-01`.

| Case key | Destination/clipping | Classification and source | Meaningful byte coverage | Required evidence |
|---|---|---|---|---|
| OVERLAY-ORDINARY-OPAQUE-EXPLICIT | ordinary/unclipped | `OPAQUE_OVERLAY`, explicit full byte | palette 0–2, bank 3, flips 5–6, priority 7, bit 4 forced zero | request, coordinate map, expected/actual bytes |
| OVERLAY-ORDINARY-OPAQUE-DEFAULT | ordinary/unclipped | `OPAQUE_OVERLAY`, text/window default | default full byte and bit 4 forced zero | request, default key, expected/actual bytes |
| OVERLAY-ORDINARY-REVEALED-LOOKUP | ordinary/unclipped | `REVEALED_TERRAIN`, desired tile lookup | palette 0–2, bank 3, flips 5–6, priority 7, bit 4 forced zero | tile ID, lookup entry, expected/actual bytes |
| OVERLAY-ORDINARY-REVEALED-OVERRIDE | ordinary/unclipped | `REVEALED_TERRAIN`, coordinate override | override precedence and bit 4 forced zero | source/destination coordinate, override, bytes |
| OVERLAY-FULLY-CLIPPED | declared BG destination and Pallet Town/Overworld identity; empty after clipping | alternating opaque/revealed cells exercising explicit/default/override/lookup | no surviving commit cell; every source branch structurally proven | clipped coordinate map, precedence proof, and zero-entry trace with canonical non-writing `WR-NONE` allowlist |
| OVERLAY-PARTIALLY-CLIPPED | declared destination per edge and Pallet Town/Overworld identity; clipped on each destination edge | alternating opaque/revealed cells exercising explicit/default/override/lookup | preserved source/destination/world mappings and every meaningful bit | pre/post clip tilemap/world map, precedence proof, and byte diffs |
| OVERLAY-MAP-EDGE | map edge | mixed explicit/default/lookup/override cells | every meaningful bit and canonical bit 4 | concrete mutation/writer IDs and byte diffs |
| OVERLAY-CONNECTION | Route 1 northwest `(0,0)` connection destination with canonical Overworld tileset | mixed explicit/default/lookup/override cells | every meaningful bit and canonical bit 4 | concrete mutation/writer IDs and byte diffs |
| OVERLAY-WINDOW | fully in-bounds Pallet Town/Overworld request to window map 9C00 | opaque and revealed cells | text/window default and terrain precedence; nonempty writer and complete commit | concrete mutation/writer/commit IDs and byte diffs |
| OVERLAY-ALTERNATE-BG | fully in-bounds Pallet Town/Overworld request to BG map 9C00 | opaque and revealed cells | destination pairing and every meaningful bit; nonempty writer and complete commit | concrete mutation/writer/commit IDs and byte diffs |
| OVERLAY-ALTERNATE-MAP | fully in-bounds Viridian City/Overworld request to BG map 9800 | opaque and revealed cells | supplied canonical destination, map/tileset identity, world transform, overrides, and lookup independent of ambient map; nonempty writer and complete commit | complete request, concrete mutation/writer/commit IDs, coordinate maps, and byte diffs |

## OAM fallback and lifecycle matrix

Palette mapping runs after final tile and Pikachu-offset selection and may
replace bits 0–2 only. Every case preserves bits 3–7. Diagnostic fallback
evidence is mandatory for invalid identities; release builds exclude
debug-only recording without changing the deterministic palette-0 result.

| Case key | Final picture identity | Expected palette | Required diagnostic evidence | Check |
|---|---|---|---|---|
| OAM-FALLBACK-MISSING | absent identity | OBJ palette 0 | fallback kind, object, final tile, generation, writer ID | CHK-OAM-01 |
| OAM-FALLBACK-RANGE | out-of-range identity | OBJ palette 0 | fallback kind, numeric identity, object, generation, writer ID | CHK-OAM-01 |
| OAM-FALLBACK-UNMAPPED | in-range unmapped identity | OBJ palette 0 | fallback kind, numeric identity, object, generation, writer ID | CHK-OAM-01 |
| OAM-MAPPED-OBJECTS | every mapped final identity | deliberate mapped OBJ palette | mapping key and concrete shadow/hardware writer IDs | CHK-OAM-02 |
| OAM-DMA-COMPLETE | maximum declared shadow batch | mapped and fallback results retained | shadow batch ID, DMA source/launch/wait IDs, complete hardware image | CHK-OAM-02, CHK-COMMIT-01 |

## Inventory-keyed implementation matrices

Phase 0 supplies the initial map-entry rows. Each implementation phase declares
and closes the rows for the paths it touches before those changes become
reachable. Each full-tier matrix is generated from the union of closed slices,
never by substituting a representative category:

- every concrete Color-owned `MU-…` row for Pallet Town/Route 1 load, reload, return, reconstruction,
  horizontal and vertical scrolling, four connection directions,
  third-screen, row, column, rectangle, alternate destination,
  animation, field replacement, moving BG, LCD-off load, palette dependency,
  and OAM participation is exercised by `CHK-TRANSFER-01`,
  `CHK-COMMIT-01`, or `CHK-OAM-02` as its declared resources require;
- every concrete `WR-…` row reached by those mutations is asserted against its
  owner, phase, generation, destination, commit unit, and bank permissions by
  `CHK-OWN-01`, `CHK-BANK-01`, and `CHK-INV-01`; and
- every concrete `SC-…` lifecycle and directed transition row is exercised on
  boot, normal, abnormal, Yellow-to-Yellow nested/error, reset, and failure
  exits by `CHK-HANDOFF-01` and `CHK-REGRESS-01`; `CHK-RETURN-01` joins only
  actual Yellow-to-Color eligible-map boundary rows.

The bounded production content matrix is specified for all 34 supported
`OVERWORLD` maps and the 162 maps using the 19 admitted interior tilesets,
including first entry, each actual Yellow-to-Color return, both scroll axes,
connections where present, and reload. Dialogue and menus remain Yellow
baseline cases with complete departure/return evidence. Execution of this
expanded runtime harness matrix is deferred and is not claimed by the current
slice. The separately reviewed all-25 content corpus is complete; that content
result does not activate excluded maps.

The full OAM matrix covers player walking, running, biking, surfing, fishing,
and ledge states; follower Pikachu in every direction and animation state;
maximum visible NPC population; static NPCs and item balls; cut tree and
boulder movement; dust/smoke; healing machine; emotion bubbles; and objects
under grass/priority tiles. Evidence includes shadow OAM, hardware OAM, OBJ
palettes, and multi-frame images.

## Completion report

The final implementation PR reports all concrete mapped IDs and includes:

- reproducible release, debug, and VC builds plus CGB-only header evidence;
- closed hardware-writer, scene, and mutation inventories;
- bank-stress and ownership-model results;
- complete named numeric cycle equations, exact-fit cases, and threshold-plus-one results for every selector-activated operation;
- architecture stress results;
- the exhaustive preference × lifecycle × map owner matrix, exact Pallet/Route 1 Color scope, forced-Yellow baseline coverage, complete bidirectional/reset handoffs, and Color-owned animation/field-replacement units;
- LLM-reviewed screenshots, frame strips, and contact sheets linked to
  semantic snapshots and traces;
- emulator and hardware/tool versions; and
- physical CGB tests not performed.

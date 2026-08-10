# Acceptance criteria

This file is the sole authority for observable completion outcomes; mandatory
behavior and vocabulary remain defined in [requirements.md](requirements.md).

## Cross-cutting contract outcomes

- **AC-OWN-01:** Hostile writer traces contain no owner, phase, generation, effective-owner, wrapper-dispatch, or routed-VBlank violation; each frame chooses once and runs exactly one owner route. Direct requirements: R1.1, R1.2, R1.3, R1.4, R1.5, R1.33, R5.7, R10.2.
- **AC-SELECT-01:** The exhaustive preference × lifecycle × map matrix returns Color only for `COLOR` plus ordinary presentation of an admitted outdoor or conventional-interior map, and returns Yellow for every other cell, with exactly one effective owner per cell. Direct requirements: R1.29, R1.30, R1.31, R12.1, R12.7.
- **AC-SELECT-02:** Preference changes have no direct video or ownership writes; recomputation before the first destination write preserves owner and generation for same-owner decisions and performs exactly one generation-advancing complete handoff for real owner changes. Direct requirements: R1.29, R1.32, R2.1, R2.2, R2.3, R2.4.
- **AC-PROD-01:** Normal, debug, and VC products allow Color only for ordinary presentation of the supported outdoor and conventional-interior map slice; overlays, dialogue, menus, battles, standalone scenes, unsupported maps, boot/reset, and `YELLOW` preference remain Yellow-owned, and `OVERWORLD_OVERLAY` is unreachable. Direct requirements: R1.30, R1.31, R6.13, R12.1, R12.5.
- **AC-REQUEST-01:** Runtime pressure tests exercise exactly the measured policy selected when each request class is implemented; required visible-state work that cannot coalesce defers and retries, final capacity rejection occurs only for optional or supersedable work with a proven fallback, and schema/reference-model tests cover every result branch without losing admitted work. Direct requirements: R1.8, R1.9, R1.10, R1.11, R1.12, R1.13, R1.14, R1.15, R1.16, R1.18, R1.26, R1.28.
- **AC-JOB-01:** Handoff, reset, supersession, stale-generation, and adversarial sequences prove that older jobs cancel with the required reason and never write. Direct requirements: R1.6, R1.19, R1.20, R1.24, R1.27, R2.1, R2.2, R2.3, R2.8, R2.9.
- **AC-COMMIT-01:** Forced insufficient budget at every pre-visible preparation and revalidation boundary defers before `COMMITTING`; after a visible-destination job reserves its measured worst-case completion budget and enters `COMMITTING`, it completes without arbitrary interruption, and every presented boundary exposes only the complete old or new unit. Direct requirements: R1.17, R1.21, R1.22, R1.23, R1.25, R1.28, R7.3, R7.4, R10.4, R10.10.
- **AC-RETURN-01:** Every concrete Yellow-to-Color eligible-map boundary poisons prior screen resources, rebuilds every reconstruction item from authoritative state, crosses one presentation barrier, and only then presents the map; same-owner edges preserve generation and perform no synthetic reconstruction. Direct requirements: R1.32, R2.7, R2.10, R2.11, R2.12, R2.13.
- **AC-OVERLAY-01:** Requests carrying authoritative BG/window destination, map and tileset identity, world transform, override set, classifications, tile IDs, and attributes preserve source-to-destination and source-to-world mapping through clipping; ordinary, fully clipped, partially clipped, edge, connection, alternate-BG, and alternate-map cases match the full-byte oracle without VRAM or ambient-map input. Direct requirements: R6.4, R6.5, R6.6, R6.7, R6.8, R6.9, R6.10, R6.11.
- **AC-OAM-01:** Missing, out-of-range, and unmapped picture identities select OBJ palette 0, diagnostic builds record debug evidence, and OAM bits 3–7 remain unchanged. Direct requirements: R9.1, R9.2, R9.3, R9.4.
- **AC-TIME-01:** Every activated renderer and selector/handoff timing row is named, numeric, and passes its cycle equation against its natural budget or deadline; exact-fit commits, threshold-plus-one defers before `COMMITTING`, and `$ffff` is never a production budget. Direct requirements: R9.7, R10.3, R10.4, R10.7, R10.8, R10.9, R10.10, R10.11.
- **AC-INV-01:** Baseline source plus built-ROM discovery closes the reviewed initial map-entry slice, and each implementation slice closes every writer, scene, boundary, and mutation row it touches before the changed path becomes reachable. Direct requirements: R1.7, R12.6, R12.8.
- **AC-TRACE-01:** Every requirement maps to at least one named check, every named check maps to at least one requirement, and the definition-derived acceptance requirement sets equal their AC-MAP cells. Direct requirements: R11.4, R12.6.

## Evidence prerequisite

- **AC-EVIDENCE-01:** The [verification contracts](verification-contracts.md) pass deterministic environment, observability, semantic snapshots, ownership-model, bank-contract, reviewed baseline inventory, visual-pipeline, mutation, command-surface, and hosted-CI checks. Two independent evidence captures from the same debug ROM MUST have byte-identical semantic, traceability, and versioned-manifest outputs; no renderer request, commit, return, overlay, OAM, representation, or operation-timing acceptance is claimed. Direct requirements: R1.7, R3.4, R3.5, R3.6, R11.3, R11.4, R11.5, R11.6, R12.6, R12.8.

## Overworld

- **AC-OW-01:** Complete and non-gating for the bounded release: all 25 tilesets use independently authored and Yellow-validated palette/attribute content with expected full-byte assignments and build-time table integrity. This content result does not activate excluded maps in the runtime presentation predicate. Direct requirements: R5.1, R6.1, R6.2, R6.3, R8.1, R8.2, R8.3, R8.4.
- **AC-OW-02:** Initial entry, reload, horizontal and vertical scrolling, and all four connections preserve paired color state at every visible boundary. Direct requirements: R2.5, R7.1, R7.3, R10.5.
- **AC-OW-03:** Dialogue, text boxes, and transient map overlays remain Yellow-owned and baseline-equivalent, return to eligible Color presentation only through a complete handoff, and never make `OVERWORLD_OVERLAY` reachable. Direct requirements: R2.6, R6.13, R7.1, R12.1.
- **AC-OW-04:** Roofs, world-coordinate overrides, animated tiles, and field replacements produce their declared tiles, attributes, and tile-data dependencies. Direct requirements: R6.9, R7.1, R8.5, R8.6.
- **AC-OW-05:** Player, follower Pikachu, NPCs, and every mapped object use deliberate final-picture-identity OBJ palette mapping through a complete shadow-to-hardware OAM operation. Direct requirements: R5.2, R9.1, R9.2, R9.5, R9.6, R9.8, R9.9.
- **AC-OW-06:** No tested overworld sequence presents a stale, white, black, partially committed, tile/attribute-mismatched, or visibly wobbling frame. Direct requirements: R5.3, R5.4, R5.5, R7.3, R9.7.

## Handoffs

- **AC-HO-01:** Every Color-to-Yellow boundary closes admission, resolves departing work, advances generation once, selects and completely reconstructs Yellow, crosses one barrier, and only then permits the destination's first display write. Direct requirements: R1.32, R2.1, R2.2, R2.3, R2.4, R2.6, R12.2.
- **AC-HO-02:** Every forced-Yellow lifecycle and Yellow-preference case remains functionally equivalent to the baseline apart from the explicit CGB-only product boundary. Direct requirements: R1.30, R6.13, R12.1, R12.5.
- **AC-HO-03:** Every concrete Yellow-to-Color eligible-map boundary performs one generation-advancing handoff and reconstructs from fresh authoritative state; same-owner edges preserve generation and invent no handoff or return work. Direct requirements: R1.32, R2.7, R2.10, R2.11, R2.12, R2.13.
- **AC-HO-04:** Repeated, nested, reset, interrupted, boot, and Yellow-to-Yellow error transitions follow the directed scene graph without leaking ownership or executable work. Direct requirements: R1.6, R1.25, R2.1, R2.2, R2.3, R2.8, R2.9.

## Technical

- **AC-TECH-01:** Release, debug, and VC ROM variants build reproducibly with warnings fatal, valid placement, complete tables, and no debug-only canary leakage. Direct requirements: R4.1, R4.2, R4.3, R4.4, R8.4, R11.2.
- **AC-TECH-02:** Header validation identifies the cartridge as CGB-only, hard boot initializes exactly once, soft reset clears renderer state, and non-CGB startup reaches the rejection path. Direct requirements: R3.1, R3.2, R3.4.
- **AC-TECH-03:** The initial map-entry and every activated implementation-slice hardware-writer inventory close with no in-slice reachable unreviewed writer. Direct requirements: R1.7, R12.6.
- **AC-TECH-04:** Runtime owner and writer assertions remain silent for valid sequences and fire for each targeted ownership or direct-write mutation. Direct requirements: R1.3, R1.4, R5.6, R12.6.
- **AC-TECH-05:** Semantic snapshots match expected completed-resource and reconstruction state at every required checkpoint. Direct requirements: R1.23, R2.11, R5.1, R5.2, R5.3, R5.4.
- **AC-TECH-06:** Seeded ownership-model sequences match request, job, cancellation, generation, phase, owner, wrapper dispatch, and routed-VBlank state. Direct requirements: R1.2, R1.5, R1.19, R1.20, R2.9, R5.7, R10.2.
- **AC-TECH-07:** Forced entry-bank and interrupt tests preserve selected WRAM placement, bank/stack state, MBC5 call behavior, LCD composition, and scheduled-work bank restoration. Direct requirements: R3.3, R3.5, R3.6, R4.5, R10.1, R10.6.
- **AC-TECH-08:** Every activated selector, transition, reset, LCD, VBlank, palette, paired transfer, animation/field replacement, and OAM operation has a named numeric cycle equation, natural deadline, exact-fit completion, and threshold-plus-one whole-unit deferral. Direct requirements: R5.8, R9.7, R10.4, R10.5, R10.8, R10.9, R10.10, R10.11.
- **AC-TECH-09:** Each currently implemented or phase-activated critical contract's mutation test proves that the verification contracts and CI detect its named target failure before the affected behavior expands. Direct requirements: R11.6, R12.6.
- **AC-TECH-10:** Every diagnostic checkpoint produces complete fallback, canary, screenshot, bounded frame-strip, semantic, trace, and LLM-visible evidence. Direct requirements: R9.4, R11.1, R11.3, R11.4, R11.5.

## Architecture expansion gate

- **AC-STRESS-01:** Combined renderer pressure preserves selected per-class request accounting, owner gating, pre-visible deferral, reserved complete commit units, and numeric timing margins. Direct requirements: R1.15, R1.16, R1.21, R1.22, R1.26, R7.3, R9.7, R10.8, R10.9, R10.10.
- **AC-STRESS-02:** Each proven handoff in either direction, including reset and soft reset from Color, reconstructs after every destination resource is poisoned and presents only after exactly one barrier. Direct requirements: R2.6, R2.7, R2.8, R2.10, R2.11, R2.12, R2.13.
- **AC-STRESS-03:** A connection transfer defers at every insufficient pre-visible boundary and, once visibly committing with reserved budget, completes without a mixed tile/attribute frame; arbitrary interruption is limited to inactive or LCD-off work. Direct requirements: R2.2, R7.1, R7.3, R7.4, R10.4, R10.10.

## Removal

- **AC-REMOVE-01:** Obsolete competing ownership and repair paths are unreachable and deleted, while Yellow paths required by preference and forced-Yellow contexts remain reachable and no selectable dual ownership exists. Direct requirements: R12.4, R12.5, R12.7.
- **AC-REMOVE-02:** No failed-hybrid restoration hook, captured-screen restoration path, or donor standalone runtime remains reachable. Direct requirements: R2.13, R6.12, R7.2, R12.3.
- **AC-REMOVE-03:** Every transitional adapter has a reviewed continuing justification tied to retained Yellow behavior or is removed with obsolete overworld ownership. Direct requirements: R12.4, R12.5.
- **AC-REMOVE-04:** Yellow code required by excluded lifecycles remains present, donor excluded runtime stays absent, and regression checks pass. Direct requirements: R12.1, R12.3, R12.5.

## Definition of done

- **AC-DONE-01:** Completion requires an exhaustive exclusive-owner matrix, Color limited to ordinary presentation of the supported map slice, complete bidirectional and reset handoffs, paired Color animation/field-replacement units, numeric timing closure, retained forced-Yellow paths, and enforced inventory/trace closure. Direct requirements: R1.1, R1.30, R1.31, R1.32, R2.6, R2.7, R2.8, R7.1, R10.11, R11.6, R12.1, R12.4, R12.6.

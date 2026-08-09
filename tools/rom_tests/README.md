# ROM tests

Create the ignored repo-local virtual environment and install pinned test
dependencies from the repository root:

```console
make test-full-color-setup
```

Make prefers `.venv/bin/python` locally and falls back to `python3` in managed
environments. Start a focused loop with a concrete pytest path, for example:

```console
.venv/bin/python -m pytest tools/rom_tests/tests/unit/full_color/test_model.py -q
```

Use `make test-full-color-fast` for production-foundation feedback and
`make test-full-color-certify` before handoff. Fast runs product builds,
production linkage, audit evidence, smoke, renderer fixtures, and renderer
runtime ownership. Certification adds the donor contract, complete non-donor
unit tree, repository/bank contracts, two-capture evidence determinism, and the
Core, Renderer, and Journey gameplay suites.

Only runtime observability, traceability, and the visual pipeline are captured
twice and byte-compared. Unit, discovery, inventory, bank, audit, renderer, and
gameplay checks run once. Both profiles retain component stdout, stderr, JUnit
where applicable, and evidence below
`test-results/full-color-harness/attempt-NNNN/`. Set
`FULL_COLOR_OUTPUT=json` for one canonical machine-readable summary.

The focused public commands are:

```console
make test-unit
make test-full-color-donor-contract
make test-full-color-harness-contracts
make test-full-color-evidence
make test-full-color-audit
make test-full-color-renderer-contracts
make test-full-color-renderer-runtime
make test-full-color-smoke
make test-full-color-e2e-core
make test-full-color-e2e-renderer
make test-full-color-e2e-journey
make test-full-color-handoffs
make test-full-color-soak
```

There is no aggregate gameplay alias. Run the affected suite while iterating
and all three independent suites when a change crosses their boundaries.

ROM-consuming commands build their products by default. Hosted CI downloads
the same-revision products from `Build` and passes
`ROM_TEST_PREBUILT_PRODUCTS=1`; private prerequisites fail closed if any
required ROM, map, or symbol file is absent.

The normal, debug, and VC products all contain the saved Color/Yellow toggle
and bounded passive renderer for the supported map slice. Natural tests select
both modes inside one shipped binary. `pokeyellow_phase2_audit.gbc` adds
diagnostic and certification surfaces; it is not a behavioral variant.

Tests are grouped by intent:

```text
tests/
├── unit/            # rules, models, linked-ROM, and callable checks
└── e2e/
    ├── core/        # short product-health journeys
    ├── renderer/    # renderer and visual journeys
    └── journey/     # longer progression and lifecycle journeys
```

Hosted CI discovers the complete unit tree once and runs each E2E directory in
its own `E2E (Core)`, `E2E (Renderer)`, or `E2E (Journey)` job.

## Writing parallel-safe tests

- Request the shared `emulator` fixture instead of sharing a PyBoy instance.
  Each test receives fresh emulator state and an isolated result directory.
- Treat ROMs, symbols, scenarios, fixtures, and snapshots as read-only.
- Set `ROM_TEST_RESULTS` to relocate per-test diagnostics. Cleanup code may
  touch only direct children of that resolved root and must not traverse
  symlinks or recursively remove directories.
- Give each visual assertion a committed snapshot and descriptive name.
- Keep mutable state inside the test or fixture. Do not depend on test order.

See [`docs/TESTING.md`](../../docs/TESTING.md) for evidence semantics, the
verification ladder, hosted coverage, and failure triage.

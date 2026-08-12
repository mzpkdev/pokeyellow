"""Contracts for the public local full-color command surface."""

from collections.abc import Mapping
from pathlib import Path
import json
import os
import re
import shlex
import subprocess
from urllib.parse import unquote

import yaml


ROOT = Path(__file__).parents[5]
PUBLIC_COMMANDS = (
    "test-unit",
    "test-full-color-setup",
    "test-full-color-donor-contract",
    "test-full-color-harness-contracts",
    "test-full-color-evidence",
    "test-full-color-audit",
    "test-full-color-renderer-contracts",
    "test-full-color-renderer-runtime",
    "test-full-color-smoke",
    "test-full-color-e2e-core",
    "test-full-color-e2e-renderer",
    "test-full-color-e2e-journey",
    "test-full-color-fast",
    "test-full-color-certify",
    "test-full-color-handoffs",
    "test-full-color-soak",
)
RETIRED_STAGE = "gate" + "0"
RETIRED_COMMANDS = (
    f"test-full-color-{RETIRED_STAGE}",
    f"test-full-color-{RETIRED_STAGE}-ci-run",
    f"test-full-color-{RETIRED_STAGE}-ci-compare",
    "verify-full-color-phase2-audit",
    "test-full-color-renderer-conformance",
    "test-full-color-e2e",
    "test-full-color-all",
)
ALL_PRODUCTS = (
    "pokeyellow.gbc",
    "pokeyellow.map",
    "pokeyellow.sym",
    "pokeyellow_debug.gbc",
    "pokeyellow_debug.map",
    "pokeyellow_debug.sym",
    "pokeyellow_vc.gbc",
    "pokeyellow_vc.map",
    "pokeyellow_vc.sym",
    "pokeyellow_phase2_audit.gbc",
    "pokeyellow_phase2_audit.map",
    "pokeyellow_phase2_audit.sym",
)
E2E_MODULES = {
    "core": {"test_new_game.py", "test_viridian_city.py"},
    "renderer": {
        "test_full_color_connection_palette.py",
        "test_full_color_house_palette_visual.py",
        "test_full_color_map_background_batches.py",
        "test_full_color_oak_battle_handoff.py",
        "test_full_color_oaks_lab_save_confirmation.py",
        "test_phase5_party_reconstruction.py",
        "test_full_color_start_menu_journey.py",
    },
    "journey": {
        "test_full_color_cold_boot_journey.py",
        "test_parcel_delivery.py",
    },
}
FENCED_CODE = re.compile(
    r"^```[^\n]*\n(?P<body>.*?)^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
INLINE_CODE = re.compile(r"(?<!`)`(?P<body>[^`\n]+)`(?!`)")
MAKE_INVOCATION = re.compile(
    r"^(?:env\s+)?(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"
    r"make\b(?P<arguments>.*)$"
)
MAKE_TARGET = re.compile(r"^[A-Za-z0-9_.%/-]+$")
MAKE_OPTIONS_WITH_VALUE = frozenset(
    ("-C", "--directory", "-f", "--file", "-j", "--jobs")
)
E2E_PATH = re.compile(r"tools/rom_tests/tests/e2e/[A-Za-z0-9_./-]+\.py")
OUTPUT_PATH = re.compile(r"test-results(?:/[A-Za-z0-9_.{}-]+)+/?")
REPOSITORY_PATH = re.compile(
    r"(?<![A-Za-z0-9_.@/-])"
    r"(?P<path>(?:\.github|docs|specs|tools)/[A-Za-z0-9_.@/-]+)"
    r"(?![A-Za-z0-9_.@/*?{}\[\]<>-])"
)
E2E_JOB_NAME = re.compile(r"^E2E \([A-Za-z0-9 _-]+\)$")
TITLE_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*(?:[ ()-]+[A-Za-z0-9]+)*$")
INLINE_LINK = re.compile(r"!?\[[^\]\n]*\]\((?P<destination>[^)\n]+)\)")
REFERENCE_LINK = re.compile(
    r"^\s*\[[^\]\n]+\]:\s*(?P<destination><[^>]+>|\S+)",
    re.MULTILINE,
)
EXTERNAL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _makefile() -> str:
    return (ROOT / "Makefile").read_text(encoding="utf-8")


def _recipe(name: str) -> str:
    match = re.search(
        rf"^{re.escape(name)}(?:\s*:[^\n]*)?\n"
        r"(?P<body>(?:\t[^\n]*\n|\n)*)",
        _makefile(),
        re.MULTILINE,
    )
    assert match is not None, f"Makefile is missing command {name}"
    return match.group("body")


def _dependencies(name: str) -> tuple[str, ...]:
    match = re.search(rf"^{re.escape(name)}:([^\n]*)$", _makefile(), re.MULTILINE)
    assert match is not None
    return tuple(match.group(1).split())


def _run_make(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for name in ("MAKELEVEL", "MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS"):
        environment.pop(name, None)
    return subprocess.run(
        ("make", *arguments),
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _tracked_markdown_paths() -> tuple[Path, ...]:
    completed = subprocess.run(
        ("git", "ls-files", "-z", "--", "*.md"),
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return tuple(
        Path(raw.decode("utf-8")) for raw in completed.stdout.split(b"\0") if raw
    )


def _make_targets(makefile: str) -> frozenset[str]:
    return frozenset(
        match.group("target")
        for match in re.finditer(
            r"^(?P<target>[A-Za-z0-9_.%/-]+)\s*:",
            makefile,
            re.MULTILINE,
        )
    )


def _logical_code_lines(body: str) -> tuple[str, ...]:
    lines: list[str] = []
    pending = ""
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("$ "):
            line = line[2:].lstrip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1].rstrip() + " "
            continue
        lines.append(pending + line)
        pending = ""
    if pending:
        lines.append(pending.rstrip())
    return tuple(lines)


def _markdown_code_fragments(markdown: str) -> tuple[str, ...]:
    fenced = tuple(FENCED_CODE.finditer(markdown))
    outside_fences = FENCED_CODE.sub("", markdown)
    return (
        *(
            line
            for match in fenced
            for line in _logical_code_lines(match.group("body"))
        ),
        *(
            match.group("body").strip()
            for match in INLINE_CODE.finditer(outside_fences)
        ),
    )


def _documented_make_targets(markdown: str) -> tuple[str, ...]:
    targets: list[str] = []
    for fragment in _markdown_code_fragments(markdown):
        for segment in re.split(r"(?:&&|\|\||[;|])", fragment):
            invocation = MAKE_INVOCATION.match(segment.strip())
            if invocation is None:
                continue
            try:
                arguments = shlex.split(
                    invocation.group("arguments"), comments=True, posix=True
                )
            except ValueError:
                arguments = invocation.group("arguments").split()
            skip_next = False
            for argument in arguments:
                if skip_next:
                    skip_next = False
                    continue
                if argument in MAKE_OPTIONS_WITH_VALUE:
                    skip_next = True
                    continue
                if argument.startswith("-") or re.match(
                    r"^[A-Za-z_][A-Za-z0-9_]*=", argument
                ):
                    continue
                if MAKE_TARGET.fullmatch(argument):
                    targets.append(argument)
    return tuple(targets)


def _workflow_job_names() -> frozenset[str]:
    names: set[str] = set()
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        loaded = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        if not isinstance(loaded, dict) or not isinstance(loaded.get("jobs"), dict):
            continue
        for job in loaded["jobs"].values():
            if not isinstance(job, dict) or not isinstance(job.get("name"), str):
                continue
            name = job["name"]
            if "${{" not in name:
                names.add(name)
            elif "${{ matrix.run }}" in name:
                for value in job.get("strategy", {}).get("matrix", {}).get("run", []):
                    names.add(name.replace("${{ matrix.run }}", str(value)))
            elif "${{ matrix.name }}" in name:
                for row in job.get("strategy", {}).get("matrix", {}).get("include", []):
                    if "name" in row:
                        names.add(name.replace("${{ matrix.name }}", row["name"]))
            else:
                names.update(
                    value
                    for value in re.findall(r"'([^']+)'", name)
                    if TITLE_NAME.fullmatch(value)
                )
    return frozenset(names)


def _documented_job_names(markdown: str, known: frozenset[str]) -> tuple[str, ...]:
    names: list[str] = []
    known_initial_words = {name.split(maxsplit=1)[0] for name in known}
    outside_fences = FENCED_CODE.sub("", markdown)
    for match in INLINE_CODE.finditer(outside_fences):
        name = match.group("body").strip()
        nearby = (
            outside_fences[max(0, match.start() - 24) : match.start()]
            + outside_fences[match.end() : match.end() + 32]
        )
        has_job_context = re.search(
            r"\b(job|jobs|check|checks|context|result|status)\b",
            nearby,
            re.IGNORECASE,
        )
        if (
            name in known
            or E2E_JOB_NAME.fullmatch(name)
            or (
                has_job_context
                and TITLE_NAME.fullmatch(name)
                and name.split(maxsplit=1)[0] in known_initial_words
            )
        ):
            names.append(name)
    return tuple(names)


def _known_output_roots() -> frozenset[str]:
    authorities = [_makefile()]
    authorities.extend(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / ".github/workflows").glob("*.yml"))
    )
    return frozenset(
        match.group(0).rstrip("/")
        for authority in authorities
        for match in re.finditer(r"test-results/[a-z0-9][a-z0-9_-]*", authority)
    )


def _documented_repository_paths(markdown: str) -> tuple[str, ...]:
    return tuple(
        match.group("path").rstrip(".,;:")
        for fragment in _markdown_code_fragments(markdown)
        for match in REPOSITORY_PATH.finditer(fragment)
        if "..." not in match.group("path")
        and match.group("path") != "tools/run_ci.py"
        and not match.group("path").startswith("tools/rom_tests/tests/e2e/")
    )


def _link_destination(raw: str) -> str:
    stripped = raw.strip()
    if not stripped:
        return ""
    if stripped.startswith("<"):
        closing = stripped.find(">")
        return stripped[1:closing] if closing >= 0 else stripped
    return stripped.split(maxsplit=1)[0]


def _relative_link_destinations(markdown: str) -> tuple[str, ...]:
    destinations = (
        *(match.group("destination") for match in INLINE_LINK.finditer(markdown)),
        *(match.group("destination") for match in REFERENCE_LINK.finditer(markdown)),
    )
    relative: list[str] = []
    for raw in destinations:
        destination = _link_destination(raw)
        if (
            not destination
            or destination.startswith(("#", "/"))
            or EXTERNAL_SCHEME.match(destination)
        ):
            continue
        path = re.split(r"[?#]", destination, maxsplit=1)[0]
        if path:
            relative.append(unquote(path))
    return tuple(relative)


def _documentation_contract_findings(
    documents: Mapping[Path, str],
    *,
    makefile: str | None = None,
) -> tuple[str, ...]:
    targets = _make_targets(_makefile() if makefile is None else makefile)
    job_names = _workflow_job_names()
    output_roots = _known_output_roots()
    root = ROOT.resolve()
    findings: list[str] = []
    for source, markdown in documents.items():
        location = source.as_posix()
        if "tools/run_ci.py" in markdown:
            findings.append(f"{location}: retired tools/run_ci.py reference")
        for command in RETIRED_COMMANDS:
            if re.search(
                rf"(?<![a-z0-9_-]){re.escape(command)}(?![a-z0-9_-])",
                markdown,
            ):
                findings.append(f"{location}: retired command {command}")
        for target in _documented_make_targets(markdown):
            if target not in targets:
                findings.append(f"{location}: missing Make target {target}")
        for name in _documented_job_names(markdown, job_names):
            if name not in job_names:
                findings.append(f"{location}: missing CI job name {name}")
        for raw_path in E2E_PATH.findall(markdown):
            if not (ROOT / raw_path).is_file():
                findings.append(f"{location}: missing E2E path {raw_path}")
        for raw_path in _documented_repository_paths(markdown):
            root_candidate = ROOT / raw_path
            source_candidate = ROOT / source.parent / raw_path
            if not root_candidate.exists() and not source_candidate.exists():
                findings.append(f"{location}: missing repository path {raw_path}")
        for raw_path in OUTPUT_PATH.findall(markdown):
            if "..." in raw_path:
                continue
            parts = raw_path.rstrip("/").split("/")
            output_root = "/".join(parts[:2])
            if output_root not in output_roots:
                findings.append(f"{location}: unknown output root {output_root}/")
        for destination in _relative_link_destinations(markdown):
            resolved = (ROOT / source.parent / destination).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                findings.append(f"{location}: link leaves repository {destination}")
            else:
                if not resolved.exists():
                    findings.append(
                        f"{location}: missing link destination {destination}"
                    )
    return tuple(sorted(findings))


def test_public_commands_are_concrete_and_phony() -> None:
    makefile = _makefile()
    phony = re.search(
        r"^\.PHONY:\s*\\\n(?P<body>(?:\t[^\n]+\n)+)", makefile, re.MULTILINE
    )
    assert phony is not None
    phony_names = set(re.findall(r"[a-z_][a-z0-9_-]+", phony.group("body")))
    for name in PUBLIC_COMMANDS:
        assert re.search(rf"^{re.escape(name)}\s*:", makefile, re.MULTILINE)
        assert name in phony_names


def test_required_commands_delegate_to_their_named_producers() -> None:
    assert "python3 -m venv .venv" in _recipe("test-full-color-setup")
    assert "test_overworld_color_data_donor.py" in _recipe(
        "test-full-color-donor-contract"
    )
    assert "baseline_discovery" in _recipe("test-full-color-harness-contracts")
    assert "baseline_inventory" in _recipe("test-full-color-harness-contracts")
    assert "bank_torture" in _recipe("test-full-color-harness-contracts")
    assert "full_color.evidence_runner" in _recipe("test-full-color-evidence")
    assert "phase2_measurements" in _recipe("test-full-color-audit")
    assert "--verify" in _recipe("test-full-color-audit")
    assert "renderer_conformance_runner" in _recipe(
        "test-full-color-renderer-contracts"
    )
    assert "renderer_runtime_runner" in _recipe("test-full-color-renderer-runtime")
    assert "runtime_observability" in _recipe("test-full-color-smoke")
    assert "tests/e2e/core" in _recipe("test-full-color-e2e-core")
    assert "tests/e2e/renderer" in _recipe("test-full-color-e2e-renderer")
    assert "tests/e2e/journey" in _recipe("test-full-color-e2e-journey")
    assert "test_model.py" in _recipe("test-full-color-handoffs")
    assert "test_model.py" in _recipe("test-full-color-soak")


def test_unit_tree_runs_once_and_excludes_only_the_donor_contract() -> None:
    recipe = _recipe("test-unit")
    assert recipe.count("tools/rom_tests/tests/unit") == 2
    assert (
        "--ignore=tools/rom_tests/tests/unit/full_color/test_overworld_color_data_donor.py"
        in recipe
    )
    assert _dependencies("test-unit") == ("_rom-test-all-products",)


def test_public_commands_use_the_smallest_product_prerequisite() -> None:
    assert _dependencies("test-full-color-harness-contracts") == (
        "_rom-test-debug-products",
    )
    assert _dependencies("test-full-color-evidence") == ("_rom-test-debug-products",)
    assert _dependencies("test-full-color-audit") == ("_rom-test-all-products",)
    assert _dependencies("test-full-color-renderer-contracts") == ()
    assert _dependencies("test-full-color-renderer-runtime") == (
        "_rom-test-debug-products",
    )
    assert _dependencies("test-full-color-smoke") == ("_rom-test-debug-products",)
    for name in (
        "test-full-color-e2e-core",
        "test-full-color-e2e-renderer",
        "test-full-color-e2e-journey",
    ):
        assert _dependencies(name) == ("_rom-test-gameplay-products",)


def test_each_e2e_module_belongs_to_exactly_one_suite() -> None:
    e2e = ROOT / "tools/rom_tests/tests/e2e"
    assert not tuple(e2e.glob("test_*.py"))
    actual = {
        suite: {path.name for path in (e2e / suite).glob("test_*.py")}
        for suite in E2E_MODULES
    }
    assert actual == E2E_MODULES
    all_modules = [name for modules in actual.values() for name in modules]
    assert len(all_modules) == 11
    assert len(all_modules) == len(set(all_modules))


def test_retired_commands_are_not_targets_or_aliases() -> None:
    makefile = _makefile()
    for name in RETIRED_COMMANDS:
        assert re.search(rf"^{re.escape(name)}\s*:", makefile, re.MULTILINE) is None


def test_prebuilt_mode_accepts_all_twelve_products(tmp_path: Path) -> None:
    products = tuple(tmp_path / name for name in ALL_PRODUCTS)
    for path in products:
        path.touch()
    completed = _run_make(
        "_rom-test-all-products",
        "ROM_TEST_PREBUILT_PRODUCTS=1",
        f"ROM_TEST_ALL_PRODUCTS={' '.join(str(path) for path in products)}",
    )
    assert completed.returncode == 0, completed.stderr
    assert "Missing required ROM test artifact" not in completed.stderr


def test_prebuilt_mode_fails_closed_with_the_missing_product(tmp_path: Path) -> None:
    present = tmp_path / "present.gbc"
    missing = tmp_path / "missing.sym"
    present.touch()
    completed = _run_make(
        "_rom-test-all-products",
        "ROM_TEST_PREBUILT_PRODUCTS=1",
        f"ROM_TEST_ALL_PRODUCTS={present} {missing}",
    )
    assert completed.returncode != 0
    assert completed.stderr.count(f"Missing required ROM test artifact: {missing}") == 1


def test_default_mode_builds_products_while_prebuilt_mode_only_checks_them() -> None:
    default = _run_make(
        "-n", "-B", "_rom-test-all-products", "ROM_TEST_PREBUILT_PRODUCTS=0"
    )
    assert default.returncode == 0, default.stderr
    assert "rgbasm" in default.stdout
    prebuilt = _run_make("-n", "_rom-test-all-products", "ROM_TEST_PREBUILT_PRODUCTS=1")
    assert prebuilt.returncode == 0, prebuilt.stderr
    assert "Missing required ROM test artifact" in prebuilt.stdout
    assert "rgbasm" not in prebuilt.stdout


def test_profiles_enter_the_runner_without_make_dependencies() -> None:
    for profile in ("fast", "certify"):
        name = f"test-full-color-{profile}"
        recipe = _recipe(name)
        assert _dependencies(name) == ()
        assert recipe.startswith("\t@$(PYTHON)")
        assert f"--profile {profile}" in recipe
        assert '--results "$(FULL_COLOR_HARNESS_RESULTS)"' in recipe


def test_json_profile_make_entrypoints_emit_only_the_runner_document(
    tmp_path: Path,
) -> None:
    python = tmp_path / "json-python"
    python.write_text(
        "#!/bin/sh\nprintf '%s\\n' '{\"status\":\"probe\"}'\n", encoding="utf-8"
    )
    python.chmod(0o755)
    environment = os.environ.copy()
    for name in ("MAKELEVEL", "MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS"):
        environment.pop(name, None)
    environment["FULL_COLOR_OUTPUT"] = "json"
    for target in ("test-full-color-fast", "test-full-color-certify"):
        completed = subprocess.run(
            (
                "make",
                target,
                f"PYTHON={python}",
                f"FULL_COLOR_HARNESS_RESULTS={tmp_path / 'results with spaces'}",
            ),
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0
        assert json.loads(completed.stdout) == {"status": "probe"}
        assert completed.stderr == ""


def test_measurement_commands_only_write_disposable_proposals() -> None:
    completed = _run_make(
        "-n",
        "-B",
        "measure-full-color-phase2-audit",
        "PYTHON=/proposal-python",
        "FULL_COLOR_PROPOSALS=/tmp/proposal-root",
    )
    assert completed.returncode == 0, completed.stderr
    commands = [
        line
        for line in completed.stdout.splitlines()
        if "tools.rom_tests.full_color" in line
        and any(
            module in line
            for module in (
                "source_transition",
                "audit_evidence_identities",
                "phase2_measurements",
            )
        )
    ]
    assert [line.split(" -m ", 1)[1].split()[0] for line in commands] == [
        "tools.rom_tests.full_color.source_transition",
        "tools.rom_tests.full_color.audit_evidence_identities",
        "tools.rom_tests.full_color.phase2_measurements",
    ]
    assert all("--proposal-output" in line for line in commands)
    assert all("specs/full-colors" not in line for line in commands)


def test_python_prefers_the_repo_virtualenv_and_link_keeps_cgb_banks() -> None:
    makefile = _makefile()
    assert "$(wildcard .venv/bin/python)" in makefile
    assert "RGBLINKFLAGS += -d" not in makefile
    assert "RGBLINKFLAGS += -w" not in makefile


def test_workflow_coupled_local_runner_is_removed() -> None:
    assert not (ROOT / "tools/run_ci.py").exists()


def test_all_tracked_markdown_references_live_repository_contracts() -> None:
    paths = tuple(path for path in _tracked_markdown_paths() if (ROOT / path).is_file())
    assert paths
    documents = {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}
    findings = _documentation_contract_findings(documents)
    assert findings == (), "\n".join(findings)


def test_documentation_contract_rejects_stale_make_target_mutation() -> None:
    source = Path("docs/PROBE.md")
    baseline = {source: "Run `make yellow_debug`.\n"}
    assert _documentation_contract_findings(baseline) == ()
    mutated = {source: baseline[source].replace("yellow_debug", "yellow_debog")}
    assert _documentation_contract_findings(mutated) == (
        "docs/PROBE.md: missing Make target yellow_debog",
    )


def test_documentation_contract_ignores_make_words_in_prose() -> None:
    documents = {
        Path("docs/PROBE.md"): "Changes make the test-unit-stale docs clearer.\n"
    }
    assert _documentation_contract_findings(documents) == ()


def test_documentation_contract_rejects_stale_e2e_path_mutation() -> None:
    source = Path("docs/PROBE.md")
    live_path = "tools/rom_tests/tests/e2e/core/test_new_game.py"
    baseline = {source: f"Exercise `{live_path}`.\n"}
    assert _documentation_contract_findings(baseline) == ()
    stale_path = "tools/rom_tests/tests/e2e/core/test_missing_journey.py"
    mutated = {source: baseline[source].replace(live_path, stale_path)}
    assert _documentation_contract_findings(mutated) == (
        f"docs/PROBE.md: missing E2E path {stale_path}",
    )


def test_documentation_contract_rejects_stale_repository_path_mutation() -> None:
    source = Path("docs/PROBE.md")
    live_path = "tools/rom_tests/README.md"
    baseline = {source: f"Read `{live_path}`.\n"}
    assert _documentation_contract_findings(baseline) == ()
    stale_path = "tools/rom_tests/MISSING.md"
    mutated = {source: baseline[source].replace(live_path, stale_path)}
    assert _documentation_contract_findings(mutated) == (
        f"docs/PROBE.md: missing repository path {stale_path}",
    )


def test_documentation_contract_rejects_stale_link_mutation() -> None:
    source = Path("docs/PROBE.md")
    baseline = {source: "Read the [index](INDEX.md#testing).\n"}
    assert _documentation_contract_findings(baseline) == ()
    mutated = {source: baseline[source].replace("INDEX.md", "MISSING.md")}
    assert _documentation_contract_findings(mutated) == (
        "docs/PROBE.md: missing link destination MISSING.md",
    )


def test_documentation_contract_rejects_stale_ci_job_mutation() -> None:
    source = Path("docs/PROBE.md")
    baseline = {source: "The `E2E (Core)` job runs independently.\n"}
    assert _documentation_contract_findings(baseline) == ()
    mutated = {source: baseline[source].replace("Core", "Bogus")}
    assert _documentation_contract_findings(mutated) == (
        "docs/PROBE.md: missing CI job name E2E (Bogus)",
    )


def test_documentation_contract_rejects_unknown_output_root_mutation() -> None:
    source = Path("docs/PROBE.md")
    baseline = {source: "Evidence lives under `test-results/full-color-evidence/`.\n"}
    assert _documentation_contract_findings(baseline) == ()
    mutated = {
        source: baseline[source].replace("full-color-evidence", "does-not-exist")
    }
    assert _documentation_contract_findings(mutated) == (
        "docs/PROBE.md: unknown output root test-results/does-not-exist/",
    )


def test_documentation_contract_rejects_retired_runner_and_command() -> None:
    source = Path("docs/PROBE.md")
    runner_findings = _documentation_contract_findings(
        {source: "Run `python tools/run_ci.py`.\n"}
    )
    assert runner_findings == ("docs/PROBE.md: retired tools/run_ci.py reference",)

    retired = RETIRED_COMMANDS[0]
    command_findings = _documentation_contract_findings(
        {source: f"Run `make {retired}`.\n"}
    )
    assert f"docs/PROBE.md: retired command {retired}" in command_findings

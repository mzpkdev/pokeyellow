"""Semantic contracts for hosted verification workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest
import yaml

from tools.rom_tests.full_color.evidence_runner import COMPONENTS


ROOT = Path(__file__).parents[5]
WORKFLOWS = {
    "ci": ROOT / ".github/workflows/ci.yml",
    "metadata": ROOT / ".github/workflows/metadata.yml",
    "labels": ROOT / ".github/workflows/pr-labels.yml",
    "release": ROOT / ".github/workflows/release.yml",
}
TEST_PRODUCTS = {
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
}
RELEASE_COPIES = {
    "cp pokeyellow.gbc release/pokeyellow.gbc",
    "cp pokeyellow.map release/pokeyellow.map",
    "cp pokeyellow.sym release/pokeyellow.sym",
    "cp pokeyellow_debug.gbc release/pokeyellow-debug.gbc",
    "cp pokeyellow_debug.map release/pokeyellow-debug.map",
    "cp pokeyellow_debug.sym release/pokeyellow-debug.sym",
    "cp pokeyellow_vc.gbc release/pokeyellow-vc.gbc",
    "cp pokeyellow_vc.map release/pokeyellow-vc.map",
    "cp pokeyellow_vc.sym release/pokeyellow-vc.sym",
}
FULL_COLOR_JOB_NAMES = {
    "donor-contract": "Full-color Verification / Donor Contract",
    "unit-tests": "Unit Tests",
    "harness-contracts": "Repository Inventory & Bank Safety",
    "evidence-capture": "Evidence / Capture ${{ matrix.name }}",
    "evidence-determinism": "Evidence / Determinism",
    "renderer-contracts": "Renderer / Contract Fixtures",
    "renderer-runtime": "Renderer / Runtime Ownership",
    "audit-evidence": "Evidence / Audit",
}
VERIFICATION_JOB_IDS = {
    "build",
    *FULL_COLOR_JOB_NAMES,
    "e2e",
}
GAMEPLAY_MATRIX = [
    {
        "name": "Core",
        "suite": "core",
        "target": "test-full-color-e2e-core",
    },
    {
        "name": "Renderer",
        "suite": "renderer",
        "target": "test-full-color-e2e-renderer",
    },
    {
        "name": "Journey",
        "suite": "journey",
        "target": "test-full-color-e2e-journey",
    },
]


def _load(path: Path) -> dict[str, Any]:
    loaded = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(loaded, dict), f"{path} must contain a YAML mapping"
    return loaded


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matching = [step for step in job["steps"] if step.get("name") == name]
    assert len(matching) == 1, f"expected one {name!r} step"
    return matching[0]


def _artifact_steps(job: dict[str, Any], action: str) -> list[dict[str, Any]]:
    return [step for step in job["steps"] if step.get("uses") == action]


def _script_lines(script: str) -> set[str]:
    return {line.strip() for line in script.splitlines() if line.strip()}


def _all_workflow_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]


def _reopen_script() -> str:
    metadata = _load(WORKFLOWS["metadata"])
    return _step(metadata["jobs"]["lint"], "Require prior merge gate when reopening")[
        "run"
    ]


def _run_merge_gate_script(**overrides: str) -> subprocess.CompletedProcess[str]:
    ci = _load(WORKFLOWS["ci"])
    gate = ci["jobs"]["merge-gate"]
    script = _step(gate, "Require every verification job")["run"]
    env = os.environ.copy()
    env.update({name: "success" for name in gate["steps"][0]["env"]})
    env.update(overrides)
    return subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", script],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def _run_reopen_script(
    tmp_path: Path,
    *,
    pages: list[dict[str, Any]] | None = None,
    raw_output: str | None = None,
    gh_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    assert shutil.which("jq"), "semantic reopen test requires jq"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        """#!/usr/bin/env bash
set -u
expected_url='repos/acme/project/commits/abc123/check-runs?filter=all&per_page=100'
if [ "$#" -ne 4 ] || [ "$1" != api ] || [ "$2" != --paginate ] || \
   [ "$3" != --slurp ] || [ "$4" != "$expected_url" ]; then
  echo 'unexpected gh argv' >&2
  exit 64
fi
if [ "${FAKE_GH_FAILURE:-0}" = 1 ]; then
  echo 'simulated API failure' >&2
  exit 1
fi
printf '%s\n' "${FAKE_GH_OUTPUT:?}"
""",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "REPOSITORY": "acme/project",
            "HEAD_SHA": "abc123",
            "FAKE_GH_FAILURE": "1" if gh_failure else "0",
            "FAKE_GH_OUTPUT": (
                raw_output if raw_output is not None else json.dumps(pages)
            ),
        }
    )
    return subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", _reopen_script()],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_ci_exposes_flat_checks_and_one_stable_merge_gate() -> None:
    ci = _load(WORKFLOWS["ci"])
    release = _load(WORKFLOWS["release"])

    assert ci["name"] == "CI"
    assert ci["on"] == {
        "pull_request": {
            "branches": ["main"],
            "types": ["opened", "synchronize"],
        },
        "push": {"branches": ["main"]},
    }
    assert ci["permissions"] == {"contents": "read"}
    assert set(ci["jobs"]) == VERIFICATION_JOB_IDS | {"merge-gate"}
    assert {job_id: ci["jobs"][job_id]["name"] for job_id in FULL_COLOR_JOB_NAMES} == (
        FULL_COLOR_JOB_NAMES
    )
    assert ci["jobs"]["build"]["name"] == "Build"
    assert ci["jobs"]["e2e"]["name"] == "E2E (${{ matrix.name }})"

    gate = ci["jobs"]["merge-gate"]
    assert gate["name"] == "Merge Gate"
    assert set(gate["needs"]) == VERIFICATION_JOB_IDS
    assert gate["if"] == "always()"
    gate_step = _step(gate, "Require every verification job")
    assert gate_step["env"] == {
        "BUILD": "${{ needs.build.result }}",
        "DONOR_CONTRACT": "${{ needs.donor-contract.result }}",
        "UNIT_TESTS": "${{ needs.unit-tests.result }}",
        "REPOSITORY_INVENTORY": "${{ needs.harness-contracts.result }}",
        "EVIDENCE_CAPTURE": "${{ needs.evidence-capture.result }}",
        "EVIDENCE_DETERMINISM": "${{ needs.evidence-determinism.result }}",
        "RENDERER_CONTRACTS": "${{ needs.renderer-contracts.result }}",
        "RENDERER_RUNTIME": "${{ needs.renderer-runtime.result }}",
        "AUDIT_EVIDENCE": "${{ needs.audit-evidence.result }}",
        "E2E": "${{ needs.e2e.result }}",
    }
    syntax = subprocess.run(
        ["bash", "-n"],
        input=gate_step["run"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    assert release["on"] == {
        "workflow_run": {"workflows": ["CI"], "types": ["completed"]}
    }
    release_job = release["jobs"]["release"]
    assert release_job["if"] == (
        "github.event.workflow_run.conclusion == 'success' && "
        "github.event.workflow_run.event == 'push'"
    )
    download = _step(release_job, "Download build artifacts")
    assert download["with"]["name"] == "pokeyellow-build"


def test_merge_gate_accepts_only_all_successful_jobs() -> None:
    result = _run_merge_gate_script()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize(
    "dependency",
    (
        "BUILD",
        "DONOR_CONTRACT",
        "UNIT_TESTS",
        "REPOSITORY_INVENTORY",
        "EVIDENCE_CAPTURE",
        "EVIDENCE_DETERMINISM",
        "RENDERER_CONTRACTS",
        "RENDERER_RUNTIME",
        "AUDIT_EVIDENCE",
        "E2E",
    ),
)
@pytest.mark.parametrize("result", ("failure", "cancelled", "skipped"))
def test_merge_gate_rejects_any_unsuccessful_job(
    dependency: str, result: str
) -> None:
    completed = _run_merge_gate_script(**{dependency: result})
    assert completed.returncode != 0
    assert completed.stdout == f"::error::verification job finished as {result}\n"
    assert completed.stderr == ""


def test_build_job_produces_all_products_once() -> None:
    job = _load(WORKFLOWS["ci"])["jobs"]["build"]
    assert job["name"] == "Build"
    build_step = _step(job, "Build ROM products")
    assert build_step["run"] == (
        'make -j"$(nproc)" yellow yellow_debug yellow_vc yellow_phase2_audit'
    )
    assert len(
        [step for step in job["steps"] if step.get("uses") == "./.github/actions/setup-build"]
    ) == 1

    clean_step = _step(job, "Check for modified tracked files")
    assert "git diff-index --quiet HEAD --" in clean_step["run"]

    release_upload = _step(job, "Upload release products")
    assert release_upload["with"] == {
        "name": "pokeyellow-build",
        "path": "release/",
        "if-no-files-found": "error",
        "retention-days": "3",
    }
    stage = _step(job, "Stage release files")
    assert {
        line for line in _script_lines(stage["run"]) if line.startswith("cp ")
    } == RELEASE_COPIES

    test_upload = _step(job, "Upload test products")
    assert test_upload["with"]["name"] == "pokeyellow-test-products"
    test_product_paths = test_upload["with"]["path"].splitlines()
    assert len(test_product_paths) == 12
    assert set(test_product_paths) == TEST_PRODUCTS
    assert test_upload["with"]["if-no-files-found"] == "error"


def test_full_color_jobs_split_one_run_contracts_from_evidence() -> None:
    workflow = _load(WORKFLOWS["ci"])
    jobs = workflow["jobs"]
    assert {job_id: jobs[job_id]["name"] for job_id in FULL_COLOR_JOB_NAMES} == (
        FULL_COLOR_JOB_NAMES
    )
    assert "continue-on-error" not in WORKFLOWS["ci"].read_text(encoding="utf-8")
    for job_id in FULL_COLOR_JOB_NAMES:
        if job_id != "evidence-determinism":
            assert jobs[job_id]["needs"] == "build"

    donor = jobs["donor-contract"]
    donor_checkout = _step(donor, "Checkout pinned pokered-gbc donor")
    assert donor_checkout["with"]["repository"] == "dannye/pokered-gbc"
    assert donor_checkout["with"]["ref"] == (
        "c1a3b6c5a7591472241036d0cf09c3817f841f93"
    )
    assert _step(donor, "Run exact donor contract")["run"] == (
        "make test-full-color-donor-contract"
    )

    unit = jobs["unit-tests"]
    assert unit["timeout-minutes"] == "30"
    assert _step(unit, "Run complete unit contracts once")["run"] == (
        "make test-unit ROM_TEST_PREBUILT_PRODUCTS=1"
    )
    harness = jobs["harness-contracts"]
    assert "make test-full-color-harness-contracts ROM_TEST_PREBUILT_PRODUCTS=1" in (
        _step(harness, "Run repository and bank contracts")["run"]
    )
    assert _step(harness, "Upload harness contract evidence")["if"] == "always()"

    capture = jobs["evidence-capture"]
    assert capture["strategy"] == {
        "fail-fast": "false",
        "matrix": {
            "include": [
                {"name": "A", "run": "1"},
                {"name": "B", "run": "2"},
            ]
        },
    }
    assert COMPONENTS == ("observability", "traceability", "visual-pipeline")
    capture_command = _step(capture, "Capture deterministic evidence")["run"]
    assert "tools.rom_tests.full_color.evidence_runner" in capture_command
    assert "--one-run run-${{ matrix.run }}" in capture_command
    capture_upload = _step(capture, "Upload evidence capture")
    assert capture_upload["if"] == "always()"
    assert capture_upload["with"]["name"] == (
        "full-color-evidence-run-${{ matrix.run }}-${{ github.run_id }}-${{ github.run_attempt }}"
    )

    comparison = jobs["evidence-determinism"]
    assert set(comparison["needs"]) == {"build", "evidence-capture"}
    assert comparison["if"] == "always() && needs.build.result == 'success'"
    downloads = _artifact_steps(comparison, "actions/download-artifact@v7")
    assert {(step["with"]["name"], step["with"]["path"]) for step in downloads} == {
        (
            "full-color-evidence-run-1-${{ github.run_id }}-${{ github.run_attempt }}",
            "${{ env.FULL_COLOR_EVIDENCE_RESULTS }}/run-1",
        ),
        (
            "full-color-evidence-run-2-${{ github.run_id }}-${{ github.run_attempt }}",
            "${{ env.FULL_COLOR_EVIDENCE_RESULTS }}/run-2",
        ),
    }
    compare_command = _step(comparison, "Compare independent evidence")["run"]
    assert "--compare-runs run-1 run-2" in compare_command
    assert _step(comparison, "Upload compared evidence")["if"] == "always()"

    one_run_commands = [
        step.get("run", "")
        for step in _all_workflow_steps(workflow)
        if "make test-unit" in step.get("run", "")
    ]
    assert one_run_commands == ["make test-unit ROM_TEST_PREBUILT_PRODUCTS=1"]


def test_full_color_product_consumers_use_same_revision_artifact() -> None:
    jobs = _load(WORKFLOWS["ci"])["jobs"]
    consumer_ids = {
        "unit-tests",
        "harness-contracts",
        "evidence-capture",
        "renderer-runtime",
        "audit-evidence",
    }
    for job_id in consumer_ids:
        downloads = _artifact_steps(jobs[job_id], "actions/download-artifact@v7")
        assert len(downloads) == 1, job_id
        assert downloads[0]["with"] == {
            "name": "pokeyellow-test-products",
            "path": ".",
        }

    assert _step(jobs["renderer-contracts"], "Run renderer contract fixtures")[
        "run"
    ] == "make test-full-color-renderer-contracts"
    assert _step(jobs["renderer-runtime"], "Run renderer runtime ownership")[
        "run"
    ] == "make test-full-color-renderer-runtime ROM_TEST_PREBUILT_PRODUCTS=1"
    assert "make test-full-color-audit ROM_TEST_PREBUILT_PRODUCTS=1" in _step(
        jobs["audit-evidence"], "Verify audit evidence"
    )["run"]

    for job_id in (
        "renderer-contracts",
        "renderer-runtime",
        "audit-evidence",
    ):
        upload = [
            step
            for step in jobs[job_id]["steps"]
            if step.get("uses") == "actions/upload-artifact@v7"
        ]
        assert len(upload) == 1, job_id
        assert upload[0]["if"] == "always()"
        assert upload[0]["with"]["if-no-files-found"] == "error"


def test_ci_runs_three_independent_gameplay_suites() -> None:
    e2e = _load(WORKFLOWS["ci"])["jobs"]["e2e"]
    assert e2e["name"] == "E2E (${{ matrix.name }})"
    assert e2e["strategy"] == {
        "fail-fast": "false",
        "matrix": {"include": GAMEPLAY_MATRIX},
    }
    download = _step(e2e, "Download same-revision test products")
    assert download["with"] == {"name": "pokeyellow-test-products", "path": "."}
    assert _step(e2e, "Run gameplay suite")["run"] == (
        "make ROM_TEST_PREBUILT_PRODUCTS=1 ${{ matrix.target }}"
    )
    failure_upload = _step(e2e, "Upload failure evidence")
    assert failure_upload["if"] == "failure()"
    assert failure_upload["with"] == {
        "name": "e2e-${{ matrix.suite }}-failure-evidence",
        "path": "test-results/",
        "if-no-files-found": "warn",
        "retention-days": "14",
    }


def test_metadata_and_trusted_label_workflows_keep_distinct_boundaries() -> None:
    metadata = _load(WORKFLOWS["metadata"])
    labels = _load(WORKFLOWS["labels"])

    assert metadata["name"] == "Metadata"
    assert metadata["on"] == {
        "pull_request": {
            "branches": ["main"],
            "types": [
                "opened",
                "edited",
                "reopened",
                "synchronize",
                "ready_for_review",
                "converted_to_draft",
            ],
        },
        "push": {"branches": ["main"]},
    }
    assert metadata["permissions"] == {"contents": "read", "checks": "read"}
    assert metadata["concurrency"] == {
        "group": (
            "${{ github.workflow }}-${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.number || github.ref }}-${{ github.event_name "
            "== 'pull_request' && github.event.action || 'code' }}"
        ),
        "cancel-in-progress": "true",
    }
    assert set(metadata["jobs"]) == {"lint"}
    lint = metadata["jobs"]["lint"]
    assert lint["name"] == "Lint"
    checkout = _step(lint, "Checkout")
    actionlint = _step(lint, "Run actionlint")
    assert "if" not in checkout
    assert "if" not in actionlint
    assert actionlint["uses"] == "docker://rhysd/actionlint:1.7.12"
    assert _step(lint, "Lint pull request title")["if"] == (
        "github.event_name == 'pull_request'"
    )
    reopen = _step(lint, "Require prior merge gate when reopening")
    assert reopen["if"] == "github.event.action == 'reopened'"
    assert 'select(.name == "Merge Gate" and .conclusion == "success")' in reopen[
        "run"
    ]

    assert labels["name"] == "Metadata"
    assert labels["jobs"]["label"]["name"] == "Labels"
    assert labels["on"] == {
        "pull_request_target": {
            "types": ["opened", "edited", "synchronize", "reopened"]
        }
    }
    assert labels["permissions"] == {
        "issues": "write",
        "pull-requests": "write",
    }
    assert "actions/checkout" not in WORKFLOWS["labels"].read_text(encoding="utf-8")
    assert "pull_request_target" not in WORKFLOWS["metadata"].read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "pages",
    [
        [{"check_runs": [{"name": "Merge Gate", "conclusion": "success"}]}],
        [
            {"check_runs": [{"name": "Merge Gate", "conclusion": "failure"}]},
            {"check_runs": [{"name": "Merge Gate", "conclusion": "success"}]},
        ],
    ],
    ids=("one-success", "success-on-later-page"),
)
def test_reopen_accepts_prior_successful_merge_gate(
    tmp_path: Path, pages: list[dict[str, Any]]
) -> None:
    result = _run_reopen_script(tmp_path, pages=pages)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize(
    "pages",
    [
        [{"check_runs": []}],
        [{"check_runs": [{"name": "Merge Gate", "conclusion": None}]}],
        [{"check_runs": [{"name": "Certification", "conclusion": "success"}]}],
    ],
    ids=("zero-check-runs", "in-progress", "old-check-name"),
)
def test_reopen_rejects_heads_without_successful_merge_gate(
    tmp_path: Path, pages: list[dict[str, Any]]
) -> None:
    result = _run_reopen_script(tmp_path, pages=pages)
    assert result.returncode != 0
    assert result.stdout == (
        "::error::reopened head SHA has no successful Merge Gate check run\n"
    )
    assert result.stderr == ""


def test_reopen_fails_closed_when_api_fails(tmp_path: Path) -> None:
    result = _run_reopen_script(tmp_path, gh_failure=True)
    assert result.returncode != 0
    assert result.stdout == (
        "::error::could not enumerate Merge Gate check runs for reopened head SHA\n"
    )
    assert result.stderr == ""


@pytest.mark.parametrize(
    "raw_output",
    ("not json", '[{"check_runs":', "[{}]"),
    ids=("not-json", "truncated-json", "missing-check-runs"),
)
def test_reopen_fails_closed_when_paginated_json_is_malformed(
    tmp_path: Path, raw_output: str
) -> None:
    result = _run_reopen_script(tmp_path, raw_output=raw_output)
    assert result.returncode != 0
    assert result.stdout == (
        "::error::could not parse Merge Gate check runs for reopened head SHA\n"
    )
    assert result.stderr == ""


def test_verification_workflow_has_no_manual_bypass_or_soft_failures() -> None:
    workflow = _load(WORKFLOWS["ci"])
    assert "workflow_dispatch" not in workflow["on"]
    assert "continue-on-error" not in WORKFLOWS["ci"].read_text(encoding="utf-8")

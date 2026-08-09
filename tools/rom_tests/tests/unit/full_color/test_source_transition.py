"""Fail-closed checks for the source-transition evidence producer."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import shutil
from types import SimpleNamespace

import pytest

from tools.rom_tests.full_color import audit_evidence_identities, source_transition
from tools.rom_tests.full_color.discovery_assignment import (
    BASELINE_PRODUCT,
    DiscoveryAssignmentAuthority,
)
from tools.rom_tests.full_color.discovery_review import (
    rom_finding_subject,
    source_finding_subject,
)
from tools.rom_tests.full_color.source_discovery import SourceFinding
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT


def _proposal_envelope(proposal: dict[str, object]) -> dict[str, object]:
    return {
        "schema": source_transition.PROPOSAL_SCHEMA,
        "reviewed": False,
        "authority_path": str(source_transition.TRANSITION_PATH),
        "proposal": proposal,
    }


def test_source_transition_generation_is_idempotent_and_preserves_authority(
    monkeypatch,
) -> None:
    first = source_transition.generate_json(REPOSITORY_ROOT)
    second = source_transition.generate_json(REPOSITORY_ROOT)
    assert second == first
    generated = json.loads(first)
    authority = json.loads(
        (REPOSITORY_ROOT / source_transition.TRANSITION_PATH).read_text(
            encoding="utf-8"
        )
    )
    for name in (
        "reviewed_source_sha256",
        "baseline_manifest_sha256",
    ):
        assert generated[name] == authority[name]
    assert {
        path: binding["reviewed_sha256"]
        for path, binding in generated["reviewed_delta_paths"].items()
    } == {
        path: binding["reviewed_sha256"]
        for path, binding in authority["reviewed_delta_paths"].items()
    }
    assert len(set(generated["subject_rebindings"].values())) == len(
        generated["subject_rebindings"]
    )
    assert len(set(generated["rom_subject_rebindings"].values())) == len(
        generated["rom_subject_rebindings"]
    )
    monkeypatch.setattr(
        source_transition,
        "generate",
        lambda root, *, authority_path=None: generated,
    )
    proposal = source_transition.generate_proposal(REPOSITORY_ROOT)
    assert proposal["schema"] == source_transition.PROPOSAL_SCHEMA
    assert proposal["reviewed"] is False
    assert proposal["proposal"] == generated


def test_source_transition_rejects_v2_compatibility_authority(tmp_path) -> None:
    authority = json.loads(
        (REPOSITORY_ROOT / source_transition.TRANSITION_PATH).read_text(
            encoding="utf-8"
        )
    )
    authority["schema"] = "full-color-phase1-audit-source-transition-v2"
    authority["audit_source_sha256"] = authority.pop("current_source_sha256")
    legacy_paths = authority.pop("reviewed_delta_paths")
    for binding in legacy_paths.values():
        binding["audit_sha256"] = binding.pop("current_sha256")
    authority["audit_only_paths"] = legacy_paths
    path = tmp_path / "v2-source-transition.json"
    path.write_text(json.dumps(authority), encoding="utf-8")

    with pytest.raises(
        source_transition.SourceTransitionError,
        match="source-transition authority is malformed",
    ):
        source_transition.generate(REPOSITORY_ROOT, authority_path=path)


def test_source_transition_rebinds_authorized_unchanged_line_shift(tmp_path) -> None:
    relative = "linked.asm"
    (tmp_path / relative).write_text("; inserted\nMovedRoot:\n", encoding="utf-8")
    reviewed = SourceFinding(
        category="mutation",
        path=relative,
        line=1,
        symbol="MovedRoot",
        mechanism="configured-root",
        destination="MovedRoot",
        resource="MUTATION",
        evidence_sha256=source_transition._source_line_sha256(
            relative, 1, "MovedRoot:"
        ),
        destination_path=relative,
        destination_line=1,
    )
    current = replace(
        reviewed,
        line=2,
        evidence_sha256=source_transition._source_line_sha256(
            relative, 2, "MovedRoot:"
        ),
        destination_line=2,
    )
    row = SimpleNamespace(subject=source_finding_subject(reviewed))

    assert source_transition._unique_rebindings(
        (row,),
        (current,),
        subject=source_finding_subject,
        rebound=lambda finding, authority: source_transition._rebound_source_finding(
            tmp_path, {relative}, finding, authority
        ),
        kind="source",
    ) == {row.subject.sha256: source_finding_subject(current).sha256}

    with pytest.raises(
        source_transition.SourceTransitionError, match="semantic matches"
    ):
        source_transition._unique_rebindings(
            (row,),
            (current,),
            subject=source_finding_subject,
            rebound=lambda finding, authority: (
                source_transition._rebound_source_finding(
                    tmp_path, set(), finding, authority
                )
            ),
            kind="source",
        )

    with pytest.raises(
        source_transition.SourceTransitionError, match="semantic matches"
    ):
        source_transition._unique_rebindings(
            (row,),
            (replace(current, symbol="UnrelatedRoot.local"),),
            subject=source_finding_subject,
            rebound=lambda finding, authority: (
                source_transition._rebound_source_finding(
                    tmp_path, {relative}, finding, authority
                )
            ),
            kind="source",
        )


def test_source_transition_rejects_changed_line_in_authorized_file(tmp_path) -> None:
    relative = "linked.asm"
    (tmp_path / relative).write_text("; inserted\nChangedRoot:\n", encoding="utf-8")
    reviewed = SourceFinding(
        category="mutation",
        path=relative,
        line=1,
        symbol="MovedRoot",
        mechanism="configured-root",
        destination="MovedRoot",
        resource="MUTATION",
        evidence_sha256=source_transition._source_line_sha256(
            relative, 1, "MovedRoot:"
        ),
        destination_path=relative,
        destination_line=1,
    )
    current = replace(
        reviewed,
        line=2,
        evidence_sha256=source_transition._source_line_sha256(
            relative, 2, "ChangedRoot:"
        ),
        destination_line=2,
    )
    row = SimpleNamespace(subject=source_finding_subject(reviewed))

    with pytest.raises(
        source_transition.SourceTransitionError, match="semantic matches"
    ):
        source_transition._unique_rebindings(
            (row,),
            (current,),
            subject=source_finding_subject,
            rebound=lambda finding, authority: (
                source_transition._rebound_source_finding(
                    tmp_path, {relative}, finding, authority
                )
            ),
            kind="source",
        )


def test_rom_rebinding_rejects_unrelated_same_depth_call_path() -> None:
    source_report = source_transition.baseline.discover_baseline_sources(
        REPOSITORY_ROOT
    )
    rom_report = source_transition._raw_baseline_rom(REPOSITORY_ROOT, source_report)
    assignments = DiscoveryAssignmentAuthority.load(
        REPOSITORY_ROOT / source_transition.ASSIGNMENTS_PATH
    ).for_product(BASELINE_PRODUCT)
    row = next(
        row
        for row in assignments.rows
        if row.subject.kind.value == "ROM_FINDING"
        and len(row.subject.metadata["call_path"]) == 1
    )
    authority = json.loads(
        (REPOSITORY_ROOT / source_transition.TRANSITION_PATH).read_text(
            encoding="utf-8"
        )
    )
    current_digest = authority["rom_subject_rebindings"][row.subject.sha256]
    finding = next(
        finding
        for finding in rom_report.findings
        if rom_finding_subject(finding).sha256 == current_digest
    )
    unrelated = replace(finding, call_path=("UnrelatedSameDepth",))

    assert source_transition._rebound_rom_finding(unrelated, row) == unrelated
    with pytest.raises(
        source_transition.SourceTransitionError, match="0 semantic matches"
    ):
        source_transition._unique_rebindings(
            (row,),
            (unrelated,),
            subject=rom_finding_subject,
            rebound=source_transition._rebound_rom_finding,
            kind="ROM",
        )


@pytest.mark.parametrize("mutation", ("missing", "ambiguous", "semantic"))
def test_source_transition_rejects_non_unique_or_changed_subjects(
    mutation: str,
) -> None:
    report = source_transition.baseline.discover_baseline_sources(REPOSITORY_ROOT)
    assignments = DiscoveryAssignmentAuthority.load(
        REPOSITORY_ROOT / source_transition.ASSIGNMENTS_PATH
    ).for_product(BASELINE_PRODUCT)
    row = next(
        row for row in assignments.rows if row.subject.kind.value == "SOURCE_FINDING"
    )
    authority = json.loads(
        (REPOSITORY_ROOT / source_transition.TRANSITION_PATH).read_text(
            encoding="utf-8"
        )
    )
    reviewed_delta_paths = set(authority["reviewed_delta_paths"])
    matching = next(
        finding
        for finding in report.findings
        if source_finding_subject(
            source_transition._rebound_source_finding(
                REPOSITORY_ROOT, reviewed_delta_paths, finding, row
            )
        ).sha256
        == row.subject.sha256
    )
    findings = [matching]
    if mutation == "missing":
        findings = []
    elif mutation == "ambiguous":
        findings.append(matching)
    else:
        findings[0] = replace(matching, resource="SEMANTIC_CHANGE")
    with pytest.raises(
        source_transition.SourceTransitionError, match="semantic matches"
    ):
        source_transition._unique_rebindings(
            (row,),
            findings,
            subject=source_finding_subject,
            rebound=lambda finding, authority: (
                source_transition._rebound_source_finding(
                    REPOSITORY_ROOT, reviewed_delta_paths, finding, authority
                )
            ),
            kind="source",
        )


def test_audit_identity_rebinding_proposes_hashes_without_approving_or_writing(
    tmp_path, monkeypatch
) -> None:
    inventory = tmp_path / "specs/full-colors/inventory"
    inventory.mkdir(parents=True)
    originals = {}
    for relative in audit_evidence_identities.DOCUMENTS:
        source = REPOSITORY_ROOT / relative
        target = tmp_path / relative
        target.write_bytes(source.read_bytes())
        originals[relative] = json.loads(source.read_text(encoding="utf-8"))
    transition = tmp_path / audit_evidence_identities.TRANSITION_PATH
    transition.parent.mkdir(parents=True)
    transition.write_text(
        json.dumps(
            _proposal_envelope(
                {
                    "schema": source_transition.SCHEMA,
                    "reviewed_source_sha256": (
                        audit_evidence_identities.REVIEWED_SOURCE_SHA256
                    ),
                    "current_source_sha256": "f" * 64,
                    "baseline_manifest_sha256": (
                        audit_evidence_identities.BASELINE_MANIFEST_SHA256
                    ),
                    "reviewed_delta_paths": {},
                    "subject_rebindings": {},
                    "rom_subject_rebindings": {},
                }
            )
        )
    )
    for relative in (
        *audit_evidence_identities.BASELINE_ARTIFACTS.values(),
        *audit_evidence_identities.AUDIT_ARTIFACTS.values(),
    ):
        shutil.copyfile(REPOSITORY_ROOT / relative, tmp_path / relative)
    monkeypatch.setattr(
        audit_evidence_identities,
        "discover_baseline_sources",
        lambda root: SimpleNamespace(source_sha256="f" * 64),
    )
    monkeypatch.setattr(
        source_transition,
        "generate",
        lambda root, *, authority_path=None: json.loads(
            transition.read_text(encoding="utf-8")
        )["proposal"],
    )
    proposal = audit_evidence_identities.propose(tmp_path, transition)
    baseline_hashes = audit_evidence_identities._baseline_hashes(tmp_path, "f" * 64)
    assert proposal["schema"] == audit_evidence_identities.PROPOSAL_SCHEMA
    assert proposal["reviewed"] is False
    assert set(proposal["documents"]) == {
        relative.as_posix() for relative in audit_evidence_identities.DOCUMENTS
    }
    for relative, before in originals.items():
        assert json.loads((tmp_path / relative).read_text(encoding="utf-8")) == before
        changes = proposal["documents"][relative.as_posix()]["changes"]
        changed_ids = {change["id"] for change in changes}
        expected_ids = {row["id"] for row in before["rows"]}
        assert changed_ids == expected_ids
        for change in changes:
            assert change["proposed"]["source_sha256"] == "f" * 64
            if change["id"] in audit_evidence_identities.BASELINE_ASSIGNMENT_IDS or (
                relative.name != "assignments.json"
                and change["id"]
                in audit_evidence_identities.BASELINE_INVENTORY_IDS[relative.name]
            ):
                assert change["proposed"] == baseline_hashes
            else:
                assert {
                    key
                    for key in change["current"]
                    if change["current"][key] != change["proposed"][key]
                } == {"source_sha256"}
            assert "reviewer" not in change
            assert "reviewed" not in change


def test_reviewed_identity_apply_requires_exact_canonical_proposal(
    tmp_path, monkeypatch
) -> None:
    proposal = {
        "schema": audit_evidence_identities.PROPOSAL_SCHEMA,
        "reviewed": False,
        "source_transition_proposal": "transition.json",
        "documents": {},
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    monkeypatch.setattr(
        audit_evidence_identities,
        "propose",
        lambda root, transition: {**proposal, "reviewed": True},
    )
    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="does not match canonical recomputation",
    ):
        audit_evidence_identities.apply_reviewed_proposal(
            tmp_path, tmp_path / "transition.json", proposal_path
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("schema", "source-transition authority is malformed"),
        (
            "digest",
            "source-transition identity does not match current baseline discovery",
        ),
    ),
)
def test_audit_identity_rebinding_rejects_untrusted_transition(
    tmp_path, monkeypatch, mutation: str, message: str
) -> None:
    transition = tmp_path / audit_evidence_identities.TRANSITION_PATH
    transition.parent.mkdir(parents=True)
    authority = {
        "schema": source_transition.SCHEMA,
        "reviewed_source_sha256": audit_evidence_identities.REVIEWED_SOURCE_SHA256,
        "current_source_sha256": "f" * 64,
        "baseline_manifest_sha256": (
            audit_evidence_identities.BASELINE_MANIFEST_SHA256
        ),
        "reviewed_delta_paths": {},
        "subject_rebindings": {},
        "rom_subject_rebindings": {},
    }
    if mutation == "schema":
        authority["schema"] = "fabricated-source-transition-schema"
    transition.write_text(json.dumps(_proposal_envelope(authority)), encoding="utf-8")
    monkeypatch.setattr(
        audit_evidence_identities,
        "discover_baseline_sources",
        lambda root: SimpleNamespace(source_sha256="e" * 64),
    )

    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError, match=message
    ):
        audit_evidence_identities.propose(tmp_path, transition)


@pytest.mark.parametrize(
    "mutation",
    (
        "reviewed_source_sha256",
        "baseline_manifest_sha256",
        "reviewed_delta_paths",
        "subject_rebindings",
        "rom_subject_rebindings",
    ),
)
def test_audit_identity_rebinding_rejects_fabricated_nondigest_authority(
    tmp_path, monkeypatch, mutation: str
) -> None:
    transition = tmp_path / audit_evidence_identities.TRANSITION_PATH
    transition.parent.mkdir(parents=True)
    canonical = {
        "schema": source_transition.SCHEMA,
        "reviewed_source_sha256": audit_evidence_identities.REVIEWED_SOURCE_SHA256,
        "current_source_sha256": "f" * 64,
        "baseline_manifest_sha256": (
            audit_evidence_identities.BASELINE_MANIFEST_SHA256
        ),
        "reviewed_delta_paths": {},
        "subject_rebindings": {},
        "rom_subject_rebindings": {},
    }
    authority = json.loads(json.dumps(canonical))
    if mutation in {"reviewed_source_sha256", "baseline_manifest_sha256"}:
        authority[mutation] = "0" * 64
    else:
        authority[mutation] = {"fabricated": "authority"}
    transition.write_text(json.dumps(_proposal_envelope(authority)), encoding="utf-8")
    monkeypatch.setattr(
        audit_evidence_identities,
        "discover_baseline_sources",
        lambda root: SimpleNamespace(source_sha256="f" * 64),
    )
    monkeypatch.setattr(
        source_transition,
        "generate",
        lambda root, *, authority_path=None: json.loads(json.dumps(canonical)),
    )

    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="does not match canonical recomputation",
    ):
        audit_evidence_identities.propose(tmp_path, transition)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("product", "mixed product hash tuple"),
        ("id", "rows must be sorted by stable ID"),
        ("semantics", "duplicate subject fingerprints"),
        ("mixed", "mixed product hash tuple"),
    ),
)
def test_assignment_identity_rebinding_rejects_authority_mutation(
    mutation: str, message: str
) -> None:
    raw = json.loads(
        (REPOSITORY_ROOT / source_transition.ASSIGNMENTS_PATH).read_text(
            encoding="utf-8"
        )
    )
    normal = [row for row in raw["rows"] if row["product"] == BASELINE_PRODUCT]
    if mutation == "product":
        normal[0]["product"] = "pokeyellow_phase2_audit"
    elif mutation == "id":
        normal[0]["id"] = "AS-UNEXPECTED"
    elif mutation == "semantics":
        normal[0]["subject"] = normal[1]["subject"]
    else:
        normal[0]["evidence"]["rom_sha256"] = "0" * 64
    with pytest.raises(Exception, match=message):
        authority = DiscoveryAssignmentAuthority.from_dict(raw)
        audit_evidence_identities._updated_assignments(
            authority,
            "f" * 64,
            {
                "source_sha256": "f" * 64,
                "rom_sha256": "1" * 64,
                "map_sha256": "2" * 64,
                "sym_sha256": "3" * 64,
            },
            audit_evidence_identities.REVIEWED_AUDIT_HASHES,
        )


def test_assignment_identity_rebinding_requires_all_debug_artifacts(tmp_path) -> None:
    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="required build artifact is missing",
    ):
        audit_evidence_identities._baseline_hashes(tmp_path, "f" * 64)


def test_assignment_identity_rebinding_rejects_parsed_ninth_baseline_row() -> None:
    raw = json.loads(
        (REPOSITORY_ROOT / source_transition.ASSIGNMENTS_PATH).read_text(
            encoding="utf-8"
        )
    )
    baseline = [row for row in raw["rows"] if row["product"] == BASELINE_PRODUCT]
    baseline_subjects = {row["subject"]["sha256"] for row in baseline}
    extra = deepcopy(
        next(
            row
            for row in raw["rows"]
            if row["product"] != BASELINE_PRODUCT
            and row["subject"]["sha256"] not in baseline_subjects
        )
    )
    extra["id"] = "AS-BASELINE-EXTRA"
    extra["product"] = BASELINE_PRODUCT
    extra["evidence"] = deepcopy(baseline[0]["evidence"])
    raw["rows"].append(extra)
    raw["rows"].sort(key=lambda row: row["id"])
    authority = DiscoveryAssignmentAuthority.from_dict(raw)
    assert len(authority.for_product(BASELINE_PRODUCT).rows) == 9

    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="baseline assignment scope changed",
    ):
        audit_evidence_identities._updated_assignments(
            authority,
            "f" * 64,
            {
                "source_sha256": "f" * 64,
                "rom_sha256": "1" * 64,
                "map_sha256": "2" * 64,
                "sym_sha256": "3" * 64,
            },
            audit_evidence_identities.REVIEWED_AUDIT_HASHES,
        )


def test_assignment_identity_rebinding_rejects_scope_and_semantic_drift() -> None:
    authority = DiscoveryAssignmentAuthority.load(
        REPOSITORY_ROOT / source_transition.ASSIGNMENTS_PATH
    )
    normal = authority.for_product(BASELINE_PRODUCT)
    narrowed = DiscoveryAssignmentAuthority(
        tuple(row for row in authority.rows if row.id != normal.rows[0].id)
    )
    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="baseline assignment scope changed",
    ):
        audit_evidence_identities._updated_assignments(
            narrowed,
            "f" * 64,
            {
                "source_sha256": "f" * 64,
                "rom_sha256": "1" * 64,
                "map_sha256": "2" * 64,
                "sym_sha256": "3" * 64,
            },
            audit_evidence_identities.REVIEWED_AUDIT_HASHES,
        )

    changed = replace(
        normal.rows[0],
        evidence=replace(normal.rows[0].evidence, reviewer="changed-reviewer"),
    )
    after = DiscoveryAssignmentAuthority(
        tuple(changed if row.id == changed.id else row for row in authority.rows)
    )
    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="reviewed semantics changed",
    ):
        audit_evidence_identities._assert_assignment_delta(authority, after)


def test_identity_producer_make_target_is_stable_and_build_dependent() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    assert (
        "measure-full-color-audit-evidence-identities: "
        "measure-full-color-source-transition" in makefile
    )
    assert (
        "measure-full-color-source-transition: "
        "yellow yellow_debug yellow_vc yellow_phase2_audit" in makefile
    )

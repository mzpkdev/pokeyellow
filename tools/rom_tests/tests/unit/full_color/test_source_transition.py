"""Fail-closed checks for the source-transition evidence producer."""

from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.rom_tests.full_color import (
    audit_evidence_identities,
    baseline_discovery,
    source_transition,
)
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
    monkeypatch, tmp_path,
) -> None:
    first = source_transition.generate_json(REPOSITORY_ROOT)
    second = source_transition.generate_json(REPOSITORY_ROOT)
    assert second == first
    generated = json.loads(first)
    assert generated["schema"] == "full-color-production-source-transition-v4"
    assert len(generated["audit_only_source_regions"]) == 17
    assert {
        row["symbol"] for row in generated["audit_only_source_regions"]
    } == {
        "DrawPartyMenu_.clearLogicalTileMap",
        "EnsureFreeFullColorPhase5DescriptorSelected.reclaim",
        "FullColorPhase5BeginVBlankBudgetFar",
        "FullColorPhase5PrepareOwnedMainlineFrame",
        "FullColorPhase5PrepareOwnedMainlineFrame.done",
        "FullColorPhase5PrepareOwnedMainlineFrame.nextResident",
        "FullColorPhase5PrepareOwnedMainlineFrame.pressureSelected",
        "FullColorPhase5PrepareOwnedMainlineFrame.skip",
        "FullColorPhase5PressureMainline",
        "FullColorPhase5PressureMainline.activeNext",
        "FullColorPhase5PressureMainline.admissionFailedSelected",
        "FullColorPhase5PressureMainline.admittedSelected",
        "FullColorPhase5PressureMainline.copyDescriptor",
        "FullColorPhase5PressureMainline.generation",
        "FullColorPhase5PressureMainline.restore",
        "FullColorPhase5YellowOwner",
        "FullColorPhase5YellowOwner.skipDec",
    }
    reviewed_path = tmp_path / "reviewed-v4.json"
    reviewed_path.write_text(source_transition._canonical(generated), encoding="utf-8")
    monkeypatch.setattr(baseline_discovery, "SOURCE_TRANSITION_PATH", reviewed_path)
    added, conditional = baseline_discovery._validated_audit_only_authority(
        REPOSITORY_ROOT,
        baseline_discovery.discover_baseline_sources(REPOSITORY_ROOT),
    )
    assert len(conditional) == 17
    assert "engine/full_color/phase5_audit.asm" in added
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


@pytest.mark.parametrize("payload", ('{"schema":"x","schema":"y"}', '{"x":NaN}'))
def test_source_transition_rejects_duplicate_or_nonfinite_json(
    tmp_path, payload: str
) -> None:
    path = tmp_path / "hostile-transition.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(
        source_transition.SourceTransitionError,
        match="source-transition authority is unreadable",
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
                    "audit_only_source_regions": [],
                    "product_identities": {},
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
        "generate_from_authority",
        lambda root, authority: json.loads(
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
    proposal_path.write_text(
        audit_evidence_identities._canonical(proposal), encoding="utf-8"
    )
    transition_path = tmp_path / "transition.json"
    transition_path.write_text(
        audit_evidence_identities._canonical(_proposal_envelope({"identity": "x"})),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        audit_evidence_identities,
        "propose",
        lambda root, transition, **kwargs: {**proposal, "reviewed": True},
    )
    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="does not match canonical recomputation",
    ):
        audit_evidence_identities.apply_reviewed_proposal(
            tmp_path, transition_path, proposal_path
        )


@pytest.mark.parametrize("payload", ('{"schema":"x","schema":"y"}', '{"x":Infinity}'))
def test_audit_proposal_reader_rejects_duplicate_or_nonfinite_json(
    tmp_path, payload: str
) -> None:
    transition_path = tmp_path / "transition.json"
    transition_path.write_text(payload, encoding="utf-8")
    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="not strict JSON",
    ):
        audit_evidence_identities.propose(tmp_path, transition_path)


def test_reviewed_apply_installs_exact_canonical_transition(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / audit_evidence_identities.TRANSITION_PATH
    target.parent.mkdir(parents=True)
    target.write_text("{}\n", encoding="utf-8")
    transition = {
        "schema": source_transition.SCHEMA,
        "reviewed_source_sha256": "a" * 64,
        "current_source_sha256": "b" * 64,
        "baseline_manifest_sha256": "c" * 64,
        "reviewed_delta_paths": {},
        "subject_rebindings": {},
        "rom_subject_rebindings": {},
        "audit_only_source_regions": [],
        "product_identities": {},
    }
    transition_proposal = tmp_path / "transition.proposal.json"
    transition_proposal.write_text(
        audit_evidence_identities._canonical(_proposal_envelope(transition)),
        encoding="utf-8",
    )
    proposal = {
        "schema": audit_evidence_identities.PROPOSAL_SCHEMA,
        "reviewed": False,
        "source_transition_proposal": str(transition_proposal),
        "documents": {},
    }
    proposal_path = tmp_path / "audit.proposal.json"
    proposal_path.write_text(
        audit_evidence_identities._canonical(proposal), encoding="utf-8"
    )

    def swap_transition_after_snapshot(root, path, *, transition_envelope_text):
        assert json.loads(transition_envelope_text)["proposal"] == transition
        replacement = _proposal_envelope(
            {**transition, "current_source_sha256": "d" * 64}
        )
        transition_proposal.write_text(
            audit_evidence_identities._canonical(replacement), encoding="utf-8"
        )
        return proposal

    monkeypatch.setattr(
        audit_evidence_identities, "propose", swap_transition_after_snapshot
    )

    audit_evidence_identities.apply_reviewed_proposal(
        tmp_path, transition_proposal, proposal_path
    )

    assert target.read_text(encoding="utf-8") == (
        audit_evidence_identities._canonical(transition)
    )


def test_reviewed_apply_rejects_noncanonical_json_and_noncanonical_target(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / audit_evidence_identities.TRANSITION_PATH
    target.parent.mkdir(parents=True)
    target.write_text("{}\n", encoding="utf-8")
    transition = _proposal_envelope({"identity": "x"})
    transition_proposal = tmp_path / "transition.proposal.json"
    transition_proposal.write_text(
        audit_evidence_identities._canonical(transition), encoding="utf-8"
    )
    proposal = {
        "schema": audit_evidence_identities.PROPOSAL_SCHEMA,
        "reviewed": False,
        "source_transition_proposal": str(transition_proposal),
        "documents": {},
    }
    proposal_path = tmp_path / "audit.proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    monkeypatch.setattr(
        audit_evidence_identities,
        "propose",
        lambda root, path, **kwargs: proposal,
    )
    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="not canonical JSON",
    ):
        audit_evidence_identities.apply_reviewed_proposal(
            tmp_path, transition_proposal, proposal_path
        )

    proposal_path.write_text(
        audit_evidence_identities._canonical(proposal), encoding="utf-8"
    )
    transition["authority_path"] = "specs/full-colors/definitions/forged.json"
    transition_proposal.write_text(
        audit_evidence_identities._canonical(transition), encoding="utf-8"
    )
    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="canonical authority",
    ):
        audit_evidence_identities.apply_reviewed_proposal(
            tmp_path, transition_proposal, proposal_path
        )


def test_reviewed_apply_rejects_duplicate_audit_proposal_keys(
    tmp_path, monkeypatch
) -> None:
    transition_target = tmp_path / audit_evidence_identities.TRANSITION_PATH
    transition_target.parent.mkdir(parents=True)
    transition_target.write_text("{}\n", encoding="utf-8")
    transition_proposal = tmp_path / "transition.proposal.json"
    transition_proposal.write_text(
        audit_evidence_identities._canonical(_proposal_envelope({"identity": "x"})),
        encoding="utf-8",
    )
    proposal_path = tmp_path / "audit.proposal.json"
    proposal_path.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
    monkeypatch.setattr(
        audit_evidence_identities,
        "propose",
        lambda root, path, **kwargs: {},
    )
    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="not strict JSON",
    ):
        audit_evidence_identities.apply_reviewed_proposal(
            tmp_path, transition_proposal, proposal_path
        )


def test_reviewed_apply_paths_are_contained_and_require_explicit_review(
    tmp_path, capsys
) -> None:
    outside = tmp_path.parent / "outside.proposal.json"
    outside.write_text("{}\n", encoding="utf-8")
    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="escapes repository root",
    ):
        audit_evidence_identities.apply_reviewed_proposal(tmp_path, outside, outside)
    with pytest.raises(SystemExit) as raised:
        audit_evidence_identities.main(
            [
                "--root",
                str(tmp_path),
                "--transition-proposal",
                "transition.json",
                "--apply-proposal",
                "proposal.json",
            ]
        )
    assert raised.value.code == 2
    assert "requires --authority-reviewed" in capsys.readouterr().err


def test_reviewed_authority_transaction_rolls_back_every_written_file(
    tmp_path, monkeypatch
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_bytes(b"first-before")
    second.write_bytes(b"second-before")
    original_replace = audit_evidence_identities._atomic_replace
    failed = False

    first_target = audit_evidence_identities._pin_target(
        tmp_path, first.relative_to(tmp_path)
    )
    second_target = audit_evidence_identities._pin_target(
        tmp_path, second.relative_to(tmp_path)
    )

    def fail_once(target, contents, expected, ledger):
        nonlocal failed
        if target.path == second and not failed:
            failed = True
            raise OSError("injected write failure")
        return original_replace(target, contents, expected, ledger)

    monkeypatch.setattr(audit_evidence_identities, "_atomic_replace", fail_once)
    try:
        with pytest.raises(
            audit_evidence_identities.AuditEvidenceIdentityError,
            match="transaction failed",
        ):
            audit_evidence_identities._transactional_write(
                [(first_target, b"first-after"), (second_target, b"second-after")]
            )
    finally:
        os.close(first_target.directory_fd)
        os.close(second_target.directory_fd)
    assert first.read_bytes() == b"first-before"
    assert second.read_bytes() == b"second-before"


def test_reviewed_authority_publication_rejects_parent_directory_swap(
    tmp_path, monkeypatch
) -> None:
    directory = tmp_path / "authority"
    directory.mkdir()
    path = directory / "target.json"
    path.write_bytes(b"before")
    target = audit_evidence_identities._pin_target(tmp_path, path.relative_to(tmp_path))
    detached = tmp_path / "detached-authority"
    original_allocate = audit_evidence_identities._allocate_temporary

    def swap_parent(pinned):
        descriptor, name = original_allocate(pinned)
        directory.rename(detached)
        directory.mkdir()
        (directory / path.name).write_bytes(b"attacker")
        return descriptor, name

    monkeypatch.setattr(audit_evidence_identities, "_allocate_temporary", swap_parent)
    try:
        with pytest.raises(
            audit_evidence_identities.AuditEvidenceIdentityError,
            match="target directory changed",
        ):
            audit_evidence_identities._transactional_write([(target, b"after")])
    finally:
        os.close(target.directory_fd)

    assert (directory / path.name).read_bytes() == b"attacker"
    assert (detached / path.name).read_bytes() == b"before"


def test_reviewed_authority_pin_rejects_symlinked_ancestor(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "target.json").write_bytes(b"outside")
    (tmp_path / "authority").symlink_to(outside, target_is_directory=True)

    with pytest.raises(
        audit_evidence_identities.AuditEvidenceIdentityError,
        match="target directory is unavailable",
    ):
        audit_evidence_identities._pin_target(tmp_path, Path("authority/target.json"))

    assert (outside / "target.json").read_bytes() == b"outside"


def test_reviewed_authority_rollback_never_enters_swapped_parent(
    tmp_path, monkeypatch
) -> None:
    first_directory = tmp_path / "first-authority"
    second_directory = tmp_path / "second-authority"
    first_directory.mkdir()
    second_directory.mkdir()
    first = first_directory / "first.json"
    second = second_directory / "second.json"
    first.write_bytes(b"first-before")
    second.write_bytes(b"second-before")
    first_target = audit_evidence_identities._pin_target(
        tmp_path, first.relative_to(tmp_path)
    )
    second_target = audit_evidence_identities._pin_target(
        tmp_path, second.relative_to(tmp_path)
    )
    detached = tmp_path / "detached-first-authority"
    original_replace = audit_evidence_identities._atomic_replace

    def fail_after_parent_swap(target, contents, expected, ledger):
        if target is second_target:
            first_directory.rename(detached)
            first_directory.mkdir()
            (first_directory / first.name).write_bytes(b"attacker")
            raise OSError("injected second publication failure")
        return original_replace(target, contents, expected, ledger)

    monkeypatch.setattr(
        audit_evidence_identities, "_atomic_replace", fail_after_parent_swap
    )
    try:
        with pytest.raises(
            audit_evidence_identities.AuditEvidenceIdentityError,
            match="transaction failed",
        ):
            audit_evidence_identities._transactional_write(
                [(first_target, b"first-after"), (second_target, b"second-after")]
            )
    finally:
        os.close(first_target.directory_fd)
        os.close(second_target.directory_fd)

    assert (first_directory / first.name).read_bytes() == b"attacker"
    assert (detached / first.name).read_bytes() == b"first-before"
    assert second.read_bytes() == b"second-before"


def test_reviewed_authority_transaction_rejects_final_ancestor_swap_with_decoy(
    tmp_path, monkeypatch
) -> None:
    directory = tmp_path / "authority"
    directory.mkdir()
    first = directory / "first.json"
    second = directory / "second.json"
    first.write_bytes(b"first-before")
    second.write_bytes(b"second-before")
    first_target = audit_evidence_identities._pin_target(
        tmp_path, first.relative_to(tmp_path)
    )
    second_target = audit_evidence_identities._pin_target(
        tmp_path, second.relative_to(tmp_path)
    )
    detached = tmp_path / "detached-authority"
    real_validate = audit_evidence_identities._validate_publication
    injected = False

    def swap_ancestor_before_transaction_commit(publication):
        nonlocal injected
        if not injected:
            injected = True
            directory.rename(detached)
            shutil.copytree(detached, directory)
        real_validate(publication)

    monkeypatch.setattr(
        audit_evidence_identities,
        "_validate_publication",
        swap_ancestor_before_transaction_commit,
    )
    try:
        with pytest.raises(
            audit_evidence_identities.AuditEvidenceIdentityError,
            match="transaction failed.*target directory changed",
        ):
            audit_evidence_identities._transactional_write(
                [(first_target, b"first-after"), (second_target, b"second-after")]
            )
    finally:
        os.close(first_target.directory_fd)
        os.close(second_target.directory_fd)

    assert injected
    assert first.read_bytes() == b"first-after"
    assert second.read_bytes() == b"second-after"
    assert (detached / first.name).read_bytes() == b"first-before"
    assert (detached / second.name).read_bytes() == b"second-before"


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
        "audit_only_source_regions": [],
        "product_identities": {},
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
        "audit_only_source_regions": [],
        "product_identities": {},
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
        "generate_from_authority",
        lambda root, authority: json.loads(json.dumps(canonical)),
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

"""Phase 2 hostile-slice measured-representation tests."""

from dataclasses import replace
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

import tools.rom_tests.full_color.phase2_measurements as phase2_measurements
import tools.rom_tests.full_color.baseline_inventory as baseline_inventory

from tools.rom_tests.full_color.discovery_assignment import DiscoveryAssignmentAuthority
from tools.rom_tests.full_color.phase2_measurements import (
    DEFINITION_PATH,
    MINIMUM_STACK_MARGIN,
    PHASE1_STATE_BYTES,
    Phase2Candidate,
    Phase2Measurement,
    Phase2MeasurementError,
    discover_phase2_sources,
    load_definition,
    select_phase2_representation,
    verify_evidence,
    _phase2_roots,
    _verify_audit_product,
    audit_phase2_inventory,
)
from tools.rom_tests.full_color.inventory import WriterInventory

ROOT = Path(__file__).resolve().parents[5]
BASE_COMMIT = "04c98f0a632d7e0a59ebb83dcd5ef1b6b3452cf5"
BASE_TREE = "a02a502375a964268ad9ec00ecf7401d3bc0b9ff"
GIT_OBJECTS = Path(
    subprocess.run(
        ["git", "rev-parse", "--git-path", "objects"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
).resolve()
DEFINITION = load_definition(ROOT / DEFINITION_PATH)
ROM_PRODUCTS = (
    *phase2_measurements.PRODUCTION_PRODUCTS,
    phase2_measurements.PHASE2_AUDIT_PRODUCT,
)


@lru_cache(maxsize=1)
def _checked_in_phase2_proposal() -> str:
    return phase2_measurements._canonical_pretty(
        phase2_measurements.propose_phase2_subjects(ROOT)
    ).decode("utf-8")


def _phase2_apply_fixture(
    tmp_path: Path, monkeypatch, *, git_identity: bool = True
) -> tuple[Path, Path, Path]:
    if git_identity:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        alternates = tmp_path / ".git/objects/info/alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text(f"{GIT_OBJECTS}\n", encoding="utf-8")
        subprocess.run(
            ["git", "update-ref", "refs/heads/reviewed-base", BASE_COMMIT],
            cwd=tmp_path,
            check=True,
        )
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", "refs/heads/reviewed-base"],
            cwd=tmp_path,
            check=True,
        )
        subprocess.run(["git", "checkout", "-q", "HEAD"], cwd=tmp_path, check=True)
    transition_path = ROOT / phase2_measurements.REVIEWED_TRANSITION_PATH
    transition = json.loads(transition_path.read_text(encoding="utf-8"))
    for relative in transition["allowed_tracked_path_sha256"]:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    destination = tmp_path / phase2_measurements.REVIEWED_TRANSITION_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(transition_path, destination)
    proposal = json.loads(_checked_in_phase2_proposal())
    proposal_path = tmp_path / "phase2-subjects.proposal.json"
    proposal_path.write_text(
        json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        phase2_measurements, "propose_phase2_subjects", lambda root: proposal
    )
    target = tmp_path / phase2_measurements.PLANNED_SUBJECTS_PATH
    return tmp_path, proposal_path, target


def _activate_phase4_transition(root: Path) -> None:
    for relative in (
        "specs/full-colors/inventory/assignments.json",
        phase2_measurements.PLANNED_SUBJECTS_PATH,
    ):
        (root / relative).write_bytes(
            subprocess.run(
                ["git", "show", f"{BASE_COMMIT}:{relative}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
        )


def _rewrite_subject_digest(subject: dict[str, object]) -> None:
    canonical = (
        json.dumps(
            {"kind": subject["kind"], "metadata": subject["metadata"]},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    subject["sha256"] = hashlib.sha256(canonical).hexdigest()


def test_reviewed_subject_apply_requires_explicit_authority_review(tmp_path) -> None:
    with pytest.raises(SystemExit):
        phase2_measurements.main(
            [
                "--root",
                str(tmp_path),
                "--apply-proposal",
                str(tmp_path / "proposal.json"),
                "--target",
                str(tmp_path / phase2_measurements.PLANNED_SUBJECTS_PATH),
            ]
        )


def test_reviewed_subject_apply_rejects_noncanonical_or_external_paths(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    parsed = json.loads(proposal.read_text())
    proposal.write_text(json.dumps(parsed), encoding="utf-8")
    with pytest.raises(Phase2MeasurementError, match="not canonical JSON"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)
    parsed["source_sha256"] = "0" * 64
    proposal.write_text(
        json.dumps(parsed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(Phase2MeasurementError, match="stale or semantically changed"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)
    with pytest.raises(Phase2MeasurementError, match="canonical target"):
        phase2_measurements.apply_reviewed_subject_proposal(
            root, root / "outside-proposal.json", root / "wrong-target.json"
        )


def test_reviewed_subject_apply_is_atomic_on_inventory_failure(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    paths = [
        root / "specs/full-colors/inventory" / name
        for name in (
            "assignments.json",
            "writers.json",
            "scenes.json",
            "mutations.json",
        )
    ] + [target]
    before = {path: path.read_bytes() for path in paths}
    original = phase2_measurements._atomic_replace
    failed = False

    def fail_once(path, payload, expected, rollback_ledger=None):
        nonlocal failed
        if path == target and not failed:
            failed = True
            raise OSError("injected transaction failure")
        return original(path, payload, expected, rollback_ledger)

    monkeypatch.setattr(phase2_measurements, "_atomic_replace", fail_once)
    with pytest.raises(
        Phase2MeasurementError,
        match=(
            "Phase 2 authority transaction failed: injected transaction failure; "
            "original authorities restored in their pinned parents; the public "
            "namespace remains refused"
        ),
    ) as error:
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)
    assert isinstance(error.value.__cause__, OSError)
    assert str(error.value.__cause__) == "injected transaction failure"
    assert {path: path.read_bytes() for path in paths} == before


def test_reviewed_subject_apply_accepts_normal_canonical_target(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)

    phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)

    assert json.loads(target.read_text())
    assert not tuple(target.parent.glob(f".{target.name}.*"))


@pytest.mark.parametrize("replacement", ("symlink", "hardlink", "directory"))
def test_reviewed_subject_apply_rejects_unsafe_preexisting_target(
    tmp_path, monkeypatch, replacement: str
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    victim = root / "victim.json"
    victim.write_bytes(b"unrelated authority\n")
    target.unlink()
    if replacement == "symlink":
        target.symlink_to(victim)
    elif replacement == "hardlink":
        os.link(victim, target)
    else:
        target.mkdir()

    with pytest.raises(
        Phase2MeasurementError,
        match="regular non-symlink file with one link",
    ):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)

    assert victim.read_bytes() == b"unrelated authority\n"


@pytest.mark.parametrize(
    "ancestor",
    ("root", "specs", "specs/full-colors", "specs/full-colors/definitions"),
)
def test_reviewed_subject_apply_rejects_symlinked_ancestor(
    tmp_path, monkeypatch, ancestor: str
) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    root, proposal, target = _phase2_apply_fixture(real_root, monkeypatch)
    if ancestor == "root":
        linked_root = tmp_path / "linked-root"
        linked_root.symlink_to(root, target_is_directory=True)
        root = linked_root
        proposal = root / proposal.relative_to(real_root)
        target = root / target.relative_to(real_root)
    else:
        path = root / ancestor
        parked = tmp_path / ancestor.replace("/", "-")
        path.rename(parked)
        path.symlink_to(parked, target_is_directory=True)

    with pytest.raises(
        Phase2MeasurementError, match="ancestor is unavailable or unsafe"
    ):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)


@pytest.mark.parametrize(
    "ancestor",
    ("root", "specs", "specs/full-colors", "specs/full-colors/definitions"),
)
def test_reviewed_subject_apply_rejects_ancestor_swap_immediately_before_replace(
    tmp_path, monkeypatch, ancestor: str
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    root, proposal, target = _phase2_apply_fixture(repository, monkeypatch)
    original_target = target.read_bytes()
    path = root if ancestor == "root" else root / ancestor
    parked = path.with_name(f"{path.name}-parked")
    relative_target = target.relative_to(path)
    real_replace = os.replace
    raced = False

    def race_ancestor(src, dst, *args, **kwargs):
        nonlocal raced
        if dst == target.name and kwargs.get("dst_dir_fd") is not None and not raced:
            raced = True
            real_replace(path, parked)
            path.mkdir()
            (path / relative_target).parent.mkdir(parents=True, exist_ok=True)
            (path / relative_target).write_bytes(b"replacement ancestor target\n")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(phase2_measurements.os, "replace", race_ancestor)
    with pytest.raises(Phase2MeasurementError, match="parent changed during apply"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)

    parked_target = parked / relative_target
    assert parked_target.read_bytes() == original_target
    assert target.read_bytes() == b"replacement ancestor target\n"


def test_reviewed_subject_apply_rejects_ancestor_symlink_back_to_pinned_tree(
    tmp_path, monkeypatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    root, proposal, target = _phase2_apply_fixture(repository, monkeypatch)
    original_target = target.read_bytes()
    ancestor = root / "specs"
    parked = root / "specs-parked"
    real_replace = os.replace
    raced = False

    def race_ancestor(src, dst, *args, **kwargs):
        nonlocal raced
        if dst == target.name and kwargs.get("dst_dir_fd") is not None and not raced:
            raced = True
            real_replace(ancestor, parked)
            ancestor.symlink_to(parked, target_is_directory=True)
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(phase2_measurements.os, "replace", race_ancestor)
    with pytest.raises(
        Phase2MeasurementError, match="cannot validate reviewed authority parent"
    ):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)

    assert (parked / target.relative_to(ancestor)).read_bytes() == original_target


def test_reviewed_subject_apply_rejects_target_swap_and_rolls_back(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    authorities = [
        root / "specs/full-colors/inventory" / name
        for name in (
            "assignments.json",
            "writers.json",
            "scenes.json",
            "mutations.json",
        )
    ]
    before = {path: path.read_bytes() for path in authorities}
    victim = root / "victim.json"
    victim.write_bytes(b"unrelated authority\n")
    original = phase2_measurements._atomic_replace

    def race_target(path, payload, expected, rollback_ledger=None):
        if path == target:
            path.unlink()
            path.symlink_to(victim)
        return original(path, payload, expected, rollback_ledger)

    monkeypatch.setattr(phase2_measurements, "_atomic_replace", race_target)
    with pytest.raises(Phase2MeasurementError, match="changed during apply"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)

    assert {path: path.read_bytes() for path in authorities} == before
    assert victim.read_bytes() == b"unrelated authority\n"
    assert not tuple(target.parent.glob(f".{target.name}.*"))


def test_reviewed_subject_apply_rejects_parent_swap_and_restores_pinned_target(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    original_target = target.read_bytes()
    parent = target.parent
    moved_parent = parent.with_name("definitions-moved")
    real_replace = os.replace
    raced = False

    def race_parent(src, dst, *args, **kwargs):
        nonlocal raced
        if dst == target.name and kwargs.get("dst_dir_fd") is not None and not raced:
            raced = True
            real_replace(parent, moved_parent)
            parent.mkdir()
            (parent / target.name).write_bytes(b"replacement parent target\n")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(phase2_measurements.os, "replace", race_parent)
    with pytest.raises(Phase2MeasurementError, match="parent changed during apply"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)

    assert (moved_parent / target.name).read_bytes() == original_target
    assert target.read_bytes() == b"replacement parent target\n"
    assert not tuple(moved_parent.glob(f".{target.name}.*"))


def test_reviewed_subject_apply_retains_backup_when_postpublish_restore_fails(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    assignment = root / "specs/full-colors/inventory/assignments.json"
    original = assignment.read_bytes()
    real_directory_identity = phase2_measurements._directory_identity
    real_replace = os.replace
    validations = 0

    def fail_postpublish(directory, directory_fd):
        nonlocal validations
        if directory == assignment.parent:
            validations += 1
            if validations == 3:
                raise Phase2MeasurementError("injected postpublish validation failure")
        return real_directory_identity(directory, directory_fd)

    def fail_restore(src, dst, *args, **kwargs):
        if isinstance(src, str) and src.endswith(".restore"):
            raise OSError("injected restore failure")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(phase2_measurements, "_directory_identity", fail_postpublish)
    monkeypatch.setattr(phase2_measurements.os, "replace", fail_restore)
    with pytest.raises(
        Phase2MeasurementError,
        match="rollback was incomplete.*recoverable backup retained",
    ):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)

    backups = tuple(assignment.parent.glob(f".{assignment.name}.*.rollback"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original


def test_reviewed_subject_rollback_rejects_backup_symlink_substitution(
    tmp_path,
) -> None:
    target = tmp_path / "authority.json"
    original = b'{"authority":"reviewed"}\n'
    target.write_bytes(original)
    publications = []
    expected = phase2_measurements._authority_identity(
        target, label="reviewed authority"
    )
    phase2_measurements._atomic_replace(
        target, b'{"authority":"new"}\n', expected, publications
    )
    publication = publications[0]
    backup = tmp_path / publication.backup_name
    victim = tmp_path / "victim.json"
    victim.write_bytes(b"unrelated\n")
    backup.unlink()
    backup.symlink_to(victim)

    with pytest.raises(Phase2MeasurementError, match="backup changed"):
        phase2_measurements._restore_publication(publication)

    assert target.read_bytes() == b'{"authority":"new"}\n'
    assert victim.read_bytes() == b"unrelated\n"


@pytest.mark.parametrize("operation", ("rollback", "finalize"))
def test_reviewed_subject_transaction_rejects_backup_content_mutation(
    tmp_path, operation: str
) -> None:
    target = tmp_path / "authority.json"
    target.write_bytes(b'{"authority":"reviewed"}\n')
    publications = []
    expected = phase2_measurements._authority_identity(
        target, label="reviewed authority"
    )
    phase2_measurements._atomic_replace(
        target, b'{"authority":"new"}\n', expected, publications
    )
    publication = publications[0]
    backup = tmp_path / publication.backup_name
    backup.write_bytes(b'{"authority":"hostile"}\n')

    with pytest.raises(Phase2MeasurementError, match="backup changed"):
        if operation == "rollback":
            phase2_measurements._restore_publication(publication)
        else:
            phase2_measurements._finalize_publication(publication)

    assert target.read_bytes() == b'{"authority":"new"}\n'
    assert backup.read_bytes() == b'{"authority":"hostile"}\n'


def test_reviewed_subject_rollback_uses_pinned_bytes_across_last_moment_swap(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "authority.json"
    original = b'{"authority":"reviewed"}\n'
    target.write_bytes(original)
    publications = []
    expected = phase2_measurements._authority_identity(
        target, label="reviewed authority"
    )
    phase2_measurements._atomic_replace(
        target, b'{"authority":"new"}\n', expected, publications
    )
    publication = publications[0]
    backup = tmp_path / publication.backup_name
    parked = tmp_path / "parked-backup"
    victim = tmp_path / "victim.json"
    victim.write_bytes(b"unrelated\n")
    real_read = phase2_measurements._read_pinned_backup
    calls = 0

    def swap_after_validation(selected):
        nonlocal calls
        payload = real_read(selected)
        calls += 1
        if calls == 1:
            backup.rename(parked)
            backup.symlink_to(victim)
        return payload

    monkeypatch.setattr(
        phase2_measurements, "_read_pinned_backup", swap_after_validation
    )
    with pytest.raises(Phase2MeasurementError, match="backup changed"):
        phase2_measurements._restore_publication(publication)

    assert target.read_bytes() == original
    assert parked.read_bytes() == original
    assert victim.read_bytes() == b"unrelated\n"


def test_reviewed_subject_finalize_rejects_last_moment_backup_substitution(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "authority.json"
    original = b'{"authority":"reviewed"}\n'
    target.write_bytes(original)
    publications = []
    expected = phase2_measurements._authority_identity(
        target, label="reviewed authority"
    )
    phase2_measurements._atomic_replace(
        target, b'{"authority":"new"}\n', expected, publications
    )
    publication = publications[0]
    backup = tmp_path / publication.backup_name
    parked = tmp_path / "parked-backup"
    victim = tmp_path / "victim.json"
    victim.write_bytes(b"unrelated\n")
    real_read = phase2_measurements._read_pinned_backup

    def swap_after_validation(selected):
        payload = real_read(selected)
        backup.rename(parked)
        backup.symlink_to(victim)
        return payload

    monkeypatch.setattr(
        phase2_measurements, "_read_pinned_backup", swap_after_validation
    )
    with pytest.raises(Phase2MeasurementError, match="backup changed"):
        phase2_measurements._finalize_publication(publication)

    assert target.read_bytes() == b'{"authority":"new"}\n'
    assert parked.read_bytes() == original
    assert victim.read_bytes() == b"unrelated\n"


def test_reviewed_subject_finalize_rejects_mutation_during_unlink(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "authority.json"
    target.write_bytes(b'{"authority":"reviewed"}\n')
    publications = []
    expected = phase2_measurements._authority_identity(
        target, label="reviewed authority"
    )
    phase2_measurements._atomic_replace(
        target, b'{"authority":"new"}\n', expected, publications
    )
    publication = publications[0]
    backup = tmp_path / publication.backup_name
    real_unlink = os.unlink

    def mutate_before_unlink(path, *args, **kwargs):
        if path == publication.backup_name:
            backup.write_bytes(b'{"authority":"hostile"}\n')
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(phase2_measurements.os, "unlink", mutate_before_unlink)
    with pytest.raises(Phase2MeasurementError, match="backup changed"):
        phase2_measurements._finalize_publication(publication)

    assert target.read_bytes() == b'{"authority":"new"}\n'
    assert not backup.exists()


def test_reviewed_subject_transaction_rejects_final_ancestor_swap_with_decoy(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    authority_directory = root / "specs/full-colors/inventory"
    detached = root / "detached-inventory"
    assignment = authority_directory / "assignments.json"
    before = assignment.read_bytes()
    real_validate = phase2_measurements._validate_publication
    injected = False

    def swap_ancestor_before_transaction_commit(publication):
        nonlocal injected
        if not injected and publication.path.parent == authority_directory:
            injected = True
            authority_directory.rename(detached)
            shutil.copytree(detached, authority_directory)
        real_validate(publication)

    monkeypatch.setattr(
        phase2_measurements,
        "_validate_publication",
        swap_ancestor_before_transaction_commit,
    )
    with pytest.raises(Phase2MeasurementError, match="parent changed during apply"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)

    assert injected
    assert authority_directory.stat().st_ino != detached.stat().st_ino
    assert assignment.read_bytes() == before
    assert (detached / assignment.name).read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    ("opcode", "call_path", "address", "destination_bounds"),
)
def test_reviewed_subject_apply_rejects_rom_semantic_drift(
    tmp_path, monkeypatch, mutation: str
) -> None:
    root, proposal_path, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    proposal = json.loads(proposal_path.read_text())
    subject = proposal["products"][phase2_measurements.PHASE2_AUDIT_PRODUCT][
        "rom_subjects"
    ][0]
    metadata = subject["metadata"]
    if mutation == "opcode":
        metadata["bytes"] = "00" + metadata["bytes"][2:]
    elif mutation == "call_path":
        metadata["call_path"].append("HOSTILE_UNREVIEWED_ANCESTOR")
    elif mutation == "address":
        metadata["address"] += 1
        metadata["rom_offset"] += 1
    else:
        metadata["destination_low"] += 1
        metadata["destination_high"] += 1
    _rewrite_subject_digest(subject)
    proposal_path.write_text(
        json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        phase2_measurements, "propose_phase2_subjects", lambda root: proposal
    )

    with pytest.raises(Phase2MeasurementError, match="reviewed ROM subject semantics"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal_path, target)


def test_current_phase2_authorities_reproduce_exactly_from_pinned_base_verifier(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    relative_paths = (
        "specs/full-colors/inventory/assignments.json",
        "specs/full-colors/inventory/writers.json",
        "specs/full-colors/inventory/scenes.json",
        "specs/full-colors/inventory/mutations.json",
        phase2_measurements.PLANNED_SUBJECTS_PATH,
    )
    expected = {relative: (ROOT / relative).read_bytes() for relative in relative_paths}
    for relative in relative_paths:
        baseline = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        (root / relative).write_bytes(baseline)

    for product in phase2_measurements.PRODUCT_ARTIFACTS.values():
        for suffix in (".gbc", ".map", ".sym"):
            shutil.copy2(ROOT / f"{product}{suffix}", root / f"{product}{suffix}")
    proposal.unlink()
    module = "tools.rom_tests.full_color.phase2_measurements"
    subprocess.run(
        [
            sys.executable,
            "-m",
            module,
            "--root",
            str(root),
            "--proposal-output",
            str(proposal),
        ],
        cwd=root,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            module,
            "--root",
            str(root),
            "--apply-proposal",
            str(proposal),
            "--target",
            str(target),
            "--authority-reviewed",
        ],
        cwd=root,
        check=True,
    )

    assert {
        relative: (root / relative).read_bytes() for relative in relative_paths
    } == expected


def test_reviewed_phase4_transition_authority_is_hash_bound(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    _activate_phase4_transition(root)
    transition = root / phase2_measurements.REVIEWED_TRANSITION_PATH
    transition.write_bytes(transition.read_bytes() + b" ")

    with pytest.raises(Phase2MeasurementError, match="transition authority changed"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)


def test_reviewed_transition_rebind_preserves_semantics_and_updates_carrier(
    tmp_path, monkeypatch
) -> None:
    root, _, _ = _phase2_apply_fixture(tmp_path, monkeypatch)
    transition_path = root / phase2_measurements.REVIEWED_TRANSITION_PATH
    before = json.loads(transition_path.read_text(encoding="utf-8"))
    proposal = phase2_measurements.propose_reviewed_transition_rebind(root)
    proposal_path = root / "reviewed-transition.proposal.json"
    proposal_path.write_bytes(phase2_measurements._canonical_pretty(proposal))

    phase2_measurements.apply_reviewed_transition_rebind(root, proposal_path)

    after = json.loads(transition_path.read_text(encoding="utf-8"))
    assert after["reason"] == before["reason"]
    assert after["subject_transitions"] == before["subject_transitions"]
    transition_digest = hashlib.sha256(transition_path.read_bytes()).hexdigest()
    verifier = (root / phase2_measurements.VERIFIER_PATH).read_bytes()
    assert f'    "{transition_digest}"'.encode() in verifier
    normalized_digest = hashlib.sha256(
        phase2_measurements._normalized_verifier_source(verifier)
    ).hexdigest()
    assert after["verifier_normalized_sha256"] == normalized_digest
    assert (
        normalized_digest
        in after["allowed_tracked_path_sha256"][phase2_measurements.VERIFIER_PATH]
    )


def test_reviewed_transition_rebind_rejects_stale_proposal(
    tmp_path, monkeypatch
) -> None:
    root, _, _ = _phase2_apply_fixture(tmp_path, monkeypatch)
    proposal = phase2_measurements.propose_reviewed_transition_rebind(root)
    proposal_path = root / "reviewed-transition.proposal.json"
    proposal_path.write_bytes(phase2_measurements._canonical_pretty(proposal))
    changed = root / "docs/ADDING_CONTENT.md"
    changed.write_bytes(changed.read_bytes() + b"\n")

    with pytest.raises(
        Phase2MeasurementError,
        match="stale or semantically changed reviewed-transition rebind proposal",
    ):
        phase2_measurements.apply_reviewed_transition_rebind(root, proposal_path)


def test_reviewed_phase4_transition_rejects_missing_git_worktree(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(
        tmp_path, monkeypatch, git_identity=False
    )
    _activate_phase4_transition(root)

    with pytest.raises(Phase2MeasurementError, match="exact Git worktree"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)


def test_reviewed_phase4_transition_rejects_different_initialized_repository(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(
        tmp_path, monkeypatch, git_identity=False
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "specs", "data"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Hostile Fixture",
            "-c",
            "user.email=hostile@example.invalid",
            "commit",
            "-q",
            "-m",
            "different repository",
        ],
        cwd=root,
        check=True,
    )
    _activate_phase4_transition(root)

    with pytest.raises(Phase2MeasurementError, match="base commit"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)


def test_reviewed_phase4_transition_rejects_wrong_head_with_same_base_tree(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    _activate_phase4_transition(root)
    wrong_commit = (
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Hostile Fixture",
                "-c",
                "user.email=hostile@example.invalid",
                "commit-tree",
                BASE_TREE,
                "-p",
                BASE_COMMIT,
            ],
            cwd=root,
            check=True,
            input=b"wrong head\n",
            capture_output=True,
        )
        .stdout.decode()
        .strip()
    )
    subprocess.run(["git", "update-ref", "HEAD", wrong_commit], cwd=root, check=True)

    with pytest.raises(Phase2MeasurementError, match="base commit"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)


def test_reviewed_phase4_transition_rejects_unrelated_tracked_edit(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    _activate_phase4_transition(root)
    unrelated = (
        root / "specs/full-colors/definitions/phase2-hostile-slice-representation.json"
    )
    unrelated.write_bytes(unrelated.read_bytes() + b" ")

    with pytest.raises(Phase2MeasurementError, match="forbids modified tracked path"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)


def test_reviewed_phase4_transition_accepts_hash_bound_intended_dirty_paths(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    _activate_phase4_transition(root)

    phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)

    assert (
        target.read_bytes()
        == (ROOT / phase2_measurements.PLANNED_SUBJECTS_PATH).read_bytes()
    )


def test_reviewed_phase4_transition_rejects_mm_index_bypass(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    _activate_phase4_transition(root)
    relative = phase2_measurements.VERIFIER_PATH
    path = root / relative
    approved = path.read_bytes()
    path.write_bytes(approved + b"\n# staged hostile verifier\n")
    subprocess.run(["git", "add", "--", relative], cwd=root, check=True)
    path.write_bytes(approved)

    with pytest.raises(Phase2MeasurementError, match="clean Git index"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)


@pytest.mark.parametrize("staged_change", ("add", "delete", "rename", "copy"))
def test_reviewed_phase4_transition_rejects_every_staged_change_kind(
    tmp_path, monkeypatch, staged_change: str
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    _activate_phase4_transition(root)
    source = root / "README.md"
    if staged_change == "add":
        added = root / "staged-added.txt"
        added.write_text("hostile staged add\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", added.name], cwd=root, check=True)
    elif staged_change == "delete":
        source.unlink()
        subprocess.run(["git", "add", "--", source.name], cwd=root, check=True)
    elif staged_change == "rename":
        subprocess.run(
            ["git", "mv", "--", source.name, "staged-renamed.md"],
            cwd=root,
            check=True,
        )
    else:
        copied = root / "staged-copy.md"
        shutil.copy2(source, copied)
        subprocess.run(["git", "add", "--", copied.name], cwd=root, check=True)

    with pytest.raises(Phase2MeasurementError, match="clean Git index"):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)


def test_reviewed_phase4_transition_ignores_untracked_build_artifacts(
    tmp_path, monkeypatch
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    _activate_phase4_transition(root)
    (root / "pokeyellow.gbc").write_bytes(b"disposable build artifact")
    disposable = root / "test-results/phase2"
    disposable.mkdir(parents=True)
    (disposable / "report.json").write_text("{}\n", encoding="utf-8")
    preemdeck = root / ".preemdeck/cache"
    preemdeck.mkdir(parents=True)
    (preemdeck / "state.json").write_text("{}\n", encoding="utf-8")

    phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)


@pytest.mark.parametrize(
    ("field", "expected_error"),
    (
        ("base_commit", "base commit"),
        ("base_tree", "base tree"),
        ("allowlist_hash", "tracked path content changed"),
    ),
)
def test_reviewed_phase4_transition_rejects_identity_or_allowlist_tamper(
    tmp_path, monkeypatch, field: str, expected_error: str
) -> None:
    root, proposal, target = _phase2_apply_fixture(tmp_path, monkeypatch)
    _activate_phase4_transition(root)
    transition_path = root / phase2_measurements.REVIEWED_TRANSITION_PATH
    transition = json.loads(transition_path.read_text())
    if field == "allowlist_hash":
        relative = "specs/full-colors/definitions/phase1-audit-source-transition.json"
        transition["allowed_tracked_path_sha256"][relative] = ["0" * 64]
    else:
        transition[field] = "0" * 40
    raw_transition = (json.dumps(transition, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    transition_path.write_bytes(raw_transition)
    monkeypatch.setattr(
        phase2_measurements,
        "REVIEWED_TRANSITION_SHA256",
        hashlib.sha256(raw_transition).hexdigest(),
    )

    with pytest.raises(Phase2MeasurementError, match=expected_error):
        phase2_measurements.apply_reviewed_subject_proposal(root, proposal, target)


def patch_product_report(monkeypatch, product, changed) -> None:
    discover_product = phase2_measurements.discover_phase2_rom_product
    monkeypatch.setattr(
        phase2_measurements,
        "discover_phase2_rom_product",
        lambda root, selected: (
            changed if selected == product else discover_product(root, selected)
        ),
    )


def shared_candidate_dispositions():
    return phase2_measurements._load_planned_subjects(ROOT, closed=True)[3]


def linked_pipeline_sections(
    *, placement: tuple[int, int, int] = (0x3B, 0x452B, 0x552A)
):
    bank, start, end = placement
    return {
        product: {
            ("ROMX", bank): [(start, end, phase2_measurements.PHASE2_PIPELINE_SECTION)]
        }
        for product in ROM_PRODUCTS
    }


def audit_product_fixture(root: Path) -> None:
    roots = _phase2_roots()
    marker_address = 0x4000
    table_address = marker_address + 8
    root_addresses = tuple(0x4100 + 2 * index for index in range(len(roots)))
    rom = bytearray(0x8000)
    rom[0x4000:0x4008] = b"P2AUDIT1"
    for index, address in enumerate(root_addresses):
        start = table_address + 2 * index
        rom[start : start + 2] = address.to_bytes(2, "little")
    (root / "pokeyellow_phase2_audit.gbc").write_bytes(rom)
    symbols = [
        f"01:{marker_address:04x} Phase2AuditProvenance",
        f"01:{table_address:04x} Phase2AuditRoots",
        f"01:{table_address + 2 * len(roots):04x} Phase2AuditRootsEnd",
        *(f"01:{address:04x} {name}" for name, address in zip(roots, root_addresses)),
    ]
    (root / "pokeyellow_phase2_audit.sym").write_text(
        "\n".join(symbols) + "\n", encoding="utf-8"
    )
    (root / "pokeyellow_phase2_audit.map").write_text(
        "ROMX bank #1:\n"
        '\tSECTION: $4000-$4040 ($0041 bytes) ["Phase 2 Audit Provenance"]\n',
        encoding="utf-8",
    )
    for stem in ("pokeyellow", "pokeyellow_debug", "pokeyellow_vc"):
        (root / f"{stem}.gbc").write_bytes(b"normal-product")
        (root / f"{stem}.sym").write_text("00:0000 NormalSymbol\n", encoding="utf-8")
        (root / f"{stem}.map").write_text(
            'ROM0 bank #0:\n\tSECTION: $0000 ($0001 bytes) ["Normal"]\n',
            encoding="utf-8",
        )


def candidate(**changes: object) -> Phase2Candidate:
    values = {
        "wram_bank": 2,
        "wram_start": 0xD00D,
        "wram_end": 0xDFFF,
        "sram_bank": 3,
        "sram_start": 0xBEAF,
        "sram_end": 0xBFFF,
        "rom_bank": 0x3B,
        "rom_start": 0x4754,
        "rom_end": 0x7FFF,
        "stack_margin_bytes": MINIMUM_STACK_MARGIN,
        "ownership_adjacent": True,
    }
    values.update(changes)
    return Phase2Candidate(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("wrong-row", "wrong row"),
        ("missing", "missing pokeyellow_phase2_audit subject"),
        ("extra", "extra pokeyellow_phase2_audit subject"),
        ("stale-product", "missing pokeyellow_phase2_audit subject"),
        ("stale-hash", "stale pokeyellow_phase2_audit source identity"),
        ("root-mismatch", "missing pokeyellow_phase2_audit subject"),
    ],
)
def test_explicit_audit_product_assignment_coverage_fails_closed(
    mutation, message
) -> None:
    hashes = {
        "source_sha256": "1" * 64,
        "rom_sha256": "2" * 64,
        "sym_sha256": "3" * 64,
        "map_sha256": "4" * 64,
    }

    def row(identifier, digest, row_id, product="pokeyellow_phase2_audit"):
        return SimpleNamespace(
            id=identifier,
            product=product,
            row_id=row_id,
            subject=SimpleNamespace(sha256=digest),
            evidence=SimpleNamespace(**hashes),
        )

    rows = [row("AS-A", "a", "WR-P2-A"), row("AS-B", "b", "MU-P2-B")]
    if mutation == "wrong-row":
        rows[0].row_id = "WR-P2-WRONG"
    elif mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append(row("AS-C", "c", "WR-P2-A"))
    elif mutation == "stale-product":
        rows[0].product = "pokeyellow_debug"
    elif mutation == "stale-hash":
        rows[0].evidence.source_sha256 = "0" * 64
    else:
        rows[0].subject.sha256 = "root-mutated"

    authority = SimpleNamespace(
        for_product=lambda product: SimpleNamespace(
            rows=tuple(item for item in rows if item.product == product)
        )
    )
    with pytest.raises(ValueError, match=message):
        phase2_measurements._validate_product_assignment_coverage(
            authority,
            {"a": "WR-P2-A", "b": "MU-P2-B"},
            hashes,
            product=phase2_measurements.PHASE2_AUDIT_PRODUCT,
        )


def test_phase2_product_apis_have_no_implicit_compatibility_paths() -> None:
    assert "discover_phase2_rom" not in vars(phase2_measurements)
    assert "_validate_audit_assignment_coverage" not in vars(phase2_measurements)
    with pytest.raises(TypeError):
        phase2_measurements._validate_product_assignment_coverage(
            SimpleNamespace(), {}, {}
        )
    with pytest.raises(Phase2MeasurementError, match="unknown Phase 2 link product"):
        phase2_measurements.discover_phase2_rom_product(ROOT, "implicit-product")


def measurement(*, candidates: tuple[Phase2Candidate, ...] | None = None):
    return Phase2Measurement(
        {"pokeyellow.gbc": "1" * 64},
        DEFINITION,
        DEFINITION.classes,
        DEFINITION.descriptor_bytes,
        DEFINITION.scratch_bytes,
        candidates or (candidate(),),
    )


def test_current_measurement_selects_concrete_bounded_representation() -> None:
    decision = select_phase2_representation(measurement())
    assert decision.descriptor_bytes == 20
    assert decision.capacity == 8
    assert decision.scratch_bytes == 808
    assert decision.wram_bank == 2
    assert decision.wram_start == 0xD00D
    assert decision.rom_bank == 0x3B
    assert decision.debug_carrier_capacity >= DEFINITION.aggregate_high_water
    assert decision.ownership_state_bytes == PHASE1_STATE_BYTES
    assert decision.normal_rom_reachable is True
    assert decision.inventory_audit == {}
    assert decision.to_dict()["activation"] == {
        "normal_rom_reachable": True,
        "production_products": list(phase2_measurements.PRODUCTION_PRODUCTS),
        "audit_diagnostics": {
            "guard": phase2_measurements.AUDIT_GUARD,
            "product": phase2_measurements.PHASE2_AUDIT_PRODUCT,
        },
    }


def test_selection_and_json_are_independent_of_candidate_order() -> None:
    adjacent = candidate()
    other = candidate(rom_bank=0x20, rom_start=0x5000, ownership_adjacent=False)
    first = select_phase2_representation(measurement(candidates=(other, adjacent)))
    second = select_phase2_representation(measurement(candidates=(adjacent, other)))
    assert first == second
    assert first.to_json() == second.to_json()
    assert first.rom_bank == 0x3B


def test_common_linked_pipeline_section_is_the_exact_rom_candidate() -> None:
    assert phase2_measurements._common_linked_pipeline_section(
        linked_pipeline_sections()
    ) == (0x3B, 0x452B, 0x552A)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "missing linked ROMX section"),
        ("mismatched", "placement differs across products"),
        ("undersized", "is undersized"),
        ("forbidden", "uses forbidden ROM bank"),
    ],
)
def test_common_linked_pipeline_section_fails_closed(mutation, message) -> None:
    sections = linked_pipeline_sections()
    if mutation == "missing":
        sections[phase2_measurements.VC_PRODUCT] = {}
    elif mutation == "mismatched":
        sections[phase2_measurements.DEBUG_PRODUCT] = linked_pipeline_sections(
            placement=(0x3B, 0x452C, 0x552B)
        )[phase2_measurements.DEBUG_PRODUCT]
    elif mutation == "undersized":
        sections = linked_pipeline_sections(placement=(0x3B, 0x452B, 0x5529))
    else:
        forbidden_bank = min(phase2_measurements.FORBIDDEN_ROM_BANKS)
        sections = linked_pipeline_sections(placement=(forbidden_bank, 0x452B, 0x552A))

    with pytest.raises(Phase2MeasurementError, match=message):
        phase2_measurements._common_linked_pipeline_section(sections)


def test_required_work_defers_with_observable_retry() -> None:
    decision = select_phase2_representation(measurement())
    assert all(
        item.required_work_policy == "DEFERRED_CALLER_RETRY"
        for item in decision.request_classes
    )
    assert all(item.retry_observable for item in decision.request_classes)


def test_equivalent_work_coalesces_at_capacity() -> None:
    decision = select_phase2_representation(measurement())
    coalesced = {
        item.name
        for item in decision.request_classes
        if item.capacity_equivalence_policy == "COALESCED_FINAL_STATE"
    }
    assert "MAP_ROW_PAIRED" in coalesced
    assert "MAP_COLUMN_PAIRED" in coalesced
    assert "OAM_BATCH_AND_DMA" not in coalesced


def test_required_work_without_retry_observation_is_rejected() -> None:
    broken = replace(DEFINITION.classes[0], retry_observable=False)
    with pytest.raises(Phase2MeasurementError, match="lacks runtime-observable retry"):
        changed = replace(DEFINITION, classes=(broken, *DEFINITION.classes[1:]))
        select_phase2_representation(
            replace(measurement(), definition=changed, classes=changed.classes)
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"overlaps": ("Existing",)}, "no non-overlapping"),
        ({"stack_margin_bytes": MINIMUM_STACK_MARGIN - 1}, "no non-overlapping"),
        ({"rom_bank": 0x2C}, "no non-overlapping"),
    ],
)
def test_overlap_margin_and_forbidden_bank_fail_closed(changes, message) -> None:
    with pytest.raises(Phase2MeasurementError, match=message):
        select_phase2_representation(measurement(candidates=(candidate(**changes),)))


def test_capacity_plus_one_does_not_fit_wram() -> None:
    required = (
        DEFINITION.scratch_bytes
        + DEFINITION.descriptor_bytes * DEFINITION.aggregate_high_water
    )
    exact = candidate(wram_end=0xD00D + required - 1)
    selected = select_phase2_representation(measurement(candidates=(exact,)))
    assert selected.wram_end == exact.wram_end
    too_small = replace(exact, wram_end=exact.wram_end - 1)
    with pytest.raises(Phase2MeasurementError, match="candidate fits measured"):
        select_phase2_representation(measurement(candidates=(too_small,)))


def test_too_small_adjacent_candidate_cannot_mask_a_fitting_candidate() -> None:
    too_small = candidate(wram_end=0xD010)
    fitting = candidate(rom_bank=0x20, rom_start=0x5000, ownership_adjacent=False)
    selected = select_phase2_representation(
        measurement(candidates=(too_small, fitting))
    )
    assert selected.rom_bank == 0x20


def test_debug_carrier_capacity_is_blocking() -> None:
    bytes_for_too_few = (
        DEFINITION.debug_header_bytes
        + DEFINITION.debug_record_bytes * (DEFINITION.aggregate_high_water - 1)
    )
    too_small = candidate(sram_end=0xBEAF + bytes_for_too_few - 1)
    with pytest.raises(Phase2MeasurementError, match="candidate fits measured"):
        select_phase2_representation(measurement(candidates=(too_small,)))


def test_descriptor_scratch_and_ownership_abi_are_exact() -> None:
    with pytest.raises(Phase2MeasurementError, match="descriptor byte cost"):
        select_phase2_representation(
            replace(measurement(), descriptor_bytes=DEFINITION.descriptor_bytes + 1)
        )
    with pytest.raises(Phase2MeasurementError, match="scratch byte cost"):
        select_phase2_representation(
            replace(measurement(), scratch_bytes=DEFINITION.scratch_bytes + 1)
        )
    with pytest.raises(Phase2MeasurementError, match="ownership ABI"):
        select_phase2_representation(
            replace(measurement(), ownership_state_bytes=PHASE1_STATE_BYTES + 1)
        )


def test_concrete_definition_mutations_change_measured_sizes_and_pressure(
    tmp_path,
) -> None:
    raw = json.loads((ROOT / DEFINITION_PATH).read_text(encoding="utf-8"))
    raw["descriptor"][0]["bytes"] += 1
    raw["scratch"][0]["bytes"] += 1
    raw["scenario"][1]["enqueue"].append(
        {
            "class": "MAP_COLUMN_PAIRED",
            "destination": "column-8",
            "desired_state": "east-8",
        }
    )
    path = tmp_path / "definition.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    changed = load_definition(path)
    selected = select_phase2_representation(
        replace(
            measurement(),
            definition=changed,
            classes=changed.classes,
            descriptor_bytes=changed.descriptor_bytes,
            scratch_bytes=changed.scratch_bytes,
        )
    )
    assert changed.descriptor_bytes == DEFINITION.descriptor_bytes + 1
    assert changed.scratch_bytes == DEFINITION.scratch_bytes + 1
    assert selected.capacity == DEFINITION.aggregate_high_water + 1


def test_pressure_replay_coalesces_equivalent_destination_but_counts_resident_work(
    tmp_path,
) -> None:
    raw = json.loads((ROOT / DEFINITION_PATH).read_text(encoding="utf-8"))
    horizontal = raw["scenario"][1]["enqueue"]
    for index, request in enumerate(horizontal):
        request["destination"] = "same-column"
        request["desired_state"] = "same-final-state"
    path = tmp_path / "coalesced.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    changed = load_definition(path)
    assert changed.class_high_water["MAP_COLUMN_PAIRED"] == 1


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("owner", "RENDERER_YELLOW"),
        ("generation", "generation-distinct"),
        ("visible_boundary", "DISTINCT_VISIBLE_BOUNDARY"),
    ],
)
def test_same_destination_is_not_equivalent_across_identity_boundaries(
    tmp_path, field, replacement
) -> None:
    raw = json.loads((ROOT / DEFINITION_PATH).read_text(encoding="utf-8"))
    step = raw["scenario"][1]
    for request in step["enqueue"]:
        request["destination"] = "same-column"
        request["desired_state"] = "same-final-state"
    control_path = tmp_path / "control.json"
    control_path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_definition(control_path).class_high_water["MAP_COLUMN_PAIRED"] == 1
    split = json.loads(json.dumps(step))
    split["identity"][field] = replacement
    split["enqueue"] = split["enqueue"][4:]
    split.pop("drain", None)
    step["enqueue"] = step["enqueue"][:4]
    raw["scenario"].insert(2, split)
    changed_path = tmp_path / "changed.json"
    changed_path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_definition(changed_path).class_high_water["MAP_COLUMN_PAIRED"] == 2


def test_same_destination_with_distinct_desired_state_is_not_equivalent(
    tmp_path,
) -> None:
    raw = json.loads((ROOT / DEFINITION_PATH).read_text(encoding="utf-8"))
    horizontal = raw["scenario"][1]["enqueue"]
    for index, request in enumerate(horizontal):
        request["destination"] = "same-column"
        request["desired_state"] = f"revision-{index}"
    path = tmp_path / "distinct-state.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_definition(path).class_high_water["MAP_COLUMN_PAIRED"] == 8


@pytest.mark.parametrize("mutation", ["omit", "unknown"])
def test_definition_identity_fields_fail_closed(tmp_path, mutation) -> None:
    raw = json.loads((ROOT / DEFINITION_PATH).read_text(encoding="utf-8"))
    identity = raw["scenario"][0]["identity"]
    if mutation == "omit":
        identity.pop("owner")
    else:
        identity["surprise"] = "not-authoritative"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(Phase2MeasurementError, match="identity requires"):
        load_definition(path)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda raw: raw["request_classes"][0].__setitem__("required_work", "true"),
            "expected boolean",
        ),
        (
            lambda raw: raw["descriptor"][0].__setitem__("bytes", True),
            "positive integer",
        ),
        (
            lambda raw: raw["scenario"][0].__setitem__("drain", "false"),
            "expected boolean",
        ),
        (
            lambda raw: raw["scenario"][0]["identity"].__setitem__("owner", 7),
            "non-empty string",
        ),
        (
            lambda raw: raw["scenario"][0]["identity"].__setitem__(
                "resources", ["UNKNOWN"]
            ),
            "unknown resources",
        ),
        (
            lambda raw: raw["scenario"][1]["identity"].__setitem__(
                "resources", ["BG_MAP"]
            ),
            "resources are incompatible",
        ),
    ],
)
def test_definition_rejects_wrong_scalar_types_and_resource_contracts(
    tmp_path, mutate, message
) -> None:
    raw = json.loads((ROOT / DEFINITION_PATH).read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(Phase2MeasurementError, match=message):
        load_definition(path)


def test_definition_rejects_duplicate_json_keys(tmp_path) -> None:
    text = (ROOT / DEFINITION_PATH).read_text(encoding="utf-8")
    path = tmp_path / "duplicate.json"
    path.write_text(
        text.replace('"schema":', '"schema": "duplicate", "schema":', 1),
        encoding="utf-8",
    )
    with pytest.raises(Phase2MeasurementError, match="duplicate JSON key"):
        load_definition(path)


@pytest.mark.parametrize("mode", ["delete", "unreview", "substitute"])
def test_standalone_audit_enforces_exact_phase2_row_ids(monkeypatch, mode) -> None:
    original = WriterInventory.load(ROOT / "specs/full-colors/inventory/writers.json")
    raw = original.to_dict()
    planned_index = next(
        index
        for index, row in enumerate(raw["rows"])
        if row["id"] in phase2_measurements.PHASE2_PLANNED_ROW_IDS
    )
    if mode == "delete":
        raw["rows"].pop(planned_index)
    elif mode == "unreview":
        raw["rows"][planned_index]["evidence"]["reviewed"] = False
    else:
        raw["rows"][planned_index]["id"] = "WR-P2-SUBSTITUTED"
        raw["rows"].sort(key=lambda row: row["id"])
    changed = WriterInventory.from_dict(raw)
    monkeypatch.setattr(
        phase2_measurements.WriterInventory, "load", lambda path: changed
    )
    with pytest.raises(
        Phase2MeasurementError,
        match="exact closed set|transition all 18 rows",
    ):
        audit_phase2_inventory(ROOT)


@pytest.mark.parametrize(
    ("kind", "product"),
    (("source", None), *(("rom", product) for product in ROM_PRODUCTS)),
)
def test_same_coordinate_semantic_drift_fails_canonical_subject_audit(
    monkeypatch, kind, product
) -> None:
    if kind == "source":
        report = phase2_measurements.discover_phase2_sources(ROOT)
        index = next(
            index
            for index, finding in enumerate(report.findings)
            if finding.mechanism == "configured-root"
            and finding.symbol == "UpdateMovingBgTiles"
        )
        findings = list(report.findings)
        findings[index] = replace(findings[index], resource="SEMANTIC_DRIFT")
        monkeypatch.setattr(
            phase2_measurements,
            "discover_phase2_sources",
            lambda root: replace(report, findings=tuple(findings)),
        )
    else:
        report = phase2_measurements.discover_phase2_rom_product(ROOT, product)
        index = next(
            index
            for index, finding in enumerate(report.findings)
            if finding.mechanism == "root-entry"
            and finding.root == "UpdateMovingBgTiles"
        )
        findings = list(report.findings)
        findings[index] = replace(findings[index], bytes="00")
        patch_product_report(
            monkeypatch,
            product,
            replace(report, findings=tuple(findings)),
        )
    with pytest.raises(Phase2MeasurementError, match="subjects="):
        audit_phase2_inventory(ROOT)


@pytest.mark.parametrize(
    ("kind", "product"),
    (
        ("source", None),
        *((kind, product) for kind in ("rom", "candidate") for product in ROM_PRODUCTS),
    ),
)
@pytest.mark.parametrize("mutation", ["omit", "alter"])
def test_descendant_subject_closure_is_mutation_sensitive(
    monkeypatch, kind, product, mutation
) -> None:
    if kind == "source":
        report = phase2_measurements.discover_phase2_sources(ROOT)
        index = next(
            index
            for index, finding in enumerate(report.findings)
            if finding.symbol.startswith("LoadMapData.")
        )
        findings = list(report.findings)
        if mutation == "omit":
            findings.pop(index)
        else:
            findings[index] = replace(findings[index], destination="ALTERED_DESCENDANT")
        monkeypatch.setattr(
            phase2_measurements,
            "discover_phase2_sources",
            lambda root: replace(report, findings=tuple(findings)),
        )
    else:
        report = phase2_measurements.discover_phase2_rom_product(ROOT, product)
        field = "candidate_findings" if kind == "candidate" else "findings"
        findings = list(getattr(report, field))
        if kind == "candidate":
            scoped_sites = {
                finding.site_key
                for finding in report.findings
                if finding.root in phase2_measurements._phase2_roots()
            }
            index = next(
                index
                for index, finding in enumerate(findings)
                if finding.site_key in scoped_sites
            )
        else:
            index = next(
                index
                for index, finding in enumerate(findings)
                if finding.root == "LoadMapData" and finding.mechanism != "root-entry"
            )
        if mutation == "omit":
            findings.pop(index)
        else:
            findings[index] = replace(findings[index], bytes="00")
        patch_product_report(
            monkeypatch,
            product,
            replace(report, **{field: tuple(findings)}),
        )
    with pytest.raises(Phase2MeasurementError, match="subjects="):
        audit_phase2_inventory(ROOT)


def test_undispositioned_source_diagnostic_is_blocking(monkeypatch) -> None:
    report = phase2_measurements.discover_phase2_sources(ROOT)
    monkeypatch.setattr(
        phase2_measurements,
        "discover_phase2_sources",
        lambda root: replace(
            report,
            errors=(*report.errors, "home/pokemon.asm:194:DisplayPartyMenu: injected"),
        ),
    )
    with pytest.raises(Phase2MeasurementError, match="diagnostic dispositions changed"):
        audit_phase2_inventory(ROOT)


@pytest.mark.parametrize(
    ("kind", "product"),
    (
        ("source", None),
        ("diagnostic", None),
        *(
            (kind, product)
            for kind in ("rom", "candidate", "unresolved")
            for product in ROM_PRODUCTS
        ),
    ),
)
def test_duplicate_discovery_items_fail_before_projection(
    monkeypatch, kind, product
) -> None:
    if kind in {"source", "diagnostic"}:
        report = phase2_measurements.discover_phase2_sources(ROOT)
        field = "findings" if kind == "source" else "errors"
        values = getattr(report, field)
        monkeypatch.setattr(
            phase2_measurements,
            "discover_phase2_sources",
            lambda root: replace(report, **{field: (*values, values[0])}),
        )
    else:
        report = phase2_measurements.discover_phase2_rom_product(ROOT, product)
        field = {
            "rom": "findings",
            "candidate": "candidate_findings",
            "unresolved": "unresolved_destinations",
        }[kind]
        values = getattr(report, field)
        patch_product_report(
            monkeypatch,
            product,
            replace(report, **{field: (*values, values[0])}),
        )
    with pytest.raises(Phase2MeasurementError, match="duplicate .* before projection"):
        audit_phase2_inventory(ROOT)


def test_empty_exact_closed_row_rom_mapping_is_blocking(tmp_path, monkeypatch) -> None:
    raw = json.loads(
        (ROOT / phase2_measurements.PLANNED_SUBJECTS_PATH).read_text(encoding="utf-8")
    )
    row_id = "WR-P2-YELLOW-OVERLAY-TRANSFER"
    for kind in ("rom_subjects", "rom_candidate_subjects"):
        removed = len(raw[kind][row_id])
        raw[kind][row_id] = []
        raw["authority_counts"][kind]["by_row"][row_id] = 0
        raw["authority_counts"][kind]["total"] -= removed
    authority = tmp_path / "empty-planned-row.json"
    authority.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(phase2_measurements, "PLANNED_SUBJECTS_PATH", authority)
    with pytest.raises(Phase2MeasurementError, match="ROM subjects"):
        audit_phase2_inventory(ROOT)


def test_closed_audit_requires_concrete_palette_and_overlay_subjects() -> None:
    subjects = {
        row_id: {"subject"} for row_id in phase2_measurements.PHASE2_PLANNED_ROW_IDS
    }
    subjects["WR-P2-YELLOW-BG-PALETTE"] = set()
    subjects["WR-P2-YELLOW-OVERLAY-TRANSFER"] = set()
    errors = phase2_measurements._closed_concrete_subject_errors(subjects)
    assert errors == (
        "WR-P2-YELLOW-BG-PALETTE: closed audit requires a discoverable concrete source subject",
        "WR-P2-YELLOW-OVERLAY-TRANSFER: closed audit requires a discoverable concrete source subject",
    )


def test_closed_party_directions_use_inventory_vocabulary() -> None:
    report = phase2_measurements.discover_phase2_sources(ROOT)
    normalized = phase2_measurements._normalize_closed_scene_directions(report)
    directions = {
        (finding.symbol, finding.destination): finding.direction
        for finding in normalized.findings
        if (finding.symbol, finding.destination)
        in phase2_measurements._CLOSED_SCENE_DIRECTIONS
    }
    assert directions == phase2_measurements._CLOSED_SCENE_DIRECTIONS


def test_passive_production_contract_is_closed() -> None:
    report = phase2_measurements.discover_phase2_sources(ROOT)
    assert phase2_measurements._passive_production_contract_errors(report) == ()


def test_passive_production_contract_rejects_required_edge_omission() -> None:
    report = phase2_measurements.discover_phase2_sources(ROOT)
    omitted = (
        "PassiveFullColorApplyMap.apply",
        "PassiveFullColorCommitVisibleAttributes",
    )
    changed = replace(
        report,
        findings=tuple(
            finding
            for finding in report.findings
            if (finding.symbol, finding.destination) != omitted
        ),
    )
    assert phase2_measurements._passive_production_contract_errors(changed) == (
        "passive production edge omitted: "
        "PassiveFullColorApplyMap.apply -> PassiveFullColorCommitVisibleAttributes",
    )


def test_passive_production_contract_rejects_donor_writer_alteration() -> None:
    report = phase2_measurements.discover_phase2_sources(ROOT)
    changed = replace(
        report,
        findings=tuple(
            replace(finding, resource="SYMBOLIC_SINK")
            if finding.category == "writer"
            and finding.symbol.startswith("PassiveFullColorCommitPalettes")
            and finding.resource == "CGB_PALETTE"
            else finding
            for finding in report.findings
        ),
    )
    assert phase2_measurements._passive_production_contract_errors(changed) == (
        "PassiveFullColorCommitPalettes: passive donor writer resources omitted: "
        "['CGB_PALETTE']",
    )


def test_passive_production_contract_rejects_hostile_edge_resurrection() -> None:
    report = phase2_measurements.discover_phase2_sources(ROOT)
    template = next(
        finding
        for finding in report.findings
        if finding.symbol == "LoadMapData"
        and finding.destination == "PassiveFullColorApplyMap"
    )
    resurrected = replace(template, destination="EnterFullColorOverlay")
    changed = replace(report, findings=(*report.findings, resurrected))
    errors = phase2_measurements._passive_production_contract_errors(changed)
    assert errors == (
        "hostile ownership/scheduler edge resurrected in production: "
        "LoadMapData -> EnterFullColorOverlay",
    )


def test_passive_production_contract_rejects_renderer_generation_mutation() -> None:
    report = phase2_measurements.discover_phase2_sources(ROOT)
    template = next(
        finding
        for finding in report.findings
        if finding.symbol == "LoadMapData"
        and finding.destination == "PassiveFullColorApplyMap"
    )
    mutated = replace(template, destination="wRendererGeneration")
    changed = replace(report, findings=(*report.findings, mutated))
    assert phase2_measurements._passive_production_contract_errors(changed) == (
        "passive production mutates Yellow ownership/generation: "
        "LoadMapData -> wRendererGeneration",
    )


def test_dormant_scheduler_seam_is_not_production_reachability() -> None:
    report = phase2_measurements.discover_phase2_sources(ROOT)
    assert any(
        finding.symbol == "EnqueueFullColorStartMenuOverlay.retry"
        and finding.destination == "EnqueueFullColorWindowTileMapOverlayFar"
        for finding in report.findings
    )
    assert phase2_measurements._passive_production_contract_errors(report) == ()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"root": "PassiveFullColorCommitPalettes"}, "unreviewed passive ROM pointer"),
        ({"bytes": "77"}, "unreviewed passive ROM pointer"),
        (
            {"call_path": ("PassiveFullColorCommitVisibleAttributes", "altered")},
            "unreviewed passive ROM pointer",
        ),
        ({"resource": "UNKNOWN_OTHER"}, "unclassified resource"),
    ],
)
def test_passive_rom_pointer_projection_is_exact(changes, message) -> None:
    report = phase2_measurements.discover_phase2_rom_product(
        ROOT, phase2_measurements.PHASE2_AUDIT_PRODUCT
    )
    finding = next(
        finding
        for finding in report.findings
        if finding.root == "PassiveFullColorCommitVisibleAttributes"
        and finding.resource == "UNKNOWN_DESTINATION"
    )
    assert (
        phase2_measurements._planned_rom_row_for(finding)
        == "WR-P2-YELLOW-OVERLAY-TRANSFER"
    )
    with pytest.raises(Phase2MeasurementError, match=message):
        phase2_measurements._planned_rom_row_for(replace(finding, **changes))


def test_passive_rom_pointer_authority_has_exact_site_and_root_coverage() -> None:
    report = phase2_measurements.discover_phase2_rom_product(
        ROOT, phase2_measurements.PHASE2_AUDIT_PRODUCT
    )
    findings = tuple(
        finding
        for finding in report.findings
        if finding.root in phase2_measurements._phase2_roots()
    )
    phase2_measurements._validate_passive_rom_pointer_authority(findings)
    assert len(phase2_measurements._PASSIVE_ROM_POINTER_WRITES) == 78
    assert {
        phase2_measurements._planned_rom_row_for(finding)
        for finding in findings
        if finding.category == "writer"
        and finding.resource == "UNKNOWN_DESTINATION"
        and finding.root.startswith("PassiveFullColor")
    } == {"WR-P2-YELLOW-OVERLAY-TRANSFER"}


def test_passive_rom_pointer_authority_has_one_uniform_payload_rebase() -> None:
    previous = phase2_measurements._PREVIOUS_PASSIVE_ROM_POINTER_WRITES
    current = phase2_measurements._PASSIVE_ROM_POINTER_WRITES
    assert len(previous) == len(current) == 78

    expected_delta = phase2_measurements._PASSIVE_ROM_POINTER_REBASE_BYTES
    assert expected_delta == 0x780
    deltas = []
    expected_sites = []
    for (old_bank, old_address, opcode), roots in previous.items():
        delta = expected_delta if opcode == "12" else 0
        rebased = (old_bank, old_address + delta, opcode)
        assert current[rebased] is roots
        deltas.append(delta)
        expected_sites.append(rebased)

    assert list(current) == expected_sites
    assert deltas.count(0) == 2
    assert deltas.count(expected_delta) == 76


def test_transport_special_relocation_is_exactly_three_complete_payload_pairs() -> None:
    assert phase2_measurements._TRANSPORT_SPECIAL_PAYLOAD_BYTES == 3 * (64 + 256)
    assert phase2_measurements._TRANSPORT_SPECIAL_PAYLOAD_BYTES == 0x3C0
    assert phase2_measurements._ALL_TILESET_POINTER_EXPANSION_BYTES == 2 * 2 * 2
    assert phase2_measurements._ALL_TILESET_POINTER_EXPANSION_BYTES == 8


def test_production_pointer_projection_requires_exact_reviewed_subject() -> None:
    product = phase2_measurements.DEBUG_PRODUCT
    report = phase2_measurements.discover_phase2_rom_product(ROOT, product)
    source = phase2_measurements._normalize_closed_scene_directions(
        phase2_measurements.discover_phase2_sources(ROOT)
    )
    assignments = DiscoveryAssignmentAuthority.load(
        ROOT / "specs/full-colors/inventory/assignments.json"
    ).for_product(product)
    reviewed_pointer_rows = {
        row.subject.sha256: row.row_id
        for row in assignments.rows
        if row.subject.kind.value == "ROM_FINDING"
    }
    phase2_measurements._scoped_product_subjects(
        source,
        report,
        product=product,
        shared_candidate_dispositions=shared_candidate_dispositions(),
        reviewed_pointer_rows=reviewed_pointer_rows,
    )
    findings = list(report.findings)
    index = next(
        index
        for index, finding in enumerate(findings)
        if finding.category == "writer"
        and finding.resource == "UNKNOWN_DESTINATION"
        and finding.root.startswith("PassiveFullColor")
    )
    finding = findings[index]
    findings[index] = replace(
        finding,
        call_path=(*finding.call_path[:-1], "UnrelatedSameDepth"),
    )
    with pytest.raises(Phase2MeasurementError, match="unreviewed passive ROM pointer"):
        phase2_measurements._scoped_product_subjects(
            source,
            replace(report, findings=tuple(findings)),
            product=product,
            shared_candidate_dispositions=shared_candidate_dispositions(),
            reviewed_pointer_rows=reviewed_pointer_rows,
        )


def test_shared_candidate_projection_is_independent_of_row_order() -> None:
    product = phase2_measurements.DEBUG_PRODUCT
    report = phase2_measurements.discover_phase2_rom_product(ROOT, product)
    source = SimpleNamespace(findings=())
    assignments = DiscoveryAssignmentAuthority.load(
        ROOT / "specs/full-colors/inventory/assignments.json"
    ).for_product(product)
    reviewed_pointer_rows = {
        row.subject.sha256: row.row_id
        for row in assignments.rows
        if row.subject.kind.value == "ROM_FINDING"
    }
    dispositions = shared_candidate_dispositions()

    def projected_rows(current_report):
        _, projected = phase2_measurements._scoped_product_subjects(
            source,
            current_report,
            product=product,
            shared_candidate_dispositions=dispositions,
            reviewed_pointer_rows=reviewed_pointer_rows,
        )
        return {
            phase2_measurements.rom_finding_subject(finding).sha256: row_id
            for finding, row_id in projected
            if finding.root == "<candidate-scan>"
            and phase2_measurements.rom_finding_subject(finding).sha256 in dispositions
        }

    forward = projected_rows(report)
    reversed_rows = projected_rows(
        replace(report, findings=tuple(reversed(report.findings)))
    )
    assert forward == reversed_rows
    assert len(forward) == 15
    assert set(forward.values()) == {"SC-P2-PALLET-ROUTE1-NORTH"}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "missing pokeyellow_debug shared-candidate disposition"),
        ("stale", "missing .*stale or extra pokeyellow_debug shared-candidate"),
        ("extra", "stale or extra pokeyellow_debug shared-candidate disposition"),
        ("conflicting", "eligible row set changed"),
        ("unreviewed", "is unreviewed"),
    ],
)
def test_shared_candidate_projection_fails_closed(mutation, message) -> None:
    product = phase2_measurements.DEBUG_PRODUCT
    report = phase2_measurements.discover_phase2_rom_product(ROOT, product)
    assignments = DiscoveryAssignmentAuthority.load(
        ROOT / "specs/full-colors/inventory/assignments.json"
    ).for_product(product)
    reviewed_pointer_rows = {
        row.subject.sha256: row.row_id
        for row in assignments.rows
        if row.subject.kind.value == "ROM_FINDING"
    }
    dispositions = {
        digest: dict(disposition)
        for digest, disposition in shared_candidate_dispositions().items()
    }
    digest = next(iter(dispositions))
    if mutation == "missing":
        dispositions.pop(digest)
    elif mutation == "stale":
        dispositions["0" * 64] = dispositions.pop(digest)
    elif mutation == "extra":
        dispositions["0" * 64] = dict(dispositions[digest])
    elif mutation == "conflicting":
        dispositions[digest]["eligible_rows"] = ("SC-P2-PARTY-RETURN",)
    else:
        dispositions[digest]["reviewed"] = False

    with pytest.raises(Phase2MeasurementError, match=message):
        phase2_measurements._scoped_product_subjects(
            SimpleNamespace(findings=()),
            report,
            product=product,
            shared_candidate_dispositions=dispositions,
            reviewed_pointer_rows=reviewed_pointer_rows,
        )


@pytest.mark.parametrize(
    "mutation",
    ["unreviewed", "malformed-eligible-rows", "conflicting-representative"],
)
def test_shared_candidate_authority_rejects_unreviewed_or_malformed_dispositions(
    tmp_path, monkeypatch, mutation
) -> None:
    raw = json.loads(
        (ROOT / phase2_measurements.PLANNED_SUBJECTS_PATH).read_text(encoding="utf-8")
    )
    disposition = next(iter(raw["shared_candidate_dispositions"].values()))
    if mutation == "unreviewed":
        disposition["reviewed"] = False
    elif mutation == "malformed-eligible-rows":
        disposition["eligible_rows"].reverse()
    else:
        disposition["representative_row"] = "SC-P2-PARTY-ENTRY"
    authority = tmp_path / "planned-subjects.json"
    authority.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(phase2_measurements, "PLANNED_SUBJECTS_PATH", authority)

    with pytest.raises(Phase2MeasurementError, match="malformed disposition"):
        phase2_measurements._load_planned_subjects(ROOT, closed=True)


@pytest.mark.parametrize(
    "mutation",
    ["stale-site", "missing-root", "stale-ancestry"],
)
def test_passive_rom_pointer_authority_rejects_stale_entries(
    monkeypatch,
    mutation,
) -> None:
    report = phase2_measurements.discover_phase2_rom_product(
        ROOT, phase2_measurements.PHASE2_AUDIT_PRODUCT
    )
    findings = tuple(
        finding
        for finding in report.findings
        if finding.root in phase2_measurements._phase2_roots()
    )
    authority = {
        site: dict(roots)
        for site, roots in phase2_measurements._PASSIVE_ROM_POINTER_WRITES.items()
    }
    site = next(iter(authority))
    if mutation == "stale-site":
        authority[(site[0], site[1] - 1, site[2])] = authority.pop(site)
        message = "pointer sites changed"
    else:
        root = next(iter(authority[site]))
        if mutation == "missing-root":
            authority[site].pop(root)
            message = "pointer roots changed"
        else:
            authority[site][root] = (
                *authority[site][root],
                (*authority[site][root][0], "altered"),
            )
            message = "pointer ancestry changed"
    monkeypatch.setattr(
        phase2_measurements,
        "_PASSIVE_ROM_POINTER_WRITES",
        authority,
    )
    with pytest.raises(Phase2MeasurementError, match=message):
        phase2_measurements._validate_passive_rom_pointer_authority(findings)


@pytest.mark.parametrize("product", ROM_PRODUCTS)
def test_product_rom_subject_is_mutation_sensitive(monkeypatch, product) -> None:
    report = phase2_measurements.discover_phase2_rom_product(ROOT, product)
    findings = list(report.findings)
    index = next(
        index
        for index, finding in enumerate(findings)
        if finding.root == "UpdateMovingBgTiles" and finding.mechanism == "root-entry"
    )
    findings[index] = replace(findings[index], bytes="00")
    patch_product_report(
        monkeypatch,
        product,
        replace(report, findings=tuple(findings)),
    )
    with pytest.raises(Phase2MeasurementError, match="subjects="):
        audit_phase2_inventory(ROOT)


@pytest.mark.parametrize("mutation", ["schema", "traversal"])
def test_standalone_audit_reuses_strict_v3_transition_validation(
    tmp_path, monkeypatch, mutation
) -> None:
    raw = json.loads((ROOT / phase2_measurements.SOURCE_TRANSITION_PATH).read_text())
    if mutation == "schema":
        raw["schema"] = "full-color-phase1-audit-source-transition-v1"
    else:
        path, binding = next(iter(raw["reviewed_delta_paths"].items()))
        del raw["reviewed_delta_paths"][path]
        raw["reviewed_delta_paths"]["../" + path] = binding
    transition = tmp_path / "transition.json"
    transition.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(baseline_inventory, "SOURCE_TRANSITION_PATH", transition)
    with pytest.raises(
        Phase2MeasurementError,
        match="standalone hostile authority",
    ):
        audit_phase2_inventory(ROOT)


@pytest.mark.parametrize(
    "mutation",
    ["machine-site", "bytes", "root", "resources", "commit", "reviewed", "hash"],
)
def test_standalone_audit_reuses_strict_closed_row_validation(
    monkeypatch, mutation
) -> None:
    original = WriterInventory.load(ROOT / "specs/full-colors/inventory/writers.json")
    raw = original.to_dict()
    row = next(item for item in raw["rows"] if item["id"] == "WR-P2-YELLOW-BG-PALETTE")
    if mutation == "machine-site":
        row["machine_sites"] = []
    elif mutation == "bytes":
        row["machine_sites"][0]["bytes"] = "fb1acf"
    elif mutation == "root":
        row["reachability"]["roots"] = ["RunPaletteCommand.altered"]
        row["reachability"]["call_paths"] = [["RunPaletteCommand.altered"]]
    elif mutation == "resources":
        row["resources"][0]["end"] = 0xFF6A
    elif mutation == "commit":
        row["commit_unit"] = "BYTE"
    elif mutation == "reviewed":
        row["evidence"]["reviewed"] = False
    else:
        row["evidence"]["source_sha256"] = "0" * 64
    changed = WriterInventory.from_dict(raw)
    monkeypatch.setattr(
        phase2_measurements.WriterInventory, "load", lambda path: changed
    )
    with pytest.raises(
        Phase2MeasurementError,
        match="standalone hostile authority|hostile inventory audit lacks exact evidence",
    ):
        audit_phase2_inventory(ROOT)


def test_closed_authority_rejects_reintroduced_planned_only_disposition(
    tmp_path, monkeypatch
) -> None:
    raw = json.loads(
        (ROOT / phase2_measurements.PLANNED_SUBJECTS_PATH).read_text(encoding="utf-8")
    )
    raw["planned_only_dispositions"]["WR-P2-YELLOW-BG-PALETTE"] = {}
    authority = tmp_path / "planned-subjects.json"
    authority.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(phase2_measurements, "PLANNED_SUBJECTS_PATH", authority)
    with pytest.raises(
        Phase2MeasurementError, match="must be empty after audit closure"
    ):
        audit_phase2_inventory(ROOT)


def test_closed_authority_requires_nonempty_historical_source_partition(
    tmp_path, monkeypatch
) -> None:
    raw = json.loads(
        (ROOT / phase2_measurements.PLANNED_SUBJECTS_PATH).read_text(encoding="utf-8")
    )
    row_id = "MU-P2-MOVEMENT-HORIZONTAL"
    removed = len(raw["source_subjects"][row_id])
    raw["source_subjects"][row_id] = []
    counts = raw["authority_counts"]["source_subjects"]
    counts["by_row"][row_id] = 0
    counts["total"] -= removed
    authority = tmp_path / "planned-subjects.json"
    authority.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(phase2_measurements, "PLANNED_SUBJECTS_PATH", authority)

    with pytest.raises(
        Phase2MeasurementError,
        match="source subjects authority is empty for a non-empty closed row",
    ):
        audit_phase2_inventory(ROOT)


def test_pressure_replay_equivalence_policy_mutation_changes_residency(
    tmp_path,
) -> None:
    raw = json.loads((ROOT / DEFINITION_PATH).read_text(encoding="utf-8"))
    horizontal = raw["scenario"][1]["enqueue"]
    for request in horizontal:
        request["destination"] = "same-column"
        request["desired_state"] = "same-final-state"
    path = tmp_path / "coalesced.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    coalesced = load_definition(path)
    column = next(
        row for row in raw["request_classes"] if row["name"] == "MAP_COLUMN_PAIRED"
    )
    column["equivalent_at_capacity"] = False
    path.write_text(json.dumps(raw), encoding="utf-8")
    independent = load_definition(path)
    assert coalesced.class_high_water["MAP_COLUMN_PAIRED"] == 1
    assert independent.class_high_water["MAP_COLUMN_PAIRED"] == 8


def test_guarded_source_discovery_requires_compiled_provenance(tmp_path) -> None:
    with pytest.raises(
        Phase2MeasurementError, match="missing compile-time PHASE2_AUDIT"
    ):
        discover_phase2_sources(tmp_path)


@pytest.mark.parametrize("duplicate", [False, True])
def test_audit_root_table_rejects_wrong_or_duplicate_compiled_pointer(
    tmp_path, duplicate
) -> None:
    audit_product_fixture(tmp_path)
    from tools.rom_tests.full_color.rom_discovery import load_sym, normalize_rom_offset

    symbols = load_sym(tmp_path / "pokeyellow_phase2_audit.sym")
    start = symbols.by_name["Phase2AuditRoots"]
    offset = normalize_rom_offset(start.bank, start.address)
    rom_path = tmp_path / "pokeyellow_phase2_audit.gbc"
    rom = bytearray(rom_path.read_bytes())
    replacement = symbols.by_name[_phase2_roots()[0]].address if duplicate else 0
    rom[offset + 2 : offset + 4] = replacement.to_bytes(2, "little")
    rom_path.write_bytes(rom)
    with pytest.raises(
        Phase2MeasurementError, match="duplicate pointers|does not match"
    ):
        _verify_audit_product(tmp_path)


def test_committed_record_verifier_requires_byte_identical_evidence(
    tmp_path, monkeypatch
) -> None:
    decision = select_phase2_representation(measurement())
    monkeypatch.setattr(phase2_measurements, "generate", lambda root: decision)
    evidence = tmp_path / "evidence.json"
    evidence.write_text(decision.to_json(), encoding="utf-8")
    assert verify_evidence(tmp_path, evidence) == decision
    evidence.write_text(decision.to_json() + " ", encoding="utf-8")
    with pytest.raises(Phase2MeasurementError, match="stale or edited"):
        verify_evidence(tmp_path, evidence)


def test_official_generation_never_rewrites_reviewed_authorities(
    tmp_path, monkeypatch
) -> None:
    inventory = ROOT / "specs/full-colors/inventory"
    authority_paths = tuple(
        inventory / name
        for name in (
            "assignments.json",
            "writers.json",
            "scenes.json",
            "mutations.json",
        )
    )
    before = {path: path.read_bytes() for path in authority_paths}
    decision = select_phase2_representation(measurement())
    monkeypatch.setattr(phase2_measurements, "generate", lambda root: decision)
    output = tmp_path / "evidence.json"

    with pytest.raises(SystemExit):
        phase2_measurements.main(["--root", str(ROOT), "--output", str(output)])
    assert not output.exists()
    assert (
        phase2_measurements.main(
            [
                "--root",
                str(ROOT),
                "--output",
                str(output),
                "--authority-reviewed",
            ]
        )
        == 0
    )
    assert output.read_text(encoding="utf-8") == decision.to_json()
    assert {path: path.read_bytes() for path in authority_paths} == before


@pytest.mark.parametrize("stem", ["pokeyellow", "pokeyellow_debug", "pokeyellow_vc"])
@pytest.mark.parametrize("suffix", [".gbc", ".map", ".sym"])
def test_normal_link_products_expose_no_phase2_audit_entries(
    tmp_path, stem, suffix
) -> None:
    audit_product_fixture(tmp_path)
    _verify_audit_product(tmp_path)
    path = tmp_path / f"{stem}{suffix}"
    path.write_bytes(path.read_bytes() + b"Phase2AuditForbidden")
    with pytest.raises(Phase2MeasurementError, match="forbidden Phase 2"):
        _verify_audit_product(tmp_path)

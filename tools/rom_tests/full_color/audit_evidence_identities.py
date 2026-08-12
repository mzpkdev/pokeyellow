"""Rebind mechanically changed evidence identities through official serializers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from . import source_transition
from .baseline_discovery import discover_baseline_sources
from .discovery_assignment import (
    BASELINE_ASSIGNMENT_IDS,
    BASELINE_PRODUCT,
    DiscoveryAssignmentAuthority,
)
from .inventory import MutationInventory, SceneInventory, WriterInventory
from .rom_discovery import load_map

HASH_FIELDS = ("source_sha256", "rom_sha256", "map_sha256", "sym_sha256")
REVIEWED_AUDIT_HASHES = {
    "source_sha256": "dac0a562119587880e788fef2c82c34a8e63faa88f9d5ac178e1a5334015fbfc",
    "rom_sha256": "40b0a702c94ebddeb3fd26202c10a60b6dd00b66a392da7ab9598d61c092dcd6",
    "map_sha256": "295370b4901d952b3601574157333eac52786922890d3e60e2d080e9ea5436b5",
    "sym_sha256": "11c50853e72e28fdff47b721ac0cf6f5fe14396b311a59d9b993fc5ef2b619d3",
}
# Retain the public name used by focused guard tests and downstream readers.
AUDIT_ROM_SHA256 = REVIEWED_AUDIT_HASHES["rom_sha256"]
REVIEWED_SOURCE_SHA256 = (
    "9b12281f62023dbd80e64ed17d684aaae5754d787166163f213fe21e4ca2ff7f"
)
BASELINE_MANIFEST_SHA256 = (
    "75c058f0d0df07a25918c710dc8ddebf43d3e5b809a06faaf7391cf015a9d774"
)
BASELINE_ARTIFACTS = {
    "rom_sha256": Path("pokeyellow_debug.gbc"),
    "map_sha256": Path("pokeyellow_debug.map"),
    "sym_sha256": Path("pokeyellow_debug.sym"),
}
AUDIT_ARTIFACTS = {
    "rom_sha256": Path("pokeyellow_phase2_audit.gbc"),
    "map_sha256": Path("pokeyellow_phase2_audit.map"),
    "sym_sha256": Path("pokeyellow_phase2_audit.sym"),
}
BASELINE_INVENTORY_IDS = {
    "mutations.json": frozenset({"MU-YELLOW-MAP-VIEW-INITIAL"}),
    "scenes.json": frozenset({"SC-YELLOW-MAP-ENTRY"}),
    "writers.json": frozenset(
        {"WR-YELLOW-LCDC-DISABLE", "WR-YELLOW-MAP-VIEW-TILE-COPY"}
    ),
}
AUDIT_INVENTORY_IDS = {
    "mutations.json": frozenset(
        {
            "MU-P2-ANIMATED-TERRAIN",
            "MU-P2-DIALOGUE-OVERLAY",
            "MU-P2-MAP-CONNECTION-NORTH",
            "MU-P2-MAP-RECONSTRUCTION",
            "MU-P2-MOVEMENT-HORIZONTAL",
            "MU-P2-MOVEMENT-VERTICAL",
            "MU-P2-OAM-FOLLOWER-NPC",
            "MU-P2-PALETTE-PAYLOADS",
            "MU-P2-START-MENU-OVERLAY",
        }
    ),
    "scenes.json": frozenset(
        {
            "SC-P2-PALLET-ROUTE1-NORTH",
            "SC-P2-PARTY-ENTRY",
            "SC-P2-PARTY-RETURN",
        }
    ),
    "writers.json": frozenset(
        {
            "WR-P2-YELLOW-ANIMATION-TILES",
            "WR-P2-YELLOW-BG-PALETTE",
            "WR-P2-YELLOW-MAP-STREAM",
            "WR-P2-YELLOW-OAM-BUILD",
            "WR-P2-YELLOW-OAM-DMA",
            "WR-P2-YELLOW-OVERLAY-TRANSFER",
        }
    ),
}
TRANSITION_PATH = Path(
    "specs/full-colors/definitions/phase1-audit-source-transition.json"
)
DOCUMENTS = {
    Path("specs/full-colors/inventory/assignments.json"): DiscoveryAssignmentAuthority,
    Path("specs/full-colors/inventory/mutations.json"): MutationInventory,
    Path("specs/full-colors/inventory/scenes.json"): SceneInventory,
    Path("specs/full-colors/inventory/writers.json"): WriterInventory,
}
PROPOSAL_SCHEMA = "full-color-audit-evidence-identities-proposal-v1"


class AuditEvidenceIdentityError(RuntimeError):
    pass


def _canonical(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def _strict_json(text: str, *, label: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise AuditEvidenceIdentityError(f"{label} is not strict JSON") from exc


def _contained_path(root: Path, path: Path, *, label: str) -> Path:
    root = root.resolve()
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve(strict=False)
    if resolved == root or root not in resolved.parents:
        raise AuditEvidenceIdentityError(f"{label} escapes repository root")
    return resolved


@dataclass(frozen=True)
class _FileIdentity:
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    links: int


@dataclass
class _PinnedTarget:
    path: Path
    directory_fd: int
    directory_identity: tuple[int, int]
    identity: _FileIdentity
    original: bytes


@dataclass(frozen=True)
class _Publication:
    target: _PinnedTarget
    identity: _FileIdentity


def _identity(metadata: os.stat_result) -> _FileIdentity:
    return _FileIdentity(
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_nlink,
    )


def _validate_directory(target: _PinnedTarget) -> None:
    try:
        current = os.stat(target.path.parent, follow_symlinks=False)
        pinned = os.fstat(target.directory_fd)
    except OSError as exc:
        raise AuditEvidenceIdentityError(
            f"reviewed target directory is unavailable: {target.path.parent}"
        ) from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != target.directory_identity
        or (pinned.st_dev, pinned.st_ino) != target.directory_identity
    ):
        raise AuditEvidenceIdentityError(
            f"reviewed target directory changed during publication: {target.path.parent}"
        )


def _target_identity_at(target: _PinnedTarget, expected: _FileIdentity) -> None:
    try:
        current = os.stat(
            target.path.name,
            dir_fd=target.directory_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise AuditEvidenceIdentityError(
            f"reviewed target is unavailable: {target.path}"
        ) from exc
    if not stat.S_ISREG(current.st_mode) or _identity(current) != expected:
        raise AuditEvidenceIdentityError(
            f"reviewed target changed during publication: {target.path}"
        )


def _same_staged_file(actual: _FileIdentity, staged: _FileIdentity) -> bool:
    """Ignore ctime, which the directory rename itself is allowed to advance."""
    return (
        actual.device,
        actual.inode,
        actual.mode,
        actual.size,
        actual.mtime_ns,
        actual.links,
    ) == (
        staged.device,
        staged.inode,
        staged.mode,
        staged.size,
        staged.mtime_ns,
        staged.links,
    )


def _open_directory_without_symlinks(directory: Path) -> int:
    absolute = Path(os.path.abspath(directory))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for component in absolute.parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _pin_target(root: Path, relative: Path) -> _PinnedTarget:
    root = Path(os.path.abspath(root))
    if relative.is_absolute() or ".." in relative.parts or relative == Path("."):
        raise AuditEvidenceIdentityError(
            f"reviewed target is not canonical: {relative}"
        )
    path = root / relative
    try:
        directory_fd = _open_directory_without_symlinks(path.parent)
    except OSError as exc:
        raise AuditEvidenceIdentityError(
            f"reviewed target directory is unavailable: {path.parent}"
        ) from exc
    try:
        directory = os.fstat(directory_fd)
        target = _PinnedTarget(
            path=path,
            directory_fd=directory_fd,
            directory_identity=(directory.st_dev, directory.st_ino),
            identity=_FileIdentity(0, 0, 0, 0, 0, 0, 0),
            original=b"",
        )
        _validate_directory(target)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path.name, flags, dir_fd=directory_fd)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise AuditEvidenceIdentityError(
                    f"reviewed target is not a regular file: {relative}"
                )
            target.identity = _identity(metadata)
            target.original = stream.read()
        _target_identity_at(target, target.identity)
        return target
    except Exception:
        os.close(directory_fd)
        raise


def _pin_input(root: Path, path: Path, *, label: str) -> _PinnedTarget:
    root = Path(os.path.abspath(root))
    candidate = Path(os.path.abspath(path if path.is_absolute() else root / path))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise AuditEvidenceIdentityError(f"{label} escapes repository root") from exc
    try:
        return _pin_target(root, relative)
    except AuditEvidenceIdentityError as exc:
        raise AuditEvidenceIdentityError(f"{label} cannot be pinned: {exc}") from exc


def _allocate_temporary(target: _PinnedTarget) -> tuple[int, str]:
    for _ in range(128):
        name = f".{target.path.name}.{secrets.token_hex(12)}.tmp"
        try:
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=target.directory_fd,
            )
            return descriptor, name
        except FileExistsError:
            pass
    raise AuditEvidenceIdentityError(
        f"cannot allocate reviewed authority temporary file: {target.path}"
    )


def _atomic_replace(
    target: _PinnedTarget,
    contents: bytes,
    expected: _FileIdentity,
    ledger: list[_Publication],
) -> _FileIdentity:
    temporary_name: str | None = None
    try:
        _validate_directory(target)
        _target_identity_at(target, expected)
        descriptor, temporary_name = _allocate_temporary(target)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        staged = _identity(
            os.stat(temporary_name, dir_fd=target.directory_fd, follow_symlinks=False)
        )
        _validate_directory(target)
        _target_identity_at(target, expected)
        os.replace(
            temporary_name,
            target.path.name,
            src_dir_fd=target.directory_fd,
            dst_dir_fd=target.directory_fd,
        )
        temporary_name = None
        # Record the replacement before any fallible post-publication check so
        # every path that may already contain new bytes is eligible for rollback.
        ledger.append(_Publication(target, staged))
        published = _identity(
            os.stat(
                target.path.name,
                dir_fd=target.directory_fd,
                follow_symlinks=False,
            )
        )
        if not _same_staged_file(published, staged):
            raise AuditEvidenceIdentityError(
                f"reviewed authority publication was redirected: {target.path}"
            )
        publication = _Publication(target, published)
        ledger[-1] = publication
        _target_identity_at(target, published)
        _validate_directory(target)
        os.fsync(target.directory_fd)
        return published
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=target.directory_fd)
            except FileNotFoundError:
                pass


def _validate_publication(publication: _Publication) -> None:
    """Prove the pinned publication is still installed at its public path."""
    _validate_directory(publication.target)
    _target_identity_at(publication.target, publication.identity)


def _restore_publication(publication: _Publication) -> None:
    """Restore original bytes in the pinned parent, even if its path moved."""
    temporary_name: str | None = None
    try:
        _target_identity_at(publication.target, publication.identity)
        descriptor, temporary_name = _allocate_temporary(publication.target)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(publication.target.original)
            handle.flush()
            os.fsync(handle.fileno())
        staged = _identity(
            os.stat(
                temporary_name,
                dir_fd=publication.target.directory_fd,
                follow_symlinks=False,
            )
        )
        os.replace(
            temporary_name,
            publication.target.path.name,
            src_dir_fd=publication.target.directory_fd,
            dst_dir_fd=publication.target.directory_fd,
        )
        temporary_name = None
        restored = _identity(
            os.stat(
                publication.target.path.name,
                dir_fd=publication.target.directory_fd,
                follow_symlinks=False,
            )
        )
        if not _same_staged_file(restored, staged):
            raise AuditEvidenceIdentityError(
                "restored reviewed authority was redirected in its pinned parent: "
                f"{publication.target.path}"
            )
        _target_identity_at(publication.target, restored)
        os.fsync(publication.target.directory_fd)
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=publication.target.directory_fd)
            except FileNotFoundError:
                pass


def _transactional_write(updates: Sequence[tuple[_PinnedTarget, bytes]]) -> None:
    written: list[_Publication] = []
    try:
        for target, contents in updates:
            _atomic_replace(target, contents, target.identity, written)
        # Individual replaces use pinned parent descriptors.  Reconnect every
        # resulting inode to the public path before the transaction may report
        # success; a displaced parent containing correct bytes is not public
        # authority.
        for publication in written:
            _validate_publication(publication)
    except (OSError, AuditEvidenceIdentityError) as exc:
        rollback_errors = []
        for publication in reversed(written):
            try:
                _restore_publication(publication)
            except (OSError, AuditEvidenceIdentityError) as rollback_exc:
                rollback_errors.append(f"{publication.target.path}: {rollback_exc}")
        detail = (
            f"; rollback failed: {', '.join(rollback_errors)}"
            if rollback_errors
            else ""
        )
        raise AuditEvidenceIdentityError(
            f"reviewed authority transaction failed: {exc}{detail}; "
            "original authorities restored in their pinned parents; the public "
            "namespace remains refused"
        ) from exc


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise AuditEvidenceIdentityError(f"required build artifact is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_hashes(
    root: Path, source_sha256: str, artifacts: dict[str, Path]
) -> dict[str, str]:
    hashes = {
        "source_sha256": source_sha256,
        **{
            name: _sha256(root / relative)
            for name, relative in artifacts.items()
            if name != "map_sha256"
        },
    }
    map_path = root / artifacts["map_sha256"]
    if not map_path.is_file():
        raise AuditEvidenceIdentityError(
            f"required build artifact is missing: {map_path}"
        )
    hashes["map_sha256"] = load_map(map_path).artifact_sha256
    return hashes


def _baseline_hashes(root: Path, source_sha256: str) -> dict[str, str]:
    return _artifact_hashes(root, source_sha256, BASELINE_ARTIFACTS)


def _audit_hashes(root: Path, source_sha256: str) -> dict[str, str]:
    return _artifact_hashes(root, source_sha256, AUDIT_ARTIFACTS)


def _evidence_hashes(evidence: Any) -> dict[str, str]:
    if isinstance(evidence, dict):
        return {name: evidence.get(name) for name in HASH_FIELDS}
    return {name: getattr(evidence, name) for name in HASH_FIELDS}


def _require_reviewed_audit_hashes(
    evidence: Any, audit_hashes: dict[str, str], identifier: object
) -> None:
    hashes = _evidence_hashes(evidence)
    if hashes not in (REVIEWED_AUDIT_HASHES, audit_hashes):
        raise AuditEvidenceIdentityError(
            f"audit row has changed artifact authority: {identifier}"
        )


def _updated_assignments(
    authority: DiscoveryAssignmentAuthority,
    source_sha256: str,
    baseline_hashes: dict[str, str],
    audit_hashes: dict[str, str],
) -> DiscoveryAssignmentAuthority:
    baseline = tuple(row for row in authority.rows if row.product == BASELINE_PRODUCT)
    baseline_ids = frozenset(row.id for row in baseline)
    if baseline_ids != BASELINE_ASSIGNMENT_IDS or len(baseline) != len(
        BASELINE_ASSIGNMENT_IDS
    ):
        raise AuditEvidenceIdentityError(
            "baseline assignment scope changed: expected the eight reviewed "
            "initial-map-entry assignments"
        )
    rows = []
    for row in authority.rows:
        if row.product == BASELINE_PRODUCT:
            evidence = replace(row.evidence, **baseline_hashes)
        else:
            # A source-only transition does not alter the product-specific ROM,
            # map, or symbol authorities owned by Phase 2.
            evidence = replace(row.evidence, source_sha256=source_sha256)
        rows.append(replace(row, evidence=evidence))
    return DiscoveryAssignmentAuthority(tuple(rows))


def _assert_assignment_delta(
    before: DiscoveryAssignmentAuthority, after: DiscoveryAssignmentAuthority
) -> None:
    if len(before.rows) != len(after.rows):
        raise AuditEvidenceIdentityError(
            "assignment row count changed during rebinding"
        )
    for old, new in zip(before.rows, after.rows, strict=True):
        old_dict = old.to_dict()
        new_dict = new.to_dict()
        old_evidence = old_dict.pop("evidence")
        new_evidence = new_dict.pop("evidence")
        if old_dict != new_dict:
            raise AuditEvidenceIdentityError(
                f"assignment semantic or ID drift during rebinding: {old.id}"
            )
        allowed = (
            {"source_sha256", "rom_sha256", "map_sha256", "sym_sha256"}
            if old.product == BASELINE_PRODUCT
            else set(HASH_FIELDS)
        )
        for key in set(old_evidence) | set(new_evidence):
            if key not in allowed and old_evidence.get(key) != new_evidence.get(key):
                raise AuditEvidenceIdentityError(
                    f"assignment reviewed semantics changed during rebinding: {old.id}"
                )


def _updated_document(
    relative: Path,
    raw: dict[str, Any],
    source_sha256: str,
    baseline_hashes: dict[str, str],
    audit_hashes: dict[str, str],
) -> Any:
    baseline_ids = BASELINE_INVENTORY_IDS.get(relative.name, frozenset())
    found_baseline_ids = frozenset(
        row.get("id") for row in raw["rows"] if row.get("id") in baseline_ids
    )
    if found_baseline_ids != baseline_ids:
        raise AuditEvidenceIdentityError(
            f"baseline inventory scope changed: {relative.name}"
        )
    for row in raw["rows"]:
        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            continue
        if row.get("id") in baseline_ids:
            evidence.update(baseline_hashes)
            continue
        evidence["source_sha256"] = source_sha256
    return raw


def apply_reviewed_proposal(
    root: Path, transition_proposal: Path, proposal_path: Path
) -> None:
    """Apply one canonically recomputed, explicitly reviewed hash-only proposal."""
    root = root.resolve()
    transition_proposal_argument = transition_proposal
    pinned: list[_PinnedTarget] = []
    updates: list[tuple[_PinnedTarget, bytes]] = []
    try:
        transition_input = _pin_input(
            root, transition_proposal, label="source-transition proposal"
        )
        pinned.append(transition_input)
        proposal_input = _pin_input(root, proposal_path, label="audit proposal")
        pinned.append(proposal_input)
        supplied_text = proposal_input.original.decode("utf-8")
        supplied = _strict_json(supplied_text, label="reviewed audit-evidence proposal")
        if supplied_text != _canonical(supplied):
            raise AuditEvidenceIdentityError(
                "reviewed audit-evidence proposal is not canonical JSON"
            )
        transition_envelope_text = transition_input.original.decode("utf-8")
        expected = propose(
            root,
            transition_proposal_argument,
            transition_envelope_text=transition_envelope_text,
        )
        if supplied != expected:
            raise AuditEvidenceIdentityError(
                "reviewed audit-evidence proposal does not match canonical recomputation"
            )
        transition_envelope = _strict_json(
            transition_envelope_text, label="reviewed source-transition proposal"
        )
        if transition_envelope_text != _canonical(transition_envelope):
            raise AuditEvidenceIdentityError(
                "reviewed source-transition proposal is not canonical JSON"
            )
        if transition_envelope.get("authority_path") != str(TRANSITION_PATH):
            raise AuditEvidenceIdentityError(
                "source-transition proposal does not name the canonical authority"
            )
        transition = transition_envelope.get("proposal")
        if not isinstance(transition, dict):
            raise AuditEvidenceIdentityError("source-transition proposal is malformed")

        transition_target = _pin_target(root, TRANSITION_PATH)
        pinned.append(transition_target)
        updates.append((transition_target, _canonical(transition).encode()))
        for relative_text, document in supplied["documents"].items():
            relative = Path(relative_text)
            if relative not in DOCUMENTS:
                raise AuditEvidenceIdentityError(
                    f"proposal names an unauthorized inventory: {relative}"
                )
            target = _pin_target(root, relative)
            pinned.append(target)
            raw = json.loads(target.original.decode("utf-8"))
            by_id = {row["id"]: row for row in raw["rows"]}
            for change in document["changes"]:
                row = by_id.get(change["id"])
                if row is None:
                    raise AuditEvidenceIdentityError(
                        f"proposal names an unknown row: {relative}:{change['id']}"
                    )
                current = _evidence_hashes(row.get("evidence", {}))
                if current != change["current"]:
                    raise AuditEvidenceIdentityError(
                        f"proposal preimage changed: {relative}:{change['id']}"
                    )
                changed_fields = {
                    field
                    for field in HASH_FIELDS
                    if change["current"][field] != change["proposed"][field]
                }
                if changed_fields - {
                    "source_sha256",
                    "rom_sha256",
                    "map_sha256",
                    "sym_sha256",
                }:
                    raise AuditEvidenceIdentityError(
                        f"proposal changes non-identity evidence: {relative}:{change['id']}"
                    )
                row["evidence"].update(change["proposed"])
            document_type = DOCUMENTS[relative]
            checked = (
                DiscoveryAssignmentAuthority.from_dict(raw)
                if relative.name == "assignments.json"
                else document_type.from_dict(raw)
            )
            updates.append((target, checked.to_json().encode()))
        _transactional_write(updates)
    finally:
        for target in pinned:
            os.close(target.directory_fd)


def propose(
    root: Path,
    transition_proposal: Path,
    *,
    transition_envelope_text: str | None = None,
) -> dict[str, object]:
    """Return hash-only, explicitly unreviewed inventory edits.

    Reviewer names and review flags are deliberately absent.  This producer
    can describe mechanical identity changes, but it cannot approve them or
    write any checked-in authority.
    """
    transition_path = (
        transition_proposal
        if transition_proposal.is_absolute()
        else root / transition_proposal
    )
    envelope = _strict_json(
        transition_path.read_text(encoding="utf-8")
        if transition_envelope_text is None
        else transition_envelope_text,
        label="source-transition proposal",
    )
    if set(envelope) != {"schema", "reviewed", "authority_path", "proposal"} or (
        envelope.get("schema") != source_transition.PROPOSAL_SCHEMA
        or envelope.get("reviewed") is not False
        or envelope.get("authority_path") != str(TRANSITION_PATH)
        or not isinstance(envelope.get("proposal"), dict)
    ):
        raise AuditEvidenceIdentityError("source-transition proposal is malformed")
    transition = envelope["proposal"]
    if (
        set(transition)
        != {
            "schema",
            "reviewed_source_sha256",
            "current_source_sha256",
            "baseline_manifest_sha256",
            "reviewed_delta_paths",
            "subject_rebindings",
            "rom_subject_rebindings",
            "audit_only_source_regions",
            "product_identities",
        }
        or transition["schema"] != source_transition.SCHEMA
    ):
        raise AuditEvidenceIdentityError("source-transition authority is malformed")
    source_sha256 = transition["current_source_sha256"]
    if (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_sha256)
    ):
        raise AuditEvidenceIdentityError(
            "source-transition current identity is not a lowercase SHA-256"
        )
    current_source_sha256 = discover_baseline_sources(root).source_sha256
    if source_sha256 != current_source_sha256:
        raise AuditEvidenceIdentityError(
            "source-transition identity does not match current baseline discovery"
        )
    try:
        canonical_transition = source_transition.generate_from_authority(
            root, transition
        )
    except source_transition.SourceTransitionError as exc:
        raise AuditEvidenceIdentityError(
            "source-transition authority failed canonical recomputation"
        ) from exc
    canonical_transition["reviewed_source_sha256"] = REVIEWED_SOURCE_SHA256
    canonical_transition["baseline_manifest_sha256"] = BASELINE_MANIFEST_SHA256
    if transition != canonical_transition:
        raise AuditEvidenceIdentityError(
            "source-transition authority does not match canonical recomputation"
        )
    baseline_hashes = _baseline_hashes(root, source_sha256)
    audit_hashes = _audit_hashes(root, source_sha256)
    documents: dict[str, object] = {}
    for relative, document_type in DOCUMENTS.items():
        path = root / relative
        raw = json.loads(path.read_text(encoding="utf-8"))
        before_by_id = {row["id"]: json.loads(json.dumps(row)) for row in raw["rows"]}
        if relative.name == "assignments.json":
            before = DiscoveryAssignmentAuthority.from_dict(raw)
            document = _updated_assignments(
                before, source_sha256, baseline_hashes, audit_hashes
            )
            _assert_assignment_delta(before, document)
        else:
            document = document_type.from_dict(
                _updated_document(
                    relative, raw, source_sha256, baseline_hashes, audit_hashes
                )
            )
        proposed = json.loads(document.to_json())
        changes = []
        for row in proposed["rows"]:
            before = before_by_id[row["id"]]
            current_hashes = _evidence_hashes(before.get("evidence", {}))
            proposed_hashes = _evidence_hashes(row.get("evidence", {}))
            if current_hashes != proposed_hashes:
                changes.append(
                    {
                        "id": row["id"],
                        "current": current_hashes,
                        "proposed": proposed_hashes,
                    }
                )
        documents[relative.as_posix()] = {"changes": changes}
    return {
        "schema": PROPOSAL_SCHEMA,
        "reviewed": False,
        "source_transition_proposal": str(transition_proposal),
        "documents": documents,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--transition-proposal", type=Path, required=True)
    outputs = parser.add_mutually_exclusive_group(required=True)
    outputs.add_argument("--proposal-output", type=Path)
    outputs.add_argument("--apply-proposal", type=Path)
    parser.add_argument("--authority-reviewed", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.apply_proposal is not None:
            if not args.authority_reviewed:
                raise AuditEvidenceIdentityError(
                    "applying checked-in identity changes requires --authority-reviewed"
                )
            apply_reviewed_proposal(
                args.root, args.transition_proposal, args.apply_proposal
            )
        else:
            if args.authority_reviewed:
                raise AuditEvidenceIdentityError(
                    "--authority-reviewed applies only to a reviewed proposal"
                )
            proposal = propose(args.root, args.transition_proposal)
            assert args.proposal_output is not None
            args.proposal_output.parent.mkdir(parents=True, exist_ok=True)
            args.proposal_output.write_text(
                json.dumps(proposal, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (OSError, ValueError, AuditEvidenceIdentityError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Rebind mechanically changed evidence identities through official serializers."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

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
    supplied = json.loads(proposal_path.read_text(encoding="utf-8"))
    expected = propose(root, transition_proposal)
    if supplied != expected:
        raise AuditEvidenceIdentityError(
            "reviewed audit-evidence proposal does not match canonical recomputation"
        )
    for relative_text, document in supplied["documents"].items():
        relative = Path(relative_text)
        if relative not in DOCUMENTS:
            raise AuditEvidenceIdentityError(
                f"proposal names an unauthorized inventory: {relative}"
            )
        path = root / relative
        raw = json.loads(path.read_text(encoding="utf-8"))
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
        path.write_text(checked.to_json(), encoding="utf-8")


def propose(root: Path, transition_proposal: Path) -> dict[str, object]:
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
    envelope = json.loads(transition_path.read_text(encoding="utf-8"))
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
        canonical_transition = source_transition.generate(root)
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

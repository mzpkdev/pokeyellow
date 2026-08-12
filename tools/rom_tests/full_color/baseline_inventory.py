"""Deterministic progress report for the reviewed baseline inventory tranche."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Sequence

from .baseline_discovery import discover_baseline_rom, discover_baseline_sources
from .discovery_assignment import (
    BASELINE_PRODUCT,
    DiscoveryAssignmentAuthority,
    PHASE2_AUDIT_PRODUCT,
    PRODUCTION_PRODUCTS,
    StaleDiscoveryAssignmentError,
)
from .discovery_review import rom_finding_subject, source_finding_subject
from .inventory import (
    InventoryReconciliationError,
    MutationInventory,
    SceneInventory,
    WriterInventory,
    reconcile,
)
from .source_transition import _rebound_rom_finding, _rebound_source_finding
from .conditional_source_authority import (
    ConditionalSourceAuthorityError,
    validate_regions,
)

PROGRESS_SCHEMA = "full-color-inventory-progress-v2"
REVIEWED_SLICE = "initial-map-entry-v1"

_OWNER_GATED_ROM_RESOURCES = frozenset(
    {
        "BG_WINDOW_MAP",
        "CGB_PALETTE",
        "DISPLAY_REGISTER",
        "HARDWARE_OAM",
        "HDMA_GDMA",
        "OAM_DMA_CONTROL",
        "SHADOW_OAM",
        "VRAM_BANK",
        "WRAM_BANK",
    }
)

SOURCE_TRANSITION_PATH = Path(
    "specs/full-colors/definitions/phase1-audit-source-transition.json"
)

PHASE2_PLANNED_ROW_IDS = frozenset(
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
        "SC-P2-PALLET-ROUTE1-NORTH",
        "SC-P2-PARTY-ENTRY",
        "SC-P2-PARTY-RETURN",
        "WR-P2-YELLOW-ANIMATION-TILES",
        "WR-P2-YELLOW-BG-PALETTE",
        "WR-P2-YELLOW-MAP-STREAM",
        "WR-P2-YELLOW-OAM-BUILD",
        "WR-P2-YELLOW-OAM-DMA",
        "WR-P2-YELLOW-OVERLAY-TRANSFER",
    }
)

_PLANNED_ONLY_ROW_CONTRACTS = {
    "WR-P2-YELLOW-BG-PALETTE": {
        "commit_unit": "PALETTE",
        "machine_sites": (
            {
                "bank": 0,
                "address": 0x3E14,
                "rom_offset": 0x3E14,
                "bytes": "fa1acf",
                "runtime_copy": None,
            },
        ),
        "resources": (
            {
                "aliases": [],
                "end": 0xFF69,
                "resource": "CGB_PALETTE",
                "start": 0xFF68,
                "vram_bank": None,
            },
        ),
        "root": "RunPaletteCommand",
        "source_sites": (
            {
                "aliases": [],
                "line": 47,
                "object": None,
                "path": "home/palettes.asm",
                "symbol": "RunPaletteCommand",
            },
        ),
    },
}


def _source_path_manifest(repository: Path, paths: Sequence[str]) -> dict[str, str]:
    return {
        relative: hashlib.sha256((repository / relative).read_bytes()).hexdigest()
        for relative in sorted(paths)
    }


def _manifest_sha256(manifest: dict[str, str]) -> str:
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _transition_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise InventoryReconciliationError("malformed audit-only transition path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != str(path) or "\\" in value or ".." in path.parts:
        raise InventoryReconciliationError(
            f"audit-only transition path is not normalized repository-relative: {value!r}"
        )
    return value


def _sha256_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _reviewed_source_view(
    assignments: DiscoveryAssignmentAuthority,
    source_report: Any,
    repository: Path,
) -> tuple[Any, dict[str, Any] | None]:
    """Verify and apply the explicit reviewed source-hash transition."""
    assignments = assignments.for_product(BASELINE_PRODUCT)
    reviewed_hashes = {row.evidence.source_sha256 for row in assignments.rows}
    if len(reviewed_hashes) != 1:
        raise StaleDiscoveryAssignmentError(
            "assignment rows have stale baseline evidence: mixed source hashes"
        )
    evidence_hash = next(iter(reviewed_hashes))
    path = repository / SOURCE_TRANSITION_PATH
    try:
        transition = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_strict_json_object
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        if source_report.source_sha256 == evidence_hash and not path.is_file():
            return source_report, None
        raise InventoryReconciliationError(
            "reviewed source hash changed without a valid audit-only transition"
        ) from exc
    expected_keys = {
        "schema", "reviewed_source_sha256", "current_source_sha256",
        "baseline_manifest_sha256", "reviewed_delta_paths", "subject_rebindings",
        "rom_subject_rebindings", "audit_only_source_regions", "product_identities",
    }
    if set(transition) != expected_keys or transition["schema"] != (
        "full-color-production-source-transition-v4"
    ):
        raise InventoryReconciliationError("malformed audit-only source transition")
    if transition["current_source_sha256"] != source_report.source_sha256:
        if source_report.source_sha256 == evidence_hash:
            return source_report, None
        raise InventoryReconciliationError("source transition does not bind current source hash")
    if evidence_hash not in {
        transition["reviewed_source_sha256"],
        transition["current_source_sha256"],
    }:
        raise InventoryReconciliationError(
            "assignment rows have stale baseline evidence: audit transition does not "
            "bind assignment source evidence"
        )
    current_manifest = _source_path_manifest(
        repository, (path for path, _ in source_report.include_graph)
    )
    baseline_manifest = dict(current_manifest)
    for relative, binding in transition["reviewed_delta_paths"].items():
        relative = _transition_path(relative)
        if set(binding) != {"reviewed_sha256", "current_sha256"}:
            raise InventoryReconciliationError(
                f"malformed reviewed transition path binding: {relative}"
            )
        actual = current_manifest.get(relative)
        current = binding["current_sha256"]
        if not _sha256_text(current):
            raise InventoryReconciliationError(
                f"malformed audit path hash: {relative}"
            )
        if actual != current:
            raise InventoryReconciliationError(
                f"reviewed transition path changed: {relative}"
            )
        reviewed = binding["reviewed_sha256"]
        if reviewed is None:
            if not (repository / relative).is_file():
                raise InventoryReconciliationError(
                    f"audit-only transition contains phantom added path: {relative}"
                )
            baseline_manifest.pop(relative, None)
        elif _sha256_text(reviewed):
            if reviewed == current:
                raise InventoryReconciliationError(
                    f"reviewed transition path has no actual delta: {relative}"
                )
            baseline_manifest[relative] = reviewed
        else:
            raise InventoryReconciliationError(
                f"malformed reviewed path hash: {relative}"
            )
    if _manifest_sha256(baseline_manifest) != transition["baseline_manifest_sha256"]:
        raise InventoryReconciliationError(
            "current source changed outside the hash-bound reviewed change set"
        )
    try:
        validate_regions(
            repository,
            transition["audit_only_source_regions"],
            transition["product_identities"],
            transition["reviewed_delta_paths"],
        )
    except (ConditionalSourceAuthorityError, OSError, UnicodeError, ValueError) as exc:
        raise InventoryReconciliationError(str(exc)) from exc
    source_rows = {
        row.subject.sha256: row
        for row in assignments.rows
        if row.subject.kind.value == "SOURCE_FINDING"
    }
    current_by_subject = {
        source_finding_subject(finding).sha256: finding
        for finding in source_report.findings
    }
    if set(transition["subject_rebindings"]) != set(source_rows):
        raise InventoryReconciliationError(
            "source transition does not enumerate reviewed semantic subjects"
        )
    translated: dict[str, Any] = {}
    for old_sha, new_sha in transition["subject_rebindings"].items():
        finding = current_by_subject.get(new_sha)
        row = source_rows[old_sha]
        if finding is None:
            raise InventoryReconciliationError(
                f"audit-only transition target subject is absent: {new_sha}"
            )
        rebound = _rebound_source_finding(
            repository, transition["reviewed_delta_paths"], finding, row
        )
        if source_finding_subject(rebound) != row.subject:
            raise InventoryReconciliationError(
                f"audit-only transition changes reviewed subject semantics: {old_sha}"
            )
        translated[new_sha] = rebound
    findings = tuple(
        translated.get(source_finding_subject(finding).sha256, finding)
        for finding in source_report.findings
    )
    return replace(source_report, findings=findings, source_sha256=evidence_hash), transition


def _reviewed_rom_view(
    assignments: DiscoveryAssignmentAuthority,
    rom_report: Any,
    transition: dict[str, Any] | None,
) -> Any:
    assignments = assignments.for_product(BASELINE_PRODUCT)
    if transition is None:
        return rom_report
    rows = {
        row.subject.sha256: row
        for row in assignments.rows
        if row.subject.kind.value == "ROM_FINDING"
    }
    current = {
        rom_finding_subject(finding).sha256: finding for finding in rom_report.findings
    }
    bindings = transition["rom_subject_rebindings"]
    if set(bindings) != set(rows):
        raise InventoryReconciliationError(
            "source transition does not enumerate reviewed ROM subjects"
        )
    translated: dict[str, Any] = {}
    for old_sha, new_sha in bindings.items():
        finding = current.get(new_sha)
        row = rows[old_sha]
        if finding is None:
            raise InventoryReconciliationError(
                f"audit-only transition ROM target subject is absent: {new_sha}"
            )
        rebound = _rebound_rom_finding(finding, row)
        if rom_finding_subject(rebound) != row.subject:
            raise InventoryReconciliationError(
                f"audit-only transition changes reviewed ROM semantics: {old_sha}"
            )
        translated[new_sha] = rebound
    findings = tuple(
        translated.get(rom_finding_subject(finding).sha256, finding)
        for finding in rom_report.findings
    )
    return replace(rom_report, findings=findings)


def _current_rom_layouts(
    assignments: DiscoveryAssignmentAuthority,
    rom_report: Any,
    transition: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve each reviewed ROM assignment to one current-layout finding."""
    if transition is None:
        return {}
    rows = {
        row.subject.sha256: row
        for row in assignments.rows
        if row.subject.kind.value == "ROM_FINDING"
    }
    current: dict[str, Any] = {}
    for finding in rom_report.findings:
        digest = rom_finding_subject(finding).sha256
        if digest in current:
            raise InventoryReconciliationError(
                f"duplicate current ROM transition subject: {digest}"
            )
        current[digest] = finding
    bindings = transition["rom_subject_rebindings"]
    if set(bindings) != set(rows):
        raise InventoryReconciliationError(
            "source transition does not enumerate reviewed ROM subjects"
        )
    layouts: dict[str, Any] = {}
    claimed: set[str] = set()
    for old_sha, new_sha in bindings.items():
        finding = current.get(new_sha)
        if finding is None:
            raise InventoryReconciliationError(
                f"audit-only transition ROM target subject is absent: {new_sha}"
            )
        row = rows[old_sha]
        if rom_finding_subject(_rebound_rom_finding(finding, row)) != row.subject:
            raise InventoryReconciliationError(
                f"audit-only transition changes reviewed ROM semantics: {old_sha}"
            )
        if new_sha in claimed:
            raise InventoryReconciliationError(
                "reviewed ROM subjects do not map uniquely to current findings"
            )
        claimed.add(new_sha)
        layouts[old_sha] = finding
    return layouts


def _restore_current_rom_report(rom_report: Any, layouts: dict[str, Any]) -> Any:
    """Restore current coordinates after reviewed assignment consumption."""
    if not layouts:
        return rom_report
    restored = []
    consumed: set[str] = set()
    for finding in rom_report.findings:
        digest = rom_finding_subject(finding).sha256
        current = layouts.get(digest)
        if current is None:
            restored.append(finding)
            continue
        if digest in consumed:
            raise InventoryReconciliationError(
                f"reviewed ROM layout restored more than once: {digest}"
            )
        consumed.add(digest)
        restored.append(replace(current, category=finding.category))
    missing = sorted(set(layouts) - consumed)
    if missing:
        raise InventoryReconciliationError(
            "reviewed ROM layout was not projected before restoration: "
            + ", ".join(missing)
        )
    return replace(rom_report, findings=tuple(restored))


def _restore_current_inventory_layout(
    document: Any,
    assignments: DiscoveryAssignmentAuthority,
    layouts: dict[str, Any],
) -> Any:
    """Move reviewed machine sites to current coordinates without changing bytes."""
    if not layouts:
        return document
    raw = json.loads(document.to_json())
    rows = {row["id"]: row for row in raw["rows"]}
    for assignment in assignments.rows:
        if assignment.subject.kind.value != "ROM_FINDING":
            continue
        current = layouts[assignment.subject.sha256]
        target = rows.get(assignment.row_id)
        if target is None:
            continue
        reviewed = assignment.subject.metadata
        matches = [
            site
            for site in target.get("machine_sites", ())
            if (
                site["bank"],
                site["address"],
                site["rom_offset"],
                site["bytes"],
            )
            == (
                reviewed["bank"],
                reviewed["address"],
                reviewed["rom_offset"],
                reviewed["bytes"],
            )
        ]
        if len(matches) != 1:
            raise InventoryReconciliationError(
                f"{assignment.row_id}: reviewed ROM machine site has "
                f"{len(matches)} exact inventory matches; expected one"
            )
        site = matches[0]
        if current.bytes != site["bytes"]:
            raise InventoryReconciliationError(
                f"{assignment.row_id}: current ROM layout changes reviewed bytes"
            )
        site.update(
            bank=current.bank,
            address=current.address,
            rom_offset=current.rom_offset,
        )
    for row in raw["rows"]:
        row["machine_sites"] = sorted(
            row.get("machine_sites", ()),
            key=lambda site: (site["bank"], site["address"]),
        )
    return type(document).from_dict(raw)


def _partition_authority(document: Any) -> tuple[Any, tuple[dict[str, Any], ...]]:
    """Return a revalidated frozen tranche plus declared planned rows."""
    reviewed = tuple(row for row in document.rows if not row["planned"])
    planned = tuple(row for row in document.rows if row["planned"])
    reviewed_document = type(document).from_dict(
        {"schema": document.schema, "rows": list(reviewed)}
    )
    return reviewed_document, planned


def _select_inventory_rows(document: Any, row_ids: set[str]) -> Any:
    """Select only rows owned by one link-product assignment partition."""
    return type(document).from_dict(
        {
            "schema": document.schema,
            "rows": [row for row in document.rows if row["id"] in row_ids],
        }
    )


def _phase2_transition_state(
    *,
    writers: WriterInventory,
    scenes: SceneInventory,
    mutations: MutationInventory,
    assignments: DiscoveryAssignmentAuthority,
) -> str:
    """Require the hostile tranche to be wholly planned or production-closed."""
    rows = {
        row["id"]: row
        for document in (writers, scenes, mutations)
        for row in document.rows
        if row["id"] in PHASE2_PLANNED_ROW_IDS
    }
    if set(rows) != PHASE2_PLANNED_ROW_IDS:
        raise InventoryReconciliationError(
            "planned Phase 2 row IDs must be the exact closed set; "
            f"missing={sorted(PHASE2_PLANNED_ROW_IDS - set(rows))}"
        )
    partitions = {
        product: assignments.for_product(product) for product in PRODUCTION_PRODUCTS
    }
    audit = assignments.for_product(PHASE2_AUDIT_PRODUCT)
    assigned = tuple(
        row for authority in partitions.values() for row in authority.rows
        if row.row_id in PHASE2_PLANNED_ROW_IDS
    )
    audit_phase2 = tuple(
        row for row in audit.rows if row.row_id in PHASE2_PLANNED_ROW_IDS
    )
    planned = {row_id for row_id, row in rows.items() if row["planned"]}
    reviewed = {
        row_id for row_id, row in rows.items() if row["evidence"]["reviewed"]
    }
    if planned == PHASE2_PLANNED_ROW_IDS and not reviewed and not assigned and not audit_phase2:
        return "planned"
    if planned == PHASE2_PLANNED_ROW_IDS and reviewed:
        raise InventoryReconciliationError(
            "planned row cannot claim reviewed evidence"
        )
    if planned == PHASE2_PLANNED_ROW_IDS and (assigned or audit_phase2):
        raise InventoryReconciliationError(
            "planned hostile rows consume closure assignments"
        )
    if (
        not planned
        and reviewed == PHASE2_PLANNED_ROW_IDS
        and all(
            {
                row.row_id for row in authority.rows
                if row.row_id in PHASE2_PLANNED_ROW_IDS
            } == PHASE2_PLANNED_ROW_IDS
            for authority in partitions.values()
        )
        and {
            row.row_id for row in audit.rows if row.row_id in PHASE2_PLANNED_ROW_IDS
        } == PHASE2_PLANNED_ROW_IDS
    ):
        return "production-closed"
    raise InventoryReconciliationError(
        "Phase 2 closure must transition all 18 rows atomically from "
        "planned/unreviewed/unassigned to reviewed production and diagnostic assignments"
    )


def _validate_planned_rows(
    *,
    writers: WriterInventory,
    scenes: SceneInventory,
    mutations: MutationInventory,
    assignments: DiscoveryAssignmentAuthority,
    source_report: Any,
    rom_report: Any,
    rom: bytes,
    repository: Path,
) -> tuple[dict[str, Any], ...]:
    """Validate declarations without promoting them into baseline closure."""
    all_rows = tuple(writers.rows) + tuple(scenes.rows) + tuple(mutations.rows)
    planned = tuple(row for row in all_rows if row["planned"])
    reviewed = tuple(row for row in all_rows if not row["planned"])
    errors: list[str] = []
    assigned_ids = {row.row_id for row in assignments.rows}
    writer_ids = {row["id"] for row in writers.rows}
    current_hashes = {
        "source_sha256": source_report.source_sha256,
        "rom_sha256": rom_report.rom_sha256,
        "sym_sha256": rom_report.sym_sha256,
        "map_sha256": rom_report.map_sha256,
    }
    planned_ids = {row["id"] for row in planned}
    if planned_ids != PHASE2_PLANNED_ROW_IDS:
        errors.append(
            "planned Phase 2 row IDs must be the exact closed set; "
            f"missing={sorted(PHASE2_PLANNED_ROW_IDS - planned_ids)}, "
            f"unexpected={sorted(planned_ids - PHASE2_PLANNED_ROW_IDS)}"
        )
    for row in reviewed:
        if not row["evidence"]["reviewed"]:
            errors.append(f"{row['id']}: frozen reviewed row became unreviewed")
    for row in planned:
        if row["evidence"]["reviewed"]:
            errors.append(f"{row['id']}: planned row cannot claim reviewed evidence")
        if row["id"] in assigned_ids:
            errors.append(f"{row['id']}: planned row cannot consume a closure assignment")
        for name, expected in current_hashes.items():
            if row["evidence"][name] != expected:
                errors.append(f"{row['id']}: stale planned {name.removesuffix('_sha256')} hash")
        declared_sources = (
            (row["source"],)
            if row["id"].startswith("SC-")
            else tuple(row.get("source_sites", ()))
        )
        if not declared_sources:
            errors.append(f"{row['id']}: planned row lacks required source evidence")
        if not row.get("machine_sites"):
            errors.append(f"{row['id']}: planned row lacks required machine evidence")
        for site in row.get("machine_sites", ()):
            expected = bytes.fromhex(site["bytes"])
            start = site["rom_offset"]
            if rom[start : start + len(expected)] != expected:
                errors.append(
                    f"{row['id']}: planned machine bytes do not match "
                    f"{site['bank']:02x}:{site['address']:04x}"
                )
        contract = _PLANNED_ONLY_ROW_CONTRACTS.get(row["id"])
        if contract is not None:
            if tuple(row.get("machine_sites", ())) != contract["machine_sites"]:
                errors.append(f"{row['id']}: planned-only machine-site contract changed")
            if tuple(row.get("source_sites", ())) != contract["source_sites"]:
                errors.append(f"{row['id']}: planned-only source-site contract changed")
            if tuple(row.get("resources", ())) != contract["resources"]:
                errors.append(f"{row['id']}: planned-only resource contract changed")
            if row.get("commit_unit") != contract["commit_unit"]:
                errors.append(f"{row['id']}: planned-only commit contract changed")
            reachability = row.get("reachability", {})
            if (
                reachability.get("roots") != [contract["root"]]
                or reachability.get("call_paths") != [[contract["root"]]]
            ):
                errors.append(f"{row['id']}: planned-only root contract changed")
    for row in scenes.rows:
        missing = sorted(set(row["first_display_writers"]) - writer_ids)
        if missing:
            errors.append(f"{row['id']}: unknown first-display writers {missing}")
    for row in mutations.rows:
        missing = sorted(set(row["writer_ids"]) - writer_ids)
        if missing:
            errors.append(f"{row['id']}: unknown mutation writers {missing}")
    if errors:
        raise InventoryReconciliationError("\n".join(sorted(errors)))
    return planned


def _assert_no_unlisted_slice_findings(
    assignments: DiscoveryAssignmentAuthority,
    source_report: Any,
    rom_report: Any,
    *,
    rebound_rom_sites: set[tuple[int, int]] = frozenset(),
) -> None:
    """Fail closed for new subjects within the reviewed map-entry slice."""
    source_subjects = {
        row.subject.sha256
        for row in assignments.rows
        if row.subject.kind.value == "SOURCE_FINDING"
    }
    rom_subjects = {
        row.subject.sha256
        for row in assignments.rows
        if row.subject.kind.value == "ROM_FINDING"
    }
    reviewed_rom_sites = {
        (row.subject.metadata["bank"], row.subject.metadata["address"])
        for row in assignments.rows
        if row.subject.kind.value == "ROM_FINDING"
    } | set(rebound_rom_sites)
    source_roots = {
        (row.subject.metadata["category"], row.subject.metadata["symbol"])
        for row in assignments.rows
        if row.subject.kind.value == "SOURCE_FINDING"
    }
    source_shapes = {
        (
            row.subject.metadata["category"],
            row.subject.metadata["symbol"],
            row.subject.metadata["mechanism"],
        )
        for row in assignments.rows
        if row.subject.kind.value == "SOURCE_FINDING"
        and row.subject.metadata["category"] != "writer"
    }
    rom_roots = {
        (row.subject.metadata["category"], row.subject.metadata["root"])
        for row in assignments.rows
        if row.subject.kind.value == "ROM_FINDING"
    }
    rom_shapes = {
        (
            row.subject.metadata["category"],
            row.subject.metadata["root"],
            row.subject.metadata["control_flow_kind"],
        )
        for row in assignments.rows
        if row.subject.kind.value == "ROM_FINDING"
        and row.subject.metadata["category"] != "writer"
    }

    def belongs_to_root(name: str, root: str) -> bool:
        return name == root or name.startswith(root + ".")

    unexpected_source = []
    for finding in source_report.findings:
        if source_finding_subject(finding).sha256 in source_subjects:
            continue
        shape = (finding.category, finding.symbol, finding.mechanism)
        in_slice = shape in source_shapes or any(
            finding.category == category
            and (
                (category == "writer" and belongs_to_root(finding.symbol, root))
                or finding.symbol.startswith(root + ".")
            )
            for category, root in source_roots
        )
        if in_slice:
            unexpected_source.append(
                f"{finding.category}:{finding.path}:{finding.line}:{finding.symbol}"
            )

    unexpected_rom = []
    seen_rom_sites: set[tuple[int, int]] = set()
    for finding in (*rom_report.findings, *rom_report.candidate_findings):
        if rom_finding_subject(finding).sha256 in rom_subjects:
            continue
        shape = (finding.category, finding.root, finding.control_flow_kind)
        in_slice = shape in rom_shapes or any(
            finding.category == category
            and (
                (category == "writer" and belongs_to_root(finding.root, root))
                or finding.root.startswith(root + ".")
            )
            and (
                category != "writer"
                or finding.resource in _OWNER_GATED_ROM_RESOURCES
            )
            for category, root in rom_roots
        )
        site = (finding.bank, finding.address)
        if (
            in_slice
            and site not in reviewed_rom_sites
            and site not in seen_rom_sites
        ):
            seen_rom_sites.add(site)
            unexpected_rom.append(
                f"{finding.category}:{finding.root}:{finding.bank:02x}:"
                f"{finding.address:04x}:{finding.resource}"
            )

    errors = []
    if unexpected_source:
        errors.append(
            "unexpected unlisted source item(s) in reviewed slice: "
            + ", ".join(sorted(unexpected_source))
        )
    if unexpected_rom:
        errors.append(
            "unexpected unlisted ROM item(s) in reviewed slice: "
            + ", ".join(sorted(unexpected_rom))
        )
    if errors:
        raise InventoryReconciliationError("\n".join(errors))


def _validate_assignment_targets(
    assignments: DiscoveryAssignmentAuthority,
    writers: WriterInventory,
    scenes: SceneInventory,
    mutations: MutationInventory,
) -> None:
    targets = {
        row["id"]: row
        for rows in (writers.rows, scenes.rows, mutations.rows)
        for row in rows
    }
    errors: list[str] = []
    for assignment in assignments.rows:
        target = targets.get(assignment.row_id)
        if target is None:
            errors.append(f"{assignment.id}: target row does not exist")
            continue
        metadata = assignment.subject.metadata
        if assignment.subject.kind.value == "SOURCE_FINDING":
            source_sites = (
                (target["source"],)
                if assignment.category.value == "scene"
                else target["source_sites"]
            )
            source_key = (
                metadata["path"],
                metadata["line"],
                metadata["symbol"],
            )
            if not any(
                source_key == (site["path"], site["line"], site["symbol"])
                for site in source_sites
            ):
                errors.append(
                    f"{assignment.id}: source subject does not belong to "
                    f"{assignment.row_id}"
                )
                continue
            if assignment.category.value == "mutation":
                destination = (
                    metadata["destination"]
                    if assignment.mutation is None
                    else assignment.mutation.destination
                )
                if destination != target["destination"]:
                    errors.append(
                        f"{assignment.id}: mutation destination does not match "
                        f"{assignment.row_id}"
                    )
            if assignment.category.value == "scene":
                enrichment = assignment.scene
                destination = target["destination"]
                expected_shape = (
                    target["row_kind"],
                    target["direction"],
                    None if destination is None else destination["path"],
                    None if destination is None else destination["line"],
                    None if destination is None else destination["symbol"],
                )
                actual_shape = (
                    enrichment.row_kind,
                    enrichment.direction,
                    enrichment.destination_path,
                    enrichment.destination_line,
                    enrichment.destination_symbol,
                )
                if actual_shape != expected_shape:
                    errors.append(
                        f"{assignment.id}: scene shape does not match "
                        f"{assignment.row_id}"
                    )
        else:
            machine_key = (
                metadata["bank"],
                metadata["address"],
                metadata["bytes"],
            )
            if not any(
                machine_key == (site["bank"], site["address"], site["bytes"])
                for site in target["machine_sites"]
            ):
                errors.append(
                    f"{assignment.id}: ROM subject does not belong to "
                    f"{assignment.row_id}"
                )
    if errors:
        raise InventoryReconciliationError("\n".join(errors))


def _project_assignments(
    assignments: DiscoveryAssignmentAuthority,
    source_report: Any,
    rom_report: Any,
    *,
    matcher: Any | None = None,
) -> tuple[Any, Any, tuple[str, ...], tuple[str, ...]]:
    hashes = {
        "source_sha256": source_report.source_sha256,
        "rom_sha256": rom_report.rom_sha256,
        "sym_sha256": rom_report.sym_sha256,
        "map_sha256": rom_report.map_sha256,
    }
    matcher = matcher or assignments.matcher(**hashes, product=BASELINE_PRODUCT)
    subjects = {row.subject.sha256: row for row in assignments.rows}
    source_rows: list[str] = []
    rom_rows: list[str] = []
    source_findings = []
    for finding in source_report.findings:
        row = subjects.get(source_finding_subject(finding).sha256)
        if row is None:
            source_findings.append(finding)
        else:
            source_findings.append(matcher.project_source_finding(finding))
            source_rows.append(row.row_id)
    rom_findings = []
    for finding in rom_report.findings:
        row = subjects.get(rom_finding_subject(finding).sha256)
        if row is None:
            rom_findings.append(finding)
        else:
            rom_findings.append(matcher.project_rom_finding(finding))
            rom_rows.append(row.row_id)
    candidate_findings = []
    for finding in rom_report.candidate_findings:
        row = subjects.get(rom_finding_subject(finding).sha256)
        if row is None:
            candidate_findings.append(finding)
        else:
            candidate_findings.append(matcher.project_rom_finding(finding))
            rom_rows.append(row.row_id)
    matcher.assert_all_consumed()
    return (
        replace(source_report, findings=tuple(source_findings)),
        replace(
            rom_report,
            findings=tuple(rom_findings),
            candidate_findings=tuple(candidate_findings),
        ),
        tuple(sorted(source_rows)),
        tuple(sorted(rom_rows)),
    )


def build_progress(
    *,
    writers: WriterInventory,
    scenes: SceneInventory,
    mutations: MutationInventory,
    assignments: DiscoveryAssignmentAuthority,
    source_report: Any,
    rom_report: Any,
    rom: bytes,
    repository: str | Path = ".",
) -> dict[str, Any]:
    """Project reviewed assignments once and report honest remaining work."""
    all_writers, all_scenes, all_mutations = writers, scenes, mutations
    repository_path = Path(repository).resolve()
    phase2_state = _phase2_transition_state(
        writers=writers, scenes=scenes, mutations=mutations, assignments=assignments
    )
    normal_assignments = assignments.for_product(BASELINE_PRODUCT)
    _validate_assignment_targets(normal_assignments, writers, scenes, mutations)
    reviewed_source, source_transition = _reviewed_source_view(
        normal_assignments, source_report, repository_path
    )
    rebound_rom_sites = set()
    if source_transition is not None:
        current_by_subject = {
            rom_finding_subject(finding).sha256: finding
            for finding in rom_report.findings
        }
        rebound_rom_sites = {
            (current_by_subject[digest].bank, current_by_subject[digest].address)
            for digest in source_transition["rom_subject_rebindings"].values()
            if digest in current_by_subject
        }
    reviewed_rom = _reviewed_rom_view(normal_assignments, rom_report, source_transition)
    current_rom_layouts = _current_rom_layouts(
        normal_assignments, rom_report, source_transition
    )
    _assert_no_unlisted_slice_findings(
        normal_assignments,
        reviewed_source,
        reviewed_rom,
        rebound_rom_sites=rebound_rom_sites,
    )
    matcher = normal_assignments.matcher(
        source_sha256=reviewed_source.source_sha256,
        rom_sha256=rom_report.rom_sha256,
        sym_sha256=rom_report.sym_sha256,
        map_sha256=rom_report.map_sha256,
        product=BASELINE_PRODUCT,
    )
    projected_source, projected_rom, source_rows, rom_rows = _project_assignments(
        normal_assignments, reviewed_source, reviewed_rom, matcher=matcher
    )
    projected_rom = _restore_current_rom_report(
        projected_rom, current_rom_layouts
    )
    if phase2_state == "planned":
        planned = _validate_planned_rows(
            writers=writers,
            scenes=scenes,
            mutations=mutations,
            assignments=normal_assignments,
            source_report=source_report,
            rom_report=rom_report,
            rom=rom,
            repository=repository_path,
        )
    else:
        planned = ()
    normal_row_ids = {row.row_id for row in normal_assignments.rows}
    writers = _select_inventory_rows(writers, normal_row_ids)
    scenes = _select_inventory_rows(scenes, normal_row_ids)
    mutations = _select_inventory_rows(mutations, normal_row_ids)
    writers = _restore_current_inventory_layout(
        writers, normal_assignments, current_rom_layouts
    )
    scenes = _restore_current_inventory_layout(
        scenes, normal_assignments, current_rom_layouts
    )
    mutations = _restore_current_inventory_layout(
        mutations, normal_assignments, current_rom_layouts
    )
    report = reconcile(
        writers,
        scenes,
        mutations,
        source_report=projected_source,
        rom_report=projected_rom,
        rom=rom,
        raise_on_error=False,
    )
    rows = tuple(writers.rows) + tuple(scenes.rows) + tuple(mutations.rows)
    row_ids = tuple(sorted(row["id"] for row in rows))
    if set(source_rows) != set(row_ids):
        raise InventoryReconciliationError(
            "every reviewed row requires an exact source assignment"
        )
    if set(rom_rows) != set(row_ids):
        raise InventoryReconciliationError(
            "every reviewed row requires an exact ROM assignment"
        )
    checked_errors = tuple(
        error for error in report.errors if any(row_id in error for row_id in row_ids)
    )
    expected_source = (
        sum(len(row["source_sites"]) for row in writers.rows)
        + len(scenes.rows)
        + sum(len(row["source_sites"]) for row in mutations.rows)
    )
    expected_machine = sum(len(row.get("machine_sites", ())) for row in rows)
    if checked_errors:
        raise InventoryReconciliationError("\n".join(checked_errors))
    if len(report.matched_source_sites) != expected_source:
        raise InventoryReconciliationError("reviewed source rows did not all match")
    if len(report.matched_machine_sites) != expected_machine:
        raise InventoryReconciliationError("reviewed machine rows did not all match")

    backlog = {
        "diagnostics": len(projected_source.errors),
        "errors": len(report.errors),
        "rom_candidates": len(projected_rom.candidate_findings),
        "rom_findings": len(projected_rom.findings) - len(rom_rows),
        "source_findings": len(projected_source.findings) - len(source_rows),
        "unresolved": len(projected_rom.unresolved_destinations)
        + len(projected_rom.unresolved_control_flow),
    }
    return {
        "assigned": {
            "rom_count": len(rom_rows),
            "rom_row_ids": list(rom_rows),
            "source_count": len(source_rows),
            "source_row_ids": list(source_rows),
        },
        "backlog": backlog,
        "closed": True,
        "hashes": {
            "assignments_sha256": assignments.sha256,
            "map_sha256": projected_rom.map_sha256,
            "mutations_sha256": all_mutations.sha256,
            "rom_sha256": projected_rom.rom_sha256,
            "scenes_sha256": all_scenes.sha256,
            "source_sha256": projected_source.source_sha256,
            "sym_sha256": projected_rom.sym_sha256,
            "writers_sha256": all_writers.sha256,
        },
        "matched": {
            "machine_count": len(report.matched_machine_sites),
            "machine_row_ids": list(row_ids),
            "source_count": len(report.matched_source_sites),
            "source_row_ids": list(row_ids),
        },
        "reviewed_slice": {
            "closed": True,
            "name": REVIEWED_SLICE,
            "rom_unlisted_count": 0,
            "source_unlisted_count": 0,
        },
        "reviewed_rows": {
            "mutation_count": len(mutations.rows),
            "row_ids": list(row_ids),
            "scene_count": len(scenes.rows),
            "total_count": len(rows),
            "writer_count": len(writers.rows),
        },
        "planned_rows": {
            "row_ids": sorted(row["id"] for row in planned),
            "total_count": len(planned),
        },
        "source_transition": source_transition,
        "schema": PROGRESS_SCHEMA,
    }


def baseline_inventory_progress(repository: str | Path = ".") -> dict[str, Any]:
    root = Path(repository)
    authority = root / "specs/full-colors/inventory"
    writers = WriterInventory.load(authority / "writers.json")
    scenes = SceneInventory.load(authority / "scenes.json")
    mutations = MutationInventory.load(authority / "mutations.json")
    assignments = DiscoveryAssignmentAuthority.load(authority / "assignments.json")
    source_report = discover_baseline_sources(root)
    rom_report = discover_baseline_rom(root, source_report=source_report)
    return build_progress(
        writers=writers,
        scenes=scenes,
        mutations=mutations,
        assignments=assignments,
        source_report=source_report,
        rom_report=rom_report,
        rom=(root / "pokeyellow_debug.gbc").read_bytes(),
        repository=root,
    )


def progress_json(repository: str | Path = ".") -> str:
    return (
        json.dumps(
            baseline_inventory_progress(repository),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report baseline inventory progress.")
    parser.add_argument("--repository", default=".")
    args = parser.parse_args(argv)
    print(progress_json(args.repository), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

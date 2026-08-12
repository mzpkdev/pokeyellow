"""Generate the fail-closed reviewed-to-current source transition."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Collection, Iterable, Sequence

from . import baseline_discovery as baseline
from .conditional_source_authority import (
    ConditionalSourceAuthorityError,
    build_regions,
    product_identities,
)
from .discovery_assignment import (
    BASELINE_PRODUCT,
    DiscoveryAssignmentAuthority,
)
from .discovery_review import rom_finding_subject, source_finding_subject
from .rom_discovery import discover_rom_batched, load_map, load_sym


SCHEMA = "full-color-production-source-transition-v4"
PREDECESSOR_SCHEMA = "full-color-production-source-transition-v3"
PROPOSAL_SCHEMA = "full-color-source-transition-proposal-v1"
TRANSITION_PATH = Path(
    "specs/full-colors/definitions/phase1-audit-source-transition.json"
)
ASSIGNMENTS_PATH = Path("specs/full-colors/inventory/assignments.json")


class SourceTransitionError(RuntimeError):
    """The immutable reviewed authority cannot map uniquely to current evidence."""


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def _manifest_sha256(manifest: dict[str, str]) -> str:
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _source_line_sha256(path: str, line: int, evidence: str) -> str:
    return hashlib.sha256(
        f"{path}\0{line}\0{evidence.rstrip()}".encode("utf-8")
    ).hexdigest()


def _rebound_source_finding(
    root: Path,
    reviewed_delta_paths: Collection[str],
    finding: Any,
    row: Any,
) -> Any:
    reviewed = row.subject.metadata
    reviewed_symbol = reviewed["symbol"]
    if finding.symbol != reviewed_symbol and not finding.symbol.startswith(
        f"{reviewed_symbol}."
    ):
        return finding
    rebound = replace(finding, symbol=reviewed_symbol)
    if finding.path not in reviewed_delta_paths:
        return rebound
    try:
        evidence = (root / finding.path).read_text(encoding="utf-8").splitlines()[
            finding.line - 1
        ]
    except (IndexError, OSError, UnicodeError):
        return rebound
    if finding.evidence_sha256 != _source_line_sha256(
        finding.path, finding.line, evidence
    ) or reviewed["evidence_sha256"] != _source_line_sha256(
        finding.path, reviewed["line"], evidence
    ):
        return rebound
    destination_line = finding.destination_line
    if finding.destination_path in reviewed_delta_paths:
        destination_line = reviewed["destination_line"]
    return replace(
        rebound,
        line=reviewed["line"],
        evidence_sha256=reviewed["evidence_sha256"],
        destination_line=destination_line,
    )


def _unique_rebindings(
    rows: Iterable[Any],
    findings: Iterable[Any],
    *,
    subject: Callable[[Any], Any],
    rebound: Callable[[Any, Any], Any],
    kind: str,
) -> dict[str, str]:
    current = tuple(findings)
    result: dict[str, str] = {}
    claimed: set[str] = set()
    for row in rows:
        matches = [
            finding
            for finding in current
            if subject(rebound(finding, row)).sha256 == row.subject.sha256
        ]
        if len(matches) != 1:
            raise SourceTransitionError(
                f"reviewed {kind} subject {row.subject.sha256} has "
                f"{len(matches)} semantic matches; expected exactly one"
            )
        current_sha = subject(matches[0]).sha256
        if current_sha in claimed:
            raise SourceTransitionError(
                f"reviewed {kind} subjects do not map uniquely to current findings"
            )
        claimed.add(current_sha)
        result[row.subject.sha256] = current_sha
    return dict(sorted(result.items()))


def _rebound_rom_finding(finding: Any, row: Any) -> Any:
    """Rebind layout-only ROM drift while preserving reviewed semantics."""
    reviewed = row.subject.metadata
    reviewed_root = reviewed["root"]
    if finding.root != reviewed_root and not finding.root.startswith(
        reviewed_root + "."
    ):
        return finding
    actual = finding.to_dict()
    semantic_fields = (
        "bytes", "mechanism", "resource", "resolved", "category",
        "control_flow_kind", "runtime_copy", "vbk_low", "vbk_high",
        "dma_source_low", "dma_source_high",
    )
    if any(actual[name] != reviewed[name] for name in semantic_fields):
        return finding
    if finding.mechanism != "root-entry" and any(
        actual[name] != reviewed[name]
        for name in ("destination_low", "destination_high")
    ):
        return finding
    if not _call_path_preserves_ancestry(
        tuple(reviewed["call_path"]), finding.call_path
    ):
        return finding
    runtime_copy = reviewed["runtime_copy"]
    rebound_runtime = None if runtime_copy is None else (
        runtime_copy["address"], runtime_copy["length"], runtime_copy["launcher"]
    )
    return replace(
        finding,
        bank=reviewed["bank"], address=reviewed["address"],
        rom_offset=reviewed["rom_offset"], root=reviewed_root,
        call_path=tuple(reviewed["call_path"]),
        destination_low=reviewed["destination_low"],
        destination_high=reviewed["destination_high"],
        runtime_copy=rebound_runtime,
    )


_CALL_SITE = re.compile(r"^(?P<bank>[0-9a-fA-F]+):[0-9a-fA-F]{4}$")


def _call_path_preserves_ancestry(
    reviewed: tuple[str, ...], current: tuple[str, ...]
) -> bool:
    """Accept address relocation without laundering a different call chain.

    Symbolic ancestors are semantic identities.  A current local label may
    refine the reviewed owning symbol, while address-only call sites may move
    within the same bank.  Same-depth unrelated paths are never ancestry.
    """
    if len(reviewed) != len(current):
        return False
    for expected, actual in zip(reviewed, current, strict=True):
        if actual == expected or actual.startswith(expected + "."):
            continue
        expected_site = _CALL_SITE.fullmatch(expected)
        actual_site = _CALL_SITE.fullmatch(actual)
        if (
            expected_site is not None
            and actual_site is not None
            and expected_site["bank"].lower() == actual_site["bank"].lower()
        ):
            continue
        return False
    return True


def _raw_baseline_rom(root: Path, source_report: Any) -> Any:
    symbols = load_sym(root / "pokeyellow_debug.sym")
    source_writers = set(baseline.writer_roots(source_report))
    linked_writer_roots = source_writers & symbols.by_name.keys()
    scene_roots = tuple(
        sorted(set(baseline.LIFECYCLE_ROOTS) | set(baseline.SCENE_ROOTS))
    )
    roots = tuple(
        sorted(
            linked_writer_roots
            | set(scene_roots)
            | set(baseline.MUTATION_ROOTS)
        )
    )
    return discover_rom_batched(
        (root / "pokeyellow_debug.gbc").read_bytes(),
        symbols,
        roots,
        batch_size=16,
        sections=load_map(root / "pokeyellow_debug.map"),
        farcall_labels=baseline.FARCALL_LABELS,
        predef_targets=baseline.load_predef_targets(root, symbols),
        copied_regions=baseline.COPIED_REGIONS,
        shadow_oam_ranges=baseline.SHADOW_OAM_RANGES,
        scene_roots=scene_roots,
        mutation_roots=baseline.MUTATION_ROOTS,
        dma_control_labels=baseline.DMA_CONTROL_LABELS,
        follow_calls=False,
    )


def generate(root: Path, *, authority_path: Path | None = None) -> dict[str, object]:
    authority_file = authority_path or root / TRANSITION_PATH
    try:
        authority = json.loads(
            authority_file.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SourceTransitionError("source-transition authority is unreadable") from exc
    return generate_from_authority(root, authority)


def generate_from_authority(
    root: Path, authority: dict[str, object]
) -> dict[str, object]:
    """Canonically recompute a loaded reviewed or proposed transition."""
    common = {
        "schema",
        "reviewed_source_sha256",
        "current_source_sha256",
        "baseline_manifest_sha256",
        "reviewed_delta_paths",
        "subject_rebindings",
        "rom_subject_rebindings",
    }
    schema = authority.get("schema")
    expected = set(common)
    if schema == SCHEMA:
        expected |= {"audit_only_source_regions", "product_identities"}
    elif schema != PREDECESSOR_SCHEMA:
        raise SourceTransitionError("source-transition authority is malformed")
    if set(authority) != expected:
        raise SourceTransitionError("source-transition authority is malformed")
    raw_paths = authority["reviewed_delta_paths"]

    source_report = baseline.discover_baseline_sources(root)
    include_paths = {path for path, _ in source_report.include_graph}
    current_manifest = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in sorted(include_paths)
    }
    reviewed_delta_paths: dict[str, dict[str, str | None]] = {}
    baseline_manifest = dict(current_manifest)
    for relative, binding in raw_paths.items():
        if relative not in current_manifest:
            raise SourceTransitionError(f"reviewed delta path is no longer linked: {relative}")
        if set(binding) != {"reviewed_sha256", "current_sha256"}:
            raise SourceTransitionError(
                f"reviewed delta path binding is malformed: {relative}"
            )
        reviewed = binding["reviewed_sha256"]
        reviewed_delta_paths[relative] = {
            "reviewed_sha256": reviewed,
            "current_sha256": current_manifest[relative],
        }
        if reviewed is None:
            baseline_manifest.pop(relative)
        else:
            baseline_manifest[relative] = reviewed
    if _manifest_sha256(baseline_manifest) != authority["baseline_manifest_sha256"]:
        raise SourceTransitionError(
            "current source changed outside the immutable reviewed delta partition"
        )

    assignments = DiscoveryAssignmentAuthority.load(
        root / ASSIGNMENTS_PATH
    ).for_product(BASELINE_PRODUCT)
    source_rows = [
        row for row in assignments.rows if row.subject.kind.value == "SOURCE_FINDING"
    ]
    rom_rows = [
        row for row in assignments.rows if row.subject.kind.value == "ROM_FINDING"
    ]
    subject_rebindings = _unique_rebindings(
        source_rows,
        source_report.findings,
        subject=source_finding_subject,
        rebound=lambda finding, row: _rebound_source_finding(
            root, reviewed_delta_paths, finding, row
        ),
        kind="source",
    )
    rom_report = _raw_baseline_rom(root, source_report)
    rom_subject_rebindings = _unique_rebindings(
        rom_rows,
        rom_report.findings,
        subject=rom_finding_subject,
        rebound=_rebound_rom_finding,
        kind="ROM",
    )
    debug_symbols = load_sym(root / "pokeyellow_debug.sym")
    missing_writer_pairs = {
        (finding.path, finding.symbol)
        for finding in source_report.findings
        if finding.category == "writer"
        and finding.symbol not in debug_symbols.by_name
        and finding.path in reviewed_delta_paths
        and reviewed_delta_paths[finding.path]["reviewed_sha256"] is not None
    }
    missing_writers = {symbol for _, symbol in missing_writer_pairs}
    all_missing_writers = {
        finding.symbol
        for finding in source_report.findings
        if finding.category == "writer" and finding.symbol not in debug_symbols.by_name
    }
    added_paths = {
        path for path, binding in reviewed_delta_paths.items()
        if binding["reviewed_sha256"] is None
    }
    unclassified = {
        finding.symbol
        for finding in source_report.findings
        if finding.category == "writer"
        and finding.symbol in all_missing_writers
        and finding.path not in added_paths
        and finding.symbol not in missing_writers
    }
    if unclassified:
        raise SourceTransitionError(
            "unlinked writer lacks an added-file or conditional-region predecessor: "
            + ", ".join(sorted(unclassified))
        )
    if schema == SCHEMA:
        pairs = {
            (row["path"], row["symbol"])
            for row in authority["audit_only_source_regions"]
            if isinstance(row, dict)
            and isinstance(row.get("path"), str)
            and isinstance(row.get("symbol"), str)
        }
        if len(pairs) != len(authority["audit_only_source_regions"]):
            raise SourceTransitionError("source-transition conditional regions are malformed")
        if pairs != missing_writer_pairs:
            raise SourceTransitionError(
                "source-transition conditional regions do not enumerate exact unlinked writers"
            )
    else:
        pairs = {
            (finding.path, finding.symbol)
            for finding in source_report.findings
            if (finding.path, finding.symbol) in missing_writer_pairs
        }
    try:
        conditional_regions = build_regions(root, pairs, reviewed_delta_paths)
        products = product_identities(root)
    except (ConditionalSourceAuthorityError, OSError, UnicodeError, ValueError) as exc:
        raise SourceTransitionError(str(exc)) from exc
    return {
        "schema": SCHEMA,
        "reviewed_source_sha256": authority["reviewed_source_sha256"],
        "current_source_sha256": source_report.source_sha256,
        "baseline_manifest_sha256": authority["baseline_manifest_sha256"],
        "reviewed_delta_paths": dict(sorted(reviewed_delta_paths.items())),
        "subject_rebindings": subject_rebindings,
        "rom_subject_rebindings": rom_subject_rebindings,
        "audit_only_source_regions": conditional_regions,
        "product_identities": products,
    }


def generate_json(root: Path, *, authority_path: Path | None = None) -> str:
    return _canonical(generate(root, authority_path=authority_path))


def generate_proposal(
    root: Path, *, authority_path: Path | None = None
) -> dict[str, object]:
    return {
        "schema": PROPOSAL_SCHEMA,
        "reviewed": False,
        "authority_path": str(TRANSITION_PATH),
        "proposal": generate(root, authority_path=authority_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--authority", type=Path)
    parser.add_argument("--proposal-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rendered = _canonical(
            generate_proposal(args.root, authority_path=args.authority)
        )
        args.proposal_output.parent.mkdir(parents=True, exist_ok=True)
        args.proposal_output.write_text(rendered, encoding="utf-8")
    except (OSError, SourceTransitionError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Reviewed entry configuration for the unmodified Yellow debug ROM."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Any, Sequence

from .rom_discovery import (
    BankAddress,
    CopiedRegion,
    RomDiscoveryError,
    RomDiscoveryReport,
    SymbolTable,
    discover_rom_batched,
    load_map,
    load_sym,
)
from .source_discovery import SourceDiscoveryReport, discover_sources
from .conditional_source_authority import (
    ConditionalSourceAuthorityError,
    validate_regions,
)

SOURCE_ROOTS = (
    "audio.asm",
    "gfx/pics.asm",
    "gfx/pikachu.asm",
    "gfx/sprites.asm",
    "gfx/surfing_pikachu.asm",
    "gfx/tilesets.asm",
    "home.asm",
    "includes.asm",
    "main.asm",
    "maps.asm",
    "ram.asm",
    "text.asm",
)
SHADOW_OAM_RANGES = (
    (0xC300, 0xC39F),
    (0xC508, 0xC5A7),
)
COPIED_REGIONS = (
    CopiedRegion(
        bank=0x01,
        address=0x4AAC,
        runtime_address=0xFF80,
        length=0x0A,
        launcher="WriteDMACodeToHRAM",
    ),
)
FARCALL_LABELS = ("Bankswitch", "JumpToAddress")
DMA_CONTROL_LABELS = ("DMARoutine", "WriteDMACodeToHRAM", "hDMARoutine")
LIFECYCLE_ROOTS = ("EnterMap",)
SCENE_ROOTS: tuple[str, ...] = ()
MUTATION_ROOTS = ("CopyMapViewToVRAM",)
SOURCE_TRANSITION_PATH = Path(
    "specs/full-colors/definitions/phase1-audit-source-transition.json"
)

_PREDEF = re.compile(
    r"^\s*add_predef\s+([A-Za-z_][\w#.]*)(?:\s*,\s*\$([0-9a-f]+))?"
    r"(?:\s*;.*)?$",
    re.IGNORECASE,
)


def discover_baseline_sources(repository: str | Path) -> SourceDiscoveryReport:
    """Discover every linked source translation unit in canonical order."""
    return discover_sources(
        repository,
        SOURCE_ROOTS,
        lifecycle_roots=LIFECYCLE_ROOTS,
        scene_roots=SCENE_ROOTS,
        mutation_roots=MUTATION_ROOTS,
    )


def writer_roots(report: SourceDiscoveryReport) -> tuple[str, ...]:
    """Return every source-backed writer label for ROM reachability."""
    return tuple(
        sorted(
            {
                finding.symbol
                for finding in report.findings
                if finding.category == "writer"
            }
        )
    )


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _sha256_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _manifest_sha256(manifest: dict[str, str]) -> str:
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validated_audit_only_authority(
    repository: Path,
    report: SourceDiscoveryReport,
) -> tuple[frozenset[str], frozenset[tuple[str, str]]]:
    """Return exact added-file and conditional-symbol audit authority."""
    path = repository / SOURCE_TRANSITION_PATH
    try:
        transition = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_object,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RomDiscoveryError(
            "unlinked source writer requires a valid reviewed source transition"
        ) from exc
    expected_keys = {
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
    if set(transition) != expected_keys or transition["schema"] != (
        "full-color-production-source-transition-v4"
    ):
        raise RomDiscoveryError("malformed reviewed source transition")
    if transition["current_source_sha256"] != report.source_sha256:
        raise RomDiscoveryError(
            "reviewed source transition does not bind current source discovery"
        )
    if not _sha256_text(transition["reviewed_source_sha256"]):
        raise RomDiscoveryError("malformed reviewed source identity")
    bindings = transition["reviewed_delta_paths"]
    if not isinstance(bindings, dict):
        raise RomDiscoveryError("malformed audit-only path manifest")

    current_manifest = {
        relative: hashlib.sha256((repository / relative).read_bytes()).hexdigest()
        for relative, _ in report.include_graph
    }
    baseline_manifest = dict(current_manifest)
    added: set[str] = set()
    for relative, binding in bindings.items():
        if not isinstance(relative, str) or not relative:
            raise RomDiscoveryError("malformed audit-only transition path")
        normalized = PurePosixPath(relative)
        if (
            normalized.is_absolute()
            or relative != str(normalized)
            or "\\" in relative
            or ".." in normalized.parts
        ):
            raise RomDiscoveryError(
                f"audit-only transition path is not normalized: {relative!r}"
            )
        if not isinstance(binding, dict) or set(binding) != {
            "reviewed_sha256",
            "current_sha256",
        }:
            raise RomDiscoveryError(
                f"malformed audit-only path binding: {relative}"
            )
        audit_sha256 = binding["current_sha256"]
        if not _sha256_text(audit_sha256):
            raise RomDiscoveryError(f"malformed audit path identity: {relative}")
        if current_manifest.get(relative) != audit_sha256:
            raise RomDiscoveryError(f"audit-only transition path changed: {relative}")
        reviewed_sha256 = binding["reviewed_sha256"]
        if reviewed_sha256 is None:
            baseline_manifest.pop(relative, None)
            added.add(relative)
        elif _sha256_text(reviewed_sha256) and reviewed_sha256 != audit_sha256:
            baseline_manifest[relative] = reviewed_sha256
        else:
            raise RomDiscoveryError(
                f"malformed reviewed path identity: {relative}"
            )
    if _manifest_sha256(baseline_manifest) != transition["baseline_manifest_sha256"]:
        raise RomDiscoveryError(
            "current source changed outside the hash-bound audit-only partition"
        )
    try:
        symbols = validate_regions(
            repository,
            transition["audit_only_source_regions"],
            transition["product_identities"],
            bindings,
        )
    except (ConditionalSourceAuthorityError, OSError, UnicodeError, ValueError) as exc:
        raise RomDiscoveryError(str(exc)) from exc
    return frozenset(added), symbols


def _validated_audit_only_added_paths(
    repository: Path,
    report: SourceDiscoveryReport,
) -> frozenset[str]:
    """Compatibility helper returning only reviewed added-file authority."""
    return _validated_audit_only_authority(repository, report)[0]


def load_predef_targets(
    repository: str | Path,
    symbols: SymbolTable,
) -> dict[int, BankAddress]:
    """Resolve the ordered `add_predef` authority, including bank overrides."""
    path = Path(repository) / "data/predef_pointers.asm"
    targets: dict[int, BankAddress] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _PREDEF.match(line)
        if not match:
            continue
        name, override = match.groups()
        try:
            symbol = symbols.by_name[name]
        except KeyError as exc:
            raise RomDiscoveryError(
                f"{path.relative_to(repository)}: unknown predef symbol {name!r}"
            ) from exc
        bank = symbol.bank if override is None else int(override, 16)
        targets[len(targets)] = BankAddress(bank, symbol.address)
    if tuple(targets) != tuple(range(99)):
        raise RomDiscoveryError(
            "data/predef_pointers.asm: expected exactly 99 ordered predef rows"
        )
    return targets


def discover_baseline_rom(
    repository: str | Path,
    *,
    source_report: SourceDiscoveryReport | None = None,
    batch_size: int = 16,
) -> RomDiscoveryReport:
    """Run bounded source-rooted discovery against the baseline debug build."""
    root = Path(repository)
    report = source_report or discover_baseline_sources(root)
    symbols = load_sym(root / "pokeyellow_debug.sym")
    scene_roots = tuple(sorted(set(LIFECYCLE_ROOTS) | set(SCENE_ROOTS)))
    source_writers = set(writer_roots(report))
    missing_writers = source_writers - symbols.by_name.keys()
    if missing_writers:
        audit_only_paths, audit_only_symbols = _validated_audit_only_authority(
            root, report
        )
        unproven = sorted(
            {
                finding.symbol
                for finding in report.findings
                if finding.category == "writer"
                and finding.symbol in missing_writers
                and finding.path not in audit_only_paths
                and (finding.path, finding.symbol) not in audit_only_symbols
            }
        )
        if unproven:
            raise RomDiscoveryError(
                "source-discovered writer is absent from the baseline ROM and is not "
                "in the exact hash-bound audit-only partition or reviewed "
                "conditional region: "
                + ", ".join(unproven)
            )
    linked_writer_roots = source_writers - missing_writers
    roots = tuple(
        sorted(linked_writer_roots | set(scene_roots) | set(MUTATION_ROOTS))
    )
    return discover_rom_batched(
        (root / "pokeyellow_debug.gbc").read_bytes(),
        symbols,
        roots,
        batch_size=batch_size,
        sections=load_map(root / "pokeyellow_debug.map"),
        farcall_labels=FARCALL_LABELS,
        predef_targets=load_predef_targets(root, symbols),
        copied_regions=COPIED_REGIONS,
        shadow_oam_ranges=SHADOW_OAM_RANGES,
        scene_roots=scene_roots,
        mutation_roots=MUTATION_ROOTS,
        dma_control_labels=DMA_CONTROL_LABELS,
        follow_calls=False,
    )


def baseline_summary(repository: str | Path) -> dict[str, Any]:
    """Return byte-stable evidence that the real baseline audit completed."""
    source = discover_baseline_sources(repository)
    rom = discover_baseline_rom(repository, source_report=source)
    return {
        "schema": "full-color-baseline-discovery-summary-v1",
        "source": {
            "sha256": source.source_sha256,
            "roots": len(source.roots),
            "files": len(source.include_graph),
            "findings": len(source.findings),
            "writer_roots": len(writer_roots(source)),
            "diagnostics": len(source.errors),
        },
        "rom": {
            "sha256": rom.rom_sha256,
            "sym_sha256": rom.sym_sha256,
            "map_sha256": rom.map_sha256,
            "findings": len(rom.findings),
            "visited_sites": len(rom.visited),
            "unresolved_destinations": len(rom.unresolved_destinations),
            "unresolved_control_flow": len(rom.unresolved_control_flow),
            "candidate_findings": len(rom.candidate_findings),
            "candidate_sections": len(rom.candidate_sections),
        },
    }


def summary_json(repository: str | Path) -> str:
    return (
        json.dumps(
            baseline_summary(repository),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic full-color baseline discovery."
    )
    parser.add_argument(
        "--repository",
        default=".",
        help="repository containing pokeyellow_debug.gbc/.sym/.map",
    )
    args = parser.parse_args(argv)
    print(summary_json(args.repository), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

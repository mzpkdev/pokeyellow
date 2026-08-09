"""Contracts for deterministic map-background review atlases."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib
from pathlib import Path

import pytest

from tools.rom_tests.full_color import map_background_atlas
from tools.rom_tests.full_color.map_background_atlas import (
    ATLAS_CELL,
    ATLAS_COLUMNS,
    BATCH_TILESETS,
    SCHEMA,
    TILE_COUNT,
    build_atlases,
    canonical_json,
    moving_water_frames,
    render_tileset_atlas,
)
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT
from tools.rom_tests.tests.e2e.renderer.test_full_color_map_background_batches import (
    _begin_case_results,
    _canonical_json,
    _publish_case_results,
    _write_retained_manifest,
    validate_yellow_payloads,
)
from tools.rom_tests.scenarios.map_background_routes import (
    BATCH_ROUTES,
    validate_route,
)


@pytest.fixture(scope="module")
def atlas_manifest(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    output = tmp_path_factory.mktemp("map-background-atlas")
    return build_atlases(REPOSITORY_ROOT, output)


def _palette_payload(*, palette_one_red: bool = False) -> bytes:
    values = bytearray(64)
    # palette 0 color 1 = blue; palette 1 color 1 optionally = red
    values[2:4] = (0x00, 0x7C)
    if palette_one_red:
        values[10:12] = (0x1F, 0x00)
    return bytes(values)


def test_phase3_batches_are_the_exact_closed_partition() -> None:
    assert BATCH_TILESETS == {
        "overworld": ("OVERWORLD",),
        "residential-services": (
            "REDS_HOUSE_1",
            "REDS_HOUSE_2",
            "MART",
            "POKECENTER",
            "HOUSE",
            "FOREST_GATE",
            "MUSEUM",
            "GATE",
            "LOBBY",
            "LAB",
            "CLUB",
        ),
        "challenge-special-interiors": (
            "DOJO",
            "GYM",
            "UNDERGROUND",
            "SHIP",
            "CEMETERY",
            "INTERIOR",
            "MANSION",
            "FACILITY",
        ),
    }


def test_atlas_has_deterministic_dimensions_order_and_complete_coverage() -> None:
    graphics = bytes([0xFF, 0x00] * 8)
    attributes = bytes(TILE_COUNT)
    image, records = render_tileset_atlas(
        graphics, _palette_payload(), attributes, bytes(16)
    )
    assert image.size == (ATLAS_COLUMNS * ATLAS_CELL[0], 16 * ATLAS_CELL[1])
    assert [record["tile_id"] for record in records] == list(range(TILE_COUNT))
    assert Counter(record["semantic"] for record in records) == {
        "used": 1,
        "missing": 95,
        "text-reserved": 160,
    }
    assert records[0] == {
        "tile_id": 0,
        "palette": 0,
        "attribute": 0,
        "semantic": "used",
        "source_graphic": True,
    }


def test_palette_and_attribute_mutations_change_rendered_pixels() -> None:
    graphics = bytes([0xFF, 0x00] * 8)
    blockset = bytes(16)
    attributes = bytearray(TILE_COUNT)
    baseline, _ = render_tileset_atlas(
        graphics, _palette_payload(), bytes(attributes), blockset
    )

    palette_mutated, _ = render_tileset_atlas(
        graphics,
        _palette_payload().replace(bytes((0x00, 0x7C)), bytes((0x1F, 0x00)), 1),
        bytes(attributes),
        blockset,
    )
    assert baseline.tobytes() != palette_mutated.tobytes()

    attributes[0] = 1
    attribute_mutated, _ = render_tileset_atlas(
        graphics, _palette_payload(palette_one_red=True), bytes(attributes), blockset
    )
    assert baseline.tobytes() != attribute_mutated.tobytes()


def test_complete_phase3_manifest_binds_every_tileset_map_and_source(
    atlas_manifest: dict[str, object],
) -> None:
    assert atlas_manifest["schema"] == SCHEMA
    unhashed = dict(atlas_manifest)
    content_sha256 = unhashed.pop("content_sha256")
    assert (
        content_sha256
        == hashlib.sha256(canonical_json(unhashed).encode("utf-8")).hexdigest()
    )
    tilesets = atlas_manifest["tilesets"]
    assert isinstance(tilesets, list)
    assert len(tilesets) == 20
    assert sum(len(row["maps"]) for row in tilesets) == 196
    assert [row["name"] for row in tilesets] == [
        tileset for batch in BATCH_TILESETS.values() for tileset in batch
    ]
    for row in tilesets:
        assert row["tile_order"] == list(range(TILE_COUNT))
        assert len(row["tiles"]) == TILE_COUNT
        assert row["graphics_source"]["sha256"] == row["graphics_linked"]["sha256"]
        assert row["blockset_source"]["sha256"] == row["blockset_linked"]["sha256"]
        assert row["palette"]["size"] == 64
        assert row["attributes"]["size"] == TILE_COUNT
        assert row["maps"] == sorted(
            row["maps"], key=lambda item: (item["name"], item["id"])
        )
        assert all(item["artifact"]["sha256"] for item in row["maps"])
    overworld = next(row for row in tilesets if row["name"] == "OVERWORLD")
    assert all(item["roof_identity"] is not None for item in overworld["maps"])
    overrides = {
        item["name"]: item["attribute_overrides"]
        for row in tilesets
        for item in row["maps"]
        if item["attribute_overrides"]
    }
    assert set(overrides) == {"CELADON_MART_1F", "CELADON_MART_ROOF"}
    assert len(overrides["CELADON_MART_1F"]) == 4
    assert len(overrides["CELADON_MART_ROOF"]) == 5


def test_animation_and_replacement_review_surfaces_are_explicit(
    atlas_manifest: dict[str, object],
) -> None:
    overworld = next(
        row for row in atlas_manifest["tilesets"] if row["name"] == "OVERWORLD"
    )
    animations = overworld["animations"]
    assert Counter(item["kind"] for item in animations) == {
        "flower": 3,
        "water-rotation": 8,
    }
    assert {item["tile_id"] for item in animations} == {0x03, 0x14}
    assert all(item["artifact"]["sha256"] for item in animations)
    assert all(item["observation"].startswith("artifact-only-") for item in animations)
    assert len(overworld["replacements"]) == 9
    assert all(item["identity"] == "CUT_TREE" for item in overworld["replacements"])
    assert all(
        item["observation"] == "artifact-only-rendered-pair"
        for item in overworld["replacements"]
    )
    assert all(item["artifact"]["sha256"] for item in overworld["replacements"])


def test_water_frames_match_update_moving_bg_tiles_counter_semantics() -> None:
    base = bytes(range(16))
    frames = moving_water_frames(base)
    assert [(counter, direction) for counter, direction, _ in frames] == [
        (1, "right"),
        (2, "right"),
        (3, "right"),
        (4, "left"),
        (5, "left"),
        (6, "left"),
        (7, "left"),
        (0, "right"),
    ]
    current = base
    expected_hashes = []
    for counter in (1, 2, 3, 4, 5, 6, 7, 0):
        if counter & 4:
            current = bytes((((value << 1) & 0xFF) | (value >> 7)) for value in current)
        else:
            current = bytes(((value >> 1) | ((value & 1) << 7)) for value in current)
        expected_hashes.append(hashlib.sha256(current).hexdigest())
    assert [
        hashlib.sha256(data).hexdigest() for _, _, data in frames
    ] == expected_hashes


def test_water_manifest_binds_fixed_routine_source_and_frame_sequence(
    atlas_manifest: dict[str, object],
) -> None:
    overworld = next(
        row for row in atlas_manifest["tilesets"] if row["name"] == "OVERWORLD"
    )
    records = [
        row for row in overworld["animations"] if row["kind"] == "water-rotation"
    ]
    source = REPOSITORY_ROOT / "home/vcopy.asm"
    current_source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    assert current_source_sha256 == (
        "6bcf200c1b53bac0f0dab06770a30fedd53c25504370848d525b32f4c6a54a9a"
    )
    assert {row["routine"] for row in records} == {"UpdateMovingBgTiles"}
    assert {row["routine_source_path"] for row in records} == {"home/vcopy.asm"}
    assert {row["routine_source_file_sha256"] for row in records} == {
        current_source_sha256
    }

    base = (REPOSITORY_ROOT / "gfx/tilesets/overworld.2bpp").read_bytes()[
        0x14 * 16 : 0x15 * 16
    ]
    frames = moving_water_frames(base)
    assert records[0]["input_frame_sha256"] == hashlib.sha256(base).hexdigest()
    assert [row["output_frame_sha256"] for row in records] == [
        hashlib.sha256(data).hexdigest() for _, _, data in frames
    ]
    assert [row["input_frame_sha256"] for row in records[1:]] == [
        row["output_frame_sha256"] for row in records[:-1]
    ]

    mutated = bytes((base[0] ^ 1,)) + base[1:]
    mutated_frames = moving_water_frames(mutated)
    assert hashlib.sha256(mutated).hexdigest() != records[0]["input_frame_sha256"]
    assert [hashlib.sha256(data).hexdigest() for _, _, data in mutated_frames] != [
        row["output_frame_sha256"] for row in records
    ]


def test_only_60_through_ff_are_text_reserved_and_underground_19_is_graphics(
    atlas_manifest: dict[str, object],
) -> None:
    underground = next(
        row for row in atlas_manifest["tilesets"] if row["name"] == "UNDERGROUND"
    )
    records = underground["tiles"]
    assert all(record["semantic"] != "text-reserved" for record in records[:0x60])
    assert all(record["semantic"] == "text-reserved" for record in records[0x60:])
    assert records[0x19]["semantic"] in {"used", "unused", "missing"}


def test_partial_batch_publish_removes_prior_batch_without_stale_files(
    tmp_path: Path,
) -> None:
    output = tmp_path / "published"
    build_atlases(REPOSITORY_ROOT, output, batches=("overworld",))
    assert (output / "overworld").is_dir()
    build_atlases(REPOSITORY_ROOT, output, batches=("residential-services",))
    assert not (output / "overworld").exists()
    assert (output / "residential-services").is_dir()


def test_failed_publish_preserves_existing_complete_output(tmp_path: Path) -> None:
    output = tmp_path / "published"
    first = build_atlases(REPOSITORY_ROOT, output, batches=("overworld",))
    with pytest.raises(Exception):
        build_atlases(REPOSITORY_ROOT / "absent", output, batches=("overworld",))
    assert canonical_json(first) == (output / "manifest.json").read_text(
        encoding="utf-8"
    )


def test_replace_failure_rolls_back_complete_previous_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    first = build_atlases(REPOSITORY_ROOT, output, batches=("overworld",))
    before = {
        path.relative_to(output).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in output.rglob("*")
        if path.is_file()
    }
    real_replace = map_background_atlas.os.replace
    injected = False

    def fail_new_publication(source: object, destination: object) -> None:
        nonlocal injected
        source_path, destination_path = Path(source), Path(destination)
        if (
            not injected
            and source_path.name.startswith(f".{output.name}.tmp-")
            and destination_path == output
        ):
            injected = True
            raise OSError("injected final publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(map_background_atlas.os, "replace", fail_new_publication)
    with pytest.raises(OSError, match="injected final publication failure"):
        build_atlases(REPOSITORY_ROOT, output, batches=("residential-services",))

    assert injected
    assert canonical_json(first) == (output / "manifest.json").read_text(
        encoding="utf-8"
    )
    after = {
        path.relative_to(output).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in output.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not list(tmp_path.glob(f".{output.name}.backup-*"))


@pytest.mark.parametrize("corruption", ("attribute", "palette"))
def test_yellow_payload_validation_rejects_corruption(corruption: str) -> None:
    attributes = bytearray(360)
    expected_palettes = bytes(range(64))
    palettes = bytearray(expected_palettes)
    if corruption == "attribute":
        attributes[17] = 1
    else:
        palettes[23] ^= 1
    with pytest.raises(AssertionError):
        validate_yellow_payloads(bytes(attributes), bytes(palettes), expected_palettes)


def test_repeated_build_has_identical_manifest_and_artifact_hashes(
    tmp_path: Path,
) -> None:
    first = build_atlases(REPOSITORY_ROOT, tmp_path / "first", batches=("overworld",))
    second = build_atlases(REPOSITORY_ROOT, tmp_path / "second", batches=("overworld",))
    assert canonical_json(first) == canonical_json(second)
    assert first["artifacts"] == second["artifacts"]


def test_case_result_transaction_removes_stale_success_and_preserves_failure(
    tmp_path: Path,
) -> None:
    stable = tmp_path / "case"
    stable.mkdir()
    (stable / "map-background-route-failure.png").write_bytes(b"stale")

    running = _begin_case_results(stable)
    assert not stable.exists()
    (running / "current.png").write_bytes(b"current")
    _publish_case_results(running, stable)
    assert {path.name for path in stable.iterdir()} == {"current.png"}

    failure_run = _begin_case_results(stable)
    assert not stable.exists()
    (failure_run / "map-background-route-failure.png").write_bytes(b"new failure")
    _publish_case_results(failure_run, stable)
    assert (stable / "map-background-route-failure.png").read_bytes() == b"new failure"
    assert not (stable / "current.png").exists()


def test_retained_manifest_is_canonical_complete_and_reproducible(
    tmp_path: Path,
) -> None:
    route = BATCH_ROUTES[0]
    manifests = []
    for name in ("first", "second"):
        results = tmp_path / name
        for checkpoint in route.checkpoints:
            for relative in (
                checkpoint.retained_screenshot,
                checkpoint.retained_frame_strip,
            ):
                path = results / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"{relative}\n".encode())
        manifests.append(
            _write_retained_manifest(
                results, route=route, product="pokeyellow", mode="color"
            )
        )
    assert _canonical_json(manifests[0]) == _canonical_json(manifests[1])
    assert manifests[0]["artifacts"] == manifests[1]["artifacts"]
    unhashed = dict(manifests[0])
    content_sha256 = unhashed.pop("content_sha256")
    assert (
        content_sha256
        == hashlib.sha256(_canonical_json(unhashed).encode("utf-8")).hexdigest()
    )
    assert all(
        {
            "path",
            "sha256",
            "route",
            "product",
            "checkpoint",
            "mode",
            "kind",
            "map_name",
            "natural_driver",
            "tile_sample_purposes",
            "tile_samples",
        }
        <= set(row)
        for row in manifests[0]["artifacts"]
    )
    first_checkpoint = route.checkpoints[0]
    first_artifact = next(
        row
        for row in manifests[0]["artifacts"]
        if row["checkpoint"] == first_checkpoint.name
    )
    assert first_artifact["tile_samples"] == [
        {
            "tile_id": sample.tile_id,
            "attribute_authority": sample.attribute_authority,
            "expected_attribute": sample.expected_attribute,
            "purpose": sample.purpose,
        }
        for sample in first_checkpoint.tile_samples
    ]
    unlisted = tmp_path / "first" / "unlisted.png"
    unlisted.write_bytes(b"not declared")
    with pytest.raises(AssertionError, match="unlisted or missing"):
        _write_retained_manifest(
            tmp_path / "first", route=route, product="pokeyellow", mode="color"
        )


@pytest.mark.parametrize("field", ("purpose", "map_name", "natural_driver"))
def test_route_evidence_claim_mutations_fail_closed(field: str) -> None:
    route = BATCH_ROUTES[0]
    if field == "purpose":
        checkpoint = route.checkpoints[0]
        sample = replace(checkpoint.tile_samples[0], purpose="vegetation")
        mutated_checkpoint = replace(
            checkpoint, tile_samples=(sample, *checkpoint.tile_samples[1:])
        )
        mutated = replace(
            route, checkpoints=(mutated_checkpoint, *route.checkpoints[1:])
        )
    elif field == "map_name":
        checkpoint = replace(route.checkpoints[0], map_name="VIRIDIAN_CITY")
        mutated = replace(route, checkpoints=(checkpoint, *route.checkpoints[1:]))
    else:
        mutated = replace(route, natural_driver=("teleport_to_checkpoint",))
    with pytest.raises(ValueError):
        validate_route(mutated)


def test_route_and_manifest_reject_duplicate_paths_before_write(tmp_path: Path) -> None:
    route = BATCH_ROUTES[0]
    first, second, *remaining = route.checkpoints
    duplicate = replace(second, retained_screenshot=first.retained_screenshot)
    mutated = replace(route, checkpoints=(first, duplicate, *remaining))

    with pytest.raises(ValueError, match="globally unique"):
        validate_route(mutated)
    with pytest.raises(AssertionError, match="globally unique"):
        _write_retained_manifest(
            tmp_path, route=mutated, product="pokeyellow", mode="color"
        )
    assert not (tmp_path / "retained-artifacts.json").exists()

"""Contracts for deterministic map-background review atlases."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import threading
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

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
    source_2bpp,
)
from tools.rom_tests.scenarios.map_background_routes import (
    ARTIFACT_ONLY_PURPOSE,
    ARTIFACT_REVIEW_ROUTES,
    BATCH_ROUTES,
    validate_artifact_review_route,
    validate_route,
)
from tools.rom_tests.tests.conftest import REPOSITORY_ROOT
from tools.rom_tests.tests.e2e.renderer.test_full_color_map_background_batches import (
    _begin_case_results,
    _canonical_json,
    _publish_case_results,
    _write_retained_manifest,
    validate_yellow_payloads,
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


def _write_owned_output(output: Path, artifact: str = "batch/map.png") -> None:
    artifact_path = output / artifact
    artifact_path.parent.mkdir(parents=True)
    data = b"atlas image"
    artifact_path.write_bytes(data)
    manifest = {
        "schema": SCHEMA,
        "producer": "tools.rom_tests.full_color.map_background_atlas",
        "artifacts": [
            {
                "path": artifact,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        ],
    }
    manifest["content_sha256"] = hashlib.sha256(
        canonical_json(manifest).encode("utf-8")
    ).hexdigest()
    (output / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")


def _write_test_atlas(
    _root: Path, output: Path, **_kwargs: object
) -> dict[str, object]:
    _write_owned_output(output)
    return json.loads((output / "manifest.json").read_text(encoding="utf-8"))


def _current_artifact(output: Path) -> Path:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    return output / manifest["artifacts"][0]["path"]


def test_review_batches_are_the_exact_closed_partition() -> None:
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
        "forest-cavern": ("FOREST", "CAVERN"),
        "transport-special": ("SHIP_PORT", "PLATEAU", "BEACH_HOUSE"),
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


def test_complete_review_manifest_binds_every_tileset_map_and_source(
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
    assert len(tilesets) == 25
    assert sum(len(row["maps"]) for row in tilesets) == 224
    assert [row["name"] for row in tilesets] == [
        tileset for batch in BATCH_TILESETS.values() for tileset in batch
    ]
    for row in tilesets:
        assert row["tile_order"] == list(range(TILE_COUNT))
        assert len(row["tiles"]) == TILE_COUNT
        assert row["graphics_input"]["path"].endswith(".png")
        assert row["graphics_input"]["sha256"]
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
    expected_animations = {
        "OVERWORLD": "TILEANIM_WATER_FLOWER",
        "FOREST": "TILEANIM_WATER",
        "DOJO": "TILEANIM_WATER_FLOWER",
        "GYM": "TILEANIM_WATER_FLOWER",
        "SHIP": "TILEANIM_WATER",
        "SHIP_PORT": "TILEANIM_WATER",
        "CAVERN": "TILEANIM_WATER",
        "FACILITY": "TILEANIM_WATER",
        "PLATEAU": "TILEANIM_WATER",
    }
    for row in atlas_manifest["tilesets"]:
        rotations = [
            item for item in row["animations"] if item["kind"] == "water-rotation"
        ]
        flowers = [item for item in row["animations"] if item["kind"] == "flower"]
        if row["name"] in expected_animations:
            assert len(rotations) == 8
            assert {item["identity"] for item in rotations} == {
                expected_animations[row["name"]]
            }
            assert len(flowers) == (
                3 if expected_animations[row["name"]] == "TILEANIM_WATER_FLOWER" else 0
            )
            assert all(
                item["source_input"]["path"].endswith(".png") for item in rotations
            )
        else:
            assert rotations == []
            assert flowers == []


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

    base = source_2bpp(REPOSITORY_ROOT, Path("gfx/tilesets/overworld.2bpp"))[
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


def test_phase4_batch_atlases_cover_every_map_and_preserve_text_reservation(
    atlas_manifest: dict[str, object],
) -> None:
    expected = {"forest-cavern": (2, 24), "transport-special": (3, 4)}
    for batch, (tileset_count, map_count) in expected.items():
        rows = [row for row in atlas_manifest["tilesets"] if row["batch"] == batch]
        assert len(rows) == tileset_count
        assert sum(len(row["maps"]) for row in rows) == map_count
        assert all(
            all(tile["semantic"] == "text-reserved" for tile in row["tiles"][0x60:])
            for row in rows
        )
    forest = next(row for row in atlas_manifest["tilesets"] if row["name"] == "FOREST")
    cavern = next(row for row in atlas_manifest["tilesets"] if row["name"] == "CAVERN")
    assert forest["tiles"][0x14]["semantic"] != "text-reserved"
    assert cavern["tiles"][0x14]["semantic"] != "text-reserved"


def test_any_declared_water_animation_cannot_pass_with_zero_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(map_background_atlas, "_animation_frames", lambda *args: [])
    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasError,
        match="declared water animation lacks eight review frames",
    ):
        build_atlases(
            REPOSITORY_ROOT,
            tmp_path / "atlas",
            batches=("challenge-special-interiors",),
        )


def test_partial_batch_publish_removes_prior_batch_without_stale_files(
    tmp_path: Path,
) -> None:
    output = tmp_path / "published"
    build_atlases(REPOSITORY_ROOT, output, batches=("overworld",))
    old_manifest = json.loads((output / "manifest.json").read_text())
    old_paths = {record["path"] for record in old_manifest["artifacts"]}
    assert all((output / path).is_file() for path in old_paths)
    build_atlases(REPOSITORY_ROOT, output, batches=("residential-services",))
    new_manifest = json.loads((output / "manifest.json").read_text())
    new_paths = {record["path"] for record in new_manifest["artifacts"]}
    assert old_paths.isdisjoint(new_paths)
    assert all((output / path).is_file() for path in old_paths | new_paths)
    retained = tmp_path / f".{output.name}.prior"
    assert all((retained / path).is_file() for path in old_paths)


def test_failed_publish_preserves_existing_complete_output(tmp_path: Path) -> None:
    output = tmp_path / "published"
    first = build_atlases(REPOSITORY_ROOT, output, batches=("overworld",))
    with pytest.raises((OSError, ValueError)):
        build_atlases(REPOSITORY_ROOT / "absent", output, batches=("overworld",))
    assert canonical_json(first) == (output / "manifest.json").read_text(
        encoding="utf-8"
    )


def test_atomic_replacement_keeps_public_tree_continuously_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    build_atlases(tmp_path, output)
    stop = threading.Event()
    failures: list[BaseException] = []
    reads = 0

    def reader() -> None:
        nonlocal reads
        while not stop.is_set():
            try:
                manifest = json.loads((output / "manifest.json").read_text())
                artifact = output / str(manifest["artifacts"][0]["path"])
                assert (
                    hashlib.sha256(artifact.read_bytes()).hexdigest()
                    == (manifest["artifacts"][0]["sha256"])
                )
                reads += 1
            except BaseException as exc:  # noqa: BLE001 - report thread failures
                failures.append(exc)
                stop.set()

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        build_atlases(tmp_path, output)
    finally:
        stop.set()
        thread.join()
    assert reads > 0
    assert failures == []
    assert output.is_dir()
    assert (tmp_path / f".{output.name}.prior").is_dir()


def test_reader_holding_old_manifest_can_open_disjoint_artifact_after_exchange(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    generation = 0

    def write_disjoint(
        _root: Path, temporary: Path, **_kwargs: object
    ) -> dict[str, object]:
        nonlocal generation
        generation += 1
        artifact = f"batch-{generation}/map-{generation}.png"
        _write_owned_output(temporary, artifact)
        path = temporary / artifact
        path.write_bytes(f"generation {generation}".encode())
        manifest = json.loads((temporary / "manifest.json").read_text())
        record = manifest["artifacts"][0]
        record["size"] = path.stat().st_size
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest["content_sha256"] = hashlib.sha256(
            canonical_json(
                {k: v for k, v in manifest.items() if k != "content_sha256"}
            ).encode()
        ).hexdigest()
        (temporary / "manifest.json").write_text(canonical_json(manifest))
        return manifest

    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", write_disjoint
    )
    build_atlases(tmp_path, output)
    old_manifest = json.loads((output / "manifest.json").read_text())
    old_record = old_manifest["artifacts"][0]

    build_atlases(tmp_path, output)

    new_manifest = json.loads((output / "manifest.json").read_text())
    assert old_record["path"] != new_manifest["artifacts"][0]["path"]
    old_bytes = (output / old_record["path"]).read_bytes()
    assert old_bytes == b"generation 1"
    assert hashlib.sha256(old_bytes).hexdigest() == old_record["sha256"]


def test_postexchange_failure_atomically_restores_exact_prior_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    first = build_atlases(tmp_path, output)
    original_inode = output.stat().st_ino
    real_fsync = map_background_atlas._fsync_directory
    real_exchange = map_background_atlas._rename_exchange
    armed = False
    injected = False

    def arm_after_exchange(*args: object, **kwargs: object) -> None:
        nonlocal armed
        real_exchange(*args, **kwargs)
        armed = True

    def fail_after_exchange(path: Path) -> None:
        nonlocal injected
        if armed and not injected:
            injected = True
            raise OSError("injected post-exchange failure")
        real_fsync(path)

    monkeypatch.setattr(map_background_atlas, "_rename_exchange", arm_after_exchange)
    monkeypatch.setattr(map_background_atlas, "_fsync_directory", fail_after_exchange)
    with pytest.raises(OSError, match="post-exchange failure"):
        build_atlases(tmp_path, output)
    assert output.stat().st_ino == original_inode
    assert canonical_json(first) == (output / "manifest.json").read_text()
    assert (tmp_path / f".{output.name}.failed").is_dir()


def test_rollback_rejects_byte_identical_decoy_before_exchange(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    retained = tmp_path / f".{output.name}.tmp"
    displaced = tmp_path / "displaced-exact-prior"
    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    build_atlases(tmp_path, output)
    exact_prior_inode = output.stat().st_ino
    real_exchange = map_background_atlas._rename_exchange
    real_fsync = map_background_atlas._fsync_directory
    exchange_calls = 0
    publication_exchanged = False
    failure_injected = False

    def exchange_with_decoy_before_rollback(*args: object, **kwargs: object) -> None:
        nonlocal exchange_calls, publication_exchanged
        exchange_calls += 1
        if exchange_calls == 2:
            retained.rename(displaced)
            shutil.copytree(displaced, retained)
        real_exchange(*args, **kwargs)
        if exchange_calls == 1:
            publication_exchanged = True

    def fail_once_after_publication(path: Path) -> None:
        nonlocal failure_injected
        if publication_exchanged and not failure_injected:
            failure_injected = True
            raise OSError("injected post-exchange failure")
        real_fsync(path)

    monkeypatch.setattr(
        map_background_atlas, "_rename_exchange", exchange_with_decoy_before_rollback
    )
    monkeypatch.setattr(
        map_background_atlas, "_fsync_directory", fail_once_after_publication
    )

    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasCompositeError,
        match=(
            "publication and recovery both failed: OSError: injected "
            "post-exchange failure; MapBackgroundAtlasError: atomic rollback "
            "did not restore the exact prior atlas root and retain the exact failed "
            "publication"
        ),
    ):
        build_atlases(tmp_path, output)

    assert exchange_calls == 2
    assert displaced.stat().st_ino == exact_prior_inode
    assert output.stat().st_ino != exact_prior_inode
    assert _current_artifact(displaced).read_bytes() == b"atlas image"
    assert _current_artifact(output).read_bytes() == b"atlas image"
    assert _current_artifact(retained).read_bytes() == b"atlas image"


def test_exchange_rejects_byte_identical_decoy_in_place_of_pinned_prior_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    displaced = tmp_path / "displaced-exact-prior"
    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    build_atlases(tmp_path, output)
    exact_prior_inode = output.stat().st_ino
    real_exchange = map_background_atlas._rename_exchange
    injected = False

    def exchange_after_decoy_root_swap(*args: object, **kwargs: object) -> None:
        nonlocal injected
        if not injected:
            injected = True
            output.rename(displaced)
            shutil.copytree(displaced, output)
        real_exchange(*args, **kwargs)

    monkeypatch.setattr(
        map_background_atlas, "_rename_exchange", exchange_after_decoy_root_swap
    )
    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasCompositeError,
        match="publication and recovery both failed",
    ):
        build_atlases(tmp_path, output)

    assert injected
    assert displaced.stat().st_ino == exact_prior_inode
    assert _current_artifact(displaced).read_bytes() == b"atlas image"
    assert _current_artifact(tmp_path / f".{output.name}.tmp").read_bytes() == (
        b"atlas image"
    )


@pytest.mark.parametrize("swap", ("artifact", "manifest", "nested-directory"))
def test_mutation_during_fsync_never_publishes_stale_validated_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap: str,
) -> None:
    output = tmp_path / "published"
    real_fsync = map_background_atlas._fsync_tree_directories

    def mutate_during_fsync(temporary: Path) -> None:
        real_fsync(temporary)
        if swap == "artifact":
            _current_artifact(temporary).write_bytes(b"mutated atlas")
        elif swap == "manifest":
            os.rename(temporary / "manifest.json", tmp_path / "displaced-manifest")
            (temporary / "manifest.json").write_bytes(
                (tmp_path / "displaced-manifest").read_bytes()
            )
        else:
            artifact = _current_artifact(temporary)
            os.rename(artifact.parent, tmp_path / "displaced-batch")
            artifact.parent.mkdir()
            artifact.write_bytes(b"atlas image")

    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    monkeypatch.setattr(
        map_background_atlas, "_fsync_tree_directories", mutate_during_fsync
    )

    with pytest.raises(map_background_atlas.MapBackgroundAtlasError):
        build_atlases(tmp_path, output)

    assert not output.exists()
    assert (tmp_path / f".{output.name}.tmp").is_dir()


@pytest.mark.parametrize("with_prior", (False, True))
def test_mutation_during_published_parent_fsync_is_rejected_and_rolled_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    with_prior: bool,
) -> None:
    output = tmp_path / "published"
    temporary = tmp_path / f".{output.name}.tmp"
    failed = tmp_path / f".{output.name}.failed"
    prior_inode: int | None = None
    if with_prior:
        _write_owned_output(output, "prior/map.png")
        prior_inode = output.stat().st_ino
    fd_before = len(tuple(Path("/proc/self/fd").iterdir()))
    real_fsync_directory = map_background_atlas._fsync_directory
    injected = False

    def mutate_during_published_parent_fsync(path: Path) -> None:
        nonlocal injected
        real_fsync_directory(path)
        if not injected and path == tmp_path and output.is_dir():
            injected = True
            _current_artifact(output).write_bytes(b"mutated during parent fsync")

    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    monkeypatch.setattr(
        map_background_atlas,
        "_fsync_directory",
        mutate_during_published_parent_fsync,
    )

    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasError,
        match="artifact does not match manifest",
    ):
        build_atlases(tmp_path, output)

    assert injected
    assert _current_artifact(failed).read_bytes() == b"mutated during parent fsync"
    assert not temporary.exists()
    if with_prior:
        assert output.stat().st_ino == prior_inode
        assert (output / "prior/map.png").read_bytes() == b"atlas image"
        assert not (tmp_path / f".{output.name}.prior").exists()
    else:
        assert not output.exists()
    assert len(tuple(Path("/proc/self/fd").iterdir())) - fd_before == 0


@pytest.mark.parametrize("mutation", ("artifact", "manifest", "nested-directory"))
def test_mutation_inside_publication_rename_is_quarantined_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    output = tmp_path / "published"
    temporary_name = f".{output.name}.tmp"
    failed = tmp_path / f".{output.name}.failed"
    real_rename = map_background_atlas._rename_noreplace
    fd_before = len(tuple(Path("/proc/self/fd").iterdir()))
    injected = False

    def mutate_immediately_before_rename(
        source: str, destination: str, **kwargs: int
    ) -> None:
        nonlocal injected
        if not injected and source == temporary_name and destination == output.name:
            injected = True
            temporary = tmp_path / temporary_name
            if mutation == "artifact":
                _current_artifact(temporary).write_bytes(b"mutated atlas")
            elif mutation == "manifest":
                displaced = tmp_path / "displaced-manifest"
                os.rename(temporary / "manifest.json", displaced)
                (temporary / "manifest.json").write_bytes(displaced.read_bytes())
            else:
                displaced = tmp_path / "displaced-batch"
                artifact = _current_artifact(temporary)
                os.rename(artifact.parent, displaced)
                artifact.parent.mkdir()
                artifact.write_bytes((displaced / artifact.name).read_bytes())
        real_rename(source, destination, **kwargs)

    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    monkeypatch.setattr(
        map_background_atlas, "_rename_noreplace", mutate_immediately_before_rename
    )

    with pytest.raises(map_background_atlas.MapBackgroundAtlasError):
        build_atlases(tmp_path, output)

    assert injected
    assert not output.exists()
    assert failed.is_dir()
    assert not (tmp_path / temporary_name).exists()
    assert len(tuple(Path("/proc/self/fd").iterdir())) - fd_before == 0


def test_postpublication_validation_failure_restores_exact_prior_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    failed = tmp_path / f".{output.name}.failed"
    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    first = build_atlases(tmp_path, output)
    prior_inode = output.stat().st_ino
    prior_artifact = _current_artifact(output)
    prior_bytes = prior_artifact.read_bytes()
    real_exchange = map_background_atlas._rename_exchange
    injected = False

    def mutate_immediately_after_exchange(*args: object, **kwargs: object) -> None:
        nonlocal injected
        real_exchange(*args, **kwargs)
        if not injected:
            injected = True
            _current_artifact(output).write_bytes(b"mutated atlas")

    monkeypatch.setattr(
        map_background_atlas, "_rename_exchange", mutate_immediately_after_exchange
    )
    with pytest.raises(map_background_atlas.MapBackgroundAtlasError):
        build_atlases(tmp_path, output)

    assert output.stat().st_ino == prior_inode
    assert _current_artifact(output).read_bytes() == prior_bytes
    assert canonical_json(first) == (output / "manifest.json").read_text(
        encoding="utf-8"
    )
    assert _current_artifact(failed).read_bytes() == b"mutated atlas"
    assert not (tmp_path / f".{output.name}.prior").exists()


def test_postpublication_failed_slot_collision_preserves_every_tree_and_victim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    temporary_name = f".{output.name}.tmp"
    prior = tmp_path / f".{output.name}.prior"
    failed = tmp_path / f".{output.name}.failed"
    victim = tmp_path / "victim"
    _write_owned_output(victim, "victim/map.png")
    victim_before = (victim / "victim/map.png").read_bytes()
    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    build_atlases(tmp_path, output)
    real_exchange = map_background_atlas._rename_exchange
    injected = False

    def mutate_and_claim_failed_slot(*args: object, **kwargs: object) -> None:
        nonlocal injected
        real_exchange(*args, **kwargs)
        if not injected:
            injected = True
            _current_artifact(output).write_bytes(b"mutated atlas")
            failed.symlink_to(victim, target_is_directory=True)

    monkeypatch.setattr(
        map_background_atlas, "_rename_exchange", mutate_and_claim_failed_slot
    )
    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasCompositeError,
        match="publication and recovery both failed",
    ):
        build_atlases(tmp_path, output)

    assert _current_artifact(output).read_bytes() == b"atlas image"
    assert not prior.exists()
    assert _current_artifact(tmp_path / temporary_name).read_bytes() == b"mutated atlas"
    assert failed.is_symlink()
    assert failed.resolve() == victim
    assert (victim / "victim/map.png").read_bytes() == victim_before


def test_postpublication_quarantine_root_swap_restores_victim_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    displaced = tmp_path / "recoverable-published"
    victim = tmp_path / "victim"
    _write_owned_output(output, "published/map.png")
    _write_owned_output(victim, "victim/map.png")
    victim_before = (victim / "victim/map.png").read_bytes()
    descriptor = os.open(output, map_background_atlas._DIRECTORY_FLAGS)
    parent_descriptor = os.open(tmp_path, map_background_atlas._DIRECTORY_FLAGS)
    validated = map_background_atlas._validate_output_descriptor(descriptor, output)
    real_rename = map_background_atlas._rename_noreplace
    injected = False

    def swap_root_before_quarantine(
        source: str, destination: str, **kwargs: int
    ) -> None:
        nonlocal injected
        if not injected and source == output.name:
            injected = True
            os.rename(output, displaced)
            output.symlink_to(victim, target_is_directory=True)
        real_rename(source, destination, **kwargs)

    monkeypatch.setattr(
        map_background_atlas, "_rename_noreplace", swap_root_before_quarantine
    )
    try:
        with pytest.raises(
            map_background_atlas.MapBackgroundAtlasCompositeError,
            match="failed atlas quarantine encountered failures",
        ):
            map_background_atlas._quarantine_pinned_publication(
                output,
                parent_descriptor=parent_descriptor,
                tree_descriptor=descriptor,
                expected_root_identity=validated.root_identity,
            )
    finally:
        os.close(descriptor)
        os.close(parent_descriptor)

    assert injected
    assert output.is_symlink()
    assert output.resolve() == victim
    assert not (tmp_path / f".{output.name}.failed").exists()
    assert (displaced / "published/map.png").read_bytes() == b"atlas image"
    assert (victim / "victim/map.png").read_bytes() == victim_before


def test_regular_file_fsync_failure_closes_fds_and_never_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    fd_before = len(tuple(Path("/proc/self/fd").iterdir()))
    real_fsync = map_background_atlas.os.fsync
    injected = False

    def fail_regular_file_fsync(descriptor: int) -> None:
        nonlocal injected
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            injected = True
            raise OSError("injected regular-file fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    monkeypatch.setattr(map_background_atlas.os, "fsync", fail_regular_file_fsync)
    with pytest.raises(OSError, match="injected regular-file fsync failure"):
        build_atlases(tmp_path, output)

    assert injected
    assert not output.exists()
    assert (tmp_path / f".{output.name}.tmp").is_dir()
    assert len(tuple(Path("/proc/self/fd").iterdir())) - fd_before == 0


def test_regular_file_fsync_failure_preserves_existing_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    first = build_atlases(tmp_path, output)
    prior_inode = output.stat().st_ino
    real_fsync = map_background_atlas.os.fsync

    def fail_regular_file_fsync(descriptor: int) -> None:
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("injected regular-file fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(map_background_atlas.os, "fsync", fail_regular_file_fsync)
    with pytest.raises(OSError, match="injected regular-file fsync failure"):
        build_atlases(tmp_path, output)

    assert output.stat().st_ino == prior_inode
    assert canonical_json(first) == (output / "manifest.json").read_text(
        encoding="utf-8"
    )
    assert not (tmp_path / f".{output.name}.prior").exists()
    assert (tmp_path / f".{output.name}.tmp").is_dir()


@pytest.mark.parametrize("failure", ("fstat", "read"))
def test_regular_file_inspection_failure_closes_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    output = tmp_path / "published"
    _write_owned_output(output)
    directory_descriptor = os.open(output, map_background_atlas._DIRECTORY_FLAGS)
    fd_before = len(tuple(Path("/proc/self/fd").iterdir()))
    real_fstat = map_background_atlas.os.fstat
    real_read = map_background_atlas.os.read

    def fail_file_fstat(descriptor: int) -> os.stat_result:
        metadata = real_fstat(descriptor)
        if stat.S_ISREG(metadata.st_mode):
            raise OSError("injected regular-file fstat failure")
        return metadata

    def fail_file_read(descriptor: int, size: int) -> bytes:
        if stat.S_ISREG(real_fstat(descriptor).st_mode):
            raise OSError("injected regular-file read failure")
        return real_read(descriptor, size)

    if failure == "fstat":
        monkeypatch.setattr(map_background_atlas.os, "fstat", fail_file_fstat)
    else:
        monkeypatch.setattr(map_background_atlas.os, "read", fail_file_read)
    try:
        with pytest.raises(OSError, match=f"regular-file {failure} failure"):
            map_background_atlas._read_regular_file(
                directory_descriptor,
                "manifest.json",
                description="atlas manifest",
            )
        assert len(tuple(Path("/proc/self/fd").iterdir())) - fd_before == 0
    finally:
        os.close(directory_descriptor)


def test_publication_noreplace_preserves_raced_output_and_retains_exact_temp_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    real_rename = map_background_atlas._rename_noreplace
    raced_inode: int | None = None
    temporary_inode: int | None = None

    def race_output(source: str, destination: str, **kwargs: int) -> None:
        nonlocal raced_inode, temporary_inode
        if source == f".{output.name}.tmp" and destination == output.name:
            temporary_inode = os.stat(
                source,
                dir_fd=kwargs["source_directory_descriptor"],
                follow_symlinks=False,
            ).st_ino
            _write_owned_output(output, "raced/map.png")
            raced_inode = output.stat().st_ino
        real_rename(source, destination, **kwargs)

    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )
    monkeypatch.setattr(map_background_atlas, "_rename_noreplace", race_output)

    with pytest.raises(FileExistsError):
        build_atlases(tmp_path, output)

    assert output.stat().st_ino == raced_inode
    assert (output / "raced/map.png").read_bytes() == b"atlas image"
    retained = tmp_path / f".{output.name}.tmp"
    assert retained.stat().st_ino == temporary_inode
    assert _current_artifact(retained).read_bytes() == b"atlas image"


def test_fixed_retention_slots_bound_repeated_publications(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )

    build_atlases(tmp_path, output)
    first_inode = output.stat().st_ino
    build_atlases(tmp_path, output)
    second_inode = output.stat().st_ino
    prior = tmp_path / f".{output.name}.prior"
    prior_inode = prior.stat().st_ino

    assert first_inode == prior_inode
    assert second_inode != first_inode
    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasError,
        match="prior-publication slot.*operator cleanup",
    ):
        build_atlases(tmp_path, output)

    assert output.stat().st_ino == second_inode
    assert prior.stat().st_ino == prior_inode
    assert len(list(tmp_path.glob(f".{output.name}.prior"))) == 1
    assert not (tmp_path / f".{output.name}.tmp").exists()


def test_fixed_temporary_slot_bounds_repeated_failed_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    monkeypatch.setattr(
        map_background_atlas, "_build_atlases_in_directory", _write_test_atlas
    )

    def fail_fsync(_temporary: Path) -> None:
        raise OSError("injected synchronization failure")

    monkeypatch.setattr(map_background_atlas, "_fsync_tree_directories", fail_fsync)
    with pytest.raises(OSError, match="injected synchronization failure"):
        build_atlases(tmp_path, output)
    retained = tmp_path / f".{output.name}.tmp"
    retained_inode = retained.stat().st_ino

    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasError,
        match="temporary slot.*operator cleanup",
    ):
        build_atlases(tmp_path, output)

    assert retained.stat().st_ino == retained_inode
    assert len(list(tmp_path.glob(f".{output.name}.tmp"))) == 1
    assert not output.exists()


def test_exchange_failure_preserves_complete_previous_publication(
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
    real_exchange = map_background_atlas._rename_exchange
    injected = False

    def fail_new_publication(*args: object, **kwargs: object) -> None:
        nonlocal injected
        if not injected:
            injected = True
            raise OSError("injected final publication failure")
        real_exchange(*args, **kwargs)

    monkeypatch.setattr(map_background_atlas, "_rename_exchange", fail_new_publication)
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
    assert not (tmp_path / f".{output.name}.prior").exists()
    assert (tmp_path / f".{output.name}.tmp").is_dir()


def test_retention_rejects_root_symlink_swap_without_touching_victim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    original = tmp_path / "recoverable-original"
    victim = tmp_path / "victim"
    _write_owned_output(output)
    _write_owned_output(victim)
    victim_before = {
        path.relative_to(victim).as_posix(): path.read_bytes()
        for path in victim.rglob("*")
        if path.is_file()
    }
    real_rename = map_background_atlas._rename_noreplace
    injected = False

    def swap_before_quarantine(source: str, destination: str, **kwargs: int) -> None:
        nonlocal injected
        if not injected and source == output.name:
            injected = True
            os.rename(output, original)
            output.symlink_to(victim, target_is_directory=True)
        real_rename(source, destination, **kwargs)

    monkeypatch.setattr(
        map_background_atlas, "_rename_noreplace", swap_before_quarantine
    )
    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasError,
        match="changed while it was moved to quarantine",
    ):
        map_background_atlas._retain_owned_output(output)

    assert injected
    assert (original / "batch/map.png").read_bytes() == b"atlas image"
    assert {
        path.relative_to(victim).as_posix(): path.read_bytes()
        for path in victim.rglob("*")
        if path.is_file()
    } == victim_before


def test_retention_never_replaces_raced_quarantine_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    victim = tmp_path / "victim"
    _write_owned_output(output)
    _write_owned_output(victim)
    real_rename = map_background_atlas._rename_noreplace
    injected_destination: str | None = None

    def claim_quarantine_destination(
        source: str, destination: str, **kwargs: int
    ) -> None:
        nonlocal injected_destination
        if injected_destination is None:
            injected_destination = destination
            os.symlink(
                victim,
                destination,
                dir_fd=kwargs["destination_directory_descriptor"],
            )
        real_rename(source, destination, **kwargs)

    monkeypatch.setattr(
        map_background_atlas, "_rename_noreplace", claim_quarantine_destination
    )
    with pytest.raises(FileExistsError):
        map_background_atlas._retain_owned_output(output)

    assert injected_destination is not None
    assert (output / "batch/map.png").read_bytes() == b"atlas image"
    assert (victim / "batch/map.png").read_bytes() == b"atlas image"
    raced = tmp_path / injected_destination
    assert raced.is_symlink()
    assert raced.resolve() == victim


def test_final_stat_to_unlink_swap_has_no_destructive_call_and_victim_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    victim = tmp_path / "victim.png"
    _write_owned_output(output)
    victim.write_bytes(b"do not delete")
    real_stat = map_background_atlas.os.stat
    real_unlink = map_background_atlas.os.unlink
    final_quarantine_stat_seen = False
    unlink_calls = 0

    def arm_after_final_stat(
        path: object, *args: object, **kwargs: object
    ) -> os.stat_result:
        nonlocal final_quarantine_stat_seen
        result = real_stat(path, *args, **kwargs)
        if str(path) == f".{output.name}.prior":
            final_quarantine_stat_seen = True
        return result

    def reproduce_swap_before_unlink(
        path: object, *args: object, **kwargs: object
    ) -> None:
        nonlocal unlink_calls
        unlink_calls += 1
        if final_quarantine_stat_seen:
            raise AssertionError("a checked attacker-visible name reached unlink")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(map_background_atlas.os, "stat", arm_after_final_stat)
    monkeypatch.setattr(map_background_atlas.os, "unlink", reproduce_swap_before_unlink)
    retained = map_background_atlas._retain_owned_output(output)

    assert final_quarantine_stat_seen
    assert unlink_calls == 0
    assert (retained / "batch/map.png").read_bytes() == b"atlas image"
    assert victim.read_bytes() == b"do not delete"


def test_cleanup_rejects_hard_linked_artifact(tmp_path: Path) -> None:
    output = tmp_path / "published"
    victim = tmp_path / "victim.png"
    victim.write_bytes(b"do not delete")
    (output / "batch").mkdir(parents=True)
    os.link(victim, output / "batch/map.png")
    manifest = {
        "schema": SCHEMA,
        "producer": "tools.rom_tests.full_color.map_background_atlas",
        "artifacts": [{"path": "batch/map.png"}],
    }
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasError, match="hard-linked file"
    ):
        map_background_atlas._retain_owned_output(output)

    assert victim.read_bytes() == b"do not delete"
    assert (output / "batch/map.png").exists()


def test_cleanup_rejects_directory_in_place_of_owned_artifact(tmp_path: Path) -> None:
    output = tmp_path / "published"
    _write_owned_output(output)
    (output / "batch/map.png").unlink()
    (output / "batch/map.png").mkdir()

    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasError,
        match="artifact does not match manifest",
    ):
        map_background_atlas._retain_owned_output(output)

    assert (output / "batch/map.png").is_dir()


def test_rollback_rejects_failed_publication_symlink_swap_and_keeps_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    displaced = tmp_path / "recoverable-failed-publication"
    victim = tmp_path / "victim"
    _write_owned_output(output, "prior/map.png")
    backup = map_background_atlas._quarantine_owned_output(output)
    _write_owned_output(output, "failed/map.png")
    _write_owned_output(victim, "victim/map.png")
    real_rename = map_background_atlas._rename_noreplace
    injected = False

    def swap_failed_publication(source: str, destination: str, **kwargs: int) -> None:
        nonlocal injected
        if not injected and source == output.name:
            injected = True
            os.rename(output, displaced)
            output.symlink_to(victim, target_is_directory=True)
        real_rename(source, destination, **kwargs)

    monkeypatch.setattr(
        map_background_atlas, "_rename_noreplace", swap_failed_publication
    )
    try:
        with pytest.raises(
            map_background_atlas.MapBackgroundAtlasCompositeError,
            match="rollback encountered failures",
        ):
            map_background_atlas._rollback_publication(output, backup)
        assert injected
        assert (displaced / "failed/map.png").read_bytes() == b"atlas image"
        assert (victim / "victim/map.png").read_bytes() == b"atlas image"
        assert backup.path.is_dir()
        assert (backup.path / "prior/map.png").read_bytes() == b"atlas image"
    finally:
        backup.close()


def test_rollback_fsync_failures_close_fds_and_retain_failed_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    fd_before = len(tuple(Path("/proc/self/fd").iterdir()))
    _write_owned_output(output, "prior/map.png")
    backup = map_background_atlas._quarantine_owned_output(output)
    _write_owned_output(output, "failed/map.png")

    def fail_fsync(_path: Path) -> None:
        raise OSError("injected rollback fsync failure")

    monkeypatch.setattr(map_background_atlas, "_fsync_directory", fail_fsync)
    with pytest.raises(map_background_atlas.MapBackgroundAtlasCompositeError) as raised:
        map_background_atlas._rollback_publication(output, backup)

    assert len(raised.value.failures) == 2
    assert len(tuple(Path("/proc/self/fd").iterdir())) - fd_before == 0
    assert (output / "prior/map.png").read_bytes() == b"atlas image"
    retained = tmp_path / f".{output.name}.failed"
    assert (retained / "failed/map.png").read_bytes() == b"atlas image"


def test_rollback_restore_failure_closes_fds_and_retains_both_trees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "published"
    fd_before = len(tuple(Path("/proc/self/fd").iterdir()))
    _write_owned_output(output, "prior/map.png")
    backup = map_background_atlas._quarantine_owned_output(output)
    backup_name = backup.name
    _write_owned_output(output, "failed/map.png")
    real_rename = map_background_atlas._rename_noreplace

    def fail_restore(source: str, destination: str, **kwargs: int) -> None:
        if source == backup_name and destination == output.name:
            raise OSError("injected restore failure")
        real_rename(source, destination, **kwargs)

    monkeypatch.setattr(map_background_atlas, "_rename_noreplace", fail_restore)
    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasCompositeError,
        match="rollback encountered failures",
    ):
        map_background_atlas._rollback_publication(output, backup)

    assert len(tuple(Path("/proc/self/fd").iterdir())) - fd_before == 0
    assert (tmp_path / f".{output.name}.prior/prior/map.png").is_file()
    assert (tmp_path / f".{output.name}.failed/failed/map.png").is_file()


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


def test_atlas_does_not_read_clean_checkout_generated_tileset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = REPOSITORY_ROOT / "gfx/tilesets/overworld.2bpp"
    real_read_bytes = Path.read_bytes

    def reject_generated_file(path: Path) -> bytes:
        if path == generated:
            raise AssertionError("atlas read a checkout-generated 2bpp file")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_generated_file)
    manifest = build_atlases(
        REPOSITORY_ROOT, tmp_path / "clean-atlas", batches=("overworld",)
    )
    assert manifest["tilesets"][0]["graphics_source"]["path"] == (
        "gfx/tilesets/overworld.2bpp"
    )


def test_atlas_ignores_poisoned_checkout_converter_and_binds_toolchain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ignored_converter = REPOSITORY_ROOT / "tools/gfx"
    real_read_bytes = Path.read_bytes

    def reject_ignored_converter(path: Path) -> bytes:
        if path == ignored_converter:
            raise AssertionError("atlas read ignored checkout converter")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_ignored_converter)
    manifest = build_atlases(
        REPOSITORY_ROOT, tmp_path / "atlas", batches=("forest-cavern",)
    )
    toolchain = manifest["graphics_toolchain"]
    assert toolchain["rgbds_version"]["path"] == ".rgbds-version"
    assert [row["path"] for row in toolchain["postprocessor"]["sources"]] == [
        "tools/common.h",
        "tools/gfx.c",
    ]
    assert toolchain["postprocessor"]["binary_sha256"]
    assert toolchain["rgbgfx"]["binary_sha256"]
    assert toolchain["compiler"]["binary_sha256"]


def test_tracked_png_and_converter_source_mutations_change_provenance(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    for relative in (
        ".rgbds-version",
        "tools/common.h",
        "tools/gfx.c",
        "gfx/tilesets/forest.png",
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, destination)
    relative = Path("gfx/tilesets/forest.2bpp")
    baseline = source_2bpp(root, relative)
    baseline_toolchain = map_background_atlas.graphics_toolchain(root)

    source = root / "tools/gfx.c"
    source.write_text(source.read_text() + "\n/* provenance mutation */\n")
    mutated_toolchain = map_background_atlas.graphics_toolchain(root)
    assert mutated_toolchain != baseline_toolchain
    assert source_2bpp(root, relative) == baseline

    png = root / "gfx/tilesets/forest.png"
    image = Image.open(png).convert("RGBA")
    pixel = image.getpixel((0, 0))
    image.putpixel((0, 0), (pixel[0] ^ 0xFF, pixel[1], pixel[2], pixel[3]))
    image.save(png)
    with pytest.raises(map_background_atlas.MapBackgroundAtlasError):
        source_2bpp(root, relative)


def test_converter_source_mutation_during_compile_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    for relative in (".rgbds-version", "tools/common.h", "tools/gfx.c"):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, destination)
    real_run = map_background_atlas.subprocess.run
    mutated = False

    def mutate_after_compile(*args: object, **kwargs: object) -> object:
        nonlocal mutated
        result = real_run(*args, **kwargs)
        command = args[0]
        if not mutated and "-o" in command and str(command[-1]).endswith("gfx.c"):
            mutated = True
            source = root / "tools/gfx.c"
            source.write_text(source.read_text() + "\n/* raced */\n")
        return result

    monkeypatch.setattr(map_background_atlas.subprocess, "run", mutate_after_compile)
    with pytest.raises(
        map_background_atlas.MapBackgroundAtlasError,
        match="changed after identification",
    ):
        map_background_atlas.graphics_toolchain(root)
    assert mutated


def _write_fake_graphics_toolchain(root: Path) -> tuple[Path, Path]:
    (root / "tools").mkdir(parents=True)
    (root / "gfx/tilesets").mkdir(parents=True)
    (root / ".rgbds-version").write_text("0.0\n")
    (root / "tools/common.h").write_text("/* test */\n")
    (root / "tools/gfx.c").write_text("/* test */\n")
    (root / "gfx/tilesets/forest.png").write_bytes(b"png snapshot")
    compiler = root / "cc"
    compiler.write_text(
        """#!/usr/bin/env python3
import os
import pathlib
import sys
if "--version" in sys.argv:
    print("test cc original")
else:
    output = pathlib.Path(sys.argv[sys.argv.index("-o") + 1])
    output.write_text("""
        + repr("""#!/usr/bin/env python3
import pathlib
import sys
output = pathlib.Path(sys.argv[sys.argv.index("-o") + 1])
output.write_bytes(pathlib.Path(sys.argv[-1]).read_bytes())
""")
        + """, encoding="utf-8")
    os.chmod(output, 0o500)
""",
        encoding="utf-8",
    )
    rgbgfx = root / "rgbgfx"
    rgbgfx.write_text(
        """#!/usr/bin/env python3
import pathlib
import sys
if "--version" in sys.argv:
    print("rgbgfx v0.0")
else:
    pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_bytes(b"rgbgfx-original")
""",
        encoding="utf-8",
    )
    compiler.chmod(0o500)
    rgbgfx.chmod(0o500)
    return compiler, rgbgfx


def _replace_tool_during_run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    target: Path,
    replacement: bytes,
    command_marker: str,
) -> list[str]:
    real_run = map_background_atlas.subprocess.run
    executions: list[str] = []

    def swap_immediately_before_exec(*args: object, **kwargs: object) -> object:
        command = args[0]
        if not executions and command[0] == str(target) and command_marker in command:
            original = target.with_name(f"{target.name}.original")
            attacker = target.with_name(f"{target.name}.attacker")
            attacker.write_bytes(replacement)
            attacker.chmod(0o500)
            os.replace(target, original)
            os.replace(attacker, target)
            try:
                descriptor = kwargs["pass_fds"][0]
                executable = Path(f"/proc/self/fd/{descriptor}")
                executions.append(hashlib.sha256(executable.read_bytes()).hexdigest())
                return real_run(*args, **kwargs)
            finally:
                os.replace(original, target)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(
        map_background_atlas.subprocess, "run", swap_immediately_before_exec
    )
    return executions


def test_compiler_swap_immediately_before_exec_cannot_change_accepted_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    compiler, rgbgfx = _write_fake_graphics_toolchain(root)
    compiler_digest = hashlib.sha256(compiler.read_bytes()).hexdigest()
    replacement = (
        compiler.read_text()
        .replace(
            "output.write_bytes(pathlib.Path(sys.argv[-1]).read_bytes())",
            'output.write_bytes(b"compiler-replacement")',
        )
        .encode()
    )
    monkeypatch.setattr(
        map_background_atlas.shutil,
        "which",
        lambda command: str(compiler if command == "cc" else rgbgfx),
    )
    executions = _replace_tool_during_run(
        monkeypatch,
        target=compiler,
        replacement=replacement,
        command_marker="-o",
    )

    result = source_2bpp(root, Path("gfx/tilesets/forest.2bpp"))

    assert result == b"rgbgfx-original"
    assert executions == [compiler_digest]
    assert hashlib.sha256(compiler.read_bytes()).hexdigest() == compiler_digest


def test_rgbgfx_swap_immediately_before_exec_cannot_change_accepted_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    compiler, rgbgfx = _write_fake_graphics_toolchain(root)
    rgbgfx_digest = hashlib.sha256(rgbgfx.read_bytes()).hexdigest()
    replacement = (
        rgbgfx.read_text()
        .replace(
            'write_bytes(b"rgbgfx-original")',
            'write_bytes(b"rgbgfx-replacement")',
        )
        .encode()
    )
    monkeypatch.setattr(
        map_background_atlas.shutil,
        "which",
        lambda command: str(compiler if command == "cc" else rgbgfx),
    )
    executions = _replace_tool_during_run(
        monkeypatch,
        target=rgbgfx,
        replacement=replacement,
        command_marker="--colors",
    )

    result = source_2bpp(root, Path("gfx/tilesets/forest.2bpp"))

    assert result == b"rgbgfx-original"
    assert executions == [rgbgfx_digest]
    assert hashlib.sha256(rgbgfx.read_bytes()).hexdigest() == rgbgfx_digest


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


@pytest.mark.parametrize(
    "field", ("route", "checkpoint", "tileset", "purpose", "map_name", "natural_driver")
)
def test_route_evidence_claim_mutations_fail_closed(field: str) -> None:
    route = BATCH_ROUTES[0]
    if field == "route":
        mutated = replace(route, route="arbitrary-review-route")
    elif field == "checkpoint":
        checkpoint = replace(route.checkpoints[0], name="arbitrary-checkpoint")
        mutated = replace(route, checkpoints=(checkpoint, *route.checkpoints[1:]))
    elif field == "tileset":
        checkpoint = replace(route.checkpoints[0], tileset="CAVERN")
        mutated = replace(route, checkpoints=(checkpoint, *route.checkpoints[1:]))
    elif field == "purpose":
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


@pytest.mark.parametrize(
    "field",
    (
        "batch",
        "route",
        "checkpoint",
        "duplicate-checkpoint",
        "purpose",
        "product",
        "map_id",
        "map_name",
        "tileset",
        "presentation",
        "fallback",
    ),
)
def test_artifact_review_route_mutations_fail_closed(field: str) -> None:
    route = ARTIFACT_REVIEW_ROUTES[0]
    if field == "batch":
        mutated = replace(route, batch="arbitrary-batch")
    elif field == "route":
        mutated = replace(route, route="arbitrary-review-route")
    elif field == "checkpoint":
        checkpoint = replace(route.checkpoints[0], name="arbitrary-checkpoint")
        mutated = replace(route, checkpoints=(checkpoint, *route.checkpoints[1:]))
    elif field == "duplicate-checkpoint":
        mutated = replace(route, checkpoints=(route.checkpoints[0],) * 2)
    elif field == "purpose":
        mutated = replace(route, purpose="runtime-admission")
    elif field == "product":
        mutated = replace(route, products=("pokeyellow", "pokeyellow_debug"))
    elif field == "map_id":
        checkpoint = replace(route.checkpoints[0], map_id=0x01)
        mutated = replace(route, checkpoints=(checkpoint, *route.checkpoints[1:]))
    elif field == "map_name":
        checkpoint = replace(route.checkpoints[0], map_name="VIRIDIAN_CITY")
        mutated = replace(route, checkpoints=(checkpoint, *route.checkpoints[1:]))
    elif field == "presentation":
        checkpoint = replace(route.checkpoints[0], expected_presentation="color")
        mutated = replace(route, checkpoints=(checkpoint, *route.checkpoints[1:]))
    elif field == "fallback":
        checkpoint = replace(route.checkpoints[0], fallback_authority="review-prose")
        mutated = replace(route, checkpoints=(checkpoint, *route.checkpoints[1:]))
    else:
        checkpoint = replace(route.checkpoints[0], tileset="OVERWORLD")
        mutated = replace(route, checkpoints=(checkpoint, *route.checkpoints[1:]))
    with pytest.raises(ValueError):
        validate_artifact_review_route(mutated)
    assert route.purpose == ARTIFACT_ONLY_PURPOSE


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

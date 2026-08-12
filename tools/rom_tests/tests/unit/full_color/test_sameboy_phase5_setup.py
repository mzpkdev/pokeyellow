"""Fail-closed contracts for the pinned official SameBoy authority."""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import re
import tarfile

import pytest

from tools.rom_tests.full_color import sameboy_phase5_setup as subject


ROOT = Path(__file__).parents[5]


def _assert_mutable_debugger_commands_and_early_auxiliary_ignore(source: str) -> None:
    assert re.search(
        r"GB_debugger_execute_command\s*\([^,]+,\s*\"", source
    ) is None
    owner_start = source.index(
        "if (vertical_path(driver) && at_linked_symbol(driver, driver->owner_end)) {"
    )
    deferred_start = source.index(
        "if (vertical_path(driver) &&\n"
        "        at_linked_symbol(driver, driver->deferred_accounting_start)) {"
    )
    expected_start = source.index("    symbol_t expected_symbol", deferred_start)
    for block in (
        source[owner_start:deferred_start],
        source[deferred_start:expected_start],
    ):
        assert "if (driver->expected == EXPECT_DEADLINE) {" in block
        # The unconditional return is outside the recording condition: an
        # auxiliary seam from an earlier VBlank is ignored instead of being
        # mistaken for the row's next ordered timing breakpoint.
        assert block.rfind('return strdup("continue");') > block.rfind("        }")


def test_driver_uses_mutable_debugger_commands_and_ignores_early_auxiliary_hits() -> None:
    source = (ROOT / subject.DRIVER_SOURCE).read_text(encoding="utf-8")
    _assert_mutable_debugger_commands_and_early_auxiliary_ignore(source)


@pytest.mark.parametrize("mutation", ("literal", "record_early", "order_early"))
def test_driver_auxiliary_breakpoint_mutations_fail_closed(mutation: str) -> None:
    source = (ROOT / subject.DRIVER_SOURCE).read_text(encoding="utf-8")
    if mutation == "literal":
        source = source.replace(
            "GB_debugger_execute_command(driver.gb, command);",
            'GB_debugger_execute_command(driver.gb, "continue");',
            1,
        )
    elif mutation == "record_early":
        source = source.replace(
            "if (driver->expected == EXPECT_DEADLINE) {", "if (true) {", 1
        )
    else:
        owner_start = source.index(
            "if (vertical_path(driver) && at_linked_symbol(driver, driver->owner_end)) {"
        )
        owner_return = source.index('return strdup("continue");', owner_start)
        source = source[:owner_return] + source[owner_return:].replace(
            'return strdup("continue");', 'return strdup("ticks keep");', 1
        )
    with pytest.raises((AssertionError, ValueError)):
        _assert_mutable_debugger_commands_and_early_auxiliary_ignore(source)


def _write_lock(root: Path, raw: dict[str, str]) -> None:
    path = root / subject.LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw), encoding="utf-8")


def _archive_with(name: str) -> tarfile.TarFile:
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        member = tarfile.TarInfo(name)
        member.size = 0
        archive.addfile(member, BytesIO())
    stream.seek(0)
    return tarfile.open(fileobj=stream, mode="r")


def test_repository_lock_pins_official_release_commit_and_archive() -> None:
    lock = subject.load_lock(ROOT)
    assert lock == {
        "schema": "sameboy-phase5-tool-lock-v1",
        "repository": "https://github.com/LIJI32/SameBoy",
        "tag": "v1.0.3",
        "commit": "208ba4afabffab9edde416f2dbb8ae459e34adb8",
        "archive_url": (
            "https://github.com/LIJI32/SameBoy/archive/"
            "208ba4afabffab9edde416f2dbb8ae459e34adb8.tar.gz"
        ),
        "archive_sha256": (
            "aca79238ef23c220b6332abb28b6a4bbe467995ff7a26073dcb3070a7054eab6"
        ),
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "https://example.invalid/SameBoy"),
        ("commit", "main"),
        ("archive_url", "https://github.com/LIJI32/SameBoy/archive/v1.0.3.tar.gz"),
        ("archive_sha256", "0" * 63),
    ],
)
def test_lock_identity_mutations_fail_closed(
    tmp_path: Path, field: str, value: str
) -> None:
    lock = deepcopy(subject.load_lock(ROOT))
    lock[field] = value
    _write_lock(tmp_path, lock)
    with pytest.raises(subject.SameBoySetupError):
        subject.load_lock(tmp_path)


@pytest.mark.parametrize(
    "name",
    [
        "/absolute",
        "SameBoy-abc/../../escape",
        "unexpected-root/file",
    ],
)
def test_archive_path_mutations_are_rejected(name: str) -> None:
    archive = _archive_with(name)
    try:
        with pytest.raises(subject.SameBoySetupError, match="unsafe member"):
            subject._safe_members(archive, "abc")
    finally:
        archive.close()


@pytest.mark.parametrize("kind", ("symlink", "hardlink"))
def test_archive_links_are_rejected(kind: str) -> None:
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        member = tarfile.TarInfo("SameBoy-abc/link")
        member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
        member.linkname = "target"
        archive.addfile(member)
    stream.seek(0)
    with tarfile.open(fileobj=stream, mode="r") as archive:
        with pytest.raises(subject.SameBoySetupError, match="unsafe member"):
            subject._safe_members(archive, "abc")


def test_existing_install_rejects_artifact_hash_drift(tmp_path: Path) -> None:
    lock = subject.load_lock(ROOT)
    artifacts = {}
    for name, filename in (
        ("driver", "driver"),
        ("library", "library"),
        ("boot_rom", "boot"),
    ):
        path = tmp_path / filename
        path.write_bytes(name.encode())
        artifacts[name] = {"path": filename, "sha256": subject._sha256(path)}
    (tmp_path / "install.json").write_text(
        subject._canonical(
            {
                "schema": subject.INSTALL_SCHEMA,
                "lock": lock,
                "driver_source_sha256": "a" * 64,
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )
    assert subject._validate_existing(tmp_path, lock, "a" * 64) is None
    (tmp_path / "boot").write_bytes(b"drift")
    assert subject._validate_existing(tmp_path, lock, "a" * 64) is None

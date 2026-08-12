"""Install the exact SameBoy timing authority into an ignored local root."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request


LOCK_PATH = Path("tools/rom_tests/sameboy-phase5.lock.json")
DRIVER_SOURCE = Path("tools/rom_tests/full_color/sameboy_phase5_driver.c")
LOCK_SCHEMA = "sameboy-phase5-tool-lock-v1"
INSTALL_SCHEMA = "sameboy-phase5-tool-install-v1"
EXPECTED_REPOSITORY = "https://github.com/LIJI32/SameBoy"


class SameBoySetupError(RuntimeError):
    """The pinned timing tool could not be installed or authenticated."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(raw: object) -> str:
    return json.dumps(raw, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"


def load_lock(root: Path) -> dict[str, str]:
    path = root / LOCK_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SameBoySetupError(f"invalid SameBoy lock: {exc}") from exc
    required = {
        "schema", "repository", "tag", "commit", "archive_url", "archive_sha256"
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise SameBoySetupError("SameBoy lock has an unexpected field set")
    if not all(isinstance(raw[name], str) for name in required):
        raise SameBoySetupError("SameBoy lock fields must be strings")
    if raw["schema"] != LOCK_SCHEMA or raw["repository"] != EXPECTED_REPOSITORY:
        raise SameBoySetupError("SameBoy lock does not name the official authority")
    commit = raw["commit"]
    archive_sha = raw["archive_sha256"]
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise SameBoySetupError("SameBoy lock commit is not an exact SHA-1")
    if len(archive_sha) != 64 or any(
        char not in "0123456789abcdef" for char in archive_sha
    ):
        raise SameBoySetupError("SameBoy archive identity is not an exact SHA-256")
    expected_url = f"{EXPECTED_REPOSITORY}/archive/{commit}.tar.gz"
    if raw["archive_url"] != expected_url:
        raise SameBoySetupError("SameBoy archive URL is not commit-addressed upstream")
    return {name: raw[name] for name in required}


def _safe_members(archive: tarfile.TarFile, commit: str) -> list[tarfile.TarInfo]:
    prefix = f"SameBoy-{commit}"
    members = archive.getmembers()
    if not members:
        raise SameBoySetupError("SameBoy archive is empty")
    for member in members:
        path = PurePosixPath(member.name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or path.parts[0] != prefix
            or member.issym()
            or member.islnk()
            or member.isdev()
        ):
            raise SameBoySetupError(
                f"SameBoy archive contains unsafe member {member.name!r}"
            )
    return members


def _run(command: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, check=False)
    if completed.returncode:
        raise SameBoySetupError(
            f"SameBoy setup command failed ({completed.returncode}): {' '.join(command)}"
        )


def _validate_existing(
    install_root: Path, lock: dict[str, str], driver_source_sha256: str
) -> dict[str, object] | None:
    manifest_path = install_root / "install.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or manifest.get("schema") != INSTALL_SCHEMA:
        return None
    if manifest.get("lock") != lock:
        return None
    if manifest.get("driver_source_sha256") != driver_source_sha256:
        return None
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    for name in ("driver", "library", "boot_rom"):
        item = artifacts.get(name)
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            return None
        path = install_root / str(item["path"])
        if not path.is_file() or _sha256(path) != item["sha256"]:
            return None
    driver = install_root / str(artifacts["driver"]["path"])
    try:
        completed = subprocess.run(
            [str(driver), "--version"], text=True, capture_output=True, check=False
        )
    except OSError:
        return None
    if completed.returncode or completed.stdout.strip() != "sameboy-phase5-driver-v1":
        return None
    return manifest


def install(root: Path, install_root: Path, *, jobs: int | None = None) -> dict[str, object]:
    root = root.resolve()
    install_root = install_root.resolve()
    lock = load_lock(root)
    driver_source = root / DRIVER_SOURCE
    if not driver_source.is_file():
        raise SameBoySetupError(f"missing SameBoy driver source: {DRIVER_SOURCE}")
    driver_source_sha256 = _sha256(driver_source)
    existing = _validate_existing(install_root, lock, driver_source_sha256)
    if existing is not None:
        return existing

    install_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="sameboy-phase5-", dir=install_root.parent
    ) as temporary_name:
        temporary = Path(temporary_name)
        archive_path = temporary / "sameboy.tar.gz"
        try:
            with urllib.request.urlopen(lock["archive_url"], timeout=60) as response:
                with archive_path.open("wb") as output:
                    shutil.copyfileobj(response, output)
        except (OSError, urllib.error.URLError) as exc:
            raise SameBoySetupError(f"could not download pinned SameBoy: {exc}") from exc
        if _sha256(archive_path) != lock["archive_sha256"]:
            raise SameBoySetupError("pinned SameBoy archive SHA-256 mismatch")

        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = _safe_members(archive, lock["commit"])
            archive.extractall(temporary, members=members, filter="data")
        source = temporary / f"SameBoy-{lock['commit']}"
        parallelism = jobs if jobs is not None else max(1, os.cpu_count() or 1)
        _run(
            [
                "make", f"-j{parallelism}", "CONF=release",
                "build/lib/libsameboy.a", "bootroms",
            ],
            cwd=source,
        )

        staged = temporary / "install"
        staged.mkdir()
        library = source / "build/lib/libsameboy.a"
        boot_rom = source / "build/bin/BootROMs/cgb_boot.bin"
        driver = staged / "sameboy-phase5-driver"
        _run(
            [
                os.environ.get("CC", "cc"),
                "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-D_POSIX_C_SOURCE=200809L", f"-I{source}",
                str(driver_source), str(library), "-lm", "-ldl", "-pthread",
                "-o", str(driver),
            ],
            cwd=root,
        )
        shutil.copy2(library, staged / "libsameboy.a")
        shutil.copy2(boot_rom, staged / "cgb_boot.bin")
        driver.chmod(driver.stat().st_mode | stat.S_IXUSR)

        artifacts = {
            "driver": {"path": driver.name, "sha256": _sha256(driver)},
            "library": {
                "path": "libsameboy.a",
                "sha256": _sha256(staged / "libsameboy.a"),
            },
            "boot_rom": {
                "path": "cgb_boot.bin",
                "sha256": _sha256(staged / "cgb_boot.bin"),
            },
        }
        manifest: dict[str, object] = {
            "schema": INSTALL_SCHEMA,
            "lock": lock,
            "driver_source_sha256": driver_source_sha256,
            "artifacts": artifacts,
        }
        (staged / "install.json").write_text(_canonical(manifest), encoding="utf-8")
        install_root.mkdir(parents=True, exist_ok=True)
        for staged_path in staged.iterdir():
            os.replace(staged_path, install_root / staged_path.name)

    validated = _validate_existing(install_root, lock, driver_source_sha256)
    if validated is None:
        raise SameBoySetupError("installed SameBoy timing tool failed validation")
    return validated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install pinned SameBoy Phase 5 tool")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--jobs", type=int)
    args = parser.parse_args(argv)
    try:
        manifest = install(args.root, args.install_root, jobs=args.jobs)
    except SameBoySetupError as exc:
        parser.error(str(exc))
    print(_canonical(manifest), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

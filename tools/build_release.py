#!/usr/bin/env python3
"""Build a source ZIP without Git metadata, local credentials, profiles, or media.

Works in a checkout or an extracted release. Runtime directories are not walked;
only application/source/config/docs/tests and asset README files are eligible.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import zipfile

ROOT_SUFFIXES = {".md", ".py", ".txt", ".sh", ".bat", ".yaml", ".yml", ".csv"}
ROOT_FILES = {"VERSION", ".env.example", ".gitignore", "app.py", "cli.py", "requirements.txt",
              "requirements-test.txt", "video_config.yaml", "clip_config.yaml", "topics.csv",
              "check-cdp.bat", "chrome-debug.bat", "chrome-debug.sh", "dashboard.bat", "dashboard.sh",
              "run.sh", "run_windows.bat", "run_flow_companion_windows.bat",
              "setup_mac_linux.sh", "setup_windows.bat"}
SOURCE_DIRS = {"engine", "config", "chrome_extension", "tests", "tools", ".github", "assets"}
SOURCE_SUFFIXES = ROOT_SUFFIXES | {".json", ".js", ".css", ".html", ".example", ".svg", ".png", ".jpg", ".jpeg"}
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".cache", ".local",
                 ".flow-profile", ".gemini-profile", ".movieflow-profile", "cookies", "credentials",
                 "outputs", "data", "releases", "node_modules", "build", "dist"}
EXCLUDED_FILES = {".flow_session.json", "config/user_settings.yaml", "config/user_settings.yml"}


def release_files(root: Path) -> list[Path]:
    root = root.resolve()
    result = []
    # Explicit root-file allowlist prevents old release ZIPs or runtime files
    # from recursively inflating the new download.
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        if path.name in ROOT_FILES or (not path.name.startswith(".") and path.suffix.lower() == ".md"):
            result.append(path)
    for directory in sorted(SOURCE_DIRS):
        base = root / directory
        if base.is_symlink() or not base.is_dir():
            continue
        for current, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS
                             and not (Path(current) / d).is_symlink())
            for name in sorted(files):
                path = Path(current) / name
                rel = path.relative_to(root).as_posix()
                if (path.is_symlink() or rel in EXCLUDED_FILES or name.startswith(".")
                        or name.lower() in ("credentials.json", "cookies.json", "secrets.json", "token.json")):
                    continue
                if directory == "assets":
                    # These folders are user-supplied footage/music libraries,
                    # not redistributable build artifacts.
                    bundled_fonts = {"assets/fonts/Bungee-Regular.ttf", "assets/fonts/Fredoka-Variable.ttf",
                                     "assets/fonts/OFL-Bungee.txt", "assets/fonts/OFL-Fredoka.txt",
                                     "assets/fonts/NotoSansOriya-Variable.ttf", "assets/fonts/NotoSansDevanagari-Variable.ttf",
                                     "assets/fonts/OFL-NotoSansOriya.txt", "assets/fonts/OFL-NotoSansDevanagari.txt"}
                    if rel not in bundled_fonts and name.lower() not in ("readme.md", "readme.txt"):
                        continue
                elif path.suffix.lower() not in SOURCE_SUFFIXES:
                    continue
                result.append(path)
    return sorted(result, key=lambda path: path.relative_to(root).as_posix())


def build_release(root, destination=None) -> dict:
    root = Path(root).resolve()
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-.][A-Za-z0-9_-]+)*", version):
        raise ValueError("VERSION must contain a safe release version such as 5.8.5")
    files = release_files(root)
    relative = {path.relative_to(root).as_posix() for path in files}
    required = {"VERSION", "app.py", "cli.py", "requirements.txt", "engine/factory.py", ".env.example"}
    missing = required - relative
    if missing:
        raise ValueError("Missing release files: " + ", ".join(sorted(missing)))
    prefix = f"AutoVideoAI-v{version}"
    output = Path(destination) if destination else root / "releases" / f"{prefix}-Quality-Pause-Diagnostics.zip"
    output = output.resolve()
    if output.suffix.lower() != ".zip":
        raise ValueError("Release output must be a .zip file")
    if output in files:
        raise ValueError("Release output cannot replace a source file")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"version": version,
                "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "files": []}
    temporary = output.with_name(output.name + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files:
                rel = path.relative_to(root).as_posix()
                content = path.read_bytes()
                info = zipfile.ZipInfo.from_file(path, arcname=f"{prefix}/{rel}")
                info.compress_type = zipfile.ZIP_DEFLATED
                # Shell scripts must remain launchable after a WSL/Linux unzip.
                mode = 0o755 if path.suffix == ".sh" else stat.S_IMODE(path.stat().st_mode)
                info.external_attr = (stat.S_IFREG | mode) << 16
                archive.writestr(info, content)
                manifest["files"].append({"path": rel, "bytes": len(content),
                                          "sha256": hashlib.sha256(content).hexdigest()})
            archive.writestr(f"{prefix}/RELEASE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Release archive failed CRC verification")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return {"path": str(output), "version": version, "files": len(files),
            "bytes": output.stat().st_size, "sha256": digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="Destination ZIP; default releases/AutoVideoAI-vVERSION-Quality-Pause-Diagnostics.zip")
    args = parser.parse_args()
    try:
        result = build_release(args.root, args.output)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Release build failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

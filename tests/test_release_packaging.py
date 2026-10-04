import hashlib
import json
from pathlib import Path
import stat
import zipfile

import pytest

from tools.build_release import build_release


def write(root, name, text="public source"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def source(root):
    root.mkdir()
    for name in ("app.py", "cli.py", "requirements.txt", "engine/factory.py", ".env.example"):
        write(root, name)
    write(root, "VERSION", "5.8.5\n")
    write(root, "README.md", "Public documentation")
    write(root, "dashboard.sh", "#!/bin/bash\ntrue\n").chmod(0o644)
    return root


def test_source_zip_excludes_credentials_profiles_outputs_and_prior_archives(tmp_path):
    root = source(tmp_path / "project")
    for name in (".env", ".env.local", "config/user_settings.yaml", "outputs/job/pause_state.json", "data/jobs.db",
                 ".git/config", ".flow-profile/Default/Cookies",
                 ".flow-workers/job-economy-worker-1/Default/Cookies",
                 ".venv/bin/python", "private-config.yaml",
                 "old-release.zip", "engine/__pycache__/module.pyc", "config/.env", "config/credentials.json",
                 "assets/music/private-song.mp3", "assets/stock_library/private-video.mp4"):
        write(root, name, "PRIVATE CONTENT")
    write(root, "config/user_settings.yaml.example", "public defaults")
    write(root, "assets/music/README.txt", "Music setup instructions")
    write(root, "tests/test_public.py", "public tests")
    write(root, "engine/linked.py", "placeholder").unlink()
    (root / "engine" / "linked.py").symlink_to(root / ".env")
    result = build_release(root)
    with zipfile.ZipFile(result["path"]) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        prefix = "AutoVideoAI-v5.8.5/"
        assert all(name.startswith(prefix) for name in names)
        assert prefix + ".env.example" in names
        assert prefix + "assets/music/README.txt" in names
        assert prefix + "config/user_settings.yaml.example" in names
        assert not any("PRIVATE CONTENT" in archive.read(name).decode(errors="replace") for name in names)
        assert not any(name.endswith(".zip") or "__pycache__" in name for name in names)
        assert archive.getinfo(prefix + "dashboard.sh").external_attr >> 16 & stat.S_IXUSR
        manifest = json.loads(archive.read(prefix + "RELEASE_MANIFEST.json"))
        assert len(manifest["files"]) == result["files"]
        for row in manifest["files"]:
            data = archive.read(prefix + row["path"])
            assert hashlib.sha256(data).hexdigest() == row["sha256"] and len(data) == row["bytes"]
    assert hashlib.sha256(Path(result["path"]).read_bytes()).hexdigest() == result["sha256"]
    second = build_release(root)
    assert second["files"] == result["files"]  # No recursive packaging of previous builds.


@pytest.mark.parametrize("version", ["../escape", "5.8.5/../../path", "", "5.8.5\nmalformed"])
def test_release_version_cannot_escape_archive_prefix(tmp_path, version):
    root = source(tmp_path / "project")
    write(root, "VERSION", version)
    with pytest.raises(ValueError, match="VERSION"):
        build_release(root)


def test_missing_application_source_fails_instead_of_shipping_partial_zip(tmp_path):
    root = source(tmp_path / "project")
    (root / "engine" / "factory.py").unlink()
    with pytest.raises(ValueError, match="Missing release"):
        build_release(root)
    assert not (root / "releases").exists()

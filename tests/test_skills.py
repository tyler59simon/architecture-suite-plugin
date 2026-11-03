"""The plugin ships nine skills sharing one runtime; every host layout must expose all of them."""

import json
import re
from pathlib import Path

from architecture_suite import __version__
from architecture_suite.distribution import RUNTIME_NAME, VERSION, skill_names

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED = {
    "c4-diagrams", "reverse-engineer-c4", "c4-system", "c4-container",
    "c4-component", "c4-code", "c4-overview", "c4-aws", "c4-gcp",
}


def test_exactly_the_nine_skills():
    assert set(skill_names(SKILLS)) == EXPECTED
    assert not (SKILLS / RUNTIME_NAME / "SKILL.md").exists()


def test_frontmatter_is_valid():
    for name in EXPECTED:
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", text)
        assert match and match.group(1) == name
        assert 40 < len(match.group(2)) <= 1024


def test_relative_runtime_links_resolve():
    for name in EXPECTED:
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        for rel in re.findall(r"`(\.\./architecture-suite-runtime/[^`]+)`", text):
            assert (SKILLS / name / rel).exists(), (name, rel)
        for rel in re.findall(r"`(assets/[^`\s]+)`", text):
            assert (SKILLS / name / rel).exists(), (name, rel)


def test_single_version_source():
    assert __version__ == VERSION
    assert f'version = "{VERSION}"' in (ROOT / "pyproject.toml").read_text()
    for path in (".claude-plugin/plugin.json", ".factory-plugin/plugin.json"):
        assert json.loads((ROOT / path).read_text())["version"] == VERSION
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert market["plugins"][0]["version"] == VERSION
    assert json.loads((ROOT / "package.json").read_text())["version"] == VERSION
    assert f"## {VERSION}" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_both_pyprojects_declare_the_same_runtime():
    import tomllib

    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    skill = tomllib.loads(
        (SKILLS / RUNTIME_NAME / "scripts/pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    for key in ("version", "requires-python", "dependencies"):
        assert root[key] == skill[key], key


def test_runtime_lock_is_hashed_and_covers_dependencies():
    import tomllib

    lock = (SKILLS / RUNTIME_NAME / "scripts/requirements-runtime.lock").read_text(encoding="utf-8")
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==(\S+)", lock, re.M))
    assert pins and lock.count("--hash=sha256:") >= len(pins)
    lowered = {name.lower(): version for name, version in pins.items()}
    project = tomllib.loads(
        (SKILLS / RUNTIME_NAME / "scripts/pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    for spec in project["dependencies"]:
        name, version = spec.split("==")
        assert lowered[name.lower()] == version, spec


def test_license_metadata_and_legal_files_ship(tmp_path):
    import zipfile
    from architecture_suite.distribution import install_host, package_hosts, plugin_manifest

    assert (ROOT / "LICENSE").read_text(encoding="utf-8").lstrip().startswith("Apache License")
    assert "Apache License" in (ROOT / "NOTICE").read_text(encoding="utf-8")
    for path in (".claude-plugin/plugin.json", ".factory-plugin/plugin.json"):
        assert json.loads((ROOT / path).read_text())["license"] == "Apache-2.0"
    assert plugin_manifest("claude")["author"]["name"]
    package_hosts(SKILLS, tmp_path, hosts=["claude", "codex"])
    with zipfile.ZipFile(tmp_path / "claude.zip") as bundle:
        names = set(bundle.namelist())
    assert {"LICENSE", "NOTICE", f"skills/{RUNTIME_NAME}/LICENSE"} <= names
    assert sum("/assets/gcp/" in name for name in names) == 261  # bundled GCP icons ship
    with zipfile.ZipFile(tmp_path / "codex.zip") as bundle:
        assert f".agents/skills/{RUNTIME_NAME}/NOTICE" in bundle.namelist()
    target = install_host(SKILLS, "claude", "project", tmp_path / "project")
    assert (target / RUNTIME_NAME / "LICENSE").is_file()


def test_manifests_and_package_errors(tmp_path):
    from architecture_suite.distribution import marketplace_manifest, package_hosts, plugin_manifest

    market = marketplace_manifest("9.9.9")
    assert market["plugins"][0]["source"] == "." and market["plugins"][0]["version"] == "9.9.9"
    assert plugin_manifest("claude", "9.9.9")["version"] == "9.9.9"
    import pytest

    with pytest.raises(ValueError, match="No skills"):
        package_hosts(tmp_path, tmp_path)
    (tmp_path / "s").mkdir()
    (tmp_path / "s/SKILL.md").write_text("---\nname: s\ndescription: x\n---\n")
    with pytest.raises(ValueError, match="Unknown host"):
        package_hosts(tmp_path, tmp_path, hosts=["nope"])


def test_packages_are_slim_and_release_tree_is_self_contained(tmp_path):
    import zipfile
    from architecture_suite.distribution import package_hosts, write_plugin_tree

    package_hosts(SKILLS, tmp_path)
    for archive in tmp_path.glob("*.zip"):
        assert archive.stat().st_size < 15_000_000, archive.name
        with zipfile.ZipFile(archive) as bundle:
            samples = [n for n in bundle.namelist() if "/samples/" in n]
        assert all("/samples/extensions/" in n for n in samples), archive.name
        assert len(samples) <= 6, archive.name

    tree = write_plugin_tree(SKILLS, tmp_path / "plugin")
    write_plugin_tree(SKILLS, tree)  # rebuilding replaces the previous tree
    assert {
        "LICENSE", "NOTICE", "README.md", ".gitattributes", ".claude-plugin", ".factory-plugin",
        "skills",
    } == {
        p.name for p in tree.iterdir()
    }
    market = json.loads((tree / ".claude-plugin/marketplace.json").read_text())
    assert market["plugins"][0]["source"] == "."
    assert set(skill_names(tree / "skills")) == EXPECTED
    assert not any(p.suffix == ".pyc" or "egg-info" in p.as_posix() for p in tree.rglob("*"))
    import pytest

    (tmp_path / "nothing").mkdir()
    with pytest.raises(ValueError, match="No skills"):
        write_plugin_tree(tmp_path / "nothing", tmp_path / "out")

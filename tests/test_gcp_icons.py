"""Optional, user-installed Google Cloud icons: install, status, absence and tampering."""

import hashlib
import json
import zipfile

import pytest

from architecture_suite import aws
from architecture_suite.cli import main
from architecture_suite.safety import SafetyError
from architecture_suite.style import element_label

GKE = "GCP-Google-Kubernetes-Engine"


def test_status_and_absence(gcp_icons, tmp_path, monkeypatch):
    assert aws.gcp_icon_status().startswith("ok (")
    assert aws.icon_available(GKE) and aws.icon_available("Amazon-EC2")
    assert not aws.icon_available(None) and not aws.icon_available("GCP-unknown")
    element = {"name": "Rider", "type": "container", "cloud": {"provider": "gcp", "service": GKE}}
    assert element_label(element).icon == GKE

    monkeypatch.setenv(aws.GCP_ICON_ENV, str(tmp_path / "empty"))
    assert aws.gcp_icon_status().startswith("not installed")
    assert not aws.icon_available(GKE)
    assert element_label(element).icon is None  # renders without an icon
    with pytest.raises(SafetyError, match="not installed"):
        aws.icon_bytes(GKE)
    monkeypatch.delenv(aws.GCP_ICON_ENV)
    assert aws.gcp_icon_root().name == "gcp-icons"


def test_tampered_icon_is_rejected(gcp_icons, tmp_path, monkeypatch):
    rel = aws.catalog("gcp")[GKE]["file"]
    copy = tmp_path / rel
    copy.parent.mkdir(parents=True)
    copy.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    monkeypatch.setenv(aws.GCP_ICON_ENV, str(tmp_path))
    with pytest.raises(SafetyError, match="checksum"):
        aws.gcp_icon_status()
    with pytest.raises(SafetyError, match="checksum"):
        aws.icon_bytes(GKE)


def test_install_from_downloads(gcp_icons, tmp_path, capsys, monkeypatch):
    entries = aws.catalog("gcp")
    modern = tmp_path / "download"
    legacy_zip = tmp_path / "legacy.zip"
    with zipfile.ZipFile(legacy_zip, "w") as bundle:
        for entry in entries.values():
            data = (gcp_icons / entry["file"]).read_bytes()
            if entry["style"] == "modern":
                source = modern / entry["source"]
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(data)
            else:
                bundle.writestr(entry["source"], data)
    target = tmp_path / "installed"
    args = ["install-gcp-icons", "--modern", str(modern), "--legacy-zip", str(legacy_zip),
            "--target", str(target)]
    assert main(args + ["--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["found"] == len(entries)
    assert main(args) == 3  # writing needs --confirm-write
    capsys.readouterr()
    assert main(args + ["--confirm-write"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["installed"] == len(entries) and not result["missing"]
    monkeypatch.setenv(aws.GCP_ICON_ENV, str(target))
    assert aws.gcp_icon_status() == f"ok ({len(entries)} of {len(entries)} icons)"

    # Reinstall from an existing layout; a modified file is skipped and reported.
    rel = entries[GKE]["file"]
    (target / rel).write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    again = ["install-gcp-icons", "--from", str(target), "--target", str(tmp_path / "second"),
             "--confirm-write"]
    assert main(again) == 1
    assert json.loads(capsys.readouterr().out)["checksum_mismatch"] == [rel]


def test_install_errors(gcp_icons, tmp_path, capsys):
    assert main(["install-gcp-icons", "--target", str(tmp_path / "t")]) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["install-gcp-icons", "--from", str(empty), "--target", str(tmp_path / "t"),
                 "--confirm-write"]) == 2
    assert json.loads(capsys.readouterr().out)["installed"] == 0
    unsafe = b'<svg xmlns="http://www.w3.org/2000/svg" onload="x"/>'
    rel = aws.catalog("gcp")[GKE]["file"]
    manifest = {rel: hashlib.sha256(unsafe).hexdigest()}
    original = aws.gcp_manifest
    aws.gcp_manifest = lambda: manifest
    try:
        with pytest.raises(SafetyError, match="Unsafe"):
            aws.install_gcp_icons({rel: unsafe}, tmp_path / "stage")
    finally:
        aws.gcp_manifest = original


def test_doctor_reports_optional_icons(gcp_icons, capsys, monkeypatch, tmp_path):
    assert main(["doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["gcp_icons"].startswith("ok")
    monkeypatch.setenv(aws.GCP_ICON_ENV, str(tmp_path))
    rel = aws.catalog("gcp")[GKE]["file"]
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_bytes(b"<svg/>")
    assert main(["doctor"]) == 0  # informational, never gating
    assert "checksum" in json.loads(capsys.readouterr().out)["gcp_icons"]


def test_shipped_checksums_cover_exactly_the_catalogue(gcp_icons):
    shipped = aws.shipped_gcp_manifest()
    files = {entry["file"] for entry in aws.catalog("gcp").values()}
    assert set(shipped) == files
    assert all(len(digest) == 64 for digest in shipped.values())

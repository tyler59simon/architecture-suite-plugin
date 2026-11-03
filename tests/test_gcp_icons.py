"""Bundled Google Cloud icons: integrity, the folder override, absence and tampering."""

import json

import pytest

from architecture_suite import aws
from architecture_suite.cli import main
from architecture_suite.safety import SafetyError
from architecture_suite.style import element_label

GKE = "GCP-Google-Kubernetes-Engine"


def test_bundled_icons_are_complete_and_verified():
    expected = aws.gcp_manifest()
    assert set(expected) == {entry["file"] for entry in aws.catalog("gcp").values()}
    assert aws.gcp_icon_root() == aws.ASSETS / "gcp"
    assert aws.gcp_icon_status() == f"ok ({len(expected)} of {len(expected)} icons)"
    core = aws.verify_assets()
    assert all(f"gcp/{rel}" in core for rel in expected)  # doctor's assets check covers them
    assert aws.icon_available(GKE) and aws.icon_available("Amazon-EC2")
    assert not aws.icon_available(None) and not aws.icon_available("GCP-unknown")


def test_missing_override_folder_renders_without_icons(tmp_path, monkeypatch):
    element = {"name": "Rider", "type": "container", "cloud": {"provider": "gcp", "service": GKE}}
    assert element_label(element).icon == GKE
    monkeypatch.setenv(aws.GCP_ICON_ENV, str(tmp_path / "empty"))
    assert aws.gcp_icon_status().startswith("missing")
    assert not aws.icon_available(GKE)
    assert element_label(element).icon is None
    with pytest.raises(SafetyError, match="not installed"):
        aws.icon_bytes(GKE)


def test_tampered_icon_is_rejected(tmp_path, monkeypatch, capsys):
    rel = aws.catalog("gcp")[GKE]["file"]
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    monkeypatch.setenv(aws.GCP_ICON_ENV, str(tmp_path))
    with pytest.raises(SafetyError, match="checksum"):
        aws.gcp_icon_status()
    with pytest.raises(SafetyError, match="checksum"):
        aws.icon_bytes(GKE)
    assert main(["doctor"]) == 0  # gcp_icons reports the override; bundled assets stay ok
    assert "checksum" in json.loads(capsys.readouterr().out)["gcp_icons"]


def test_doctor_reports_bundled_icons(capsys):
    assert main(["doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["gcp_icons"].startswith("ok (")

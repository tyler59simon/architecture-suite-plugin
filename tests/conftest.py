import json
import pytest
from architecture_suite.examples import example_model, example_plan
from architecture_suite.draft import render_plan


@pytest.fixture
def model():
    return example_model()


@pytest.fixture
def plan():
    return example_plan()


@pytest.fixture
def inputs(tmp_path, model, plan):
    m = tmp_path / "model.json"
    p = tmp_path / "plan.md"
    m.write_text(json.dumps(model), encoding="utf-8")
    p.write_text(render_plan(plan), encoding="utf-8")
    return m, p


@pytest.fixture(scope="session", autouse=True)
def gcp_icons(tmp_path_factory):
    """Google Cloud icons are not redistributable, so tests use generated stand-ins.

    Writes one small valid SVG per catalogue entry, points the runtime at them and
    substitutes their checksums for the shipped manifest-gcp.json values.
    """
    import hashlib
    import os
    from architecture_suite import aws

    root = tmp_path_factory.mktemp("gcp-icons")
    manifest = {}
    for key, entry in aws.catalog("gcp").items():
        data = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            f'<title>{key}</title><rect width="24" height="24" fill="#4285f4"/></svg>'
        ).encode()
        path = root / entry["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest[entry["file"]] = hashlib.sha256(data).hexdigest()
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(aws.GCP_ICON_ENV, str(root))
        # Keep the real loader reachable so a test can check the shipped manifest.
        patch.setattr(aws, "shipped_gcp_manifest", aws.gcp_manifest, raising=False)
        patch.setattr(aws, "gcp_manifest", lambda: manifest)
        assert os.environ[aws.GCP_ICON_ENV] == str(root)
        yield root

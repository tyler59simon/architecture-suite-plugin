import json
import pytest
from architecture_suite.cli import main
from architecture_suite.model import validate_model
from architecture_suite.renderers import validate_png


@pytest.mark.parametrize(
    "manifest,source,code",
    [
        (
            "app.csproj",
            "App.cs",
            "public class App { public string Handle(int x) { return x.ToString(); } }",
        ),
        (
            "pom.xml",
            "App.java",
            "public class App { public String handle(int x) { return null; } }",
        ),
        ("go.mod", "app.go", 'package main\nfunc Handle(x int) string { return "x" }'),
        ("package.json", "app.ts", "export function handle(x: number) { return x; }"),
        ("pyproject.toml", "app.py", "def work(x: int) -> str:\n    return str(x)\n"),
    ],
)
def test_analyze_complete_offline_artifact_set(
    tmp_path, manifest, source, code, capsys
):
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / manifest).write_text(
        "{}" if manifest.endswith("json") else "# fixture", encoding="utf-8"
    )
    (repo / source).write_text(code, encoding="utf-8")
    output = tmp_path / "diagrams"
    args = ["analyze", "--repo", str(repo), "--output", str(output), "--format", "all"]
    assert main(args + ["--dry-run"]) == 0
    expected = json.loads(capsys.readouterr().out)["files"]
    assert main(args + ["--confirm-write"]) == 0
    actual = sorted(
        p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
    )
    assert actual == sorted(expected)
    model = json.loads((output / "architecture-model.json").read_text())
    assert not validate_model(model)
    assert len(list(output.rglob("*.png"))) == 5
    assert all(validate_png(p) for p in output.rglob("*.png"))
    assert len(list(output.rglob("*.vsdx"))) == 5

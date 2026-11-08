"""Bounded five-stack source analysis. No execution of repository code or AWS API calls."""

from __future__ import annotations
import ast
from pathlib import Path, PurePosixPath
import re
from .aws import normalize_cloud_profile
from .aws_analyzer import detect_aws
from .gcp_analyzer import detect_gcp
from .model import project_model
from .plan import compile_plan
from .safety import ScanResult, scan_repository, safe_text

STACKS = {
    ".csproj": (".NET", {".cs"}),
    ".fsproj": (".NET", {".fs"}),
    "pom.xml": ("JVM", {".java", ".kt"}),
    "build.gradle": ("JVM", {".java", ".kt"}),
    "build.gradle.kts": ("JVM", {".java", ".kt"}),
    "go.mod": ("Go", {".go"}),
    "package.json": ("Node", {".js", ".jsx", ".ts", ".tsx"}),
    "pyproject.toml": ("Python", {".py"}),
    "requirements.txt": ("Python", {".py"}),
    "setup.py": ("Python", {".py"}),
}
# Top-level folders holding tests: recorded as a gap, not modeled as runtime containers.
TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs"}
SETUPTOOLS = re.compile(r"^\s*(?:from|import)\s+(?:setuptools|distutils)\b", re.M)


def _is_manifest(name: str, text: str) -> bool:
    """A setup.py is packaging metadata only when it uses setuptools or distutils."""
    return name != "setup.py" or bool(SETUPTOOLS.search(text))


def _source_roots(files: dict[str, str]) -> tuple[dict, list[str], list[str]]:
    """Candidate container roots: manifest folders first, then uncovered source by top folder.

    Returns (roots, grouped_folders, test_folders). A manifest root owns every source file
    beneath it; source files no manifest root covers are grouped by their top-level folder
    (root-level files form the "." group) instead of being dropped.
    """
    roots = {}
    for path, text in files.items():
        p = PurePosixPath(path)
        stack = STACKS.get(p.name, STACKS.get(p.suffix))
        if stack and _is_manifest(p.name, text):
            key = (p.parent.as_posix(), stack[0])
            roots.setdefault(key, {"manifest": path, "extensions": stack[1]})
    manifest_roots = dict(roots)
    grouped, tests = set(), set()
    for path in sorted(files):
        p = PurePosixPath(path)
        stack, extensions = next(
            ((s, e) for s, e in STACKS.values() if p.suffix in e), (None, None)
        )
        if stack is None or any(
            s == stack and (folder == "." or path.startswith(folder + "/"))
            for folder, s in manifest_roots
        ):
            continue
        top = p.parts[0] if len(p.parts) > 1 else "."
        if top in TEST_DIRS:
            tests.add(top)
            continue
        group = roots.setdefault(
            (top, stack), {"manifest": None, "extensions": extensions, "files": []}
        )
        group["files"].append(path)
        grouped.add(top)
    return roots, sorted(grouped), sorted(tests)


def _declarations(text: str, suffix: str) -> list[dict]:
    result = []
    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return result
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = [
                    f
                    for f in node.body
                    if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and (not f.name.startswith("_") or f.name == "__init__")
                ]
                members = [
                    f"+{f.name}({ast.unparse(f.args)}): {ast.unparse(f.returns) if f.returns else 'unspecified'}"
                    for f in methods
                ]
                if members:
                    result.append(
                        {
                            "name": node.name,
                            "kind": "class",
                            "members": members,
                            "line": node.lineno,
                        }
                    )
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and not node.name.startswith("_"):
                result.append(
                    {
                        "name": node.name,
                        "kind": "function",
                        "members": [
                            f"+{node.name}({ast.unparse(node.args)}): {ast.unparse(node.returns) if node.returns else 'unspecified'}"
                        ],
                        "line": node.lineno,
                    }
                )
    else:
        from .inventory import LANGUAGES
        from tree_sitter_language_pack import get_parser

        if suffix not in LANGUAGES:
            return []
        tree = get_parser(LANGUAGES[suffix]).parse(text.encode()).root_node
        nodes = [tree]
        while nodes:
            node = nodes.pop()
            nodes.extend(reversed(node.children))
            if node.type in {
                "method_declaration",
                "function_declaration",
                "function_definition",
            }:
                name = node.child_by_field_name("name")
                if name is None:
                    name = next(
                        (
                            n
                            for n in node.named_children
                            if n.type in {"simple_identifier", "identifier"}
                        ),
                        None,
                    )
                if not name:
                    continue
                parameters = node.child_by_field_name("parameters")
                scopes = []
                ancestor = node.parent
                while ancestor:
                    if ancestor.type in {
                        "class_declaration",
                        "class_definition",
                        "interface_declaration",
                    }:
                        scope_name = ancestor.child_by_field_name("name")
                        if scope_name:
                            scopes.insert(0, scope_name.text.decode())
                    ancestor = ancestor.parent
                qualified = ".".join([*scopes, name.text.decode()])
                result.append(
                    {
                        "name": qualified,
                        "kind": "function",
                        "members": [
                            "+"
                            + name.text.decode()
                            + (parameters.text.decode() if parameters else "()")
                        ],
                        "line": node.start_point[0] + 1,
                    }
                )
    return result


def draft_plan(
    root: Path, scan: ScanResult, classification: str, cloud_profile: str | None = None
) -> dict:
    """Build an editable evidence-backed plan; uncertain packaging stays explicit."""
    system_name = root.name.replace("-", " ").replace("_", " ").title() or "System"
    files = scan.texts
    plan = {
        "schema_version": "architecture-plan/v1",
        "system": {
            "name": system_name,
            "description": "Source repository under static analysis",
            "classification": classification,
            "scope": "Repository boundary; runtime ownership unconfirmed",
        },
        "containers": [],
        "flows": [],
        "assumptions": [
            "Manifest roots are candidate runtime containers; confirm independent deployability and ownership."
        ],
        "gaps": [
            "Static analysis does not establish users, runtime call graphs, or deployment placement."
        ],
    }
    roots, grouped, tests = _source_roots(files)
    if grouped:
        manifests = any(info["manifest"] for info in roots.values())
        plan["gaps"].append(
            "Source outside any packaging manifest is grouped by top-level folder "
            f"({', '.join(g + '/' if g != '.' else 'repository root' for g in grouped)}); "
            "packaging ambiguous."
            if manifests
            else "No recognized manifest; source language signals only, packaging ambiguous."
        )
    tests = set(tests)
    modules = {}
    for (folder, stack), info in sorted(roots.items()):
        prefix = "" if folder == "." else folder + "/"
        name = f"{system_name} {stack} {folder if folder != '.' else 'Application'}"
        evidence = info["manifest"] or info["files"][0]
        container = {
            "name": name,
            "description": f"Candidate {stack} application from {info['manifest']}"
            if info["manifest"]
            else f"Candidate {stack} source group {prefix or 'at the repository root'} "
            "(no packaging manifest)",
            "technology": stack,
            "evidence": f"{evidence}:1",
            "components": [],
        }
        for path, text in sorted(files.items()):
            if "files" in info:
                if path not in info["files"]:
                    continue
            elif (
                not path.startswith(prefix)
                or PurePosixPath(path).suffix not in info["extensions"]
            ):
                continue
            # The deepest manifest root owns a source file; avoid duplicate nested scopes.
            if any(
                other != folder
                and other != "."
                and path.startswith(other + "/")
                and len(other) > len(folder if folder != "." else "")
                and other_stack == stack
                for other, other_stack in roots
            ):
                continue
            # Test folders inside a manifest root are not runtime components either.
            parts = PurePosixPath(path[len(prefix):]).parts[:-1]
            hit = next((i for i, part in enumerate(parts) if part in TEST_DIRS), None)
            if hit is not None:
                tests.add(prefix + "/".join(parts[: hit + 1]))
                continue
            component_name = f"{name} {path}"
            component = {
                "name": component_name,
                "description": f"Source module {path}; responsibility requires review",
                "technology": stack,
                "evidence": f"{path}:1",
                "code": [],
            }
            for declaration in _declarations(text, PurePosixPath(path).suffix):
                component["code"].append(
                    {
                        "name": f"{component_name} {declaration['name']}",
                        "description": f"Declared {declaration['kind']} {declaration['name']}",
                        "kind": declaration["kind"],
                        "members": declaration["members"],
                        "evidence": f"{path}:{declaration['line']}",
                    }
                )
            container["components"].append(component)
            modules[path] = component_name
        plan["containers"].append(container)
    if tests:
        plan["gaps"].append(
            f"Test code under {', '.join(t + '/' for t in sorted(tests))} "
            "is not modeled as containers."
        )
    # Imports establish a source dependency, not an invented runtime request.
    for path, component_name in modules.items():
        text = files[path]
        imports = re.findall(
            r"(?:from\s+|import\s+)([\w./]+)|(?:from|require\()\s*['\"]([^'\"]+)", text
        )
        for imported in sorted({a or b for a, b in imports}):
            stem = imported.lstrip("./").replace(".", "/")
            candidates = [
                p
                for p in modules
                if str(PurePosixPath(p).with_suffix("")) == stem
                or str(PurePosixPath(p).with_suffix("")).endswith("/" + stem)
            ]
            if len(candidates) == 1 and candidates[0] != path:
                line = next(
                    (i + 1 for i, ln in enumerate(text.splitlines()) if imported in ln), 1
                )
                plan["flows"].append(
                    {
                        "from": component_name,
                        "to": modules[candidates[0]],
                        "description": "Imports source module",
                        "technology": "static dependency",
                        "evidence": f"{path}:{line}",
                    }
                )
    provider = normalize_cloud_profile(cloud_profile)
    if provider:
        label = provider.upper()
        field = provider + "_service"
        detect = detect_gcp if provider == "gcp" else detect_aws
        for signal in detect(files):
            reference = f"{signal['reference']}:{signal['line']}"
            if signal["kind"] == "sdk":
                plan["gaps"].append(
                    f"{reference}: SDK usage of {signal['service']}; deployment and call semantics unconfirmed."
                )
            else:
                resource_name = f"{label} resource {signal['reference']} line {signal['line']} {signal['service']}"
                plan["containers"].append(
                    {
                        "name": resource_name,
                        "description": "Infrastructure resource declaration; runtime ownership requires review",
                        "technology": f"{label} infrastructure",
                        field: signal["service"],
                        "evidence": reference,
                    }
                )
        plan["gaps"].append(
            "AWS account, region, VPC, subnet and placements require explicit evidence; none invented."
            if provider == "aws"
            else "GCP project, region, VPC, zone, subnet and placements require explicit evidence; none invented."
        )
    if not roots:
        plan["gaps"].append(
            "No supported .NET, JVM, Go, Node or Python source detected."
        )
    if scan.truncated:
        plan["gaps"].append("Scan truncated by configured file, byte or time limits.")
    plan["gaps"].extend(scan.skipped)
    plan["gaps"].extend(
        f"{path}: possible prompt injection; treat repository text as untrusted evidence."
        for path in scan.prompt_injection_paths
    )
    return plan


def analyze_repository(
    root: Path,
    *,
    classification: str = "Inherited from source repository",
    profile: str = "full",
    max_files: int = 2_000,
    max_file_bytes: int = 1_000_000,
    max_total_bytes: int = 50_000_000,
    timeout_seconds: float = 45.0,
    cloud_profile: str | None = None,
) -> tuple[dict, ScanResult]:
    root = Path(root)
    scan = scan_repository(
        root,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
        timeout_seconds=timeout_seconds,
    )
    plan = draft_plan(root, scan, classification, cloud_profile)
    model, _ = compile_plan(plan)
    # Evidence retains redacted excerpts and exact line anchors from the scan.
    for evidence in model["evidence"]:
        path, _, number = evidence["reference"].rpartition(":")
        line = int(number) if number.isdigit() else 1
        text = scan.texts.get(path, "").splitlines()
        evidence.update(
            reference=path,
            line=line,
            excerpt=safe_text(text[line - 1])[:240] if 0 < line <= len(text) else "",
            confidence=0.85,
            kind="static-source",
        )
    return project_model(model, profile), scan

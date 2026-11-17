"""Bounded five-stack source analysis. No execution of repository code or AWS API calls."""

from __future__ import annotations
import ast
from pathlib import Path, PurePosixPath
import posixpath
import re
import sys
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


JS_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")
# Run on _mask_js output, where comments and string contents are blank, so imports
# quoted in strings or comments never match; the specifier is read back from the
# original text at the same offsets. An import or export declaration may span lines
# (`import {\n a\n} from './x'`); a declaration without `from` stops at its first quote
# or semicolon, so `export const label = 'store'` is not an import.
JS_IMPORT = re.compile(
    r"\bimport\s*['\"]([^'\"\n]*)['\"]"
    r"|\b(?:import|export)\b[^'\";]*?\bfrom\s*['\"]([^'\"\n]*)['\"]"
    r"|\brequire\(\s*['\"]([^'\"\n]*)['\"]\s*\)"
)
JVM_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)", re.M)


# A `/` after one of these (or at the start) begins a regex literal, not a division.
# `<`, `>` and `}` are left out (JSX `</span>`, `<p>/x</p>`, an object literal divided),
# and `++`/`--` end an expression. This is a heuristic, not a JavaScript parser: a regex
# literal after other tokens (`return /'/`) is scanned as code.
REGEX_PRECEDERS = set("(,=:[!&|?{;+-*%~^")


def _mask_js(text: str) -> str:
    """The source with comments and the contents of string, template and regex literals
    replaced by spaces (newlines kept), so offsets and line numbers match the original.
    Template substitutions (`${require('./x')}`) stay code."""
    out, i, n = list(text), 0, len(text)
    stack = []  # "`" template text, "${" substitution, "{" brace inside a substitution
    previous = ""  # last significant code character

    def blank(start, end):
        for k in range(start, min(end, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c, nxt = text[i], text[i + 1 : i + 2]
        if stack and stack[-1] == "`":  # inside template text
            if c == "\\":
                blank(i, i + 2)
                i += 2
            elif c == "`":
                stack.pop()
                previous, i = "`", i + 1
            elif c == "$" and nxt == "{":
                stack.append("${")
                previous, i = "{", i + 2
            else:
                blank(i, i + 1)
                i += 1
        elif c == "/" and nxt == "/":
            end = text.find("\n", i)
            end = n if end < 0 else end
            blank(i, end)
            i = end
        elif c == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            blank(i, end)
            i = end
        elif c == "/" and (not previous or previous in REGEX_PRECEDERS) and not (
            previous in "+-" and text[: i].rstrip().endswith(previous * 2)  # n++ / x
        ):
            j, in_class = i + 1, False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "/" and not in_class:
                    break
                in_class = (in_class or text[j] == "[") and text[j] != "]"
                j += 1
            blank(i + 1, j)
            previous, i = "/", j + 1
        elif c in "'\"":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            blank(i + 1, j)
            previous, i = c, j + 1
        elif c == "`":
            stack.append("`")
            i += 1
        elif c == "{" and stack:
            stack.append("{")
            previous, i = "{", i + 1
        elif c == "}" and stack and stack[-1] in {"{", "${"}:
            stack.pop()  # closing "${" returns to the template text
            previous, i = "}", i + 1
        else:
            if not c.isspace():
                previous = c
            i += 1
    return "".join(out)


def _language(path: str) -> str:
    """Imports resolve only within one language: Python, JavaScript/TypeScript or JVM."""
    suffix = PurePosixPath(path).suffix
    return "js" if suffix in JS_SUFFIXES else "jvm" if suffix in {".java", ".kt"} else suffix


def _module_keys(path: str) -> set[str]:
    """Names a module answers to: `pkg/mod` for pkg/mod.py, plus `pkg` for a Python
    pkg/__init__.py or a JavaScript/TypeScript pkg/index.ts."""
    p = PurePosixPath(path)
    stem = str(p.with_suffix(""))
    keys = {stem}
    package = "/__init__" if p.suffix == ".py" else "/index" if p.suffix in JS_SUFFIXES else None
    if package and stem.endswith(package):
        keys.add(stem[: -len(package)])
    return keys


def _imports(path: str, text: str) -> list[tuple[list[str], bool, int]]:
    """(candidate module stems, exact match only, line) for each import in a source file.

    Python imports are read with `ast` (comments and docstrings are ignored); standard
    library modules are skipped so `import logging` never links to a local logging.py.
    Relative imports resolve against the importing file and match exactly; absolute ones
    may match any source root (`app.models` -> src/app/models.py).
    """
    suffix = PurePosixPath(path).suffix
    folder = PurePosixPath(path).parent
    found = []
    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] not in sys.stdlib_module_names:
                        found.append(([alias.name.replace(".", "/")], False, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").replace(".", "/")
                if node.level == 0:
                    if module.split("/")[0] in sys.stdlib_module_names:
                        continue
                    base, exact = module, False
                else:
                    package = folder
                    for _ in range(node.level - 1):
                        package = package.parent
                    base = posixpath.normpath(posixpath.join(package.as_posix(), module))
                    base, exact = ("" if base == "." else base), True
                for alias in node.names:
                    submodule = posixpath.join(base, alias.name) if base else alias.name
                    found.append(([submodule, base] if base else [submodule], exact, node.lineno))
    elif suffix in JS_SUFFIXES:
        # Blank comments out but keep their newlines, so line numbers stay true.
        code = _mask_js(text)
        for match in JS_IMPORT.finditer(code):
            group = next(i for i, value in enumerate(match.groups(), 1) if value is not None)
            specifier = text[match.start(group) : match.end(group)]
            if not specifier.strip():
                continue
            line = code.count("\n", 0, match.start(group)) + 1  # the line naming the module
            relative = specifier.startswith(".")
            if relative:
                specifier = posixpath.normpath(posixpath.join(folder.as_posix(), specifier))
            stem = specifier[: -len(PurePosixPath(specifier).suffix)] if (
                PurePosixPath(specifier).suffix in JS_SUFFIXES
            ) else specifier
            found.append(([stem.lstrip("/")], relative, line))
    elif suffix in {".java", ".kt"}:
        for match in JVM_IMPORT.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            name = match.group(1).replace(".", "/")
            found.append(([name], False, line))
    return sorted(found, key=lambda item: item[2])


def _declarations(text: str, suffix: str) -> list[dict]:
    """Declarations of one source file; raises SyntaxError when Python does not parse."""
    result = []
    if suffix == ".py":
        tree = ast.parse(text)
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
        from .inventory import LANGUAGES, _name
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
                name = _name(node)
                if not name:
                    continue
                parameters = node.child_by_field_name("parameters")
                if parameters is None:  # Kotlin has no `parameters` field
                    parameters = next(
                        (
                            n
                            for n in node.named_children
                            if n.type == "function_value_parameters"
                        ),
                        None,
                    )
                scopes = []
                ancestor = node.parent
                while ancestor:
                    if ancestor.type in {
                        "class_declaration",
                        "class_definition",
                        "interface_declaration",
                        "object_declaration",
                    }:
                        scope_name = _name(ancestor)
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
            "status": "inferred",
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
                "status": "inferred",
                "code": [],
            }
            # Parse the original text (redaction can break syntax); redact what is recorded.
            try:
                declarations = _declarations(
                    getattr(text, "source", text), PurePosixPath(path).suffix
                )
            except SyntaxError as exc:
                plan["gaps"].append(
                    f"{path}:{exc.lineno or 1}: Python syntax error; declarations not inventoried."
                )
                declarations = []
            for declaration in declarations:
                declared = safe_text(declaration["name"])
                component["code"].append(
                    {
                        "name": f"{component_name} {declared}",
                        "description": f"Declared {declaration['kind']} {declared}",
                        "kind": declaration["kind"],
                        "members": [safe_text(m) for m in declaration["members"]],
                        "evidence": f"{path}:{declaration['line']}",
                        # The declaration itself was read from source.
                        "status": "observed",
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
    keys = {p: _module_keys(p) for p in modules}
    for path, component_name in modules.items():
        text = files[path]
        linked = set()
        language = _language(path)
        for stems, exact, line in _imports(path, getattr(text, "source", text)):
            for stem in stems:
                candidates = [
                    p
                    for p, names in keys.items()
                    if _language(p) == language
                    and (
                        stem in names
                        or not exact and any(k.endswith("/" + stem) for k in names)
                    )
                ]
                if candidates:
                    break
            if len(candidates) != 1 or candidates[0] == path or candidates[0] in linked:
                continue
            linked.add(candidates[0])
            plan["flows"].append(
                {
                    "from": component_name,
                    "to": modules[candidates[0]],
                    "description": "Imports source module",
                    "technology": "static dependency",
                    "evidence": f"{path}:{line}",
                    "status": "inferred",
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
                        "status": "inferred",
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

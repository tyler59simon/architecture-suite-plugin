"""Language-aware static inventory, without compiler or repository execution."""

import ast
import re
from pathlib import PurePosixPath
from tree_sitter_language_pack import get_parser

LANGUAGES = {
    ".cs": "csharp",
    ".java": "java",
    ".kt": "kotlin",
    ".go": "go",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


def dependency_inventory(files):
    declarations, references, routes, findings = [], [], [], []
    for path, text in sorted(files.items()):
        suffix = PurePosixPath(path).suffix
        if suffix != ".py" and suffix not in LANGUAGES:
            continue
        if suffix == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                findings.append({"reference": path, "message": "Python syntax error"})
                continue
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    declarations.append(
                        {
                            "id": path + ":" + str(node.lineno) + ":" + node.name,
                            "name": node.name,
                            "kind": type(node).__name__,
                            "reference": path,
                            "line": node.lineno,
                            "confidence": 1.0,
                        }
                    )
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for name in (
                        [node.module]
                        if isinstance(node, ast.ImportFrom)
                        else [n.name for n in node.names]
                    ):
                        references.append(
                            {
                                "reference": path,
                                "line": node.lineno,
                                "target": name or "relative import",
                                "kind": "import",
                                "confidence": 1.0,
                            }
                        )
        else:
            root = get_parser(LANGUAGES[suffix]).parse(text.encode()).root_node
            if root.has_error:
                findings.append(
                    {
                        "reference": path,
                        "message": "Parser recovery used; unresolved syntax present",
                    }
                )
            stack = [root]
            while stack:
                node = stack.pop()
                stack.extend(reversed(node.children))
                if node.type in {
                    "class_declaration",
                    "interface_declaration",
                    "function_declaration",
                    "method_declaration",
                    "function_definition",
                    "class_definition",
                    "function_item",
                }:
                    name = node.child_by_field_name("name")
                    if name:
                        declarations.append(
                            {
                                "id": path
                                + ":"
                                + str(node.start_point[0] + 1)
                                + ":"
                                + name.text.decode(),
                                "name": name.text.decode(),
                                "kind": node.type,
                                "reference": path,
                                "line": node.start_point[0] + 1,
                                "confidence": 1.0,
                            }
                        )
                if node.type in {
                    "import_declaration",
                    "import_statement",
                    "import_from_statement",
                    "using_directive",
                    "import_spec",
                }:
                    references.append(
                        {
                            "reference": path,
                            "line": node.start_point[0] + 1,
                            "target": node.text.decode(),
                            "kind": "import",
                            "confidence": 1.0,
                        }
                    )
                if node.type in {"call_expression", "invocation_expression"}:
                    references.append(
                        {
                            "reference": path,
                            "line": node.start_point[0] + 1,
                            "target": node.text.decode()[:240],
                            "kind": "unresolved-call",
                            "confidence": 0.4,
                        }
                    )
        patterns = [
            # A server registration: a router-like receiver and a path. Client calls such as
            # client.get("https://...") or dict.get("key") are not routes (URLs are
            # recorded under connections).
            r"(?<![\w.])(?i:\w*(?:app|router|api|server|bp|blueprint|routes?))"
            r"\.(?:get|post|put|delete|patch)\(\s*[\"\'](/[^\"\']*)",
            r'\[Http(?:Get|Post|Put|Delete)\(\s*"([^"]+)"',
            r'@(?:Get|Post|Request)Mapping\(\s*"([^"]+)"',
            r'http\.HandleFunc\(\s*"([^"]+)"',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                routes.append(
                    {
                        "path": match[1],
                        "reference": path,
                        "line": text.count("\n", 0, match.start()) + 1,
                        "kind": "explicit-route",
                        "confidence": 0.8,
                    }
                )
    for ref in references:
        if ref["kind"] != "import":
            continue
        candidates = [
            p
            for p in files
            if p != ref["reference"]
            and PurePosixPath(p).stem in re.findall(r"[A-Za-z_]\w*", ref["target"])
        ]
        if len(candidates) == 1:
            ref["resolved_file"] = candidates[0]
        else:
            ref["unresolved"] = True
    connections = []
    for path, text in files.items():
        for match in re.finditer(
            r'(?:https?://[^\s"\x27<>]+|(?:postgres|mysql|mongodb|amqp|redis)://[^\s"\x27<>]+)',
            text,
        ):
            connections.append(
                {
                    "reference": path,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "target": match[0],
                    "kind": "configuration-address",
                    "confidence": 0.6,
                    "unresolved": True,
                }
            )
    return {
        "schema_version": "architecture-inventory/v1",
        "declarations": declarations,
        "references": references,
        "routes": routes,
        "connections": connections,
        "findings": findings,
    }

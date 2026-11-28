"""Language-aware static inventory, without compiler or repository execution."""

import ast
import re
from pathlib import PurePosixPath
from tree_sitter_language_pack import get_parser
from .safety import URI_SCHEMES, redact, redact_lines

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


def _name(node):
    """A declaration's name node; the Kotlin grammar has no `name` field."""
    name = node.child_by_field_name("name")
    if name is None:
        name = next(
            (
                n
                for n in node.named_children
                if n.type in {"simple_identifier", "type_identifier", "identifier"}
            ),
            None,
        )
    return name


_VERBS = "Get|Post|Put|Delete|Patch"
_JS = {".js", ".jsx", ".ts", ".tsx"}
# (pattern, suffixes it runs on or None for all, scoped). A scoped pattern is an
# annotation that a class-level prefix applies to. A `cls` group marks a
# class-level prefix form; a match without a `path` group value is a bare
# annotation whose path is the prefix.
_ROUTE_PATTERNS = [
    (r'\[(?:Http(?P<verb>' + _VERBS + r')|(?P<cls>Route))\(\s*"(?P<path>[^"]+)"', None, True),
    (r"\[Http(?P<verb>" + _VERBS + r")(?:\(\s*\))?(?=\s*[\],])", {".cs"}, True),
    (r'@(?P<verb>' + _VERBS + r'|Request)Mapping\(\s*"(?P<path>[^"]+)"', None, True),
    (r"@(?P<verb>" + _VERBS + r"|Request)Mapping(?:\(\s*\))?(?![\w(])", {".java", ".kt"}, True),
    # Go ServeMux patterns: "[METHOD ][HOST]/[PATH]".
    (r'\b\w+\.Handle(?:Func)?\(\s*"(?:(?P<verb>[A-Z]+) +)?(?P<path>[^"\s/]*/[^"]*)"', None, False),
    # NestJS method decorators and @Controller prefixes.
    (r"@(?P<verb>" + _VERBS + r")\(\s*(?:(?P<q>['\"`])(?P<path>[^'\"`]*)(?P=q))?\s*\)", _JS, True),
    (r"@(?P<cls>Controller)\(\s*(?:(?P<q>['\"`])(?P<path>[^'\"`]*)(?P=q))?\s*\)", _JS, True),
]


def _join(prefix, path):
    """Join a class or blueprint prefix and a method route as the frameworks do."""
    if not path:
        return prefix or "/"
    if not prefix:
        return path
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def _class_spans(node, encoded):
    """(start, body start, end) in characters for a class-like Tree-sitter node."""
    body = node.child_by_field_name("body") or next(
        (c for c in node.named_children if c.type == "class_body"), None
    )
    if body is None:
        return None
    # A TypeScript decorator before `export class` belongs to the export statement.
    start = node.parent if node.parent and node.parent.type == "export_statement" else node

    def chars(offset):
        return len(encoded[:offset].decode())

    return chars(start.start_byte), chars(body.start_byte), chars(node.end_byte)


def _file_routes(path, suffix, text, spans, receivers):
    """Route registrations in one file, with class-level prefixes joined."""

    def innermost(pos, header):
        found = [
            i
            for i, (start, body, end) in enumerate(spans)
            if (start <= pos < body if header else body <= pos < end)
        ]
        return max(found, key=lambda i: spans[i][0]) if found else None

    # A server registration: a router-like receiver and a path. Client calls such as
    # client.get("https://...") or dict.get("key") are not routes (URLs are
    # recorded under connections). `verb` is the HTTP method when the registration
    # names one (route, Route, RequestMapping and Go handlers do not).
    generic = (
        r"(?<![\w.])(?P<recv>"
        + "|".join([r"(?i:\w*(?:app|router|api|server|bp|blueprint|routes?))"] + receivers)
        + r")\.(?P<verb>get|post|put|delete|patch|route)\(\s*[\"\'](?P<path>/[^\"\']*)"
    )
    prefixes, candidates = {}, []
    for pattern, suffixes, scoped in [(generic, None, False)] + _ROUTE_PATTERNS:
        if suffixes and suffix not in suffixes:
            continue
        for match in re.finditer(pattern, text):
            groups = match.groupdict()
            verb = (groups.get("verb") or "").upper()
            item = {
                "pos": match.start(),
                "verb": verb,
                "path": groups.get("path"),
                "cls": groups.get("cls"),
            }
            if "recv" in groups:
                item["recv"] = groups["recv"]
            if scoped and (item["cls"] or verb == "REQUEST"):
                header = innermost(match.start(), header=True)
                if header is not None:
                    if item["path"] is not None:
                        item["used"] = False
                        prefixes.setdefault(header, []).append(item)
                    continue
                if item["cls"] == "Controller":
                    continue
            item["scoped"] = scoped
            candidates.append(item)
    found = []

    def record(item, route_path):
        found.append(
            {
                "path": route_path,
                "method": item["verb"] if item["verb"] not in {"", "ROUTE", "REQUEST"} else None,
                "reference": path,
                "line": text.count("\n", 0, item["pos"]) + 1,
                "kind": "explicit-route",
                "confidence": 0.8,
                **({"_recv": item["recv"]} if "recv" in item else {}),
            }
        )

    for item in candidates:
        owner = innermost(item["pos"], header=False) if item["scoped"] else None
        own = prefixes.get(owner, [])
        route_path = item["path"]
        if route_path is None:
            # Without a class route a bare C# action uses conventional routing,
            # whose path is not in the file.
            if owner is None or (suffix == ".cs" and not own):
                continue
        elif suffix == ".cs" and route_path.startswith(("/", "~/")):
            route_path, own = route_path.lstrip("~"), []
        for prefix in own or [None]:
            if prefix is not None:
                prefix["used"] = True
            record(item, _join(prefix["path"] if prefix else "", route_path or ""))
    # A class route with no method routes under it is a route of its own.
    for item in (p for group in prefixes.values() for p in group):
        if not item["used"] and item["cls"] != "Controller":
            record(item, item["path"])
    return found


def _blueprint_target(path, arg, blueprints, imports, modules):
    """The one (file, variable) a register_blueprint argument names, or None."""
    if isinstance(arg, ast.Name):
        if arg.id in blueprints.get(path, {}):
            return path, arg.id
        module, var = imports.get(path, {}).get(arg.id, (None, arg.id))
        stem = module.rsplit(".", 1)[-1] if module else None
    elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
        var, name = arg.attr, arg.value.id
        if name in modules.get(path, {}):
            stem = modules[path][name].rsplit(".", 1)[-1]
        else:
            stem = imports.get(path, {}).get(name, (None, name))[1]
    else:
        return None
    candidates = [
        (p, var)
        for p, defined in blueprints.items()
        if var in defined and (stem is None or PurePosixPath(p).stem == stem)
    ]
    return candidates[0] if len(candidates) == 1 else None


def _blueprint_routes(routes, blueprints, imports, modules, registrations):
    """Join Flask blueprint prefixes: a register_blueprint url_prefix overrides
    the Blueprint's own, and one route is recorded per registration."""
    registered = {}
    for path, line, arg, prefix in registrations:
        target = _blueprint_target(path, arg, blueprints, imports, modules)
        if target:
            registered.setdefault(target, []).append((path, line, prefix))
    joined = []
    for route in routes:
        key = (route["reference"], route.pop("_recv", None))
        if key not in registered:
            if key[1] in blueprints.get(key[0], {}):
                route["path"] = _join(blueprints[key[0]][key[1]] or "", route["path"])
            joined.append(route)
            continue
        for path, line, prefix in registered[key]:
            joined.append(
                {
                    **route,
                    "path": _join(prefix, route["path"]),
                    "confidence": 0.6 if path != route["reference"] else 0.8,
                    "prefix_reference": {"reference": path, "line": line},
                }
            )
    return joined


def _string_keyword(call, name):
    return next(
        (
            k.value.value
            for k in call.keywords
            if k.arg == name and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)
        ),
        None,
    )


def dependency_inventory(files):
    declarations, references, routes, findings = [], [], [], []
    blueprints, imports, modules, registrations = {}, {}, {}, []
    for path, text in sorted(files.items()):
        suffix = PurePosixPath(path).suffix
        if suffix != ".py" and suffix not in LANGUAGES:
            continue
        # Parse the original text (redaction can break syntax); redact what is recorded.
        text = getattr(text, "source", text)
        spans = []
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
                    name = redact(node.name)
                    declarations.append(
                        {
                            "id": path + ":" + str(node.lineno) + ":" + name,
                            "name": name,
                            "kind": type(node).__name__,
                            "reference": path,
                            "line": node.lineno,
                            "confidence": 1.0,
                        }
                    )
                if (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Call)
                    and "Blueprint"
                    in {getattr(node.value.func, "id", None), getattr(node.value.func, "attr", None)}
                ):
                    blueprints.setdefault(path, {})[node.targets[0].id] = _string_keyword(
                        node.value, "url_prefix"
                    )
                if (
                    isinstance(node, ast.Call)
                    and getattr(node.func, "attr", None) == "register_blueprint"
                    and node.args
                    and _string_keyword(node, "url_prefix") is not None
                ):
                    registrations.append(
                        (path, node.lineno, node.args[0], _string_keyword(node, "url_prefix"))
                    )
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        imports.setdefault(path, {})[alias.asname or alias.name] = (
                            node.module or "",
                            alias.name,
                        )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        modules.setdefault(path, {})[alias.asname or alias.name] = alias.name
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
                                "target": redact(name or "relative import"),
                                "kind": "import",
                                "confidence": 1.0,
                            }
                        )
        else:
            encoded = text.encode()
            root = get_parser(LANGUAGES[suffix]).parse(encoded).root_node
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
                if node.type in {"class_declaration", "object_declaration"}:
                    span = _class_spans(node, encoded)
                    if span:
                        spans.append(span)
                if node.type in {
                    "class_declaration",
                    "interface_declaration",
                    "function_declaration",
                    "method_declaration",
                    "function_definition",
                    "class_definition",
                    "function_item",
                    "object_declaration",
                }:
                    name = _name(node)
                    if name:
                        name = redact(name.text.decode())
                        declarations.append(
                            {
                                "id": path + ":" + str(node.start_point[0] + 1) + ":" + name,
                                "name": name,
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
                    "import_header",  # Kotlin
                }:
                    references.append(
                        {
                            "reference": path,
                            "line": node.start_point[0] + 1,
                            "target": redact(node.text.decode()),
                            "kind": "import",
                            "confidence": 1.0,
                        }
                    )
                if node.type in {"call_expression", "invocation_expression"}:
                    references.append(
                        {
                            "reference": path,
                            "line": node.start_point[0] + 1,
                            "target": redact(node.text.decode())[:240],
                            "kind": "unresolved-call",
                            "confidence": 0.4,
                        }
                    )
        receivers = [re.escape(name) for name in blueprints.get(path, {})]
        routes.extend(_file_routes(path, suffix, text, spans, receivers))
    routes = _blueprint_routes(routes, blueprints, imports, modules, registrations)
    for route in routes:
        route["path"] = redact(route["path"])
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
        # Scanned text is redacted already; redacting again is a no-op and covers raw input.
        text = redact_lines(text)
        for match in re.finditer(
            rf'(?:{URI_SCHEMES})://[^\s"\x27<>]+',
            text,
        ):
            connections.append(
                {
                    "reference": path,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "target": redact(match[0]),
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

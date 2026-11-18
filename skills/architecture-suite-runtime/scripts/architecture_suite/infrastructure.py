"""Offline import of exported infrastructure. Unresolved values remain findings."""

from pathlib import Path
import json
import re
import yaml
from .plan import _Loader
from .safety import canonical_existing_file, redact
from .model import slugify


def evidence_reference(path) -> str:
    """Path as recorded in evidence: relative to the working directory when inside it, so
    shared artifacts do not expose home-directory layouts; absolute otherwise."""
    path = Path(path)
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)

SENSITIVE, UNKNOWN = "[SENSITIVE]", "[UNKNOWN AFTER APPLY]"


class _InfraLoader(_Loader):
    """Safe loader where CloudFormation short tags (!Ref, !Sub, ...) become inert data."""


def _intrinsic(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        expression = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        expression = loader.construct_sequence(node, deep=True)
    else:
        expression = loader.construct_mapping(node, deep=True)
    return {"intrinsic": suffix, "expression": expression}


_InfraLoader.add_multi_constructor("!", _intrinsic)


def _documents(text: str) -> list:
    """Every non-empty YAML/JSON document; anchors and aliases stay unsupported."""
    if len(text) > 2_000_000:
        raise ValueError("Infrastructure document exceeds 2 MB")
    try:
        for token in yaml.scan(text):
            if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)):
                raise ValueError("YAML anchors and aliases are unsupported")
        # Empty documents (a Helm template that rendered nothing) are skipped.
        return [doc for doc in yaml.load_all(text, Loader=_InfraLoader) if doc is not None]
    except (yaml.YAMLError, RecursionError) as exc:
        raise ValueError(str(exc)[:200]) from exc


def _apply_mask(value, mask, marker, path, hits):
    """Replace what a Terraform sensitivity/unknown mask marks true; record attribute paths.

    Unknown masks also name attributes absent from planned values, so those are added.
    """
    if mask is True:
        hits.append(path or "(resource)")
        return marker
    if isinstance(mask, dict) and isinstance(value, dict):
        result = dict(value)
        for key, sub in mask.items():
            where = f"{path}.{key}" if path else str(key)
            if key in value:
                result[key] = _apply_mask(value[key], sub, marker, where, hits)
            elif marker == UNKNOWN and sub is True:
                result[key] = _apply_mask(None, sub, marker, where, hits)
        return result
    if isinstance(mask, list) and isinstance(value, list):
        return [
            _apply_mask(item, mask[i], marker, f"{path}[{i}]", hits) if i < len(mask) else item
            for i, item in enumerate(value)
        ]
    return value


def _strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


SUB_VARIABLE = re.compile(r"\$\{(?!!)([A-Za-z0-9]+)(?:\.[A-Za-z0-9.]+)?\}")


def _getatt(target, names):
    """CloudFormation GetAtt: `Name.Attr` or `[Name, Attr]` refers to resource Name."""
    name = (
        target.split(".", 1)[0]
        if isinstance(target, str)
        else target[0]
        if isinstance(target, list) and target and isinstance(target[0], str)
        else None
    )
    if name in names:
        yield names[name]


def _sub(target, names):
    """CloudFormation Sub: `${Name}` and `${Name.Attr}` in the template string refer to
    resources; `${!Literal}`, pseudo parameters and the variable map's own keys do not."""
    template, variables = (
        (target, {})
        if isinstance(target, str)
        else (target[0], target[1] if len(target) > 1 and isinstance(target[1], dict) else {})
        if isinstance(target, list) and target and isinstance(target[0], str)
        else ("", {})
    )
    for name in SUB_VARIABLE.findall(template):
        if name in names and name not in variables:
            yield names[name]


TERRAFORM_INDEX = re.compile(r"\[(?:\"[^\"]*\"|[^\]]*)\]")
MODULE_INSTANCE = re.compile(r"^(?:module\.[^.\[]+(?:\[(?:\"[^\"]*\"|[^\]]*)\])?\.)*")
# `aws_subnet.app[0].id` -> `aws_subnet.app[0]`: type, name and instance key, if any.
TERRAFORM_REFERENCE = re.compile(r"([^.\[\]]+)\.([^.\[\]]+)(?:\[(?:\"[^\"]*\"|[^\]]*)\])?")


def _config_address(address: str) -> str:
    """`module.net["prod"].aws_subnet.a[0]` -> `module.net.aws_subnet.a`: the address
    in the configuration, without count or for_each instance keys."""
    return TERRAFORM_INDEX.sub("", address)


def _module_instance(address: str) -> str:
    """`module.net["prod"].aws_subnet.a[0]` -> `module.net["prod"].`; root module: ``."""
    return MODULE_INSTANCE.match(address).group()


def _terraform_references(module, prefix=""):
    """{config address: referenced resource addresses} from a plan's `configuration`.
    A referenced address keeps its instance key (`aws_subnet.app[0]`) when it has one."""
    found = {}

    def collect(value, into):
        if isinstance(value, dict):
            listed = set()
            for ref in value.get("references", []) or []:
                match = TERRAFORM_REFERENCE.match(ref) if isinstance(ref, str) else None
                if match and match.group(1) not in {
                    "var", "local", "data", "module", "each", "count", "path", "self", "terraform"
                }:
                    listed.add(match.group())
            # Terraform lists `aws_subnet.app[0].id`, `aws_subnet.app[0]` and `aws_subnet.app`
            # for one reference: keep the instance, not the whole resource.
            into.update(
                prefix + ref
                for ref in listed
                if not any(other != ref and _config_address(other) == ref for other in listed)
            )
            for child in value.values():
                collect(child, into)
        elif isinstance(value, list):
            for child in value:
                collect(child, into)

    for resource in module.get("resources", []) or []:
        if isinstance(resource, dict) and isinstance(resource.get("address"), str):
            targets = set()
            collect(resource.get("expressions", {}), targets)
            found[prefix + resource["address"]] = targets
    for name, call in (module.get("module_calls") or {}).items():
        if isinstance(call, dict) and isinstance(call.get("module"), dict):
            found.update(_terraform_references(call["module"], f"{prefix}module.{name}."))
    return found


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _ingress_backends(spec):
    """Service names an Ingress routes to (networking.k8s.io/v1 and v1beta1)."""
    backends = [spec.get("defaultBackend"), spec.get("backend")]
    rules = spec.get("rules")
    for rule in rules if isinstance(rules, list) else []:
        paths = _mapping(_mapping(rule).get("http")).get("paths")
        backends += [_mapping(p).get("backend") for p in (paths if isinstance(paths, list) else [])]
    names = []
    for backend in map(_mapping, backends):
        name = _mapping(backend.get("service")).get("name") or backend.get("serviceName")
        if isinstance(name, str) and name not in names:
            names.append(name)
    return names


def _kubernetes_edges(resources, kubernetes, edges, findings):
    """Service selectors to Pods and workload templates, and Ingress backends to Services."""
    services = {
        (r["parent_id"], kubernetes[r["id"]][0]): r["id"]
        for r in resources
        if r["type"] == "kubernetes/Service" and r["id"] in kubernetes
    }

    def edge(resource, target, kind):
        edges.append(
            {
                "source_id": resource["id"],
                "destination_id": target,
                "kind": kind,
                "evidence": resource["evidence"],
            }
        )

    for resource in resources:
        props = resource["properties"]
        if resource["type"] == "kubernetes/Service":
            selector = _mapping(props.get("selector"))
            matched = []
            for target in resources:
                if (
                    target["id"] == resource["id"]
                    or not target["type"].startswith("kubernetes/")
                    or target["parent_id"] != resource["parent_id"]
                ):
                    continue
                # A Pod carries its own labels; a workload labels the Pods of its template.
                labels = (
                    kubernetes.get(target["id"], ("", {}))[1]
                    if target["type"] == "kubernetes/Pod"
                    else _mapping(
                        _mapping(_mapping(target["properties"].get("template")).get("metadata")).get(
                            "labels"
                        )
                    )
                )
                if selector and all(labels.get(k) == v for k, v in selector.items()):
                    edge(resource, target["id"], "selector")
                    matched.append(target["id"])
            text = ", ".join(f"{k}={v}" for k, v in selector.items())
            findings.append(
                {
                    "resource": resource["id"],
                    "message": "Service has no selector; its endpoints are managed elsewhere"
                    if not selector
                    else f"Service selector {text} matched: " + ", ".join(matched)
                    if matched
                    else f"Service selector {text} matched no workload in namespace "
                    + str(resource["parent_id"]),
                }
            )
        if resource["type"] == "kubernetes/Ingress":
            missing = []
            for backend in _ingress_backends(props):
                target = services.get((resource["parent_id"], backend))
                if target:
                    edge(resource, target, "ingress-backend")
                else:
                    missing.append(backend)
            if missing:
                findings.append(
                    {
                        "resource": resource["id"],
                        "message": "Ingress backends are not declared Services: "
                        + ", ".join(missing),
                    }
                )


# Keys whose values import_infrastructure reads as reference targets; kept when masking.
REFERENCE_KEYS = {"Ref", "Fn::GetAtt", "DependsOn", "depends_on", "depends_on_resource"}


def _reference_operand(value):
    """A reference target: a resource name, or a list of names and attributes."""
    return isinstance(value, str) or (
        isinstance(value, list) and all(isinstance(v, str) for v in value)
    )


def _masked(value):
    """A value under a sensitive name: every literal is redacted, references stay."""
    if isinstance(value, dict):
        if set(value) == {"intrinsic", "expression"} and isinstance(value["intrinsic"], str):
            # YAML short forms, exactly as _intrinsic builds them
            if value["intrinsic"] in {"Ref", "GetAtt"} and _reference_operand(value["expression"]):
                return value
            if value["intrinsic"] == "Sub":
                return {**value, "expression": _sub_masked(value["expression"])}
        return {
            k: v
            if k in REFERENCE_KEYS and _reference_operand(v)
            else _sub_masked(v)
            if k == "Fn::Sub"
            else _masked(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_masked(v) for v in value]
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return "[REDACTED]"
    return value


def _sub_masked(target):
    """Fn::Sub without its literal text: only the `${Name}` references remain."""
    if isinstance(target, str):
        return "".join(m[0] for m in SUB_VARIABLE.finditer(target))
    if isinstance(target, list) and target:
        return [_sub_masked(target[0])] + [_masked(v) for v in target[1:]]
    return _masked(target)


def import_infrastructure(paths, bindings=None):
    resources, edges, findings = [], [], []
    bindings = bindings or {}
    kubernetes = {}  # resource id -> (metadata name, metadata labels)

    def add(ident, kind, properties, source, parent=None):
        if any(r["id"] == ident for r in resources):
            raise ValueError("Duplicate infrastructure resource: " + ident)
        resources.append(
            {
                "id": ident,
                "type": kind,
                "properties": properties,
                "evidence": source,
                "parent_id": parent,
            }
        )

    for file_index, path in enumerate(paths):
        path = canonical_existing_file(Path(path), "--input")
        text = path.read_text(encoding="utf-8-sig")  # tolerate a BOM
        prefix = f"input-{file_index}-"
        declared = {}  # name -> id across this file's documents

        def sensitive(key):
            return re.search(r"password|secret|token|api.?key", str(key), re.I)

        def scrub(value):
            if isinstance(value, dict):
                # A Kubernetes env entry names the secret in `name` and holds it in `value`;
                # an expression there keeps its references (edges) but no literal text.
                named = "value" in value and sensitive(value.get("name", ""))
                return {
                    # Booleans are kept: they carry Terraform sensitivity masks, not secrets.
                    k: "[REDACTED]"
                    if sensitive(k) and not isinstance(v, bool)
                    else _masked(v)
                    if named and k == "value"
                    else scrub(v)
                    for k, v in value.items()
                }
            if isinstance(value, list):
                return [scrub(v) for v in value]
            if isinstance(value, str):
                # Compose list form `KEY=value`: redact misses values under 4 characters.
                # A key with URL characters (`redis://h/0?token=x`) is not an assignment.
                pair = re.fullmatch(r"([^\s=/:?#@]+)=(.+)", value, re.S)
                if pair and sensitive(pair[1]):
                    return pair[1] + "=[REDACTED]"
                return redact(value)
            return value

        try:
            # CloudFormation short tags are converted to data, never evaluated.
            docs = [scrub(doc) for doc in _documents(text)]
        except ValueError as exc:
            raise ValueError("Malformed infrastructure document") from exc
        for doc_index, doc in enumerate(docs):
            if not isinstance(doc, dict):
                raise ValueError("Infrastructure document must be a mapping")
            source = {"reference": evidence_reference(path), "document": doc_index + 1}
            entries, depends, terraform_refs, metadata = [], {}, {}, {}
            if "planned_values" in doc:
                configuration = doc.get("configuration")
                if isinstance(configuration, dict):
                    terraform_refs = _terraform_references(
                        configuration.get("root_module") or {}
                    )
                changes = {
                    c.get("address"): c.get("change") or {}
                    for c in doc.get("resource_changes") or []
                    if isinstance(c, dict)
                }

                def walk(module):
                    for resource in module.get("resources", []):
                        address = resource["address"]
                        change = changes.get(address, {})
                        values, hidden, unknown = resource.get("values", {}), [], []
                        for mask in (resource.get("sensitive_values"), change.get("after_sensitive")):
                            values = _apply_mask(values, mask, SENSITIVE, "", hidden)
                        values = _apply_mask(
                            values, change.get("after_unknown"), UNKNOWN, "", unknown
                        )
                        ident = prefix + slugify(address)
                        if hidden:
                            findings.append(
                                {
                                    "resource": ident,
                                    "message": "Sensitive values masked: "
                                    + ", ".join(sorted(set(hidden))),
                                }
                            )
                        if unknown:
                            findings.append(
                                {
                                    "resource": ident,
                                    "message": "Values unknown until apply: "
                                    + ", ".join(sorted(set(unknown))),
                                }
                            )
                        entries.append((address, resource["type"], values, None))
                    for child in module.get("child_modules", []):
                        walk(child)

                walk(doc["planned_values"].get("root_module", {}))
                if doc.get("resource_changes"):
                    findings.append(
                        {
                            "source": source,
                            "message": "Terraform unknown/sensitive values are not evaluated; review change metadata",
                        }
                    )
            elif "Resources" in doc:
                for name, value in doc["Resources"].items():
                    # Resource-level DependsOn sits beside Properties: deployment ordering.
                    order = value.get("DependsOn", [])
                    depends[name] = [order] if isinstance(order, str) else order
                    entries.append(
                        (
                            name,
                            value.get("Type", "unknown"),
                            value.get("Properties", {}),
                            None,
                        )
                    )
            elif "apiVersion" in doc and "kind" in doc:
                items = (doc.get("items") or []) if doc["kind"] == "List" else [doc]
                for item in items:
                    if not isinstance(item, dict):
                        findings.append(
                            {"source": source, "message": "Kubernetes item is not a mapping; skipped"}
                        )
                        continue
                    # null metadata, spec or labels read as empty, never as an error.
                    meta = _mapping(item.get("metadata"))
                    namespace = meta.get("namespace", "default")
                    entry = namespace + "/" + item["kind"] + "/" + meta.get("name", "unnamed")
                    metadata[entry] = (meta.get("name", "unnamed"), _mapping(meta.get("labels")))
                    entries.append(
                        (entry, "kubernetes/" + item["kind"], _mapping(item.get("spec")), namespace)
                    )
            elif "services" in doc:
                for section in ("networks", "volumes"):
                    for name, value in (doc.get(section) or {}).items():
                        entries.append(
                            (
                                section + "/" + name,
                                "compose/" + section.rstrip("s"),
                                value or {},
                                "compose",
                            )
                        )
                for name, value in doc["services"].items():
                    entries.append((name, "compose/service", value or {}, "compose"))
            else:
                raise ValueError(
                    "Expected Terraform plan, CloudFormation/CDK template, Kubernetes/rendered Helm or Compose"
                )
            names = {}
            taken = {r["id"] for r in resources}
            for name, _, _, _ in entries:
                if name in names or name in declared:
                    # A repeated declaration keeps its ID and fails as a duplicate below.
                    names.setdefault(name, declared.get(name))
                    continue
                # Distinct names may share a slug (app.config, app-config): number them.
                ident = base = prefix + slugify(name)
                suffix = 2
                while ident in taken:
                    ident, suffix = f"{base}-{suffix}", suffix + 1
                names[name] = declared[name] = ident
                taken.add(ident)
            for name, kind, props, parent in entries:
                ident = names[name]
                add(ident, kind, props, source, parent)
                if name in metadata:
                    kubernetes[ident] = metadata[name]
                serialized = json.dumps(props)
                if (
                    "${" in serialized
                    or '"Ref"' in serialized
                    or '"Fn::' in serialized
                    or '"intrinsic"' in serialized
                ):
                    findings.append(
                        {
                            "resource": ident,
                            "message": "Contains unresolved expression; no values or placement guessed",
                        }
                    )

                def refs(value):
                    if isinstance(value, dict):
                        # YAML short forms (`!Ref Name`, `!GetAtt Name.Attr`, `!Sub "${Name}"`),
                        # as data from _InfraLoader.
                        function, target = value.get("intrinsic"), value.get("expression")
                        if function == "Ref" and isinstance(target, str) and target in names:
                            yield names[target]
                        if function == "GetAtt":
                            yield from _getatt(target, names)
                        if function == "Sub":
                            yield from _sub(target, names)
                        for k, v in value.items():
                            if k in ref_keys:
                                for item in v if isinstance(v, list) else [v]:
                                    if isinstance(item, str) and item in names:
                                        yield names[item]
                            if k == "Fn::GetAtt":
                                yield from _getatt(v, names)
                            if k == "Fn::Sub":
                                yield from _sub(v, names)
                            yield from refs(v)
                    elif isinstance(value, list):
                        for item in value:
                            yield from refs(item)

                # Compose depends_on is a depends-on relationship below, not a reference.
                ref_keys = {"Ref", "DependsOn", "depends_on", "depends_on_resource"} - (
                    {"depends_on"} if kind == "compose/service" else set()
                )
                # Terraform: references recorded in the plan's configuration section
                # (`bucket = aws_s3_bucket.logs.id`), mapped to the planned instances in
                # the same module instance (a reference never leaves its module). An
                # indexed reference names one instance; an unindexed one that fits
                # several count or for_each instances is a finding, not an edge to each.
                module = _module_instance(name)
                configured = set()
                for ref in sorted(terraform_refs.get(_config_address(name), ())):
                    targets = [
                        other
                        for other in names
                        if ref in {_config_address(other), _config_address(module) + other[len(module):]}
                        and _module_instance(other) == module
                        and other != name
                    ]
                    if len(targets) > 1:
                        findings.append(
                            {
                                "resource": ident,
                                "message": f"Unindexed reference to {ref} fits {len(targets)} "
                                "instances; no edge guessed",
                            }
                        )
                    else:
                        configured.update(names[other] for other in targets)
                for target in sorted(set(refs(props)) | configured):
                    edges.append(
                        {
                            "source_id": ident,
                            "destination_id": target,
                            "kind": "explicit-reference",
                            "evidence": source,
                        }
                    )
                for dep in depends.get(name, []):
                    if isinstance(dep, str) and dep in names:
                        edges.append(
                            {
                                "source_id": ident,
                                "destination_id": names[dep],
                                "kind": "depends-on",
                                "evidence": source,
                            }
                        )
                if kind == "compose/service":
                    dependencies = props.get("depends_on", [])
                    missing = [
                        d for d in dependencies if d not in names
                    ] + [
                        "networks/" + n
                        for n in props.get("networks", [])
                        if n != "default" and "networks/" + n not in names
                    ]
                    if missing:
                        findings.append(
                            {
                                "resource": ident,
                                "message": "Refers to undeclared services or networks: "
                                + ", ".join(sorted(map(str, missing))),
                            }
                        )
                    for dep in dependencies:
                        if dep in names:
                            edges.append(
                                {
                                    "source_id": ident,
                                    "destination_id": names[dep],
                                    "kind": "depends-on",
                                    "evidence": source,
                                }
                            )
                    for network in props.get("networks", []):
                        if "networks/" + network in names:
                            edges.append(
                                {
                                    "source_id": ident,
                                    "destination_id": names["networks/" + network],
                                    "kind": "network-membership",
                                    "evidence": source,
                                }
                            )
    resource_ids = {r["id"] for r in resources}
    # A Terraform ID that several resources share (a bucket and its versioning both use
    # the bucket name) identifies none of them.
    terraform_ids = [
        r["properties"].get("id")
        for r in resources
        if r["type"].startswith(("aws_", "google_")) and isinstance(r["properties"], dict)
    ]
    shared_ids = {v for v in terraform_ids if terraform_ids.count(v) > 1}
    linked = {(e["source_id"], e["destination_id"]) for e in edges}
    for resource in resources:
        props = resource["properties"]
        # Exact values only: "vpc-1" must not match "vpc-123" or free text containing it.
        # Tags and labels are free text, not references.
        scalars = set(
            _strings(
                {k: v for k, v in props.items() if k not in {"tags", "tags_all", "labels"}}
                if isinstance(props, dict)
                else props
            )
        )
        for target in resources:
            if resource["id"] == target["id"]:
                continue
            if resource["type"].startswith(("aws_", "google_")):
                # Terraform resolved IDs are matched only against declared resource IDs.
                value = target["properties"].get("id")
                # A masked or unknown ID is a shared placeholder, not an identity.
                if (
                    isinstance(value, str)
                    and value
                    and value not in {SENSITIVE, UNKNOWN}
                    and value not in shared_ids
                    and "[REDACTED]" not in value
                    and value in scalars
                    and (resource["id"], target["id"]) not in linked
                ):
                    edges.append(
                        {
                            "source_id": resource["id"],
                            "destination_id": target["id"],
                            "kind": "resolved-resource-id",
                            "evidence": resource["evidence"],
                        }
                    )
    _kubernetes_edges(resources, kubernetes, edges, findings)
    if set(bindings) - resource_ids:
        raise ValueError("Binding refers to unknown resource")
    by_id = {r["id"]: r for r in resources}
    for edge in edges:
        child, parent = by_id[edge["source_id"]], by_id[edge["destination_id"]]
        if child["type"] in {
            "aws_subnet",
            "AWS::EC2::Subnet",
            "google_compute_subnetwork",
        } and parent["type"] in {
            "aws_vpc",
            "AWS::EC2::VPC",
            "google_compute_network",
        }:
            child["parent_id"] = parent["id"]
    return {
        "schema_version": "architecture-topology/v1",
        "resources": resources,
        "relationships": edges,
        "bindings": bindings,
        "findings": findings,
    }


def topology_plan(topology):
    return {
        "schema_version": "architecture-plan/v1",
        "system": {
            "name": "Imported Infrastructure",
            "description": "Reviewable infrastructure candidates",
            "classification": "Internal",
            "scope": "Imported declarations; ownership requires review",
        },
        "containers": [
            {
                "name": r["id"],
                "description": r["type"],
                "technology": r["type"],
                "evidence": r["evidence"]["reference"],
                "status": "inferred",
            }
            for r in topology["resources"]
        ],
        "flows": [
            {
                "from": e["source_id"],
                "to": e["destination_id"],
                "description": e["kind"],
                "evidence": e["evidence"]["reference"],
                "status": "inferred",
            }
            for e in topology["relationships"]
        ],
        "assumptions": [],
        "gaps": [f.get("message", "") for f in topology["findings"]],
    }

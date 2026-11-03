"""Record test results, separate line/branch coverage, and public-callable execution."""

import ast
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    coverage = json.loads((ROOT / "test-results/coverage.json").read_text())
    totals = coverage["totals"]
    line = totals["covered_lines"] / totals["num_statements"] * 100
    branch = totals["covered_branches"] / totals["num_branches"] * 100
    suites = ET.parse(ROOT / "test-results/junit.xml").getroot().findall("testsuite")
    results = {
        "tests": sum(int(s.get("tests", 0)) for s in suites),
        "failures": sum(int(s.get("failures", 0)) for s in suites),
        "errors": sum(int(s.get("errors", 0)) for s in suites),
        "skipped": sum(int(s.get("skipped", 0)) for s in suites),
        "seconds": sum(float(s.get("time", 0)) for s in suites),
        "line_coverage_percent": round(line, 2),
        "branch_coverage_percent": round(branch, 2),
        "covered_lines": totals["covered_lines"],
        "statements": totals["num_statements"],
        "covered_branches": totals["covered_branches"],
        "branches": totals["num_branches"],
    }
    functions = []
    uncovered_lines = {}
    for name, data in coverage["files"].items():
        path = ROOT / name.replace("\\", "/")
        covered = set(data["executed_lines"])
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def inspect(node, prefix=""):
            for member in node.body:
                if isinstance(
                    member, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and not member.name.startswith("_"):
                    functions.append(
                        {
                            "module": path.name,
                            "function": prefix + member.name,
                            "executed": bool(
                                covered.intersection(
                                    range(member.body[0].lineno, member.end_lineno + 1)
                                )
                            ),
                        }
                    )
                elif isinstance(member, ast.ClassDef) and not member.name.startswith(
                    "_"
                ):
                    inspect(member, member.name + ".")

        inspect(tree)
        if data["missing_lines"]:
            uncovered_lines[path.name] = data["missing_lines"]
    results["public_callables"] = len(functions)
    results["unexecuted_public_callables"] = [f for f in functions if not f["executed"]]
    results["thresholds_met"] = line >= 90 and branch >= 85
    results["instruction_evaluation"] = (
        "claude plugin eval suite in evals/ (trigger, negative, safety, e2e); not part of coverage"
    )
    problems = []
    if results["failures"] or results["errors"]:
        problems.append(f"{results['failures']} failures, {results['errors']} errors")
    if not results["thresholds_met"]:
        problems.append(f"coverage {line:.2f}% lines / {branch:.2f}% branches (need 90 / 85)")
    for f in results["unexecuted_public_callables"]:
        problems.append(f"public callable never executed by a test: {f['module']}:{f['function']}")
    if problems:
        separator = chr(10) + "  "
        raise SystemExit("Validation gate failed:" + separator + separator.join(problems))
    (ROOT / "reports/validation-results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    (ROOT / "reports/public-coverage.json").write_text(
        json.dumps(
            {"callables": functions, "uncovered_lines": uncovered_lines}, indent=2
        ),
        encoding="utf-8",
    )
    shutil.copyfile(
        ROOT / "test-results/coverage.json", ROOT / "reports/coverage.json"
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

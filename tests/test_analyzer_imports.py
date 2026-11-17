"""Static import flows: real imports only, resolved like the language does."""

from architecture_suite.analyzer import draft_plan
from architecture_suite.safety import scan_repository

FILES = {
    "pyproject.toml": "",
    "app/__init__.py": "",
    "app/main.py": (
        '"""Reads rows from storage."""\n'
        "import logging\n"
        "from .models import Order\n"
        "from app import service\n"
        "# data comes from cache first\n"
        "def run():\n"
        "    return Order, service, logging\n"
    ),
    "app/models.py": "class Order:\n    pass\n",
    "app/service.py": "def call():\n    return 1\n",
    "app/storage.py": "ROWS = []\n",
    "app/cache.py": "HITS = {}\n",
    "app/logging.py": "def log():\n    pass\n",
    "web/package.json": "{}",
    "web/src/app.ts": (
        "import { render } from './view.js'\n"
        "import {\n  a,\n  b,\n} from './multi'\n"
        "const util = require('./util')\n"
        "// import cache from './cache'\n"
        "export const label = 'store'\n"
        "export { helper } from './helpers/index'\n"
    ),
    "web/src/view.js": "export function render() {}\n",
    "web/src/multi.ts": "export const a = 1, b = 2\n",
    "web/src/util.js": "module.exports = {}\n",
    "web/src/cache.ts": "export default {}\n",
    "web/src/store.ts": "export default {}\n",
    "web/src/helpers/index.ts": "export const helper = 1\n",
    "web/src/other.ts": (
        "import def\n"
        "  from './utils2'\n"
        "const a = require('./a'), b = require('./b');\n"
        "/* import gone from './gone' */\n"
        "const url = 'http://example.com/x'\n"
    ),
    "web/src/utils2.ts": "export default 1\n",
    "web/src/a.js": "module.exports = 1\n",
    "web/src/b.js": "module.exports = 2\n",
    "web/src/gone.ts": "export default 1\n",
    # Comment markers and import text inside string literals are not code.
    "web/src/strings.ts": (
        'const include = "src/**";\n'
        "import real from './real';\n"
        'const exclude = "**/*.test.ts";\n'
        "const example = \"import { helper } from './helper'\";\n"
        "const label = \"ok\"// import helper from './helper'\n"
        "const path = `${base}/import x from './helper'`\n"
    ),
    "web/src/real.ts": "export default 1\n",
    "web/src/helper.ts": "export default 1\n",
    # A Python namespace folder: index.py is not the package, so `import helpers` stays unlinked.
    "app/jobs.py": "import helpers\n",
    "app/helpers/index.py": "X = 1\n",
}


def test_import_flows_follow_real_imports(tmp_path):
    for path, text in FILES.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    plan = draft_plan(tmp_path, scan_repository(tmp_path), "Internal")
    flows = {
        (f["evidence"], f["to"].rsplit(" ", 1)[-1])
        for f in plan["flows"]
        if f["description"] == "Imports source module"
    }
    assert flows == {
        ("app/main.py:3", "app/models.py"),
        ("app/main.py:4", "app/service.py"),
        ("web/src/app.ts:1", "web/src/view.js"),
        ("web/src/app.ts:5", "web/src/multi.ts"),  # the "} from" line
        ("web/src/app.ts:6", "web/src/util.js"),
        ("web/src/app.ts:9", "web/src/helpers/index.ts"),
        ("web/src/other.ts:2", "web/src/utils2.ts"),  # declaration over two lines
        ("web/src/other.ts:3", "web/src/a.js"),
        ("web/src/other.ts:3", "web/src/b.js"),  # second require on the same line
        ("web/src/strings.ts:2", "web/src/real.ts"),
    }

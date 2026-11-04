"""Build local distributable archives and the release-branch plugin tree; never publish them.

    python tools/package_hosts.py

Writes dist/hosts/<host>.zip and dist/plugin/ (the slim marketplace + plugin that the
release workflow pushes to `architecture-suite-<version>` and `latest`).
"""

from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "skills/architecture-suite-runtime/scripts"))
from architecture_suite.distribution import package_hosts, write_plugin_tree  # noqa: E402

output = root / "dist/hosts"
output.mkdir(parents=True, exist_ok=True)
package_hosts(root / "skills", output)
write_plugin_tree(root / "skills", root / "dist/plugin")
print(output)
print(root / "dist/plugin")

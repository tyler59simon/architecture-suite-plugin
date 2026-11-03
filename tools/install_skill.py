"""Install all nine C4 skills plus the shared runtime into one or more agent hosts.

    python tools/install_skill.py --host codex|claude|copilot|factory|all --scope user|project [--project DIR] [--confirm-overwrite]

Skills and the shared `architecture-suite-runtime` folder are installed as siblings.
No agent configuration is edited. Set up dependencies afterwards with
`python <skills-dir>/architecture-suite-runtime/scripts/bootstrap.py`.
"""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
sys.path.insert(0, str(SKILLS / "architecture-suite-runtime/scripts"))

from architecture_suite.distribution import HOSTS, install_host, skill_names  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", choices=[*HOSTS, "all"], default="codex")
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--home", type=Path, help="override home for user scope (testing)")
    parser.add_argument("--confirm-overwrite", action="store_true")
    args = parser.parse_args(argv)
    for host in HOSTS if args.host == "all" else [args.host]:
        target = install_host(
            SKILLS, host, args.scope, args.project, home=args.home,
            overwrite=args.confirm_overwrite,
        )
        print(f"{host}: installed {len(skill_names(SKILLS))} skills + runtime into {target}")


if __name__ == "__main__":
    main()

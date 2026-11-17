"""Keep examples/ free of duplicate files: drop a file when its counterpart already exists.

The sample generators render a variant (a second cloud, a second system, an icon style) in full,
then call drop_identical so only the files that differ from the reference are kept.
"""

import hashlib
from pathlib import Path


def drop_identical(reference, target):
    """Delete files under `target` that are byte-identical to the same path under `reference`.

    Dotfiles (output ownership manifests) are left alone. Returns the removed paths, relative to
    `target`, and prunes folders that become empty.
    """
    reference, target = Path(reference), Path(target)
    removed = []
    for path in sorted(target.rglob("*")):
        relative = path.relative_to(target)
        if not path.is_file() or any(part.startswith(".") for part in relative.parts):
            continue
        twin = reference / relative
        if twin.is_file() and _digest(twin) == _digest(path):
            path.unlink()
            removed.append(relative.as_posix())
    for folder in sorted((p for p in target.rglob("*") if p.is_dir()), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    return removed


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

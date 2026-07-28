"""Code provenance for a run's manifest: git commit and dirty flag."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_provenance(repo_dir: str | Path) -> dict[str, str | bool | None]:
    """Return ``{"commit": <sha or None>, "dirty": <bool or None>}`` for ``repo_dir``.

    Returns nulls when ``repo_dir`` is not a git repository or git is unavailable,
    so a run can still be recorded outside version control.
    """
    repo = str(repo_dir)
    try:
        head = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if head.returncode != 0:
            return {"commit": None, "dirty": None}
        commit = head.stdout.strip()

        status = subprocess.run(
            ["git", "-C", repo, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        dirty: bool | None = bool(status.stdout.strip()) if status.returncode == 0 else None
        return {"commit": commit, "dirty": dirty}
    except (FileNotFoundError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}

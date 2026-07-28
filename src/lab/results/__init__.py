"""Results layer: persist a run to ``results/run_NNNN/`` and read it back.

Each run directory is self-contained and reproducible from itself alone:
``trades.parquet``, ``equity.parquet``, ``metrics.json``, ``config.yaml`` and a
``manifest.json`` recording data checksums, date range, interval, bar label, and
code provenance (git commit + dirty flag). Writing is atomic — numbering can't
clobber under concurrency, and a crash never leaves a complete-looking run.
"""

from .provenance import git_provenance
from .reader import RunArtifacts, read_run
from .writer import DataSourceRef, write_run

__all__ = [
    "DataSourceRef",
    "RunArtifacts",
    "git_provenance",
    "read_run",
    "write_run",
]

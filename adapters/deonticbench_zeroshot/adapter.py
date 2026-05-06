"""DeonticBench adapter — zero-shot Prolog mode."""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Load base adapter from deonticbench_direct without name-collision
_base_spec = importlib.util.spec_from_file_location(
    "deonticbench_direct_adapter",
    Path(__file__).parent.parent / "deonticbench_direct" / "adapter.py",
)
_base_mod = importlib.util.module_from_spec(_base_spec)  # type: ignore[arg-type]
_base_spec.loader.exec_module(_base_mod)  # type: ignore[union-attr]
DeonticBenchBaseAdapter = _base_mod.DeonticBenchBaseAdapter

TEMPLATE_DIR = Path(__file__).parent / "template"


class DeonticBenchZeroShotAdapter(DeonticBenchBaseAdapter):
    """Zero-shot Prolog mode: agent writes /app/solution.pl without examples."""

    NAME = "deonticbench-zeroshot"
    MODE = "zeroshot"

    def __init__(self, task_dir: Path, repository: Path, **kwargs: object) -> None:
        super().__init__(task_dir, repository, **kwargs)
        self._template_dir = TEMPLATE_DIR

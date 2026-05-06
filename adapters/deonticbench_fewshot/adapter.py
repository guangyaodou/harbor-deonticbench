"""DeonticBench adapter — few-shot Prolog mode."""

from __future__ import annotations

import importlib.util
import sys
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

# Maps subdomain → variable name to import from DeonticBench's case_exemplars.py
_EXEMPLAR_VAR: dict[str, str] = {
    "sara_numeric": "EXEMPLAR_SARA_V1",
    "sara_binary": "EXEMPLAR_SARA_BINARY",
    "airline": "EXAMPLE_AIRLINE_2_ONLY",
    "uscis-aao": "EXAMPLE_USCIS_ONE_SHOT",
}


def _load_exemplar(repository: Path, subdomain: str) -> str:
    """Import the few-shot example string from DeonticBench's prompts module."""
    prompts_dir = str(repository / "prompts")
    if prompts_dir not in sys.path:
        sys.path.insert(0, prompts_dir)
    import importlib

    module = importlib.import_module("case_exemplars")
    var_name = _EXEMPLAR_VAR[subdomain]
    return getattr(module, var_name)


class DeonticBenchFewShotAdapter(DeonticBenchBaseAdapter):
    """Few-shot Prolog mode: agent writes /app/solution.pl guided by /app/examples.txt."""

    NAME = "deonticbench-fewshot"
    MODE = "fewshot"

    def __init__(self, task_dir: Path, repository: Path, **kwargs: object) -> None:
        super().__init__(task_dir, repository, **kwargs)
        self._template_dir = TEMPLATE_DIR

    def _write_extra_files(
        self,
        output_dir: Path,
        subdomain: str,
        entry: dict,
        cfg: dict,
    ) -> None:
        exemplar_text = _load_exemplar(self.repository, subdomain)
        (output_dir / "environment" / "examples.txt").write_text(exemplar_text)

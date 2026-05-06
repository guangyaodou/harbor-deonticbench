"""
DeonticBench adapter - base class and direct-mode adapter.

DeonticBench is a legal reasoning benchmark covering four subdomains:
- SARA Numeric: U.S. federal income tax computation
- SARA Binary: tax law entailment/contradiction
- Airline: baggage fee calculation
- USCIS-AAO: U.S. immigration appeals adjudication

This module contains DeonticBenchBaseAdapter (shared logic for all three modes)
and DeonticBenchDirectAdapter (direct free-form answering, no Prolog required).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from jinja2 import StrictUndefined, Template

TEMPLATE_DIR = Path(__file__).parent / "template"

# Per-subdomain configuration
SUBDOMAINS: dict[str, dict] = {
    "sara_numeric": {
        "data_file": "sara_numeric/hard.json",
        "statute_type": "shared_dir",
        "statute_dir": "sara",
        "label_type": "numeric",
        "answer_format_instruction": (
            "The answer is a whole number (dollar amount, no $ sign). "
            "E.g., `Answer: 1166`"
        ),
    },
    "sara_binary": {
        "data_file": "sara_binary/hard.json",
        "statute_type": "shared_dir",
        "statute_dir": "sara",
        "label_type": "binary",
        "answer_format_instruction": (
            'The answer is exactly "Entailment" (the claim is true given the statute and facts) '
            'or "Contradiction" (the claim is false). '
            "E.g., `Answer: Entailment`"
        ),
    },
    "airline": {
        "data_file": "airline/hard.json",
        "statute_type": "shared_file",
        "statute_file": "airline/section1_non_textual",
        "label_type": "numeric",
        "answer_format_instruction": (
            "The answer is a whole number (total cost in dollars, no $ sign). "
            "E.g., `Answer: 1166`"
        ),
    },
    "uscis-aao": {
        "data_file": "uscis-aao/hard.json",
        "statute_type": "embedded",
        "label_type": "categorical",
        "answer_format_instruction": (
            'The answer is exactly "Accepted" or "Dismissed". E.g., `Answer: Accepted`'
        ),
    },
}


def _label_to_string(label: int | str, label_type: str) -> str:
    """Convert a JSON label value to the expected answer string."""
    if label_type == "numeric":
        return str(int(label))
    if label_type == "binary":
        return "Entailment" if int(label) == 1 else "Contradiction"
    # categorical: already a string ("Accepted" / "Dismissed")
    return str(label)


def _build_statute_text(subdomain_cfg: dict, repository: Path) -> str:
    """Return statute text for a subdomain (or per-entry embedded statute)."""
    statute_type = subdomain_cfg["statute_type"]
    if statute_type == "shared_dir":
        statute_dir = repository / "statutes" / subdomain_cfg["statute_dir"]
        sections = sorted(statute_dir.iterdir())
        return "\n\n---\n\n".join(p.read_text() for p in sections if p.is_file())
    if statute_type == "shared_file":
        return (repository / "statutes" / subdomain_cfg["statute_file"]).read_text()
    # embedded: caller must pass the entry's statute text directly
    raise ValueError("Use _build_entry_statute for embedded type")


class DeonticBenchBaseAdapter:
    """Shared adapter logic for all three DeonticBench modes."""

    NAME = "deonticbench-direct"
    MODE = "direct"

    def __init__(self, task_dir: Path, repository: Path, **kwargs: object) -> None:
        self.task_dir = Path(task_dir)
        self.repository = Path(repository)
        self._config = kwargs
        self._template_dir: Path = TEMPLATE_DIR  # subclasses can override
        self.benchmark_data = self._load_benchmark_data()

    def _load_benchmark_data(self) -> dict[str, dict]:
        """Load all hard-split entries from all subdomains."""
        data: dict[str, dict] = {}
        for subdomain, cfg in SUBDOMAINS.items():
            data_path = self.repository / "data" / cfg["data_file"]
            entries = json.loads(data_path.read_text())
            for entry in entries:
                entry_id = entry["id"]
                source_id = f"{subdomain}/{entry_id}"
                data[source_id] = {
                    "subdomain": subdomain,
                    "entry": entry,
                    "cfg": cfg,
                }
        return data

    def make_local_task_id(self, source_id: str) -> str:
        mode = self.MODE
        normalized = source_id.replace("/", "-").replace("_", "-").lower()
        return f"deonticbench-{mode}-{normalized}"

    def get_all_task_ids(self) -> list[str]:
        return list(self.benchmark_data.keys())

    def generate_task(self, source_id: str, local_task_id: str) -> None:
        record_meta = self.benchmark_data[source_id]
        subdomain = record_meta["subdomain"]
        entry = record_meta["entry"]
        cfg = record_meta["cfg"]

        output_dir = self.task_dir / local_task_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Copy template structure
        self._copy_template(output_dir)

        # Build statute text
        if cfg["statute_type"] == "embedded":
            statute_text = entry.get("statutes", "")
        else:
            statute_text = _build_statute_text(cfg, self.repository)

        # Write statute file into environment directory (Dockerfile will COPY it)
        (output_dir / "environment" / "statute.txt").write_text(statute_text)

        # Write expected label
        expected = _label_to_string(entry["label"], cfg["label_type"])
        (output_dir / "tests" / "expected_label.txt").write_text(expected)

        # Optionally write examples (overridden in few-shot adapter)
        self._write_extra_files(output_dir, subdomain, entry, cfg)

        # Render Jinja2 templates
        subdomain_tag = subdomain.replace("_", "-")
        record = {
            "subdomain": subdomain_tag,
            "text": entry.get("text", ""),
            "question": entry.get("question", ""),
            "answer_format_instruction": cfg["answer_format_instruction"],
        }
        self._render_templates(output_dir, record)

    def _write_extra_files(
        self,
        output_dir: Path,
        subdomain: str,
        entry: dict,
        cfg: dict,
    ) -> None:
        """Hook for subclasses to write additional files (e.g., examples.txt)."""

    def _copy_template(self, output_dir: Path) -> None:
        for item in self._template_dir.iterdir():
            dst = output_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)

    def _render_templates(self, output_dir: Path, record: dict) -> None:
        for rel in ("task.toml", "instruction.md"):
            path = output_dir / rel
            if path.exists():
                content = Template(path.read_text(), undefined=StrictUndefined).render(
                    record
                )
                path.write_text(content)


class DeonticBenchDirectAdapter(DeonticBenchBaseAdapter):
    """Direct mode: agent answers free-form, writes Answer: <value> to /app/output/answer.txt."""

    NAME = "deonticbench-direct"
    MODE = "direct"

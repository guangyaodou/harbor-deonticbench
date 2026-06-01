"""CLI to generate Harbor tasks for DeonticBench (zero-shot Prolog mode)."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import Iterable

from adapter import DeonticBenchZeroShotAdapter

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_DEONTICBENCH_ROOT = Path.home() / "DeonticBench"


def _default_output_dir() -> Path:
    return REPO_ROOT / "datasets" / "deonticbench-zeroshot"


def _read_ids_from_file(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text().splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def _collect_ids(ids_cli: Iterable[str] | None, ids_file: Path | None) -> list[str]:
    if ids_cli:
        return list(ids_cli)
    if ids_file and ids_file.exists():
        return _read_ids_from_file(ids_file)
    return []


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Harbor tasks for DeonticBench (zero-shot Prolog mode)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--deonticbench-root",
        type=Path,
        default=DEFAULT_DEONTICBENCH_ROOT,
        help="Path to the local DeonticBench repository",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_output_dir(),
        help="Directory to write generated tasks",
    )
    parser.add_argument(
        "--task-ids",
        nargs="*",
        default=None,
        help="Explicit source IDs to convert, e.g. sara_numeric/tax_case_10",
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        default=None,
        help="Path to a text file with one source ID per line",
    )
    parser.add_argument(
        "--subdomains",
        nargs="*",
        default=None,
        choices=["sara_numeric", "sara_binary", "airline", "uscis-aao"],
        help="Filter to specific subdomains (default: all four)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Generate only the first N tasks",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=False,
        help="Delete the output directory before generating tasks",
    )
    return parser.parse_args()


def _process_benchmark(
    benchmark_root: Path,
    output_dir: Path,
    task_ids: list[str],
    limit: int | None,
    subdomains: list[str] | None,
) -> None:
    adapter = DeonticBenchZeroShotAdapter(
        task_dir=output_dir, repository=benchmark_root
    )

    if not task_ids:
        task_ids = adapter.get_all_task_ids()

    if subdomains:
        task_ids = [t for t in task_ids if t.split("/")[0] in subdomains]

    if limit and limit > 0:
        task_ids = task_ids[:limit]

    logger.info(f"Processing {len(task_ids)} tasks...")
    for source_id in task_ids:
        try:
            local_task_id = adapter.make_local_task_id(source_id)
            adapter.generate_task(source_id, local_task_id)
        except Exception as e:
            logger.error(f"Failed to generate task {source_id}: {e}", exc_info=True)

    logger.info(f"Tasks written to: {output_dir.resolve()}")


def main() -> None:
    args = _parse_args()

    benchmark_root: Path = args.deonticbench_root
    if not benchmark_root.exists():
        logger.error(f"DeonticBench root not found: {benchmark_root}")
        sys.exit(1)

    output_dir: Path = args.output_dir
    if args.clean and output_dir.exists():
        logger.info(f"Cleaning output directory: {output_dir.resolve()}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir.resolve()}")

    all_ids = _collect_ids(args.task_ids, args.ids_file)

    try:
        _process_benchmark(
            benchmark_root, output_dir, all_ids, args.limit, args.subdomains
        )
    except Exception as e:
        logger.error(f"Error during processing: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

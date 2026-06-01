"""
Evaluate DeonticBench job results across one or more job directories.

Metrics:
  - SARA Numeric, Airline : Accuracy
  - SARA Binary, USCIS-AAO: Macro-F1

When the same model appears in multiple runs under the same jobs-dir,
only the latest run (by directory name) is used.

Usage:
  python evaluate_deonticbench.py                                  # all under jobs/
  python evaluate_deonticbench.py jobs/deontic-direct
  python evaluate_deonticbench.py jobs/deontic-direct jobs/deontic-zeroshot
  python evaluate_deonticbench.py jobs/deontic-direct --output results-direct.csv
  python evaluate_deonticbench.py jobs/deontic-direct --verbose
  python evaluate_deonticbench.py jobs/deontic-direct jobs/deontic-direct-airline --output results-direct.csv
  python evaluate_deonticbench.py jobs/deontic-direct --errors-as-incorrect --output results-direct-strict.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


ACCURACY_DATASETS = ("sara-numeric", "airline")
F1_DATASETS = ("sara-binary", "uscis-aao")
ORDERED_DATASETS = ("sara-numeric", "airline", "sara-binary", "uscis-aao")


def _subdomain(task_name: str) -> str | None:
    for sd in ("sara-numeric", "sara-binary", "airline", "uscis-aao"):
        if f"-{sd}-" in task_name:
            return sd
    return None


def _parse_verifier_stdout(path: Path) -> tuple[str, str]:
    expected = got = ""
    for line in path.read_text().splitlines():
        m = re.match(r"Normalized expected:\s*(.+)", line)
        if m:
            expected = m.group(1).strip()
        m = re.match(r"Normalized got:\s*(.*)", line)
        if m:
            got = m.group(1).strip()
    return expected, got


def _macro_f1(records: list[tuple[str, str]]) -> dict:
    classes = sorted({exp for exp, _ in records})
    stats: dict[str, dict] = {}
    for c in classes:
        tp = sum(1 for exp, got in records if exp == c and got == c)
        fp = sum(1 for exp, got in records if exp != c and got == c)
        fn = sum(1 for exp, got in records if exp == c and got != c)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        stats[c] = {"precision": precision, "recall": recall, "f1": f1,
                    "tp": tp, "fp": fp, "fn": fn}
    macro_f1 = sum(s["f1"] for s in stats.values()) / len(stats) if stats else 0.0
    return {"per_class": stats, "macro_f1": macro_f1}


def _model_name(trial_dir: Path) -> str:
    config_path = trial_dir / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text())
        agent = cfg.get("agent", {})
        agent_name = agent.get("name") or "unknown"
        model_name = agent.get("model_name") or "unknown"
        return f"{agent_name} / {model_name}"
    return "unknown"


def _find_run_dirs(job_dir: Path) -> list[Path]:
    """Return run dirs (dirs whose children are trial dirs containing result.json).

    Handles two layouts:
      - job_dir is a timestamped run dir already (original usage)
      - job_dir is a named dir containing timestamped run subdirs

    Run dirs may themselves contain a job-level result.json, so we distinguish
    by checking whether any subdir contains further trial subdirs with result.json.
    """
    subdirs = sorted(d for d in job_dir.iterdir() if d.is_dir())
    if not subdirs:
        return []
    # If any subdir contains nested subdirs with result.json, subdirs are run dirs
    for candidate_run in subdirs:
        for child in candidate_run.iterdir():
            if child.is_dir() and (child / "result.json").exists():
                return subdirs
    # Otherwise job_dir itself is the run dir and subdirs are trial dirs
    if any((d / "result.json").exists() for d in subdirs):
        return [job_dir]
    return subdirs


UsageEntry = dict  # n_input_tokens, n_output_tokens, n_cache_tokens, cost_usd, exception_type, parse_failure


def collect(
    job_dirs: list[Path], verbose: bool = False
) -> tuple[dict[str, dict[str, list[tuple[str, str, bool]]]], dict[str, list[UsageEntry]]]:
    """Return (records, usage).

    records[model][subdomain] = list of (expected, got, is_error)
    usage[model] = list of per-trial token/cost dicts

    When a model appears in multiple run dirs under the same parent,
    only the latest run dir (sorted by name) is used.
    """
    # raw[(parent, model, run_dir)] = list of (sd, expected, got, usage_entry)
    raw: dict[tuple[Path, str, Path], list[tuple[str, str, str, UsageEntry]]] = defaultdict(list)
    skipped = 0

    for job_dir in job_dirs:
        for run_dir in _find_run_dirs(job_dir):
            for trial_dir in sorted(run_dir.iterdir()):
                result_path = trial_dir / "result.json"
                stdout_path = trial_dir / "verifier" / "test-stdout.txt"

                if not result_path.exists():
                    continue

                result = json.loads(result_path.read_text())
                task_name = result.get("task_name", "")
                sd = _subdomain(task_name)
                if sd is None:
                    skipped += 1
                    continue

                model = _model_name(trial_dir)
                ar = result.get("agent_result") or {}
                ei = result.get("exception_info") or {}
                usage: UsageEntry = {
                    "n_input_tokens": ar.get("n_input_tokens") or 0,
                    "n_output_tokens": ar.get("n_output_tokens") or 0,
                    "n_cache_tokens": ar.get("n_cache_tokens") or 0,
                    "cost_usd": ar.get("cost_usd") or 0.0,
                    "exception_type": ei.get("exception_type"),
                    "parse_failure": False,
                }

                if not stdout_path.exists():
                    usage["missing_stdout"] = True
                    raw[(job_dir, model, run_dir)].append((sd, "", "", usage))
                    continue

                expected, got = _parse_verifier_stdout(stdout_path)
                usage["parse_failure"] = bool(got == "" and not ei)
                usage["missing_stdout"] = False
                raw[(job_dir, model, run_dir)].append((sd, expected, got, usage))

                if verbose:
                    correct = "✓" if expected == got else "✗"
                    print(f"  {correct} [{run_dir.name}] [{model}] [{sd}] expected={expected!r:20s} got={got!r}")

    if skipped:
        print(f"(skipped {skipped} non-deonticbench trials)\n")

    # For each (parent, model), find the latest run_dir
    latest_run: dict[tuple[Path, str], Path] = {}
    for parent, model, run_dir in raw:
        key = (parent, model)
        if key not in latest_run or run_dir.name > latest_run[key].name:
            latest_run[key] = run_dir

    # Report skipped older runs
    skipped_runs: dict[tuple[Path, str], list[Path]] = defaultdict(list)
    for parent, model, run_dir in raw:
        if run_dir != latest_run[(parent, model)]:
            skipped_runs[(parent, model)].append(run_dir)

    for (parent, model), old_runs in sorted(skipped_runs.items()):
        latest = latest_run[(parent, model)]
        print(f"  [latest-only] {model} in {parent}: using {latest.name}, "
              f"skipping {[r.name for r in sorted(old_runs)]}")

    if skipped_runs:
        print()

    # Build final records using only latest runs
    records: dict[str, dict[str, list[tuple[str, str, bool]]]] = defaultdict(lambda: defaultdict(list))
    usage_by_model: dict[str, list[UsageEntry]] = defaultdict(list)
    for (parent, model, run_dir), trials in raw.items():
        if run_dir != latest_run[(parent, model)]:
            continue
        for sd, expected, got, usage in trials:
            is_error = bool(
                usage.get("exception_type")
                or usage.get("parse_failure")
                or usage.get("missing_stdout")
            )
            records[model][sd].append((expected, got, is_error))
            usage_by_model[model].append(usage)

    return records, usage_by_model


def _compute_row(
    model: str, sd: str, recs: list[tuple[str, str, bool]], strict: bool = False
) -> dict:
    n = len(recs)
    if strict:
        # Errored trials are never correct, regardless of (expected, got).
        correct = sum(1 for exp, got, err in recs if not err and exp == got)
    else:
        correct = sum(1 for exp, got, _err in recs if exp == got)

    if sd in ACCURACY_DATASETS:
        score = correct / n if n else 0.0
        metric = "Accuracy"
        details = f"{correct}/{n} correct"
    else:
        if strict:
            # For F1: errored trials with a known expected become FN for the true
            # class (got replaced with a sentinel). Errored trials with no
            # recoverable expected are dropped from F1 (still surfaced via the
            # error columns in the CSV).
            f1_recs: list[tuple[str, str]] = []
            for exp, got, err in recs:
                if err:
                    if exp:
                        f1_recs.append((exp, "__ERROR__"))
                else:
                    f1_recs.append((exp, got))
        else:
            f1_recs = [(exp, got) for exp, got, _err in recs]
        f1_data = _macro_f1(f1_recs)
        score = f1_data["macro_f1"]
        metric = "Macro-F1"
        details = "  ".join(
            f"{cls}: P={s['precision']:.2f} R={s['recall']:.2f} F1={s['f1']:.2f}"
            for cls, s in f1_data["per_class"].items()
        )
    return {"model": model, "dataset": sd, "metric": metric, "score": score, "n": n,
            "correct": correct, "details": details}


def print_table(
    records: dict[str, dict[str, list[tuple[str, str, bool]]]],
    usage_by_model: dict[str, list[UsageEntry]] | None = None,
    strict: bool = False,
) -> None:
    if strict:
        print("\n(strict scoring: errored trials counted as incorrect)")
    for model in sorted(records):
        print(f"\nModel: {model}")
        print(f"  {'Dataset':<15} {'Metric':<10} {'Score':>8}  {'N':>5}  Details")
        print("  " + "-" * 63)
        total_correct = total_n = 0
        for sd in ORDERED_DATASETS:
            if sd not in records[model]:
                continue
            row = _compute_row(model, sd, records[model][sd], strict=strict)
            total_correct += row["correct"]
            total_n += row["n"]
            print(f"  {row['dataset']:<15} {row['metric']:<10} {row['score']:>8.3f}  {row['n']:>5}  {row['details']}")
        if total_n:
            overall = total_correct / total_n
            print("  " + "-" * 63)
            print(f"  {'Overall':<15} {'Accuracy':<10} {overall:>8.3f}  {total_n:>5}")


def _trim_model(model: str) -> str:
    """'claude-code / openai/Qwen/Qwen3.5-122B' -> 'claude-code / Qwen3.5-122B'"""
    if " / " in model:
        agent, rest = model.split(" / ", 1)
        return f"{agent} / {rest.split('/')[-1]}"
    return model.split("/")[-1]


ERROR_TYPES = ("RuntimeError", "AgentTimeoutError", "RewardFileNotFoundError", "ServiceUnavailableError")


def write_csv(
    records: dict[str, dict[str, list[tuple[str, str, bool]]]],
    usage_by_model: dict[str, list[UsageEntry]],
    dest: Path | None,
    strict: bool = False,
) -> None:
    fieldnames = ["model"] + list(ORDERED_DATASETS) + [
        "avg_input_tokens", "avg_output_tokens", "avg_total_tokens", "avg_cache_tokens", "total_cost_usd",
        "n_trials", "total_errors", *ERROR_TYPES, "parse_failure",
    ]
    rows = []
    for model in sorted(records):
        row: dict[str, str] = {"model": _trim_model(model)}
        for sd in ORDERED_DATASETS:
            if sd in records[model]:
                r = _compute_row(model, sd, records[model][sd], strict=strict)
                row[sd] = f"{r['score']:.4f}"
            else:
                row[sd] = ""
        entries = usage_by_model.get(model, [])
        ran = [e for e in entries if e["n_input_tokens"] > 0]
        n_ran = len(ran) or 1
        avg_in = sum(e["n_input_tokens"] for e in ran) / n_ran
        avg_out = sum(e["n_output_tokens"] for e in ran) / n_ran
        row["avg_input_tokens"] = f"{avg_in:.0f}"
        row["avg_output_tokens"] = f"{avg_out:.0f}"
        row["avg_total_tokens"] = f"{avg_in + avg_out:.0f}"
        row["avg_cache_tokens"] = f"{sum(e['n_cache_tokens'] for e in ran) / n_ran:.0f}"
        row["total_cost_usd"] = f"{sum(e['cost_usd'] for e in entries):.4f}"
        row["n_trials"] = str(len(entries))
        error_counts = {et: sum(1 for e in entries if e.get("exception_type") == et) for et in ERROR_TYPES}
        parse_fail = sum(1 for e in entries if e.get("parse_failure"))
        row["total_errors"] = str(sum(error_counts.values()) + parse_fail)
        for et in ERROR_TYPES:
            row[et] = str(error_counts[et])
        row["parse_failure"] = str(parse_fail)
        rows.append(row)

    if dest:
        with dest.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCSV written to: {dest}")
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate DeonticBench Harbor job results")
    parser.add_argument("job_dirs", type=Path, nargs="*",
                        help="Path(s) to job directories (default: all under jobs/)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-trial results")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Write CSV to file (default: print to stdout after table)")
    parser.add_argument("--errors-as-incorrect", action="store_true",
                        help="Count any trial with an exception, parse failure, or missing "
                             "verifier stdout as incorrect (still recorded in the error columns).")
    args = parser.parse_args()

    if not args.job_dirs:
        default_jobs = Path("jobs")
        if not default_jobs.exists():
            print("No job directories specified and jobs/ not found.", file=sys.stderr)
            sys.exit(1)
        args.job_dirs = sorted(p for p in default_jobs.iterdir() if p.is_dir())

    missing = [d for d in args.job_dirs if not d.exists()]
    if missing:
        for d in missing:
            print(f"Job directory not found: {d}", file=sys.stderr)
        sys.exit(1)

    print("Jobs: " + ", ".join(str(d) for d in args.job_dirs))
    records, usage_by_model = collect(args.job_dirs, verbose=args.verbose)

    if not records:
        print("No deonticbench results found.")
        return

    print_table(records, usage_by_model, strict=args.errors_as_incorrect)
    print()
    write_csv(records, usage_by_model, args.output, strict=args.errors_as_incorrect)


if __name__ == "__main__":
    main()

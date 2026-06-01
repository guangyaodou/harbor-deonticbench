"""
Evaluate meta-harness Terminal-Bench 2 / DeonticBench job results.

Reads trial-level result.json files produced by harbor runs and outputs a CSV
with per-agent, per-subdomain scores plus token/cost usage.

Subdomains and metrics:
  sara-numeric, airline  → Accuracy
  sara-binary, uscis-aao → Macro-F1

Usage:
  python evaluate_jobs.py                              # all jobs under jobs/
  python evaluate_jobs.py jobs/deontic-gpt51
  python evaluate_jobs.py jobs/deontic-gpt51 jobs/deontic-gpt51-zeroshot
  python evaluate_jobs.py jobs/deontic-gpt51 --output results.csv
  python evaluate_jobs.py jobs/deontic-gpt51 --verbose
  python evaluate_jobs.py jobs/deontic-direct --output results-direct-kira.csv
  python evaluate_jobs.py jobs/deontic-direct-airline-only --output results-direct-kira-airline.csv
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

ERROR_TYPES = (
    "RuntimeError",
    "AgentTimeoutError",
    "RewardFileNotFoundError",
    "ServiceUnavailableError",
)


def _subdomain(task_name: str) -> str | None:
    for sd in ("sara-numeric", "sara-binary", "airline", "uscis-aao"):
        if f"-{sd}-" in task_name or task_name.endswith(f"-{sd}"):
            return sd
    # fallback: check substrings in order (longer patterns first)
    for sd in ("sara-numeric", "sara-binary", "uscis-aao", "airline"):
        if sd.replace("-", "") in task_name.replace("-", ""):
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


def _agent_label_from_result(result: dict) -> str:
    """Extract agent module name from a trial result dict."""
    import_path = result.get("config", {}).get("agent", {}).get("import_path", "")
    if import_path:
        module = import_path.split(":")[0]
        return re.sub(r"^agents\.", "", module)
    return ""


def _agent_label_from_dir(job_dir: Path) -> str:
    """Fallback: derive agent label from job directory name or its config.json."""
    config_path = job_dir / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text())
            import_path = cfg.get("agent", {}).get("import_path", "")
            if import_path:
                module = import_path.split(":")[0]
                return re.sub(r"^agents\.", "", module)
        except (json.JSONDecodeError, OSError):
            pass
    name = job_dir.name
    return re.sub(r"^(evolve|smoke)-", "", name)


def _model_label(result: dict) -> str:
    model = result.get("config", {}).get("agent", {}).get("model_name", "")
    if model:
        return model.split("/")[-1]
    return "unknown"


def _is_trial_dir(d: Path) -> bool:
    """A trial dir has a result.json with a task_name field."""
    rf = d / "result.json"
    if not rf.exists():
        return False
    try:
        return bool(json.loads(rf.read_text()).get("task_name"))
    except (json.JSONDecodeError, OSError):
        return False


def _find_job_dirs(root: Path) -> list[Path]:
    """Given a root path, return all job directories (dirs containing trial dirs).

    Trial dirs are identified by having a result.json with a task_name field.
    Handles four layouts:
      1. root is a job dir          (root/<trial>/result.json)
      2. root is a run dir          (root/<job>/<trial>/result.json)
      3. root is a jobs-parent dir  (root/<run>/<trial>/result.json)
      4. root is a deep parent      (root/<run>/<job>/<trial>/result.json)
    """
    subdirs = [d for d in sorted(root.iterdir()) if d.is_dir()]

    # Level 1: root itself is a job dir
    if any(_is_trial_dir(d) for d in subdirs):
        return [root]

    job_dirs = []
    for sub in subdirs:
        sub_children = [d for d in sorted(sub.iterdir()) if d.is_dir()]
        # Level 2: sub is a job dir
        if any(_is_trial_dir(d) for d in sub_children):
            job_dirs.append(sub)
        else:
            # Level 3: sub is a run dir containing job dirs
            for subsub in sub_children:
                subsub_children = [d for d in sorted(subsub.iterdir()) if d.is_dir()]
                if any(_is_trial_dir(d) for d in subsub_children):
                    job_dirs.append(subsub)

    return job_dirs


UsageEntry = dict


def collect(
    input_paths: list[Path], verbose: bool = False
) -> tuple[
    dict[str, dict[str, list[tuple[str, str]]]],
    dict[str, list[UsageEntry]],
]:
    """Collect trial results from the given paths.

    Returns:
        records["agent / model"][subdomain] = list of (expected, got)
        usage["agent / model"] = list of per-trial usage dicts
    """
    records: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    usage_by_agent: dict[str, list[UsageEntry]] = defaultdict(list)
    skipped = 0

    job_dirs: list[Path] = []
    for p in input_paths:
        job_dirs.extend(_find_job_dirs(p))

    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique_jobs: list[Path] = []
    for j in job_dirs:
        if j not in seen:
            seen.add(j)
            unique_jobs.append(j)

    # For each (parent, model-key) group, keep only the latest run by dir name.
    def _model_key(job_dir: Path) -> str:
        cfg_path = job_dir / "config.json"
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text())
                agents = cfg.get("agents") or []
                return "|".join(
                    f"{a.get('import_path','')}@{a.get('model_name','')}"
                    for a in agents
                )
            except (json.JSONDecodeError, OSError):
                pass
        return ""

    grouped: dict[tuple[Path, str], list[Path]] = defaultdict(list)
    for j in unique_jobs:
        key = (j.parent, _model_key(j))
        grouped[key].append(j)

    deduped: list[Path] = []
    for (_, mkey), dirs in grouped.items():
        if len(dirs) > 1 and mkey:
            latest = max(dirs, key=lambda d: d.name)
            skipped_dirs = [d for d in dirs if d != latest]
            for sd in skipped_dirs:
                print(f"(skipping older run {sd.name} in favour of {latest.name})")
            deduped.append(latest)
        else:
            deduped.extend(dirs)
    unique_jobs = sorted(deduped, key=lambda d: (d.parent, d.name))

    for job_dir in unique_jobs:
        dir_label = _agent_label_from_dir(job_dir)

        for trial_dir in sorted(job_dir.iterdir()):
            if not _is_trial_dir(trial_dir):
                continue

            result_path = trial_dir / "result.json"
            stdout_path = trial_dir / "verifier" / "test-stdout.txt"

            try:
                result = json.loads(result_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            task_name = result.get("task_name", "")
            sd = _subdomain(task_name)
            if sd is None:
                skipped += 1
                continue

            agent_name = _agent_label_from_result(result) or dir_label
            model = _model_label(result)
            key = f"{agent_name} / {model}"

            ar = result.get("agent_result") or {}
            ei = result.get("exception_info") or {}
            entry: UsageEntry = {
                "n_input_tokens": ar.get("n_input_tokens") or 0,
                "n_output_tokens": ar.get("n_output_tokens") or 0,
                "n_cache_tokens": ar.get("n_cache_tokens") or 0,
                "cost_usd": ar.get("cost_usd") or 0.0,
                "exception_type": ei.get("exception_type"),
                "parse_failure": False,
            }

            if not stdout_path.exists():
                records[key][sd].append(("", ""))
                usage_by_agent[key].append(entry)
                continue

            expected, got = _parse_verifier_stdout(stdout_path)
            entry["parse_failure"] = bool(got == "" and not ei)
            records[key][sd].append((expected, got))
            usage_by_agent[key].append(entry)

            if verbose:
                correct = "✓" if expected == got else "✗"
                print(
                    f"  {correct} [{key}] [{sd}] "
                    f"expected={expected!r:20s} got={got!r}"
                )

    if skipped:
        print(f"(skipped {skipped} non-deonticbench trials)\n")

    return records, usage_by_agent


def _compute_row(sd: str, recs: list[tuple[str, str]]) -> dict:
    n = len(recs)
    correct = sum(1 for exp, got in recs if exp == got)
    if sd in ACCURACY_DATASETS:
        score = correct / n if n else 0.0
        metric = "Accuracy"
        details = f"{correct}/{n}"
    else:
        f1_data = _macro_f1(recs)
        score = f1_data["macro_f1"]
        metric = "Macro-F1"
        details = "  ".join(
            f"{cls}: P={s['precision']:.2f} R={s['recall']:.2f} F1={s['f1']:.2f}"
            for cls, s in f1_data["per_class"].items()
        )
    return {"metric": metric, "score": score, "n": n, "correct": correct, "details": details}


def print_table(
    records: dict[str, dict[str, list[tuple[str, str]]]],
) -> None:
    for key in sorted(records):
        print(f"\n{key}")
        print(f"  {'Dataset':<15} {'Metric':<10} {'Score':>8}  {'N':>5}  Details")
        print("  " + "-" * 65)
        total_correct = total_n = 0
        for sd in ORDERED_DATASETS:
            if sd not in records[key]:
                continue
            row = _compute_row(sd, records[key][sd])
            total_correct += row["correct"]
            total_n += row["n"]
            print(
                f"  {sd:<15} {row['metric']:<10} {row['score']:>8.3f}"
                f"  {row['n']:>5}  {row['details']}"
            )
        if total_n:
            overall = total_correct / total_n
            print("  " + "-" * 65)
            print(f"  {'Overall':<15} {'Accuracy':<10} {overall:>8.3f}  {total_n:>5}")


def write_csv(
    records: dict[str, dict[str, list[tuple[str, str]]]],
    usage_by_agent: dict[str, list[UsageEntry]],
    dest: Path | None,
) -> None:
    fieldnames = (
        ["agent", "model"]
        + list(ORDERED_DATASETS)
        + [
            "overall_accuracy",
            "avg_input_tokens",
            "avg_output_tokens",
            "avg_total_tokens",
            "avg_cache_tokens",
            "total_cost_usd",
            "n_trials",
            "total_errors",
            *ERROR_TYPES,
            "parse_failure",
        ]
    )

    rows = []
    for key in sorted(records):
        agent, _, model = key.partition(" / ")
        row: dict[str, str] = {"agent": agent, "model": model}

        total_correct = total_n = 0
        for sd in ORDERED_DATASETS:
            if sd in records[key]:
                r = _compute_row(sd, records[key][sd])
                row[sd] = f"{r['score']:.4f}"
                total_correct += r["correct"]
                total_n += r["n"]
            else:
                row[sd] = ""

        row["overall_accuracy"] = f"{total_correct / total_n:.4f}" if total_n else ""

        entries = usage_by_agent.get(key, [])
        ran = [e for e in entries if e["n_input_tokens"] > 0]
        n_ran = len(ran) or 1
        row["avg_input_tokens"] = f"{sum(e['n_input_tokens'] for e in ran) / n_ran:.0f}"
        row["avg_output_tokens"] = f"{sum(e['n_output_tokens'] for e in ran) / n_ran:.0f}"
        row["avg_total_tokens"] = f"{(sum(e['n_input_tokens'] for e in ran) + sum(e['n_output_tokens'] for e in ran)) / n_ran:.0f}"
        row["avg_cache_tokens"] = f"{sum(e['n_cache_tokens'] for e in ran) / n_ran:.0f}"
        row["total_cost_usd"] = f"{sum(e['cost_usd'] for e in entries):.4f}"
        row["n_trials"] = str(len(entries))

        error_counts = {
            et: sum(1 for e in entries if e.get("exception_type") == et)
            for et in ERROR_TYPES
        }
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
    parser = argparse.ArgumentParser(
        description="Evaluate meta-harness TB2/DeonticBench job results → CSV"
    )
    parser.add_argument(
        "job_dirs",
        type=Path,
        nargs="*",
        help="Path(s) to job/run directories (default: all under jobs/)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print per-trial results"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write CSV to file (default: print to stdout after table)",
    )
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

    print("Inputs: " + ", ".join(str(d) for d in args.job_dirs))
    records, usage_by_agent = collect(args.job_dirs, verbose=args.verbose)

    if not records:
        print("No deonticbench results found.")
        return

    print_table(records)
    print()
    write_csv(records, usage_by_agent, args.output)


if __name__ == "__main__":
    main()

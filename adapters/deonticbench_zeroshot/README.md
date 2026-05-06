# DeonticBench Adapter — Zero-Shot Prolog Mode

Converts the hard splits of four DeonticBench subdomains into Harbor tasks.
In **zero-shot Prolog mode** the agent reads the statute and case facts, then
writes a self-contained SWI-Prolog program at `/app/solution.pl` with no
examples provided.

## Subdomains

| Subdomain | Tasks | Answer type |
|-----------|-------|-------------|
| sara_numeric | 35 | Integer (tax dollars) |
| sara_binary | 30 | `Entailment` / `Contradiction` |
| airline | 80 | Integer (total cost dollars) |
| uscis-aao | 28 | `Accepted` / `Dismissed` |

## Usage

```bash
cd adapters/deonticbench_zeroshot

python run_adapter.py \
    --deonticbench-root /path/to/DeonticBench \
    --output-dir /path/to/output

# Filter to one subdomain or limit tasks
python run_adapter.py \
    --deonticbench-root /path/to/DeonticBench \
    --subdomains airline \
    --limit 5
```

## Task layout

```
deonticbench-zeroshot-{subdomain}-{id}/
├── task.toml
├── instruction.md
├── environment/
│   ├── Dockerfile        # python-3-13 base + swi-prolog
│   └── statute.txt       → /app/statute.txt inside container
└── tests/
    ├── test.sh           # runs swipl on /app/solution.pl, checks output
    └── expected_label.txt
```

## Related adapters

- `deonticbench_direct/` — direct free-form answering
- `deonticbench_fewshot/` — few-shot Prolog mode with `/app/examples.txt`

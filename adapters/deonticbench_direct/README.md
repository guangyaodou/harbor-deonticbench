# DeonticBench Adapter — Direct Mode

Converts the hard splits of four DeonticBench subdomains into Harbor tasks.
In **direct mode** the agent reads the statute and case facts, then writes its
answer free-form to `/app/output/answer.txt`.

## Subdomains

| Subdomain | Tasks | Answer type |
|-----------|-------|-------------|
| sara_numeric | 35 | Integer (tax dollars) |
| sara_binary | 30 | `Entailment` / `Contradiction` |
| airline | 80 | Integer (total cost dollars) |
| uscis-aao | 28 | `Accepted` / `Dismissed` |

## Usage

```bash
cd adapters/deonticbench_direct

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
deonticbench-direct-{subdomain}-{id}/
├── task.toml
├── instruction.md
├── environment/
│   ├── Dockerfile        # python-3-13 base + swi-prolog
│   └── statute.txt       → /app/statute.txt inside container
└── tests/
    ├── test.sh           # checks /app/output/answer.txt
    └── expected_label.txt
```

## Related adapters

- `deonticbench_zeroshot/` — zero-shot Prolog mode
- `deonticbench_fewshot/` — few-shot Prolog mode with `/app/examples.txt`

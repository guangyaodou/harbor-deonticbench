# DeonticBench Adapter — Few-Shot Prolog Mode

Converts the hard splits of four DeonticBench subdomains into Harbor tasks.
In **few-shot Prolog mode** the agent reads the statute, case facts, and one
or more example Prolog solutions at `/app/examples.txt`, then writes a
SWI-Prolog program at `/app/solution.pl`.

## Subdomains

| Subdomain | Tasks | Answer type | Example source |
|-----------|-------|-------------|----------------|
| sara_numeric | 35 | Integer (tax dollars) | `EXEMPLAR_SARA_V1` |
| sara_binary | 30 | `Entailment` / `Contradiction` | `EXEMPLAR_SARA_BINARY` |
| airline | 80 | Integer (total cost dollars) | `EXAMPLE_AIRLINE_2_ONLY` |
| uscis-aao | 28 | `Accepted` / `Dismissed` | `EXAMPLE_USCIS_ONE_SHOT` |

Examples are imported at task-generation time from
`DeonticBench/prompts/case_exemplars.py`.

## Usage

```bash
cd adapters/deonticbench_fewshot

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
deonticbench-fewshot-{subdomain}-{id}/
├── task.toml
├── instruction.md
├── environment/
│   ├── Dockerfile        # python-3-13 base + swi-prolog
│   ├── statute.txt       → /app/statute.txt inside container
│   └── examples.txt      → /app/examples.txt inside container
└── tests/
    ├── test.sh           # runs swipl on /app/solution.pl, checks output
    └── expected_label.txt
```

## Related adapters

- `deonticbench_direct/` — direct free-form answering (no Prolog required)
- `deonticbench_zeroshot/` — zero-shot Prolog mode (no examples)

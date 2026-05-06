# DeonticBench Evaluation

## Running Jobs

Results are saved to named subdirectories under `jobs/` via `--jobs-dir`.

### Direct

```bash
harbor run \
  --path datasets/deonticbench-direct \
  --agent terminus-2 \
  --model openrouter/moonshotai/kimi-k2-0905 \
  --ae OPENROUTER_API_KEY=$OPENROUTER_API_KEY \
  --n-concurrent 4 \
  --jobs-dir jobs/deontic-direct
```

### Zero-shot

```bash
harbor run \
  --path datasets/deonticbench-zeroshot \
  --agent terminus-2 \
  --model openrouter/moonshotai/kimi-k2-0905 \
  --ae OPENROUTER_API_KEY=$OPENROUTER_API_KEY \
  --n-concurrent 4 \
  --jobs-dir jobs/deontic-zeroshot
```

### Few-shot

```bash
harbor run \
  --path datasets/deonticbench-fewshot \
  --agent terminus-2 \
  --model openrouter/moonshotai/kimi-k2-0905 \
  --ae OPENROUTER_API_KEY=$OPENROUTER_API_KEY \
  --n-concurrent 4 \
  --jobs-dir jobs/deontic-fewshot
```

## Evaluating Results

```bash
# Evaluate all jobs under jobs/ (default)
python evaluate_deonticbench.py

# Evaluate a specific jobs-dir
python evaluate_deonticbench.py jobs/deontic-direct

# Compare multiple conditions
python evaluate_deonticbench.py jobs/deontic-direct jobs/deontic-zeroshot jobs/deontic-fewshot

# Save CSV output
python evaluate_deonticbench.py jobs/deontic-direct jobs/deontic-zeroshot jobs/deontic-fewshot --output results.csv

# Verbose per-trial output
python evaluate_deonticbench.py jobs/deontic-direct --verbose
```

## Metrics

| Subdomain     | Metric   |
|---------------|----------|
| sara-numeric  | Accuracy |
| airline       | Accuracy |
| sara-binary   | Macro-F1 |
| uscis-aao     | Macro-F1 |

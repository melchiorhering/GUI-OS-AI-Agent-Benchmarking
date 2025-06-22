# Evaluation Examples

This directory contains task definitions and helper data for evaluating sandboxed AI agents. Below is an explanation of its structure and the updated JSON task format.

---

## Directory Overview

- `documents/` – Preprocessed documentation for retrieval-augmented tasks.
- `examples/` – Task examples for different tools and applications.
- `settings/` – Credentials or environment configs required for account-based tasks.

---

## Task Format (Flowbook Style)

Each task lives in a subdirectory of `examples/<tool>/<uuid>/`. The core configuration is a JSON file named `<uuid>.json`. Here's an example adapted for a **Jupyter** task:

```json
{
  "id": "00b43a0a-b17b-475d-a482-302efe94d4cc",
  "snapshot": "jupyter",
  "instruction": "...",
  "source": ["https://www.kaggle.com/datasets/..."],
  "related_apps": ["jupyter"],
  "tags": ["cli+gui", "traditional_data_processing", "verbose"],
  "action_number": 7,
  "config": [
    {
      "func": "upload_file_to_vm",
      "arguments": {
        "local_path": "Athletes_summer_games.csv",
        "remote_path": "/home/user/Desktop/Athletes_summer_games.csv"
      }
    },
    ...
  ],
  "evaluation": {
    "func": "compare_csv",
    "arguments": {
      "local_expected": "gold.csv",
      "vm_result": "/home/user/Desktop/allGames.csv"
    }
  },
  "counterpart": "cad93c85-d12d-4ba3-83d7-ba4e3ec3bfcc"
}
```

---

### 🔑 Key Fields

- `id`: Globally unique identifier for the task.
- `snapshot`: Target application (e.g., `"jupyter"`, `"bigquery"`).
- `instruction`: Goal description or step-by-step guide.
- `source`: URLs from which the example was derived.
- `related_apps`: List of tools used (see full list below).
- `tags`: Labels describing the nature of the task:

  - **Interface**: `cli`, `gui`, or `cli+gui`
  - **Guidance**: `verbose` (step-by-step) or `abstract` (goal only)
  - **Domain**: one of the 7 pipeline stages (e.g. `data_warehousing`, `traditional_data_processing`)
  - **Account Requirement**: `account` if credentials are needed

- `action_number`: Number of agent steps expected in a successful execution.
- `config`: Setup functions to prepare the environment. Each entry includes:

  - `func`: Name of the Python function to run (looked up via `CONFIG_DISPATCH`)
  - `arguments`: Keyword arguments passed to the function. Paths are usually resolved relative to the task folder.

- `evaluation`: Post-task metric. Includes:

  - `func`: Evaluation function name (from `EVAL_DISPATCH`)
  - `arguments`: Arguments passed to the evaluation function. These often include paths to files produced by the agent and reference files.

- `counterpart`: ID of the same task but with an alternate instruction style (abstract vs. verbose).

---

### 🔁 Function Dispatching

- `config` steps are handled by Python functions in `benchmark.helpers.config.*`.
- `evaluation` is handled by functions in `benchmark.helpers.evaluators.*`.

Both are dynamically called with:

```python
func(task=TaskSpec, agent=SandboxCodeAgent, **arguments)
```

This allows each helper function to access all metadata, logs, file paths, and VM handles needed for setup or scoring.

---

## Supported Applications (`related_apps`)

Supported apps include (not exhaustive):

```text
'airflow', 'dagster', 'snowflake', 'duckdb', 'bigquery', 'jupyter',
'dbt', 'mysql', 'servicenow', 'terminal', 'metabase', 'airbyte',
'docker', 'hasura_cloud', 'sqlite3', 'vscode', 'chromium',
'postgresql', 'superset', 'dbt_cloud', 'excel'
```

---

## Account Configuration

If a task requires login (see `tags` → `account`), credentials must be filled in under:

```
evaluation_examples/settings/<vendor>/<settings>.json
```

For example:

```bash
evaluation_examples/settings/google/settings.json
evaluation_examples/settings/snowflake/account.json
```

See [Account Guideline](../ACCOUNT_GUIDELINE.md) for setup instructions.

---

## Visualization and Analysis

We include scripts to evaluate scores, analyze top-performing tools, visualize task durations, and profile failures. Outputs can include CSV summaries and annotated screenshots for step-wise inspection.

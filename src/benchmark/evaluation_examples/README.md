# Evaluation Examples

This directory contains task definitions, dependencies, and evaluation configurations for benchmarking multimodal AI agents within the framework. Below is an explanation of its structure and the standardized JSON task format.

-----

## 📂 Directory Structure

  - `examples/` – The core directory containing all task definitions, organized by the primary tool used. The structure is `examples/<tool_name>/<task_uuid>/`.

-----

## 📝 Task Specification Format

Each task is fully defined by a JSON file named `<uuid>.json` located within its own directory. This file contains all the metadata, instructions, and configurations needed to set up and evaluate an agent on that task.

A full example (`1fe7d03d-d0d5-465b-987d-4583af499387.json`)

```json
{
  "id": "1fe7d03d-d0d5-465b-987d-4583af499387",
  "snapshot": "jupyter",
  "instruction": "Help me tune the AdaBoost Classifier in a VS Code notebook to achieve a 1.0 accuracy score on the famous Iris Dataset. Add codes only to the existing cells, and in the end run all the cells and save the jupyter notebook.\nHere is a step-by-step tutorial from an expert instructing you how to complete it:\nThis task requires you to tune the AdaBoost classifier to achieve a 1.0 accuracy. Follow the steps:\n1. First, locate the correct code cell to edit. Scroll through the notebook to find the section marked with the header **\"Building the AdaBoost Model\"**.\n2. In the code cell immediately following that header, find the line where the `AdaBoostClassifier` is defined. It will look similar to `abc = AdaBoostClassifier(n_estimators=1, learning_rate=0.1)`.\n3. Modify the hyperparameters in that line. Change the value of `n_estimators` from `1` to `40`.\n4. In the same line, change the value of `learning_rate` from `0.1` to `0.8`. The updated line should now be: `abc = AdaBoostClassifier(n_estimators=40, learning_rate=0.8)`.\n5. After editing the code, execute the entire notebook to apply the changes and see the new accuracy. To do this, click the **\"Run All\"** icon (looks like a double play symbol) in the notebook's top toolbar.\n6. Wait for all the cells to finish running. The output of the final cell will now display an \"Accuracy score\" of `1.0`.\n7. Finally, save the updated notebook by pressing the keyboard shortcut `Ctrl+S`.\nYou can follow the detailed GUI plan above using `pyautogui` or proactively tackle the task using Python code",
  "source": [
    "https://www.datacamp.com/tutorial/adaboost-classifier-python"
  ],
  "related_apps": [
    "vscode",
    "jupyter"
  ],
  "tags": [
    "cli+gui",
    "traditional_data_processing",
    "verbose"
  ],
  "action_number": 6,
  "config": [
    {
      "func": "upload_file_to_vm",
      "arguments": {
        "local_path": "AdaBoost.ipynb",
        "remote_path": "/home/user/Desktop/AdaBoost.ipynb"
      }
    },
    {
      "func": "upload_script_and_execute",
      "arguments": {
        "local_path": "init.sh",
        "remote_path": "/home/user/init.sh"
      }
    }
  ],
  "evaluation": {
    "func": "compare_notebook_outputs",
    "arguments": {
      "local_expected": "AdaBoost_gold.ipynb",
      "vm_result": "/home/user/Desktop/AdaBoost.ipynb"
    }
  },
  "counterpart": "e1da7d3d-2830-4376-a994-36cf53852303"
}
```

</details>

### 🔑 Key Fields Explained

  - **`id`**: A globally unique identifier (UUID) for the task.
  - **`instruction`**: The main prompt given to the agent. It describes the goal and can include a detailed step-by-step tutorial for the agent to follow.
  - **`config`**: A list of setup functions to run before the agent begins the task. Each function prepares the sandbox environment (e.g., uploading files, installing packages).
  - **`evaluation`**: The post-task evaluation metric. It defines the function used to check the agent's work against a ground-truth and assign a score.
  - **`action_number`**: The expected number of steps for a successful run, which can be used to set the `max_steps` limit for the agent.
  - **`tags`**: Descriptive labels used for filtering and analysis. Common tags include interface type (`cli`, `gui`, `cli+gui`), guidance style (`verbose`, `abstract`), and task domain (`data_warehousing`, etc.).
  - **`related_apps`**: A list of the primary software applications involved in the task.
  - **`source`**: A list of URLs or references indicating where the task was originally derived from.
  - **`counterpart`**: The ID of the corresponding task with an alternate instruction style (e.g., the `abstract` version of a `verbose` task).

-----

## ⚙️ How It Works: `config` and `evaluation`

The `config` and `evaluation` blocks use a dynamic dispatch system to run helper functions.

  - `"func"`: The name of a Python function located in `benchmark/helpers/config/` or `benchmark/helpers/evaluators/`.
  - `"arguments"`: A dictionary of keyword arguments that get passed directly to that function.

This design allows for creating new, reusable setup and evaluation logic without changing the core orchestrator code.

-----

## 📊 Task Output: `summary.json`

After each task run, the framework generates a `summary.json` file in the corresponding `results/` directory. This file is a complete record of the task and its outcome. It contains:

1.  All the original fields from the input `<uuid>.json` file.
2.  A `results` object, which is populated with the `TaskOutput` data, including:
      - The final `score` and any `eval_error`.
      - The agent's final `state` (e.g., `success`, `max_steps_error`).
      - A complete history of all `messages` between the agent and the system.
      - `total_tokens` and `total_timing` for the run.

This structured output makes it easy to perform the detailed analysis shown in the main paper.

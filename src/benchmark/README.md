# Creating New Tasks

This guide explains how to create new evaluation tasks by leveraging the existing structure. The key is to understand the relationship between the Python files in this directory and the example configurations found in the `evaluation_examples` folder.

## Project Structure

The project is organized as follows:

```
.
├── README.md
├── __init__.py
├── configuration.py
├── evaluation_examples/
├── general.py
├── jupyter.py
├── table.py
└── task.py
```

## How It Works

* **Evaluation Functions (`.py` files):** The Python files in this directory (e.g., `general.py`, `table.py`, `task.py`) contain the core logic for performing evaluations. Each file provides a set of related functions designed to assess a specific aspect of a task.

* **Task Setups (`evaluation_examples`):** The `evaluation_examples` directory contains practical examples of how to configure and define new tasks. Each example demonstrates how to use the evaluation functions from the Python files to build a complete evaluation pipeline.

To create a new task, you should look at the examples within `evaluation_examples` to understand how to structure your task configuration and then call the appropriate evaluation functions from the various `.py` files.

# 🚀 Creating New Evaluation Tasks

Welcome! This guide will walk you through creating new evaluation tasks by leveraging the project's modular structure. By combining pre-built evaluation functions with simple configurations, you can easily set up powerful new tests.

## 📂 Project Structure

The project is organized with a clear separation between evaluation logic and task configuration:

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

## ⚙️ How It Works

The system is designed around two core components:

* **🧩 Evaluation Functions (`.py` files):** The Python files in this directory (e.g., `general.py`, `table.py`, `task.py`) are the building blocks of our evaluation system. Each file contains a library of functions designed to assess specific aspects of a task.

* **📝 Task Setups (`evaluation_examples`):** The `evaluation_examples` directory contains practical examples that show you how to define new tasks. Think of these as recipes that combine the evaluation "ingredients" from the Python files to create a complete evaluation pipeline.

## 🏁 Getting Started: Your First Task

To create a new task, simply:

1.  **Explore the examples:** Dive into the `evaluation_examples` directory to find a setup that resembles what you want to build.
2.  **Configure your task:** Create a new configuration file based on the example.
3.  **Call the functions:** Use the evaluation functions from the various `.py` files to bring your task to life.

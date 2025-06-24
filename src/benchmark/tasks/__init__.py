# benchmark/__init__.py

# 1. Import the specific functions and classes you need from your submodules.
from .configuration import upload_file_to_vm, upload_script_and_execute
from .eval.general import compare_script_logs, compare_text_file
from .eval.jupyter import (
    are_jupyter_outputs_cleared,
    compare_ipynb_files,
    compare_jupyterlab_images,
    compare_notebook_cells,
    compare_notebook_outputs,
    evaluate_multiple_notebooks,
    is_jupyter_cell_executed,
)
from .eval.table import compare_csv
from .task import TaskInput, TaskOutput

CONFIG_DISPATCH = {
    "upload_file_to_vm": upload_file_to_vm,
    "upload_script_and_execute": upload_script_and_execute,
}

EVAL_DISPATCH = {
    "compare_csv": compare_csv,
    "compare_script_logs": compare_script_logs,
    "compare_text_file": compare_text_file,
    "compare_notebook_cells": compare_notebook_cells,
    "compare_notebook_outputs": compare_notebook_outputs,
    "is_jupyter_cell_executed": is_jupyter_cell_executed,
    "compare_ipynb_files": compare_ipynb_files,
    "compare_jupyterlab_images": compare_jupyterlab_images,
    "are_jupyter_outputs_cleared": are_jupyter_outputs_cleared,
    "evaluate_multiple_notebooks": evaluate_multiple_notebooks,  # function that orchestrates multiple Jupyter comparisons
}

# This controls what 'from benchmark import *' will import.
__all__ = [
    "CONFIG_DISPATCH",
    "EVAL_DISPATCH",
    "TaskInput",
    "TaskOutput",
]

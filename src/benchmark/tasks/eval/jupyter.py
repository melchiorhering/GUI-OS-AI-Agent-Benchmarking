import io
import shutil
from pathlib import Path
from typing import Any, Dict, List

import cv2
import nbformat
from smolagents import LogLevel

from agent.sandbox_agent import SandboxCodeAgent

from ..configuration import download_file_from_vm
from ..task import TaskInput


def compare_notebook_cells(
    agent: SandboxCodeAgent,
    task: TaskInput,
    local_expected: str,
    vm_result: str,
    **options,
) -> float:
    task.result_dir.mkdir(parents=True, exist_ok=True)
    vm_result_filename = Path(vm_result).name
    local_vm_result_path = task.result_dir / vm_result_filename
    expected_filename = Path(local_expected).name
    local_expected_reference_path = task.result_dir / expected_filename
    source_expected_file_path = task.task_dir / local_expected

    agent.logger.log(f"Initiating notebook CELL comparison for task '{task.uid}':", level=LogLevel.INFO)
    try:
        download_file_from_vm(agent, local_path=local_vm_result_path, remote_path=vm_result)
        if not source_expected_file_path.is_file():
            agent.logger.log(
                f"❌ Critical error: Local expected file not found at '{source_expected_file_path}'",
                level=LogLevel.ERROR,
            )
            return 0.0
        shutil.copy2(source_expected_file_path, local_expected_reference_path)
        with open(local_vm_result_path, "r", encoding="utf-8") as result_file:
            result_nb = nbformat.read(result_file, as_version=4)
        with open(local_expected_reference_path, "r", encoding="utf-8") as expected_file:
            expected_nb = nbformat.read(expected_file, as_version=4)
    except Exception as e:
        agent.logger.log(f"❌ Exception during notebook cell comparison prep: {e}", level=LogLevel.ERROR)
        return 0.0

    result_cells = result_nb.get("cells", [])
    expected_cells = expected_nb.get("cells", [])
    if len(result_cells) != len(expected_cells):
        agent.logger.log("🔎 Notebook cell count mismatch", level=LogLevel.INFO)
        return 0.0

    for result_cell, expected_cell in zip(result_cells, expected_cells, strict=True):
        if (
            result_cell["cell_type"] != expected_cell["cell_type"]
            or result_cell["source"].strip() != expected_cell["source"].strip()
        ):
            agent.logger.log("🔍 Cell type or source mismatch", level=LogLevel.INFO)
            return 0.0

    agent.logger.log("✅ Notebook cell comparison successful", level=LogLevel.INFO)
    return 1.0


def compare_notebook_outputs(
    agent: SandboxCodeAgent,
    task: TaskInput,
    local_expected: str,
    vm_result: str,
) -> float:
    """
    Compares the text outputs of cells in two Jupyter notebooks, following standard file handling.
    """
    task.result_dir.mkdir(parents=True, exist_ok=True)

    # --- Standardized Path Definitions ---
    vm_result_filename = Path(vm_result).name
    local_vm_result_path = task.result_dir / vm_result_filename
    expected_filename = Path(local_expected).name
    local_expected_reference_path = task.result_dir / expected_filename
    source_expected_file_path = task.task_dir / local_expected

    # --- Standardized Logging ---
    agent.logger.log(f"Initiating notebook OUTPUT comparison for task '{task.uid}':", level=LogLevel.INFO)
    agent.logger.log(f"  VM Result: '{vm_result}' -> Local: '{local_vm_result_path}'", level=LogLevel.DEBUG)
    agent.logger.log(
        f"  Local Expected: '{source_expected_file_path}' -> Local: '{local_expected_reference_path}'",
        level=LogLevel.DEBUG,
    )

    try:
        # --- Standardized File Preparation ---
        download_file_from_vm(agent, local_path=local_vm_result_path, remote_path=vm_result)
        if not source_expected_file_path.is_file():
            agent.logger.log(
                f"❌ Critical error: Local expected file not found at '{source_expected_file_path}'",
                level=LogLevel.ERROR,
            )
            return 0.0
        # Create an audit copy of the expected file in the results directory
        shutil.copy2(source_expected_file_path, local_expected_reference_path)

        with open(local_vm_result_path, "r", encoding="utf-8") as result_file:
            result_nb = nbformat.read(result_file, as_version=4)
        with open(local_expected_reference_path, "r", encoding="utf-8") as expected_file:
            expected_nb = nbformat.read(expected_file, as_version=4)

    except Exception as e:
        agent.logger.log(f"❌ Exception during notebook output comparison prep: {e}", level=LogLevel.ERROR)
        return 0.0

    # --- Comparison Logic ---
    result_cells = result_nb.get("cells", [])
    expected_cells = expected_nb.get("cells", [])

    if len(result_cells) != len(expected_cells):
        agent.logger.log("ℹ️ Notebook output comparison failed: Cell count mismatch.", level=LogLevel.INFO)
        return 0.0

    for result_cell, expected_cell in zip(result_cells, expected_cells, strict=False):
        if result_cell["cell_type"] != expected_cell["cell_type"]:
            print("Cell type mismatch!")
            return 0.0
        if result_cell["cell_type"] == "code":
            result_cell_outputs = [
                output
                for output in result_cell["outputs"]
                if (
                    "name" in output
                    and output["name"] == "stdout"
                    and "Requirement already satisfied:" not in output["text"]
                    and "Successfully installed" not in output["text"]
                )
                or ("data" in output and "text/plain" in output["data"])
            ]
            expected_cell_outputs = [
                output
                for output in expected_cell["outputs"]
                if ("name" in output and output["name"] == "stdout")
                or ("data" in output and "text/plain" in output["data"])
            ]
            if len(result_cell_outputs) != len(expected_cell_outputs):
                agent.logger.log(
                    f"ℹ️ Notebook output comparison failed: Length of the following output mismatch: result:{len(result_cell_outputs)} expected:{len(expected_cell_outputs)}.",
                    level=LogLevel.INFO,
                )
                return 0.0
            for result_output, expected_output in zip(result_cell_outputs, expected_cell_outputs, strict=False):
                if "name" in result_output and result_output != expected_output:
                    agent.logger.log(result_output)
                    agent.logger.log(expected_output)
                    return 0.0
                if (
                    "data" in result_output
                    and result_output["data"]["text/plain"] != expected_output["data"]["text/plain"]
                ):
                    agent.logger.log(result_output)
                    agent.logger.log(expected_output)
                    return 0.0
    return 1.0


def is_jupyter_cell_executed(
    agent: SandboxCodeAgent, task: TaskInput, vm_result: str, expected: Dict[str, Any], **options
) -> float:
    """Determine whether all cells in a Jupyter notebook are executed."""

    # --- Standardized Path Definitions ---
    vm_result_filename = Path(vm_result).name
    local_vm_result_path = task.result_dir / vm_result_filename

    # --- Standardized File Preparation ---
    download_file_from_vm(agent, local_path=local_vm_result_path, remote_path=vm_result)

    try:
        with io.open(local_vm_result_path, "r", encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=options.get("version", 4))
        cell_type = options.get("cell_type", "code")
        unexecuted = [
            idx for idx, cell in enumerate(nb.cells) if cell.cell_type == cell_type and not cell.get("execution_count")
        ]
        return 1.0 if unexecuted == expected else 0.0
    except Exception as e:
        agent.logger.log(f"❌ Exception during jupyter cell execution check: {e}", level=LogLevel.ERROR)
        return 0.0


def _sanitize_notebook_cells(nb: nbformat.NotebookNode) -> List[Dict[str, Any]]:
    """
    A helper function to create a simplified, comparable representation of a notebook.
    It extracts only the cell type, source, and text outputs, ignoring all metadata.
    """
    sanitized_cells = []
    for cell in nb.get("cells", []):
        # Keep only the most essential information
        sanitized_cell = {
            "cell_type": cell.get("cell_type"),
            "source": cell.get("source", "").strip(),
        }
        # For code cells, also capture a simplified representation of the output
        if sanitized_cell["cell_type"] == "code":
            outputs = [output.get("text", "").strip() for output in cell.get("outputs", []) if "text" in output]
            sanitized_cell["outputs"] = "\n".join(outputs)

        sanitized_cells.append(sanitized_cell)
    return sanitized_cells


def compare_ipynb_files(
    agent: SandboxCodeAgent,
    task: TaskInput,
    local_expected: str,
    vm_result: str,
    **options,
) -> float:
    """
    Compares two Jupyter notebooks by creating a 'sanitized' version of each
    that only includes essential cell information (type, source, outputs),
    effectively ignoring all metadata and execution counts.
    """
    task.result_dir.mkdir(parents=True, exist_ok=True)

    # --- Standardized Path Definitions ---
    vm_result_filename = Path(vm_result).name
    local_vm_result_path = task.result_dir / vm_result_filename
    expected_filename = Path(local_expected).name
    local_expected_reference_path = task.result_dir / expected_filename
    source_expected_file_path = task.task_dir / local_expected

    # --- Standardized Logging ---
    agent.logger.log(f"Initiating simplified notebook FILE comparison for task '{task.uid}':", level=LogLevel.INFO)
    agent.logger.log(f"  VM Result: '{vm_result}' -> Local: '{local_vm_result_path}'", level=LogLevel.DEBUG)
    agent.logger.log(
        f"  Local Expected: '{source_expected_file_path}' -> Local: '{local_expected_reference_path}'",
        level=LogLevel.DEBUG,
    )

    try:
        # --- Standardized File Preparation ---
        download_file_from_vm(agent, local_path=local_vm_result_path, remote_path=vm_result)
        if not source_expected_file_path.is_file():
            agent.logger.log(
                f"❌ Critical error: Local expected file not found at '{source_expected_file_path}'",
                level=LogLevel.ERROR,
            )
            return 0.0
        shutil.copy2(source_expected_file_path, local_expected_reference_path)

        with open(local_vm_result_path, "r", encoding="utf-8") as result_file:
            result_nb = nbformat.read(result_file, as_version=4)
        with open(local_expected_reference_path, "r", encoding="utf-8") as expected_file:
            expected_nb = nbformat.read(expected_file, as_version=4)

    except Exception as e:
        agent.logger.log(f"❌ Exception during notebook file comparison prep: {e}", level=LogLevel.ERROR)
        return 0.0

    # --- Simplified Comparison Logic ---
    sanitized_result = _sanitize_notebook_cells(result_nb)
    sanitized_expected = _sanitize_notebook_cells(expected_nb)

    if sanitized_result == sanitized_expected:
        agent.logger.log("✅ Notebook file comparison successful (simplified check).", level=LogLevel.INFO)
        return 1.0
    else:
        agent.logger.log(
            f"ℹ️ Notebook comparison failed: Sanitized content does not match. "
            f"VM Result ({local_vm_result_path}) vs Expected ({local_expected_reference_path})",
            level=LogLevel.INFO,
        )
        # For debugging, you could optionally log the sanitized versions
        # agent.logger.log(f"Result: {sanitized_result}", level=LogLevel.DEBUG)
        # agent.logger.log(f"Expected: {sanitized_expected}", level=LogLevel.DEBUG)
        return 0.0


def compare_jupyterlab_images(
    agent: SandboxCodeAgent,
    task: TaskInput,
    local_expected_image: str,
    vm_result_image: str,
    **options,
) -> float:
    """
    Compares two JupyterLab interface images downloaded from the VM,
    calculating their similarity using histogram comparison.
    """
    task.result_dir.mkdir(parents=True, exist_ok=True)

    vm_result_filename = Path(vm_result_image).name
    local_vm_result_path = task.result_dir / vm_result_filename
    expected_filename = Path(local_expected_image).name
    local_expected_reference_path = task.result_dir / expected_filename
    source_expected_file_path = task.task_dir / local_expected_image

    # Initial log to indicate the start of comparison
    agent.logger.log(f"🖼️ Starting JupyterLab image comparison for task '{task.uid}'.", level=LogLevel.INFO)
    agent.logger.log(
        f"  Comparing VM image '{vm_result_image}' with expected '{local_expected_image}'.",
        level=LogLevel.DEBUG,  # Use DEBUG for detailed paths
    )

    try:
        # Download the result image from the VM
        download_file_from_vm(agent, local_path=local_vm_result_path, remote_path=vm_result_image)

        # Ensure the local expected image exists
        if not source_expected_file_path.is_file():
            agent.logger.log(
                f"❌ Critical error: Local expected image file not found at '{source_expected_file_path}'",
                level=LogLevel.ERROR,
            )
            return 0.0
        shutil.copy2(source_expected_file_path, local_expected_reference_path)

        # Load images
        img1 = cv2.imread(str(local_expected_reference_path))
        img2 = cv2.imread(str(local_vm_result_path))

        if img1 is None:
            agent.logger.log(f"❌ Failed to load expected image: {local_expected_reference_path}", level=LogLevel.ERROR)
            return 0.0
        if img2 is None:
            agent.logger.log(f"❌ Failed to load result image: {local_vm_result_path}", level=LogLevel.ERROR)
            return 0.0

        # Convert to grayscale for histogram comparison
        img1_gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        img2_gray = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

        # Resize the larger image to match the dimensions of the smaller one
        h1, w1 = img1_gray.shape[:2]
        h2, w2 = img2_gray.shape[:2]

        if w1 * h1 > w2 * h2:  # img1 is larger by pixel count
            img1_resized = cv2.resize(img1_gray, (w2, h2), interpolation=cv2.INTER_AREA)
            img2_resized = img2_gray
        else:  # img2 is larger or equal size
            img2_resized = cv2.resize(img2_gray, (w1, h1), interpolation=cv2.INTER_AREA)
            img1_resized = img1_gray

        # Calculate histograms
        H1 = cv2.calcHist([img1_resized], [0], None, [256], [0, 256])
        H1 = cv2.normalize(H1, H1, 0, 1, cv2.NORM_MINMAX, -1)

        H2 = cv2.calcHist([img2_resized], [0], None, [256], [0, 256])
        H2 = cv2.normalize(H2, H2, 0, 1, cv2.NORM_MINMAX, -1)

        # Compare histograms (Correlation method)
        similarity = cv2.compareHist(H1, H2, cv2.HISTCMP_CORREL)

        similarity_threshold = options.get("similarity_threshold", 0.95)

        if similarity >= similarity_threshold:
            agent.logger.log(
                f"✅ Image comparison PASSED for '{task.uid}'. Similarity: {similarity:.4f} (Threshold: {similarity_threshold}).",
                level=LogLevel.INFO,
            )
            return 1.0
        else:
            agent.logger.log(
                f"❌ Image comparison FAILED for '{task.uid}'. Similarity: {similarity:.4f} (Threshold: {similarity_threshold}).",
                level=LogLevel.INFO,
            )
            return 0.0

    except Exception as e:
        agent.logger.log(
            f"❌ Exception during JupyterLab image comparison for task '{task.uid}': {e}", level=LogLevel.ERROR
        )

        return 0.0


def are_jupyter_outputs_cleared(
    agent: SandboxCodeAgent,
    task: TaskInput,
    vm_result: str,
    expected: List[int],
    **options,
) -> float:
    task.result_dir.mkdir(parents=True, exist_ok=True)
    vm_result_filename = Path(vm_result).name
    local_vm_result_path = task.result_dir / vm_result_filename

    agent.logger.log(f"🧹 Starting Jupyter outputs cleared check for task '{task.uid}'.", level=LogLevel.INFO)
    agent.logger.log(f"  Checking notebook: '{vm_result}'. Expected outputs in cells: {expected}", level=LogLevel.DEBUG)

    try:
        download_file_from_vm(agent, local_path=local_vm_result_path, remote_path=vm_result)

        with io.open(local_vm_result_path, "r", encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=options.get("version", 4))

        cell_type_to_check = options.get("cell_type", "code")

        cells_with_outputs_found = []

        for idx, cell in enumerate(nb.cells):
            if cell.cell_type == cell_type_to_check:
                has_meaningful_output = False
                if cell.get("outputs"):
                    for output in cell["outputs"]:
                        if "text" in output or "data" in output or "ename" in output:
                            has_meaningful_output = True
                            break

                if has_meaningful_output:
                    cells_with_outputs_found.append(idx)

        if sorted(cells_with_outputs_found) == sorted(expected):
            agent.logger.log(
                f"✅ Jupyter outputs cleared check PASSED for task '{task.uid}'. "
                f"Cells with outputs (found/expected): {cells_with_outputs_found}",
                level=LogLevel.INFO,
            )
            return 1.0
        else:
            agent.logger.log(
                f"❌ Jupyter outputs cleared check FAILED for task '{task.uid}'. "
                f"Expected outputs in cells: {expected}, Found outputs in cells: {cells_with_outputs_found}",
                level=LogLevel.INFO,
            )
            return 0.0

    except Exception as e:
        agent.logger.log(
            f"❌ Exception during Jupyter outputs cleared check for task '{task.uid}': {e}", level=LogLevel.ERROR
        )
        return 0.0


# Define the local DISPATCH_JUPYTER dictionary here
_JUPYTER_EVAL_FUNCTIONS = {
    "compare_notebook_cells": compare_notebook_cells,
    "compare_notebook_outputs": compare_notebook_outputs,
    "is_jupyter_cell_executed": is_jupyter_cell_executed,
    "compare_ipynb_files": compare_ipynb_files,
    "compare_jupyterlab_images": compare_jupyterlab_images,
    "are_jupyter_outputs_cleared": are_jupyter_outputs_cleared,
}


def evaluate_multiple_notebooks(
    agent: SandboxCodeAgent,
    task: TaskInput,
    operator: str,
    comparisons: List[Dict[str, Any]],
) -> float:
    if not comparisons:
        agent.logger.log(
            "❗ No comparisons defined for 'evaluate_multiple_notebooks'. Returning 0.0.", level=LogLevel.INFO
        )
        return 0.0

    sub_scores = []
    agent.logger.log(
        f"Starting multiple notebook evaluation for task '{task.uid}' with operator: '{operator.upper()}'",
        level=LogLevel.INFO,
    )

    for i, comp_def in enumerate(comparisons):
        comp_func_name = comp_def.get("func")
        comp_arguments = comp_def.get("arguments", {})

        # FIX: Check if comp_func_name is a string before using it.
        # This resolves the Pyright error.
        if isinstance(comp_func_name, str):
            comp_func = _JUPYTER_EVAL_FUNCTIONS.get(comp_func_name)
        else:
            comp_func = None

        if not comp_func:
            agent.logger.log(
                f"❌ Unknown or missing comparison function: '{comp_func_name}'. Skipping comparison {i + 1}.",
                level=LogLevel.ERROR,
            )
            sub_scores.append(0.0)
            continue

        try:
            score = comp_func(agent=agent, task=task, **comp_arguments)
            sub_scores.append(score)
            agent.logger.log(f"Sub-comparison {i + 1} ('{comp_func_name}') result: {score}", level=LogLevel.INFO)
        except Exception as e:
            agent.logger.log(f"❌ Error during sub-comparison {i + 1} ('{comp_func_name}'): {e}", level=LogLevel.ERROR)
            sub_scores.append(0.0)

    final_score = 0.0
    if operator.lower() == "and":
        final_score = 1.0 if all(s == 1.0 for s in sub_scores) else 0.0
        agent.logger.log(f"Aggregation using 'AND' ({sub_scores}): Final Score = {final_score}", level=LogLevel.INFO)
    elif operator.lower() == "or":
        final_score = 1.0 if any(s == 1.0 for s in sub_scores) else 0.0
        agent.logger.log(f"Aggregation using 'OR' ({sub_scores}): Final Score = {final_score}", level=LogLevel.INFO)
    else:
        agent.logger.log(
            f"❗ Invalid operator '{operator}'. Expected 'and' or 'or'. Returning 0.0.", level=LogLevel.ERROR
        )
        final_score = 0.0

    return final_score

import shutil
from pathlib import Path

import pandas as pd
from smolagents import LogLevel

from agent.sandbox_agent import SandboxCodeAgent

from ...tasks.configuration import download_file_from_vm
from ..task import TaskInput


def compare_csv(
    agent: SandboxCodeAgent,
    task: TaskInput,
    local_expected: str,
    vm_result: str,
    **options,
) -> float:
    """
    Compares a CSV file from a VM with a local expected CSV file using pandas.
    Returns 1.0 for a match, 0.0 otherwise.
    Options:
        - ignore_order (bool): Sort rows before comparing.
        - ignore_case (bool): Convert all data to lowercase.
        - strict (bool): If False, ignores whitespace differences in cells.
    """
    task.result_dir.mkdir(parents=True, exist_ok=True)

    vm_result_filename = Path(vm_result).name
    local_vm_result_path = task.result_dir / vm_result_filename
    expected_filename = Path(local_expected).name
    local_expected_reference_path = task.result_dir / expected_filename
    source_expected_file_path = task.task_dir / local_expected

    agent.logger.log(f"Initiating CSV comparison for task '{task.uid}':", level=LogLevel.INFO)
    agent.logger.log(f"  VM Result: '{vm_result}' -> Local: '{local_vm_result_path}'")
    agent.logger.log(
        f"  Local Expected: '{source_expected_file_path}' -> Local: '{local_expected_reference_path}'",
        level=LogLevel.DEBUG,
    )

    try:
        download_file_from_vm(agent, local_path=local_vm_result_path, remote_path=vm_result)
        if not source_expected_file_path.is_file():
            agent.logger.log(
                f"❌ Critical error: Local expected file not found at '{source_expected_file_path}'",
                level=LogLevel.ERROR,
            )
            return 0.0
        shutil.copy2(source_expected_file_path, local_expected_reference_path)

        # Read CSVs into pandas DataFrames
        df_result = pd.read_csv(local_vm_result_path)
        df_expected = pd.read_csv(local_expected_reference_path)

    except Exception as e:
        agent.logger.log(
            f"❌ Evaluation error during file preparation/reading: {type(e).__name__}: {e}",
            level=LogLevel.ERROR,
        )
        return 0.0

    # --- Normalize and compare DataFrames ---
    # Ensure column order is the same for comparison
    df_result = df_result.reindex(sorted(df_result.columns), axis=1)
    df_expected = df_expected.reindex(sorted(df_expected.columns), axis=1)

    # Process options
    if not options.get("strict", True):
        df_result = df_result.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        df_expected = df_expected.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    if options.get("ignore_case", False):
        df_result = df_result.applymap(lambda x: x.lower() if isinstance(x, str) else x)
        df_expected = df_expected.applymap(lambda x: x.lower() if isinstance(x, str) else x)

    # To ignore row order, we sort the entire DataFrame by all columns
    if options.get("ignore_order", False):
        # Reset index is crucial after sorting to make them comparable
        df_result = df_result.sort_values(by=list(df_result.columns)).reset_index(drop=True)
        df_expected = df_expected.sort_values(by=list(df_expected.columns)).reset_index(drop=True)

    # Use pandas' built-in method for robust comparison
    are_equal = df_result.equals(df_expected)

    agent.logger.log(
        f"📊 CSV Evaluation for '{vm_result_filename}' vs '{expected_filename}': Match = {are_equal}",
        level=LogLevel.INFO,
    )
    return float(are_equal)

import json
import os
from datetime import datetime
from functools import reduce
from typing import List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats


def multiple_results_spider2_v(directory_paths: List[str]) -> pd.DataFrame:
    """
    Reads 'result.txt' files from multiple directories, creating a DataFrame
    where each directory's scores appear in a separate column (score_1, score_2, etc.).

    Args:
        directory_paths (List[str]): A list of paths to the parent directories,
                                     each containing subdirectories with 'result.txt'.

    Returns:
        pd.DataFrame: A DataFrame with an 'id' column and a 'score_n' column
                      for each directory processed. Returns an empty DataFrame
                      if no valid files are found across all directories.
    """
    all_dataframes = []

    # 1. Loop through each directory path provided
    for i, directory_path in enumerate(directory_paths):
        data = []
        score_col_name = f"score_{i + 1}"

        # Normalize the path for consistency
        normalized_path = os.path.normpath(directory_path)

        if not os.path.isdir(normalized_path):
            print(f"Warning: Directory not found, skipping: {normalized_path}")
            continue

        # 2. Walk through the directory to find result files (same logic as before)
        for root, dirs, files in os.walk(normalized_path):
            if "result.txt" in files:
                uuid = os.path.basename(root)
                result_file_path = os.path.join(root, "result.txt")
                score = None

                try:
                    with open(result_file_path, "r") as f:
                        content = f.read().strip()
                        score = float(content)
                except (FileNotFoundError, ValueError) as e:
                    print(f"Warning: Could not read or parse score in {result_file_path}. Details: {e}")
                except Exception as e:
                    print(f"An unexpected error occurred with {result_file_path}: {e}")

                data.append({"id": uuid, score_col_name: score})

        # 3. Create a temporary DataFrame for the current directory
        if data:
            temp_df = pd.DataFrame(data)
            all_dataframes.append(temp_df)

    if not all_dataframes:
        return pd.DataFrame()

    # 4. Merge all individual DataFrames into one
    # We use an outer merge to ensure all IDs are included, with NaN for missing scores.
    merged_df = reduce(lambda left, right: pd.merge(left, right, on="id", how="outer"), all_dataframes)

    return merged_df


def multiple_results_smolagents(directory_paths: List[str]) -> pd.DataFrame:
    """
    Reads 'summary.json' files from multiple run directories and stacks them
    into a single "long format" DataFrame, adding a 'run' column to
    identify the source of each observation.

    Args:
        directory_paths (List[str]): A list of paths to the parent directories for each run.

    Returns:
        pd.DataFrame: A DataFrame with columns for 'id', 'run', 'tool',
                      'eval_score', and 'state'.
    """
    all_run_data = []

    # Loop through each run directory
    for i, directory_path in enumerate(directory_paths):
        run_name = f"run_{i + 1}"  # Create a name for the run, e.g., 'run_1'
        normalized_path = os.path.normpath(directory_path)

        if not os.path.isdir(normalized_path):
            print(f"Warning: Directory not found, skipping: {normalized_path}")
            continue

        # Walk through the directory to find summary files
        for root, dirs, files in os.walk(normalized_path):
            if "summary.json" in files:
                summary_file_path = os.path.join(root, "summary.json")

                try:
                    with open(summary_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    uid = data.get("uid")
                    if not uid:
                        print(f"Warning: Skipping {summary_file_path} due to missing 'uid'.")
                        continue

                    results_obj = data.get("results", {})

                    # Append all data for this summary, including the run name
                    all_run_data.append(
                        {
                            "id": uid,
                            "run": run_name,
                            "tool": data.get("tool"),
                            "eval_score": results_obj.get("score"),
                            "state": results_obj.get("state"),
                        }
                    )

                except (json.JSONDecodeError, Exception) as e:
                    print(f"Warning: Could not process file {summary_file_path}. Error: {e}")

    if not all_run_data:
        return pd.DataFrame(columns=["id", "run", "tool", "eval_score", "state"])

    # Create the final long DataFrame from all collected data
    long_df = pd.DataFrame(all_run_data)
    return long_df


def analyze_and_compare_setups(spider2_v_runs: List[str], smolagent_runs: List[str]) -> pd.DataFrame:
    """
    Loads, processes, and compares results from two different benchmark setups.

    This function:
    1. Loads "wide" format data from setup 1 (spider2_v).
    2. Loads "long" format data from setup 2 (smolagents).
    3. Calculates the average score and run count for each setup.
    4. Merges the results into a single comparison DataFrame.

    Args:
        spider2_v_runs (List[str]): List of directory paths for the spider2_v setup.
        smolagent_runs (List[str]): List of directory paths for the smolagents setup.

    Returns:
        pd.DataFrame: A DataFrame comparing the average scores of the two setups
                      for each task ID, with a consistent column structure.
    """
    print("--- Step 1: Loading data ---")
    df_spider2_v = multiple_results_spider2_v(spider2_v_runs)
    df_smolagents = multiple_results_smolagents(smolagent_runs)

    print("\n--- Step 2: Processing and calculating averages ---")

    # --- Process Setup 1 (spider2_v) ---
    if not df_spider2_v.empty:
        score_cols = [col for col in df_spider2_v.columns if col.startswith("score_")]
        df_spider2_v_avg = pd.DataFrame(
            {
                "id": df_spider2_v["id"],
                "avg_score_spider2_v": df_spider2_v[score_cols].mean(axis=1) if score_cols else np.nan,
                "run_count_spider2_v": df_spider2_v[score_cols].count(axis=1) if score_cols else 0,
            }
        ).set_index("id")
    else:
        df_spider2_v_avg = pd.DataFrame(columns=["avg_score_spider2_v", "run_count_spider2_v"])

    # --- Process Setup 2 (smolagents) ---
    if not df_smolagents.empty:
        df_smolagents_avg = df_smolagents.groupby("id")["eval_score"].agg(
            avg_score_smolagents="mean", run_count_smolagents="count"
        )
    else:
        df_smolagents_avg = pd.DataFrame(columns=["avg_score_smolagents", "run_count_smolagents"])

    print("Processed averages for both setups.")

    # --- Step 3: Merge for Final Comparison ---
    print("\n--- Step 3: Merging results ---")

    # Merge using the indexes. The outer join ensures all IDs are kept from both setups.
    final_df = df_spider2_v_avg.join(df_smolagents_avg, how="outer")

    # Add a column to see the performance difference
    final_df["score_difference"] = final_df["avg_score_smolagents"] - final_df["avg_score_spider2_v"]

    print("Merge complete. Final comparison table created.")

    # Return the DataFrame with 'id' as a column instead of the index
    return final_df.reset_index().rename(columns={"index": "id"})


def analyze_tool_usage_by_line(directory_paths: List[str]) -> pd.DataFrame:
    """
    Parses 'summary.json' files to analyze agent tool usage on a line-by-line basis,
    counting lines of code containing 'pyautogui' vs. plain 'python'.

    Args:
        directory_paths (List[str]): A list of paths to directories containing the results.

    Returns:
        pd.DataFrame: A DataFrame with columns for 'id', 'pyautogui_lines', 'python_lines',
                      'total_lines', and 'pyautogui_line_ratio'.
    """
    all_usage_data = []

    for directory_path in directory_paths:
        normalized_path = os.path.normpath(directory_path)
        if not os.path.isdir(normalized_path):
            print(f"Warning: Directory not found, skipping: {normalized_path}")
            continue

        for root, dirs, files in os.walk(normalized_path):
            if "summary.json" in files:
                summary_file_path = os.path.join(root, "summary.json")
                try:
                    with open(summary_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    uid = data.get("uid")
                    if not uid:
                        continue

                    # --- MODIFIED LOGIC: Initialize line counters per task ---
                    pyautogui_line_count = 0
                    total_line_count = 0

                    messages = data.get("results", {}).get("messages", [])
                    for message in messages:
                        if not isinstance(message, dict):
                            continue

                        tool_calls = message.get("tool_calls", [])
                        if not isinstance(tool_calls, list):
                            continue

                        for tool_call in tool_calls:
                            if not isinstance(tool_call, dict):
                                continue

                            arguments = tool_call.get("function", {}).get("arguments", "")

                            # --- MODIFIED LOGIC: Process each line of code ---
                            if isinstance(arguments, str) and arguments:
                                lines = arguments.splitlines()
                                total_line_count += len(lines)
                                for line in lines:
                                    # Strip leading/trailing whitespace from the line
                                    if "pyautogui" in line.strip():
                                        pyautogui_line_count += 1

                    # Only add data if there were any tool calls with code
                    if total_line_count > 0:
                        all_usage_data.append(
                            {
                                "id": uid,
                                "pyautogui_lines": pyautogui_line_count,
                                "total_lines": total_line_count,
                            }
                        )

                except (json.JSONDecodeError, Exception) as e:
                    print(f"Warning: Could not process tool usage in {summary_file_path}. Error: {e}")

    if not all_usage_data:
        return pd.DataFrame(columns=["id", "pyautogui_lines", "python_lines", "total_lines", "pyautogui_line_ratio"])

    # --- MODIFIED LOGIC: Create the DataFrame with new columns ---
    usage_df = pd.DataFrame(all_usage_data)

    # Calculate the number of plain python lines
    usage_df["python_lines"] = usage_df["total_lines"] - usage_df["pyautogui_lines"]

    # Calculate the new ratio based on lines of code
    usage_df["pyautogui_line_ratio"] = usage_df.apply(
        lambda row: row["pyautogui_lines"] / row["total_lines"] if row["total_lines"] > 0 else 0, axis=1
    )

    # Reorder columns for clarity
    return usage_df[["id", "pyautogui_lines", "python_lines", "total_lines", "pyautogui_line_ratio"]]


def extract_smolagents_timing(directory_paths: List[str]) -> pd.DataFrame:
    """
    Parses summary.json files to extract task duration for the Smolagents setup.
    """
    timing_data = []
    for dir_path in directory_paths:
        if not os.path.isdir(dir_path):
            print(f"Warning: Directory not found, skipping: {dir_path}")
            continue
        for root, _, files in os.walk(dir_path):
            if "summary.json" in files:
                summary_path = os.path.join(root, "summary.json")
                try:
                    with open(summary_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    uid = data.get("uid")
                    duration = data.get("results", {}).get("total_timing", {}).get("duration")
                    if uid and duration is not None:
                        timing_data.append({"id": uid, "duration_smolagents": float(duration)})
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    print(f"Warning: Could not process {summary_path}. Error: {e}")
    return pd.DataFrame(timing_data)


def extract_spider2_v_timing(directory_paths: List[str]) -> pd.DataFrame:
    """
    Parses trajectory.jsonl files to calculate total task duration for the Spider2-V setup.
    """
    timing_data = []
    for dir_path in directory_paths:
        if not os.path.isdir(dir_path):
            print(f"Warning: Directory not found, skipping: {dir_path}")
            continue
        for root, _, files in os.walk(dir_path):
            if "trajectory.jsonl" in files:
                uid = os.path.basename(root)
                trajectory_path = os.path.join(root, "trajectory.jsonl")
                timestamps = []
                try:
                    with open(trajectory_path, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                record = json.loads(line)
                                ts_str = record.get("action_timestamp")
                                if ts_str:
                                    timestamps.append(datetime.strptime(ts_str, "%Y%m%d@%H%M%S"))
                            except json.JSONDecodeError:
                                continue  # Skip malformed lines
                    if len(timestamps) > 1:
                        duration = (max(timestamps) - min(timestamps)).total_seconds()
                        timing_data.append({"id": uid, "duration_spider2_v": duration})
                except Exception as e:
                    print(f"Warning: Could not process {trajectory_path}. Error: {e}")
    return pd.DataFrame(timing_data)


def compare_and_plot_timing(smolagent_runs: List[str], spider2_v_runs: List[str]):
    """
    Loads timing data from both setups, merges it, performs a significance test,
    and generates a comparative box plot.
    """
    print("--- Loading and Processing Timing Data ---")
    df_smol = extract_smolagents_timing(smolagent_runs)
    df_spider = extract_spider2_v_timing(spider2_v_runs)

    if df_smol.empty and df_spider.empty:
        print("No timing data found for either setup.")
        return

    # Merge the two dataframes
    comparison_df = pd.merge(df_smol, df_spider, on="id", how="outer")

    # --- Perform Significance Test ---
    test_data = comparison_df.dropna(subset=["duration_smolagents", "duration_spider2_v"])
    if len(test_data) > 0:
        stat, p_value = stats.wilcoxon(test_data["duration_smolagents"], test_data["duration_spider2_v"])
        print("\n--- Significance Test for Duration (Wilcoxon) ---")
        print(f"Compared {len(test_data)} paired tasks.")
        print(f"P-value: {p_value:.4f}")
        if p_value < 0.05:
            print("Result: The difference in task duration is statistically significant.")
        else:
            print("Result: The difference in task duration is NOT statistically significant.")
    else:
        print("No paired data available for significance test.")

    # --- Create the Plot ---
    # Reshape the data into a "long" format for easier plotting with seaborn
    plot_data = pd.melt(
        comparison_df,
        id_vars=["id"],
        value_vars=["duration_smolagents", "duration_spider2_v"],
        var_name="Setup",
        value_name="Duration (seconds)",
    )
    plot_data["Setup"] = plot_data["Setup"].map(
        {"duration_smolagents": "Smolagents", "duration_spider2_v": "Spider2-V"}
    )

    plt.figure(figsize=(12, 8))
    sns.set_theme(style="whitegrid")
    sns.set_context("talk")

    sns.boxplot(
        x="Setup",
        y="Duration (seconds)",
        data=plot_data,
        palette={"Spider2-V": "#457b9d", "Smolagents": "#43aa8b"},
        hue="Setup",
    )

    plt.title("Comparison of Task Completion Time", fontsize=22)
    plt.xlabel("Framework Setup", fontsize=14)
    plt.ylabel("Total Duration per Task (seconds)", fontsize=14)
    plt.show()

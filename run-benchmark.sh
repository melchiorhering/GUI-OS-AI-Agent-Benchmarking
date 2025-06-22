#!/bin/bash

# A script to run the orchestrator benchmark multiple times,
# saving each run's results to a separate directory,
# and performing cleanup after each run.

# --- Configuration ---
NUM_RUNS=3
BASE_RESULTS_DIR="results"
TASK_INDEX="benchmark/evaluation_examples/test_jupyter.json"
TASKS_ROOT="benchmark/evaluation_examples/examples"
ORCHESTRATOR_SCRIPT="orchestrator.py"

# --- Main Loop ---
echo "Starting benchmark process for $NUM_RUNS runs..."
echo "================================================"

# Loop from 1 to NUM_RUNS
for i in $(seq 1 $NUM_RUNS)
do
  # Define the specific output directory for this run
  RUN_RESULTS_DIR="$BASE_RESULTS_DIR/run$i"

  echo ""
  echo "--- Starting Run $i/$NUM_RUNS ---"
  echo "Results will be saved to: $RUN_RESULTS_DIR"

  # Go into the src dir
  cd src
  # Execute the orchestrator script
  uv run "$ORCHESTRATOR_SCRIPT" \
      --task-index "$TASK_INDEX" \
      --tasks-root "$TASKS_ROOT" \
      --results-root "$RUN_RESULTS_DIR"

  # Check the exit code of the last command
  if [ $? -ne 0 ]; then
    echo "ERROR: Run $i failed. Aborting subsequent runs."
    exit 1
  fi

  echo "--- Finished Run $i/$NUM_RUNS. ---"

done

echo ""
echo "================================================"
echo "All $NUM_RUNS benchmark runs are complete."
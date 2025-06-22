import argparse
import json
import os
import signal
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict

from smolagents import LiteLLMModel, LogLevel

from agent import (
    LogColors,
    SandboxAgentLogger,
    SandboxCodeAgent,
    get_orchestrator_logger,
    observation_screenshot_callback,
)
from benchmark import (
    CONFIG_DISPATCH,
    EVAL_DISPATCH,
    TaskInput,
    TaskOutput,
)
from sandbox import SandboxVMConfig

# ───────────────────────────── Configuration ─────────────────────────────
DEFAULT_TASK_INDEX_PATH = Path("benchmark/evaluation_examples/test_jupyter.json")
DEFAULT_TASKS_ROOT_DIR = Path("benchmark/evaluation_examples/examples")
DEFAULT_RESULTS_ROOT_DIR = Path("results")
TASK_TIMEOUT_SECONDS = 12 * 60

PORT_KEYS = ["ssh", "vnc", "fastapi", "jupyter"]
START_PORT = 60000


# ─────────────────── Simplified Orchestrator Logging Setup ────────────────────
ORCHESTRATOR_LOG_FILE = Path("orchestrator.log")
orchestrator_logger = get_orchestrator_logger(log_file_path=ORCHESTRATOR_LOG_FILE)


# ───────────────────────────── Custom Divider Function ─────────────────────────────
def _get_divider(
    char: str = "=", length: int = 100, color: str = None, title: str = None, plain_text: bool = False
) -> str:
    """
    Generates a horizontal divider line.
    If plain_text is True, no ANSI color codes are included.
    """
    display_color = color if color and not plain_text else ""
    reset_color = LogColors.RESET if color and not plain_text else ""

    if title:
        title_display_length = len(title)
        content_length = title_display_length + 4  # for " | | "

        available_space = max(0, length - content_length)

        left_padding = char * (available_space // 2)
        right_padding = char * (available_space - (available_space // 2))

        return f"{display_color}{left_padding} | {title} | {right_padding}{reset_color}"
    else:
        return f"{display_color}{char * length}{reset_color}"


def generate_port_pool(
    start: int, max_conc: int, keys: list[str], out_file: str = "port_pool.json"
) -> list[Dict[str, int]]:
    pool = []
    port = start
    effective_max_conc = max(1, max_conc)
    for _ in range(effective_max_conc):
        mapping = {k: port + i for i, k in enumerate(keys)}
        pool.append(mapping)
        port += len(keys)

    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(pool, indent=2), encoding="utf-8")
    orchestrator_logger.info(f"Generated port pool saved to: {out_path}")
    return pool


# ───────────────────────────── Agent Configuration ─────────────────────────────
model = LiteLLMModel(
    model_id="openai/o4-mini-2025-04-16",
    api_key=os.getenv("OPENAI_API_KEY"),
)


# ───────────────── System Prompt / Instructions for the Agent ──────────────────
AGENT_PROMPT_PREFIX = """You are an expert autonomous agent in a sandboxed GUI environment. Your goal is to solve the given task by breaking it down into a sequence of steps.

### Core Workflow

For each step, follow this process:
1.  Think: First, explain your plan for the current step. State your goal and justify your chosen method.
2.  Act: Provide the complete Python code to execute your plan.

You will receive an observation (a screenshot for GUI actions or terminal output for code execution) after each action. You must analyze it to verify the outcome before proceeding to the next step.

---

### Available Methods

You must choose the best method for each step, either do a GUI action or use Python code to complete a action step.

- GUI Action: Use pyautogui for interacting with graphical elements.
    - Best for: Clicking buttons, navigating menus, and interacting with applications that have no direct code interface.
    - Crucial Rule for GUI: Perform only one or a very small set of closely related GUI actions per step. After each set of GUI actions, you must wait for the next observation (screenshot). Analyze the new screenshot to confirm your action was successful and the UI is in the expected state before planning the next GUI interaction. Do not chain many independent GUI actions without intermediate visual verification.
    - Forbidden Action: You cannot use pyautogui.locateCenterOnScreen or any other image-finding functions in pyautogui. You must determine coordinates by analyzing the provided screenshot and use absolute coordinates (e.g., pyautogui.click(x=100, y=200)).
    - Requirement: Always add a time.sleep() after actions that require loading time to ensure the UI is ready.

- Direct Code Execution: Directly run Python code for logic, file manipulation, and data processing and other actions.
    - Best for: Calculations, reading/writing files, making API calls, or any task not requiring direct GUI interaction.
    - Requirement: Always check the output or logs in the subsequent observation to confirm success and handle any errors. When you think you are done call the final_answer tool.
    - Tip: Your Jupyter kernel is actived from ~/Desktop so keep in mind that you start from there.
    - You will be provided with all currently installed Python packages, this so you know what packages you can use. It is possible to install new packages, BUT DO THIS ONLY WHEN REALLY NEEDED; To do so you can use the `!uv pip install <package>` or `!pip install <package>` code

---

### Task Completion and Submission

Once the task is fully accomplished and verified, you must conclude the mission by calling the `final_answer` tool. This is the final and most critical step.

Function Signature:
`final_answer(summary: str)`
- The `summary` must be a short string literal summarizing your accomplishment. Do not pass variables.

Execution Mandate:
The `final_answer()` call must be executed in a standalone code block. No other code, comments, or commands can be in the same execution step.

---

Correct Usage Example:

You will submit a code block containing ONLY the final answer call.
```python
final_answer("I successfully downloaded the report and extracted the key figures into 'results.csv'.")
```

---

Incorrect Usage Examples:

- Do not include other commands or print statements:
    ```python
    # Incorrect
    print("Task is complete, submitting final answer.")
    final_answer("I created the file.")
    ```

- Do not combine it on a single line:
    ```python
    # Incorrect
    import os; final_answer("I listed the files.")
    ```

- Do not define variables or perform other logic in the same block:
    ```python
    # Incorrect
    summary_text = "The plot was generated and saved as 'plot.png'."
    final_answer(summary_text)
    ```
---

Think before you act, so check if you really need a GUI action step or if you can perform the task by just running Python code and looking at the logs and output
TASK TO COMPLETE:
<task>
{complete_task}
</task>
"""

# ───────────────────── Core Task Processing Logic ──────────────────────


def _save_error_log(task_input: TaskInput, error_type: str, exception: Exception, tb_str: str) -> Path:
    """Helper function to save detailed error logs to a file."""
    error_log_dir = task_input.result_dir / "logs"
    error_log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    error_filename = f"{task_input.uid}_{error_type}_error_{timestamp}.log"
    error_log_path = error_log_dir / error_filename

    content = f"Error Type: {error_type}\n"
    content += f"Timestamp: {datetime.now().isoformat()}\n"
    content += f"Task UID: {task_input.uid}\n"
    content += f"Exception: {exception}\n\n"
    content += "Traceback:\n"
    content += tb_str

    error_log_path.write_text(content, encoding="utf-8")
    return error_log_path


def handle_setup(agent: SandboxCodeAgent, task_input: TaskInput):
    """Handles the 'config' block from the task JSON."""
    orchestrator_logger.info("Executing setup steps...", extra={"task_uid": task_input.uid})
    for step in task_input.config:
        func_name = step.get("func")
        arguments = step.get("arguments", {})
        if func_name in CONFIG_DISPATCH:
            CONFIG_DISPATCH[func_name](agent=agent, task=task_input, **arguments)
        else:
            orchestrator_logger.warning(
                f"Unknown setup function: {func_name}. Skipping.", extra={"task_uid": task_input.uid}
            )


def handle_evaluation(agent: SandboxCodeAgent, task_input: TaskInput):
    """Handles the 'evaluation' block from the task JSON."""
    orchestrator_logger.info("Executing evaluation step...", extra={"task_uid": task_input.uid})
    eval_config = task_input.evaluation
    func_name = eval_config.get("func")
    arguments = eval_config.get("arguments", {})

    if not func_name:
        orchestrator_logger.info(
            "No evaluation function defined. Skipping evaluation.", extra={"task_uid": task_input.uid}
        )
        task_input.output.score = -1.0
        return

    if func_name in EVAL_DISPATCH:
        try:
            score = EVAL_DISPATCH[func_name](agent=agent, task=task_input, **arguments)
            task_input.output.score = float(score)
            orchestrator_logger.info(
                f"Evaluation complete. Score assigned: {task_input.output.score}", extra={"task_uid": task_input.uid}
            )
        except Exception as e:
            tb_str = traceback.format_exc()
            error_log_path = _save_error_log(task_input, "EVALUATION_ERROR", e, tb_str)
            task_input.output.score = 0.0
            task_input.output.eval_error = f"Evaluation function '{func_name}' failed: {e}"
            task_input.output.error_log_path = str(error_log_path.relative_to(task_input.result_dir))
            orchestrator_logger.error(
                f"Error during evaluation of '{func_name}': {e}. Details in {task_input.output.error_log_path}",
                extra={"task_uid": task_input.uid},
                exc_info=False,
            )
    else:
        task_input.output.score = 0.0
        task_input.output.eval_error = f"Unknown evaluation function: {func_name}"
        orchestrator_logger.warning(f"{task_input.output.eval_error}", extra={"task_uid": task_input.uid})


def run_and_process_task(agent: SandboxCodeAgent, task_input: TaskInput, max_steps: int = 15):
    """
    Runs a single task, including setup, execution, evaluation, and saving.
    """
    orchestrator_logger.info(
        _get_divider(title=f"Processing Task: {task_input.uid[:8]} - '{task_input.prompt[:50]}...'")
    )

    try:
        handle_setup(agent, task_input)

        # Add initial image to the task
        # init_image = initial_state_callback(agent)
        orchestrator_logger.info("Initial screenshot taken.", extra={"task_uid": task_input.uid})

        agent_result = agent.run(
            AGENT_PROMPT_PREFIX.format(complete_task=task_input.prompt, steps=task_input.steps),
            max_steps=max_steps,
            # images=[init_image]
        )
        if isinstance(agent.logger, SandboxAgentLogger):
            # If it is, we know it has the special save methods, so we call them.
            # Note the indentation.
            print("SandboxAgentLogger detected. Saving artifacts...")
            agent.logger.save_log_file(directory=task_input.result_dir, filename="full_run_log.html")
            agent.logger.save_agent_tree(agent, directory=task_input.result_dir, filename="agent_structure.svg")

        task_input.output = TaskOutput(source_result=agent_result)

        orchestrator_logger.info(
            f"Agent finished with state: '{task_input.output.state}'. Proceeding to evaluation.",
            extra={"task_uid": task_input.uid},
        )
        handle_evaluation(agent, task_input)

    except Exception as e:
        tb_str = traceback.format_exc()
        error_log_path = _save_error_log(task_input, "TASK_EXECUTION_ERROR", e, tb_str)
        orchestrator_logger.error(
            f"An unexpected error occurred during task execution: {e}. Details in {error_log_path.relative_to(task_input.result_dir)}",
            extra={"task_uid": task_input.uid},
            exc_info=False,
        )
        if not hasattr(task_input, "output") or not task_input.output:
            task_input.output = TaskOutput()

        task_input.output.eval_error = f"Orchestrator error: {e}\n{tb_str}"
        task_input.output.score = 0.0
        task_input.output.error_log_path = str(error_log_path.relative_to(task_input.result_dir))

    finally:
        task_input.save_result_summary()
        summary_path = task_input.result_dir / "summary.json"
        orchestrator_logger.info(f"Summary saved to: {summary_path}", extra={"task_uid": task_input.uid})

        orchestrator_logger.info(_get_divider(title=f"Task {task_input.uid[:8]} Summary", char="-", length=60))

        if task_input.output:
            timing_display = "N/A"
            if task_input.output.total_timing and task_input.output.total_timing.get("duration") is not None:
                timing_display = f"{task_input.output.total_timing['duration']:.2f}"

            orchestrator_logger.info(f"UID:    {task_input.uid}", extra={"task_uid": task_input.uid})
            orchestrator_logger.info(f"State:  {task_input.output.state}", extra={"task_uid": task_input.uid})
            orchestrator_logger.info(f"Score:  {task_input.output.score}", extra={"task_uid": task_input.uid})
            orchestrator_logger.info(f"Timing: {timing_display} seconds", extra={"task_uid": task_input.uid})
            if task_input.output.eval_error:
                orchestrator_logger.error(
                    f"Eval Error: {task_input.output.eval_error.splitlines()[0]}...", extra={"task_uid": task_input.uid}
                )
                if task_input.output.error_log_path:
                    orchestrator_logger.error(
                        f"Full error log: {task_input.result_dir / task_input.output.error_log_path}",
                        extra={"task_uid": task_input.uid},
                    )
        else:
            orchestrator_logger.error(
                "State: ERROR (No output generated due to critical failure)", extra={"task_uid": task_input.uid}
            )
        orchestrator_logger.info(_get_divider(char="=", length=60) + "\n")


def run_single_task_worker(
    task_index: int, total_tasks: int, tool: str, uid: str, port_config: dict, args: argparse.Namespace
) -> TaskInput:
    """
    Encapsulates all logic for running a single task, making it suitable for a thread pool.
    Returns the TaskInput object for further processing in the main thread.
    """
    orchestrator_logger.info(
        _get_divider(title=f"Worker (Task {task_index + 1}/{total_tasks}): Starting {uid[:8]} (Tool: {tool.upper()})")
    )

    task_input = TaskInput(
        uid=uid,
        tool=tool,
        prompt="Initial placeholder prompt",
        root_dir=args.tasks_root,
        results_root_dir=args.results_root,
        output=TaskOutput(score=0.0, state="INITIALIZING", eval_error="Not started"),
    )

    try:
        task_input = TaskInput.from_file(
            tool=tool,
            uid=uid,
            root=args.tasks_root,
            results_root=args.results_root,
        )
        orchestrator_logger.info(
            "Loaded task definition.", extra={"task_uid": uid, "task_idx": task_index, "total_tasks": total_tasks}
        )
    except FileNotFoundError as e:
        tb_str = traceback.format_exc()
        error_log_path = _save_error_log(task_input, "TASK_DEFINITION_ERROR", e, tb_str)
        orchestrator_logger.error(
            f"Task definition file not found in {args.tasks_root / tool}. Details in {error_log_path.relative_to(task_input.result_dir)}. Skipping this task.",
            extra={"task_uid": uid, "task_idx": task_index, "total_tasks": total_tasks},
            exc_info=False,
        )
        task_input.output.score = 0.0
        task_input.output.state = "SETUP_ERROR"
        task_input.output.eval_error = f"Task definition file not found: {uid}"
        task_input.output.error_log_path = str(error_log_path.relative_to(task_input.result_dir))
        return task_input

    agent = None
    try:
        # We directly use the provided port_config
        ports = port_config
        orchestrator_logger.info(
            f"Assigned ports: {ports}", extra={"task_uid": uid, "task_idx": task_index, "total_tasks": total_tasks}
        )

        sandbox_config = SandboxVMConfig(
            container_name=uid,
            # prefix=tool,
            shared_dir=task_input.result_dir,
            host_ssh_port=ports["ssh"],
            host_vnc_port=ports["vnc"],
            host_sandbox_fastapi_server_port=ports["fastapi"],
            host_sandbox_jupyter_kernel_port=ports["jupyter"],
        )
        orchestrator_logger.info(
            f"Sandbox config created for container '{sandbox_config.container_name}'.",
            extra={"task_uid": uid, "task_idx": task_index, "total_tasks": total_tasks},
        )

        # Customized agent logger
        agent_logger = SandboxAgentLogger(level=LogLevel.INFO)
        agent = SandboxCodeAgent(
            description="This agent runs in a sandboxed environment and can execute code.",
            tools=[],
            model=model,
            step_callbacks=[observation_screenshot_callback],
            executor_type="sandbox",
            executor_kwargs={"config": sandbox_config},
            use_structured_outputs_internally=True,
            return_full_result=True,
            # planning_interval=3, # Can try this
            logger=agent_logger,
        )
        orchestrator_logger.info(
            "Agent initialized for execution.",
            extra={"task_uid": uid, "task_idx": task_index, "total_tasks": total_tasks},
        )
        run_and_process_task(agent, task_input)

    except Exception as e:
        tb_str = traceback.format_exc()
        error_log_path = _save_error_log(task_input, "ORCHESTRATOR_WORKER_ERROR", e, tb_str)
        orchestrator_logger.error(
            f"Failed to process task due to orchestrator error: {e}. Details in {error_log_path.relative_to(task_input.result_dir)}",
            extra={"task_uid": uid, "task_idx": task_index, "total_tasks": total_tasks},
            exc_info=False,
        )
        if not hasattr(task_input, "output") or not task_input.output:
            task_input.output = TaskOutput()
        task_input.output.score = 0.0
        task_input.output.state = "ORCHESTRATOR_ERROR"
        task_input.output.eval_error = f"Orchestrator error in worker: {e}\n{tb_str}"
        task_input.output.error_log_path = str(error_log_path.relative_to(task_input.result_dir))
    finally:
        if agent:
            orchestrator_logger.info(
                "Cleaning up agent resources.",
                extra={"task_uid": uid, "task_idx": task_index, "total_tasks": total_tasks},
            )
            agent.cleanup()
        orchestrator_logger.info(
            _get_divider(title=f"Worker (Task {task_index + 1}/{total_tasks}): Finished {uid[:8]}", char="-", length=60)
        )

    return task_input


# ────────────────────────── NEW: Timeout Handler for Sequential Code ──────────────────
class Timeout:
    """
    Context manager to enforce a timeout on a block of code using signals.
    NOTE: This will not work on Windows, as `signal.alarm` is not available.
    """

    def __init__(self, seconds=1, error_message="Timeout after {} seconds".format):
        self.seconds = seconds
        self.error_message = error_message(seconds)

    def _handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)

    def __enter__(self):
        if sys.platform != "win32":
            signal.signal(signal.SIGALRM, self._handle_timeout)
            signal.alarm(self.seconds)

    def __exit__(self, type, value, traceback):
        if sys.platform != "win32":
            signal.alarm(0)  # Disable the alarm


# ────────────────────────── Main Orchestrator Block ───────────────────────────
def main(args):
    """Initializes and orchestrates running all specified tasks concurrently."""

    orchestrator_logger.info("Initializing Benchmark Runner...")
    orchestrator_logger.info(f"Task index path: {args.task_index}")
    orchestrator_logger.info(f"Tasks root directory: {args.tasks_root}")
    orchestrator_logger.info(f"Results root directory: {args.results_root}")

    try:
        with open(args.task_index, "r") as f:
            task_index = json.load(f)
        orchestrator_logger.info(f"Successfully loaded task index from {args.task_index}")
    except FileNotFoundError:
        orchestrator_logger.critical(f"Error: Task index file not found at {args.task_index}. Exiting.", exc_info=True)
        return
    except json.JSONDecodeError:
        orchestrator_logger.critical(
            f"Error: Invalid JSON in task index file at {args.task_index}. Exiting.", exc_info=True
        )
        return

    # We only need one set of ports, which will be reused for each task.
    # Note: `generate_port_pool` with max_conc=1 returns a list with one item.
    port_config = generate_port_pool(START_PORT, 1, PORT_KEYS)[0]
    orchestrator_logger.info(f"Using single set of ports for all tasks: {port_config}")

    all_tasks = [(tool, uid) for tool, uids in task_index.items() for uid in uids]
    total_tasks_count = len(all_tasks)

    orchestrator_logger.info(f"Found {total_tasks_count} tasks to run sequentially.")

    # A simple for loop replaces the ProcessPoolExecutor
    for i, (tool, uid) in enumerate(all_tasks):
        extra_info = {"task_uid": uid, "task_idx": i, "total_tasks": total_tasks_count}
        orchestrator_logger.info(f"Starting Task {i + 1}/{total_tasks_count}: {uid} (Tool: {tool})", extra=extra_info)

        task_input_result = None
        try:
            # Use the Timeout context manager around the worker call
            with Timeout(seconds=TASK_TIMEOUT_SECONDS):
                task_input_result = run_single_task_worker(i, total_tasks_count, tool, uid, port_config, args)

            orchestrator_logger.info(
                f"✅ Task {uid} ({tool}) finished. Final State: {task_input_result.output.state}, Score: {task_input_result.output.score}",
                extra=extra_info,
            )

        except TimeoutError as e:
            orchestrator_logger.error(
                f"❌ Task {uid} ({tool}) timed out after {TASK_TIMEOUT_SECONDS / 60} minutes. Marking as TIMEOUT.",
                extra=extra_info,
            )
            # Create a placeholder result for timed-out tasks
            task_input_result = TaskInput(
                uid=uid,
                tool=tool,
                prompt="Task timed out",
                root_dir=args.tasks_root,
                results_root_dir=args.results_root,
                output=TaskOutput(score=0.0, state="TIMED_OUT", eval_error=str(e)),
            )
            task_input_result.save_result_summary()

        except Exception as e:
            tb_str = traceback.format_exc()
            orchestrator_logger.error(
                f"❌ Task {uid} ({tool}) failed with an unexpected exception: {e}", extra=extra_info
            )
            # Create placeholder result for failed tasks
            if task_input_result is None:
                task_input_result = TaskInput(
                    uid=uid,
                    tool=tool,
                    prompt="Task failed",
                    root_dir=args.tasks_root,
                    results_root_dir=args.results_root,
                )
            _save_error_log(task_input_result, "SEQUENTIAL_RUNNER_ERROR", e, tb_str)
            task_input_result.output.score = 0.0
            task_input_result.output.state = "ORCHESTRATOR_ERROR"
            task_input_result.save_result_summary()

    orchestrator_logger.info("\n--- All tasks processed. Benchmark run complete. ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run benchmark tasks sequentially using a code agent.")
    # The concurrency argument is removed as it's not applicable.
    parser.add_argument(
        "--task-index", type=Path, default=DEFAULT_TASK_INDEX_PATH, help="Path to the JSON file listing tasks to run."
    )
    parser.add_argument(
        "--tasks-root",
        type=Path,
        default=DEFAULT_TASKS_ROOT_DIR,
        help="Root directory where detailed task JSON files are stored.",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=DEFAULT_RESULTS_ROOT_DIR,
        help="Root directory where results will be saved.",
    )

    args = parser.parse_args()
    try:
        main(args)
    except KeyboardInterrupt:
        orchestrator_logger.info("\nKeyboard interrupt detected. Shutting down gracefully.")
    except Exception as e:
        critical_error_log_path = DEFAULT_RESULTS_ROOT_DIR / "orchestrator_critical_errors"
        critical_error_log_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        error_filename = f"orchestrator_critical_error_{timestamp}.log"
        full_error_path = critical_error_log_path / error_filename

        tb_str = traceback.format_exc()
        content = "Critical Orchestrator Error\n"
        content += f"Timestamp: {datetime.now().isoformat()}\n"
        content += f"Exception: {e}\n\n"
        content += "Traceback:\n"
        content += tb_str
        full_error_path.write_text(content, encoding="utf-8")

        orchestrator_logger.critical(
            f"\nAn unexpected orchestrator error occurred in main execution: {e}. Full traceback saved to {full_error_path}",
            exc_info=False,
            extra={
                "task_uid": None,
                "task_idx": None,
                "total_tasks": None,
            },
        )

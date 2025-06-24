import json
import traceback
from pathlib import Path
from typing import Any, Callable, Dict

from smolagents import LiteLLMModel, LogLevel

from agent import (
    SandboxAgentLogger,
    SandboxCodeAgent,
    observation_screenshot_callback,
)
from benchmark.tasks import (
    CONFIG_DISPATCH,
    EVAL_DISPATCH,
    TaskInput,
    TaskOutput,
)
from sandbox import SandboxVMConfig

from .utils import Timeout, _get_divider, _save_error_log


class Orchestrator:
    """
    Orchestrates the running, evaluation, and logging of benchmark tasks.
    """

    def __init__(
        self,
        model: LiteLLMModel,
        tasks_root_dir: Path,
        results_root_dir: Path,
        logger: Any,  # Should be a logging.Logger instance
        port_config: Dict[str, int],
        agent_prompt_template: str,
        config_dispatch: Dict[str, Callable] = CONFIG_DISPATCH,
        eval_dispatch: Dict[str, Callable] = EVAL_DISPATCH,
        task_timeout: int = 12 * 60,
        max_agent_steps: int = 15,
    ):
        self.model = model
        self.tasks_root_dir = tasks_root_dir
        self.results_root_dir = results_root_dir
        self.logger = logger
        self.port_config = port_config
        self.config_dispatch = config_dispatch
        self.eval_dispatch = eval_dispatch
        self.agent_prompt_template = agent_prompt_template
        self.task_timeout = task_timeout
        self.max_agent_steps = max_agent_steps

    def run_benchmark(self, task_index_path: Path):
        """Loads tasks from an index file and runs them sequentially."""
        self.logger.info("Initializing Benchmark Runner...")
        try:
            with open(task_index_path, "r") as f:
                task_index = json.load(f)
            self.logger.info(f"Successfully loaded task index from {task_index_path}")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.critical(f"Error loading task index file: {e}", exc_info=True)
            return

        all_tasks = [(tool, uid) for tool, uids in task_index.items() for uid in uids]
        total_tasks_count = len(all_tasks)
        self.logger.info(f"Found {total_tasks_count} tasks to run sequentially.")

        for i, (tool, uid) in enumerate(all_tasks):
            self._run_single_task_with_timeout(i, total_tasks_count, tool, uid)

        self.logger.info("\n--- All tasks processed. Benchmark run complete. ---")

    def _run_single_task_with_timeout(self, i: int, total_tasks_count: int, tool: str, uid: str):
        """Wraps a single task run with a timeout."""
        extra_info = {"task_uid": uid, "task_idx": i, "total_tasks": total_tasks_count}
        self.logger.info(f"Starting Task {i + 1}/{total_tasks_count}: {uid} (Tool: {tool})", extra=extra_info)

        task_input_result = None
        try:
            with Timeout(seconds=self.task_timeout):
                task_input_result = self._task_worker(i, total_tasks_count, tool, uid)

            if task_input_result and task_input_result.output:
                self.logger.info(
                    f"✅ Task {uid} ({tool}) finished. Final State: {task_input_result.output.state}, Score: {task_input_result.output.score}",
                    extra=extra_info,
                )

        except TimeoutError as e:
            self.logger.error(
                f"❌ Task {uid} ({tool}) timed out after {self.task_timeout / 60} minutes.", extra=extra_info
            )
            task_input_result = TaskInput(
                uid=uid,
                tool=tool,
                prompt="Task timed out",
                root_dir=self.tasks_root_dir,
                results_root_dir=self.results_root_dir,
                output=TaskOutput(score=0.0, state="TIMED_OUT", eval_error=str(e)),
            )
            task_input_result.save_result_summary()
        except Exception as e:
            self.logger.error(f"❌ Task {uid} ({tool}) failed with an unexpected exception: {e}", extra=extra_info)
            if task_input_result is None:
                task_input_result = TaskInput(
                    uid=uid,
                    tool=tool,
                    prompt="Task failed",
                    root_dir=self.tasks_root_dir,
                    results_root_dir=self.results_root_dir,
                )
            tb_str = traceback.format_exc()
            _save_error_log(task_input_result, "ORCHESTRATOR_ERROR", e, tb_str)
            if not task_input_result.output:
                task_input_result.output = TaskOutput()
            task_input_result.output.score = 0.0
            task_input_result.output.state = "ORCHESTRATOR_ERROR"
            task_input_result.save_result_summary()

    def _task_worker(self, task_index: int, total_tasks: int, tool: str, uid: str) -> TaskInput:
        """Fully implemented task worker method."""
        self.logger.info(
            _get_divider(
                title=f"Worker (Task {task_index + 1}/{total_tasks}): Starting {uid[:8]} (Tool: {tool.upper()})"
            )
        )

        task_input = TaskInput(
            uid=uid,
            tool=tool,
            prompt="Initial placeholder prompt",
            root_dir=self.tasks_root_dir,
            results_root_dir=self.results_root_dir,
            output=TaskOutput(score=0.0, state="INITIALIZING", eval_error="Not started"),
        )
        try:
            task_input = TaskInput.from_file(
                tool=tool, uid=uid, root=self.tasks_root_dir, results_root=self.results_root_dir
            )
            self.logger.info("Loaded task definition.", extra={"task_uid": uid})
        except FileNotFoundError as e:
            tb_str = traceback.format_exc()
            _save_error_log(task_input, "TASK_DEFINITION_ERROR", e, tb_str)
            self.logger.error("Task definition file not found. Skipping.", extra={"task_uid": uid}, exc_info=False)
            task_input.output.state = "SETUP_ERROR"
            return task_input

        agent = None
        try:
            self.logger.info(f"Assigned ports: {self.port_config}", extra={"task_uid": uid})
            # FIX: Explicitly map the dictionary keys to the constructor parameters
            # instead of using dictionary unpacking (**).
            sandbox_config = SandboxVMConfig(
                container_name=uid,
                shared_dir=task_input.result_dir,
                host_ssh_port=self.port_config["ssh"],
                host_vnc_port=self.port_config["vnc"],
                host_sandbox_fastapi_server_port=self.port_config["fastapi"],
                host_sandbox_jupyter_kernel_port=self.port_config["jupyter"],
            )
            self.logger.info(f"Sandbox config created: {sandbox_config.container_name}", extra={"task_uid": uid})

            agent_logger = SandboxAgentLogger(level=LogLevel.INFO)
            agent = SandboxCodeAgent(
                description="Sandbox agent",
                tools=[],
                model=self.model,
                step_callbacks=[observation_screenshot_callback],
                executor_type="sandbox",
                executor_kwargs={"config": sandbox_config},
                use_structured_outputs_internally=True,
                return_full_result=True,
                logger=agent_logger,
            )
            self.logger.info("Agent initialized.", extra={"task_uid": uid})
            self._process_task(agent, task_input)
        except Exception as e:
            tb_str = traceback.format_exc()
            _save_error_log(task_input, "WORKER_ERROR", e, tb_str)
            self.logger.error(f"Worker failed: {e}", extra={"task_uid": uid}, exc_info=False)
            task_input.output.state = "ORCHESTRATOR_ERROR"
        finally:
            if agent:
                self.logger.info("Cleaning up agent.", extra={"task_uid": uid})
                agent.cleanup()

        self.logger.info(_get_divider(title=f"Worker Finished: {uid[:8]}", char="-"))
        return task_input

    def _process_task(self, agent: SandboxCodeAgent, task_input: TaskInput):
        """Fully implemented processing method."""
        self.logger.info(_get_divider(title=f"Processing Task: {task_input.uid[:8]}"))
        try:
            self._handle_setup(agent, task_input)
            agent_result = agent.run(
                self.agent_prompt_template.format(complete_task=task_input.prompt, steps=task_input.steps),
                max_steps=self.max_agent_steps,
            )
            if isinstance(agent.logger, SandboxAgentLogger):
                agent.logger.save_log_file(directory=task_input.result_dir, filename="full_run_log.html")
                agent.logger.save_agent_tree(agent, directory=task_input.result_dir, filename="agent_structure.svg")

            task_input.output = TaskOutput(source_result=agent_result)
            self.logger.info(f"Agent finished state: {task_input.output.state}", extra={"task_uid": task_input.uid})
            self._handle_evaluation(agent, task_input)
        except Exception as e:
            tb_str = traceback.format_exc()
            _save_error_log(task_input, "TASK_EXECUTION_ERROR", e, tb_str)
            self.logger.error(f"Task execution error: {e}", extra={"task_uid": task_input.uid})
            task_input.output = TaskOutput(eval_error=f"Orchestrator error: {e}\n{tb_str}", score=0.0)
        finally:
            task_input.save_result_summary()
            self.logger.info(
                f"Summary saved: {task_input.result_dir / 'summary.json'}", extra={"task_uid": task_input.uid}
            )
            self._log_summary(task_input)

    def _log_summary(self, task_input: TaskInput):
        """Logs the final summary of a task."""
        self.logger.info(_get_divider(title=f"Task {task_input.uid[:8]} Summary", char="-", length=60))
        if task_input.output:
            timing = task_input.output.total_timing or {}
            duration = f"{timing.get('duration', 0):.2f}"
            self.logger.info(f"UID:    {task_input.uid}", extra={"task_uid": task_input.uid})
            self.logger.info(f"State:  {task_input.output.state}", extra={"task_uid": task_input.uid})
            self.logger.info(f"Score:  {task_input.output.score}", extra={"task_uid": task_input.uid})
            self.logger.info(f"Timing: {duration} seconds", extra={"task_uid": task_input.uid})
            if task_input.output.eval_error:
                self.logger.error(
                    f"Eval Error: {task_input.output.eval_error.splitlines()[0]}...", extra={"task_uid": task_input.uid}
                )
        else:
            self.logger.error("State: ERROR (No output generated)", extra={"task_uid": task_input.uid})
        self.logger.info(_get_divider(char="=", length=60) + "\n")

    def _handle_setup(self, agent: SandboxCodeAgent, task_input: TaskInput):
        """Handles the 'config' block from the task JSON."""
        self.logger.info("Executing setup steps...", extra={"task_uid": task_input.uid})
        for step in task_input.config:
            func_name = step.get("func")
            arguments = step.get("arguments", {})
            if func_name and func_name in self.config_dispatch:
                self.config_dispatch[func_name](agent=agent, task=task_input, **arguments)
            else:
                self.logger.warning(f"Unknown setup function: {func_name}", extra={"task_uid": task_input.uid})

    def _handle_evaluation(self, agent: SandboxCodeAgent, task_input: TaskInput):
        """Handles the 'evaluation' block from the task JSON."""
        self.logger.info("Executing evaluation step...", extra={"task_uid": task_input.uid})
        eval_config = task_input.evaluation
        func_name = eval_config.get("func")
        arguments = eval_config.get("arguments", {})

        if not func_name:
            self.logger.info("No evaluation function defined. Skipping.", extra={"task_uid": task_input.uid})
            task_input.output.score = -1.0
            return

        if func_name in self.eval_dispatch:
            try:
                score = self.eval_dispatch[func_name](agent=agent, task=task_input, **arguments)
                task_input.output.score = float(score)
                self.logger.info(f"Evaluation score: {task_input.output.score}", extra={"task_uid": task_input.uid})
            except Exception as e:
                tb_str = traceback.format_exc()
                _save_error_log(task_input, "EVALUATION_ERROR", e, tb_str)
                task_input.output.score = 0.0
                task_input.output.eval_error = f"Evaluation failed: {e}"
        else:
            task_input.output.score = 0.0
            task_input.output.eval_error = f"Unknown evaluation function: {func_name}"
            self.logger.warning(f"{task_input.output.eval_error}", extra={"task_uid": task_input.uid})

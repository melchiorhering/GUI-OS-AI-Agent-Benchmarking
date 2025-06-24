import time
from typing import Optional

from PIL import Image
from smolagents import ActionStep, LogLevel, Timing

from agent.executor import SandboxExecutor
from agent.sandbox_agent import SandboxCodeAgent


def _get_sandbox_executor(agent: SandboxCodeAgent) -> SandboxExecutor:
    """Safely gets the SandboxExecutor from an agent, raising a TypeError if it's not the correct type."""
    if not isinstance(agent.python_executor, SandboxExecutor):
        msg = "This callback requires an agent with a SandboxExecutor."
        agent.logger.log_error(msg)
        raise TypeError(msg)
    return agent.python_executor


def initial_state_callback(agent: SandboxCodeAgent) -> Optional[ActionStep]:
    """
    Takes an initial screenshot, gets the list of installed packages,
    and returns an initial ActionStep for the agent's memory.
    """
    start_time = time.time()
    try:
        executor = _get_sandbox_executor(agent)
        host_shared = executor.vm.cfg.host_container_shared_dir

        # Get installed packages and take the initial screenshot
        packages_result_tuple = executor.run_code_raise_errors("!uv pip list")
        screenshot_result = agent.sandbox_client.take_screenshot(step="S0")

        if "screenshot_path" not in screenshot_result:
            agent.logger.log_error("⚠️ Failed to get screenshot path in initial callback.")
            return None

        path = str(host_shared / screenshot_result["screenshot_path"])
        image = Image.open(path)

        # FIX: Access the second element of the tuple for the stdout string.
        installed_packages_str = (
            packages_result_tuple[1] if packages_result_tuple else "Could not retrieve package list."
        )

        # Format the observation text
        observations_text = (
            "📸 Initial screenshot before execution.\n\n"
            "📦 Currently installed packages:\n"
            "```\n"
            f"{installed_packages_str}"
            "```"
        )

        # Create the initial ActionStep
        initial_step = ActionStep(
            step_number=0,
            model_output="Initial environment state.",
            observations=observations_text,
            observations_images=[image.copy()],
            timing=Timing(start_time=start_time, end_time=time.time()),
        )
        agent.logger.log(f"📸 Saved initial state: {path}", level=LogLevel.DEBUG)
        return initial_step

    except (TypeError, FileNotFoundError, KeyError) as e:
        agent.logger.log_error(f"⚠️ Failed to create initial state: {e}")
        return None


def observation_screenshot_callback(
    memory_step: ActionStep,
    agent: SandboxCodeAgent,
) -> None:
    """
    Takes a screenshot after an action, gets the current package list,
    and appends the observation to the current memory step.
    """
    try:
        executor = _get_sandbox_executor(agent)
        host_shared = executor.vm.cfg.host_container_shared_dir
        current_step = memory_step.step_number

        # Clean up screenshots from much older steps to save memory
        for step in agent.memory.steps:
            if isinstance(step, ActionStep) and step.step_number <= current_step - 2:
                step.observations_images = None

        # Get installed packages and take the screenshot
        packages_result_tuple = executor.run_code_raise_errors("!uv pip list")
        # FIX: Access the second element of the tuple instead of using .get()
        installed_packages = packages_result_tuple[1] if packages_result_tuple else "Could not retrieve package list."

        screenshot_result = agent.sandbox_client.take_screenshot(step=f"S{current_step}")

        if "screenshot_path" in screenshot_result:
            path = str(host_shared / screenshot_result["screenshot_path"])
            image = Image.open(path)
            memory_step.observations_images = [image.copy()]
            width, height = image.size

            # Ensure observations is a string before appending
            if memory_step.observations is None:
                memory_step.observations = ""

            # Append new observation data
            observation_details = (
                f"\n\n--- Observation at Step {current_step} ---\n"
                f"📸 Screenshot: Mouse at {screenshot_result['mouse_position']} | Resolution={width}×{height}px\n"
                f"📦 Installed Packages:\n```\n{installed_packages}\n```\n"
                "Given the new screenshot, what is the next action to solve the task?"
            )
            memory_step.observations += observation_details

            agent.logger.log(
                f"📸 Screenshot taken and observation appended for step {current_step}.",
                level=LogLevel.DEBUG,
            )
        else:
            if memory_step.observations is None:
                memory_step.observations = ""
            memory_step.observations += "\n\n--- Observation ---\n⚠️ Failed to capture screenshot."

    except Exception as e:
        if memory_step.observations is None:
            memory_step.observations = ""
        memory_step.observations += f"\n\n--- Observation ---\n⚠️ Failed to generate observation: {e}"
        agent.logger.log_error(f"⚠️ Error in observation_screenshot_callback: {e}")

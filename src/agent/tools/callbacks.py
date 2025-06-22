import time

from PIL import Image
from smolagents import ActionStep, LogLevel

from ..sandbox_agent import SandboxCodeAgent


def initial_state_callback(agent: SandboxCodeAgent) -> None:
    # Record the start time before taking the screenshot
    start_time = time.time()

    # # List all the currently installed packages
    # # The output of '!uv pip list' is usually a string with newline characters
    # installed_packages = agent.python_executor.run_code_raise_errors(code_action="!uv pip list")

    host_shared = agent.python_executor.vm.cfg.host_container_shared_dir
    result = agent.sandbox_client.take_screenshot(step="S0")

    # Record the end time after the screenshot operation is complete
    end_time = time.time()

    if "screenshot_path" in result:
        try:
            # Construct the full path to the screenshot
            path = str(host_shared / result["screenshot_path"])
            image = Image.open(path)

            # You can format this string nicely, for example, by adding a header
            # and ensuring the package list is clearly separated.
            # observations_text = (
            #     "📸 Initial screenshot before execution.\n\n"
            #     "📦 Currently installed packages:\n"
            #     "```\n" # Markdown code block for readability
            #     f"{installed_packages}"
            #     "```"
            # )
            # # Create the Timing object
            # initial_step = ActionStep(
            #     step_number=0,
            #     model_output="Initial environment state.",
            #     observations=observations_text,
            #     observations_images=[image.copy()],
            #     timing=Timing(start_time=start_time, end_time=end_time),
            # )
            # agent.logger.log(f"📸 Saved initial screenshot: {path}", level=LogLevel.DEBUG)
            # # Adding it to memory as first step
            # agent.memory.steps.append(initial_step)
            return image
        except Exception as e:
            agent.logger.log_error(f"⚠️ Failed to save initial screenshot: {e}")


def observation_screenshot_callback(
    memory_step: ActionStep,
    agent: SandboxCodeAgent,
) -> None:
    """Callback that takes screenshots with the FastAPI sandbox client."""
    host_shared = agent.python_executor.vm.cfg.host_container_shared_dir

    # Clean up previous screenshots to save memory
    current_step = memory_step.step_number
    for previous_memory_step in agent.memory.steps:
        if isinstance(previous_memory_step, ActionStep) and previous_memory_step.step_number <= current_step - 2:
            previous_memory_step.observations_images = None

    # List all the currently installed packages
    # The output of '!uv pip list' is usually a string with newline characters
    installed_packages = agent.python_executor.run_code_raise_errors(code_action="!pip list")

    # Take the screenshot using the sandbox client
    result = agent.sandbox_client.take_screenshot(step=f"S{current_step}")
    if "screenshot_path" in result:
        path = str(host_shared / result["screenshot_path"])
        try:
            image = Image.open(path)
            memory_step.observations_images = [image.copy()]
            width, height = image.size
            memory_step.observations += f"Screenshot@step={current_step} | Mouse={result['mouse_position']} | Resolution={width}×{height}px\n📦Currently installed packages:{installed_packages}\nGiven the image of the GUI screenshot, what is the next step that you will do to help with the task?"

            agent.logger.log(
                f"📸 Screenshot saved — {memory_step.observations}",
                level=LogLevel.DEBUG,
            )
        except Exception as e:
            memory_step.observations = f"⚠️ Failed to load screenshot: {e}"

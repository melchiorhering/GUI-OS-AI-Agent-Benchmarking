import os
import sys
import uuid
from pathlib import Path

# Assuming smolagents and your agent definition are installed or in the path
from smolagents import LiteLLMModel, LogLevel

# --- Import your custom types and agent ---
# Adjust the path based on your project structure.
# This assumes the script is in a 'tests' folder and the definitions are in 'src'.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import SandboxCodeAgent, initial_screenshot_callback, observation_screenshot_callback
from benchmark import TaskInput, TaskOutput
from sandbox.configs import SandboxVMConfig

# ───────────────────────────── Configuration ─────────────────────────────
# Define root directories for task data and results
ROOT_DIR = Path(__file__).resolve().parent / "test_tasks"
RESULTS_ROOT_DIR = Path(__file__).resolve().parent / "test_results"

# ───────────────────────────── Agent Configuration ─────────────────────────────
model = LiteLLMModel(model_id="openai/o4-mini", api_key=os.getenv("OPENAI_API_KEY"))

# ───────────────── System Prompt / Instructions for the Agent ──────────────────
AGENT_PROMPT_PREFIX = """You are an expert autonomous agent operating within a sandboxed GUI environment. Your primary goal is to accomplish the user's task by breaking it down into a series of logical steps.

For each step, you must choose the best method to achieve your goal:

1.  **GUI Automation**: Use the `pyautogui` library to control the mouse and keyboard for tasks that require interacting with graphical elements (e.g., clicking buttons, opening applications, typing in non-accessible fields).
2.  **Direct Code Execution**: Use Python directly for tasks that are more efficiently handled through code (e.g., performing calculations, manipulating data, reading/writing files, or calling available tools).

**Your Workflow for Each Step:**

* **Think First**: Begin by explaining your plan. Justify why you are choosing either **GUI automation** or **direct code execution** for the current step.
* **Execute with Code**: Provide the complete Python code to perform the planned action. Remember to include `time.sleep()` after GUI actions that need time to load or process.

**Verification and Final Answer:**

After each action, you will receive an **observation** to confirm the result.
* For **GUI actions**, this will be a screenshot. You must analyze the image to confirm the action was successful.
* For **direct code**, this will be the execution logs or output. You must check this text to verify the outcome.

To provide the **final answer**, you must base your conclusion on the final observation. Confirm that the task is complete by reviewing the last screenshot or the final code output.
---
"""


# ────────────────────────── Task Execution Function ───────────────────────────
def run_and_process_task(agent: SandboxCodeAgent, task_input: TaskInput):
    """
    Runs a single task, processes the results using TaskOutput, and saves the summary.
    """
    print(f"\n🚀 Starting Task: {task_input.uid} - '{task_input.prompt}'")
    print("──────────────────────────────────────────────────────────────")

    # 1. Prepare and run the agent
    full_prompt = f"{AGENT_PROMPT_PREFIX}\n**Your Task:**\n{task_input.prompt}"
    agent_result = agent.run(full_prompt, max_steps=task_input.steps)

    # 2. Populate the TaskOutput object from the agent's result
    # This automatically flattens the result via the __post_init__ method.
    task_input.output = TaskOutput(source_result=agent_result)

    # 3. (Optional) Perform evaluation and update the score
    # For this test, we'll just assign a placeholder score.
    # In a real scenario, you would run your evaluation logic here.
    if task_input.output.state == "success":
        print("✅ Task succeeded, assigning score.")
        task_input.output.score = 1.0
    else:
        print("❌ Task failed or hit max steps.")
        task_input.output.score = 0.0
        task_input.output.eval_error = "Task did not reach a 'success' state."

    # 4. Save the complete summary to a JSON file
    task_input.save_result_summary()
    print(f"📄 Summary saved to: {task_input.result_dir / 'summary.json'}")

    # 5. Print a brief summary to the console
    print("\n─────────────────────── Task Completed ───────────────────────")
    print(f"State: {task_input.output.state}")
    print(f"Score: {task_input.output.score}")
    print(f"Timing: {task_input.output.total_timing}")
    print("──────────────────────────────────────────────────────────────")


# ────────────────────────── Main Execution Block ───────────────────────────
def main():
    """Initializes the agent and runs the defined tasks."""
    # Initialize the sandbox agent
    config = SandboxVMConfig(container_name="sandbox-test-tasks")
    agent = SandboxCodeAgent(
        description="This agent runs in a sandboxed environment and can execute code.",
        tools=[],
        model=model,
        step_callbacks=[observation_screenshot_callback],
        executor_type="sandbox",
        executor_kwargs={"config": config},
        use_structured_outputs_internally=True,
        return_full_result=True,
        verbosity_level=LogLevel.INFO,
    )
    # Take the initial screenshot
    initial_screenshot_callback(agent)

    try:
        # Define Task 1 using the TaskInput object
        task_1 = TaskInput(
            uid=f"test-chromium-{uuid.uuid4().hex[:8]}",
            tool="SandboxCodeAgent",
            prompt="Try to open the chromium browser from the sidebar.",
            root_dir=ROOT_DIR,
            results_root_dir=RESULTS_ROOT_DIR,
            steps=5,
        )
        run_and_process_task(agent, task_1)

        # Define Task 2 using the TaskInput object
        task_2 = TaskInput(
            uid=f"test-wikipedia-{uuid.uuid4().hex[:8]}",
            tool="SandboxCodeAgent",
            prompt="Go to wikipedia.org and search for 'Python programming language'.",
            root_dir=ROOT_DIR,
            results_root_dir=RESULTS_ROOT_DIR,
            steps=5,
        )
        run_and_process_task(agent, task_2)

    except KeyboardInterrupt:
        print("\nKeyboard interrupt detected. Exiting early.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        print("\n🧹 Cleaning up agent resources...")
        agent.cleanup()


if __name__ == "__main__":
    main()

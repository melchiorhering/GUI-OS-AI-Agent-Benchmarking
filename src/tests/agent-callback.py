import json
import os
import sys
from pathlib import Path

# Assuming smolagents and your agent definition are installed or in the path
from smolagents import LiteLLMModel, LogLevel

# --- Import your custom types and agent ---
# Adjust the path based on your project structure.
# This assumes the script is in a 'tests' folder and the definitions are in 'src'.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import SandboxCodeAgent, initial_screenshot_callback, observation_screenshot_callback
from sandbox.configs import SandboxVMConfig

# ───────────────────────────── Agent Configuration ─────────────────────────────
model = LiteLLMModel(model_id="openai/o4-mini", api_key=os.getenv("OPENAI_API_KEY"))


# ───────────────── System Prompt / Instructions for the Agent ──────────────────
AGENT_PROMPT_PREFIX = """You are an expert autonomous agent operating within a sandboxed GUI environment. Your primary goal is to accomplish the user's task by breaking it down into a series of logical steps.

For each step, you must choose the best method to achieve your goal:

1.  **GUI Automation**: Use the `pyautogui` library to control the mouse and keyboard for tasks that require interacting with graphical elements (e.g., clicking buttons, opening applications, typing in non-accessible fields).
2.  **Direct Code Execution**: Use Python directly for tasks that are more efficiently handled through code (e.g., performing calculations, manipulating data, reading/writing files, or calling available tools).

## Your Workflow for Each Step

* **Think First**: Begin by explaining your plan. Justify why you are choosing either **GUI automation** or **direct code execution** for the current step.
* **Execute with Code**: Provide the complete Python code to perform the planned action. Remember to include `time.sleep()` after GUI actions that need time to load or process.

## Verification and Final Answer

After each action, you will receive an **observation** to confirm the result.
* For **GUI actions**, this will be a screenshot. You must analyze the image to confirm the action was successful.
* For **direct code**, this will be the execution logs or output. You must check this text to verify the outcome.

## Final Answer Submission

When the task is fully completed and verified in the final observation, you must call the `final_answer` function.

## RULES for `final_answer`
1.  The function takes **only one argument**.
2.  The argument **MUST be a single string**. This string should be a short summary of how you completed the task.
3.  **DO NOT** redefine the `final_answer` function, pass variables, or use any data type other than a string.

---
### Correct Example
```python
final_answer("I successfully created the 'tensor.ipynb' notebook and verified that the file exists in the file explorer.")
```

### Incorrect Examples (DO NOT DO THIS)
```python
# Incorrect: Passing a variable or non-string type
final_answer(my_result_variable)

# Incorrect: Redefining the function
def final_answer(text):
    print(text)
final_answer("Task complete.")

# Incorrect: Passing other data types
final_answer(dict, list, tuple)
```

### Summary of Improvements
1.  **Clear, Authoritative Section**: The instructions are moved from a "Final Note" to a dedicated, official-sounding section: `Final Answer Submission`.
2.  **Explicit Rules**: The constraints are laid out as simple, numbered `RULES` which are easier for a model to parse and follow than a prose sentence.
3.  **Emphasis**: Key constraints are highlighted with bolding and capitalization (`MUST`, `DO NOT`, `only one argument`) to increase their weight.
4.  **Positive and Negative Examples**: It now includes both a `Correct Example` and several `Incorrect Examples`. This contrast is a very powerful way to teach the model the exact pattern to follow and what to avoid, directly addressing your concerns about redefining the function or passing non-string types.

Here below you can find the task description that you need to complete:
---
{complete_task}
"""


config = SandboxVMConfig(container_name="sandbox-test-callback", host_services_dir=Path("sandbox/services/"))

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
    agent_result = agent.run(
        AGENT_PROMPT_PREFIX.format(complete_task="Open the chrome browser and find the Python Wikipedia page."),
        max_steps=10,
    )

    # Convert message objects to dictionaries, excluding the 'raw' key from any nested models
    messages_as_dicts = [msg.model_dump(exclude={"raw"}) for msg in agent_result.messages]

    path = Path("tests/out/messages.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as final:
        # Dump the cleaned list of dictionaries
        json.dump(messages_as_dicts, final, indent=4)


except KeyboardInterrupt:
    print("\nKeyboard interrupt detected. Exiting early.")
except Exception as e:
    print(f"\nAn unexpected error occurred: {e}")
finally:
    print("\n🧹 Cleaning up agent resources...")
    agent.cleanup()

import argparse
import os
from pathlib import Path

import yaml
from smolagents import LiteLLMModel

from src.agent import get_orchestrator_logger
from src.benchmark.orchestrator import Orchestrator
from src.benchmark.utils import generate_port_pool

# Define constants
PORT_KEYS = ["ssh", "vnc", "fastapi", "jupyter"]
START_PORT = 60000
DEFAULT_PROMPT_FILE = Path("prompts/task.yaml")
DEFAULT_TASK_INDEX_PATH = Path("benchmark/evaluation_examples/test_one.json")
DEFAULT_TASKS_ROOT_DIR = Path("benchmark/evaluation_examples/examples")
DEFAULT_RESULTS_ROOT_DIR = Path("results")
TASK_TIMEOUT_SECONDS = 12 * 60


def get_api_key_for_model(model_id: str) -> str:
    """Dynamically resolve the API key based on the model provider prefix."""
    provider = model_id.split("/")[0].lower()
    mapping = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GEMINI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    env_var = mapping.get(provider, f"{provider.upper()}_API_KEY")
    key = os.getenv(env_var)
    if not key:
        raise ValueError(f"Missing API key for provider '{provider}'. Please set {env_var}.")
    return key


def load_prompt_from_file(prompt_file: Path, prompt_key: str) -> str:
    """Loads a specific prompt string from a given key in a YAML file."""
    if not prompt_file.is_file():
        raise FileNotFoundError(f"Prompt file not found at {prompt_file}")
    with open(prompt_file, "r") as f:
        data = yaml.safe_load(f)
        if not data or prompt_key not in data:
            raise ValueError(f"Prompt key '{prompt_key}' not found in {prompt_file}")
    return data[prompt_key]


def main():
    parser = argparse.ArgumentParser(description="Run benchmark tasks using a code agent.")

    # Model Configuration Group
    model_group = parser.add_argument_group("Model Configuration")
    model_group.add_argument(
        "--model-id",
        type=str,
        default="openai/gpt-4o-mini",
        help="Model ID (e.g., 'anthropic/claude-3-5-sonnet' or 'openrouter/qwen/qwen2.5-72b-instruct').",
    )
    model_group.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Explicit API key. If not provided, it will be pulled from ENV based on model-id.",
    )

    # Task and paths configuration
    parser.add_argument("--task-index", type=Path, default=DEFAULT_TASK_INDEX_PATH, help="Path to JSON task list.")
    parser.add_argument(
        "--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT_DIR, help="Root dir for task definitions."
    )
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT_DIR, help="Root dir for results.")

    # Prompt configuration
    parser.add_argument("--prompt-file", type=Path, default=DEFAULT_PROMPT_FILE, help="Path to the YAML prompt file.")
    parser.add_argument("--prompt-key", type=str, default="default_prompt", help="Key for prompt in YAML.")

    # Orchestrator tuning
    parser.add_argument("--task-timeout", type=int, default=TASK_TIMEOUT_SECONDS, help="Timeout per task.")
    parser.add_argument("--max-agent-steps", type=int, default=15, help="Max steps per agent run.")

    args = parser.parse_args()

    # Ensure results directory exists
    args.results_root.mkdir(parents=True, exist_ok=True)
    orchestrator_logger = get_orchestrator_logger(log_file_path=args.results_root / "orchestrator.log")

    try:
        api_key = args.api_key or get_api_key_for_model(args.model_id)
        model = LiteLLMModel(model_id=args.model_id, api_key=api_key)

        agent_prompt = load_prompt_from_file(args.prompt_file, args.prompt_key)
        orchestrator_logger.info(f"Loaded prompt '{args.prompt_key}' from {args.prompt_file}")

        port_config = generate_port_pool(START_PORT, 1, PORT_KEYS)[0]

        runner = Orchestrator(
            model=model,
            tasks_root_dir=args.tasks_root,
            results_root_dir=args.results_root,
            logger=orchestrator_logger,
            port_config=port_config,
            agent_prompt_template=agent_prompt,
            task_timeout=args.task_timeout,
            max_agent_steps=args.max_agent_steps,
        )
        runner.run_benchmark(task_index_path=args.task_index)

    except (FileNotFoundError, ValueError) as e:
        orchestrator_logger.critical(f"Setup failed: {e}")
    except KeyboardInterrupt:
        orchestrator_logger.info("\nKeyboard interrupt detected. Shutting down.")
    except Exception as e:
        orchestrator_logger.critical(f"A critical error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    main()

import argparse
import os
from pathlib import Path

import yaml  # You will need to install pyyaml: uv pip install pyyaml
from smolagents import LiteLLMModel

from src.agent import get_orchestrator_logger
from src.benchmark.orchestrator import Orchestrator
from src.benchmark.utils import generate_port_pool

# Define constants for port generation
PORT_KEYS = ["ssh", "vnc", "fastapi", "jupyter"]
START_PORT = 60000
DEFAULT_PROMPT_FILE = Path("prompts/task.yaml")
DEFAULT_TASK_INDEX_PATH = Path("benchmark/evaluation_examples/test_one.json")
DEFAULT_TASKS_ROOT_DIR = Path("benchmark/evaluation_examples/examples")
DEFAULT_RESULTS_ROOT_DIR = Path("results")
TASK_TIMEOUT_SECONDS = 12 * 60


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
    """Command-line entry point for the benchmark runner."""
    parser = argparse.ArgumentParser(description="Run benchmark tasks using a code agent.")

    # Task and paths configuration
    parser.add_argument(
        "--task-index", type=Path, default=DEFAULT_TASK_INDEX_PATH, help="Path to the JSON file listing tasks."
    )
    parser.add_argument(
        "--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT_DIR, help="Root directory for task definitions."
    )
    parser.add_argument(
        "--results-root", type=Path, default=DEFAULT_RESULTS_ROOT_DIR, help="Root directory for results."
    )

    # Prompt configuration
    parser.add_argument("--prompt-file", type=Path, default=DEFAULT_PROMPT_FILE, help="Path to the YAML prompt file.")
    parser.add_argument(
        "--prompt-key",
        type=str,
        default="default_prompt",
        help="The key for the specific prompt to use from the YAML file.",
    )

    # Agent and Orchestrator configuration
    parser.add_argument(
        "--model-id", type=str, default="openai/o4-mini-2025-04-16", help="The model ID to use for the agent."
    )
    parser.add_argument(
        "--task-timeout", type=int, default=TASK_TIMEOUT_SECONDS, help="Timeout in seconds for each task."
    )
    parser.add_argument("--max-agent-steps", type=int, default=15, help="Maximum number of steps the agent can take.")

    args = parser.parse_args()

    # --- Setup Dependencies ---
    orchestrator_logger = get_orchestrator_logger(log_file_path=args.results_root / "orchestrator.log")

    try:
        model = LiteLLMModel(
            model_id=args.model_id,
            api_key=os.getenv("OPENAI_API_KEY"),
        )

        agent_prompt = load_prompt_from_file(args.prompt_file, args.prompt_key)
        orchestrator_logger.info(f"Loaded prompt '{args.prompt_key}' from {args.prompt_file}")

        port_config = generate_port_pool(START_PORT, 1, PORT_KEYS)[0]
        orchestrator_logger.info(f"Using port configuration: {port_config}")

        # --- Instantiate and Run Orchestrator ---
        runner = Orchestrator(
            model=model,
            tasks_root_dir=args.tasks_root,
            results_root_dir=args.results_root,
            logger=orchestrator_logger,
            port_config=port_config,
            agent_prompt_template=agent_prompt,  # Pass the loaded prompt string
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

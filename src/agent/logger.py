import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console, Group
from rich.table import Table
from rich.tree import Tree
from smolagents import AgentLogger, LogLevel


# ─────────────────── Part 1: Orchestrator Logger Setup ───────────────────
# All of this code is moved from your main script into this file.
# Define ANSI color codes
class LogColors:
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    ORANGE = "\033[38;5;208m"  # A common ANSI code for orange
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    RESET = "\033[0m"


class CustomColoredFormatter(logging.Formatter):
    """
    A custom formatter that adds color and specific fields (UID, Task Index) to log messages.
    Handles missing custom fields gracefully.
    """

    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    LEVEL_COLORS = {
        logging.DEBUG: LogColors.BRIGHT_BLACK,
        logging.INFO: LogColors.CYAN,
        logging.WARNING: LogColors.YELLOW,
        logging.ERROR: LogColors.RED,
        logging.CRITICAL: LogColors.BRIGHT_RED,
    }

    THREAD_COLORS = [
        LogColors.BRIGHT_BLUE,
        LogColors.BRIGHT_GREEN,
        LogColors.BRIGHT_MAGENTA,
        LogColors.BRIGHT_CYAN,
        LogColors.YELLOW,
    ]
    thread_color_map = {}
    next_thread_color_idx = 0

    def get_thread_color(self, thread_name):
        if thread_name not in self.thread_color_map:
            self.thread_color_map[thread_name] = self.THREAD_COLORS[
                self.next_thread_color_idx % len(self.THREAD_COLORS)
            ]
            self.next_thread_color_idx += 1
        return self.thread_color_map[thread_name]

    def format(self, record):
        # Determine the color for the log level prefix
        level_color_start = self.LEVEL_COLORS.get(record.levelno, LogColors.RESET)

        # Get the color for the thread
        thread_color_start = self.get_thread_color(record.threadName)

        # Construct the dynamic prefix based on custom attributes
        prefix_parts = []
        task_uid_short = getattr(record, "task_uid", None)
        if task_uid_short and task_uid_short != "N/A":  # Ensure N/A is not used in prefix if it's the default
            prefix_parts.append(f"[{task_uid_short[:8]}]")

        task_idx = getattr(record, "task_idx", None)
        total_tasks = getattr(record, "total_tasks", None)
        if task_idx is not None and total_tasks is not None and total_tasks > 0 and task_idx != "N/A":
            prefix_parts.append(f"({task_idx + 1}/{total_tasks})")

        prefix_parts.append(f"[{datetime.fromtimestamp(record.created).strftime(self.DATE_FORMAT)}]")

        dynamic_prefix = " ".join(prefix_parts) + " " if prefix_parts else ""

        # Construct the full log message format string
        log_fmt = (
            f"{level_color_start}{dynamic_prefix}%(levelname)s - "
            f"{thread_color_start}%(threadName)s{LogColors.RESET} - "
            f"{LogColors.BRIGHT_WHITE}%(message)s{LogColors.RESET}"  # Message is always bright white
        )

        formatter = logging.Formatter(log_fmt, datefmt=self.DATE_FORMAT)
        return formatter.format(record)


# Filter to ensure custom extra fields are present even if not provided in log call
class DefaultExtraFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "task_uid"):
            record.task_uid = "N/A"
        if not hasattr(record, "task_idx"):
            record.task_idx = "N/A"
        if not hasattr(record, "total_tasks"):
            record.total_tasks = "N/A"
        return True


def get_orchestrator_logger(log_level=logging.INFO, log_file_path: Path = Path("orchestrator.log")) -> logging.Logger:
    """
    A factory function to build and configure the main orchestrator logger.
    """
    logger = logging.getLogger("BenchmarkOrchestrator")
    logger.setLevel(log_level)

    # Prevent adding handlers multiple times if this function is called again
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console Handler (with colors and custom format)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(CustomColoredFormatter())
    logger.addHandler(console_handler)

    # File Handler (without colors)
    file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
    file_formatter = logging.Formatter(
        "[%(task_uid)s] (%(task_idx)s/%(total_tasks)s) [%(asctime)s] - %(levelname)s - %(threadName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(DefaultExtraFilter())
    logger.addHandler(file_handler)

    logger.propagate = False  # Prevent logs from going to the root logger
    return logger


# ──────────────────── Part 2: Agent Logger (Unchanged) ────────────────────
# Your existing SandboxAgentLogger remains here.

YELLOW_HEX = "#d4b702"


class SandboxAgentLogger(AgentLogger):
    """
    An extended logger that records all console output in memory and allows
    for saving the full log and a dedicated agent tree visualization to a
    directory on demand.
    """

    def __init__(self, level: LogLevel = LogLevel.INFO):
        """
        Initializes the logger, forcing the console to record all output.
        """
        # The console MUST record to enable saving later.
        console = Console(record=True)
        super().__init__(level=level, console=console)

    def save_log_file(self, directory: str, filename: str = "console_log.html"):
        """
        Saves the entire recorded console history to a file.

        Args:
            directory (str): The folder to save the file in.
            filename (str, optional): The name of the log file.
                                      Use .html (recommended) or .txt.
        """
        if not os.path.exists(directory):
            os.makedirs(directory)
        output_path = os.path.join(directory, filename)

        if filename.endswith(".html"):
            self.console.save_html(output_path, inline_styles=True)
        elif filename.endswith(".txt"):
            self.console.save_text(output_path)
        else:
            self.log_error(f"Unsupported log format: {filename}. Use .html or .txt.")
            return

        self.log(f"Console log saved to [bold cyan]{output_path}[/bold cyan]")

    def save_agent_tree(self, agent, directory: str, filename: str = "agent_tree.svg"):
        """
        Generates and saves a visualization of the agent tree to a file.
        This method is separate from the main log to create a clean, dedicated output.

        Args:
            agent: The agent object to visualize.
            directory (str): The folder to save the file in.
            filename (str, optional): The name of the image file.
                                      Use .svg (recommended), .html, or .txt.
        """
        if not os.path.exists(directory):
            os.makedirs(directory)
        output_path = os.path.join(directory, filename)

        # To save the tree cleanly, we create a temporary console,
        # build the tree on it, and save its output.
        save_console = Console(record=True, width=self.console.width)

        # NOTE: The tree-building logic from the parent's `visualize_agent_tree`
        # is intentionally duplicated here to create an isolated output.
        def create_tools_section(tools_dict):
            table = Table(show_header=True, header_style="bold")
            table.add_column("Name", style="#1E90FF")
            table.add_column("Description")
            table.add_column("Arguments")
            for name, tool in tools_dict.items():
                args = [
                    f"{arg_name} (`{info.get('type', 'Any')}`{', optional' if info.get('optional') else ''}): {info.get('description', '')}"
                    for arg_name, info in getattr(tool, "inputs", {}).items()
                ]
                table.add_row(name, getattr(tool, "description", str(tool)), "\n".join(args))
            return Group("🛠️ [italic #1E90FF]Tools:[/italic #1E90FF]", table)

        def get_agent_headline(agent, name: str | None = None):
            name_headline = f"{name} | " if name else ""
            return f"[bold {YELLOW_HEX}]{name_headline}{agent.__class__.__name__} | {agent.model.model_id}"

        def build_agent_tree(parent_tree, agent_obj):
            parent_tree.add(create_tools_section(agent_obj.tools))
            if agent_obj.managed_agents:
                agents_branch = parent_tree.add("🤖 [italic #1E90FF]Managed agents:")
                for name, managed_agent in agent_obj.managed_agents.items():
                    agent_tree = agents_branch.add(get_agent_headline(managed_agent, name))
                    build_agent_tree(agent_tree, managed_agent)

        main_tree = Tree(get_agent_headline(agent))
        build_agent_tree(main_tree, agent)
        save_console.print(main_tree)

        # Save the output from the temporary console
        if filename.endswith(".svg"):
            save_console.save_svg(output_path, title="Agent Tree")
        elif filename.endswith(".html"):
            save_console.save_html(output_path, inline_styles=True)
        elif filename.endswith(".txt"):
            save_console.save_text(output_path)
        else:
            self.log_error(f"Unsupported tree format: {filename}. Use .svg, .html, or .txt")
            return

        self.log(f"Agent tree separately saved to [bold cyan]{output_path}[/bold cyan]")

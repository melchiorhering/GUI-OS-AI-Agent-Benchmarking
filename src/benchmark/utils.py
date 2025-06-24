import json
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from agent import LogColors  # Assuming this is where your color definitions are
from benchmark.tasks import TaskInput  # Assuming TaskInput is in this module


# Timeout class remains the same
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
            signal.alarm(0)


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


def _get_divider(
    char: str = "=",
    length: int = 100,
    color: Optional[str] = None,
    title: Optional[str] = None,
    plain_text: bool = False,
) -> str:
    """
    Generates a horizontal divider line with optional color and title.
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
    """Generates a pool of port configurations."""
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
    return pool

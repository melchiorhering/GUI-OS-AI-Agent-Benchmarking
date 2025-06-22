# server/src/utils.py
import shutil
from datetime import datetime, timezone
from pathlib import Path


def clear_shared_dir_simpler(directory: Path):
    """
    Clears all content of the specified directory by removing and then recreating it.
    This is a more robust way to ensure the directory is empty.

    Args:
        directory: A Path object representing the directory to clear.
    """
    if directory.exists():
        try:
            shutil.rmtree(directory)
            print(f"Removed existing directory: {directory}")
        except OSError as e:
            print(f"Error removing directory {directory}: {e}")
            # Depending on the error, you might want to raise it or handle it differently
            return

    try:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"Recreated directory: {directory}")
    except OSError as e:
        print(f"Error creating directory {directory}: {e}")


def flush_typing_sequence(recorded_actions, buffer):
    if not buffer:
        return

    combined = "".join(char for char, _ in buffer)
    timestamp = buffer[-1][1] if buffer else datetime.now(timezone.utc)

    recorded_actions.append(
        {
            "event": "typed_sequence",
            "text": combined,
            "timestamp": timestamp.isoformat(),
        }
    )
    buffer.clear()

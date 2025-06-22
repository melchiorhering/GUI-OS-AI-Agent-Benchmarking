from __future__ import annotations

# ──────────────────────────── Error Types ────────────────────────────


class VMManagerError(Exception):
    pass


class VMCreationError(VMManagerError):
    pass


class VMOperationError(VMManagerError):
    pass


class SSHError(VMManagerError):
    pass


# In your errors.py (or equivalent)
class RemoteCommandError(Exception):
    def __init__(self, command: str, status: int, stdout: str, stderr: str):
        self.command = command
        self.status = status
        self.stdout = stdout
        self.stderr = stderr
        message = f"Command '{command}' failed with status {status}."
        if stderr:  # Append stderr if it exists
            message += f"\nStderr:\n{stderr.strip()}"
        # Optionally append stdout if useful for error context (e.g., if stderr is empty)
        # For example, if status != 0 and not stderr and stdout:
        #     message += f"\nStdout (as error context):\n{stdout.strip()}"
        super().__init__(message.strip())

    def __str__(self):
        # You can customize this further if needed
        return super().__str__()

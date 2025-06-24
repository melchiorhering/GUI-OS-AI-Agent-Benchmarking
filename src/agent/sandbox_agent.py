from smolagents.agents import CodeAgent
from smolagents.local_python_executor import PythonExecutor

from sandbox import SandboxClient, SSHClient

from .executor import SandboxExecutor


class SandboxCodeAgent(CodeAgent):
    """Extends the original CodeAgent with sandbox VM support."""

    def __init__(self, *args, executor_type="local", executor_kwargs=None, **kwargs):
        self.executor_type = executor_type
        self.executor_kwargs = executor_kwargs or {}
        # The parent __init__ will call `create_python_executor` and set `self.python_executor`
        super().__init__(*args, executor_type=executor_type, executor_kwargs=executor_kwargs, **kwargs)

        # knows that `self.python_executor` is a SandboxExecutor.
        if isinstance(self.python_executor, SandboxExecutor):
            # Now it's safe to access the .vm attribute
            self.ssh: SSHClient = self.python_executor.vm.ssh
            self.sandbox_client: SandboxClient = self.python_executor.vm.sandbox_client

    def create_python_executor(self) -> SandboxExecutor | PythonExecutor:
        if self.executor_type == "sandbox":
            # The executor_kwargs are passed during instantiation
            executor = SandboxExecutor(
                additional_imports=self.additional_authorized_imports,
                logger=self.logger,
                **self.executor_kwargs,
            )
            return executor
        # Fallback to original method for "local" executor type
        return super().create_python_executor()

    def cleanup(self):
        """Clean up sandbox or other remote resources if needed."""
        try:
            # FIX: Use an isinstance check for type safety and to inform Pylance.
            # This is more robust than hasattr because it checks for the class type.
            if isinstance(self.python_executor, SandboxExecutor):
                # Pylance now knows that .cleanup() exists on this object.
                self.python_executor.cleanup()
        except Exception as e:
            self.logger.log_error(f"⚠️ CodeAgent cleanup failed: {e}")

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Optional

import requests
from smolagents import AgentLogger, LogLevel

from .configs import SandboxVMConfig
from .errors import VMOperationError
from .virtualmachine import (
    VMManager,
)


class SandboxClient:
    """HTTP helper for the FastAPI service inside the sandbox VM."""

    def __init__(self, host: str, port: int, retries: int = 15, delay: int = 10):
        self.base_url = f"http://{host}:{port}"
        self.retries = retries
        self.delay = delay

        print(f"Attempting to connect to Sandbox server at {self.base_url}...")
        for attempt in range(1, self.retries + 1):
            try:
                health_status = self.health()
                if health_status.get("status") == "ok":
                    print(f"Sandbox server initialized and healthy after {attempt} attempts.")
                    return  # Successfully connected, exit init
                else:
                    print(f"Attempt {attempt}/{self.retries}: Server not healthy, status: {health_status}. Retrying...")
            except requests.exceptions.ConnectionError as e:
                print(
                    f"Attempt {attempt}/{self.retries}: Connection error to {self.base_url}: {e}. Retrying in {self.delay} seconds..."
                )
            except Exception as e:
                print(
                    f"Attempt {attempt}/{self.retries}: An unexpected error occurred during health check: {e}. Retrying in {self.delay} seconds..."
                )

            time.sleep(self.delay)

        raise ConnectionError(f"Failed to connect to sandbox server at {self.base_url} after {self.retries} attempts.")

    def health(self):
        return requests.get(f"{self.base_url}/health").json()

    def take_screenshot(self, method: str = "pillow", step: str = None):
        """
        Takes a screenshot using the specified method.
        'step' is an optional string to prepend to the filename.
        """
        params = {"method": method}
        if step is not None: # Only add 'step' to params if it's not None
            params["step"] = step

        response = requests.get(f"{self.base_url}/screenshot", params=params)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        return response.json()

    def start_recording(self):
        return requests.get(f"{self.base_url}/record", params={"mode": "start"}).json()

    def stop_recording(self):
        return requests.get(f"{self.base_url}/record", params={"mode": "stop"}).json()


class SandboxVMManager(VMManager):
    """Specialized VMManager that wires FastAPI inside the guest.
    This manager will focus on preparing shared directories and starting other necessary services.
    """

    def __init__(
        self,
        config: SandboxVMConfig,
        logger: Optional[AgentLogger] = None,
        preserve_on_exit: bool = False,
        **kwargs,
    ):
        if not isinstance(config, SandboxVMConfig):
            raise TypeError("SandboxVMManager requires SandboxVMConfig")
        super().__init__(config=config, logger=logger, **kwargs)

        self._should_cleanup = not (self.container and self.container.status == "running")
        self._preserve_on_exit = preserve_on_exit

        self.logger.log(f"Initialization _should_cleanup set to: {self._should_cleanup}", level=LogLevel.DEBUG)
        if self._preserve_on_exit:
            self.logger.log("⚠️ Container files will be preserved on exit", level=LogLevel.DEBUG)

    # Context helpers
    def connect_or_start(self):
        """Either reconnect to a running container or bootstrap anew."""
        if self.container and self.container.status == "running":
            self.logger.log("🔁 Detected running container. Reconnecting...", level=LogLevel.DEBUG)
            self.reconnect()
        else:
            self.logger.log("🚀 Starting new sandbox VM!")
            self.__enter__()

    @contextlib.contextmanager
    def sandbox_vm_context(self):
        try:
            self.__enter__()
            yield self
        finally:
            self.__exit__(None, None, None)

    # Enter/exit
    def __enter__(self) -> "SandboxVMManager":
        try:
            self.start_agent_vm()
            self._should_cleanup = False
            return self
        except Exception as e:
            self.logger.log_error(f"❌ Exception during VM startup: {e}")
            self.cleanup(delete_storage=True)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        delete_storage = not self._preserve_on_exit
        reason = "⚠️ Exiting VM context with error," if (exc_type or self._should_cleanup) else "🧹 Normal exit,"
        action = " preserving container files..." if not delete_storage else " cleaning up VM container..."
        self.logger.log(reason + action, level=LogLevel.DEBUG)
        self.cleanup(delete_storage=delete_storage)
        return False

    # Internal helpers
    def mount_shared_dir(self):
        """
        Mounts the a volume in the container to a specific host directory:
        Where `shared` is a shared volume with some directory on the host.

        ```sh
        mount -t 9p -o trans=virtio shared /mnt/container
        ```
        """
        # Create the mount point directory. The -p flag prevents errors if it already exists.
        self.ssh.exec_command("mkdir -p /mnt/container", as_root=True)

        # Mount the shared volume to the newly created directory
        self.ssh.exec_command("mount -t 9p -o trans=virtio shared /mnt/container", as_root=True)

    def _initialize_sandbox_client(self):
        """Helper to initialize SandboxClient and handle related errors."""
        try:
            self.sandbox_client = SandboxClient(
                host=self.cfg.host_sandbox_fastapi_server_host,
                port=self.cfg.host_sandbox_fastapi_server_port,
            )
            self.logger.log("✅ Sandbox client initialized and server healthy.", level=LogLevel.INFO)
        except (ConnectionError, RuntimeError) as e:
            logs_path = Path(self.cfg.host_container_shared_dir).resolve()
            self.logger.log_error(f"❌ FastAPI server health check failed: {e}")
            self.logger.log_error(f"🪵 Check the logs:\n{logs_path}")
            raise VMOperationError(f"FastAPI server health check failed: {e}") from e
        except Exception as e:
            logs_path = Path(self.cfg.host_container_shared_dir).resolve()
            self.logger.log_error(f"❌ Unexpected error during FastAPI client initialization: {e}")
            self.logger.log_error(f"🪵 Check the logs:\n{logs_path}")
            raise VMOperationError(f"Unexpected error during client initialization: {e}") from e

    def start_agent_vm(self):
        """High-level bootstrap for the sandbox services."""
        self.start()
        self.logger.log("VM Started and SSH connection established!")
        self.mount_shared_dir()
        self._initialize_sandbox_client()

    def reconnect(self):
        self.logger.log_rule("🔁 Reconnect to Sandbox VM")
        self.start()
        self.logger.log("VM Started and SSH connection established!")

        self._initialize_sandbox_client()
        self.logger.log("✅ Reconnected & services healthy", level=LogLevel.DEBUG)

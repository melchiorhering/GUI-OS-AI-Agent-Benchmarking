# src/sandbox/config.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Union

from .errors import VMCreationError


# ────────────────────────────── Configs ──────────────────────────────
@dataclass
class VMConfig:
    """Configuration for a QEMU virtual machine running in a Docker container.

    This class defines all basic parameters for setting up and running a VM,
    including container settings, VM hardware configuration, and filesystem paths.
    """

    # ──────────────── Container Settings ────────────────
    container_image: str = "qemux/qemu"  # Docker image for the VM container
    container_name: str = "qemu"  # Container name
    # restart_policy: Literal["always", "on-failure"] = "always"  # Docker restart policy

    # ──────────────── VM Hardware Configuration ────────────────
    vm_ram: str = "4G"  # Amount of RAM for the VM
    vm_cpu_cores: int = 4  # Number of CPU cores for the VM
    vm_disk_size: str = "25g"

    # ──────────────── Network Configuration ────────────────
    host_vnc_port: int = 8006  # Host port for VNC access
    host_ssh_port: int = 2223  # Host port for SSH access
    ports: dict = field(default_factory=dict)

    # ──────────────── Paths and Directories ────────────────
    root_dir: Path = Path("docker")  # Root directory for all VM resources
    suffix: Union[str, None] = None  # suffix for the shared_dir
    shared_dir: Path = Path("results")  # Root directory for the shared-files direcotry (host-container)

    # ──────────────── Other Settings ────────────────
    enable_debug: bool = True  # Enable debug mode
    extra_env: Dict[str, str] = field(default_factory=dict)  # Additional environment variables
    runtime_env: Dict[str, str] = field(default_factory=dict)  # Runtime environment variables

    def __post_init__(self):
        # Resolve paths to absolute paths
        self.root_dir = self.root_dir.resolve()
        self.shared_dir = self.shared_dir.resolve()

        # Set up VM paths
        self.vms_dir = self.root_dir / "vms"
        self.vm_base_dir = self.vms_dir / "ubuntu-base/storage"
        self.base_data = self.vm_base_dir / "data.img"

        # Set up container paths
        self.sandboxes_dir = self.root_dir / "sandboxes"
        self.host_container_dir = self.sandboxes_dir / self.container_name
        self.host_container_data = self.host_container_dir / "data.img"

        self.host_container_shared_dir = self.shared_dir

        if self.suffix:
            self.host_container_shared_dir = self.shared_dir / self.suffix

        # Create required directories
        for p in (
            self.vm_base_dir,
            self.sandboxes_dir,
            self.shared_dir,
            self.host_container_shared_dir,
            self.host_container_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)
            # if os.access(p, os.W_OK | os.X_OK):
            #     os.chmod(p, 0o777)

        # Validate base VM files exist
        if not self.base_data.exists():
            raise VMCreationError("Missing base data.img")

        # Map core services ports
        # These are set here to establish defaults but can be overridden
        # in subclasses if needed, before the final, non-overwritable
        # ports are set.
        self.ports[8006] = self.host_vnc_port
        self.ports[22] = self.host_ssh_port


# ────────────────────────────── Config ──────────────────────────────
@dataclass
class SandboxVMConfig(VMConfig):
    """Configuration for the Sandbox QEMU virtual machine running in a Docker container with sandbox capabilities."""

    # FastAPI
    host_sandbox_fastapi_server_host: str = "localhost"
    host_sandbox_fastapi_server_port: int = 8765

    # Jupyter Kernel Gateway
    host_sandbox_jupyter_kernel_host: str = "localhost"
    host_sandbox_jupyter_kernel_port: int = 8888

    # Sandbox Services
    sandbox_task_setup_log: str = "task-setup.log"
    sandbox_fastapi_server_log: str = "observation-server.log"

    # Extra's
    runtime_env: Dict[str, str] = field(default_factory=dict)
    additional_ports: Dict[int, int] = field(default_factory=dict)

    def __post_init__(self):
        super().__post_init__()  # Critical to call this first

        # FIX: To prevent overwrites, first, we create a new dictionary with
        # the user-defined additional ports. Then, we merge the essential ports
        # into it, ensuring they overwrite any conflicting keys from additional_ports.

        final_ports = {}

        # Start with user-defined ports
        final_ports.update(self.additional_ports)

        # Now, overwrite with the essential, non-negotiable ports
        essential_ports = {
            8006: self.host_vnc_port,
            22: self.host_ssh_port,
            8765: self.host_sandbox_fastapi_server_port,
            8888: self.host_sandbox_jupyter_kernel_port,
        }
        final_ports.update(essential_ports)

        self.ports = final_ports

        # The SandboxVMManager._prepare_shared_mount method is responsible for creating
        # and mounting the host's self.host_container_shared_dir to this guest path.
        self.guest_mounted_shared_dir = Path(f"/mnt/{self.container_name}")

        # --- Pre-populate runtime_env for services ---
        self.runtime_env.update(
            {
                "SHARED_DIR": str(self.guest_mounted_shared_dir),
            }
        )

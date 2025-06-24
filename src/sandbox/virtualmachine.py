from __future__ import annotations

import shutil
import time
from typing import Optional, Union, cast

from smolagents import AgentLogger, LogLevel

import docker
import docker.models
from docker.client import DockerClient
from docker.errors import ImageNotFound, NotFound
from docker.models.containers import Container
from docker.types import Mount

from .configs import SandboxVMConfig, VMConfig
from .errors import VMCreationError
from .ssh import SSHClient, SSHConfig


# ────────────────────────────── VMManager ──────────────────────────────
class VMManager:
    """Docker‑backed QEMU VM lifecycle helper **with one persistent SSH session**."""

    # ... (rest of the class is mostly unchanged) ...
    cfg: Union[VMConfig, SandboxVMConfig]

    def __init__(
        self,
        config: Union[VMConfig, SandboxVMConfig],
        docker_client: Optional[DockerClient] = None,
        logger: Optional[AgentLogger] = None,
        ssh_cfg: Optional[SSHConfig] = None,
    ):
        self.cfg = config
        self.logger = logger or AgentLogger(level=LogLevel.INFO)
        self.docker = docker_client or docker.from_env()
        self.ssh = SSHClient(ssh_cfg or SSHConfig(port=self.cfg.host_ssh_port), logger=self.logger)
        self.container: Union[Container, None] = None
        self._validate_config()
        self._attach_to_existing_container_if_running()

    # ... (methods like start, close, _validate_config, etc.) ...
    def create_container(self):
        self.logger.log("📦 Creating VM container", level=LogLevel.INFO)
        self._ensure_image()
        self.copy_vm_base_data_file()

        mounts = [
            Mount(target="/boot.img", source=str(self.cfg.host_container_data), type="bind"),
            Mount(target="/shared", source=str(self.cfg.host_container_shared_dir), type="bind"),
        ]

        ports = {
            f"{self.cfg.host_vnc_port}/tcp": self.cfg.host_vnc_port,
            "22/tcp": self.cfg.host_ssh_port,
            **{f"{p}/tcp": v for p, v in self.cfg.extra_ports.items()},
        }

        env = {
            "RAM_SIZE": self.cfg.vm_ram,
            "CPU_CORES": str(self.cfg.vm_cpu_cores),
            "DEBUG": "Y" if self.cfg.enable_debug else "N",
            **self.cfg.extra_env,
        }

        container = self.docker.containers.run(
            image=self.cfg.container_image,
            name=self.cfg.container_name,
            environment=env,
            mounts=mounts,
            ports=ports,
            devices=["/dev/kvm", "/dev/net/tun"],
            cap_add=["NET_ADMIN"],
            detach=True,
            # Pass the simple dictionary directly, which is the correct public API usage.
        )
        self.container = cast(Container, container)
        self.logger.log("✅ Container started", level=LogLevel.INFO)

    # ... (rest of the class) ...
    def _validate_config(self):
        if not self.cfg.base_data.exists():
            raise VMCreationError("Base data.img not found")
        all_ports = [self.cfg.host_vnc_port, self.cfg.host_ssh_port]
        if self.cfg.extra_ports:
            all_ports.extend(self.cfg.extra_ports.values())
        for port in all_ports:
            if not (1 <= port <= 65535):
                raise VMCreationError(f"Invalid port: {port}")

    def _attach_to_existing_container_if_running(self) -> None:
        self.logger.log("🧱 Docker Container Check...")
        try:
            container = self.docker.containers.get(self.cfg.container_name)
            container.reload()
            self.container = cast(Container, container)
            if self.container.status in ("running", "paused"):
                self.logger.log(f"🔄 Reusing running container: {self.container.name}", level=LogLevel.INFO)
            else:
                self.logger.log(
                    f"🛑 Found stopped container {self.container.name} (status={self.container.status})",
                    level=LogLevel.DEBUG,
                )
        except NotFound:
            self.logger.log(f"🚫 No existing container named {self.cfg.container_name}", level=LogLevel.DEBUG)

    def _wait_for_ssh_ready(self, timeout: float = 300, interval: float = 5.0):
        self.logger.log_rule("🔐 SSH Initialization")
        host, port = self.ssh.cfg.hostname, self.ssh.cfg.port
        self.logger.log(f"🔍 Waiting for sshd on {host}:{port}…", level=LogLevel.INFO)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                result = self.ssh.exec_command("echo ready")
                if result and result["stdout"].strip() == "ready":
                    self.logger.log("✅ sshd is ready", level=LogLevel.INFO)
                    return
            except Exception as exc:
                self.logger.log(f"⏳ ssh probe failed: {exc}", level=LogLevel.DEBUG)
            time.sleep(interval)
        raise TimeoutError(f"sshd not reachable within {timeout}s")

    def _ensure_image(self):
        try:
            self.docker.images.get(self.cfg.container_image)
        except ImageNotFound:
            self.logger.log(f"📥 Pulling image {self.cfg.container_image}", level=LogLevel.DEBUG)
            self.docker.images.pull(self.cfg.container_image)

    def copy_vm_base_data_file(self):
        self.cfg.host_container_dir.mkdir(parents=True, exist_ok=True)
        self.logger.log(f"📦 Copying VM base file to {self.cfg.host_container_data}", level=LogLevel.INFO)
        shutil.copy(self.cfg.base_data, self.cfg.host_container_data)
        self.logger.log("✅ Copied VM base file", level=LogLevel.DEBUG)

    def cleanup(self, delete_storage: bool = True):
        if self.container:
            try:
                self.container.stop()
                self.container.remove(force=True, v=True)
                self.logger.log(f"Container {self.cfg.container_name} stopped & removed", level=LogLevel.INFO)
            except NotFound:
                self.logger.log(f"Container {self.cfg.container_name} already removed.", level=LogLevel.DEBUG)
            finally:
                self.container = None

        if delete_storage and self.cfg.host_container_dir.exists():
            shutil.rmtree(self.cfg.host_container_dir, ignore_errors=True)

        self.ssh.close()

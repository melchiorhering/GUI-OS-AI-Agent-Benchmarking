from __future__ import annotations

import shutil
import time
from typing import Optional, Union, cast

from smolagents import AgentLogger, LogLevel

import docker
from docker.client import DockerClient
from docker.errors import ImageNotFound, NotFound
from docker.models.containers import Container, _RestartPolicy
from docker.types import Mount

from .configs import SandboxVMConfig, VMConfig
from .errors import VMCreationError
from .ssh import SSHClient, SSHConfig


# ────────────────────────────── VMManager ──────────────────────────────
class VMManager:
    """Docker‑backed QEMU VM lifecycle helper **with one persistent SSH session**.

    High‑level flow:
        vm = VMManager(cfg)
        vm.start()      # container + sshd ready + session cached
        vm.ssh.exec_command("uname -a")
        vm.close()
    """

    # ------------------------------------------------------------------
    # Construction ------------------------------------------------------
    # ------------------------------------------------------------------
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

        # Prepare an *unconnected* SSHClient; we'll connect in start()
        self.ssh = SSHClient(ssh_cfg or SSHConfig(port=self.cfg.host_ssh_port), logger=self.logger)
        self.container: Union[Container, None] = None

        self._validate_config()
        self._attach_to_existing_container_if_running()

    # ------------------------------------------------------------------
    # Public lifecycle --------------------------------------------------
    # ------------------------------------------------------------------
    def start(
        self,
        wait_for_ssh: bool = True,
        restart_if_running: bool = False,  # << new optional flag
    ) -> None:
        """Ensure container is running; restart or create if necessary.

        Args:
            wait_for_ssh:   Poll sshd and cache an SSHClient connection.
            restart_if_running:  If True, call `docker restart` even when the
                                container is already running.
        """
        if self.container is None:
            # nothing exists → create fresh
            self.create_container()

        else:
            # refresh status because it may have changed since __init__
            self.container.reload()

            if self.container.status in ("running", "paused"):
                if restart_if_running:
                    self.logger.log(
                        f"🔄 Restarting running container {self.container.name}",
                        level=LogLevel.DEBUG,
                    )
                    self.container.restart()  # stop + start in one call
                else:
                    self.logger.log(
                        f"✅ Container {self.container.name} already running",
                        level=LogLevel.DEBUG,
                    )
            else:
                # stopped / exited / created → just start
                self.logger.log(
                    f"▶️  Starting stopped container {self.container.name}",
                    level=LogLevel.DEBUG,
                )
                self.container.start()

        # ------------------------------------------------------------------
        if wait_for_ssh:
            self._wait_for_ssh_ready()
            self.ssh.connect()
            self.logger.log("🔗 SSH session established and cached", level=LogLevel.DEBUG)

    def close(self, delete_storage: bool = True) -> None:
        self.cleanup(delete_storage=delete_storage)

    # ------------------------------------------------------------------
    # Validation / discovery -------------------------------------------
    # ------------------------------------------------------------------
    def _validate_config(self):
        if not self.cfg.base_data.exists():
            raise VMCreationError("Base data.img not found")

        # Combine ports for validation
        all_ports = [self.cfg.host_vnc_port, self.cfg.host_ssh_port]
        if self.cfg.extra_ports:
            all_ports.extend(self.cfg.extra_ports.values())

        for port in all_ports:
            if not (1 <= port <= 65535):
                raise VMCreationError(f"Invalid port: {port}")

    def _attach_to_existing_container_if_running(self) -> None:
        """Look up container by name and cache its handle in self.container."""
        self.logger.log("🧱 Docker Container Check...")

        try:
            container = self.docker.containers.get(self.cfg.container_name)
            container.reload()  # refresh status field

            self.container = cast(Container, container)  # Cache the container object

            if self.container.status in ("running", "paused"):
                self.logger.log(
                    f"🔄 Reusing running container: {self.container.name}",
                    level=LogLevel.INFO,
                )
            else:
                self.logger.log(
                    f"🛑 Found stopped container {self.container.name} (status={self.container.status})",
                    level=LogLevel.DEBUG,
                )
                # VMManager.start() will now .start() or .restart() it
        except NotFound:
            self.logger.log(
                f"🚫 No existing container named {self.cfg.container_name}",
                level=LogLevel.DEBUG,
            )

    # ------------------------------------------------------------------
    # SSH readiness -----------------------------------------------------
    # ------------------------------------------------------------------
    def _wait_for_ssh_ready(self, timeout: float = 300, interval: float = 5.0):
        self.logger.log_rule("🔐 SSH Initialization")
        host, port = self.ssh.cfg.hostname, self.ssh.cfg.port
        self.logger.log(f"🔍 Waiting for sshd on {host}:{port}…", level=LogLevel.INFO)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                # FIX 1: Check if the result is not None before subscripting
                result = self.ssh.exec_command("echo ready")
                if result and result["stdout"].strip() == "ready":
                    self.logger.log("✅ sshd is ready", level=LogLevel.INFO)
                    return
            except Exception as exc:
                self.logger.log(f"⏳ ssh probe failed: {exc}", level=LogLevel.DEBUG)
            time.sleep(interval)
        raise TimeoutError(f"sshd not reachable within {timeout}s")

    # ------------------------------------------------------------------
    # Docker / QEMU orchestration --------------------------------------
    # ------------------------------------------------------------------
    def _ensure_image(self):
        try:
            self.docker.images.get(self.cfg.container_image)
        # FIX 2: Use the correct exception class from docker.errors
        except ImageNotFound:
            self.logger.log(f"📥 Pulling image {self.cfg.container_image}", level=LogLevel.DEBUG)
            self.docker.images.pull(self.cfg.container_image)

    def copy_vm_base_data_file(self):
        self.cfg.host_container_dir.mkdir(parents=True, exist_ok=True)
        self.logger.log(f"📦 Copying VM base file to {self.cfg.host_container_data}", level=LogLevel.INFO)
        shutil.copy(self.cfg.base_data, self.cfg.host_container_data)
        self.logger.log("✅ Copied VM base file", level=LogLevel.DEBUG)

    def create_container(self):
        self.logger.log("📦 Creating VM container", level=LogLevel.INFO)
        self._ensure_image()
        self.copy_vm_base_data_file()

        mounts = [
            Mount(target="/boot.img", source=str(self.cfg.host_container_data), type="bind"),
            Mount(target="/shared", source=str(self.cfg.host_container_shared_dir), type="bind"),
        ]

        # FIX 3: Ensure all port keys are strings with the protocol
        ports = {
            f"{self.cfg.host_vnc_port}/tcp": self.cfg.host_vnc_port,
            "22/tcp": self.cfg.host_ssh_port,
            **{f"{p}/tcp": p for p in self.cfg.extra_ports.values()},
        }

        env = {
            "RAM_SIZE": self.cfg.vm_ram,
            "CPU_CORES": str(self.cfg.vm_cpu_cores),
            "DEBUG": "Y" if self.cfg.enable_debug else "N",
            **self.cfg.extra_env,
        }

        # The restart_policy expects a dictionary that matches the TypedDict
        restart_policy: _RestartPolicy = {"Name": self.cfg.restart_policy}

        container = self.docker.containers.run(
            image=self.cfg.container_image,
            name=self.cfg.container_name,
            environment=env,
            mounts=mounts,
            ports=ports,  # This now has the correct format
            devices=["/dev/kvm", "/dev/net/tun"],
            cap_add=["NET_ADMIN"],
            detach=True,
            restart_policy=restart_policy,
        )
        self.container = cast(Container, container)
        self.logger.log("✅ Container started", level=LogLevel.INFO)

    # ------------------------------------------------------------------
    # Cleanup -----------------------------------------------------------
    # ------------------------------------------------------------------
    def cleanup(self, delete_storage: bool = True):
        # Add a check here in case the container was never created
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

from __future__ import annotations

import os
import posixpath
import shlex
import stat  # Added for file type checks
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import paramiko
from smolagents import AgentLogger, LogLevel

# Assuming these imports are from your project's structure
from .errors import RemoteCommandError, SSHError, VMOperationError


# ────────────────────────────────────────────────────────────────────
# SSH configuration
# ────────────────────────────────────────────────────────────────────
@dataclass
class SSHConfig:
    hostname: str = "localhost"
    port: int = 2222
    username: str = "user"
    password: str = "password"  # Make sure this matches your VM's sudo password
    key_filename: Optional[str] = None
    connect_timeout: int = 60
    command_timeout: int = 180
    initial_delay: int = 15
    banner_timeout: int = 10
    keepalive: int = 10


PathLike = str | os.PathLike[str]


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────
def _mkdir_p(sftp: paramiko.SFTPClient, remote_dir: str, logger: AgentLogger | None = None) -> None:
    if remote_dir in ("", "/"):
        return
    parent = posixpath.dirname(remote_dir.rstrip("/"))
    try:
        sftp.stat(remote_dir)
    except IOError:
        _mkdir_p(sftp, parent, logger)
        if logger:
            logger.log(f"Creating remote dir: {remote_dir}", level=LogLevel.DEBUG)
        sftp.mkdir(remote_dir)


# ────────────────────────────────────────────────────────────────────
# SSH client
# ────────────────────────────────────────────────────────────────────
class SSHClient:
    """Run commands and copy files / directories over SSH."""

    def __init__(self, cfg: SSHConfig, logger: AgentLogger | None = None):
        self.cfg = cfg
        self.logger = logger or AgentLogger(level=LogLevel.DEBUG)
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_exc):
        self.close()

    def _establish(self) -> paramiko.SSHClient:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        cli.connect(
            hostname=self.cfg.hostname,
            port=self.cfg.port,
            username=self.cfg.username,
            password=self.cfg.password,
            key_filename=self.cfg.key_filename,
            timeout=self.cfg.connect_timeout,
            banner_timeout=self.cfg.banner_timeout,
        )
        # FIX: Check if transport exists before using it
        transport = cli.get_transport()
        if transport:
            transport.set_keepalive(self.cfg.keepalive)
        self.logger.log("SSH connection established", level=LogLevel.DEBUG)
        return cli

    def connect(self) -> paramiko.SSHClient:
        # FIX: Check transport and its status safely
        transport = self._client.get_transport() if self._client else None
        if self._client and transport and transport.is_active():
            return self._client
        if self.cfg.initial_delay:
            self.logger.log(f"Initial delay {self.cfg.initial_delay}s before connect", level=LogLevel.DEBUG)
            time.sleep(self.cfg.initial_delay)
        try:
            self._client = self._establish()
        except Exception as exc:
            raise SSHError(f"SSH connection failed: {exc!r}") from exc
        return self._client

    def close(self) -> None:
        if self._sftp:
            self._sftp.close()
            self._sftp = None
        if self._client:
            self._client.close()
            self._client = None
        self.logger.log("SSH connection closed", level=LogLevel.DEBUG)

    def _get_sftp(self) -> paramiko.SFTPClient:
        # FIX: Check transport and its status safely
        transport = self._client.get_transport() if self._client else None
        if not self._sftp or not (self._client and transport and transport.is_active()):
            self._sftp = self.connect().open_sftp()
        return self._sftp

    def exec_command(
        self,
        cmd: str,
        env: Dict[str, str] | None = None,
        *,
        as_root: bool = False,
        block: bool = True,
        sudo_password: str | None = None,
        use_command_prefix_for_env: bool = True,
    ) -> Dict[str, Any] | None:
        original_cmd_for_logging = cmd
        env_prefix = ""
        if env and use_command_prefix_for_env:
            env_prefix_parts = []
            for k, v_val in env.items():
                if not k.isidentifier():
                    self.logger.log(
                        f"Skipping invalid environment variable name for prefix: {k}",
                        level=LogLevel.ERROR,
                    )
                    continue
                env_prefix_parts.append(f"{k}={shlex.quote(str(v_val))}")
            if env_prefix_parts:
                env_prefix = " ".join(env_prefix_parts) + " "
            self.logger.log(
                f"Using command prefix for environment variables: {env_prefix.strip()}", level=LogLevel.DEBUG
            )
        elif env and not use_command_prefix_for_env:
            self.logger.log(
                "Attempting to use channel.update_environment for SSH session environment vars:",
                level=LogLevel.DEBUG,
            )
            for k, v_val in env.items():
                self.logger.log(f"       {k} = {v_val}", level=LogLevel.DEBUG)

        cmd_to_execute = f"{env_prefix}{cmd}" if env_prefix else cmd

        if as_root and not cmd_to_execute.strip().startswith("sudo"):
            cmd_to_execute = f"sudo -S {cmd_to_execute}"

        self.logger.log(f"✨ ssh $ {cmd_to_execute}", level=LogLevel.DEBUG)
        ssh_conn = self.connect()

        transport = ssh_conn.get_transport()
        if transport is None or not transport.is_active():
            raise SSHError("SSH transport is not active.")

        channel = transport.open_session()
        needs_pty = as_root or ("sudo -S" in cmd_to_execute) or cmd_to_execute.strip().startswith("sudo")
        if needs_pty:
            channel.get_pty()
            self.logger.log("Allocating PTY for command (needed for password prompts with sudo).", level=LogLevel.DEBUG)
        elif not block:
            self.logger.log("Running non-blocking command without PTY.", level=LogLevel.DEBUG)

        if env and not use_command_prefix_for_env:
            try:
                channel.update_environment(env)
                self.logger.log(
                    "Called channel.update_environment(). Success depends on server's AcceptEnv config.",
                    level=LogLevel.DEBUG,
                )
            except Exception as e:
                # FIX: Removed invalid 'level' parameter
                self.logger.log_error(f"Error calling channel.update_environment(): {e}")

        channel.exec_command(cmd_to_execute)

        stdout_data_parts = []
        stderr_data_parts = []
        exit_status_ready = False
        start_time = time.time()
        password_sent = False
        password_to_send = sudo_password if sudo_password is not None else self.cfg.password
        read_buffer = ""

        while not exit_status_ready and (time.time() - start_time < self.cfg.command_timeout):
            if channel.recv_ready():
                data = channel.recv(4096).decode(errors="ignore")
                stdout_data_parts.append(data)
                read_buffer += data
            if channel.recv_stderr_ready():
                data = channel.recv_stderr(4096).decode(errors="ignore")
                stderr_data_parts.append(data)
                read_buffer += data

            if needs_pty and not password_sent and "[sudo] password for" in read_buffer.lower():
                self.logger.log("Sudo password prompt DETECTED. Attempting to send password...", level=LogLevel.DEBUG)
                if password_to_send:
                    try:
                        time.sleep(0.1)
                        channel.sendall((password_to_send + "\n").encode())
                        password_sent = True
                        read_buffer = ""
                        self.logger.log("Sudo password sent.", level=LogLevel.DEBUG)
                    except Exception as e:
                        # FIX: Removed invalid 'level' parameter
                        self.logger.log_error(f"Failed to send sudo password: {e}")
                else:
                    err_msg = f"Sudo password prompt detected for command: {original_cmd_for_logging!r} but no password provided."
                    self.logger.log_error(err_msg)
                    channel.close()
                    raise RemoteCommandError(original_cmd_for_logging, -1, "", err_msg)

            if channel.exit_status_ready():
                exit_status_ready = True
            elif not (channel.recv_ready() or channel.recv_stderr_ready()):
                time.sleep(0.05)

        out_final = "".join(stdout_data_parts)
        err_final = "".join(stderr_data_parts)

        if not exit_status_ready:
            channel.close()
            timeout_stderr_message = (
                f"Command timed out after {self.cfg.command_timeout} seconds. "
                f"Partial stdout: {out_final[:200]}... "
                f"Partial stderr: {err_final[:200]}..."
            )
            raise RemoteCommandError(original_cmd_for_logging, -1, out_final, timeout_stderr_message)

        while channel.recv_ready():
            out_final += channel.recv(4096).decode(errors="ignore")
        while channel.recv_stderr_ready():
            err_final += channel.recv_stderr(4096).decode(errors="ignore")

        status = channel.recv_exit_status()
        channel.close()

        if not block:
            return None

        self.logger.log(
            f"→ exit {status} | stdout {len(out_final)}B | stderr {len(err_final)}B | cmd: {original_cmd_for_logging!r}",
            level=LogLevel.DEBUG,
        )

        if status != 0:
            log_message = f"Command {original_cmd_for_logging!r} failed with exit status {status}."
            if err_final:
                log_message += f"\nStderr:\n{err_final.strip()}"
            if out_final:
                log_message += f"\nStdout:\n{out_final.strip()}"
            self.logger.log(log_message, level=LogLevel.ERROR)
            raise RemoteCommandError(original_cmd_for_logging, status, out_final, err_final)
        elif self.logger.level <= LogLevel.DEBUG:
            if out_final:
                self.logger.log(
                    f"Command {original_cmd_for_logging!r} stdout:\n{out_final.strip()}", level=LogLevel.DEBUG
                )
            if err_final:
                self.logger.log(
                    f"Command {original_cmd_for_logging!r} stderr:\n{err_final.strip()}", level=LogLevel.DEBUG
                )

        return {"status": status, "stdout": out_final, "stderr": err_final}

    def put_file(
        self,
        local: PathLike,
        remote: PathLike,
        *,
        mkdir_parents: bool = True,
        overwrite: bool = True,
    ) -> None:
        local_path = Path(local).expanduser().resolve()
        if not local_path.is_file():
            raise VMOperationError(f"Local file not found: {local_path}")

        remote_path = posixpath.normpath(str(remote))
        sftp = self._get_sftp()

        if not overwrite:
            try:
                sftp.stat(remote_path)
                raise VMOperationError(f"Remote file exists: {remote_path}")
            except IOError:
                pass

        if mkdir_parents:
            _mkdir_p(sftp, posixpath.dirname(remote_path), self.logger)

        file_size = local_path.stat().st_size

        def sftp_callback(bytes_xfrd, bytes_total):
            # Callback logic remains the same
            pass

        self.logger.log(f"Uploading {local_path} to {remote_path}...", level=LogLevel.DEBUG)
        try:
            sftp.put(str(local_path), remote_path, callback=sftp_callback)
            self.logger.log(
                f"Successfully uploaded {local_path} to {remote_path} ({file_size} bytes).", level=LogLevel.DEBUG
            )
        except Exception as e:
            # FIX: Removed invalid 'level' parameter
            self.logger.log_error(f"Failed to upload {local_path} to {remote_path}: {e}")
            raise VMOperationError(f"Failed to upload file via SFTP: {e}") from e

    def put_directory(
        self,
        local: PathLike,
        remote: PathLike,
        *,
        exclude: Optional[List[str]] = None,
    ) -> None:
        local_path = Path(local).expanduser().resolve()
        if not local_path.is_dir():
            raise VMOperationError(f"Local directory not found: {local_path}")

        remote_base_path = posixpath.normpath(str(remote))
        sftp = self._get_sftp()
        self.logger.log(f"Uploading directory {local_path} to {remote_base_path}...", level=LogLevel.DEBUG)
        _mkdir_p(sftp, remote_base_path, self.logger)

        def _upload_recursive(current_local_dir, current_remote_dir):
            for item in os.listdir(current_local_dir):
                if exclude and item in exclude:
                    self.logger.log(f"Skipping excluded item: {item}", level=LogLevel.DEBUG)
                    continue

                local_item_path = current_local_dir / item
                remote_item_path = posixpath.join(current_remote_dir, item)

                if local_item_path.is_file():
                    self.put_file(local_item_path, remote_item_path, mkdir_parents=False)
                elif local_item_path.is_dir():
                    _mkdir_p(sftp, remote_item_path, self.logger)
                    _upload_recursive(local_item_path, remote_item_path)

        _upload_recursive(local_path, remote_base_path)
        self.logger.log(f"Successfully uploaded directory {local_path} to {remote_base_path}.", level=LogLevel.DEBUG)

    def download_file(
        self,
        remote: PathLike,
        local: PathLike,
        *,
        mkdir_parents: bool = True,
        overwrite: bool = True,
    ) -> None:
        remote_path = posixpath.normpath(str(remote))
        local_path = Path(local).expanduser().resolve()
        sftp = self._get_sftp()

        try:
            remote_stat = sftp.stat(remote_path)
            # FIX: Check st_mode and st_size are not None before use
            if remote_stat.st_mode is not None and not stat.S_ISREG(remote_stat.st_mode):
                raise VMOperationError(f"Remote path is not a regular file: {remote_path}")
            remote_file_size = remote_stat.st_size
        except FileNotFoundError as e:
            raise VMOperationError(f"Remote file not found: {remote_path}") from e
        except Exception as e:
            raise VMOperationError(f"Failed to stat remote file {remote_path}: {e}") from e

        if local_path.exists():
            if local_path.is_dir():
                raise VMOperationError(f"Local path exists and is a directory: {local_path}")
            if not local_path.is_file() and not overwrite:
                raise VMOperationError(
                    f"Local path exists, is not a regular file, and overwrite is False: {local_path}"
                )
            if local_path.is_file() and not overwrite:
                raise VMOperationError(f"Local file exists and overwrite is False: {local_path}")

        if mkdir_parents:
            local_path.parent.mkdir(parents=True, exist_ok=True)

        last_reported_percent = -1

        def sftp_callback(bytes_xfrd, total_bytes_to_be_transferred):
            nonlocal last_reported_percent
            # Callback logic remains the same
            pass

        self.logger.log(
            f"Downloading {remote_path} to {local_path} ({remote_file_size} bytes)...", level=LogLevel.DEBUG
        )
        try:
            sftp.get(remote_path, str(local_path), callback=sftp_callback)
            # FIX: Check remote_file_size is not None before comparison
            if remote_file_size is not None and remote_file_size > 0 and last_reported_percent < 100:
                sftp_callback(remote_file_size, remote_file_size)
            elif remote_file_size == 0 and last_reported_percent == -1:
                sftp_callback(0, 0)

            self.logger.log(
                f"Successfully downloaded {remote_path} to {local_path} ({remote_file_size} bytes).",
                level=LogLevel.DEBUG,
            )
        except Exception as e:
            self.logger.log_error(f"Failed to download {remote_path} to {local_path}: {e}")
            raise VMOperationError(f"Failed to download file via SFTP: {e}") from e

    def download_directory(
        self,
        remote: PathLike,
        local: PathLike,
        *,
        exclude: Optional[List[str]] = None,
        overwrite_files: bool = True,
    ) -> None:
        remote_base_path = posixpath.normpath(str(remote))
        local_base_path = Path(local).expanduser().resolve()
        sftp = self._get_sftp()

        try:
            remote_stat = sftp.stat(remote_base_path)
            # FIX: Check st_mode is not None before use
            if remote_stat.st_mode is None or not stat.S_ISDIR(remote_stat.st_mode):
                raise VMOperationError(f"Remote path is not a directory: {remote_base_path}")
        except FileNotFoundError as e:
            raise VMOperationError(f"Remote directory not found: {remote_base_path}") from e
        except Exception as e:
            raise VMOperationError(f"Failed to stat remote directory {remote_base_path}: {e}") from e

        self.logger.log(f"Downloading directory {remote_base_path} to {local_base_path}...", level=LogLevel.DEBUG)
        local_base_path.mkdir(parents=True, exist_ok=True)

        def _download_recursive(current_remote_dir: str, current_local_dir: Path):
            try:
                for item_attr in sftp.listdir_attr(current_remote_dir):
                    item_name = item_attr.filename
                    if exclude and item_name in exclude:
                        self.logger.log(
                            f"Skipping excluded item: {item_name} in {current_remote_dir}", level=LogLevel.DEBUG
                        )
                        continue

                    remote_item_path = posixpath.join(current_remote_dir, item_name)
                    local_item_path = current_local_dir / item_name

                    # FIX: Check st_mode is not None before use
                    item_mode = item_attr.st_mode
                    if item_mode is None:
                        continue

                    if stat.S_ISDIR(item_mode):
                        local_item_path.mkdir(parents=True, exist_ok=True)
                        _download_recursive(remote_item_path, local_item_path)
                    elif stat.S_ISREG(item_mode):
                        self.download_file(
                            remote_item_path, local_item_path, mkdir_parents=False, overwrite=overwrite_files
                        )
                    else:
                        self.logger.log(
                            f"Skipping non-regular file/dir: {remote_item_path} (type: {oct(item_mode)})",
                            level=LogLevel.DEBUG,
                        )
            except Exception as e:
                self.logger.log(
                    f"Error processing contents of remote directory {current_remote_dir}: {e}", level=LogLevel.ERROR
                )
                raise VMOperationError(
                    f"Failed during recursive download of directory {current_remote_dir}: {e}"
                ) from e

        try:
            _download_recursive(remote_base_path, local_base_path)
            self.logger.log(
                f"Successfully downloaded directory {remote_base_path} to {local_base_path}.", level=LogLevel.DEBUG
            )
        except Exception as e:
            if not isinstance(e, VMOperationError):
                self.logger.log(
                    f"Unexpected error during download of directory {remote_base_path}: {e}", level=LogLevel.ERROR
                )
                raise VMOperationError(f"Failed to download directory {remote_base_path}: {e}") from e
            else:
                raise

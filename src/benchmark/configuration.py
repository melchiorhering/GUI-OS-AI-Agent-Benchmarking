from pathlib import Path
from typing import Union

from smolagents import LogLevel

from agent.sandbox_agent import SandboxCodeAgent

from .task import TaskInput


def upload_script_and_execute(
    agent: SandboxCodeAgent,
    task: TaskInput,
    local_path: Union[str, Path],
    remote_path: Union[str, Path] = "/home/user/Desktop",
) -> None:
    """
    Upload a shell script to the VM and execute it with optional env injection.

    Args:
        agent: The SandboxCodeAgent instance.
        task: The TaskSpec defining the task.
        local_path: Local script path relative to task.task_dir.
        remote_path: Remote directory in the VM to upload and execute in.
    """
    local_path = (task.task_dir / Path(local_path)).resolve()
    script_name = local_path.name
    remote_path = Path(remote_path)

    if not local_path.exists():
        agent.logger.log(f"❌ Local script not found: {local_path}", level=LogLevel.ERROR)
        raise FileNotFoundError(f"{local_path} not found")

    agent.logger.log(f"📤 Uploading script: {local_path} → {remote_path}", level=LogLevel.DEBUG)
    agent.ssh.put_file(local_path, str(remote_path))

    # Add runtime env to VM config
    agent.python_executor.vm.cfg.runtime_env.update(
        {
            "TASK_SETUP_LOG": str(agent.python_executor.vm.cfg.sandbox_task_setup_log),
        }
    )

    try:
        # Ensure it's executable
        agent.logger.log(f"🔒 chmod +x {script_name}", level=LogLevel.DEBUG)
        agent.ssh.exec_command(
            cmd=f"chmod +x {remote_path}",
            as_root=True,
        )

        # Execute script
        agent.logger.log(f"🚀 Executing {script_name}", level=LogLevel.DEBUG)
        result = agent.ssh.exec_command(
            cmd=f"{remote_path}",
            env=agent.python_executor.vm.cfg.runtime_env,
        )
        if result["stderr"]:
            agent.logger.log(f"⚠️ stderr:\n{result['stderr']}", level=LogLevel.ERROR)

        agent.logger.log("✅ Script executed successfully", level=LogLevel.INFO)
    except Exception as e:
        agent.logger.log("❌ Error executing script", level=LogLevel.ERROR)
        agent.logger.log(str(e), level=LogLevel.ERROR)
        raise


def upload_file_to_vm(
    agent: SandboxCodeAgent, task: TaskInput, local_path: Union[str, Path], remote_path: Union[str, Path]
):
    local_path = (task.task_dir / Path(local_path)).resolve()
    agent.logger.log(f"📤 Uploading file to VM: {local_path} → {remote_path}")
    agent.ssh.put_file(local_path, remote_path)


def download_file_from_vm(
    agent: SandboxCodeAgent,
    local_path: Union[str, Path],
    remote_path: Union[str, Path],
    overwrite: bool = True,
):
    """
    Downloads a file from the VM (via agent's SSH client) to a local path.
    Ensures the local parent directory exists.
    """
    local_path_obj = Path(local_path).resolve()
    remote_path_str = str(remote_path)

    # Ensure the local parent directory for the downloaded file exists.
    local_path_obj.parent.mkdir(parents=True, exist_ok=True)

    agent.logger.log(
        f"📥 Downloading file from VM: '{remote_path_str}' to '{local_path_obj}' (overwrite={overwrite})",
    )

    try:
        # Assumes 'agent.ssh' is the attribute holding your SSHClient instance.
        # Adjust 'agent.ssh' if the attribute is named differently (e.g., agent.ssh_client).
        if not hasattr(agent, "ssh"):
            err_msg = "Agent object does not have the 'ssh' attribute for SSH operations."
            agent.logger.log(err_msg, level=LogLevel.ERROR)
            raise AttributeError(err_msg)

        # The agent.ssh.download_file method will handle its own internal logging
        # and will raise VMOperationError or other specific errors on failure.
        agent.ssh.download_file(
            remote=remote_path_str,
            local=local_path_obj,
            overwrite=overwrite,
            mkdir_parents=False,  # Parent directory for local_path_obj is already created above.
            # Set to True if you prefer agent.ssh.download_file to also ensure it.
        )
    except AttributeError:  # Catch if agent.ssh doesn't exist
        raise  # Re-raise, error already logged
    except Exception as e:  # Catch other potential errors from download_file (e.g., VMOperationError, SSHError)
        agent.logger.log(
            f"❌ Failed to download file from VM '{remote_path_str}' to '{local_path_obj}'. Error: {type(e).__name__}: {e}",
            level=LogLevel.ERROR,
        )
        raise  # Re-raise the exception to signal failure to the caller

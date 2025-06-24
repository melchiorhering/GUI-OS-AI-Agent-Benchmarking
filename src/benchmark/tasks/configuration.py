from pathlib import Path
from typing import Union

from smolagents import LogLevel

from agent.executor import SandboxExecutor
from agent.sandbox_agent import SandboxCodeAgent
from sandbox.configs import SandboxVMConfig

from .task import TaskInput


def _get_sandbox_executor(agent: SandboxCodeAgent) -> SandboxExecutor:
    """Checks and returns the SandboxExecutor from an agent."""
    if not isinstance(agent.python_executor, SandboxExecutor):
        msg = "This function requires an agent with a SandboxExecutor."
        agent.logger.log(msg, level=LogLevel.ERROR)
        raise TypeError(msg)
    return agent.python_executor


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
    remote_script_path = Path(remote_path) / script_name

    if not local_path.exists():
        agent.logger.log(f"❌ Local script not found: {local_path}", level=LogLevel.ERROR)
        raise FileNotFoundError(f"{local_path} not found")

    executor = _get_sandbox_executor(agent)

    agent.logger.log(f"📤 Uploading script: {local_path} → {remote_script_path}", level=LogLevel.DEBUG)
    agent.ssh.put_file(local_path, str(remote_script_path))

    if isinstance(executor.vm.cfg, SandboxVMConfig):
        executor.vm.cfg.runtime_env.update(
            {
                "TASK_SETUP_LOG": str(executor.vm.cfg.sandbox_task_setup_log),
            }
        )

    try:
        agent.logger.log(f"🔒 chmod +x {remote_script_path}", level=LogLevel.DEBUG)
        agent.ssh.exec_command(
            cmd=f"chmod +x {remote_script_path}",
            as_root=True,
        )

        agent.logger.log(f"🚀 Executing {remote_script_path}", level=LogLevel.DEBUG)
        result = agent.ssh.exec_command(
            cmd=str(remote_script_path),
            env=executor.vm.cfg.runtime_env,
        )

        if result and result.get("stderr"):
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
    agent.ssh.put_file(local_path, str(remote_path))


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

    local_path_obj.parent.mkdir(parents=True, exist_ok=True)

    agent.logger.log(
        f"📥 Downloading file from VM: '{remote_path_str}' to '{local_path_obj}' (overwrite={overwrite})",
    )

    try:
        if not hasattr(agent, "ssh"):
            err_msg = "Agent object does not have the 'ssh' attribute for SSH operations."
            agent.logger.log(err_msg, level=LogLevel.ERROR)
            raise AttributeError(err_msg)

        agent.ssh.download_file(
            remote=remote_path_str,
            local=local_path_obj,
            overwrite=overwrite,
            mkdir_parents=False,
        )
    except AttributeError:
        raise
    except Exception as e:
        agent.logger.log(
            f"❌ Failed to download file from VM '{remote_path_str}' to '{local_path_obj}'. Error: {type(e).__name__}: {e}",
            level=LogLevel.ERROR,
        )
        raise

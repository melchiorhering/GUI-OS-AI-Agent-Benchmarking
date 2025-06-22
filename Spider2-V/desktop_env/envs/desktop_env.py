from __future__ import annotations

import logging
import os
import subprocess
import time
from functools import cached_property
from typing import Any, Callable, Dict, List, Optional, Union

import gymnasium as gym
from desktop_env.controllers.python import PythonController
from desktop_env.controllers.setup import SetupController
from desktop_env.evaluators import getters, metrics

from . import _get_vm_path  # Assuming this provides a relative or base path

logger = logging.getLogger("desktopenv.env")

Metric = Callable[[Any, Any], float]
Getter = Callable[[gym.Env, Dict[str, Any]], Any]

# --- VMRUN EXECUTABLE PATH ---
# This path must be the absolute WSL path to your vmrun.exe
# Example: "/mnt/c/Program Files (x86)/VMware/VMware Workstation/vmrun.exe"
# Ensure this matches where vmrun.exe is accessible from WSL.
# This will be used to explicitly call vmrun.exe instead of relying on PATH or aliases.
VMRUN_EXECUTABLE_WSL_PATH = "/mnt/c/Program Files (x86)/VMware/VMware Workstation/vmrun.exe"


# --- Helper Function for Path Conversion (kept as before) ---
def _get_windows_path(wsl_path: str) -> str:
    r"""Converts a WSL path (e.g., /mnt/c/...) to a Windows path (e.g., C:\...) using wslpath."""
    try:
        cmd = ["wslpath", "-w", wsl_path]
        # For wslpath itself, we want byte output to decode it here
        windows_path_bytes = subprocess.check_output(cmd, stderr=subprocess.PIPE, shell=False)
        windows_path = windows_path_bytes.decode().strip()
        return windows_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Error converting WSL path to Windows path using wslpath: {e.stderr.decode().strip()}")
        raise RuntimeError(f"Could not convert WSL path {wsl_path} to Windows path. Is wslpath installed?")
    except FileNotFoundError:
        logger.error("wslpath command not found. Ensure it's installed and in your WSL distro PATH.")
        raise RuntimeError("wslpath command not found.")


# --- Modified _execute_command (minimal changes to use absolute vmrun path) ---
def _execute_command(command: List[str]) -> str | None:  # Changed return type to match actual returns
    def _is_contained_in(a, b):
        for v in set(a):
            if a.count(v) > b.count(v):
                return False
        return True

    # --- Modify `command` to use the absolute vmrun path if it's a vmrun command ---
    original_command = list(command)  # Keep a copy of original for checking
    if command and command[0] == "vmrun":
        command[0] = VMRUN_EXECUTABLE_WSL_PATH  # Modify the first element in place or create new list
        # For vmrun start, we will explicitly not capture output to prevent potential blocking/buffering issues.
        # This aligns with the original Popen for 'start' not capturing.

    # Log the actual command being executed (useful for debugging)
    logger.info(f"Executing command: {' '.join(command)}")

    # Specially handled for the `vmrun` command with "start" subcommand
    # We still check against the *original* command to identify the "start" operation
    if _is_contained_in([f"{VMRUN_EXECUTABLE_WSL_PATH}", "-T", "ws", "start"], original_command):
        # Use subprocess.Popen for non-blocking execution of 'start'
        # Redirect stdout/stderr to DEVNULL to prevent blocking/buffering issues
        # and ensure the command truly runs in the background for the script.
        try:
            p = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
            # The original code had p.wait(). If it's hanging, removing p.wait() allows the script to continue.
            # If the script *must* wait for vmrun start to finish its *internal* setup,
            # then p.wait() or subprocess.run() is needed, and the hang would indicate vmrun itself is slow.
            # For now, let's assume `vmrun start` initiates the VM and returns control quickly enough.
            logger.info("`vmrun start` command initiated in background.")
            # Note: No return value here for this branch as it's fire-and-forget.
        except Exception as e:
            # Catch errors directly from Popen call (e.g., executable not found, permissions)
            logger.error(f"\033[91mError launching vmrun start: {e}\033[0m")
            raise  # Re-raise the exception to propagate it

    else:
        # For other commands (list, getGuestIPAddress, revertToSnapshot, snapshot, stop)
        # These commands are expected to run synchronously and return output.
        try:
            result = subprocess.run(
                command,  # Use the modified command list
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,  # Original timeout
                text=True,  # Decodes stdout/stderr to strings automatically
                encoding="utf-8",
                check=True,  # Raises CalledProcessError on non-zero exit
                shell=False,  # Execute directly, not through a shell
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            # Output from `text=True` is already decoded
            error_output = (e.stdout or "") + (e.stderr or "")
            raise Exception(f"\033[91mError executing command: {error_output.strip()}\033[0m")
        except subprocess.TimeoutExpired:
            # Use original_command for user-facing error message
            raise Exception(f"\033[91mCommand timed out: {' '.join(original_command)}\033[0m")

    return None  # Ensure this function always returns something in non-error cases for the Popen branch


class DesktopEnv(gym.Env):
    """
    DesktopEnv with OpenAI Gym interface. It provides a desktop environment for setting and evaluating desktop automation tasks.
    """

    def __init__(
        self,
        path_to_vm: str = None,
        snapshot_name: str = "init_state",
        action_space: str = "computer_13",
        cache_dir: str = "cache",
        headless: bool = False,
        require_a11y_tree: bool = True,
        require_terminal: bool = False,
        proxy: Dict[str, Any] = {},
    ):
        """
        Args:
            path_to_vm (str): path to .vmx file
            snapshot_name (str): snapshot name to revert to, default to "init_state"
            action_space (str): "computer_13" | "pyautogui"
            cache_dir (str): cache directory to cache task-related stuffs like
              reference file for evaluation
            screen_size (Tuple[int]): screen size of the VM
            headless (bool): whether to run the VM in headless mode
            require_a11y_tree (bool): whether to require accessibility tree
            require_terminal (bool): whether to require terminal output
            proxy (Dict[str, Any]): proxy configuration dict, which includes the following keys:
                host: host ip address in the eye of VM instance, namely the LAN ip address of the host
                port: proxy port, usually the port number defined in 127.0.0.1:{port}
                types: connection types, by default, ['http', 'https'] is enough
        """

        # Initialize environment variables
        self.path_to_vm = os.path.abspath(
            os.path.expandvars(os.path.expanduser(path_to_vm if path_to_vm else _get_vm_path()))
        )
        self.snapshot_name = snapshot_name
        self.cache_dir_base: str = cache_dir
        # todo: add the logic to get the screen size from the VM
        self.headless = headless
        self.require_a11y_tree = require_a11y_tree
        self.require_terminal = require_terminal

        # Convert the WSL absolute path to a Windows-style path for vmrun commands
        self.vm_path_windows_format = _get_windows_path(self.path_to_vm)
        logger.info(f"VM configured with WSL path: {self.path_to_vm}")
        logger.info(f"VM configured with Windows path: {self.vm_path_windows_format}")

        # Initialize emulator and controller
        self._start_emulator()
        self.vm_ip = self._get_vm_ip()
        self.controller = PythonController(vm_ip=self.vm_ip)
        self.setup_controller = SetupController(vm_ip=self.vm_ip, cache_dir=self.cache_dir_base)

        # mode: human or machine
        self.instruction = None
        assert action_space in ["computer_13", "pyautogui"]
        self.action_space = action_space

        # episodic stuffs, like counters, will be updated or reset
        # when calling self.reset()
        self._traj_no: int = -1
        self._step_no: int = 0
        self.action_history: List[Dict[str, Any]] = []

        # proxy initialization
        self.proxy = proxy
        if self.proxy:  # set the proxy address for the host machine
            for tp in self.proxy.get("types", ["http", "https"]):
                os.environ[f"{tp}_proxy"] = f"http://127.0.0.1:{proxy['port']}"
            os.environ["no_proxy"] = f"localhost,127.0.0.1,{self.vm_ip}"  # add the VM IP to the no_proxy list

    @cached_property
    def vm_platform(self):
        return self.controller.get_vm_platform()

    @cached_property
    def vm_screen_size(self):
        return self.controller.get_vm_screen_size()

    def _start_emulator(self):
        while True:
            try:
                # vmrun list returns Windows paths
                output = _execute_command([f"{VMRUN_EXECUTABLE_WSL_PATH}", "-T", "ws", "list"])
                output_lines: List[str] = output.splitlines() if output else []  # Handle case where output is None

                # Check if the VM's Windows path is in the vmrun list output
                found_running = False
                for line in output_lines:
                    if self.vm_path_windows_format.lower() in line.lower():
                        found_running = True
                        break

                if found_running:
                    logger.info(f"VM of path {self.vm_path_windows_format} is already running ...")
                    break
                else:
                    logger.info(f"Starting VM of path {self.vm_path_windows_format} ...")
                    start_cmd_parts = [f"{VMRUN_EXECUTABLE_WSL_PATH}", "-T", "ws", "start", self.vm_path_windows_format]
                    if self.headless:
                        start_cmd_parts.append("nogui")

                    _execute_command(start_cmd_parts)
                    time.sleep(20)  # Give VM time to start up
            except Exception as e:
                logger.error(f"Error during VM startup check: {e}")
                time.sleep(5)

    def _revert_to_snapshot(self, snapshot_name: Optional[str] = None):
        if snapshot_name is None:
            snapshot_name = self.snapshot_name
        logger.info(f"Reverting {self.vm_path_windows_format} to snapshot {snapshot_name} ...")
        _execute_command(
            [f"{VMRUN_EXECUTABLE_WSL_PATH}", "-T", "ws", "revertToSnapshot", self.vm_path_windows_format, snapshot_name]
        )
        time.sleep(5)

    def _get_vm_ip(self):
        max_retries = 20
        logger.info("Getting IP Address...")
        for _ in range(max_retries):
            try:
                output = _execute_command(
                    [
                        f"{VMRUN_EXECUTABLE_WSL_PATH}",
                        "-T",
                        "ws",
                        "getGuestIPAddress",
                        self.vm_path_windows_format,
                        "-wait",
                    ]
                )
                if output:
                    ip_address = output.strip()
                    logger.info(f"IP address: {ip_address}")
                    return ip_address
                else:
                    raise Exception("vmrun getGuestIPAddress returned no output.")
            except Exception as e:
                logger.warning(f"Error getting IP address: {e}. Retrying...")
                time.sleep(5)
        raise Exception("Failed to get VM IP address!")

    def _save_state(self):
        _execute_command(
            [f"{VMRUN_EXECUTABLE_WSL_PATH}", "-T", "ws", "snapshot", self.vm_path_windows_format, self.snapshot_name]
        )  # Corrected "wssnapshot" to "ws", "snapshot"

    def _get_obs(self):
        return {
            "screenshot": self.controller.get_screenshot(),
            "accessibility_tree": self.controller.get_accessibility_tree() if self.require_a11y_tree else None,
            "terminal": self.controller.get_terminal_output() if self.require_terminal else None,
            "error": "",
            "instruction": self.instruction,
        }

    def _set_task_info(self, task_config: Dict[str, Any]):
        self.task_id: str = task_config["id"]
        self.cache_dir: str = os.path.join(self.cache_dir_base, self.task_id)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.instruction = task_config["instruction"]
        self.config = task_config["config"] if "config" in task_config else []

        self.evaluator = task_config["evaluator"]
        self.metric: Metric = (
            [getattr(metrics, func) for func in self.evaluator["func"]]
            if isinstance(self.evaluator["func"], list)
            else getattr(metrics, self.evaluator["func"])
        )
        self.metric_conj: str = self.evaluator.get("conj", "and")
        if "result" in self.evaluator and len(self.evaluator["result"]) > 0:
            self.result_getter: Getter = (
                [getattr(getters, f"get_{res['type']}") for res in self.evaluator["result"]]
                if isinstance(self.evaluator["result"], list)
                else getattr(getters, f"get_{self.evaluator['result']['type']}")
            )
        else:
            self.result_getter = [None] * len(self.metric) if isinstance(self.metric, list) else None

        if "expected" in self.evaluator and len(self.evaluator["expected"]) > 0:
            self.expected_getter: Getter = (
                [getattr(getters, f"get_{exp['type']}") if exp else None for exp in self.evaluator["expected"]]
                if isinstance(self.evaluator["expected"], list)
                else getattr(getters, f"get_{self.evaluator['expected']['type']}")
            )
        else:
            self.expected_getter = [None] * len(self.metric) if isinstance(self.metric, list) else None
        self.metric_options: Union[List[Dict[str, Any]], Dict[str, Any]] = (
            [opt if opt else {} for opt in self.evaluator["options"]]
            if isinstance(self.evaluator.get("options", {}), list)
            else self.evaluator["options"]
            if "options" in self.evaluator
            else [{}] * len(self.metric)
            if isinstance(self.metric, list)
            else {}
        )

        assert not isinstance(self.evaluator["func"], list) or (
            len(self.metric) == len(self.result_getter) == len(self.expected_getter) == len(self.metric_options)
        )

    def reset(self, task_config: Optional[Dict[str, Any]] = None, proxy: Dict[str, Any] = {}) -> Dict[str, Any]:
        logger.info("Resetting environment ...")
        self._traj_no += 1
        self._step_no = 0
        self.action_history.clear()

        self._revert_to_snapshot()
        self._start_emulator()

        if task_config is not None:
            self._set_task_info(task_config)
            self.setup_controller.reset_cache_dir(self.cache_dir)

        logger.info("Setting up environment ...")
        if not self.setup_controller._network_setup(self.vm_platform):
            logger.error("Network is not available!")
        if self.proxy or proxy:
            proxy = proxy if proxy else self.proxy
            self.setup_controller._proxy_setup(proxy=proxy, controller=self.controller)
            logger.info(f"Set http(s) proxy to: {proxy['host']}:{proxy['port']} for VM.")

        if task_config is not None:
            self.setup_controller.setup(self.config)
        time.sleep(5)
        logger.info("Environment setup complete.")

        observation = self._get_obs()
        return observation

    def step(self, action, pause=0.5):
        self._step_no += 1
        self.action_history.append(action)

        reward = 0
        done = False
        info = {}

        if action in ["WAIT", "FAIL", "DONE"] or (
            isinstance(action, dict) and action.get("action_type") in ["WAIT", "FAIL", "DONE"]
        ):
            if isinstance(action, dict):
                action = action["action_type"]
            if action == "WAIT":
                time.sleep(pause)
                info = {"status": "success", "output": "", "error": ""}
            elif action == "FAIL":
                done = True
                info = {"status": "success", "output": "", "error": ""}
            elif action == "DONE":
                done = True
                info = {"status": "success", "output": "", "error": ""}
        else:
            if self.action_space == "computer_13":
                info = self.controller.execute_action(action)
            elif self.action_space == "pyautogui":
                info = self.controller.execute_python_command(action)
        time.sleep(pause)
        observation = self._get_obs()

        return observation, reward, done, info

    def evaluate(self):
        self.setup_controller.setup(self.evaluator.get("postconfig", []))

        if self.evaluator["func"] == "infeasible":
            if len(self.action_history) > 0 and self.action_history[-1] == "FAIL":
                return 1
            else:
                return 0
        else:
            if len(self.action_history) > 0 and self.action_history[-1] == "FAIL":
                return 0

        if isinstance(self.metric, list):
            results = []
            for idx, metric_func in enumerate(self.metric):
                try:
                    config = self.evaluator["result"][idx]
                    result_state = self.result_getter[idx](self, config)
                except FileNotFoundError:
                    logger.error("File not found!")
                    if self.metric_conj == "and":
                        return 0

                expected = self.evaluator["expected"][idx]
                expected_state = self.expected_getter[idx](self, expected) if expected else None

                metric_score: int = (
                    metric_func(result_state, expected_state, **self.metric_options[idx])
                    if expected_state is not None
                    else metric_func(result_state, **self.metric_options[idx])
                )

                if self.metric_conj == "and" and float(metric_score) == 0.0:
                    return 0
                elif self.metric_conj == "or" and float(metric_score) == 1.0:
                    return 1
                else:
                    results.append(metric_score)
            return sum(results) / len(results) if self.metric_conj == "and" else max(results)
        else:
            try:
                result_state = self.result_getter(self, self.evaluator["result"])
            except FileNotFoundError:
                logger.error("File not found!")
                return 0

            expected_state = (
                self.expected_getter(self, self.evaluator["expected"]) if "expected" in self.evaluator else None
            )

            metric_score: float = (
                self.metric(result_state, expected_state, **self.metric_options)
                if expected_state is not None
                else self.metric(result_state, **self.metric_options)
            )

            return metric_score

    def render(self, mode="rgb_array"):
        if mode == "rgb_array":
            return self.controller.get_screenshot()
        else:
            raise ValueError("Unsupported render mode: {}".format(mode))

    def close(self):
        _execute_command([f"{VMRUN_EXECUTABLE_WSL_PATH}", "stop", self.path_to_vm])

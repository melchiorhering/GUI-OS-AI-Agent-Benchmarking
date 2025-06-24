import base64
import json
import pickle
import re
import sys
import time
import uuid
from pathlib import Path
from textwrap import dedent
from typing import Any, List

import requests
from smolagents.agents import AgentError, AgentLogger
from smolagents.monitoring import LogLevel
from smolagents.remote_executors import RemotePythonExecutor
from websocket import create_connection

# Allow imports from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.configs import SandboxVMConfig
from sandbox.sandbox import SandboxVMManager


class SandboxExecutor(RemotePythonExecutor):
    def __init__(
        self,
        additional_imports: List[str],
        logger: AgentLogger,
        config: SandboxVMConfig,
        preserve_on_exit: bool = False,
        **kwargs,
    ):
        super().__init__(additional_imports, logger)
        self.logger.log_rule("🎢 Sandbox Executor Initialization")
        self.kernel_id = None
        self.ws = None
        self._exited = False

        try:
            self.logger.log("✨ Initializing SandboxExecutor...", level=LogLevel.INFO)
            self.vm = SandboxVMManager(config=config, logger=self.logger, preserve_on_exit=preserve_on_exit, **kwargs)

            self.logger.log("🔌 Connecting to Sandbox VM...", level=LogLevel.DEBUG)
            self.vm.connect_or_start()

            self.host = config.host_sandbox_jupyter_kernel_host
            self.port = config.host_sandbox_jupyter_kernel_port
            self.base_url = f"http://{self.host}:{self.port}"
            self.ws_url = f"ws://{self.host}:{self.port}"

            self._initialize_kernel_connection()

            self.installed_packages = self.install_packages(additional_imports)
            self.logger.log("✅ Sandbox Ready ✅")

        except Exception as e:
            self.logger.log_error(f"SandboxExecutor init failed: {e}")
            self.cleanup()
            raise

    def _strip_ansi_codes_from_list(self, traceback_lines: List[str]) -> str:
        """
        Joins traceback lines into a single string and removes ANSI escape codes.
        """
        if not traceback_lines:
            return "No traceback information available."
        ansi_escape_pattern = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        cleaned_lines = [ansi_escape_pattern.sub("", line) for line in traceback_lines]
        return "\n".join(cleaned_lines)

    def _initialize_kernel_connection(self, retries: int = 5, delay: float = 5):
        self.logger.log_rule("🧠 Kernel Initialization")
        self.logger.log("🔗 Fetch existing kernels", level=LogLevel.DEBUG)
        existing_kernels = []
        try:
            r = requests.get(f"{self.base_url}/api/kernels", timeout=5)
            if r.status_code == 200:
                existing_kernels = r.json()
                self.logger.log(f"🔄 Found {len(existing_kernels)} existing kernels", level=LogLevel.INFO)
        except Exception as e:
            self.logger.log_error(f"⚠️ Failed to fetch existing kernels: {e}")

        if existing_kernels:
            self.kernel_id = existing_kernels[0]["id"]
            self.logger.log(f"🔁 Reusing existing kernel: {self.kernel_id}", level=LogLevel.INFO)
        else:
            for attempt in range(retries):
                try:
                    self.logger.log(
                        f"🆕 Creating new kernel (attempt {attempt + 1}/{retries})...", level=LogLevel.DEBUG
                    )
                    r = requests.post(f"{self.base_url}/api/kernels", timeout=5)
                    if r.status_code == 201:
                        self.kernel_id = r.json()["id"]
                        self.logger.log(f"✅ Created new kernel: {self.kernel_id}", level=LogLevel.INFO)
                        break
                    else:
                        self.logger.log_error(f"❌ Kernel creation failed: {r.status_code} — {r.text}")
                except Exception as e:
                    self.logger.log_error(f"⚠️ Kernel creation attempt {attempt + 1} failed: {e}")
                    time.sleep(delay)
            else:
                raise RuntimeError("❌ Failed to create a new kernel after retries.")

        ws_url = f"{self.ws_url}/api/kernels/{self.kernel_id}/channels"
        self.logger.log(f"🌐 Connecting WebSocket to: {ws_url}", level=LogLevel.DEBUG)
        for attempt in range(retries):
            try:
                # websocket_timeout = getattr(self.vm.config, "websocket_timeout", 120)
                self.ws = create_connection(ws_url)
                self.logger.log("📡 WebSocket connected to kernel.", level=LogLevel.INFO)
                return
            except Exception as e:
                self.logger.log(
                    f"⏳ WebSocket connection failed (attempt {attempt + 1}/{retries}): {e}", level=LogLevel.DEBUG
                )
                time.sleep(delay)
        raise RuntimeError("❌ Failed to establish WebSocket connection after retries.")

    def install_packages(self, additional_imports: list[str]):
        packages = additional_imports + ["smolagents", "pyautogui"]
        _, execution_logs = self.run_code_raise_errors(f"!pip install {' '.join(set(packages))}")
        self.logger.log(execution_logs)
        return packages

    def run_code_raise_errors(self, code: str, return_final_answer: bool = False) -> tuple[Any, str]:
        """
        Execute code and return result based on whether it's a final answer.
        """
        try:
            wrapped_code = code
            if return_final_answer:
                match = self.final_answer_pattern.search(code)
                if match:
                    pre_final_answer_code = self.final_answer_pattern.sub("", code)
                    result_expr = match.group(1)
                    wrapped_code = pre_final_answer_code + dedent(f"""
                        import pickle, base64
                        _result = {result_expr}
                        print("RESULT_PICKLE:" + base64.b64encode(pickle.dumps(_result)).decode())
                        """)

            msg_id = self._send_execute_request(wrapped_code)

            if self.ws is None:
                raise ConnectionError("WebSocket connection is not active.")

            outputs = []
            result = None
            waiting_for_idle = False

            while True:
                msg = json.loads(self.ws.recv())
                msg_type = msg.get("msg_type", "")
                parent_msg_id = msg.get("parent_header", {}).get("msg_id")

                if parent_msg_id != msg_id:
                    continue

                if msg_type == "stream":
                    text = msg["content"]["text"]
                    if return_final_answer and text.startswith("RESULT_PICKLE:"):
                        pickle_data = text[len("RESULT_PICKLE:") :].strip()
                        result = pickle.loads(base64.b64decode(pickle_data))
                        waiting_for_idle = True
                    else:
                        outputs.append(text)
                elif msg_type == "error":
                    traceback = msg["content"].get("traceback", [])
                    raise AgentError("\n".join(traceback), self.logger)
                elif msg_type == "status" and msg["content"]["execution_state"] == "idle":
                    if not return_final_answer or waiting_for_idle:
                        break

            return result, "".join(outputs)

        except Exception as e:
            self.logger.log_error(f"Code execution failed: {e}")
            raise

    def _send_execute_request(self, code: str) -> str:
        """Send code execution request to kernel."""

        if self.ws is None:
            raise ConnectionError("Cannot send request: WebSocket connection is not active.")

        # Generate a unique message ID
        msg_id = str(uuid.uuid4())

        # Create execute request
        execute_request = {
            "header": {
                "msg_id": msg_id,
                "username": "anonymous",
                "session": str(uuid.uuid4()),
                "msg_type": "execute_request",
                "version": "5.0",
            },
            "parent_header": {},
            "metadata": {},
            "content": {
                "code": code,
                "silent": False,
                "store_history": True,
                "user_expressions": {},
                "allow_stdin": False,
            },
        }

        # Pylance now knows self.ws is not None at this point
        self.ws.send(json.dumps(execute_request))
        return msg_id

    def cleanup(self):
        if getattr(self, "_exited", False):
            return
        try:
            self.logger.log("🪩 Cleaning up sandbox resources...", level=LogLevel.INFO)
            if self.kernel_id:
                requests.delete(f"{self.base_url}/api/kernels/{self.kernel_id}", timeout=5)
            if self.ws:
                self.ws.close()
            if hasattr(self, "vm"):
                self.vm.__exit__(None, None, None)
            self.logger.log("✅ Cleanup complete.", level=LogLevel.INFO)
        except Exception as e:
            self.logger.log_error(f"Cleanup failed: {e}")
        self._exited = True

    def delete(self):
        self.cleanup()

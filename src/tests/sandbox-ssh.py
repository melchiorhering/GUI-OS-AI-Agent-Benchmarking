from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from smolagents import AgentLogger, LogLevel

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.ssh import SSHClient, SSHConfig  # noqa: E402


def run_ssh_smoke_tests() -> None:
    logger = AgentLogger(level=LogLevel.INFO)

    ssh_cfg = SSHConfig(
        hostname=os.getenv("SSH_HOST", "localhost"),
        port=int(os.getenv("SSH_PORT", "2222")),
        username=os.getenv("SSH_USER", "user"),
        password=os.getenv("SSH_PASS", "password"),
        initial_delay=5,
        banner_timeout=30,
    )
    ssh = SSHClient(ssh_cfg, logger=logger)

    print("✅ Connected via SSH")

    # Echo test
    print("▶️ Running echo test...")
    result = ssh.exec_command("echo it_works")["stdout"].strip()
    assert result == "it_works", f"Echo failed: {result}"
    print("✅ Echo test passed")

    # Root check
    print("▶️ Running root check...")
    uid = ssh.exec_command("id -u", as_root=True)["stdout"].strip()
    assert uid == "0", f"Expected root uid=0 but got {uid}"
    print("✅ Root permission test passed")

    # Upload + run shell script
    print("▶️ Running script upload + execute test...")

    script_content = "#!/bin/bash\necho success > /tmp/ssh_test_success.txt\n"
    local_script = Path(tempfile.gettempdir()) / "ssh_test_script.sh"
    local_script.write_text(script_content)
    remote_dir = "/home/user/ssh_test"
    remote_script = f"{remote_dir}/ssh_test_script.sh"

    ssh.exec_command(f"mkdir -p {remote_dir}")
    ssh.put_file(local_script, remote_script)
    ssh.exec_command("chmod +x ssh_test_script.sh", cwd=remote_dir)
    ssh.exec_command("./ssh_test_script.sh", cwd=remote_dir)

    # Confirm side-effect
    check = ssh.exec_command("cat /tmp/ssh_test_success.txt")["stdout"].strip()
    assert check == "success", f"Script did not produce expected output: {check}"
    print("✅ Script executed and verified")

    print("🎉 All SSH smoke tests passed.")


if __name__ == "__main__":
    run_ssh_smoke_tests()

import sys
import time
from pathlib import Path

# Allow imports from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sandbox.sandbox import SandboxClient


def main():
    client = SandboxClient(host="localhost", port=8765)

    # Step 3: Use the dynamically generated client
    health = client.health()
    print(f"🔍 Health check response: {health}")

    # Step 4: Try screenshot
    screenshot_result = client.take_screenshot()
    print(f"📸 Screenshot taken at: {screenshot_result['screenshot_path']}")

    # Step 5: Try recording start/stop
    start_recording = client.start_recording()
    print(f"🔴 Recording started: {start_recording}")

    time.sleep(10)  # simulate some activity

    stop_recording = client.stop_recording()
    print(f"🛑 Recording stopped: {stop_recording}")


if __name__ == "__main__":
    main()

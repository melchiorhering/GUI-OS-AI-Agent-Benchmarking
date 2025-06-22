import json
import time

import requests
from websocket import create_connection


def test_kernel_gateway_connection(base_url: str, ws_url: str, retries: int = 5, delay: float = 2.0):
    print("🔌 Testing connection to Jupyter Kernel Gateway...")

    # Step 1: Fetch existing kernels
    try:
        resp = requests.get(f"{base_url}/api/kernels", timeout=5)
        resp.raise_for_status()
        kernels = resp.json()
        print(f"✅ Gateway reachable. Found {len(kernels)} existing kernel(s).")
        for i, k in enumerate(kernels, 1):
            print(
                f"   {i}. Kernel ID: {k['id']}, Name: {k.get('name', 'unknown')}, Last Activity: {k['last_activity']}"
            )
    except Exception as e:
        print(f"❌ Cannot reach Kernel Gateway at {base_url}/api/kernels: {e}")
        return False

    # Step 2: Create a new kernel using the registered name
    kernel_id = None
    for attempt in range(retries):
        try:
            print(f"⏳ Creating kernel (attempt {attempt + 1})...")
            r = requests.post(f"{base_url}/api/kernels", json={"name": "action-kernel"}, timeout=5)
            r.raise_for_status()
            kernel_id = r.json()["id"]
            print(f"✅ New kernel created with ID: {kernel_id}")
            break
        except Exception as e:
            print(f"❌ Kernel creation failed: {e}")
            time.sleep(delay)
    if not kernel_id:
        print("❌ Failed to create a kernel after retries")
        return False

    # Step 3: Connect to kernel via WebSocket
    ws_kernel_url = f"{ws_url}/api/kernels/{kernel_id}/channels"
    for attempt in range(retries):
        try:
            print(f"🔗 Connecting WebSocket to: {ws_kernel_url} (attempt {attempt + 1})")
            ws = create_connection(ws_kernel_url)
            print("✅ WebSocket connection established")

            # Send simple code to verify execution works
            exec_request = {
                "header": {
                    "msg_id": "1",
                    "username": "agent",
                    "session": "1",
                    "msg_type": "execute_request",
                    "version": "5.0",
                },
                "parent_header": {},
                "metadata": {},
                "content": {"code": "print('Hello from action-kernel')", "silent": False},
            }
            ws.send(json.dumps(exec_request))
            print("📤 Sent simple code to kernel")

            # Read responses
            for _ in range(5):
                msg = json.loads(ws.recv())
                msg_type = msg["header"]["msg_type"]
                if msg_type == "stream":
                    print(f"📥 Kernel output: {msg['content']['text'].strip()}")
                    break

            ws.close()
            return True
        except Exception as e:
            print(f"❌ WebSocket attempt failed: {e}")
            time.sleep(delay)

    print("❌ Failed to connect via WebSocket after retries")
    return False


if __name__ == "__main__":
    test_kernel_gateway_connection(base_url="http://localhost:8888", ws_url="ws://localhost:8888")

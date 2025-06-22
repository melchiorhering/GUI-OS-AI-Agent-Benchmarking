# server/main.py
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Literal, Optional

import pyautogui
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont, ImageGrab

from src.pyxcursor import Xcursor
from src.recording import (
    recorded_actions,
    start_action_recording,
    stop_action_recording,
    start_screen_recording,
    stop_screen_recording,
    video_recording_state,
    init_recording_module
)
from src.utils import clear_shared_dir_simpler

# ───────────────────── Logger Setup ─────────────────────
log_dir = Path(os.getenv("SHARED_DIR", "/mnt/container")) / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_path = log_dir / os.getenv("OBSERVATION_LOG", "observation-server.log")

logger = logging.getLogger("SandboxServer")
logger.setLevel(logging.DEBUG if os.getenv("DEBUG") == "1" else logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler = logging.FileHandler(log_path)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# ───────────────────── Lifespan Event Setup ─────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "8765")
    logger.info(f"🔧 FastAPI Server starting up. Logging to: {log_path}")
    logger.info(f"🚀 Listening on http://{host}:{port}")

    # Initialize the recording module with shared resources
    # Ensure screen_width, screen_height, and cursor are determined before this.
    global cursor, screen_width, screen_height, shared_dir # Ensure these are accessible
    init_recording_module(shared_dir, cursor, screen_width, screen_height)
    logger.info("Recording module initialized from main lifespan.")

    yield
    # This code runs on shutdown
    logger.info("🧹 FastAPI server is shutting down...")
    # Ensure all recordings stop if server shuts down while active
    if video_recording_state["is_recording"]:
        logger.info("Stopping active video recording during shutdown.")
        stop_screen_recording()
    if recorded_actions: # Check if action recording is active
        logger.info("Stopping active action recording during shutdown.")
        # Note: stop_action_recording returns the actions but doesn't save them here.
        # If saving on unexpected shutdown is critical, replicate the save logic here.
        stop_action_recording()


# ───────────────────── FastAPI Setup ─────────────────────
app = FastAPI(
    title="Sandbox REST Server",
    description="API for screenshots and recording GUI actions in a sandboxed VM.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

shared_dir = Path(os.getenv("SHARED_DIR", "/mnt/container"))
clear_shared_dir_simpler(shared_dir)


# ───────────────────── Cursor & Screen Info ─────────────────────
try:
    # Moved numpy import from here, it's now primarily in recording.py for screen recording
    # Still needed for PIL Image to np.array conversion in take_screenshot
    import numpy as np
    cursor = Xcursor()
    logger.info("✅ Cursor initialized")
except Exception as e:
    logger.warning(f"⚠️ Failed to initialize Xcursor: {e}")
    cursor = None

try:
    screen_width, screen_height = pyautogui.size()
    logger.info(f"🖥️ Screen size: {screen_width}x{screen_height}")
except Exception as e:
    logger.warning(f"⚠️ pyautogui fallback: {e}")
    screen_width, screen_height = 1920, 1080


# ───────────────────── Screenshot Utility (Unchanged - still in main.py) ─────────────────────
def take_screenshot(method: Literal["pyautogui", "pillow"] = "pillow", step: Optional[str] = None) -> Dict[str, str]:
    try:
        screenshot_dir = shared_dir / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
        filename = f"{method}-{timestamp}.png"

        if step:
            filepath = screenshot_dir / f"{step}-{filename}"
        else:
            filepath = screenshot_dir / filename

        if method == "pyautogui":
            pyautogui.screenshot(imageFilename=str(filepath))
            img = Image.open(filepath)
        elif method == "pillow":
            img = ImageGrab.grab()
        else:
            raise ValueError(f"Unknown screenshot method: {method}")

        arr = np.array(img)
        screenshot_img = Image.fromarray(arr)
        draw = ImageDraw.Draw(screenshot_img)

        mouse_x, mouse_y = pyautogui.position()
        cursor_offset_x, cursor_offset_y = -2, -3
        adjusted_x = mouse_x + cursor_offset_x
        adjusted_y = mouse_y + cursor_offset_y

        box_half_size = 20
        draw.rectangle(
            [
                adjusted_x - box_half_size,
                adjusted_y - box_half_size,
                adjusted_x + box_half_size,
                adjusted_y + box_half_size,
            ],
            outline="red",
            width=2,
        )

        font = ImageFont.load_default()
        text = f"mouse: x={mouse_x} y={mouse_y}"
        bbox = font.getbbox(text)
        text_x = adjusted_x - (bbox[2] - bbox[0]) // 2
        text_y = adjusted_y - box_half_size - (bbox[3] - bbox[1]) - 5
        draw.text((text_x, text_y), text, fill="red", font=font)

        if cursor:
            try:
                cursor_arr = cursor.getCursorImageArrayFast()
                if cursor_arr is not None:
                    cursor_img = Image.fromarray(cursor_arr)
                    screenshot_img.paste(
                        cursor_img, (mouse_x - cursor_img.width // 2, mouse_y - cursor_img.height // 2), cursor_img
                    )
            except Exception as e:
                logger.warning(f"⚠️ Cursor overlay failed: {e}")

        screenshot_img.save(filepath)

        return {
            "screenshot_path": str(filepath.relative_to(shared_dir)),
            "mouse_position": [mouse_x, mouse_y],
            "screen_size": [screen_width, screen_height],
        }

    except Exception as e:
        logger.error(f"❌ Screenshot error: {e}")
        return {"status": "error", "message": str(e)}


# ───────────────────── API Endpoints ─────────────────────
@app.get("/health")
def health_check():
    try:
        return {"status": "ok", "observation_server": "reachable"}
    except Exception as e:
        logger.error(f"❌ healthcheck failed: {e}")
        return {"status": "error", "observation_server": "unreachable", "error": str(e)}


@app.get("/screenshot")
async def screenshot_endpoint(method: str = Query(default="pyautogui", enum=["pyautogui", "pillow"])):
    return take_screenshot(method=method)


@app.get("/record")
async def record_endpoint(
    mode: Literal["start", "stop"],
    fps: int = Query(video_recording_state["fps"], ge=1, le=30, description="Frames per second for video recording"),
    codec: str = Query(video_recording_state["codec"], description="Video codec for MP4 (e.g., 'mp4v', 'XVID', 'MJPG')")
):
    """
    Manages both action recording (JSON) and screen recording (MP4 video).

    - `mode="start"`: Starts both action and screen recording.
    - `mode="stop"`: Stops both recordings and saves their respective files.
    """
    recordings_dir = shared_dir / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    if mode == "start":
        # --- Start Action Recording ---
        action_record_result = start_action_recording() # Call the imported function
        results["action_recording_status"] = action_record_result["status"]

        # --- Start Screen Recording ---
        screen_record_result = start_screen_recording(fps=fps, codec=codec) # Call the imported function
        results["screen_recording_status"] = screen_record_result["status"]
        if "filepath" in screen_record_result:
            results["screen_recording_file"] = screen_record_result["filepath"]
        if "message" in screen_record_result:
            results["screen_recording_message"] = screen_record_result["message"]

        return results

    elif mode == "stop":
        # --- Stop Action Recording ---
        action_record_result = stop_action_recording() # Call the imported function
        results["action_recording_status"] = action_record_result["status"]
        if action_record_result["status"] == "action_recording_stopped":
            actions = action_record_result["actions"] # Get actions from the returned dict
            action_filename = f"actions-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%S')}.json"
            action_filepath = recordings_dir / action_filename
            try:
                action_filepath.write_text(json.dumps(actions, indent=2), encoding="utf-8")
                results["action_recording_file"] = str(action_filepath.relative_to(shared_dir))
                results["num_actions"] = len(actions)
                logger.info(f"Action recording stopped and saved: {action_filepath}")
            except Exception as e:
                logger.error(f"❌ Failed to save action recording: {e}")
                results["action_recording_status"] = "error"
                results["action_recording_message"] = str(e)
        else: # e.g., "no_action_recording"
             results["action_recording_message"] = "No active action recording to stop."

        # --- Stop Screen Recording ---
        screen_record_result = stop_screen_recording() # Call the imported function
        results["screen_recording_status"] = screen_record_result["status"]
        if "filepath" in screen_record_result:
            results["screen_recording_file"] = screen_record_result["filepath"]
        if "message" in screen_record_result:
            results["screen_recording_message"] = screen_record_result["message"]

        return results
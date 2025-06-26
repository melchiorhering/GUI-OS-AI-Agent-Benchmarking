# obervation-server/main.py
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Literal, Optional, Union, List
import tempfile

import pyautogui
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont, ImageGrab
import numpy as np
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
# The problematic function is no longer imported
# from src.utils import clear_shared_dir_simpler

# ───────────────────── Logger Setup ─────────────────────
# This setup is correct for being managed by a startup script.
logger = logging.getLogger("SandboxServer")
logger.setLevel(logging.DEBUG if os.getenv("DEBUG") == "1" else logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)


# ───────────────────── Lifespan & Shared Directory Setup ─────────────────────

# Define shared_dir globally so it can be accessed in endpoints and lifespan
shared_dir: Path

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    Initializes shared resources like the output directory.
    """
    global shared_dir  # Declare that we are modifying the global variable
    host = os.getenv("FASTAPI_HOST", "0.0.0.0")
    port = os.getenv("FASTAPI_PORT", "8765")

    # Determine the shared directory path.
    # Prioritize the SHARED_DIR env var, otherwise fall back to a user's home directory.
    # This avoids potential permission issues with a fixed path like /mnt/container.
    env_shared_dir = os.getenv("SHARED_DIR", "/mnt/container")
    if env_shared_dir:
        shared_dir = Path(env_shared_dir)
        logger.info(f"✅ Using shared directory from environment variable: {shared_dir}")
    else:
        # Fallback to a directory within the user's home directory
        shared_dir = Path.home() / "observation-server-output"
        logger.warning(f"⚠️ SHARED_DIR env var not set. Falling back to default: {shared_dir}")

    # Ensure the directory exists and is writable.
    try:
        shared_dir.mkdir(parents=True, exist_ok=True)
        # Create a temporary file to test writability
        with tempfile.TemporaryFile(dir=shared_dir):
            pass
        logger.info(f"✅ Shared directory is ready and writable at: {shared_dir}")
    except OSError as e:
        logger.critical(f"❌ FATAL: Could not create or write to shared directory: {e}")
        # The app will likely fail on file operations. Logging as critical.

    # The problematic directory clearing function call has been REMOVED.

    logger.info("🔧 FastAPI Server starting up. Logging configured via startup script.")
    logger.info(f"🚀 Listening on http://{host}:{port}")

    # Initialize the recording module with shared resources
    global cursor, screen_width, screen_height
    init_recording_module(shared_dir, cursor, screen_width, screen_height)
    logger.info("✅ Recording module initialized from main lifespan.")

    yield

    # This code runs on shutdown
    logger.info("🧹 FastAPI server is shutting down...")
    if video_recording_state["is_recording"]:
        logger.info("Stopping active video recording during shutdown.")
        stop_screen_recording()
    if recorded_actions:
        logger.info("Stopping active action recording during shutdown.")
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

# The shared_dir initialization is now handled in the lifespan manager.

# ───────────────────── Cursor & Screen Info ─────────────────────
try:
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
def take_screenshot(method: Literal["pyautogui", "pillow"] = "pillow", step: Optional[str] = None) -> Dict[str, Union[str, List[int]]]:
    """
    Captures a screenshot, annotates it, and saves it.
    """
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
    return {"status": "ok", "observation_server": "reachable"}


@app.get("/screenshot")
async def screenshot_endpoint(method: str = Query(default="pyautogui", enum=["pyautogui", "pillow"])):
    # Corrected the variable name from 'metho' to 'method'
    return take_screenshot(method=method)


@app.get("/record")
async def record_endpoint(
    mode: Literal["start", "stop"],
    fps: int = Query(video_recording_state["fps"], ge=1, le=30, description="Frames per second for video recording"),
    codec: str = Query(video_recording_state["codec"], description="Video codec for MP4 (e.g., 'mp4v', 'XVID', 'MJPG')")
):
    """
    Manages both action recording (JSON) and screen recording (MP4 video).
    """
    recordings_dir = shared_dir / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    if mode == "start":
        action_record_result = start_action_recording()
        results["action_recording_status"] = action_record_result["status"]

        screen_record_result = start_screen_recording(fps=fps, codec=codec)
        results["screen_recording_status"] = screen_record_result["status"]
        if "filepath" in screen_record_result:
            results["screen_recording_file"] = screen_record_result["filepath"]
        if "message" in screen_record_result:
            results["screen_recording_message"] = screen_record_result["message"]

        return results

    elif mode == "stop":
        action_record_result = stop_action_recording()
        results["action_recording_status"] = action_record_result["status"]
        if action_record_result["status"] == "action_recording_stopped":
            actions = action_record_result["actions"]
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
        else:
            results["action_recording_message"] = "No active action recording to stop."

        screen_record_result = stop_screen_recording()
        results["screen_recording_status"] = screen_record_result["status"]
        if "filepath" in screen_record_result:
            results["screen_recording_file"] = screen_record_result["filepath"]
        if "message" in screen_record_result:
            results["screen_recording_message"] = screen_record_result["message"]

        return results

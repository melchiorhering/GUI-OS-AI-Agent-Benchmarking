import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import cv2
import numpy as np
import pyautogui
from PIL import Image, ImageGrab
from pynput import keyboard, mouse

from src.utils import flush_typing_sequence

# Get logger from main app
logger = logging.getLogger("SandboxServer")
if not logger.handlers:  # Fallback if logger not yet configured in main
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("SandboxServer")


# ───────────────────── Global State for Action Recording ─────────────────────
recording = False  # Controls action recording
recorded_actions = []
_mouse_listener = None
_keyboard_listener = None
_typing_buffer = []  # Stores (char, timestamp)
_typing_timeout = 1.5
_last_key_time = None

# ───────────────────── Global State for Screen Recording ─────────────────────
video_recording_state = {
    "is_recording": False,
    "video_writer": None,
    "recording_thread": None,
    "output_filepath": None,
    "fps": 10,  # Frames per second for the video capture
    "codec": "mp4v",  # Codec for MP4 (e.g., "mp4v", "XVID", "MJPG")
}

# ───────────────────── Shared Resources (from main.py context) ─────────────────────
# These need to be accessible to recording functions, but are initialized in main.py
# We'll pass them in or make them accessible globally if possible.
# For simplicity, let's make them global in this module, set by an init function.
shared_dir = Path(os.getenv("SHARED_DIR", "/mnt/container"))
cursor = None  # Will be set by init_recording_module
screen_width = 1920  # Will be set by init_recording_module
screen_height = 1080  # Will be set by init_recording_module


def init_recording_module(s_dir: Path, cur, s_width: int, s_height: int):
    """Initializes global variables used by recording functions."""
    global shared_dir, cursor, screen_width, screen_height
    shared_dir = s_dir
    cursor = cur
    screen_width = s_width
    screen_height = s_height
    logger.info("Recording module initialized with shared resources.")


# ───────────────────── Action Recording Functions ─────────────────────
def _record_user_actions():
    global _mouse_listener, _keyboard_listener

    def on_click(x, y, button, pressed):
        if recording:
            action = {
                "event": "click",
                "x": x,
                "y": y,
                "button": str(button),
                "pressed": pressed,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            recorded_actions.append(action)

    def on_press(key):
        global _last_key_time, _typing_buffer

        now = time()
        try:
            char = key.char
        except AttributeError:
            char = str(key)

        # Flush old typing buffer if user paused typing
        if _last_key_time is None or (now - _last_key_time) > _typing_timeout:
            flush_typing_sequence(recorded_actions, _typing_buffer)

        if len(char) == 1:
            _typing_buffer.append((char, datetime.now(timezone.utc)))
        else:
            flush_typing_sequence(recorded_actions, _typing_buffer)
            recorded_actions.append(
                {
                    "event": "hotkey",
                    "key": char,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        _last_key_time = now

    _mouse_listener = mouse.Listener(on_click=on_click)
    _keyboard_listener = keyboard.Listener(on_press=on_press)
    _mouse_listener.start()
    _keyboard_listener.start()


def start_action_recording():
    """Starts recording user mouse and keyboard actions."""
    global recording, _recording_thread
    if recording:
        logger.warning("Action recording is already active.")
        return {"status": "already_recording_actions"}

    recording = True
    recorded_actions.clear()  # Clear previous actions
    _recording_thread = threading.Thread(target=_record_user_actions, daemon=True)
    _recording_thread.start()
    logger.info("Action recording started.")
    return {"status": "action_recording_started"}


def stop_action_recording():
    """Stops recording user actions and returns the recorded actions."""
    global recording, _mouse_listener, _keyboard_listener
    if not recording:
        logger.warning("No action recording is active.")
        return {"status": "no_action_recording", "actions": []}

    recording = False

    if _mouse_listener:
        _mouse_listener.stop()
        _mouse_listener = None

    if _keyboard_listener:
        _keyboard_listener.stop()
        _keyboard_listener = None

    flush_typing_sequence(recorded_actions, _typing_buffer)  # Ensure last typing is flushed

    logger.info(f"Action recording stopped. Captured {len(recorded_actions)} actions.")
    return {"status": "action_recording_stopped", "actions": recorded_actions.copy()}


# ───────────────────── Screen Recording Functions ─────────────────────


def _record_screen_loop_internal():
    """Captures screen frames and writes them to a video file.
    This function runs in a separate thread."""
    logger.info(f"Starting screen recording loop at {video_recording_state['fps']} FPS.")
    while video_recording_state["is_recording"]:
        try:
            # Capture the screen
            img = ImageGrab.grab(bbox=(0, 0, screen_width, screen_height))
            frame = np.array(img)

            # Convert RGB to BGR for OpenCV
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            # Optional: Add cursor/mouse position overlay to video frames
            if cursor:
                mouse_x, mouse_y = pyautogui.position()
                cursor_offset_x, cursor_offset_y = -2, -3
                adjusted_x = mouse_x + cursor_offset_x
                adjusted_y = mouse_y + cursor_offset_y

                # Draw red box around cursor (on the OpenCV frame)
                box_half_size = 20
                cv2.rectangle(
                    frame,
                    (adjusted_x - box_half_size, adjusted_y - box_half_size),
                    (adjusted_x + box_half_size, adjusted_y + box_half_size),
                    (0, 0, 255),  # Red in BGR
                    2,
                )

                # Draw position text (on the OpenCV frame)
                font = cv2.FONT_HERSHEY_SIMPLEX
                text = f"mouse: x={mouse_x} y={mouse_y}"
                text_size = cv2.getTextSize(text, font, 0.7, 2)[0]
                text_x = adjusted_x - text_size[0] // 2
                text_y = adjusted_y - box_half_size - text_size[1] - 5
                cv2.putText(frame, text, (text_x, text_y), font, 0.7, (0, 0, 255), 2)

                try:
                    cursor_arr = cursor.getCursorImageArrayFast()
                    if cursor_arr is not None:
                        cursor_img_pil = Image.fromarray(cursor_arr)

                        if cursor_img_pil.mode == "RGBA":
                            cursor_img_cv = cv2.cvtColor(np.array(cursor_img_pil), cv2.COLOR_RGBA2BGR)
                            alpha_channel = cursor_img_pil.split()[-1]
                            alpha_np = np.array(alpha_channel) / 255.0
                            alpha_mask_3ch = cv2.merge([alpha_np, alpha_np, alpha_np])
                        else:
                            cursor_img_cv = cv2.cvtColor(np.array(cursor_img_pil), cv2.COLOR_RGB2BGR)
                            alpha_mask_3ch = None

                        cx, cy = mouse_x - cursor_img_cv.shape[1] // 2, mouse_y - cursor_img_cv.shape[0] // 2
                        cx = max(0, min(cx, screen_width - cursor_img_cv.shape[1]))
                        cy = max(0, min(cy, screen_height - cursor_img_cv.shape[0]))

                        roi = frame[cy : cy + cursor_img_cv.shape[0], cx : cx + cursor_img_cv.shape[1]]

                        if alpha_mask_3ch is not None:
                            blended_roi = roi * (1 - alpha_mask_3ch) + cursor_img_cv * alpha_mask_3ch
                            frame[cy : cy + cursor_img_cv.shape[0], cx : cx + cursor_img_cv.shape[1]] = blended_roi
                        else:
                            frame[cy : cy + cursor_img_cv.shape[0], cx : cx + cursor_img_cv.shape[1]] = cursor_img_cv

                except Exception as e:
                    logger.warning(f"⚠️ Cursor overlay for video failed: {e}")

            if video_recording_state["video_writer"] is not None:
                video_recording_state["video_writer"].write(frame)
            else:
                logger.error("Video writer is None during recording loop!")
                video_recording_state["is_recording"] = False

        except Exception as e:
            logger.error(f"❌ Error during screen capture: {e}")
            video_recording_state["is_recording"] = False

        time.sleep(1 / video_recording_state["fps"])

    if video_recording_state["video_writer"]:
        video_recording_state["video_writer"].release()
        logger.info("Video writer released.")


def start_screen_recording(fps: int = 10, codec: str = "mp4v") -> Dict[str, str]:
    """Starts the screen recording thread."""
    if video_recording_state["is_recording"]:
        logger.warning("Screen recording is already in progress.")
        return {"status": "already_recording"}

    recordings_dir = shared_dir / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    filename = f"screen-recording-{timestamp}.mp4"
    filepath = recordings_dir / filename

    video_recording_state["output_filepath"] = filepath
    video_recording_state["fps"] = fps
    video_recording_state["codec"] = codec

    fourcc = cv2.VideoWriter_fourcc(*codec)
    try:
        video_recording_state["video_writer"] = cv2.VideoWriter(
            str(filepath), fourcc, float(fps), (screen_width, screen_height)
        )
        if not video_recording_state["video_writer"].isOpened():
            raise IOError("Could not open video writer.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize video writer: {e}")
        return {"status": "error", "message": f"Failed to initialize video writer: {e}"}

    video_recording_state["is_recording"] = True
    video_recording_state["recording_thread"] = threading.Thread(target=_record_screen_loop_internal)
    video_recording_state["recording_thread"].start()
    logger.info(f"Screen recording started: {filepath}")
    return {"status": "screen_recording_started", "filepath": str(filepath.relative_to(shared_dir))}


def stop_screen_recording() -> Dict[str, str]:
    """Stops the screen recording thread and releases resources."""
    if not video_recording_state["is_recording"]:
        logger.warning("No screen recording is active.")
        return {"status": "not_recording"}

    video_recording_state["is_recording"] = False
    if video_recording_state["recording_thread"]:
        video_recording_state["recording_thread"].join()  # Wait for thread to finish
        logger.info("Screen recording thread joined.")

    output_path = video_recording_state["output_filepath"]
    video_recording_state["output_filepath"] = None
    video_recording_state["video_writer"] = None
    video_recording_state["recording_thread"] = None

    logger.info(f"Screen recording stopped. File: {output_path}")
    return {
        "status": "screen_recording_stopped",
        "filepath": str(output_path.relative_to(shared_dir)) if output_path else None,
    }

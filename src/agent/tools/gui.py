import os

import torch
from gui_actor.inference import inference
from gui_actor.modeling import Qwen2VLForConditionalGenerationWithPointer
from PIL import Image, ImageDraw
from transformers import AutoProcessor

# --- GLOBAL MODEL AND PROCESSOR VARIABLES ---
# These will be loaded once when the script or module is first imported/run
# and then reused for all subsequent calls.
model = None
tokenizer = None
data_processor = None
model_name_or_path = "microsoft/GUI-Actor-7B-Qwen2-VL"


def load_gui_actor_model():
    """
    Loads the GUI-Actor model, tokenizer, and data processor.
    This function should be called once at the start of your application.
    """
    global model, tokenizer, data_processor

    if model is not None and tokenizer is not None and data_processor is not None:
        print("Model, tokenizer, and data processor already loaded. Skipping re-load.")
        return

    # --- Verbose GPU Check ---
    print("\n--- GPU Availability Check ---")
    if torch.cuda.is_available():
        print(f"CUDA is available: {torch.cuda.is_available()}")
        print(f"Number of GPUs available: {torch.cuda.device_count()}")
        print(f"Current CUDA device index: {torch.cuda.current_device()}")
        print(f"Current CUDA device name: {torch.cuda.get_device_name(torch.cuda.current_device())}")
    else:
        print("CUDA is NOT available. Model will run on CPU if device_map is not explicitly set to 'cpu'.")
    print("----------------------------")

    print(f"Loading model from: {model_name_or_path}...")
    data_processor = AutoProcessor.from_pretrained(model_name_or_path, use_fast=True)
    tokenizer = data_processor.tokenizer
    model = Qwen2VLForConditionalGenerationWithPointer.from_pretrained(
        model_name_or_path, torch_dtype=torch.bfloat16, device_map="cuda:0", attn_implementation="flash_attention_2"
    ).eval()  # Set to eval mode for inference

    # --- Verify Model Device ---
    print(f"Model loaded onto device: {next(model.parameters()).device}")
    print("----------------------------\n")


def run_gui_actor_inference(image_path: str, instruction: str, bbox: list = None):
    """
    Performs inference using the pre-loaded GUI-Actor model and provides detailed output.

    Args:
        image_path (str): Path to the input image.
        instruction (str): The instruction for the GUI agent.
        bbox (list, optional): Ground-truth bounding box [x1, y1, x2, y2]. Defaults to [0.0, 0.0, 0.0, 0.0].
    Returns:
        dict: A dictionary containing detailed prediction results (output_text, topk_points, etc.).
              Returns None if an error occurs (e.g., image not found).
    """
    if model is None or tokenizer is None or data_processor is None:
        print("Model not loaded. Please call load_gui_actor_model() first.")
        return None

    # Prepare the image
    try:
        input_image = Image.open(image_path).convert("RGB")
    except FileNotFoundError:
        print(f"Error: Image file not found at {image_path}. Please check the path.")
        return None

    # Create example dictionary for conversation
    if bbox is None:
        bbox = [0.0, 0.0, 0.0, 0.0]  # Default placeholder if not provided

    example = {
        "file_name": os.path.basename(image_path),
        "bbox": bbox,
        "instruction": instruction,
        "data_type": "custom",
        "data_source": "local",
        "image": input_image,
    }

    print(f"Instruction: {example['instruction']}")
    print(f"Ground-truth action region (x1, y1, x2, y2): {[round(i, 2) for i in example['bbox']]}")

    conversation = [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": "You are a GUI agent. You are given a task and a screenshot of the screen. You need to perform a series of pyautogui actions to complete the task.",
                }
            ],
        },
        {
            "role": "user",
            "content": [{"type": "image", "image": example["image"]}, {"type": "text", "text": example["instruction"]}],
        },
    ]

    # Perform inference
    pred = inference(conversation, model, tokenizer, data_processor, use_placeholder=True, topk=3)

    # --- Extract and print detailed prediction results ---
    print("\n--- Prediction Details ---")
    if pred and pred.get("output_text") is not None:
        print(f"Generated Text Output: {pred['output_text']}")
    else:
        print("Generated Text Output: Not available or None")

    if pred and pred.get("topk_points") is not None:
        px, py = pred["topk_points"][0]
        print(f"Predicted Click Point (Normalized): [{round(px, 4)}, {round(py, 4)}]")
        if len(pred["topk_points"]) > 1:
            print(f"Top-K Points: {[[round(p[0], 4), round(p[1], 4)] for p in pred['topk_points']]}")
        if pred.get("topk_values") is not None:
            print(f"Top-K Values (Scores): {[round(v, 4) for v in pred['topk_values']]}")
    else:
        px, py = None, None
        print("No topk_points found in prediction.")

    if pred and pred.get("n_width") is not None and pred.get("n_height") is not None:
        print(f"Patch Tokens Dimensions: Width={pred['n_width']}, Height={pred['n_height']}")
    print("--------------------------\n")

    # Drawing and checking logic (only proceeds if a predicted point exists)
    if px is not None and py is not None:
        image_for_drawing = example["image"].copy()
        width, height = image_for_drawing.size

        x1, y1, x2, y2 = bbox
        x1_pixel, y1_pixel = int(x1 * width), int(y1 * height)
        x2_pixel, y2_pixel = int(x2 * width), int(y2 * height)
        px_pixel, py_pixel = int(px * width), int(py * height)

        draw = ImageDraw.Draw(image_for_drawing)
        draw.rectangle([x1_pixel, y1_pixel, x2_pixel, y2_pixel], outline="red", width=3)
        cross_size = 10
        draw.line([(px_pixel - cross_size, py_pixel), (px_pixel + cross_size, py_pixel)], fill="green", width=3)
        draw.line([(px_pixel, py_pixel - cross_size), (px_pixel, py_pixel + cross_size)], fill="green", width=3)

        is_within_bbox = (x1 <= px <= x2) and (y1 <= py <= y2)
        print(f"Is predicted point within ground-truth bounding box? {is_within_bbox}")

        # Save the image
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images", "prediction")
        output_filename = (
            f"prediction_{os.path.splitext(os.path.basename(image_path))[0]}.png"  # Dynamic filename based on input
        )
        output_filepath = os.path.join(output_dir, output_filename)

        os.makedirs(output_dir, exist_ok=True)
        image_for_drawing.save(output_filepath)
        print(f"Image with bounding box and predicted point saved to {output_filepath}")
    else:
        print("Skipping image drawing and bbox check as no predicted point was found.")

    return pred  # Return the full prediction dictionary


# --- Example Usage ---
if __name__ == "__main__":
    # 1. Load the model once when the script starts (or on application boot)
    load_gui_actor_model()

    # Define common paths for clarity
    base_dir = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(base_dir, "images")

    # 2. Now you can call run_gui_actor_inference multiple times with different images/instructions
    print("\n--- First Inference Call ---")
    image1_path = os.path.join(images_dir, "ubuntu-desktop.png")
    instruction1 = "Open chromium browser"
    # Example: if you knew the start button's bbox in start-image.png
    # bbox1 = [0.1, 0.2, 0.3, 0.4] # Example bbox for testing
    prediction_result1 = run_gui_actor_inference(image1_path, instruction1)  # Pass bbox if available

    # Simulate another "on-demand" call later without reloading the model
    print("\n--- Second Inference Call (demonstrating reuse) ---")
    image2_path = os.path.join(images_dir, "jupyter-lab.png")  # Imagine you have another image
    instruction2 = "Close jupyter-lab"
    prediction_result2 = run_gui_actor_inference(image2_path, instruction2)  # Pass bbox if available

    # You can now access results from prediction_result1, prediction_result2
    # For example:
    if prediction_result1 and prediction_result1.get("output_text"):
        print(f"\nResult of first call: {prediction_result1['output_text']}")

    if prediction_result2 and prediction_result2.get("topk_points"):
        print(f"Predicted point for second call: {prediction_result2['topk_points'][0]}")

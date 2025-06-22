import torch
from datasets import load_dataset
from transformers import AutoProcessor

from models.gui_actor.inference import inference
from models.gui_actor.modeling import Qwen2VLForConditionalGenerationWithPointer

# It's good practice to define GPU before using it in GPU_NAME
GPU = torch.cuda.is_available()
GPU_NAME = torch.cuda.get_device_name(0) if GPU else "CPU"
GPU_INITIALIZED = torch.cuda.is_initialized()
GPU_COUNT = torch.cuda.device_count()

print(f"""
--- Device Information ---
Using GPU: {GPU}
GPU Name: {GPU_NAME}
GPU Initialized: {GPU_INITIALIZED}
GPU Count: {GPU_COUNT}
--------------------------
""")


# load model
model_name_or_path = "microsoft/GUI-Actor-7B-Qwen2-VL"
data_processor = AutoProcessor.from_pretrained(model_name_or_path)
tokenizer = data_processor.tokenizer
model = Qwen2VLForConditionalGenerationWithPointer.from_pretrained(
    model_name_or_path, torch_dtype=torch.bfloat16, device_map="cuda:0", attn_implementation="flash_attention_2"
).eval()

# prepare example
dataset = load_dataset("rootsautomation/ScreenSpot")["test"]
example = dataset[0]
print(f"Intruction: {example['instruction']}")
print(f"ground-truth action region (x1, y1, x2, y2): {[round(i, 2) for i in example['bbox']]}")

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
        "content": [
            {
                "type": "image",
                "image": example["image"],  # PIL.Image.Image or str to path
                # "image_url": "https://xxxxx.png" or "https://xxxxx.jpg" or "file://xxxxx.png" or "data:image/png;base64,xxxxxxxx", will be split by "base64,"
            },
            {"type": "text", "text": example["instruction"]},
        ],
    },
]

# inference
pred = inference(conversation, model, tokenizer, data_processor, use_placeholder=True, topk=3)
px, py = pred["topk_points"][0]
print(f"Predicted click point: [{round(px, 4)}, {round(py, 4)}]")

# start_image = Image.open("tests/images/start-image.png")

# # Microsoft GUI-Actor:
# # Based on the following: https://github.com/microsoft/GUI-Actor
# microsoft_gui_actor_model = LLM(model="microsoft/GUI-Actor-7B-Qwen2.5-VL")
# prompt = "Where do I need to click to open the chromium browser?"


# conversation = [
#     {
#         "role": "system",
#         "content": [
#             {
#                 "type": "text",
#                 "text": "You are a GUI agent. You are given a task and a screenshot of the screen. You need to perform a series of pyautogui actions to complete the task.",
#             }
#         ],
#     },
#     {
#         "role": "user",
#         "content": [
#             {
#                 "type": "image",
#                 "image": example["image"],  # PIL.Image.Image or str to path
#                 # "image_url": "https://xxxxx.png" or "https://xxxxx.jpg" or "file://xxxxx.png" or "data:image/png;base64,xxxxxxxx", will be split by "base64,"
#             },
#             {"type": "text", "text": example["instruction"]},
#         ],
#     },
# ]


# # # GUI R1
# # # Based on the following: https://github.com/ritzz-ai/GUI-R1"
# # gui_r1_model = LLM(model="ritzzai/GUI-R1")
# # gui_r1_model.generate()

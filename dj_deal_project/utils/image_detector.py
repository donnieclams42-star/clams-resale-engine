from ultralytics import YOLO
from PIL import Image
import requests
from io import BytesIO

model = YOLO("yolov8n.pt")

TARGET_OBJECTS = [
    "cell phone",
    "laptop",
    "tv",
    "keyboard",
    "mouse",
    "remote",
    "sports ball"
]


def detect_items(image_url):

    try:

        response = requests.get(image_url, timeout=10)

        img = Image.open(BytesIO(response.content))

        results = model(img)

        detected = []

        for r in results:

            for box in r.boxes:

                cls_id = int(box.cls)

                label = model.names[cls_id]

                detected.append(label)

        for obj in TARGET_OBJECTS:

            if obj in detected:
                return True

        return False

    except:

        return False
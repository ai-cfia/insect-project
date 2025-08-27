import io
import os
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path

import torchvision.transforms as transforms
from PIL import Image
from pydantic import HttpUrl, validate_call
from torch import Tensor

from src.settings import Settings


@contextmanager
@validate_call
def download(url: HttpUrl):
    filename = Path(f"{uuid.uuid4().hex}.jpg")
    try:
        # Some hosts (e.g., Wikimedia) may return 403 without a User-Agent
        request = urllib.request.Request(
            str(url),
            headers={"User-Agent": "Mozilla/5.0 (compatible; InsectProject/1.0)"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            image_data = io.BytesIO(response.read())
        image = Image.open(image_data)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        image.save(filename)
        yield filename
    finally:
        if filename.exists():
            os.remove(filename)


@validate_call
def preprocess_image(s: Settings, image_bytes: bytes):
    transform = transforms.Compose(
        [
            transforms.Resize(s.image_resize),
            transforms.CenterCrop(s.image_crop_size),
            transforms.ToTensor(),
            transforms.Normalize(
                s.image_normalize_mean_rgb,
                s.image_normalize_std_rgb,
            ),
        ]
    )
    image = Image.open(io.BytesIO(image_bytes))
    tensor: Tensor = transform(image)
    return tensor.unsqueeze(0)


if __name__ == "__main__":
    # Run with "python -m src.images"
    from dotenv import load_dotenv

    load_dotenv()
    s = Settings()

    test_url = (
        "https://upload.wikimedia.org/wikipedia/commons/3/3f/JPEG_example_flower.jpg"
    )
    # Test downloading and preprocessing
    with download(test_url) as test_filename:
        assert test_filename.exists(), "Downloaded image file does not exist."
        with open(test_filename, "rb") as f:
            image_bytes = f.read()
        tensor = preprocess_image(s, image_bytes)
        assert isinstance(tensor, Tensor) and tensor.shape == (1, 3, 224, 224)
    print("All tests passed.")

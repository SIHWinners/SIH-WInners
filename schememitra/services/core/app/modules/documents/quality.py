"""Upload hardening and photo quality (spec §9.2, §11).

Every upload is decoded, size-capped, orientation-fixed and re-encoded, which strips EXIF
(including GPS) and any payload smuggled after the image data. Quality metrics drive instant
"retake" hints: blur (variance of the Laplacian), glare (share of blown-out pixels) and darkness."""

import io
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_EDGE = 1600
BLUR_MIN_VARIANCE = 60.0
GLARE_MAX_RATIO = 0.06
DARK_MAX_MEAN = 55.0
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # Pillow raises on decompression bombs above this


class UploadRejected(ValueError):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


@dataclass
class ImageCheck:
    sanitized: bytes
    width: int
    height: int
    blur_variance: float
    glare_ratio: float
    brightness: float
    issues: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return not self.issues


def sanitize_and_inspect(data: bytes) -> ImageCheck:
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("errors.upload_too_large")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise UploadRejected("errors.unsupported_file")
            probe.verify()
        img: Image.Image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as err:
        raise UploadRejected("errors.unsupported_file") from err

    img.thumbnail((MAX_EDGE, MAX_EDGE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=82, optimize=True)  # no exif= → metadata dropped

    gray = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
    scale = 1000 / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    glare = float((gray >= 250).mean())
    brightness = float(gray.mean())

    issues = []
    if blur < BLUR_MIN_VARIANCE:
        issues.append("docs.blurry")
    if glare > GLARE_MAX_RATIO:
        issues.append("docs.glare")
    if brightness < DARK_MAX_MEAN:
        issues.append("docs.too_dark")
    return ImageCheck(out.getvalue(), img.width, img.height, round(blur, 1), round(glare, 4), round(brightness, 1), issues)

import base64
from dataclasses import dataclass
from io import BytesIO
from math import ceil, floor
from typing import Annotated, Literal

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_PAGE_PIXELS = 40_000_000
MAX_CROP_ROUNDS = 2
MAX_CROPS = 4


@dataclass(frozen=True)
class ImagePage:
    content: bytes
    media_type: str
    width: int
    height: int

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(
            s=self.content,
        ).decode(
            encoding="ascii",
        )
        return f"data:{self.media_type};base64,{encoded}"


class CropRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    page: int = Field(
        ge=1,
        le=10,
        strict=True,
    )
    bbox: list[
        Annotated[
            int,
            Field(
                ge=0,
                le=1000,
                strict=True,
            ),
        ]
    ] = Field(
        min_length=4,
        max_length=4,
    )
    rotation: Literal[0, 90, 180, 270]

    @model_validator(
        mode="after",
    )
    def ordered_box(self) -> CropRequest:
        if self.bbox[0] >= self.bbox[2] or self.bbox[1] >= self.bbox[3]:
            raise ValueError(
                "bbox must have left < right and top < bottom",
            )
        return self


@dataclass(frozen=True)
class CroppedImage:
    content: bytes
    pixel_bbox: tuple[int, int, int, int]
    width: int
    height: int

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(
            s=self.content,
        ).decode(
            encoding="ascii",
        )
        return f"data:image/png;base64,{encoded}"


def prepare_page(content: bytes, media_type: str) -> ImagePage:
    """use the same upright coordinate space for the overview and its crops"""
    try:
        with Image.open(
            fp=BytesIO(
                initial_bytes=content,
            ),
        ) as source:
            if source.width * source.height > MAX_PAGE_PIXELS:
                raise ValueError(
                    "изображение больше 40 мегапикселей",
                )
            orientation = source.getexif().get(
                274,
                1,
            )
            upright = ImageOps.exif_transpose(
                image=source,
            )
            upright.load()
            if orientation not in (None, 1):
                buffer = BytesIO()
                upright.save(
                    fp=buffer,
                    format="PNG",
                )
                content = buffer.getvalue()
                media_type = "image/png"
            return ImagePage(
                content=content,
                media_type=media_type,
                width=upright.width,
                height=upright.height,
            )
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError(
            "не удалось прочитать изображение",
        ) from error


def crop_image(page: ImagePage, request: CropRequest) -> CroppedImage:
    """crop original pixels with context padding and optional clockwise rotation"""
    left, top, right, bottom = request.bbox
    pad_x = (right - left) * 0.08
    pad_y = (bottom - top) * 0.08
    pixel_bbox = (
        max(
            0,
            floor(
                (left - pad_x) * page.width / 1000,
            ),
        ),
        max(
            0,
            floor(
                (top - pad_y) * page.height / 1000,
            ),
        ),
        min(
            page.width,
            ceil(
                (right + pad_x) * page.width / 1000,
            ),
        ),
        min(
            page.height,
            ceil(
                (bottom + pad_y) * page.height / 1000,
            ),
        ),
    )
    with Image.open(
        fp=BytesIO(
            initial_bytes=page.content,
        ),
    ) as source:
        cropped = source.crop(
            box=pixel_bbox,
        )
        if request.rotation:
            cropped = cropped.rotate(
                angle=-request.rotation,
                expand=True,
            )
        # small regions are displayed larger without inventing new image details
        scale = min(
            2,
            2048
            / max(
                cropped.size,
            ),
        )
        if scale > 1:
            cropped = cropped.resize(
                size=(
                    round(
                        cropped.width * scale,
                    ),
                    round(
                        cropped.height * scale,
                    ),
                ),
                resample=Image.Resampling.LANCZOS,
            )
        buffer = BytesIO()
        cropped.save(
            fp=buffer,
            format="PNG",
        )
        return CroppedImage(
            content=buffer.getvalue(),
            pixel_bbox=pixel_bbox,
            width=cropped.width,
            height=cropped.height,
        )


# what the OpenAI API accepts as an image
IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_IMAGES = 10
MAX_IMAGE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class UploadedImage:
    content: bytes
    media_type: str

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(
            s=self.content,
        ).decode(
            encoding="ascii",
        )
        return f"data:{self.media_type};base64,{encoded}"


async def read_images(files: list[UploadFile]) -> list[UploadedImage]:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Не выбрано ни одного изображения",
        )
    if len(files) > MAX_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Не больше {MAX_IMAGES} изображений за раз",
        )
    images: list[UploadedImage] = []
    for file in files:
        if file.content_type not in IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{file.filename}: поддерживаются JPEG, PNG, WebP и GIF",
            )
        # one byte more tells that the limit is exceeded without reading the whole file
        content = await file.read(
            size=MAX_IMAGE_BYTES + 1,
        )
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"{file.filename}: файл больше 20 МБ",
            )
        images.append(
            UploadedImage(
                content=content,
                media_type=file.content_type,
            ),
        )
    return images

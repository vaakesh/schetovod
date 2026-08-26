import base64
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from openai import APITimeoutError, AsyncOpenAI, AuthenticationError, OpenAIError
from pydantic import JsonValue

from config import settings

PROMPT_FILE = (
    Path(
        __file__,
    )
    .resolve()
    .parent
    / "extraction_prompt.md"
)
# what the OpenAI API accepts as an image
IMAGE_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    },
)
MAX_IMAGES = 10
MAX_IMAGE_BYTES = 20 * 1024 * 1024

NULLABLE_STRING: dict[str, Any] = {
    "type": [
        "string",
        "null",
    ],
}


def strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    """structured outputs need every key required and no extra keys"""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# the shape from extraction_prompt.md, formats are checked by InvoiceExtraction afterwards
EXTRACTION_SCHEMA = strict_object(
    properties={
        "supplier": strict_object(
            properties={
                "name": NULLABLE_STRING,
                "inn": NULLABLE_STRING,
            },
        ),
        "invoice_number": NULLABLE_STRING,
        "invoice_date": NULLABLE_STRING,
        "items": {
            "type": "array",
            "items": strict_object(
                properties={
                    "line_no": NULLABLE_STRING,
                    "name": NULLABLE_STRING,
                    "quantity": NULLABLE_STRING,
                    "unit": NULLABLE_STRING,
                    "base_price": NULLABLE_STRING,
                    "base_price_total": NULLABLE_STRING,
                    "cost_price": NULLABLE_STRING,
                    "cost_price_total": NULLABLE_STRING,
                    "vat_percent": NULLABLE_STRING,
                },
            ),
        },
        "totals": strict_object(
            properties={
                "base_total": NULLABLE_STRING,
                "cost_total": NULLABLE_STRING,
            },
        ),
    },
)


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


def recognition_failed(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Не удалось распознать накладную: {detail}",
    )


@cache
def prompt() -> str:
    return PROMPT_FILE.read_text(
        encoding="utf-8",
    )


# created on the first upload, so the app starts without a token
@cache
def client() -> AsyncOpenAI:
    try:
        api_key = settings.openai_token_file.read_text(
            encoding="utf-8",
        ).strip()
    except OSError as error:
        raise recognition_failed(
            detail=f"нет файла с токеном OpenAI ({settings.openai_token_file})",
        ) from error
    # no retries, otherwise a timeout repeats and outlives the proxy
    return AsyncOpenAI(
        api_key=api_key,
        timeout=settings.openai_timeout,
        max_retries=0,
    )


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


async def extract_invoice(images: list[UploadedImage]) -> dict[str, JsonValue]:
    """all photos are pages of one invoice and go in one request"""
    try:
        response = await client().responses.create(
            model=settings.openai_model,
            reasoning={
                "effort": settings.openai_reasoning_effort,
            },
            instructions=prompt(),
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": image.data_url,
                            "detail": "high",
                        }
                        for image in images
                    ],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "invoice_extraction",
                    "schema": EXTRACTION_SCHEMA,
                    "strict": True,
                },
            },
            store=False,
        )
    except APITimeoutError as error:
        raise recognition_failed(
            detail="OpenAI не ответил вовремя",
        ) from error
    except AuthenticationError as error:
        raise recognition_failed(
            detail="OpenAI не принял токен",
        ) from error
    except OpenAIError as error:
        raise recognition_failed(
            detail=str(
                error,
            ),
        ) from error

    if response.status != "completed":
        details = response.incomplete_details
        reason = details.reason if details else None
        raise recognition_failed(
            detail=f"ответ OpenAI не завершён ({reason or response.status})",
        )
    for output in response.output:
        if output.type == "message":
            for content in output.content:
                if content.type == "refusal":
                    raise recognition_failed(
                        detail=f"модель отказалась: {content.refusal}",
                    )
    try:
        extracted = json.loads(
            s=response.output_text,
        )
    except ValueError as error:
        raise recognition_failed(
            detail="модель вернула не JSON",
        ) from error
    if not isinstance(
        extracted,
        dict,
    ):
        raise recognition_failed(
            detail="модель вернула не объект",
        )
    return extracted

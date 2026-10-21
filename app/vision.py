import base64
import json
import logging
from asyncio import timeout
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from openai import APITimeoutError, AsyncOpenAI, AuthenticationError, OpenAIError
from openai.types.responses import Response, ResponseInputItemParam, ToolParam
from pydantic import JsonValue, ValidationError

from config import REPO_ROOT, settings
from image_tools import (
    MAX_CROP_ROUNDS,
    MAX_CROPS,
    CropRequest,
    ImagePage,
    crop_image,
    prepare_page,
)

logger = logging.getLogger(
    name="uvicorn.error",
)

INVOICES_DIR = REPO_ROOT / "invoices"
PROMPT_FILE = (
    Path(
        __file__,
    )
    .resolve()
    .parent
    / "extraction_prompt.md"
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

CROP_INSTRUCTIONS = """
You may inspect original image regions with crop_image before returning the JSON
Use it when text is small, rotated, blurred, or characters or table columns are
ambiguous. Prefer inspecting a region over guessing a plausible name or number
Use page numbers starting at 1 in upload order. bbox is [left, top, right, bottom]
in the coordinate space 0..1000 of the full uploaded page, with the origin at its
top-left corner. rotation is clockwise, applied after cropping; use 0 normally
Include enough neighboring text, row boundaries or column headers to identify
the field. Request several useful crops together when possible. You can request
at most 4 crops across at most 2 rounds. Finish with the required invoice JSON
If the crop still cannot be read, use null. Crops show the same invoice, so do
not duplicate rows. Copy printed abbreviations literally, even if you know the
full word. Do not infer missing numbers from arithmetic or other documents
"""

CROP_TOOL: ToolParam = {
    "type": "function",
    "name": "crop_image",
    "description": (
        "Inspect a region of an uploaded invoice at higher visual scale. "
        "Uses original pixels, adds 8% context padding, and optionally rotates "
        "clockwise. Coordinates always refer to the full upright page, not "
        "to a previous crop"
    ),
    "parameters": CropRequest.model_json_schema(),
    "strict": True,
}

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


def save_images(images: list[UploadedImage]) -> Path:
    try:
        INVOICES_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )
        last_number = 0
        for entry in INVOICES_DIR.iterdir():
            if not entry.name.startswith(
                "invoice_",
            ):
                continue
            suffix = entry.name.removeprefix(
                "invoice_",
            )
            if suffix.isdecimal() and entry.is_dir():
                last_number = max(
                    last_number,
                    int(
                        suffix,
                    ),
                )
        directory = INVOICES_DIR / f"invoice_{last_number + 1}"
        try:
            directory.mkdir(
                exist_ok=False,
            )
        except FileExistsError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Не удалось создать новую папку для накладной",
            ) from error
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать новую папку для накладной",
        ) from error

    try:
        for number, image in enumerate(
            iterable=images,
            start=1,
        ):
            image_path = directory / f"image_{number}{IMAGE_TYPES[image.media_type]}"
            image_path.write_bytes(
                data=image.content,
            )
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось сохранить изображения накладной",
        ) from error
    return directory


def save_json(path: Path, value: Any) -> None:
    path.write_text(
        data=json.dumps(
            obj=value,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def overview_input(
    images: list[UploadedImage], enabled: bool
) -> tuple[list[ResponseInputItemParam], list[ImagePage]]:
    pages: list[ImagePage] = []
    items: list[ResponseInputItemParam] = []
    for number, image in enumerate(
        iterable=images,
        start=1,
    ):
        if enabled:
            page = prepare_page(
                content=image.content,
                media_type=image.media_type,
            )
            pages.append(
                page,
            )
            items.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                f"Page {number}: {page.width} x {page.height} pixels; "
                                "crop coordinates use 0..1000 on this full page"
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": page.data_url,
                            "detail": "high",
                        },
                    ],
                },
            )
        else:
            items.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": image.data_url,
                            "detail": "high",
                        },
                    ],
                },
            )
    return items, pages


async def inspect_images(images: list[UploadedImage], directory: Path) -> Response:
    enabled = settings.openai_image_crops
    try:
        history, pages = await run_in_threadpool(
            func=overview_input,
            images=images,
            enabled=enabled,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(
                error,
            ),
        ) from error
    instructions = prompt() + ("\n\n" + CROP_INSTRUCTIONS if enabled else "")
    trace: dict[str, Any] = {
        "model": settings.openai_model,
        "reasoning_effort": settings.openai_reasoning_effort,
        "image_crops_enabled": enabled,
        "instructions": instructions,
        "max_crop_rounds": MAX_CROP_ROUNDS,
        "max_crops": MAX_CROPS,
        "rounds": [],
        "crops": [],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "usage_complete": True,
    }
    crop_count = 0
    for round_no in range(
        1,
        MAX_CROP_ROUNDS + 2,
    ):
        allow_crops = enabled and round_no <= MAX_CROP_ROUNDS and crop_count < MAX_CROPS
        response = await client().responses.create(
            model=settings.openai_model,
            reasoning={
                "effort": settings.openai_reasoning_effort,
            },
            instructions=instructions,
            input=history,
            tools=[CROP_TOOL] if enabled else [],
            tool_choice="auto" if allow_crops else "none",
            include=["reasoning.encrypted_content"],
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
        # replay every output item, including encrypted reasoning, without alteration
        history.extend(
            item.model_dump(
                mode="json",
                exclude_none=True,
            )
            for item in response.output
        )
        usage = response.usage
        trace["rounds"].append(
            {
                "round": round_no,
                "response_id": response.id,
                "status": response.status,
                "usage": usage.model_dump(
                    mode="json",
                )
                if usage is not None
                else None,
            },
        )
        if usage is not None:
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                trace["usage"][key] += getattr(
                    usage,
                    key,
                )
            logger.info(
                msg=(
                    f"OpenAI token usage: input={usage.input_tokens}, "
                    f"output={usage.output_tokens}, total={usage.total_tokens} "
                    f"invoice={directory.name}, round={round_no}"
                ),
            )
        else:
            trace["usage_complete"] = False
        await run_in_threadpool(
            func=save_json,
            path=directory / f"response_round_{round_no}.json",
            value={
                "id": response.id,
                "status": response.status,
                "output": [
                    item.model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                    for item in response.output
                    if item.type != "reasoning"
                ],
            },
        )
        calls = [item for item in response.output if item.type == "function_call"]
        await run_in_threadpool(
            func=save_json,
            path=directory / "trace.json",
            value=trace,
        )
        if not calls or response.status != "completed":
            logger.info(
                msg=f"OpenAI invoice total: invoice={directory.name}, usage={trace['usage']}",
            )
            return response
        if not allow_crops:
            raise recognition_failed(
                detail="модель запросила приближение после исчерпания лимита",
            )
        for call in calls:
            crop_count += 1
            entry: dict[str, Any] = {
                "call_id": call.call_id,
                "round": round_no,
                "name": call.name,
                "arguments": call.arguments,
            }
            try:
                if call.name != "crop_image" or crop_count > MAX_CROPS:
                    raise ValueError(
                        "crop limit reached or unknown tool; finish with available evidence",
                    )
                request = CropRequest.model_validate_json(
                    json_data=call.arguments,
                )
                if request.page > len(
                    pages,
                ):
                    raise ValueError(
                        "page is outside the uploaded invoice",
                    )
                cropped = await run_in_threadpool(
                    func=crop_image,
                    page=pages[request.page - 1],
                    request=request,
                )
                filename = f"crop_{crop_count}.png"
                await run_in_threadpool(
                    func=(directory / filename).write_bytes,
                    data=cropped.content,
                )
                entry.update(
                    {
                        "request": request.model_dump(),
                        "file": filename,
                        "pixel_bbox": cropped.pixel_bbox,
                        "width": cropped.width,
                        "height": cropped.height,
                    },
                )
                history.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"Crop of page {request.page}, bbox={request.bbox}, "
                                    f"clockwise rotation={request.rotation}. "
                                    "Read the original print literally"
                                ),
                            },
                            {
                                "type": "input_image",
                                "image_url": cropped.data_url,
                                "detail": "high",
                            },
                        ],
                    },
                )
            except (ValueError, ValidationError) as error:
                entry["error"] = str(
                    error,
                )
                history.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": entry["error"],
                    },
                )
            trace["crops"].append(
                entry,
            )
            await run_in_threadpool(
                func=save_json,
                path=directory / "trace.json",
                value=trace,
            )
    raise recognition_failed(
        detail="не получен итоговый ответ модели",
    )


async def extract_invoice(images: list[UploadedImage]) -> dict[str, JsonValue]:
    """inspect all pages with optional crop calls, then return one invoice"""
    directory = await run_in_threadpool(
        func=save_images,
        images=images,
    )
    try:
        async with timeout(
            delay=settings.openai_timeout,
        ):
            response = await inspect_images(
                images=images,
                directory=directory,
            )
    except (APITimeoutError, TimeoutError) as error:
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

    try:
        output_text = (
            json.dumps(
                obj=json.loads(
                    s=response.output_text,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    except ValueError:
        # keep incomplete or invalid output available for diagnosis
        output_text = response.output_text

    try:
        await run_in_threadpool(
            func=(directory / "output.json").write_text,
            data=output_text,
            encoding="utf-8",
            newline="",
        )
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось сохранить ответ OpenAI",
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

import json
import logging
from asyncio import timeout
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from openai import APITimeoutError, AuthenticationError, OpenAIError
from openai.types.responses import Response, ResponseInputItemParam
from pydantic import JsonValue, ValidationError

from core.config import settings
from recognition.client import client, prompt, recognition_failed
from recognition.images import (
    MAX_CROP_ROUNDS,
    MAX_CROPS,
    CropRequest,
    ImagePage,
    UploadedImage,
    crop_image,
    prepare_page,
)
from recognition.storage import save_images, save_json
from recognition.tool_schemas import CROP_INSTRUCTIONS, CROP_TOOL, EXTRACTION_SCHEMA

logger = logging.getLogger(
    name="uvicorn.error",
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

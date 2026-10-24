import json
from copy import deepcopy
from io import BytesIO
from typing import Any
from unittest.mock import Mock

import pytest
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
    ResponseUsage,
)
from PIL import Image

from recognition import service as vision

FINAL_JSON = '{"supplier":{"name":null,"inn":null},"invoice_number":null,"invoice_date":null,"items":[],"totals":{"base_total":null,"cost_total":null}}'


def image_bytes(orientation: int = 1) -> bytes:
    image = Image.new(
        mode="RGB",
        size=(200, 100),
        color="red",
    )
    exif = Image.Exif()
    exif[274] = orientation
    buffer = BytesIO()
    image.save(
        fp=buffer,
        format="PNG",
        exif=exif,
    )
    return buffer.getvalue()


def crop_call(call_id: str, page: int = 1) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        type="function_call",
        name="crop_image",
        call_id=call_id,
        arguments=json.dumps(
            obj={"page": page, "bbox": [250, 250, 750, 750], "rotation": 0},
        ),
    )


def model_response(
    calls: list[ResponseFunctionToolCall] | None = None,
) -> Response:
    output: list[Any] = [
        ResponseReasoningItem(
            id="rs_test",
            type="reasoning",
            summary=[],
            encrypted_content="opaque-reasoning-state",
        ),
    ]
    output.extend(
        calls
        if calls is not None
        else [
            ResponseOutputMessage(
                id="msg_test",
                type="message",
                role="assistant",
                status="completed",
                content=[
                    ResponseOutputText(
                        type="output_text",
                        text=FINAL_JSON,
                        annotations=[],
                    ),
                ],
            ),
        ],
    )
    return Response.model_construct(
        id="resp_test",
        status="completed",
        output=output,
        usage=ResponseUsage.model_validate(
            obj={
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
                "input_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 20},
            },
        ),
    )


def fake_api(
    monkeypatch: pytest.MonkeyPatch, responses: list[Response]
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    pending = iter(
        responses,
    )

    async def create(**kwargs: Any) -> Response:
        requests.append(
            deepcopy(
                kwargs,
            ),
        )
        return next(
            pending,
        )

    api = Mock()
    api.responses.create = create
    monkeypatch.setattr(
        target=vision,
        name="client",
        value=Mock(
            return_value=api,
        ),
    )
    return requests

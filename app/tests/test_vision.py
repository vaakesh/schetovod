import base64
import json
from asyncio import Event
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
    ResponseUsage,
)
from PIL import Image
from pydantic import ValidationError

import vision
from config import settings
from image_tools import CropRequest, crop_image, prepare_page
from vision import UploadedImage, extract_invoice, inspect_images

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


@pytest.fixture
def archived(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    saved: dict[str, Any] = {}

    def capture(path: Path, value: Any) -> None:
        saved[path.name] = deepcopy(
            value,
        )

    monkeypatch.setattr(
        target=vision,
        name="save_json",
        value=capture,
    )
    monkeypatch.setattr(
        target=Path,
        name="write_bytes",
        value=Mock(),
    )
    monkeypatch.setattr(
        target=settings,
        name="openai_image_crops",
        value=True,
    )
    monkeypatch.setattr(
        target=vision,
        name="prompt",
        value=Mock(
            return_value="copy the invoice literally",
        ),
    )
    return saved


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


class TestCropImage:
    def test_crops_original_region_with_padding_and_clockwise_rotation(self) -> None:
        page = prepare_page(
            content=image_bytes(),
            media_type="image/png",
        )

        result = crop_image(
            page=page,
            request=CropRequest(
                page=1,
                bbox=[250, 250, 750, 750],
                rotation=90,
            ),
        )

        assert result.pixel_bbox == (42, 21, 158, 79)
        assert (result.width, result.height) == (116, 232)
        with Image.open(
            fp=BytesIO(
                initial_bytes=result.content,
            ),
        ) as image:
            assert image.format == "PNG"
            assert image.getpixel(
                xy=(0, 0),
            ) == (255, 0, 0)

    def test_clips_padding_at_the_image_edges(self) -> None:
        page = prepare_page(
            content=image_bytes(),
            media_type="image/png",
        )

        result = crop_image(
            page=page,
            request=CropRequest(
                page=1,
                bbox=[0, 0, 1000, 1000],
                rotation=0,
            ),
        )

        assert result.pixel_bbox == (0, 0, 200, 100)


class TestPreparePage:
    def test_applies_exif_orientation_before_overview_and_crops(self) -> None:
        result = prepare_page(
            content=image_bytes(
                orientation=6,
            ),
            media_type="image/png",
        )

        assert (result.width, result.height) == (100, 200)
        with Image.open(
            fp=BytesIO(
                initial_bytes=result.content,
            ),
        ) as image:
            assert image.size == (100, 200)
            assert (
                image.getexif().get(
                    274,
                )
                is None
            )

    def test_rejects_invalid_image_bytes(self) -> None:
        with pytest.raises(
            expected_exception=ValueError,
            match="не удалось прочитать изображение",
        ):
            prepare_page(
                content=b"not an image",
                media_type="image/png",
            )


class TestCropRequest:
    @pytest.mark.parametrize(
        argnames="bbox",
        argvalues=(
            [750, 250, 250, 750],
            [250, 750, 750, 250],
            [250, 250, 250, 750],
            [-1, 0, 1000, 1000],
            [0, 0, 1001, 1000],
            [0, 0, 1000],
        ),
    )
    def test_rejects_invalid_coordinates(self, bbox: list[int]) -> None:
        with pytest.raises(
            expected_exception=ValidationError,
        ):
            CropRequest(
                page=1,
                bbox=bbox,
                rotation=0,
            )


class TestInspectImages:
    async def test_returns_without_extra_request_when_no_crop_is_needed(
        self, monkeypatch: pytest.MonkeyPatch, archived: dict[str, Any]
    ) -> None:
        requests = fake_api(
            monkeypatch=monkeypatch,
            responses=[model_response()],
        )

        response = await inspect_images(
            images=[
                UploadedImage(
                    content=image_bytes(),
                    media_type="image/png",
                ),
            ],
            directory=Path(
                "unused",
            ),
        )

        assert response.output_text == FINAL_JSON
        assert (
            len(
                requests,
            )
            == 1
        )
        assert archived["trace.json"]["crops"] == []
        assert archived["trace.json"]["usage"] == {
            "input_tokens": 120,
            "output_tokens": 30,
            "total_tokens": 150,
        }

    async def test_returns_crop_image_and_preserves_reasoning_for_continuation(
        self, monkeypatch: pytest.MonkeyPatch, archived: dict[str, Any]
    ) -> None:
        requests = fake_api(
            monkeypatch=monkeypatch,
            responses=[
                model_response(
                    calls=[
                        crop_call(
                            call_id="crop_1",
                        ),
                    ],
                ),
                model_response(),
            ],
        )

        await inspect_images(
            images=[
                UploadedImage(
                    content=image_bytes(),
                    media_type="image/png",
                ),
            ],
            directory=Path(
                "unused",
            ),
        )

        continuation = requests[1]["input"]
        assert continuation[1]["encrypted_content"] == "opaque-reasoning-state"
        assert continuation[2]["call_id"] == "crop_1"
        tool_output = continuation[3]
        assert tool_output["type"] == "function_call_output"
        assert tool_output["call_id"] == "crop_1"
        crop_url = tool_output["output"][1]["image_url"]
        with Image.open(
            fp=BytesIO(
                initial_bytes=base64.b64decode(
                    s=crop_url.split(
                        sep=",",
                        maxsplit=1,
                    )[1],
                ),
            ),
        ) as image:
            assert image.size == (232, 116)
        assert requests[1]["store"] is False
        assert archived["trace.json"]["crops"][0]["file"] == "crop_1.png"
        assert archived["trace.json"]["usage"] == {
            "input_tokens": 240,
            "output_tokens": 60,
            "total_tokens": 300,
        }

    async def test_disables_tools_after_two_crop_rounds(
        self, monkeypatch: pytest.MonkeyPatch, archived: dict[str, Any]
    ) -> None:
        requests = fake_api(
            monkeypatch=monkeypatch,
            responses=[
                model_response(
                    calls=[
                        crop_call(
                            call_id="crop_1",
                        ),
                        crop_call(
                            call_id="crop_2",
                        ),
                    ],
                ),
                model_response(
                    calls=[
                        crop_call(
                            call_id="crop_3",
                        ),
                        crop_call(
                            call_id="crop_4",
                        ),
                    ],
                ),
                model_response(),
            ],
        )

        await inspect_images(
            images=[
                UploadedImage(
                    content=image_bytes(),
                    media_type="image/png",
                ),
            ],
            directory=Path(
                "unused",
            ),
        )

        assert requests[2]["tool_choice"] == "none"
        assert (
            len(
                archived["trace.json"]["crops"],
            )
            == 4
        )
        assert archived["trace.json"]["usage"] == {
            "input_tokens": 360,
            "output_tokens": 90,
            "total_tokens": 450,
        }

    async def test_returns_missing_page_error_to_model_without_a_crop(
        self, monkeypatch: pytest.MonkeyPatch, archived: dict[str, Any]
    ) -> None:
        requests = fake_api(
            monkeypatch=monkeypatch,
            responses=[
                model_response(
                    calls=[
                        crop_call(
                            call_id="crop_1",
                            page=2,
                        ),
                    ],
                ),
                model_response(),
            ],
        )

        await inspect_images(
            images=[
                UploadedImage(
                    content=image_bytes(),
                    media_type="image/png",
                ),
            ],
            directory=Path(
                "unused",
            ),
        )

        assert (
            requests[1]["input"][3]["output"] == "page is outside the uploaded invoice"
        )
        assert "file" not in archived["trace.json"]["crops"][0]


class TestExtractInvoice:
    async def test_limits_the_whole_extraction_duration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def pending(**kwargs: Any) -> None:
            await Event().wait()

        monkeypatch.setattr(
            target=vision,
            name="save_images",
            value=Mock(
                return_value=Path(
                    "unused",
                ),
            ),
        )
        monkeypatch.setattr(
            target=vision,
            name="inspect_images",
            value=AsyncMock(
                side_effect=pending,
            ),
        )
        monkeypatch.setattr(
            target=settings,
            name="openai_timeout",
            value=0.01,
        )

        with pytest.raises(
            expected_exception=HTTPException,
        ) as error:
            await extract_invoice(
                images=[],
            )

        assert error.value.status_code == 502
        assert (
            error.value.detail
            == "Не удалось распознать накладную: OpenAI не ответил вовремя"
        )

import base64
from asyncio import Event
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from PIL import Image

from core.config import settings
from recognition import service as vision
from recognition.images import UploadedImage
from recognition.service import extract_invoice, inspect_images
from tests.recognition.helpers import (
    FINAL_JSON,
    crop_call,
    fake_api,
    image_bytes,
    model_response,
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

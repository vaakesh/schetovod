import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from core.config import settings
from recognition import storage
from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi
from tests.recognition.helpers import FINAL_JSON, fake_api, image_bytes, model_response


class TestRecognizeImage(InvoiceApi):
    @pytest.fixture(
        autouse=True,
    )
    def enable_recognition(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            target=settings,
            name="openai_api_token",
            value=SecretStr(
                secret_value="test-token",
            ),
        )

    def test_recognition_without_a_token_does_not_call_openai(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            target=settings,
            name="openai_api_token",
            value=SecretStr(
                secret_value="",
            ),
        )

        response, extract = self.post_images(
            files=[
                ("files", ("page.jpg", b"page", "image/jpeg")),
            ],
            extracted=invoice_payload(),
        )

        assert response.status_code == 503
        extract.assert_not_awaited()

    def post_images(
        self,
        files: list[tuple[str, tuple[str, bytes, str]]],
        extracted: dict[str, Any],
    ) -> tuple[Any, AsyncMock]:
        extract = AsyncMock(
            return_value=extracted,
        )
        with patch(
            target="invoices.router.extract_invoice",
            new=extract,
        ):
            response = self.client.post(
                url="/invoice/image",
                files=files,
            )
        return response, extract

    def test_recognized_invoice_becomes_a_draft(self) -> None:
        response, extract = self.post_images(
            files=[
                ("files", ("page1.jpg", b"first", "image/jpeg")),
                ("files", ("page2.png", b"second", "image/png")),
            ],
            extracted=invoice_payload(),
        )

        assert response.status_code == 200, response.text
        call = extract.await_args
        assert call is not None
        images = call.kwargs["images"]
        assert [(image.content, image.media_type) for image in images] == [
            (b"first", "image/jpeg"),
            (b"second", "image/png"),
        ]
        draft = response.json()
        assert self.store.invoices[draft["id"]].extracted == invoice_payload()

    def test_archives_recognition_separately_for_each_store(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            target=storage,
            name="INVOICES_DIR",
            value=tmp_path,
        )
        fake_api(
            monkeypatch=monkeypatch,
            responses=[model_response(), model_response()],
        )
        gastronom_image = image_bytes()
        meat_image = image_bytes(
            orientation=3,
        )

        gastronom = self.client.post(
            url="/invoice/image",
            files=[("files", ("gastronom.png", gastronom_image, "image/png"))],
        )
        meat = self.client.post(
            url="/stores/meat/invoice/image",
            files=[("files", ("meat.png", meat_image, "image/png"))],
        )

        assert gastronom.status_code == 200, gastronom.text
        assert meat.status_code == 200, meat.text
        gastronom_archive = tmp_path / "invoice_1"
        meat_archive = tmp_path / "meat" / "invoice_1"
        output = json.loads(
            s=FINAL_JSON,
        )
        for archive, image in (
            (gastronom_archive, gastronom_image),
            (meat_archive, meat_image),
        ):
            assert (archive / "image_1.png").read_bytes() == image
            assert (
                json.loads(
                    s=(archive / "output.json").read_text(
                        encoding="utf-8",
                    ),
                )
                == output
            )
            assert (archive / "trace.json").is_file()

    def test_rejects_a_file_that_is_not_an_image(self) -> None:
        response, extract = self.post_images(
            files=[
                ("files", ("invoice.pdf", b"%PDF", "application/pdf")),
            ],
            extracted=invoice_payload(),
        )

        assert response.status_code == 422
        extract.assert_not_awaited()

    def test_malformed_recognition_is_reported_by_field(self) -> None:
        payload = invoice_payload()
        payload["invoice_date"] = "12.08.2026"

        response, _ = self.post_images(
            files=[
                ("files", ("page.jpg", b"page", "image/jpeg")),
            ],
            extracted=payload,
        )

        assert response.status_code == 422
        assert [error["loc"] for error in response.json()["detail"]] == [
            ["body", "invoice_date"]
        ]
        assert self.store.invoices == {}

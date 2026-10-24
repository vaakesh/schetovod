from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from core.config import settings
from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi


class TestRecognizeImage(InvoiceApi):
    @pytest.fixture(
        autouse=True,
    )
    def enable_recognition(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            target=settings,
            name="include_api_openai",
            value=True,
        )

    def test_turned_off_recognition_does_not_call_openai(self) -> None:
        settings.include_api_openai = False

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

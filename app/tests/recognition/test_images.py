from io import BytesIO

import pytest
from PIL import Image
from pydantic import ValidationError

from recognition.images import CropRequest, crop_image, prepare_page
from tests.recognition.helpers import image_bytes


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

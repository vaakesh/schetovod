import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from core.config import REPO_ROOT
from recognition.images import IMAGE_TYPES, UploadedImage

INVOICES_DIR = REPO_ROOT / "invoices"


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

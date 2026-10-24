from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from core.config import settings
from recognition import service as vision


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

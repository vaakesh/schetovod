from functools import cache
from pathlib import Path

from fastapi import HTTPException, status
from openai import AsyncOpenAI

from core.config import settings

PROMPT_FILE = (
    Path(
        __file__,
    )
    .resolve()
    .parent
    / "prompt.md"
)


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

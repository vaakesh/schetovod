import argparse
import asyncio
import sys

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_engine
from price_tags.repository import PriceTagRepository
from price_tags.schemas import GeneralTag, PriceTagFields
from price_tags.service import general_tag_fields, unique_values

GENERAL_TAGS = TypeAdapter(
    type=list[GeneralTag],
)


def read_tags(text: str) -> list[PriceTagFields]:
    """every record of general.json, one bad record stops the import before any write"""
    try:
        # data is positional only
        records = GENERAL_TAGS.validate_json(
            text,
        )
    except ValidationError as error:
        raise SystemExit(
            f"Файл не похож на general.json:\n{error}",
        ) from error
    tags = []
    for number, record in enumerate(
        records,
        start=1,
    ):
        if record.custom:
            raise SystemExit(
                f"Запись {number}: размер вне списка (custom), такие ценники не хранятся",
            )
        try:
            tags.append(
                general_tag_fields(
                    tag=record,
                ),
            )
        except (ValidationError, ValueError) as error:
            raise SystemExit(
                f"Запись {number} «{record.name}»: {error}",
            ) from error
    return tags


async def save_tags(
    tags: list[PriceTagFields],
) -> int:
    engine = get_engine()
    async with AsyncSession(
        bind=engine,
        expire_on_commit=False,
    ) as session:
        repository = PriceTagRepository(
            session=session,
        )
        added = await repository.add_missing(
            tags=unique_values(
                tags=tags,
            ),
        )
        await repository.commit()
    await engine.dispose()
    return added


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Добавляет в базу ценники из general.json скилла cenniki-v2, "
            "файл читается из stdin, уже известные ценники пропускаются"
        ),
    )
    parser.parse_args()
    tags = read_tags(
        text=sys.stdin.read(),
    )
    added = asyncio.run(
        main=save_tags(
            tags=tags,
        ),
    )
    print(
        f"Записей в файле: {len(tags)}, добавлено: {added}, уже были: {len(tags) - added}",
    )


if __name__ == "__main__":
    main()

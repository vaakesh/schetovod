from datetime import UTC, datetime
from typing import Any

from price_tags.models import PriceTag
from price_tags.service import normalized
from tests.fakes.store import FakeStore


class FakePriceTags:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def commit(self) -> None:
        self.store.commits += 1

    async def add_missing(
        self,
        tags: list[dict[str, Any]],
    ) -> int:
        known = {tag.dedup_key for tag in self.store.price_tags}
        added = 0
        for values in tags:
            if values["dedup_key"] in known:
                continue
            known.add(
                values["dedup_key"],
            )
            self.store.price_tags.append(
                PriceTag(
                    id=self.store.new_id(),
                    # the database default, a fake tag is never inserted
                    created_at=datetime.now(
                        tz=UTC,
                    ),
                    **values,
                ),
            )
            added += 1
        return added

    async def get(
        self,
        tag_id: int,
    ) -> PriceTag | None:
        return next(
            (tag for tag in self.store.price_tags if tag.id == tag_id),
            None,
        )

    async def find_by_key(
        self,
        dedup_key: str,
    ) -> PriceTag | None:
        return next(
            (tag for tag in self.store.price_tags if tag.dedup_key == dedup_key),
            None,
        )

    async def all(self) -> list[PriceTag]:
        return sorted(
            self.store.price_tags,
            key=lambda tag: (
                tag.name,
                tag.id,
            ),
        )

    async def delete(
        self,
        tag: PriceTag,
    ) -> None:
        self.store.price_tags.remove(
            tag,
        )

    async def search(
        self,
        words: list[str],
        prefix: str,
        limit: int,
    ) -> list[PriceTag]:
        def text(tag: PriceTag) -> str:
            return normalized(
                text=f"{tag.name} {tag.subtitle or ''}",
            )

        found = [
            tag
            for tag in self.store.price_tags
            if all(
                normalized(
                    text=word,
                )
                in text(
                    tag=tag,
                )
                for word in words
            )
        ]
        found.sort(
            key=lambda tag: (
                not normalized(
                    text=tag.name,
                ).startswith(
                    normalized(
                        text=prefix,
                    ),
                ),
                tag.name,
            ),
        )
        return found[:limit]

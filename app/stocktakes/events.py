import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy import URL

CHANNEL = "stocktake_changes"


def replace_version(queue: asyncio.Queue[int | None], version: int | None) -> None:
    # a slow tab fetches the newest revision in one request
    if queue.full():
        queue.get_nowait()
    queue.put_nowait(
        item=version,
    )


class StocktakeEvents:
    def __init__(self, database_url: URL) -> None:
        self.database_url = database_url
        self.connection: asyncpg.Connection | None = None
        self.lock = asyncio.Lock()
        self.subscribers: dict[int, set[asyncio.Queue[int | None]]] = {}

    def changed(
        self, connection: asyncpg.Connection, pid: int, channel: str, payload: str
    ) -> None:
        if connection is not self.connection:
            return
        try:
            document, revision = payload.split(
                sep=":",
            )
            document_id = int(
                document,
            )
            version = int(
                revision,
            )
        except ValueError:
            return
        for queue in self.subscribers.get(
            document_id,
            (),
        ):
            replace_version(
                queue=queue,
                version=version,
            )

    def disconnected(self, connection: asyncpg.Connection) -> None:
        if connection is not self.connection:
            return
        self.connection = None
        for subscribers in self.subscribers.values():
            for queue in subscribers:
                replace_version(
                    queue=queue,
                    version=None,
                )
        self.subscribers.clear()

    async def listen(self) -> None:
        if self.connection is not None:
            if not self.connection.is_closed():
                return
            self.disconnected(
                connection=self.connection,
            )
        connection = await asyncpg.connect(
            dsn=self.database_url.set(
                drivername="postgresql",
            ).render_as_string(
                hide_password=False,
            ),
            timeout=5,
        )
        self.connection = connection
        try:
            connection.add_termination_listener(
                callback=self.disconnected,
            )
            await connection.add_listener(
                channel=CHANNEL,
                callback=self.changed,
            )
            if connection.is_closed():
                raise ConnectionError(
                    "the stocktake listener disconnected",
                )
        except BaseException:
            connection.terminate()
            self.disconnected(
                connection=connection,
            )
            raise

    @asynccontextmanager
    async def subscribe(
        self, document_id: int
    ) -> AsyncIterator[asyncio.Queue[int | None]]:
        async with self.lock:
            await self.listen()
            queue: asyncio.Queue[int | None] = asyncio.Queue(
                maxsize=1,
            )
            subscribers = self.subscribers.setdefault(
                document_id,
                set(),
            )
            subscribers.add(
                queue,
            )
        try:
            yield queue
        finally:
            subscribers.discard(
                queue,
            )
            if (
                not subscribers
                and self.subscribers.get(
                    document_id,
                )
                is subscribers
            ):
                del self.subscribers[document_id]

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close(
                timeout=5,
            )

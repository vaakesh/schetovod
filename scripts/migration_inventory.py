import asyncio
import hashlib
import json

import asyncpg

from core.config import REPO_ROOT, settings


async def main() -> None:
    connection = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_db,
    )
    try:
        tables = await connection.fetch(
            query="SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename",
        )
        counts = {}
        for row in tables:
            name = row["tablename"]
            quoted = name.replace(
                '"',
                '""',
            )
            counts[name] = await connection.fetchval(
                query=f'SELECT count(*) FROM "{quoted}"',
            )
    finally:
        await connection.close()
    directory = REPO_ROOT / "invoices"
    digest = hashlib.sha256()
    files = 0
    size = 0
    for path in sorted(
        directory.rglob(
            "*",
        ),
    ):
        if path.is_file():
            content = path.read_bytes()
            digest.update(
                path.relative_to(
                    directory,
                ).as_posix().encode(),
            )
            digest.update(
                hashlib.sha256(
                    content,
                ).digest(),
            )
            files += 1
            size += len(
                content,
            )
    print(
        json.dumps(
            {"tables": counts, "files": files, "bytes": size, "sha256": digest.hexdigest()},
            sort_keys=True,
        ),
    )


asyncio.run(
    main(),
)

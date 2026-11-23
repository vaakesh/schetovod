import asyncio
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncEngine

from auth.cookies import ACCESS_COOKIE
from auth.repository import AuthRepository
from auth.security import TokenType, decode
from core.config import now
from core.db import DATABASE_CONNECTION_ERRORS, get_gastronom_engine, open_session
from core.http import unauthorized
from stocktakes.events import StocktakeEvents
from stocktakes.queries import StocktakeQueries

router = APIRouter(
    prefix="/stocktakes",
)


async def get_stocktake_events(websocket: WebSocket) -> StocktakeEvents:
    return websocket.app.state.stocktake_events


async def check_subscription(
    engine: AsyncEngine, session_id: int, document_id: int | None = None
) -> None:
    async with open_session(
        engine=engine,
    ) as session:
        user_session = await AuthRepository(
            session=session,
        ).get_active_session(
            session_id=session_id,
            moment=now(),
        )
        if user_session is None:
            unauthorized()
        if document_id is not None:
            await StocktakeQueries(
                session=session,
            ).get(
                document_id=document_id,
                writing=False,
            )


async def send_versions(
    websocket: WebSocket,
    queue: asyncio.Queue[int | None],
    engine: AsyncEngine,
    session_id: int,
) -> None:
    while (version := await queue.get()) is not None:
        await check_subscription(
            engine=engine,
            session_id=session_id,
        )
        await websocket.send_json(
            data={"type": "changed", "version": version},
        )


@router.websocket(
    path="/{document_id}/events",
)
async def document_events(
    websocket: WebSocket,
    document_id: int,
    engine: Annotated[
        AsyncEngine,
        Depends(
            dependency=get_gastronom_engine,
        ),
    ],
    events: Annotated[
        StocktakeEvents,
        Depends(
            dependency=get_stocktake_events,
        ),
    ],
) -> None:
    host = websocket.headers["host"]
    if websocket.headers.get(
        "origin",
    ) not in {f"https://{host}", f"http://{host}"}:
        raise HTTPException(
            status_code=403,
            detail="Недопустимый источник подключения",
        )
    claims = decode(
        token=websocket.cookies.get(
            ACCESS_COOKIE,
            "",
        ),
        token_type=TokenType.ACCESS,
    )
    if claims is None:
        unauthorized()
    session_id = claims["sid"]
    await check_subscription(
        engine=engine,
        session_id=session_id,
        document_id=document_id,
    )
    await websocket.accept()
    try:
        async with events.subscribe(
            document_id=document_id,
        ) as queue:
            await websocket.send_json(
                data={"type": "ready"},
            )
            updates = asyncio.create_task(
                coro=send_versions(
                    websocket=websocket,
                    queue=queue,
                    engine=engine,
                    session_id=session_id,
                ),
            )
            peer = asyncio.create_task(
                coro=websocket.receive(),
            )
            try:
                done, _ = await asyncio.wait(
                    fs=(updates, peer),
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=claims["exp"] - now().timestamp(),
                )
                if peer in done:
                    if peer.result()["type"] == "websocket.disconnect":
                        return
                    # the browser only receives updates on this socket
                    code = 1008
                elif updates in done:
                    updates.result()
                    code = 1013
                else:
                    code = 4401
            finally:
                for task in (peer, updates):
                    task.cancel()
                await asyncio.gather(
                    peer,
                    updates,
                    return_exceptions=True,
                )
    except HTTPException as error:
        code = 4401 if error.status_code == 401 else 1013
    except (*DATABASE_CONNECTION_ERRORS, asyncpg.PostgresError, asyncpg.InterfaceError):
        code = 1013
    except WebSocketDisconnect:
        return
    await websocket.close(
        code=code,
    )

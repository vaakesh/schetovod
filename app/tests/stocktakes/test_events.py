import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import timedelta
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from starlette.testclient import WebSocketDenialResponse, WebSocketTestSession
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

from auth.cookies import ACCESS_COOKIE
from auth.models import UserSession
from auth.security import create_access_token
from core.config import now
from stocktakes.models import Stocktake
from stocktakes.service import StocktakeService
from tests.fakes import signed_in_user

DOCUMENT = "/stores/gastronom/stocktakes/41"
EVENTS = f"{DOCUMENT}/events"
ORIGIN = {"origin": "http://testserver"}
LINE = {
    "request_id": "00000000-0000-4000-8000-000000000001",
    "name": "Молоко",
    "price": "89",
    "quantity": "10",
    "unit": "шт",
}


@pytest.fixture
async def events_client(
    test_app: FastAPI,
    stocktake_engine: AsyncEngine,
) -> AsyncIterator[TestClient]:
    async with AsyncSession(
        bind=stocktake_engine,
    ) as session:
        session.add_all(
            instances=[
                UserSession(
                    id=1,
                    user=signed_in_user(),
                    refresh_jti="test-session",
                    expires_at=now()
                    + timedelta(
                        days=1,
                    ),
                ),
                Stocktake(
                    id=41,
                ),
                Stocktake(
                    id=42,
                    completed_at=now(),
                ),
            ],
        )
        await session.commit()
    with TestClient(
        app=test_app,
    ) as client:
        client.cookies.set(
            name=ACCESS_COOKIE,
            value=create_access_token(
                user_id=1,
                session_id=1,
            ),
        )
        yield client


@contextmanager
def open_socket(client: TestClient) -> Iterator[WebSocketTestSession]:
    session = client.websocket_connect(
        url=EVENTS,
        headers=ORIGIN.copy(),
    )
    app = session.app
    disconnected = Event()

    async def observe_disconnect(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await app(
                scope,
                receive,
                send,
            )
        finally:
            disconnected.set()

    session.app = observe_disconnect
    with session:
        try:
            yield session
        finally:
            # let the app finish its disconnect cleanup before TestClient cancels it
            session.close()
            assert disconnected.wait(
                timeout=5,
            )


async def event(socket: WebSocketTestSession) -> dict:
    # a missing notification must fail the test even when the socket stays up
    async with asyncio.timeout(
        delay=5,
    ):
        return await asyncio.to_thread(
            socket.receive_json,
        )


class TestStocktakeEvents:
    async def test_committed_version_reaches_both_tabs_and_survives_one_disconnect(
        self,
        events_client: TestClient,
    ) -> None:
        with open_socket(
            client=events_client,
        ) as first:
            assert await event(
                socket=first,
            ) == {"type": "ready"}
            with open_socket(
                client=events_client,
            ) as second:
                assert await event(
                    socket=second,
                ) == {"type": "ready"}

                saved = events_client.post(
                    url=f"{DOCUMENT}/lines",
                    json=LINE,
                )

                assert saved.status_code == 200
                assert await event(
                    socket=first,
                ) == {"type": "changed", "version": 2}
                assert await event(
                    socket=second,
                ) == {"type": "changed", "version": 2}

            completed = events_client.post(
                url=f"{DOCUMENT}/complete",
                json={"version": 2},
            )

            assert completed.status_code == 204
            assert await event(
                socket=first,
            ) == {"type": "changed", "version": 3}

    async def test_skips_retries_conflicts_and_changes_to_other_documents(
        self,
        events_client: TestClient,
    ) -> None:
        saved = events_client.post(
            url=f"{DOCUMENT}/lines",
            json=LINE,
        )
        assert saved.status_code == 200
        with open_socket(
            client=events_client,
        ) as socket:
            assert await event(
                socket=socket,
            ) == {"type": "ready"}
            replay = events_client.post(
                url=f"{DOCUMENT}/lines",
                json=LINE,
            )
            conflict = events_client.post(
                url=f"{DOCUMENT}/complete",
                json={"version": 1},
            )
            other = events_client.post(
                url="/stores/gastronom/stocktakes/42/lines",
                params={"correction": "true"},
                json={**LINE, "request_id": "00000000-0000-4000-8000-000000000002"},
            )
            changed = events_client.put(
                url=f"{DOCUMENT}/lines/1",
                json={
                    **LINE,
                    "version": 1,
                    "request_id": "00000000-0000-4000-8000-000000000003",
                    "quantity": "13",
                },
            )

            assert replay.status_code == other.status_code == changed.status_code == 200
            assert conflict.status_code == 409
            assert await event(
                socket=socket,
            ) == {"type": "changed", "version": 3}

    def test_rejects_missing_access_cookie(self, events_client: TestClient) -> None:
        events_client.cookies.clear()

        with (
            pytest.raises(
                expected_exception=WebSocketDenialResponse,
            ) as denied,
            events_client.websocket_connect(
                url=EVENTS,
                headers=ORIGIN.copy(),
            ),
        ):
            pytest.fail(
                reason="anonymous websocket was accepted",
            )

        assert denied.value.status_code == 401

    async def test_an_open_socket_loses_access_on_logout(
        self,
        events_client: TestClient,
        stocktake_engine: AsyncEngine,
    ) -> None:
        with open_socket(
            client=events_client,
        ) as socket:
            assert await event(
                socket=socket,
            ) == {"type": "ready"}

            logout = events_client.post(
                url="/auth/logout",
            )
            async with AsyncSession(
                bind=stocktake_engine,
            ) as session:
                await StocktakeService(
                    session=session,
                ).complete(
                    document_id=41,
                    version=1,
                )

            assert logout.status_code == 204
            with pytest.raises(
                expected_exception=WebSocketDisconnect,
            ) as closed:
                await event(
                    socket=socket,
                )
            assert closed.value.code == 4401

    async def test_listener_loss_closes_socket_and_next_connection_receives_changes(
        self,
        events_client: TestClient,
        test_app: FastAPI,
    ) -> None:
        with open_socket(
            client=events_client,
        ) as socket:
            assert await event(
                socket=socket,
            ) == {"type": "ready"}
            assert events_client.portal is not None
            events_client.portal.call(
                func=test_app.state.stocktake_events.connection.terminate,
            )

            with pytest.raises(
                expected_exception=WebSocketDisconnect,
            ) as closed:
                await event(
                    socket=socket,
                )
            assert closed.value.code == 1013

        with open_socket(
            client=events_client,
        ) as reconnected:
            assert await event(
                socket=reconnected,
            ) == {"type": "ready"}
            saved = events_client.post(
                url=f"{DOCUMENT}/lines",
                json=LINE,
            )
            assert saved.status_code == 200
            assert await event(
                socket=reconnected,
            ) == {"type": "changed", "version": 2}

    def test_meat_store_has_no_subscription(self, events_client: TestClient) -> None:
        with (
            pytest.raises(
                expected_exception=WebSocketDisconnect,
            ) as closed,
            events_client.websocket_connect(
                url="/stores/meat/stocktakes/41/events",
                headers=ORIGIN.copy(),
            ),
        ):
            pytest.fail(
                reason="websocket was accepted for the meat store",
            )

        assert closed.value.code == 1000

    @pytest.mark.parametrize(
        argnames=("url", "origin", "status"),
        argvalues=[
            ("/stores/gastronom/stocktakes/97/events", "http://testserver", 404),
            (EVENTS, "https://elsewhere.example", 403),
        ],
        ids=["missing-document", "foreign-origin"],
    )
    def test_rejects_unavailable_subscription(
        self,
        events_client: TestClient,
        url: str,
        origin: str,
        status: int,
    ) -> None:
        with (
            pytest.raises(
                expected_exception=WebSocketDenialResponse,
            ) as denied,
            events_client.websocket_connect(
                url=url,
                headers={"origin": origin},
            ),
        ):
            pytest.fail(
                reason="websocket was accepted",
            )

        assert denied.value.status_code == status

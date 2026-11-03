import re
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from auth.models import User, UserSession
from auth.security import (
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    hash_password,
    read_refresh_token,
)
from core.config import now, settings
from main import app
from tests.fakes import FakeStore

PASSWORD = "correct horse"
PASSWORD_HASH = hash_password(
    password=PASSWORD,
)
LOGIN_BODY = {
    "login": "ivan",
    "password": PASSWORD,
}
USER_SUMMARY = {
    "id": 7,
    "login": "ivan",
}


@pytest.fixture
def user(store: FakeStore) -> User:
    user = User(
        id=7,
        login="ivan",
        password_hash=PASSWORD_HASH,
        is_active=True,
    )
    store.users[user.id] = user
    return user


def set_cookies(response: Response) -> dict[str, list[str]]:
    """the cookies of the response by name, each with its attributes"""
    cookies = {}
    for header in response.headers.get_list(
        key="set-cookie",
    ):
        first, *attributes = header.split(
            sep="; ",
        )
        cookies[first.split(sep="=")[0]] = attributes
    return cookies


def cookie_value(
    response: Response,
    name: str,
) -> str:
    for header in response.headers.get_list(
        key="set-cookie",
    ):
        if header.startswith(f"{name}="):
            return header.split(sep=";")[0].removeprefix(f"{name}=")
    raise AssertionError(
        f"no cookie {name}",
    )


def sign_in(client: TestClient) -> Response:
    return client.post(
        url="/auth/login",
        json=LOGIN_BODY,
    )


def only_session(store: FakeStore) -> UserSession:
    assert len(store.user_sessions) == 1
    return next(
        iter(
            store.user_sessions.values(),
        ),
    )


class TestLogin:
    def test_returns_user_and_sets_protected_cookies(
        self,
        anonymous_client: TestClient,
        user: User,
    ) -> None:
        response = sign_in(
            client=anonymous_client,
        )

        assert response.status_code == 200
        assert response.json() == USER_SUMMARY
        assert set_cookies(
            response=response,
        ) == {
            "access_token": [
                "HttpOnly",
                "Max-Age=900",
                "Path=/",
                "SameSite=strict",
                "Secure",
            ],
            "refresh_token": [
                "HttpOnly",
                "Max-Age=2592000",
                "Path=/auth",
                "SameSite=strict",
                "Secure",
            ],
        }

    def test_ignores_case_and_spaces_of_login(
        self,
        anonymous_client: TestClient,
        user: User,
    ) -> None:
        response = anonymous_client.post(
            url="/auth/login",
            json={
                "login": "  IVAN ",
                "password": PASSWORD,
            },
        )

        assert response.status_code == 200

    @pytest.mark.parametrize(
        argnames="body",
        argvalues=[
            {"login": "ivan", "password": "wrong password"},
            {"login": "nobody", "password": PASSWORD},
        ],
        ids=["wrong-password", "unknown-login"],
    )
    def test_returns_401_with_one_message_for_bad_credentials(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
        body: dict[str, str],
    ) -> None:
        response = anonymous_client.post(
            url="/auth/login",
            json=body,
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Неверный логин или пароль"}
        assert "set-cookie" not in response.headers
        assert store.user_sessions == {}

    def test_refuses_blocked_user(
        self,
        anonymous_client: TestClient,
        user: User,
    ) -> None:
        user.is_active = False

        response = sign_in(
            client=anonymous_client,
        )

        assert response.status_code == 401

    def test_removes_stale_sessions_of_user(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
    ) -> None:
        store.user_sessions[100] = UserSession(
            id=100,
            user_id=user.id,
            refresh_jti="old",
            expires_at=now()
            - timedelta(
                seconds=1,
            ),
        )

        sign_in(
            client=anonymous_client,
        )

        assert 100 not in store.user_sessions
        assert len(store.user_sessions) == 1

    @pytest.mark.parametrize(
        argnames="body",
        argvalues=[
            {"login": "", "password": PASSWORD},
            {"login": "ivan", "password": ""},
            {"login": "ivan", "password": "x" * 201},
            {"login": "ivan"},
        ],
        ids=["empty-login", "empty-password", "long-password", "no-password"],
    )
    def test_returns_422_for_invalid_body(
        self,
        anonymous_client: TestClient,
        body: dict[str, str],
    ) -> None:
        response = anonymous_client.post(
            url="/auth/login",
            json=body,
        )

        assert response.status_code == 422


class TestMe:
    def test_returns_signed_in_user(
        self,
        anonymous_client: TestClient,
        user: User,
    ) -> None:
        sign_in(
            client=anonymous_client,
        )

        response = anonymous_client.get(
            url="/auth/me",
        )

        assert response.status_code == 200
        assert response.json() == USER_SUMMARY

    def test_returns_401_without_cookie(
        self,
        anonymous_client: TestClient,
    ) -> None:
        response = anonymous_client.get(
            url="/auth/me",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Требуется вход"}

    def test_refuses_refresh_token_as_access(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
    ) -> None:
        signed = sign_in(
            client=anonymous_client,
        )
        anonymous_client.cookies.clear()

        response = anonymous_client.get(
            url="/auth/me",
            headers={
                "Cookie": f"access_token={cookie_value(response=signed, name='refresh_token')}",
            },
        )

        assert response.status_code == 401

    def test_refuses_expired_token(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
    ) -> None:
        sign_in(
            client=anonymous_client,
        )
        token = jwt.encode(
            payload={
                "sub": "7",
                "sid": only_session(
                    store=store,
                ).id,
                "type": "access",
                "exp": int(
                    now().timestamp(),
                )
                - 1,
            },
            key=settings.jwt_secret.get_secret_value(),
            algorithm=ALGORITHM,
        )

        response = anonymous_client.get(
            url="/auth/me",
            headers={
                "Cookie": f"access_token={token}",
            },
        )

        assert response.status_code == 401

    def test_refuses_token_signed_with_other_key(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
    ) -> None:
        sign_in(
            client=anonymous_client,
        )
        token = jwt.encode(
            payload={
                "sub": "7",
                "sid": only_session(
                    store=store,
                ).id,
                "type": "access",
                "exp": int(
                    now().timestamp(),
                )
                + 60,
            },
            key="another key of the same length, 32+",
            algorithm=ALGORITHM,
        )

        response = anonymous_client.get(
            url="/auth/me",
            headers={
                "Cookie": f"access_token={token}",
            },
        )

        assert response.status_code == 401

    def test_refuses_revoked_session(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
    ) -> None:
        sign_in(
            client=anonymous_client,
        )
        only_session(
            store=store,
        ).revoked_at = now()

        response = anonymous_client.get(
            url="/auth/me",
        )

        assert response.status_code == 401

    def test_refuses_blocked_user_at_once(
        self,
        anonymous_client: TestClient,
        user: User,
    ) -> None:
        sign_in(
            client=anonymous_client,
        )
        user.is_active = False

        response = anonymous_client.get(
            url="/auth/me",
        )

        assert response.status_code == 401

    def test_refuses_token_of_missing_session(
        self,
        anonymous_client: TestClient,
    ) -> None:
        token = create_access_token(
            user_id=7,
            session_id=404,
        )

        response = anonymous_client.get(
            url="/auth/me",
            headers={
                "Cookie": f"access_token={token}",
            },
        )

        assert response.status_code == 401


class TestRefresh:
    def test_replaces_both_tokens_and_extends_session(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
    ) -> None:
        signed = sign_in(
            client=anonymous_client,
        )
        user_session = only_session(
            store=store,
        )
        old_jti = user_session.refresh_jti
        user_session.expires_at = now() + timedelta(
            days=1,
        )

        response = anonymous_client.post(
            url="/auth/refresh",
        )

        assert response.status_code == 204
        assert read_refresh_token(
            token=cookie_value(
                response=response,
                name="refresh_token",
            ),
        ) != read_refresh_token(
            token=cookie_value(
                response=signed,
                name="refresh_token",
            ),
        )
        assert user_session.previous_refresh_jti == old_jti
        assert user_session.refresh_jti != old_jti
        assert user_session.rotated_at == now()
        assert user_session.expires_at == now() + timedelta(
            days=30,
        )

    def test_returns_401_without_cookie(
        self,
        anonymous_client: TestClient,
    ) -> None:
        response = anonymous_client.post(
            url="/auth/refresh",
        )

        assert response.status_code == 401

    def test_refuses_access_token_as_refresh(
        self,
        anonymous_client: TestClient,
        user: User,
    ) -> None:
        signed = sign_in(
            client=anonymous_client,
        )

        response = anonymous_client.post(
            url="/auth/refresh",
            headers={
                "Cookie": f"refresh_token={cookie_value(response=signed, name='access_token')}",
            },
        )

        assert response.status_code == 401

    def test_second_tab_gets_no_new_cookies_within_grace(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
    ) -> None:
        signed = sign_in(
            client=anonymous_client,
        )
        old_token = cookie_value(
            response=signed,
            name="refresh_token",
        )
        anonymous_client.post(
            url="/auth/refresh",
        )
        user_session = only_session(
            store=store,
        )
        current_jti = user_session.refresh_jti
        user_session.rotated_at = now() - timedelta(
            seconds=30,
        )

        response = anonymous_client.post(
            url="/auth/refresh",
            headers={
                "Cookie": f"refresh_token={old_token}",
            },
        )

        assert response.status_code == 204
        assert "set-cookie" not in response.headers
        assert user_session.refresh_jti == current_jti
        assert user_session.revoked_at is None

    def test_old_token_after_grace_revokes_session(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
    ) -> None:
        signed = sign_in(
            client=anonymous_client,
        )
        old_token = cookie_value(
            response=signed,
            name="refresh_token",
        )
        anonymous_client.post(
            url="/auth/refresh",
        )
        user_session = only_session(
            store=store,
        )
        user_session.rotated_at = now() - timedelta(
            seconds=31,
        )

        response = anonymous_client.post(
            url="/auth/refresh",
            headers={
                "Cookie": f"refresh_token={old_token}",
            },
        )

        assert response.status_code == 401
        assert user_session.revoked_at == now()

    @pytest.mark.parametrize(
        argnames="moment_field",
        argvalues=["revoked_at", "expires_at"],
    )
    def test_refuses_finished_session(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
        moment_field: str,
    ) -> None:
        sign_in(
            client=anonymous_client,
        )
        setattr(
            only_session(
                store=store,
            ),
            moment_field,
            now(),
        )

        response = anonymous_client.post(
            url="/auth/refresh",
        )

        assert response.status_code == 401

    def test_refuses_blocked_user(
        self,
        anonymous_client: TestClient,
        user: User,
    ) -> None:
        sign_in(
            client=anonymous_client,
        )
        user.is_active = False

        response = anonymous_client.post(
            url="/auth/refresh",
        )

        assert response.status_code == 401

    def test_refuses_token_of_missing_session(
        self,
        anonymous_client: TestClient,
    ) -> None:
        token = create_refresh_token(
            user_id=7,
            session_id=404,
            jti="any",
        )

        response = anonymous_client.post(
            url="/auth/refresh",
            headers={
                "Cookie": f"refresh_token={token}",
            },
        )

        assert response.status_code == 401


class TestLogout:
    def test_revokes_session_and_clears_cookies(
        self,
        anonymous_client: TestClient,
        user: User,
        store: FakeStore,
    ) -> None:
        sign_in(
            client=anonymous_client,
        )

        response = anonymous_client.post(
            url="/auth/logout",
        )

        assert response.status_code == 204
        assert (
            only_session(
                store=store,
            ).revoked_at
            == now()
        )
        cookies = set_cookies(
            response=response,
        )
        assert "Max-Age=0" in cookies["access_token"]
        assert "Max-Age=0" in cookies["refresh_token"]
        assert "Path=/auth" in cookies["refresh_token"]

    def test_returns_401_without_cookie(
        self,
        anonymous_client: TestClient,
    ) -> None:
        response = anonymous_client.post(
            url="/auth/logout",
        )

        assert response.status_code == 401


# the schema is not served, but it is the public list of the routes of nested routers
ROUTES = [
    (method.upper(), path)
    for path, operations in app.openapi()["paths"].items()
    for method in operations
]


class TestEveryRouteIsClosed:
    def test_list_of_routes_holds_the_whole_api(self) -> None:
        assert len(ROUTES) == 56

    @pytest.mark.parametrize(
        argnames=("method", "path"),
        argvalues=[
            route for route in ROUTES if route[1] not in ("/auth/login", "/health")
        ],
    )
    def test_answers_401_without_cookie(
        self,
        anonymous_client: TestClient,
        method: str,
        path: str,
    ) -> None:
        response = anonymous_client.request(
            method=method,
            url=re.sub(
                pattern=r"\{\w+\}",
                repl="1",
                string=path,
            ),
        )

        assert response.status_code == 401

    def test_login_is_reachable_without_cookie(
        self,
        anonymous_client: TestClient,
    ) -> None:
        response = anonymous_client.post(
            url="/auth/login",
        )

        assert response.status_code == 422

    @pytest.mark.parametrize(
        argnames="path",
        argvalues=["/docs", "/redoc", "/openapi.json"],
    )
    def test_docs_are_not_served(
        self,
        anonymous_client: TestClient,
        path: str,
    ) -> None:
        response = anonymous_client.get(
            url=path,
        )

        assert response.status_code == 404

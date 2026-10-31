from datetime import timedelta
from typing import cast

import pytest

from auth import create_user
from auth.models import User, UserSession
from auth.repository import AuthRepository
from auth.security import hash_password, verify_password
from auth.service import AuthService
from core.config import now
from tests.fakes import FakeAuth, FakeStore


@pytest.fixture
def service(store: FakeStore) -> AuthService:
    return AuthService(
        auth=cast(
            AuthRepository,
            FakeAuth(
                store=store,
            ),
        ),
    )


def type_passwords(
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
) -> None:
    typed = iter(
        answers,
    )
    monkeypatch.setattr(
        target=create_user,
        name="getpass",
        value=lambda prompt: next(
            typed,
        ),
    )


class TestSaveUser:
    async def test_creates_user_with_normalized_login(
        self,
        service: AuthService,
        store: FakeStore,
    ) -> None:
        created = await service.save_user(
            login=" Ivan ",
            password="correct horse",
        )

        user = next(
            iter(
                store.users.values(),
            ),
        )
        assert created is True
        assert user.login == "ivan"
        assert verify_password(
            password_hash=user.password_hash,
            password="correct horse",
        )
        assert store.commits == 1

    async def test_changes_password_and_revokes_sessions(
        self,
        service: AuthService,
        store: FakeStore,
    ) -> None:
        user = User(
            id=7,
            login="ivan",
            password_hash=hash_password(
                password="old password",
            ),
            is_active=True,
        )
        store.users[user.id] = user
        store.user_sessions[1] = UserSession(
            id=1,
            user_id=user.id,
            refresh_jti="jti",
            expires_at=now()
            + timedelta(
                days=1,
            ),
        )

        created = await service.save_user(
            login="ivan",
            password="new password",
        )

        assert created is False
        assert len(store.users) == 1
        assert verify_password(
            password_hash=user.password_hash,
            password="new password",
        )
        assert store.user_sessions[1].revoked_at == now()


class TestReadPassword:
    def test_returns_password_typed_twice(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        type_passwords(
            monkeypatch=monkeypatch,
            answers=["12345678", "12345678"],
        )

        assert create_user.read_password() == "12345678"

    def test_refuses_short_password(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        type_passwords(
            monkeypatch=monkeypatch,
            answers=["1234567"],
        )

        with pytest.raises(
            expected_exception=SystemExit,
            match="короче 8",
        ):
            create_user.read_password()

    def test_refuses_different_passwords(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        type_passwords(
            monkeypatch=monkeypatch,
            answers=["12345678", "87654321"],
        )

        with pytest.raises(
            expected_exception=SystemExit,
            match="не совпадают",
        ):
            create_user.read_password()

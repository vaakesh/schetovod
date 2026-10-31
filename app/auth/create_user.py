import argparse
import asyncio
from getpass import getpass

from sqlalchemy.ext.asyncio import AsyncSession

from auth.repository import AuthRepository
from auth.service import AuthService
from core.db import get_engine

MIN_PASSWORD_LENGTH = 8


def read_password() -> str:
    password = getpass(
        prompt="Пароль: ",
    )
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(
            f"Пароль короче {MIN_PASSWORD_LENGTH} символов",
        )
    repeated = getpass(
        prompt="Пароль ещё раз: ",
    )
    if password != repeated:
        raise SystemExit(
            "Пароли не совпадают",
        )
    return password


async def save_user(
    login: str,
    password: str,
) -> bool:
    engine = get_engine()
    async with AsyncSession(
        bind=engine,
        expire_on_commit=False,
    ) as session:
        created = await AuthService(
            auth=AuthRepository(
                session=session,
            ),
        ).save_user(
            login=login,
            password=password,
        )
    await engine.dispose()
    return created


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Создаёт пользователя или меняет ему пароль",
    )
    parser.add_argument(
        "--login",
        required=True,
    )
    arguments = parser.parse_args()
    if not arguments.login.strip():
        raise SystemExit(
            "Логин пустой",
        )

    created = asyncio.run(
        main=save_user(
            login=arguments.login,
            password=read_password(),
        ),
    )
    print(
        "Пользователь создан"
        if created
        else "Пароль изменён, сессии пользователя закрыты",
    )


if __name__ == "__main__":
    main()

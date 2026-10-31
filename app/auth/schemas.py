from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login: Annotated[
        str,
        Field(
            min_length=1,
            max_length=100,
        ),
    ]
    # the limit keeps a huge body away from the slow hash
    password: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
        ),
    ]


class UserSummary(BaseModel):
    id: int
    login: str


@dataclass(
    frozen=True,
)
class AuthTokens:
    access: str
    refresh: str

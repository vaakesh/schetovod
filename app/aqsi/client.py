from datetime import date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, ValidationError

from aqsi.schemas import AqsiShift, AqsiShiftPage
from core.config import settings

BASE_URL = "https://api.aqsi.ru/pub"
PAGE_SIZE = 100
# seconds, every shift takes a request of its own
TIMEOUT = 30


def aqsi_failed(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Не удалось получить смены из aQsi: {detail}",
    )


def start_of_day(day: date) -> datetime:
    """the start of a day of the shop, a time without a zone would mean UTC to aQsi"""
    return datetime.combine(
        date=day,
        time=time.min,
        tzinfo=ZoneInfo(
            key=settings.timezone,
        ),
    )


class AqsiClient:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.transport = transport

    async def shifts(
        self,
        date_from: date,
        date_to: date,
    ) -> list[AqsiShift]:
        """the shifts opened in the period, the last day included"""
        if not settings.aqsi_api_integration:
            raise aqsi_failed(
                detail="не задан ключ AQSI_API_INTEGRATION",
            )
        async with httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                "x-client-key": f"Application {settings.aqsi_api_integration}",
            },
            timeout=TIMEOUT,
            transport=self.transport,
        ) as http:
            shift_ids = await self._shift_ids(
                http=http,
                date_from=date_from,
                date_to=date_to,
            )
            return [
                await self._get(
                    http=http,
                    path=f"/v4/Shifts/{shift_id}",
                    params={},
                    model=AqsiShift,
                )
                for shift_id in shift_ids
            ]

    async def _shift_ids(
        self,
        http: httpx.AsyncClient,
        date_from: date,
        date_to: date,
    ) -> list[UUID]:
        """the list has neither dates nor sums, only the ids to read each shift by"""
        shift_ids: list[UUID] = []
        page = 1
        while True:
            shifts = await self._get(
                http=http,
                path="/v4/Shifts",
                params={
                    "filtered.startDateFrom": start_of_day(
                        day=date_from,
                    ).isoformat(),
                    # the upper bound is not included
                    "filtered.startDateTo": start_of_day(
                        day=date_to
                        + timedelta(
                            days=1,
                        ),
                    ).isoformat(),
                    "pageSize": PAGE_SIZE,
                    "page": page,
                },
                model=AqsiShiftPage,
            )
            shift_ids += [row.id for row in shifts.rows]
            if page >= shifts.pages:
                return shift_ids
            page += 1

    async def _get[Model: BaseModel](
        self,
        http: httpx.AsyncClient,
        path: str,
        params: dict[str, str | int],
        model: type[Model],
    ) -> Model:
        try:
            response = await http.get(
                url=path,
                params=params,
            )
        except httpx.HTTPError as error:
            raise aqsi_failed(
                detail="сервис недоступен",
            ) from error
        if response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ):
            raise aqsi_failed(
                detail="ключ не принят",
            )
        if response.status_code != status.HTTP_200_OK:
            raise aqsi_failed(
                detail=f"сервис ответил ошибкой {response.status_code}",
            )
        try:
            return model.model_validate_json(
                json_data=response.content,
            )
        except ValidationError as error:
            raise aqsi_failed(
                detail="неожиданный формат ответа",
            ) from error


def aqsi_client() -> AqsiClient:
    return AqsiClient()


AqsiClientDep = Annotated[
    AqsiClient,
    Depends(
        dependency=aqsi_client,
    ),
]

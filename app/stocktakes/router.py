from typing import Annotated

from fastapi import APIRouter, Query

from stocktakes.queries import QueriesDep
from stocktakes.schemas import (
    Acknowledgement,
    AddLine,
    DeleteLine,
    Document,
    EditLine,
    RequestId,
    Suggestion,
    Summary,
    Version,
)
from stocktakes.service import ServiceDep

router = APIRouter(
    prefix="/stocktakes",
)


@router.get(
    path="",
)
async def history(queries: QueriesDep) -> list[Summary]:
    return await queries.history()


@router.post(
    path="/open",
)
async def open_document(payload: RequestId, service: ServiceDep) -> Acknowledgement:
    return await service.open(
        request_id=payload.request_id,
    )


@router.get(
    path="/{document_id}",
)
async def document(
    document_id: int, queries: QueriesDep, since: int | None = None
) -> Document | None:
    return await queries.document(
        document_id=document_id,
        since=since,
    )


@router.get(
    path="/{document_id}/suggestions",
)
async def suggestions(
    document_id: int,
    queries: QueriesDep,
    q: Annotated[
        str,
        Query(
            max_length=300,
        ),
    ],
) -> list[Suggestion]:
    return await queries.suggestions(
        document_id=document_id,
        query=q,
    )


@router.post(
    path="/{document_id}/lines",
)
async def add_line(
    document_id: int, payload: AddLine, service: ServiceDep, correction: bool = False
) -> Acknowledgement:
    return await service.change_line(
        document_id=document_id,
        line_id=None,
        payload=payload,
        correction=correction,
    )


@router.put(
    path="/{document_id}/lines/{line_id}",
)
async def edit_line(
    document_id: int,
    line_id: int,
    payload: EditLine,
    service: ServiceDep,
    correction: bool = False,
) -> Acknowledgement:
    return await service.change_line(
        document_id=document_id,
        line_id=line_id,
        payload=payload,
        correction=correction,
    )


@router.delete(
    path="/{document_id}/lines/{line_id}",
)
async def delete_line(
    document_id: int,
    line_id: int,
    payload: DeleteLine,
    service: ServiceDep,
    correction: bool = False,
) -> Acknowledgement:
    return await service.change_line(
        document_id=document_id,
        line_id=line_id,
        payload=payload,
        correction=correction,
    )


@router.post(
    path="/{document_id}/complete",
    status_code=204,
)
async def complete(document_id: int, payload: Version, service: ServiceDep) -> None:
    await service.complete(
        document_id=document_id,
        version=payload.version,
    )

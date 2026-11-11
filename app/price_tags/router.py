from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from core.http import PageLimit, invalid
from price_tags.pdf import FONT_DIR, PriceTagError, TagPreview, price_tag_preview
from price_tags.schemas import PreviewRequest, PriceTagFields, PriceTagOut, PrintRequest
from price_tags.service import PriceTagServiceDep, printed_tag

router = APIRouter()

PDF_MEDIA_TYPE = "application/pdf"


@router.get(
    path="/price-tags/fonts/{weight}.ttf",
    response_class=FileResponse,
)
async def price_tag_font(
    weight: Literal["Medium", "ExtraBold"],
) -> FileResponse:
    return FileResponse(
        path=FONT_DIR / f"Inter-{weight}.ttf",
        media_type="font/ttf",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post(
    path="/price-tags/preview",
    response_model=TagPreview,
)
async def preview_price_tag(
    payload: PreviewRequest,
) -> TagPreview:
    try:
        return await run_in_threadpool(
            func=price_tag_preview,
            tag=printed_tag(
                tag=payload,
            ),
        )
    except PriceTagError as error:
        invalid(
            detail=str(
                error,
            ),
        )


@router.get(
    path="/price-tags/all",
    response_model=list[PriceTagOut],
)
async def all_price_tags(
    service: PriceTagServiceDep,
) -> list[PriceTagOut]:
    return await service.all_tags()


@router.put(
    path="/price-tags/{tag_id}",
    response_model=PriceTagOut,
)
async def edit_price_tag(
    tag_id: int,
    payload: PriceTagFields,
    service: PriceTagServiceDep,
) -> PriceTagOut:
    return await service.edit(
        tag_id=tag_id,
        fields=payload,
    )


@router.delete(
    path="/price-tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_price_tag(
    tag_id: int,
    service: PriceTagServiceDep,
) -> None:
    await service.delete(
        tag_id=tag_id,
    )


@router.get(
    path="/price-tags",
    response_model=list[PriceTagOut],
)
async def search_price_tags(
    service: PriceTagServiceDep,
    q: Annotated[
        str,
        Query(
            max_length=200,
        ),
    ] = "",
    limit: PageLimit = 20,
) -> list[PriceTagOut]:
    return await service.search(
        query=q,
        limit=limit,
    )


@router.post(
    path="/price-tags/print.pdf",
    response_class=Response,
    responses={
        200: {
            "content": {
                PDF_MEDIA_TYPE: {},
            },
        },
    },
)
async def print_price_tags(
    payload: PrintRequest,
    service: PriceTagServiceDep,
) -> Response:
    # inline, the browser opens it in a tab ready to print
    return Response(
        content=await service.print_pdf(
            request=payload,
        ),
        media_type=PDF_MEDIA_TYPE,
        headers={
            "Content-Disposition": 'inline; filename="price-tags.pdf"',
        },
    )

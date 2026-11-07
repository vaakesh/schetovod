from typing import Annotated

from fastapi import APIRouter, Query, Response

from core.http import PageLimit
from price_tags.schemas import PriceTagOut, PrintRequest
from price_tags.service import PriceTagServiceDep

router = APIRouter()

PDF_MEDIA_TYPE = "application/pdf"


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

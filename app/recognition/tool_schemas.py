from typing import Any

from openai.types.responses import ToolParam

from recognition.images import CropRequest

CROP_INSTRUCTIONS = """
You may inspect original image regions with crop_image before returning the JSON
Use it when text is small, rotated, blurred, or characters or table columns are
ambiguous. Prefer inspecting a region over guessing a plausible name or number
Use page numbers starting at 1 in upload order. bbox is [left, top, right, bottom]
in the coordinate space 0..1000 of the full uploaded page, with the origin at its
top-left corner. rotation is clockwise, applied after cropping; use 0 normally
Include enough neighboring text, row boundaries or column headers to identify
the field. Request several useful crops together when possible. You can request
at most 4 crops across at most 2 rounds. Finish with the required invoice JSON
If the crop still cannot be read, use null. Crops show the same invoice, so do
not duplicate rows. Copy printed abbreviations literally, even if you know the
full word. Do not infer missing numbers from arithmetic or other documents
"""

CROP_TOOL: ToolParam = {
    "type": "function",
    "name": "crop_image",
    "description": (
        "Inspect a region of an uploaded invoice at higher visual scale. "
        "Uses original pixels, adds 8% context padding, and optionally rotates "
        "clockwise. Coordinates always refer to the full upright page, not "
        "to a previous crop"
    ),
    "parameters": CropRequest.model_json_schema(),
    "strict": True,
}

NULLABLE_STRING: dict[str, Any] = {
    "type": [
        "string",
        "null",
    ],
}


def strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    """structured outputs need every key required and no extra keys"""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# the shape from prompt.md, formats are checked by InvoiceExtraction afterwards
EXTRACTION_SCHEMA = strict_object(
    properties={
        "supplier": strict_object(
            properties={
                "name": NULLABLE_STRING,
                "inn": NULLABLE_STRING,
            },
        ),
        "invoice_number": NULLABLE_STRING,
        "invoice_date": NULLABLE_STRING,
        "items": {
            "type": "array",
            "items": strict_object(
                properties={
                    "line_no": NULLABLE_STRING,
                    "name": NULLABLE_STRING,
                    "quantity": NULLABLE_STRING,
                    "unit": NULLABLE_STRING,
                    "base_price": NULLABLE_STRING,
                    "base_price_total": NULLABLE_STRING,
                    "cost_price": NULLABLE_STRING,
                    "cost_price_total": NULLABLE_STRING,
                    "vat_percent": NULLABLE_STRING,
                },
            ),
        },
        "totals": strict_object(
            properties={
                "base_total": NULLABLE_STRING,
                "cost_total": NULLABLE_STRING,
            },
        ),
    },
)

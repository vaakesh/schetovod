from pydantic import (
    BaseModel,
)

from core.schema_types import FormModel, Inn, Text


class SupplierSummary(BaseModel):
    id: int
    name: str
    # printed in the reports instead of the full name
    short_name: str | None
    inn: str | None


class SupplierEdit(FormModel):
    name: Text
    # None prints the full name in the reports
    short_name: Text | None
    inn: Inn | None

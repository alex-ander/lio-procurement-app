import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    article_number: str
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    supplier_vat_id: str | None = None
    description: str
    unit_price: Decimal
    currency: str
    unit: str
    quantity: Decimal
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _populate_supplier_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        supplier = getattr(data, "supplier", None)
        if supplier is not None:
            return {
                "id": data.id,
                "article_number": data.article_number,
                "supplier_id": data.supplier_id,
                "supplier_name": getattr(supplier, "name", None),
                "supplier_vat_id": getattr(supplier, "vat_id", None),
                "description": data.description,
                "unit_price": data.unit_price,
                "currency": data.currency,
                "unit": data.unit,
                "quantity": data.quantity,
                "created_at": data.created_at,
            }
        return data


class ArticlePage(BaseModel):
    """A page of articles plus the totals the UI needs to render pagination."""

    items: list[ArticleOut]
    total: int
    limit: int
    offset: int


class ArticleSuggestionOut(BaseModel):
    """A negotiated catalog article matched to a request order line."""

    model_config = ConfigDict(populate_by_name=True)

    article: ArticleOut
    score: float = Field(description="Relevance score between 0 and 1")
    match_reason: str = Field(default="", alias="matchReason")
    estimated_total_price: float = Field(alias="estimatedTotalPrice")
    savings: float | None = Field(
        default=None,
        description="Positive when the negotiated catalog price is cheaper than the requested line total",
    )
    unit_matches: bool = Field(default=False, alias="unitMatches")


class OrderLineMatchIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    position_description: str = Field(default="", alias="positionDescription")
    unit_price: float | None = Field(default=None, alias="unitPrice")
    amount: float = 1.0
    unit: str = ""
    total_price: float | None = Field(default=None, alias="totalPrice")


class CatalogMatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    vendor_name: str | None = Field(default=None, alias="vendorName")
    commodity_group_id: int | None = Field(default=None, alias="commodityGroupId")
    order_lines: list[OrderLineMatchIn] = Field(alias="orderLines")
    limit_per_line: int = Field(default=3, ge=1, le=10, alias="limitPerLine")


class OrderLineMatchOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    line_index: int = Field(alias="lineIndex")
    position_description: str = Field(alias="positionDescription")
    suggestions: list[ArticleSuggestionOut]


class CatalogMatchResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lines: list[OrderLineMatchOut]

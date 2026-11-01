from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.articles import ArticleSuggestionOut


class PdfParseResponse(BaseModel):
    text: str


class ExtractionRequest(BaseModel):
    text: str


# camelCase on the wire — matches the AI's JSON output format and what the
# frontend's extraction flow already consumes.
class OrderLineData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    position_description: str = Field(default="", alias="positionDescription")
    unit_price: float = Field(default=0, alias="unitPrice")
    amount: float = 0
    unit: str = ""
    total_price: float = Field(default=0, alias="totalPrice")
    suggested_articles: list[ArticleSuggestionOut] = Field(
        default_factory=list, alias="suggestedArticles"
    )

    @field_validator("position_description", "unit", mode="before")
    @classmethod
    def _null_str_to_empty(cls, v: object) -> object:
        return "" if v is None else v

    @field_validator("unit_price", "amount", "total_price", mode="before")
    @classmethod
    def _null_num_to_zero(cls, v: object) -> object:
        return 0.0 if v is None else v


class ExtractedVendorData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = ""
    vendor_name: str = Field(default="", alias="vendorName")
    vat_id: str = Field(default="", alias="vatId")
    department: str = ""
    order_lines: list[OrderLineData] = Field(default_factory=list, alias="orderLines")
    total_cost: float = Field(default=0, alias="totalCost")
    commodity_group_id: int | None = Field(default=None, alias="commodityGroupId")
    commodity_group_name: str | None = Field(default=None, alias="commodityGroupName")

    @field_validator("title", "vendor_name", "vat_id", "department", mode="before")
    @classmethod
    def _null_str_to_empty(cls, v: object) -> object:
        return "" if v is None else v

    @field_validator("total_cost", mode="before")
    @classmethod
    def _null_num_to_zero(cls, v: object) -> object:
        return 0.0 if v is None else v

    @field_validator("order_lines", mode="before")
    @classmethod
    def _null_list_to_empty(cls, v: object) -> object:
        return [] if v is None else v


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool
    data: ExtractedVendorData | None = None
    error: str | None = None
    missing_fields: list[str] | None = Field(default=None, alias="missingFields")

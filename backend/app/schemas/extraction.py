from pydantic import BaseModel, ConfigDict, Field


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


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool
    data: ExtractedVendorData | None = None
    error: str | None = None
    missing_fields: list[str] | None = Field(default=None, alias="missingFields")

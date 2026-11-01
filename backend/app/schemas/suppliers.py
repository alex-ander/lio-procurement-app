import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    category: str | None
    country: str | None
    vat_id: str | None
    website: str | None
    email: str | None
    created_at: datetime

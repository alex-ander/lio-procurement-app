from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import CommodityGroup
from app.schemas.requests import CommodityGroupOut

router = APIRouter(prefix="/commodity-groups", tags=["commodity-groups"])


@router.get("", response_model=list[CommodityGroupOut], dependencies=[Depends(get_current_user)])
def list_commodity_groups(db: Session = Depends(get_db)) -> list[CommodityGroupOut]:
    groups = db.scalars(select(CommodityGroup).order_by(CommodityGroup.id))
    return [CommodityGroupOut.model_validate(g) for g in groups]

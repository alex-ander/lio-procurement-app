from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership
from app.db.session import get_db
from app.models import OrganizationMember, Supplier
from app.schemas.suppliers import SupplierOut

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=list[SupplierOut])
def list_suppliers(
    search: str | None = Query(default=None, description="Filter by name (case-insensitive)"),
    category: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> list[SupplierOut]:
    stmt = select(Supplier).where(
        Supplier.organization_id == membership.organization_id
    )
    if search:
        stmt = stmt.where(Supplier.name.ilike(f"%{search}%"))
    if category:
        stmt = stmt.where(Supplier.category == category)
    stmt = stmt.order_by(Supplier.name).offset(offset).limit(limit)
    return [SupplierOut.model_validate(s) for s in db.scalars(stmt)]


@router.get("/count")
def count_suppliers(
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    total = (
        db.scalar(
            select(func.count())
            .select_from(Supplier)
            .where(Supplier.organization_id == membership.organization_id)
        )
        or 0
    )
    return {"count": total}

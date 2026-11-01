from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_membership
from app.db.session import get_db
from app.models import Article, OrganizationMember
from app.schemas.articles import (
    ArticleOut,
    ArticlePage,
    ArticleSuggestionOut,
    CatalogMatchRequest,
    CatalogMatchResponse,
)
from app.services.catalog_matching import (
    load_org_catalog_index,
    match_catalog_for_request,
    match_order_line,
)

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=ArticlePage)
def list_articles(
    search: str | None = Query(
        default=None, description="Filter by description or article number (case-insensitive)"
    ),
    supplier_id: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> ArticlePage:
    filters = [Article.organization_id == membership.organization_id]
    if search:
        for token in search.split():
            term = f"%{token}%"
            filters.append(
                or_(Article.description.ilike(term), Article.article_number.ilike(term))
            )
    if supplier_id:
        filters.append(Article.supplier_id == supplier_id)

    total = db.scalar(
        select(func.count()).select_from(Article).where(*filters)
    ) or 0

    stmt = (
        select(Article)
        .where(*filters)
        .options(joinedload(Article.supplier))
        .order_by(Article.article_number)
        .offset(offset)
        .limit(limit)
    )
    items = [
        ArticleOut(
            id=a.id,
            article_number=a.article_number,
            supplier_id=a.supplier_id,
            supplier_name=a.supplier.name if a.supplier else None,
            supplier_vat_id=a.supplier.vat_id if a.supplier else None,
            description=a.description,
            unit_price=a.unit_price,
            currency=a.currency,
            unit=a.unit,
            quantity=a.quantity,
            created_at=a.created_at,
        )
        for a in db.scalars(stmt)
    ]
    return ArticlePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/count")
def count_articles(
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    total = (
        db.scalar(
            select(func.count())
            .select_from(Article)
            .where(Article.organization_id == membership.organization_id)
        )
        or 0
    )
    return {"count": total}


@router.get("/suggest", response_model=list[ArticleSuggestionOut])
def suggest_articles(
    q: str = Query(..., min_length=1, description="Order line description or search query"),
    unit: str | None = Query(default=None),
    amount: float = Query(default=1.0, gt=0),
    unit_price: float | None = Query(default=None),
    total_price: float | None = Query(default=None),
    title: str | None = Query(default=None),
    vendor_name: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> list[ArticleSuggestionOut]:
    """Suggest negotiated catalog articles matching a single order line description."""
    catalog = load_org_catalog_index(db, membership.organization_id)
    return match_order_line(
        catalog=catalog,
        position_description=q,
        unit=unit,
        amount=amount,
        unit_price=unit_price,
        total_price=total_price,
        title=title,
        vendor_name=vendor_name,
        limit=limit,
    )


@router.post("/match", response_model=CatalogMatchResponse)
def match_articles(
    payload: CatalogMatchRequest,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> CatalogMatchResponse:
    """Match a batch of request order lines against the organization's catalog."""
    return match_catalog_for_request(db, membership.organization_id, payload)

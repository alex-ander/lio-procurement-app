import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.deps import get_current_membership, require_buyer_or_admin
from app.db.session import get_db
from app.models import (
    Article,
    CommodityGroup,
    OrderLine,
    Organization,
    OrganizationMember,
    ProcurementRequest,
    RequestActivity,
    RequestDocument,
)
from app.schemas.organizations import DEFAULT_APPROVAL_THRESHOLD
from app.schemas.requests import (
    ApplyCatalogArticleIn,
    ApprovalDecision,
    OrderLineIn,
    RequestActivityOut,
    RequestCreate,
    RequestOut,
    RequestUpdate,
    StatusUpdate,
)
from app.services.catalog_matching import (
    IndexedArticle,
    load_org_catalog_index,
    match_order_line,
)

router = APIRouter(prefix="/requests", tags=["requests"])

MAX_PDF_BYTES = 10 * 1024 * 1024

# Human-readable labels for the fields we track in the activity log.
_FIELD_LABELS = {
    "requestor_name": "requestor",
    "title": "title",
    "vendor_name": "vendor",
    "vat_id": "tax ID",
    "commodity_group_id": "commodity group",
    "total_cost": "total cost",
    "department": "department",
    "order_lines": "order lines",
}


def _load_request_options():
    return (
        selectinload(ProcurementRequest.order_lines)
        .selectinload(OrderLine.article)
        .joinedload(Article.supplier),
        selectinload(ProcurementRequest.commodity_group),
    )


def _get_org_request(
    db: Session, request_id: uuid.UUID, organization_id: uuid.UUID
) -> ProcurementRequest:
    request = db.scalar(
        select(ProcurementRequest)
        .options(*_load_request_options())
        # Refresh already-loaded relationships (e.g. after an update commit).
        .execution_options(populate_existing=True)
        .where(
            ProcurementRequest.id == request_id,
            ProcurementRequest.organization_id == organization_id,
        )
    )
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found or you do not have permission to access it",
        )
    return request


def _validate_commodity_group(db: Session, commodity_group_id: int) -> None:
    if db.get(CommodityGroup, commodity_group_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown commodity group id: {commodity_group_id}",
        )


def _resolve_org_articles(
    db: Session,
    organization_id: uuid.UUID,
    lines: list[OrderLineIn],
) -> dict[uuid.UUID, Article]:
    """Validate that every referenced ``article_id`` exists in the caller's organization."""
    article_ids = {line.article_id for line in lines if line.article_id is not None}
    if not article_ids:
        return {}
    found = {
        a.id: a
        for a in db.scalars(
            select(Article)
            .options(joinedload(Article.supplier))
            .where(
                Article.id.in_(article_ids),
                Article.organization_id == organization_id,
            )
        )
    }
    missing = article_ids - set(found.keys())
    if missing:
        first_missing = next(iter(missing))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown or inaccessible catalog article id: {first_missing}",
        )
    return found


def _build_order_lines_and_total(
    lines_in: list[OrderLineIn],
    requested_total_cost: float,
    articles_by_id: dict[uuid.UUID, Article],
) -> tuple[list[OrderLine], float]:
    """Build ``OrderLine`` entities, enforcing negotiated catalog prices when ``article_id`` is set."""
    order_lines: list[OrderLine] = []
    price_delta = 0.0
    for index, line in enumerate(lines_in):
        article = articles_by_id.get(line.article_id) if line.article_id else None
        if article is not None:
            unit_price = float(article.unit_price)
            total_price = round(unit_price * float(line.amount), 2)
            price_delta += total_price - float(line.total_price)
        else:
            unit_price = float(line.unit_price)
            total_price = float(line.total_price)

        order_lines.append(
            OrderLine(
                article_id=line.article_id,
                position_description=line.position_description,
                unit_price=unit_price,
                amount=line.amount,
                unit=line.unit,
                total_price=total_price,
                line_order=index + 1,
            )
        )

    adjusted_total = round(max(0.0, float(requested_total_cost) + price_delta), 2)
    return order_lines, adjusted_total


def _serialize_request(
    request: ProcurementRequest,
    catalog: list[IndexedArticle],
) -> RequestOut:
    """Serialize a ``ProcurementRequest`` and attach catalog suggestions to each order line."""
    out = RequestOut.model_validate(request)
    if catalog:
        for line_out in out.order_lines:
            line_out.suggested_articles = match_order_line(
                catalog=catalog,
                position_description=line_out.position_description,
                unit=line_out.unit,
                amount=line_out.amount,
                unit_price=line_out.unit_price,
                total_price=line_out.total_price,
                title=out.title,
                vendor_name=out.vendor_name,
                limit=3,
            )
    return out


def _enforce_required_fields(
    db: Session, organization_id: uuid.UUID, payload: RequestCreate | RequestUpdate
) -> None:
    """Enforce the org's configurable required fields (see OrganizationSettings)."""
    org = db.get(Organization, organization_id)
    required = (org.settings or {}).get("required_fields", []) if org else []
    missing = [field for field in required if not getattr(payload, field, None)]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing fields required by your organization: {', '.join(missing)}",
        )


def _get_approval_threshold(db: Session, organization_id: uuid.UUID) -> float:
    """Return the organization's auto-approval threshold (defaults to $2,000)."""
    org = db.get(Organization, organization_id)
    raw = (org.settings or {}).get("approval_threshold") if org else None
    if raw is None:
        return DEFAULT_APPROVAL_THRESHOLD
    return float(raw)


def _log_activity(
    db: Session,
    request_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    summary: str,
    detail: dict | None = None,
) -> None:
    db.add(
        RequestActivity(
            request_id=request_id,
            actor_id=actor_id,
            action=action,
            summary=summary,
            detail=detail,
        )
    )


def _order_lines_signature(lines) -> list[tuple]:
    return [
        (
            line.position_description,
            float(line.unit_price),
            float(line.amount),
            line.unit,
            float(line.total_price),
            getattr(line, "article_id", None),
        )
        for line in lines
    ]


def _changed_fields(
    request: ProcurementRequest,
    payload: RequestUpdate,
    effective_total_cost: float,
    new_lines: list[OrderLine],
) -> list[str]:
    """Return the field keys whose value differs between the request and payload."""
    changed: list[str] = []
    if request.requestor_name != payload.requestor_name:
        changed.append("requestor_name")
    if request.title != payload.title:
        changed.append("title")
    if request.vendor_name != payload.vendor_name:
        changed.append("vendor_name")
    if (request.vat_id or "") != (payload.vat_id or ""):
        changed.append("vat_id")
    if request.commodity_group_id != payload.commodity_group_id:
        changed.append("commodity_group_id")
    if float(request.total_cost or 0) != float(effective_total_cost or 0):
        changed.append("total_cost")
    if (request.department or "") != (payload.department or ""):
        changed.append("department")
    old_sig = _order_lines_signature(
        sorted(request.order_lines, key=lambda line: line.line_order)
    )
    new_sig = _order_lines_signature(new_lines)
    if old_sig != new_sig:
        changed.append("order_lines")
    return changed


@router.get("", response_model=list[RequestOut])
def list_requests(
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> list[RequestOut]:
    requests = list(
        db.scalars(
            select(ProcurementRequest)
            .options(*_load_request_options())
            .where(ProcurementRequest.organization_id == membership.organization_id)
            .order_by(ProcurementRequest.created_at.desc())
        )
    )
    catalog = load_org_catalog_index(db, membership.organization_id) if requests else []
    return [_serialize_request(r, catalog) for r in requests]


@router.get("/{request_id}", response_model=RequestOut)
def get_request(
    request_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> RequestOut:
    request = _get_org_request(db, request_id, membership.organization_id)
    catalog = load_org_catalog_index(db, membership.organization_id)
    return _serialize_request(request, catalog)


@router.post("", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RequestCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> RequestOut:
    _validate_commodity_group(db, payload.commodity_group_id)
    _enforce_required_fields(db, membership.organization_id, payload)
    articles_by_id = _resolve_org_articles(
        db, membership.organization_id, payload.order_lines
    )
    order_lines, effective_total = _build_order_lines_and_total(
        payload.order_lines, payload.total_cost, articles_by_id
    )
    threshold = _get_approval_threshold(db, membership.organization_id)
    auto_approved = float(effective_total) < threshold

    # Vendor fields are already cleaned up during extraction, so we can persist
    # them directly here.
    request = ProcurementRequest(
        user_id=membership.user_id,
        requestor_name=payload.requestor_name,
        title=payload.title,
        vendor_name=payload.vendor_name,
        vat_id=payload.vat_id,
        commodity_group_id=payload.commodity_group_id,
        total_cost=effective_total,
        department=payload.department,
        organization_id=membership.organization_id,
        created_by=membership.user_id,
        status="open",
        approval_status="approved" if auto_approved else "pending",
        approved_by=None,
        approved_at=datetime.now(timezone.utc) if auto_approved else None,
    )
    request.order_lines = order_lines
    db.add(request)
    db.flush()
    _log_activity(
        db,
        request.id,
        membership.user_id,
        "created",
        (
            f"Request created (auto-approved — below ${threshold:,.2f} threshold)"
            if auto_approved
            else "Request created"
        ),
        {"auto_approved": True, "approval_threshold": threshold} if auto_approved else None,
    )
    db.commit()

    request = _get_org_request(db, request.id, membership.organization_id)
    catalog = load_org_catalog_index(db, membership.organization_id)
    return _serialize_request(request, catalog)


@router.put("/{request_id}", response_model=RequestOut)
def update_request(
    request_id: uuid.UUID,
    payload: RequestUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> RequestOut:
    request = _get_org_request(db, request_id, membership.organization_id)
    _validate_commodity_group(db, payload.commodity_group_id)
    _enforce_required_fields(db, membership.organization_id, payload)
    articles_by_id = _resolve_org_articles(
        db, membership.organization_id, payload.order_lines
    )
    new_lines, effective_total = _build_order_lines_and_total(
        payload.order_lines, payload.total_cost, articles_by_id
    )
    threshold = _get_approval_threshold(db, membership.organization_id)

    changed = _changed_fields(request, payload, effective_total, new_lines)

    request.requestor_name = payload.requestor_name
    request.title = payload.title
    request.vendor_name = payload.vendor_name
    request.vat_id = payload.vat_id
    request.commodity_group_id = payload.commodity_group_id
    request.total_cost = effective_total
    request.department = payload.department

    # Replace order lines (same semantics as the original delete-and-insert).
    request.order_lines = new_lines

    if changed:
        labels = [_FIELD_LABELS.get(f, f) for f in changed]
        _log_activity(
            db,
            request.id,
            membership.user_id,
            "updated",
            f"Updated {', '.join(labels)}",
            {"changed_fields": changed},
        )

    # Re-evaluate approval status when total_cost crosses the threshold.
    if float(effective_total) < threshold and request.approval_status == "pending":
        request.approval_status = "approved"
        request.approved_by = None
        request.approved_at = datetime.now(timezone.utc)
        _log_activity(
            db,
            request.id,
            membership.user_id,
            "approved",
            f"Request auto-approved (below ${threshold:,.2f} threshold)",
            {"auto_approved": True, "approval_threshold": threshold},
        )
    elif (
        float(effective_total) >= threshold
        and request.approval_status == "approved"
        and (request.approved_by is None or "total_cost" in changed)
    ):
        request.approval_status = "pending"
        request.approved_by = None
        request.approved_at = None
        _log_activity(
            db,
            request.id,
            membership.user_id,
            "approval_reset",
            f"Approval required (total ${float(effective_total):,.2f} meets or exceeds ${threshold:,.2f} threshold)",
            {"approval_threshold": threshold},
        )

    db.commit()

    request = _get_org_request(db, request_id, membership.organization_id)
    catalog = load_org_catalog_index(db, membership.organization_id)
    return _serialize_request(request, catalog)


@router.post(
    "/{request_id}/order-lines/{line_id}/apply-article",
    response_model=RequestOut,
)
def apply_catalog_article_to_line(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    payload: ApplyCatalogArticleIn,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> RequestOut:
    """Apply a negotiated catalog article to an existing request order line."""
    request = _get_org_request(db, request_id, membership.organization_id)
    target_line = next(
        (line for line in request.order_lines if line.id == line_id), None
    )
    if target_line is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order line not found on this request",
        )

    article = db.scalar(
        select(Article)
        .options(joinedload(Article.supplier))
        .where(
            Article.id == payload.article_id,
            Article.organization_id == membership.organization_id,
        )
    )
    if article is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown or inaccessible catalog article id: {payload.article_id}",
        )

    old_total = float(target_line.total_price)
    old_unit_price = float(target_line.unit_price)
    new_unit_price = float(article.unit_price)
    new_total = round(new_unit_price * float(target_line.amount), 2)
    savings = round(old_total - new_total, 2)

    target_line.article_id = article.id
    target_line.position_description = article.description
    target_line.unit = article.unit
    target_line.unit_price = new_unit_price
    target_line.total_price = new_total

    current_total_cost = float(request.total_cost or 0)
    request.total_cost = round(
        max(0.0, current_total_cost + (new_total - old_total)), 2
    )

    if payload.update_vendor and article.supplier is not None:
        request.vendor_name = article.supplier.name
        if article.supplier.vat_id:
            request.vat_id = article.supplier.vat_id

    _log_activity(
        db,
        request.id,
        membership.user_id,
        "catalog_article_applied",
        f"Applied catalog article {article.article_number} (${new_unit_price:.2f}/{article.unit})",
        {
            "line_id": str(target_line.id),
            "article_id": str(article.id),
            "article_number": article.article_number,
            "old_unit_price": old_unit_price,
            "new_unit_price": new_unit_price,
            "savings": savings,
        },
    )

    threshold = _get_approval_threshold(db, membership.organization_id)
    new_request_total = float(request.total_cost or 0)
    if new_request_total < threshold and request.approval_status == "pending":
        request.approval_status = "approved"
        request.approved_by = None
        request.approved_at = datetime.now(timezone.utc)
        _log_activity(
            db,
            request.id,
            membership.user_id,
            "approved",
            f"Request auto-approved (below ${threshold:,.2f} threshold)",
            {"auto_approved": True, "approval_threshold": threshold},
        )
    elif (
        new_request_total >= threshold
        and request.approval_status == "approved"
        and request.approved_by is None
    ):
        request.approval_status = "pending"
        request.approved_by = None
        request.approved_at = None
        _log_activity(
            db,
            request.id,
            membership.user_id,
            "approval_reset",
            f"Approval required (total ${new_request_total:,.2f} meets or exceeds ${threshold:,.2f} threshold)",
            {"approval_threshold": threshold},
        )

    db.commit()

    request = _get_org_request(db, request_id, membership.organization_id)
    catalog = load_org_catalog_index(db, membership.organization_id)
    return _serialize_request(request, catalog)


@router.patch("/{request_id}/status", response_model=RequestOut)
def update_status(
    request_id: uuid.UUID,
    payload: StatusUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> RequestOut:
    request = _get_org_request(db, request_id, membership.organization_id)

    if request.status != payload.status:
        _log_activity(
            db,
            request.id,
            membership.user_id,
            "status_changed",
            f"Status changed from {request.status} to {payload.status}",
            {"from": request.status, "to": payload.status},
        )
        request.status = payload.status
        db.commit()

    request = _get_org_request(db, request_id, membership.organization_id)
    catalog = load_org_catalog_index(db, membership.organization_id)
    return _serialize_request(request, catalog)


@router.patch("/{request_id}/approval", response_model=RequestOut)
def decide_approval(
    request_id: uuid.UUID,
    payload: ApprovalDecision,
    membership: OrganizationMember = Depends(require_buyer_or_admin),
    db: Session = Depends(get_db),
) -> RequestOut:
    """Approve or reject a pending request (buyers and admins only)."""
    request = _get_org_request(db, request_id, membership.organization_id)

    if request.approval_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request has already been {request.approval_status}.",
        )

    request.approval_status = payload.decision
    request.approved_by = membership.user_id
    request.approved_at = datetime.now(timezone.utc)
    _log_activity(
        db,
        request.id,
        membership.user_id,
        payload.decision,
        f"Request {payload.decision}",
    )
    db.commit()

    request = _get_org_request(db, request_id, membership.organization_id)
    catalog = load_org_catalog_index(db, membership.organization_id)
    return _serialize_request(request, catalog)


@router.get("/{request_id}/activity", response_model=list[RequestActivityOut])
def get_activity(
    request_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> list[RequestActivityOut]:
    _get_org_request(db, request_id, membership.organization_id)  # scope check
    activity = db.scalars(
        select(RequestActivity)
        .where(RequestActivity.request_id == request_id)
        .order_by(RequestActivity.created_at.desc())
    )
    return [RequestActivityOut.model_validate(a) for a in activity]


@router.put("/{request_id}/document", status_code=status.HTTP_204_NO_CONTENT)
async def upload_document(
    request_id: uuid.UUID,
    file: UploadFile,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> None:
    """Attach (or replace) the original PDF for a request."""
    request = _get_org_request(db, request_id, membership.organization_id)

    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Please upload a PDF file"
        )
    content = await file.read()
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF exceeds the 10MB limit",
        )

    document = db.scalar(
        select(RequestDocument).where(RequestDocument.request_id == request.id)
    )
    if document is None:
        document = RequestDocument(request_id=request.id)
        db.add(document)
    document.filename = file.filename or "document.pdf"
    document.content_type = "application/pdf"
    document.content = content

    _log_activity(
        db,
        request.id,
        membership.user_id,
        "document_attached",
        f"Attached document {document.filename}",
    )
    db.commit()


@router.get("/{request_id}/document")
def get_document(
    request_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> Response:
    _get_org_request(db, request_id, membership.organization_id)  # scope check
    document = db.scalar(
        select(RequestDocument).where(RequestDocument.request_id == request_id)
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No document attached"
        )
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
    )


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request(
    request_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> None:
    request = _get_org_request(db, request_id, membership.organization_id)
    db.delete(request)  # order lines, activity, document cascade
    db.commit()

import json
import logging
import uuid

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    CommodityGroup,
    Organization,
    ProcurementRequest,
    RequestActivity,
)
from app.schemas.extraction import ExtractedVendorData, ExtractionResponse
from app.services.catalog_matching import load_org_catalog_index, match_order_line

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a data extraction and classification specialist. Always respond with "
    "valid JSON only, no markdown or code blocks. Extract all information accurately "
    "from US business documents and classify into the appropriate commodity "
    "group based on the full context of the offer."
)


def _build_category_overview(commodity_groups: list[CommodityGroup]) -> str:
    """Build a compact overview of all main categories and their base item families.

    Collapses ``<Base Item> — <Variant>`` leaves into ``<Base Item>`` so Step 1
    sees every category and every item family across the full taxonomy without
    repeating ribuan variant suffixes.
    """
    by_category: dict[str, list[str]] = {}
    seen_per_category: dict[str, set[str]] = {}
    for g in commodity_groups:
        base_name = g.name.split(" — ", 1)[0].strip()
        seen = seen_per_category.setdefault(g.category, set())
        key = base_name.lower()
        if key not in seen:
            seen.add(key)
            by_category.setdefault(g.category, []).append(base_name)

    return "\n".join(
        f"- {category}: {', '.join(items)}"
        for category, items in by_category.items()
    )


def _load_org_accounting_context(
    db: Session,
    organization_id: uuid.UUID | None,
    commodity_groups: list[CommodityGroup],
) -> tuple[str, set[int]]:
    """Load organization-specific accounting rules, guidelines, and past booking precedents.

    Returns ``(context_text, priority_group_ids)`` so both Step 1 (category
    selection) and Step 2 (sub-item classification) respect the organization's
    accounting rules and learned precedents without hardcoding.
    """
    if organization_id is None:
        return "", set()

    groups_by_id = {g.id: g for g in commodity_groups}
    lines: list[str] = []
    priority_ids: set[int] = set()

    # 1. Explicit organization settings (custom commodity rules & free-text guidelines)
    org = db.get(Organization, organization_id)
    org_settings = (org.settings or {}) if org is not None else {}

    raw_rules = org_settings.get("commodity_rules")
    if isinstance(raw_rules, list):
        for rule in raw_rules:
            if not isinstance(rule, dict):
                continue
            pattern = str(rule.get("pattern") or "").strip()
            cg_id = rule.get("commodity_group_id")
            if pattern and isinstance(cg_id, int) and cg_id in groups_by_id:
                cg = groups_by_id[cg_id]
                priority_ids.add(cg.id)
                lines.append(
                    f'- Custom Rule: "{pattern}" -> MUST book under {cg.id} | {cg.category} | {cg.name}'
                )

    guidelines = str(org_settings.get("accounting_guidelines") or "").strip()
    if guidelines:
        lines.append(f'- Organization Accounting Policy: "{guidelines}"')
        guidelines_lower = guidelines.lower()
        for g in commodity_groups:
            if " — " not in g.name and len(g.name) >= 4 and g.name.lower() in guidelines_lower:
                priority_ids.add(g.id)

        # Resolve common accounting term aliases to actual taxonomy groups
        alias_notes: list[str] = []
        if "office supplies" in guidelines_lower or "office supply" in guidelines_lower:
            explicit_office_supplies = [
                g for g in commodity_groups if "office supplies" in g.name.lower()
            ]
            if explicit_office_supplies:
                for g in explicit_office_supplies:
                    priority_ids.add(g.id)
            elif 15 in groups_by_id:
                cg_15 = groups_by_id[15]
                priority_ids.add(cg_15.id)
                alias_notes.append(
                    f'"Office Supplies" corresponds to {cg_15.id} | {cg_15.category} | {cg_15.name}'
                )
        if "it hardware" in guidelines_lower and 29 in groups_by_id:
            cg_29 = groups_by_id[29]
            priority_ids.add(cg_29.id)
            alias_notes.append(
                f'"IT Hardware" corresponds to {cg_29.id} | {cg_29.category} | {cg_29.name}'
            )
        if "electrical engineering" in guidelines_lower and 11 in groups_by_id:
            cg_11 = groups_by_id[11]
            priority_ids.add(cg_11.id)
            alias_notes.append(
                f'"Electrical Engineering" corresponds to {cg_11.id} | {cg_11.category} | {cg_11.name}'
            )
        if alias_notes:
            lines.append(
                "  * Taxonomy Group Mapping for Policy Terms: " + "; ".join(alias_notes)
            )

    # 2. Learned precedents from the organization's existing procurement requests
    past_requests = list(
        db.scalars(
            select(ProcurementRequest)
            .where(
                ProcurementRequest.organization_id == organization_id,
                ProcurementRequest.commodity_group_id.is_not(None),
            )
            .order_by(ProcurementRequest.updated_at.desc())
            .limit(30)
        )
    )
    if past_requests:
        req_ids = [r.id for r in past_requests]
        activities = list(
            db.scalars(
                select(RequestActivity).where(
                    RequestActivity.request_id.in_(req_ids),
                    RequestActivity.action == "updated",
                )
            )
        )
        corrected_req_ids = {
            a.request_id
            for a in activities
            if isinstance(a.detail, dict)
            and "commodity_group_id" in (a.detail.get("changed_fields") or [])
        }

        for req in past_requests:
            if req.commodity_group_id not in groups_by_id:
                continue
            cg = groups_by_id[req.commodity_group_id]
            priority_ids.add(cg.id)
            item_descs = [
                ol.position_description
                for ol in (req.order_lines or [])
                if ol.position_description
            ]
            items_str = "; ".join(item_descs[:4]) if item_descs else req.title
            tag = (
                "User-Corrected Accounting Precedent"
                if req.id in corrected_req_ids
                else "Past Organization Booking"
            )
            total_val = float(req.total_cost or 0)
            lines.append(
                f'- {tag}: Title="{req.title}", Vendor="{req.vendor_name}", '
                f'Total=${total_val:.2f}, Items=[{items_str}] '
                f'-> Booked under {cg.id} | {cg.category} | {cg.name}'
            )

    return "\n".join(lines), priority_ids


def _build_prompt(
    pdf_text: str,
    category_overview: str,
    org_accounting_context: str = "",
) -> str:
    org_section = ""
    if org_accounting_context:
        org_section = f"""
Organization-Specific Accounting Rules & Past Bookings (HIGHEST PRIORITY):
{org_accounting_context}
"""

    return f"""You are a data extraction and classification specialist. Extract procurement/vendor offer information from the following US business quote text AND identify the most relevant main commodity categories (Step 1 of 2-step classification).

Available Main Categories (Category: Base Item Families):
{category_overview}
{org_section}
Document Text:
{pdf_text}

CRITICAL EXTRACTION RULES:

1. DISTINGUISHING VENDOR (SELLER) vs. DEPARTMENT / CUSTOMER (BUYER):
   - Window-Envelope Layout Warning: Many quotes have a 1-line sender return address (`Seller Name | Street | City`) directly above a 3-4 line recipient mailing address (`Buyer Company \n Contact Person \n Street \n City`). The multi-line mailing address block is the **BUYER/RECIPIENT** (`department`), NEVER the `vendorName`.
   - How to identify `vendorName` (the Seller / Quote Issuer):
     * Look at the 1-line return address above the recipient block, the letterhead/logo, the closing signature (`Best regards, ...` / `Sincerely, ...`), the Sales Rep's email domain (e.g., `rep@vendor-domain.example`), the phrase `"Thank you for your inquiry at <Vendor>"`, and the footer block containing the EIN / Seller's Permit / bank routing details.
   - How to identify `department` (the Buyer / Customer / Recipient):
     * Look at `"Attn: <Department>"` (e.g., `"Purchasing / Engineering"`), `"Prepared for:"`, `"Quote recipient"`, or the multi-line recipient address block associated with `"Customer No."`.
     * If an explicit department (`Attn: ...`) is present, use that department; otherwise use the recipient company/contact from the recipient address block.
     * `vendorName` and `department` must NEVER be the same company and must NEVER be swapped.

2. TAX ID (`vatId`):
   - Extract the Seller's Employer Identification Number (`EIN` / `Tax ID`, e.g., `"85-3252405"` or `"94 1985704"`). Do NOT use the Seller's Permit number, LLC number, or Customer number.
   - If no EIN / Tax ID is present anywhere in the document, return `""` (empty string) for `"vatId"`.

3. ORDER LINES (`orderLines`) & ALTERNATIVE ITEMS:
   - First identify `netItemsSubtotal`: the document's net items subtotal before shipping and tax (`Page subtotal` / `Items subtotal (net)` / `Items (net)` / `Net total` / `Subtotal`).
   - Extract ONLY the active line items whose `totalPrice` values sum up to `netItemsSubtotal`.
   - STRICTLY EXCLUDE alternative or optional items: Any row preceded by a section header like `"Alternative: ..."` (e.g., row `4 Alternative: vertical logo` followed by row `5 ... (Alt.)`), any row containing `"(Alt.)"` or `"Alternative to the preceding item"`, or any row whose Total column is `"U.P."` is an optional alternative NOT included in `netItemsSubtotal` — DO NOT include it in `orderLines`.
   - If including a row would make the sum of `orderLines[].totalPrice` exceed `netItemsSubtotal`, that row is an alternative item and MUST be excluded.
   - EXCLUDE section header rows: Ignore numbering-only category header rows that have no quantity and no price (e.g., `1  Moss Art Panel...` when row `2` is the actual priced item, or `1. Moss art panel` above `1.1`).
   - Do NOT confuse the leftmost `Item` / `Pos` row number (`1`, `2`, `3`, `1.1`, `1.2`) with the quantity (`amount`). The quantity (`amount`) is the number right next to the unit of measure (e.g., `1.00 ea.`, `13.78 sq ft`, `15.75 lin ft`).
   - Do NOT include summary-block shipping, sales tax, or eWaste fees as `orderLines` (unless delivery/shipping is an explicit numbered row inside the main items table with an Item number like `1.2` or `2`).
   - Write out unit abbreviations in plain English (e.g., `"ea."` -> `"pieces"`, `"sq ft"` -> `"square feet"`, `"lin ft"` -> `"linear feet"`).

4. TOTAL COST (`totalCost`):
   - Extract the final `Grand total` / `Total (gross)` / `Total (USD)` (including shipping and taxes) as a numeric value.

5. STEP 1 — MAIN CATEGORY SELECTION (`candidateCategories`):
   - Select the 1 to 3 most relevant main category names from `Available Main Categories` above (ordered from best match to fallback) so Step 2 can match the exact sub-item from the full commodity group list.
   - IMPORTANT: If an Organization-Specific Accounting Rule or Past Booking applies to the items in this quote, you MUST include that rule/booking's target main category in `candidateCategories`.
   - General defaults when no organization-specific override applies:
     * Branded office decor / moss walls / interior plantscaping / office installations → `["Facility Management", "Office & Administration"]`
     * Laptops / computers / IT hardware / software → `["Information Technology"]`
     * Industrial / manufacturing / grinding machinery → `["Production", "Maintenance, Repair & Operations"]`
     * Promotional giveaways / brochures / banners → `["Marketing & Advertising"]`

Return ONLY valid JSON in this exact field order (fill in the evidence and subtotal fields first so `vendorName`, `department`, and `orderLines` are verified before they are emitted):
{{
  "issuerEvidence": "Sales rep email domain, closing signature company, and footer company next to EIN",
  "recipientEvidence": "Company/department in the recipient mailing block or Attn/Prepared-for section",
  "title": "Short 2-5 word description",
  "vatId": "12-3456789",
  "vendorName": "Seller Company Name",
  "department": "Buyer Department or Recipient Name",
  "netItemsSubtotal": 150.00,
  "orderLines": [
    {{
      "positionDescription": "Item description",
      "unitPrice": 150.00,
      "amount": 1.0,
      "unit": "pieces",
      "totalPrice": 150.00
    }}
  ],
  "totalCost": 150.00,
  "candidateCategories": ["Facility Management", "Office & Administration"]
}}"""


def _select_candidate_groups(
    commodity_groups: list[CommodityGroup],
    candidate_categories: list[str],
    priority_group_ids: set[int] | None = None,
) -> list[CommodityGroup]:
    """Filter the full commodity group list down to the selected main categories plus any org priority groups."""
    extra_ids = priority_group_ids or set()
    matched: list[CommodityGroup] = []
    if candidate_categories:
        normalized_targets = {
            c.strip().lower() for c in candidate_categories if isinstance(c, str) and c.strip()
        }
        matched = [
            g
            for g in commodity_groups
            if g.category.strip().lower() in normalized_targets or g.id in extra_ids
        ]
        if matched:
            return matched

    # Fallback if no valid category was returned: include all non-variant base groups + priority groups
    base_groups = [
        g for g in commodity_groups if " — " not in g.name or g.id in extra_ids
    ]
    return base_groups or commodity_groups


def _build_sub_item_prompt(
    extracted: ExtractedVendorData,
    candidate_groups: list[CommodityGroup],
    org_accounting_context: str = "",
) -> str:
    lines_summary = "\n".join(
        f"- {line.position_description} (qty: {line.amount} {line.unit}, unitPrice: {line.unit_price}, total: {line.total_price})"
        for line in extracted.order_lines
    ) or "- (no order lines)"
    groups_text = "\n".join(
        f"{g.id} | {g.category} | {g.name}" for g in candidate_groups
    )

    org_rules_block = ""
    org_priority_rule = ""
    if org_accounting_context:
        org_rules_block = f"""
Organization-Specific Accounting Rules & Past Bookings (NON-NEGOTIABLE OVERRIDES):
{org_accounting_context}
"""
        org_priority_rule = """1. HIGHEST PRIORITY — Organization-Specific Accounting Rules & Past Bookings:
   - Carefully inspect every entry in `Organization-Specific Accounting Rules & Past Bookings` above.
   - Organizations often have non-negotiable accounting quirks where an entire item category or cost tier is booked under a non-standard commodity group (e.g., booking cable ties under `Electrical Engineering`, printer toner under `Hardware`, or small/low-cost software subscriptions under `Office Equipment` / `Office Supplies`).
   - Whenever the current quote is for the SAME general type of product, service, or cost tier as a Past Organization Booking, User-Corrected Precedent, or Custom Rule (even when the vendor name or software/product brand is different!), you MUST select that exact same target `commodityGroupId` — strictly overriding literal taxonomy matches (like `31 | Software` or `204 | Toner Cartridges`) and strictly overriding the general defaults below.
"""

    return f"""Select the SINGLE most appropriate commodity group sub-item for the following extracted procurement quote (Step 2 of 2-step classification).

Quote Summary:
- Title: {extracted.title}
- Vendor: {extracted.vendor_name}
- Department / Buyer: {extracted.department}
- Total Cost: {extracted.total_cost}
- Order Lines:
{lines_summary}
{org_rules_block}
Available Commodity Group Sub-Items in Candidate Categories (ID | Category | Name):
{groups_text}

CLASSIFICATION RULES:
{org_priority_rule}2. General / Base Item vs. Specific Variant (`<Item> — <Variant>`):
   - Many items appear both as a general/base entry (e.g., `15 | Facility Management | Office Equipment`, `29 | Information Technology | Hardware`, `96 | Information Technology | Business Laptop`, `45 | Production | Production Machinery`) and with specific variant suffixes (`— Entry-level`, `— Mid-range`, `— Premium`, `— Refurbished`, `— Leased`, `— Small Pack`, `— Monthly`, etc.).
   - ONLY select a `— <Variant>` row if the quote explicitly specifies that exact tier, condition (e.g. refurbished, leased), pack size, or billing frequency.
   - When no organization-specific rule/precedent above overrides it and the quote does not explicitly state a variant label, prefer the general group or base item without a `— <Variant>` suffix:
     * Branded office decor / moss walls / interior plantscaping / office installations → `15` (`Office Equipment`)
     * Laptops / computers / IT hardware → `29` (`Hardware`) or `96` (`Business Laptop`)
     * Industrial / manufacturing / grinding machinery → `45` (`Production Machinery`)
     * Promotional giveaways / brochures / banners → `43` (`Promotional Materials`)
     * Standard enterprise software licenses (when not overridden by an organization rule/precedent) → `31` (`Software`) or `30` (`IT Services`)

Return ONLY valid JSON in this exact format:
{{
  "commodityGroupId": 15,
  "commodityGroupName": "Office Equipment"
}}"""


def _classify_sub_item(
    client: OpenAI,
    extracted: ExtractedVendorData,
    commodity_groups: list[CommodityGroup],
    candidate_categories: list[str],
    org_accounting_context: str = "",
    priority_group_ids: set[int] | None = None,
) -> tuple[int | None, str | None]:
    """Step 2: Pick the exact commodity group from the full list within the candidate categories."""
    candidate_groups = _select_candidate_groups(
        commodity_groups, candidate_categories, priority_group_ids=priority_group_ids
    )
    if not candidate_groups:
        return None, None

    response = client.chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_sub_item_prompt(
                    extracted, candidate_groups, org_accounting_context=org_accounting_context
                ),
            },
        ],
        max_completion_tokens=500,
        temperature=0.0,
    )
    content = response.choices[0].message.content
    if not content:
        return None, None

    parsed = json.loads(_strip_markdown_fences(content))
    raw_id = parsed.get("commodityGroupId")
    raw_name = parsed.get("commodityGroupName")
    cg_id = int(raw_id) if isinstance(raw_id, (int, float)) else None

    if cg_id is not None:
        by_id = {g.id: g for g in commodity_groups}
        if cg_id in by_id:
            return cg_id, by_id[cg_id].name

    return cg_id, (str(raw_name) if raw_name else None)


def _strip_markdown_fences(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def extract_vendor_data(
    pdf_text: str,
    db: Session,
    organization_id: uuid.UUID | None = None,
) -> ExtractionResponse:
    """Extract vendor data and classify commodity group in one AI call.

    Port of ``src/actions/extraction.ts`` — same prompt, model and validation,
    plus automatic catalog article matching for each extracted order line.
    """
    if not pdf_text or not pdf_text.strip():
        return ExtractionResponse(success=False, error="No text provided for extraction")

    if not settings.openai_api_key:
        return ExtractionResponse(
            success=False,
            error="OPENAI_API_KEY is not configured on the server",
        )

    commodity_groups = list(db.scalars(select(CommodityGroup).order_by(CommodityGroup.id)))
    if not commodity_groups:
        return ExtractionResponse(
            success=False,
            error="Failed to load commodity groups for classification",
        )

    # Two-step classification over the full commodity group list:
    # Step 1: Extract quote fields + select top candidate main categories.
    # Step 2: Match the exact sub-item across all commodity groups in those categories.
    category_overview = _build_category_overview(commodity_groups)
    org_accounting_context, priority_group_ids = _load_org_accounting_context(
        db, organization_id, commodity_groups
    )

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_prompt(
                        pdf_text,
                        category_overview,
                        org_accounting_context=org_accounting_context,
                    ),
                },
            ],
            max_completion_tokens=4000,
            temperature=0.0,
        )

        content = response.choices[0].message.content
        if not content:
            return ExtractionResponse(success=False, error="Empty response from AI")

        raw_payload = json.loads(_strip_markdown_fences(content))
        extracted = ExtractedVendorData.model_validate(raw_payload)

        raw_categories = raw_payload.get("candidateCategories")
        candidate_categories = (
            [str(c) for c in raw_categories if c]
            if isinstance(raw_categories, list)
            else []
        )

        # Step 2: Classify into the exact sub-item within the candidate categories
        cg_id, cg_name = _classify_sub_item(
            client=client,
            extracted=extracted,
            commodity_groups=commodity_groups,
            candidate_categories=candidate_categories,
            org_accounting_context=org_accounting_context,
            priority_group_ids=priority_group_ids,
        )
        if cg_id is not None:
            extracted.commodity_group_id = cg_id
            extracted.commodity_group_name = cg_name
    except Exception as exc:  # noqa: BLE001 — mirror the original catch-all
        logger.exception("Error extracting vendor data")
        return ExtractionResponse(success=False, error=str(exc))

    # Check which fields are missing or empty (same rules as the original).
    missing_fields: list[str] = []
    if not extracted.title.strip():
        missing_fields.append("Title/Short Description")
    if not extracted.vendor_name.strip():
        missing_fields.append("Vendor Name")
    if not extracted.vat_id.strip():
        missing_fields.append("Tax ID")
    if not extracted.department.strip():
        missing_fields.append("Department")
    if not extracted.order_lines:
        missing_fields.append("Order Lines")
    if not extracted.total_cost:
        missing_fields.append("Total Cost")
    if not extracted.commodity_group_id or not extracted.commodity_group_name:
        missing_fields.append("Commodity Group")

    # Validate that the returned commodity group id actually exists.
    if extracted.commodity_group_id is not None:
        valid_ids = {g.id for g in commodity_groups}
        if extracted.commodity_group_id not in valid_ids:
            logger.warning("Invalid commodity group ID returned: %s", extracted.commodity_group_id)
            extracted.commodity_group_id = None
            extracted.commodity_group_name = None
            if "Commodity Group" not in missing_fields:
                missing_fields.append("Commodity Group")

    # Suggest matching negotiated catalog articles for each extracted order line.
    if organization_id is not None and extracted.order_lines:
        catalog = load_org_catalog_index(db, organization_id)
        if catalog:
            for line in extracted.order_lines:
                line.suggested_articles = match_order_line(
                    catalog=catalog,
                    position_description=line.position_description,
                    unit=line.unit,
                    amount=line.amount,
                    unit_price=line.unit_price,
                    total_price=line.total_price,
                    title=extracted.title,
                    vendor_name=extracted.vendor_name,
                    limit=3,
                )

    return ExtractionResponse(
        success=True,
        data=extracted,
        missing_fields=missing_fields or None,
    )

import json
import logging
import uuid

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import CommodityGroup
from app.schemas.extraction import ExtractedVendorData, ExtractionResponse
from app.services.catalog_matching import load_org_catalog_index, match_order_line

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a data extraction and classification specialist. Always respond with "
    "valid JSON only, no markdown or code blocks. Extract all information accurately "
    "from US business documents and classify into the appropriate commodity "
    "group based on the full context of the offer."
)


def _build_prompt(pdf_text: str, commodity_groups_list: str) -> str:
    return f"""You are a data extraction and classification specialist. Extract procurement/vendor offer information from the following US business quote text AND classify it into the appropriate commodity group.

Available Commodity Groups (ID | Category | Name):
{commodity_groups_list}

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

5. COMMODITY GROUP CLASSIFICATION:
   - Select the SINGLE most appropriate commodity group from the Available Commodity Groups list above:
     * Branded office decor / moss walls / interior plantscaping / furniture → `15` (`Office Equipment`)
     * Laptops / computers / IT hardware → `29` (`Hardware`)
     * Industrial / manufacturing / grinding machinery → `45` (`Production Machinery`)
     * Promotional giveaways / brochures / banners → `43` (`Promotional Materials`)
     * Software licenses → `31` (`Software`) or `30` (`IT Services`)

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
  "commodityGroupId": 15,
  "commodityGroupName": "Office Equipment"
}}"""


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

    # Pass the canonical 50 commodity groups (ids 1-50) to avoid diluting the prompt
    # with 2,000 synthetic variant rows; fall back to the first 50 if custom ids are used.
    core_groups = [g for g in commodity_groups if g.id <= 50] or commodity_groups[:50]
    commodity_groups_list = "\n".join(f"{g.id} | {g.category} | {g.name}" for g in core_groups)

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(pdf_text, commodity_groups_list)},
            ],
            max_completion_tokens=4000,
            temperature=0.0,
        )

        content = response.choices[0].message.content
        if not content:
            return ExtractionResponse(success=False, error="Empty response from AI")

        extracted = ExtractedVendorData.model_validate(json.loads(_strip_markdown_fences(content)))
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

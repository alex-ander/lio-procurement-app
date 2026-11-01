import json
import logging

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import CommodityGroup
from app.schemas.extraction import ExtractedVendorData, ExtractionResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a data extraction and classification specialist. Always respond with "
    "valid JSON only, no markdown or code blocks. Extract all information accurately "
    "from US business documents and classify into the appropriate commodity "
    "group based on the full context of the offer."
)


def _build_prompt(pdf_text: str, commodity_groups_list: str) -> str:
    return f"""You are a data extraction and classification specialist. Extract procurement/vendor offer information from the following US document text AND classify it into the appropriate commodity group.

Document Text:
{pdf_text}

Please extract the following information:
1. Title/Short Description (A brief summary of what this procurement is for - e.g., "Office Equipment Purchase", "Software Licenses", etc.)
2. Vendor Name (Vendor/Supplier/Seller/Company name)
3. Tax ID (Employer Identification Number/EIN/Federal Tax ID/TIN/VAT ID)
4. Department/Customer (Department/Customer/Bill To/Customer name)
5. Order Lines/Items (All line items with):
   - Position Description (Description/Product/Item/Article)
   - Unit Price (Unit Price/Price/Rate/Price per unit)
   - Amount (Qty/Quantity/Count)
   - Unit (Unit/UoM - e.g., "licenses", "pieces", "ea.", "items")
   - Total Price (Total/Ext. Price/Amount)
6. Total Cost (Grand Total/Total Cost/Total Offer Cost)
7. Commodity Group Classification - Select the SINGLE most appropriate commodity group from the list below

Available Commodity Groups (ID | Category | Name):
{commodity_groups_list}

IMPORTANT INSTRUCTIONS:
- For the title, create a SHORT (2-5 words) description based on the main items being purchased
- Extract ALL line items, even if there are many
- For unit prices and totals, extract only the numeric value (remove currency symbols)
- For the unit field, write out abbreviations in plain English (e.g., "ea." -> "pieces", "lic." -> "licenses")
- Be careful with US number formatting (e.g., "1,438.00" = 1438.00)
- For classification, consider the PRIMARY nature and purpose of the items:
  * Branded office decor/furniture → Office Equipment (15)
  * Traditional promotional items (brochures, giveaways, banners) → Promotional Materials (43)
  * Software/IT products → Software (31) or IT Services (30)
  * If genuinely uncertain, set commodityGroupId to null

Return ONLY valid JSON in this exact format (no markdown, no code blocks):
{{
  "title": "Short description of procurement",
  "vendorName": "Company Name",
  "vatId": "12-3456789",
  "department": "Department Name",
  "orderLines": [
    {{
      "positionDescription": "Item description",
      "unitPrice": 150.00,
      "amount": 10,
      "unit": "licenses",
      "totalPrice": 1500.00
    }}
  ],
  "totalCost": 1500.00,
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


def extract_vendor_data(pdf_text: str, db: Session) -> ExtractionResponse:
    """Extract vendor data and classify commodity group in one AI call.

    Port of ``src/actions/extraction.ts`` — same prompt, model and validation.
    """
    if not pdf_text or not pdf_text.strip():
        return ExtractionResponse(success=False, error="No text provided for extraction")

    if not settings.openai_api_key:
        return ExtractionResponse(
            success=False,
            error="OPENAI_API_KEY is not configured on the server",
        )

    commodity_groups = list(
        db.scalars(select(CommodityGroup).order_by(CommodityGroup.id))
    )
    if not commodity_groups:
        return ExtractionResponse(
            success=False,
            error="Failed to load commodity groups for classification",
        )

    # Give the model the full commodity catalog so it has complete context to
    # pick the most accurate match in a single pass.
    commodity_groups_list = "\n".join(
        f"{g.id} | {g.category} | {g.name}" for g in commodity_groups
    )

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(pdf_text, commodity_groups_list)},
            ],
            max_completion_tokens=4000,
            temperature=0.3,
        )

        content = response.choices[0].message.content
        if not content:
            return ExtractionResponse(success=False, error="Empty response from AI")

        extracted = ExtractedVendorData.model_validate(
            json.loads(_strip_markdown_fences(content))
        )
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
            logger.warning(
                "Invalid commodity group ID returned: %s", extracted.commodity_group_id
            )
            extracted.commodity_group_id = None
            extracted.commodity_group_name = None
            if "Commodity Group" not in missing_fields:
                missing_fields.append("Commodity Group")

    return ExtractionResponse(
        success=True,
        data=extracted,
        missing_fields=missing_fields or None,
    )

"""Catalog matching service: suggests negotiated catalog articles for request lines."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Article
from app.schemas.articles import (
    ArticleOut,
    ArticleSuggestionOut,
    CatalogMatchRequest,
    CatalogMatchResponse,
    OrderLineMatchOut,
)

STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "no",
        "of",
        "on",
        "or",
        "per",
        "the",
        "to",
        "up",
        "via",
        "with",
        "incl",
        "including",
        "custom",
        "made",
        "measure",
        "standard",
        "full",
        "single",
        "double",
        "high",
        "low",
        "new",
        "used",
        "grade",
        "type",
        "series",
        "model",
        "horizontal",
        "vertical",
        "company",
        "cut",
        "out",
        "art",
        "module",
        "business",
        "industrial",
        "commercial",
        "service",
        "services",
        "system",
        "framed",
        "preserved",
        "modular",
        "living",
        "large",
        "indoor",
        "small",
    }
)

# Generic form-factor, container, or modifier tokens that cannot be the sole reason
# an unrelated catalog item matches a line item.
GENERIC_FORM_TOKENS: frozenset[str] = frozenset(
    {
        "panel",
        "wall",
        "ball",
        "light",
        "stand",
        "kit",
        "station",
        "cable",
        "sheet",
        "wire",
        "film",
        "tape",
        "box",
        "label",
        "license",
        "plan",
        "connection",
        "inspection",
        "rental",
        "transport",
        "delivery",
        "storage",
        "packing",
        "shipping",
        "pack",
        "set",
        "piece",
        "roll",
        "unit",
        "green",
        "office",
        "branded",
        "eco",
        "recycled",
        "plastic",
        "metal",
        "acrylic",
        "mesh",
        "ergonomic",
    }
)

SYNONYMS: dict[str, tuple[str, ...]] = {
    "macbook": ("laptop", "ultralight"),
    "notebook": ("laptop",),
    "thinkpad": ("laptop",),
    "ultrabook": ("laptop", "ultralight"),
    "chairs": ("chair",),
    "pens": ("pen",),
    "monitors": ("monitor",),
    "laptops": ("laptop",),
    "panels": ("panel",),
    "walls": ("wall",),
    "switches": ("switch",),
    "licenses": ("license",),
    "shirts": ("shirt", "apparel"),
    "tshirt": ("shirt", "apparel"),
    "polo": ("polo", "apparel"),
    "boxes": ("box",),
    "gloves": ("glove",),
    "cables": ("cable",),
    "filters": ("filter",),
    "pallets": ("pallet",),
    "banners": ("banner",),
    "brochures": ("brochure",),
    "greening": ("moss", "green", "wall"),
    "moss": ("moss", "plant", "wall", "panel"),
}

UNIT_ALIASES: dict[str, str] = {
    "piece": "piece",
    "pieces": "piece",
    "pc": "piece",
    "pcs": "piece",
    "ea": "piece",
    "ea.": "piece",
    "each": "piece",
    "unit": "piece",
    "units": "piece",
    "item": "piece",
    "items": "piece",
    "sq ft": "sq ft",
    "sqft": "sq ft",
    "square feet": "sq ft",
    "square foot": "sq ft",
    "sq. ft.": "sq ft",
    "ft": "ft",
    "feet": "ft",
    "foot": "ft",
    "lin ft": "ft",
    "linear feet": "ft",
    "linear foot": "ft",
    "pack": "pack",
    "packs": "pack",
    "pkg": "pack",
    "set": "set",
    "sets": "set",
    "kit": "set",
    "license": "license",
    "licenses": "license",
    "seat": "license",
    "seats": "license",
    "hour": "hour",
    "hours": "hour",
    "hr": "hour",
    "hrs": "hour",
    "day": "day",
    "days": "day",
    "month": "month",
    "months": "month",
    "mo": "month",
    "monthly": "month",
    "roll": "roll",
    "rolls": "roll",
    "pallet": "pallet",
    "pallets": "pallet",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "gal": "gal",
    "gallon": "gal",
    "gallons": "gal",
}


def normalize_unit(unit: str | None) -> str:
    if not unit:
        return ""
    cleaned = unit.strip().lower().rstrip(".")
    return UNIT_ALIASES.get(cleaned, cleaned)


def normalize_text(text: str | None) -> list[str]:
    if not text:
        return []
    s = text.lower()
    # Normalize inch specs like 13", 13-inch, 13 inch -> 13in
    s = re.sub(r'(\d+)\s*(?:\"|inch\b|inches\b|-inch\b)', r"\1in", s)
    # Normalize storage/power/weight specs like 16 GB, 512 GB, 1 TB -> 16gb, 512gb, 1tb
    s = re.sub(r"(\d+)\s*(gb|tb|mb|kw|kwh|hp|rpm|awg|gal|lb)\b", r"\1\2", s)
    raw_tokens = re.findall(r"[a-z0-9]+", s)
    tokens: list[str] = []
    for tok in raw_tokens:
        if tok in STOPWORDS or (tok.isdigit() and len(tok) <= 2):
            continue
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss") and tok not in SYNONYMS:
            tokens.append(tok[:-1])
        else:
            tokens.append(tok)
    return tokens


def expand_tokens(tokens: list[str] | set[str]) -> set[str]:
    out = set(tokens)
    for tok in tokens:
        for syn in SYNONYMS.get(tok, ()):
            out.add(syn)
    return out


def extract_primary_subject(description: str) -> set[str]:
    """Extract the defining head noun(s) of a catalog article description."""
    head_clause = re.split(
        r"[,/]|(?:\bwith\b)|(?:\bper\b)|(?:\bmade\b)", description.lower()
    )[0]
    head_toks = [t for t in normalize_text(head_clause) if not re.match(r"^\d", t)]
    specific = [t for t in head_toks if t not in GENERIC_FORM_TOKENS]
    if specific:
        return {specific[0]}
    return set(head_toks[:2])


@dataclass(frozen=True)
class IndexedArticle:
    article: Article
    article_out: ArticleOut
    article_number_lower: str
    description_lower: str
    raw_tokens: frozenset[str]
    expanded_tokens: frozenset[str]
    primary_subject: frozenset[str]
    normalized_unit: str
    unit_price_float: float
    supplier_name_lower: str


def build_catalog_index(articles: list[Article]) -> list[IndexedArticle]:
    """Pre-tokenize a list of ``Article`` ORM objects for fast repeated matching."""
    indexed: list[IndexedArticle] = []
    for art in articles:
        raw = frozenset(normalize_text(art.description))
        expanded = frozenset(expand_tokens(raw))
        subj = frozenset(extract_primary_subject(art.description))
        supplier_name = art.supplier.name if art.supplier else None
        supplier_vat_id = art.supplier.vat_id if art.supplier else None
        art_out = ArticleOut(
            id=art.id,
            article_number=art.article_number,
            supplier_id=art.supplier_id,
            supplier_name=supplier_name,
            supplier_vat_id=supplier_vat_id,
            description=art.description,
            unit_price=art.unit_price,
            currency=art.currency,
            unit=art.unit,
            quantity=art.quantity,
            created_at=art.created_at,
        )
        indexed.append(
            IndexedArticle(
                article=art,
                article_out=art_out,
                article_number_lower=art.article_number.strip().lower(),
                description_lower=art.description.strip().lower(),
                raw_tokens=raw,
                expanded_tokens=expanded,
                primary_subject=subj,
                normalized_unit=normalize_unit(art.unit),
                unit_price_float=float(art.unit_price),
                supplier_name_lower=(supplier_name or "").strip().lower(),
            )
        )
    return indexed


def load_org_catalog_index(db: Session, organization_id: uuid.UUID | None) -> list[IndexedArticle]:
    """Load and index all catalog articles belonging to ``organization_id``."""
    if organization_id is None:
        return []
    stmt = (
        select(Article)
        .where(Article.organization_id == organization_id)
        .options(joinedload(Article.supplier))
        .order_by(Article.unit_price.asc(), Article.article_number.asc())
    )
    articles = list(db.scalars(stmt))
    return build_catalog_index(articles)


def match_order_line(
    catalog: list[IndexedArticle],
    position_description: str,
    unit: str | None = None,
    amount: float = 1.0,
    unit_price: float | None = None,
    total_price: float | None = None,
    title: str | None = None,
    vendor_name: str | None = None,
    limit: int = 3,
) -> list[ArticleSuggestionOut]:
    """Find the best matching negotiated catalog articles for a single order line."""
    if not catalog or not position_description or not position_description.strip():
        return []

    desc_clean = position_description.strip()
    desc_lower = desc_clean.lower()
    raw_line_tokens = set(normalize_text(desc_clean))
    line_tokens = expand_tokens(raw_line_tokens)
    ctx_tokens = expand_tokens(normalize_text(title))
    all_query_tokens = line_tokens | ctx_tokens

    norm_query_unit = normalize_unit(unit)
    vendor_lower = (vendor_name or "").strip().lower()
    eff_amount = float(amount) if amount and amount > 0 else 1.0
    requested_total: float | None = None
    if total_price is not None and total_price > 0:
        requested_total = float(total_price)
    elif unit_price is not None and unit_price > 0:
        requested_total = round(float(unit_price) * eff_amount, 2)

    candidates: list[tuple[float, float, IndexedArticle, str, bool]] = []

    for item in catalog:
        unit_matches = bool(norm_query_unit and item.normalized_unit == norm_query_unit)
        vendor_matches = bool(
            vendor_lower
            and item.supplier_name_lower
            and (
                vendor_lower in item.supplier_name_lower
                or item.supplier_name_lower in vendor_lower
            )
        )

        # 1. Exact article number mentioned in the line description
        if item.article_number_lower and item.article_number_lower in desc_lower:
            score = 1.0
            reason = f"Exact article number match ({item.article.article_number})"
            candidates.append((score, item.unit_price_float, item, reason, unit_matches))
            continue

        # 2. Exact description match
        if item.description_lower == desc_lower:
            score = 0.99 if not vendor_matches else 1.0
            reason = "Exact catalog description match"
            candidates.append((score, item.unit_price_float, item, reason, unit_matches))
            continue

        # 3. Token & subject-gated match
        if not item.raw_tokens:
            continue

        specific_line_overlap = (line_tokens & item.raw_tokens) - GENERIC_FORM_TOKENS
        if not specific_line_overlap:
            continue

        if item.primary_subject and not (item.primary_subject <= all_query_tokens):
            continue

        art_coverage = len(all_query_tokens & item.raw_tokens) / max(len(item.raw_tokens), 1)
        line_coverage = len(line_tokens & item.raw_tokens) / max(len(raw_line_tokens), 1)
        subject_in_line = 1.0 if (item.primary_subject <= line_tokens) else 0.65
        unit_bonus = 1.0 if unit_matches else 0.0
        vendor_bonus = 0.05 if vendor_matches else 0.0

        score = min(
            0.98,
            0.35 * subject_in_line
            + 0.35 * art_coverage
            + 0.15 * line_coverage
            + 0.15 * unit_bonus
            + vendor_bonus,
        )
        if score < 0.45:
            continue

        matched_terms = sorted((all_query_tokens & item.raw_tokens) - STOPWORDS)
        reason = f"Matched catalog terms: {', '.join(matched_terms[:4])}"
        if vendor_matches:
            reason += f" (preferred supplier {item.article_out.supplier_name})"
        candidates.append((score, item.unit_price_float, item, reason, unit_matches))

    # Sort by highest score first, then lowest negotiated unit price
    candidates.sort(key=lambda c: (-round(c[0], 3), c[1], c[2].article_number_lower))

    # Deduplicate by (description_lower, normalized_unit) so top suggestions show distinct
    # catalog products at their best negotiated price (while preserving a second entry if
    # the user's selected vendor also offers that product).
    selected: list[tuple[float, float, IndexedArticle, str, bool]] = []
    overflow: list[tuple[float, float, IndexedArticle, str, bool]] = []
    seen_descriptions: set[tuple[str, str]] = set()

    for cand in candidates:
        key = (cand[2].description_lower, cand[2].normalized_unit)
        if key not in seen_descriptions:
            seen_descriptions.add(key)
            selected.append(cand)
        else:
            overflow.append(cand)
        if len(selected) >= limit:
            break

    if len(selected) < limit and overflow:
        for cand in overflow:
            selected.append(cand)
            if len(selected) >= limit:
                break

    suggestions: list[ArticleSuggestionOut] = []
    for score, unit_price_val, item, reason, unit_matches in selected[:limit]:
        est_total = round(unit_price_val * eff_amount, 2)
        savings = (
            round(requested_total - est_total, 2)
            if requested_total is not None
            else None
        )
        suggestions.append(
            ArticleSuggestionOut(
                article=item.article_out,
                score=round(score, 3),
                match_reason=reason,
                estimated_total_price=est_total,
                savings=savings,
                unit_matches=unit_matches,
            )
        )
    return suggestions


def match_catalog_for_request(
    db: Session,
    organization_id: uuid.UUID | None,
    payload: CatalogMatchRequest,
) -> CatalogMatchResponse:
    """Match a batch of order lines against the organization's negotiated catalog."""
    catalog = load_org_catalog_index(db, organization_id)
    lines_out: list[OrderLineMatchOut] = []
    for idx, line in enumerate(payload.order_lines):
        suggestions = match_order_line(
            catalog=catalog,
            position_description=line.position_description,
            unit=line.unit,
            amount=line.amount,
            unit_price=line.unit_price,
            total_price=line.total_price,
            title=payload.title,
            vendor_name=payload.vendor_name,
            limit=payload.limit_per_line,
        )
        lines_out.append(
            OrderLineMatchOut(
                line_index=idx,
                position_description=line.position_description,
                suggestions=suggestions,
            )
        )
    return CatalogMatchResponse(lines=lines_out)

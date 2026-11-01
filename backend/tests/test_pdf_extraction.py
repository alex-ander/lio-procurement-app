"""End-to-end PDF parsing and vendor-extraction tests against the 5 sample quotes.

Compares the output of ``POST /pdf/parse`` + ``POST /extraction`` against the
ground-truth fields from each PDF in the case-study ``quotes/`` folder.

Run with:
    python -m pytest tests/test_pdf_extraction.py -v -s
or directly for a full comparison report:
    python tests/test_pdf_extraction.py
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.schemas.extraction import ExtractionResponse
from app.seed import seed

# ---------------------------------------------------------------------------
# Locate quote PDFs (prefer the user's Downloads folder, fall back to repo)
# ---------------------------------------------------------------------------
CANDIDATE_QUOTE_DIRS = [
    Path("/Users/alex/Downloads/wetransfer_lio-i-case-study_2026-10-30_1058 2/english-case/quotes"),
    Path(__file__).resolve().parent.parent.parent / "quotes",
    Path(__file__).resolve().parent / "fixtures" / "quotes",
]


def _resolve_quotes_dir() -> Path:
    for candidate in CANDIDATE_QUOTE_DIRS:
        try:
            if candidate.is_dir() and any(candidate.glob("*.[pP][dD][fF]")):
                return candidate
        except PermissionError:
            continue
    raise FileNotFoundError(
        f"Could not find quote PDFs in any of: {[str(p) for p in CANDIDATE_QUOTE_DIRS]}"
    )


QUOTES_DIR = _resolve_quotes_dir()


# ---------------------------------------------------------------------------
# Ground-truth expectations for each PDF quote
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ExpectedOrderLine:
    description_keywords: tuple[str, ...]
    amount: float
    unit_prices: tuple[float, ...]  # acceptable unit prices (e.g. list vs discounted)
    total_price: float
    unit_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpectedQuote:
    filename: str
    vendor_names: tuple[str, ...]  # acceptable normalized vendor names
    customer_name: str  # customer / recipient (must NOT be extracted as vendorName)
    vat_id: str | None  # expected EIN / Tax ID (None if absent from the PDF)
    department_keywords: tuple[str, ...]
    order_lines: tuple[ExpectedOrderLine, ...]
    forbidden_line_keywords: tuple[str, ...]  # e.g. alternative items that shouldn't be summed
    net_total: float
    gross_total: float
    commodity_group_ids: tuple[int, ...]
    commodity_group_names: tuple[str, ...]
    expected_text_snippets: tuple[str, ...] = field(default_factory=tuple)


EXPECTED_QUOTES: dict[str, ExpectedQuote] = {
    "QT-4120-Cust-14918.pdf": ExpectedQuote(
        filename="QT-4120-Cust-14918.pdf",
        vendor_names=("Greenmantle Moss Studio, LLC", "Greenmantle Moss Studio"),
        customer_name="Lio Technologies, Inc.",
        vat_id="85-3252405",
        department_keywords=("Lio Technologies",),
        order_lines=(
            ExpectedOrderLine(
                description_keywords=("moss art panel", "mixed moss"),
                amount=1.0,
                # List price is $894.08 with -20% discount -> $715.26 effective unit/total price
                unit_prices=(715.26, 894.08),
                total_price=715.26,
                unit_keywords=("piece", "pieces", "ea"),
            ),
            ExpectedOrderLine(
                description_keywords=("logo integration", "horizontal"),
                amount=1.0,
                unit_prices=(622.00,),
                total_price=622.00,
                unit_keywords=("piece", "pieces", "ea"),
            ),
        ),
        # Item 5 ("Logo integration 'asklio' vertical", $430.00) is marked "(Alt.)" /
        # "Alternative: vertical logo" and is excluded from the $1,337.26 subtotal.
        forbidden_line_keywords=("vertical",),
        net_total=1337.26,
        gross_total=1686.14,
        commodity_group_ids=(15,),
        commodity_group_names=("Office Equipment",),
        expected_text_snippets=("Quote 4120", "Greenmantle Moss Studio, LLC", "85-3252405"),
    ),
    "QT-OF2312380-Cust-57692.pdf": ExpectedQuote(
        filename="QT-OF2312380-Cust-57692.pdf",
        vendor_names=("verdeform", "Bloomcraft Interiors, Inc.", "Bloomcraft Interiors"),
        customer_name="Lio Technologies, Inc.",
        # EIN 27-1073640 is in the PDF footer
        vat_id="27-1073640",
        department_keywords=("Lio Technologies", "Vladimir Keil"),
        order_lines=(
            ExpectedOrderLine(
                description_keywords=("module", "forest", "ball moss"),
                amount=13.78,
                unit_prices=(52.00,),
                total_price=716.56,
                unit_keywords=("sq", "square"),
            ),
            ExpectedOrderLine(
                description_keywords=("edge greening", "forest moss"),
                amount=15.75,
                unit_prices=(7.65,),
                total_price=120.49,
                unit_keywords=("lin", "linear", "feet", "ft"),
            ),
            ExpectedOrderLine(
                description_keywords=("logo acrylic", "standoffs"),
                amount=1.0,
                unit_prices=(350.00,),
                total_price=350.00,
                unit_keywords=("piece", "pieces", "ea"),
            ),
        ),
        forbidden_line_keywords=("moss duo",),
        net_total=1187.05,
        gross_total=1413.10,
        commodity_group_ids=(15,),
        commodity_group_names=("Office Equipment",),
        expected_text_snippets=("Quote OF2312380", "verdeform", "Bloomcraft Interiors, Inc."),
    ),
    "QuoteA0492_23.Pdf": ExpectedQuote(
        filename="QuoteA0492_23.Pdf",
        vendor_names=("Hollis Greenscapes",),
        customer_name="Lio Technologies, Inc.",
        vat_id="94-1985704",
        department_keywords=("Lio Technologies", "Vladimir Keil"),
        order_lines=(
            ExpectedOrderLine(
                description_keywords=("moss panel", "70:30"),
                amount=1.0,
                unit_prices=(1560.00,),
                total_price=1560.00,
            ),
            ExpectedOrderLine(
                description_keywords=("transport", "packing"),
                amount=1.0,
                unit_prices=(320.00,),
                total_price=320.00,
            ),
        ),
        # Items 1.1a ($2,090.00) and 1.1b ($1,830.00) are labeled
        # "Alternative to the preceding item" with Total = "U.P." and are excluded
        # from the $1,880.00 net total.
        forbidden_line_keywords=("ball moss only", "forest moss throughout"),
        net_total=1880.00,
        gross_total=2042.15,
        commodity_group_ids=(15,),
        commodity_group_names=("Office Equipment",),
        expected_text_snippets=("Quote A0492/23", "Hollis Greenscapes", "941985704"),
    ),
    "Quote_1__Lio_Technologies_Inc__1x_MBA___2214703918.pdf": ExpectedQuote(
        filename="Quote_1__Lio_Technologies_Inc__1x_MBA___2214703918.pdf",
        vendor_names=("Apple", "Apple Business Team", "Apple Inc."),
        customer_name="Lio Technologies, Inc.",
        vat_id="94-2404110",
        department_keywords=("Lio Technologies", "Lukas Heinzmann"),
        order_lines=(
            ExpectedOrderLine(
                description_keywords=("macbook air", "m2"),
                amount=1.0,
                unit_prices=(1409.06,),
                total_price=1409.06,
                unit_keywords=("piece", "pieces", "ea", "unit", "item"),
            ),
        ),
        forbidden_line_keywords=(),
        net_total=1409.06,
        gross_total=1534.59,
        # 29 = Hardware (original 50), 69 = Business Laptop (expanded taxonomy)
        commodity_group_ids=(29, 69),
        commodity_group_names=("Hardware", "Business Laptop"),
        expected_text_snippets=("2214703918", "Apple Business Team", "94-2404110", "MacBook Air"),
    ),
    "Quote_Hartwell_Cleveland_ACME_Grinding_Machine.pdf": ExpectedQuote(
        filename="Quote_Hartwell_Cleveland_ACME_Grinding_Machine.pdf",
        vendor_names=("Hartwell Industrial Tools, Inc.", "Hartwell Industrial Tools"),
        customer_name="ACME Corp",
        # No Tax ID / EIN is present anywhere in this quote
        vat_id=None,
        department_keywords=("Purchasing", "Engineering", "ACME"),
        order_lines=(
            ExpectedOrderLine(
                description_keywords=("grinding machine", "hw-gs 450"),
                amount=1.0,
                unit_prices=(15000.00,),
                total_price=15000.00,
                unit_keywords=("piece", "pieces", "ea"),
            ),
            ExpectedOrderLine(
                description_keywords=("delivery", "installation"),
                amount=1.0,
                unit_prices=(2000.00,),
                total_price=2000.00,
                unit_keywords=("lump sum", "service", "piece", "pieces", "item"),
            ),
        ),
        forbidden_line_keywords=(),
        net_total=17000.00,
        gross_total=18402.50,
        commodity_group_ids=(45,),
        commodity_group_names=("Production Machinery",),
        expected_text_snippets=(
            "Q-HW-2026-041",
            "Hartwell Industrial Tools, Inc.",
            "Grinding machine HW-GS 450",
        ),
    ),
}


# ---------------------------------------------------------------------------
# In-memory test database & FastAPI client setup
# ---------------------------------------------------------------------------
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_fks(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(engine)

with TestingSession() as _s:
    seed(_s)


def _override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _bind_test_db():
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if prev is not None:
            app.dependency_overrides[get_db] = prev


client = TestClient(app)


def _get_auth_headers() -> dict[str, str]:
    app.dependency_overrides[get_db] = _override_get_db
    r = client.post(
        "/auth/signin",
        json={"email": "admin@acme.com", "password": "demo1234"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _normalize_tax_id(val: str) -> str:
    return val.replace("-", "").replace(" ", "").strip()


# ---------------------------------------------------------------------------
# Comparison logic returning all discrepancies for a quote
# ---------------------------------------------------------------------------
def evaluate_extraction(expected: ExpectedQuote, response: ExtractionResponse) -> list[str]:
    """Compare an ``ExtractionResponse`` against ``ExpectedQuote``.

    Returns a list of human-readable mismatch strings (empty list = perfect match).
    """
    issues: list[str] = []

    if not response.success or response.data is None:
        issues.append(f"Extraction failed with error: {response.error!r}")
        return issues

    data = response.data
    missing = set(response.missing_fields or [])

    # 1. Title
    if not data.title or not data.title.strip():
        issues.append("Title is empty")

    # 2. Vendor Name (also detect vendor/customer swap)
    vendor_actual = data.vendor_name.strip()
    if vendor_actual.lower() == expected.customer_name.lower():
        issues.append(
            f"Vendor/Customer swapped: vendorName={vendor_actual!r} is actually the customer "
            f"(expected one of {expected.vendor_names})"
        )
    elif not any(v.lower() in vendor_actual.lower() for v in expected.vendor_names):
        issues.append(
            f"Vendor mismatch: got {vendor_actual!r}, expected one of {expected.vendor_names}"
        )

    # 3. Tax ID (vatId)
    vat_actual = (data.vat_id or "").strip()
    if expected.vat_id is None:
        if vat_actual:
            issues.append(f"Expected no vatId (None in PDF), but got {vat_actual!r}")
        if "Tax ID" not in missing:
            issues.append(
                f"Expected 'Tax ID' in missingFields when PDF has no Tax ID, got {response.missing_fields}"
            )
    else:
        if _normalize_tax_id(vat_actual) != _normalize_tax_id(expected.vat_id):
            issues.append(f"Tax ID mismatch: got {vat_actual!r}, expected {expected.vat_id!r}")

    # 4. Department / Customer (must not be the vendor's own name)
    dept_actual = (data.department or "").strip()
    if any(v.lower() in dept_actual.lower() for v in expected.vendor_names):
        issues.append(
            f"Department contains the vendor's name ({dept_actual!r}); "
            f"expected customer/department keywords {expected.department_keywords}"
        )

    # 5. Forbidden / Alternative order lines
    for line in data.order_lines:
        desc_lower = line.position_description.lower()
        for forbidden in expected.forbidden_line_keywords:
            if forbidden.lower() in desc_lower:
                issues.append(
                    f"Order lines include alternative/excluded item: {line.position_description!r} "
                    f"(matched forbidden keyword {forbidden!r})"
                )

    # 6. Expected Order Lines
    if len(data.order_lines) != len(expected.order_lines):
        issues.append(
            f"Order line count mismatch: got {len(data.order_lines)} lines "
            f"({[l.position_description for l in data.order_lines]}), "
            f"expected {len(expected.order_lines)}"
        )

    for idx, exp_line in enumerate(expected.order_lines, start=1):
        matching = [
            l
            for l in data.order_lines
            if all(kw.lower() in l.position_description.lower() for kw in exp_line.description_keywords)
        ]
        if not matching:
            issues.append(
                f"Missing expected order line #{idx} matching keywords {exp_line.description_keywords}"
            )
            continue

        actual_line = matching[0]
        if abs(actual_line.amount - exp_line.amount) > 1e-2:
            issues.append(
                f"Line {actual_line.position_description!r} amount mismatch: "
                f"got {actual_line.amount}, expected {exp_line.amount}"
            )
        if not any(abs(actual_line.unit_price - up) <= 0.05 for up in exp_line.unit_prices):
            issues.append(
                f"Line {actual_line.position_description!r} unitPrice mismatch: "
                f"got {actual_line.unit_price}, expected one of {exp_line.unit_prices}"
            )
        if abs(actual_line.total_price - exp_line.total_price) > 0.05:
            issues.append(
                f"Line {actual_line.position_description!r} totalPrice mismatch: "
                f"got {actual_line.total_price}, expected {exp_line.total_price}"
            )

    # 7. Total Cost
    if not (
        abs(data.total_cost - expected.gross_total) <= 0.05
        or abs(data.total_cost - expected.net_total) <= 0.05
    ):
        issues.append(
            f"totalCost mismatch: got {data.total_cost}, "
            f"expected gross {expected.gross_total} (or net {expected.net_total})"
        )

    # 8. Commodity Group
    if data.commodity_group_id not in expected.commodity_group_ids:
        issues.append(
            f"commodityGroupId mismatch: got {data.commodity_group_id} ({data.commodity_group_name!r}), "
            f"expected one of {expected.commodity_group_ids} ({expected.commodity_group_names})"
        )

    return issues


# ---------------------------------------------------------------------------
# Pytest test cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", list(EXPECTED_QUOTES.keys()))
def test_pdf_parse_quote_files(filename: str):
    """Verify ``POST /pdf/parse`` extracts text from each quote PDF."""
    headers = _get_auth_headers()
    pdf_path = QUOTES_DIR / filename
    assert pdf_path.is_file(), f"Missing quote file: {pdf_path}"

    expected = EXPECTED_QUOTES[filename]
    r = client.post(
        "/pdf/parse",
        files={"file": (filename, pdf_path.read_bytes(), "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    text = r.json()["text"]
    assert text.strip(), f"Empty text extracted from {filename}"

    for snippet in expected.expected_text_snippets:
        assert snippet in text, f"Expected snippet {snippet!r} not found in parsed text of {filename}"

    # If the quote has a Tax ID, check that PDF text parsing actually captured it
    if expected.vat_id is not None:
        norm_text = _normalize_tax_id(text)
        norm_vat = _normalize_tax_id(expected.vat_id)
        assert norm_vat in norm_text, (
            f"Tax ID {expected.vat_id!r} from {filename} was not captured by /pdf/parse "
            f"(e.g. embedded in a raster header/footer image)"
        )


@pytest.mark.skipif(
    not (settings.openai_api_key or os.environ.get("OPENAI_API_KEY")),
    reason="OPENAI_API_KEY is required for live LLM extraction tests",
)
@pytest.mark.parametrize("filename", list(EXPECTED_QUOTES.keys()))
def test_pdf_extraction_matches_ground_truth(filename: str, monkeypatch: pytest.MonkeyPatch):
    """End-to-end test: ``POST /pdf/parse`` -> ``POST /extraction`` compared with PDF ground truth."""
    if not settings.openai_api_key and os.environ.get("OPENAI_API_KEY"):
        monkeypatch.setattr(settings, "openai_api_key", os.environ["OPENAI_API_KEY"])

    headers = _get_auth_headers()
    pdf_path = QUOTES_DIR / filename
    expected = EXPECTED_QUOTES[filename]

    # Step 1: Parse PDF text via endpoint
    parse_resp = client.post(
        "/pdf/parse",
        files={"file": (filename, pdf_path.read_bytes(), "application/pdf")},
        headers=headers,
    )
    assert parse_resp.status_code == 200, parse_resp.text
    pdf_text = parse_resp.json()["text"]

    # Step 2: Run AI vendor extraction via endpoint
    ext_resp = client.post(
        "/extraction",
        json={"text": pdf_text},
        headers=headers,
    )
    assert ext_resp.status_code == 200, ext_resp.text
    parsed = ExtractionResponse.model_validate(ext_resp.json())

    # Step 3: Compare against PDF ground truth
    issues = evaluate_extraction(expected, parsed)
    assert not issues, (
        f"Extraction inconsistencies for {filename}:\n  - "
        + "\n  - ".join(issues)
        + f"\n\nActual payload:\n{ext_resp.text}"
    )


if __name__ == "__main__":
    if not settings.openai_api_key and os.environ.get("OPENAI_API_KEY"):
        settings.openai_api_key = os.environ["OPENAI_API_KEY"]

    headers = _get_auth_headers()
    print(f"Using quotes directory: {QUOTES_DIR}\n")

    total_issues = 0
    for fname, exp in EXPECTED_QUOTES.items():
        pdf_bytes = (QUOTES_DIR / fname).read_bytes()
        r_parse = client.post(
            "/pdf/parse",
            files={"file": (fname, pdf_bytes, "application/pdf")},
            headers=headers,
        )
        text = r_parse.json()["text"]
        r_ext = client.post("/extraction", json={"text": text}, headers=headers)
        resp_obj = ExtractionResponse.model_validate(r_ext.json())
        issues = evaluate_extraction(exp, resp_obj)

        status_label = "PASS" if not issues else f"FAIL ({len(issues)} issues)"
        print(f"=== {fname}: {status_label} ===")
        if issues:
            total_issues += len(issues)
            for issue in issues:
                print(f"  [!] {issue}")
        print()

    if total_issues:
        raise SystemExit(f"Finished with {total_issues} extraction discrepancy(ies).")
    print("ALL PDF EXTRACTION TESTS PASSED")

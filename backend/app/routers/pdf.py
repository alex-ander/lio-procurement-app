from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.core.deps import get_current_user
from app.schemas.extraction import PdfParseResponse
from app.services.pdf import extract_text

router = APIRouter(prefix="/pdf", tags=["pdf"])

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB, matches the upload UI's stated limit


@router.post("/parse", response_model=PdfParseResponse, dependencies=[Depends(get_current_user)])
async def parse_pdf(file: UploadFile) -> PdfParseResponse:
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Please upload a PDF file"
        )

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF exceeds the 10MB limit",
        )

    try:
        text = extract_text(pdf_bytes)
    except Exception:  # noqa: BLE001 — mirror the original catch-all
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Failed to parse PDF",
        )

    return PdfParseResponse(text=text)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.schemas.extraction import ExtractionRequest, ExtractionResponse
from app.services.extraction import extract_vendor_data

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post("", response_model=ExtractionResponse, response_model_by_alias=True,
             dependencies=[Depends(get_current_user)])
def extract(payload: ExtractionRequest, db: Session = Depends(get_db)) -> ExtractionResponse:
    """Extract structured vendor data from PDF text via OpenAI.

    Returns ``{success, data?, error?, missingFields?}`` — the same envelope the
    original server action produced (errors are part of the payload, not HTTP
    errors, so the UI can show partial-extraction warnings).
    """
    return extract_vendor_data(payload.text, db)

import base64
import io
import logging
import os
import struct
import zlib

from openai import OpenAI
from pypdf import PdfReader

from app.core.config import settings

logger = logging.getLogger(__name__)


def _encode_rgb_bands_to_png(
    raw: bytes,
    width: int,
    height: int,
    y_ranges: list[tuple[int, int]],
    step: int = 2,
) -> bytes:
    """Encode horizontal bands (header/footer) of a raw 24-bit RGB buffer into a PNG."""
    rows: list[bytes] = []
    stride = width * 3
    out_w = (width + step - 1) // step
    for y0, y1 in y_ranges:
        for y in range(max(0, y0), min(y1, height), step):
            row_start = y * stride
            row = bytearray([0])  # PNG filter type 0 (None)
            for x in range(0, width, step):
                px = row_start + x * 3
                row.extend(raw[px : px + 3])
            rows.append(bytes(row))

    out_h = len(rows)
    raw_data = b"".join(rows)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", crc)

    ihdr = struct.pack("!IIBBBBB", out_w, out_h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw_data, 6))
        + _chunk(b"IEND", b"")
    )


def _extract_stationery_image_text(reader: PdfReader) -> str:
    """Transcribe header/footer bands of full-page raster stationery images if present."""
    api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return ""

    seen_keys: set[str] = set()
    transcriptions: list[str] = []

    for page in reader.pages:
        resources = page.get("/Resources")
        if not resources:
            continue
        res_obj = resources.get_object()
        xobjects = res_obj.get("/XObject")
        if not xobjects:
            continue
        xobj_dict = xobjects.get_object()

        for key, ref in xobj_dict.items():
            if key in seen_keys:
                continue
            try:
                obj = ref.get_object()
                if obj.get("/Subtype") != "/Image":
                    continue
                width = int(obj.get("/Width") or 0)
                height = int(obj.get("/Height") or 0)
                # Only inspect full-page stationery background images
                if width < 1000 or height < 1000:
                    continue
                raw = obj.get_data()
                if len(raw) != width * height * 3:
                    continue

                seen_keys.add(key)
                # Crop top 20% (letterhead + return address) and bottom 12% (footer with EIN/bank)
                png_bytes = _encode_rgb_bands_to_png(
                    raw,
                    width,
                    height,
                    [(0, int(height * 0.20)), (int(height * 0.88), height)],
                    step=2,
                )
                b64 = base64.b64encode(png_bytes).decode("ascii")
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Transcribe all text visible in this document header "
                                        "and footer image verbatim (company name, address, CEO, "
                                        "EIN/Tax ID, bank details). Plain text only."
                                    ),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                                },
                            ],
                        }
                    ],
                    max_completion_tokens=400,
                    temperature=0,
                )
                content = (resp.choices[0].message.content or "").strip()
                if content:
                    transcriptions.append(content)
            except Exception:  # noqa: BLE001
                logger.debug("Skipping stationery image OCR for %s", key, exc_info=True)

    return "\n".join(transcriptions)


def extract_text(pdf_bytes: bytes) -> str:
    """Extract the text from a vendor-offer PDF.

    Uses layout mode so 2D spatial structure (return address vs recipient block,
    metadata columns, and line-item tables) is preserved, and transcribes
    embedded raster stationery headers/footers when present.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except Exception:  # noqa: BLE001
            text = page.extract_text() or ""
        pages.append(text)

    stationery_text = _extract_stationery_image_text(reader)
    if stationery_text:
        pages.append(stationery_text)

    return "\n".join(pages)

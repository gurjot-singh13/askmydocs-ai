import logging
from pathlib import Path

import fitz  # PyMuPDF

from models.schemas.parser import ExtractionResult, PageText

logger = logging.getLogger(__name__)


def extract_pdf_text(file_path: Path | str, document_id) -> ExtractionResult:
    """
    Extract text from every page of a PDF file using PyMuPDF (fitz).

    Args:
        file_path: Path to the PDF file on local disk.
        document_id: UUID of the Document row this file belongs to —
                      included in the result for traceability only.

    Returns:
        ExtractionResult containing per-page text, page count, and total
        character count.

    Raises:
        FileNotFoundError: if file_path does not point to an existing file.
        ValueError: if the file cannot be opened as a PDF (corrupt or
                    not actually a PDF despite its extension).
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        pdf = fitz.open(file_path)
    except Exception as exc:
        # fitz raises various exceptions (RuntimeError, ValueError) for
        # corrupt/invalid PDFs — normalize to ValueError for the caller
        raise ValueError(f"Could not open '{file_path.name}' as a PDF: {exc}") from exc

    try:
        pages: list[PageText] = []
        total_chars = 0

        for index, page in enumerate(pdf):
            # get_text("text") returns plain reading-order text for the page
            text = page.get_text("text")
            char_count = len(text)
            total_chars += char_count

            pages.append(
                PageText(
                    page_number=index + 1,  # 1-indexed for human-readable output
                    text=text,
                    char_count=char_count,
                )
            )

        page_count = pdf.page_count

    finally:
        pdf.close()

    logger.info(
        "Extracted %d pages (%d total chars) from %s",
        page_count,
        total_chars,
        file_path.name,
    )

    return ExtractionResult(
        document_id=document_id,
        file_type="pdf",
        page_count=page_count,
        total_char_count=total_chars,
        pages=pages,
    )

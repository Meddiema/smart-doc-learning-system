import os
import time
from pypdf import PdfReader
from database.documents_db import (
    save_document_to_turso,
    list_turso_documents,
    get_turso_document_pages,
    delete_turso_document,
    purge_expired_documents,
)

UPLOAD_DIR = os.path.join("data", "uploaded_docs")
SEVEN_DAYS_SECONDS = 7 * 24 * 60 * 60


def extract_pdf_pages(file_path: str) -> list[dict]:
    """Extract text from each page of a PDF file."""
    try:
        reader = PdfReader(file_path)
        if reader.is_encrypted:
            return [{
                "page_num": 1,
                "text": "⚠️ This PDF is password-protected/encrypted and cannot be read.",
            }]

        pages_data = []
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or "[No selectable text found on this page]"
            pages_data.append({
                "page_num": idx,
                "text": text.strip(),
            })
        return pages_data
    except Exception as e:
        return [{
            "page_num": 1,
            "text": f"⚠️ Error reading PDF: {str(e)}",
        }]


def save_uploaded_pdf(uploaded_file) -> str:
    """Save an uploaded PDF to UPLOAD_DIR, extract pages once, and persist to Turso (7-day TTL)."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = os.path.basename(uploaded_file.name)
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    pages = extract_pdf_pages(file_path)
    save_document_to_turso(filename=safe_name, pages=pages)
    return file_path


def cleanup_expired_pdfs(upload_dir: str = UPLOAD_DIR, max_age_seconds: int = SEVEN_DAYS_SECONDS) -> int:
    """Purge expired PDFs from Turso and remove local PDFs older than 7 days."""
    os.makedirs(upload_dir, exist_ok=True)
    expired_turso = purge_expired_documents()

    now = time.time()
    removed_local = 0

    # Remove local files that expired in Turso or exceed 7 days by mtime
    for fname in os.listdir(upload_dir):
        if not fname.lower().endswith(".pdf"):
            continue
        fpath = os.path.join(upload_dir, fname)
        try:
            if not os.path.isfile(fpath):
                continue
            age = now - os.path.getmtime(fpath)
            if fname in expired_turso or age > max_age_seconds:
                os.remove(fpath)
                removed_local += 1
        except Exception:
            pass

    return len(expired_turso) + removed_local


def list_saved_pdfs() -> list[str]:
    """Return a sorted list of active PDF filenames across Turso and local disk."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    cleanup_expired_pdfs()

    disk_pdfs = {f for f in os.listdir(UPLOAD_DIR) if f.lower().endswith(".pdf")}
    turso_pdfs = {doc["filename"] for doc in list_turso_documents() if doc.get("filename")}

    return sorted(disk_pdfs | turso_pdfs)


def get_pdf_pages(filename: str) -> list[dict]:
    """Load PDF pages from local disk if available, falling back to Turso after container reboots."""
    safe_name = os.path.basename(filename)
    local_path = os.path.join(UPLOAD_DIR, safe_name)

    if os.path.exists(local_path) and os.path.isfile(local_path):
        pages = extract_pdf_pages(local_path)
        # Backfill Turso if the local file existed without a Turso row
        if pages and not get_turso_document_pages(safe_name):
            save_document_to_turso(filename=safe_name, pages=pages)
        return pages

    turso_pages = get_turso_document_pages(safe_name)
    if turso_pages:
        return turso_pages

    return [{
        "page_num": 1,
        "text": "⚠️ PDF file is no longer on disk and has no cached pages in Turso. Re-upload to read.",
    }]


def delete_saved_pdf(filename: str, upload_dir: str = UPLOAD_DIR) -> bool:
    """Immediately delete a PDF from Turso and remove its local file if present."""
    safe_name = os.path.basename(filename)
    delete_turso_document(safe_name)

    fpath = os.path.join(upload_dir, safe_name)
    if os.path.exists(fpath) and os.path.isfile(fpath):
        try:
            os.remove(fpath)
            return True
        except Exception:
            return False
    return True
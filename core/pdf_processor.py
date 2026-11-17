import os
from pypdf import PdfReader

UPLOAD_DIR = os.path.join("data", "uploaded_docs")


def save_uploaded_pdf(uploaded_file) -> str:
    """Save an uploaded Streamlit file to data/uploaded_docs/ and return its path."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    # Use basename to prevent path traversal issues
    safe_name = os.path.basename(uploaded_file.name)
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path


def list_saved_pdfs() -> list[str]:
    """Return a sorted list of saved PDF filenames."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    return sorted([f for f in os.listdir(UPLOAD_DIR) if f.lower().endswith(".pdf")])


def extract_pdf_pages(file_path: str) -> list[dict]:
    """Extract text from each page of a PDF file."""
    try:
        reader = PdfReader(file_path)
        if reader.is_encrypted:
            return [{
                "page_num": 1,
                "text": "⚠️ This PDF is password-protected/encrypted and cannot be read."
            }]

        pages_data = []
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or "[No selectable text found on this page]"
            pages_data.append({
                "page_num": idx,
                "text": text.strip()
            })
        return pages_data
    except Exception as e:
        return [{
            "page_num": 1,
            "text": f"⚠️ Error reading PDF: {str(e)}"
        }]
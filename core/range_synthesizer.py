RANGE_SYNTHESIS_SYSTEM_PROMPT = """
You are a senior technical mentor helping an engineer or security practitioner make sense of a multi-page reading span.
Given extracted text from a page range (for example, pages 1 to 100), respond in three clear sections:

1. **Flow & Connecting Threads:** Trace how key concepts, components, or arguments link together across the page range—what builds on what, and how the narrative/technical flow moves from early pages to later pages.
2. **What It Actually Means:** Translate the core ideas and relationships into clear, practical meaning without repeating raw textbook filler.
3. **Industry Application:** Show how to apply these concepts in real-world software engineering, system/network administration, or application security work (include concrete workflows, design/review checks, or trade-offs).
"""


def _normalize_pages(pages_input) -> list[tuple[int, str]]:
    """Normalize a list/dict/tuple of pages into sorted (page_num, text) tuples."""
    normalized: list[tuple[int, str]] = []
    if isinstance(pages_input, dict):
        for k, v in pages_input.items():
            try:
                p_num = int(k)
            except (TypeError, ValueError):
                continue
            normalized.append((p_num, str(v or "")))
        normalized.sort(key=lambda item: item[0])
    elif isinstance(pages_input, (list, tuple)):
        for idx, item in enumerate(pages_input, start=1):
            if isinstance(item, dict):
                p_val = item.get("page", item.get("page_num", idx))
                txt_val = item.get("text", item.get("content", ""))
                try:
                    p_num = int(p_val)
                except (TypeError, ValueError):
                    p_num = idx
                normalized.append((p_num, str(txt_val or "")))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    p_num = int(item[0])
                except (TypeError, ValueError):
                    p_num = idx
                normalized.append((p_num, str(item[1] or "")))
            else:
                normalized.append((idx, str(item or "")))
    return normalized


def build_page_window_digest(
    pages_input,
    start_page: int,
    end_page: int,
    max_total_chars: int = 28000,
    per_page_cap: int = 900,
) -> dict:
    """Select pages in [start_page, end_page] and build a bounded prompt payload."""
    pages = _normalize_pages(pages_input)
    if not pages:
        return {
            "selected_count": 0,
            "sampled_count": 0,
            "actual_start": start_page,
            "actual_end": end_page,
            "digest_text": "",
        }

    lo = min(int(start_page), int(end_page))
    hi = max(int(start_page), int(end_page))
    in_range = [(p, t) for (p, t) in pages if lo <= p <= hi]

    if not in_range:
        return {
            "selected_count": 0,
            "sampled_count": 0,
            "actual_start": lo,
            "actual_end": hi,
            "digest_text": "",
        }

    selected_count = len(in_range)
    max_slices = 24
    if selected_count > max_slices:
        step = selected_count / max_slices
        sampled = [in_range[min(int(i * step), selected_count - 1)] for i in range(max_slices)]
        # Always ensure first and last pages in range are included
        if sampled[0] != in_range[0]:
            sampled[0] = in_range[0]
        if sampled[-1] != in_range[-1]:
            sampled[-1] = in_range[-1]
    else:
        sampled = in_range

    blocks = []
    used_chars = 0
    for p_num, text in sampled:
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            continue
        snippet = cleaned[:per_page_cap]
        if len(cleaned) > per_page_cap:
            snippet += " ..."
        chunk = f"[Page {p_num}]\n{snippet}\n"
        if used_chars + len(chunk) > max_total_chars:
            break
        blocks.append(chunk)
        used_chars += len(chunk)

    return {
        "selected_count": selected_count,
        "sampled_count": len(blocks),
        "actual_start": in_range[0][0],
        "actual_end": in_range[-1][0],
        "digest_text": "\n".join(blocks).strip(),
    }


def format_range_synthesis_markdown(
    doc_title: str,
    start_page: int,
    end_page: int,
    focus_topic: str,
    synthesis_body: str,
) -> str:
    """Format a multi-page synthesis note for display and cheat-sheet export."""
    clean_doc = (doc_title or "Uploaded Document").strip()
    focus_line = f"- **Focus Lens:** {focus_topic.strip()}\n" if (focus_topic or "").strip() else ""
    return (
        f"# 📚 Multi-Page Flow & Industry Synthesis: `{clean_doc}`\n"
        f"- **Page Range:** Pages {start_page}–{end_page}\n"
        f"{focus_line}\n"
        f"{(synthesis_body or '').strip()}"
    ).strip()
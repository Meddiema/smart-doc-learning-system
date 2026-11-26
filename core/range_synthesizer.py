import re
from collections import Counter

SINGLE_PASS_PUZZLE_PROMPT = """
You are a senior software engineering and cybersecurity mentor helping a learner put small technical puzzle pieces together across a multi-page span into one clear mental model.
You will receive ordered milestone excerpts from across the requested page range (for example, pages 1–100).

Respond in four concise, high-signal sections using ONLY ONE AI call:

1. **🧩 Puzzle-Piece Connection Map:** A Markdown table (`Page Span | Puzzle Piece / Concept | How It Connects Forward`) showing how earlier pages set up later pages.
2. **🔗 Putting the Pieces Together:** Explain how the separate mechanisms, rules, or steps connect into one unified system or workflow.
3. **💡 What It Actually Means:** Translate the combined ideas into clear, practical meaning without filler.
4. **🏭 Industry Work Application:** Give concrete ways to apply this in real engineering, system/network administration, or security work (workflows, checks, or trade-offs).
"""

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "will", "would", "could", "should", "into", "your",
    "you", "can", "all", "any", "not", "but", "use", "using", "used", "when",
    "what", "which", "who", "how", "why", "where", "then", "than", "also",
    "each", "more", "most", "some", "such", "only", "over", "after", "before",
    "between", "through", "about", "page", "pages", "section", "chapter", "note",
}


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


def build_single_call_range_digest(
    pages_input,
    start_page: int,
    end_page: int,
    focus_topic: str = "",
    max_total_chars: int = 24000,
    max_slices: int = 16,
) -> dict:
    """
    Build a compact, ordered multi-checkpoint digest across [start_page, end_page]
    so a SINGLE AI call can connect early, middle, and late pages in the span.
    """
    pages = _normalize_pages(pages_input)
    lo = min(int(start_page), int(end_page))
    hi = max(int(start_page), int(end_page))
    in_range = [
        (p, " ".join(str(t or "").split()))
        for (p, t) in pages
        if lo <= p <= hi and str(t or "").strip()
    ]

    if not in_range:
        return {
            "selected_count": 0,
            "included_count": 0,
            "actual_start": lo,
            "actual_end": hi,
            "digest_text": "",
            "top_terms": [],
        }

    # Extract top recurring technical terms across the selected range (0 API cost)
    focus_terms = {w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]{2,}", focus_topic or "")}
    word_counts = Counter()
    for _, clean_txt in in_range:
        for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]{3,}", clean_txt.lower()):
            if tok not in STOPWORDS:
                word_counts[tok] += 1
    top_terms = [w for w, _ in word_counts.most_common(10)]

    # Choose checkpoints evenly across the range, prioritizing pages matching focus_terms if given
    n = len(in_range)
    if n <= max_slices:
        chosen = in_range
    else:
        step = n / max_slices
        indices = sorted({min(int(i * step), n - 1) for i in range(max_slices)})
        indices[0] = 0
        indices[-1] = n - 1

        if focus_terms:
            scored = []
            for idx, (p_num, txt) in enumerate(in_range):
                hits = sum(1 for ft in focus_terms if ft in txt.lower())
                if hits > 0:
                    scored.append((hits, idx))
            scored.sort(reverse=True)
            for _, idx in scored[:4]:
                if idx not in indices and len(indices) < max_slices:
                    indices.append(idx)
            indices.sort()

        chosen = [in_range[i] for i in indices]

    per_slice_cap = max(550, min(1400, max_total_chars // max(1, len(chosen))))
    blocks = []
    used_chars = 0
    for p_num, clean_txt in chosen:
        snippet = clean_txt[:per_slice_cap]
        if len(clean_txt) > per_slice_cap:
            snippet += " ..."
        chunk = f"[Page {p_num}]\n{snippet}\n"
        if used_chars + len(chunk) > max_total_chars:
            break
        blocks.append(chunk)
        used_chars += len(chunk)

    return {
        "selected_count": n,
        "included_count": len(blocks),
        "actual_start": in_range[0][0],
        "actual_end": in_range[-1][0],
        "digest_text": "\n".join(blocks).strip(),
        "top_terms": top_terms,
    }


def format_range_synthesis_markdown(
    doc_title: str,
    start_page: int,
    end_page: int,
    focus_topic: str,
    synthesis_body: str,
    mode_label: str = "1 AI Call",
) -> str:
    """Format a 1-call multi-page synthesis note for display and cheat-sheet export."""
    clean_doc = (doc_title or "Uploaded Document").strip()
    focus_line = f"- **Focus / Anchor:** {focus_topic.strip()}\n" if (focus_topic or "").strip() else ""
    return (
        f"# 🧩 Multi-Page Puzzle & Industry Synthesis: `{clean_doc}`\n"
        f"- **Page Range:** Pages {start_page}–{end_page} *({mode_label})*\n"
        f"{focus_line}\n"
        f"{(synthesis_body or '').strip()}"
    ).strip()
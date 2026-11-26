BATCH_PUZZLE_EXTRACTION_PROMPT = """
You are a technical reading analyst extracting puzzle pieces from one sequential block of a technical manual.
Given a batch of consecutive pages (for example, pages 1–20), extract ONLY the concrete building blocks introduced or refined in this span.
Respond in 5–7 concise bullet points covering:
- **Core Mechanism / Rule:** What system behavior, protocol, attack vector, or architecture principle is established here.
- **Key Terms & Dependencies:** Any prerequisite concept from earlier pages that this section relies on, or new terms it introduces for later pages.
- **Practical Signal:** Specific command, header, configuration, or edge case mentioned in these pages.
Keep it dense, factual, and free of filler so a master synthesizer can connect this batch with adjacent batches.
"""

MASTER_PUZZLE_ASSEMBLY_PROMPT = """
You are a senior software engineering and cybersecurity mentor helping a learner put small technical puzzle pieces together across a large reading span (such as pages 1–100) into one clear mental model.
You will receive sequential Puzzle-Piece Ledgers extracted from consecutive page blocks across the selected range.

Respond in four structured sections:

1. **🧩 Puzzle-Piece Connection Map:** Present a concise Markdown table with columns `Page Block | Puzzle Piece Introduced | How It Connects to the Next Piece` showing the exact chain of dependencies from start to finish.
2. **🔗 The Big Picture (Putting the Pieces Together):** Explain in clear, connected prose how all those separate mechanisms fit together as one unified system or workflow—resolve any apparent contradictions and highlight cause-and-effect links across pages.
3. **💡 What It Actually Means in Practice:** Translate the combined concept into plain English without textbook jargon so the learner truly grasps *why* things are designed this way.
4. **🏭 Industry Work Application:** Show concrete ways to apply this combined knowledge in real engineering, system/network administration, or security testing work (include specific review checks, debugging workflows, or defensive/offensive trade-offs).
"""

RANGE_SYNTHESIS_SYSTEM_PROMPT = """
You are a senior technical mentor helping an engineer or security practitioner make sense of a multi-page reading span.
Given extracted text from a page range, respond in four clear sections:

1. **🧩 Puzzle-Piece Connection Map:** A concise Markdown table (`Pages | Puzzle Piece | How It Connects Forward`) tracing how early ideas unlock later ones.
2. **🔗 The Big Picture (Putting the Pieces Together):** Explain how the parts work together as one coherent system.
3. **💡 What It Actually Means in Practice:** Translate the core ideas into clear, practical meaning.
4. **🏭 Industry Work Application:** Show concrete workflows, review checks, or trade-offs for real-world engineering or security work.
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


def build_sequential_batches(
    pages_input,
    start_page: int,
    end_page: int,
    batch_size: int = 20,
    per_page_cap: int = 1100,
    max_batch_chars: int = 22000,
) -> dict:
    """Split [start_page, end_page] into consecutive non-skipping batches for Deep Multi-Pass synthesis."""
    pages = _normalize_pages(pages_input)
    lo = min(int(start_page), int(end_page))
    hi = max(int(start_page), int(end_page))
    in_range = [(p, t) for (p, t) in pages if lo <= p <= hi]

    if not in_range:
        return {
            "selected_count": 0,
            "actual_start": lo,
            "actual_end": hi,
            "batches": [],
        }

    batches = []
    for i in range(0, len(in_range), max(1, int(batch_size))):
        window = in_range[i : i + int(batch_size)]
        blocks = []
        used_chars = 0
        for p_num, text in window:
            cleaned = " ".join(str(text or "").split())
            if not cleaned:
                continue
            snippet = cleaned[:per_page_cap]
            if len(cleaned) > per_page_cap:
                snippet += " ..."
            chunk = f"[Page {p_num}]\n{snippet}\n"
            if used_chars + len(chunk) > max_batch_chars:
                break
            blocks.append(chunk)
            used_chars += len(chunk)

        if blocks:
            batches.append(
                {
                    "batch_index": len(batches) + 1,
                    "start_page": window[0][0],
                    "end_page": window[-1][0],
                    "page_count": len(window),
                    "digest_text": "\n".join(blocks).strip(),
                }
            )

    return {
        "selected_count": len(in_range),
        "actual_start": in_range[0][0],
        "actual_end": in_range[-1][0],
        "batches": batches,
    }


def build_page_window_digest(
    pages_input,
    start_page: int,
    end_page: int,
    max_total_chars: int = 28000,
    per_page_cap: int = 900,
) -> dict:
    """Select pages in [start_page, end_page] and build a fast sampled prompt payload."""
    pages = _normalize_pages(pages_input)
    lo = min(int(start_page), int(end_page))
    hi = max(int(start_page), int(end_page))
    if not pages:
        return {
            "selected_count": 0,
            "sampled_count": 0,
            "actual_start": lo,
            "actual_end": hi,
            "digest_text": "",
        }

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
    mode_label: str = "Deep Multi-Pass",
) -> str:
    """Format a multi-page synthesis note for display and cheat-sheet export."""
    clean_doc = (doc_title or "Uploaded Document").strip()
    focus_line = f"- **Focus / Anchor Question:** {focus_topic.strip()}\n" if (focus_topic or "").strip() else ""
    return (
        f"# 🧩 Multi-Page Puzzle & Industry Synthesis: `{clean_doc}`\n"
        f"- **Page Range:** Pages {start_page}–{end_page} ({mode_label})\n"
        f"{focus_line}\n"
        f"{(synthesis_body or '').strip()}"
    ).strip()
from typing import Any

from backend.app.schemas import Note, SourceDoc


def organize_evidence(notes: list[Note], sources: list[SourceDoc]) -> dict[str, Any]:
    """Deduplicate notes, assign citation numbers to unique sources from 1, and group by sub-question."""
    # 1. Build source index from unique URLs starting at 1
    source_index: dict[int, dict[str, str]] = {}
    url_to_source_num: dict[str, int] = {}
    current_source_num = 1

    # First add from sources list
    for src in sources:
        url = src.url.strip()
        if url and url not in url_to_source_num:
            url_to_source_num[url] = current_source_num
            source_index[current_source_num] = {
                "url": url,
                "title": src.title.strip() or url,
            }
            current_source_num += 1

    # Also capture sources from notes if not present in sources
    for n in notes:
        url = n.source_url.strip()
        if url and url not in url_to_source_num:
            url_to_source_num[url] = current_source_num
            source_index[current_source_num] = {
                "url": url,
                "title": n.source_title.strip() or url,
            }
            current_source_num += 1

    # 2. Deduplicate notes (same URL and identical/near-identical fact)
    seen_notes: set[tuple[str, str]] = set()
    numbered_notes: list[dict[str, Any]] = []
    current_note_num = 1

    for n in notes:
        norm_url = n.source_url.strip().lower()
        norm_fact = " ".join(n.fact.strip().lower().split()[:15])  # Compare first 15 words
        key = (norm_url, norm_fact)
        if key in seen_notes:
            continue
        seen_notes.add(key)

        src_num = url_to_source_num.get(n.source_url.strip(), 1)
        numbered_notes.append(
            {
                "note_number": current_note_num,
                "sub_question_id": n.sub_question_id,
                "fact": n.fact.strip(),
                "source_number": src_num,
                "source_url": n.source_url.strip(),
                "source_title": n.source_title.strip() or source_index.get(src_num, {}).get("title", ""),
                "snippet": n.snippet.strip(),
            }
        )
        current_note_num += 1

    # 3. Group notes by sub_question_id
    grouped_notes: dict[str, list[dict[str, Any]]] = {}
    for note_dict in numbered_notes:
        sq_id = note_dict["sub_question_id"]
        if sq_id not in grouped_notes:
            grouped_notes[sq_id] = []
        grouped_notes[sq_id].append(note_dict)

    return {
        "grouped_notes": grouped_notes,
        "source_index": source_index,
        "numbered_notes": numbered_notes,
    }

"""Select reading slices for discussion sessions."""
from __future__ import annotations
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..db import Section, Chunk


@dataclass
class SessionSlice:
    """A selected slice for a reading session."""
    section_ids: list[str]
    sections: list[dict]  # Section data
    total_tokens: int
    total_reading_time: int  # minutes
    chunk_ids: list[str]  # All chunk IDs in the slice
    context_text: str  # Combined text for context


def select_session_slice(
    db: Session,
    book_id: str,
    time_budget_min: int = 20,
    start_section_id: str | None = None,
    section_ids: list[str] | None = None,
) -> SessionSlice:
    """
    Select sections for a reading session based on time budget.

    Args:
        db: Database session
        book_id: Book ID
        time_budget_min: Target reading time in minutes
        start_section_id: Optional section to start from
        section_ids: Optional explicit list of section IDs

    Returns:
        SessionSlice with selected sections and context
    """
    if section_ids:
        # Use explicitly provided sections
        sections = (
            db.query(Section)
            .filter(Section.book_id == book_id, Section.id.in_(section_ids))
            .order_by(Section.order_index)
            .all()
        )
    else:
        # Auto-select based on time budget
        all_sections = (
            db.query(Section)
            .filter(Section.book_id == book_id)
            .order_by(Section.order_index)
            .all()
        )

        if not all_sections:
            raise ValueError(f"No sections found for book {book_id}")

        # Find starting point
        start_idx = 0
        if start_section_id:
            for i, s in enumerate(all_sections):
                if s.id == start_section_id:
                    start_idx = i
                    break

        # Select sections to fit time budget
        sections = []
        total_time = 0

        for section in all_sections[start_idx:]:
            reading_time = section.reading_time_min or 5
            if total_time + reading_time > time_budget_min and sections:
                break
            sections.append(section)
            total_time += reading_time

        # Ensure we have at least one section
        if not sections and all_sections:
            sections = [all_sections[start_idx]]

    # Get all chunks for selected sections
    section_ids_list = [s.id for s in sections]
    chunks = (
        db.query(Chunk)
        .filter(Chunk.section_id.in_(section_ids_list))
        .order_by(Chunk.char_start)
        .all()
    )

    # Build context text
    context_parts = []
    for section in sections:
        section_chunks = [c for c in chunks if c.section_id == section.id]
        if section.title:
            context_parts.append(f"## {section.title}\n")
        for chunk in section_chunks:
            context_parts.append(chunk.text)
        context_parts.append("\n\n")

    context_text = "\n".join(context_parts)

    return SessionSlice(
        section_ids=section_ids_list,
        sections=[
            {
                "id": s.id,
                "title": s.title,
                "section_type": s.section_type,
                "order_index": s.order_index,
                "token_estimate": s.token_estimate,
                "reading_time_min": s.reading_time_min,
                "page_start": s.page_start,
                "page_end": s.page_end,
            }
            for s in sections
        ],
        total_tokens=sum(s.token_estimate or 0 for s in sections),
        total_reading_time=sum(s.reading_time_min or 0 for s in sections),
        chunk_ids=[c.id for c in chunks],
        context_text=context_text,
    )

"""Helpers for translating between reading units and UI-facing sections."""

from __future__ import annotations

from ..db import ReadingUnit, Section


def overlap_length(
    start_a: int,
    end_a: int,
    start_b: int,
    end_b: int,
) -> int:
    """Return the overlapping character span between two half-open ranges."""
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def choose_section_for_unit(
    sections: list[Section],
    unit: ReadingUnit | None,
) -> Section | None:
    """Pick the section that best matches the current reading unit span."""
    if not unit or not sections:
        return None

    ranked = sorted(
        sections,
        key=lambda section: (
            overlap_length(section.char_start, section.char_end, unit.char_start, unit.char_end),
            -abs(section.char_start - unit.char_start),
        ),
        reverse=True,
    )
    best = ranked[0]
    if overlap_length(best.char_start, best.char_end, unit.char_start, unit.char_end) > 0:
        return best
    return min(sections, key=lambda section: abs(section.char_start - unit.char_start))


def choose_unit_for_section(
    units: list[ReadingUnit],
    section: Section,
) -> ReadingUnit | None:
    """Pick the reading unit that best maps onto a section span."""
    if not units:
        return None

    ranked = sorted(
        units,
        key=lambda unit: (
            overlap_length(unit.char_start, unit.char_end, section.char_start, section.char_end),
            -abs(unit.char_start - section.char_start),
        ),
        reverse=True,
    )
    best = ranked[0]
    if overlap_length(best.char_start, best.char_end, section.char_start, section.char_end) > 0:
        return best
    return min(units, key=lambda unit: abs(unit.char_start - section.char_start))

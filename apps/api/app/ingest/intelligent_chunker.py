"""
Intelligent Chunking System

Two-pass chunking for massive texts:
1. Structure analysis: LLM samples the text to understand divisions
2. Unit creation: Create reading units that respect narrative boundaries

Handles complex structures like:
- Infinite Jest (sections + endnotes)
- House of Leaves (nested narratives)
- Non-linear timelines
- Poetry collections
"""

import re
import random
from dataclasses import dataclass, field
from typing import AsyncIterator
from pydantic import BaseModel

from app.db.models import ReadingUnitType


# =============================================================================
# SCHEMAS FOR LLM STRUCTURED OUTPUT
# =============================================================================

class StructureDivision(BaseModel):
    """A detected division in the book structure."""
    title: str | None = None
    division_type: str  # chapter, section, part, scene, endnote_section, etc.
    marker_pattern: str | None = None  # Regex or description of how to find this division
    estimated_length: str  # short, medium, long
    starts_at_sample: int | None = None  # Which sample this was found in


class NarrativeThread(BaseModel):
    """A narrative thread for non-linear texts."""
    name: str  # "Hal Incandenza", "Don Gately", "The Entertainment"
    description: str
    identifiers: list[str]  # How to identify this thread in text


class BookStructure(BaseModel):
    """Complete structure analysis of a book."""
    book_type: str  # novel, short_stories, poetry, essay_collection, experimental
    has_chapters: bool
    has_parts: bool
    has_endnotes: bool
    has_footnotes: bool
    is_non_linear: bool
    estimated_complexity: str  # low, medium, high, extreme

    divisions: list[StructureDivision]
    narrative_threads: list[NarrativeThread] = []

    # For special structures
    endnote_style: str | None = None  # numbered, lettered, symbolic
    timeline_notes: str | None = None  # Notes about chronology


class ReadingUnitSpec(BaseModel):
    """Specification for a reading unit to be created."""
    title: str
    unit_type: str
    char_start: int
    char_end: int
    source_refs: list[str] = []
    narrative_thread: str | None = None
    chronological_position: int | None = None
    related_unit_indices: list[int] = []  # Indices of related units


# =============================================================================
# STRUCTURE ANALYZER
# =============================================================================

class StructureAnalyzer:
    """
    Analyzes book structure using LLM sampling.
    Works even for experimental texts without clear chapters.
    """

    def __init__(self, llm_client):
        self.llm = llm_client

    def _extract_samples(
        self,
        text: str,
        sample_size: int = 8000,
        count: int = 8
    ) -> list[tuple[int, str]]:
        """Extract representative samples from different parts of the text."""
        samples = []
        text_len = len(text)

        # Always include beginning and end
        samples.append((0, text[:sample_size]))
        samples.append((max(0, text_len - sample_size), text[-sample_size:]))

        # Middle
        mid_start = (text_len // 2) - (sample_size // 2)
        samples.append((mid_start, text[mid_start:mid_start + sample_size]))

        # Random samples from remaining positions
        remaining = count - 3
        for _ in range(remaining):
            start = random.randint(sample_size, text_len - sample_size * 2)
            samples.append((start, text[start:start + sample_size]))

        return samples

    async def analyze_structure(self, full_text: str) -> BookStructure:
        """
        Analyze the book's structure by sampling and using LLM.
        """
        samples = self._extract_samples(full_text)

        # Format samples for LLM
        samples_text = "\n\n".join([
            f"=== SAMPLE {i+1} (starts at char {pos}) ===\n{text[:2000]}..."
            for i, (pos, text) in enumerate(samples)
        ])

        prompt = f"""Analyze this book's structure from these samples.

{samples_text}

Identify:
1. Book type (novel, short_stories, poetry, essay_collection, experimental)
2. Division patterns:
   - Does it have chapters? Parts? Sections?
   - How are divisions marked? (e.g., "CHAPTER", "###", blank lines, numbered sections)
   - Are there endnotes or footnotes?

3. For experimental/complex texts:
   - Is the narrative non-linear?
   - Are there multiple narrative threads/POVs?
   - Is there a parallel structure (like Infinite Jest's endnotes)?

4. Complexity assessment:
   - low: Standard novel with clear chapters
   - medium: Some non-linearity or multiple POVs
   - high: Complex structure, endnotes, multiple timelines
   - extreme: Experimental (House of Leaves, Pale Fire, etc.)

Be specific about how to detect divisions programmatically.
For narrative threads, explain how to identify which thread a section belongs to.

Return your analysis as structured data."""

        # Use structured output if available, otherwise parse
        try:
            structure = await self.llm.complete_structured(
                [{"role": "user", "content": prompt}],
                schema=BookStructure
            )
        except AttributeError:
            # Fallback: regular completion + parsing
            response = await self.llm.complete(
                [{"role": "system", "content": "You are a literary structure analyst. Return JSON."},
                 {"role": "user", "content": prompt}]
            )
            structure = self._parse_structure_response(response, full_text)

        return structure

    def _parse_structure_response(self, response: str, full_text: str) -> BookStructure:
        """Fallback parser for LLM response."""
        # Try to extract JSON from response
        import json

        # Look for JSON block
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return BookStructure(**data)
            except (json.JSONDecodeError, ValueError):
                pass

        # Ultimate fallback: basic structure detection
        return self._detect_basic_structure(full_text)

    def _detect_basic_structure(self, text: str) -> BookStructure:
        """
        Fallback: detect structure using regex patterns.
        """
        divisions = []

        # Check for common chapter patterns
        chapter_patterns = [
            (r'CHAPTER\s+\d+', 'chapter'),
            (r'Chapter\s+\d+', 'chapter'),
            (r'PART\s+\w+', 'part'),
            (r'^#{1,3}\s+', 'section'),  # Markdown-style
            (r'^\d+\.\s+', 'section'),  # Numbered sections
            (r'\n{3,}', 'scene'),  # Multiple blank lines
        ]

        for pattern, div_type in chapter_patterns:
            matches = list(re.finditer(pattern, text, re.MULTILINE))
            if matches:
                divisions.append(StructureDivision(
                    division_type=div_type,
                    marker_pattern=pattern,
                    estimated_length="medium"
                ))

        # Check for endnotes
        has_endnotes = bool(re.search(r'(ENDNOTES?|NOTES?)\s*\n', text, re.IGNORECASE))
        has_footnotes = bool(re.search(r'\[\d+\]|\{\d+\}', text))

        return BookStructure(
            book_type="novel",
            has_chapters=any(d.division_type == "chapter" for d in divisions),
            has_parts=any(d.division_type == "part" for d in divisions),
            has_endnotes=has_endnotes,
            has_footnotes=has_footnotes,
            is_non_linear=False,
            estimated_complexity="low" if divisions else "medium",
            divisions=divisions
        )


# =============================================================================
# INTELLIGENT CHUNKER
# =============================================================================

class IntelligentChunker:
    """
    Creates reading units from book text using structure analysis.
    """

    # Target size for reading units (roughly 20-30 pages)
    DEFAULT_TARGET_TOKENS = 15000
    MIN_UNIT_TOKENS = 3000
    MAX_UNIT_TOKENS = 25000

    def __init__(self, llm_client, target_tokens: int = None):
        self.llm = llm_client
        self.target_tokens = target_tokens or self.DEFAULT_TARGET_TOKENS
        self.analyzer = StructureAnalyzer(llm_client)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token for English."""
        return len(text) // 4

    async def create_reading_units(
        self,
        full_text: str,
        structure: BookStructure | None = None
    ) -> list[ReadingUnitSpec]:
        """
        Create reading units from text, optionally using pre-analyzed structure.
        """
        if structure is None:
            structure = await self.analyzer.analyze_structure(full_text)

        # Route to appropriate handler based on complexity
        if structure.estimated_complexity == "extreme":
            return await self._handle_experimental(full_text, structure)
        elif structure.has_endnotes and structure.estimated_complexity == "high":
            return await self._handle_endnotes_structure(full_text, structure)
        elif structure.is_non_linear:
            return await self._handle_non_linear(full_text, structure)
        else:
            return await self._handle_standard(full_text, structure)

    async def _handle_standard(
        self,
        text: str,
        structure: BookStructure
    ) -> list[ReadingUnitSpec]:
        """Handle standard novels with chapters."""
        units = []

        # Find chapter divisions
        divisions = self._find_divisions(text, structure)

        if not divisions:
            # No clear divisions - create units by size
            return self._chunk_by_size(text)

        for i, (start, end, title, div_type) in enumerate(divisions):
            div_text = text[start:end]
            div_tokens = self._estimate_tokens(div_text)

            if div_tokens <= self.MAX_UNIT_TOKENS:
                # Fits as one unit
                units.append(ReadingUnitSpec(
                    title=title or f"{div_type.title()} {i+1}",
                    unit_type=div_type,
                    char_start=start,
                    char_end=end,
                    source_refs=self._extract_source_refs(div_text)
                ))
            else:
                # Need to split
                sub_units = await self._split_large_division(
                    div_text, start, div_type, title, i
                )
                units.extend(sub_units)

        return units

    async def _handle_endnotes_structure(
        self,
        text: str,
        structure: BookStructure
    ) -> list[ReadingUnitSpec]:
        """
        Handle texts with significant endnotes (like Infinite Jest).
        Creates two parallel tracks: main text and endnotes.
        """
        # Split main text and endnotes
        endnotes_match = re.search(
            r'(NOTES|ENDNOTES|Notes and References)\s*\n',
            text, re.IGNORECASE
        )

        if endnotes_match:
            main_text = text[:endnotes_match.start()]
            endnotes_text = text[endnotes_match.start():]
            endnotes_offset = endnotes_match.start()
        else:
            main_text = text
            endnotes_text = ""
            endnotes_offset = len(text)

        # Process main text
        main_units = await self._handle_standard(main_text, structure)

        # Process endnotes into batches
        if endnotes_text:
            endnote_units = self._chunk_endnotes(
                endnotes_text, endnotes_offset, structure
            )

            # Link endnote references
            for unit in main_units:
                unit_text = text[unit.char_start:unit.char_end]
                # Find endnote references like [1], [23], etc.
                refs = re.findall(r'\[(\d+)\]', unit_text)
                if refs:
                    unit.source_refs.append(f"See endnotes: {', '.join(refs[:5])}")

            main_units.extend(endnote_units)

        return main_units

    def _chunk_endnotes(
        self,
        endnotes_text: str,
        offset: int,
        structure: BookStructure
    ) -> list[ReadingUnitSpec]:
        """Chunk endnotes into readable batches."""
        units = []

        # Find individual endnotes
        pattern = r'(\d+)\.\s+'
        matches = list(re.finditer(pattern, endnotes_text))

        if not matches:
            # Just chunk by size
            for spec in self._chunk_by_size(endnotes_text, prefix="Endnotes"):
                spec.char_start += offset
                spec.char_end += offset
                spec.unit_type = "endnote_batch"
                units.append(spec)
            return units

        # Group endnotes into batches
        current_batch_start = 0
        current_batch_notes = []
        current_tokens = 0

        for i, match in enumerate(matches):
            note_start = match.start()
            note_end = matches[i + 1].start() if i + 1 < len(matches) else len(endnotes_text)
            note_text = endnotes_text[note_start:note_end]
            note_tokens = self._estimate_tokens(note_text)

            if current_tokens + note_tokens > self.target_tokens and current_batch_notes:
                # Create batch
                batch_end = note_start
                first_note = current_batch_notes[0]
                last_note = current_batch_notes[-1]

                units.append(ReadingUnitSpec(
                    title=f"Endnotes {first_note}-{last_note}",
                    unit_type="endnote_batch",
                    char_start=offset + current_batch_start,
                    char_end=offset + batch_end,
                    source_refs=[f"Notes {first_note}-{last_note}"]
                ))

                current_batch_start = note_start
                current_batch_notes = []
                current_tokens = 0

            current_batch_notes.append(match.group(1))
            current_tokens += note_tokens

        # Final batch
        if current_batch_notes:
            first_note = current_batch_notes[0]
            last_note = current_batch_notes[-1]
            units.append(ReadingUnitSpec(
                title=f"Endnotes {first_note}-{last_note}",
                unit_type="endnote_batch",
                char_start=offset + current_batch_start,
                char_end=offset + len(endnotes_text),
                source_refs=[f"Notes {first_note}-{last_note}"]
            ))

        return units

    async def _handle_non_linear(
        self,
        text: str,
        structure: BookStructure
    ) -> list[ReadingUnitSpec]:
        """Handle non-linear narratives with multiple threads."""
        # First, create units normally
        units = await self._handle_standard(text, structure)

        # Then, try to identify narrative threads and chronological order
        if structure.narrative_threads:
            units = await self._tag_narrative_threads(units, text, structure)

        return units

    async def _tag_narrative_threads(
        self,
        units: list[ReadingUnitSpec],
        text: str,
        structure: BookStructure
    ) -> list[ReadingUnitSpec]:
        """Tag units with their narrative thread."""
        thread_identifiers = {
            thread.name: thread.identifiers
            for thread in structure.narrative_threads
        }

        for unit in units:
            unit_text = text[unit.char_start:unit.char_end][:1000]  # Sample

            for thread_name, identifiers in thread_identifiers.items():
                for identifier in identifiers:
                    if identifier.lower() in unit_text.lower():
                        unit.narrative_thread = thread_name
                        break
                if unit.narrative_thread:
                    break

        return units

    async def _handle_experimental(
        self,
        text: str,
        structure: BookStructure
    ) -> list[ReadingUnitSpec]:
        """
        Handle experimental texts.
        Uses LLM more heavily to find sensible break points.
        """
        # For experimental texts, we ask the LLM to help identify breaks
        prompt = f"""This is an experimental/complex text. Help me identify sensible reading break points.

Text sample (first 5000 chars):
{text[:5000]}

The text is approximately {len(text)} characters ({self._estimate_tokens(text)} tokens).

I want to create reading units of roughly {self.target_tokens} tokens each.

Identify natural break points (scene changes, perspective shifts, typographic breaks, etc.)
that would make good stopping points for a reading session.

For each break point, provide:
1. An approximate character offset
2. Why this is a good break point
3. A suggested title for the unit ending here"""

        response = await self.llm.complete(
            [{"role": "user", "content": prompt}]
        )

        # Parse response and create units
        # For now, fall back to size-based chunking with smarter breaks
        return self._chunk_by_size_smart(text, response)

    def _find_divisions(
        self,
        text: str,
        structure: BookStructure
    ) -> list[tuple[int, int, str | None, str]]:
        """Find division boundaries in text."""
        divisions = []

        for div in structure.divisions:
            if not div.marker_pattern:
                continue

            try:
                matches = list(re.finditer(div.marker_pattern, text, re.MULTILINE))

                for i, match in enumerate(matches):
                    start = match.start()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

                    # Try to extract title
                    title_text = text[match.start():match.start() + 200]
                    title_match = re.search(r'[A-Za-z][\w\s]+', title_text)
                    title = title_match.group().strip()[:100] if title_match else None

                    divisions.append((start, end, title, div.division_type))

            except re.error:
                continue

        # Sort by start position
        divisions.sort(key=lambda x: x[0])

        # Merge overlapping divisions
        if divisions:
            merged = [divisions[0]]
            for div in divisions[1:]:
                if div[0] < merged[-1][1]:
                    # Overlapping - extend previous
                    merged[-1] = (merged[-1][0], max(merged[-1][1], div[1]),
                                  merged[-1][2], merged[-1][3])
                else:
                    merged.append(div)
            divisions = merged

        return divisions

    async def _split_large_division(
        self,
        text: str,
        offset: int,
        div_type: str,
        parent_title: str | None,
        parent_index: int
    ) -> list[ReadingUnitSpec]:
        """Split a too-large division at natural points."""
        units = []

        # Find scene breaks (multiple blank lines, "* * *", etc.)
        scene_breaks = list(re.finditer(r'\n{3,}|\*\s*\*\s*\*|—{3,}|_{3,}', text))

        if scene_breaks:
            # Use scene breaks
            current_start = 0
            part_num = 1

            for br in scene_breaks:
                chunk = text[current_start:br.end()]
                if self._estimate_tokens(chunk) >= self.MIN_UNIT_TOKENS:
                    units.append(ReadingUnitSpec(
                        title=f"{parent_title or f'{div_type.title()} {parent_index+1}'}, Part {part_num}",
                        unit_type="scene",
                        char_start=offset + current_start,
                        char_end=offset + br.end(),
                        source_refs=[]
                    ))
                    current_start = br.end()
                    part_num += 1

            # Remaining text
            if current_start < len(text):
                units.append(ReadingUnitSpec(
                    title=f"{parent_title or f'{div_type.title()} {parent_index+1}'}, Part {part_num}",
                    unit_type="scene",
                    char_start=offset + current_start,
                    char_end=offset + len(text),
                    source_refs=[]
                ))
        else:
            # No scene breaks - split by paragraph at target size
            return self._chunk_by_size(text, prefix=parent_title, offset=offset)

        return units

    def _chunk_by_size(
        self,
        text: str,
        prefix: str = "Section",
        offset: int = 0
    ) -> list[ReadingUnitSpec]:
        """Chunk text by target size, breaking at paragraph boundaries."""
        units = []
        current_start = 0
        unit_num = 1

        paragraphs = text.split('\n\n')
        current_chunk = ""

        for para in paragraphs:
            potential_chunk = current_chunk + '\n\n' + para if current_chunk else para

            if self._estimate_tokens(potential_chunk) > self.target_tokens and current_chunk:
                # Save current chunk
                chunk_end = current_start + len(current_chunk)
                units.append(ReadingUnitSpec(
                    title=f"{prefix} {unit_num}",
                    unit_type="section",
                    char_start=offset + current_start,
                    char_end=offset + chunk_end,
                    source_refs=[]
                ))

                current_start = chunk_end
                current_chunk = para
                unit_num += 1
            else:
                current_chunk = potential_chunk

        # Final chunk
        if current_chunk:
            units.append(ReadingUnitSpec(
                title=f"{prefix} {unit_num}",
                unit_type="section",
                char_start=offset + current_start,
                char_end=offset + len(text),
                source_refs=[]
            ))

        return units

    def _chunk_by_size_smart(
        self,
        text: str,
        llm_hints: str
    ) -> list[ReadingUnitSpec]:
        """
        Chunk by size but use LLM hints for better break points.
        """
        # Parse hints for suggested break points
        # For now, just use basic chunking
        return self._chunk_by_size(text)

    def _extract_source_refs(self, text: str) -> list[str]:
        """Extract page references or locations from text."""
        refs = []

        # Look for page numbers
        page_match = re.search(r'p(?:age)?\.?\s*(\d+)', text[:500], re.IGNORECASE)
        if page_match:
            refs.append(f"p. {page_match.group(1)}")

        return refs


# =============================================================================
# SPECIAL HANDLERS
# =============================================================================

class InfiniteJestHandler:
    """
    Special handling for Infinite Jest's unique structure.
    """

    YEAR_NAMES = [
        "Year of the Whopper",
        "Year of the Tucks Medicated Pad",
        "Year of the Trial-Size Dove Bar",
        "Year of the Perdue Wonderchicken",
        "Year of the Whisper-Quiet Maytag Dishmaster",
        "Year of the Yushityu 2007 Mimetic-Resolution-Cartridge-View-Motherboard-Easy-To-Install-Upgrade For Infernatron/InterLace TP Systems For Home, Office, Or Mobile",
        "Year of Dairy Products from the American Heartland",
        "Year of the Depend Adult Undergarment",
        "Year of Glad",
    ]

    def __init__(self, chunker: IntelligentChunker):
        self.chunker = chunker

    async def process(self, text: str) -> list[ReadingUnitSpec]:
        """Process Infinite Jest with special handling."""
        # Detect IJ-specific patterns
        structure = BookStructure(
            book_type="experimental",
            has_chapters=False,
            has_parts=False,
            has_endnotes=True,
            has_footnotes=True,
            is_non_linear=True,
            estimated_complexity="extreme",
            divisions=[],
            narrative_threads=[
                NarrativeThread(
                    name="Hal Incandenza",
                    description="Tennis prodigy at E.T.A.",
                    identifiers=["Hal", "E.T.A.", "Enfield", "Incandenza"]
                ),
                NarrativeThread(
                    name="Don Gately",
                    description="Recovering addict at Ennet House",
                    identifiers=["Gately", "Ennet House", "AA", "Demerol"]
                ),
                NarrativeThread(
                    name="The Entertainment",
                    description="The lethal film cartridge",
                    identifiers=["Entertainment", "samizdat", "cartridge", "Joelle"]
                ),
            ],
            endnote_style="numbered"
        )

        return await self.chunker.create_reading_units(text, structure)


# =============================================================================
# FACTORY
# =============================================================================

def get_chunker(llm_client, book_title: str = None) -> IntelligentChunker:
    """Get appropriate chunker for the book."""
    chunker = IntelligentChunker(llm_client)

    # Special handlers for known complex texts
    if book_title:
        title_lower = book_title.lower()
        if "infinite jest" in title_lower:
            return InfiniteJestHandler(chunker)

    return chunker

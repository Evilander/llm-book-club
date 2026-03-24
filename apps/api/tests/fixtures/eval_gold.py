"""Gold-standard test fixtures for retrieval and citation evaluation.

Provides a synthetic but realistic literary corpus with three sections,
15+ chunks of real-ish prose, ground-truth retrieval relevance judgments,
and citation test cases covering exact, normalized, fuzzy, and invalid quotes.

All data is structured via dataclasses -- no raw dicts floating around.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass
class GoldChunk:
    """A chunk of book text with stable IDs for testing."""
    id: str
    section_id: str
    order_index: int
    text: str
    char_start: int
    char_end: int

    @property
    def token_count(self) -> int:
        return len(self.text) // 4


@dataclass
class GoldSection:
    """A section (chapter) of the gold book."""
    id: str
    title: str
    section_type: str
    order_index: int
    char_start: int
    char_end: int
    chunks: list[GoldChunk] = field(default_factory=list)


@dataclass
class GoldBook:
    """The complete gold-standard book fixture."""
    id: str
    title: str
    author: str
    sections: list[GoldSection] = field(default_factory=list)

    @property
    def all_chunks(self) -> list[GoldChunk]:
        chunks = []
        for section in self.sections:
            chunks.extend(section.chunks)
        return chunks

    def chunk_by_id(self, chunk_id: str) -> GoldChunk | None:
        for chunk in self.all_chunks:
            if chunk.id == chunk_id:
                return chunk
        return None


# ---------------------------------------------------------------------------
# Retrieval ground truth
# ---------------------------------------------------------------------------

@dataclass
class RetrievalQuery:
    """A test query with known-relevant chunk IDs."""
    query: str
    relevant_chunk_ids: list[str]
    # Whether this query favors lexical (FTS) or semantic (vector) retrieval
    query_type: str = "mixed"  # "entity", "thematic", "mixed"
    description: str = ""


# ---------------------------------------------------------------------------
# Citation test cases
# ---------------------------------------------------------------------------

@dataclass
class CitationTestCase:
    """A single citation to be tested against the gold corpus."""
    chunk_id: str
    quote: str
    should_verify: bool
    expected_match_type: str | None = None  # "exact", "normalized", "fuzzy", None
    description: str = ""


# ---------------------------------------------------------------------------
# Build the gold corpus
# ---------------------------------------------------------------------------

# Stable IDs so tests can reference them deterministically
BOOK_ID = "gold-book-00000000-0000-0000-0000-000000000001"

SECTION_IDS = [
    "gold-sec-00000000-0000-0000-0000-000000000001",
    "gold-sec-00000000-0000-0000-0000-000000000002",
    "gold-sec-00000000-0000-0000-0000-000000000003",
]

# 18 chunks across 3 sections (6 per section)
CHUNK_IDS = [f"gold-chunk-{i:04d}" for i in range(1, 19)]


def build_gold_book() -> GoldBook:
    """Construct the gold-standard book with 3 sections and 18 chunks."""

    # --- Section 1: Chapter 1 - The Arrival ---
    s1_chunks = [
        GoldChunk(
            id=CHUNK_IDS[0],
            section_id=SECTION_IDS[0],
            order_index=0,
            text=(
                "The train pulled into Ashworth station just after midnight, "
                "its brakes screaming against the frozen rails. Eleanor Voss "
                "stepped onto the platform with nothing but a leather valise "
                "and the weight of three unanswered letters."
            ),
            char_start=0,
            char_end=230,
        ),
        GoldChunk(
            id=CHUNK_IDS[1],
            section_id=SECTION_IDS[0],
            order_index=1,
            text=(
                "The station master, a hunched figure named Briggs, watched her "
                "from behind fogged glass. He had not seen a visitor arrive this "
                "late since the war, and something about the way she held her "
                "shoulders told him she had not come to stay."
            ),
            char_start=230,
            char_end=460,
        ),
        GoldChunk(
            id=CHUNK_IDS[2],
            section_id=SECTION_IDS[0],
            order_index=2,
            text=(
                "Ashworth had been a prosperous mill town before the river "
                "changed course. Now the empty factories stood like broken "
                "teeth along the waterfront, their windows dark, their chimneys "
                "cold. The only industry left was silence."
            ),
            char_start=460,
            char_end=680,
        ),
        GoldChunk(
            id=CHUNK_IDS[3],
            section_id=SECTION_IDS[0],
            order_index=3,
            text=(
                "Eleanor walked the half-mile to the Blackwood Inn without "
                "seeing another soul. The cobblestones gleamed under a thin "
                "sheet of ice, and the gas lamps cast trembling circles of "
                "amber light that seemed to retreat as she approached."
            ),
            char_start=680,
            char_end=910,
        ),
        GoldChunk(
            id=CHUNK_IDS[4],
            section_id=SECTION_IDS[0],
            order_index=4,
            text=(
                "At the inn, a woman with silver hair and steady hands poured "
                "her a glass of whisky without being asked. 'You must be the "
                "one Doctor Harlan wrote about,' she said. 'I am Mrs. Calloway. "
                "Your room is at the top of the stairs.'"
            ),
            char_start=910,
            char_end=1140,
        ),
        GoldChunk(
            id=CHUNK_IDS[5],
            section_id=SECTION_IDS[0],
            order_index=5,
            text=(
                "The room was spare but clean: a narrow bed, a washstand, a "
                "writing desk positioned under the window. Through the glass "
                "Eleanor could see the dark outline of Ashworth Hill, where "
                "the old Voss estate crouched among the pines like a secret."
            ),
            char_start=1140,
            char_end=1370,
        ),
    ]

    section1 = GoldSection(
        id=SECTION_IDS[0],
        title="Chapter 1: The Arrival",
        section_type="chapter",
        order_index=0,
        char_start=0,
        char_end=1370,
        chunks=s1_chunks,
    )

    # --- Section 2: Chapter 2 - The Library ---
    s2_chunks = [
        GoldChunk(
            id=CHUNK_IDS[6],
            section_id=SECTION_IDS[1],
            order_index=0,
            text=(
                "The Voss library had been sealed for eleven years. When Eleanor "
                "broke the wax seal on the door the next morning, the air that "
                "rushed out carried the smell of old paper and lavender, as "
                "though the room had been holding its breath."
            ),
            char_start=1370,
            char_end=1600,
        ),
        GoldChunk(
            id=CHUNK_IDS[7],
            section_id=SECTION_IDS[1],
            order_index=1,
            text=(
                "Floor-to-ceiling shelves lined every wall, crammed with volumes "
                "in no discernible order. Theology beside botany, maritime law "
                "wedged between fairy tales. Her grandfather had been a collector "
                "without method, a magpie of the mind."
            ),
            char_start=1600,
            char_end=1840,
        ),
        GoldChunk(
            id=CHUNK_IDS[8],
            section_id=SECTION_IDS[1],
            order_index=2,
            text=(
                "It was on the third shelf from the floor, between a water-stained "
                "atlas and a book of Common Prayer, that Eleanor found the journal. "
                "The leather cover was cracked but the pages inside were intact, "
                "filled with her grandmother's careful copperplate."
            ),
            char_start=1840,
            char_end=2090,
        ),
        GoldChunk(
            id=CHUNK_IDS[9],
            section_id=SECTION_IDS[1],
            order_index=3,
            text=(
                "The first entry was dated March 14, 1923. 'Today I planted the "
                "roses along the east wall. R. says they will not survive the "
                "wind, but I have read that Rosa rugosa thrives in adversity. "
                "I intend to prove him wrong.'"
            ),
            char_start=2090,
            char_end=2330,
        ),
        GoldChunk(
            id=CHUNK_IDS[10],
            section_id=SECTION_IDS[1],
            order_index=4,
            text=(
                "As Eleanor turned the pages, the journal revealed a woman she "
                "had never known. Her grandmother had been a naturalist, a "
                "watercolorist, a reader of Darwin and Dickinson. She had "
                "catalogued every wildflower on Ashworth Hill."
            ),
            char_start=2330,
            char_end=2560,
        ),
        GoldChunk(
            id=CHUNK_IDS[11],
            section_id=SECTION_IDS[1],
            order_index=5,
            text=(
                "But interspersed among the botanical observations were darker "
                "entries. References to 'the arrangement' and 'what must not be "
                "spoken of.' Twice she mentioned a locked room on the third floor "
                "that Eleanor's grandfather forbade anyone from entering."
            ),
            char_start=2560,
            char_end=2800,
        ),
    ]

    section2 = GoldSection(
        id=SECTION_IDS[1],
        title="Chapter 2: The Library",
        section_type="chapter",
        order_index=1,
        char_start=1370,
        char_end=2800,
        chunks=s2_chunks,
    )

    # --- Section 3: Chapter 3 - The Storm ---
    s3_chunks = [
        GoldChunk(
            id=CHUNK_IDS[12],
            section_id=SECTION_IDS[2],
            order_index=0,
            text=(
                "The storm arrived on the third day, as Mrs. Calloway had "
                "predicted. Wind tore across the moor and hurled rain against "
                "the windows of the Blackwood Inn with the force of thrown gravel. "
                "The power failed at noon."
            ),
            char_start=2800,
            char_end=3020,
        ),
        GoldChunk(
            id=CHUNK_IDS[13],
            section_id=SECTION_IDS[2],
            order_index=1,
            text=(
                "Eleanor sat by candlelight reading the journal while the building "
                "groaned around her. Her grandmother's handwriting grew more urgent "
                "in the later entries, the loops tighter, the ink pressed deeper "
                "into the page."
            ),
            char_start=3020,
            char_end=3250,
        ),
        GoldChunk(
            id=CHUNK_IDS[14],
            section_id=SECTION_IDS[2],
            order_index=2,
            text=(
                "'September 3, 1931. I have found what he hid behind the plaster. "
                "God forgive me, I understand now why he kept it locked away. The "
                "portrait is not of a stranger. It is of the woman who drowned in "
                "the millpond in 1889.'"
            ),
            char_start=3250,
            char_end=3490,
        ),
        GoldChunk(
            id=CHUNK_IDS[15],
            section_id=SECTION_IDS[2],
            order_index=3,
            text=(
                "A crack of thunder shook the inn. Eleanor looked up from the "
                "journal and saw, through the rain-streaked window, a light "
                "burning in the upper storey of the Voss estate. No one had "
                "lived there in over a decade."
            ),
            char_start=3490,
            char_end=3700,
        ),
        GoldChunk(
            id=CHUNK_IDS[16],
            section_id=SECTION_IDS[2],
            order_index=4,
            text=(
                "She pulled on her coat and stepped into the storm. The wind "
                "was a living thing, pressing against her chest, tearing at her "
                "collar. Rain blinded her within seconds. She kept walking, one "
                "hand on the stone wall that lined the road to the hill."
            ),
            char_start=3700,
            char_end=3950,
        ),
        GoldChunk(
            id=CHUNK_IDS[17],
            section_id=SECTION_IDS[2],
            order_index=5,
            text=(
                "When she reached the estate, the front door stood open. Water "
                "pooled on the marble floor of the entrance hall. Above her, on "
                "the landing, she could hear footsteps -- slow, deliberate, "
                "impossible. The house, it seemed, had been waiting for her."
            ),
            char_start=3950,
            char_end=4200,
        ),
    ]

    section3 = GoldSection(
        id=SECTION_IDS[2],
        title="Chapter 3: The Storm",
        section_type="chapter",
        order_index=2,
        char_start=2800,
        char_end=4200,
        chunks=s3_chunks,
    )

    return GoldBook(
        id=BOOK_ID,
        title="The Voss Inheritance",
        author="Marguerite Hale",
        sections=[section1, section2, section3],
    )


# ---------------------------------------------------------------------------
# Retrieval ground truth queries
# ---------------------------------------------------------------------------

def build_retrieval_queries() -> list[RetrievalQuery]:
    """Return queries with known-relevant chunks for retrieval evaluation."""
    return [
        RetrievalQuery(
            query="Eleanor arrives at the train station",
            relevant_chunk_ids=[CHUNK_IDS[0], CHUNK_IDS[1]],
            query_type="mixed",
            description="Opening scene: arrival at Ashworth station",
        ),
        RetrievalQuery(
            query="the abandoned factories and economic decline of the town",
            relevant_chunk_ids=[CHUNK_IDS[2]],
            query_type="thematic",
            description="Town decay and industrial decline imagery",
        ),
        RetrievalQuery(
            query="Mrs. Calloway",
            relevant_chunk_ids=[CHUNK_IDS[4], CHUNK_IDS[12]],
            query_type="entity",
            description="Entity search: the innkeeper appears in ch1 and ch3",
        ),
        RetrievalQuery(
            query="the grandmother's journal and botanical observations",
            relevant_chunk_ids=[CHUNK_IDS[8], CHUNK_IDS[9], CHUNK_IDS[10]],
            query_type="thematic",
            description="Journal discovery and naturalist grandmother",
        ),
        RetrievalQuery(
            query="Briggs station master",
            relevant_chunk_ids=[CHUNK_IDS[1]],
            query_type="entity",
            description="Entity search: minor character name",
        ),
        RetrievalQuery(
            query="locked room on the third floor secret",
            relevant_chunk_ids=[CHUNK_IDS[11], CHUNK_IDS[14]],
            query_type="thematic",
            description="Gothic mystery: forbidden room and hidden portrait",
        ),
        RetrievalQuery(
            query="the storm and the light in the Voss estate",
            relevant_chunk_ids=[CHUNK_IDS[12], CHUNK_IDS[15], CHUNK_IDS[16]],
            query_type="mixed",
            description="Climactic storm scene and mysterious light",
        ),
        RetrievalQuery(
            query="Rosa rugosa roses east wall planting",
            relevant_chunk_ids=[CHUNK_IDS[9]],
            query_type="entity",
            description="Specific botanical reference from journal entry",
        ),
        RetrievalQuery(
            query="portrait of the woman who drowned in the millpond",
            relevant_chunk_ids=[CHUNK_IDS[14]],
            query_type="mixed",
            description="Key plot revelation: the hidden portrait",
        ),
        RetrievalQuery(
            query="footsteps in the empty house impossible sounds",
            relevant_chunk_ids=[CHUNK_IDS[17]],
            query_type="thematic",
            description="Gothic climax: ghostly presence in the estate",
        ),
    ]


# ---------------------------------------------------------------------------
# Citation test cases
# ---------------------------------------------------------------------------

def build_citation_test_cases() -> list[CitationTestCase]:
    """Return citation test cases for verification evaluation."""
    return [
        # --- Exact matches (verbatim substrings) ---
        CitationTestCase(
            chunk_id=CHUNK_IDS[0],
            quote="its brakes screaming against the frozen rails",
            should_verify=True,
            expected_match_type="exact",
            description="Exact verbatim substring from chunk 0",
        ),
        CitationTestCase(
            chunk_id=CHUNK_IDS[2],
            quote="The only industry left was silence.",
            should_verify=True,
            expected_match_type="exact",
            description="Exact match including sentence-final period",
        ),
        CitationTestCase(
            chunk_id=CHUNK_IDS[8],
            quote="filled with her grandmother's careful copperplate",
            should_verify=True,
            expected_match_type="exact",
            description="Exact substring from journal discovery chunk",
        ),
        CitationTestCase(
            chunk_id=CHUNK_IDS[14],
            quote="The portrait is not of a stranger.",
            should_verify=True,
            expected_match_type="exact",
            description="Exact match from the key revelation journal entry",
        ),
        CitationTestCase(
            chunk_id=CHUNK_IDS[17],
            quote="The house, it seemed, had been waiting for her.",
            should_verify=True,
            expected_match_type="exact",
            description="Exact match of the final sentence",
        ),

        # --- Normalized matches (case/whitespace differences) ---
        CitationTestCase(
            chunk_id=CHUNK_IDS[0],
            quote="ELEANOR VOSS STEPPED ONTO THE PLATFORM",
            should_verify=True,
            expected_match_type="normalized",
            description="All-uppercase version of exact substring",
        ),
        CitationTestCase(
            chunk_id=CHUNK_IDS[3],
            quote="the  cobblestones   gleamed  under  a  thin  sheet  of  ice",
            should_verify=True,
            expected_match_type="normalized",
            description="Extra whitespace but same words",
        ),
        CitationTestCase(
            chunk_id=CHUNK_IDS[7],
            quote="theology beside botany, maritime law wedged between fairy tales",
            should_verify=True,
            expected_match_type="normalized",
            description="Lowercase version of mixed-case original",
        ),
        CitationTestCase(
            chunk_id=CHUNK_IDS[15],
            quote="Eleanor  looked  up  from  the  journal",
            should_verify=True,
            expected_match_type="normalized",
            description="Double-spaced version of text",
        ),

        # --- Invalid: wrong chunk_id (quote exists but in different chunk) ---
        CitationTestCase(
            chunk_id=CHUNK_IDS[0],
            quote="The only industry left was silence.",
            should_verify=False,
            expected_match_type=None,
            description="Quote from chunk 2 cited against chunk 0",
        ),
        CitationTestCase(
            chunk_id=CHUNK_IDS[6],
            quote="its brakes screaming against the frozen rails",
            should_verify=False,
            expected_match_type=None,
            description="Quote from chunk 0 cited against chunk 6",
        ),

        # --- Invalid: completely fabricated quotes ---
        CitationTestCase(
            chunk_id=CHUNK_IDS[3],
            quote="The moonlight painted silver rivers across the desert sand.",
            should_verify=False,
            expected_match_type=None,
            description="Entirely hallucinated quote -- not in any chunk",
        ),
        CitationTestCase(
            chunk_id=CHUNK_IDS[10],
            quote="She had always loved the smell of fresh coffee in the morning.",
            should_verify=False,
            expected_match_type=None,
            description="Another fabricated quote with no textual basis",
        ),

        # --- Invalid: nonexistent chunk_id ---
        CitationTestCase(
            chunk_id="nonexistent-chunk-id-999",
            quote="some quoted text that will never match",
            should_verify=False,
            expected_match_type=None,
            description="Chunk ID does not exist in the corpus",
        ),
    ]


# ---------------------------------------------------------------------------
# Convenience: pre-built gold data singleton
# ---------------------------------------------------------------------------

GOLD_BOOK = build_gold_book()
GOLD_QUERIES = build_retrieval_queries()
GOLD_CITATIONS = build_citation_test_cases()

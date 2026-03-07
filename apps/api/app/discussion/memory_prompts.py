"""
Memory-Aware Agent Prompts

Enhanced prompts that integrate BookMemory for rich, contextual discussions.
Agents remember previous chapters, track themes, and make cross-textual connections.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class MemoryContext:
    """Context from BookMemory for agent prompts."""
    # Current position
    current_unit_title: str
    current_unit_index: int
    total_units: int

    # Reading progress
    units_completed: list[str]  # Titles of completed units
    reading_progress_pct: float

    # Tracked elements from previous reading
    key_moments: list[dict]  # {text, significance, unit_title, unit_index}
    tracked_themes: list[dict]  # {name, description, first_appearance, mentions}
    tracked_characters: list[dict]  # {name, description, first_appearance, arc_notes}
    user_notes: list[dict]  # {content, note_type, unit_title}

    # Connections discovered
    connections: list[dict]  # {source_description, target_description, relationship}

    # User progress
    quiz_performance: dict | None  # {avg_score, total_quizzes, strong_areas, weak_areas}
    xp_earned: int
    current_level: int

    # Narrative context for non-linear texts
    narrative_thread: str | None
    chronological_notes: str | None


# =============================================================================
# PERSONALITY GUIDELINES (from VISION.md)
# =============================================================================

PERSONALITY_CORE = """
PERSONALITY GUIDELINES:

Voice: Warm, conversational, genuinely enthusiastic. Like a brilliant friend who
happens to love books — not a professor, not a critic, a friend.

Approach:
- Talk like a real person, not an academic paper
- Get excited about good ideas — but show it, don't announce it
- Use humor naturally when the text invites it
- Admit when something is confusing or hard ("This passage is dense, let me help break it down")
- Meet readers where they are — never condescend, never show off
- Build on what the reader said earlier. Reference their specific insights by name.

Never do:
- Use academic jargon without explaining it in plain language
- Say "Great observation!" — instead, show WHY it's good by building on it
- Dismiss any reading as "wrong" — offer alternatives instead
- Over-explain when the reader clearly gets it
- Lecture or monologue. Keep it conversational.
- Be dry, stiff, or formal

Embrace:
- The reader's personal connections to the text
- Multiple valid readings of ambiguous moments
- Genuine puzzlement at difficult passages
- Humor — especially for heavy or challenging texts
- Building on previous insights from earlier readings
- Making intimidating books feel approachable
"""

# =============================================================================
# MEMORY-AWARE SYSTEM PROMPTS
# =============================================================================

def build_memory_context_block(memory: MemoryContext) -> str:
    """Build a context block from BookMemory for injection into prompts."""

    lines = []

    # Progress header
    lines.append(f"📖 READING PROGRESS: Unit {memory.current_unit_index + 1}/{memory.total_units}")
    lines.append(f"   Currently reading: \"{memory.current_unit_title}\"")
    lines.append(f"   Overall progress: {memory.reading_progress_pct:.0f}%")

    if memory.narrative_thread:
        lines.append(f"   Narrative thread: {memory.narrative_thread}")

    # Previous units summary
    if memory.units_completed:
        lines.append(f"\n📚 PREVIOUSLY READ ({len(memory.units_completed)} units):")
        for title in memory.units_completed[-5:]:  # Last 5 units
            lines.append(f"   • {title}")
        if len(memory.units_completed) > 5:
            lines.append(f"   ... and {len(memory.units_completed) - 5} earlier units")

    # Key moments from previous reading
    if memory.key_moments:
        lines.append(f"\n⭐ KEY MOMENTS TO REMEMBER ({len(memory.key_moments)} tracked):")
        for moment in memory.key_moments[-5:]:
            lines.append(f"   [{moment.get('unit_title', 'Earlier')}] \"{moment.get('text', '')[:100]}...\"")
            lines.append(f"      Significance: {moment.get('significance', 'Notable moment')}")

    # Tracked themes
    if memory.tracked_themes:
        lines.append(f"\n🎭 TRACKED THEMES ({len(memory.tracked_themes)}):")
        for theme in memory.tracked_themes[:5]:
            mentions = theme.get('mentions', 0)
            lines.append(f"   • {theme.get('name')}: {theme.get('description', '')} (seen {mentions}x)")

    # Tracked characters
    if memory.tracked_characters:
        lines.append(f"\n👤 CHARACTER NOTES ({len(memory.tracked_characters)}):")
        for char in memory.tracked_characters[:5]:
            lines.append(f"   • {char.get('name')}: {char.get('description', '')}")
            if char.get('arc_notes'):
                lines.append(f"      Arc: {char.get('arc_notes')}")

    # User's own notes and insights
    if memory.user_notes:
        lines.append(f"\n📝 USER'S OWN NOTES ({len(memory.user_notes)}):")
        for note in memory.user_notes[-3:]:
            note_type = note.get('note_type', 'note')
            lines.append(f"   [{note_type}] \"{note.get('content', '')[:150]}\"")

    # Discovered connections
    if memory.connections:
        lines.append(f"\n🔗 DISCOVERED CONNECTIONS ({len(memory.connections)}):")
        for conn in memory.connections[-3:]:
            lines.append(f"   • {conn.get('source_description')} ↔ {conn.get('target_description')}")
            lines.append(f"      ({conn.get('relationship')})")

    # Quiz performance
    if memory.quiz_performance:
        perf = memory.quiz_performance
        lines.append(f"\n📊 COMPREHENSION PROFILE:")
        lines.append(f"   Average quiz score: {perf.get('avg_score', 0):.0f}%")
        if perf.get('strong_areas'):
            lines.append(f"   Strong areas: {', '.join(perf.get('strong_areas', []))}")
        if perf.get('weak_areas'):
            lines.append(f"   Areas for review: {', '.join(perf.get('weak_areas', []))}")

    # Gamification context
    if memory.xp_earned > 0:
        lines.append(f"\n🎮 READER LEVEL: {memory.current_level} ({memory.xp_earned} XP)")

    return "\n".join(lines)


# =============================================================================
# AGENT-SPECIFIC PROMPTS WITH MEMORY
# =============================================================================

MEMORY_AWARE_FACILITATOR = """You are Sam — a warm, genuinely enthusiastic book club companion who REMEMBERS everything you've read together.

{personality}

{memory_context}

YOUR UNIQUE CAPABILITY: You remember everything from previous reading sessions. Use this to:
- Reference key moments from earlier chapters when relevant
- Draw connections between current and past content
- Build on themes the reader has been tracking
- Recall the reader's own insights and questions
- Acknowledge the reader's growing understanding

CURRENT READING SLICE:
{context}

DISCUSSION APPROACH:
Based on reading progress of {progress_pct:.0f}%:
{phase_guidance}

IMPORTANT: Respond with valid JSON: {{"analysis": "your text with [1] markers", "citations": [{{"marker": 1, "chunk_id": "id", "quote": "exact text"}}]}}
The "quote" MUST be an exact substring from the evidence passages. Do NOT paraphrase.

Remember: You're not just discussing this passage in isolation - you're helping the reader
build a coherent understanding of the whole work, informed by everything that came before."""


MEMORY_AWARE_CLOSE_READER = """You are Ellis — a detail-obsessed reader who notices the small things AND remembers patterns across the entire work.

{personality}

{memory_context}

YOUR UNIQUE CAPABILITY: You can connect textual details to patterns across the entire work.
When you notice something in this passage, check if it echoes or contrasts with:
- Similar moments from earlier chapters
- Tracked themes and their evolution
- Character behaviors and development
- The reader's own marked moments and insights

CURRENT READING SLICE:
{context}

CLOSE READING APPROACH:
1. Start with the specific - word choices, images, structure in THIS passage
2. Then zoom out - how does this connect to what came before?
3. Point to earlier moments when relevant: "Remember when...?" or "This echoes..."
4. Note when something contradicts or complicates earlier patterns

IMPORTANT: Respond with valid JSON: {{"analysis": "your text with [1] markers", "citations": [{{"marker": 1, "chunk_id": "id", "quote": "exact text"}}]}}
The "quote" MUST be an exact substring from the evidence passages. Do NOT paraphrase.

When referencing earlier content, be specific:
- "Back in {{unit_title}}, we saw..."
- "This connects to a key moment the reader marked..."
- "The {{theme_name}} theme appears again here, but notice how..."

Help the reader see how close attention to language reveals larger structures."""


MEMORY_AWARE_SKEPTIC = """You are Kit — a charming devil's advocate who challenges claims with EVIDENCE from across the text.

{personality}

{memory_context}

YOUR UNIQUE CAPABILITY: You can challenge interpretations by referencing the full context.
When someone makes a claim, you can ask:
- "But what about that earlier moment when...?"
- "How does this square with what we discussed in {{previous_unit}}?"
- "The reader marked something relevant earlier - does it support or complicate this?"

CURRENT READING SLICE:
{context}

SKEPTIC APPROACH:
1. Acknowledge what's valuable in the interpretation
2. Raise questions that arise from the full context (not just this passage)
3. Point to earlier evidence that complicates simple readings
4. Challenge with genuine curiosity, not gotcha energy

When pushing back, be specific with references:
- "I see your point, but remember when {{character}} did X in {{earlier_chapter}}?"
- "The reader noted {{user_note}} - does that change how we read this?"
- "We've been tracking {{theme}} - how does your reading account for its evolution?"

IMPORTANT: Respond with valid JSON: {{"analysis": "your text with [1] markers", "citations": [{{"marker": 1, "chunk_id": "id", "quote": "exact text"}}]}}
The "quote" MUST be an exact substring from the evidence passages. Do NOT paraphrase.

You're not trying to "win" - you're helping everyone develop more nuanced readings
that account for the whole text, not just convenient passages."""


MEMORY_AWARE_CONNECTOR = """You are a connector who finds patterns and relationships across the text.

{personality}

{memory_context}

YOUR UNIQUE CAPABILITY: Pattern recognition across the full work. You specialize in:
- Echoes and callbacks between distant passages
- Character parallels and foils
- Thematic development and transformation
- Structural patterns (repetition, inversion, mirroring)
- Foreshadowing and payoff
- How reader's earlier observations connect to current content

CURRENT READING SLICE:
{context}

CONNECTOR APPROACH:
1. Look for connections between this passage and earlier content
2. Note when tracked themes/characters appear in new contexts
3. Highlight moments that answer earlier questions or fulfill foreshadowing
4. Suggest new connections the reader might not have noticed

Frame connections clearly:
- "This moment connects to {{earlier_key_moment}} - notice how..."
- "The {{theme}} theme has evolved since we first saw it in {{unit}}..."
- "{{character}}'s action here mirrors/contrasts with what they did in..."
- "Remember the reader's question about X? This passage might answer it..."

IMPORTANT: Respond with valid JSON: {{"analysis": "your text with [1] markers", "citations": [{{"marker": 1, "chunk_id": "id", "quote": "exact text"}}]}}
The "quote" MUST be an exact substring from the evidence passages. Do NOT paraphrase.
When citing connections, include citations for both ends of the connection.

Your goal: Help the reader see the work as a unified whole, where distant moments
illuminate each other."""


# =============================================================================
# QUIZ AND TEACHING PROMPTS
# =============================================================================

QUIZ_GENERATOR = """You are creating a comprehension quiz to help a reader solidify their understanding.

{memory_context}

CURRENT READING SLICE (just completed):
{context}

QUIZ DESIGN PRINCIPLES:
1. Test comprehension, not gotcha details
2. Include questions at multiple levels:
   - Recall: What happened? Who said what?
   - Understanding: Why did this matter? What does it reveal?
   - Connection: How does this relate to earlier content?
   - Analysis: What patterns/themes does this develop?

3. For each question:
   - One clearly correct answer
   - Plausible distractors (not obviously wrong)
   - Reference the specific passage being tested

4. Based on reader's quiz history:
   {quiz_focus}

5. Include at least one question that connects to previous reading

Generate 3-5 questions. Format each as:
{{
  "question": "...",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct": "A",
  "explanation": "...",
  "difficulty": "recall|understanding|connection|analysis",
  "references_unit": "current|previous_unit_name"
}}"""


READING_SUMMARY_GENERATOR = """You are creating a progress summary for a reader finishing a reading unit.

{memory_context}

JUST COMPLETED:
{context}

Create a concise summary that:
1. Captures the key developments in this section
2. Identifies any new themes or significant moments worth tracking
3. Notes character developments or revelations
4. Highlights potential connections to earlier content
5. Poses 1-2 questions to carry into the next reading

Format:
## Summary of "{unit_title}"

### What Happened
[Brief narrative summary - 2-3 sentences]

### Key Moments Worth Remembering
[Bullet list of 2-4 significant moments with brief notes on why they matter]

### Themes & Patterns
[Any themes introduced or developed, patterns noticed]

### Character Notes
[Any significant character developments]

### Connections to Previous Reading
[Links to earlier content if relevant]

### Questions to Carry Forward
[1-2 questions raised by this section]

### XP Earned
[Suggest XP based on section length and complexity: 50-150 XP]"""


# =============================================================================
# QUIZ AREA CLASSIFICATION
# =============================================================================


def classify_quiz_areas(
    quiz_results: list,
    strong_threshold: float = 70.0,
    weak_threshold: float = 50.0,
    min_questions: int = 2,
) -> tuple[list[str], list[str]]:
    """
    Classify difficulty categories as strong or weak based on quiz answer data.

    Iterates over QuizResult ORM objects, inspects each question's difficulty
    category (the ``type`` or ``difficulty`` field) and correctness (the
    ``correct`` or ``was_correct`` field), then computes per-category accuracy.

    Args:
        quiz_results: List of QuizResult ORM objects. Each has a ``questions``
            JSON field containing dicts with at minimum a difficulty indicator
            (``type`` or ``difficulty``) and a correctness indicator (``correct``
            or ``was_correct``).
        strong_threshold: Accuracy percentage at or above which a category is
            considered strong. Default 70%.
        weak_threshold: Accuracy percentage strictly below which a category is
            considered weak. Default 50%.
        min_questions: Minimum number of questions in a category before it is
            classified. Categories with fewer questions are ignored. Default 2.

    Returns:
        A ``(strong_areas, weak_areas)`` tuple, each a sorted list of
        difficulty category strings (e.g. ``["recall", "understanding"]``).
        If there are no quiz results or no questions, both lists are empty.
    """
    # Aggregate correct/total counts per difficulty category.
    category_stats: dict[str, dict[str, int]] = {}

    for quiz_result in quiz_results:
        questions = getattr(quiz_result, "questions", None) or []
        for q in questions:
            if not isinstance(q, dict):
                continue

            # The ORM schema stores difficulty as "type"; the quiz_system
            # uses "difficulty".  Accept either key.
            category = q.get("type") or q.get("difficulty") or "unknown"
            category = str(category).lower().strip()
            if not category or category == "unknown":
                continue

            # Correctness: the ORM uses "correct"; quiz_system uses
            # "was_correct".  Accept either.
            was_correct = q.get("correct", q.get("was_correct", False))

            if category not in category_stats:
                category_stats[category] = {"correct": 0, "total": 0}

            category_stats[category]["total"] += 1
            if was_correct:
                category_stats[category]["correct"] += 1

    strong_areas: list[str] = []
    weak_areas: list[str] = []

    for category, stats in sorted(category_stats.items()):
        if stats["total"] < min_questions:
            continue
        accuracy = stats["correct"] / stats["total"] * 100
        if accuracy >= strong_threshold:
            strong_areas.append(category)
        elif accuracy < weak_threshold:
            weak_areas.append(category)

    return strong_areas, weak_areas


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_memory_aware_prompt(
    agent_type: str,
    mode: str,
    context: str,
    memory: MemoryContext | None = None,
) -> str:
    """
    Get a memory-aware prompt for an agent.

    If memory is None, falls back to standard prompts.
    """
    if memory is None:
        # Import and use standard prompts
        from .prompts import get_agent_prompt
        return get_agent_prompt(agent_type, mode, context)

    memory_block = build_memory_context_block(memory)
    progress_pct = memory.reading_progress_pct

    # Compute phase guidance for facilitator template
    if progress_pct < 25:
        phase_guidance = "- Early reading: Focus on establishing themes, characters, key moments. Ask what's grabbing their attention."
    elif progress_pct < 75:
        phase_guidance = "- Mid-reading: Connect current content to earlier moments. Ask about evolving understanding of themes/characters."
    else:
        phase_guidance = "- Late reading: Synthesize across the full text. Ask about how early observations have paid off or shifted."

    prompts = {
        "facilitator": MEMORY_AWARE_FACILITATOR,
        "close_reader": MEMORY_AWARE_CLOSE_READER,
        "skeptic": MEMORY_AWARE_SKEPTIC,
        "connector": MEMORY_AWARE_CONNECTOR,
    }

    template = prompts.get(agent_type, MEMORY_AWARE_FACILITATOR)

    return template.format(
        personality=PERSONALITY_CORE,
        memory_context=memory_block,
        context=context,
        progress_pct=progress_pct,
        phase_guidance=phase_guidance,
    )


def build_memory_from_db(
    book_memory,  # BookMemory ORM object
    current_unit,  # ReadingUnit ORM object
    total_units: int,
) -> MemoryContext:
    """
    Build a MemoryContext from database objects.

    This is a helper to convert ORM objects to the MemoryContext dataclass.
    """
    # Extract key moments
    key_moments = []
    for moment in (book_memory.key_moments or []):
        key_moments.append({
            "text": moment.quote,
            "significance": moment.significance,
            "unit_title": f"Unit {moment.reading_unit_id}" if moment.reading_unit_id else "Unknown",
            "unit_index": 0,  # reading_unit_id is a plain FK, no relationship to resolve order_index
        })

    # Extract themes
    tracked_themes = []
    for theme in (book_memory.themes or []):
        tracked_themes.append({
            "name": theme.name,
            "description": theme.description,
            "first_appearance": theme.first_seen_unit_id,
            "mentions": len(theme.evidence) if theme.evidence else 0,
        })

    # Extract characters
    tracked_characters = []
    for char in (book_memory.characters or []):
        tracked_characters.append({
            "name": char.name,
            "description": char.description,
            "first_appearance": char.first_appearance_unit_id,
            "arc_notes": char.arc_notes,
        })

    # Extract user notes
    user_notes = []
    for note in (book_memory.user_notes or []):
        user_notes.append({
            "content": note.content,
            "note_type": note.note_type.value if note.note_type else "note",
            "unit_title": f"Unit {note.reading_unit_id}" if note.reading_unit_id else "Unknown",
        })

    # Extract connections
    connections = []
    for conn in (book_memory.connections or []):
        connections.append({
            "source_description": conn.from_quote or f"Unit {conn.from_unit_id}",
            "target_description": conn.to_quote or f"Unit {conn.to_unit_id}",
            "relationship": conn.connection_type,
        })

    # Calculate quiz performance
    quiz_performance = None
    quiz_results = book_memory.quiz_results or []
    if quiz_results:
        scores = [q.score * 100 for q in quiz_results if q.score is not None]
        if scores:
            quiz_performance = {
                "avg_score": sum(scores) / len(scores),
                "total_quizzes": len(quiz_results),
                "strong_areas": classify_quiz_areas(quiz_results)[0],
                "weak_areas": classify_quiz_areas(quiz_results)[1],
            }

    # Calculate level from XP
    xp = book_memory.xp_earned or 0
    level = 1 + (xp // 500)  # Level up every 500 XP

    # Get completed unit titles
    completed_ids = set(book_memory.units_completed or [])
    # We'd need to query these - for now just use count
    units_completed_titles = [f"Unit {i+1}" for i in range(len(completed_ids))]

    return MemoryContext(
        current_unit_title=current_unit.title if current_unit else "Unknown",
        current_unit_index=current_unit.order_index if current_unit else 0,
        total_units=total_units,
        units_completed=units_completed_titles,
        reading_progress_pct=(len(completed_ids) / total_units * 100) if total_units > 0 else 0,
        key_moments=key_moments,
        tracked_themes=tracked_themes,
        tracked_characters=tracked_characters,
        user_notes=user_notes,
        connections=connections,
        quiz_performance=quiz_performance,
        xp_earned=xp,
        current_level=level,
        narrative_thread=current_unit.narrative_thread if current_unit else None,
        chronological_notes=None,
    )

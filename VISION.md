# LLM Book Club - Product Vision

## Core Promise

**A reading companion that remembers, connects, teaches, and makes reading deeply engaging.**

Not just Q&A over text. A system that:
- Grows its understanding as you progress through chapters
- Makes connections you might miss ("Remember when X happened in Chapter 2? This mirrors...")
- Teaches actively - quizzes, comprehension checks, discussion prompts
- Gamifies the journey - streaks, achievements, mastery levels
- Feels modern, clean, and genuinely fun to use

---

## The Reading Journey

```
┌─────────────────────────────────────────────────────────────────────┐
│  CHAPTER 1          CHAPTER 2          CHAPTER 3         ...        │
│  ━━━━━━━━━          ━━━━━━━━━          ━━━━━━━━━                     │
│                                                                      │
│  [Read] ──► [Discuss] ──► [Quiz] ──► [Notes saved]                  │
│                │                          │                          │
│                ▼                          ▼                          │
│         ┌──────────────────────────────────────┐                    │
│         │         BOOK MEMORY                   │                    │
│         │  • Key moments                        │                    │
│         │  • Character arcs                     │                    │
│         │  • Themes emerging                    │                    │
│         │  • Your insights                      │                    │
│         │  • Quiz scores                        │                    │
│         └──────────────────────────────────────┘                    │
│                          │                                           │
│                          ▼                                           │
│              [Agents reference memory]                               │
│              "In Chapter 1, you noted that..."                       │
│              "This connects to the theme we identified..."           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Feature Categories

### 1. Progressive Memory System

The LLM remembers everything as you read:

| Memory Type | What's Stored | How It's Used |
|-------------|---------------|---------------|
| **Chapter Summaries** | AI-generated + user-approved summaries | "Last chapter, we saw X happen..." |
| **Key Moments** | Pivotal scenes, quotes, revelations | "Remember when the author said..." |
| **Character Sheets** | Who they are, relationships, arc | "Notice how Y has changed since Ch.2" |
| **Theme Tracker** | Emerging themes with evidence | "The isolation theme appears again here" |
| **User Notes** | Highlights, annotations, reactions | "You highlighted this passage..." |
| **Comprehension Log** | Quiz results, discussion depth | Adapts difficulty to your level |

**Agent Prompt Injection:**
```
## Book Memory (Chapters 1-5 completed)

### Key Moments You've Discussed
- Ch.1: The opening metaphor of the locked door (you found this significant)
- Ch.3: First appearance of the antagonist
- Ch.4: The betrayal scene (quiz score: 90%)

### Themes We've Identified Together
1. Isolation vs. Connection (strong in Ch.1, 3, 5)
2. The unreliable narrator (you caught this in Ch.2!)

### Your Notes
- "I think the author is setting up a twist" (Ch.2)
- "This reminds me of Kafka" (Ch.4)

## Current Chapter: 6
[Retrieved passages here]
```

---

### 2. Deep Comprehension Features

**Connections Engine:**
- Automatic detection: "This scene parallels Chapter 2's opening"
- Thematic threading: "The water imagery returns - third time now"
- Foreshadowing alerts: "Remember X? Here's the payoff"

**Teaching Modes:**
| Mode | Description |
|------|-------------|
| **Guided** | Agent leads discussion with prompts |
| **Socratic** | Questions that push you to think deeper |
| **Quiz** | Multiple choice, short answer, quote identification |
| **Explain** | "Explain this passage in your own words" with feedback |
| **Debate** | Take a position, Skeptic agent challenges you |

**Comprehension Checks:**
- After each chapter: "Quick check - who is X and why did they do Y?"
- Adaptive: Easy questions if struggling, harder if cruising
- Not punitive - "Let's revisit that section together"

---

### 3. Gamification System

**Progress & Streaks:**
```
┌────────────────────────────────────────┐
│  📖 "The Great Gatsby"                 │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│  ████████████░░░░░░░░  Chapter 5/9     │
│                                        │
│  🔥 7-day reading streak               │
│  ⭐ 2,450 XP this book                 │
│  🎯 Comprehension: 87%                 │
└────────────────────────────────────────┘
```

**XP Sources:**
| Action | XP | Notes |
|--------|-----|-------|
| Complete chapter discussion | 100 | Base reward |
| Quiz: Perfect score | 50 | Bonus |
| Find a connection yourself | 30 | "I noticed X relates to Y" |
| Add a note/highlight | 10 | Engagement |
| Daily reading | 25 | Streak bonus multiplier |
| Deep dive discussion | 75 | Extended analysis |

**Achievements:**
- 🏆 **First Insight** - Made your first cross-chapter connection
- 📚 **Bookworm** - 7-day reading streak
- 🔍 **Close Reader** - Scored 100% on 5 quizzes
- 🎭 **Theme Hunter** - Identified all major themes
- 💬 **Socratic Scholar** - Completed 10 Socratic sessions
- 🌟 **Completionist** - Finished a book with 90%+ comprehension

**Levels:**
```
Novice Reader → Active Reader → Engaged Reader →
Deep Reader → Scholar → Literary Critic
```

**Leaderboards (optional/social):**
- Weekly reading minutes
- Quiz accuracy
- Books completed
- Insights shared

---

### 4. UI Vision

**Design Principles:**
- Dark mode first (easy on eyes for reading)
- Minimal chrome, maximum content
- Smooth animations (not flashy, satisfying)
- Progress always visible but not distracting
- Mobile-first, desktop-enhanced

**Key Screens:**

**Library View:**
```
┌─────────────────────────────────────────────────────────┐
│  LLM Book Club                      🔥 12 day streak   │
│                                     ⭐ Level 7          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Currently Reading                                      │
│  ┌─────────┐  ┌─────────┐                              │
│  │ ▓▓▓▓▓░░ │  │ ▓▓░░░░░ │                              │
│  │  68%    │  │  23%    │                              │
│  │ Gatsby  │  │ 1984    │                              │
│  └─────────┘  └─────────┘                              │
│                                                         │
│  + Add Book                                             │
│                                                         │
│  ─────────────────────────────────────────────────      │
│  Recent Activity                                        │
│  • Completed Ch.4 of Gatsby (+100 XP)                  │
│  • 🏆 Achievement: Theme Hunter                         │
│  • Quiz score: 95% on Chapter 3                        │
└─────────────────────────────────────────────────────────┘
```

**Reading/Discussion View:**
```
┌────────────────────────────────────────┬───────────────┐
│  Chapter 5: The Party                  │  Book Memory  │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │               │
│                                        │  Themes:      │
│  ┌─────────────────────────────────┐   │  • Wealth     │
│  │  Facilitator                    │   │  • Illusion   │
│  │                                 │   │               │
│  │  "This party scene is pivotal.  │   │  Characters:  │
│  │  Notice how Gatsby watches      │   │  • Nick ━━━━  │
│  │  from across the room - this    │   │  • Gatsby ━━  │
│  │  mirrors the green light        │   │  • Daisy ━━━  │
│  │  imagery from Chapter 1."       │   │               │
│  │                                 │   │  Your Notes:  │
│  │  [cite: ch5_p3, "He stretched   │   │  📝 3 notes   │
│  │  out his arms..."]              │   │               │
│  └─────────────────────────────────┘   │  ───────────  │
│                                        │               │
│  ┌─────────────────────────────────┐   │  Quick Quiz   │
│  │  You: I think Gatsby seems      │   │  [Start →]    │
│  │  nervous here, not confident    │   │               │
│  └─────────────────────────────────┘   │  Connections  │
│                                        │  [View →]     │
│  [Type your response...]          📤   │               │
├────────────────────────────────────────┴───────────────┤
│  [💬 Discuss] [📝 Quiz] [🔍 Deep Dive] [⏭️ Next Ch.]   │
└────────────────────────────────────────────────────────┘
```

**Quiz View:**
```
┌─────────────────────────────────────────────────────────┐
│  Chapter 5 Quiz                          Question 3/5   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                         │
│  Who does Gatsby ask to arrange the meeting with Daisy? │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  A) Tom Buchanan                                │    │
│  └─────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────┐    │
│  │  B) Jordan Baker                                │    │
│  └─────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────┐    │
│  │  C) Nick Carraway                         ✓     │ ◄──│
│  └─────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────┐    │
│  │  D) Meyer Wolfsheim                             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│                                        [Check Answer →] │
└─────────────────────────────────────────────────────────┘
```

**Achievement Popup:**
```
        ┌─────────────────────────────┐
        │                             │
        │      🏆 Achievement!        │
        │                             │
        │      THEME HUNTER           │
        │                             │
        │   Identified all major      │
        │   themes in the book        │
        │                             │
        │        +150 XP              │
        │                             │
        │      [ Awesome! ]           │
        └─────────────────────────────┘
```

---

---

## Handling Massive Texts (Infinite Jest Problem)

### The Challenge

| Book | Words | Est. Tokens | Chapters | Notes |
|------|-------|-------------|----------|-------|
| Normal novel | 80k | ~100k | 20-30 | Easy |
| War and Peace | 580k | ~750k | 365 | Large |
| **Infinite Jest** | 545k | ~700k | 192 sections + 388 endnotes | Brutal |
| In Search of Lost Time | 1.2M | ~1.5M | 7 volumes | Extreme |

A single context window can't hold Infinite Jest. We need **intelligent segmentation**.

### Strategy: LLM-Assisted Chunking

Instead of dumb page/character chunking, we let the LLM analyze structure:

```python
class IntelligentChunker:
    """
    Two-pass chunking for massive texts.
    Pass 1: Structure analysis (what are the natural divisions?)
    Pass 2: Chunk within divisions
    """

    async def analyze_structure(self, full_text: str) -> BookStructure:
        """
        Sample the text to understand its structure.
        Works even for experimental texts without clear chapters.
        """
        # Sample: first 10k chars, middle 10k, last 10k, random 5 samples
        samples = self._extract_samples(full_text, sample_size=10000, count=8)

        prompt = """
        Analyze this book's structure from these samples.

        For each natural division point you identify, note:
        - Type: chapter, section, part, scene break, temporal shift, POV change
        - Markers: How to detect it (e.g., "###", "CHAPTER", blank lines, date headers)
        - Approximate length: short (1-5 pages), medium (5-20), long (20+)

        Some books have unconventional structures:
        - Infinite Jest: numbered sections + endnotes (treat endnotes as parallel track)
        - House of Leaves: multiple narratives, footnotes within footnotes
        - Pale Fire: poem + commentary (two reading tracks)

        Return a structure analysis.
        """

        structure = await self.llm.complete_structured(
            samples + prompt,
            schema=BookStructure
        )
        return structure

    async def create_reading_units(
        self,
        full_text: str,
        structure: BookStructure,
        target_unit_tokens: int = 15000  # ~20 pages, fits in context with room for discussion
    ) -> list[ReadingUnit]:
        """
        Create logical reading units based on structure.
        Units respect natural boundaries but stay under token budget.
        """
        units = []

        for division in structure.divisions:
            division_text = self._extract_division(full_text, division)
            division_tokens = self._count_tokens(division_text)

            if division_tokens <= target_unit_tokens:
                # Fits as one unit
                units.append(ReadingUnit(
                    title=division.title or f"Section {len(units)+1}",
                    text=division_text,
                    type=division.type,
                    estimated_reading_min=division_tokens // 250
                ))
            else:
                # Need to split - find sub-boundaries
                sub_units = await self._split_large_division(
                    division_text,
                    division.type,
                    target_unit_tokens
                )
                units.extend(sub_units)

        return units

    async def _split_large_division(
        self,
        text: str,
        division_type: str,
        target_tokens: int
    ) -> list[ReadingUnit]:
        """
        Split a too-large division at natural points.
        Uses LLM to find scene breaks, topic shifts, etc.
        """
        prompt = f"""
        This {division_type} is too long for a single reading session.
        Find natural break points (scene changes, time jumps, topic shifts).

        Text sample (first 5000 chars):
        {text[:5000]}

        Identify 3-5 potential split points with their character offsets.
        """
        # LLM identifies natural breaks, we split there
        ...
```

### Infinite Jest Specific Handling

```python
class InfiniteJestHandler:
    """
    Special handling for IJ's unique structure:
    - Main text (numbered sections, non-chronological)
    - Endnotes (388 of them, some are mini-chapters)
    - Year naming system (Year of the Depend Adult Undergarment, etc.)
    """

    def parse_structure(self, text: str) -> IJStructure:
        return IJStructure(
            main_sections=self._find_main_sections(text),  # Look for section breaks
            endnotes=self._extract_endnotes(text),  # Numbered endnotes
            timeline=self._build_chronology(),  # Map to actual years
            character_appearances={},  # Track who appears where
        )

    def create_reading_order(
        self,
        structure: IJStructure,
        mode: str = "default"
    ) -> list[ReadingUnit]:
        """
        Multiple reading order options:
        - default: As written (sections + endnotes when referenced)
        - chronological: Reordered by in-world timeline
        - character-focused: Follow one character's arc
        - first-timer: Simplified path for accessibility
        """
        if mode == "default":
            return self._default_order(structure)
        elif mode == "chronological":
            return self._chronological_order(structure)
        # etc.

    def get_endnote_context(self, endnote_num: int) -> str:
        """
        When user reaches an endnote reference, provide:
        - The endnote content
        - Why it matters
        - Connection to main text
        """
        ...
```

### Reading Unit Model

```python
class ReadingUnit(BaseModel):
    """
    A digestible chunk for one reading/discussion session.
    Replaces simple "chapter" concept.
    """
    id: str
    book_id: str
    order_index: int

    # Identity
    title: str  # "Section 14" or "The Eschaton Game" or "Endnotes 110-134"
    unit_type: str  # chapter, section, endnote_batch, scene, part

    # Boundaries
    char_start: int
    char_end: int
    source_refs: list[str]  # ["pp. 321-358", "endnotes 110-134"]

    # Metadata
    estimated_tokens: int
    estimated_reading_min: int
    characters_present: list[str]
    themes_touched: list[str]
    chronological_position: int | None  # Where this falls in timeline

    # For complex structures
    related_units: list[str]  # IDs of connected units (endnotes, parallel scenes)
    prerequisite_units: list[str]  # Must read these first for context

    # Progress
    status: str  # unread, in_progress, completed
    comprehension_score: float | None
```

### Adaptive Session Sizing

```python
class SessionPlanner:
    """
    Plan reading sessions based on user's pace and available time.
    """

    async def plan_session(
        self,
        book_memory: BookMemory,
        available_time_min: int,
        energy_level: str = "normal"  # low, normal, high
    ) -> SessionPlan:
        """
        User says "I have 30 minutes" - we plan accordingly.
        """
        # Estimate reading speed from history
        words_per_min = book_memory.avg_reading_speed or 250

        # Adjust for energy/complexity
        if energy_level == "low":
            words_per_min *= 0.7
        if book_memory.book.complexity == "high":  # IJ, Ulysses, etc.
            words_per_min *= 0.6

        target_words = available_time_min * words_per_min * 0.7  # Leave time for discussion

        # Find next reading units that fit
        units = self._select_units_for_budget(
            book_memory.next_unread_units,
            target_words
        )

        return SessionPlan(
            units=units,
            estimated_reading_min=int(sum(u.estimated_reading_min for u in units)),
            discussion_prompts=await self._generate_prompts(units),
            quiz_available=len(units) >= 1
        )
```

### UI for Complex Structures

```
┌────────────────────────────────────────────────────────────────┐
│  Infinite Jest                                    📖 Progress  │
│                                                                │
│  ┌─ Main Text ──────────────────────────────────────────────┐ │
│  │ ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  Section 28   │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌─ Endnotes ───────────────────────────────────────────────┐ │
│  │ █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  Note 78/388  │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  📍 Currently: "The Eschaton Game"                             │
│  ⏱️ ~45 min read | 🎯 3 endnotes to check                      │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  💡 Connection Alert                                     │ │
│  │                                                          │ │
│  │  This section references "The Entertainment" -           │ │
│  │  you first encountered this in Section 3.                │ │
│  │  [Review Section 3 notes →]                              │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  [▶️ Start Reading]  [📋 Reading Map]  [👥 Characters]         │
└────────────────────────────────────────────────────────────────┘

┌─ Reading Map View ──────────────────────────────────────────────┐
│                                                                  │
│  Timeline (chronological, not reading order):                    │
│                                                                  │
│  Y.D.A.U.  ━━●━━━━━━━━━●━━━━━━━━━━━●━━━━━━━━●━━━━━━━━━━━►       │
│              │          │           │         │                  │
│           Sec 3      Sec 28      Sec 14    Sec 45               │
│           (read)     (current)   (read)    (unread)             │
│                                                                  │
│  Narrative threads:                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Hal Incandenza  │  │ Don Gately      │  │ The Entertainment│  │
│  │ ████████░░░░░░  │  │ ████░░░░░░░░░░  │  │ ██░░░░░░░░░░░░  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### The Greatest Book Club Partner

The agents should feel like that one friend who:
- Actually read the book (has perfect recall)
- Makes you feel smart when you notice things
- Pushes you just enough without being insufferable
- Gets genuinely excited about connections
- Remembers YOUR observations and builds on them

**Personality injection:**
```python
FACILITATOR_PERSONALITY = """
You are the best book club partner anyone could ask for.

Your style:
- Genuinely enthusiastic, not performatively so
- You get excited when the user catches something subtle
- You remember everything they've said and reference it naturally
- You push them to think deeper, but never condescendingly
- You admit when something is confusing ("IJ is HARD, and that's ok")
- You make connections they might miss, but give them credit when they're close
- You use humor when appropriate (especially for heavy texts)

What you NEVER do:
- Lecture or monologue
- Make them feel dumb for missing something
- Spoil future plot points
- Be dry or academic
- Forget what they said earlier

Example response:
"Oh WOW okay so you caught the 'annular fusion' thing - that's going to matter
SO much later. And remember how you said the Eschaton game felt like a
metaphor for something bigger? Hold onto that thought. How are you feeling
about Hal at this point? I'm curious if your read on him has changed since
Chapter 2 when you said he seemed 'hollow.'"
"""
```

---

## Technical Implementation

### New Data Models

```python
# Book-level persistent memory
class BookMemory(Base):
    id: str
    book_id: str
    user_id: str  # When auth is added

    # Progress
    current_chapter: int
    chapters_completed: list[int]
    total_reading_time_min: int

    # Comprehension
    chapter_summaries: dict[int, str]  # {chapter_num: summary}
    key_moments: list[KeyMoment]
    themes: list[Theme]
    characters: list[Character]

    # Gamification
    xp_total: int
    xp_by_chapter: dict[int, int]
    achievements: list[str]
    quiz_scores: dict[int, float]  # {chapter: score}
    streak_days: int
    last_activity: datetime

class KeyMoment(BaseModel):
    chapter: int
    description: str
    quote: str
    chunk_id: str
    significance: str  # Why it matters
    connections: list[str]  # IDs of related moments

class Theme(BaseModel):
    name: str
    description: str
    evidence: list[ThemeEvidence]  # Passages that support it
    strength: float  # How prominent (0-1)

class Character(BaseModel):
    name: str
    first_appearance: int  # Chapter
    description: str
    relationships: dict[str, str]  # {other_char: relationship}
    arc_notes: list[str]  # How they change

class UserNote(Base):
    id: str
    book_memory_id: str
    chapter: int
    chunk_id: str
    content: str
    note_type: str  # highlight, note, question, insight
    created_at: datetime

class QuizResult(Base):
    id: str
    book_memory_id: str
    chapter: int
    questions: list[dict]
    answers: list[dict]
    score: float
    xp_earned: int
    created_at: datetime
```

### New Endpoints

```
POST   /v1/books/{id}/memory              Create/get book memory
GET    /v1/books/{id}/memory              Get current memory state
PATCH  /v1/books/{id}/memory              Update memory (add note, etc.)

POST   /v1/books/{id}/chapters/{ch}/complete   Mark chapter done, generate summary
GET    /v1/books/{id}/chapters/{ch}/quiz       Generate quiz questions
POST   /v1/books/{id}/chapters/{ch}/quiz       Submit quiz answers

GET    /v1/books/{id}/connections          Get cross-chapter connections
GET    /v1/books/{id}/themes               Get theme analysis

GET    /v1/user/stats                      XP, streaks, achievements
GET    /v1/user/achievements               All achievements + progress
POST   /v1/user/activity                   Log reading activity (for streaks)
```

### Agent Enhancements

```python
class MemoryAwareAgent(BaseAgent):
    """Agent that has access to book memory."""

    def __init__(self, ..., book_memory: BookMemory):
        self.memory = book_memory

    def build_context(self, current_chapter: int) -> str:
        """Build rich context from memory."""
        return f"""
## Your Reading Journey So Far

Chapters completed: {self.memory.chapters_completed}
Current chapter: {current_chapter}

## Key Moments We've Discussed
{self._format_key_moments()}

## Themes You've Identified
{self._format_themes()}

## Characters
{self._format_characters()}

## Your Notes & Insights
{self._format_user_notes()}

## Comprehension Profile
Quiz average: {self._avg_quiz_score()}%
Areas of strength: {self._strengths()}
Could revisit: {self._weak_areas()}
"""

class ConnectionsAgent:
    """Specialized agent for finding cross-chapter connections."""

    async def find_connections(
        self,
        current_passage: str,
        book_memory: BookMemory
    ) -> list[Connection]:
        # Search previous chapters for related moments
        # Return connections with explanations
        pass

class QuizGenerator:
    """Generate adaptive quizzes from chapter content."""

    async def generate_quiz(
        self,
        chapter_chunks: list[Chunk],
        difficulty: str,  # easy, medium, hard
        question_types: list[str],  # multiple_choice, short_answer, quote_id
        count: int = 5
    ) -> list[QuizQuestion]:
        pass
```

---

## Implementation Phases

### Phase 1: Memory Foundation (Current Sprint)
- [ ] BookMemory model + persistence
- [ ] Chapter completion flow with summary generation
- [ ] Key moment extraction (automatic + user-tagged)
- [ ] Memory injection into agent prompts
- [ ] Basic "previously in this book" references

### Phase 2: Active Learning
- [ ] Quiz generation from chapter content
- [ ] Quiz UI with scoring
- [ ] Adaptive difficulty based on performance
- [ ] "Explain this passage" with feedback
- [ ] Comprehension tracking

### Phase 3: Connections & Deep Analysis
- [ ] Cross-chapter connection detection
- [ ] Theme tracking with evidence
- [ ] Character arc visualization
- [ ] "Deep dive" discussion mode
- [ ] Foreshadowing/callback highlighting

### Phase 4: Gamification
- [ ] XP system with actions
- [ ] Achievement definitions + unlock logic
- [ ] Streak tracking
- [ ] Progress visualizations
- [ ] Achievement popups/celebrations

### Phase 5: UI Polish
- [ ] Dark mode design system
- [ ] Smooth transitions/animations
- [ ] Mobile-responsive layouts
- [ ] Progress rings/bars
- [ ] Reading statistics dashboard
- [ ] Social features (optional)

---

## Success Metrics

| Metric | Target | Why |
|--------|--------|-----|
| Session length | >15 min avg | Users are engaged |
| Return rate | >60% next day | Habit forming |
| Book completion | >40% | Actually finishing books |
| Quiz accuracy | Improves over time | Learning happening |
| Notes per chapter | >2 avg | Active reading |
| NPS | >50 | Would recommend |

---

## The North Star

**A user finishes a book and thinks:**

*"I actually understood that. The quizzes helped me catch things I missed.
The connections the AI made blew my mind. I have notes I'll actually
revisit. And honestly? It was fun. I want to read another one."*

---

*Vision doc created: 2025-12-20*

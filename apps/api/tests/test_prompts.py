"""Tests for prompt generation, agent prompt construction, and memory-aware prompts.

Covers:
  - DISCUSSION_PROMPTS config structure
  - AGENT_PROMPTS security requirements
  - get_agent_prompt / get_facilitator_prompt (documents known format bugs)
  - get_memory_aware_prompt with and without memory context
  - Security firewall presence in all agent prompts
  - build_memory_context_block
"""
import pytest

from app.discussion.prompts import (
    DISCUSSION_PROMPTS,
    AGENT_PROMPTS,
    CITATION_FORMAT_INSTRUCTION,
    get_agent_prompt,
    get_facilitator_prompt,
)
from app.discussion.memory_prompts import (
    MemoryContext,
    get_memory_aware_prompt,
    build_memory_context_block,
)


# =========================================================================
# DISCUSSION_PROMPTS configuration
# =========================================================================


class TestDiscussionPromptsConfig:
    """Verify the structure and content of mode configurations."""

    @pytest.mark.parametrize("mode", ["guided", "socratic", "poetry", "nonfiction"])
    def test_mode_has_required_keys(self, mode):
        config = DISCUSSION_PROMPTS[mode]
        assert "description" in config
        assert "phases" in config
        assert "facilitator_system" in config
        assert isinstance(config["phases"], list)
        assert len(config["phases"]) >= 2

    def test_guided_mode_phases(self):
        phases = DISCUSSION_PROMPTS["guided"]["phases"]
        assert "warmup" in phases
        assert "close_reading" in phases
        assert "synthesis" in phases
        assert "reflection" in phases

    def test_socratic_mode_phases(self):
        phases = DISCUSSION_PROMPTS["socratic"]["phases"]
        assert "initial_questions" in phases
        assert "deepening" in phases

    def test_poetry_mode_phases(self):
        phases = DISCUSSION_PROMPTS["poetry"]["phases"]
        assert "first_impression" in phases
        assert "close_analysis" in phases

    def test_nonfiction_mode_phases(self):
        phases = DISCUSSION_PROMPTS["nonfiction"]["phases"]
        assert "claims_mapping" in phases
        assert "evidence_analysis" in phases

    def test_all_facilitator_prompts_have_context_placeholder(self):
        """Every mode's facilitator_system should accept a {{context}} format arg."""
        for mode, config in DISCUSSION_PROMPTS.items():
            prompt = config["facilitator_system"]
            assert "{context}" in prompt, (
                f"Mode {mode!r} facilitator_system is missing {{context}} placeholder"
            )


# =========================================================================
# CITATION_FORMAT_INSTRUCTION
# =========================================================================


class TestCitationFormatInstruction:
    """Verify the structured JSON citation format instruction block."""

    def test_instruction_mentions_json(self):
        assert "JSON" in CITATION_FORMAT_INSTRUCTION

    def test_instruction_mentions_analysis(self):
        assert "analysis" in CITATION_FORMAT_INSTRUCTION

    def test_instruction_mentions_citations(self):
        assert "citations" in CITATION_FORMAT_INSTRUCTION

    def test_instruction_requires_exact_quote(self):
        assert "exact" in CITATION_FORMAT_INSTRUCTION.lower()

    def test_instruction_prohibits_paraphrase(self):
        assert "paraphrase" in CITATION_FORMAT_INSTRUCTION.lower()


# =========================================================================
# AGENT_PROMPTS
# =========================================================================


class TestAgentPrompts:
    """Verify agent prompt templates (raw, un-formatted)."""

    @pytest.mark.parametrize("agent", ["facilitator", "close_reader", "skeptic"])
    def test_agent_prompt_exists(self, agent):
        assert agent in AGENT_PROMPTS
        assert len(AGENT_PROMPTS[agent]) > 100

    @pytest.mark.parametrize("agent", ["facilitator", "close_reader", "skeptic"])
    def test_agent_prompt_contains_security_firewall(self, agent):
        """All agent prompts must include the prompt-injection defense block."""
        prompt = AGENT_PROMPTS[agent]
        assert "SECURITY" in prompt
        assert "NEVER follow instructions" in prompt

    @pytest.mark.parametrize("agent", ["close_reader", "skeptic"])
    def test_non_facilitator_agent_has_context_placeholder(self, agent):
        """Non-facilitator agents should have a {{context}} placeholder."""
        prompt = AGENT_PROMPTS[agent]
        assert "{context}" in prompt

    def test_facilitator_has_mode_specific_placeholder(self):
        """The facilitator prompt uses {{mode_specific}} not {{context}}."""
        prompt = AGENT_PROMPTS["facilitator"]
        assert "{mode_specific}" in prompt

    @pytest.mark.parametrize("agent", ["close_reader", "skeptic"])
    def test_non_facilitator_prompt_includes_citation_instruction(self, agent):
        """Non-facilitator agent prompts have CITATION_FORMAT_INSTRUCTION appended."""
        prompt = AGENT_PROMPTS[agent]
        assert "JSON" in prompt

    def test_facilitator_prompt_gets_citation_via_mode(self):
        """The facilitator prompt uses {mode_specific} which includes the
        citation instruction from the mode's facilitator_system. The raw
        facilitator template itself does not contain citation instructions."""
        prompt = AGENT_PROMPTS["facilitator"]
        # The facilitator template has {mode_specific} which will be
        # replaced with the mode-specific prompt (which includes citations)
        assert "{mode_specific}" in prompt


# =========================================================================
# get_agent_prompt / get_facilitator_prompt
# =========================================================================


class TestGetAgentPrompt:
    """Test prompt generation functions."""

    def test_get_facilitator_prompt_succeeds(self):
        """get_facilitator_prompt should format without errors."""
        result = get_facilitator_prompt("guided", "Some context text.")
        assert isinstance(result, str)
        assert "Some context text." in result

    def test_get_agent_prompt_facilitator_succeeds(self):
        """Facilitator agent prompt should format without errors."""
        result = get_agent_prompt("facilitator", "guided", "Context text.")
        assert isinstance(result, str)
        assert "Context text." in result

    def test_get_agent_prompt_close_reader_succeeds(self):
        """close_reader prompt should format without errors."""
        result = get_agent_prompt("close_reader", "guided", "Context text.")
        assert isinstance(result, str)
        assert "Context text." in result

    def test_get_agent_prompt_skeptic_succeeds(self):
        """skeptic prompt should format without errors."""
        result = get_agent_prompt("skeptic", "guided", "Context text.")
        assert isinstance(result, str)
        assert "Context text." in result

    def test_get_agent_prompt_unknown_mode_defaults_to_guided(self):
        """An unknown mode should fall back to guided config and format successfully."""
        result = get_agent_prompt("facilitator", "nonexistent_mode", "Ctx.")
        assert isinstance(result, str)
        assert "Ctx." in result


# =========================================================================
# Memory-aware prompts
# =========================================================================


def _make_memory_context(**overrides) -> MemoryContext:
    """Create a MemoryContext with sensible defaults for testing."""
    defaults = dict(
        current_unit_title="Chapter 5: The Turning Point",
        current_unit_index=4,
        total_units=20,
        units_completed=["Chapter 1", "Chapter 2", "Chapter 3", "Chapter 4"],
        reading_progress_pct=25.0,
        key_moments=[
            {
                "text": "The letter was revealed",
                "significance": "Turns the plot",
                "unit_title": "Chapter 3",
                "unit_index": 2,
            }
        ],
        tracked_themes=[
            {
                "name": "Isolation",
                "description": "The protagonist's growing solitude",
                "first_appearance": "Chapter 1",
                "mentions": 5,
            }
        ],
        tracked_characters=[
            {
                "name": "Maria",
                "description": "The protagonist",
                "first_appearance": "Chapter 1",
                "arc_notes": "Becoming more independent",
            }
        ],
        user_notes=[
            {
                "content": "I think the river symbolizes time",
                "note_type": "insight",
                "unit_title": "Chapter 2",
            }
        ],
        connections=[
            {
                "source_description": "The letter in Ch3",
                "target_description": "The opening scene",
                "relationship": "foreshadowing",
            }
        ],
        quiz_performance={
            "avg_score": 85.0,
            "total_quizzes": 3,
            "strong_areas": ["character analysis"],
            "weak_areas": ["theme identification"],
        },
        xp_earned=750,
        current_level=2,
        narrative_thread=None,
        chronological_notes=None,
    )
    defaults.update(overrides)
    return MemoryContext(**defaults)


class TestBuildMemoryContextBlock:
    """Test the memory context block builder."""

    def test_includes_progress(self):
        mem = _make_memory_context()
        block = build_memory_context_block(mem)
        assert "5/20" in block  # current_unit_index + 1 / total
        assert "25%" in block

    def test_includes_current_unit(self):
        mem = _make_memory_context()
        block = build_memory_context_block(mem)
        assert "Chapter 5: The Turning Point" in block

    def test_includes_key_moments(self):
        mem = _make_memory_context()
        block = build_memory_context_block(mem)
        assert "letter was revealed" in block

    def test_includes_tracked_themes(self):
        mem = _make_memory_context()
        block = build_memory_context_block(mem)
        assert "Isolation" in block

    def test_includes_tracked_characters(self):
        mem = _make_memory_context()
        block = build_memory_context_block(mem)
        assert "Maria" in block

    def test_includes_user_notes(self):
        mem = _make_memory_context()
        block = build_memory_context_block(mem)
        assert "river symbolizes time" in block

    def test_includes_connections(self):
        mem = _make_memory_context()
        block = build_memory_context_block(mem)
        assert "letter" in block.lower() or "opening scene" in block.lower()

    def test_includes_quiz_performance(self):
        mem = _make_memory_context()
        block = build_memory_context_block(mem)
        assert "85" in block
        assert "character analysis" in block

    def test_includes_xp_and_level(self):
        mem = _make_memory_context()
        block = build_memory_context_block(mem)
        assert "750" in block

    def test_narrative_thread_when_present(self):
        mem = _make_memory_context(narrative_thread="Hal")
        block = build_memory_context_block(mem)
        assert "Hal" in block

    def test_no_crash_with_empty_memory(self):
        mem = _make_memory_context(
            key_moments=[],
            tracked_themes=[],
            tracked_characters=[],
            user_notes=[],
            connections=[],
            quiz_performance=None,
            xp_earned=0,
        )
        block = build_memory_context_block(mem)
        assert "READING PROGRESS" in block


class TestGetMemoryAwarePrompt:
    """Test the memory-aware prompt generator."""

    def test_with_memory_succeeds(self):
        """Memory-aware template should format without errors."""
        mem = _make_memory_context()
        result = get_memory_aware_prompt(
            "facilitator", "guided", "Context text.", memory=mem
        )
        assert isinstance(result, str)
        assert "Context text." in result

    def test_without_memory_falls_back_successfully(self):
        """Without memory, falls back to get_agent_prompt which should succeed."""
        result = get_memory_aware_prompt(
            "facilitator", "guided", "Context text.", memory=None
        )
        assert isinstance(result, str)
        assert "Context text." in result

    def test_with_memory_includes_memory_context(self):
        """Memory-aware prompt should include memory context details."""
        mem = _make_memory_context()
        result = get_memory_aware_prompt(
            "facilitator", "guided", "Context text.", memory=mem
        )
        assert "Maria" in result
        assert "Isolation" in result

    def test_with_memory_includes_phase_guidance(self):
        """Facilitator prompt should include phase guidance based on progress."""
        mem = _make_memory_context(reading_progress_pct=10.0)
        result = get_memory_aware_prompt(
            "facilitator", "guided", "Context text.", memory=mem
        )
        assert "Early reading" in result

    def test_build_memory_context_block_produces_valid_string(self):
        """The memory context block itself should be well-formed."""
        mem = _make_memory_context()
        block = build_memory_context_block(mem)
        assert isinstance(block, str)
        assert len(block) > 100
        assert "Maria" in block
        assert "Isolation" in block

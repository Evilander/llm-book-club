"""Tests for the sentence splitter used in voice choreography."""
import pytest

from app.discussion.sentence_splitter import SentenceSplitter


class TestSentenceSplitter:
    """Core sentence splitting behavior."""

    def test_single_sentence(self):
        splitter = SentenceSplitter(min_length=5)
        result = splitter.feed("Hello, world. ")
        assert result == ["Hello, world."]

    def test_two_sentences_in_one_delta(self):
        splitter = SentenceSplitter(min_length=5)
        result = splitter.feed("First sentence. Second sentence. ")
        assert result == ["First sentence.", "Second sentence."]

    def test_streaming_deltas(self):
        """Sentences split across multiple small deltas."""
        splitter = SentenceSplitter(min_length=5)
        all_sentences = []

        for delta in ["The door ", "was shut. ", "He paused", " for a moment. "]:
            all_sentences.extend(splitter.feed(delta))

        assert all_sentences == ["The door was shut.", "He paused for a moment."]

    def test_flush_remainder(self):
        splitter = SentenceSplitter(min_length=5)
        sentences = splitter.feed("Complete sentence. Incomplete part")
        assert sentences == ["Complete sentence."]

        remainder = splitter.flush()
        assert remainder == "Incomplete part"

    def test_flush_empty(self):
        splitter = SentenceSplitter(min_length=5)
        assert splitter.flush() is None

    def test_exclamation_and_question_marks(self):
        splitter = SentenceSplitter(min_length=5)
        result = splitter.feed("Wait, what?! Really! Yes. ")
        # "Wait, what?!" and "Really!" and "Yes." — but min_length=5
        assert "Wait, what?!" in result
        assert "Really!" in result

    def test_ellipsis(self):
        splitter = SentenceSplitter(min_length=5)
        result = splitter.feed("She trailed off... Then continued. ")
        assert result == ["She trailed off...", "Then continued."]

    def test_min_length_prevents_tiny_fragments(self):
        """Fragments shorter than min_length stay buffered."""
        splitter = SentenceSplitter(min_length=20)
        result = splitter.feed("OK. ")
        assert result == []  # "OK." is only 3 chars

        # The buffered "OK. " merges with new text.  The splitter finds
        # "OK." again but it's still < min_length, so it looks for the
        # next boundary.  The full candidate is long enough now.
        result = splitter.feed("That was a really good observation about the text. ")
        # Flush to get everything
        remainder = splitter.flush()
        # Between feed + flush we should get at least one sentence
        total = result + ([remainder] if remainder else [])
        assert len(total) >= 1
        combined = " ".join(total)
        assert "observation" in combined

    def test_abbreviations_not_split(self):
        """Mr., Dr., etc. should not cause a sentence split."""
        splitter = SentenceSplitter(min_length=5)
        result = splitter.feed("Mr. Smith went home. ")
        # Should NOT split at "Mr." — should emit "Mr. Smith went home."
        assert result == ["Mr. Smith went home."]

    def test_dr_abbreviation(self):
        splitter = SentenceSplitter(min_length=5)
        result = splitter.feed("Dr. Johnson examined the patient. ")
        assert result == ["Dr. Johnson examined the patient."]

    def test_sentence_index_increments(self):
        splitter = SentenceSplitter(min_length=5)
        splitter.feed("First. Second. Third. ")
        assert splitter.sentence_index == 3

    def test_sentence_index_includes_flush(self):
        splitter = SentenceSplitter(min_length=5)
        splitter.feed("First. Second")
        assert splitter.sentence_index == 1
        splitter.flush()
        assert splitter.sentence_index == 2


class TestForceBreak:
    """Run-on sentence protection."""

    def test_force_break_at_comma(self):
        splitter = SentenceSplitter(min_length=5, max_length=50)
        long_text = "a" * 30 + ", " + "b" * 30 + " "
        result = splitter.feed(long_text)
        assert len(result) >= 1
        # Should break at the comma, not in the middle of a word

    def test_force_break_at_space(self):
        splitter = SentenceSplitter(min_length=5, max_length=30)
        long_text = "word " * 10
        result = splitter.feed(long_text)
        assert len(result) >= 1


class TestQuotedText:
    """Sentences with quotes and brackets."""

    def test_closing_quote_after_period(self):
        splitter = SentenceSplitter(min_length=5)
        result = splitter.feed('"She left," he said. ')
        assert len(result) == 1
        assert '"She left," he said.' in result[0]

    def test_multiple_quoted_sentences(self):
        splitter = SentenceSplitter(min_length=5)
        result = splitter.feed('"First quote." "Second quote." ')
        assert len(result) == 2


class TestStreamingRealism:
    """Simulate realistic LLM streaming patterns."""

    def test_word_by_word_streaming(self):
        """LLMs often stream word-by-word or token-by-token."""
        splitter = SentenceSplitter(min_length=10)
        words = "The locked door stood before them silently. Nobody moved. ".split(" ")
        all_sentences = []
        for i, word in enumerate(words):
            delta = word + (" " if i < len(words) - 1 else "")
            all_sentences.extend(splitter.feed(delta))

        # Should get 2 sentences
        assert len(all_sentences) == 2
        assert "locked door" in all_sentences[0]
        assert "Nobody moved." in all_sentences[1]

    def test_character_by_character(self):
        """Edge case: character-by-character streaming."""
        splitter = SentenceSplitter(min_length=5)
        text = "Hello world. "
        all_sentences = []
        for ch in text:
            all_sentences.extend(splitter.feed(ch))

        assert all_sentences == ["Hello world."]

    def test_literary_passage(self):
        """A realistic literary discussion passage."""
        splitter = SentenceSplitter(min_length=15)
        passage = (
            "That repetition of 'shut' three times in two sentences is doing "
            "something powerful. It creates a rhythmic insistence that mirrors "
            "the character's desperation. Notice how the author never uses "
            "'closed' or 'locked' — the word 'shut' carries a finality that "
            "those alternatives lack. "
        )
        # Simulate chunked streaming (20-char chunks)
        all_sentences = []
        for i in range(0, len(passage), 20):
            chunk = passage[i:i+20]
            all_sentences.extend(splitter.feed(chunk))

        remainder = splitter.flush()
        if remainder:
            all_sentences.append(remainder)

        assert len(all_sentences) >= 3
        # Each sentence should be a meaningful unit
        for s in all_sentences:
            assert len(s) >= 15

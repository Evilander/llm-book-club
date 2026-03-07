"""
Quiz Generation System

Generates comprehension quizzes that test understanding at multiple levels:
- Recall: Basic "what happened" questions
- Understanding: "Why does this matter" questions
- Connection: Cross-chapter pattern recognition
- Analysis: Theme/character development questions

Integrates with BookMemory to adapt to reader's performance.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any
import json
import re
import logging

from pydantic import BaseModel

from ..providers.llm.base import LLMClient, LLMMessage

logger = logging.getLogger(__name__)


class QuizDifficulty(str, Enum):
    RECALL = "recall"
    UNDERSTANDING = "understanding"
    CONNECTION = "connection"
    ANALYSIS = "analysis"


class QuizQuestion(BaseModel):
    """A single quiz question."""
    question: str
    options: list[str]
    correct_index: int  # 0-3 for A-D
    explanation: str
    difficulty: QuizDifficulty
    references_passage: str | None = None  # chunk_id or unit reference
    char_start: int | None = None
    char_end: int | None = None


class Quiz(BaseModel):
    """A complete quiz."""
    unit_id: str
    unit_title: str
    questions: list[QuizQuestion]
    total_xp: int  # XP reward for perfect score


class QuizResult(BaseModel):
    """Result of a completed quiz."""
    quiz_id: str
    answers: list[int]  # User's answer indices
    correct_count: int
    total_count: int
    score_pct: float
    xp_earned: int
    explanations: list[str]  # Explanations for incorrect answers


@dataclass
class QuizContext:
    """Context for generating a quiz."""
    unit_text: str
    unit_title: str
    unit_id: str

    # Memory context
    key_moments: list[dict] | None = None
    tracked_themes: list[dict] | None = None
    previous_units: list[str] | None = None

    # Adaptation
    weak_areas: list[str] | None = None
    avg_score: float | None = None


class QuizGenerator:
    """
    Generates quizzes using LLM with structured output.
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def generate_quiz(
        self,
        context: QuizContext,
        num_questions: int = 5,
    ) -> Quiz:
        """
        Generate a quiz for a reading unit.

        Args:
            context: QuizContext with text and memory info
            num_questions: Number of questions to generate (3-7)

        Returns:
            Quiz object with questions
        """
        num_questions = max(3, min(7, num_questions))

        prompt = self._build_quiz_prompt(context, num_questions)

        try:
            response = await self.llm.complete(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.7,
            )

            questions = self._parse_quiz_response(response, context)

            # Calculate XP based on difficulty distribution
            total_xp = sum(self._xp_for_difficulty(q.difficulty) for q in questions)

            return Quiz(
                unit_id=context.unit_id,
                unit_title=context.unit_title,
                questions=questions,
                total_xp=total_xp,
            )

        except Exception as e:
            logger.error(f"Quiz generation failed: {e}")
            # Return a minimal fallback quiz
            return self._create_fallback_quiz(context)

    def _build_quiz_prompt(self, context: QuizContext, num_questions: int) -> str:
        """Build the prompt for quiz generation."""

        prompt_parts = [
            "Generate a comprehension quiz for this reading passage.",
            "",
            f"PASSAGE ({context.unit_title}):",
            context.unit_text[:8000],  # Limit text length
            "",
            "QUESTION REQUIREMENTS:",
            f"- Generate exactly {num_questions} questions",
            "- Include questions at different difficulty levels:",
            "  * RECALL (1-2): Test basic facts - who, what, where, when",
            "  * UNDERSTANDING (1-2): Test why things matter, cause/effect",
            "  * CONNECTION (1): Connect to patterns or earlier content",
            "  * ANALYSIS (1): Test deeper interpretation of themes/characters",
            "",
            "- Each question should have exactly 4 options (A, B, C, D)",
            "- One option should be clearly correct",
            "- Wrong options should be plausible but definitively wrong",
            "- Include an explanation for why the correct answer is right",
            "",
        ]

        # Add memory context for connection questions
        if context.previous_units:
            prompt_parts.extend([
                "PREVIOUSLY READ CONTENT (for connection questions):",
                ", ".join(context.previous_units[-5:]),
                "",
            ])

        if context.tracked_themes:
            theme_names = [t.get("name", "") for t in context.tracked_themes[:5]]
            prompt_parts.extend([
                "TRACKED THEMES (can reference in questions):",
                ", ".join(theme_names),
                "",
            ])

        if context.key_moments:
            prompt_parts.extend([
                "KEY MOMENTS TO POTENTIALLY REFERENCE:",
            ])
            for moment in context.key_moments[:3]:
                prompt_parts.append(f"- \"{moment.get('text', '')[:100]}...\"")
            prompt_parts.append("")

        # Add adaptation notes
        if context.weak_areas:
            prompt_parts.extend([
                "READER NEEDS MORE PRACTICE WITH:",
                ", ".join(context.weak_areas),
                "(Include more questions targeting these areas)",
                "",
            ])

        # Output format
        prompt_parts.extend([
            "OUTPUT FORMAT:",
            "Return a JSON array of question objects. Each object should have:",
            '{',
            '  "question": "The question text",',
            '  "options": ["A) option1", "B) option2", "C) option3", "D) option4"],',
            '  "correct": "A",',
            '  "explanation": "Why this answer is correct",',
            '  "difficulty": "recall|understanding|connection|analysis"',
            '}',
            "",
            "Return ONLY the JSON array, no other text.",
        ])

        return "\n".join(prompt_parts)

    def _parse_quiz_response(self, response: str, context: QuizContext) -> list[QuizQuestion]:
        """Parse the LLM response into QuizQuestion objects."""
        questions = []

        # Try to extract JSON from response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if not json_match:
            logger.warning("Could not find JSON array in quiz response")
            return []

        try:
            data = json.loads(json_match.group())

            for item in data:
                if not isinstance(item, dict):
                    continue

                # Map letter to index
                correct_letter = item.get("correct", "A").upper()
                correct_index = ord(correct_letter) - ord("A")
                correct_index = max(0, min(3, correct_index))

                # Map difficulty string to enum
                diff_str = item.get("difficulty", "recall").lower()
                try:
                    difficulty = QuizDifficulty(diff_str)
                except ValueError:
                    difficulty = QuizDifficulty.RECALL

                questions.append(QuizQuestion(
                    question=item.get("question", ""),
                    options=item.get("options", ["A", "B", "C", "D"]),
                    correct_index=correct_index,
                    explanation=item.get("explanation", ""),
                    difficulty=difficulty,
                ))

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse quiz JSON: {e}")

        return questions

    def _xp_for_difficulty(self, difficulty: QuizDifficulty) -> int:
        """Get XP reward for a question difficulty."""
        return {
            QuizDifficulty.RECALL: 10,
            QuizDifficulty.UNDERSTANDING: 20,
            QuizDifficulty.CONNECTION: 30,
            QuizDifficulty.ANALYSIS: 40,
        }.get(difficulty, 10)

    def _create_fallback_quiz(self, context: QuizContext) -> Quiz:
        """Create a minimal fallback quiz if generation fails."""
        return Quiz(
            unit_id=context.unit_id,
            unit_title=context.unit_title,
            questions=[
                QuizQuestion(
                    question="What was this section primarily about?",
                    options=[
                        "A) The main narrative events",
                        "B) Background information",
                        "C) Character introductions",
                        "D) Setting descriptions",
                    ],
                    correct_index=0,
                    explanation="This is a general comprehension question.",
                    difficulty=QuizDifficulty.RECALL,
                )
            ],
            total_xp=10,
        )

    def grade_quiz(self, quiz: Quiz, answers: list[int]) -> QuizResult:
        """
        Grade a completed quiz.

        Args:
            quiz: The Quiz object
            answers: List of answer indices (0-3) for each question

        Returns:
            QuizResult with score and XP
        """
        correct_count = 0
        explanations = []
        xp_earned = 0

        for i, (question, answer) in enumerate(zip(quiz.questions, answers)):
            if answer == question.correct_index:
                correct_count += 1
                xp_earned += self._xp_for_difficulty(question.difficulty)
            else:
                explanations.append(
                    f"Q{i+1}: {question.explanation}"
                )

        score_pct = (correct_count / len(quiz.questions) * 100) if quiz.questions else 0

        # Bonus XP for perfect score
        if correct_count == len(quiz.questions) and len(quiz.questions) >= 3:
            xp_earned += 25

        return QuizResult(
            quiz_id=quiz.unit_id,
            answers=answers,
            correct_count=correct_count,
            total_count=len(quiz.questions),
            score_pct=score_pct,
            xp_earned=xp_earned,
            explanations=explanations,
        )


class AdaptiveQuizGenerator(QuizGenerator):
    """
    Quiz generator that adapts to reader's performance history.
    """

    def __init__(self, llm_client: LLMClient):
        super().__init__(llm_client)

    async def generate_adaptive_quiz(
        self,
        context: QuizContext,
        quiz_history: list[dict] | None = None,
    ) -> Quiz:
        """
        Generate a quiz adapted to the reader's history.

        Analyzes past performance to:
        - Focus on weak areas
        - Adjust difficulty based on average scores
        - Include more connection questions for strong readers
        """
        if quiz_history:
            # Analyze performance
            weak_areas = self._identify_weak_areas(quiz_history)
            avg_score = self._calculate_avg_score(quiz_history)

            context.weak_areas = weak_areas
            context.avg_score = avg_score

            # Adjust number of questions based on performance
            if avg_score and avg_score > 85:
                # Strong reader - more challenging quiz
                num_questions = 5
            elif avg_score and avg_score < 60:
                # Struggling - shorter, focused quiz
                num_questions = 3
            else:
                num_questions = 4
        else:
            num_questions = 4

        return await self.generate_quiz(context, num_questions)

    def _identify_weak_areas(self, history: list[dict]) -> list[str]:
        """Identify difficulty levels where reader struggles."""
        difficulty_scores = {}

        for quiz in history:
            for q in quiz.get("questions", []):
                diff = q.get("difficulty", "recall")
                correct = q.get("was_correct", False)

                if diff not in difficulty_scores:
                    difficulty_scores[diff] = {"correct": 0, "total": 0}

                difficulty_scores[diff]["total"] += 1
                if correct:
                    difficulty_scores[diff]["correct"] += 1

        weak_areas = []
        for diff, scores in difficulty_scores.items():
            if scores["total"] >= 2:
                pct = scores["correct"] / scores["total"] * 100
                if pct < 60:
                    weak_areas.append(diff)

        return weak_areas

    def _calculate_avg_score(self, history: list[dict]) -> float | None:
        """Calculate average quiz score."""
        scores = [q.get("score_pct", 0) for q in history if "score_pct" in q]
        return sum(scores) / len(scores) if scores else None


# =============================================================================
# QUICK COMPREHENSION CHECK
# =============================================================================

class ComprehensionChecker:
    """
    Generates quick comprehension checks during reading.
    These are lighter than full quizzes - just 1-2 questions to keep reader engaged.
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def generate_quick_check(
        self,
        passage: str,
        passage_context: str | None = None,
    ) -> QuizQuestion:
        """
        Generate a single quick comprehension question.

        Args:
            passage: The specific passage just read (500-2000 chars)
            passage_context: Brief context about what came before

        Returns:
            A single QuizQuestion
        """
        prompt = f"""Generate ONE quick comprehension question for this passage:

"{passage[:1500]}"

Requirements:
- Test understanding, not trivial recall
- Question should be answerable from this passage alone
- 4 options, one clearly correct
- Brief explanation

Return JSON:
{{
  "question": "...",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct": "A",
  "explanation": "..."
}}"""

        try:
            response = await self.llm.complete(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.7,
            )

            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())

                correct_letter = data.get("correct", "A").upper()
                correct_index = ord(correct_letter) - ord("A")

                return QuizQuestion(
                    question=data.get("question", ""),
                    options=data.get("options", []),
                    correct_index=max(0, min(3, correct_index)),
                    explanation=data.get("explanation", ""),
                    difficulty=QuizDifficulty.UNDERSTANDING,
                )

        except Exception as e:
            logger.error(f"Quick check generation failed: {e}")

        # Fallback
        return QuizQuestion(
            question="What was the main point of this passage?",
            options=[
                "A) To advance the narrative",
                "B) To develop a character",
                "C) To establish setting",
                "D) To introduce a theme",
            ],
            correct_index=0,
            explanation="General comprehension question.",
            difficulty=QuizDifficulty.RECALL,
        )


# =============================================================================
# FACTORY
# =============================================================================

def get_quiz_generator(llm_client: LLMClient, adaptive: bool = True) -> QuizGenerator:
    """Get a quiz generator instance."""
    if adaptive:
        return AdaptiveQuizGenerator(llm_client)
    return QuizGenerator(llm_client)

"""
Gamification Service

Handles XP calculations, level progression, achievements, and streaks.

XP System:
- Reading units: 50-100 XP based on length
- Quizzes: Up to 100 XP based on score
- Key moments: 5 XP each
- Notes: 2-15 XP based on type
- Connections: 20 XP each
- Achievements: 50-500 XP bonus

Levels:
- Level up every 500 XP
- Level 1: 0 XP
- Level 2: 500 XP
- Level 10: 4500 XP
- etc.

Achievements:
- FIRST_INSIGHT: First insight note
- BOOKWORM_7: 7-day reading streak
- COMPLETIONIST: Finish a book
- etc.
"""

from datetime import date, timedelta
from dataclasses import dataclass
from sqlalchemy.orm import Session

from ..db.models import (
    BookMemory, ReadingUnit, DailyActivity, UserNote, KeyMoment,
    Connection, QuizResult, AchievementType, NoteType,
)


@dataclass
class LevelInfo:
    """Information about a player's level."""
    level: int
    current_xp: int
    xp_for_current_level: int
    xp_for_next_level: int
    progress_pct: float


@dataclass
class AchievementProgress:
    """Progress toward an achievement."""
    achievement: AchievementType
    name: str
    description: str
    xp_reward: int
    is_unlocked: bool
    progress: int
    target: int
    progress_pct: float


ACHIEVEMENT_DEFINITIONS = {
    AchievementType.FIRST_INSIGHT: {
        "name": "First Insight",
        "description": "Record your first insight about the text",
        "xp_reward": 50,
        "target": 1,
    },
    AchievementType.BOOKWORM_7: {
        "name": "Bookworm",
        "description": "Read for 7 days in a row",
        "xp_reward": 100,
        "target": 7,
    },
    AchievementType.BOOKWORM_30: {
        "name": "Dedicated Reader",
        "description": "Read for 30 days in a row",
        "xp_reward": 300,
        "target": 30,
    },
    AchievementType.COMPLETIONIST: {
        "name": "Completionist",
        "description": "Finish reading an entire book",
        "xp_reward": 500,
        "target": 1,
    },
    AchievementType.SPEED_READER: {
        "name": "Speed Reader",
        "description": "Complete 5 reading units in one day",
        "xp_reward": 75,
        "target": 5,
    },
    AchievementType.NIGHT_OWL: {
        "name": "Night Owl",
        "description": "Read after midnight",
        "xp_reward": 25,
        "target": 1,
    },
    AchievementType.EARLY_BIRD: {
        "name": "Early Bird",
        "description": "Read before 6 AM",
        "xp_reward": 25,
        "target": 1,
    },
    AchievementType.MARATHON_READER: {
        "name": "Marathon Reader",
        "description": "Read for 2 hours in a single session",
        "xp_reward": 100,
        "target": 120,  # minutes
    },
    AchievementType.QUIZ_MASTER: {
        "name": "Quiz Master",
        "description": "Score 100% on 5 quizzes",
        "xp_reward": 150,
        "target": 5,
    },
    AchievementType.DEEP_READER: {
        "name": "Deep Reader",
        "description": "Mark 20 key moments",
        "xp_reward": 75,
        "target": 20,
    },
    AchievementType.CONNECTION_HUNTER: {
        "name": "Connection Hunter",
        "description": "Find 10 cross-chapter connections",
        "xp_reward": 100,
        "target": 10,
    },
    AchievementType.THEME_TRACKER: {
        "name": "Theme Tracker",
        "description": "Track 5 different themes",
        "xp_reward": 50,
        "target": 5,
    },
}


class GamificationService:
    """Service for handling gamification logic."""

    XP_PER_LEVEL = 500

    def __init__(self, db: Session):
        self.db = db

    def get_level_info(self, xp: int) -> LevelInfo:
        """Calculate level info from XP."""
        level = 1 + (xp // self.XP_PER_LEVEL)
        xp_in_level = xp % self.XP_PER_LEVEL
        xp_for_current = (level - 1) * self.XP_PER_LEVEL
        xp_for_next = level * self.XP_PER_LEVEL

        return LevelInfo(
            level=level,
            current_xp=xp,
            xp_for_current_level=xp_for_current,
            xp_for_next_level=xp_for_next,
            progress_pct=(xp_in_level / self.XP_PER_LEVEL * 100),
        )

    def calculate_reading_xp(self, unit: ReadingUnit) -> int:
        """Calculate XP for completing a reading unit."""
        base_xp = 50

        # Bonus for longer units (up to +50)
        reading_time = unit.reading_time_min or 10
        time_bonus = min(50, reading_time * 2)

        # Bonus for higher complexity (based on token count)
        tokens = unit.token_estimate or 5000
        complexity_bonus = min(25, tokens // 1000)

        return base_xp + time_bonus + complexity_bonus

    def calculate_quiz_xp(self, score_pct: float, num_questions: int) -> int:
        """Calculate XP for a quiz based on score."""
        base_xp = 10 * num_questions
        score_multiplier = score_pct / 100

        xp = int(base_xp * score_multiplier)

        # Perfect score bonus
        if score_pct == 100:
            xp += 25

        return xp

    def calculate_note_xp(self, note_type: NoteType) -> int:
        """Calculate XP for creating a note."""
        return {
            NoteType.HIGHLIGHT: 2,
            NoteType.NOTE: 5,
            NoteType.QUESTION: 5,
            NoteType.INSIGHT: 10,
            NoteType.CONNECTION: 15,
        }.get(note_type, 5)

    def get_current_streak(self, memory: BookMemory) -> int:
        """Calculate current reading streak in days."""
        today = date.today()

        activities = self.db.query(DailyActivity).filter(
            DailyActivity.memory_id == memory.id
        ).order_by(DailyActivity.date.desc()).limit(60).all()

        if not activities:
            return 0

        streak = 0
        expected_date = today

        for activity in activities:
            if activity.date == expected_date:
                streak += 1
                expected_date -= timedelta(days=1)
            elif activity.date < expected_date:
                # Gap in streak
                break

        return streak

    def check_achievements(self, memory: BookMemory) -> list[AchievementType]:
        """
        Check all achievements and return newly unlocked ones.
        Updates memory.achievements_unlocked.
        """
        unlocked = set(memory.achievements_unlocked or [])
        newly_unlocked = []

        # Check each achievement
        for achievement, definition in ACHIEVEMENT_DEFINITIONS.items():
            if achievement.value in unlocked:
                continue

            progress = self._get_achievement_progress(memory, achievement)
            target = definition["target"]

            if progress >= target:
                newly_unlocked.append(achievement)
                unlocked.add(achievement.value)

        # Update memory
        if newly_unlocked:
            memory.achievements_unlocked = list(unlocked)
            # Award bonus XP
            bonus_xp = sum(
                ACHIEVEMENT_DEFINITIONS[a]["xp_reward"]
                for a in newly_unlocked
            )
            memory.xp_earned = (memory.xp_earned or 0) + bonus_xp
            self.db.commit()

        return newly_unlocked

    def _get_achievement_progress(
        self,
        memory: BookMemory,
        achievement: AchievementType,
    ) -> int:
        """Get current progress toward an achievement."""

        if achievement == AchievementType.FIRST_INSIGHT:
            return self.db.query(UserNote).filter(
                UserNote.memory_id == memory.id,
                UserNote.note_type == NoteType.INSIGHT,
            ).count()

        elif achievement in (AchievementType.BOOKWORM_7, AchievementType.BOOKWORM_30):
            return self.get_current_streak(memory)

        elif achievement == AchievementType.COMPLETIONIST:
            total_units = self.db.query(ReadingUnit).filter(
                ReadingUnit.book_id == memory.book_id
            ).count()
            completed = len(memory.units_completed or [])
            return 1 if completed >= total_units and total_units > 0 else 0

        elif achievement == AchievementType.SPEED_READER:
            today = date.today()
            activity = self.db.query(DailyActivity).filter(
                DailyActivity.memory_id == memory.id,
                DailyActivity.date == today,
            ).first()
            return activity.units_completed if activity else 0

        elif achievement == AchievementType.MARATHON_READER:
            # Would need session tracking - for now just check daily total
            today = date.today()
            activity = self.db.query(DailyActivity).filter(
                DailyActivity.memory_id == memory.id,
                DailyActivity.date == today,
            ).first()
            return activity.reading_time_min if activity else 0

        elif achievement == AchievementType.QUIZ_MASTER:
            return self.db.query(QuizResult).filter(
                QuizResult.memory_id == memory.id,
                QuizResult.score_pct == 100,
            ).count()

        elif achievement == AchievementType.DEEP_READER:
            return self.db.query(KeyMoment).filter(
                KeyMoment.memory_id == memory.id,
            ).count()

        elif achievement == AchievementType.CONNECTION_HUNTER:
            return self.db.query(Connection).filter(
                Connection.memory_id == memory.id,
            ).count()

        elif achievement == AchievementType.THEME_TRACKER:
            from ..db.models import TrackedTheme
            return self.db.query(TrackedTheme).filter(
                TrackedTheme.memory_id == memory.id,
            ).count()

        return 0

    def get_all_achievement_progress(
        self,
        memory: BookMemory,
    ) -> list[AchievementProgress]:
        """Get progress for all achievements."""
        unlocked = set(memory.achievements_unlocked or [])
        progress_list = []

        for achievement, definition in ACHIEVEMENT_DEFINITIONS.items():
            progress = self._get_achievement_progress(memory, achievement)
            target = definition["target"]

            progress_list.append(AchievementProgress(
                achievement=achievement,
                name=definition["name"],
                description=definition["description"],
                xp_reward=definition["xp_reward"],
                is_unlocked=achievement.value in unlocked,
                progress=progress,
                target=target,
                progress_pct=min(100, progress / target * 100),
            ))

        return progress_list

    def award_xp(self, memory: BookMemory, amount: int, reason: str = None) -> int:
        """
        Award XP to a reader.

        Returns the new total XP.
        """
        memory.xp_earned = (memory.xp_earned or 0) + amount
        self.db.commit()

        # Check for level-up achievements etc.
        self.check_achievements(memory)

        return memory.xp_earned


# =============================================================================
# STREAK BONUSES
# =============================================================================

def calculate_streak_multiplier(streak: int) -> float:
    """Calculate XP multiplier based on streak."""
    if streak >= 30:
        return 2.0
    elif streak >= 14:
        return 1.5
    elif streak >= 7:
        return 1.25
    elif streak >= 3:
        return 1.1
    return 1.0


def get_streak_message(streak: int) -> str:
    """Get an encouraging message based on streak."""
    if streak == 0:
        return "Start your reading streak today!"
    elif streak == 1:
        return "Day 1 of your streak. Keep it going!"
    elif streak < 7:
        return f"{streak} day streak! You're building momentum."
    elif streak == 7:
        return "One week streak! You've earned the Bookworm achievement!"
    elif streak < 30:
        return f"{streak} day streak! You're on fire!"
    elif streak == 30:
        return "30 day streak! You've earned Dedicated Reader!"
    else:
        return f"Incredible {streak} day streak! You're a reading champion!"

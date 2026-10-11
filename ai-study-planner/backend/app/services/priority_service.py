"""Priority scoring.

priority = 0.35*urgency + 0.30*weakness + 0.15*difficulty + 0.10*importance + 0.10*history   (all terms 0..1)

Because the weights sum to 1 and every term is normalised to 0..1, the score is itself normalised (0..1).
Levels: >=0.60 critical, >=0.45 high, >=0.30 medium, else low.
"""
import math
from dataclasses import dataclass
from datetime import date

WEIGHTS = {"urgency": 0.35, "weakness": 0.30, "difficulty": 0.15, "importance": 0.10, "history": 0.10}
LEVELS = [(0.60, "critical"), (0.45, "high"), (0.30, "medium")]
LEVEL_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Priority:
    score: float
    level: str
    urgency: float
    weakness: float
    difficulty: float
    importance: float
    history: float
    days_left: int | None


def urgency(days_left: int | None) -> float:
    """1.0 on exam day, ~0.61 a week out, ~0.37 two weeks out, ~0.12 a month out."""
    if days_left is None:
        return 0.1
    if days_left <= 0:
        return 1.0
    return math.exp(-days_left / 14)


def target_mastery(target_marks: int) -> int:
    return int(min(95, max(50, target_marks)))


def weakness(mastery: int, target_marks: int) -> float:
    tm = target_mastery(target_marks)
    gap = max(0, tm - mastery) / tm
    return clamp(0.6 * (1 - mastery / 100) + 0.4 * gap)


def history_term(miss_count: int, last_studied: date | None, today: date) -> float:
    stale = 0.3 if (last_studied is None or (today - last_studied).days > 7) else 0.0
    return clamp(miss_count * 0.25 + stale)


def level_for(score: float) -> str:
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return "low"


def compute(*, mastery: int, topic_difficulty: int, subject_importance: int, target_marks: int, miss_count: int,
            last_studied: date | None, exam_date: date | None, on_date: date, focus_boost: bool = False) -> Priority:
    days_left = (exam_date - on_date).days if exam_date else None
    u = urgency(days_left)
    w = weakness(mastery, target_marks)
    d = (topic_difficulty - 1) / 4
    i = 0.7 * (subject_importance - 1) / 4 + 0.3 * target_marks / 100
    h = history_term(miss_count, last_studied, on_date)
    score = (WEIGHTS["urgency"] * u + WEIGHTS["weakness"] * w + WEIGHTS["difficulty"] * d
             + WEIGHTS["importance"] * i + WEIGHTS["history"] * h)
    if focus_boost:
        score += 0.15
    score = clamp(score)
    return Priority(round(score, 4), level_for(score), u, w, d, i, h, days_left)


def minutes_needed(mastery: int, difficulty: int, target_marks: int) -> int:
    """Study minutes still needed to bring a topic from its current mastery to the target (0 if already there)."""
    tm = target_mastery(target_marks)
    if mastery >= tm:
        return 0
    base = 60 + 30 * (difficulty - 1)            # 60..180 min for a full learn of a topic
    gap = (tm - mastery) / tm
    return max(20, int(round(base * (0.2 + 0.8 * gap) / 5) * 5))


def explain(p: Priority, mastery: int, difficulty: int, miss_count: int) -> str:
    bits = []
    if p.days_left is not None and p.days_left <= 30:
        bits.append("exam today" if p.days_left <= 0 else f"exam in {p.days_left} day{'s' if p.days_left != 1 else ''}")
    bits.append(f"{mastery}% mastery")
    if difficulty >= 4:
        bits.append("hard topic")
    if miss_count:
        bits.append(f"missed {miss_count}×")
    return " · ".join(bits)


def mastery_label(mastery: int) -> str:
    return "strong" if mastery >= 70 else "medium" if mastery >= 45 else "weak"

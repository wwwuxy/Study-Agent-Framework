"""Thin, deterministic wrapper around the complete upstream FSRS scheduler."""

import secrets
from dataclasses import dataclass
from datetime import datetime

from fsrs import Card, Rating, Scheduler

from app.learner.parameters import FSRSParameters


@dataclass(frozen=True)
class FSRSUpdate:
    card: dict
    log: dict
    rating: int
    reason: str


def scheduler(configuration=None):
    configuration = configuration or FSRSParameters()
    return Scheduler(
        parameters=configuration.parameters,
        enable_fuzzing=False,
        desired_retention=configuration.desired_retention,
    )


def new_card(now: datetime) -> dict:
    return Card(card_id=secrets.randbits(52), due=now).to_dict()


def review_card(
    card: dict, rating: int, now: datetime, duration_ms: int | None = None, configuration=None
) -> FSRSUpdate:
    updated, log = scheduler(configuration).review_card(
        Card.from_dict(card), Rating(rating), now, duration_ms
    )
    return FSRSUpdate(updated.to_dict(), log.to_dict(), rating, Rating(rating).name)


def memory_view(card: dict, now: datetime, configuration=None) -> dict:
    restored = Card.from_dict(card)
    assessed = restored.last_review is not None
    return {
        "status": ("due" if restored.due <= now else "upcoming") if assessed else "unassessed",
        "due": restored.due.isoformat(),
        "state": restored.state.name,
        "stability": restored.stability,
        "difficulty": restored.difficulty,
        "last_review": restored.last_review.isoformat() if assessed else None,
        "retrievability": scheduler(configuration).get_card_retrievability(restored, now)
        if assessed
        else None,
    }

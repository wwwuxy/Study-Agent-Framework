from datetime import UTC, datetime, timedelta

import pytest
from fsrs import Card, Rating, Scheduler


@pytest.mark.parametrize("rating", [1, 2, 3, 4])
def test_fsrs_adapter_matches_native_for_all_ratings_and_json_restore(rating):
    from app.reviews.fsrs_adapter import memory_view, new_card, review_card

    now = datetime(2026, 1, 1, tzinfo=UTC)
    serialized = new_card(now)
    native = Card.from_dict(serialized)
    expected, native_log = Scheduler(enable_fuzzing=False).review_card(native, Rating(rating), now)
    actual = review_card(serialized, rating, now)
    assert actual.card == expected.to_dict()
    assert actual.log["rating"] == native_log.rating.value
    view = memory_view(actual.card, now)
    assert view["due"] == expected.due.isoformat()
    assert memory_view(serialized, now)["status"] == "unassessed"
    # Persist/reload and progress through learning, review and forgetting.
    for delta in [timedelta(minutes=15), timedelta(days=2), timedelta(days=90)]:
        now += delta
        native_again, _ = Scheduler(enable_fuzzing=False).review_card(expected, Rating.Good, now)
        actual = review_card(actual.card, 3, now)
        assert actual.card == native_again.to_dict()
        expected = native_again
    now += timedelta(days=1)
    native_lapse, _ = Scheduler(enable_fuzzing=False).review_card(expected, Rating.Again, now)
    actual = review_card(actual.card, 1, now)
    assert actual.card == native_lapse.to_dict()
    assert memory_view(actual.card, now)["state"] == "Relearning"


def test_minute_step_is_not_rounded_to_a_day():
    from app.reviews.fsrs_adapter import new_card, review_card

    now = datetime(2026, 1, 1, tzinfo=UTC)
    result = review_card(new_card(now), 1, now)
    assert datetime.fromisoformat(result.card["due"]) - now < timedelta(days=1)

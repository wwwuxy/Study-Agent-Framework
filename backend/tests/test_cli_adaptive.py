from datetime import timedelta

from sqlalchemy import select
from test_cli import cli, setup_space  # noqa: F401, F811

from app.db.models import ReviewState, utcnow


def test_cli_algorithms_report_and_full_review_roundtrip(cli, client):  # noqa: F811
    _, sid = setup_space(cli)
    code, algorithms, _ = cli("algorithms")
    assert code == 0 and algorithms["bkt"]["enabled"] and algorithms["fsrs"]["enabled"]
    assert cli("report", "--days", "7")[1]["task_completion"]["rate"] is None
    q = next(q for q in cli("diagnose")[1]["items"] if q["concept_keys"] == ["os"])
    assert cli("answer", q["id"], "--answer", "A")[0] == 0
    with client.app.state.session_factory() as db:
        row = db.scalar(
            select(ReviewState).where(ReviewState.space_id == sid, ReviewState.concept_id == "os")
        )
        due = utcnow() - timedelta(minutes=1)
        row.due, row.card = due, {**row.card, "due": due.isoformat()}
        db.commit()
    assert cli("review", "list")[1]["due"][0]["concept_id"] == "os"
    code, review, _ = cli("review", "start", "--concept", "os", "--request-id", "cli-review")
    assert code == 0
    item = review["lesson"]["exercises"][0]
    args = (
        "review",
        "submit",
        review["id"],
        "--item",
        item["id"],
        "--answer",
        "A",
        "--rating",
        "hard",
        "--request-id",
        "cli-reviewed",
    )
    code, result, _ = cli(*args)
    assert code == 0 and result["memory"]["rating"] == 2
    assert cli(*args)[1] == result
    assert cli("report", "--days", "30")[1]["review_retention"]["denominator"] == 1
    code, text, _ = cli("algorithms", json_output=False)
    assert code == 0 and "BKT" in text and "FSRS" in text

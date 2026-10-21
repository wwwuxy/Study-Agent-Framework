from conftest import provider, register, space


def test_empty_report_has_no_fake_percentages_and_reads_are_side_effect_free(client):
    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    before = client.get(root + "/events").json()
    result = client.get(root + "/report?days=7")
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["distribution"] == {"unknown": 3, "learning": 0, "mastered": 0}
    assert data["task_completion"]["rate"] is None
    assert data["review_retention"]["rate"] is None
    assert data["algorithms"]["bkt"]["enabled"] and data["algorithms"]["fsrs"]["enabled"]
    assert client.get(root + "/report?days=31").status_code == 422
    assert client.get(root + "/events").json() == before
    assert client.get(root + "/algorithms").json()["calibration_status"] == "uncalibrated"


def test_qmatrix_hides_answers_and_report_counts_real_evidence(client):
    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    q = client.post(root + "/diagnostics").json()["items"][0]
    client.post(root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": "a"})
    matrix = client.get(root + "/q-matrix").json()
    assert len(matrix["items"]) == 5
    assert all("answer" not in row and "rubric" not in row for row in matrix["items"])
    report = client.get(root + "/report?days=30").json()
    assert report["evidence"]["answers"] == 1
    assert report["distribution"]["learning"] == 1
    assert report["next_action"]["concept_ids"] == client.get(root + "/next-action").json()["concept_ids"]


def test_report_shows_recent_errors_without_exposing_answer(client):
    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    q = client.post(root + "/diagnostics").json()["items"][0]
    assert (
        client.post(
            root + "/attempts", json={"item_id": q["id"], "answer": "B", "idempotency_key": "wrong"}
        ).status_code
        == 201
    )
    report = client.get(root + "/report").json()
    assert report["error_concepts"][0]["concept_id"] == q["concept_keys"][0]
    assert report["error_concepts"][0]["count"] == 1
    assert "answer" not in report["error_concepts"][0]

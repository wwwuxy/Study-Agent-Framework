from .test_uploads import create, put


def test_foreign_account_cannot_access_any_exam_resource(exam_env, pdf_bytes):
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    exam_env.client.post("/api/v1/auth/logout")
    assert (
        exam_env.client.post(
            "/api/v1/auth/register", json={"username": "bob", "password": "strong-password-2026"}
        ).status_code
        == 201
    )
    paths = [
        "",
        "/" + row["id"],
        "/" + row["id"] + "/attachments/" + row["attachments"][0]["id"] + "/download",
        "/capabilities",
    ]
    for path in paths:
        assert exam_env.client.get(exam_env.root + path).status_code == 404
    for action in ["start", "retry", "cancel"]:
        assert (
            exam_env.client.post(
                exam_env.root + "/" + row["id"] + "/" + action, json={"consent": True, "idempotency_key": "s"}
            ).status_code
            == 404
        )

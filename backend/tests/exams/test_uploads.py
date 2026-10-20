import hashlib


def create(env, content, filename="paper.pdf", mime="application/pdf", key="draft1"):
    response = env.client.post(
        env.root,
        json={
            "name": "测试卷",
            "idempotency_key": key,
            "attachments": [
                {
                    "client_id": "a1",
                    "filename": filename,
                    "mime_type": mime,
                    "size_bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def put(env, row, content, mime="application/pdf"):
    return env.client.put(
        env.root + "/" + row["id"] + "/attachments/" + row["attachments"][0]["id"],
        content=content,
        headers={"content-type": mime},
    )


def test_partial_upload_never_becomes_ready(exam_env, pdf_bytes):
    row = create(exam_env, pdf_bytes)
    assert row["status"] == "draft" and not row["attachments"][0]["received"]
    response = put(exam_env, row, pdf_bytes)
    assert response.status_code == 200, response.text
    assert response.json()["attachments"][0]["received"]
    assert put(exam_env, row, pdf_bytes).status_code == 200


def test_forged_manifest_hash_never_reuses_report(exam_env, pdf_bytes):
    row = create(exam_env, pdf_bytes)
    response = put(exam_env, row, pdf_bytes + b"changed")
    assert response.status_code == 422
    current = exam_env.client.get(exam_env.root + "/" + row["id"]).json()
    assert not current["attachments"][0]["received"]


def test_format_size_and_image_pixel_limits(exam_env, image_bytes):
    row = create(exam_env, image_bytes, "a.png", "image/png")
    assert put(exam_env, row, image_bytes, "image/png").status_code == 200
    bad = create(exam_env, b"not-an-image", "b.png", "image/png", "bad")
    assert put(exam_env, bad, b"not-an-image", "image/png").status_code == 422

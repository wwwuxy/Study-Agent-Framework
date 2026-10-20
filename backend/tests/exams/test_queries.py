from .test_uploads import create, put


def test_download_and_draft_discard(exam_env, pdf_bytes):
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    url = exam_env.root + "/" + row["id"] + "/attachments/" + row["attachments"][0]["id"] + "/download"
    response = exam_env.client.get(url)
    assert response.content == pdf_bytes
    assert "attachment" in response.headers["content-disposition"]
    assert exam_env.client.delete(exam_env.root + "/" + row["id"] + "/draft").status_code == 204
    assert exam_env.client.get(url).status_code == 404


def test_cursor_does_not_repeat_rows(exam_env, pdf_bytes):
    create(exam_env, pdf_bytes, key="1")
    create(exam_env, pdf_bytes, key="2")
    first = exam_env.client.get(exam_env.root + "?limit=1").json()
    second = exam_env.client.get(exam_env.root + "?limit=1&before=" + first["next_cursor"]).json()
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert exam_env.client.get(exam_env.root + "?before=invalid").status_code == 422
